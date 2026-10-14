"""Eenmalige GitHub Actions builder; netwerk nodig. Bewaart eerder gecontroleerde kenmerken."""
import argparse
import sqlite3
import time
from pathlib import Path
import requests

BASE = 'https://api.inaturalist.org/v1'
DB = Path(__file__).with_name('families.sqlite3')
S = requests.Session()
S.headers.update({'User-Agent': 'InzichtInNatuur/0.6 (taxonomic educational snapshot)'})

def api(path, params):
    for retry in range(7):
        try:
            r = S.get(BASE + path, params=params, timeout=50)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 3 * 2**retry))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if retry == 6:
                raise
            time.sleep(min(60, 3 * 2**retry))
    raise RuntimeError(path)

def pages(params):
    page = 1
    while True:
        data = api('/taxa', {**params, 'page': page, 'per_page': 200})
        results = data.get('results', [])
        if not results:
            break
        yield from results
        if page * 200 >= data.get('total_results', 0):
            break
        page += 1
        time.sleep(.35)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count-species', action='store_true', help='Langzaam: 1 API-request per familie')
    args = parser.parse_args()
    with sqlite3.connect(DB) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS families (
          id INTEGER PRIMARY KEY, kingdom TEXT, phylum TEXT, class_name TEXT,
          order_name TEXT, name TEXT, common_name TEXT, species_count INTEGER,
          feature1 TEXT, feature2 TEXT, feature3 TEXT, source TEXT)''')
        con.commit()
        # Rank=family zonder taxon_id: alle actieve families over alle rijken.
        families = {}
        for f in pages({'rank': 'family', 'is_active': 'true'}):
            if f.get('rank') == 'family' and f.get('is_active', True):
                families[f['id']] = f
        print(f'{len(families)} families gevonden', flush=True)
        for i, f in enumerate(families.values(), 1):
            ancestor = {a.get('rank'): a.get('name') for a in f.get('ancestors', []) if isinstance(a, dict)}
            old = con.execute('SELECT species_count FROM families WHERE id=?', (f['id'],)).fetchone()
            species = old[0] if old else None
            if args.count_species and species is None:
                try:
                    species = int(api('/taxa', {'taxon_id': f['id'], 'rank': 'species', 'per_page': 1}).get('total_results'))
                except (ValueError, TypeError, requests.RequestException) as exc:
                    print('Telling mislukt:', f['id'], exc, flush=True)
                time.sleep(.35)
            con.execute('''INSERT INTO families (id,kingdom,phylum,class_name,order_name,name,common_name,species_count,source)
              VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              kingdom=excluded.kingdom,phylum=excluded.phylum,class_name=excluded.class_name,
              order_name=excluded.order_name,name=excluded.name,common_name=excluded.common_name,
              species_count=COALESCE(families.species_count,excluded.species_count),source=excluded.source''',
              (f['id'], ancestor.get('kingdom'), ancestor.get('phylum'), ancestor.get('class'), ancestor.get('order'),
               f.get('name'), f.get('preferred_common_name'), species, 'iNaturalist taxa API'))
            if i % 50 == 0:
                con.commit()
                print(f'{i}/{len(families)} opgeslagen', flush=True)
        con.commit()
        print('Database klaar:', DB, flush=True)
if __name__ == '__main__':
    main()
