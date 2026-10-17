"""Conservative, resumable source collection. No fabricated facts or AI-generated text."""
import argparse,sqlite3,time,re,html
from pathlib import Path
import requests
DB=Path(__file__).with_name('families.sqlite3')
S=requests.Session();S.headers.update({'User-Agent':'InzichtInNatuurResearch/1.0 (educational noncommercial project)','Accept':'application/json'})
def setup(c):
    c.executescript("""CREATE TABLE IF NOT EXISTS family_profiles (family_id INTEGER PRIMARY KEY, introduction TEXT, language TEXT, status TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS family_facts (id INTEGER PRIMARY KEY AUTOINCREMENT,family_id INTEGER NOT NULL,position INTEGER NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,source_url TEXT,UNIQUE(family_id,position));
    CREATE TABLE IF NOT EXISTS family_sources (id INTEGER PRIMARY KEY AUTOINCREMENT,family_id INTEGER NOT NULL,source_name TEXT NOT NULL,url TEXT NOT NULL,accessed_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(family_id,url));""")
def fetch(name,lang):
    # Wikipedia REST summary, exact title only; ambiguous pages are rejected.
    url=f'https://{lang}.wikipedia.org/w/api.php'
    data=S.get(url,params={'action':'query','format':'json','redirects':1,'prop':'extracts|info','inprop':'url','exintro':1,'explaintext':1,'titles':name},timeout=25)
    data.raise_for_status();pages=data.json().get('query',{}).get('pages',{})
    item=next(iter(pages.values()),{})
    if 'missing' in item or 'invalid' in item:return None
    extract=re.sub(r'\s+',' ',html.unescape(item.get('extract',''))).strip()
    if not extract or len(extract)<70 or '(disambiguation)' in item.get('title','').lower():return None
    return extract[:1800],item.get('fullurl',f'https://{lang}.wikipedia.org/wiki/{name}'),lang
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=20);ap.add_argument('--delay',type=float,default=1.0);ap.add_argument('--retry-missing',action='store_true');args=ap.parse_args()
    with sqlite3.connect(DB) as c:
        setup(c)
        # Distribute sample across kingdoms, using names with most recorded species first.
        rows=c.execute('SELECT id,name,kingdom FROM families WHERE name IS NOT NULL ORDER BY kingdom,species_count DESC,name').fetchall()
        groups={}
        for row in rows:groups.setdefault(row[2] or 'Unknown',[]).append(row)
        sample=[]
        while len(sample)<args.limit and any(groups.values()):
            for k in sorted(groups):
                if groups[k] and len(sample)<args.limit:sample.append(groups[k].pop(0))
        for i,(id,name,kingdom) in enumerate(sample,1):
            old=c.execute('SELECT status FROM family_profiles WHERE family_id=?',(id,)).fetchone()
            if old and (not args.retry_missing or old[0]=='source_collected'):continue
            found=None
            for lang in ('nl','en'):
                try:
                    found=fetch(name,lang)
                    if found:break
                except requests.RequestException as e:print('Request failed:',name,lang,e,flush=True)
                time.sleep(args.delay)
            if found:
                intro,url,lang=found
                c.execute('INSERT OR REPLACE INTO family_profiles(family_id,introduction,language,status) VALUES(?,?,?,?)',(id,intro,lang,'source_collected_unreviewed'))
                c.execute('INSERT OR IGNORE INTO family_sources(family_id,source_name,url) VALUES(?,?,?)',(id,f'Wikipedia ({lang})',url))
                print(f'{i}/{len(sample)} {name}: source collected ({lang})',flush=True)
            else:
                c.execute('INSERT OR REPLACE INTO family_profiles(family_id,introduction,language,status) VALUES(?,?,?,?)',(id,None,None,'no_source_found'))
                print(f'{i}/{len(sample)} {name}: no source found',flush=True)
            c.commit();time.sleep(args.delay)
    print('Done. Source extracts are unreviewed; no facts have been invented.')
if __name__=='__main__':main()
