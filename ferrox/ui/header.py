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
        with open(filepath, 'r', encoding='utf-8') as f:
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
