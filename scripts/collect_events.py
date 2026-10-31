"""RACE//RADAR: collecte FFA + veille des calendriers officiels 67/68.

Collecte FFA et inventaire des liens des commissions officielles 67 et 68.
Vérifie robots.txt avant les requêtes aux sources complémentaires.
Aucune date approximative n'est publiée comme date exacte.
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
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from datetime import timedelta
import argparse
import os
import io
import zipfile
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

SOURCE = 'https://www.athle.fr/base/calendrier'
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


def date_from_label(s: str, today: date) -> str | None:
    # Exemples : 01 novembre ; 01-02 novembre ; 08 août.
    m = re.search(r'\b(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s+([a-zA-Zéèêûôàùïëîç]+)\b', s, re.I)
    if not m:
        return None
    day, mo = int(m.group(1)), MONTHS.get(normalized(m.group(2)))
    if not mo:
        return None
    # Calendrier courant : une course dont le mois est largement antérieur
    # à aujourd'hui est très probablement en début d'année suivante.
    year = today.year + (1 if mo < today.month - 3 else 0)
    try:
        d = date(year, mo, day)
    except ValueError:
        return None
    return d.isoformat() if d >= today else None


def parse_ffa(html: str, today: date) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, 'html.parser')
    out, seen = [], 0
    for tr in soup.select('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 4:
            continue
        label = cells[0].get_text(' ', strip=True)
        raw_city = cells[2].get_text(' ', strip=True)
        m_date = date_from_label(label, today)
        # Aucune interprétation à partir des autres tables du site.
        if not m_date or not re.search(r'\b0?(?:67|68)\b', raw_city):
            continue
        kind_raw = normalized(cells[3].get_text(' ', strip=True))
        if not ('running' in kind_raw or 'cross' in kind_raw):
            continue
        seen += 1
        city = next(cells[2].stripped_strings, '').strip()
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
    official = watch_official(today)
    official_candidates = extract_official_candidates(official, today)
    added, review = merge_candidates(existing, candidates)
    existing['running'].sort(key=lambda x: (x['date'], x['name'].lower()))
    existing['runningCheckedAt'] = today.isoformat()
    existing['collectionStatus'] = [{'name':'FFA','url':SOURCE,'status':'ok',
                                     'checkedAt':today.isoformat(),'rows':rows,'inArea':len(candidates)}]
    existing['collectionSummary'] = {'date':today.isoformat(), 'sourcesOk':1,'sourcesTotal':1,
                                      'candidates':len(candidates),'added':added,
                                      'conflicts':len(review),
                                      'officialWatchOk':sum(x['status']=='links_found' for x in official),
                                      'officialWatchTotal':len(official)}
    if added:
        existing['asOf'] = today.isoformat()
    print(f'BILAN : FFA 1/1, candidates {len(candidates)}, nouvelles {added}, conflits {len(review)}')
    print(f"VEILLE : sources officielles {sum(x['status']=='links_found' for x in official)}/{len(official)} ; import officiel complémentaire en attente de validation")
    print(f'EXTRACTION : {len(official_candidates)} candidats officiels a valider ; aucun ajout automatique')
    print('Couverture 30 min en voiture : NON vérifiée. HYROX : pas encore automatisé.')
    if args.dry_run:
        print('MODE TEST : aucun fichier modifié.')
        return 0
    args.data.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    Path('review_candidates.json').write_text(json.dumps({'checkedAt':today.isoformat(), 'conflicts':review, 'officialCandidates':official_candidates}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    Path('source_watch.json').write_text(json.dumps({'checkedAt':today.isoformat(), 'sources':official}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
