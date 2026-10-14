import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

BASE = 'https://api.inaturalist.org/v1'
DB = Path(__file__).with_name('inzicht_cache.sqlite3')
HEADERS = {'User-Agent': 'InzichtInNatuur/0.4 (educational biodiversity overview)'}
RANKS = {'Rijk': 'kingdom', 'Klasse': 'class', 'Orde': 'order'}
HIERARCHY = {'kingdom': 'Rijk', 'phylum': 'Stam', 'class': 'Klasse', 'order': 'Orde'}


def connection():
    con = sqlite3.connect(DB, timeout=30)
    con.execute('PRAGMA busy_timeout=30000')
    con.execute('CREATE TABLE IF NOT EXISTS family_data (id INTEGER PRIMARY KEY, counts_obs INTEGER, counts_species INTEGER, hierarchy TEXT, updated REAL)')
    con.execute('CREATE TABLE IF NOT EXISTS family_species (id INTEGER PRIMARY KEY, species INTEGER, hierarchy TEXT, updated REAL)')
    con.commit()
    return con


def api(path, params=None):
    last = None
    for attempt in range(4):
        try:
            r = requests.get(BASE + path, params=params or {}, headers=HEADERS, timeout=35)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'API niet bereikbaar: {path}: {last}')


@st.cache_data(ttl=86400, show_spinner=False)
def search_taxa(query, rank):
    return [x for x in api('/taxa/autocomplete', {'q': query, 'rank': rank, 'per_page': 30}).get('results', []) if x.get('rank') == rank]


@st.cache_data(ttl=86400, show_spinner=False)
def families_for(taxon_id):
    params = {'taxon_id': taxon_id, 'rank': 'family', 'per_page': 200}
    first = api('/taxa', {**params, 'page': 1})
    total = int(first.get('total_results', 0))
    items = list(first.get('results', []))
    for page in range(2, min((total + 199) // 200, 50) + 1):
        batch = api('/taxa', {**params, 'page': page}).get('results', [])
        if not batch:
            break
        items.extend(batch)
    unique = {int(x['id']): x for x in items if x.get('rank') == 'family' and x.get('is_active', True)}
    return list(unique.values()), total, len({int(x['id']) for x in items}) < total


def fetch_one(family, include_observations=False):
    """One taxonomy count request per family; reuse hierarchy already in list payload."""
    family_id = int(family['id'])
    ancestors = family.get('ancestors') or []
    hierarchy = {HIERARCHY[a['rank']]: a.get('name', '') for a in ancestors if isinstance(a, dict) and a.get('rank') in HIERARCHY}
    response = api('/taxa', {'taxon_id': family_id, 'rank': 'species', 'per_page': 1})
    species = response.get('total_results')
    if species is None:
        raise RuntimeError('Geen soortentotaal ontvangen')
    obs = None
    if include_observations:
        obs = api('/observations', {'taxon_id': family_id, 'per_page': 0}).get('total_results')
    return family_id, int(species), hierarchy, obs


@st.cache_resource
def job_registry():
    return {'lock': threading.Lock(), 'running': set(), 'errors': {}}


def background_job(key, families_to_fetch, include_observations):
    registry = job_registry()
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fetch_one, f, include_observations): int(f["id"]) for f in families_to_fetch}
            for future in as_completed(futures):
                family_id = futures[future]
                try:
                    tid, species, hierarchy, obs = future.result()
                    with connection() as con:
                        con.execute('INSERT OR REPLACE INTO family_species VALUES (?, ?, ?, ?)', (tid, species, json.dumps(hierarchy), time.time()))
                        if include_observations:
                            con.execute('UPDATE family_data SET counts_obs=? WHERE id=?', (obs, tid))
                            if con.execute('SELECT changes()').fetchone()[0] == 0:
                                con.execute('INSERT INTO family_data (id, counts_obs) VALUES (?, ?)', (tid, obs))
                except Exception as e:
                    with registry['lock']:
                        registry['errors'][family_id] = str(e)
    finally:
        with registry['lock']:
            registry['running'].discard(key)


def start_job(key, families_to_fetch, include_observations):
    registry = job_registry()
    with registry['lock']:
        if key in registry['running'] or not families_to_fetch:
            return
        registry['running'].add(key)
    threading.Thread(target=background_job, args=(key, families_to_fetch, include_observations), daemon=True).start()


def read_cached(ids, include_observations):
    if not ids:
        return {}
    result = {}
    with connection() as con:
        for start in range(0, len(ids), 400):
            batch = ids[start:start + 400]
            marks = ','.join('?' * len(batch))
            for tid, species, hierarchy, updated in con.execute('SELECT * FROM family_species WHERE id IN (' + marks + ')', batch):
                result[tid] = [species, json.loads(hierarchy or '{}'), None]
            if include_observations:
                for tid, obs in con.execute('SELECT id, counts_obs FROM family_data WHERE id IN (' + marks + ')', batch):
                    if tid in result:
                        result[tid][2] = obs
    return result


