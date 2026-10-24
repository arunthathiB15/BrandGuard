from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from PIL import Image
from io import BytesIO
import sqlite3, json, re, os, uuid

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data' / 'brandguard.db'
app = FastAPI(title='BrandGuard', description='Evidence-cited, human-controlled brand governance')
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')

DEFAULT_RULES = [
 ('VOICE-01','Tone & voice','Use a helpful, confident and human tone. Avoid exaggerated or fear-based language.','tone','high'),
 ('TERM-01','Terminology','Use “customers” instead of “users” when referring to people who buy or use the product.','terminology','medium'),
 ('TERM-02','Terminology','Do not use the phrase “revolutionary solution”; prefer specific, verifiable benefits.','terminology','medium'),
 ('CLAIM-01','Claims policy','Every numerical performance, ranking or comparative claim must have an approved source in the Claim Ledger.','claims','high'),
 ('ACCESS-01','Accessibility','Social images must include meaningful alternative text and avoid low-contrast text.','accessibility','medium'),
 ('MSG-01','Messaging','Do not promise guaranteed results or use “100% guaranteed” unless explicitly approved.','messaging','high'),
]
DEFAULT_CLAIMS = [
 ('CL-001','Reduces processing time by 40%','Approved internal pilot report BG-PILOT-24','2027-03-31','Operations','active'),
 ('CL-002','Trusted by 10,000 customers','Quarterly customer report BG-Q3-25','2025-12-31','Marketing','expired'),
 ('CL-003','Available on web and mobile','Product release note BG-REL-18','2027-06-30','Product','active'),
]

def conn():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
 DB.parent.mkdir(parents=True, exist_ok=True)
 c=conn(); c.executescript('''
 CREATE TABLE IF NOT EXISTS rules(id TEXT PRIMARY KEY,title TEXT,body TEXT,category TEXT,severity TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY,claim TEXT,source TEXT,expires TEXT,owner TEXT,status TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,title TEXT,content TEXT,channel TEXT,audience TEXT,status TEXT,findings TEXT,created_at TEXT,updated_at TEXT,version INTEGER DEFAULT 1,author TEXT DEFAULT 'Demo Creator');
 CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT,review_id TEXT,author TEXT,body TEXT,created_at TEXT);
 CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,review_id TEXT,actor TEXT,action TEXT,details TEXT,created_at TEXT);
 ''')
 if c.execute('select count(*) from rules').fetchone()[0]==0:
  for r in DEFAULT_RULES: c.execute('insert into rules values(?,?,?,?,?,?)',(*r,datetime.now().isoformat(timespec='seconds')))
 if c.execute('select count(*) from claims').fetchone()[0]==0:
  for cl in DEFAULT_CLAIMS: c.execute('insert into claims values(?,?,?,?,?,?,?)',(*cl,datetime.now().isoformat(timespec='seconds')))
 if c.execute('select count(*) from reviews').fetchone()[0]==0:
  samples=[('Launch email — autumn update','Meet our revolutionary solution. We are India’s #1 platform, trusted by 10,000 customers. Our tool reduces processing time by 40%. Results are 100% guaranteed.','Email','Existing customers','needs_review'),('Instagram product teaser','Our new experience helps customers work with more clarity. Available on web and mobile.','Social media','Prospective customers','approved')]
  for title,content,ch,aud,st in samples:
   rid=uuid.uuid4().hex[:10]; fs=review_content(content,c)
   c.execute('insert into reviews values(?,?,?,?,?,?,?,?,?,?,?)',(rid,title,content,ch,aud,st,json.dumps(fs),datetime.now().isoformat(timespec='seconds'),datetime.now().isoformat(timespec='seconds'),1,'Demo Creator'))
   c.execute('insert into audit(review_id,actor,action,details,created_at) values(?,?,?,?,?)',(rid,'System','Demo seed','Sample review created for the demo.',datetime.now().isoformat(timespec='seconds')))
 c.commit(); c.close()

