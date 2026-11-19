"""Simple maps of current foehn conditions at SwissMetNet stations."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects
import matplotlib.pyplot as plt
import numpy as np

from . import obs

BORDER_URL = ("https://api3.geo.admin.ch/rest/services/api/MapServer/find"
              "?layer=ch.swisstopo.swissboundaries3d-land-flaeche.fill&searchText=CH"
              "&searchField=id&returnGeometry=true&geometryFormat=geojson&sr=2056")


def swiss_border() -> list[np.ndarray]:
    """Outer rings of the Swiss national border in LV95 coordinates (m), cached."""
    path = obs.CACHE_DIR / "swiss_border_lv95.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = obs._session.get(BORDER_URL, timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
    geom = json.loads(path.read_text())["results"][0]["geometry"]
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [np.asarray(p[0]) for p in polys]


def _place_labels(fig, ax, x, y, u, v, cur, is_foehn):
    """Greedy label placement: try 8 positions around each station, keep the first
    one that overlaps neither earlier labels nor station markers/arrows."""
    from matplotlib.transforms import Bbox

    renderer = fig.canvas.get_renderer()
    pts = ax.transData.transform(np.column_stack([x, y]))
    tips = ax.transData.transform(np.column_stack([x + u * 9, y + v * 9]))
    obstacles = [Bbox.from_extents(min(p[0], q[0]) - 6, min(p[1], q[1]) - 6,
                                   max(p[0], q[0]) + 6, max(p[1], q[1]) + 6)
                 for p, q in zip(pts, tips)]
    placed = []
    # (dx, dy) in points, ha, va
    cands = [(6, 4, "left", "bottom"), (-6, 4, "right", "bottom"), (6, -4, "left", "top"),
             (-6, -4, "right", "top"), (8, 0, "left", "center"), (-8, 0, "right", "center"),
             (0, 8, "center", "bottom"), (0, -8, "center", "top")]
    halo = [matplotlib.patheffects.withStroke(linewidth=2.5, foreground="white")]

    for i, (row, f) in enumerate(zip(cur.itertuples(), is_foehn)):
        label = (f"{row.station_abbr}  F={f}  {row.temp_c:.1f}°C\n"
                 f"{row.wind_ms:.1f} m/s {row.wind_dir:.0f}°  G {row.gust_ms:.1f}")
        best, best_cost = None, None
        for dx, dy, ha, va in cands:
            txt = ax.annotate(label, (x[i], y[i]), xytext=(dx, dy), textcoords="offset points",
                              ha=ha, va=va, fontsize=7, linespacing=1.15, zorder=4,
                              color="#d62728" if f else "#222", path_effects=halo)
            bb = txt.get_window_extent(renderer).expanded(1.03, 1.08)
            others = placed + [o for j, o in enumerate(obstacles) if j != i]
            cost = sum(bb.overlaps(o) for o in others)
            if best_cost is None or cost < best_cost:
                if best is not None:
                    best[0].remove()
                best, best_cost = (txt, bb), cost
            else:
                txt.remove()
            if cost == 0:
                break
        placed.append(best[1])


def plot_current(output: str = "foehn_current.png") -> str:
    cur = obs.current_foehn()
    st = obs.load_meta("stations")[["station_abbr", "station_coordinates_lv95_east",
                                    "station_coordinates_lv95_north"]]
    cur = cur.merge(st, on="station_abbr")
    x = cur["station_coordinates_lv95_east"].to_numpy() / 1000  # km
    y = cur["station_coordinates_lv95_north"].to_numpy() / 1000
    is_foehn = (cur["foehn"] == 2).astype(int)  # 1 = foehn, 0 = no foehn / mixing air

    fig, ax = plt.subplots(figsize=(13, 8.5))
    for ring in swiss_border():
        ax.fill(ring[:, 0] / 1000, ring[:, 1] / 1000, color="#f2f2ee", ec="#555", lw=0.8, zorder=0)

    # Wind arrow points where the air flows to (meteorological direction is "from").
    d = np.deg2rad(cur["wind_dir"].astype(float))
    u, v = -np.sin(d), -np.cos(d)
    ax.quiver(x, y, u, v, angles="xy", scale_units="xy", scale=1 / 9, width=0.0022,
              headwidth=4, color="#333", zorder=2)

    colors = np.where(is_foehn == 1, "#d62728", "#7f7f7f")
    ax.scatter(x, y, s=60, c=colors, ec="white", lw=0.8, zorder=3)

    t = cur["time"].max()
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.tight_layout()
    _place_labels(fig, ax, x, y, u, v, cur, is_foehn)

    ax.set_title(f"Föhn: {t:%d.%m.%Y %H:%M} UTC", fontsize=15, loc="left")
    ax.text(1, 1.01, "F = foehn index (1 foehn, 0 no foehn) · arrow: wind blowing to · "
                     "Data: MeteoSwiss OGD", transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="#555")
    fig.savefig(output, dpi=150, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return output
