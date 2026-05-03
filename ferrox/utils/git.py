import subprocess
from typing import Optional


def get_git_branch() -> Optional[str]:
    """
    Get the current git branch name.
    Returns None if not in a git repository.
    """
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.STDOUT, text=True
        ).strip()
        return branch
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
