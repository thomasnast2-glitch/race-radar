import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import notify_ifttt as notifier


class NotificationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'state.json'
        self.patch = patch.object(notifier, 'STATE_PATH', self.state)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.event = {'id': 'h7', 'name': 'HYROX Lyon', 'date': '2027-05-12',
                      'end': '2027-05-16', 'status': 'Ouverture annoncée — Doubles Pro',
                      'open_date': '2026-11-15', 'registration_category': 'Doubles Pro',
                      'registration_verified_at': '2026-11-12',
                      'registration_source': 'https://hyrox.com/event/hyrox-lyon/'}

    def current(self, hyrox=None):
        return {'running': {}, 'hyrox': hyrox or {'h7': self.event}, 'cycling': {}}

    def old(self):
        return {'running': [], 'hyrox': ['h7'], 'cycling': []}

    def test_migrate_without_historical_alert(self):
        sent = []
        notifier.notify(self.current(), self.old(), '2026-11-12', sent.append)
        self.assertEqual(sent, [])
        self.assertIn('h7', json.loads(self.state.read_text(encoding='utf-8'))['hyrox_registrations'])

    def test_opening_change_is_notified_once(self):
        old = self.old()
        old['hyrox_registrations'] = {'h7': None}
        sent = []
        notifier.notify(self.current(), old, '2026-11-12', sent.append)
        self.assertEqual(len(sent), 1)
        self.assertIn('Doubles Pro', sent[0][1])
        self.assertIn('2026-11-15', sent[0][1])
        notifier.notify(self.current(), json.loads(self.state.read_text(encoding='utf-8')), '2026-11-12', sent.append)
        self.assertEqual(len(sent), 1)

    def test_verification_date_alone_does_not_alert(self):
        old = self.old()
        old['hyrox_registrations'] = {'h7': notifier.registration_key(self.event)}
        self.event['registration_verified_at'] = '2026-11-13'
        sent = []
        notifier.notify(self.current(), old, '2026-11-13', sent.append)
        self.assertEqual(sent, [])

    def test_unverified_and_spoofed_sources_do_not_alert(self):
        for source in ['', 'https://hyrox.com.evil.test/event/foo', 'https://hyrox.com/find-my-race/']:
            self.event['registration_source'] = source
            self.assertIsNone(notifier.registration_key(self.event))

    def test_failed_category_is_retried_without_repeating_success(self):
        current = self.current()
        current['running'] = {'r1': {'name': 'Course', 'date': '2027-01-01'}}
        old = self.old()
        old['hyrox_registrations'] = {'h7': None}
        sent = []
        def delivery(values):
            if 'HYROX' in values[0]:
                raise OSError('offline')
            sent.append(values)
        with self.assertRaises(OSError):
            notifier.notify(current, old, '2026-11-12', delivery)
        saved = json.loads(self.state.read_text(encoding='utf-8'))
        self.assertIn('r1', saved['running'])
        self.assertIsNone(saved['hyrox_registrations']['h7'])
        notifier.notify(current, saved, '2026-11-12', sent.append)
        self.assertEqual(len(sent), 2)
        self.assertIn('HYROX', sent[1][0])

    def test_past_events_are_silent_and_multiday_events_are_upcoming(self):
        self.assertFalse(notifier.upcoming({'date': '2026-10-01'}, '2026-11-12'))
        self.assertTrue(notifier.upcoming({'date': '2026-11-10', 'end': '2026-11-15'}, '2026-11-12'))

    def test_new_cycling_with_unconfirmed_day(self):
        current = self.current()
        current['cycling'] = {'cyc-new': {'name': 'Cyclo', 'sort': '2027-06-99', 'date_hint': 'Juin 2027 à confirmer'}}
        sent = []
        notifier.notify(current, self.old(), '2026-11-12', sent.append)
        self.assertEqual(len(sent), 1)
        self.assertIn('à confirmer', sent[0][1])


    def test_webhook_formats_normalised_without_exposing_key(self):
        from unittest.mock import patch
        key = 'ExampleKey12345'
        samples = [
            key,
            f'https://maker.ifttt.com/trigger/race_radar_new/with/key/{key}',
            f'https://maker.ifttt.com/trigger//json/with/key/{key}',
            f'https://maker.ifttt.com/trigger/test/json/with/key/{key}',
        ]
        for raw in samples:
            with self.subTest(raw=raw.split('/')[0]), patch.dict('os.environ', {'IFTTT_WEBHOOK_URL': raw}):
                self.assertEqual(
                    notifier.webhook_url(),
                    f'https://maker.ifttt.com/trigger/race_radar_new/with/key/{key}'
                )

    def test_invalid_webhook_rejected_without_leaking_secret(self):
        from unittest.mock import patch
        raw = 'https://not-ifttt.example/trigger/race_radar_new/with/key/Sensitive123'
        with patch.dict('os.environ', {'IFTTT_WEBHOOK_URL': raw}):
            with self.assertRaises(RuntimeError) as caught:
                notifier.webhook_url()
        self.assertNotIn('Sensitive123', str(caught.exception))



if __name__ == '__main__':
    unittest.main()
