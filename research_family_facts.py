"""Conservative source-grounded English fact-card extractor. No AI service required."""
import argparse, re, sqlite3, time
from pathlib import Path
from urllib.parse import quote
import requests
DB=Path(__file__).with_name('families.sqlite3')
SESSION=requests.Session()
SESSION.headers.update({'User-Agent':'InzichtInNatuur/2.0 (educational biodiversity encyclopedia; https://github.com/)', 'Accept':'application/json'})
TOPICS=[('Ecology and diet',r'\b(feed|feeds|feeding|diet|prey|predat|herbivor|carnivor|nectar|host plant|saprotroph|decompos|photosynthesi)'),('Reproduction and development',r'\b(reproduc|breed|breeding|egg|larva|larvae|pollinat|seed|spore|germinat|mating)'),('Habitat and distribution',r'\b(endemic|native to|distributed|distribution|habitat|tropical|temperate|freshwater|marine|rainforest|desert)'),('Adaptations and behavior',r'\b(adapt|camouflag|mimic|flight|song|call|venom|defen[sc]|symbiosis|mutualis|bioluminescen)'),('Names and history',r'\b(named after|name derives|name is derived|etymolog|first described|named for)'),('People and conservation',r'\b(conservat|threaten|endanger|cultivat|medicinal|economic|agricultur|commercial)')]
def fetch(name,delay):
    # Wikipedia is supplementary; a missing page is normal, not an error.
    for lang in ('en',):
        url=f'https://{lang}.wikipedia.org/w/api.php'
        params={'action':'query','format':'json','redirects':1,'prop':'extracts','explaintext':1,'titles':name,'exsectionformat':'plain'}
        for attempt in range(3):
            try:
                r=SESSION.get(url,params=params,timeout=25)
                if r.status_code in (429,503):
                    wait=min(35,5*(attempt+1));print(f'Wikipedia rate limited; wait {wait}s',flush=True);time.sleep(wait);continue
                if r.status_code in (403,404):break
                r.raise_for_status(); data=r.json()
                for p in data.get('query',{}).get('pages',{}).values():
                    if 'missing' in p:continue
                    if p.get('title','').casefold()!=name.casefold():continue
                    extract=p.get('extract','')
                    if extract and len(extract)>80:
                        time.sleep(delay)
                        return extract, f'https://en.wikipedia.org/wiki/{quote(name)}'
                break
            except (requests.RequestException,ValueError) as e:
                print(f'  source unavailable: {str(e)[:100]}',flush=True);time.sleep(2)
    return None,None
def sentences(text):
    text=re.sub(r'\s+',' ',text)
    for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])',text):
        s=s.strip()
        if 55<=len(s)<=420 and not re.search(r'\b(?:citation needed|this article|edit section|references|see also)\b',s,re.I):yield s

def extract(text,name,maxfacts):
    found=[]; used=set()
    for title,pattern in TOPICS:
        for sentence in sentences(text):
            if re.search(pattern,sentence,re.I) and sentence not in used:
                # Reject sentences that are predominantly about an unrelated taxon; these are candidates, not validated family-wide claims.
                if sentence.startswith(('For example,','For instance,','One species,','A species,','Some species,','The species ')):continue
                found.append((title,sentence));used.add(sentence);break
        if len(found)>=maxfacts:break
    return found

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=20);ap.add_argument('--delay',type=float,default=2.0);ap.add_argument('--refresh',action='store_true');ap.add_argument('--max-facts',type=int,default=6);args=ap.parse_args()
    with sqlite3.connect(DB) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS family_fact_research (family_id INTEGER PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, fact_count INTEGER NOT NULL DEFAULT 0)''')
        ids=[r[0] for r in c.execute('SELECT family_id FROM family_profiles ORDER BY family_id LIMIT ?', (args.limit,))]
        for i,fid in enumerate(ids,1):
            name=c.execute('SELECT name FROM families WHERE id=?',(fid,)).fetchone()[0]
            if c.execute('SELECT 1 FROM family_fact_research WHERE family_id=?',(fid,)).fetchone() and not args.refresh:
                print(f'{i}/{len(ids)} {name}: cached',flush=True);continue
            print(f'{i}/{len(ids)} {name}: searching for biological information',flush=True)
            existing=c.execute("SELECT text,source_url FROM family_evidence WHERE family_id=? AND language='en' AND evidence_type='introduction' ORDER BY length(text) DESC LIMIT 1",(fid,)).fetchone()
            text,url=fetch(name,args.delay)
            if text:
                c.execute('''INSERT INTO family_evidence(family_id,source_name,source_url,language,evidence_type,text) VALUES(?,?,?,?,?,?) ON CONFLICT(family_id,source_url,evidence_type) DO UPDATE SET text=excluded.text,fetched_at=CURRENT_TIMESTAMP''',(fid,'Wikipedia (en)',url,'en','full_article',text[:25000]))
                c.execute('INSERT OR IGNORE INTO family_sources(family_id,source_name,url) VALUES(?,?,?)',(fid,'Wikipedia (en)',url))
            elif existing:
                text,url=existing
            else:
                text='';url=''
            facts=extract(text,name,args.max_facts)
            # Only replace facts when new source evidence exists; preserve any manually curated facts.
            if facts:
                c.execute('DELETE FROM family_facts WHERE family_id=? AND source_url=?',(fid,url))
                base=c.execute('SELECT COALESCE(MAX(position),0) FROM family_facts WHERE family_id=?',(fid,)).fetchone()[0]
                for j,(title,body) in enumerate(facts,1):
                    c.execute('INSERT INTO family_facts(family_id,position,title,body,source_url) VALUES(?,?,?,?,?)',(fid,base+j,title,body,url))
            status='source_excerpts_need_review' if facts else 'no_biological_source'
            c.execute('''INSERT INTO family_fact_research(family_id,status,fact_count) VALUES(?,?,?) ON CONFLICT(family_id) DO UPDATE SET status=excluded.status,fact_count=excluded.fact_count,updated_at=CURRENT_TIMESTAMP''',(fid,status,len(facts)))
            c.commit();print(f'  {len(facts)} sourced excerpts ({status})',flush=True)
        print('TOTAL:',c.execute('SELECT COUNT(*),COALESCE(SUM(fact_count),0) FROM family_fact_research').fetchone(),flush=True)
if __name__=='__main__':main()