def claim_expiry_state(claim, today=None):
 """Return whether a registered claim is active, expired, or has an invalid expiry date.

 The stored status is not sufficient by itself: an accidentally stale `active` status
 must not make out-of-date evidence look valid.
 """
 status = (claim.get('status') or '').strip().lower()
 if status == 'expired':
  return 'expired'
 try:
  expiry = date.fromisoformat(str(claim.get('expires', '')).strip())
 except (TypeError, ValueError):
  return 'invalid'
 today = today or date.today()
 return 'expired' if expiry < today else 'active'

def normalise_claim_text(value):
 """Normalise punctuation/spacing so a registered claim can be matched consistently."""
 return re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).strip()

def review_content(content, c=None):
 own=False
 if c is None: c=conn(); own=True
 rules=[dict(x) for x in c.execute('select * from rules').fetchall()]
 claims=[dict(x) for x in c.execute('select * from claims').fetchall()]
 findings=[]
 def add(category,severity,excerpt,reason,source,fix,confidence=0.92):
  findings.append({'id':'F-'+uuid.uuid4().hex[:6].upper(),'category':category,'severity':severity,'excerpt':excerpt,'reason':reason,'source_id':source,'source':next((r['title']+': '+r['body'] for r in rules if r['id']==source),next((x['claim']+' — '+x['source'] for x in claims if x['id']==source),'No approved source available')),'fix':fix,'minimal_fix':fix,'tone_rewrite':fix,'clarify':'Ask the content owner to provide approved evidence or clarify the intended wording.','confidence':confidence,'decision':'open'})
 low=content.lower()
 for phrase,src,fix,reason in [
  ('revolutionary solution','TERM-02','A practical solution','Avoid vague superlatives; use a specific, supportable benefit.'),
  ('users','TERM-01','customers','The approved glossary prefers “customers” for this audience.'),
  ('100% guaranteed','MSG-01','designed to help deliver consistent results','Absolute guarantees can mislead unless explicitly approved.'),
  ('india’s #1','CLAIM-01','a platform built for your team','A ranking claim needs an approved source in the Claim Ledger.'),
  ("india's #1",'CLAIM-01','a platform built for your team','A ranking claim needs an approved source in the Claim Ledger.'),
 ]:
  if phrase in low:
   r=next((x for x in rules if x['id']==src),None)
   if r: add(r['category'],r['severity'],phrase,reason,src,fix,.95)
 for claim in claims:
  if any(token in low for token in re.findall(r'[a-z0-9]+',claim['claim'].lower()) if len(token)>4) and claim['status']=='expired':
   excerpt=claim['claim']
   if excerpt.lower() in low or any(n in low for n in re.findall(r'\d[\d,]*%?',excerpt)):
    add('claims','high',excerpt,'This claim appears in the draft but its approved evidence has expired. Verify or remove it before publication.',claim['id'],'Remove the claim or replace it with a current, approved fact.',.98)
 # Flag a registered claim if its exact wording appears and its evidence is expired
 # or has an invalid expiry date. Date comparison is authoritative even when the
 # stored status was mistakenly left as "active".
 normalised_content = normalise_claim_text(content)
 for claim in claims:
  normalised_claim = normalise_claim_text(claim.get('claim', ''))
  if not normalised_claim or normalised_claim not in normalised_content:
   continue
  expiry_state = claim_expiry_state(claim)
  if expiry_state == 'expired':
   add('claims','high',claim['claim'],'This registered claim appears in the draft, but its approved evidence has expired. Verify or remove it before publication.',claim['id'],'Remove the claim or replace it with a current, approved fact.',.98)
  elif expiry_state == 'invalid':
   add('claims','high',claim['claim'],'The registered claim has an invalid or missing expiry date, so its evidence validity cannot be confirmed. Ask the claim owner to verify it before publication.',claim['id'],'Confirm the evidence source and enter a valid expiry date before using this claim.',.65)
 # detect numerical/absolute/ranking claims that aren't grounded by an active approved claim
 for m in re.finditer(r'(?i)(?:\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*%|\b(?:#1|number one|no\. 1|guaranteed|best-in-class|world-leading)\b)',content):
  excerpt=m.group(0)
  if not any(f['excerpt'].lower()==excerpt.lower() or excerpt.lower() in f['excerpt'].lower() for f in findings):
   active_supported=any(cl['status']=='active' and any(tok in low for tok in re.findall(r'[a-z0-9]+',cl['claim'].lower()) if len(tok)>4) for cl in claims)
   add('claims','high' if '%' in excerpt or '#' in excerpt else 'medium',excerpt,'Promotional or quantitative claim detected. The current approved register does not clearly establish evidence for this exact wording; human verification is required.','CLAIM-01','Attach an approved source, or rewrite the statement as a non-quantified benefit.',.72)
 # generic readability/tone
 if len(content.split())>80:
  add('accessibility','low','Long-form draft','This draft is relatively long for a quick promotional message. Consider shorter sentences and plain language.','ACCESS-01','Break long sentences into shorter, direct statements.',.75)
 if own: c.close()
 return findings

