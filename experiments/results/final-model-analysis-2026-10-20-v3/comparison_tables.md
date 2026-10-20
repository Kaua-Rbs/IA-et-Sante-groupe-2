# Verified aggregate comparison

Model errors use held-out 2022 reporting partitions, previously inspected in earlier project work; model choice used early 2021 only.

| Task | Model | Test n | MAE |
|---|---|---:|---:|
| room | intervention_median | 3043 | 18.1480 |
| room | consult_HGB_log | 3043 | 16.6217 |
| los | intervention_median | 3059 | 0.4861 |
| los | consult_XGB_log | 3059 | 0.5056 |
| room | existing_full_features | 3043 | 14.3331 |
| room | existing_web_masked | 3043 | 17.9005 |

| Rooms | Arm | Completed/day | Unstarted/day | Overtime min/day | Start delay min/day |
|---:|---|---:|---:|---:|---:|
| 1 | median | 6.3750 | 6.1250 | 41.6250 | 150.8750 |
| 1 | ml | 6.3750 | 6.1250 | 54.1250 | 124.7500 |
| 2 | median | 10.6250 | 1.8750 | 79.2500 | 300.6875 |
| 2 | ml | 10.6875 | 1.8125 | 98.0000 | 214.1875 |

64 paired runs, 100 distinct cases, 8 daily cohorts; repeated seeds are not independent hospital instances.
LOS is fixed at one day and 30 beds are explicitly available; ward outcomes were not evaluated.
ML reduces start delay but increases overtime in this pilot. No uniform scheduling improvement is established.
