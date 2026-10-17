"""Generate source-grounded Dutch draft profiles with an optional OpenAI API key.
Never publish unreviewed drafts as verified facts.
"""
import argparse, json, os, sqlite3, time, urllib.request, urllib.error
from pathlib import Path
DB=Path(__file__).with_name('families.sqlite3')
def init(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS family_draft_reviews(family_id INTEGER PRIMARY KEY,status TEXT NOT NULL DEFAULT 'needs_review',model TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,notes TEXT); CREATE TABLE IF NOT EXISTS family_evidence_validation(evidence_id INTEGER PRIMARY KEY,decision TEXT NOT NULL,reason TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
def validate(c):
 rows=c.execute('''SELECT e.id,e.family_id,f.name,e.source_name,e.evidence_type,e.text FROM family_evidence e JOIN families f ON f.id=e.family_id''').fetchall()
 for eid,fid,name,source,kind,txt in rows:
  decision='context_only' if kind.startswith('taxon') else 'needs_review'; reason='Taxonomic metadata is not biological narrative evidence' if decision=='context_only' else 'Identity and claims must be checked against original source'
  if source=='Wikidata':
   decision='needs_review';reason='Wikidata search labels alone cannot establish taxon identity; verify P105 family and P225 scientific name'
  c.execute('INSERT INTO family_evidence_validation(evidence_id,decision,reason) VALUES(?,?,?) ON CONFLICT(evidence_id) DO UPDATE SET decision=excluded.decision,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP',(eid,decision,reason))
 c.commit()
def generate(key,model,payload):
 schema={'type':'object','properties':{'introduction':{'type':'string'},'facts':{'type':'array','items':{'type':'object','properties':{'title':{'type':'string'},'body':{'type':'string'},'source_urls':{'type':'array','items':{'type':'string'}}},'required':['title','body','source_urls'],'additionalProperties':False}}},'required':['introduction','facts'],'additionalProperties':False}
 body={'model':model,'instructions':('Schrijf in helder Nederlands een korte introductie (max 130 woorden) en maximaal 6 verrassende feiten voor de familie. Gebruik UITSLUITEND de meegegeven bronteksten. Verzin niets. GBIF taxonomische metadata bewijst geen biologische bijzonderheden. Wikidata records zijn NIET gevalideerd: gebruik ze niet voor inhoudelijke claims. Bij onvoldoende inhoud: lege introductie en/of lege facts. Elk feit moet een of meer exacte source_urls uit de invoer hebben. Verwar soortkenmerken niet met kenmerken van alle familieleden. Geen extrapolatie over endemisme.'),'input':json.dumps(payload,ensure_ascii=False),'text':{'format':{'type':'json_schema','name':'family_profile','strict':True,'schema':schema}}}
 req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(req,timeout=100) as response: result=json.load(response)
 texts=[part.get('text','') for item in result.get('output',[]) for part in item.get('content',[]) if part.get('type')=='output_text']
 return json.loads(''.join(texts))
def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=20);p.add_argument('--model',default='gpt-4.1-mini');p.add_argument('--retry',action='store_true');a=p.parse_args()
 with sqlite3.connect(DB) as c:
  init(c);validate(c)
  ids=[x[0] for x in c.execute('SELECT family_id FROM family_research_log ORDER BY family_id LIMIT ?', (a.limit,))]
  key=os.getenv('OPENAI_API_KEY','')
  if not key: print('OPENAI_API_KEY absent: validated evidence metadata only. No AI profiles generated.',flush=True);return
  for fid in ids:
   name,kingdom,order=c.execute('SELECT name,kingdom,order_name FROM families WHERE id=?',(fid,)).fetchone()
   old=c.execute('SELECT status FROM family_draft_reviews WHERE family_id=?',(fid,)).fetchone()
   if old and not a.retry:continue
   evidence=[{'source':s,'url':u,'text':t[:3000]} for s,u,t,kind in c.execute("SELECT source_name,source_url,text,evidence_type FROM family_evidence WHERE family_id=? AND evidence_type='introduction'",(fid,))]
   if not evidence:
    print(name,'no suitable narrative evidence; skipped',flush=True);continue
   try:
    result=generate(key,a.model,{'family':name,'kingdom':kingdom,'order':order,'evidence':evidence})
    allowed={x['url'] for x in evidence};facts=[x for x in result.get('facts',[]) if x.get('source_urls') and set(x['source_urls']).issubset(allowed) and x.get('body')]
    c.execute("INSERT INTO family_profiles(family_id,introduction,language,status) VALUES(?,?,'nl','draft_needs_review') ON CONFLICT(family_id) DO UPDATE SET introduction=excluded.introduction,language=excluded.language,status=excluded.status,updated_at=CURRENT_TIMESTAMP",(fid,result.get('introduction','')))
    c.execute('DELETE FROM family_facts WHERE family_id=?',(fid,))
    for pos,fact in enumerate(facts,1):c.execute('INSERT INTO family_facts(family_id,position,title,body,source_url) VALUES(?,?,?,?,?)',(fid,pos,fact['title'],fact['body'],fact['source_urls'][0]))
    c.execute("INSERT INTO family_draft_reviews(family_id,status,model) VALUES(?,'needs_review',?) ON CONFLICT(family_id) DO UPDATE SET status='needs_review',model=excluded.model,updated_at=CURRENT_TIMESTAMP",(fid,a.model));c.commit()
    print(name, 'draft',len(facts),'facts',flush=True);time.sleep(1)
   except (ValueError,urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as e:print(name,'generation failed',str(e)[:180],flush=True)
if __name__=='__main__':main()
