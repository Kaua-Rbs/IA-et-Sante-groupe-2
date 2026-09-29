"""Run 100-case instances sequentially and 300-case instances in four batches.

Use --resume-100 only to reuse completed 100-case files from an interrupted
combined run. Partial 300-case outputs are replaced by complete fresh shards.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pandas as pd

METHODS = ['baseline', 'annealing', 'tabu', 'genetic', 'hybrid', 'aco']
COMMON = ['--seeds','0','1','2','--max-evaluations','1000','--solver-budget','60','--target-load','1.1']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--resume-100',action='store_true')
    args=parser.parse_args()
    destination=args.output/'large'
    if not args.resume_100:
        subprocess.run([sys.executable,'-m','hospital_sim.experiment','--synthetic-cases','100','--instance-seeds','0','1','--methods',*METHODS,*COMMON,'--output',str(destination)],check=True)
    complete=list(destination.glob('sample-100-*-*-*-*-*.json'))
    assert len(complete)==144, f'Expected all 144 completed 100-case runs, got {len(complete)}'
    def shard(pair):
        instance,method=pair
        output=args.output/'shards'/f'300-{instance}-{method}'
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.with_suffix('.log').open('w') as log:
            subprocess.run([sys.executable,'-m','hospital_sim.experiment','--synthetic-cases','300','--instance-seeds',str(instance),'--methods',method,*COMMON,'--output',str(output)],stdout=log,stderr=subprocess.STDOUT,check=True)
        print(f'Finished 300-case sample {instance}, {method}',flush=True)
        return output
    with ThreadPoolExecutor(max_workers=4) as pool:
        shards=list(pool.map(shard,[(i,m) for i in (0,1) for m in METHODS]))
    manifest=json.loads((destination/'manifest.json').read_text())
    manifest['execution_layout']='100-case runs sequential; 300-case runs in four concurrent batches; end-to-end solver times include shared CPU load.'
    for folder in shards:
        source=json.loads((folder/'manifest.json').read_text())
        assert source['code']['implementation_sha256']==manifest['code']['implementation_sha256']
        assert source['dataset_sha256']==manifest['dataset_sha256']
        manifest['instances'].update(source['instances'])
        for path in folder.glob('sample-*.json'):
            shutil.copy2(path,destination/path.name)
    rows=[]
    for path in sorted(destination.glob('sample-*.json')):
        if path.name.endswith('-initial.json'):
            continue
        result=json.loads(path.read_text())
        row={k:result[k] for k in ('instance_id','date','method','seed','scenario','policy')}
        row.update(result['metrics']);row['initial_objective_gap']=None
        rows.append(row)
    assert len(rows)==288
    pd.DataFrame(rows).to_csv(destination/'summary.csv',index=False)
    manifest['dates']=['2022-01-01']*4
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    main()
