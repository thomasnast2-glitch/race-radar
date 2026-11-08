#!/usr/bin/env python3
"""HYROX : relève des indices d'annonces dans un flux RSS d'actualités.

Pas de scraping sur hyrox.com. Les indices n'ont PAS valeur d'annonce officielle.
Version V3 : filtrage strict des titres et retrait des anciens indices hors sujet.
Ils ne sont jamais publiés dans events.json sans validation humaine.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree

SEARCH = [
    'HYROX (inscriptions OR billetterie OR ouverture OR tickets OR prévente) (France OR Paris OR Lyon OR Bordeaux OR Toulouse OR Nice)',
    'HYROX (registration OR tickets OR ticket sales OR opening OR sold out) (Basel OR Frankfurt OR Freiburg OR Strasbourg)',
    'HYROX (2027 OR 2028) (inscriptions OR billetterie OR tickets OR ouverture OR registration OR annonce)',
]
RSS_BASE = 'https://news.google.com/rss/search?'

# Les titres de presse restent des pistes, JAMAIS des confirmations officielles.
# Pas de filtrage par simple ville, nom de course ou mot « date ».
ACTION_MARKERS = (
    'inscription', 'billetterie', 'ticket', 'billet', 'reservation', 'reserve',
    'registration', 'register', 'on sale', 'sale opens', 'ticket sales',
    'ouverture', 'ouvre', 'opening', 'prevente', 'presale',
    'sold out', 'complet', 'epuise', 'liste d attente', 'waitlist',
    'nouvel evenement', 'nouvelle course', 'new race', 'new event',
    'calendrier 2027', 'calendrier 2028',
)


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKD', text.casefold())
    return ''.join(char for char in text if not unicodedata.combining(char)).replace('’', ' ').replace("'", ' ')


def relevant_title(title: str) -> bool:
    text = normalize(title)
    return 'hyrox' in text and any(marker in text for marker in ACTION_MARKERS)


def rss_url(q: str) -> str:
    return RSS_BASE + 'q=' + quote(q) + '&hl=fr&gl=FR&ceid=FR:fr'


def parse_rss(xml_text: str, now: datetime) -> list[dict]:
    root = ElementTree.fromstring(xml_text)
    if root.tag != 'rss':
        raise ValueError('Réponse non RSS')
    entries = []
    for item in root.findall('./channel/item'):
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        pub = (item.findtext('pubDate') or '').strip()
        publisher = (item.findtext('source') or '').strip()
        if not title or not link or not link.startswith('https://'):
            continue
        if not relevant_title(title):
            continue
        try:
            published = parsedate_to_datetime(pub)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            published = published.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if published < now - timedelta(days=65) or published > now + timedelta(days=2):
            continue
        # Stable fingerprint: use full story URL + title, not a date-sensitive key.
        identifier = hashlib.sha256((title.casefold() + '\n' + link).encode()).hexdigest()[:16]
        entries.append({
            'id': identifier,
            'titre': title[:250],
            'source_media': publisher[:100],
            'lien_actualite': link,
            'date_publication': published.date().isoformat(),
            'statut': 'A VERIFIER - actualite non officielle',
        })
    return entries


def merge_candidates(old: list[dict], feeds: list[list[dict]], *, limit: int = 160) -> tuple[list[dict], int]:
    if not isinstance(old, list):
        raise ValueError('hyrox_candidates.json invalide : liste attendue')
    by_id = {row['id']: row for row in old if isinstance(row, dict) and row.get('id') and relevant_title(row.get('titre', ''))}
    new_count = 0
    for feed in feeds:
        for row in feed:
            if row['id'] not in by_id:
                by_id[row['id']] = row
                new_count += 1
    result = sorted(by_id.values(), key=lambda x:(x.get('date_publication', ''), x['id']), reverse=True)[:limit]
    return result, new_count


def download_feed(url: str) -> str:
    req = Request(url, headers={'User-Agent':'RaceRadarPersonalNewsRSS/1.0 (scheduled RSS reader)',
                                'Accept':'application/rss+xml,application/xml;q=0.9'})
    with urlopen(req, timeout=18) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise RuntimeError('Flux RSS trop volumineux')
        return data.decode('utf-8-sig', errors='replace')


def run(data_path: Path, status_path: Path, fetch=download_feed, now: datetime | None=None) -> tuple[int,int]:
    now = now or datetime.now(timezone.utc)
    old = json.loads(data_path.read_text(encoding='utf-8')) if data_path.exists() else []
    all_feeds = []
    errors = []
    for search in SEARCH:
        try:
            rows = parse_rss(fetch(rss_url(search)), now)
            all_feeds.append(rows)
        except Exception as ex:
            errors.append(str(ex)[:160])
    # If all external sources refuse us, fail visibly, do not report a green check.
    if not all_feeds:
        print('HYROX VEILLE : 0 source disponible, aucune donnée modifiée. ' + '; '.join(errors))
        raise RuntimeError('Toutes les sources RSS sont indisponibles')
    merged, new_count = merge_candidates(old, all_feeds)
    # Never alter events.json here. Only the validation script does that.
    if merged != old:
        data_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + '\n',encoding='utf-8')
    state = {
        'last_checked': now.date().isoformat(),
        'flux_accessibles': len(all_feeds),
        'flux_total': len(SEARCH),
        'nouveaux_indices': new_count,
        'indices_conserves': len(merged),
        'erreurs': errors,
        'rappel': 'Sources de presse uniquement : validation officielle avant publication sur le site',
    }
    status_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'HYROX VEILLE : sources {len(all_feeds)}/{len(SEARCH)}, nouveaux indices {new_count}, en memoire {len(merged)}')
    if errors:
        print('HYROX VEILLE : avertissements : ' + ' ; '.join(errors))
    print('HYROX VEILLE : 0 date automatiquement publiee (verification officielle requise)')
    return len(all_feeds), new_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidates',type=Path,default=Path('hyrox_candidates.json'))
    parser.add_argument('--status',type=Path,default=Path('hyrox_watch.json'))
    args = parser.parse_args()
    run(args.candidates,args.status)

if __name__=='__main__':
    main()
