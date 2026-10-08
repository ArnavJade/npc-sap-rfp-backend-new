"""Proposal diagrams ({{diagram:<key>}}) drawn with matplotlib from the sizing result -> PNG bytes.

timeline      Gantt of the waves on the programme calendar, each month coloured by its SAP Activate phase
methodology   SAP Activate phases as chevrons with their main activities
architecture  SAP S/4HANA core with the in-scope lines of business, middleware and third-party systems
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon  # noqa: E402

from bidcore.ledger.models import Ledger  # noqa: E402
from bidcore.sizing import SizingResult  # noqa: E402

PHASE_COLOURS = {"Prepare": "#9DC3E6", "Explore": "#5B9BD5", "Realize": "#2E75B6", "Deploy": "#1F4E78",
                 "PGLS": "#A9D18E"}
NAVY, GREY = "#1F4E78", "#595959"


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def timeline(ledger: Ledger, sizing: SizingResult) -> bytes:
    grids = sizing.plan.grids
    span = max((g.start_month + g.months for g in grids), default=1)
    fig, ax = plt.subplots(figsize=(10, 0.8 + 0.7 * max(len(grids), 1)))
    for y, grid in enumerate(reversed(grids)):
        for i, band in enumerate(grid.phase_bands):
            ax.barh(y, 1, left=grid.start_month + i, color=PHASE_COLOURS.get(band, "#BFBFBF"), edgecolor="white")
        ax.text(grid.start_month - 0.2, y, grid.wave_name, ha="right", va="center", fontsize=9, color=NAVY)
    ax.set_xlim(-0.1, span + 0.1)
    ax.set_xticks([m + 0.5 for m in range(span)])
    ax.set_xticklabels([f"M{m + 1}" for m in range(span)], fontsize=7)
    ax.set_yticks([])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in PHASE_COLOURS.values()]
    labels = [*list(PHASE_COLOURS)[:-1], "Hypercare"]
    ax.legend(handles, labels, ncol=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.25), frameon=False)
    ax.set_title("Implementation timeline", fontsize=11, color=NAVY, loc="left")
    return _png(fig)


METHODOLOGY = [
    ("Prepare", ["Project set-up", "Governance & plan", "System provisioning"]),
    ("Explore", ["Fit-to-standard workshops", "Delta design", "Backlog"]),
    ("Realize", ["Configuration sprints", "Development & integration", "Testing & data loads"]),
    ("Deploy", ["UAT sign-off", "Training & cutover", "Go-live"]),
    ("Run", ["Hypercare", "Stabilisation", "Handover to support"]),
]


def methodology(ledger: Ledger, sizing: SizingResult) -> bytes:
    fig, ax = plt.subplots(figsize=(10, 2.6))
    width, gap = 1.9, 0.08
    colours = [PHASE_COLOURS["Prepare"], PHASE_COLOURS["Explore"], PHASE_COLOURS["Realize"],
               PHASE_COLOURS["Deploy"], PHASE_COLOURS["PGLS"]]
    for i, ((phase, steps), colour) in enumerate(zip(METHODOLOGY, colours)):
        x = i * (width + gap)
        tip = 0.25
        ax.add_patch(Polygon([(x, 1.6), (x + width, 1.6), (x + width + tip, 2.0), (x + width, 2.4), (x, 2.4),
                              (x + tip, 2.0)], closed=True, color=colour))
        ax.text(x + width / 2 + tip / 2, 2.0, phase, ha="center", va="center", fontsize=11, color="white",
                weight="bold")
        for j, step in enumerate(steps):
            ax.text(x + 0.15, 1.3 - j * 0.4, f"- {step}", fontsize=8, color=GREY, va="center")
    ax.set_xlim(-0.1, len(METHODOLOGY) * (width + gap) + 0.3)
    ax.set_ylim(0, 2.6)
    ax.axis("off")
    ax.set_title("SAP Activate methodology", fontsize=11, color=NAVY, loc="left")
    return _png(fig)


def _box(ax, x, y, w, h, text, face, colour="white", size=8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=face, ec="white"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=colour, wrap=True)


def architecture(ledger: Ledger, sizing: SizingResult) -> bytes:
    lobs = [lob for lob, m in sizing.effort.modules.items() if m.rows][:9]
    systems = [r.system for r in ledger.integrations.rows][:10]
    middleware = sorted({r.middleware for r in ledger.integrations.rows if r.middleware}) or ["Integration layer"]
    fig, ax = plt.subplots(figsize=(10, 5))
    _box(ax, 3.0, 1.0, 4.0, 3.6, "", "#DEEBF7")
    ax.text(5.0, 4.35, "SAP S/4HANA", ha="center", fontsize=12, color=NAVY, weight="bold")
    cols = 3
    for i, lob in enumerate(lobs or ["Core business processes"]):
        r, c = divmod(i, cols)
        _box(ax, 3.15 + c * 1.27, 3.45 - r * 0.95, 1.17, 0.8, lob.replace(" and ", " &\n"), NAVY, size=7)
    _box(ax, 7.4, 1.0, 0.9, 3.6, "\n".join(middleware[:4]), "#7F7F7F", size=8)
    for i, system in enumerate(systems or ["Third-party systems"]):
        y = 4.3 - i * (3.6 / max(len(systems), 1))
        _box(ax, 8.6, y - 0.3, 1.4, 0.32, system, "#A9D18E", colour="#203864", size=7)
        ax.annotate("", xy=(8.3, y - 0.14), xytext=(8.6, y - 0.14), arrowprops={"arrowstyle": "<->", "color": GREY})
    _box(ax, 0.2, 2.2, 2.4, 1.2, "Users\n(SAP Fiori launchpad,\nanalytics)", "#5B9BD5", size=8)
    ax.annotate("", xy=(3.0, 2.8), xytext=(2.6, 2.8), arrowprops={"arrowstyle": "<->", "color": GREY})
    ax.set_xlim(0, 10.2)
    ax.set_ylim(0.8, 4.8)
    ax.axis("off")
    ax.set_title("To-be solution landscape (indicative)", fontsize=11, color=NAVY, loc="left")
    return _png(fig)


DRAWERS = {"timeline": timeline, "methodology": methodology, "architecture": architecture}


def draw(key: str, ledger: Ledger, sizing: SizingResult) -> bytes | None:
    drawer = DRAWERS.get(key)
    return drawer(ledger, sizing) if drawer else None
