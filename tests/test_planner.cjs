const {test}=require('node:test');
const assert=require('node:assert/strict');
const p=require('../planner-model.js');
const now=new Date('2026-11-22T12:00:00Z');
test('verified badge requires explicit official evidence, date and safe source',()=>{
  const official={source_type:'official',verified_at:'2026-11-22',source:'https://example.org/race'};
  assert.equal(p.reliability(official,now).verified,true);
  assert.equal(p.reliability(official,now).date,'2026-11-22');
  for(const event of [{certainty:'confirmée',verified:'2026-11-22',source:official.source},
    {...official,source_type:'calendar'},{...official,verified_at:null},
    {...official,verified_at:'2026-02-30'},{...official,verified_at:'2026-11-23'},
    {...official,source:'javascript:alert(1)'},{url:'https://hyrox.com/event',registration_verified_at:'2026-11-22'}]){
    assert.equal(p.reliability(event,now).verified,false);
    assert.equal(p.reliability(event,now).label,'À confirmer');
  }
});
test('legacy favorites receive interested status without rewriting their IDs',()=>{
  const legacy=['r1','h1','cyc-1'],statuses=p.readStatuses(null);
  assert.deepEqual(legacy.map(id=>p.statusFor(statuses,id)),['interested','interested','interested']);
  assert.deepEqual(legacy,['r1','h1','cyc-1']);
});
test('malformed status storage is tolerated and unrecognized values are ignored',()=>{
  for(const raw of ['null','[]','false','broken'])assert.equal(Object.keys(p.readStatuses(raw)).length,0);
  const statuses=p.readStatuses('{"r1":"registered","h1":"goal","other":"invented","__proto__":"goal"}');
  assert.equal(p.statusFor(statuses,'r1'),'registered');assert.equal(p.statusFor(statuses,'h1'),'goal');
  assert.equal(p.statusFor(statuses,'other'),'interested');assert.equal({}.polluted,undefined);
});
test('month navigation crosses years and includes leap days',()=>{
  assert.equal(p.shiftMonth('2026-12',1),'2027-01');assert.equal(p.shiftMonth('2027-01',-1),'2026-12');
  assert.equal(p.monthDays('2028-02',[]).length,29);assert.equal(p.monthDays('2027-02',[]).length,28);
  assert.deepEqual(p.monthDays('bad',[]),[]);assert.equal(p.shiftMonth('2027-13',1),null);
});
test('calendar includes each day of intervals crossing month boundaries, never tentative sort dates',()=>{
  const events=[{id:'span',date:'2027-04-30',end:'2027-05-02'},
    {id:'single',date:'2027-05-03'}, {id:'unknown',date:null,sort:'2027-05-01'},
    {id:'invalid',date:'2027-02-30'}, {id:'reversed',date:'2027-05-04',end:'2027-05-01'}];
  const days=p.monthDays('2027-05',events);
  assert.deepEqual(days[0].events.map(e=>e.id),['span']);assert.deepEqual(days[1].events.map(e=>e.id),['span']);
  assert.deepEqual(days[2].events.map(e=>e.id),['single']);assert.deepEqual(days[3].events.map(e=>e.id),['reversed']);
  assert.equal(days.some(d=>d.events.some(e=>e.id==='unknown'||e.id==='invalid')),false);
});
