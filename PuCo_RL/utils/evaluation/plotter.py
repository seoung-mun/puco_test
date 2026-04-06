import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def save_trueskill_plot(ratings_dict, save_path="report/trueskill_comparison.png"):
    names = list(ratings_dict.keys())
    mus = [r["mu"] for r in ratings_dict.values()]
    sigmas = [r["sigma"] for r in ratings_dict.values()]
    
    plt.figure(figsize=(10, 6))
    plt.errorbar(mus, range(len(names)), xerr=sigmas, fmt='o', capsize=5, ecolor='black')
    plt.yticks(range(len(names)), names)
    plt.xlabel("TrueSkill Mu (Capability)")
    plt.title("Agent TrueSkill Rating with Uncertainty (Sigma)")
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

def save_vp_margin_boxplot(vp_margins, save_path="report/vp_margins_boxplot.png"):
    """
    vp_margins is a dict mapping agent name -> list of margins
    """
    data = []
    labels = []
    for name, margins in vp_margins.items():
        data.extend(margins)
        labels.extend([name] * len(margins))
        
    df = pd.DataFrame({"Agent": labels, "VP Margin": data})
    
    plt.figure(figsize=(10, 6))
    sns.boxplot(x="Agent", y="VP Margin", data=df)
    plt.axhline(0, color='red', linestyle='--', alpha=0.5)
    plt.title("VP Margin Distribution (Higher is Better)")
    plt.ylabel("VP Margin vs Field Average")
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

def save_learning_curve(steps, phase_ppo_metrics, ppo_metrics, metric_name="Win Rate", save_path="report/learning_curve.png"):
    plt.figure(figsize=(10, 6))
    plt.plot(steps, phase_ppo_metrics, marker='o', label='Phase PPO')
    plt.plot(steps, ppo_metrics, marker='s', label='Standard PPO')
    plt.xlabel("Training Steps")
    plt.ylabel(metric_name)
    plt.title(f"{metric_name} Learning Convergence")
    plt.legend()
    plt.grid(True)
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

def save_selfplay_avg_vp_plot(agent_vp_dict, save_path="report/selfplay_avg_vp.png"):
    names = list(agent_vp_dict.keys())
    vps = list(agent_vp_dict.values())
    
    plt.figure(figsize=(8, 6))
    bars = plt.bar(names, vps, color=['#4C72B0', '#DD8452', '#55A868'] * 2)
    plt.ylabel("Average Victory Points (VP)")
    plt.title("Self-Play Average Final VP (A-A-A vs B-B-B)")
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, yval, f'{yval:.1f}', va='bottom', ha='center')
        
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

def save_role_selection_plot(role_counts_dict, role_names, save_path="report/role_selection_frequency.png"):
    df_data = []
    for agent, counts in role_counts_dict.items():
        total = sum(counts)
        if total == 0: total = 1 # prevent div by zero
        for i, count in enumerate(counts):
            df_data.append({"Agent": agent, "Role": role_names[i], "Frequency": count / total})
            
    df = pd.DataFrame(df_data)
    
    plt.figure(figsize=(10, 6))
    sns.barplot(x="Role", y="Frequency", hue="Agent", data=df)
    plt.title("Role Selection Frequency")
    plt.ylabel("Frequency")
    plt.xticks(rotation=45)
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
