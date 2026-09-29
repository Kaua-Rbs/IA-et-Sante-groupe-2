# Comparison results

These are aggregate exports for the [comparison report](../metaheuristics-mesa-comparison.md) and its [French version](../metaheuristics-mesa-comparison-fr.md).
They contain no patient-level rows or original patient/personnel identifiers.

- `runs.csv`: one row per execution; the key is `(group, instance_id, method, seed, scenario, policy)`.
- `initial-plans.csv`: one row per initial optimization; `unstarted`, `overtime`, `changes` and `cost` are **predicted** objective components. `gap` exists only for the exact small reference.
- `provenance.json`: evaluated source hashes, commit, workbook fingerprint, dependencies and room assumptions.
- `generated-completions.png`: descriptive mean paired differences for the generated workloads, without confidence intervals.

There are 576 execution rows, but only 144 distinct initial plans. The four execution conditions reuse each initial plan. Solver seeds repeat a fixed workload; they are not independent hospital days. Baseline seed repetitions are deterministic.

`runs.csv` uses realized outcomes. Overtime sums room occupancy and turnover after closing across rooms. `mean_start_delay_minutes` excludes unstarted and initially unassigned cases; use `delay_measured_cases` when pooling delays. Utilization excludes turnover and uses total configured room-hours as its denominator, including closure time. Initial solver time is included in each replay's total; do not sum those totals to estimate total campaign wall time.

The 100-case runs were sequential. The 300-case runs used four concurrent batches, so elapsed search times include shared CPU load. The common stopping budget was 1,000 fitness calls per nontrivial request, with a 60-second safety deadline. Reactive execution can invoke extra requests; static and reactive total search effort therefore differ.

Reproduction from the repository root:

```bash
bash scripts/run_comparison_campaign.sh artifacts/comparison-rerun
venv/bin/python -m pip install reportlab==5.0.1  # optional PDF dependency
venv/bin/python scripts/build_comparison_report.py --input artifacts/comparison-rerun
```

The builder audits execution constraints and recomputes aggregate metrics before writing the report. Full schedules and episode event logs remain local under ignored `artifacts/`. Source data remains under ignored `resources/`.

The French PDF can be regenerated with `venv/bin/python scripts/render_french_comparison.py`. This checks the translated numerical tables against the English report and renders `generated-completions-fr.png` from the same aggregate CSV; it does not rerun experiments.
