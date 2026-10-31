"""RACE//RADAR V8 : calendrier Alsace en courant + FFA + veille officielle 67/68.

Exploration bornée des liens mensuels réellement publiés par la FFA.
Pas de contournement de robots.txt, de date extrapolée ni de géolocalisation inventée.
En cas de lien mensuel indisponible, la collecte principale reste fonctionnelle.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, urldefrag, urlencode
from urllib.robotparser import RobotFileParser
from datetime import timedelta
import argparse
import os
import time
import io
import zipfile
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

SOURCE = 'https://www.athle.fr/base/calendrier'
FFA_SEASON_HUB = 'https://www.athle.fr/contenu/tout-le-calendrier-2027/5255'
# Scanner au maximum huit mois futurs (et non uniquement les prochains jours).
HORIZON_MONTHS = 8
MAX_FFA_PAGES = 8
DATA = Path('events.json')
# Communes retenues à titre indicatif, PAS d'isochrone routière à 30 minutes.
CITIES = {
    'soultzmatt': 'sud', 'sulzbach': 'sud', 'guebwiller': 'sud',
    'soultz haut rhin': 'sud', 'buhl': 'sud', 'rouffach': 'sud',
    'pfaffenheim': 'sud', 'wintzfelden': 'sud', 'westhalten': 'sud',
    'orfschwihr': 'sud', 'bergholtz': 'sud', 'jungholtz': 'sud',
    'issenheim': 'sud', 'cernay': 'sud', 'ensISheim'.lower(): 'sud',
    'wettolsheim': 'centre', 'wintzenheim': 'centre', 'colmar': 'centre',
    'horbourg wihr': 'centre', 'sundhoffen': 'centre', 'munster': 'centre',
    'turckheim': 'centre', 'ingersheim': 'centre', 'eguisheim': 'centre',
    'kaysersberg': 'centre', 'kientzheim': 'centre', 'ribeauville': 'centre',
    'riquewihr': 'centre', 'bergheim': 'centre', 'scherwiller': 'centre',
    'selestat': 'centre', 'chatenois': 'centre', 'saint hippolyte': 'centre',
    'marckolsheim': 'centre', 'sainte marie aux mines': 'centre',
    'dambach la ville': 'centre', 'epfig': 'centre', 'ville': 'centre',
    'barr': 'centre', 'andlau': 'centre', 'obernai': 'centre',
    'rosheim': 'centre', 'boersch': 'centre', 'molsheim': 'nord',
    'mutzig': 'nord', 'dorlisheim': 'nord', 'ernolsheim bruche': 'nord',
    'strasbourg': 'nord', 'illkirch graffenstaden': 'nord',
    'ostwald': 'nord', 'lingolsheim': 'nord', 'eckbolsheim': 'nord',
    'schiltigheim': 'nord', 'bischheim': 'nord', 'hoenheim': 'nord',
    'mundolsheim': 'nord', 'lampertheim': 'nord', 'eckwersheim': 'nord',
    'la wantzenau': 'nord', 'vendenheim': 'nord', 'reichstett': 'nord',
    'erstein': 'nord', 'gerstheim': 'nord', 'benfeld': 'centre',
    'rhinau': 'centre', 'geispolsheim': 'nord', 'fegersheim': 'nord',
    'eschau': 'nord', 'marmoutier': 'nord', 'wasselonne': 'nord',
    'marlenheim': 'nord', 'westhoffen': 'nord', 'brumath': 'nord',
}
MONTHS = {
    'janvier':1, 'fevrier':2, 'mars':3, 'avril':4, 'mai':5,
    'juin':6, 'juillet':7, 'aout':8, 'septembre':9, 'octobre':10,
    'novembre':11, 'decembre':12,
}

def normalized(s: str) -> str:
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    s = s.lower().replace('œ', 'oe')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def date_from_label(s: str, today: date, year_hint: int | None = None) -> str | None:
    # Exemples : 01 novembre ; 01-02 novembre ; 08 août.
    m = re.search(r'\b(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s+([a-zA-Zéèêûôàùïëîç]+)\b', s, re.I)
    if not m:
        return None
    day, mo = int(m.group(1)), MONTHS.get(normalized(m.group(2)))
    if not mo:
        return None
    explicit = re.search(r'\b20\d{2}\b', s)
    # La date de l'en-tête FFA (ex. « Mars 2027 ») prime. L'inférence
    # précédente ne marche pas pour août 2027 quand nous sommes en oct. 2026.
    year = int(explicit.group()) if explicit else (year_hint if year_hint else
           today.year + (1 if mo < today.month - 3 else 0))
    try:
        d = date(year, mo, day)
    except ValueError:
        return None
    return d.isoformat() if d >= today else None


def parse_ffa(html: str, today: date, year_hint: int | None = None, season: int | None = None) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, 'html.parser')
    out, seen = [], 0
    for tr in soup.select('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 4:
            continue
        label = cells[0].get_text(' ', strip=True)
        raw_city = cells[2].get_text(' ', strip=True)
        # La plupart des pages FFA affichent des tableaux groupés par mois.
        # Une année d'en-tête évite de dater une course au mauvais millésime.
        header = tr.find_previous(['h2', 'h3', 'h4', 'caption'])
        text_header = header.get_text(' ', strip=True) if header else ''
        match_year = re.search(r'\b(20\d{2})\b', text_header) if any(m in normalized(text_header) for m in MONTHS) else None
        row_year = int(match_year.group(1)) if match_year else year_hint
        # Les saisons FFA couvrent septembre (N-1) a aout (N).
        # Ne pas extrapoler l'annee avec la date du jour pour ce calendrier.
        if season is not None and row_year is None:
            month_token = re.search(r'\b\d{1,2}(?:\s*[-–]\s*\d{1,2})?\s+([a-zA-Zéèêûôàùïëîç]+)\b', label, re.I)
            mo = MONTHS.get(normalized(month_token.group(1))) if month_token else None
            if mo:
                row_year = season-1 if mo >= 9 else season
        m_date = date_from_label(label, today, row_year)
        # Aucune interprétation à partir des autres tables du site.
        if not m_date or not re.search(r'\b0?(?:67|68)\b', raw_city):
            continue
        kind_raw = normalized(cells[3].get_text(' ', strip=True))
        if not ('running' in kind_raw or 'cross' in kind_raw):
            continue
        seen += 1
        # La ville et le departement peuvent etre dans un meme td ou deux sous-elements.
        city = re.split(r'\b0?(?:67|68)\s*[-–]\s*G-E\b', raw_city, maxsplit=1, flags=re.I)[0].strip(' |,-')
        zone = CITIES.get(normalized(city))
        if not zone:
            continue
        name = cells[1].get_text(' ', strip=True)
        if len(name) < 4 or 'annule' in normalized(name):
            continue
        kind = 'Cross' if 'cross' in kind_raw else ('Trail' if 'trail' in normalized(name) else 'Nature' if 'nature' in normalized(name) else 'Route')
        href = None
        for a in tr.select('a[href]'):
            h = a.get('href', '')
            if '/competitions/' in h:
                from urllib.parse import urljoin
                href = urljoin(SOURCE, h)
                break
        key = normalized(f'{name} {city} {m_date}')
        id_ = 'ffa-' + hashlib.sha256(key.encode()).hexdigest()[:12]
        distances = [float(x.replace(',', '.')) for x in re.findall(r'(?<!\d)(\d{1,3}(?:[,.]\d+)?)\s*km\b', name, re.I)]
        out.append({'id':id_,'name':name,'city':city,'date':m_date,'end':m_date,
                    'kind':kind,'dist':distances,'zone':zone,'source':href or SOURCE,
                    'certainty':'à vérifier','country':'FR'})
    return out, seen


def same_event(a: dict, b: dict) -> bool:
    if a['date'] != b['date'] or normalized(a['city']) != normalized(b['city']):
        return False
    an, bn = normalized(a['name']), normalized(b['name'])
    return an == bn or SequenceMatcher(None, an, bn).ratio() >= 0.70



# Calendriers complémentaires recensant running ET trail dans chaque département.
# Ces pages sont des listes: publication automatique UNIQUEMENT pour les dates complètes.
# Miles Republic répond HTTP 429 à l'exécution sur GitHub : ne plus le solliciter.
# La FFA reste la seule source de nouvelles courses publiées automatiquement
# jusqu'à validation des formats et des droits des calendriers officiels.
OFFICIAL_WATCH = (
    ('CDR67', 'https://running67.fr/running.html'),
    ('CDA68', 'https://cd68.athle.fr/asp.net/espaces.html/html.aspx?id=45230'),
)
AGENT = 'RaceRadar/1.1 (veille calendrier sportif personnel; contact via depot GitHub)'
MAX_HTML = 4_000_000
# Quelques graphies manquantes dans le premier inventaire, zone indicative seulement.
CITIES.update({
    'hattstatt':'sud', 'wuenheim':'sud', 'ungersheim':'sud',
    'neuf brisach':'centre', 'beblenheim':'centre', 'oberschaeffolsheim':'nord',
    'wolfisheim':'nord', 'oberhaslach':'nord', 'dangolsheim':'nord',
    'quatzenheim':'nord', 'dinsheim sur bruche':'nord', 'ottrott':'centre',
    'le hohwald':'centre', 'reichsfeld':'centre', 'romanswiller':'nord',
    'niederhausbergen':'nord', 'hohrod':'centre', 'orbey':'centre',
    'fortschwihr':'centre', 'jebsheim':'centre', 'barr':'centre',
    'saint nabor':'centre', 'blaesheim':'nord', 'eguisheim':'centre',
})

FRENCH_MONTH_PATTERN = r'janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre'
MILES_DATE = re.compile(
    r'(?<!\d)(?P<day>\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s+'
    rf'(?P<month>{FRENCH_MONTH_PATTERN})\s+(?P<year>20\d{{2}})\b', re.I)
MILES_DEPT = re.compile(r'\(\s*(67|68)\s*\)')
DISTANCE = re.compile(r'(?<!\d)(\d{1,3}(?:[.,]\d{1,3})?)\s*km\b', re.I)


def fetch(url: str, check_robots: bool = True) -> str:
    """GET prudent: UA transparent, timeout, taille bornée, contrôle robots."""
    if check_robots:
        parts = urlsplit(url)
        robots_url = f'{parts.scheme}://{parts.netloc}/robots.txt'
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            robots_req = Request(robots_url, headers={'User-Agent': AGENT})
            with urlopen(robots_req, timeout=10) as robots_res:
                robots_txt = robots_res.read(300_000).decode('utf-8', errors='replace')
            rp.parse(robots_txt.splitlines())
            if not rp.can_fetch(AGENT, url):
                raise PermissionError(f'robots.txt interdit la collecte : {url}')
        except PermissionError:
            raise
        except HTTPError as exc:
            # Absence de robots.txt = aucune interdiction publiée à cet emplacement.
            # 401/403 indiquent en revanche un accès refusé.
            if exc.code not in (404, 410):
                raise RuntimeError(f'impossible de vérifier robots.txt : HTTP {exc.code}') from exc
        except Exception as exc:
            raise RuntimeError(f'impossible de vérifier robots.txt : {exc}') from exc
    req = Request(url, headers={
        'User-Agent': AGENT, 'Accept': 'text/html,application/xhtml+xml'
    })
    with urlopen(req, timeout=25) as res:
        if res.status != 200:
            raise RuntimeError(f'HTTP {res.status}')
        body = res.read(MAX_HTML + 1)
        if len(body) > MAX_HTML:
            raise ValueError('page trop volumineuse')
        return body.decode('utf-8', errors='replace')


def parse_miles_card(text: str, href: str, today: date) -> dict | None:
    """Analyse un lien-carte comprenant nom/date/distances/ville/département.

    Rejette toutes les dates absentes ou imprécises ("Date à confirmer").
    """
    text = re.sub(r'\s+', ' ', text).strip()
    if not text or 'date a confirmer' in normalized(text) or 'course terminee' in normalized(text) or 'annule' in normalized(text):
        return None
    m = MILES_DATE.search(text)
    if not m:
        return None
    try:
        d = date(int(m.group('year')), MONTHS[normalized(m.group('month'))], int(m.group('day')))
    except (ValueError, KeyError):
        return None
    if d < today or d > today + timedelta(days=540):
        return None
    name = re.sub(r'^(?:achat instantan[eé]\s+)', '', text[:m.start()], flags=re.I).strip(' -')
    if not 4 <= len(name) <= 120:
        return None
    remainder = text[m.end():]
    dept_match = MILES_DEPT.search(remainder)
    if not dept_match:
        return None
    before_city = remainder[:dept_match.start()]
    distances = list(DISTANCE.finditer(before_city))
    if not distances:
        return None
    city = before_city[distances[-1].end():].strip(' ,.;-')
    # Aucune distance n'est un nom de ville. Rejet conservateur si structure change.
    if not city or len(city) > 65 or any(ch.isdigit() for ch in city):
        return None
    zone = CITIES.get(normalized(city))
    if zone is None:
        return None
    kilometers = sorted(set(float(x.group(1).replace(',', '.')) for x in distances))
    kind = 'Cross' if 'cross' in normalized(name) else ('Trail' if 'trail' in normalized(text[dept_match.end():]) or 'trail' in normalized(name) else 'Nature' if 'nature' in normalized(name) else 'Route')
    key = normalized(f'{name} {city} {d.isoformat()}')
    return {
        'id': 'mr-' + hashlib.sha256(key.encode()).hexdigest()[:12],
        'name': name, 'city': city, 'date': d.isoformat(), 'end': d.isoformat(),
        'kind': kind, 'dist': kilometers, 'zone': zone, 'source': href,
        'certainty': 'à vérifier', 'country': 'FR'
    }


def parse_miles(html: str, base_url: str, today: date) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    seen_links = set()
    cards = 0
    for a in soup.select('a[href]'):
        href = urljoin(base_url, a.get('href', ''))
        parts = urlsplit(href)
        if parts.netloc != 'fr.milesrepublic.com' or not parts.path.startswith('/event/'):
            continue
        if href in seen_links:
            continue
        seen_links.add(href)
        cards += 1
        # Sur certaines versions, seul le titre est dans <a> et la date dans
        # son parent. N'autoriser qu'un petit conteneur de carte, jamais toute
        # la page (sinon risque de mélanger les événements).
        txt = a.get_text(' ', strip=True)
        e = parse_miles_card(txt, href, today)
        if not e:
            parent = a.parent
            for _ in range(2):
                if parent is None:
                    break
                pt = parent.get_text(' ', strip=True)
                if len(pt) > 600:
                    break
                e = parse_miles_card(pt, href, today)
                if e:
                    break
                parent = parent.parent
        if e:
            out.append(e)
    return out, cards


def is_conflicting_date(a: dict, b: dict) -> bool:
    """Même course/ville +/- 7 jours, mais date différente : revue humaine."""
    if normalized(a['city']) != normalized(b['city']):
        return False
    if SequenceMatcher(None, normalized(a['name']), normalized(b['name'])).ratio() < 0.82:
        return False
    try:
        delta = abs((date.fromisoformat(a['date']) - date.fromisoformat(b['date'])).days)
        return 0 < delta <= 7
    except ValueError:
        return False


def merge_candidates(existing: dict, candidates: list[dict]) -> tuple[int, list[dict]]:
    added = 0
    review: list[dict] = []
    for item in candidates:
        if any(same_event(e, item) for e in existing['running']):
            continue
        conflicting = next((e for e in existing['running'] if is_conflicting_date(e, item)), None)
        if conflicting:
            review.append({'candidate': item, 'existing_id': conflicting['id'], 'reason':'dates contradictoires'})
            continue
        existing['running'].append(item)
        added += 1
    return added, review



def discover_calendar_links(html: str, base_url: str) -> list[dict]:
    """Trouve les liens vers calendriers officiels, sans prétendre lire les événements.

    Ne télécharge pas les PDF/XLSX : l'extraction de leurs dates reste à valider.
    """
    soup = BeautifulSoup(html, 'html.parser')
    found = {}
    for tag in soup.select('a[href],iframe[src]'):
        raw = tag.get('href') or tag.get('src') or ''
        url = urljoin(base_url, raw)
        scheme = urlsplit(url).scheme
        if scheme not in ('https', 'http'):
            continue
        label = tag.get_text(' ', strip=True)[:100]
        surrounding = (label + ' ' + raw).lower()
        good_ext = re.search(r'\.(pdf|xlsx?|csv|ics)(?:[?&#]|$)', raw, re.I)
        calendar_word = any(word in normalized(surrounding) for word in ('calendrier', 'running', 'course', '2026', '2027'))
        is_embed = tag.name == 'iframe'
        if good_ext or calendar_word or is_embed:
            found[url] = {'url':url, 'label':label or ('iframe' if is_embed else 'document'),
                          'format': ('document' if good_ext else 'iframe' if is_embed else 'page')}
    return list(found.values())[:40]


def watch_official(today: date) -> list[dict]:
    reports = []
    for name, url in OFFICIAL_WATCH:
        try:
            html = fetch(url, check_robots=True)
            links = discover_calendar_links(html, url)
            if not links:
                raise ValueError('aucun lien de calendrier détecté : structure à inspecter')
            reports.append({'name':name,'url':url,'status':'links_found',
                            'checkedAt':today.isoformat(), 'links':links})
            print(f'VEILLE {name} : {len(links)} liens potentiels (pas encore de courses importées)')
        except Exception as exc:
            reports.append({'name':name,'url':url,'status':'error',
                            'checkedAt':today.isoformat(), 'error':str(exc)[:180]})
            print(f'::warning::VEILLE {name} : {exc}')
    return reports


# V5 : extraction exploratoire de calendriers officiels vers une liste de validation.
# N'ajoute jamais ces candidats directement au site tant que leur structure
# n'a pas été vérifiée sur les sources réelles.
DATE_EXPLICIT = re.compile(
    r"\b(?P<iso>20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b|"
    r"\b(?P<day>\d{1,2})[./](?P<month_num>\d{1,2})[./](?P<year_num>20\d{2})\b|"
    r"\b(?P<day_fr>\d{1,2})\s+(?P<month_fr>" + FRENCH_MONTH_PATTERN + r")\s+(?P<year_fr>20\d{2})\b", re.I)


def explicit_date(value: str, today: date) -> str | None:
    for m in DATE_EXPLICIT.finditer(value):
        try:
            if m.group('iso'):
                d = date.fromisoformat(m.group('iso').replace('/', '-'))
            elif m.group('day'):
                d = date(int(m.group('year_num')), int(m.group('month_num')), int(m.group('day')))
            else:
                d = date(int(m.group('year_fr')), MONTHS[normalized(m.group('month_fr'))], int(m.group('day_fr')))
        except (ValueError, KeyError):
            continue
        if today <= d <= today + timedelta(days=550):
            return d.isoformat()
    return None


def download_binary(url: str) -> bytes:
    """Respecte robots.txt et refuse les documents volumineux."""
    parts = urlsplit(url)
    robots_url = f'{parts.scheme}://{parts.netloc}/robots.txt'
    rp = RobotFileParser()
    try:
        with urlopen(Request(robots_url, headers={'User-Agent': AGENT}), timeout=12) as response:
            rp.parse(response.read(300_000).decode('utf-8', 'replace').splitlines())
        if not rp.can_fetch(AGENT, url):
            raise PermissionError('Accès interdit par robots.txt')
    except HTTPError as exc:
        if exc.code not in (404, 410):
            raise
    with urlopen(Request(url, headers={'User-Agent': AGENT}), timeout=20) as response:
        payload = response.read(5_000_001)
    if len(payload) > 5_000_000:
        raise ValueError('Fichier trop volumineux')
    return payload


def parse_official_rows(rows: list[list[str]], url: str, today: date) -> list[dict]:
    """Sélection conservatrice : date comportant l'année et commune reconnue."""
    candidates = []
    already = set()
    for row in rows:
        cells = [re.sub(r'\s+', ' ', str(v or '')).strip() for v in row]
        if not cells or len(' '.join(cells)) > 850:
            continue
        dt = next((explicit_date(x, today) for x in cells if explicit_date(x, today)), None)
        if not dt:
            continue
        places = [(cell, CITIES.get(normalized(cell))) for cell in cells]
        matching = [(city,zone) for city,zone in places if zone]
        if not matching:
            continue
        city, zone = matching[0]
        names = [x for x in cells if 5 <= len(x) <= 125 and not explicit_date(x,today)
                 and normalized(x) != normalized(city)
                 and not x.isnumeric() and not x.lower().startswith(('http:', 'https:'))]
        if not names:
            continue
        name = max(names, key=lambda x: len(x))
        if normalized(name) in ('calendrier running', 'nom de la course', 'nom competition'):
            continue
        key = normalized(f'{name} {city} {dt}')
        if key in already:
            continue
        already.add(key)
        kind = 'Trail' if 'trail' in normalized(name) else 'Cross' if 'cross' in normalized(name) else 'Nature' if 'nature' in normalized(name) else 'Route'
        candidates.append({'id': 'off-'+hashlib.sha256(key.encode()).hexdigest()[:12],
                           'name': name, 'city': city, 'date': dt, 'end': dt,
                           'kind': kind, 'dist': [], 'zone': zone, 'source': url,
                           'certainty': 'à vérifier', 'country': 'FR',
                           'reviewReason':'Détecté dans un calendrier officiel : colonnes à vérifier'})
    return candidates


