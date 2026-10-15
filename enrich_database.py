"""Enrich an existing family snapshot with ancestry and optional species totals.

Run against a pre-existing families.sqlite3. Re-running is safe.
"""
import argparse
import sqlite3
import time
from pathlib import Path
import requests

DB = Path(__file__).with_name('families.sqlite3')
API = 'https://api.inaturalist.org/v1'
s = requests.Session()
s.headers['User-Agent'] = 'InzichtInNatuur/0.8 (family taxonomy snapshot)'

def get(path, params=None):
    for attempt in range(6):
        try:
            r = s.get(API + path, params=params, timeout=75)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(90, 3 * 2 ** attempt)); continue
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 5: raise
            time.sleep(min(90, 3 * 2 ** attempt))
    raise RuntimeError(f'API unavailable: {path}')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--count-species', action='store_true')
    args = p.parse_args()
    if not DB.exists():
        raise SystemExit('Missing families.sqlite3: upload the existing snapshot first')
    with sqlite3.connect(DB) as db:
        rows = db.execute('SELECT id FROM families WHERE kingdom IS NULL OR kingdom="" OR phylum IS NULL OR class_name IS NULL OR order_name IS NULL').fetchall()
        ids = [str(r[0]) for r in rows]
        print(f'Enriching ancestry for {len(ids)} families', flush=True)
        for pos in range(0, len(ids), 30):
            chunk = ids[pos:pos+30]
            data = get('/taxa/' + ','.join(chunk))
            for f in data.get('results', []):
                ancestor = {a.get('rank'): a.get('name') for a in f.get('ancestors', []) if isinstance(a, dict)}
                db.execute('''UPDATE families SET kingdom=COALESCE(?,kingdom), phylum=COALESCE(?,phylum), class_name=COALESCE(?,class_name), order_name=COALESCE(?,order_name), common_name=COALESCE(common_name,?) WHERE id=?''',
                           (ancestor.get('kingdom'), ancestor.get('phylum'), ancestor.get('class'), ancestor.get('order'), f.get('preferred_common_name'), f['id']))
            db.commit()
            if pos % 300 == 0: print(f'Ancestry {min(pos+30,len(ids))}/{len(ids)}', flush=True)
            time.sleep(0.4)
        if args.count_species:
            ids = [r[0] for r in db.execute('SELECT id FROM families WHERE species_count IS NULL')]
            print(f'Counting species for {len(ids)} families (this can take hours)', flush=True)
            for i, taxon_id in enumerate(ids, 1):
                try:
                    data = get('/taxa', {'taxon_id': taxon_id, 'rank': 'species', 'is_active': 'true', 'per_page': 1})
                    if 'total_results' in data:
                        db.execute('UPDATE families SET species_count=? WHERE id=?', (int(data['total_results']), taxon_id))
                except requests.RequestException as e:
                    print(f'Failed count {taxon_id}: {e}', flush=True)
                if i % 25 == 0:
                    db.commit(); print(f'Species {i}/{len(ids)}', flush=True)
                time.sleep(0.4)
            db.commit()
        n = db.execute('SELECT COUNT(*) FROM families').fetchone()[0]
        populated = db.execute('SELECT COUNT(*) FROM families WHERE kingdom IS NOT NULL').fetchone()[0]
        print(f'Database: {n} families, {populated} with kingdom', flush=True)
        if populated < n * .9:
            raise SystemExit('Validation failed: fewer than 90% families have kingdom')

if __name__ == '__main__': main()
