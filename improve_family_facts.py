"""Review existing family fact candidates and add carefully sourced pilot facts. No AI/API key.
Run: python improve_family_facts.py --limit 20 [--refresh]
The curated pilot facts are editorial examples, not automatically verified research.
"""
import argparse, sqlite3, re
from pathlib import Path
DB=Path(__file__).with_name('families.sqlite3')
PILOT={
'Orchidaceae':[
('Fungal partners','Orchid seeds are typically minute and have very limited food reserves. Germination in nature commonly depends on a compatible mycorrhizal fungus.','https://www.kew.org/read-and-watch/orchid-seeds'),
('Deceptive pollination','Some orchids attract pollinators without offering a reward; in certain Ophrys species, flowers mimic signals of female insects. This is not a trait of every orchid.','https://www.britannica.com/plant/orchid/Adaptations-for-pollination')],
'Geometridae':[
('Inchworm caterpillars','Many geometrid caterpillars have reduced numbers of abdominal prolegs and move by looping the body, giving rise to the name inchworms.','https://www.britannica.com/animal/geometrid-moth')],
'Cerambycidae':[
('Long antennae','Longhorn beetles are named for the conspicuously long antennae of many species, although antenna length varies within the family.','https://www.britannica.com/animal/long-horned-beetle'),
('Wood-associated larvae','Larvae of many longhorn beetles develop inside wood or other plant tissues, with major differences in host use among species.','https://www.britannica.com/animal/long-horned-beetle')]
}
BAD=re.compile(r'^(?:references|see also|external links|further reading|taxonomy|classification|description|distribution)\s',re.I)
def quality(body):
    if not body or len(body)<65 or len(body)>430:return False
    if BAD.search(body) or re.search(r'\b(citation needed|this article|wikipedia|click here)\b',body,re.I):return False
    if body.count('(')!=body.count(')'):return False
    return True

def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=20);p.add_argument('--refresh',action='store_true');a=p.parse_args()
 with sqlite3.connect(DB) as c:
  c.execute('CREATE TABLE IF NOT EXISTS family_fact_quality (family_id INTEGER PRIMARY KEY, retained INTEGER, removed INTEGER, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)')
  c.execute('CREATE TABLE IF NOT EXISTS family_fact_provenance (fact_id INTEGER PRIMARY KEY, review_status TEXT NOT NULL, origin TEXT NOT NULL)')
  ids=[x[0] for x in c.execute('SELECT family_id FROM family_profiles ORDER BY family_id LIMIT ?',(a.limit,))]
  for fid in ids:
   name=c.execute('SELECT name FROM families WHERE id=?',(fid,)).fetchone()[0]
   facts=c.execute('SELECT id,title,body,source_url FROM family_facts WHERE family_id=? ORDER BY position',(fid,)).fetchall()
   kept=[];removed=0;seen=set()
   for factid,title,body,url in facts:
    norm=re.sub(r'\W+','',body.casefold())
    if not quality(body) or norm in seen or not url or not url.startswith('https://'):
     c.execute('DELETE FROM family_fact_provenance WHERE fact_id=?',(factid,));c.execute('DELETE FROM family_facts WHERE id=?',(factid,));removed+=1;continue
    seen.add(norm);kept.append(factid)
    c.execute('INSERT INTO family_fact_provenance VALUES(?,?,?) ON CONFLICT(fact_id) DO NOTHING',(factid,'needs_review','automated_excerpt'))
   for title,body,url in PILOT.get(name,[]):
    if not any(x[0]==title and x[1]==body for x in c.execute('SELECT title,body FROM family_facts WHERE family_id=?',(fid,))):
     pos=c.execute('SELECT COALESCE(MAX(position),0)+1 FROM family_facts WHERE family_id=?',(fid,)).fetchone()[0]
     cur=c.execute('INSERT INTO family_facts(family_id,position,title,body,source_url) VALUES(?,?,?,?,?)',(fid,pos,title,body,url))
     c.execute('INSERT INTO family_fact_provenance VALUES(?,?,?)',(cur.lastrowid,'source_to_verify','editorial_pilot'))
     c.execute('INSERT OR IGNORE INTO family_sources(family_id,source_name,url) VALUES(?,?,?)',(fid,'Specialist reference (pilot)',url))
   c.execute('INSERT INTO family_fact_quality(family_id,retained,removed) VALUES(?,?,?) ON CONFLICT(family_id) DO UPDATE SET retained=excluded.retained,removed=excluded.removed,updated_at=CURRENT_TIMESTAMP',(fid,len(kept),removed))
   print(f'{name}: kept {len(kept)}, removed {removed}, pilot additions {len(PILOT.get(name,[]))}',flush=True)
  c.commit()
  print('Total fact cards:',c.execute('SELECT COUNT(*) FROM family_facts').fetchone()[0])
if __name__=='__main__':main()