@app.on_event('startup')
def startup(): init_db()

@app.get('/',response_class=HTMLResponse)
def home(): return (ROOT/'static'/'index.html').read_text(encoding='utf-8')
@app.get('/api/health')
def health(): return {'ok':True,'product':'BrandGuard','mode':'local demo; deterministic checks; no external AI service configured'}
@app.get('/api/dashboard')
def dashboard():
 c=conn(); reviews=[dict(x) for x in c.execute('select * from reviews order by updated_at desc').fetchall()]; rules=c.execute('select count(*) from rules').fetchone()[0]; claims=[dict(x) for x in c.execute('select * from claims').fetchall()]
 allfind=[f for r in reviews for f in json.loads(r['findings'] or '[]')]
 cats={}
 for f in allfind: cats[f['category']]=cats.get(f['category'],0)+1
 out={'reviews':reviews,'stats':{'total':len(reviews),'needs_review':sum(r['status'] in ('needs_review','changes_requested','in_review') for r in reviews),'approved':sum(r['status']=='approved' for r in reviews),'open_findings':sum(f['decision']=='open' for f in allfind),'rules':rules,'claims':len(claims),'expired_claims':sum(x['status']=='expired' or x['expires']<date.today().isoformat() for x in claims)},'categories':cats,'claims':claims,'rules':[dict(x) for x in c.execute('select * from rules order by id').fetchall()]}; c.close(); return out
@app.get('/api/reviews')
def get_reviews():
 c=conn(); rows=[dict(x) for x in c.execute('select * from reviews order by updated_at desc').fetchall()]; c.close()
 for r in rows: r['findings']=json.loads(r['findings'] or '[]')
 return rows
class ReviewIn(BaseModel):
 title:str=Field(min_length=1,max_length=160); content:str=Field(min_length=5,max_length=30000); channel:str='Website'; audience:str='General audience'; author:str='Demo Creator'
@app.post('/api/reviews')
def create_review(body:ReviewIn):
 c=conn(); rid=uuid.uuid4().hex[:10]; now=datetime.now().isoformat(timespec='seconds'); fs=review_content(body.content,c); status='needs_review' if fs else 'in_review'
 c.execute('insert into reviews values(?,?,?,?,?,?,?,?,?,?,?)',(rid,body.title,body.content,body.channel,body.audience,status,json.dumps(fs),now,now,1,body.author)); c.execute('insert into audit(review_id,actor,action,details,created_at) values(?,?,?,?,?)',(rid,body.author,'Review created',f'{len(fs)} finding(s) generated against approved rules and facts.',now)); c.commit(); row=dict(c.execute('select * from reviews where id=?',(rid,)).fetchone()); row['findings']=fs; c.close(); return row
