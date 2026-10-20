"""Aggregate-only final comparison figures and tables; no patient-level inputs."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--scheduling", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("Output must be new or empty")
    paths = [args.models/"model_metrics.csv", args.models/"report.json",
             args.scheduling/"scheduling_runs.csv", args.verification/"artifact_verification.json"]
    table = pd.read_csv(paths[0])
    report = json.loads(paths[1].read_text())
    runs = pd.read_csv(paths[2])
    artifact = json.loads(paths[3].read_text())
    comparison = []
    for kind in ("room", "los"):
        test = table.loc[table.kind.eq(kind)&table.partition.eq("test")]
        for model in ("intervention_median", "consult_HGB_log" if kind=="room" else "consult_XGB_log"):
            row = test.loc[test.model.eq(model)].iloc[0]
            comparison.append({"task":kind, "model":model, "test_n":int(row.n), "mae":row.mae,
                               "long_mae":row.long_mae, "long_bias":row.long_bias})
    comparison.extend([{"task":"room", "model":name, "test_n":report[name]["n"], "mae":report[name]["mae"],
                        "long_mae":report[name]["long_mae"], "long_bias":report[name]["long_bias"]}
                       for name in ("existing_full_features", "existing_web_masked")])
    pd.DataFrame(comparison).to_csv(args.output/"model_comparison.csv", index=False)
    fig, axes = plt.subplots(1,2,figsize=(11,4.5))
    labels = ["Existing full\nretrospective", "Existing\nweb-masked", "Train-only\nintervention median", "Consultation\nHGB (selected)"]
    vals = [report["existing_full_features"]["mae"], report["existing_web_masked"]["mae"],
            comparison[0]["mae"], comparison[1]["mae"]]
    axes[0].bar(range(4),vals,color=["#999999","#b7b7b7","#df9f44","#3789ad"])
    axes[0].set_xticks(range(4),labels,fontsize=8)
    axes[0].set_ylabel("2022 held-out MAE (minutes)")
    axes[0].set_title("OR occupancy: available inputs matter")
    for i,v in enumerate(vals): axes[0].text(i,v+.25,f"{v:.2f}",ha="center",fontsize=9)
    losvals = [comparison[2]["mae"],comparison[3]["mae"],report["los_full_reproduction"]["test_mae_days"]]
    axes[1].bar(range(3),losvals,color=["#df9f44","#3789ad","#999999"])
    axes[1].set_xticks(range(3),["Train-only\nintervention median","Consultation\nXGB","Full-feature\nreproduction"],fontsize=8)
    axes[1].set_ylabel("2022 held-out MAE (inclusive days)")
    axes[1].set_title("LOS: consultation ML does not beat median")
    for i,v in enumerate(losvals): axes[1].text(i,v+.008,f"{v:.3f}",ha="center",fontsize=9)
    fig.tight_layout()
    for extension in ("png","svg"): fig.savefig(args.output/f"prediction_mae.{extension}",dpi=160)
    plt.close(fig)
    measures = [("completed","Completed cases"), ("overtime_minutes_including_turnover","Overtime incl. turnover (min)"),
                ("total_start_delay_minutes","Total start delay (min)")]
    grouped = runs.groupby(["cohort","rooms","arm"])[[name for name,_ in measures]].mean().unstack("arm")
    fig,axes=plt.subplots(1,3,figsize=(12,4))
    for ax,(name,label) in zip(axes,measures):
        diff=grouped[name]["ml"]-grouped[name]["median"]
        for j,rooms in enumerate((1,2)):
            values=diff.xs(rooms,level="rooms").to_numpy()
            ax.scatter(j+np.linspace(-.10,.10,len(values)),values,color="#3789ad",alpha=.8)
            ax.plot([j-.17,j+.17],[values.mean()]*2,color="#bb4d32",lw=3)
        ax.axhline(0,color="grey",lw=.8)
        ax.set_xticks([0,1],["1 room","2 rooms"])
        ax.set_ylabel("ML minus median")
        ax.set_title(label,fontsize=10)
    fig.suptitle("Scheduling tradeoffs: 8 held-out daily cohorts, 2 search seeds averaged per dot",fontsize=11)
    fig.tight_layout()
    for extension in ("png","svg"): fig.savefig(args.output/f"scheduling_tradeoffs.{extension}",dpi=160)
    plt.close(fig)
    coverage={"OR P95 overall":report["room"]["test_coverage_selected"]["p95"],
              "OR P95 actual >=120min":artifact["room_tail"]["coverage"],
              "LOS 90% overall":report["los"]["test_coverage_selected"]["interval_90"],
              "LOS 90% actual >=7days":artifact["los_tail"]["coverage"]}
    pd.DataFrame([{"group":k,"coverage":v} for k,v in coverage.items()]).to_csv(args.output/"coverage.csv",index=False)
    summary=runs.groupby(["rooms","arm"])[[n for n,_ in measures]+["evaluations","solver_seconds"]].mean().reset_index()
    lines=["# Verified aggregate comparison", "", "Model errors use held-out 2022 reporting partitions, previously inspected in earlier project work; model choice used early 2021 only.", "",
        "| Task | Model | Test n | MAE |", "|---|---|---:|---:|"]
    lines += [f"| {r['task']} | {r['model']} | {r['test_n']} | {r['mae']:.4f} |" for r in comparison]
    lines += ["", "| Rooms | Arm | Completed/day | Unstarted/day | Overtime min/day | Start delay min/day |", "|---:|---|---:|---:|---:|---:|"]
    means=runs.groupby(["rooms","arm"])[[n for n,_ in measures]+["unstarted"]].mean().reset_index()
    lines += [f"| {r.rooms} | {r.arm} | {r.completed:.4f} | {r.unstarted:.4f} | {r.overtime_minutes_including_turnover:.4f} | {r.total_start_delay_minutes:.4f} |" for r in means.itertuples()]
    lines += ["", "64 paired runs, 100 distinct cases, 8 daily cohorts; repeated seeds are not independent hospital instances.",
              "LOS is fixed at one day and 30 beds are explicitly available; ward outcomes were not evaluated.",
              "ML reduces start delay but increases overtime in this pilot. No uniform scheduling improvement is established.", ""]
    (args.output/"comparison_tables.md").write_text("\n".join(lines),encoding="utf-8")
    manifest={"script_sha256":sha256(Path(__file__).read_bytes()).hexdigest(),
              "input_sha256":{str(p):sha256(p.read_bytes()).hexdigest() for p in paths},
              "output_sha256":{p.name:sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir() if p.is_file()}}
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")


if __name__ == "__main__":
    main()
