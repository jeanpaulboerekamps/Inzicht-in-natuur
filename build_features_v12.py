"""V12: collect source-backed candidate descriptions for manual diagnostic review.
Does NOT pretend that arbitrary description sentences are diagnostic traits.
"""
import argparse, csv, json, sqlite3, time
from pathlib import Path
import requests

DB = Path(__file__).with_name('families.sqlite3')
API = 'https://api.gbif.org/v1'
S = requests.Session()
S.headers.update({'User-Agent':'InzichtInNatuur/1.2 (taxonomic family research; contact via repository)', 'Accept':'application/json'})

def get(path, params=None):
    for retry in range(4):
        try:
            r=S.get(API+path,params=params,timeout=25)
            if r.status_code in (429,500,502,503,504):
                pause=min(90,8*2**retry)
                print(f'GBIF {r.status_code}; waiting {pause}s',flush=True)
                time.sleep(pause)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if retry==3: raise
            time.sleep(5*(retry+1))
    raise RuntimeError('GBIF API temporarily unavailable')

def select_families(db, limit):
    # Round-robin kingdoms to avoid selecting only alphabetically first families.
    rows=db.execute('SELECT id,name,kingdom FROM families WHERE name IS NOT NULL ORDER BY kingdom,name').fetchall()
    groups={}
    for row in rows: groups.setdefault(row[2] or 'Unknown',[]).append(row)
    selected=[]
    while len(selected)<limit and any(groups.values()):
        for kingdom in sorted(groups):
            if groups[kingdom] and len(selected)<limit:
                selected.append(groups[kingdom].pop(0))
    return selected

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--limit',type=int,default=100)
    p.add_argument('--delay',type=float,default=1.5)
    args=p.parse_args()
    if not DB.exists(): raise SystemExit('Missing families.sqlite3')
    with sqlite3.connect(DB) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS feature_research (
            family_id INTEGER PRIMARY KEY, family_name TEXT, kingdom TEXT,
            gbif_key INTEGER, match_status TEXT, description TEXT,
            description_source TEXT, source_url TEXT, status TEXT,
            checked_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        db.commit()
        families=select_families(db,args.limit)
        print(f'Selected {len(families)} families across kingdoms',flush=True)
        try:
            for i,(id,name,kingdom) in enumerate(families,1):
                if db.execute('SELECT 1 FROM feature_research WHERE family_id=?',(id,)).fetchone():
                    continue
                try:
                    match=get('/species/match',{'name':name,'rank':'FAMILY','strict':'true'})
                    key=match.get('usageKey') if match.get('rank')=='FAMILY' and match.get('scientificName','').split(' ')[0]==name else None
                    descriptions=[]
                    if key:
                        data=get(f'/species/{key}/descriptions',{'limit':20})
                        descriptions=[x for x in data.get('results',[]) if x.get('description')]
                    item=descriptions[0] if descriptions else {}
                    desc=item.get('description','')[:10000]
                    status='candidate_needs_review' if desc else ('matched_no_description' if key else 'no_exact_match')
                    db.execute('''INSERT INTO feature_research
                        (family_id,family_name,kingdom,gbif_key,match_status,description,description_source,source_url,status)
                        VALUES (?,?,?,?,?,?,?,?,?)''',
                        (id,name,kingdom,key,match.get('status',''),desc,str(item.get('source','')),
                         f'https://www.gbif.org/species/{key}' if key else '',status))
                    db.commit()
                    print(f'{i}/{len(families)} {name}: {status}',flush=True)
                except Exception as exc:
                    print(f'{i}/{len(families)} {name}: temporary error {exc}',flush=True)
                time.sleep(max(0,args.delay))
        finally:
            out=Path('feature_research_review.csv')
            cols=['family_id','family_name','kingdom','gbif_key','match_status','description','description_source','source_url','status']
            with out.open('w',newline='',encoding='utf-8-sig') as f:
                w=csv.writer(f);w.writerow(cols)
                w.writerows(db.execute('SELECT '+','.join(cols)+' FROM feature_research ORDER BY kingdom,family_name'))
            print('Saved research review CSV and database checkpoint',flush=True)
        print('NOTE: feature1/2/3 deliberately unchanged until verified.',flush=True)

if __name__=='__main__':main()
