"""Logo animation controller with keyboard interrupt handling."""

import math
import os
import time
from typing import Callable, Optional

from rich.console import Console
from rich.text import Text

from .logo_config import AnimationSpeed, LogoConfig, get_logo_config
from .logo_effects import (
    ease_in_out,
    effect_fade_in,
    effect_reveal_lines,
    get_palette,
    random_scheme,
    split_lines,
)

console = Console()


def load_ascii_art(filename: str = "tiger.txt") -> str:
    """Load ASCII art from file in project root."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(base_dir, "..", "..")
    filepath = os.path.join(project_root, filename)

    try:
        with open(filepath, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return """       (Ferrox Tiger Art Missing)"""


class AnimationController:
    """Controls logo animation with skip support."""

    def __init__(self, config: Optional[LogoConfig] = None):
        self.config = config or get_logo_config()
        self._skipped = False
        self._start_time: Optional[float] = None
        self._ascii_art: Optional[str] = None
        self._lines: Optional[list[str]] = None

    def _check_timeout(self) -> bool:
        """Check if animation exceeded max duration."""
        if self._start_time is None:
            return False
        elapsed = time.time() - self._start_time
        return elapsed >= self.config.max_duration_sec

    def _should_continue(self) -> bool:
        """Check if animation should continue."""
        if self._skipped:
            return False
        if self.config._interrupted:
            return False
        return not self._check_timeout()

    def _prepare_art(self) -> list[str]:
        """Load and prepare ASCII art lines."""
        if self._lines is None:
            art = self._ascii_art or load_ascii_art("ascii-art.txt")
            lines = split_lines(art)
            # Strip leading empty lines and limit height
            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()
            # Limit to reasonable height for animation
            if len(lines) > 40:
                lines = lines[:40]
            self._lines = lines
        return self._lines

    def _get_palette(self):
        """Get the color palette for animation."""
        scheme = random_scheme() if self.config.random_scheme else self.config.color_scheme
        return get_palette(scheme)

    def _render_frame(self, progress: float, effect_fn: Callable, palette: Optional[list] = None) -> Text:
        """Render a single animation frame."""
        lines = self._prepare_art()
        if palette is None:
            palette = self._get_palette()
        # Apply easing
        eased = ease_in_out(progress)
        return effect_fn(lines, palette, eased)

    @staticmethod
    def _terminal_rows(lines: list[str]) -> int:
        """
        Count how many terminal rows the art will occupy.

        Each text line that is wider than the terminal wraps onto extra rows.
        We need the true row count — not just len(lines) — so the cursor-up
        escape moves back exactly to the top of the animation area.
        """
        try:
            term_width = os.get_terminal_size().columns
        except OSError:
            term_width = 80
        rows = 0
        for line in lines:
            rows += max(1, math.ceil(len(line) / term_width) if line else 1)
        return rows

    def _cursor_to_top(self, rows: int) -> None:
        """
        Move the terminal cursor up `rows` lines and back to column 0.

        We write the ANSI escape directly to console.file (the raw stdout/stderr
        file handle) so that Rich's markup renderer never sees — and never
        escapes — the control sequence.  \033[<n>F = cursor up N lines + col 0.
        """
        console.file.write(f"\033[{rows}F")
        console.file.flush()

    def play(self, effect_name: Optional[str] = None) -> None:
        """Play the logo animation."""
        if self.config.should_skip():
            self._render_static()
            return

        self._start_time = time.time()
        self._skipped = False
        self.config.reset()

        # Choose effect
        if effect_name:
            from .logo_effects import get_effect
            effect_fn = get_effect(effect_name) or effect_fade_in
        else:
            effect_fn = effect_reveal_lines

        lines = self._prepare_art()

        # Fast path: instant speed
        if self.config.speed == AnimationSpeed.INSTANT:
            self._render_static()
            return

        # Non-interactive output (pipe/redirect) can't animate in-place.
        if not console.is_terminal:
            self._render_static()
            return

        delay = self.config.get_delay()
        total_frames = int(self.config.max_duration_sec / delay)
        total_frames = max(20, min(total_frames, 100))

        # Resolve palette once — keeps colours stable across frames and avoids
        # re-randomising the scheme on every tick when random_scheme=True.
        palette = self._get_palette()

        # Pre-compute how many terminal rows the art occupies (handles wrapping).
        rows = self._terminal_rows(lines)

        try:
            for frame in range(total_frames + 1):
                if not self._should_continue():
                    break

                progress = frame / total_frames
                text = self._render_frame(progress, effect_fn, palette)

                # From the second frame onward, jump back to the top of the art
                # area by writing the cursor-up escape directly to the terminal
                # file handle — bypassing Rich so it is never treated as markup.
                if frame > 0:
                    self._cursor_to_top(rows)

                console.print(text, end="")
                time.sleep(delay)

            # Final frame at 100% using the same effect as the rest of the
            # animation (previously hardcoded to effect_fade_in regardless).
            if not self._skipped:
                self._cursor_to_top(rows)
                final_text = self._render_frame(1.0, effect_fn, palette)
                console.print(final_text, end="")

        except KeyboardInterrupt:
            if self.config.skip_on_interrupt:
                self._skipped = True
                self._render_static()
            else:
                raise
        finally:
            # Leave cursor on a fresh line after the animation.
            console.print()

    def _render_static(self) -> None:
        """Render the logo without animation (fallback)."""
        lines = self._prepare_art()
        palette = self._get_palette()
        text = effect_fade_in(lines, palette, 1.0)
        console.print(text)

    def skip(self) -> None:
        """Skip the remaining animation."""
        self._skipped = True
        self.config.interrupt()


def animate_logo(config: Optional[LogoConfig] = None, effect: Optional[str] = None) -> None:
    """Convenience function to animate the Ferrox logo."""
    controller = AnimationController(config)
    controller.play(effect)


def render_static_logo(config: Optional[LogoConfig] = None) -> None:
    """Render the logo without animation."""
    controller = AnimationController(config)
    controller._render_static()
