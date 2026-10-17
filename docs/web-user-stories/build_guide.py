"""Build an illustrated guide from real app captures. No hospital data is read."""
from pathlib import Path
import html
import json
from xml.sax.saxutils import escape
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parent
REGIONS = json.loads((ROOT / 'capture-regions.json').read_text())
# Full-page capture changes the sticky navigation offset. Frame panels using
# the saved image coordinates, checked against the rendered screenshots.
for _region in REGIONS.values():
    _region['y'] -= 54
    _region['height'] += 12
GREEN = '#23864f'
INK = '#143d2b'
MUTED = '#52675c'
STORIES = [
 dict(title='Give a new patient two explained dates', role='Surgeon',
 story='As a surgeon, I want room-time and length-of-stay estimates from the consultation details, so that I can discuss feasible dates with the patient.',
 steps='Open Nouvelle demande; enter a pseudonym, birth year, sex, surgeon, diagnosis, CCAM code, procedure type and requested date window; choose Créer et proposer des dates.',
 outcome='DEMO-NOUVEAU receives Monday 19 October and Friday 23 October. Each option explains room load, bed availability throughout the predicted stay, and the 10% vacation margin.',
 check='The prediction is about 70 minutes and a four-day stay. A date proposal uses 71 rounded minutes. These are estimates of room occupancy, including more than the surgical act alone.',
 figures=[('03-predictions-dates',dict(x=20,y=210,width=1220,height=580),'Two possible dates with capacity explanations and the trained-model prediction.')],
 extras=[('02-new-request','Consultation input form with synthetic details.')]),
 dict(title='Confirm a date and reserve the stay', role='Surgeon / bed manager',
 story='As a surgeon, I want to confirm one proposed date, so that the room capacity and beds for the predicted stay are reserved together.',
 steps='Review Date A and select Confirmer cette date. Then open Lits to inspect the resulting occupancy forecast.',
 outcome='The request becomes Programmée for 19 October, with a predicted last occupied day of 22 October. In this demo, conventional occupancy rises from one to two beds on those four days.',
 check='Confirmation rechecks current capacity. A proposal by itself creates no reservation. Observed room time and stay can be recorded after surgery; recording them does not automatically retrain the models.',
 figures=[('04-confirmed',dict(x=20,y=80,width=1220,height=760),'The confirmed intervention, its predicted stay and fields for later observed outcomes.')],
 extras=[('05-bed-forecast','The Lits screen now shows 2/3 conventional beds occupied on 19-22 October.')]),
 dict(title='Plan a cohort, then publish proposals', role='Operating-room planner',
 story='As a planner, I want to optimize pending requests together, so that shared room and bed constraints are considered across the cohort.',
 steps='In Bloc, set 19-23 October under Optimisation de la cohorte; choose SMA x Metaheuristiques; calculate an overview, then select Publier des propositions.',
 outcome='The combined engine places two of eight pending requests; six remain unassigned. Publication recalculates and checks capacity, then publishes two proposals awaiting clinical confirmation.',
 check='Confirmed cases are preserved. Unassigned cases remain visible. Published proposals are still provisional and do not reserve beds or room time.',
 figures=[('08-cohort-preview-full',None,'Preview: two assignments and six unassigned requests.'),('09-published-full',None,'Publication: two proposals, each awaiting clinical confirmation.')],extras=[]),
 dict(title='Respond to a change in room availability', role='Operating-room planner',
 story='As a planner, I want resource changes to trigger a review of pending proposals and highlight affected confirmed cases, so that the team can respond to a disruption.',
 steps='In Ressources, deactivate Salle 1. Return to Bloc, inspect Interventions confirmées à revoir and select Actualiser les propositions.',
 outcome='Four confirmed interventions are flagged because their room is unavailable. The refresh completes and updates two pending proposals; the queue returns to zero pending changes.',
 check='Confirmed reservations remain in place for team review. The refresh does not automatically relocate confirmed operations. This demo uses manual refresh; a background worker is optional.',
 figures=[('10-capacity-alert-full',None,'The four affected confirmed interventions require review.'),('11-replanning-complete-full',None,'The completed refresh reports two updated proposals.')],extras=[]),
 dict(title='Test the impact of longer hospital stays', role='Planner / research team',
 story='As a planner, I want to test a hypothetical scenario before changing the live plan, so that I can see whether beds or room capacity limit admissions.',
 steps='Use Simulation Mesa : salles et lits for 19-23 October. Keep baseline, Réactive, room factor 1 and the 10:00-12:00 closure. Compare stay factor 1 with stay factor 2.',
 outcome='With the same eight pending cases and four confirmed bookings, factor 1 starts two cases and leaves six unstarted. Factor 2 starts one and leaves seven unstarted. Both report zero bed-conflict days and zero solver failures.',
 check='These are hypothetical execution durations derived from predictions. They are not observed patient outcomes, oracle forecasts, or a comparison proving that one solver is best. Simulation creates no bookings.',
 figures=[('06-mesa-baseline-full',None,'Stay factor 1: two started; six unstarted; four replans.'),('07-mesa-longer-stays-full',None,'Stay factor 2: one started; seven unstarted; two replans.')],extras=[]),
]