@app.get('/api/reviews/{rid}')
def get_review(rid:str):
 c=conn(); row=c.execute('select * from reviews where id=?',(rid,)).fetchone()
 if not row: c.close(); raise HTTPException(404,'Review not found')
 r=dict(row); r['findings']=json.loads(r['findings'] or '[]'); r['comments']=[dict(x) for x in c.execute('select * from comments where review_id=? order by id desc',(rid,))]; r['audit']=[dict(x) for x in c.execute('select * from audit where review_id=? order by id desc',(rid,))]; c.close(); return r
class DecisionIn(BaseModel): decision:str; actor:str='Demo Creator'; note:Optional[str]=None; replacement:Optional[str]=None
@app.post('/api/reviews/{rid}/findings/{fid}/decision')
def decide(rid:str,fid:str,b:DecisionIn):
 if b.decision not in ('accepted','rejected','needs_human_check'): raise HTTPException(400,'Invalid decision')
 c=conn(); row=c.execute('select * from reviews where id=?',(rid,)).fetchone()
 if not row: c.close(); raise HTTPException(404,'Review not found')
 fs=json.loads(row['findings'] or '[]'); f=next((x for x in fs if x['id']==fid),None)
 if not f: c.close(); raise HTTPException(404,'Finding not found')
 f['decision']=b.decision; f['decision_note']=b.note or ''; f['replacement']=b.replacement or ''; now=datetime.now().isoformat(timespec='seconds')
 c.execute('update reviews set findings=?,updated_at=? where id=?',(json.dumps(fs),now,rid)); c.execute('insert into audit(review_id,actor,action,details,created_at) values(?,?,?,?,?)',(rid,b.actor,'Finding '+b.decision,f['excerpt']+' — '+(b.note or 'No note supplied'),now)); c.commit(); c.close(); return {'ok':True,'finding':f}
class WorkflowIn(BaseModel): action:str; actor:str='Demo Manager'; note:str=''
@app.post('/api/reviews/{rid}/workflow')
def workflow(rid:str,b:WorkflowIn):
 mapping={'approve':'approved','request_changes':'changes_requested','submit':'in_review','reopen':'needs_review'}
 if b.action not in mapping: raise HTTPException(400,'Unknown workflow action')
 c=conn(); row=c.execute('select * from reviews where id=?',(rid,)).fetchone()
 if not row: c.close(); raise HTTPException(404,'Review not found')
 fs=json.loads(row['findings'] or '[]')
 if b.action=='approve' and any(f['decision']=='open' for f in fs): c.close(); raise HTTPException(400,'Resolve every finding before approval. Use “Needs human check” if appropriate.')
 now=datetime.now().isoformat(timespec='seconds'); status=mapping[b.action]
 c.execute('update reviews set status=?,updated_at=? where id=?',(status,now,rid)); c.execute('insert into audit(review_id,actor,action,details,created_at) values(?,?,?,?,?)',(rid,b.actor,{'approve':'Approved','request_changes':'Changes requested','submit':'Submitted for review','reopen':'Reopened'}[b.action],b.note or 'Workflow status updated.',now)); c.commit(); c.close(); return {'ok':True,'status':status}
class CommentIn(BaseModel): author:str='Demo Reviewer'; body:str=Field(min_length=1,max_length=2000)
@app.post('/api/reviews/{rid}/comments')
def comment(rid:str,b:CommentIn):
 c=conn();
 if not c.execute('select id from reviews where id=?',(rid,)).fetchone(): c.close(); raise HTTPException(404,'Review not found')
 now=datetime.now().isoformat(timespec='seconds'); c.execute('insert into comments(review_id,author,body,created_at) values(?,?,?,?)',(rid,b.author,b.body,now)); c.execute('insert into audit(review_id,actor,action,details,created_at) values(?,?,?,?,?)',(rid,b.author,'Comment added',b.body,now)); c.commit(); c.close(); return {'ok':True}
