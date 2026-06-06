"""Logo animation effects library with timing and color management."""

import math
import random
from typing import Callable, Optional

from rich.text import Text

from .logo_config import ColorScheme

# ── Color Palette Definitions ──────────────────────────────────────────────

PALETTES: dict[ColorScheme, list[str]] = {
    ColorScheme.FIRE: [
        "#ff0000",
        "#ff1a00",
        "#ff3300",
        "#ff4d00",
        "#ff6600",
        "#ff8000",
        "#ff9900",
        "#ffb300",
        "#ffcc00",
        "#ffe600",
        "#ffff00",
    ],
    ColorScheme.CYBER: [
        "#00ffff",
        "#1affff",
        "#33ffff",
        "#ff00ff",
        "#ff1aff",
        "#ff33ff",
        "#00ff00",
        "#1aff1a",
        "#33ff33",
        "#00ff80",
        "#00ffcc",
    ],
    ColorScheme.OCEAN: [
        "#000080",
        "#0000b3",
        "#0000e6",
        "#0040ff",
        "#0080ff",
        "#00bfff",
        "#00ffff",
        "#80ffff",
        "#b3ffff",
        "#e6ffff",
        "#ffffff",
    ],
    ColorScheme.FOREST: [
        "#006400",
        "#008000",
        "#009600",
        "#00b300",
        "#00cc00",
        "#00e600",
        "#1aff1a",
        "#4dff4d",
        "#80ff80",
        "#b3ffb3",
        "#ccff00",
    ],
    ColorScheme.SUNSET: [
        "#4b0082",
        "#6a0dad",
        "#8b00ff",
        "#ff00ff",
        "#ff1493",
        "#ff0066",
        "#ff3300",
        "#ff6600",
        "#ff9900",
        "#ffcc00",
        "#ffeb3b",
    ],
    ColorScheme.MONOCHROME: [
        "#000000",
        "#1a1a1a",
        "#333333",
        "#4d4d4d",
        "#666666",
        "#808080",
        "#999999",
        "#b3b3b3",
        "#cccccc",
        "#e6e6e6",
        "#ffffff",
    ],
    ColorScheme.RAINBOW: [
        "#ff0000",
        "#ff7f00",
        "#ffff00",
        "#00ff00",
        "#0000ff",
        "#4b0082",
        "#9400d3",
        "#ff1493",
        "#ff0000",
    ],
    ColorScheme.GOLD: [
        "#b8860b",
        "#daa520",
        "#ffd700",
        "#ffdf00",
        "#ffea00",
        "#ffff00",
        "#fffacd",
        "#fff8dc",
        "#ffec8b",
        "#ffd700",
        "#ffae00",
    ],
}


# ── Timing & Easing Functions ──────────────────────────────────────────────


def linear(t: float) -> float:
    return t


def ease_in(t: float) -> float:
    return t * t


def ease_out(t: float) -> float:
    return 1 - (1 - t) * (1 - t)


def ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


def bounce_out(t: float) -> float:
    if t < 1 / 2.75:
        return 7.5625 * t * t
    elif t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    elif t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    else:
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375


def flicker(t: float, intensity: float = 0.3) -> float:
    """Add random flicker to timing."""
    noise = random.uniform(-intensity, intensity)  # nosec: B311 — jitter delay, not cryptographic
    return max(0.0, min(1.0, t + noise))


# ── Color Utilities ────────────────────────────────────────────────────────


def get_palette(scheme: ColorScheme) -> list[str]:
    """Get color palette for a scheme."""
    return PALETTES.get(scheme, PALETTES[ColorScheme.FIRE])


