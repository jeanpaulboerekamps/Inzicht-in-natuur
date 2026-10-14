import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
import streamlit as st

BASE = 'https://api.inaturalist.org/v1'
S = requests.Session()
S.headers.update({'User-Agent':'InzichtInNatuur/0.1 (educational Streamlit dashboard)'})

st.set_page_config(page_title='Inzicht in Natuur', layout='wide', page_icon='🌿')
st.title('🌿 Inzicht in Natuur')
st.caption('Wereldwijde taxonomie en waarnemingen op iNaturalist · uitwerking tot familieniveau')

@st.cache_data(ttl=86400, show_spinner=False)
def api(path, params=None):
    r = requests.get(BASE + path, params=params or {}, headers={'User-Agent':'InzichtInNatuur/0.1'}, timeout=35)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=86400, show_spinner=False)
def search_taxa(query, rank):
    data = api('/taxa/autocomplete', {'q':query,'rank':rank,'per_page':30})
    return [x for x in data.get('results',[]) if x.get('rank')==rank]

@st.cache_data(ttl=86400, show_spinner=False)
def descendants(taxon_id):
    """Query families directly, avoiding the nonexistent /taxa/{id}/descendants route.

    iNaturalist /taxa supports taxon_id (descendant filter) and rank.
    """
    params = {'taxon_id': taxon_id, 'rank': 'family', 'per_page': 200}
    first = api('/taxa', {**params, 'page': 1})
    total = int(first.get('total_results', 0))
    items = list(first.get('results', []))
    page_size = 200
    # iNaturalist paginated API endpoints commonly limit deep pagination.
    max_pages = 50
    pages = min((total + page_size - 1) // page_size, max_pages)
    for page in range(2, pages + 1):
        batch = api('/taxa', {**params, 'page': page}).get('results', [])
        if not batch:
            break
        items.extend(batch)
    unique = {int(item['id']): item for item in items}
    return list(unique.values()), total, len(unique) < total

@st.cache_data(ttl=604800, show_spinner=False)
def details(taxon_id):
    data = api(f'/taxa/{taxon_id}')
    return (data.get('results') or [{}])[0]

@st.cache_data(ttl=86400, show_spinner=False)
def observation_count(taxon_id):
    return api('/observations', {'taxon_id':taxon_id,'per_page':0,'page':1}).get('total_results')

@st.cache_data(ttl=86400, show_spinner=False)
def observed_species_count(taxon_id):
    # Species count from observation/species_counts is not a count of all described species.
    return api('/observations/species_counts', {'taxon_id':taxon_id,'per_page':0,'page':1}).get('total_results')

RANKS = {'Rijk':'kingdom','Klasse':'class','Orde':'order'}
with st.sidebar:
    st.header('Selectie')
    level = st.radio('Kies niveau', list(RANKS), horizontal=True)
    rank = RANKS[level]
    initial = {'kingdom':'Plantae','class':'Aves','order':'Lepidoptera'}[rank]
    q = st.text_input('Zoek taxon (wetenschappelijke naam)',value=initial, key=rank)
    matches = search_taxa(q,rank) if len(q.strip())>=2 else []
    if not matches:
        st.info('Geen passende taxa gevonden. Probeer een andere naam.')
        st.stop()
    selected = st.selectbox('Taxon',matches,format_func=lambda x: f"{x['name']} · {x.get('preferred_common_name','')} · ID {x['id']}")
    st.divider()
    st.caption('De taxonomie en waarnemingen komen live uit de openbare iNaturalist-API. Resultaten worden tijdelijk gecachet.')

st.subheader(selected['name'])
st.write(f"**Rang:** {level} · **iNaturalist taxon-ID:** {selected['id']}")
try:
    with st.spinner('Taxonomische afstammelingen ophalen…'):
        nodes,total,truncated = descendants(selected['id'])
except Exception as e:
    st.error(f'Kan de taxonomie niet ophalen: {e}')
    st.stop()

families = [n for n in nodes if n.get('rank')=='family' and n.get('is_active',True)]
if selected.get('rank')=='family': families=[selected]
if truncated:
    st.warning('Niet alle families konden worden opgehaald. Kies een kleinere groep (klasse of orde) voor een volledig overzicht.')
if not families:
    st.warning('Geen families gevonden voor dit taxon. Probeer een andere klasse of orde.')
    st.stop()

# Keep taxonomic hierarchy rather than sorting by observation count or alphabetically.
# iNaturalist returns descendant records, but does not guarantee a phylogenetic ordering among sibling taxa.
by_id={x['id']:x for x in nodes}
by_id[selected['id']]=selected

def hierarchy(f):
    lineage=[]
    for a in f.get('listed_taxa',[]): pass
    for a in f.get('ancestors',[]):
        if a.get('rank') in ('kingdom','phylum','class','order'):
            lineage.append((a.get('rank'),a.get('name')))
    cur=f
    seen=set()
    while cur.get('parent_id') in by_id and cur['parent_id'] not in seen:
        seen.add(cur['parent_id'])
        cur=by_id[cur['parent_id']]
        if cur.get('rank') in ('kingdom','phylum','class','order'):
            lineage.append((cur['rank'],cur['name']))
    return {k:v for k,v in reversed(lineage)}

rows=[]
for f in families:
    h=hierarchy(f)
    rows.append({'Taxon ID':f['id'],'Rijk':h.get('kingdom',''),'Stam':h.get('phylum',''),'Klasse':h.get('class',''),'Orde':h.get('order',''),'Familie':f['name'],'Engelse naam':f.get('preferred_common_name',''),'Waarnemingen':None,'Waargenomen soorten':None,'Kenmerk 1':'','Kenmerk 2':'','Kenmerk 3':''})

df=pd.DataFrame(rows)
# Alphabetical tie-break is explicit; the API does not provide a reliable phylogenetic family order.
df=df.sort_values(['Rijk','Stam','Klasse','Orde','Familie'],kind='stable').reset_index(drop=True)
st.metric('Families gevonden',len(df))
st.info('Volgorde: taxonomische hiërarchie (rijk → stam → klasse → orde → familie), alfabetisch binnen dezelfde orde. iNaturalist levert geen eenduidige fylogenetische volgorde van families.')

st.markdown('#### Waarnemingen en soorten')
st.caption('Waarnemingen = alle observaties binnen de familie; waargenomen soorten = soorten met ten minste één observatie. Dit laatste is NIET het totale aantal bestaande soorten.')
limit=st.number_input('Aantal families waarvoor live aantallen worden opgehaald',min_value=1,max_value=len(df),value=min(20,len(df)))
if st.button('Haal aantallen op',type='primary'):
    bar=st.progress(0)
    selected_ids=df['Taxon ID'].head(limit).tolist()
    def get_counts(tid):
        result={}
        for fn,name in [(observation_count,'Waarnemingen'),(observed_species_count,'Waargenomen soorten')]:
            try: result[name]=fn(tid)
            except Exception: result[name]=None
        return tid,result
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(get_counts,i) for i in selected_ids]
        for i,future in enumerate(as_completed(futures)):
            tid,counts=future.result()
            for name,value in counts.items():
                df.loc[df['Taxon ID']==tid,name]=value
            bar.progress((i+1)/len(futures))
    st.session_state['counts']={int(r['Taxon ID']):{'Waarnemingen':r['Waarnemingen'],'Waargenomen soorten':r['Waargenomen soorten']} for _,r in df.iterrows() if pd.notna(r['Waarnemingen']) or pd.notna(r['Waargenomen soorten'])}
if 'counts' in st.session_state:
    for tid,vals in st.session_state['counts'].items():
        for name,val in vals.items():
            df.loc[df['Taxon ID']==tid,name]=val

st.markdown('#### Familieoverzicht')
st.dataframe(df.drop(columns='Taxon ID'),hide_index=True,use_container_width=True,height=580)
st.download_button('Download CSV',df.to_csv(index=False).encode('utf-8-sig'),file_name=f"inzicht_in_natuur_{selected['name']}.csv",mime='text/csv')
st.caption('Herkenningskenmerken zijn nog niet gevuld: iNaturalist biedt geen gestructureerde bron met drie betrouwbare diagnostische kenmerken per familie. Automatisch gegenereerde kenmerken zonder broncontrole zouden misleidend zijn.')
st.caption(f'Families via iNaturalist /taxa: {len(families)} van {total} gerapporteerde resultaten.' + (' De lijst is onvolledig.' if truncated else ''))
