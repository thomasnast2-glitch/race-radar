const STATUS_KEY='race-radar-favorite-statuses';
let favoriteStatuses=RacePlanner.readStatuses(null),plannerView='cards';
let plannerCardHeading=null;
try{favoriteStatuses=RacePlanner.readStatuses(localStorage.getItem(STATUS_KEY));}catch(_){}
let plannerMonth=String(TODAY.getFullYear())+'-'+String(TODAY.getMonth()+1).padStart(2,'0');
function reliabilityBadge(e){
  const r=RacePlanner.reliability(e);
  return `<div class="reliability ${r.verified?'verified':'unverified'}"><span>${r.verified?'✓':'◌'} ${r.label}</span>${r.date?`<small>Vérifié le ${safe(formatDate(r.date))}</small>`:''}</div>`;
}
function favoriteStatusControl(e){
  if(!favoriteIds.has(e.id))return '';
  const current=RacePlanner.statusFor(favoriteStatuses,e.id);
  return `<label class="favorite-status">Ton statut<select data-favorite-status="${safe(e.id)}" aria-label="Statut pour ${safe(e.name)}">${Object.entries(RacePlanner.STATUSES).map(([v,label])=>`<option value="${v}" ${v===current?'selected':''}>${label}</option>`).join('')}</select></label>`;
}
function persistFavoriteStatus(id,status){
  if(!favoriteIds.has(id)||!Object.hasOwn(RacePlanner.STATUSES,status))return;
  favoriteStatuses[id]=status;
  try{localStorage.setItem(STATUS_KEY,JSON.stringify(favoriteStatuses));}
  catch(_){$('planner-feedback').textContent='Ce navigateur ne permet pas d’enregistrer les statuts. Ils restent disponibles pendant cette visite.';}
  // Garder le contrôle et son focus : le changement n'a pas besoin de recréer les cartes.
  document.querySelectorAll('[data-favorite-status]').forEach(el=>{if(el.dataset.favoriteStatus===id)el.value=status;});
  if(plannerView==='calendar')renderMonthlyCalendar();
}
function detailPlanner(e){
  const r=RacePlanner.reliability(e);
  return `<section class="detail-planner" aria-label="Fiabilité et favoris">${reliabilityBadge(e)}${r.source?`<a class="reliability-source" href="${safe(r.source)}" target="_blank" rel="noopener noreferrer">Source de la vérification ↗</a>`:'<p class="note">Les informations de cette course restent à confirmer auprès de l’organisateur.</p>'}<p class="note">La vérification de la date et du format ne garantit pas des places disponibles.</p><div id="detail-favorite">${favoriteIds.has(e.id)?favoriteStatusControl(e):`<button class="pill-btn primary" data-add-favorite="${safe(e.id)}">♡ Ajouter aux favoris</button>`}</div><p class="note">Ton statut est un choix personnel, conservé dans ce navigateur. Il ne réalise aucune inscription.</p></section>`;
}
function refreshDetailFavorite(){
  if(!detailsDialog.open||!detailEventId)return;
  const e=[...DATA.running,...DATA.hyrox,...CYCLING.cycling].find(e=>e.id===detailEventId);
  const el=$('detail-favorite');
  if(e&&el)el.innerHTML=favoriteStatusControl(e)||`<button class="pill-btn primary" data-add-favorite="${safe(e.id)}">♡ Ajouter aux favoris</button>`;
}
document.addEventListener('change',event=>{
  if(event.target.matches('[data-favorite-status]'))persistFavoriteStatus(event.target.dataset.favoriteStatus,event.target.value);
});
document.addEventListener('click',event=>{
  const add=event.target.closest('[data-add-favorite]');
  if(add&&!favoriteIds.has(add.dataset.addFavorite)){
    toggleFavorite(add.dataset.addFavorite);refreshDetailFavorite();
    $('detail-favorite')?.querySelector('select')?.focus();
  }
});
function setPlannerView(view){
  const headingIds=['section-overline','section-title','section-subtitle'];
  if(view==='calendar'&&plannerView==='cards')plannerCardHeading=headingIds.map(id=>$(id).textContent);
  plannerView=view;
  const calendar=view==='calendar';
  const heading=calendar?['05 / TON PROGRAMME','Ta saison en un coup d’œil.','Running, HYROX et Cyclo réunis. Choisis une discipline ou retrouve tes favoris.']:plannerCardHeading;
  if(heading)headingIds.forEach((id,i)=>{$(id).textContent=heading[i];});
  $('update-message').classList.toggle('hide',calendar);
  $('calendar-panel').classList.toggle('hide',!calendar);
  $('results').classList.toggle('hide',calendar);
  document.querySelector('.filters').classList.toggle('hide',calendar);
  document.querySelector('.toolbar').classList.toggle('hide',calendar);
  $('data-note').classList.toggle('hide',calendar);
  document.querySelectorAll('[data-planner-view]').forEach(b=>{
    b.classList.toggle('active',b.dataset.plannerView===view);
    b.setAttribute('aria-pressed',String(b.dataset.plannerView===view));
  });
  if(calendar)renderMonthlyCalendar();
}
function calendarEvents(){
  const scope=$('calendar-scope').value;
  const groups=[['running',DATA.running],['hyrox',DATA.hyrox],['cycling',CYCLING.cycling]];
  return groups.flatMap(([sport,events])=>scope==='all'||scope==='favorites'||scope===sport?events.map(e=>({...e,sport})):[])
    .filter(e=>scope!=='favorites'||favoriteIds.has(e.id))
    .sort((a,b)=>a.name.localeCompare(b.name,'fr'));
}
function calendarEventButton(e){
  const label={running:'Running',hyrox:'HYROX',cycling:'Cyclo'}[e.sport];
  const status=favoriteIds.has(e.id)?RacePlanner.STATUSES[RacePlanner.statusFor(favoriteStatuses,e.id)]:'';
  return `<button class="calendar-event ${e.sport==='hyrox'?'hyrox-card':e.sport==='cycling'?'cycling-card':''}" data-calendar-event="${safe(e.id)}" aria-haspopup="dialog" aria-controls="event-dialog"><span class="calendar-sport">${label}</span><strong>${safe(e.name)}</strong><span>${safe(e.city)}</span>${status?`<span class="calendar-favorite">♡ ${status}</span>`:''}<span class="calendar-certainty">${RacePlanner.reliability(e).verified?'✓ Vérifié':'◌ À confirmer'}</span></button>`;
}
function renderMonthlyCalendar(){
  if(plannerView!=='calendar')return;
  const events=calendarEvents(),days=RacePlanner.monthDays(plannerMonth,events);
  const first=RacePlanner.date(plannerMonth+'-01');
  $('calendar-month').textContent=first.toLocaleDateString('fr-FR',{month:'long',year:'numeric',timeZone:'UTC'});
  const offset=(first.getUTCDay()+6)%7;
  const today=String(TODAY.getFullYear())+'-'+String(TODAY.getMonth()+1).padStart(2,'0')+'-'+String(TODAY.getDate()).padStart(2,'0');
  const count=new Set(days.flatMap(d=>d.events.map(e=>e.id))).size;
  $('calendar-summary').textContent=`${count} événement${count>1?'s':''} ce mois-ci · les épreuves sur plusieurs jours figurent chaque jour concerné.`;
  $('calendar-days').innerHTML='<div class="calendar-padding" aria-hidden="true"></div>'.repeat(offset)+days.map(day=>`<section class="calendar-day ${day.events.length?'':'empty'} ${day.date===today?'today':''}" aria-label="${safe(formatDate(day.date))}"><h3><time datetime="${day.date}" ${day.date===today?'aria-current="date"':''}><span class="desktop-day">${new Date(day.date+'T12:00:00').getDate()}</span><span class="mobile-day">${new Date(day.date+'T12:00:00').toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'})}</span></time>${day.date===today?'<span class="today-label">Aujourd’hui</span>':''}</h3>${day.events.map(calendarEventButton).join('')}</section>`).join('');
  $('calendar-empty').classList.toggle('hide',count>0);
  const undated=events.filter(e=>!RacePlanner.date(e.date));
  $('calendar-undated').innerHTML=undated.length?`<h3>Dates à confirmer (${undated.length})</h3><p class="note">Ces événements ne sont pas placés sur un jour du calendrier. Les périodes ci-dessous restent indicatives.</p><div class="undated-events">${undated.map(e=>`<div>${calendarEventButton(e)}<p class="note">${safe(e.date_hint||'Date non annoncée')}</p></div>`).join('')}</div>`:'';
}
document.querySelectorAll('[data-planner-view]').forEach(b=>b.addEventListener('click',()=>setPlannerView(b.dataset.plannerView)));
$('calendar-prev').addEventListener('click',()=>{plannerMonth=RacePlanner.shiftMonth(plannerMonth,-1);renderMonthlyCalendar();});
$('calendar-next').addEventListener('click',()=>{plannerMonth=RacePlanner.shiftMonth(plannerMonth,1);renderMonthlyCalendar();});
$('calendar-today').addEventListener('click',()=>{plannerMonth=String(TODAY.getFullYear())+'-'+String(TODAY.getMonth()+1).padStart(2,'0');renderMonthlyCalendar();});
$('calendar-scope').addEventListener('change',renderMonthlyCalendar);
$('calendar-panel').addEventListener('click',event=>{
  const button=event.target.closest('[data-calendar-event]');if(button)openDetails(button.dataset.calendarEvent,button);
});
// Synchroniser les statuts entre les onglets de ce navigateur, sans réécrire les anciens favoris.
window.addEventListener('storage',event=>{
  if(event.key===STATUS_KEY){favoriteStatuses=RacePlanner.readStatuses(event.newValue);render();refreshDetailFavorite();}
  if(event.key==='race-radar-favorites'){
    try{const ids=JSON.parse(event.newValue||'[]');if(Array.isArray(ids)){favoriteIds=new Set(ids.filter(id=>typeof id==='string'));render();refreshDetailFavorite();}}catch(_){}
  }
});

loadEvents();
loadCycling();