def region(name, override=None):
    path=ROOT/'images'/f'{name}.jpg'
    w,h=Image.open(path).size
    r=override or REGIONS.get(name) or dict(x=0,y=0,width=w,height=h)
    assert r['x'] >= 0 and r['y'] >= 0 and r['x']+r['width'] <= w+2 and r['y']+r['height'] <= h+2, (name,r,w,h)
    return path,r,w,h

def make_sources():
    data=dict(title='KYST | Five illustrated user stories',date='2026-10-17',
        branch='codex/web-full-system',commit='a63560c2962a05f078281eb61a1d6117e3634237',
        source='Real screenshots of the local application, using an isolated synthetic database.',
        models=['room-b3942fd9960a','los-fed3079fc30d','care-from-los-fed3079fc30d'],
        assumptions=['English explanations; original French application labels.',
                     'Two synthetic rooms, three conventional beds and six ambulatory places.',
                     'Eight pending requests and four confirmed bookings after the consultation example.',
                     'The multi-day preview simplifies room calendars and uses hypothetical execution factors.',
                     'After a calculation, some app forms reset their controls. Where shown with results, the submitted settings were re-entered for readability without rerunning or changing the results.'],
        stories=STORIES)
    (ROOT/'stories.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    md=['# KYST: five illustrated user stories','',data['source'],'',
        'English guide with the application’s French labels. Captured on 17 October 2026. All people and patient references in the images are synthetic.','',
        '## The user journey','',
        'Consultation details → ML predictions → feasible dates / cohort optimization → clinical confirmation → reservations → resource review. Mesa provides separate what-if previews.','']
    parts=[]
    for n,s in enumerate(STORIES,1):
        md += [f'## {n}. {s["title"]}','',f'**{s["role"]}.** {s["story"]}','',f'**Actions:** {s["steps"]}','',f'**Observed result:** {s["outcome"]}','',f'**Interpretation:** {s["check"]}','']
        figs=[]
        for name,r,caption in s['figures']:
            path,rc,w,h=region(name,r)
            md += [f'![{caption}](images/{name}.jpg)',f'*{caption} Full capture; the HTML and PDF focus on the relevant panel.*','']
            style=f'width:100%;aspect-ratio:{rc["width"]}/{rc["height"]};overflow:hidden;position:relative'
            imgstyle=f'position:absolute;width:{w/rc["width"]*100:.6f}%;max-width:none;left:{-rc["x"]/rc["width"]*100:.6f}%;top:{-rc["y"]/rc["height"]*100:.6f}%'
            figs.append(f'<figure><a href="images/{name}.jpg"><div style="{style}"><img alt="{html.escape(caption)}" src="images/{name}.jpg" style="{imgstyle}"></div></a><figcaption>{html.escape(caption)}</figcaption></figure>')
        for name,caption in s['extras']:
            md += [f'![{caption}](images/{name}.jpg)',f'*{caption}*','']
            figs.append(f'<details><summary>{html.escape(caption)}</summary><img class="extra" src="images/{name}.jpg" alt="{html.escape(caption)}"></details>')
        parts.append(f'<section id="story-{n}"><p class="eyebrow">STORY {n} / {html.escape(s["role"])}</p><h2>{html.escape(s["title"])}</h2><p class="story">{html.escape(s["story"])}</p><div class="copy"><p><b>Actions</b><br>{html.escape(s["steps"])}</p><p><b>Observed result</b><br>{html.escape(s["outcome"])}</p></div><div class="figures {"paired" if len(s["figures"])==2 else ""}">{"".join(figs)}</div><p class="note">{html.escape(s["check"])}</p></section>')
    scope='The immediate A/B suggestions use the fast individual scheduling path. The cohort action calls the selected optimization engine. Mesa evaluates hypothetical execution separately. Trained predictors were enabled for these captures; their accuracy and uncertainty still need calibration for the reduced web input fields. The multi-day web preview is limited to 14 days and 30 cases, with simplified room calendars. These examples demonstrate implemented workflows; they are not clinical validation or the historical benchmark campaign.'
    md += ['## Scope and interpretation','',scope,'','### Capture notes','']+[f'- {x}' for x in data['assumptions']]+['',f'Source version: `{data["branch"]}` at `{data["commit"]}`.','']
    (ROOT/'user-stories.md').write_text('\n'.join(md))
    css='''*{box-sizing:border-box}body{margin:0;color:#143d2b;background:#f3f6f0;font:17px/1.65 system-ui,sans-serif}header,main,footer{max-width:1100px;margin:auto;padding:40px 32px}header{padding-top:64px}h1{font-size:48px;line-height:1.08;max-width:800px;margin:12px 0 24px}h2{font-size:32px;line-height:1.2;margin:8px 0 20px}.eyebrow{color:#23864f;font-size:12px;letter-spacing:2px;font-weight:750;text-transform:uppercase}.tag{display:inline-block;background:#deebdf;padding:5px 12px;border-radius:5px;margin:0 8px 8px 0;font-size:13px}nav a{display:block;color:#23864f;margin:8px 0}section{border-top:1px solid #cad6cd;padding:42px 0}.story{font-size:21px;max-width:900px}.copy{display:grid;grid-template-columns:1fr 1fr;gap:30px}.figures{margin:20px 0}.paired{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0;background:white;border:1px solid #cad6cd;border-radius:8px;overflow:hidden}figcaption{font-size:14px;line-height:1.5;padding:12px 16px;color:#52675c}img{display:block}details{grid-column:1/-1;margin:14px 0;color:#23864f}summary{cursor:pointer}.extra{width:100%;margin-top:15px}.note{padding:18px 22px;background:#e4ece2;border-left:4px solid #23864f;font-size:15px}footer{font-size:14px;color:#52675c}@media(max-width:720px){header,main,footer{padding:24px}h1{font-size:36px}.copy,.paired{grid-template-columns:1fr}}@media print{body{background:white}section{break-inside:avoid}details{display:none}}'''
    nav=''.join(f'<a href="#story-{n}">{n}. {html.escape(s["title"])}</a>' for n,s in enumerate(STORIES,1))
    (ROOT/'index.html').write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KYST | Illustrated user stories</title><style>{css}</style><header><p class="eyebrow">KYST / APPLICATION SHOWCASE / 17 OCTOBER 2026</p><h1>From a new patient to a plan the team can review</h1><p>Five user stories showing how ML estimates, optimization and Mesa connect in the application.</p><span class="tag">Real application screenshots</span><span class="tag">Synthetic patients only</span><span class="tag">French UI / English guide</span><nav>{nav}</nav></header><main>{"".join(parts)}<section><h2>Scope and interpretation</h2><p>{html.escape(scope)}</p><ul>{"".join(f"<li>{html.escape(x)}</li>" for x in data["assumptions"])}</ul></section></main><footer>Captured locally from <code>{data["branch"]}</code>, commit <code>{data["commit"][:7]}</code>. Screenshot panels are framed through document layout; the underlying captures remain available by clicking each image.</footer></html>')

