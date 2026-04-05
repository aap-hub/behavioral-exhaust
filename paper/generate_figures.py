#!/usr/bin/env python3
"""Generate publication-quality figures for the UGA paper."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# Style setup
plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,
})

# Colorblind-friendly palette (Okabe-Ito)
CB_BLUE = "#0072B2"
CB_ORANGE = "#E69F00"
CB_GREEN = "#009E73"
CB_RED = "#D55E00"
CB_PURPLE = "#CC79A7"
CB_GREY = "#999999"


def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png", dpi=300)
    plt.close(fig)
    print(f"  saved {name}.pdf/.png")


# ─── Figure 1: Trajectory Degradation ────────────────────────────────────────

def fig1_trajectory_degradation():
    print("Figure 1: Trajectory Degradation")
    positions = ["Early\n(0-33%)", "Mid\n(33-67%)", "Late\n(67-100%)"]
    x = np.arange(len(positions))

    delib_rho = [0.180, 0.166, 0.038]
    delib_p   = [0.016, 0.028, 0.615]
    align_rho = [0.242, 0.165, 0.026]
    align_p   = [0.001, 0.029, 0.735]

    # Bootstrap-style SE approximation: SE ~ 1/sqrt(n-3) for Spearman.
    # From memo, n per bin ~ 180. SE ~ 1/sqrt(177) ~ 0.075
    se = 0.075

    fig, ax = plt.subplots(figsize=(7, 4))
    width = 0.30

    bars1 = ax.bar(x - width/2, delib_rho, width, yerr=se, capsize=4,
                   color=CB_BLUE, edgecolor="white", label="deliberation_length")
    bars2 = ax.bar(x + width/2, align_rho, width, yerr=se, capsize=4,
                   color=CB_ORANGE, edgecolor="white", label="reasoning_to_action_alignment")

    ax.axhline(y=0, color="black", linestyle="--", linewidth=0.8, alpha=0.5)

    # Significance markers
    for i, (p_d, p_a) in enumerate(zip(delib_p, align_p)):
        if p_d < 0.05:
            ax.text(x[i] - width/2, delib_rho[i] + se + 0.012, "*",
                    ha="center", va="bottom", fontsize=14, fontweight="bold", color=CB_BLUE)
        if p_a < 0.05:
            ax.text(x[i] + width/2, align_rho[i] + se + 0.012, "*",
                    ha="center", va="bottom", fontsize=14, fontweight="bold", color=CB_ORANGE)

    ax.set_xticks(x)
    ax.set_xticklabels(positions)
    ax.set_ylabel("Spearman \u03c1")
    ax.set_xlabel("Trajectory Position")
    ax.set_title("Signal Degradation Over Agent Trajectory")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_ylim(-0.05, 0.40)

    save(fig, "fig1_trajectory_degradation")


# ─── Figure 2: Interaction Effect Heatmap ─────────────────────────────────────

def fig2_interaction_heatmap():
    print("Figure 2: Interaction Effect Heatmap")

    # Rows: deliberation (High, Low); Cols: diagnostic_precision (High, Low)
    pass_rates = np.array([
        [73, 23],   # High deliberation: High diag, Low diag
        [32, 38],   # Low deliberation: High diag, Low diag
    ])
    ns = np.array([
        [22, 22],
        [22, 21],
    ])

    fig, ax = plt.subplots(figsize=(5, 4))

    im = ax.imshow(pass_rates, cmap="RdYlGn", vmin=15, vmax=80, aspect="auto")

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["High", "Low"])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["High", "Low"])
    ax.set_xlabel("Diagnostic Precision")
    ax.set_ylabel("Deliberation Length")

    # Annotate cells
    for i in range(2):
        for j in range(2):
            val = pass_rates[i, j]
            n = ns[i, j]
            text_color = "white" if val < 40 else "black"
            ax.text(j, i, f"{val}%\n(n={n})", ha="center", va="center",
                    fontsize=12, fontweight="bold", color=text_color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, label="Pass Rate (%)")
    ax.set_title("Deliberation \u00d7 Diagnostic Precision Interaction\n(Sonnet / sympy)")

    save(fig, "fig2_interaction_heatmap")


# ─── Figure 3: Cross-Model Feature Comparison ────────────────────────────────

def fig3_cross_model():
    print("Figure 3: Cross-Model Feature Comparison")

    features = [
        "metacognitive_density",
        "backtrack_count",
        "think_t_compat_fraction",
        "instead_contrast_density",
        "deliberation_length",
        "early_error_rate",
        "fail_streak_max",
    ]
    sonnet = [0.138, 0.359, 0.0, 0.282, 0.214, -0.273, -0.294]
    codex  = [-0.261, -0.108, -0.323, -0.264, 0.0, -0.282, -0.296]

    y = np.arange(len(features))
    height = 0.35

    fig, ax = plt.subplots(figsize=(7, 4.5))

    ax.barh(y + height/2, sonnet, height, color=CB_BLUE, edgecolor="white",
            label="Sonnet 4.6", zorder=3)
    ax.barh(y - height/2, codex, height, color=CB_RED, edgecolor="white",
            label="Codex", zorder=3)

    ax.axvline(x=0, color="black", linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(features, fontsize=9)
    ax.set_xlabel("Spearman \u03c1")
    ax.set_xlim(-0.45, 0.45)
    ax.set_title("Cross-Model Feature Associations (sympy)")
    ax.legend(loc="lower right", framealpha=0.9)

    # Highlight polarity flip on instead_contrast_density
    flip_idx = features.index("instead_contrast_density")
    rect = mpatches.FancyBboxPatch(
        (-0.42, flip_idx - 0.48), 0.84, 0.96,
        boxstyle="round,pad=0.02", linewidth=1.5,
        edgecolor=CB_PURPLE, facecolor="none", linestyle="--", zorder=2
    )
    ax.add_patch(rect)
    ax.annotate("polarity\nflip", xy=(0.38, flip_idx), fontsize=8,
                color=CB_PURPLE, fontweight="bold", ha="center", va="center")

    fig.tight_layout()
    save(fig, "fig3_cross_model")


# ─── Figure 4: Evidence Hierarchy ─────────────────────────────────────────────

def fig4_evidence_hierarchy():
    print("Figure 4: Evidence Hierarchy")

    tiers = [
        ("Gold\n(cross-model)", ["fail_streak_max", "early_error_rate"],
         "#FFD700", "black"),
        ("Silver\n(model-specific)", ["deliberation_length", "think_t_compat_fraction"],
         "#C0C0C0", "black"),
        ("Moderate", ["first_edit_position", "instead_contrast_density"],
         "#CD7F32", "white"),
        ("Retracted", ["reasoning_to_action_alignment"],
         "#CC3333", "white"),
        ("Null", ["hedging_score", "verification_score",
                   "planning_score", "precision_naming_score"],
         "#BBBBBB", "black"),
    ]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.set_xlim(0, 11)
    ax.set_ylim(-0.5, len(tiers) - 0.5)
    ax.invert_yaxis()
    ax.axis("off")

    label_x = 1.0
    item_start_x = 2.8

    for row, (tier_name, items, bg, fg) in enumerate(tiers):
        # Tier label
        ax.text(label_x, row, tier_name, ha="center", va="center",
                fontsize=10, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=bg, edgecolor="none", alpha=0.85),
                color=fg)

        # Feature badges
        for col, item in enumerate(items):
            x = item_start_x + col * 1.8
            display = item
            style = dict(boxstyle="round,pad=0.25", facecolor="white",
                         edgecolor=bg, linewidth=1.5)
            text_kw = dict(fontsize=8, color="black", fontstyle="normal")

            if tier_name == "Retracted":
                style["edgecolor"] = "#CC3333"
                style["linewidth"] = 2
                # strikethrough via annotation
                ax.text(x, row, display, ha="center", va="center",
                        bbox=style, **text_kw)
                # Draw red X over it
                ax.plot([x - 0.6, x + 0.6], [row - 0.15, row + 0.15],
                        color="#CC3333", linewidth=2, zorder=5)
                ax.plot([x - 0.6, x + 0.6], [row + 0.15, row - 0.15],
                        color="#CC3333", linewidth=2, zorder=5)
            else:
                ax.text(x, row, display, ha="center", va="center",
                        bbox=style, **text_kw)

    ax.set_title("Evidence Hierarchy of Behavioral Features", fontsize=12,
                 fontweight="bold", pad=12)

    fig.tight_layout()
    save(fig, "fig4_evidence_hierarchy")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    fig1_trajectory_degradation()
    fig2_interaction_heatmap()
    fig3_cross_model()
    fig4_evidence_hierarchy()
    print("\nAll figures generated.")
