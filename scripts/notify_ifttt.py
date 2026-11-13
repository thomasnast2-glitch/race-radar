#!/usr/bin/env python3
"""RACE RADAR -> IFTTT: une alerte par rubrique et par detection, sans doublon.

Premiere execution : initialise l'historique, sans notifier les courses deja connues.
"""

import json
import os
import re
from urllib.error import HTTPError, URLError
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

STATE_PATH = Path('.ifttt_seen.json')
SOURCES = (
    ('running', Path('events.json'), 'running', 'RUNNING'),
    ('hyrox', Path('events.json'), 'hyrox', 'HYROX'),
    ('cycling', Path('cycling.json'), 'cycling', 'CYCLO'),
)


def stable_key(event):
    return str(event.get('id') or '|'.join(str(event.get(k, '')).strip().casefold()
                                           for k in ('name', 'city', 'date')))


def load_events():
    results = {}
    for label, path, field, _ in SOURCES:
        data = json.loads(path.read_text(encoding='utf-8'))
        entries = data.get(field, [])
        if not isinstance(entries, list):
            raise ValueError(f'Le champ {field} de {path} ne contient pas de liste')
        results[label] = {stable_key(e): e for e in entries if isinstance(e, dict) and e.get('name')}
    return results


def save_state(state):
    temporary = STATE_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(STATE_PATH)


def registration_key(event):
    """Only officially validated announcements qualify; RSS hints never do."""
    source = event.get('registration_source') or ''
    parts = urlsplit(source)
    if (not event.get('registration_verified_at') or parts.scheme != 'https'
            or parts.hostname not in {'hyrox.com', 'www.hyrox.com', 'hyroxfrance.com', 'www.hyroxfrance.com'}
            or parts.username or parts.password
            or not parts.path.startswith(('/event/', '/fr/event/'))):
        return None
    if event.get('registration') == 'waitlist' or event.get('status') == 'Ouverture non annoncée':
        return None
    return json.dumps([event.get('status'), event.get('open_date'),
                       event.get('registration_category')], ensure_ascii=False)


def upcoming(event, today):
    value = event.get('end') or event.get('date') or event.get('sort') or ''
    return bool(value and value[:4].isdigit() and value >= today)


def notify(current, old, today, deliver=None):
    deliver = deliver or send
    # Preserve the existing v1 ID lists when adding registration tracking.
    seen = {label: set(old.get(label, [])) for label in current}
    registrations = {key: registration_key(e) for key, e in current['hyrox'].items()}
    previous = old.get('hyrox_registrations')
    state = {label: sorted(ids) for label, ids in seen.items()}
    state['hyrox_registrations'] = dict(previous if previous is not None else registrations)
    save_state(state)
    for label, _, _, title in SOURCES:
        events = current[label]
        new_keys = set(events) - seen[label]
        new_futures = [events[key] for key in new_keys if upcoming(events[key], today)]
        changed = []
        if label == 'hyrox' and previous is not None:
            changed = [e for key, e in events.items() if key in seen[label]
                       and upcoming(e, today) and registrations[key] is not None
                       and registrations[key] != previous.get(key)]
        alerts = sorted(new_futures + changed,
                        key=lambda e: (e.get('open_date') or e.get('date') or e.get('sort') or '', e['name']))
        if alerts:
            first = alerts[0]
            details = []
            for event in alerts[:3]:
                when = event.get('date') or event.get('date_hint') or 'date à confirmer'
                description = f"{event['name']} - {when}"
                if label == 'hyrox' and registration_key(event):
                    description += f" : {event.get('status', '')}"
                    if event.get('open_date'):
                        description += f" (ouverture {event['open_date']})"
                details.append(description)
            heading = (f'{len(alerts)} nouveauté(s) {title}' if changed
                       else f'{len(alerts)} nouvelle(s) course(s) {title}')
            deliver([heading, ' ; '.join(details)[:500],
                     str(first.get('registration_source') or first.get('source') or first.get('url') or 'RACE RADAR')[:500]])
            print(f'IFTTT : {len(alerts)} nouveauté(s) {title} notifiée(s).')
        else:
            print(f'IFTTT : aucune nouveauté {title}.')
        state[label] = sorted(seen[label] | new_keys)
        if label == 'hyrox':
            state['hyrox_registrations'].update(registrations)
        # Persist each successful category, even if the next delivery fails.
        save_state(state)


