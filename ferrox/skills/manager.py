"""Skill manager for Ferrox - Load and inject skill documentation into agent prompts."""

import contextlib
from pathlib import Path
from typing import Optional

# Skill directory
SKILLS_DIR = Path(__file__).parent


def get_skill_content(skill_name: str) -> Optional[str]:
    """Load skill content from SKILL.md file.

    Args:
        skill_name: Name of the skill directory (e.g., "x_bot")

    Returns:
        Skill content as string, or None if not found
    """
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"

    if not skill_path.exists():
        return None

    try:
        with open(skill_path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error loading skill {skill_name}: {e}")
        return None


def load_skill(skill_name: str) -> dict:
    """Load skill metadata and content.

    Args:
        skill_name: Name of the skill directory

    Returns:
        Dictionary with skill metadata and content
    """
    skill_path = SKILLS_DIR / skill_name
    skill_md_path = skill_path / "SKILL.md"

    result = {
        "name": skill_name,
        "exists": False,
        "content": None,
        "version": "1.0.0",
    }

    if not skill_path.exists() or not skill_path.is_dir():
        return result

    result["exists"] = True

    # Try to get version from __init__.py
    init_path = skill_path / "__init__.py"
    if init_path.exists():
        try:
            with open(init_path, encoding="utf-8") as f:
                init_content = f.read()
                # Extract version
                for line in init_content.split("\n"):
                    if "SKILL_VERSION" in line:
                        with contextlib.suppress(IndexError, ValueError, AttributeError):
                            result["version"] = line.split("=")[1].strip().strip('"')
        except (OSError, FileNotFoundError, PermissionError):
            pass

    # Load SKILL.md content
    if skill_md_path.exists():
        result["content"] = get_skill_content(skill_name)

    return result


def list_skills() -> list[str]:
    """List all available skills.

    Returns:
        List of skill names
    """
    skills = []

    if not SKILLS_DIR.exists():
        return skills

    for item in SKILLS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith("__"):
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skills.append(item.name)

    return skills


class SkillManager:
    """Manages skill loading and prompt injection."""

    def __init__(self):
        self.active_skills: list[str] = []
        self.skill_cache: dict = {}

    def activate_skill(self, skill_name: str) -> bool:
        """Activate a skill by name.

        Args:
            skill_name: Name of skill to activate

        Returns:
            True if successful, False otherwise
        """
        skill = load_skill(skill_name)

        if not skill["exists"]:
            return False

        if skill_name not in self.active_skills:
            self.active_skills.append(skill_name)
            self.skill_cache[skill_name] = skill

        return True

    def deactivate_skill(self, skill_name: str) -> bool:
        """Deactivate a skill by name.

        Args:
            skill_name: Name of skill to deactivate

        Returns:
            True if successful
        """
        if skill_name in self.active_skills:
            self.active_skills.remove(skill_name)
            self.skill_cache.pop(skill_name, None)

        return True

    def get_active_skills_prompt(self) -> str:
        """Get combined prompt from all active skills.

        Returns:
            Combined skill prompt text
        """
        if not self.active_skills:
            return ""

        prompts = []

        for skill_name in self.active_skills:
            if skill_name in self.skill_cache:
                content = self.skill_cache[skill_name].get("content", "")
                if content:
                    prompts.append(f"\n\n## SKILL: {skill_name.upper()}\n{content}")
            else:
                # Load from disk if not cached
                content = get_skill_content(skill_name)
                if content:
                    prompts.append(f"\n\n## SKILL: {skill_name.upper()}\n{content}")

        return "\n".join(prompts)

    def is_skill_active(self, skill_name: str) -> bool:
        """Check if a skill is currently active.

        Args:
            skill_name: Name of skill to check

        Returns:
            True if active
        """
        return skill_name in self.active_skills

    def get_active_skill_names(self) -> list[str]:
        """Get list of active skill names.

        Returns:
            List of active skill names
        """
        return self.active_skills.copy()
