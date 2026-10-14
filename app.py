from pathlib import Path
import sqlite3
import pandas as pd
import streamlit as st

DB = Path(__file__).with_name('families.sqlite3')
st.set_page_config(page_title='Inzicht in Natuur', layout='wide')
st.title('🌿 Inzicht in Natuur')
st.caption('Vaste taxonomische familie-encyclopedie · iNaturalist-snapshot · geen live API bij zoeken')
if not DB.exists():
    st.warning('De vaste database is nog niet opgebouwd. Start in GitHub Actions de workflow “Build family database” en voeg het gegenereerde families.sqlite3-bestand toe aan deze repository.')
    st.stop()
@st.cache_data(show_spinner=False)
def load_database(mtime):
    with sqlite3.connect(f'file:{DB}?mode=ro', uri=True) as con:
        return pd.read_sql_query('SELECT kingdom AS Rijk, phylum AS Stam, class_name AS Klasse, order_name AS Orde, name AS Familie, common_name AS "Engelse naam", species_count AS "Aantal soorten", feature1 AS "Kenmerk 1", feature2 AS "Kenmerk 2", feature3 AS "Kenmerk 3", id AS "iNaturalist ID" FROM families', con)
df = load_database(DB.stat().st_mtime_ns)
if df.empty:
    st.warning('De database bevat nog geen families.')
    st.stop()
st.metric('Families in database', f'{len(df):,}'.replace(',', '.'))
st.caption('Soortenaantallen zijn taxonomische tellingen op het moment van de databasebouw; ontbrekende waarden worden niet als nul weergegeven.')
with st.sidebar:
    st.header('Zoeken en filteren')
    search = st.text_input('Zoek in namen en kenmerken', placeholder='Bijv. Lepidoptera, antennes, Asteraceae')
    for column in ('Rijk', 'Stam', 'Klasse', 'Orde'):
        opts = sorted(x for x in df[column].dropna().unique() if str(x).strip())
        selected = st.selectbox(column, ['Alle'] + opts)
        if selected != 'Alle':
            df = df[df[column] == selected]
    only_features = st.checkbox('Alleen families met kenmerken')
if search:
    cols = ['Rijk', 'Stam', 'Klasse', 'Orde', 'Familie', 'Engelse naam', 'Kenmerk 1', 'Kenmerk 2', 'Kenmerk 3']
    mask = df[cols].fillna('').astype(str).apply(lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)
    df = df[mask]
if only_features:
    df = df[df[['Kenmerk 1', 'Kenmerk 2', 'Kenmerk 3']].notna().any(axis=1)]
mode = st.radio('Sortering', ['Taxonomisch', 'Meeste soorten', 'Alfabetisch'], horizontal=True)
if mode == 'Meeste soorten':
    df = df.sort_values('Aantal soorten', ascending=False, na_position='last')
elif mode == 'Alfabetisch':
    df = df.sort_values('Familie')
else:
    df = df.sort_values(['Rijk', 'Stam', 'Klasse', 'Orde', 'Familie'], na_position='last')
st.subheader(f'Familieoverzicht · {len(df)} families')
st.dataframe(df, use_container_width=True, hide_index=True, height=650, column_config={'iNaturalist ID': None})
st.caption('Kenmerken zonder geverifieerde bron blijven leeg. De taxonomische volgorde volgt de hiërarchie; binnen een orde alfabetisch.')
