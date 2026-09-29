"""Build an aggregate Markdown report and PDF from the fixed comparison campaign.

Run from repository root. PDF generation needs optional reportlab; numerical
analysis uses the project's pandas/matplotlib. Raw episode exports stay ignored.
"""
import argparse
import json
from pathlib import Path
from html import escape
import re
from hashlib import sha256

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

METHODS = ['baseline', 'annealing', 'tabu', 'genetic', 'hybrid', 'aco']
LABELS = dict(zip(METHODS, ['Baseline', 'Annealing', 'Tabu', 'Genetic', 'Tabu x annealing', 'ACO']))


def table(frame):
    def fmt(x):
        if isinstance(x, float):
            return f'{x:.2f}'
        return str(x)
    rows = [[fmt(x) for x in row] for row in frame.itertuples(index=False, name=None)]
    return '\n'.join(['| ' + ' | '.join(map(str, frame.columns)) + ' |',
                      '| ' + ' | '.join(['---'] * len(frame.columns)) + ' |'] +
                     ['| ' + ' | '.join(row) + ' |' for row in rows])


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--input', type=Path, default=Path('artifacts/comparison-2026-09-28'))
    cli.add_argument('--markdown', type=Path, default=Path('docs/metaheuristics-mesa-comparison.md'))
    cli.add_argument('--pdf', type=Path, default=Path('artifacts/comparison-2026-09-28/metaheuristics-mesa-comparison.pdf'))
    args = cli.parse_args()
    frames, manifests, initial = [], {}, []
    for group in ('small', 'historical', 'large'):
        folder = args.input / group
        manifest = json.loads((folder / 'manifest.json').read_text())
        manifests[group] = manifest
        frame = pd.read_csv(folder / 'summary.csv')
        frame['group'] = group
        frames.append(frame)
        for path in sorted(folder.glob('*-initial.json')):
            record = json.loads(path.read_text())
            stem, method, seed = path.stem.removesuffix('-initial').rsplit('-', 2)
            initial.append({'group': group, 'instance_id': stem, 'method': method, 'seed': int(seed),
                            **record['report']['objective'], 'seconds': record['report']['elapsed_seconds'],
                            'gap': record['exact_objective_gap'], 'stop': record['report']['stop_reason'],
                            'evaluations': record['report']['evaluations']})
    data, plans = pd.concat(frames, ignore_index=True), pd.DataFrame(initial)
    assert len(data) == 576 and len(plans) == 144
    assert (data.completed + data.unstarted == data.cases).all()
    assert data[['failures', 'search_failures', 'timeouts', 'search_deadline_stops']].sum().sum() == 0
    paired = data.pivot(index=['group', 'instance_id', 'method', 'seed', 'scenario'], columns='policy')
    for metric in ('completed', 'unstarted', 'overtime_minutes_including_turnover', 'room_occupancy_minutes_in_hours', 'total_start_delay_minutes'):
        a = paired[metric].xs('no_outage', level='scenario')
        assert (a['static'] == a['reactive']).all(), metric
    # Validate room execution independently from the exported aggregate metrics.
    checked = 0
    for group, manifest in manifests.items():
        for path in (args.input / group).glob('*.json'):
            if path.name == 'manifest.json' or path.name.endswith('-initial.json'):
                continue
            run = json.loads(path.read_text())
            configs = manifest['instances'][run['instance_id']]['configurations']
            config = next(c for c in configs if bool(c['outage']) == (run['scenario'] == 'outage'))
            completed = [x for x in run['executed_schedule'] if x['status'] == 'completed']
            episodes = run['executed_schedule']
            assert len(episodes) == run['metrics']['cases']
            assert len({x['case_id'] for x in episodes}) == len(episodes)
            assert all(re.fullmatch(r'case-[0-9]{4}', x['case_id']) for x in episodes)
            assert all(x['status'] in ('waiting', 'completed') for x in episodes)
            assert len(completed) == run['metrics']['completed']
            assert sum(x['status'] == 'waiting' for x in episodes) == run['metrics']['unstarted']
            by_room = {}
            overtime = occupancy = 0
            for item in completed:
                assert config['opening'] <= item['start'] < config['closing']
                assert item['finish'] > item['start']
                outage = config['outage']
                if outage and item['room_id'] == outage['room_id']:
                    assert not outage['start'] <= item['start'] < outage['end']
                by_room.setdefault(item['room_id'], []).append(item)
                overtime += max(0, item['finish'] + config['turnover'] - max(item['start'], config['closing']))
                occupancy += max(0, min(item['finish'], config['closing']) - max(item['start'], config['opening']))
            for items in by_room.values():
                items.sort(key=lambda x: x['start'])
                assert all(a['finish'] + config['turnover'] <= b['start'] for a, b in zip(items, items[1:]))
            assert overtime == run['metrics']['overtime_minutes_including_turnover']
            assert occupancy == run['metrics']['room_occupancy_minutes_in_hours']
            for report in run['search_reports']:
                assert report['evaluations'] <= 1000
                if report['stop_reason'] == 'evaluations':
                    assert report['evaluations'] == 1000
            checked += 1
    for group in manifests:
        for initial_path in (args.input / group).glob('*-initial.json'):
            prefix = initial_path.name.removesuffix('-initial.json')
            schedules = []
            for run_path in (args.input / group).glob(prefix + '-*.json'):
                if run_path == initial_path:
                    continue
                run = json.loads(run_path.read_text())
                schedules.append(run['schedule_history'][0])
            assert len(schedules) == 4 and all(x == schedules[0] for x in schedules)
    workbook = Path('resources/donnees_bloc_nettoyees.xlsx')
    if workbook.exists():
        assert sha256(workbook.read_bytes()).hexdigest() == manifests['historical']['dataset_sha256']
    assert len({m['code']['implementation_sha256'] for m in manifests.values()}) == 1
    # Shareable exports contain aggregate metrics only, never episode-level data.
    exported = args.markdown.parent / 'comparison-results'
    exported.mkdir(parents=True, exist_ok=True)
    data.to_csv(exported / 'runs.csv', index=False)
    plans.to_csv(exported / 'initial-plans.csv', index=False)
    provenance = {g: {k: m[k] for k in ('code', 'dataset_sha256', 'dependencies', 'python', 'instances', 'max_evaluations', 'solver_budget_seconds')} for g, m in manifests.items()}
    for group, manifest in manifests.items():
        provenance[group]['execution_layout'] = manifest.get('execution_layout', 'Sequential runs')
    (exported / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    quality = manifests['historical']['data_quality']
    pages = []
    def page(title, text):
        title = re.sub(r'^\d+\. ', '', title)
        pages.append(f'## {len(pages)+1}. {title}\n\n' + text.strip())
    page('1. Purpose and scope', '''
This report compares five metaheuristics on a common operating-room scheduling problem, then evaluates their coupling to a Mesa simulation. It covers an exactly enumerable small instance, three historical daily workloads, and larger generated workloads.

The implementation is working and the campaign contains 576 execution runs. These represent 144 initial plans replayed under four policy/scenario combinations. The experiment compares allocation algorithms under a fixed budget; it does not establish a universal ranking or reproduce the hospital's actual decisions.

Two distinct uses of “hybrid” must be separated. Tabu x annealing combines two search algorithms. Optimizer-Mesa coupling combines a scheduler with an execution simulation and reactive replanning. Every search algorithm can participate in the second form of hybridization.

The main question is whether a method finds better predicted room allocations and whether those gains survive execution with hidden historical durations and a temporary room closure. The two outcomes are measured separately.

**Reading the results.** Fewer unstarted cases is the first priority. Overtime must be read alongside case completion: a plan that leaves more patients waiting may appear better on overtime alone. Three solver seeds and two generated samples per size support a descriptive comparison, not a claim of statistical superiority.
''')
    page('2. Data and patient-episode agents', f'''
The cleaned workbook contains {quality['input_rows']:,} rows. Parsing retains {quality['usable_rows']:,} episodes and excludes {quality['excluded_rows']} rows, all because of zero clock endpoints in this version of the file. The source workbook is not modified.

| Source field | Role in this experiment |
| --- | --- |
| date_inter | Select the training period or a held-out daily workload |
| interv_type | Normalized procedure category used to predict duration |
| Room entry and exit clocks | Calculate hidden realized room occupancy |
| no_cas | Internal deterministic ordering only; replaced by local case IDs |
| Clinical/personnel fields | Not used as scheduling attributes |

The exact clock fields are heure_d_entree_en_salle_d_operation_calimed and heure_de_sortie_de_salle_d_operation_calimed. Missing, invalid, zero or nonpositive intervals are excluded; exit-before-entry is not interpreted as overnight surgery.

Duration estimates use {quality['training_rows']:,} valid episodes from 2019-2021. A procedure median is used only with at least ten training episodes; otherwise the global training median is {quality['fallback_median_minutes']:.0f} minutes. Predicted and realized durations are rounded upward to whole minutes. Realized durations and future completion times are never supplied to the scheduler. Starts and completions become observable only as execution occurs.

A Mesa agent represents one episode, with a local ID, procedure, prediction and waiting/running/completed state. Realized duration belongs to execution. Rooms are resources, not deliberating agents. No original patient or personnel identifiers are exported in the shared report tables.

Historical days are treated as complete daily workloads ready at opening. The selected days (9, 15 and 25 cases) have no excluded source rows. The 9-case day is a convenient low-volume example; the 15-case day is the median and the 25-case day the maximum among dates without exclusions, ordered by valid case count. Generated workloads sample valid 2022 rows with replacement, keeping procedure and outcome paired; they do not preserve within-day correlations.
''')
    page('3. A common optimization problem', '''
A candidate assigns every waiting case to a room. The shared decoder orders cases within each room by ascending predicted duration, breaking ties by local ID. It respects availability, turnover and known closures. A case whose decoded start is at or after closing is explicitly unassigned. Running and completed cases are preserved. Finishes are allowed after closing, so completing more cases can entail substantial overtime.

This is an allocation search with a fixed sequencing rule. It does not search all possible surgical sequences. The exact optimum below is therefore exact only within this representation and the stated objective.

The predicted cost is minimized in the following strict order: unstarted waiting cases U, overtime O, then changed waiting decisions R. With N waiting cases and B equal to their total predicted duration plus turnover:

**C = U + (O + R / (N + 1)) / (B + 1); fitness = -C.**

Since R <= N and O <= B, one additional unstarted case dominates the lower-priority terms. One overtime minute dominates all decision changes. At initial planning R = 0. Fixed activity contributes a constant and is excluded from the request objective, but remains in execution metrics. Costs with different denominators should not be used as a cross-size performance ranking; report U and O as well.

**What happened to 5, 3 and 0.05?** The native vacation optimizer still minimizes 5 x excess vacation minutes + 3 x excess bed-days + 0.05 x standard deviation of vacation loads. These are configurable default trade-off weights in the code; this campaign supplies no clinical calibration for them. They belong to a different model and are not used in the room-only Mesa comparison. Comparing its raw scores with C would be misleading.

All methods share the same prediction inputs, decoder, validator and starting incumbent. The incumbent is a greedy allocation initially and a repaired allocation from the accepted plan during replanning. Keeping the best evaluated candidate protects the predicted objective, not the realized hospital outcome.
''')
    page('4. Algorithms actually executed', '''
| Method | Search mechanism | Coupled settings |
| --- | --- | --- |
| Baseline | Shortest prediction first; earliest feasible room | Deterministic greedy allocation |
| Annealing | One neighboring allocation; accept worsening moves probabilistically | T0=1, cooling=0.95 |
| Tabu | Best admissible sampled neighbor; memory discourages repeated moves | 15 neighbors, memory 20 |
| Genetic | Population, fitness-weighted selection, one-point crossover and mutation | Population 40, crossover 0.8, mutation 0.08, elitism |
| Tabu x annealing | Tabu candidate selection followed by annealing acceptance | 15 neighbors, memory 20, T0=1, cooling=0.97 |
| ACO | Construct allocations using pheromone and current room load | 15 ants, alpha=1, beta=2, evaporation=0.3, Q=1 |

Local moves reassign a case or swap assignments. Tabu aspiration permits a tabu move that improves the best score; if all sampled candidates are tabu, the implementation uses the best sampled candidate. The genetic population includes the incumbent. ACO records the incumbent as a best-so-far candidate while its ants construct new allocations.

**ACO in detail.** For case i and room j, selection probability is proportional to tau(i,j)^alpha x eta(j)^beta. Here eta(j) = 1 / (1 + accumulated predicted load(j) / remaining capacity(j)). This favors relatively lightly loaded rooms; it is not a full feasibility test. The common decoder applies turnover, closure and closing rules when evaluating the complete allocation. The constructive load heuristic itself does not include turnover.

After 15 ants, pheromone is multiplied by 0.7. Assignments used by the best ant of that iteration receive 1 / (1 + C) additional pheromone. The best solution found across all evaluated candidates is retained. Pheromone is initialized afresh for each scheduling request; the simulation does not maintain an inter-request ant colony.

The settings are fixed implementation defaults for this study, with the two initial temperatures adapted to the normalized objective. No hyperparameter tuning is claimed. Equal fitness-call budgets produce different numbers of iterations or generations and do not imply equal elapsed time.
''')
    page('5. How Mesa and the optimizer are assembled', '''
The control loop is: historical workload -> predicted initial allocation -> validation and acceptance -> Mesa execution -> observed room closure/reopening -> a new request for waiting cases -> validation and acceptance -> continued execution.

Mesa 3.5.1 advances in one-minute steps. Each minute processes completions and turnover release, availability changes, state synchronization, optional replanning, and eligible starts in that order. The model reads the currently accepted plan rather than installing future start callbacks that could become obsolete.

Static execution preserves initial assignments and room order. Delays shift subsequent starts. Reactive execution starts from the exact same saved initial schedule and replans at closure and reopening. The closure is first revealed when it begins; its ending time is then known. There is no replanning merely because a duration overruns its prediction.

The optimizer receives predictions, observed statuses, availability estimates and fixed commitments. Remaining time for an ongoing case is estimated from its original prediction and elapsed time, never from its hidden finish. Execution guards prevent overlap when that estimate is optimistic. A running episode finishes normally during a closure; the closure only forbids new starts.

The contract remains Scheduler.propose(request). The adapter runs nontrivial searches in a separate process, reports incumbents and respects an evaluation budget and safety deadline. Simulated time pauses during optimization. The coordinator checks case coverage, uniqueness, room/calendar feasibility and fixed commitments before accepting a result. On failure, the current plan remains protected by execution guards.

This is centralized simulation-optimization coupling. Patient agents carry episode state; they do not negotiate or independently optimize. The architecture can accept another scheduler without changing Mesa execution, provided it returns the same schedule structure and uses only visible request data.
''')
    page('6. Experimental protocol and metric definitions', '''
| Family | Workloads | Solver seeds | Execution runs |
| --- | --- | --- | --- |
| Small exact | 7 cases, 2 rooms, 128 allocations | 0, 1, 2 | 72 |
| Historical | 2022-01-03: 9; 2022-02-02: 15; 2022-10-20: 25 cases | 0, 1, 2 | 216 |
| Generated | 100 and 300 cases; sample seeds 0 and 1 | 0, 1, 2 | 288 |

Every workload/seed uses six methods, two policies and two closure scenarios. Each nontrivial search is allowed 1,000 fitness calls, counting initialization and repeats, with a 60-second safety deadline. Baseline uses no search calls. Requests with zero or one waiting case use trivial/exact handling and may consume less budget. A reactive run can use up to three request budgets, so it is not an equal-total-computation comparison against static scheduling.

Historical and generated opening hours are 08:00-17:00, with 15-minute turnover. Historical days use two identical synthetic rooms. Small-instance hours are 08:00-11:00. Room 1 closes to new starts from 10:00-12:00 (small: 09:00-10:00). Initial plans have no knowledge of the future closure.

Generated room counts are ceil(total predicted duration including turnover / (540 x 1.1)). The 1.1 target deliberately stresses capacity; rounding changes the achieved ratio. This campaign does not include a light-load sensitivity study. Only one room closes, so the disruption affects a smaller fraction of capacity as room count grows.

Completed cases include those finishing after closing; waiting cases at closing are unstarted. Overtime is actual room occupancy plus required turnover after closing, summed across rooms, not the latest wall-clock finish. Utilization counts occupancy within opening hours, excludes turnover and divides by all configured room-hours, including closure time.

Delay is max(0, actual start - initial planned start), measured only for completed cases that had an initial assignment. Newly scheduled cases and unstarted cases are excluded; delay therefore needs its own denominator. Changed decisions count revisions across replans and may count a case twice. Runtime includes worker startup and communication. These are local end-to-end measurements, not isolated algorithm kernel timings.
''')
    small = plans[plans.group.eq('small')].groupby('method').agg(gap=('gap','mean'), worst=('gap','max'), hits=('gap',lambda x: int((x.abs()<1e-9).sum())), sec=('seconds','mean')).reindex(METHODS)
    small.index = small.index.map(LABELS)
    small = small.reset_index(); small.columns = ['Method', 'Mean gap', 'Worst gap', 'Optima / 3', 'Initial s']
    exact = manifests['small']['exact_references']['small-reference']['objective']
    page('7. Small problem: comparison to the exact optimum', f'''
The small fixture has predicted durations 30, 40, 50, 60, 70, 80 and 90 minutes; hidden realized durations are 35, 50, 45, 80, 65, 100 and 120 minutes. Exhaustive enumeration evaluates all 2^7 = 128 room allocations through the common decoder.

The exact initial objective is U={exact['unstarted']}, O={exact['overtime']} minutes, C={exact['cost']:.6f}. The gap below is candidate predicted cost minus that exact cost. Each row contains three solver seeds on one fixture; the baseline repetitions are identical, not independent samples.

{table(small)}

All five metaheuristics reach the exact initial optimum for all three seeds. The greedy baseline leaves one predicted case unstarted and has a cost gap of about 0.8004. This shows a benefit from allocation search on the chosen fixture, without distinguishing the five methods.

An optimum here certifies only the initial predicted allocation under fixed shortest-duration sequencing. It does not certify optimal execution under the hidden durations, nor an optimum after a disruption. Repeating seeds explores solver variability on this one fixture; it does not test diversity of small problems.
''')
    # Descriptive tables retain workload size and distinguish static and reactive.
    for group, title in [('historical','8. Historical workloads: actual execution'), ('large','9. Generated workloads: scaling and execution')]:
        subset = data[data.group.eq(group) & data.scenario.eq('outage')].copy()
        subset['Workload'] = subset.instance_id if group == 'historical' else subset.cases.astype(str)
        grouped = subset.groupby(['Workload','method','policy'], sort=False).agg(completed=('completed','mean'), overtime=('overtime_minutes_including_turnover','mean'))
        rows=[]
        for workload in sorted(subset.Workload.unique(), key=lambda x: int(x) if group=='large' else x):
            for method in METHODS:
                st = grouped.loc[(workload,method,'static')]; re_ = grouped.loc[(workload,method,'reactive')]
                rows.append([workload,LABELS[method],st.completed,re_.completed,st.overtime,re_.overtime])
        result = pd.DataFrame(rows,columns=['Workload','Method','Done S','Done R','OT S','OT R'])
        page(title, f'''
Closure scenario. S = static; R = reactive. Done = mean completed cases; OT = mean overtime including turnover, in minutes summed over rooms. {'Each mean uses three solver seeds for a fixed historical date.' if group=='historical' else 'Each mean uses two sampled workloads x three solver seeds (six runs).'} Raw aggregate results preserve every seed and both scenarios.

{table(result)}

These are paired comparisons: each S/R pair shares its initial plan and realized durations. No-outage policies match on completion, overtime, occupancy and total delay in all pairs. The comparisons therefore isolate the effect of the implemented closure-triggered replanning, conditional on each initial method.
''')
    large = plans[plans.group.eq('large')].copy()
    large['cases'] = large.instance_id.str.split('-').str[1].astype(int)
    predicted_means = large.groupby(['cases','method']).overtime.mean()
    timings = large.groupby(['cases','method']).agg(U=('unstarted','mean'), O=('overtime','mean'), seconds=('seconds','mean'), max_seconds=('seconds','max')).reset_index()
    timings['method'] = timings.method.map(LABELS)
    timings.columns = ['Cases','Method','Predicted U','Predicted OT','Mean s','Max s']
    roomrows=[]
    for key, value in manifests['large']['instances'].items():
        roomrows.append(f"{key}: {value['configurations'][0]['rooms']} rooms")
    page('10. Larger problems: predicted quality and computation', f'''
Initial planning only; six observations per method and size (two sampled instances, three solver seeds). The predicted unstarted count and overtime are reported separately because normalized costs are not directly comparable across sizes. Time includes process startup. Small, historical and 100-case runs were sequential; the 300-case workloads ran in four concurrent batches. Their measured search times include shared CPU load, so cross-size timings are descriptive and are not a controlled speed comparison.

{table(timings)}

At 100 cases, tabu reduces mean predicted overtime from {predicted_means.loc[(100,'baseline')]:.1f} to {predicted_means.loc[(100,'tabu')]:.1f} minutes; annealing and Tabu x annealing reach the same mean. At 300 cases, tabu and Tabu x annealing reach {predicted_means.loc[(300,'tabu')]:.1f} versus {predicted_means.loc[(300,'baseline')]:.1f} for the baseline. Genetic search retains the initial incumbent at both sizes, and ACO does so at 300 cases. Under this budget, the local searches improve predicted quality more consistently; the execution tables show why that does not establish a universal winner.

Generated resources: {'; '.join(roomrows)}. Increasing rooms alongside cases avoids treating all growth as resource scarcity, although the target load is intentionally above one.

The baseline is a useful computational reference, but uses zero search evaluations and has no spawned search worker. ACO constructs whole allocations for each ant and has additional per-case probability calculations. Search time should therefore be compared alongside quality, not inferred from equal evaluation counts. This bounded study has no exact large-instance optimum or certified large-instance optimality gap.
''')
    reference_rows=[]
    clean=data[data.scenario.eq('no_outage') & data.policy.eq('static')].copy()
    clean['Family']=clean.apply(lambda r: ('Generated '+str(r.cases)) if r.group=='large' else r.group.title(),axis=1)
    for family in ['Small','Historical','Generated 100','Generated 300']:
        for method in METHODS:
            v=clean[clean.Family.eq(family) & clean.method.eq(method)]
            reference_rows.append([family,LABELS[method],v.completed.mean(),v.unstarted.mean(),v.overtime_minutes_including_turnover.mean()])
    page('No-closure execution reference', 'Static execution; reactive gives identical operational results because no replanning trigger occurs. Means cover three solver seeds per instance. Historical means pool three different days and must be interpreted with the per-day closure table, not as a single representative hospital day. Generated means use two samples per size.\n\n'+table(pd.DataFrame(reference_rows,columns=['Family','Method','Completed','Unstarted','OT min']))+'\n\nThese outcomes use realized durations. They are distinct from the predicted initial objective and make the cost of duration uncertainty visible even without a room closure.')
    outage = paired.xs('outage',level='scenario')
    dc = outage['completed']['reactive'] - outage['completed']['static']
    do = outage['overtime_minutes_including_turnover']['reactive'] - outage['overtime_minutes_including_turnover']['static']
    more, same, fewer = int((dc>0).sum()), int((dc==0).sum()), int((dc<0).sum())
    page('11. Interpretation and limits', f'''
Across the 144 closure pairs, reactive scheduling completes more cases in {more}, the same number in {same}, and fewer in {fewer}. These counts include deterministic baseline repetitions and heterogeneous workloads; they are descriptive, not independent statistical trials. Overtime falls in {int((do<0).sum())} pairs, is unchanged in {int((do==0).sum())}, and rises in {int((do>0).sum())}.

On 2022-01-03, all methods complete nine cases under both policies, but reactive overtime is higher. On 2022-02-02, some methods trade fewer completed cases for less overtime. On 2022-10-20, every method completes 16 cases under both policies, while replanning lowers overtime. These day-level outcomes explain why one average or one preferred example would be insufficient.

The central result is that hybridization is technically feasible, but replanning is not automatically beneficial. The search optimizes predictions. Historical duration errors, the fixed sequencing rule, and the prohibition on starting before a planned time can change realized performance. Replanning may improve one metric at the expense of another. Lower overtime accompanied by fewer completed cases cannot be called an unqualified improvement.

No overall winner is justified by these experiments. Only one exact fixture, three selected historical days and two generated samples per size were evaluated, with three solver seeds and one evaluation budget. Historical days do not reconstruct actual room availability, staffing, specialty eligibility, beds, emergency arrivals or the hospital's own priorities. Generated cases preserve individual procedure-duration pairing, but not daily dependencies or clinical mix constraints.

Neither total search effort nor disruption severity is constant between every comparison: reactive runs can use more requests than static runs, and one closed room is a smaller fraction of a large resource pool. Simulation pauses during computation, so optimization latency does not itself delay an operation. These choices must be retained when interpreting the tables.

A useful next experimental extension is a held-out campaign across more dates and generated samples, multiple evaluation budgets, and both light and overloaded conditions. Algorithm tuning and duration-model tuning should use separate development data. Clinical deployment would additionally require validated constraints and prospective evaluation; this report establishes a reproducible experimental comparison under the present model.
''')
    page('12. Verification, provenance and reproduction', f'''
The report builder independently checked {checked} execution records: case conservation, opening/closing and closure start rules, no overlap, turnover separation, occupancy and overtime totals, and evaluation caps. It also checked all no-outage policy pairs for identical operational outcomes. The campaign recorded zero coordinator/search failures, timeouts or deadline stops. The prior implementation verification reported 90 tests, with 88 passing and two optional Tkinter tests skipped; those tests were not rerun for this documentation-only campaign.

Code commit used by the campaign: {manifests['small']['code']['commit']}. Python {manifests['small']['python']}; Mesa {manifests['small']['dependencies']['mesa']}. Exact dependency versions, code hashes, workbook fingerprint and generated resources are preserved in comparison-results/provenance.json. The 300-case workloads used four concurrent batches, recorded in the large-run manifest. Raw local run manifests may mark the checkout dirty once report scripts were added; the simulation source fingerprint identifies the evaluated code.

To reproduce the experiments from the repository root, run:

`bash scripts/run_comparison_campaign.sh artifacts/comparison-rerun`

Then build the report (install the optional document dependency with venv/bin/python -m pip install reportlab==5.0.1):

`venv/bin/python scripts/build_comparison_report.py --input artifacts/comparison-rerun`

The cleaned workbook is required for historical/generated runs. Raw episode logs remain under ignored artifacts/. Shareable aggregate tables are docs/comparison-results/runs.csv and initial-plans.csv. The editable report is docs/metaheuristics-mesa-comparison.md. The PDF is generated locally under artifacts/comparison-2026-09-28/; the aggregate figure is in docs/comparison-results/.

Implementation sources: hospital_sim/historical_data.py (field mapping and train/test split); room_problem.py (decoder/objective); metaheuristics.py (adapters/settings); simulation.py (Mesa execution and metrics); experiment.py and instances.py (protocol); optimiseur/optimizer.py and search_control.py (search algorithms and budgets). This report describes and tests that implementation; it is not a literature review. No external clinical evidence is inferred from these experiments.
''')
    secondary = data[data.scenario.eq('outage') & data.policy.eq('reactive')].copy()
    secondary['Family'] = secondary.apply(lambda r: ('Generated ' + str(r.cases)) if r.group == 'large' else r.group.title(), axis=1)
    secondary_rows = []
    for family in ['Small','Historical','Generated 100','Generated 300']:
        for method in METHODS:
            v = secondary[secondary.Family.eq(family) & secondary.method.eq(method)]
            secondary_rows.append([family, LABELS[method], v.total_start_delay_minutes.sum()/max(1,v.delay_measured_cases.sum()),100*v.room_utilization_fraction.mean(),v.changed_assignment_decisions.mean(),v.solver_seconds.mean()])
    page('13. Secondary execution metrics', 'Closure scenario, reactive policy only. Delay is pooled over eligible completed cases; utilization, changed decisions and total solver time are unweighted means over runs. Solver time includes the cached initial solve plus replanning. The aggregate CSV includes all policies and scenarios.\n\n' + table(pd.DataFrame(secondary_rows,columns=['Family','Method','Delay min','Use %','Changes','Solver s'])) + '\n\nThe delay population can differ between methods because unstarted and initially unassigned cases are excluded. Changed decisions are revision events, not a count of distinct patients. These quantities should be read alongside completed cases and overtime, not combined into a new undocumented score.')
    # Figure: paired effects by family, method, and size are available in CSV;
    # plot the generated workload averages without pretending seeds are new days.
    fig, axes = plt.subplots(2,1,figsize=(7.5,7),layout='constrained')
    for ax, count in zip(axes,[100,300]):
        view=data[data.group.eq('large') & data.cases.eq(count) & data.scenario.eq('outage')]
        vals=view.groupby(['method','policy']).completed.mean().unstack().reindex(METHODS)
        vals.index=[LABELS[x] for x in vals.index]
        delta=vals['reactive']-vals['static']
        delta.plot.bar(ax=ax,color=['#176B87' if x>=0 else '#E79A36' for x in delta],rot=25)
        ax.axhline(0,color='#333333',linewidth=.8)
        ax.set_ylim(min(-.2,delta.min()-.4),max(.2,delta.max()+.4))
        for i,value in enumerate(delta):
            ax.text(i,value+(.06 if value>=0 else -.06),f'{value:+.2f}',ha='center',va='bottom' if value>=0 else 'top',fontsize=9)
        ax.set_title(f'{count} cases: closure scenario')
        ax.set_ylabel('Change in completed cases (reactive - static)'); ax.set_xlabel('')
        ax.grid(axis='y',alpha=.2)
    figure=exported/'generated-completions.png'; fig.savefig(figure,dpi=180); plt.close(fig)
    text='# Metaheuristics and Mesa: experimental comparison\n\n28 September 2026 | Reproducible room-only study\n\n' + '\n\n---\n\n'.join(pages) + '\n'
    text += f'\n## {len(pages)+1}. Generated workloads: paired policy comparison\n\n![Mean paired change in completed cases](comparison-results/generated-completions.png)\n\nMean paired differences over two workloads and three solver seeds. Positive values mean more completions with reactive scheduling; negative values mean fewer. Read alongside overtime; bars do not represent confidence intervals.\n'
    args.markdown.write_text(text)
    render_pdf(args.pdf, pages, figure)
    print(json.dumps({'runs':len(data),'plans':len(plans),'audited':checked,'reactive_more_equal_fewer':[more,same,fewer], 'pdf':str(args.pdf)},indent=2))


def render_pdf(path, pages, figure):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_LEFT
    fonts=Path('/usr/share/fonts/truetype/dejavu')
    pdfmetrics.registerFont(TTFont('DejaVu',str(fonts/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('DejaVu-Bold',str(fonts/'DejaVuSans-Bold.ttf')))
    pdfmetrics.registerFontFamily('DejaVu',normal='DejaVu',bold='DejaVu-Bold',italic='DejaVu',boldItalic='DejaVu-Bold')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Body',fontName='DejaVu',fontSize=9,leading=13,spaceAfter=9))
    styles.add(ParagraphStyle(name='Head',fontName='DejaVu-Bold',fontSize=17,leading=22,textColor=colors.HexColor('#124B62'),spaceAfter=17))
    styles.add(ParagraphStyle(name='Cell',fontName='DejaVu',fontSize=7.3,leading=10))
    def rich(s):
        s=escape(s)
        s=re.sub(r'\*\*(.*?)\*\*',r'<b>\1</b>',s)
        return s.replace('`','')
    story=[]
    for idx,page in enumerate(pages):
        if idx: story.append(PageBreak())
        else:
            story.append(Paragraph('Metaheuristics and Mesa',styles['Head']))
            story.append(Paragraph('Experimental comparison | 28 September 2026',styles['Body']))
            story.append(Spacer(1,18))
        for block in page.split('\n\n'):
            if block.startswith('## '):
                story.append(Paragraph(rich(block[3:]),styles['Head']))
            elif block.startswith('|'):
                lines=[line for line in block.splitlines() if not re.match(r'^\|[\s|:-]+\|$',line)]
                cells=[[Paragraph(rich(c.strip()),styles['Cell']) for c in line.strip('|').split('|')] for line in lines]
                n=len(cells[0]); widths={3:[100,250,145],4:[105,210,90,90],5:[130,90,90,90,95],6:[75,112,77,77,77,77]}.get(n,[495/n]*n)
                t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DDEAF0')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F6F8')]),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
                story.extend([t,Spacer(1,12)])
            else:
                story.append(Paragraph(rich(block).replace('\n',' '),styles['Body']))
    story.extend([PageBreak(),Paragraph(f'{len(pages)+1}. Generated workloads: paired policy comparison',styles['Head']),Image(str(figure),width=495,height=462),Spacer(1,12),Paragraph('Mean paired differences over two generated workloads and three solver seeds. Positive values mean more completed cases with reactive scheduling; negative values mean fewer. Every pair shares its initial schedule and hidden outcomes. Read alongside the overtime table. These bars are descriptive means, not confidence intervals.',styles['Body'])])
    def footer(canvas, doc):
        canvas.setFont('DejaVu',8); canvas.setFillColor(colors.HexColor('#52616B'))
        canvas.drawString(50,28,'Metaheuristics + Mesa | Experimental comparison | 28 Sep 2026')
        canvas.drawRightString(545,28,str(doc.page))
    path.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(path),pagesize=(595.28,841.89),rightMargin=50,leftMargin=50,topMargin=48,bottomMargin=48,title='Metaheuristics and Mesa: experimental comparison',author='IA et Sante - Groupe 2').build(story,onFirstPage=footer,onLaterPages=footer)


if __name__=='__main__':
    main()
