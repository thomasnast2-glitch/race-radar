const {test}=require('node:test');
const assert=require('node:assert/strict');
const p=require('../pricing.js');
test('distance bands have exclusive lower and inclusive upper limits',()=>{
  for(const [band,inside,outside] of [
    ['short',[.1,5],[5.01]],['ten',[5.01,10],[5,10.01]],
    ['half',[10.01,21.1],[10,21.11]],['marathon',[21.11,42.2],[21.1,42.21]],
    ['ultra',[42.21,100],[42.2]]]){
    for(const n of inside)assert.equal(p.matchesDistance({dist:[n]},band),true);
    for(const n of outside)assert.equal(p.matchesDistance({dist:[n]},band),false);
  }
});
test('multiple distances, missing distances and malformed values',()=>{
  assert.equal(p.matchesDistance({dist:[5,10,21.1]},'half'),true);
  for(const dist of [undefined,[],[null,'',0,-1,'abc',{},true,Infinity]]){
    assert.equal(p.matchesDistance({dist},'all'),true);
    assert.equal(p.matchesDistance({dist},'short'),false);
  }
  assert.deepEqual(p.distances({dist:['21,1',21.1,5]}),[21.1,5]);
});
test('official price wins only with a source, currency and matching edition',()=>{
  const e={id:'fixture',date:'2027-05-01',kind:'Route'};
  const entry={status:'official',amount:17.5,currency:'EUR',source:'https://example.org/tarifs',verifiedAt:'2026-11-15'};
  const data={events:{fixture:{eventDate:e.date,distances:{10:entry}}}};
  assert.equal(p.price(e,10,'running',data).amount,17.5);
  assert.equal(p.price(e,5,'running',data).status,'estimated');
  for(const patch of [{status:'estimated'},{source:''},{source:'javascript:alert(1)'},{amount:-1},{amount:'17'},{currency:'USD'}]){
    const bad=structuredClone(data);Object.assign(bad.events.fixture.distances[10],patch);
    assert.equal(p.price(e,10,'running',bad).status,'estimated');
  }
  assert.equal(p.price({...e,date:'2028-05-01'},10,'running',data).status,'estimated');
});
test('configurable estimates depend on discipline and distance; unknowns stay unavailable',()=>{
  assert.notDeepEqual(p.price({kind:'Route'},10,'running'),p.price({kind:'Trail'},10,'running'));
  for(const [sport,kinds] of Object.entries(p.RULES))for(const kind of Object.keys(kinds)){
    const a=p.price({kind},5,sport),b=p.price({kind},100,sport);
    assert.equal(a.status,'estimated');assert.ok(a.min<=a.max);assert.ok(b.min>a.min);
  }
  assert.equal(p.price({kind:'Inconnu'},10,'running').status,'unavailable');
  assert.equal(p.price({kind:'Route'},null,'running').status,'unavailable');
  assert.equal(p.price({kind:'HYROX'},8,'hyrox').status,'unavailable');
});
test('HYROX accepts only verified category records',()=>{
  const e={id:'h-fixture',date:'2027-01-01'};
  const data={events:{[e.id]:{eventDate:e.date,categories:{'Doubles Pro':{status:'official',amount:180,currency:'EUR',source:'https://example.org/tickets'}}}}};
  assert.equal(p.official(e,'Doubles Pro',data,true).amount,180);
  assert.equal(p.official(e,'Open',data,true),null);
});
