const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const http=require('node:http');
const fs=require('node:fs/promises');
const path=require('node:path');
let browser,server,base;
const root=path.resolve(__dirname,'..');
before(async()=>{
  server=http.createServer(async(req,res)=>{
    const name=new URL(req.url,'http://localhost').pathname;
    try{
      const file=path.resolve(root,'.'+(name==='/'?'/index.html':name));
      if(!file.startsWith(root+path.sep))throw Error('path');
      res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.json')?'application/json':'text/html');
      res.end(await fs.readFile(file));
    }catch(_){res.statusCode=404;res.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));base=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{});
});
after(async()=>{await browser?.close();await new Promise(resolve=>server?server.close(resolve):resolve());});
const running=[
  {id:'r-verified',name:'Trail vérifié',city:'Colmar',date:'2026-11-30',end:'2026-12-02',kind:'Trail',dist:[12,25],zone:'centre',source_type:'official',verified_at:'2026-11-22',source:'https://example.org/organisateur'},
  {id:'r-secondary',name:'Course secondaire',city:'Strasbourg',date:'2026-12-01',end:'2026-12-01',kind:'Route',dist:[10],zone:'nord',certainty:'confirmée',source:'https://example.org/calendrier'}
];
const hyrox=[{id:'h-test',name:'HYROX test',city:'Paris',date:'2026-11-30',end:'2026-12-01',status:'Voir billetterie',country:'FR',location:'France',url:'https://example.org/tickets'}];
const cycling=[
  {id:'cyc-dated',name:'Cyclo datée',city:'Évron',region:'Babybel',kind:'Gravel',dist:[63],date:'2026-12-01',end:'2026-12-01',sort:'2026-12-01',date_hint:'1 décembre 2026',source:'https://example.org/cyclo'},
  {id:'cyc-tentative',name:'Cyclo incertaine',city:'Annecy',region:'Annecy',kind:'Route',dist:[100],date:null,end:null,sort:'2026-12-05',date_hint:'Décembre 2026 à confirmer',source:'https://example.org/tentative'}
];
async function setup(viewport){
  const context=await browser.newContext({viewport});
  await context.route('**/*',async route=>{
    const url=route.request().url();if(!url.startsWith(base))return route.abort();
    if(url.includes('/events.json'))return route.fulfill({json:{running,hyrox,asOf:'2026-11-22'}});
    if(url.includes('/cycling.json'))return route.fulfill({json:{cycling,asOf:'2026-11-22'}});
    if(url.includes('/pricing.json'))return route.fulfill({json:{version:1,events:{}}});
    return route.continue();
  });
  const page=await context.newPage();await page.clock.setFixedTime(new Date('2026-11-22T12:00:00Z'));
  // Simuler de vrais anciens favoris, y compris un ID absent des données actuelles.
  await page.addInitScript(()=>{
    if(!localStorage.getItem('fixture-seeded')){
      localStorage.setItem('race-radar-favorites',JSON.stringify(['r-verified','h-test','archived-id']));
      localStorage.setItem('fixture-seeded','yes');
    }
  });
  return {context,page};
}
for(const viewport of [{width:1280,height:900},{width:390,height:844},{width:320,height:740}]){
  test(`reliability, legacy favorite statuses and monthly calendar at ${viewport.width}px`,async()=>{
    const {context,page}=await setup(viewport),errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base);await page.waitForSelector('.event');
    const card=page.locator('[data-event-id="r-verified"]');
    assert.match(await card.locator('.reliability').textContent(),/Vérifié sur le site officiel.*22 novembre 2026/s);
    assert.match(await page.locator('[data-event-id="r-secondary"] .reliability').textContent(),/À confirmer/);
    assert.equal(await card.locator('select').inputValue(),'interested');
    assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('race-radar-favorites'))),['r-verified','h-test','archived-id']);
    await card.locator('.favorite-status').click({position:{x:10,y:5}});
    assert.equal(await page.locator('dialog').evaluate(e=>e.open),false);
    await card.locator('select').selectOption('goal');
    assert.equal(await card.locator('select').evaluate(e=>e===document.activeElement),true);
    await card.locator('[data-details]').click();
    assert.equal(await page.locator('#detail-favorite select').inputValue(),'goal');
    assert.equal(await page.getByRole('link',{name:'Source de la vérification'}).getAttribute('href'),'https://example.org/organisateur');
    await page.locator('#detail-favorite select').selectOption('registered');
    assert.match(await page.locator('.detail-planner').textContent(),/ne réalise aucune inscription/);
    await page.keyboard.press('Escape');await page.reload();await page.waitForSelector('.event');
    assert.equal(await card.locator('select').inputValue(),'registered');
    await page.getByRole('button',{name:'Calendrier mensuel',exact:true}).click();
    assert.equal(await page.locator('.filters').isVisible(),false);
    assert.match(await page.locator('#calendar-month').textContent(),/novembre 2026/);
    assert.equal(await page.locator('.calendar-day [data-calendar-event="r-verified"]').count(),1);
    assert.equal(await page.locator('.calendar-day [data-calendar-event="h-test"]').count(),1);
    assert.equal(await page.locator('.calendar-day [data-calendar-event="cyc-tentative"]').count(),0);
    assert.equal(await page.locator('#calendar-undated [data-calendar-event="cyc-tentative"]').count(),1);
    await page.getByRole('button',{name:'Mois suivant'}).click();
    assert.match(await page.locator('#calendar-month').textContent(),/décembre 2026/);
    assert.equal(await page.locator('.calendar-day [data-calendar-event="r-verified"]').count(),2);
    assert.equal(await page.locator('.calendar-day [data-calendar-event="h-test"]').count(),1);
    assert.equal(await page.locator('.calendar-day [data-calendar-event="cyc-dated"]').count(),1);
    assert.equal(await page.locator('.calendar-day:has(time[datetime="2026-12-01"]) .calendar-event').count(),4);
    if(process.env.SCREENSHOT_DIR)await page.locator('#calendar-panel').screenshot({path:path.join(process.env.SCREENSHOT_DIR,'calendar-'+viewport.width+'.png')});
    assert.match(await page.locator('.calendar-day .hyrox-card').first().evaluate(e=>getComputedStyle(e).backgroundColor),/13, 23, 30/);
    await page.selectOption('#calendar-scope','favorites');
    assert.equal(await page.locator('.calendar-day [data-calendar-event="cyc-dated"]').count(),0);
    assert.match(await page.locator('.calendar-day [data-calendar-event="r-verified"]').first().textContent(),/Inscrit/);
    await page.selectOption('#calendar-scope','cycling');
    assert.equal(await page.locator('.calendar-day [data-calendar-event="h-test"]').count(),0);
    const cycle=page.locator('.calendar-day [data-calendar-event="cyc-dated"]');
    await cycle.focus();await page.keyboard.press('Enter');
    await page.getByRole('button',{name:'Ajouter aux favoris'}).click();
    await page.locator('#detail-favorite select').selectOption('goal');
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>document.activeElement?.dataset.calendarEvent==='cyc-dated');
    assert.match(await cycle.textContent(),/Objectif principal/);
    const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('race-radar-favorites')));
    assert.deepEqual(saved,['r-verified','h-test','archived-id','cyc-dated']);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.getByRole('button',{name:'Ce mois-ci',exact:true}).click();
    assert.match(await page.locator('#calendar-month').textContent(),/novembre 2026/);
    assert.equal(await page.locator('#calendar-empty').isVisible(),true);
    await page.locator('[data-tab="favorites"]').click();
    assert.equal(await page.locator('#calendar-panel').isVisible(),false);
    assert.equal(await page.locator('.event').count(),3);
    assert.match(await page.locator('.event.hyrox-card').evaluate(e=>getComputedStyle(e).backgroundColor),/13, 23, 30/);
    await page.locator('[data-event-id="r-verified"] .fav').click();
    assert.equal(await page.locator('[data-event-id="r-verified"]').count(),0);
    assert.ok((await page.evaluate(()=>JSON.parse(localStorage.getItem('race-radar-favorites')))).includes('archived-id'));
    assert.deepEqual(errors,[]);await context.close();
  });
}
test('status updates propagate across browser tabs',async()=>{
  const {context,page}=await setup({width:1280,height:900});
  await page.goto(base);await page.waitForSelector('.event');
  const second=await context.newPage();await second.goto(base);await second.waitForSelector('.event');
  await second.locator('[data-event-id="r-verified"] select').selectOption('goal');
  await page.waitForFunction(()=>document.querySelector('[data-event-id="r-verified"] select').value==='goal');
  await context.close();
});
test('blocked persistence keeps the chosen status during the visit and reports the limitation',async()=>{
  const {context,page}=await setup({width:390,height:844});
  await page.goto(base);await page.waitForSelector('.event');
  await page.evaluate(()=>{Storage.prototype.setItem=()=>{throw new Error('Storage blocked');};});
  await page.locator('[data-event-id="r-verified"] select').selectOption('goal');
  assert.match(await page.locator('#planner-feedback').textContent(),/pendant cette visite/);
  await page.locator('[data-tab="favorites"]').click();
  assert.equal(await page.locator('[data-event-id="r-verified"] select').inputValue(),'goal');
  await context.close();
});
