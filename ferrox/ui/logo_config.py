"""Logo animation configuration and user preferences."""

import os
from dataclasses import dataclass, field
from enum import Enum


class AnimationSpeed(Enum):
    SLOW = 0.15      # ~7 fps, dramatic
    NORMAL = 0.08    # ~12 fps, standard
    FAST = 0.04      # ~25 fps, snappy
    INSTANT = 0.0    # Skip animation


class ColorScheme(Enum):
    FIRE = "fire"           # Red -> Orange -> Yellow
    CYBER = "cyber"         # Cyan -> Magenta -> Green
    OCEAN = "ocean"         # Blue -> Cyan -> White
    FOREST = "forest"       # Green -> Lime -> Yellow
    SUNSET = "sunset"       # Purple -> Pink -> Orange
    MONOCHROME = "mono"     # White -> Gray -> Black
    RAINBOW = "rainbow"     # Full spectrum cycle
    GOLD = "gold"           # Yellow -> Orange -> Red


@dataclass
class LogoConfig:
    """User preferences for logo animation."""

    enabled: bool = True
    speed: AnimationSpeed = AnimationSpeed.NORMAL
    color_scheme: ColorScheme = ColorScheme.FIRE
    auto_detect_theme: bool = True
    random_scheme: bool = False
    max_duration_sec: float = 5.0
    skip_on_interrupt: bool = True

    # Internal state (not persisted)
    _interrupted: bool = field(default=False, repr=False)

    @classmethod
    def from_env(cls) -> "LogoConfig":
        """Load config from environment variables."""
        config = cls()

        # FERROX_ANIMATION=0 disables
        env_anim = os.getenv("FERROX_ANIMATION", "1").lower()
        if env_anim in ("0", "false", "no", "off", "disabled"):
            config.enabled = False

        # FERROX_ANIM_SPEED=slow|normal|fast|instant
        env_speed = os.getenv("FERROX_ANIM_SPEED", "normal").lower()
        speed_map = {
            "slow": AnimationSpeed.SLOW,
            "normal": AnimationSpeed.NORMAL,
            "fast": AnimationSpeed.FAST,
            "instant": AnimationSpeed.INSTANT,
        }
        config.speed = speed_map.get(env_speed, AnimationSpeed.NORMAL)

        # FERROX_ANIM_SCHEME=fire|cyber|ocean|forest|sunset|mono|rainbow|gold|random
        env_scheme = os.getenv("FERROX_ANIM_SCHEME", "fire").lower()
        if env_scheme == "random":
            config.random_scheme = True
        else:
            scheme_map = {s.value: s for s in ColorScheme}
            config.color_scheme = scheme_map.get(env_scheme, ColorScheme.FIRE)

        # FERROX_ANIM_DURATION=seconds
        env_dur = os.getenv("FERROX_ANIM_DURATION", "")
        if env_dur:
            try:
                config.max_duration_sec = float(env_dur)
            except ValueError:
                pass

        return config

    def should_skip(self) -> bool:
        """Check if animation should be skipped entirely."""
        return not self.enabled or self.speed == AnimationSpeed.INSTANT or self._interrupted

    def get_delay(self) -> float:
        """Get frame delay in seconds."""
        return self.speed.value

    def interrupt(self) -> None:
        """Signal that user wants to skip remaining animation."""
        self._interrupted = True

    def reset(self) -> None:
        """Reset interrupt flag for next run."""
        self._interrupted = False


def get_logo_config() -> LogoConfig:
    """Get the global logo animation configuration."""
    return LogoConfig.from_env()
