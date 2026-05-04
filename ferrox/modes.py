import json
import os
from enum import Enum


class Mode(Enum):
    NORMAL = "NORMAL"
    PLAN = "PLAN"
    BYPASS = "BYPASS"
    EDIT = "EDIT"
    SOCIAL = "SOCIAL"


class ModeManager:
    def __init__(self):
        self.current_mode = Mode.NORMAL
        self.mode_order = [Mode.NORMAL, Mode.PLAN, Mode.EDIT, Mode.BYPASS]

    def cycle_mode(self):
        """Cycles: Normal -> Plan -> Edit -> Bypass -> Normal"""
        current_idx = self.mode_order.index(self.current_mode)
        next_idx = (current_idx + 1) % len(self.mode_order)
        self.current_mode = self.mode_order[next_idx]
        return self.current_mode

    def set_mode(self, mode_name: str | Mode):
        if isinstance(mode_name, Mode):
            self.current_mode = mode_name
            return
        try:
            self.current_mode = Mode[mode_name.upper()]
        except KeyError:
            raise ValueError(f"Invalid mode: {mode_name}") from None

    def get_prompt_prefix(self) -> str:
        """Returns colored prefix for prompt_toolkit"""
        colors = {
            Mode.NORMAL: "#00FF00",
            Mode.PLAN: "#FFA500",
            Mode.EDIT: "#00BFFF",
            Mode.BYPASS: "#FF0000",
            Mode.SOCIAL: "#1DA1F2",
        }
        colors.get(self.current_mode, "#FFFFFF")
        return f"[{self.current_mode.value}]"

    def get_mode_color(self) -> str:
        colors = {
            Mode.NORMAL: "green",
            Mode.PLAN: "orange1",
            Mode.EDIT: "deep_sky_blue1",
            Mode.BYPASS: "red",
            Mode.SOCIAL: "bright_blue",
        }
        return colors.get(self.current_mode, "white")

    def get_mode_icon(self) -> str:
        icons = {
            Mode.NORMAL: "●",
            Mode.PLAN: "◎",
            Mode.EDIT: "✎",
            Mode.BYPASS: "⚡",
            Mode.SOCIAL: "🐦",
        }
        return icons.get(self.current_mode, "?")

    def get_mode_description(self) -> str:
        descriptions = {
            Mode.NORMAL: "ask before write/exec",
            Mode.PLAN: "shell allowed, write asks",
            Mode.EDIT: "scoped edits, shell asks",
            Mode.BYPASS: "auto-approve all",
            Mode.SOCIAL: "X bot automation mode",
        }
        return descriptions.get(self.current_mode, "")

    def save_state(self, filepath: str):
        state = {"mode": self.current_mode.value}
        with open(filepath, "w") as f:
            json.dump(state, f)

    def load_state(self, filepath: str):
        if os.path.exists(filepath):
            with open(filepath) as f:
                state = json.load(f)
                try:
                    self.current_mode = Mode[state["mode"]]
                except (KeyError, ValueError):
                    self.current_mode = Mode.NORMAL
