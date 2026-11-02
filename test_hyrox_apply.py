import unittest
from scripts.apply_hyrox_updates import apply
class TestApply(unittest.TestCase):
 def test_empty_keeps_data(self):
  data={'running':[{'id':'r1'}],'hyrox':[{'id':'h1','status':'Voir billetterie','open_date':None}],'asOf':'2026-10-29'}
  out,n=apply(data,{'updates':[]},'2026-11-01')
  self.assertEqual(n,0);self.assertEqual(len(out['hyrox']),1);self.assertEqual(len(out['running']),1)
 def test_validated_open(self):
  data={'running':[],'hyrox':[{'id':'h7','name':'HYROX Lyon','date':'2027-05-12','open_date':None}]}
  out,n=apply(data,{'updates':[{'id':'h7','registration':'announced','open_date':'2026-11-15','category':'Doubles Pro','source_url':'https://hyrox.com/event/hyrox-lyon-s26-27/'}]},'2026-11-01')
  self.assertEqual(n,1);self.assertEqual(out['hyrox'][0]['open_date'],'2026-11-15')
 def test_reject_unverified_date(self):
  data={'hyrox':[{'id':'h7'}]}
  with self.assertRaises(ValueError):
   apply(data,{'updates':[{'id':'h7','registration':'announced','open_date':'demain','source_url':'https://hyrox.com/event/foo/'}]},'2026-11-01')
if __name__=='__main__':unittest.main()
