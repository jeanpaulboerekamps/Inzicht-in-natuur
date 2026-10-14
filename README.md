# Inzicht in Natuur — statische editie

De Streamlit-app zoekt uitsluitend in `families.sqlite3` en doet zelf geen API-aanroepen.

## Eenmalige opbouw
1. Upload deze projectbestanden naar de root van de GitHub-repository.
2. Open GitHub > Actions > Build family database > Run workflow.
3. Download na voltooiing het artifact `families-database` en pak dit uit.
4. Voeg `families.sqlite3` toe aan de root van de repository en commit.
5. Streamlit laadt voortaan de vaste database onmiddellijk.

**Let op:** deze ZIP bevat nog niet de wereldwijde gevulde database. De builder haalt alle actieve families op via iNaturalist. De volledige soortentelling vraagt nog één API-call per familie en kan uren duren of tegen paginering/API-limieten aanlopen. Controleer het aantal families en ontbrekende tellingen vóór publicatie. De GitHub-workflow uploadt de database als artifact; zonder commit blijft die niet beschikbaar voor Streamlit.

De drie onderscheidende kenmerken blijven bewust leeg totdat ze uit betrouwbare bronnen zijn verzameld en gecontroleerd. Bestaande kenmerken worden bij het opnieuw bouwen niet overschreven.
