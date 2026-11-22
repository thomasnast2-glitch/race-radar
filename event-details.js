let PRICING={version:1,events:{}};
let pricingUnavailable=false,detailOpener=null,detailEventId=null;
const detailsDialog=$('event-dialog');
const euro=n=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR',maximumFractionDigits:2}).format(n);
function priceMarkup(p){
  if(p.status==='official'){
    const verified=/^\d{4}-\d{2}-\d{2}$/.test(p.verifiedAt||'')?` · Vérifié le ${safe(formatDate(p.verifiedAt))}`:'';
    return `<strong>${safe(euro(p.amount))}</strong><small>Tarif officiel${verified}</small><a href="${safe(p.source)}" target="_blank" rel="noopener noreferrer">Source du tarif ↗</a>`;
  }
  if(p.status==='estimated')return `<strong>${safe(euro(p.min))} – ${safe(euro(p.max))}</strong><small>Tarif estimé — non officiel</small>`;
  return '<span>Tarif à vérifier auprès de l’organisateur</span>';
}
function openDetails(id,opener){
  const bike=CYCLING.cycling.find(e=>e.id===id),hy=DATA.hyrox.find(e=>e.id===id);
  const e=bike||hy||DATA.running.find(e=>e.id===id);if(!e)return;
  if(!detailsDialog.open)detailOpener=opener;
  detailEventId=id;
  detailsDialog.className='details-dialog'+(hy?' hyrox-card':bike?' cycling-card':'');
  $('details-title').textContent=e.name;
  const date=e.date?dateRange({...e,end:e.end||e.date}):(e.date_hint||'Date à confirmer');
  const meta=[['Date',date],['Ville',e.city],['Discipline',hy?'HYROX':e.kind||'Non renseignée']];
  if(Array.isArray(e.formats)&&e.formats.length)meta.push(['Formats et jours',e.formats.map(f=>`${f.name} : ${formatDate(f.date)} · ${f.distanceKm} km`).join(' ; ')]);
  let rows=[];
  if(hy){
    const record=PRICING.events?.[id];
    for(const category of Object.keys(record?.categories||{})){
      const p=RacePricing.official(e,category,PRICING,true);
      if(p)rows.push(`<li><strong>${safe(category)}</strong><div>${priceMarkup(p)}</div></li>`);
    }
  }else{
    rows=RacePricing.distances(e).map(d=>`<li><strong>${safe(String(d).replace('.',','))} km</strong><div>${priceMarkup(RacePricing.price(e,d,bike?'cycling':'running',PRICING))}</div></li>`);
  }
  const link=RacePricing.sourceURL(hy?e.url:e.source);
  $('details-content').innerHTML=`<dl class="details-meta">${meta.map(([k,v])=>`<div><dt>${k}</dt><dd>${safe(v)}</dd></div>`).join('')}</dl><h3>${hy?'Tarifs par catégorie':'Distances et inscriptions'}</h3>${rows.length?`<ul class="price-list">${rows.join('')}</ul>`:`<p>${hy?'Tarif à consulter sur la billetterie officielle':'Distances non renseignées. Tarif à vérifier auprès de l’organisateur'}</p>`}${!hy?'<p class="note">Les estimations sont indicatives et non officielles. Les options, frais et vagues tarifaires peuvent faire varier le prix. Confirme le montant auprès de l’organisateur.</p>':''}${pricingUnavailable?'<p class="note">Les tarifs vérifiés sont momentanément indisponibles.</p>':''}${detailPlanner(e)}${link?`<a class="pill-btn primary details-link" href="${safe(link)}" target="_blank" rel="noopener noreferrer">${hy?'Billetterie officielle':'Site organisateur / inscription'} ↗</a>`:''}`;
  if(!detailsDialog.open){detailsDialog.showModal();$('details-close').focus();}
}
$('results').addEventListener('click',event=>{
  const button=event.target.closest('[data-details]');
  if(button){openDetails(button.dataset.details,button);return;}
  if(event.target.closest('button,a,input,select,textarea,label'))return;
  const article=event.target.closest('[data-event-id]');
  if(article)openDetails(article.dataset.eventId,article.querySelector('[data-details]'));
});
$('details-close').addEventListener('click',()=>detailsDialog.close());
detailsDialog.addEventListener('close',()=>{
  const id=detailEventId;detailEventId=null;
  const attr=detailOpener?.hasAttribute('data-calendar-event')?'data-calendar-event':'data-details';
  const restored=detailOpener?.isConnected?detailOpener:[...document.querySelectorAll(`[${attr}]`)].find(el=>el.getAttribute(attr)===id);
  (restored||document.querySelector('[data-planner-view][aria-pressed="true"]'))?.focus();
});
// Compléter le dialogue natif pour boucler le focus sans passer par la barre du navigateur.
detailsDialog.addEventListener('keydown',event=>{
  if(event.key!=='Tab')return;
  const controls=[...detailsDialog.querySelectorAll('button:not(:disabled),a[href],select:not(:disabled)')];
  const first=controls[0],last=controls[controls.length-1];
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
});
// Le dialogue natif gère Échap et l'arrière-plan inerte.
async function loadPricing(){
  try{
    const res=await fetch('./pricing.json?v='+Date.now(),{cache:'no-store'});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const next=await res.json();
    if(next.version!==1||!next.events||typeof next.events!=='object'||Array.isArray(next.events))throw new Error('Format pricing.json incorrect');
    PRICING=next;pricingUnavailable=false;
  }catch(_){pricingUnavailable=true;}
  if(detailsDialog.open&&detailEventId)openDetails(detailEventId,detailOpener);
}
loadPricing();
