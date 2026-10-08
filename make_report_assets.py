"""
make_report_assets.py -- Regenerate every figure and table of the report from
the result CSVs, so that all numbers come from the same runs.

Inputs : results_mc.csv                 (robustness_mc.py)
         results_ga_sensitivity.csv     (ga_sensitivity.py, optional)
Outputs: figures/fig1_cost_large.png, fig2_time.png, fig3_robustness.png
         tables/table1_quality.tex, table2_time.tex, table3_robustness.tex

All quantities are COST (= -fitness); lower is better.

Usage:  python make_report_assets.py
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

W_VAC = 5.0   # weight of the vacation-overrun term in PlanningProblem
SHORT = {"Recuit simule": "SA", "Tabou": "Tabu", "Genetique": "GA",
         "Tabou x Recuit": "Tabu+SA", "Fourmis (ACO)": "ACO", "Random": "Random"}
GA_TUNED = "GA-1/n"
ORDER = ["SA", "Tabu", "Tabu+SA", "GA", GA_TUNED, "ACO", "Random"]
TEX = {"SA": "SA", "Tabu": "Tabu", "Tabu+SA": r"Tabu$\times$SA",
       "GA": "GA (default)", GA_TUNED: r"GA ($p_{\mathrm{mut}}=1/n$)",
       "ACO": "ACO", "Random": "Random"}
PLOT = {"SA": "SA", "Tabu": "Tabu", "Tabu+SA": "Tabu+SA", "GA": "GA\n(default)",
        GA_TUNED: "GA\n(p_mut=1/n)", "ACO": "ACO", "Random": "Random"}
C_NOM, C_UP = "#4C78A8", "#F58518"


def load(mc_path, ga_path):
    df = pd.read_csv(mc_path)
    df["m"] = df["method"].map(SHORT)
    if Path(ga_path).exists():
        g = pd.read_csv(ga_path)
        g["scale"], g["m"] = "large", GA_TUNED
        df = pd.concat([df, g], ignore_index=True)
    return df


def save_tex(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    print(f"--- {path}\n{text}")


def f0(x):
    return f"{x:,.0f}".replace(",", r"\,")


def pm(mean, sd):
    return f"{f0(mean)} $\\pm$ {f0(sd)}"


# ------------------------------------------------------------------ tables
def table_quality(df, bound_vac, path):
    lb = W_VAC * bound_vac
    sub = df[(df.scale == "large") & df["mode"].isin(["nominal", "baseline"])]
    g = sub.groupby("m")
    rows = []
    for m in ORDER:
        if m not in g.groups:
            continue
        s = g.get_group(m)
        gap = s["nominal_cost"].mean() / lb - 1
        rows.append(f"{TEX[m]} & {pm(s['nominal_cost'].mean(), s['nominal_cost'].std())} & "
                    f"{f0(s['ov_vac'].mean())} & {s['ov_lits'].mean():.1f} & {gap:+.1%} \\\\".replace("%", r"\%"))
    body = "\n".join(rows)
    save_tex(path, rf"""\begin{{table}}[h]
\centering
\begin{{tabular}}{{lrrrr}}
\toprule
Method & Cost (mean $\pm$ sd) & OR overrun (min) & Bed overrun & Gap to bound \\
\midrule
{body}
\bottomrule
\end{{tabular}}
\caption{{Large scale (n = 420), schedules planned on point-prediction LOS; 10 seeds. Cost $=-$fitness (lower is better). Lower bound on cost: {f0(lb)} ($= 5 \times {bound_vac:g}$ min of unavoidable overrun in one specialty).}}
\label{{tab:quality}}
\end{{table}}
""")


def table_time(df, path):
    sub = df[(df["mode"].isin(["nominal", "upper"])) & (df.m != GA_TUNED)]
    t = sub.groupby(["m", "scale"])["time_s"].mean().unstack()
    t = t.sort_values("large")
    rows = [f"{TEX[m]} & {t.loc[m, 'small']:.2f} & {t.loc[m, 'large']:.2f} \\\\" for m in t.index]
    body = "\n".join(rows)
    save_tex(path, rf"""\begin{{table}}[h]
\centering
\begin{{tabular}}{{lrr}}
\toprule
Method & Small (s) & Large (s) \\
\midrule
{body}
\bottomrule
\end{{tabular}}
\caption{{Mean planning time per run (both planning modes, all seeds), default hyperparameters.}}
\label{{tab:time}}
\end{{table}}
""")


def robustness_stats(df):
    sub = df[(df.scale == "large") & df["mode"].isin(["nominal", "upper"])]
    out = {}
    for m in [x for x in ORDER if x != "Random"]:
        s = sub[sub.m == m]
        if s.empty:
            continue
        piv = s.pivot_table(index="seed", columns="mode", values="mc_mean")
        d = (piv["upper"] - piv["nominal"]).dropna()
        out[m] = {
            "mc_nom": s[s["mode"] == "nominal"]["mc_mean"].mean(),
            "inc_nom": s[s["mode"] == "nominal"]["cost_increase"].mean(),
            "mc_up": s[s["mode"] == "upper"]["mc_mean"].mean(),
            "inc_up": s[s["mode"] == "upper"]["cost_increase"].mean(),
            "d_mean": d.mean(),
            "d_se": d.std() / np.sqrt(len(d)),
        }
    return pd.DataFrame(out).T


def table_robustness(df, path):
    r = robustness_stats(df)
    rows = []
    for m, x in r.iterrows():
        rows.append(f"{TEX[m]} & {f0(x.mc_nom)} & {x.inc_nom:+.0f} & {f0(x.mc_up)} & "
                    f"{x.inc_up:+.0f} & ${x.d_mean:+.0f} \\pm {x.d_se:.0f}$ \\\\")
    body = "\n".join(rows)
    save_tex(path, rf"""\begin{{table}}[h]
