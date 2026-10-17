"""Resumable multi-source family research; raw sourced evidence, never invented facts."""
import argparse, sqlite3, time, json, random
from pathlib import Path
from urllib.parse import quote
import requests
DB=Path(__file__).with_name('families.sqlite3')
S=requests.Session();S.headers.update({'User-Agent':'InzichtInNatuur/1.7 (biodiversity research; contact: https://github.com/)', 'Accept':'application/json'})
def get(url,params=None,delay=1.5):
    for attempt in range(4):
        try:
            r=S.get(url,params=params,timeout=25)
            if r.status_code in (429,500,502,503,504):
                wait=min(45, max(float(r.headers.get('Retry-After','0') or 0), 3*(2**attempt)))
                print(f'  HTTP {r.status_code}; waiting {wait:.0f}s',flush=True);time.sleep(wait);continue
            r.raise_for_status();time.sleep(delay);return r.json()
        except (requests.RequestException,ValueError) as e:
            print('  source error:',str(e)[:180],flush=True);time.sleep(2*(attempt+1))
    return None
def init(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS family_evidence (id INTEGER PRIMARY KEY, family_id INTEGER NOT NULL, source_name TEXT NOT NULL, source_url TEXT NOT NULL, language TEXT, evidence_type TEXT NOT NULL, text TEXT NOT NULL, fetched_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(family_id,source_url,evidence_type));
    CREATE TABLE IF NOT EXISTS family_research_log (family_id INTEGER PRIMARY KEY, status TEXT NOT NULL, attempted_at TEXT DEFAULT CURRENT_TIMESTAMP, evidence_count INTEGER DEFAULT 0);''')
def store(c,fid,source,url,lang,kind,value):
    if not value:return 0
    value=' '.join(str(value).split())[:5000]
    c.execute('INSERT INTO family_evidence(family_id,source_name,source_url,language,evidence_type,text) VALUES(?,?,?,?,?,?) ON CONFLICT(family_id,source_url,evidence_type) DO UPDATE SET text=excluded.text,fetched_at=CURRENT_TIMESTAMP',(fid,source,url,lang,kind,value))
    c.execute('INSERT OR IGNORE INTO family_sources(family_id,source_name,url) VALUES(?,?,?)',(fid,source,url))
    return 1
def research(c,fid,name,delay):
    count=0
    # GBIF taxon match: validate rank and scientific name to avoid genus-level false matches.
    data=get('https://api.gbif.org/v1/species/match',{'name':name,'rank':'FAMILY','strict':'true'},delay)
    if data and data.get('rank')=='FAMILY' and data.get('scientificName','').split(' ')[0].rstrip('.')==name:
        key=data.get('usageKey');url=f'https://www.gbif.org/species/{key}'
        count+=store(c,fid,'GBIF',url,'en','taxon',json.dumps({k:data.get(k) for k in ('scientificName','status','kingdom','phylum','class','order','family','authorship') if data.get(k)},ensure_ascii=False))
        if key:
            details=get(f'https://api.gbif.org/v1/species/{key}',delay=delay)
            if details:
                count+=store(c,fid,'GBIF',url,'en','taxon_details',json.dumps({k:details.get(k) for k in ('scientificName','authorship','publishedIn','taxonomicStatus','rank','kingdom','phylum','class','order','family') if details.get(k)},ensure_ascii=False))
    # Wikidata: exact scientific name and rank via SPARQL endpoint is rate sensitive; search candidates and validate label/description.
    wd=get('https://www.wikidata.org/w/api.php',{'action':'wbsearchentities','search':name,'language':'en','format':'json','limit':5},delay)
    if wd:
        for item in wd.get('search',[]):
            if item.get('label','').casefold()==name.casefold():
                count+=store(c,fid,'Wikidata',item.get('concepturi',f'https://www.wikidata.org/wiki/{item["id"]}'),'en','description',item.get('description',''))
                break
    # Wikimedia REST summaries: one request per language, exact title, verify returned title.
    for lang in ('nl','en'):
        page=get(f'https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(name)}',delay=delay)
        if page and page.get('type')!='disambiguation' and page.get('title','').casefold()==name.casefold():
            url=page.get('content_urls',{}).get('desktop',{}).get('page',f'https://{lang}.wikipedia.org/wiki/{quote(name)}')
            count+=store(c,fid,f'Wikipedia ({lang})',url,lang,'introduction',page.get('extract',''))
    return count
def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=20);p.add_argument('--delay',type=float,default=1.5);p.add_argument('--retry',action='store_true');a=p.parse_args()
    with sqlite3.connect(DB) as c:
        init(c)
        # Existing first batch is kept stable; use original selection if research rows already exist.
        existing=c.execute('SELECT family_id FROM family_profiles ORDER BY family_id').fetchall()
        if existing:
            ids=[r[0] for r in existing][:a.limit]
            rows=c.execute('SELECT id,name FROM families WHERE id IN (%s)'%','.join('?'*len(ids)),ids).fetchall() if ids else []
        else:
            rows=c.execute('SELECT id,name FROM families ORDER BY kingdom,species_count DESC LIMIT ?', (a.limit,)).fetchall()
        for i,(fid,name) in enumerate(rows,1):
            old=c.execute('SELECT status FROM family_research_log WHERE family_id=?',(fid,)).fetchone()
            if old and not a.retry:
                print(f'{i}/{len(rows)} {name}: cached',flush=True);continue
            print(f'{i}/{len(rows)} {name}: researching',flush=True)
            count=research(c,fid,name,a.delay)
            c.execute('INSERT INTO family_research_log(family_id,status,evidence_count) VALUES(?,?,?) ON CONFLICT(family_id) DO UPDATE SET status=excluded.status,evidence_count=excluded.evidence_count,attempted_at=CURRENT_TIMESTAMP',(fid,'evidence_collected' if count else 'no_evidence',count))
            c.commit();print(f'  {count} evidence records',flush=True)
    print('Finished. Evidence is source material, NOT verified Dutch narratives or fact cards.',flush=True)
if __name__=='__main__':main()
