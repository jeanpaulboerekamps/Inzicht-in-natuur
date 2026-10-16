from pathlib import Path
import sqlite3
import pandas as pd
import streamlit as st
DB = Path(__file__).with_name('families.sqlite3')
st.set_page_config(page_title='Inzicht in Natuur V13',layout='wide')
st.title('🌿 Inzicht in Natuur')
st.caption('Taxonomic family encyclopedia · V13 quality pilot · offline SQLite snapshot')
if not DB.exists():
    st.error('families.sqlite3 ontbreekt.'); st.stop()
@st.cache_data(show_spinner=False)
def load(mtime):
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as con:
        return pd.read_sql_query("""SELECT f.kingdom AS Kingdom, f.phylum AS Phylum, f.class_name AS Class,
          f.order_name AS `Order`, f.name AS Family, f.common_name AS `English name`,
          f.species_count AS Species, f.feature1 AS `Feature 1`, f.feature2 AS `Feature 2`,
          f.feature3 AS `Feature 3`, q.status AS `Feature status`, q.exceptions_note AS `Exceptions`,
          q.source_reference AS `Verified source`, f.id AS `iNaturalist ID`
          FROM families f LEFT JOIN feature_quality_review q ON f.id=q.family_id""",con)
df=load(DB.stat().st_mtime_ns)
a,b,c=st.columns(3)
a.metric('Families',f'{len(df):,}')
b.metric('Species counts',f'{df.Species.notna().sum():,}')
c.metric('Feature drafts',f'{df["Feature 1"].notna().sum():,}')
st.warning('The 12 feature sets are provisional drafts, not individually source-verified diagnoses. Do not treat them as definitive identification keys.')
with st.sidebar:
    st.header('Filters')
    search=st.text_input('Search family, taxonomy and features')
    for col in ['Kingdom','Phylum','Class','Order']:
        opts=sorted(str(x) for x in df[col].dropna().unique() if str(x).strip())
        selected=st.selectbox(col,['All']+opts)
        if selected!='All': df=df[df[col]==selected]
    only=st.checkbox('Only families with draft features')
if only: df=df[df['Feature 1'].notna()]
if search:
    cols=['Kingdom','Phylum','Class','Order','Family','English name','Feature 1','Feature 2','Feature 3']
    df=df[df[cols].fillna('').astype(str).apply(lambda s:s.str.contains(search,case=False,regex=False)).any(axis=1)]
mode=st.radio('Sort',['Taxonomic','Most species','Alphabetical'],horizontal=True)
if mode=='Most species':df=df.sort_values('Species',ascending=False,na_position='last')
elif mode=='Alphabetical':df=df.sort_values('Family')
else:df=df.sort_values(['Kingdom','Phylum','Class','Order','Family'],na_position='last')
st.subheader(f'{len(df):,} families')
st.dataframe(df,use_container_width=True,hide_index=True,height=620,column_config={'iNaturalist ID':None})
st.caption('The original taxonomy and species counts are preserved. No online API is called while browsing.')
