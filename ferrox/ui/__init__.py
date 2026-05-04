from ..console_logger import UIHandler
from .header import render_ferrox_crew_banner, render_header
from .trace_viewer import show_trace_viewer

# Real-time monitoring components
try:
    from .realtime_trace import dashboard as RealTimeTraceViewer  # noqa: N812
except ImportError:
    RealTimeTraceViewer = None

# Logo animation components
try:
    from .logo_animation import (
        AnimationController,
        animate_logo,
        render_static_logo,
    )
    from .logo_config import AnimationSpeed, ColorScheme, LogoConfig, get_logo_config
    from .logo_effects import (
        effect_fade_in,
        effect_glow_pulse,
        effect_rainbow_shift,
        effect_reveal_lines,
        effect_scan,
        effect_sparkle,
        effect_typewriter,
        get_effect,
        get_palette,
        list_effects,
        random_effect,
        random_scheme,
    )
except ImportError:
    LogoConfig = None
    AnimationSpeed = None
    ColorScheme = None
    get_logo_config = None
    get_palette = None
    get_effect = None
    random_effect = None
    random_scheme = None
    list_effects = None
    effect_typewriter = None
    effect_reveal_lines = None
    effect_fade_in = None
    effect_scan = None
    effect_glow_pulse = None
    effect_rainbow_shift = None
    effect_sparkle = None
    animate_logo = None
    render_static_logo = None
    AnimationController = None

__all__ = [
    "render_header",
    "render_ferrox_crew_banner",
    "UIHandler",
    "show_trace_viewer",
    "RealTimeTraceViewer",
    # Logo animation
    "LogoConfig",
    "AnimationSpeed",
    "ColorScheme",
    "get_logo_config",
    "get_palette",
    "get_effect",
    "random_effect",
    "random_scheme",
    "list_effects",
    "effect_typewriter",
    "effect_reveal_lines",
    "effect_fade_in",
    "effect_scan",
    "effect_glow_pulse",
    "effect_rainbow_shift",
    "effect_sparkle",
    "animate_logo",
    "render_static_logo",
    "AnimationController",
]
