import asyncio
import re
from pathlib import Path


async def build_project_index(root_dir: str) -> dict:
    """
    Builds a simple index of symbols (defs/classes) in Python/JS/TS files.
    """
    index = {}
    root_path = Path(root_dir)

    # Common ignore patterns
    ignore_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}

    for filepath in root_path.rglob("*"):
        # Skip directories and ignored paths
        if filepath.is_dir() or any(ignore in filepath.parts for ignore in ignore_dirs):
            continue

        if filepath.suffix in [".py", ".js", ".ts", ".jsx", ".tsx"]:
            try:
                content = filepath.read_text(encoding="utf-8")
                rel_path = str(filepath.relative_to(root_path))

                defs = []
                if filepath.suffix == ".py":
                    # Match def and class
                    defs = re.findall(r"^(def \w+|class \w+)", content, re.MULTILINE)
                elif filepath.suffix in [".js", ".ts", ".jsx", ".tsx"]:
                    # Match function, const, class
                    defs = re.findall(
                        r"^(function \w+|const \w+|class \w+|export (default )?function \w+)",
                        content,
                        re.MULTILINE,
                    )

                if defs:
                    index[rel_path] = defs

            except Exception:
                continue

    return index


async def find_symbol_usage(symbol_name: str, root_dir: str) -> list:
    """
    Uses ripgrep (rg) to find where a symbol is used across the project.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "rg",
            "--type",
            "py",
            "--type",
            "js",
            "--type",
            "ts",
            "-n",
            "-i",
            symbol_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=root_dir,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        return output.split("\n") if output else []
    except Exception:
        return []
