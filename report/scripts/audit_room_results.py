"""Audit optional local episode exports without copying patient-level records."""
from pathlib import Path
import json,hashlib
base=Path(__file__).resolve().parents[2]
counts={}
for campaign,root in [('room-comparison',base/'artifacts/comparison-2026-09-28'),('duration-comparison',base/'artifacts/full-duration-comparison')]:
 folders=[root/g for g in ('small','historical','large')] if campaign=='room-comparison' else [root/m/g for m in ('median','oracle') for g in ('small','historical','large')]
 total=0;paired={};dig=hashlib.sha256()
 for folder in folders:
  manifest=json.loads((folder/'manifest.json').read_text())
  for p in sorted(folder.glob('*.json')):
   if p.name=='manifest.json' or p.name.endswith('-initial.json'):continue
   raw=p.read_bytes();dig.update(p.relative_to(root).as_posix().encode());dig.update(raw)
   run=json.loads(raw);out=run['metrics'];rows=run['executed_schedule']
   config=next(c for c in manifest['instances'][run['instance_id']]['configurations'] if bool(c['outage'])==(run['scenario']=='outage'))
   assert len(rows)==out['cases'] and len({x['case_id'] for x in rows})==len(rows)
   assert all(x['status'] in {'waiting','completed'} for x in rows)
   assert sum(x['status']=='waiting' for x in rows)==out['unstarted']
   completed=[x for x in rows if x['status']=='completed']
   assert len(completed)==out['completed']
   assert out['completed']+out['unstarted']==out['cases']
   overtime=occupancy=0;rooms={}
   for row in completed:
    assert row['room_id'] in {f'room-{i+1}' for i in range(config['rooms'])}
    start,finish=row['start'],row['finish'];assert config['opening']<=start<config['closing'] and finish>start
    outage=config['outage']
    if outage and row['room_id']==outage['room_id']:assert not outage['start']<=start<outage['end']
    rooms.setdefault(row['room_id'],[]).append(row)
    overtime+=max(0,finish+config['turnover']-max(start,config['closing']))
    occupancy+=max(0,min(finish,config['closing'])-max(start,config['opening']))
   for rows_in_room in rooms.values():
    rows_in_room.sort(key=lambda x:x['start']);assert all(a['finish']+config['turnover']<=b['start'] for a,b in zip(rows_in_room,rows_in_room[1:]))
   assert overtime==out['overtime_minutes_including_turnover'] and occupancy==out['room_occupancy_minutes_in_hours']
   assert abs(out['room_utilization_fraction']-occupancy/(config['rooms']*(config['closing']-config['opening'])))<1e-12
   assert all(not out[key] for key in ['failures','timeouts','search_failures','search_deadline_stops'])
   for search in run['search_reports']:assert search['evaluations']<=manifest['max_evaluations']
   key=(str(folder),run['instance_id'],run['method'],run['seed'])
   paired.setdefault(key,[]).append(run['schedule_history'][0])
   total+=1
 for records in paired.values():assert len(records)==4 and all(x==records[0] for x in records)
 counts[campaign]={'execution_records_checked':total,'shared_initial_plans_checked':len(paired),'raw_export_sha256':dig.hexdigest(),'checks':['case conservation','start windows and closures','turnover and room non-overlap','recomputed occupancy and overtime','utilization denominator','evaluation caps','four-way initial-plan equality','zero reported failures/timeouts/deadline stops']}
 assert total==(576 if campaign=='room-comparison' else 1152)
print(json.dumps(counts,indent=2))
(base/'report/contributions/room-study').mkdir(exist_ok=True,parents=True)
(base/'report/contributions/room-study/execution-audit.json').write_text(json.dumps(counts,indent=2)+'\n')
