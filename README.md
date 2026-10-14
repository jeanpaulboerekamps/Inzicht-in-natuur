# Inzicht in Natuur v3

Streamlit-app voor taxonomische familieoverzichten op basis van iNaturalist.

- Automatisch ophalen van alle gevonden families, inclusief aantallen en hiërarchie.
- Berekening via een achtergrondthread met maximaal 3 gelijktijdige verzoekreeksen.
- Tussentijdse resultaten worden opgeslagen in `inzicht_cache.sqlite3` op de Streamlit-server.
- Scherm ververst elke vijf seconden; mislukte families zijn opnieuw te proberen.
- De lokale SQLite-cache kan verdwijnen wanneer Streamlit Community Cloud de app opnieuw bouwt of de container vervangt. Voor duurzame opslag tussen deployments is externe opslag nodig.
- De kenmerken zijn nog niet ingevuld: de iNaturalist-API levert hiervoor geen betrouwbare gestructureerde data.

Start: `streamlit run app.py`
