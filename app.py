from pathlib import Path
import sqlite3
import pandas as pd
import requests
import streamlit as st
DB=Path(__file__).with_name('families.sqlite3')
st.set_page_config(page_title='Inzicht in natuur',layout='wide')
st.title('🌿 Inzicht in natuur')
st.caption('Taxonomic encyclopedia of families')
if not DB.exists():st.error('families.sqlite3 ontbreekt');st.stop()
@st.cache_data(show_spinner=False)
def load(mtime):
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as c:
        f=pd.read_sql_query('SELECT id,kingdom,phylum,class_name,order_name,name,common_name,species_count FROM families',c)
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        profiles=pd.read_sql_query('SELECT * FROM family_profiles',c) if 'family_profiles' in tables else pd.DataFrame()
        facts=pd.read_sql_query('SELECT * FROM family_facts ORDER BY position',c) if 'family_facts' in tables else pd.DataFrame()
        sources=pd.read_sql_query('SELECT * FROM family_sources',c) if 'family_sources' in tables else pd.DataFrame()
        evidence=pd.read_sql_query('SELECT * FROM family_evidence ORDER BY source_name',c) if 'family_evidence' in tables else pd.DataFrame()
        return f,profiles,facts,sources,evidence
f,profiles,facts,sources,evidence=load(DB.stat().st_mtime_ns)
# Images are resolved by exact scientific taxon name, not a free-text image search.
# iNaturalist taxon photos are supplied with a taxon ID and licensing metadata.
@st.cache_data(ttl=604800,show_spinner=False)
def taxon_photo(scientific_name):
    try:
        response=requests.get('https://api.inaturalist.org/v1/taxa/autocomplete',
            params={'q':scientific_name,'per_page':20},timeout=12,
            headers={'User-Agent':'InzichtInNatuur/1.0 (educational project)'})
        response.raise_for_status()
        matches=[t for t in response.json().get('results',[]) if t.get('name','').lower()==scientific_name.lower() and t.get('rank')=='species']
        if not matches:return None
        t=matches[0]; photo=t.get('default_photo') or {}
        url=photo.get('medium_url') or photo.get('url')
        if not url:return None
        # iNaturalist records the license; attribution links to the exact taxon.
        return (url,'https://www.inaturalist.org/taxa/'+str(t['id']),photo.get('attribution') or 'iNaturalist')
    except (requests.RequestException,ValueError,KeyError,TypeError):
        return None

# Taxonomically targeted images: no generic Commons search that can return another family.
HEADER_TAXA=[('Geometra papilionaria','Groene spanner'),('Biston betularia','Berkenspanner'),('Operophtera brumata','Kleine wintervlinder')]
FACT_TAXA={
 'Een beroemd voorbeeld van evolutie':'Biston betularia',
 'Smaragdgroene spanners':'Geometra papilionaria',
 'Vrouwtjes zonder vliegvermogen':'Operophtera brumata',
 'Tropische specialisten op waardplanten':'Eois pallidicosta',
}

def render_taxon_photo(name,caption=None):
    found=taxon_photo(name)
    if not found:return False
    url,source,credit=found
    st.image(url,use_container_width=True)
    st.caption(f'{caption or name} · [Foto en naamsvermelding]({source})')
    return True

with st.sidebar:
    with st.expander('Over bronnen en betrouwbaarheid'):
        st.write('Familieprofielen zijn redactioneel samengesteld uit biologische bronnen. '
                 'De teksten kunnen onvolkomenheden bevatten en zijn niet allemaal onafhankelijk per bewering geverifieerd. '
                 'Raadpleeg bij twijfel de vermelde oorspronkelijke bronnen. '
                 'Foto’s worden aan de hand van exacte wetenschappelijke soortnamen opgehaald; '
                 'als een passende foto ontbreekt, tonen we geen willekeurige vervanging.')

st.caption(f'{len(f):,} families · {len(profiles):,} onderzoeksprofielen')
with st.sidebar:
    st.header('Filters')
    q=st.text_input('Zoek familie of taxonomie')
    options=[('kingdom','Rijk'),('phylum','Stam'),('class_name','Klasse'),('order_name','Orde')]
    filtered=f.copy()
    for field,label in options:
        vals=sorted(filtered[field].dropna().astype(str).unique())
        selected=st.selectbox(label,['Alle']+vals)
        if selected!='Alle':filtered=filtered[filtered[field]==selected]
    only=st.checkbox('Alleen families met profiel')
    if only:filtered=filtered[filtered.id.isin(profiles.family_id)] if not profiles.empty else filtered.iloc[0:0]
