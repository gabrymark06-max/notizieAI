"""Bot Telegram: ogni ora le notizie nuove sull'intelligenza artificiale.

Gira su GitHub Actions (vedi .github/workflows/notizie.yml). Legge i feed e i
blog ufficiali, tiene in visti.json le notizie gia' mandate e manda su Telegram
solo quelle nuove, nella lingua originale. Se non c'e' niente di nuovo, tace.
Segna con 🔥 i lanci grossi (nuovi modelli GPT, Claude, Gemini, Llama...).

Variabili d'ambiente (segreti del repository): TELEGRAM_TOKEN, TELEGRAM_CHAT_ID.
Solo libreria standard di Python.
"""

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VISTI = Path(__file__).with_name("visti.json")
ROMA = ZoneInfo("Europe/Rome")
UA = "Mozilla/5.0 (compatible; notizieAI-bot/1.0; +https://github.com/gabrymark06-max/notizieAI)"
MAX_ETA = timedelta(hours=48)  # le notizie piu' vecchie non si mandano mai
TIENI = timedelta(days=45)     # per quanto si ricorda una notizia gia' vista

# (nome, tipo, url): "feed" = RSS/Atom, "pagina" = blog senza feed (si leggono i link)
FONTI = [
    ("OpenAI", "feed", "https://openai.com/news/rss.xml"),
    ("Anthropic", "pagina", "https://www.anthropic.com/news"),
    ("Google", "feed", "https://blog.google/innovation-and-ai/technology/ai/rss/"),
    ("Google DeepMind", "feed", "https://deepmind.google/blog/rss.xml"),
    ("Meta AI", "pagina", "https://ai.meta.com/blog/"),
    ("Hugging Face", "feed", "https://huggingface.co/blog/feed.xml"),
    ("TechCrunch", "feed", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge", "feed", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
]

# link degli articoli nei blog senza feed
LINK_PAGINA = {
    "Anthropic": re.compile(r'href="(/(?:news/[a-z0-9-]+|claude-[a-z0-9-]+))"'),
    "Meta AI": re.compile(r'href="(https://ai\.meta\.com/blog/[a-z0-9-]+/)"'),
}

# lanci grossi: nomi di modelli con un numero di versione, o parole da annuncio
GROSSO = re.compile(
    r"\b(GPT-?\d|o\d\b|Claude|Opus|Sonnet|Haiku|Fable|Mythos|Gemini \d|Gemma \d|Llama \d|Grok \d|"
    r"Mistral (Large|Medium)|DeepSeek[- ]?[VR]?\d|Qwen ?\d|Sora|Veo \d)",
    re.IGNORECASE,
)
ANNUNCIO = re.compile(r"\b(introduc|launch|releas|announc|now available|unveil|debut)", re.IGNORECASE)


def scarica(url: str, tentativi: int = 2) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    for k in range(tentativi):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo = r.read().decode("utf-8", "replace")
            if corpo.strip():
                return corpo
        except Exception:
            if k == tentativi - 1:
                raise
    raise ValueError("risposta vuota")


def testo(el) -> str:
    # alcuni feed (The Verge) codificano due volte gli apostrofi: "&#8217;"
    return html.unescape((el.text or "").strip()) if el is not None else ""


def data(s: str) -> datetime | None:
    s = s.strip()
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def leggi_feed(nome: str, url: str) -> list[dict]:
    radice = ET.fromstring(scarica(url))
    out = []
    for it in radice.iter("item"):  # RSS
        out.append({"fonte": nome, "titolo": testo(it.find("title")), "link": testo(it.find("link")),
                    "data": data(testo(it.find("pubDate")))})
    atom = "{http://www.w3.org/2005/Atom}"
    for it in radice.iter(atom + "entry"):  # Atom
        link = it.find(atom + "link[@rel='alternate']")
        if link is None:
            link = it.find(atom + "link")
        out.append({"fonte": nome, "titolo": testo(it.find(atom + "title")),
                    "link": link.get("href", "") if link is not None else "",
                    "data": data(testo(it.find(atom + "published")) or testo(it.find(atom + "updated")))})
    return [x for x in out if x["link"] and x["titolo"]]


def leggi_pagina(nome: str, url: str) -> list[dict]:
    corpo = scarica(url)
    visti, out = set(), []
    for m in LINK_PAGINA[nome].finditer(corpo):
        link = urllib.parse.urljoin(url, m.group(1))
        if link not in visti and link.rstrip("/") != url.rstrip("/"):
            visti.add(link)
            out.append({"fonte": nome, "titolo": "", "link": link, "data": None})
    return out


def titolo_pagina(link: str) -> str:
    try:
        m = re.search(r"<title[^>]*>(.*?)</title>", scarica(link), re.S | re.I)
    except Exception:
        return link
    t = html.unescape(m.group(1)).strip() if m else link
    return re.sub(r"\s*[\\|]\s*(Anthropic|AI at Meta|Meta AI)\s*$", "", t)


def manda(righe: list[str]) -> None:
    token, chat = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    # Telegram accetta al massimo 4096 caratteri: si spezza per notizie
    pezzi, cur = [], ""
    for r in righe:
        if len(cur) + len(r) + 2 > 3800:
            pezzi.append(cur)
            cur = ""
        cur += r + "\n\n"
    if cur:
        pezzi.append(cur)
    for p in pezzi:
        dati = urllib.parse.urlencode({"chat_id": chat, "text": p.strip(), "parse_mode": "HTML",
                                       "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=dati, timeout=30)


def riga(n: dict) -> str:
    fuoco = "🔥 " if GROSSO.search(n["titolo"]) and (ANNUNCIO.search(n["titolo"]) or n["fonte"] in ("OpenAI", "Anthropic", "Google", "Google DeepMind", "Meta AI")) else ""
    ora = f" · {n['data'].astimezone(ROMA):%d/%m %H:%M}" if n["data"] else ""
    return (f"{fuoco}<b>{html.escape(n['titolo'])}</b>\n"
            f"<i>{html.escape(n['fonte'])}{ora}</i>\n{html.escape(n['link'])}")


def main() -> None:
    adesso = datetime.now(timezone.utc)
    primo_giro = not VISTI.exists()
    visti = {} if primo_giro else json.loads(VISTI.read_text(encoding="utf-8"))

    nuove, errori = [], []
    for nome, tipo, url in FONTI:
        try:
            voci = leggi_feed(nome, url) if tipo == "feed" else leggi_pagina(nome, url)
        except Exception as e:  # una fonte giu' non ferma le altre
            errori.append(f"{nome}: {e}")
            continue
        for v in voci:
            if v["link"] in visti:
                continue
            visti[v["link"]] = adesso.isoformat()
            if v["data"] and adesso - v["data"] > MAX_ETA:
                continue
            nuove.append(v)

    if primo_giro:
        # la prima volta si segnano come viste e si mandano solo le 5 piu' recenti
        recenti = sorted([n for n in nuove if n["data"]], key=lambda n: n["data"], reverse=True)[:5]
        manda(["🤖 <b>Bot notizie AI attivo.</b> Da ora ti scrivo ogni ora, solo se ci sono notizie nuove.",
               "Le ultime uscite:"] + [riga(n) for n in recenti])
    elif nuove:
        for n in nuove:
            if not n["titolo"]:
                n["titolo"] = titolo_pagina(n["link"])
        nuove.sort(key=lambda n: (not riga(n).startswith("🔥"), -(n["data"] or adesso).timestamp()))
        intestazione = f"🗞 <b>{len(nuove)} notizi{'a' if len(nuove) == 1 else 'e'} AI</b> · {adesso.astimezone(ROMA):%d/%m %H:%M}"
        manda([intestazione] + [riga(n) for n in nuove])

    limite = adesso - TIENI
    visti = {k: v for k, v in visti.items() if datetime.fromisoformat(v) > limite}
    VISTI.write_text(json.dumps(visti, indent=0, sort_keys=True), encoding="utf-8")
    print(f"notizie nuove: {len(nuove)} (primo giro: {primo_giro})")
    for e in errori:
        print("fonte non letta:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