def webhook_url():
    """Normalise le secret sans afficher sa cle dans les logs GitHub.

    Accepte les deux URLs presentees par IFTTT (/with/key et /json/with/key),
    y compris si le champ nom d'evenement a ete laisse vide, ou la cle seule.
    Envoie toujours au declencheur 'Receive a web request' race_radar_new.
    """
    raw = os.getenv('IFTTT_WEBHOOK_URL', '').strip()
    if not raw:
        raise RuntimeError(
            'IFTTT_WEBHOOK_URL est vide ou inaccessible. '
            'GitHub > Settings > Secrets and variables > Actions : mettre a jour le secret.'
        )
    if raw.startswith('https://'):
        parts = urlsplit(raw)
        match = re.fullmatch(r'/trigger/[^/]*/(?:json/)?with/key/([A-Za-z0-9_-]+)', parts.path)
        if (parts.hostname != 'maker.ifttt.com' or parts.port is not None
                or parts.username or parts.password or parts.query or parts.fragment
                or not match):
            raise RuntimeError(
                'IFTTT_WEBHOOK_URL invalide : copier une URL Webhooks Documentation '
                '(sans guillemets), ou uniquement la cle.'
            )
        key = match.group(1)
    elif re.fullmatch(r'[A-Za-z0-9_-]{10,}', raw):
        key = raw
    else:
        raise RuntimeError(
            'IFTTT_WEBHOOK_URL n\'est ni une cle IFTTT ni une URL Webhooks reconnue.'
        )
    return f'https://maker.ifttt.com/trigger/race_radar_new/with/key/{key}'


def send(values):
    url = webhook_url()
    body = json.dumps({f'value{i}': v for i, v in enumerate(values, start=1)}, ensure_ascii=False).encode('utf-8')
    req = Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(req, timeout=20) as response:
            if not (200 <= response.status < 300):
                raise RuntimeError(f'IFTTT a renvoye HTTP {response.status}')
    except HTTPError as error:
        # Ne jamais inclure l'URL webhook (et donc la cle) dans les logs.
        if error.code in (401, 403):
            raise RuntimeError('IFTTT refuse la cle Webhook. La regenerer et mettre a jour le secret GitHub.') from None
        if error.code == 404:
            raise RuntimeError('Declencheur IFTTT introuvable : verifier l\'applet Webhooks race_radar_new.') from None
        raise RuntimeError(f'IFTTT a renvoye HTTP {error.code}.') from None
    except URLError:
        raise RuntimeError('Connexion a IFTTT impossible, reessayer plus tard.') from None


def main():
    current = load_events()
    state_exists = STATE_PATH.exists()
    if state_exists:
        old = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    else:
        old = {label: sorted(events) for label, events in current.items()}
        old['hyrox_registrations'] = {
            key: registration_key(event) for key, event in current['hyrox'].items()
        }
        save_state(old)
        print('Initialisation : courses actuelles mémorisées, aucune alerte historique envoyée.')

    if os.getenv('TEST_NOTIFICATION', '').strip().lower() == 'true':
        send(['TEST', 'GitHub Actions est bien connecté à IFTTT', 'RACE RADAR'])
        print('Notification TEST envoyée à IFTTT.')

    if state_exists:
        today = datetime.now(ZoneInfo('Europe/Paris')).date().isoformat()
        notify(current, old, today)


if __name__ == '__main__':
    main()
