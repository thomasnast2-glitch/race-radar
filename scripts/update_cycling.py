#!/usr/bin/env python3
"""Veille prudente des sites officiels cyclosportifs, sans extraction non autorisee.

- Respecte robots.txt et limite la collecte aux organisateurs connus.
- Met a jour cycling.json uniquement sur signaux explicites et non ambigus.
- Place les changements de date incertains dans cycling_review.json.
- Ecrit un bilan cycling_watch.json pour le suivi quotidien.
Aucune dependenance Python externe.
"""
import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from datetime import date, datetime, timezone
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = 'RaceRadarCycloBot/1.0 (+public event monitor; 1 request/site/day)'
TIMEOUT = 12
MAX_BYTES = 500_000

# Only organizers' own public pages; no automated querying of HYROX, FFA or aggregator pages.
SOURCES = [
    ('cyc-babybel-route-2027', 'https://cyclosportive-babybel.fr/journee/route/'),
    ('cyc-babybel-gravel-2027', 'https://cyclosportive-babybel.fr/'),
    ('cyc-tricolore-2027', 'https://lasundgauvienne.fr/'),
    ('cyc-alsacienne-2027', 'https://www.alsacienne-cyclo.org/fr/'),
    ('cyc-gfny-2027', 'https://grandballon.gfny.com/'),
    ('cyc-jpp-2027', 'https://www.cyclo-jpp.com/'),
    ('cyc-etape-2027', 'https://www.letapedutourdefrance.com/fr/la-course/s-inscrire'),
]
MONTHS = {'janvier':1, 'fevrier':2, 'mars':3, 'avril':4, 'mai':5, 'juin':6,
          'juillet':7, 'aout':8, 'septembre':9, 'octobre':10, 'novembre':11, 'decembre':12}

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hide = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','svg'):
            self.hide += 1
        elif tag in ('p','h1','h2','h3','li','br','div'):
            self.parts.append(' ')
    def handle_endtag(self, tag):
        if tag in ('script','style','svg'):
            self.hide = max(0,self.hide-1)
        else:
            self.parts.append(' ')
    def handle_data(self, data):
        if not self.hide:
            self.parts.append(data)

def normalized(raw):
    import unicodedata
    t = unicodedata.normalize('NFKD', html.unescape(raw))
    t = ''.join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', t).strip().lower()

def text_from_html(raw):
    p = PlainText()
    p.feed(raw)
    return re.sub(r'\s+', ' ', html.unescape(' '.join(p.parts))).strip()

def extract_dates(text):
    """Return explicit dates with year 2027, never infer a year."""
    t = normalized(text)
    results = set()
    for m in re.finditer(r'\b(\d{1,2})\s+(janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\s+2027\b', t):
        try: results.add(date(2027,MONTHS[m.group(2)],int(m.group(1))).isoformat())
        except ValueError: continue
    for m in re.finditer(r'\b(\d{1,2})[/-](\d{1,2})[/-]2027\b',t):
        try: results.add(date(2027,int(m.group(2)),int(m.group(1))).isoformat())
        except ValueError: continue
    for m in re.finditer(r'\b2027-(\d{2})-(\d{2})\b',t):
        try: results.add(date(2027,int(m.group(1)),int(m.group(2))).isoformat())
        except ValueError: continue
    return sorted(results)

def registration_open(text):
    t = normalized(text)
    return bool(re.search(r'(?:inscriptions?\s+(?:sont\s+)?ouvertes?|billetterie\s+ouverte)', t))

def robots_allows(url):
    """Deny on ambiguous robots error; explicit 404 means no robots.txt."""
    parsed = urlparse(url)
    robots = f'{parsed.scheme}://{parsed.netloc}/robots.txt'
    req = Request(robots,headers={'User-Agent':USER_AGENT})
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            content = r.read(200_000).decode('utf-8','replace')
    except HTTPError as e:
        if e.code == 404: return True, 'robots.txt absent (404)'
        return False, f'robots.txt HTTP {e.code}'
    except Exception as e:
        return False, f'robots.txt indisponible ({type(e).__name__})'
    rp = RobotFileParser(robots)
    rp.parse(content.splitlines())
    return rp.can_fetch(USER_AGENT,url), 'robots.txt consulte'

def fetch_site(url):
    allowed, why = robots_allows(url)
    if not allowed:
        return None, f'NON CONSULTE: acces interdit ou robots inconnu ({why})'
    try:
        req = Request(url, headers={'User-Agent':USER_AGENT, 'Accept':'text/html'})
        with urlopen(req,timeout=TIMEOUT) as res:
            ctype = res.headers.get('Content-Type','')
            if 'html' not in ctype.lower():
                return None, 'Non HTML: '+ctype
            raw = res.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES: return None, 'Page trop volumineuse'
            charset = res.headers.get_content_charset() or 'utf-8'
        page = raw.decode(charset,'replace')
        if 'just a moment' in page.lower() or 'checking your browser' in page.lower() or 'request is being verified' in page.lower():
            return None, 'Protection anti-bot detectee, aucun contournement'
        return text_from_html(page), 'OK'
    except (HTTPError,URLError,TimeoutError) as e:
        return None, f'Inaccessible: {e}'

