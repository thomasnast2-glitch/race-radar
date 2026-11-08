import importlib.util
from pathlib import Path
from datetime import datetime,timezone
from email.utils import format_datetime
import tempfile, json, unittest
m_path=Path(__file__).parent/'watch_hyrox_news.py'
spec=importlib.util.spec_from_file_location('watcher',m_path)
watcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)
class HyroxFilterTests(unittest.TestCase):
    def test_guide_is_ignored(self):
        self.assertFalse(watcher.relevant_title('HYROX : le guide complet pour attaquer la saison 2026-2027 - Red Bull'))
    def test_training_article_ignored(self):
        self.assertFalse(watcher.relevant_title('HYROX Lyon 2027 : tout savoir pour préparer sa course - Red Bull'))
    def test_old_irrelevant_article_ignored(self):
        self.assertFalse(watcher.relevant_title('HYROX polémique : jusqu’au bout malgré une diarrhée'))
    def test_opening_fr(self):
        self.assertTrue(watcher.relevant_title('HYROX Lyon : ouverture des inscriptions le 12 décembre'))
    def test_opening_la(self):
        self.assertTrue(watcher.relevant_title('HYROX Strasbourg : lancement de la billetterie demain'))
    def test_open_sales(self):
        self.assertTrue(watcher.relevant_title('HYROX Toulouse : billets en vente dès lundi'))
    def test_new_competition(self):
        self.assertTrue(watcher.relevant_title('HYROX Marseille : nouvelle date annoncée'))
    def test_registration_en(self):
        self.assertTrue(watcher.relevant_title('HYROX Zurich : registration opens next Friday'))
    def test_complete_not_sold_out(self):
        self.assertFalse(watcher.relevant_title('HYROX : guide complet de la saison'))
    def test_sold_out(self):
        self.assertTrue(watcher.relevant_title('HYROX Paris : sold out en quelques minutes'))
    def test_existing_candidates_cleaned(self):
        guide={'id':'a','titre':'HYROX : le guide complet pour attaquer la saison 2026-2027'}
        opening={'id':'b','titre':'HYROX Lyon : ouverture des inscriptions'}
        merged,new=watcher.merge_candidates([guide,opening],[])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]['id'],'b')
        self.assertEqual(new,0)
    def test_rss_filters_guide(self):
        now=datetime(2026,11,8,tzinfo=timezone.utc)
        xml='''<rss version="2.0"><channel>
          <item><title>HYROX : le guide complet pour attaquer la saison 2026-2027 - Red Bull</title><link>https://news.google.com/rss/articles/a</link><pubDate>Sun, 08 Nov 2026 08:00:00 GMT</pubDate></item>
          <item><title>HYROX Lyon : ouverture des inscriptions vendredi</title><link>https://news.google.com/rss/articles/b</link><pubDate>Sun, 08 Nov 2026 08:00:00 GMT</pubDate></item>
        </channel></rss>'''
        res=watcher.parse_rss(xml,now)
        self.assertEqual(len(res),1)
        self.assertIn('ouverture',res[0]['titre'])
    def test_run_does_not_change_events(self):
        now=datetime(2026,11,8,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            cand=td/'hyrox_candidates.json'
            status=td/'hyrox_watch.json'
            events=td/'events.json'
            events.write_text('{"hyrox": ["unchanged"]}')
            cand.write_text(json.dumps([{'id':'old','titre':'HYROX guide complet saison 2026-2027'}]))
            xml='''<rss version="2.0"><channel><item><title>HYROX Lyon : ouverture des inscriptions vendredi</title><link>https://news.google.com/rss/articles/b</link><pubDate>Sun, 08 Nov 2026 08:00:00 GMT</pubDate></item></channel></rss>'''
            sources, news=watcher.run(cand,status,fetch=lambda url:xml,now=now)
            self.assertEqual(sources,3)
            self.assertEqual(news,1)
            self.assertEqual(len(json.loads(cand.read_text())),1)
            self.assertEqual(events.read_text(),'{"hyrox": ["unchanged"]}')
if __name__=='__main__': unittest.main()
