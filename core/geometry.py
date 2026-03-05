"""
Ring geometry calculations: hub and node positions for the radial menu.
"""

import math


def build_ring_geometry(groups: dict, cfg: dict) -> dict:
    """Compute hub and node positions from *groups* and *cfg*.

    Returns::

        {
            "center": {"x": float, "y": float},
            "hubs":   [{"app": str, "x": float, "y": float}, ...],
            "nodes":  [{"id": str, "app": str, "title": str, "x": float, "y": float}, ...],
        }
    """
    ring_size  = cfg["graphics"]["ring_size"]
    hub_radius = cfg["graphics"]["hub_radius"]
    spoke      = cfg["graphics"]["spoke_length"]
    cx = cy    = ring_size / 2.0

    apps = sorted(groups.keys())
    num_apps = len(apps)

    if num_apps == 0:
        return {"center": {"x": cx, "y": cy}, "hubs": [], "nodes": []}

    angles = [
        2 * math.pi * i / num_apps - (math.pi / 2)
        for i in range(num_apps)
    ]

    hubs: list[dict] = []
    nodes: list[dict] = []

    for i, app in enumerate(apps):
        angle = angles[i]
        hx = cx + hub_radius * math.cos(angle)
        hy = cy + hub_radius * math.sin(angle)
        hubs.append({"app": app, "x": hx, "y": hy})

        wins = groups[app]
        num_wins = len(wins)

        for j, win in enumerate(wins):
            # Fan out multiple windows around the hub angle
            offset = (j - (num_wins - 1) / 2.0) * (math.pi / 11) if num_wins > 1 else 0
            node_angle = angle + offset
            nx = hx + spoke * math.cos(node_angle)
            ny = hy + spoke * math.sin(node_angle)
            nodes.append({
                "id":    win["id"],
                "app":   app,
                "title": win["title"],
                "x":     nx,
                "y":     ny,
            })

    return {"center": {"x": cx, "y": cy}, "hubs": hubs, "nodes": nodes}
