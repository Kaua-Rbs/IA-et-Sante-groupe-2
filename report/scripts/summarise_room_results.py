"""Validate pinned aggregate room campaigns and regenerate article tables/figure.

Run from any directory with the existing project Python environment. The
optional audit_room_results.py separately checks local episode exports.
"""
from pathlib import Path
import hashlib
import json
import os

os.environ.setdefault('MPLCONFIGDIR', '/tmp/report-room-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'contributions/room-study'
TABLES = ROOT / 'tables'
METHODS = ['baseline', 'annealing', 'tabu', 'genetic', 'hybrid', 'aco']
LABELS = dict(zip(METHODS, ['Baseline', 'SA', 'Tabu', 'GA', 'Hybrid', 'ACO']))
OT = 'overtime_minutes_including_turnover'
KEY = ['group', 'instance_id', 'method', 'seed']


def tex_table(name, caption, columns, rows, align):
    lines = [r'\begin{table}[H]', r'\centering\small', r'\caption{' + caption + '}',
             r'\label{tab:' + name + '}', r'\begin{tabular}{@{}' + align + '@{}}',
             r'\toprule', ' & '.join(columns) + r' \\', r'\midrule']
    for row in rows:
        lines.append(' & '.join(str(x) for x in row) + r' \\')
    lines += [r'\bottomrule', r'\end{tabular}', r'\end{table}', '']
    (TABLES / (name + '.tex')).write_text('\n'.join(lines))


def check_runs(frame, key):
    assert set(frame.scenario) == {'outage', 'no_outage'}
    assert set(frame.policy) == {'static', 'reactive'}
    assert not frame.duplicated(key + ['scenario', 'policy']).any()
    assert frame.groupby(key).size().eq(4).all()
    assert (frame.completed + frame.unstarted).eq(frame.cases).all()
    assert frame[['failures', 'timeouts', 'search_failures', 'search_deadline_stops']].eq(0).all().all()
    paired = frame.pivot(index=key + ['scenario'], columns='policy')
    for metric in ['completed', 'unstarted', OT, 'room_occupancy_minutes_in_hours', 'total_start_delay_minutes']:
        values = paired[metric].xs('no_outage', level='scenario')
        assert values.static.eq(values.reactive).all()
    return paired


def main():
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    for name, record in manifest['files'].items():
        assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == record['sha256'], name
    data = pd.read_csv(SOURCE / 'runs.csv')
    initial = pd.read_csv(SOURCE / 'initial-plans.csv')
    duration = pd.read_csv(SOURCE / 'duration-runs.csv').rename(columns={'family': 'group'})
    assert len(data) == 576 and len(initial) == 144 and len(duration) == 1152
    assert not initial.duplicated(KEY).any()
    assert set(map(tuple, initial[KEY].to_numpy())) == set(map(tuple, data[KEY].to_numpy()))
    assert set(data.method) == set(METHODS) and set(data.seed) == {0, 1, 2}
    paired = check_runs(data, KEY)
    check_runs(duration, ['duration_mode'] + KEY)
    assert duration.groupby(['duration_mode', 'group']).size().to_dict() == {
        (mode, group): count for mode in ['median', 'oracle'] for group, count in [('small', 72), ('historical', 216), ('large', 288)]}
    paired_modes = duration.pivot(index=KEY + ['scenario', 'policy'], columns='duration_mode')
    assert paired_modes['cases']['median'].eq(paired_modes['cases']['oracle']).all()
    provenance = json.loads((SOURCE / 'duration-provenance.json').read_text())
    for group in ['small', 'historical', 'large']:
        a, b = [provenance[f'{mode}/{group}'] for mode in ['median', 'oracle']]
        assert a['instances'] == b['instances']
        assert a['dataset_sha256'] == b['dataset_sha256']
        assert a['code']['implementation_sha256'] == b['code']['implementation_sha256']
    for row in initial.itertuples():
        # For initial planning all changes are zero; normalization is checked
        # exactly on the small fixture whose total predicted work is known.
        if row.group == 'small':
            assert abs(row.cost - row.unstarted - row.overtime / 526) < 1e-10
        assert row.evaluations <= 1000 and row.changes == 0
    TABLES.mkdir(exist_ok=True)
    small = initial.query("group == 'small'").groupby('method')
    rows = []
    for method in METHODS:
        g = small.get_group(method)
        rows.append([LABELS[method], f'{g.gap.mean():.5f}', f'{g.gap.max():.5f}',
                     f'{int(g.gap.abs().lt(1e-9).sum())}/3', f'{g.seconds.mean():.3f}'])
    tex_table('room-exact', 'Small room-allocation reference: absolute initial predicted-cost gaps, exact hits and mean initial solve time. Three seeds on one fixed seven-case fixture; baseline repeats are identical.',
              ['Method', 'Mean gap', 'Worst gap', 'Exact hits', 'Time (s)'], rows, 'lrrrr')
    hist = data.query("group == 'historical' and scenario == 'outage'").groupby(['instance_id', 'method', 'policy'])[['completed', OT]].mean()
    rows = []
    for day in sorted(data.query("group == 'historical'").instance_id.unique()):
        for method in METHODS:
            a, b = [hist.loc[(day, method, policy)] for policy in ['static', 'reactive']]
            rows.append([day, LABELS[method], f'{a.completed:.2f}', f'{b.completed:.2f}', f'{a[OT]:.1f}', f'{b[OT]:.1f}'])
    tex_table('room-historical', 'Historical closure scenario: mean completed cases and realised overtime over three solver seeds per day. S = static; R = reactive. Each pair shares its initial plan. Overtime includes turnover and sums minutes over rooms.',
              ['Date', 'Method', 'Done S', 'Done R', 'OT S', 'OT R'], rows, 'llrrrr')
    generated = data.query("group == 'large' and scenario == 'outage'").groupby(['cases', 'method', 'policy'])[['completed', OT]].mean()
    quality = initial.query("group == 'large'").copy()
    quality['cases'] = quality.instance_id.str.split('-').str[1].astype(int)
    q = quality.groupby(['cases', 'method'])[['unstarted', 'overtime', 'seconds']].mean()
    rows = []
    for size in [100, 300]:
        for method in METHODS:
            a, b = [generated.loc[(size, method, p)] for p in ['static', 'reactive']]
            rows.append([size, LABELS[method], f'{a.completed:.2f}', f'{b.completed:.2f}', f'{a[OT]:.1f}', f'{b[OT]:.1f}'])
    tex_table('room-generated', 'Generated closure scenario: means over two sampled workloads and three solver seeds (six runs per cell). Resources are 14/15 rooms for 100 cases and 44/45 for 300 cases. OT is realised overtime including turnover, in room-minutes.',
              ['Cases', 'Method', 'Done S', 'Done R', 'OT S', 'OT R'], rows, 'rlrrrr')
    rows = [[size, LABELS[m], f'{q.loc[(size,m)].unstarted:.2f}', f'{q.loc[(size,m)].overtime:.1f}', f'{q.loc[(size,m)].seconds:.3f}'] for size in [100,300] for m in METHODS]
    tex_table('room-initial', 'Generated workloads: initial predicted unstarted count U, overtime OT and end-to-end solve time, averaged over six plans per method and size. These predicted quantities are distinct from execution outcomes. The 300-case campaign used four concurrent batches.',
              ['Cases', 'Method', 'Predicted U', 'Predicted OT', 'Time (s)'], rows, 'rlrrr')
    d = duration.query("group == 'large' and scenario == 'no_outage' and policy == 'static'").groupby(['cases', 'method', 'duration_mode'])[['completed', OT]].mean()
    rows = []
    for size in [100,300]:
        for m in METHODS:
            a,b=[d.loc[(size,m,mode)] for mode in ['median','oracle']]
            rows.append([size,LABELS[m],f'{a.completed:.2f}',f'{b.completed:.2f}',f'{a[OT]:.1f}',f'{b[OT]:.1f}'])
    tex_table('room-duration', 'Separate duration-information campaign: no-closure static execution. M = historical-median estimates; O = oracle durations. Means use two workloads and three solver seeds. Resources and hidden outcomes are held fixed across modes; initial plans are recomputed. OT includes turnover.',
              ['Cases','Method','Done M','Done O','OT M','OT O'],rows,'rlrrrr')
    closure = paired.xs('outage',level='scenario')
    differences = {metric: closure[metric].reactive - closure[metric].static for metric in ['completed',OT]}
    summary = {'primary_execution_runs':len(data),'primary_initial_plans':len(initial),
               'duration_execution_runs':len(duration),'duration_initial_plans':len(duration)//4,
               'closure_pairs':{metric:{'positive':int((v>0).sum()),'equal':int((v==0).sum()),'negative':int((v<0).sum())} for metric,v in differences.items()},
               'interpretation':'Separate median reruns are not pooled; solver seeds do not create new hospital days.'}
    (TABLES/'room-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(9,3.1),sharey=True)
    for ax,size in zip(axes,[100,300]):
        vals=[generated.loc[(size,m,'reactive')].completed-generated.loc[(size,m,'static')].completed for m in METHODS]
        ax.bar([LABELS[m] for m in METHODS],vals,color=['#477aa8' if x>=0 else '#c87532' for x in vals])
        ax.axhline(0,color='#555555',linewidth=.8);ax.set_title(f'{size} cases');ax.tick_params(axis='x',labelrotation=30)
    axes[0].set_ylabel('Reactive minus static completions')
    fig.tight_layout();(ROOT/'figures').mkdir(exist_ok=True)
    fig.savefig(ROOT/'figures/room-policy-differences.png',dpi=200);plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
