# Tvangsauktioner Overblik

Samler aktuelle tvangsauktioner fra tvangsauktioner.dk, opdateres automatisk hver dag og kan filtreres.

## Filer
- `scraper.py` – henter tvangsauktioner og gemmer dem i `data/auctions.json`
- `kommuner.py` – henter kommunale ejendomme/grunde til salg fra 25 sjællandske kommuners hjemmesider til `data/kommunale.json` (siden `kommunale.html`). Kommunelisten står øverst i filen.
- `index.html`, `app.js`, `style.css` – selve hjemmesiden (læser data-filen)
- `.github/workflows/daily.yml` – daglig automatisk kørsel på GitHub

## Kør selv på din computer
1. Åbn en terminal i mappen og kør én gang: `pip install -r requirements.txt`
2. Hent data: `python scraper.py` og `python kommuner.py` (første gang tager det ca. 4 min; senere kun nye auktioner)
3. Se siden: `python -m http.server 8000` og åbn http://localhost:8000
   (siden kan ikke åbnes ved dobbeltklik på index.html, fordi browseren blokerer indlæsning af data-filen)

## Regler scraperen overholder
Max ét kald hver 2. sekund, tydelig User-Agent, detaljesider hentes kun for nye auktioner, kun fakta og links gemmes (ingen beskrivelser eller billeder kopieres).
