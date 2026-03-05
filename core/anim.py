"""
Easing and animation helper functions.
"""


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out: fast start, smooth deceleration."""
    t = max(0.0, min(1.0, float(t)))
    p = t - 1.0
    return p * p * p + 1.0


def shockwave_envelope(t: float) -> float:
    """Simple 0→1 shockwave envelope (decaying intensity)."""
    t = max(0.0, min(1.0, float(t)))
    return (1.0 - t) * (0.8 + 0.2 * t)