class RuleIn(BaseModel): id:str=''; title:str; body:str; category:str='messaging'; severity:str='medium'
@app.post('/api/rules')
def add_rule(b:RuleIn):
 c=conn(); rid=b.id.strip() or ('RULE-'+uuid.uuid4().hex[:5].upper());
 if c.execute('select id from rules where id=?',(rid,)).fetchone(): c.close(); raise HTTPException(409,'Rule ID already exists')
 c.execute('insert into rules values(?,?,?,?,?,?)',(rid,b.title,b.body,b.category,b.severity,datetime.now().isoformat(timespec='seconds'))); c.commit(); c.close(); return {'ok':True,'id':rid}
class ClaimIn(BaseModel): id:str=''; claim:str; source:str; expires:str; owner:str='Marketing'; status:str='active'
@app.post('/api/claims')
def add_claim(b:ClaimIn):
 c=conn(); rid=b.id.strip() or ('CL-'+uuid.uuid4().hex[:5].upper())
 if c.execute('select id from claims where id=?',(rid,)).fetchone(): c.close(); raise HTTPException(409,'Claim ID already exists')
 c.execute('insert into claims values(?,?,?,?,?,?,?)',(rid,b.claim,b.source,b.expires,b.owner,b.status,datetime.now().isoformat(timespec='seconds'))); c.commit(); c.close(); return {'ok':True,'id':rid}
@app.post('/api/visual-check')
async def visual_check(file:UploadFile=File(...), alt_text:str=''):
 data=await file.read()
 if len(data)>8*1024*1024: raise HTTPException(413,'Image must be under 8 MB')
 try:
  im=Image.open(BytesIO(data)).convert('RGB'); im.thumbnail((250,250)); pix=list(im.getdata()); avg=tuple(round(sum(p[i] for p in pix)/len(pix)) for i in range(3));
 except Exception: raise HTTPException(400,'Please upload a valid image (PNG, JPG or WEBP).')
 def lum(rgb):
  vals=[]
  for v in rgb:
   v=v/255; vals.append(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)
  return .2126*vals[0]+.7152*vals[1]+.0722*vals[2]
 light=lum((255,255,255)); dark=lum((0,0,0)); L=lum(avg); contrast=(max(light,L)+.05)/(min(light,L)+.05)
 issues=[]
 if not alt_text.strip(): issues.append({'severity':'medium','title':'Alternative text missing','detail':'Add concise alt text describing the image’s purpose and meaningful visual information.'})
 if 0.25 < L < .78: issues.append({'severity':'low','title':'Mixed image colours','detail':'Average colour sampling cannot confirm text contrast. Check text/background pairs with a contrast analyser.'})
 return {'filename':file.filename,'width':Image.open(BytesIO(data)).width,'height':Image.open(BytesIO(data)).height,'average_rgb':avg,'average_hex':'#%02X%02X%02X'%avg,'average_luminance':round(L,3),'contrast_if_black_text':round((L+.05)/(dark+.05),2),'contrast_if_white_text':round((light+.05)/(L+.05),2),'alt_text':alt_text,'issues':issues,'disclaimer':'Automated image sampling is a screening aid, not a guarantee of WCAG compliance. Actual text/background regions must be measured separately.'}
@app.get('/api/export/{rid}')
def export_review(rid:str):
 from fastapi.responses import JSONResponse
 c=conn(); r=c.execute('select * from reviews where id=?',(rid,)).fetchone()
 if not r: c.close(); raise HTTPException(404,'Review not found')
 out=dict(r); out['findings']=json.loads(out['findings'] or '[]'); out['comments']=[dict(x) for x in c.execute('select * from comments where review_id=?',(rid,))]; out['audit']=[dict(x) for x in c.execute('select * from audit where review_id=?',(rid,))]; c.close(); return out
