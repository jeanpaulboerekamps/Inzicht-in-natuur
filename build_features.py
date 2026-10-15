"""Conservative, resumable Wikipedia-backed family character extraction.

Only explicitly morphological/ecological sentences from a Wikipedia article
with an exact scientific title are copied as candidate characteristics.
Review is required before interpreting them as diagnostic characters.
"""
import argparse, re, sqlite3, time
from pathlib import Path
import requests

DB=Path(__file__).with_name('families.sqlite3')
API='https://en.wikipedia.org/w/api.php'
KEYWORDS=re.compile(r'\b(?:wing|antenna|larva|larvae|caterpillar|leaf|leaves|flower|fruit|seed|spore|gill|cap|stem|root|petal|sepal|shell|leg|body|beak|bill|feather|scale|habitat|feed|pollinat|parasit|aquatic|terrestrial|fung|mushroom|hypha|sporang|coloni|filament|cell wall)\w*\b',re.I)
SENTENCE=re.compile(r'(?<=[.!?])\s+(?=[A-Z])')

def candidates(text):
    text=re.sub(r'\s+',' ',text or '').strip()
    out=[]
    for sentence in SENTENCE.split(text):
        sentence=sentence.strip()
        if 35<=len(sentence)<=320 and KEYWORDS.search(sentence) and not re.search(r'\b(?:was named|named after|described by|established by|first described|is a family of)\b',sentence,re.I):
            out.append(sentence)
        if len(out)==3: break
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--limit',type=int,default=1000)
    p.add_argument('--delay',type=float,default=1.0)
    a=p.parse_args()
    s=requests.Session();s.headers['User-Agent']='InzichtInNatuur/1.0 (educational research; Wikipedia summary candidate collection)'
    with sqlite3.connect(DB) as db:
        db.execute('CREATE TABLE IF NOT EXISTS feature_provenance (family_id INTEGER PRIMARY KEY, source_url TEXT, status TEXT NOT NULL, checked_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        db.commit()
        rows=db.execute('SELECT id,name FROM families WHERE id NOT IN (SELECT family_id FROM feature_provenance) ORDER BY id LIMIT ?', (a.limit,)).fetchall()
        print('Families to inspect:',len(rows),flush=True)
        for n,(fid,name) in enumerate(rows,1):
            status='not_found';url=None;features=[]
            try:
                response=s.get(API,params={'action':'query','format':'json','prop':'extracts','explaintext':1,'exintro':1,'redirects':1,'titles':name},timeout=35)
                response.raise_for_status()
                pages=response.json()['query']['pages']
                page=next(iter(pages.values()))
                if 'missing' not in page:
                    # Exact canonical title only: redirects to unrelated topics are excluded.
                    title=page.get('title','')
                    if title.casefold()==name.casefold():
                        features=candidates(page.get('extract',''))
                        url='https://en.wikipedia.org/wiki/'+name.replace(' ','_')
                        status='candidate' if features else 'no_characteristics'
                    else: status='title_mismatch'
            except (requests.RequestException,ValueError,KeyError) as exc:
                print('API failure:',name,exc,flush=True)
                time.sleep(5)
                continue  # retry next run
            if features:
                db.execute('UPDATE families SET feature1=?,feature2=?,feature3=? WHERE id=? AND feature1 IS NULL AND feature2 IS NULL AND feature3 IS NULL',(*((features+[None]*3)[:3]),fid))
            db.execute('INSERT OR REPLACE INTO feature_provenance (family_id,source_url,status,checked_at) VALUES (?,?,?,CURRENT_TIMESTAMP)',(fid,url,status))
            if n%20==0:
                db.commit();print(f'Checked {n}/{len(rows)}',flush=True)
            time.sleep(max(0,a.delay))
        db.commit()
        print('Total reviewed:',db.execute('SELECT COUNT(*) FROM feature_provenance').fetchone()[0],flush=True)
        print('With candidate text:',db.execute("SELECT COUNT(*) FROM feature_provenance WHERE status='candidate'").fetchone()[0],flush=True)
if __name__=='__main__':main()
