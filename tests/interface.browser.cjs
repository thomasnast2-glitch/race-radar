const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const http=require('node:http');
const fs=require('node:fs/promises');
const path=require('node:path');
let server,browser,base;
const root=path.resolve(__dirname,'..');
before(async()=>{
  server=http.createServer(async(req,res)=>{
    const name=new URL(req.url,'http://localhost').pathname;
    try{
      const target=path.resolve(root,'.'+(name==='/'?'/index.html':name));
      if(!target.startsWith(root+path.sep))throw Error('path');
      res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.json')?'application/json':'text/html');
      res.end(await fs.readFile(target));
    }catch(_){res.statusCode=404;res.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  base=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{});
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?server.close(resolve):resolve());});
const running=[
  {id:'fixture-multi',name:'Course multiple',city:'Colmar',kind:'Route',dist:[5,10,21.1],zone:'centre',date:'2027-05-01',end:'2027-05-01',source:'https://example.org/inscription'},
  {id:'fixture-empty',name:'Distance inconnue',city:'Colmar',kind:'Route',dist:[],zone:'centre',date:'2027-05-01',end:'2027-05-01',source:'https://example.org'},
  {id:'fixture-trail',name:'Trail long',city:'Strasbourg',kind:'Trail',dist:[52],zone:'nord',date:'2027-06-01',end:'2027-06-01',source:'https://example.org'}
];
const hyrox=[{id:'h-fixture',name:'HYROX test',city:'Paris',country:'FR',location:'France',status:'non annoncée',date:'2027-07-01',end:'2027-07-01',url:'https://example.org/tickets'}];
const cycling=[{id:'cyc-fixture',name:'Gravel test',city:'Évron',kind:'Gravel',region:'Babybel',dist:[41,63],date:null,end:null,sort:'2027-05-01',date_hint:'Mai 2027 à confirmer',source:'https://example.org/cyclo'}];
for(const viewport of [{width:1280,height:900},{width:390,height:844},{width:320,height:740}]){
  test(`filters, details, colors and actions at ${viewport.width}px`,async()=>{
    const context=await browser.newContext({viewport,acceptDownloads:true});
    const page=await context.newPage();const errors=[];
    await page.clock.setFixedTime(new Date('2026-11-15T12:00:00Z'));
    page.on('pageerror',e=>errors.push(e.message));
    await context.route('**/*',async route=>{
      const url=route.request().url();
      if(!url.startsWith(base))return route.abort();
      if(url.includes('/events.json'))return route.fulfill({json:{running,hyrox,asOf:'2026-11-15'}});
      if(url.includes('/cycling.json'))return route.fulfill({json:{cycling,asOf:'2026-11-15'}});
      if(url.includes('/pricing.json'))return route.fulfill({json:{version:1,events:{'fixture-multi':{eventDate:'2027-05-01',distances:{10:{status:'official',amount:17.5,currency:'EUR',source:'https://example.org/tarifs',verifiedAt:'2026-11-15'}}}}}});
      return route.continue();
    });
    await page.goto(base);
    await page.waitForFunction(()=>document.querySelectorAll('.event').length===3);
    for(const text of ['🏃 RUNNING','🏋️ HYROX','🚴 CYCLO','♡ FAVORIS'])assert.ok(await page.getByRole('button',{name:new RegExp(text)}).count());
    assert.equal(await page.locator('#nav-runcount').textContent(),'3');
    for(const band of ['short','ten','half']){
      await page.selectOption('#distance',band);assert.equal(await page.locator('.event').count(),1);
      assert.match(await page.locator('.event h3').textContent(),/multiple/);
    }
    await page.selectOption('#kind','Trail');assert.equal(await page.locator('.event').count(),0);
    await page.selectOption('#kind','Route');await page.selectOption('#zone','nord');assert.equal(await page.locator('.event').count(),0);
    await page.selectOption('#zone','centre');await page.selectOption('#period','2026');assert.equal(await page.locator('.event').count(),0);
    await page.selectOption('#period','2027');await page.fill('#search','inconnue');assert.equal(await page.locator('.event').count(),0);
    await page.getByRole('button',{name:'Effacer les filtres'}).click();
    assert.equal(await page.locator('#distance').inputValue(),'all');assert.equal(await page.locator('.event').count(),3);
    const card=page.locator('[data-event-id="fixture-multi"]');
    await card.locator('.location').click();assert.equal(await page.locator('dialog').evaluate(e=>e.open),true);
    assert.match(await page.locator('#details-content').textContent(),/Tarif officiel.*15 novembre 2026/s);
    assert.match(await page.locator('#details-content').textContent(),/17,50/);
    assert.match(await page.locator('#details-content').textContent(),/Tarif estimé — non officiel/);
    assert.equal(await page.getByRole('link',{name:'Source du tarif'}).getAttribute('href'),'https://example.org/tarifs');
    if(process.env.SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR,'details-'+viewport.width+'.png')});
    await page.keyboard.press('Escape');assert.equal(await page.locator('dialog').evaluate(e=>e.open),false);
    await page.waitForFunction(()=>document.activeElement?.dataset.details==='fixture-multi');
    await page.keyboard.press('Enter');await page.keyboard.press('Shift+Tab');
    assert.equal(await page.locator('dialog').evaluate(e=>e.contains(document.activeElement)),true);
    await page.getByRole('button',{name:'Fermer la fiche'}).click();
    await card.locator('.fav').click();assert.equal(await page.locator('dialog').evaluate(e=>e.open),false);
    assert.ok((await page.evaluate(()=>JSON.parse(localStorage.getItem('race-radar-favorites')))).includes('fixture-multi'));
    const downloadPromise=page.waitForEvent('download');await card.getByRole('button',{name:'Calendrier'}).click();
    assert.match((await downloadPromise).suggestedFilename(),/\.ics$/);assert.equal(await page.locator('dialog').evaluate(e=>e.open),false);
    const popupPromise=page.waitForEvent('popup');await card.getByRole('link').click();const popup=await popupPromise;await popup.close();
    assert.equal(await page.locator('dialog').evaluate(e=>e.open),false);
    const runningBackground=await card.evaluate(e=>getComputedStyle(e).backgroundColor);assert.equal(runningBackground,'rgb(255, 255, 255)');
    await page.locator('[data-tab="hyrox"]').click();assert.equal(await page.locator('#distance').isVisible(),false);
    const hy=page.locator('.event.hyrox-card');const dark=await hy.evaluate(e=>getComputedStyle(e).backgroundColor);assert.equal(dark,'rgb(13, 23, 30)');
    await hy.locator('.fav').click();await hy.locator('[data-details]').click();
    assert.match(await page.locator('#details-content').textContent(),/Tarif à consulter sur la billetterie officielle/);
    await page.keyboard.press('Escape');
    await page.locator('[data-tab="cycling"]').click();assert.equal(await page.locator('#distance').isVisible(),false);
    await page.locator('.cycling-card .fav').click();await page.locator('.cycling-card [data-details]').click();
    assert.match(await page.locator('#details-content').textContent(),/41 km.*63 km/s);
    await page.keyboard.press('Escape');assert.equal(await page.locator('.cycling-card .event-bottom button').isDisabled(),true);
    await page.locator('[data-tab="favorites"]').click();assert.equal(await page.locator('#distance').isVisible(),false);
    assert.equal(await page.locator('.event').count(),3);
    assert.equal(await page.locator('.event.hyrox-card').evaluate(e=>getComputedStyle(e).backgroundColor),dark);
    assert.match(await page.locator('.event.cycling-card').evaluate(e=>getComputedStyle(e).backgroundImage),/gradient/);
    await page.reload();await page.locator('[data-tab="favorites"]').click();await page.waitForFunction(()=>document.querySelectorAll('.event').length===3);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.locator('[data-tab="running"]').click();await page.locator('[data-event-id="fixture-empty"] [data-details]').click();
    assert.match(await page.locator('#details-content').textContent(),/Distances non renseignées/);
    assert.equal(await page.locator('dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
    assert.deepEqual(errors,[]);
    await context.close();
  });
}
test('running status exposes degraded collectors and date conflicts',async()=>{
  const context=await browser.newContext();const page=await context.newPage();
  await page.clock.setFixedTime(new Date('2026-11-22T12:00:00Z'));
  await context.route('**/events.json*',route=>route.fulfill({json:{running,hyrox,
    collectionStatus:[{status:'ok'},{status:'unavailable'},{status:'unavailable'}]}}));
  await context.route('**/source_watch.json*',route=>route.fulfill({json:{checkedAt:'2026-11-22',sources:[{status:'links_found'}]}}));
  await context.route('**/review_candidates.json*',route=>route.fulfill({json:{conflicts:[{}, {}, {}, {}, {}]}}));
  await page.goto(base);
  await page.waitForFunction(()=>document.getElementById('radar-running').textContent.includes('5 conflit'));
  assert.match(await page.locator('#radar-running').textContent(),/2 collecte/);
  assert.equal(await page.locator('#radar-running').evaluate(e=>e.classList.contains('radar-warning')),true);
  await context.close();
});

test('missing pricing file preserves events and estimates',async()=>{
  const context=await browser.newContext();const page=await context.newPage();
  await page.clock.setFixedTime(new Date('2026-11-15T12:00:00Z'));
  await context.route('**/pricing.json*',route=>route.fulfill({status:404,body:''}));
  await page.goto(base);await page.waitForSelector('.event');await page.locator('.event [data-details]').first().click();
  assert.match(await page.locator('#details-content').textContent(),/tarifs vérifiés sont momentanément indisponibles/);
  assert.ok(await page.locator('.event').count()>0);await context.close();
});
test('verified HYROX category appears without estimating other categories',async()=>{
  const context=await browser.newContext();const page=await context.newPage();
  await page.clock.setFixedTime(new Date('2026-11-15T12:00:00Z'));
  await context.route('**/events.json*',route=>route.fulfill({json:{running,hyrox,asOf:'2026-11-15'}}));
  await context.route('**/pricing.json*',route=>route.fulfill({json:{version:1,events:{'h-fixture':{eventDate:'2027-07-01',categories:{'Doubles Pro':{status:'official',amount:180,currency:'EUR',source:'https://example.org/tickets'},'Open':{status:'estimated',amount:90,currency:'EUR',source:'https://example.org'}}}}}}));
  await page.goto(base);await page.locator('[data-tab="hyrox"]').click();
  await page.locator('.event.hyrox-card [data-details]').click();
  assert.match(await page.locator('#details-content').textContent(),/Doubles Pro.*180,00.*Tarif officiel/s);
  assert.doesNotMatch(await page.locator('#details-content').textContent(),/Open|Tarif estimé/);
  await context.close();
});
