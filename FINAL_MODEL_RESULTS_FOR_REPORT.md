# Verified additions that may be summarized in the scientific report

These are new completed experiments; no final article was edited.

Using seven features exposed by the consultation input contract, a validation-
selected HGB model achieved OR occupancy MAE16.62 minutes on3,043 held-out2022
cases, compared with17.90 for the existing model under web-field masking and
18.15 for train-only intervention medians. The original full-feature retrospective
model remained more accurate (14.33). Historical feature capture times were
not verified; this is not prospective deployment validation.

A reproducible consultation-only LOS XGB artifact achieved MAE0.506 inclusive
days on3,059 held-out cases and89.24% coverage for a nominal90% interval.
It did not beat intervention medians (0.486 days). Coverage among actual stays
>=7 days was only25.37%, exposing an important limitation hidden by marginal
coverage. A separate current full-feature reproduction achieved0.450 days MAE;
these results must not be mixed with older LOS implementations.

A paired static scheduling pilot used100 distinct held-out cases across eight
daily cohorts, two room-capacity settings, two solver seeds, identical initial
allocations and500 evaluations/run (64 runs). With one room, ML left completed
counts unchanged, reduced total start delay26.125 minutes/day, and increased
overtime12.5 minutes/day. With two rooms, it added0.0625 completed cases/day,
reduced total start delay86.5 minutes/day, and increased overtime18.75 minutes/day.
LOS was fixed and beds nonbinding. Repeated seeds were grouped within cohorts.
The result demonstrates operational tradeoffs, not uniform ML superiority.

Actual web adapter classes loaded all five new artifacts successfully. A synthetic
saved-model-to-S1/S2 test passed independent full-stay validation. The executed
regression suite ran184 tests:183 passed, one skipped. All312 previously saved
S1/S2 returned schedules were independently reverified.
