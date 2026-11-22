/* Modèle sans dépendance : favoris et calendrier ne modifient jamais les JSON collectés. */
(function(root){
  const STATUSES={interested:'Intéressé',registered:'Inscrit',goal:'Objectif principal'};
  function date(value){
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
    const d=new Date(value+'T12:00:00Z');
    return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===value?d:null;
  }
  function httpURL(value){try{const u=new URL(value);return /^https?:$/.test(u.protocol)?u.href:null;}catch(_){return null;}}
  function reliability(event,now=new Date()){
    const verified=date(event.verified_at),source=httpURL(event.source||event.url);
    const today=new Date(Date.UTC(now.getFullYear(),now.getMonth(),now.getDate(),12));
    // Ni certainty="confirmée", ni un contrôle de collecte ne prouvent une vérification organisateur.
    if(event.source_type==='official'&&verified&&verified<=today&&source){
      return {verified:true,label:'Vérifié sur le site officiel',date:event.verified_at,source};
    }
    return {verified:false,label:'À confirmer',date:null,source:null};
  }
  function readStatuses(raw){
    try{
      const value=JSON.parse(raw||'{}'),out=Object.create(null);
      if(!value||typeof value!=='object'||Array.isArray(value))return out;
      for(const [id,status] of Object.entries(value))if(Object.hasOwn(STATUSES,status))out[id]=status;
      return out;
    }catch(_){return Object.create(null);}
  }
  function statusFor(statuses,id){return Object.hasOwn(STATUSES,statuses[id])?statuses[id]:'interested';}
  function shiftMonth(month,offset){
    if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(month))return null;
    const [year,m]=month.split('-').map(Number),d=new Date(Date.UTC(year,m-1+offset,1,12));
    return d.toISOString().slice(0,7);
  }
  function monthDays(month,events){
    const first=date(month+'-01');if(!first)return [];
    const next=date(shiftMonth(month,1)+'-01');
    const rows=[];
    for(let d=new Date(first);d<next;d.setUTCDate(d.getUTCDate()+1)){
      const iso=d.toISOString().slice(0,10);
      rows.push({date:iso,events:events.filter(e=>{
        if(!date(e.date))return false;
        const end=date(e.end)&&e.end>=e.date?e.end:e.date;
        return e.date<=iso&&end>=iso;
      })});
    }
    return rows;
  }
  const api={STATUSES,date,httpURL,reliability,readStatuses,statusFor,shiftMonth,monthDays};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.RacePlanner=api;
})(globalThis);
