# Proposed title

Add opt-in full-stay feasibility-first SA with independent validation and scaling experiments

# Proposed description

The vacation optimizer can hide bed demand after its last surgery day, and weighted load balance can rank an infeasible assignment above a feasible one. Add a separate opt-in full-stay problem and float feasibility-first objective using the existing SA loop, with explicit future bed supply, complete assignment checks, a separate feasible incumbent and an independent calendar validator. Reject mapping/set capacity inputs that previously consumed keys or unordered elements as supply.

Keep the existing optimizer defaults and web/API interfaces unchanged. This is a research scheduling mode, not a drop-in replacement for all plotting/disruption helpers or a production booking path.

Evidence is mixed and preserved in full:

- Original 16-patient campaign: final feasibility A/B/C = 40/60, 49/60, 55/60.
- Fresh 60-patient workloads: 21/40, 40/40, 40/40. This supports full-stay accounting but does not show an incremental feasibility-rate benefit from feasibility-first scoring.
- Bounded 300-patient pilot: 2/4, 4/4, 4/4, on only two workloads.
- Exact replay of five original failures confirms local optima/plateaus and rapidly frozen uphill exploration; no parameters were tuned to make them pass.

Validation: 139 relevant tests run, 138 passed and one confidential-data skip; independent replay checks all 312 saved final schedules plus 278 feasible incumbents across both campaigns. New larger runs all used 6,000 evaluations, without deadline stops. Source/input/output hashes and synthetic witnesses accompany the results.

Before application exposure, review future capacity calendars, per-unit beds and accepted reservations, reconstruction/plot horizon compatibility, timeouts and fallbacks. Detailed findings and exact commit allowlist are in `experiments/S1_S2_GENERALIZATION_REVIEW.md` and `experiments/COMMIT_FILES.txt`. No trained model, patient dataset or article is changed.
