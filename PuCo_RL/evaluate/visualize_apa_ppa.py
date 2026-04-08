import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import argparse

def main():
    parser = argparse.ArgumentParser(description="Visualize APA vs PPA vs TrueSkill")
    parser.add_argument("--report_dir", type=str, default="report", help="Directory containing report subfolders")
    args = parser.parse_args()

    csv_files = glob.glob(os.path.join(args.report_dir, "*", "metrics_summary.csv"))
    
    if not csv_files:
        print(f"No metrics_summary.csv found in {args.report_dir}/ directory.")
        return
        
    print(f"Found {len(csv_files)} report files. Aggregating data...")
    df_list = []
    for f in csv_files:
        try:
            df = pd.read_csv(f)
            df_list.append(df)
        except Exception as e:
            print(f"Failed to read {f}: {e}")
            
    if not df_list:
        return

    merged_df = pd.concat(df_list, ignore_index=True)
    
    # Group by Agent and aggregate
    grouped = merged_df.groupby("Agent").agg({
        "Avg_APA": "mean",
        "Avg_PPA": "mean",
        "TrueSkill_Mu": "mean"
    }).reset_index()
    
    # Prepare plot
    plt.figure(figsize=(12, 9))
    sns.set_theme(style="whitegrid")
    
    # Bubble plot
    scatter = sns.scatterplot(
        data=grouped, 
        x="Avg_PPA", 
        y="Avg_APA", 
        size="TrueSkill_Mu", 
        hue="Agent",
        sizes=(200, 2000), 
        alpha=0.8,
        palette="tab10"
    )
    
    # Annotate points
    for i in range(grouped.shape[0]):
        plt.text(
            grouped["Avg_PPA"].iloc[i] + 0.15, 
            grouped["Avg_APA"].iloc[i] + 0.15, 
            grouped["Agent"].iloc[i], 
            horizontalalignment='left', 
            size='large', color='black', weight='bold'
        )
        
    # Draw reference axes lines
    plt.axhline(0, color='gray', linestyle='-', linewidth=1.5, alpha=0.5)
    plt.axvline(0, color='gray', linestyle='-', linewidth=1.5, alpha=0.5)

    plt.title("Advantage Profile: Action(APA) vs Passive(PPA)\nBubble Size = TrueSkill Mu", fontsize=18, pad=20)
    plt.xlabel("Passive Player Advantage (PPA) - Gain from others' actions", fontsize=14)
    plt.ylabel("Action Player Advantage (APA) - Gain from own actions", fontsize=14)
    
    # Adjust legend
    h, l = scatter.get_legend_handles_labels()
    plt.legend(h, l, bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0., title="Agents & TrueSkill")
    
    plt.tight_layout()
    output_path = "apa_ppa_correlation.png"
    plt.savefig(output_path, dpi=300)
    print(f"\n[Success] Visualization saved to {os.path.abspath(output_path)}")
    print("\n[Agent Coordinates]")
    print(grouped.to_string(index=False))

if __name__ == "__main__":
    main()