if q:
    mask=filtered[['kingdom','phylum','class_name','order_name','name','common_name']].fillna('').astype(str).apply(lambda s:s.str.contains(q,case=False,regex=False)).any(axis=1)
    filtered=filtered[mask]
order=st.radio('Sortering',['Taxonomisch','Meeste soorten','Alfabetisch'],horizontal=True)
if order=='Meeste soorten':filtered=filtered.sort_values('species_count',ascending=False,na_position='last')
elif order=='Alfabetisch':filtered=filtered.sort_values('name')
else:filtered=filtered.sort_values(['kingdom','phylum','class_name','order_name','name'],na_position='last')
st.subheader(f'{len(filtered):,} families')
view=filtered[['kingdom','phylum','class_name','order_name','name']].rename(columns={'kingdom':'Rijk','phylum':'Stam','class_name':'Klasse','order_name':'Orde','name':'Familie'})
event=st.dataframe(view,hide_index=True,use_container_width=True,height=520,on_select='rerun',selection_mode='single-row',key='family_table')
if event.selection.rows:
    rec=filtered.iloc[event.selection.rows[0]]
    with st.container(border=True):
        st.header(rec['name'])
        if rec['name']=='Geometridae':
            photo_cols=st.columns(3,gap='small')
            for col,(species,label) in zip(photo_cols,HEADER_TAXA):
                with col:
                    render_taxon_photo(species,label)
        if pd.notna(rec.common_name):st.caption(rec.common_name)
        st.caption(' › '.join(str(rec[k]) for k in ['kingdom','phylum','class_name','order_name'] if pd.notna(rec[k])))
        a,b=st.columns(2)
        a.metric('Soorten in iNaturalist',f'{int(rec.species_count):,}' if pd.notna(rec.species_count) else 'Onbekend')
        b.metric('iNaturalist taxon-ID',str(rec.id))
        st.caption('Waarnemingsaantallen zijn niet aanwezig in de aangeleverde database.')
        prof=profiles[profiles.family_id==rec.id] if not profiles.empty else pd.DataFrame()
        if prof.empty:st.info('Voor deze familie is nog geen encyclopedisch profiel onderzocht.')
        else:
            r=prof.iloc[0]
            st.subheader('Introductie')
            intro=r.introduction if pd.notna(r.introduction) and r.introduction else 'Nog geen introductie beschikbaar.'
            for paragraph in str(intro).split('\n\n'):
                if paragraph.strip():st.markdown(paragraph.strip())
            # Onderzoeksstatus wordt intern bijgehouden
            ff=facts[facts.family_id==rec.id] if not facts.empty else pd.DataFrame()
            if not ff.empty:
                st.subheader('Bijzonderheden')
                for _,fact in ff.iterrows():
                    with st.container(border=True):
                        if rec['name']=='Geometridae' and fact.title in FACT_TAXA:
                            left,right=st.columns([1,3],gap='medium')
                            with left:
                                species=FACT_TAXA.get(fact.title)
                                if species:render_taxon_photo(species)
                                # For caterpillar-specific facts, do not show an adult moth as illustration.
                            with right:
                                st.markdown(f'#### {fact.title}')
                                st.write(fact.body)
                                if pd.notna(fact.source_url) and fact.source_url:
                                    st.markdown(f'[Meer lezen / achtergrondbron]({fact.source_url})')
                        else:
                            st.markdown(f'#### {fact.title}')
                            st.write(fact.body)
                            if pd.notna(fact.source_url) and fact.source_url:
                                st.markdown(f'[Meer lezen / achtergrondbron]({fact.source_url})')
            # Oude automatisch verzamelde fragmenten worden niet op de publieksprofielpagina getoond.
            ss=sources[sources.family_id==rec.id] if not sources.empty else pd.DataFrame()
            if not ss.empty:
                st.subheader('Bronnen')
                for _,s in ss.iterrows():st.markdown(f'- [{s.source_name}]({s.url})')
else:st.info('Klik op een familie in de tabel om het profiel te openen.')
