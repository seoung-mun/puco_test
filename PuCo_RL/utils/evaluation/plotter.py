import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

# ── Global style ──────────────────────────────────────────────────────────────
_PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2"]
_ROLE_NAMES = ["Settler", "Mayor", "Builder", "Craftsman", "Trader", "Captain", "Prosp1", "Prosp2"]


def _setup_style():
    sns.set_theme(style="darkgrid", font_scale=1.1)
    plt.rcParams.update({"figure.dpi": 150, "savefig.bbox": "tight"})


def _ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


# ── 1. TrueSkill Horizontal Bar Chart (sorted by μ) ─────────────────────────
def save_trueskill_plot(ratings_dict: dict, save_path: str):
    """Horizontal error-bar chart sorted by TrueSkill μ (best at top)."""
    _setup_style()

    sorted_items = sorted(ratings_dict.items(), key=lambda x: x[1]["mu"])
    names  = [name for name, _ in sorted_items]
    mus    = [r["mu"]    for _, r in sorted_items]
    sigmas = [r["sigma"] for _, r in sorted_items]
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(names))]

    fig, ax = plt.subplots(figsize=(9, max(4, 0.6 * len(names))))
    y_pos = range(len(names))

    ax.barh(y_pos, mus, xerr=sigmas, color=colors, ecolor="#444444",
            capsize=4, height=0.6, error_kw={"linewidth": 1.5})

    for i, (mu, sigma) in enumerate(zip(mus, sigmas)):
        ax.text(mu + sigma + 0.15, i, f"μ={mu:.1f} ±{sigma:.1f}",
                va="center", fontsize=9)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(names)
    ax.set_xlabel("TrueSkill μ")
    ax.set_title("Agent TrueSkill Ratings (μ ± σ)", fontweight="bold")
    ax.axvline(25, color="gray", linestyle="--", linewidth=1, alpha=0.7,
               label="Default μ=25")
    ax.legend(fontsize=9)

    _ensure_dir(save_path)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


# ── 2. VP Margin Violin + Box Plot ───────────────────────────────────────────
def save_vp_margin_boxplot(vp_margins: dict, save_path: str):
    """Violin plot of VP margin distribution per agent, sorted by median."""
    _setup_style()

    sorted_names = sorted(vp_margins, key=lambda n: np.median(vp_margins[n]) if vp_margins[n] else 0, reverse=True)
    data, labels = [], []
    for name in sorted_names:
        data.extend(vp_margins[name])
        labels.extend([name] * len(vp_margins[name]))

    df = pd.DataFrame({"Agent": labels, "VP Margin": data})

    fig, ax = plt.subplots(figsize=(max(8, len(sorted_names) * 1.5), 6))
    sns.violinplot(x="Agent", y="VP Margin", hue="Agent", data=df, palette=_PALETTE,
                   inner="box", cut=0, ax=ax, order=sorted_names, legend=False)
    ax.axhline(0, color="red", linestyle="--", linewidth=1.5, alpha=0.7, label="Break-even")
    ax.set_title("VP Margin Distribution (vs Field Average)", fontweight="bold")
    ax.set_ylabel("VP Margin")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(fontsize=9)

    _ensure_dir(save_path)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


# ── 3. VP Decomposition: Shipping vs Building ────────────────────────────────
def save_vp_decomposition_plot(vp_averages: dict, save_path: str):
    """
    Stacked horizontal bar chart showing average Shipping VP vs Building VP.
    vp_averages: {agent_name: {"shipping": float, "building": float}}
    """
    _setup_style()

    sorted_names = sorted(vp_averages,
                          key=lambda n: vp_averages[n]["shipping"] + vp_averages[n]["building"],
                          reverse=True)

    ship_vals  = [vp_averages[n]["shipping"] for n in sorted_names]
    build_vals = [vp_averages[n]["building"] for n in sorted_names]
    y_pos = range(len(sorted_names))

    fig, ax = plt.subplots(figsize=(9, max(4, 0.6 * len(sorted_names))))
    bars1 = ax.barh(list(y_pos), ship_vals,  color="#4C72B0", height=0.55, label="Shipping VP")
    bars2 = ax.barh(list(y_pos), build_vals, left=ship_vals, color="#DD8452", height=0.55, label="Building VP")

    for i, (sv, bv) in enumerate(zip(ship_vals, build_vals)):
        total = sv + bv
        ax.text(total + 0.3, i, f"{total:.1f}", va="center", fontsize=9)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(sorted_names)
    ax.set_xlabel("Average VP")
    ax.set_title("VP Path Decomposition (Shipping vs Building)", fontweight="bold")
    ax.legend(loc="lower right")

    _ensure_dir(save_path)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


