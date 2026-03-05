"""
Relative CPU / GPU / RAM cost estimator based on the current config.
"""


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def estimate_costs(cfg: dict) -> dict:
    """Return estimated resource usage percentages and explanations.

    Returns a dict with keys: ``cpu_pct``, ``gpu_pct``, ``ram_pct``, ``explain``.
    """
    c = cfg.get("costs", {})
    g = cfg.get("graphics", {})
    p = cfg.get("performance", {})
    a = cfg.get("animations", {})

    # Normalize values to 0..1
    ring_factor = _clamp01((g.get("ring_size", 780) - 400) / 1000)
    node_factor = _clamp01((g.get("node_radius", 16) - 8) / 40)
    fps_factor  = _clamp01(p.get("max_fps", 60) / 240)

    gpu = (
        ring_factor * c.get("ring_size", 0.35)
        + node_factor * c.get("node_radius", 0.18)
        + (1.0 if a.get("shockwave", False) else 0.0) * c.get("shockwave", 0.12)
        + 0.25 * c.get("glow_effects", 0.25)
    )
    cpu = (
        fps_factor * c.get("max_fps", 0.20)
        + 0.03 * c.get("smart_grouping", 0.03)
    )
    ram = 0.10 * ring_factor + 0.05 * node_factor

    def _pct(x: float) -> int:
        return max(0, min(100, int(round(x * 100))))

    return {
        "cpu_pct": _pct(cpu),
        "gpu_pct": _pct(gpu),
        "ram_pct": _pct(ram),
        "explain": {
            "cpu": "CPU grows with FPS and smart grouping.",
            "gpu": "GPU grows with ring size, glow effects, and shockwave.",
            "ram": "RAM grows slightly with ring and node sizes.",
        },
    }
