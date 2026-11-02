import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from scripts.watch_hyrox_news import parse_rss, merge_candidates, run

SAMPLE='''<rss version="2.0"><channel>
<item><title>HYROX Lyon 2027 : ouverture des inscriptions</title><link>https://news.google.com/rss/articles/a</link><pubDate>Sat, 31 Oct 2026 09:00:00 GMT</pubDate><source>Journal local</source></item>
<item><title>Festival musique à Lyon</title><link>https://news.google.com/rss/articles/b</link><pubDate>Sat, 31 Oct 2026 09:00:00 GMT</pubDate></item>
</channel></rss>'''
NOW=datetime(2026,11,1,tzinfo=timezone.utc)
class TestHyroxWatch(unittest.TestCase):
 def test_parse(self):
  events=parse_rss(SAMPLE,NOW);self.assertEqual(len(events),1);self.assertIn('A VERIFIER',events[0]['statut'])
 def test_duplicate(self):
  rows=parse_rss(SAMPLE,NOW);merged,new=merge_candidates(rows,[rows]);self.assertEqual(new,0);self.assertEqual(len(merged),1)
 def test_workflow_does_not_touch_events(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);events=p/'events.json';events.write_text('{"hyrox":[{"id":"h1"}]}')
   n,c=run(p/'hyrox_candidates.json',p/'hyrox_watch.json',fetch=lambda _: SAMPLE,now=NOW)
   self.assertEqual(n,3);self.assertEqual(c,1);self.assertEqual(json.loads(events.read_text()),{'hyrox':[{'id':'h1'}]})
 def test_if_all_feeds_fail(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)
   with self.assertRaises(RuntimeError):
    run(p/'hyrox_candidates.json',p/'hyrox_watch.json',fetch=lambda _: (_ for _ in ()).throw(OSError('offline')),now=NOW)
   self.assertFalse((p/'hyrox_watch.json').exists())

if __name__=='__main__':unittest.main()
