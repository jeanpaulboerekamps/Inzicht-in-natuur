from pathlib import Path
import sqlite3
import pandas as pd
import streamlit as st

DB = Path(__file__).with_name('families.sqlite3')
st.set_page_config(page_title='Inzicht in Natuur', layout='wide')
st.title('🌿 Inzicht in Natuur')
st.caption('Taxonomic family encyclopedia · offline SQLite snapshot')
if not DB.exists():
    st.error('families.sqlite3 is missing.'); st.stop()

@st.cache_data(show_spinner=False)
def load(mtime):
    with sqlite3.connect(f'file:{DB}?mode=ro', uri=True) as con:
        return pd.read_sql_query('''SELECT f.id AS taxon_id, f.kingdom AS Kingdom,
        f.phylum AS Phylum, f.class_name AS Class, f.order_name AS "Order",
        f.name AS Family, f.common_name AS english_name, f.species_count AS species,
        f.feature1 AS feature1, f.feature2 AS feature2, f.feature3 AS feature3,
        q.status AS feature_status, q.exceptions_note AS exceptions,
        q.source_reference AS source_reference
        FROM families f LEFT JOIN feature_quality_review q ON f.id=q.family_id''', con)

all_df = load(DB.stat().st_mtime_ns)
a,b,c=st.columns(3)
a.metric('Families',f'{len(all_df):,}')
b.metric('Species counts',f'{all_df.species.notna().sum():,}')
c.metric('Families with draft features',f'{all_df.feature1.notna().sum():,}')

with st.sidebar:
    st.header('Filters')
    search=st.text_input('Search family, taxonomy and features')
    filters={}
    for col in ['Kingdom','Phylum','Class','Order']:
        options=sorted(str(x) for x in all_df[col].dropna().unique() if str(x).strip())
        filters[col]=st.selectbox(col,['All']+options)
    only=st.checkbox('Only families with draft features')

df=all_df
for col,value in filters.items():
    if value!='All': df=df[df[col]==value]
if only: df=df[df.feature1.notna()]
if search:
    cols=['Kingdom','Phylum','Class','Order','Family','english_name','feature1','feature2','feature3']
    mask=df[cols].fillna('').astype(str).apply(lambda s:s.str.contains(search,case=False,regex=False)).any(axis=1)
    df=df[mask]
mode=st.radio('Sort',['Taxonomic','Most species','Alphabetical'],horizontal=True)
if mode=='Most species':df=df.sort_values('species',ascending=False,na_position='last')
elif mode=='Alphabetical':df=df.sort_values('Family')
else:df=df.sort_values(['Kingdom','Phylum','Class','Order','Family'],na_position='last')

st.subheader(f'{len(df):,} families')
st.caption('Select a row to view family details. The table contains taxonomy only.')
visible=['Kingdom','Phylum','Class','Order','Family']
selected=st.dataframe(df[visible],use_container_width=True,hide_index=True,height=590,
    on_select='rerun',selection_mode='single-row',key='family_table')
rows=selected.selection.rows
if rows:
    record=df.iloc[rows[0]]
    with st.container(border=True):
        st.subheader(str(record['Family']))
        if pd.notna(record.english_name) and str(record.english_name).strip():
            st.caption(str(record.english_name))
        lineage=' › '.join(str(record[x]) for x in visible[:-1] if pd.notna(record[x]) and str(record[x]).strip())
        st.write(lineage)
        left,right=st.columns(2)
        left.metric('Species',f'{int(record.species):,}' if pd.notna(record.species) else 'Unknown')
        right.metric('iNaturalist taxon ID',str(int(record.taxon_id)))
        st.markdown('#### Distinguishing characteristics')
        features=[record[x] for x in ('feature1','feature2','feature3') if pd.notna(record[x]) and str(record[x]).strip()]
        if features:
            for i,feature in enumerate(features,1):
                st.markdown(f'**{i}.** {feature}')
        else:
            st.info('No distinguishing characteristics recorded for this family yet.')
        if pd.notna(record.feature_status) and str(record.feature_status).strip():
            st.caption(f'Status: {record.feature_status}')
        if pd.notna(record.exceptions) and str(record.exceptions).strip():
            st.markdown('#### Exceptions and limitations')
            st.write(record.exceptions)
        if pd.notna(record.source_reference) and str(record.source_reference).strip():
            st.markdown('#### Source')
            st.write(record.source_reference)
        if features and (pd.isna(record.feature_status) or str(record.feature_status).lower()!='verified'):
            st.warning('Provisional characteristics: scientific source verification is still required.')
else:
    st.info('Click a family row above to open its details.')