def official_html_candidates(html: str, url: str, today: date) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    rows = [[c.get_text(' ', strip=True) for c in tr.find_all(['th','td'])]
            for tr in soup.select('tr')]
    return parse_official_rows(rows, url, today)


def official_xlsx_candidates(data: bytes, url: str, today: date) -> list[dict]:
    """Lecteur XLSX léger standardlib, dates de cellule converties si nécessaire."""
    NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            root=ET.fromstring(archive.read('xl/sharedStrings.xml'))
            shared=[''.join(t.text or '' for t in si.iter(NS+'t')) for si in root.findall(NS+'si')]
        allrows=[]
        sheet_paths=sorted(x for x in archive.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', x))[:5]
        for sheet in sheet_paths:
            xml=ET.fromstring(archive.read(sheet))
            for row in xml.iter(NS+'row'):
                vals=[]
                for c in row.findall(NS+'c'):
                    t=c.get('t','')
                    v=c.find(NS+'v')
                    value=v.text if v is not None else ''
                    if t=='s' and value:
                        value=shared[int(value)]
                    elif t=='inlineStr':
                        value=''.join(n.text or '' for n in c.iter(NS+'t'))
                    elif t not in ('s', 'str') and value and c.get('s') is not None:
                        # Dates Excel en format serial (cellules stylées).
                        try:
                            serial = float(value)
                            if 46_000 <= serial <= 50_000:
                                value = (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()
                        except ValueError:
                            pass
                    vals.append(value or '')
                if vals:
                    allrows.append(vals)
    return parse_official_rows(allrows, url, today)


def extract_official_candidates(watches: list[dict], today: date) -> list[dict]:
    """V5 : extrait quelques documents fiables, mais met les résultats en revue."""
    found={}
    for w in watches:
        if w['status']!='links_found':
            continue
        if w['name'] == 'CDA68':
            print('EXTRACTION CDA68 : desactivee (robots.txt), veille uniquement')
            continue
        suitable=[]
        for link in w.get('links', []):
            u=link['url']
            if re.search(r'\.xlsx(?:[?#]|$)',u,re.I) and 'running' in normalized(u+' '+link.get('label','')):
                suitable.append(('xlsx',u))
            elif link.get('format')=='iframe' and ('docs.google.com' in urlsplit(u).netloc or 'running67.fr' in urlsplit(u).netloc):
                suitable.append(('html',u))
        for fmt,u in suitable[:2]:
            try:
                if fmt=='xlsx':
                    items=official_xlsx_candidates(download_binary(u),u,today)
                else:
                    items=official_html_candidates(fetch(u,check_robots=True),u,today)
                for e in items:
                    key=normalized(f"{e['name']} {e['city']} {e['date']}")
                    found[key]=e
                print(f"EXTRACTION {w['name']} : {len(items)} candidats a verifier ({fmt})")
            except Exception as exc:
                print(f"::warning::EXTRACTION {w['name']} : {str(exc)[:180]}")
    return list(found.values())

def month_distance(y: int, m: int, today: date) -> int:
    return 12 * (y - today.year) + m - today.month


def discover_ffa_month_urls(html: str, today: date) -> list[dict]:
    """Découvre UNIQUEMENT les URLs mensuelles réelles présentes sur le site FFA.

    Ne tente aucune URL inventée ni API privée. Sélectionne les liens dont la
    carte/le titre mentionne un mois, une année et une famille Running/Cross.
    """
    soup = BeautifulSoup(html, 'html.parser')
    found: dict[str, dict] = {}
    month_re = re.compile(r'\b(' + '|'.join(MONTHS) + r')\s+(20\d{2})\b', re.I)
    for link in soup.select('a[href]'):
        full = urljoin(FFA_SEASON_HUB, link['href'])
        full, _ = urldefrag(full)
        parts = urlsplit(full)
        if parts.scheme != 'https' or parts.hostname not in ('www.athle.fr', 'athle.fr'):
            continue
        if '/base/calendrier' not in parts.path:
            continue
        # Le lien générique n'offre pas de période : il est déjà traité.
        if full.rstrip('/') == SOURCE:
            continue
        card_date = None
        card_text = ''
        for parent in [link, *list(link.parents)[:5]]:
            if not getattr(parent, 'get_text', None):
                continue
            snippet = re.sub(r'\s+', ' ', parent.get_text(' ', strip=True))
            # Une carte ne doit pas réunir plusieurs mois : sinon ambiguïté.
            mm = list(month_re.finditer(normalized(snippet)))
            if len(snippet) <= 350 and len(mm) == 1:
                card_date = (int(mm[0].group(2)), MONTHS[mm[0].group(1)])
                card_text = snippet
                break
        if not card_date:
            continue
        year, month = card_date
        if not (0 <= month_distance(year, month, today) < HORIZON_MONTHS):
            continue
        # Déterminer la famille par contexte et NON par simple présence du mot
        # Running dans un tableau contenant toutes les disciplines.
        prev_heading = link.find_previous(['h2', 'h3', 'h4', 'h5'])
        discipline = None
        h = prev_heading
        for _ in range(6):
            if h is None:
                break
            head = normalized(h.get_text(' ', strip=True))
            for word in ('running', 'cross', 'piste', 'marche', 'salle'):
                if re.search(rf'\b{word}\b', head):
                    discipline = word
                    break
            if discipline:
                break
            h = h.find_previous(['h2', 'h3', 'h4', 'h5'])
        if discipline not in ('running','cross'):
            continue
        found[full] = {'url': full, 'year': year, 'month': month}
    return sorted(found.values(), key=lambda x: (x['year'], x['month'], x['url']))[:MAX_FFA_PAGES]


def collect_ffa_months(today: date) -> tuple[list[dict], dict]:
    """Collecte bornée, ne bloque jamais la collecte principale FFA."""
    status = {'discovered': 0, 'read': 0, 'failed': 0, 'regionalRows': 0,
              'candidates': 0, 'status': 'not_started', 'reason': ''}
    try:
        hub_html = fetch(FFA_SEASON_HUB, check_robots=True)
        pages = discover_ffa_month_urls(hub_html, today)
        status['discovered'] = len(pages)
        if not pages:
            status['status'] = 'unavailable'
            status['reason'] = 'Aucun lien mensuel Running/Cross exploitable découvert : filtre FFA à valider'
            print('FFA MOIS : 0 lien mensuel exploitable ; collecte principale conservee')
            return [], status
        all_candidates = {}
        for page in pages:
            try:
                # Requêtes légères, espacées : ne pas saturer la FFA.
                time.sleep(1.0)
                page_html = fetch(page['url'], check_robots=True)
                candidates, count = parse_ffa(page_html, today, year_hint=page['year'])
                status['read'] += 1
                status['regionalRows'] += count
                for c in candidates:
                    all_candidates[(normalized(c['name']), normalized(c['city']), c['date'])] = c
            except Exception as exc:
                status['failed'] += 1
                print(f"::warning::FFA MOIS {page['month']:02d}/{page['year']} : {str(exc)[:140]}")
        status['candidates'] = len(all_candidates)
        status['status'] = ('empty' if status['regionalRows'] == 0 else
                            'ok' if status['read'] == len(pages) else 'partial')
        print(f"FFA MOIS : liens {status['discovered']}, pages lues {status['read']}, echecs {status['failed']}, lignes 67/68 {status['regionalRows']}, candidats {status['candidates']}")
        return list(all_candidates.values()), status
    except Exception as exc:
        status['status'] = 'unavailable'
        status['reason'] = str(exc)[:180]
        print(f'::warning::FFA MOIS : exploration non disponible : {status["reason"]}')
        return [], status



# V7 : test de la liste officielle FFA par saison. Cette methode a ete
# observee sur une page du CDA67 renvoyant a la FFA (saison 2026).
# Nous testons la saison 2027 sur GitHub avant toute publication automatique.
FFA_LEGACY_ENDPOINT = 'https://www.athle.fr/bases/liste.aspx'

def ffa_legacy_url(season: int) -> str:
    fields = [
        ('frmbase', 'calendrier'), ('frmdate1', ''), ('frmdate2', ''),
        ('frmdepartement', ''), ('frmepreuve', ''), ('frmespace', '0'),
        ('frmligue', 'G-E'), ('frmmode', '1'), ('frmniveau', ''),
        ('frmniveaulab', ''), ('frmpostback', 'true'),
        ('frmsaisonffa', str(season)), ('frmtype1', 'Hors Stade'),
        ('frmtype2', ''), ('frmtype3', ''), ('frmtype4', ''),
    ]
    return FFA_LEGACY_ENDPOINT + '?' + urlencode(fields)


def probe_ffa_season(today: date) -> tuple[list[dict], dict]:
    # Une seule page de Grand-Est, pas de rafale de requetes par commune.
    # Le controle robots.txt est obligatoire ; aucune tentative de contournement.
    season = today.year + 1 if today.month >= 9 else today.year
    url = ffa_legacy_url(season)
    status = {'source': url, 'season': season, 'status': 'unavailable',
              'regionalRows': 0, 'areaCandidates': 0, 'checkedAt':today.isoformat()}
    try:
        html = fetch(url, check_robots=True)
        # Eviter d'interpreter une redirection ou une page de recherche vide
        # comme un calendrier exploitable.
        if 'calendrier' not in normalized(html):
            raise ValueError('reponse FFA non reconnue')
        candidates, count = parse_ffa(html, today, season=season)
        for item in candidates:
            item['source'] = url
            item['reviewReason'] = 'Calendrier saisonnier FFA : extraction a confirmer avant publication'
        status.update({'regionalRows':count, 'areaCandidates':len(candidates),
                       'status': 'ok' if count else 'empty'})
        preview = ', '.join(f"{x['date']} {x['city']}" for x in candidates[:3]) or 'aucun candidat'
        print(f'FFA SAISON {season} : lignes 67/68 {count}, zone indicative {len(candidates)}, exemples : {preview}')
        if not count:
            print('::warning::FFA SAISON : aucune ligne reconnue ; aucun import.')
        return candidates, status
    except Exception as exc:
        status['error'] = str(exc)[:200]
        print(f'::warning::FFA SAISON {season} : non exploitable ({status["error"]})')
        return [], status


# V8 : "L'Alsace en courant" : source complémentaire structurée.
# Les calendriers sont indicatifs : ne pas inventer les années futures,
# ni affirmer que nos zones indicatives sont à <= 30 minutes de route.
ALSACE_URL = 'https://www.alsace-en-courant.com/courses/index_{year}.php'
ALSACE_ALLOWED_TYPES = {
    'route': 'Route', 'nature':'Nature', 'trail':'Trail', 'ultra trail':'Trail',
    'montagne':'Trail', 'cross':'Cross', 'urbain':'Nature',
    'nocturne':'Trail', 'relais':'Nature',
}
ALSACE_HEADER = ('type','jour','date','course','distance','d','dep','depart')


def alsace_base_name(name: str) -> str:
    """Regrouper les variantes d'une course (5, 10 km, semi) sans perdre leurs distances."""
    base = re.sub(r'\s*\([^()]{1,90}\)\s*$', '', name).strip()
    return base if len(base) >= 5 else name.strip()


def parse_alsace(html: str, year: int, today: date) -> tuple[list[dict], dict]:
    """Extrait les lignes du tableau explicite de l'année; échec fermé si structure inattendue."""
    soup = BeautifulSoup(html, 'html.parser')
    table = None
    for candidate in soup.select('table'):
        for tr in candidate.select('tr')[:6]:
            cols = [normalized(td.get_text(' ', strip=True)) for td in tr.find_all(['td','th'], recursive=False)]
            if len(cols) >= 8 and cols[0] == 'type' and cols[2] == 'date' and cols[3] == 'course' and cols[7] in ('depart','lieu de depart'):
                table = candidate
                break
        if table is not None:
            break
    if table is None:
        raise ValueError('Tableau Type/Jour/Date/Course/Distance/Dep/Depart introuvable : format changé')
    stats = {'rows':0, 'upcoming':0, 'inArea':0, 'excludedType':0,
             'unrecognizedCities': set(), 'skippedDates':0}
    grouped: dict[tuple, dict] = {}
    for tr in table.select('tr'):
        cols = tr.find_all('td', recursive=False)
        if len(cols) < 8:
            continue
        stats['rows'] += 1
        typ = normalized(cols[0].get_text(' ', strip=True))
        kind = ALSACE_ALLOWED_TYPES.get(typ)
        if not kind:
            stats['excludedType'] += 1
            continue
        raw = cols[2].get_text(' ', strip=True)
        m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(20\d{2})', raw)
        if not m:
            stats['skippedDates'] += 1
            continue
        try:
            race_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            stats['skippedDates'] += 1
            continue
        # Ne jamais deviner la date de 2027 à partir d'une course 2026.
        if race_date.year != year or not (today <= race_date <= today + timedelta(days=550)):
            continue
        stats['upcoming'] += 1
        dep = cols[6].get_text(' ', strip=True)
        if dep not in ('67','68'):
            continue
        city = re.sub(r'\s+', ' ', cols[7].get_text(' ', strip=True)).strip()
        zone = CITIES.get(normalized(city))
        if zone is None:
            stats['unrecognizedCities'].add(city)
            continue
        name = re.sub(r'\s+', ' ', cols[3].get_text(' ', strip=True)).strip()
        if not 5 <= len(name) <= 155 or 'annul' in normalized(name):
            continue
        stats['inArea'] += 1
        dist_raw = cols[4].get_text(' ', strip=True).replace(',', '.')
        try:
            dist = float(dist_raw) if re.fullmatch(r'\d+(?:\.\d+)?', dist_raw) else None
        except ValueError:
            dist = None
        if dist is not None and not (0.1 <= dist <= 350):
            dist = None
        link = cols[3].find('a', href=True)
        href = urljoin(ALSACE_URL.format(year=year), link['href']) if link else ALSACE_URL.format(year=year)
        if urlsplit(href).scheme not in ('http','https'):
            href = ALSACE_URL.format(year=year)
        basename = alsace_base_name(name)
        key = (normalized(basename), normalized(city), race_date.isoformat())
        if key not in grouped:
            digest = hashlib.sha256('|'.join(key).encode()).hexdigest()[:12]
            grouped[key] = {
                'id':'aec-'+digest, 'name':basename, 'city':city,
                'date':race_date.isoformat(), 'end':race_date.isoformat(),
                'kind':kind, 'dist':[], 'zone':zone, 'source':href,
                'certainty':'à vérifier', 'country':'FR',
            }
        current = grouped[key]
        if dist is not None and dist not in current['dist']:
            current['dist'].append(dist)
        # Si au moins un des formats est trail, privilégier cette catégorie.
        if kind == 'Trail':
            current['kind'] = 'Trail'
    for item in grouped.values():
        item['dist'].sort()
    stats['candidates'] = len(grouped)
    stats['unrecognizedCities'] = sorted(stats['unrecognizedCities'])[:30]
    return list(grouped.values()), stats


def collect_alsace(today: date) -> tuple[list[dict], dict]:
    """Maximum deux pages par jour, robots.txt contrôlé via fetch() : pas de contournement."""
    years = [today.year]
    if today.month >= 9:
        years.append(today.year + 1)
    report = {'status':'unavailable', 'years':{}, 'pagesOk':0,
              'candidates':0, 'checkedAt':today.isoformat(),
              'url':ALSACE_URL.format(year=today.year)}
    out = {}
    for year in years:
        url = ALSACE_URL.format(year=year)
        try:
            html = fetch(url, check_robots=True)
            items, stats = parse_alsace(html, year, today)
            report['years'][str(year)] = {'status':'ok', **stats}
            report['pagesOk'] += 1
            for item in items:
                out[(normalized(item['name']),normalized(item['city']),item['date'])] = item
            print(f"ALSACE {year} : lignes {stats['rows']}, a venir {stats['upcoming']}, zone indicative {stats['inArea']}, evenements {stats['candidates']}")
        except HTTPError as exc:
            # Le calendrier de l'année suivante peut ne pas être encore publié.
            status = 'non_published' if exc.code in (404,410) else 'error'
            report['years'][str(year)] = {'status': status, 'error': f'HTTP {exc.code}'}
            print(f"ALSACE {year} : {status} (HTTP {exc.code}), aucune date extrapolee")
        except Exception as exc:
            report['years'][str(year)] = {'status':'error','error':str(exc)[:200]}
            print(f'::warning::ALSACE {year} : {str(exc)[:170]}')
    report['candidates'] = len(out)
    report['status'] = 'ok' if report['pagesOk'] == len(years) else 'partial' if report['pagesOk'] else 'unavailable'
    return list(out.values()), report


def equivalent_alsace(a: dict, b: dict) -> bool:
    """Une course existante le même jour et dans la même ville peut regrouper les formats."""
    if a.get('date') != b.get('date') or normalized(a.get('city','')) != normalized(b.get('city','')):
        return False
    an = re.sub(r'^(?:le|la|les|l) ', '', normalized(alsace_base_name(a.get('name',''))))
    bn = re.sub(r'^(?:le|la|les|l) ', '', normalized(alsace_base_name(b.get('name',''))))
    if an == bn:
        return True
    if min(len(an), len(bn)) >= 9 and (an.startswith(bn) or bn.startswith(an)):
        return True
    return SequenceMatcher(None, an, bn).ratio() >= 0.77


def merge_alsace(existing: dict, candidates: list[dict]) -> tuple[int, int, list[dict]]:
    """Ne pas écraser une course existante ; dates contradictoires mises en revue."""
    added, updated = 0, 0
    review = []
    for item in candidates:
        match = next((e for e in existing['running'] if equivalent_alsace(e,item)), None)
        if match:
            before = set(match.get('dist') or [])
            match['dist'] = sorted(before | set(item['dist']))
            if set(match['dist']) != before:
                updated += 1
            continue
        clash = next((e for e in existing['running'] if is_conflicting_date(e,item)), None)
        if clash:
            review.append({'candidate':item, 'existing_id':clash['id'], 'reason':'dates contradictoires'})
            continue
        existing['running'].append(item)
        added += 1
    return added, updated, review



# V9 : evenements 2027 verifies manuellement au 31/10/2026.
# Ce petit noyau permet d'enrichir la saison tant que le calendrier
# Alsace en courant 2027 n'est pas disponible. Ne pas extrapoler de dates
# depuis 2026, ne pas interroger Miles Republic (HTTP 429).
# Ces fiches datées ont une URL de provenance consultable ; les courses
# non confirmees par l'organisateur restent marquees "a verifier".
VERIFIED_2027 = (
    {
        'name': 'Les Foulées du Schiebenberg', 'city': 'Dinsheim-sur-Bruche',
        'date': '2027-04-10', 'end': '2027-04-10', 'kind': 'Nature',
        'dist': [5, 10, 20], 'zone': 'nord',
        'source': 'https://www.le-sportif.com/calendrier/232473/foulees-du-schiebenberg-2027-dinsheim-sur-bruche/course-a-pied-sur-route/',
        'certainty': 'à vérifier', 'country': 'FR',
    },
    {
        'name': 'Trail du Grand Ballon — Printanière', 'city': 'Le Markstein',
        'date': '2027-04-24', 'end': '2027-04-25', 'kind': 'Trail',
        'dist': [25.2, 35.5, 46.3, 59.2, 79.9], 'zone': 'sud',
        'source': 'https://grandballon.com/sportevents/trail-du-grand-ballon-spring/fr',
        'certainty': 'confirmée', 'country': 'FR',
    },
    {
        'name': "Courses de l'Ungersberg (U3T)", 'city': 'Reichsfeld',
        'date': '2027-05-09', 'end': '2027-05-09', 'kind': 'Trail',
        'dist': [14.5, 24, 42.6], 'zone': 'centre',
        'source': 'https://www.le-sportif.com/calendrier/232478/u3t-courses-de-l-ungersberg-2027-reichsfeld/trail-course-nature/',
        'certainty': 'à vérifier', 'country': 'FR',
    },
    {
        'name': 'Trail du Grand Ballon — Estivale', 'city': 'Le Markstein',
        'date': '2027-07-17', 'end': '2027-07-17', 'kind': 'Trail',
        # Seules la distance la plus courte et la plus longue sont reprises;
        # les autres formats sont a confirmer aupres de l'organisateur.
        'dist': [20, 80], 'zone': 'sud',
        'source': 'https://web.sqmtime.com/les-trails-du-grand-ballon/fr',
        'certainty': 'confirmée', 'country': 'FR',
    },
)


def merge_verified_2027(existing: dict, today: date) -> tuple[int, int, list[dict]]:
    """Ajoute des dates 2027 documentees. Rejouer la collecte est idempotent.

    Un conflit de date reste en revue, jamais publie automatiquement.
    Les dates/lieux des fiches existantes ne sont pas ecrases.
    """
    added = updated = 0
    conflicts = []
    for original in VERIFIED_2027:
        item = dict(original)
        d = date.fromisoformat(item['date'])
        if d.year != 2027 or d < today:
            continue
        if date.fromisoformat(item['end']) < d:
            raise ValueError('Date de fin avant la date de debut : ' + item['name'])
        city = normalized(item['city'])
        if city != 'le markstein' and CITIES.get(city) != item['zone']:
            raise ValueError('Commune non presente dans les zones existantes : ' + item['city'])
        key = normalized(item['name'] + '|' + item['city'] + '|' + item['date'])
        item['id'] = 'v27-' + hashlib.sha256(key.encode()).hexdigest()[:12]
        existing_match = next((e for e in existing['running'] if equivalent_alsace(e, item)), None)
        if existing_match:
            if date.fromisoformat(existing_match['date']).year != 2027:
                raise ValueError("Erreur d'annee de course lors de la fusion")
            previous = set(existing_match.get('dist') or [])
            combined = sorted(previous | set(item['dist']))
            if combined != sorted(previous):
                existing_match['dist'] = combined
                updated += 1
            continue
        clash = next((e for e in existing['running'] if is_conflicting_date(e,item)), None)
        if clash:
            conflicts.append({'candidate':item,'existing_id':clash['id'],
                              'reason':'Dates 2027 contradictoires : verification humaine'})
            continue
        existing['running'].append(item)
        added += 1
    return added, updated, conflicts



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='simuler sans écriture')
    parser.add_argument('--data', type=Path, default=DATA)
    args = parser.parse_args()
    existing = json.loads(args.data.read_text(encoding='utf-8'))
    if not isinstance(existing.get('running'), list) or not isinstance(existing.get('hyrox'), list):
        raise ValueError('events.json invalide : running et hyrox doivent être des listes')
    today = datetime.now(ZoneInfo('Europe/Paris')).date()
    # Ne pas compter comme « sources collectées » les calendriers seulement surveillés.
    try:
        html = fetch(SOURCE, check_robots=False)
        candidates, rows = parse_ffa(html, today)
        if rows == 0:
            raise ValueError('FFA : aucune ligne régionale trouvée, format à contrôler')
        print(f'FFA : {rows} lignes régionales, {len(candidates)} dans la zone indicative')
    except Exception as ex:
        print(f'::error::FFA inaccessible ou non reconnue : {ex}. Données conservées.')
        return 1
    monthly, month_report = collect_ffa_months(today)
    # Sonde la source FFA officielle longue sans changer les courses du site.
    season_candidates, season_report = probe_ffa_season(today)
    # Garder la source courante et la source mensuelle ; les doublons entre
    # les pages FFA sont supprimés avant publication.
    unique = {}
    for item in candidates + monthly:
        key = (normalized(item['name']), normalized(item['city']), item['date'])
        unique[key] = item
    candidates = list(unique.values())
    alsace_candidates, alsace_report = collect_alsace(today)
    official = watch_official(today)
    official_candidates = extract_official_candidates(official, today)
    added, review = merge_candidates(existing, candidates)
    alsace_added, alsace_updated, alsace_review = merge_alsace(existing, alsace_candidates)
    review.extend(alsace_review)
    verified_added, verified_updated, verified_review = merge_verified_2027(existing, today)
    review.extend(verified_review)
    existing['running'].sort(key=lambda x: (x['date'], x['name'].lower()))
    existing['runningCheckedAt'] = today.isoformat()
    existing['collectionStatus'] = [
        {'name':'FFA','url':SOURCE,'status':'ok', 'checkedAt':today.isoformat(),
         'rows':rows,'inArea':len(candidates)},
        {'name':'FFA calendrier mensuel','url':FFA_SEASON_HUB,
         'checkedAt':today.isoformat(), **month_report},
        {'name':'FFA liste saisonniere (test)','url':season_report['source'],
         **season_report},
        {'name':'Alsace en courant', **alsace_report},
        {'name':'Courses 2027 documentees', 'status':'ok', 'checkedAt':today.isoformat(),
         'catalogueSize':len(VERIFIED_2027), 'new':verified_added},
    ]
    existing['collectionSummary'] = {'date':today.isoformat(), 'sourcesOk':1,'sourcesTotal':1,
                                      'candidates':len(candidates) + len(alsace_candidates) + len(VERIFIED_2027),'added':added + alsace_added + verified_added,
                                      'conflicts':len(review),
                                      'officialWatchOk':sum(x['status']=='links_found' for x in official),
                                      'officialWatchTotal':len(official)}
    if added or alsace_added or alsace_updated or verified_added or verified_updated:
        existing['asOf'] = today.isoformat()
    print(f'2027 VERIFIE : fiches {len(VERIFIED_2027)}, nouveaux {verified_added}, distances completees {verified_updated}, conflits {len(verified_review)}')
    print(f'ALSACE BILAN : pages {alsace_report["pagesOk"]}, candidates {len(alsace_candidates)}, nouveaux {alsace_added}, distances completees {alsace_updated}, conflits {len(alsace_review)}')
    print(f'BILAN : FFA 1/1, pages mensuelles {month_report["read"]}/{month_report["discovered"]}, candidates {len(candidates)}, nouvelles {added}, conflits {len(review)}')
    print(f"VEILLE : sources officielles {sum(x['status']=='links_found' for x in official)}/{len(official)} ; import officiel complémentaire en attente de validation")
    print(f'EXTRACTION : {len(official_candidates)} candidats officiels a valider ; aucun ajout automatique')
    print('Zone geographique existante conservee sans modification. HYROX : donnees conservees.')
    if args.dry_run:
        print('MODE TEST : aucun fichier modifié.')
        return 0
    args.data.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    Path('review_candidates.json').write_text(json.dumps({'checkedAt':today.isoformat(), 'conflicts':review,
       'officialCandidates':official_candidates, 'alsaceStatus':alsace_report,
       'alsaceDateConflicts':alsace_review, 'verified2027Conflicts':verified_review, 'ffaSeasonPreview':season_candidates,
       'ffaSeasonStatus':season_report}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    Path('source_watch.json').write_text(json.dumps({'checkedAt':today.isoformat(), 'sources':official}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
