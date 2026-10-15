"""Build a resumable snapshot of active iNaturalist families.

The iNaturalist taxa endpoint has deep-pagination limits. Query smaller
subtrees instead of requesting page 51+ of the worldwide family list.
"""
import argparse
import os
import sqlite3
import time
from pathlib import Path

import requests

BASE = 'https://api.inaturalist.org/v1'
DB = Path(__file__).with_name('families.sqlite3')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'InzichtInNatuur/0.7 (educational taxonomy snapshot)'})
PAGE_SIZE = 200
MAX_PAGE = 49  # split before the 10,000-record deep-pagination boundary


def api(path, params):
    for retry in range(6):
        try:
            response = SESSION.get(BASE + path, params=params, timeout=60)
            if response.status_code in (403, 429, 500, 502, 503, 504):
                delay = min(120, 5 * (2 ** retry))
                print(f'HTTP {response.status_code}: {params}; retry in {delay}s', flush=True)
                if retry == 5:
                    response.raise_for_status()
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError):
            if retry == 5:
                raise
            time.sleep(min(120, 5 * (2 ** retry)))
    raise RuntimeError(f'API failed: {path} {params}')


def init_db(con):
    con.execute('''CREATE TABLE IF NOT EXISTS families (
        id INTEGER PRIMARY KEY, kingdom TEXT, phylum TEXT, class_name TEXT,
        order_name TEXT, name TEXT, common_name TEXT, species_count INTEGER,
        feature1 TEXT, feature2 TEXT, feature3 TEXT, source TEXT)''')
    con.execute('''CREATE TABLE IF NOT EXISTS completed_subtrees (
        taxon_id INTEGER PRIMARY KEY, completed_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    con.commit()


def save_family(con, f):
    if f.get('rank') != 'family' or not f.get('is_active', True):
        return
    ancestors = {a.get('rank'): a.get('name') for a in f.get('ancestors', []) if isinstance(a, dict)}
    con.execute('''INSERT INTO families
        (id,kingdom,phylum,class_name,order_name,name,common_name,source)
        VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        kingdom=excluded.kingdom, phylum=excluded.phylum,
        class_name=excluded.class_name, order_name=excluded.order_name,
        name=excluded.name, common_name=excluded.common_name,
        source=excluded.source''',
        (f['id'], ancestors.get('kingdom'), ancestors.get('phylum'),
         ancestors.get('class'), ancestors.get('order'), f.get('name'),
         f.get('preferred_common_name'), 'iNaturalist taxa API'))


def children(taxon_id):
    """Immediate active child taxa; use the taxon detail children endpoint."""
    data = api(f'/taxa/{taxon_id}', {})
    results = data.get('results', [])
    if not results:
        raise RuntimeError(f'No details for taxon {taxon_id}')
    return [c for c in results[0].get('children', []) if c.get('is_active', True)]


def collect_subtree(con, taxon_id, depth=0):
    if con.execute('SELECT 1 FROM completed_subtrees WHERE taxon_id=?', (taxon_id,)).fetchone():
        print(f'Skip completed subtree {taxon_id}', flush=True)
        return
    if depth > 20:
        raise RuntimeError(f'Taxonomy nesting too deep at {taxon_id}')
    params = {'rank': 'family', 'is_active': 'true', 'taxon_id': taxon_id, 'per_page': PAGE_SIZE}
    first = api('/taxa', {**params, 'page': 1})
    total = first.get('total_results', 0)
    if total > MAX_PAGE * PAGE_SIZE:
        kids = children(taxon_id)
        if not kids:
            raise RuntimeError(f'{total} families under {taxon_id}, but no children to split into')
        print(f'Split taxon {taxon_id} ({total} families) into {len(kids)} children', flush=True)
        for child in kids:
            collect_subtree(con, child['id'], depth + 1)
    else:
        for page in range(1, (total + PAGE_SIZE - 1) // PAGE_SIZE + 1):
            data = first if page == 1 else api('/taxa', {**params, 'page': page})
            for f in data.get('results', []):
                save_family(con, f)
            con.commit()
            if page % 10 == 0:
                print(f'Taxon {taxon_id}: page {page}, {total} total', flush=True)
            time.sleep(0.6)
    con.execute('INSERT OR IGNORE INTO completed_subtrees(taxon_id) VALUES (?)', (taxon_id,))
    con.commit()
    print(f'Completed subtree {taxon_id}; stored {con.execute("SELECT COUNT(*) FROM families").fetchone()[0]} families', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count-species', action='store_true')
    args = parser.parse_args()
    with sqlite3.connect(DB) as con:
        init_db(con)
        # Discover kingdoms without relying on a single worldwide family query.
        data = api('/taxa', {'rank': 'kingdom', 'is_active': 'true', 'per_page': 200})
        kingdoms = data.get('results', [])
        if not kingdoms:
            raise RuntimeError('No kingdoms returned')
        for k in kingdoms:
            print(f'Kingdom: {k.get("name")} ({k["id"]})', flush=True)
            collect_subtree(con, k['id'])
        if args.count_species:
            rows = con.execute('SELECT id FROM families WHERE species_count IS NULL ORDER BY id').fetchall()
            for i, (taxon_id,) in enumerate(rows, 1):
                try:
                    result = api('/taxa', {'taxon_id': taxon_id, 'rank': 'species', 'per_page': 1})
                    count = result.get('total_results')
                    if count is not None:
                        con.execute('UPDATE families SET species_count=? WHERE id=?', (int(count), taxon_id))
                except requests.RequestException as exc:
                    print(f'Species count failed for {taxon_id}: {exc}', flush=True)
                if i % 25 == 0:
                    con.commit()
                    print(f'Species counts: {i}/{len(rows)}', flush=True)
                time.sleep(0.6)
        con.commit()
        print('Database ready:', DB, flush=True)


if __name__ == '__main__':
    main()
