#!/usr/bin/env python3
"""Generate Figure 0: Architecture/pipeline diagram for the UGA paper."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
C_INNER   = "#3B6FA0"   # blue  – thinking / inner trace
C_INNER_L = "#A8C6E0"   # light blue fill
C_OUTER   = "#D4762C"   # orange – messages / outer trace
C_OUTER_L = "#F5D5B0"   # light orange fill
C_STRUCT  = "#4A8C5C"   # green – structural features
C_STRUCT_L= "#BEE0C8"   # light green fill
C_GRAY    = "#888888"
C_LGRAY   = "#E8E8E8"
C_BG      = "#FAFAFA"
C_GOLD    = "#C9A84C"   # evidence hierarchy

# ---------------------------------------------------------------------------
# Helper drawing functions
# ---------------------------------------------------------------------------

def box(ax, x, y, w, h, text, fc="#ffffff", ec="#333333", lw=1.2,
        fontsize=9, fontweight="normal", ha="center", va="center",
        text_color="black", alpha=1.0, style="round,pad=0.02"):
    """Draw a rounded box with centred text and return its centre."""
    p = FancyBboxPatch((x - w/2, y - h/2), w, h,
                        boxstyle=style,
                        facecolor=fc, edgecolor=ec, linewidth=lw, alpha=alpha,
                        zorder=2)
    ax.add_patch(p)
    ax.text(x, y, text, fontsize=fontsize, fontweight=fontweight,
            ha=ha, va=va, color=text_color, zorder=3)
    return (x, y)


def arrow(ax, x0, y0, x1, y1, color="#333333", lw=1.0, style="-|>",
          connectionstyle="arc3,rad=0", shrinkA=4, shrinkB=4):
    a = FancyArrowPatch((x0, y0), (x1, y1),
                         arrowstyle=style, color=color,
                         lw=lw, connectionstyle=connectionstyle,
                         shrinkA=shrinkA, shrinkB=shrinkB, zorder=1,
                         mutation_scale=12)
    ax.add_patch(a)


def brace_down(ax, x, y_top, y_bot, text, color=C_GRAY, fontsize=7):
    """Draw a small vertical bracket with label."""
    mid = (y_top + y_bot) / 2
    ax.annotate("", xy=(x, y_bot), xytext=(x, y_top),
                arrowprops=dict(arrowstyle="-", color=color, lw=0.8))
    ax.text(x + 0.02, mid, text, fontsize=fontsize, color=color, va="center")


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------

fig, ax = plt.subplots(figsize=(10, 6.8))
fig.patch.set_facecolor("white")
ax.set_xlim(-0.05, 1.05)
ax.set_ylim(-0.02, 1.02)
ax.axis("off")

# ── Row heights (top to bottom) ──
Y_TITLE  = 0.96
Y_TASK   = 0.88
Y_AGENT  = 0.78
Y_TRACE  = 0.67
Y_LAYER  = 0.555
Y_FEAT   = 0.42
Y_VALID  = 0.30
Y_STAT   = 0.18
Y_EVID   = 0.06

# ── Column centres ──
XL = 0.28   # Sonnet pipeline
XR = 0.72   # Codex pipeline
XM = 0.50   # merged centre

# ===== Title =====
ax.text(XM, Y_TITLE, "Behavioral Exhaust Mining Pipeline",
        fontsize=13, fontweight="bold", ha="center", va="center", color="#222")

# ===== Task row =====
box(ax, XL, Y_TASK, 0.30, 0.055, "SWE-bench Lite Tasks  (75 tasks)",
    fc=C_LGRAY, fontsize=8.5)
box(ax, XR, Y_TASK, 0.30, 0.055, "SWE-bench Lite Tasks  (70 tasks)",
    fc=C_LGRAY, fontsize=8.5)

# ===== Agent row =====
box(ax, XL, Y_AGENT, 0.26, 0.055, "Claude Sonnet 4.6",
    fc="#D6E6F5", ec=C_INNER, fontsize=9, fontweight="bold")
box(ax, XR, Y_AGENT, 0.26, 0.055, "Codex GPT-5.4",
    fc="#D6E6F5", ec=C_INNER, fontsize=9, fontweight="bold")
ax.text(XL, Y_AGENT - 0.033, "183 runs  ·  claude -p", fontsize=6.5,
        ha="center", color=C_GRAY)
ax.text(XR, Y_AGENT - 0.033, "190 runs  ·  codex exec", fontsize=6.5,
        ha="center", color=C_GRAY)

arrow(ax, XL, Y_TASK - 0.03, XL, Y_AGENT + 0.03)
arrow(ax, XR, Y_TASK - 0.03, XR, Y_AGENT + 0.03)

# ===== Trace row =====
box(ax, XL, Y_TRACE, 0.30, 0.055, "Stream-JSON Trace", fc="#FFF9EE",
    ec=C_OUTER, fontsize=9)
box(ax, XR, Y_TRACE, 0.30, 0.055, "Stream-JSON Trace", fc="#FFF9EE",
    ec=C_OUTER, fontsize=9)

arrow(ax, XL, Y_AGENT - 0.06, XL, Y_TRACE + 0.03)
arrow(ax, XR, Y_AGENT - 0.06, XR, Y_TRACE + 0.03)

# ===== Three-layer decomposition (one for each pipeline) =====
def draw_layers(cx, y_top, y_bot):
    """Draw the outer/inner trace decomposition."""
    dx = 0.12
    ymid = (y_top + y_bot) / 2
    # Left branch – OUTER
    box(ax, cx - dx, ymid, 0.11, 0.07,
        "Tool Calls\n& Messages",
        fc=C_OUTER_L, ec=C_OUTER, fontsize=7.5, fontweight="bold")
    ax.text(cx - dx, ymid - 0.045, "OUTER", fontsize=6, ha="center",
            color=C_OUTER, fontweight="bold")
    # Right branch – INNER
    box(ax, cx + dx, ymid, 0.11, 0.07,
        "Thinking\nBlocks",
        fc=C_INNER_L, ec=C_INNER, fontsize=7.5, fontweight="bold")
    ax.text(cx + dx, ymid - 0.045, "INNER", fontsize=6, ha="center",
            color=C_INNER, fontweight="bold")
    # Arrows from trace
    arrow(ax, cx - 0.04, y_top, cx - dx, ymid + 0.04, color=C_OUTER)
    arrow(ax, cx + 0.04, y_top, cx + dx, ymid + 0.04, color=C_INNER)
    return cx - dx, cx + dx, ymid


lxL, rxL, ymL = draw_layers(XL, Y_TRACE - 0.03, Y_LAYER)
lxR, rxR, ymR = draw_layers(XR, Y_TRACE - 0.03, Y_LAYER)

# ===== Feature tier row =====
def draw_features(cx, y, ylayer_mid):
    dx = 0.14
    bw, bh = 0.095, 0.065
    # Tier 0 – Structural (green)
    box(ax, cx - dx, y, bw, bh,
        "Tier 0\nStructural", fc=C_STRUCT_L, ec=C_STRUCT,
        fontsize=7, fontweight="bold")
    # Tier 1-2 – Linguistic (orange)
    box(ax, cx, y, bw, bh,
        "Tier 1–2\nLinguistic", fc=C_OUTER_L, ec=C_OUTER,
        fontsize=7, fontweight="bold")
    # CWC – Thinking (blue)
    box(ax, cx + dx, y, bw, bh,
        "CWC\nThinking", fc=C_INNER_L, ec=C_INNER,
        fontsize=7, fontweight="bold")

    # Arrows from layers to features
    arrow(ax, cx - dx + 0.02, ylayer_mid - 0.045, cx - dx, y + bh/2 + 0.005,
          color=C_STRUCT, lw=0.8)  # outer → structural
    arrow(ax, cx - dx + 0.02, ylayer_mid - 0.045, cx, y + bh/2 + 0.005,
          color=C_OUTER, lw=0.8)   # outer → linguistic
    arrow(ax, cx + dx - 0.02, ylayer_mid - 0.045, cx + dx, y + bh/2 + 0.005,
          color=C_INNER, lw=0.8)   # inner → CWC

    return cx, y - bh/2


fcL, fbL = draw_features(XL, Y_FEAT, ymL)
fcR, fbR = draw_features(XR, Y_FEAT, ymR)

# ===== Convergence: both pipelines merge =====
# Draw converging arrows from both feature rows to validation
arrow(ax, XL, fbL - 0.01, XM - 0.03, Y_VALID + 0.035, color=C_GRAY, lw=1.2)
arrow(ax, XR, fbR - 0.01, XM + 0.03, Y_VALID + 0.035, color=C_GRAY, lw=1.2)

# ===== Independent Validation =====
vw, vh = 0.38, 0.055
box(ax, XM, Y_VALID, vw, vh,
    "Independent Validation  (fresh env, test replay)",
    fc="#E8F5E9", ec=C_STRUCT, fontsize=8.5, fontweight="bold")
# Crossed-out self-report — draw a small box with X through it
sr_x = XM + vw/2 + 0.055
sr_y = Y_VALID
ax.text(sr_x, sr_y, "agent\nself-report",
        fontsize=6, ha="center", va="center", color="#BB3333",
        style="italic", zorder=3,
        bbox=dict(boxstyle="round,pad=0.15", fc="#FFEEEE", ec="#BB3333",
                  lw=0.7, alpha=0.9))
# Red X
xd = 0.032
yd = 0.022
ax.plot([sr_x - xd, sr_x + xd], [sr_y - yd, sr_y + yd],
        color="#CC2222", lw=2.5, zorder=5)
ax.plot([sr_x - xd, sr_x + xd], [sr_y + yd, sr_y - yd],
        color="#CC2222", lw=2.5, zorder=5)

# Pass/Fail label
ax.text(XM, Y_VALID - 0.04, "Pass / Fail  (ground truth)",
        fontsize=7.5, ha="center", color=C_STRUCT, fontweight="bold")

# ===== Statistical pipeline =====
stat_boxes = [
    ("Within-Repo\nSpearman", XM - 0.22),
    ("CWC Fisher\nCombination", XM),
    ("Permutation\nTest (10K)", XM + 0.22),
]
for label, sx in stat_boxes:
    box(ax, sx, Y_STAT, 0.15, 0.06, label,
        fc="#F3F0FF", ec="#6B5B95", fontsize=7.5, fontweight="bold")

# Fan-out arrows from ground truth to statistical pipeline
gt_y = Y_VALID - 0.065
arrow(ax, XM, Y_VALID - 0.055, XM, gt_y, color=C_GRAY, lw=1.0, style="-")
arrow(ax, XM, gt_y, XM - 0.22, Y_STAT + 0.035, color="#6B5B95", lw=1.0)
arrow(ax, XM, gt_y, XM,        Y_STAT + 0.035, color="#6B5B95", lw=1.0)
arrow(ax, XM, gt_y, XM + 0.22, Y_STAT + 0.035, color="#6B5B95", lw=1.0)

# Arrows between stat boxes
arrow(ax, XM - 0.145, Y_STAT, XM - 0.075, Y_STAT, color="#6B5B95", lw=0.8)
arrow(ax, XM + 0.075, Y_STAT, XM + 0.145, Y_STAT, color="#6B5B95", lw=0.8)

# ===== Evidence Hierarchy =====
box(ax, XM, Y_EVID, 0.42, 0.055,
    "Evidence Hierarchy   (Gold  /  Silver  /  Moderate)",
    fc="#FFF8E1", ec=C_GOLD, fontsize=9, fontweight="bold")
arrow(ax, XM, Y_STAT - 0.035, XM, Y_EVID + 0.03, color=C_GOLD, lw=1.4)

# ===== Annotations =====
# Feature counts
ax.text(XL - 0.14, Y_FEAT - 0.055, "7 features", fontsize=6, color=C_STRUCT,
        ha="center")
ax.text(XL, Y_FEAT - 0.055, "12 features", fontsize=6, color=C_OUTER,
        ha="center")
ax.text(XL + 0.14, Y_FEAT - 0.055, "5 features", fontsize=6, color=C_INNER,
        ha="center")

ax.text(XR - 0.14, Y_FEAT - 0.055, "7 features", fontsize=6, color=C_STRUCT,
        ha="center")
ax.text(XR, Y_FEAT - 0.055, "12 features", fontsize=6, color=C_OUTER,
        ha="center")
ax.text(XR + 0.14, Y_FEAT - 0.055, "5 features", fontsize=6, color=C_INNER,
        ha="center")

# Legend
legend_y = 0.96
legend_x = 0.88
for i, (label, fc, ec) in enumerate([
    ("Outer trace", C_OUTER_L, C_OUTER),
    ("Inner trace", C_INNER_L, C_INNER),
    ("Structural",  C_STRUCT_L, C_STRUCT),
]):
    yy = legend_y - i * 0.035
    p = FancyBboxPatch((legend_x - 0.025, yy - 0.01), 0.05, 0.02,
                        boxstyle="round,pad=0.003",
                        facecolor=fc, edgecolor=ec, linewidth=0.8, zorder=2)
    ax.add_patch(p)
    ax.text(legend_x + 0.035, yy, label, fontsize=6.5, va="center", color="#333")

# N = 373 annotation
ax.text(XM, Y_VALID - 0.06, "N = 373 validated runs  (345 with definitive outcomes)",
        fontsize=6.5, ha="center", color=C_GRAY, style="italic")

# Dashed separator between parallel pipelines
ax.plot([0.50, 0.50], [Y_TASK + 0.03, Y_FEAT - 0.07],
        color="#CCCCCC", lw=0.8, ls="--", zorder=0)

plt.tight_layout(pad=0.3)

# ── Save ──
fig.savefig("paper/figures/fig0_architecture.png",
            dpi=300, bbox_inches="tight", facecolor="white")
fig.savefig("paper/figures/fig0_architecture.pdf",
            bbox_inches="tight", facecolor="white")
print("Saved fig0_architecture.png and .pdf")
