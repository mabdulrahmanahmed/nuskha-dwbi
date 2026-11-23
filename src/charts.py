"""One chart style for every report figure (static PNGs, matplotlib). Synthetic data.

Rules followed (so every chart reads the same way):
  * categorical colours in a fixed slot order, and a category always gets the SAME colour
    (colour follows the entity, never its rank); validated 8-slot palette
  * one y-axis only; bar axes start at zero; thin 2 px lines; recessive grid
  * a legend whenever there are 2+ series; text in neutral ink, never in series colours
  * every figure carries the note "Synthetic data (seed 472)" and its units
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SLOTS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
CATEGORIES = ["Analgesics", "Antibiotics", "Cardiovascular", "Diabetes Care", "Gastro", "Cough and Cold",
              "Vitamins and Supplements", "Personal Care"]
CATEGORY_COLOR = dict(zip(CATEGORIES, SLOTS))
REGION_COLOR = {"North": SLOTS[0], "East": SLOTS[1], "South": SLOTS[2]}


def color_of(name: str, i: int = 0) -> str:
    return CATEGORY_COLOR.get(name) or REGION_COLOR.get(name) or SLOTS[i % len(SLOTS)]


def figure(width: float = 10, height: float = 5):
    fig, ax = plt.subplots(figsize=(width, height), facecolor=SURFACE)
    style(ax)
    return fig, ax


def style(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8)
    ax.yaxis.label.set_color(INK_2)
    ax.xaxis.label.set_color(INK_2)


def finish(fig, ax, title: str, path, ylabel: str = "", note: str = "", legend: bool = True) -> None:
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9)
    if legend and len(ax.get_legend_handles_labels()[0]) >= 2:
        leg = ax.legend(fontsize=8, frameon=False, labelcolor=INK_2, ncol=2)
        leg.set_title(None)
    fig.text(0.01, 0.01, ("Synthetic data (seed 472). " + note).strip(), fontsize=7, color=INK_2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, dpi=110, facecolor=SURFACE)
    plt.close(fig)


def millions(ax) -> None:
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1e6:.1f}M"))