\centering
\begin{{tabular}}{{lrrrrr}}
\toprule
 & \multicolumn{{2}}{{c}}{{Planned on point LOS}} & \multicolumn{{2}}{{c}}{{Planned on upper bound}} & Paired $\Delta$ \\
\cmidrule(lr){{2-3}} \cmidrule(lr){{4-5}}
Method & E[cost] & Increase & E[cost] & Increase & (upper $-$ point) \\
\midrule
{body}
\bottomrule
\end{{tabular}}
\caption{{Large scale. Frozen schedules re-evaluated on 200 LOS scenarios drawn from the 90\% conformal interval; 10 seeds. E[cost] is the mean cost over scenarios; Increase is E[cost] minus the cost on the point-prediction instance; the last column is the paired difference in E[cost] (mean $\pm$ standard error over seeds).}}
\label{{tab:robustness}}
\end{{table}}
""")


# ----------------------------------------------------------------- figures
def fig_cost(df, bound_vac, path):
    lb = W_VAC * bound_vac
    sub = df[(df.scale == "large") & (df["mode"] == "nominal")]
    ms = [m for m in ORDER if m in set(sub.m) and m != "Random"]
    mean = [sub[sub.m == m]["nominal_cost"].mean() for m in ms]
    sd = [sub[sub.m == m]["nominal_cost"].std() for m in ms]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.errorbar(range(len(ms)), mean, yerr=sd, fmt="o", color=C_NOM, capsize=4)
    ax.axhline(lb, color="black", ls="--", lw=1, label=f"lower bound = {lb:,.0f}")
    for i, v in enumerate(mean):
        ax.annotate(f"{v / lb - 1:+.1%}", (i, v), textcoords="offset points",
                    xytext=(8, 6), fontsize=8)
    ax.set_xticks(range(len(ms)))
    ax.set_xticklabels([PLOT[m] for m in ms])
    ax.set_ylabel("cost (lower = better)")
    ax.set_title("Large scale: cost of the planned schedule (mean $\\pm$ sd, 10 seeds)")
    ax.legend()
    plt.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close()


def fig_time(df, path):
    sub = df[(df["mode"].isin(["nominal", "upper"])) & (df.m != GA_TUNED)]
    t = sub.groupby(["m", "scale"])["time_s"].mean().unstack()
    t = t.reindex([m for m in ORDER if m in t.index])[["small", "large"]]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    t.plot(kind="bar", ax=ax, logy=True, color=["#F58518", "#4C78A8"], rot=0)
    ax.set_xticklabels([PLOT[m] for m in t.index])
    ax.set_ylabel("mean time per run (s, log scale)")
    ax.set_xlabel("")
    ax.set_title("Planning time")
    plt.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close()


def fig_robust(df, path):
    r = robustness_stats(df)
    x = np.arange(len(r))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    w = 0.38
    axes[0].bar(x - w / 2, r.inc_nom, w, color=C_NOM, label="planned on point LOS")
    axes[0].bar(x + w / 2, r.inc_up, w, color=C_UP, label="planned on upper bound")
    axes[0].set_title("(a) Cost increase when LOS is sampled")
    axes[0].set_ylabel("E[cost] $-$ cost on point instance")
    axes[0].legend()
    axes[1].bar(x, r.d_mean, 0.6, yerr=r.d_se, capsize=4, color="#7F7F7F")
    axes[1].axhline(0, color="black", lw=0.8)
    axes[1].set_title("(b) Paired change in E[cost]: upper $-$ point planning")
    axes[1].set_ylabel("cost difference (negative = upper bound better)")
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels([PLOT[m] for m in r.index])
    plt.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", default="results_mc.csv")
    ap.add_argument("--ga", default="results_ga_sensitivity.csv")
    ap.add_argument("--bound-ov-vac", type=float, default=1038.0,
                    help="unavoidable OR overrun in minutes (floor_check.py: 15438 - 14400)")
    args = ap.parse_args()

    df = load(args.mc, args.ga)
    table_quality(df, args.bound_ov_vac, "tables/table1_quality.tex")
    table_time(df, "tables/table2_time.tex")
    table_robustness(df, "tables/table3_robustness.tex")
    fig_cost(df, args.bound_ov_vac, "figures/fig1_cost_large.png")
    fig_time(df, "figures/fig2_time.png")
    fig_robust(df, "figures/fig3_robustness.png")
    print("\nSaved figures/fig1_cost_large.png, fig2_time.png, fig3_robustness.png "
          "and tables/table{1,2,3}_*.tex")


if __name__ == "__main__":
    main()