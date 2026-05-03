import os
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

console = Console()


def load_ascii_art(filename: str = "tiger.txt") -> str:
    """Load ASCII art from file in project root."""
    # Find project root (assumes ferrox/ui/header.py structure)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(base_dir, "..", "..")
    filepath = os.path.join(project_root, filename)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback minimal ASCII
        return "       (Ferrox Tiger Art Missing)"


def render_header():
    """Render the Ferrox header with ASCII art and title."""
    ascii_art = load_ascii_art("tiger.txt")

    # Render art in a panel for clean look
    console.print(Panel(ascii_art, border_style="orange_red1", padding=(0, 2)))

    # Title
    title = Text("FERROX", style="bold magenta")
    console.print(title, justify="center")
    console.print("")


def _load_header_txt() -> list[str]:
    """Load header.txt from the project root."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(base_dir, "..", "..")
    filepath = os.path.join(project_root, "header.txt")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return []


def _ansi_gradient_color(t: float) -> str:
    """Return an ANSI true-colour code for a vertical gradient.

    t ranges 0.0 (top) -> 1.0 (bottom).
    Colours cycle: red -> orange -> yellow -> green -> cyan -> blue -> purple.
    """
    stops = [
        (255, 0, 0),      # red
        (255, 100, 0),    # orange-red
        (255, 165, 0),    # orange
        (255, 215, 0),    # gold
        (255, 255, 0),    # yellow
        (0, 255, 0),      # green
        (0, 255, 200),    # cyan
        (0, 191, 255),    # deep-sky-blue
        (135, 0, 255),    # purple
    ]
    t = max(0.0, min(1.0, t))
    idx = t * (len(stops) - 1)
    i = int(idx)
    frac = idx - i
    r1, g1, b1 = stops[min(i, len(stops) - 1)]
    r2, g2, b2 = stops[min(i + 1, len(stops) - 1)]
    r = int(r1 + (r2 - r1) * frac)
    g = int(g1 + (g2 - g1) * frac)
    b = int(b1 + (b2 - b1) * frac)
    return f"\033[38;2;{r};{g};{b}m"


def render_ferrox_crew_banner() -> None:
    """Render header.txt with a vertical gradient.

    Writes raw ANSI true-colour escapes directly to the terminal
    file handle so prompt_toolkit patch_stdout never sees (and
    never escapes) the control sequences.
    """
    lines = _load_header_txt()
    if not lines:
        console.print("[dim]header.txt not found[/dim]")
        return

    # Strip trailing empty lines to keep gradient tight
    while lines and not lines[-1].strip():
        lines.pop()

    reset = "\033[0m"
    n = len(lines)
    out_lines = []
    for i, line in enumerate(lines):
        t = i / max(n - 1, 1)
        colour = _ansi_gradient_color(t)
        out_lines.append(f"{colour}{line}{reset}")

    console.file.write("\n".join(out_lines) + "\n")
    console.file.flush()
