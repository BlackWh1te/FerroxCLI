"""Bidirectional skill sync between Ferrox skills and Hermes skills.

Hermes uses a simple skill format:
    ~/.hermes/skills/<skill-name>/
        SKILL.md          (required, YAML frontmatter + markdown body)
        <optional assets>

Ferrox uses:
    <package>/ferrox/skills/<skill-name>/
        SKILL.md
        __init__.py       (optional, with SKILL_VERSION)
        <optional assets>

This module provides:
- export_ferrox_skill(name, target_dir): copy a Ferrox skill into Hermes layout
- import_hermes_skill(name, source_dir): copy a Hermes skill into Ferrox layout
- sync_all(direction): bulk export or import
- list_exported(): show what was previously synced
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from .manager import SKILLS_DIR

SyncDirection = Literal["export", "import"]


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _default_hermes_skills_dir() -> Path:
    """Default Hermes skills directory (cross-platform)."""
    import os

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            return Path(local) / "hermes" / "hermes-agent" / "skills"
        return Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent" / "skills"
    return Path.home() / ".hermes" / "skills"


def _sync_state_file() -> Path:
    """File that records sync history."""
    return SKILLS_DIR / ".hermes_sync_state.json"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class SyncRecord:
    """One sync event."""

    direction: str
    skill: str
    source: str
    target: str
    timestamp: str
    bytes: int
    status: str  # "ok" | "skipped" | "error"
    message: str = ""


@dataclass
class SyncState:
    """Persistent sync history."""

    records: list[SyncRecord] = field(default_factory=list)

    def add(self, record: SyncRecord) -> None:
        self.records.append(record)

    def to_dict(self) -> dict:
        return {
            "records": [
                {
                    "direction": r.direction,
                    "skill": r.skill,
                    "source": r.source,
                    "target": r.target,
                    "timestamp": r.timestamp,
                    "bytes": r.bytes,
                    "status": r.status,
                    "message": r.message,
                }
                for r in self.records
            ]
        }

    @classmethod
    def load(cls) -> SyncState:
        path = _sync_state_file()
        if not path.exists():
            return cls()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return cls()
        records = [SyncRecord(**r) for r in data.get("records", [])]
        return cls(records=records)

    def save(self) -> None:
        path = _sync_state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


# ---------------------------------------------------------------------------
# Core sync functions
# ---------------------------------------------------------------------------


def _ensure_hermes_skill_md(src_md: Path, dst_md: Path, skill_name: str) -> None:
    """Copy SKILL.md, ensuring it has YAML frontmatter (Hermes requirement)."""
    text = src_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        front = (
            f"---\nname: {skill_name}\ndescription: Synced from Ferrox CLI\nversion: 1.0.0\n---\n\n"
        )
        text = front + text
    dst_md.write_text(text, encoding="utf-8")


def _copy_tree(src: Path, dst: Path) -> int:
    """Copy a directory tree, returning total bytes copied."""
    if not src.exists():
        return 0
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    total = 0
    for f in dst.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def export_ferrox_skill(
    name: str,
    target_dir: Path | None = None,
    state: SyncState | None = None,
) -> SyncRecord:
    """Export a single Ferrox skill to a Hermes-compatible directory.

    Args:
        name: Skill name to export.
        target_dir: Destination directory; defaults to ``~/.hermes/skills/<name>``.
        state: Optional state object to record the operation.
    """
    target_dir = target_dir or (_default_hermes_skills_dir() / name)
    state = state or SyncState.load()
    src = SKILLS_DIR / name
    src_md = src / "SKILL.md"

    if not src_md.exists():
        record = SyncRecord(
            direction="export",
            skill=name,
            source=str(src),
            target=str(target_dir),
            timestamp=datetime.utcnow().isoformat() + "Z",
            bytes=0,
            status="error",
            message=f"Ferrox skill '{name}' not found",
        )
        state.add(record)
        state.save()
        return record

    target_dir.mkdir(parents=True, exist_ok=True)
    bytes_copied = _copy_tree(src, target_dir)
    # Make sure SKILL.md has frontmatter
    _ensure_hermes_skill_md(src_md, target_dir / "SKILL.md", name)

    record = SyncRecord(
        direction="export",
        skill=name,
        source=str(src),
        target=str(target_dir),
        timestamp=datetime.utcnow().isoformat() + "Z",
        bytes=bytes_copied,
        status="ok",
    )
    state.add(record)
    state.save()
    return record


def import_hermes_skill(
    name: str,
    source_dir: Path | None = None,
    target_dir: Path | None = None,
    state: SyncState | None = None,
) -> SyncRecord:
    """Import a Hermes skill into the Ferrox skill tree.

    Args:
        name: Skill name to import.
        source_dir: Source directory; defaults to ``~/.hermes/skills/<name>``.
        target_dir: Destination directory; defaults to ``ferrox/skills/<name>``.
        state: Optional state object.
    """
    source_dir = source_dir or (_default_hermes_skills_dir() / name)
    target_dir = target_dir or (SKILLS_DIR / name)
    state = state or SyncState.load()
    src_md = source_dir / "SKILL.md"

    if not src_md.exists():
        record = SyncRecord(
            direction="import",
            skill=name,
            source=str(source_dir),
            target=str(target_dir),
            timestamp=datetime.utcnow().isoformat() + "Z",
            bytes=0,
            status="error",
            message=f"Hermes skill '{name}' not found at {source_dir}",
        )
        state.add(record)
        state.save()
        return record

    bytes_copied = _copy_tree(source_dir, target_dir)

    record = SyncRecord(
        direction="import",
        skill=name,
        source=str(source_dir),
        target=str(target_dir),
        timestamp=datetime.utcnow().isoformat() + "Z",
        bytes=bytes_copied,
        status="ok",
    )
    state.add(record)
    state.save()
    return record


def sync_all(
    direction: SyncDirection,
    state: SyncState | None = None,
) -> list[SyncRecord]:
    """Sync all skills in one direction.

    Args:
        direction: ``"export"`` (Ferrox → Hermes) or ``"import"`` (Hermes → Ferrox).
        state: Optional shared state.
    """
    state = state or SyncState.load()
    records: list[SyncRecord] = []

    if direction == "export":
        for skill_md in SKILLS_DIR.glob("*/SKILL.md"):
            if skill_md.parent.name.startswith("."):
                continue
            records.append(export_ferrox_skill(skill_md.parent.name, state=state))
    else:
        for skill_md in _default_hermes_skills_dir().glob("*/SKILL.md"):
            if skill_md.parent.name.startswith("."):
                continue
            records.append(import_hermes_skill(skill_md.parent.name, state=state))

    return records


def list_exported() -> list[dict]:
    """Return all recorded sync history as a list of dicts."""
    return SyncState.load().to_dict()["records"]


def format_records(records: list[dict]) -> str:
    """Render sync records as a human-readable table."""
    if not records:
        return "No sync history."
    lines = ["direction  skill                    status  bytes    timestamp"]
    for r in records[-25:]:
        lines.append(
            f"{r['direction']:<10} {r['skill']:<24} {r['status']:<7} {r['bytes']:<8} {r['timestamp']}"
        )
    return "\n".join(lines)
