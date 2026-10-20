# Incorporation of Colleagues' Report Material

Integrated on 20 October 2026 into the English article on `codex/report-fil-rouge`.
This is a document integration, not a merge of the source branches' application
code or an independent re-training of their predictive models.

## Pinned sources and attribution

| Source | Commit | Incorporated material |
| --- | --- | --- |
| `report/latex` | `8708301f03d4f365e4ec25025fb59cff4f437d93` | Introduction and problem/literature material, source-workbook audit, derived targets, data limitations and proposed predictive evaluation design. |
| `model/los-bridge` | `d2dc2260d7b9c4b1ed2a49e6889b08fe0c484888` | Virna Lissi Martinez Sanchez's original LOS uncertainty report, updated structural analysis, bridge and experiment definitions, committed result CSVs, discussion and limitations. |

Exact source copies are under `contributions/`. The file-level SHA-256 values
and source commit IDs are in `contributions/manifest.json`. The article cites
both the group data audit and the individual LOS contribution. Original source
language and notices are retained in this archive; the compiled article is in
English. Empty algorithm/results placeholders in the old report are not
reproduced as completed scientific content. The source articles' overlapping
background is consolidated with the existing introduction and literature review.

## Where the material appears

- Section 3: additional literature on outpatient/inpatient differences,
  integrated bed planning, neural-network surrogates and predictive-prescriptive methods.
- Section 5: aggregate mathematical formulation and LOS objective.
- Section 6: hybrid search description and prediction/execution interface.
- Section 7: original data audit, prediction-time requirements, target
  definitions, LOS model, matching, scheduling instances and scenario protocol.
  Selected annual, missingness and timestamp checks are nested here, with
  fuller population and discrepancy detail preserved in the source archive.
  There is no separate appendix.
- Section 8: original five-method comparison, mutation sensitivity, session
  granularity, uncertainty results, load and matched-only sensitivity.
- Sections 9 and 10: interpretation, limitations, managerial implications and
  provisional conclusions, preserving the scope of the original contribution.
- `bibliography.bib`: imported references converted from biblatex to the
  current BibTeX/natbib format; existing entries are reused rather than duplicated.

## Numerical verification and interpretation

`venv/bin/python report/scripts/summarise_los_results.py` regenerates three
LaTeX tables and three aggregate figures from pinned CSVs. It verifies cost
identities, scenario-cost differences, unique run keys, paired seed coverage,
load settings and the matched-only cohort size. It does not run private data
preprocessing, load saved ML models or repeat the optimisation campaign.

Repeated noise/tracking evaluations are filtered before aggregating saved
plans. Main comparisons use ten seed-level replicates; the 200 scenarios per
seed are not counted as 200 optimiser runs. Cost dispersion uses sample SD;
paired upper-minus-point differences use sample SD divided by sqrt(10).
Runtime for the original campaign averages the two planning modes, whereas
the structural table reports point-planning runtime. The captions state this.

The integrated text makes these evidence-based adjustments to the source prose:

1. A cost near 5198 is close to the overload lower bound of 5190; it is not
   a certificate that the full objective has reached its optimum.
2. The split-session campaign includes four methods, not ACO. Its hybrid
   result is the lowest mean among those four tested configurations.
3. For two 240-minute sessions, the floor/truncated upper-minus-point
   scenario-mean differences are -88.6 +/- 68.8 (SA), +31.3 +/- 87.6 (Tabu),
   +9.1 +/- 34.1 (hybrid), and -98.4 +/- 167.8 (GA), expressed as mean +/- SE.
   A uniform increase of 78-95 is not supported by those CSVs. The original
   one-session results and the split-session results are kept separate.
4. The load experiment varies bottleneck-speciality operating-block load
   with bed capacity fixed at 42. It cannot establish a 93% bed-utilisation
   threshold or prove that beds are always the dominant bottleneck.
5. Matched-only filtering removes 57 cases and changes demand. Its zero
   overload lower bound makes relative gaps undefined; its nonzero final
   cost includes balance penalties. It does not isolate the effect of matching.
6. `bridge_los.py` uses the median of matched predictions within the selected
   window for unmatched rows, with a three-day fallback. Calling this a
   training-only global median would be inaccurate.
7. The bridge's HIGH flag thresholds regression output at four days. It is
   distinguished from a separately evaluated risk classifier.
8. The original audit counts 14,649 raw cases. These counts are attributed
   to that source and not conflated with cleaned, test or matched cohorts.
9. Predictive metrics (MAE 0.412 days, R2 0.789, coverage 89.4%) remain
   explicitly attributed to the contributor. Their calibration, feature
   availability and evaluation split need saved-model verification.
10. Inclusive total LOS, the optimiser's additional-day bed convention,
    mean shifts from clipping/rounding and horizon truncation are explicit.
    No general hospital-deployment recommendation is inferred from these runs.

## Project review and room-study integration (20 October 2026)

The project review filled the previous room/Mesa gaps within the same eleven
sections. Section 5 now formalises allocation, deterministic decoding and the
lexicographic room objective; Section 6 documents coupled parameters, incumbents,
worker budgets and versioned proposal acceptance. Sections 7–8 add the actual
cohorts, paired protocols, exact reference, historical and generated execution
results, and a separate median/oracle experiment. Sections 9–10 synthesise these
findings with LOS without pooling objectives or replication units.

Pinned room inputs and their SHA-256 values are in
`contributions/room-study/manifest.json`. The primary aggregate campaign contains
576 executions/144 initial plans; the separate duration campaign contains
1152 executions/288 initial plans. Their median executions are separate reruns.
No row-level episode exports, private model predictions or trained models are
copied into the report. The independently checked execution-audit receipt is
stored alongside the aggregates. Reproduction commands are in README.md.

The current `model/or-occupation` code and its review are pinned at
`a9607f9bc3247bcb8e8af094c04e797ee69505e7`. Its current selection/calibration
protocol is described; historical numerical tables explicitly identified as
belonging to a previous protocol are not promoted to current model results.
Notebook split rules are described separately from the room median baseline,
which uses a temporal split without patient-disjoint exclusion.

## Evidence still needed

- Current saved-model calibration and held-out ML-to-Mesa performance on the
  same room-occupancy target, workloads, resource assumptions and budgets.
- LOS target/bed-accounting reconciliation and prediction-matching analysis
  that does not conflate matching with removing demand.
- More independent days and generated samples; several loads, budgets,
  disruption patterns and sequencing policies; equal total policy budgets.
- Clinical resource eligibility, staff, ward occupancy and multi-day admission
  decisions, with appropriate workflow and prospective validation.

These are limitations stated in the article, not claims that the relevant
project branches or future features have been experimentally validated here.
