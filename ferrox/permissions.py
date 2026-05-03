"""Permission engine with scoped allowances for Ferrox"""

import os
import json
from enum import Enum
from typing import Optional, Dict, List
from .modes import Mode


class PermissionAction(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class PermissionScope(Enum):
    ONCE = "once"  # Allow this action just now
    COMMAND = "command"  # Always allow this specific command
    PROJECT = "project"  # Always allow in current working directory
    SESSION = "session"  # Allow for entire session


class PermissionRule:
    """Represents a permission rule"""

    def __init__(self, scope: PermissionScope, command: str = None, path: str = None):
        self.scope = scope
        self.command = command
        self.path = path

    def matches(self, command: str, path: str) -> bool:
        if self.scope == PermissionScope.COMMAND:
            return self.command == command
        elif self.scope in (PermissionScope.PROJECT, PermissionScope.SESSION):
            return self.path and path.startswith(self.path)
        return False

    def to_dict(self):
        return {"scope": self.scope.value, "command": self.command, "path": self.path}

    @classmethod
    def from_dict(cls, data):
        return cls(
            scope=PermissionScope(data.get("scope", "once")),
            command=data.get("command"),
            path=data.get("path"),
        )


class PermissionEngine:
    """Permission engine with scoped allowances"""

    def __init__(self, config_path: str = "~/.ferrox/permissions.json"):
        self.config_path = os.path.expanduser(config_path)
        self.session_allowed = set()  # Paths allowed for this session only
        self.session_denied = set()  # Paths denied for this session only
        self.denied_providers = set()  # Providers denied permanently
        self.session_outside_project = False  # Allow edits outside project for session
        self.persistent_rules: List[PermissionRule] = []
        self._load_config()

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    rules = data.get("rules", [])
                    self.persistent_rules = [PermissionRule.from_dict(r) for r in rules]
                    self.denied_providers = set(data.get("denied_providers", []))
            except (json.JSONDecodeError, IOError):
                pass

    def _save_config(self):
        data = {
            "rules": [rule.to_dict() for rule in self.persistent_rules],
            "denied_providers": list(self.denied_providers),
        }
        try:
            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass

    def is_provider_allowed(self, provider_id: str) -> bool:
        return provider_id not in self.denied_providers

    def deny_provider(self, provider_id: str):
        self.denied_providers.add(provider_id)
        self._save_config()

    def cleanup(self):
        """Remove session permissions file"""
        if os.path.exists(self.config_path):
            try:
                os.remove(self.config_path)
            except IOError:
                pass

    def check_access(
        self, path: str, action: PermissionAction, current_mode: Mode, command: str = None
    ):
        """
        Returns:
            True - Access granted
            False - Access denied
            None - Need to ask user
        """
        abs_path = os.path.normpath(os.path.abspath(os.path.expanduser(path))).lower()
        cwd = os.path.normpath(os.path.abspath(os.getcwd())).lower()

        # Bypass mode - always allow
        if current_mode == Mode.BYPASS:
            return True

        # Plan mode - allow execute, ask for write, allow read
        if current_mode == Mode.PLAN:
            if action == PermissionAction.WRITE:
                return None  # Ask for write
            if action == PermissionAction.EXECUTE:
                return True  # Allow shell in plan mode
            return True  # Allow read

        # Edit mode - allow write only in project directory, ask for outside
        if current_mode == Mode.EDIT:
            if action == PermissionAction.WRITE:
                # Always allow writes inside the current project directory
                if (
                    abs_path == cwd
                    or abs_path.startswith(cwd + os.sep)
                    or abs_path.startswith(cwd + "/")
                ):
                    return True
                if self.session_outside_project:
                    return True
                return None  # Ask to allow outside project
            if action == PermissionAction.EXECUTE:
                return None  # Ask for shell in edit mode
            return True  # Allow read

        # Normal mode - ask for write/execute, allow read
        if current_mode == Mode.NORMAL:
            if action in [PermissionAction.WRITE, PermissionAction.EXECUTE]:
                return None
            return True

        # Check session cache
        if abs_path in self.session_allowed:
            return True
        if abs_path in self.session_denied:
            return False

        # Check persistent rules
        for rule in self.persistent_rules:
            if rule.matches(command or "", abs_path):
                return True

        return None

    def grant_once(self, path: str):
        """Grant permission for this action only"""
        abs_path = os.path.abspath(os.path.expanduser(path))
        self.session_allowed.add(abs_path)

    def grant_session_outside_project(self):
        """Grant permission to edit outside project for entire session"""
        self.session_outside_project = True

    def grant_command(self, command: str):
        """Grant permission for this command always"""
        rule = PermissionRule(PermissionScope.COMMAND, command=command)
        self.persistent_rules.append(rule)
        self._save_config()

    def grant_project(self, project_path: str):
        """Grant permission for this project always"""
        abs_path = os.path.abspath(os.path.expanduser(project_path))
        rule = PermissionRule(PermissionScope.PROJECT, path=abs_path)
        self.persistent_rules.append(rule)
        self._save_config()

    def deny_access(self, path: str):
        """Deny permission for this session"""
        abs_path = os.path.abspath(os.path.expanduser(path))
        self.session_denied.add(abs_path)

    def get_permission_options(
        self, path: str, command: str = None, mode: Mode = Mode.NORMAL
    ) -> List[tuple]:
        """Get available permission options for prompt"""
        options = [
            ("Yes", "Allow this action once"),
            ("No", "Deny this action"),
        ]
        if command:
            options.insert(1, (f"Always '{command}'", "Always allow this command"))
        options.insert(1, ("Yes, this session", "Allow for entire session"))
        if mode == Mode.EDIT:
            options.insert(1, ("Yes, outside project", "Allow edits outside project for session"))
        return options

    def get_ask_prompt(self, path: str, action: PermissionAction, mode: Mode = Mode.NORMAL) -> str:
        op = action.value
        if mode == Mode.EDIT and action == PermissionAction.WRITE:
            return f"Ferrox EDIT mode wants to write outside project dir '{path}'. Allow?"
        return f"Ferrox wants to {op} '{path}'. Allow?"
