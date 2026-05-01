import json
import os
from enum import Enum


class Mode(Enum):
    NORMAL = "NORMAL"
    PLAN = "PLAN"
    BYPASS = "BYPASS"


class ModeManager:
    def __init__(self):
        self.current_mode = Mode.NORMAL
        self.mode_order = [Mode.NORMAL, Mode.PLAN, Mode.BYPASS]

    def cycle_mode(self):
        """Cycles: Normal -> Plan -> Bypass -> Normal"""
        current_idx = self.mode_order.index(self.current_mode)
        next_idx = (current_idx + 1) % len(self.mode_order)
        self.current_mode = self.mode_order[next_idx]
        return self.current_mode

    def set_mode(self, mode_name: str):
        try:
            self.current_mode = Mode[mode_name.upper()]
        except KeyError:
            raise ValueError(f"Invalid mode: {mode_name}")

    def get_prompt_prefix(self) -> str:
        """Returns colored prefix for prompt_toolkit"""
        colors = {
            Mode.NORMAL: "#00FF00",
            Mode.PLAN: "#FFFF00",
            Mode.BYPASS: "#FF0000"
        }
        color = colors.get(self.current_mode, "#FFFFFF")
        return f"[{self.current_mode.value}]"

    def get_mode_color(self) -> str:
        colors = {
            Mode.NORMAL: "green",
            Mode.PLAN: "yellow",
            Mode.BYPASS: "red"
        }
        return colors.get(self.current_mode, "white")

    def save_state(self, filepath: str):
        state = {"mode": self.current_mode.value}
        with open(filepath, 'w') as f:
            json.dump(state, f)

    def load_state(self, filepath: str):
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                state = json.load(f)
                try:
                    self.current_mode = Mode[state['mode']]
                except (KeyError, ValueError):
                    self.current_mode = Mode.NORMAL