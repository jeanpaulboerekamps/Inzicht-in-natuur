"""Build conservative English profiles from already collected evidence, without AI."""
import argparse, re, sqlite3
from urllib.parse import urlparse

def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()

def sentences(s):
    return re.split(r'(?<=[.!?])\s+(?=[A-Z])', clean(s))

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=20);p.add_argument('--retry',action='store_true');args=p.parse_args()
    c=sqlite3.connect('families.sqlite3');c.row_factory=sqlite3.Row
    families=c.execute('SELECT id,name FROM families WHERE id IN (SELECT family_id FROM family_evidence) ORDER BY id LIMIT ?', (args.limit,)).fetchall()
    for f in families:
        old=c.execute('SELECT status FROM family_profiles WHERE family_id=?',(f['id'],)).fetchone()
        if old and old['status'] in ('reviewed','draft_ai'):
            print(f"{f['name']}: preserving existing curated profile");continue
        if old and old['status']=='draft_english_rules' and not args.retry:continue
        evidence=c.execute('SELECT e.* FROM family_evidence e LEFT JOIN family_evidence_validation v ON v.evidence_id=e.id WHERE e.family_id=? AND COALESCE(v.decision,\'accept\') != \'reject\' ORDER BY CASE WHEN lower(e.source_name) LIKE \'%wikipedia%\' THEN 0 ELSE 1 END,e.id',(f['id'],)).fetchall()
        usable=[]
        for e in evidence:
            if e['language'] not in ('en','eng',None,''):continue
            t=clean(e['text']);name=f['name']
            if not t or not re.search(r'\b'+re.escape(name)+r'\b',t,re.I):continue
            if len(t)<65:continue
            if not urlparse(e['source_url']).scheme.startswith('http'):continue
            if not (e['evidence_type'] in ('summary','description','extract','intro','article') or 'wikipedia' in e['source_name'].lower()):continue
            usable.append(e)
        if not usable:
            print(f"{f['name']}: no suitable English narrative source");continue
        best=usable[0];parts=sentences(best['text']);intro=' '.join(parts[:3])[:650]
        if len(intro)<50:continue
        c.execute("INSERT INTO family_profiles(family_id,introduction,language,status,updated_at) VALUES(?,?,?,'draft_english_rules',CURRENT_TIMESTAMP) ON CONFLICT(family_id) DO UPDATE SET introduction=excluded.introduction,language=excluded.language,status=excluded.status,updated_at=CURRENT_TIMESTAMP",(f['id'],intro,'en'))
        c.execute('DELETE FROM family_facts WHERE family_id=?',(f['id'],))
        c.execute('INSERT OR IGNORE INTO family_sources(family_id,source_name,url) VALUES(?,?,?)',(f['id'],best['source_name'],best['source_url']))
        print(f"{f['name']}: English introduction from {best['source_name']}; no unsupported facts invented")
    c.commit();c.close()
if __name__=='__main__':main()