def apply_event_updates(event, page_text):
    """Do not overwrite a known date with an ambiguous scraped date."""
    changes = []
    reviews = []
    dates = extract_dates(page_text)
    # A new date is only trusted when it is uniquely present on the official
    # organizer page. Existing differing dates always need human confirmation.
    if dates and len(dates)==1:
        found = dates[0]
        if not event.get('date'):
            event['date']=found
            event['end']=found
            event['sort']=found
            event['date_hint']=date.fromisoformat(found).strftime('%d/%m/%Y')
            event['status']='Date annoncée sur le site organisateur'
            changes.append(f'date {found}')
        elif event['date']!=found:
            reviews.append({'event_id':event['id'],'current_date':event['date'], 'found_date':found, 'reason':'date officielle differente - validation humaine requise'})
    elif len(dates)>1:
        # No guess if the home page advertises multiple activities/dates.
        pass
    # Opening status only if 2027 is explicitly present and event date is already known.
    if event.get('date') in dates and registration_open(page_text):
        existing = event.get('status','')
        if 'Inscriptions ouvertes' not in existing:
            event['status'] = existing.rstrip(' ·') + ' · Inscriptions ouvertes'
            changes.append('inscriptions ouvertes')
    # Exact official 2027 L'Etape notice: do not infer any other opening day.
    if event['id']=='cyc-etape-2027':
        t=normalized(page_text)
        if re.search(r'(?:inscriptions.{0,90}ouvr\w*.{0,60}02/11/2026|ouverture.{0,90}inscriptions.{0,90}2\s+novembre\s+2026)',t):
            if not event.get('open_date'):
                event['open_date']='2026-11-02'
                changes.append('ouverture 2026-11-02')
    return changes, reviews, dates

def save_json(path,data):
    path.write_text(json.dumps(data, ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def run(root=ROOT, fetch=fetch_site, now=None):
    now = now or datetime.now(timezone.utc)
    path=root/'cycling.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data.get('cycling'),list): raise ValueError('cycling.json invalide: champ cycling absent')
    by_id={r['id']:r for r in data['cycling']}
    if len(by_id)!=len(data['cycling']): raise ValueError('IDs cycling.json dupliques')
    watch={'lastCheckedAt':now.isoformat(timespec='seconds'), 'sources':[]}
    reviews=[]
    updated=0
    success=0
    for eid,url in SOURCES:
        if eid not in by_id: continue
        raw,state=fetch(url)
        item={'event_id':eid, 'url':url, 'result':state}
        if raw is not None:
            success+=1
            item['sha256']=hashlib.sha256(raw.encode('utf-8')).hexdigest()
            changes, found_reviews, dates=apply_event_updates(by_id[eid],raw)
            item['dates_2027_detectees']=dates
            item['modifications']=changes
            reviews.extend({**r,'source':url} for r in found_reviews)
            updated+=len(changes)
        watch['sources'].append(item)
        print(f'CYCLO {eid}: {state}'+(f' ({len(item.get("dates_2027_detectees",[]))} dates 2027)' if raw is not None else ''))
    data['cyclingCheckedAt']=now.date().isoformat()
    data['cyclingSourcesAccessible']=success
    if updated: data['asOf']=now.date().isoformat()
    save_json(path,data)
    save_json(root/'cycling_watch.json',watch)
    # Keep a stable review output, never publish uncertain dates as confirmed.
    save_json(root/'cycling_review.json',{'checkedAt':now.date().isoformat(),'candidates':reviews})
    print(f'CYCLO BILAN : sources {success}/{len(watch["sources"])}, mises_a_jour {updated}, dates_a_verifier {len(reviews)}')
    if not success:
        print('CYCLO AVERTISSEMENT : aucune source organisateur accessible ; donnees existantes conservees.')

def self_test():
    assert extract_dates('Dimanche 16 mai 2027')==['2027-05-16']
    assert extract_dates('Édition 2026')==[]
    assert extract_dates('le 2027-07-11')==['2027-07-11']
    assert extract_dates('15 et 16 mai 2027')==['2027-05-16']  # no guessing for 15
    assert registration_open('Inscriptions ouvertes')
    assert not registration_open('Inscriptions à venir')
    e={'id':'cyc-test','date':'2027-06-26','status':'Date confirmée'}
    changes,reviews,dates=apply_event_updates(e,'Edition 2027, 27 juin 2027')
    assert not changes and reviews and e['date']=='2027-06-26'
    e={'id':'cyc-test','date':None,'status':'Date à confirmer'}
    changes,reviews,dates=apply_event_updates(e,'Rendez-vous le 6 juin 2027')
    assert e['date']=='2027-06-06' and not reviews
    print('CYCLO TEST : 8 controles reussis')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test: self_test()
    else: run()
