/* Règles indicatives en euros : forfait + prix/km, arrondis à l'euro.
 * Ce modèle générique ne connaît ni les frais de plateforme, ni les options,
 * ni les vagues tarifaires. Ce ne sont jamais des prix organisateur.
 * Modifier ces coefficients ici pour ajuster les estimations par discipline.
 */
(function(root){
  const RULES = {
    running: {Route:[5,.7,10,1.5], Trail:[7,.8,15,1.8], Nature:[6,.7,12,1.6], Cross:[3,.5,8,1]},
    cycling: {Route:[15,.2,30,.6], Gravel:[12,.25,25,.65], Ultra:[25,.3,60,.9]}
  };
  const BANDS = {short:[0,5], ten:[5,10], half:[10,21.1], marathon:[21.1,42.2], ultra:[42.2,Infinity]};
  function km(value){
    if(typeof value!=='number' && typeof value!=='string')return null;
    if(typeof value==='string'&&!/^\d+(?:[.,]\d+)?$/.test(value.trim()))return null;
    const n=Number(String(value).replace(',','.'));
    return Number.isFinite(n)&&n>0?n:null;
  }
  function distances(event){return [...new Set((Array.isArray(event.dist)?event.dist:[]).map(km).filter(n=>n!==null))];}
  function matchesDistance(event,band){
    if(band==='all')return true;
    const limits=BANDS[band];
    return !!limits&&distances(event).some(n=>n>limits[0]&&n<=limits[1]);
  }
  function sourceURL(value){
    try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch(_){return null;}
  }
  function official(event,key,data,category=false){
    const record=data?.events?.[event.id];
    // Lier le tarif à cette édition, même si un identifiant est réutilisé.
    if(!record || record.eventDate!==(event.date||event.sort))return null;
    const entry=(category?record.categories:record.distances)?.[String(key)];
    if(!entry || entry.status!=='official' || typeof entry.amount!=='number' ||
       !Number.isFinite(entry.amount)||entry.amount<0||entry.currency!=='EUR'||!sourceURL(entry.source))return null;
    return {status:'official',amount:entry.amount,source:sourceURL(entry.source),verifiedAt:entry.verifiedAt||null};
  }
  function price(event,distance,sport,data){
    const verified=official(event,distance,data);
    if(verified)return verified;
    const n=km(distance),rule=RULES[sport]?.[event.kind];
    if(!rule||n===null)return {status:'unavailable'};
    return {status:'estimated',min:Math.round(rule[0]+rule[1]*n),max:Math.round(rule[2]+rule[3]*n)};
  }
  const api={RULES,BANDS,km,distances,matchesDistance,sourceURL,official,price};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.RacePricing=api;
})(globalThis);
