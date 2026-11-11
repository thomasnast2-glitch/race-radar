#!/usr/bin/env python3
"""RACE RADAR -> IFTTT: une alerte par rubrique et par detection, sans doublon.

Premiere execution : initialise l'historique, sans notifier les courses deja connues.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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
    STATE_PATH.write_text(
        json.dumps({key: sorted(values) for key, values in state.items()},
                   ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )


def send(values):
    url = os.getenv('IFTTT_WEBHOOK_URL', '').strip()
    if not url.startswith('https://maker.ifttt.com/trigger/race_radar_new/with/key/'):
        raise RuntimeError('Secret IFTTT_WEBHOOK_URL manquant ou URL incorrecte : verifier GitHub Settings > Secrets')
    body = json.dumps({f'value{i}': v for i, v in enumerate(values, start=1)}, ensure_ascii=False).encode('utf-8')
    req = Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(req, timeout=20) as response:
        if not (200 <= response.status < 300):
            raise RuntimeError(f'IFTTT a renvoye HTTP {response.status}')


def main():
    current = load_events()
    state_exists = STATE_PATH.exists()
    if state_exists:
        old = json.loads(STATE_PATH.read_text(encoding='utf-8'))
        seen = {key: set(old.get(key, [])) for key in current}
    else:
        seen = {key: set(events) for key, events in current.items()}
        save_state(seen)
        print('Initialisation : courses actuelles memorisees, aucune alerte historique envoyee.')

    if os.getenv('TEST_NOTIFICATION', '').strip().lower() == 'true':
        send(['TEST', 'GitHub Actions est bien connecte a IFTTT', 'RACE RADAR'])
        print('Notification TEST envoyee a IFTTT.')

    if not state_exists:
        return

    today = datetime.now(ZoneInfo('Europe/Paris')).date().isoformat()
    for label, _, _, title in SOURCES:
        events = current[label]
        new_keys = set(events) - seen[label]
        new_futures = [events[key] for key in new_keys if str(events[key].get('date', '')) >= today]
        new_futures.sort(key=lambda e: (e.get('date', ''), e.get('name', '')))
        if new_futures:
            first = new_futures[0]
            count = len(new_futures)
            desc = f"{first['name']} - {first.get('city', '?')} - {first.get('date', '?')}"
            if count > 1:
                desc += f' (+{count - 1} autres)'
            values = [f'{count} nouvelle(s) course(s) {title}', desc[:240],
                      str(first.get('source') or first.get('url') or 'RACE RADAR')[:500]]
            send(values)
            print(f'IFTTT : {count} nouveaute(s) {title} notifiee(s).')
        else:
            print(f'IFTTT : aucune nouvelle course {title}.')
        # Garde aussi les courses passees pour eviter une fausse alerte ulterieure.
        seen[label].update(new_keys)
    save_state(seen)


if __name__ == '__main__':
    main()