# ── 4. Role Selection Heatmap ─────────────────────────────────────────────────
def save_role_selection_plot(role_distributions: dict, save_path: str):
    """
    Heatmap of normalised role selection frequencies.
    role_distributions: {agent_name: np.ndarray(8,)}
    """
    _setup_style()

    sorted_names = sorted(role_distributions.keys())
    matrix = np.array([role_distributions[n] for n in sorted_names])

    fig, ax = plt.subplots(figsize=(11, max(3, 0.6 * len(sorted_names))))
    sns.heatmap(matrix, annot=True, fmt=".2f", cmap="YlOrRd",
                xticklabels=_ROLE_NAMES, yticklabels=sorted_names,
                linewidths=0.5, ax=ax, vmin=0, vmax=0.5)
    ax.set_title("Role Selection Frequency Heatmap", fontweight="bold")
    ax.tick_params(axis="x", rotation=30)

    _ensure_dir(save_path)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


# ── 5. Win-Rate Summary Bar Chart ─────────────────────────────────────────────
def save_winrate_plot(win_rates: dict, save_path: str, title: str = "Win Rate (%)"):
    """Simple bar chart of win rates, sorted descending."""
    _setup_style()

    sorted_items = sorted(win_rates.items(), key=lambda x: x[1], reverse=True)
    names  = [n for n, _ in sorted_items]
    rates  = [r for _, r in sorted_items]
    colors = [_PALETTE[i % len(_PALETTE)] for i in range(len(names))]

    fig, ax = plt.subplots(figsize=(max(7, len(names) * 1.3), 5))
    bars = ax.bar(names, rates, color=colors, width=0.6)
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{rate:.1f}%", ha="center", va="bottom", fontsize=10)
    ax.axhline(100 / len(names), color="gray", linestyle="--", linewidth=1,
               label=f"Random baseline ({100/len(names):.1f}%)")
    ax.set_ylabel("Win Rate (%)")
    ax.set_title(title, fontweight="bold")
    ax.tick_params(axis="x", rotation=20)
    ax.legend(fontsize=9)

    _ensure_dir(save_path)
    fig.tight_layout()
    fig.savefig(save_path)
    plt.close(fig)


# ── 6. APA vs PPA Correlation Bubble Chart ────────────────────────────────────
def save_apa_ppa_correlation_plot(apa_ppa_data: list[dict], save_path: str):
    """
    Bubble plot showing APA vs PPA with TrueSkill as bubble size.
    apa_ppa_data: list of {Agent, Avg_APA, Avg_PPA, TrueSkill_Mu}
    """
    _setup_style()
    
    if not apa_ppa_data:
        return
    
    df = pd.DataFrame(apa_ppa_data)
    
    fig, ax = plt.subplots(figsize=(12, 9))
    
    # Normalize TrueSkill for bubble sizes (200 to 2000)
    mu_min, mu_max = df["TrueSkill_Mu"].min(), df["TrueSkill_Mu"].max()
    if mu_max > mu_min:
        sizes = 200 + 1800 * (df["TrueSkill_Mu"] - mu_min) / (mu_max - mu_min)
    else:
        sizes = [1000] * len(df)
    
    ax.scatter(
        df["Avg_PPA"], df["Avg_APA"],
        s=sizes,
        c=range(len(df)),
        cmap="tab10",
        alpha=0.8,
        edgecolors="black",
        linewidth=1,
    )
    
    # Annotate points
    for i, row in df.iterrows():
        ax.text(
            row["Avg_PPA"] + 0.15,
            row["Avg_APA"] + 0.15,
            row["Agent"],
            horizontalalignment="left",
            fontsize=11,
            fontweight="bold",
        )
    
    # Draw reference axes
    ax.axhline(0, color="gray", linestyle="-", linewidth=1.5, alpha=0.5)
    ax.axvline(0, color="gray", linestyle="-", linewidth=1.5, alpha=0.5)
    
    ax.set_title(
        "Advantage Profile: Action(APA) vs Passive(PPA)\nBubble Size = TrueSkill μ",
        fontsize=16, fontweight="bold", pad=20
    )
    ax.set_xlabel("Passive Player Advantage (PPA) — Gain from others' actions", fontsize=12)
    ax.set_ylabel("Action Player Advantage (APA) — Gain from own actions", fontsize=12)
    
    # Add legend for bubble sizes
    handles = [
        plt.scatter([], [], s=200, c="gray", alpha=0.6, label=f"Low TrueSkill (μ≈{mu_min:.0f})"),
        plt.scatter([], [], s=1000, c="gray", alpha=0.6, label=f"Mid TrueSkill"),
        plt.scatter([], [], s=2000, c="gray", alpha=0.6, label=f"High TrueSkill (μ≈{mu_max:.0f})"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=10, title="TrueSkill μ")
    
    _ensure_dir(save_path)
    fig.tight_layout()
    fig.savefig(save_path, dpi=300)
    plt.close(fig)
