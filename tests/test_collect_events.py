import importlib.util
import unittest
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location('collect_events', Path(__file__).resolve().parents[1] / 'scripts' / 'collect_events.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ParseTest(unittest.TestCase):
    TODAY = date(2026, 10, 30)
    MILES = 'https://fr.milesrepublic.com/trail/haut-rhin'

    def test_miles_confirmed(self):
        text = 'Trail du petit ballon 14 mars 2027 52 km, 23 km, 12 km Rouffach (68) À partir de 14 € Trail'
        e = m.parse_miles_card(text, 'https://fr.milesrepublic.com/event/trail-du-petit-ballon-1', self.TODAY)
        self.assertEqual((e['date'], e['city'], e['zone'], e['dist']), ('2027-03-14', 'Rouffach', 'sud', [12.0, 23.0, 52.0]))

    def test_miles_unconfirmed(self):
        text = 'Trail des casemates Date à confirmer février 2027 24 km Dangolsheim (67) Trail'
        self.assertIsNone(m.parse_miles_card(text, 'https://fr.milesrepublic.com/event/casemates-1', self.TODAY))

    def test_miles_ignores_outside_area(self):
        text = 'Les foulées du nord 10 avril 2027 12 km Haguenau (67) Running'
        self.assertIsNone(m.parse_miles_card(text, 'https://fr.milesrepublic.com/event/foulees-2', self.TODAY))

    def test_miles_html_card(self):
        html = '<html><body><a href="/event/test-20">Course de Strasbourg 9 mai 2027 10 km, 5 km Strasbourg (67) Running</a></body></html>'
        matches, seen = m.parse_miles(html, self.MILES, self.TODAY)
        self.assertEqual((len(matches), seen, matches[0]['date']), (1, 1, '2027-05-09'))

    def test_miles_parent_card(self):
        html = '<div class="card"><a href="/event/test-21">Course de Strasbourg</a><span>9 mai 2027 10 km Strasbourg (67)</span></div>'
        matches, seen = m.parse_miles(html, self.MILES, self.TODAY)
        self.assertEqual((len(matches), seen), (1, 1))

    def test_conflict_is_held_for_review(self):
        existing = {'running': [{'id':'r1','name':'Trail du petit ballon','city':'Rouffach','date':'2027-03-14'}]}
        new = {'id':'m1','name':'Trail du petit ballon','city':'Rouffach','date':'2027-03-13'}
        added, review = m.merge_candidates(existing, [new])
        self.assertEqual((added,len(review),len(existing['running'])),(0,1,1))

    def test_ffa_excludes_field_and_indoor_meetings_mislabelled_as_cross(self):
        names = ['Meeting 3 lancers PCA AV', 'Meeting De Lancers Longs',
                 'Meeting en salle U14 PCA ESRCAC', 'Meeting CDA 68 en salle à partir de U16',
                 'Meeting Indoor U 16', 'Meeting Perche en salle PCA ESRCAC']
        html = '<table>' + ''.join(
            f'<tr><td>28 novembre</td><td>{name}</td><td>Colmar 068 - G-E</td><td>Cross</td></tr>'
            for name in names + ['Cross de Colmar']) + '</table>'
        events, _ = m.parse_ffa(html, self.TODAY)
        self.assertEqual([event['name'] for event in events], ['Cross de Colmar'])

    def test_distinct_formats_and_multiday_events_do_not_conflict(self):
        a = {'name':'Trail Alsace by UTMB - Trail des Pèlerins','city':'Barr','date':'2027-05-15'}
        b = {'name':'Trail Alsace by UTMB - Trail des Celtes','city':'Barr','date':'2027-05-16'}
        self.assertFalse(m.is_conflicting_date(a, b))
        a = {'name':'Les 5 km de Molsheim','city':'Molsheim','date':'2027-05-29'}
        b = {'name':'Les 10 km de Molsheim','city':'Molsheim','date':'2027-05-30'}
        self.assertFalse(m.is_conflicting_date(a, b))
        a = {'name':'Trail du Grand Ballon — Hivernale','city':'Jungholtz','date':'2027-01-16','end':'2027-01-17'}
        b = {'name':"Trail du Grand Ballon - L'hivernale",'city':'Jungholtz','date':'2027-01-17'}
        self.assertTrue(m.equivalent_alsace(a, b))
        self.assertFalse(m.is_conflicting_date(a, b))

    def test_official_editions_survive_secondary_merges_and_replays(self):
        data = {'running':[]}
        self.assertEqual(m.apply_official_events(data), 7)
        self.assertEqual(m.apply_official_events(data), 0)
        original = next(e.copy() for e in data['running'] if e['id'] == 'aec-489641e0d032')
        secondary = dict(original, dist=[48.9], source='https://secondary.example')
        self.assertEqual(m.merge_alsace(data, [secondary]), (0, 0, []))
        self.assertEqual(next(e for e in data['running'] if e['id'] == original['id'])['dist'], [47])
        self.assertEqual(next(e for e in data['running'] if e['id'] == 'r26')['date'], '2027-05-30')

    def test_specific_format_repairs_distances_from_an_old_aggregate(self):
        semi = {'id':'semi','name':'Le Semi-Marathon de Colmar','city':'Colmar',
                'date':'2027-09-19','dist':[10,21.1,42.195]}
        candidate = dict(semi, dist=[21.1])
        data = {'running':[semi]}
        self.assertEqual(m.merge_alsace(data, [candidate]), (0,1,[]))
        self.assertEqual(semi['dist'], [21.1])
        self.assertEqual(m.merge_alsace(data, [candidate]), (0,0,[]))

    def test_ffa_parser_regional(self):
        html = '''<table><tr><td>08 novembre</td><td>Courses de Colmar</td><td>Colmar<br/>068 - G-E</td><td>Running</td></tr></table>'''
        events, seen = m.parse_ffa(html, self.TODAY)
        self.assertEqual((seen,len(events),events[0]['date']), (1,1,'2026-11-08'))

if __name__=='__main__':
    unittest.main()
