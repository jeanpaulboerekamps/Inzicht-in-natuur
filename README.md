# Inzicht in Natuur — eerste prototype

Streamlit-dashboard voor het kiezen van rijk, klasse of orde en het bekijken van de onderliggende families uit iNaturalist.

## Starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Belangrijke beperkingen

- Dit is een eerste werkend prototype, niet de complete wetenschappelijk gevalideerde familiedatabase.
- De iNaturalist descendants-API kan bij grote taxa begrensd zijn; de app waarschuwt bij afkapping.
- Binnen een orde staan families alfabetisch, niet in een veronderstelde fylogenetische volgorde.
- 'Waargenomen soorten' telt soorten met observaties en is niet gelijk aan het totaal aantal beschreven soorten.
- De drie diagnostische familiekenmerken blijven voorlopig leeg; hiervoor is een aparte gecontroleerde gegevensbron nodig.
- iNaturalist-verzoeken worden beperkt tot 3 parallelle taken en een instelbaar aantal families.