st.set_page_config(page_title='Inzicht in Natuur', page_icon='🌿', layout='wide')
st.title('🌿 Inzicht in Natuur')
st.caption('Wereldwijde taxonomie en waarnemingen op iNaturalist · tot familieniveau')
with st.sidebar:
    st.header('Selectie')
    level = st.radio('Kies niveau', list(RANKS), horizontal=True)
    rank = RANKS[level]
    query = st.text_input('Zoek taxon (wetenschappelijke naam)', value={'kingdom': 'Plantae', 'class': 'Aves', 'order': 'Lepidoptera'}[rank], key=rank)
    try:
        matches = search_taxa(query, rank) if len(query.strip()) >= 2 else []
    except Exception as e:
        st.error(f'Zoeken mislukt: {e}')
        st.stop()
    if not matches:
        st.info('Geen taxa gevonden.')
        st.stop()
    selected = st.selectbox('Taxon', matches, format_func=lambda x: f"{x['name']} · {x.get('preferred_common_name', '')} · ID {x['id']}")
    st.divider()
    st.caption('Soortenaantallen worden automatisch berekend. Waarnemingen alleen op ordeniveau. Resultaten worden lokaal gecachet.')

st.subheader(selected['name'])
st.write(f"**Rang:** {level} · **iNaturalist taxon-ID:** {selected['id']}")
try:
    with st.spinner('Families ophalen…'):
        families, total, truncated = families_for(selected['id'])
except Exception as e:
    st.error(f'Kan families niet ophalen: {e}')
    st.stop()
if truncated:
    st.warning('De iNaturalist-API heeft mogelijk niet alle families teruggegeven. Dit overzicht kan onvolledig zijn.')
if not families:
    st.warning('Geen families gevonden.')
    st.stop()

ids = [int(f['id']) for f in families]
include_observations = rank == 'order'
key = str(selected['id']) + ('_order' if include_observations else '_species')
st.metric('Families gevonden', len(ids))
st.caption('Volgorde: rijk → stam → klasse → orde → familie. Binnen een orde alfabetisch; iNaturalist geeft geen betrouwbare fylogenetische volgorde.')

@st.fragment(run_every='5s')
def results_view():
    cached = read_cached(ids, include_observations)
    missing = [i for i in ids if i not in cached or (include_observations and cached[i][2] is None)]
    registry = job_registry()
    with registry['lock']:
        running = key in registry['running']
        errors = {i: registry['errors'][i] for i in ids if i in registry['errors']}
    if missing and not running:
        # Avoid continuously retrying failed requests on each refresh.
        retryable = [i for i in missing if i not in errors]
        if retryable:
            start_job(key, [f for f in families if int(f["id"]) in set(retryable)], include_observations)
            running = True
    complete = len(ids) - len(missing)
    st.subheader('Automatische verwerking')
    st.progress(complete / len(ids), text=f'{complete} van {len(ids)} families verwerkt')
    if running:
        st.caption('De berekening loopt op de achtergrond. Je kunt het overzicht blijven gebruiken; het ververst elke 5 seconden.')
    elif not missing:
        st.success('Alle families zijn verwerkt. De resultaten zijn lokaal opgeslagen.')
    if errors:
        st.warning(f'{len(errors)} families konden niet worden opgehaald. Probeer ze opnieuw wanneer de API weer beschikbaar is.')
        if st.button('Mislukte families opnieuw proberen'):
            with registry['lock']:
                for i in errors:
                    registry['errors'].pop(i, None)
            st.rerun(scope='fragment')
    rows = []
    for f in families:
        tid = int(f['id'])
        species, h, obs = cached.get(tid, (None, {}, None))
        if not h:
            h = {HIERARCHY[a['rank']]: a.get('name', '') for a in (f.get('ancestors') or []) if isinstance(a, dict) and a.get('rank') in HIERARCHY}
        rows.append({'Taxon ID': tid, **{name: h.get(name, '') for name in HIERARCHY.values()}, 'Familie': f['name'], 'Engelse naam': f.get('preferred_common_name', ''), 'Aantal soorten': species, **({'Waarnemingen': obs} if include_observations else {}), 'Kenmerk 1': '', 'Kenmerk 2': '', 'Kenmerk 3': ''})
    df = pd.DataFrame(rows).sort_values(['Rijk', 'Stam', 'Klasse', 'Orde', 'Familie'], kind='stable')
    st.subheader('Familieoverzicht')
    st.dataframe(df.drop(columns='Taxon ID'), hide_index=True, use_container_width=True, height=580)
    st.download_button('Download CSV', df.to_csv(index=False).encode('utf-8-sig'), file_name=f"inzicht_in_natuur_{selected['name']}.csv", mime='text/csv')
    st.caption('Aantal soorten = soort-taxa die iNaturalist in de familie indexeert; dit is niet noodzakelijk het volledige aantal wetenschappelijk beschreven soorten. Waarnemingen verschijnen alleen bij selectie van een orde. Familiekenmerken volgen later.')

results_view()
