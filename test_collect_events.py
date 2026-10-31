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

    def test_ffa_parser_regional(self):
        html = '''<table><tr><td>08 novembre</td><td>Courses de Colmar</td><td>Colmar<br/>068 - G-E</td><td>Running</td></tr></table>'''
        events, seen = m.parse_ffa(html, self.TODAY)
        self.assertEqual((seen,len(events),events[0]['date']), (1,1,'2026-11-08'))

    def test_discover_official_calendar_links(self):
        html = '<html><a href="/calendrier_running_2027.xlsx">Calendrier running 2027</a><iframe src="https://docs.google.com/spreadsheets/d/example/pubhtml"></iframe></html>'
        links = m.discover_calendar_links(html, 'https://cd68.athle.fr/calendar')
        self.assertEqual(len(links), 2)
        self.assertTrue(links[0]['url'].startswith('https://cd68.athle.fr/'))

    def test_excludes_unrelated_links(self):
        links = m.discover_calendar_links('<a href="/contact">Contact</a>', 'https://running67.fr/running.html')
        self.assertEqual(links, [])

if __name__=='__main__':
    unittest.main()
