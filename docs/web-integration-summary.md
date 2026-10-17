# KYST integration: summary for the team

## Short message to share

KYST now connects the existing duration and length-of-stay models, optimization
algorithms and Mesa simulations to the web application. Surgeons can request
dates using model estimates and confirm a date with room and bed capacity
checks. Planners can optimize pending requests together, publish proposals for
clinical confirmation, refresh them after changes, and test hypothetical room
and bed scenarios. Confirmed operations remain protected and are flagged for
review if a resource change affects them. The illustrated guide demonstrates
these workflows using synthetic patients.

## What changed for users

- **New patients:** the consultation form can call the trained room-duration
  and LOS predictors when configured. The usual A/B suggestions explain room
  load, beds over the predicted stay and the emergency margin. The immediate
  individual suggestions still use the fast greedy scheduler.
- **Cohort planning:** the planner can choose among the ten existing methods,
  preview assignments and unassigned cases, then publish recalculated
  proposals. Publication creates suggestions; clinicians confirm them
  individually, with a fresh capacity check.
- **Adaptation:** changes to requests, rejected dates, cancellations and
  resources enter a persistent queue. A manual refresh, or the optional
  background worker, updates pending proposals. Failed runs preserve the
  previous proposals. Confirmed bookings stay fixed; conflicts are shown for
  team review.
- **Simulation:** the planning page offers a room-only Mesa preview and a
  multi-day room-and-bed preview. These are what-if calculations and create
  no reservations. The multi-day preview counts existing bookings and carries
  waiting cases forward.
- **Reference material:** five illustrated user stories, their editable
  sources, original synthetic screenshots and a six-page PDF are tracked in
  this branch for colleagues and the final presentation.

## What this PR does not establish

The contribution connects and adapts existing research components; it does
not introduce new ML models or new metaheuristic algorithms. Trained artifacts
must be supplied separately; demonstration predictions remain the default.
The models need retraining/calibration for the fields available in the web
form before clinical use. Mesa uses simplified rooms and hypothetical duration
factors, rather than live hospital observations. Its multi-day web preview is
limited to 14 days and 30 cases. The optional replanning worker requires one
API process. This is an integrated research demonstration, not a validated
clinical deployment or a guarantee of oracle performance.

## References

- [Illustrated user stories](web-user-stories/user-stories.md)
- [HTML guide](web-user-stories/index.html)
- [Shareable PDF](web-user-stories/output/pdf/kyst-user-stories.pdf)
- [Guide sources and rebuild instructions](web-user-stories/README.md)
- [Detailed integration, configuration, limitations and validation](web-full-system-integration.md)