def random_scheme() -> ColorScheme:
    """Pick a random color scheme."""
    return random.choice(list(ColorScheme))  # nosec: B311 — jitter delay, not cryptographic


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Linear interpolation between two hex colors."""

    def hex_to_rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

    def rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"

    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)

    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)

    return rgb_to_hex(r, g, b)


def cycle_palette(palette: list[str], offset: float) -> list[str]:
    """Rotate palette by offset amount (0.0-1.0)."""
    if not palette:
        return palette
    n = len(palette)
    shift = int(offset * n) % n
    return palette[shift:] + palette[:shift]


# ── Text Manipulation ──────────────────────────────────────────────────────


def split_lines(text: str) -> list[str]:
    """Split text into lines, preserving empty lines."""
    return text.split("\n")


def get_line_width(lines: list[str]) -> int:
    """Get maximum line width."""
    if not lines:
        return 0
    return max(len(line) for line in lines)


def center_line(line: str, width: int, fill: str = " ") -> str:
    """Center a line within given width."""
    pad = (width - len(line)) // 2
    return fill * pad + line + fill * (width - len(line) - pad)


def pad_lines(lines: list[str], width: int) -> list[str]:
    """Pad all lines to same width."""
    return [line.ljust(width) for line in lines]


# ── Effect Generators ─────────────────────────────────────────────────────


def effect_typewriter(lines: list[str], palette: list[str], progress: float) -> Text:
    """Typewriter effect: characters appear progressively."""
    text = Text()
    total_chars = sum(len(line) + 1 for line in lines)
    chars_to_show = int(total_chars * progress)

    shown = 0
    for line in lines:
        for _i, ch in enumerate(line):
            if shown < chars_to_show:
                color_idx = min(int((shown / max(1, total_chars)) * len(palette)), len(palette) - 1)
                style = palette[color_idx] if ch.strip() else ""
                text.append(ch, style=style)
            else:
                text.append(" ")
            shown += 1
        text.append("\n")
        shown += 1

    return text


def effect_reveal_lines(lines: list[str], palette: list[str], progress: float) -> Text:
    """Reveal lines from top to bottom."""
    text = Text()
    num_lines = len(lines)
    lines_to_show = int(num_lines * progress)

    for i, line in enumerate(lines):
        if i < lines_to_show:
            color_idx = min(int((i / max(1, num_lines)) * len(palette)), len(palette) - 1)
            text.append(line, style=palette[color_idx])
        else:
            text.append(" " * len(line))
        text.append("\n")

    return text


def effect_fade_in(lines: list[str], palette: list[str], progress: float) -> Text:
    """Fade in all lines simultaneously."""
    text = Text()
    intensity = int(progress * len(palette))
    color_idx = min(intensity, len(palette) - 1)

    for line in lines:
        text.append(line, style=palette[color_idx])
        text.append("\n")

    return text


def effect_scan(lines: list[str], palette: list[str], progress: float) -> Text:
    """Scanning beam effect left to right."""
    text = Text()
    width = get_line_width(lines)
    scan_pos = int(width * progress)

    for line in lines:
        for i, ch in enumerate(line.ljust(width)):
            if i <= scan_pos and ch.strip():
                color_idx = min(int((i / max(1, width)) * len(palette)), len(palette) - 1)
                text.append(ch, style=palette[color_idx])
            else:
                text.append(" ")
        text.append("\n")

    return text


def effect_glow_pulse(lines: list[str], palette: list[str], progress: float) -> Text:
    """Pulsing glow effect."""
    text = Text()
    # Use sine wave for pulse
    pulse = (math.sin(progress * math.pi * 4) + 1) / 2
    color_idx = min(int(pulse * len(palette)), len(palette) - 1)

    for line in lines:
        text.append(line, style=palette[color_idx])
        text.append("\n")

    return text


def effect_rainbow_shift(lines: list[str], palette: list[str], progress: float) -> Text:
    """Color cycling across lines."""
    text = Text()
    shifted = cycle_palette(palette, progress)
    num_lines = len(lines)

    for i, line in enumerate(lines):
        color_idx = min(int((i / max(1, num_lines)) * len(shifted)), len(shifted) - 1)
        text.append(line, style=shifted[color_idx])
        text.append("\n")

    return text


def effect_sparkle(lines: list[str], palette: list[str], progress: float) -> Text:
    """Random sparkle effect."""
    text = Text()
    total_chars = sum(len(line) for line in lines)
    sparkles = int(progress * total_chars * 1.5)
    sparkle_set = set(random.sample(range(total_chars), min(sparkles, total_chars)))  # nosec: B311 — jitter delay, not cryptographic

    idx = 0
    for line in lines:
        for ch in line:
            if ch.strip() and idx in sparkle_set:
                color_idx = random.randint(0, len(palette) - 1)  # nosec: B311 — jitter delay, not cryptographic
                text.append(ch, style=palette[color_idx])
            elif ch.strip():
                text.append(ch, style=palette[0])
            else:
                text.append(" ")
            idx += 1
        text.append("\n")

    return text


# ── Effect Registry ────────────────────────────────────────────────────────

EFFECTS: list[tuple[str, Callable]] = [
    ("typewriter", effect_typewriter),
    ("reveal", effect_reveal_lines),
    ("fade", effect_fade_in),
    ("scan", effect_scan),
    ("glow", effect_glow_pulse),
    ("rainbow", effect_rainbow_shift),
    ("sparkle", effect_sparkle),
]


def get_effect(name: str) -> Optional[Callable]:
    """Get effect function by name."""
    for n, fn in EFFECTS:
        if n == name:
            return fn
    return None


def random_effect() -> tuple[str, Callable]:
    """Pick a random effect."""
    return random.choice(EFFECTS)  # nosec: B311 — jitter delay, not cryptographic


def list_effects() -> list[str]:
    """List all available effect names."""
    return [name for name, _ in EFFECTS]