def make_pdf():
    for name,file in [('Body','DejaVuSans.ttf'),('Bold','DejaVuSans-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(name,'/usr/share/fonts/truetype/dejavu/'+file))
    dest=ROOT/'output'/'pdf'/'kyst-user-stories.pdf';dest.parent.mkdir(parents=True,exist_ok=True)
    W,H=landscape(A4); c=canvas.Canvas(str(dest),pagesize=(W,H))
    c.setTitle('KYST | Five illustrated user stories');c.setAuthor('KYST project')
    def para(txt,x,y,w,size=10,leading=None,color=INK,bold=False):
        p=Paragraph(txt,ParagraphStyle('p',fontName='Bold' if bold else 'Body',fontSize=size,leading=leading or size*1.45,textColor=colors.HexColor(color)))
        _,h=p.wrap(w,1000);p.drawOn(c,x,y-h);return y-h
    def base(page,label,title):
        c.setFillColor(colors.HexColor('#f4f7f0'));c.rect(0,0,W,H,fill=1,stroke=0)
        c.setFillColor(colors.HexColor(GREEN));c.rect(0,H-8,W,8,fill=1,stroke=0)
        para('KYST / '+label.upper(),32,H-26,W-64,8,color=GREEN,bold=True)
        para(title,32,H-45,W-64,23,27,bold=True)
        c.setStrokeColor(colors.HexColor('#cfdbd0'));c.line(32,30,W-32,30)
        para('Real application captures | Synthetic patients | 17 October 2026',32,22,W-100,7,color=MUTED)
        para(f'{page} / 6',W-70,22,40,7,color=MUTED)
    def fig(name,r,x,y,w,h,caption):
        path,rc,iw,ih=region(name,r);scale=min(w/rc['width'],h/rc['height']);dw=rc['width']*scale;dh=rc['height']*scale
        x+=(w-dw)/2
        c.saveState();p=c.beginPath();p.rect(x,y-dh,dw,dh);c.clipPath(p,stroke=0,fill=0)
        c.drawImage(str(path),x-rc['x']*scale,y+(rc['y']+rc['height']-ih)*scale-dh,width=iw*scale,height=ih*scale)
        c.restoreState();c.setStrokeColor(colors.HexColor('#cad6cd'));c.rect(x,y-dh,dw,dh,fill=0,stroke=1)
        para(escape(caption),x,y-dh-5,dw,7,color=MUTED)
        return y-dh-22
    base(1,'Application showcase','From a new patient to a plan the team can review')
    para('Five illustrated user stories',32,H-92,W-64,18,bold=True)
    para('ML estimates inform scheduling; clinicians confirm dates; planners review changes. Mesa provides separate what-if scenarios.',32,H-124,W-64,12)
    y=H-187
    for n,s in enumerate(STORIES,1):
        para(f'{n:02d}',32,y,38,16,color=GREEN,bold=True)
        para(escape(s['title']),82,y,W-120,13,bold=True)
        para(escape(s['role']),82,y-22,W-120,9,color=MUTED)
        y-=57
    para('DEMO CONTEXT',32,104,150,8,color=GREEN,bold=True)
    para('Two rooms, three conventional beds, eight pending requests and four confirmed bookings after the consultation example. All patient references and clinical cases in the screenshots are synthetic. Trained duration and LOS models were enabled.',32,86,W-64,9)
    para('A/B dates use the fast individual scheduler; cohort planning calls the selected engine. Mesa uses simplified scenarios. Model estimates still need validation and calibration for the web input fields.',32,53,W-64,7.5,color=MUTED)
    c.showPage()
    for n,s in enumerate(STORIES,1):
        base(n+1,f'Story {n} / {s["role"]}',s['title'])
        y=para(escape(s['story']),32,H-89,W-64,10.5)
        y=para('<b>Actions:</b> '+escape(s['steps']),32,y-7,W-64,8.8)
        y=para('<b>Result:</b> '+escape(s['outcome']),32,y-6,W-64,8.8)
        top=y-14;bottom=98;avail=top-bottom
        if len(s['figures'])==1:
            name,r,caption=s['figures'][0];fig(name,r,32,top,W-64,avail,caption)
        else:
            fw=(W-80)/2
            for i,(name,r,caption) in enumerate(s['figures']):fig(name,r,32+i*(fw+16),top,fw,avail,caption)
        para(escape(s['check']),32,71,W-64,8.1,color=MUTED)
        c.showPage()
    c.save();print(dest)

if __name__=='__main__':
    make_sources();make_pdf()
