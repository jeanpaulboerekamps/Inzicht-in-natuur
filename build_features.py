"""Conservative resumable collection of candidate family traits from Wikipedia.
A 429 stops the run safely; no failed family is marked as checked.
Candidate sentences require human review before use as diagnostic characters.
"""
import argparse, re, sqlite3, time
from pathlib import Path
from urllib.parse import quote
import requests

DB=Path(__file__).with_name('families.sqlite3')
API='https://en.wikipedia.org/api/rest_v1/page/summary/'
KEYWORDS=re.compile(r'\b(?:wing|antenna|larva|larvae|caterpillar|leaf|leaves|flower|fruit|seed|spore|gill|cap|stem|root|petal|sepal|shell|leg|body|beak|bill|feather|scale|habitat|feed|pollinat|parasit|aquatic|terrestrial|fung|mushroom|hypha|sporang|coloni|filament|cell wall)\w*\b',re.I)
SENTENCE=re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
def candidates(text):
    out=[]
    for sentence in SENTENCE.split(re.sub(r'\s+',' ',text or '').strip()):
        if 35<=len(sentence)<=320 and KEYWORDS.search(sentence) and not re.search(r'\b(?:was named|named after|described by|established by|first described|is a family of)\b',sentence,re.I):
            out.append(sentence)
        if len(out)==3: break
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=25);p.add_argument('--delay',type=float,default=5.0);a=p.parse_args()
    s=requests.Session();s.headers.update({'User-Agent':'InzichtInNatuurResearch/1.1 (noncommercial taxonomy study; contact via GitHub jeanpaulboerekamps/Inzicht-in-natuur)','Accept':'application/json'})
    with sqlite3.connect(DB) as db:
        db.execute('CREATE TABLE IF NOT EXISTS feature_provenance (family_id INTEGER PRIMARY KEY, source_url TEXT, status TEXT NOT NULL, checked_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        db.commit()
        rows=db.execute('SELECT id,name FROM families WHERE id NOT IN (SELECT family_id FROM feature_provenance) ORDER BY id LIMIT ?', (a.limit,)).fetchall()
        print('Families to inspect:',len(rows),flush=True)
        for n,(fid,name) in enumerate(rows,1):
            try:
                response=s.get(API+quote(name.replace(' ','_'),safe=''),timeout=35)
            except requests.RequestException as e:
                db.commit();raise SystemExit(f'Network problem at {name}; saved checkpoint, retry later: {e}')
            if response.status_code in (429,403,503):
                db.commit();raise SystemExit(f'Wikipedia HTTP {response.status_code} at {name}. STOP: rate-limited; no failed rows marked. Try later or change source.')
            status='not_found';url=None;features=[]
            if response.status_code==200:
                try: page=response.json()
                except ValueError: db.commit();raise SystemExit('Invalid Wikipedia response; stopped without marking family')
                title=page.get('title','')
                if title.casefold().replace(' ','_')==name.casefold().replace(' ','_'):
                    features=candidates(page.get('extract',''))
                    url=page.get('content_urls',{}).get('desktop',{}).get('page')
                    status='candidate' if features else 'no_characteristics'
                else: status='title_mismatch'
            elif response.status_code!=404:
                db.commit();raise SystemExit(f'Unexpected HTTP {response.status_code}; checkpoint saved')
            if features:
                db.execute('UPDATE families SET feature1=?,feature2=?,feature3=? WHERE id=? AND feature1 IS NULL AND feature2 IS NULL AND feature3 IS NULL',(*((features+[None]*3)[:3]),fid))
            db.execute('INSERT OR REPLACE INTO feature_provenance (family_id,source_url,status,checked_at) VALUES (?,?,?,CURRENT_TIMESTAMP)',(fid,url,status))
            db.commit()
            print(f'{n}/{len(rows)} {name}: {status}',flush=True)
            time.sleep(max(0,a.delay))
        print('Checked:',db.execute('SELECT COUNT(*) FROM feature_provenance').fetchone()[0],flush=True)
        print('With candidate characteristics:',db.execute("SELECT COUNT(*) FROM feature_provenance WHERE status='candidate'").fetchone()[0],flush=True)
if __name__=='__main__':main()
