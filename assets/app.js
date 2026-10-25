const pct=x=>x==null?"—":x+"%";const dlt=x=>(x>0?"+":"")+x+" pp";const arrows={up:"↑",flat:"→",down:"↓",unknown:"?"};function tab(rows,heads){return '<div class="chartbox"><table><thead><tr>'+heads.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'}function card(label,value,meta,cls=""){return '<div class="card '+cls+'"><div class="label">'+label+'</div><div class="value">'+value+'</div><div class="meta">'+meta+'</div></div>'}// Archived forecasts are immutable. These exact-match display overrides only
// restate the previously recorded monitoring conditions as plain sentences.
const archivedThresholdStatements = new Map([
  ["Whether economic and energy stress begins impairing priority state allocations or coercive-system compensation.", ["Economic and energy stress could disrupt priority state allocations.","Economic and energy stress could disrupt compensation for security personnel."]],
  ["Whether Yemen fighting meets the frozen escalation definition, and whether rial intervention fails into the 25%/30-day currency threshold.", ["Major interstate strikes connected to Yemen could meet the escalation threshold if they lasted 72 hours.","A sustained 25% fall in the parallel-market rial over 30 days would meet the currency-crisis threshold."]],
  ["Whether repeated strikes satisfy the 72-hour frozen interstate-escalation rule; whether external settlements fail in two essential import categories for 14 days; whether rial depreciation reaches 25% in a rolling 30-day window.", ["Major interstate strikes lasting 72 hours would meet the regional-escalation duration threshold.","Settlement failures lasting 14 days in two essential-import categories would signal a possible external-payments crisis.","A sustained 25% fall in the parallel-market rial over 30 days would meet the currency-crisis threshold."]]
]);
function nextThresholdSentences(value){
  const text=(value||'').trim();
  if(!text)return ['—'];
  if(archivedThresholdStatements.has(text))return archivedThresholdStatements.get(text);
  // Future generated copy uses one declarative sentence per event.
  return text.split(/(?<!\b[A-Z]\.)(?<=[.!?])\s+(?=[A-Z])/).map(s=>s.trim()).filter(Boolean);
} fetch('data/history.json').then(r=>{if(!r.ok)throw new Error('history unavailable');return r.json()}).then(d=>{const x=d.updates.at(-1),p=d.updates.at(-2);revisionDate.textContent='Revision date: '+(x.methodology_revision_date||x.date);freshness.innerHTML='<strong>Assessment date:</strong> '+x.date+' · <strong>Evidence cutoff:</strong> '+(x.assessment_evidence_cutoff||'not recorded')+' · <strong>Methodology/page revised:</strong> '+(x.methodology_revision_date||'—')+' · <strong>Next scheduled:</strong> '+(x.next_scheduled_update||'not recorded');limitations.textContent=x.limitations||'';protocolStatus.innerHTML='<strong>Protocol:</strong> '+(x.protocol_version_for_assessment||'v1.0')+(x.protocol_version_for_assessment&&x.protocol_version_for_assessment.includes('legacy')?' · this assessment predates frozen v1':'');changed.innerHTML='<div class="change-point change-card"><strong>Change</strong><p>'+(x.what_changed||"See revision drivers below.")+'</p></div><div class="change-point change-card"><strong>Most important stabilizer</strong><p>'+(x.stabilizer||"—")+'</p></div><div class="change-point change-card"><strong>Thresholds to watch</strong>'+nextThresholdSentences(x.next_threshold).map(sentence=>'<p>'+sentence+'</p>').join('')+'</div>';const cond=[['Hormuz','Severely restricted; limited transit continues',(x.metrics.hormuz||'')+' · '+(x.conditions?.hormuz||'Observation · confidence unknown')],['Energy system',x.metrics.energy_stress,x.conditions?.energy||"Inference · confidence unknown"],['Elite cohesion','Continuity observed; fracture unverified',x.conditions?.elite||"Inference · confidence limited"],['Coercive apparatus','Status unknown',x.conditions?.coercion||"Inference · confidence Low due to data gaps"]];cond.forEach(c=>conditionCards.insertAdjacentHTML('beforeend',card(c[0],c[1],c[2])));(x.forecasts||[]).forEach(f=>{forecastCards.insertAdjacentHTML('beforeend',card(f.label,pct(f.p),f.horizon+' · confidence '+f.confidence+(f.resolution_deadline?' · resolves '+f.resolution_deadline.slice(0,10):'')+(f.range?' · uncertainty '+f.range[0]+'–'+f.range[1]+'%':'')+(f.scored===false?' · RETROSPECTIVE — NOT SCORED':'')));forecastTriggers.insertAdjacentHTML('beforeend','<div class="panel forecast-detail"><strong>'+f.label+'</strong><div><b>Event definition:</b> '+f.event_definition+'</div><div class="triggergrid"><span><b>Would raise:</b> '+(f.raise||"Not specified")+'</span><span><b>Would lower:</b> '+(f.lower||"Not specified")+'</span></div></div>')});forecastAudit.innerHTML='<div class="panel small"><strong>Forecast IDs:</strong> '+(x.forecasts||[]).filter(f=>f.scored).map(f=>(f.forecast_id||'legacy')+' → '+(f.resolution_deadline||'deadline not recorded')).join(' · ')+'<br><strong>Revision attribution:</strong> '+(x.revision_attribution_status||'Prospective signed contribution audit applies under Protocol v1.')+'</div>';regionalNote.textContent=x.regional_resolution_note||'';regional.innerHTML=tab(x.regional.map(z=>[z.name,pct(z.p),p?dlt(z.p-(p.regional.find(q=>q.name===z.name)?.p??z.p)):'—']),['Scenario','Current','Change']);politicalNote.textContent=x.political_resolution_note||'';political.innerHTML=tab(x.political.map(z=>[z.name,pct(z.p),p?dlt(z.p-(p.political.find(q=>q.name===z.name)?.p??z.p)):'—']),['Legacy descriptive outcome','Current','Change']);binaryPolitical.innerHTML='<h3>Scored binary political forecasts</h3>'+tab((x.binary_political||[]).map(z=>[z.label,pct(z.p),z.scored===false?'Retrospective — not scored':'Scored']),['Event','Probability','Status']);Object.entries(x.warning||{}).forEach(([k,v])=>warningGrid.insertAdjacentHTML('beforeend','<div class="item '+v.level+'"><div class="head"><span><span class="signal '+v.level+'">●</span> '+k+'</span><span class="dir '+(v.direction||"unknown")+'">'+(arrows[v.direction]||"?")+'</span></div><div>'+v.text+'</div><div class="small">Evidence: '+(v.coverage||"Unknown")+' · '+(v.role||"mixed")+'</div></div>'));(x.chains||[]).forEach(c=>chains.insertAdjacentHTML('beforeend','<div class="chain"><strong>'+c.name+'</strong><div class="small">'+c.note+'</div><div class="steps">'+c.steps.map((s,i)=>'<span class="step '+(i<c.confirmed?'done ':'')+(i===c.current?'current '+c.level:'')+'">'+s+'</span>').join('')+'</div><div class="small">'+(c.pathway_note||'')+'</div></div>'));(x.absence_indicators||[]).forEach(a=>absence.insertAdjacentHTML('beforeend','<div class="item '+(a.status||"normal")+'"><div class="head"><span><span class="signal '+(a.status||"normal")+'">●</span> '+a.label+'</span></div><div>'+a.text+'</div><div class="small">Coverage: '+a.coverage+'</div></div>'));haircut.innerHTML=card("Model estimate",pct(x.metrics.china_oil_credit_haircut),(x.haircut?.range?'Judgmental range '+x.haircut.range[0]+'–'+x.haircut.range[1]+'%. ':'')+(x.haircut?.note||"Not an observed contract term."));haircutMethod.innerHTML=x.haircut?.method?'<div class="panel"><strong>Reproducible rule</strong><p>'+x.haircut.method.rule+'</p>'+tab(x.haircut.method.components.map(z=>[z[0],z[1]+' pp',z[2]+' pp']),['Component','Current','Cap'])+'</div>':'';houthi.innerHTML='<p class="small"><strong>Unscored judgmental diagnostics — not part of the four scored forecasts.</strong> Historical estimates carried forward; current evidence does not establish fresh Iranian support.</p>'+tab([['6 months',pct(x.houthi?.m6)],['12 months',pct(x.metrics.houthi_support_12m)],['24 months',pct(x.houthi?.m24)]],['Horizon','Estimated probability strategically meaningful Iranian support continues (unscored)']);houthiDetail.innerHTML='<div class="panel"><p>'+((x.houthi||{}).definition||'')+'</p>'+tab([['Iranian matériel support, 12m',pct(x.houthi?.material_support_12m)],['Iranian technical/financial support, 12m',pct(x.houthi?.technical_financial_support_12m)],['Houthi independent/local capability, 12m',pct(x.houthi?.independent_capability_12m)]],['Component (events may overlap; not a probability partition)','Unscored probability'])+'<p class="small">'+(x.houthi?.diagnostic_note||'Houthi support estimates are unscored and judgmental.')+'</p></div>';(x.evidence||[]).forEach(e=>evidenceLedger.insertAdjacentHTML('beforeend','<article class="news"><span class="tag">'+e.category+'</span><h3>'+e.id+' · '+e.date+'</h3><div>'+e.observation+'</div><div class="small">Reliability: '+e.reliability+' · Status: '+(e.evidence_status||'unclassified')+' · Direction: '+(e.direction||'unclassified')+' · Impact: '+(e.impact_magnitude||'unrated')+' · affects: '+e.affects.join(', ')+' · <a href="'+e.source+'" rel="noopener">source</a></div></article>'));correctionLedger.innerHTML=(x.corrections&&x.corrections.length)?x.corrections.map(q=>'<article class="news">'+q+'</article>').join(''):'<div class="empty">No published corrections.</div>';(x.news||[]).forEach(n=>news.insertAdjacentHTML('beforeend','<article class="news"><span class="tag">'+(n.revision_type||n.type)+'</span><h3>'+n.title+'</h3><div>'+n.impact+'</div><div class="small">Revision: '+(n.revision_date||x.date)+(n.event_date?' · Source/event: '+n.event_date:'')+(n.url?' · <a href="'+n.url+'" rel="noopener">source</a>':'')+'</div>'+(n.source_note?'<div class="source-note"><strong>Source supports:</strong> '+n.source_note+'</div>':'')+'</article>'));d.updates.slice().reverse().slice(0,4).forEach((a,i)=>archive.insertAdjacentHTML('beforeend','<article class="archive"><h3>'+a.date+(a.forecasts?'':' <span class="legacy">legacy record</span>')+'</h3><div>Escalation '+pct(a.metrics.regional_escalation_90d)+' · Regime-ending event '+pct(a.metrics.regime_end_12m)+' · Legacy FX composite (unscored) '+pct(a.metrics.fx_crisis_12m)+'</div><div class="small">'+a.summary+'</div></article>'));drawForecasts(d.updates);drawHaircut(d.updates);renderAccessibleSvgCharts(d.updates)}).catch(e=>{document.querySelector('main').innerHTML='<div class="failure"><h2>Data temporarily unavailable</h2><p>The dashboard could not load its validated assessment. Please use the forecast history or return later.</p></div>'});function axes(c,max=100){const g=c.getContext('2d'),W=c.width,H=c.height,p=42;g.clearRect(0,0,W,H);g.strokeStyle='#cfd6dc';g.fillStyle='#64717d';g.font='12px sans-serif';for(let y=0;y<=max;y+=max/4){const py=H-p-(H-2*p)*y/max;g.beginPath();g.moveTo(p,py);g.lineTo(W-p,py);g.stroke();g.fillText(Math.round(y)+'%',6,py+4)}return[g,W,H,p]}
function datedAxis(c,records,max=100){
  const [g,W,H,p]=axes(c,max);
  const days=records.map(r=>Date.parse(r.date+'T00:00:00Z'));
  if(days.some(t=>!Number.isFinite(t)))throw new Error('Invalid assessment date in chart history');
  const first=days.length?Math.min(...days):0,last=days.length?Math.max(...days):0;
  const x=i=>p+(W-2*p)*(first===last?.5:(days[i]-first)/(last-first));
  g.save();g.strokeStyle='#9da9b4';g.fillStyle='#475562';g.font='12px sans-serif';
  g.textBaseline='alphabetic';
  records.forEach((r,i)=>{const px=x(i);g.beginPath();g.moveTo(px,H-p);g.lineTo(px,H-p+5);g.stroke()});
  // Print exact ISO dates where there is room; always keep the first and
  // last assessment labeled. Short intervals do not overlap their neighbors.
  let previous=-Infinity;
  records.forEach((r,i)=>{
    const px=x(i),isFirst=i===0,isLast=i===records.length-1;
    if(isFirst||isLast||px-previous>=100&&x(records.length-1)-px>=100){
      g.textAlign=isFirst?'left':isLast?'right':'center';
      if(records.length===1)g.textAlign='center';
      g.fillText(r.date,px,H-12);
      previous=px;
    }
  });
  g.restore();
  return {g,W,H,p,x};
}
function drawSeries(ctx,records,x,y,key,color){
  ctx.strokeStyle=color;ctx.lineWidth=3;ctx.beginPath();
  let active=false;
  records.forEach((r,i)=>{
    const value=r.metrics?.[key];
    if(typeof value!=='number'||!Number.isFinite(value)){active=false;return}
    const px=x(i),py=y(value);
    if(active)ctx.lineTo(px,py);else ctx.moveTo(px,py);
    active=true;
  });
  ctx.stroke();ctx.fillStyle=color;
  records.forEach((r,i)=>{
    const value=r.metrics?.[key];
    if(typeof value!=='number'||!Number.isFinite(value))return;
    ctx.beginPath();ctx.arc(x(i),y(value),3.5,0,Math.PI*2);ctx.fill();
  });
}
function drawForecasts(records){
  // Only the four Protocol-v1.0 scored event IDs are comparable in this chart.
  // Previous fx_crisis_12m is a legacy composite, NOT currency_crisis_12m.
  const series=[
    ['regional_escalation_90d','#a92c2c','Escalation'],
    ['regime_end_12m','#9a6415','Regime end'],
    ['currency_crisis_12m','#245c83','Currency crisis'],
    ['external_payments_crisis_12m','#28734b','Payments crisis']
  ];
  const keys=series.map(([id])=>id);
  const scored=records.map(r=>{
    const rows=(r.forecasts||[]).filter(f=>f.scored===true&&keys.includes(f.event_id));
    if(rows.length!==4||new Set(rows.map(f=>f.event_id)).size!==4)return null;
    return {date:r.date,metrics:Object.fromEntries(rows.map(f=>[f.event_id,f.p]))};
  }).filter(Boolean);
  const {g,W,H,p,x}=datedAxis(chart,scored);
  const y=value=>H-p-(H-2*p)*value/100;
  series.forEach(([key,color,label],i)=>{
    drawSeries(g,scored,x,y,key,color);
    g.fillStyle=color;g.font='12px sans-serif';g.fillText(label,p+i*116,18);
  });
  chart.setAttribute('role','img');
  chart.setAttribute('aria-label','Four Protocol v1.0 scored forecast probabilities by assessment date. '+scored.map(r=>r.date+': '+series.map(([key,,label])=>label+' '+pct(r.metrics?.[key])).join(', ')).join('; '));
}
function drawHaircut(records){
  const max=60,{g,W,H,p,x}=datedAxis(haircutChart,records,max);
  drawSeries(g,records,x,value=>H-p-(H-2*p)*value/max,'china_oil_credit_haircut','#28734b');
  g.fillStyle='#28734b';g.font='12px sans-serif';g.fillText('Model estimate',p,18);
  haircutChart.setAttribute('role','img');
  haircutChart.setAttribute('aria-label','Iran–China oil-credit haircut by assessment date. '+records.map(r=>r.date+': '+pct(r.metrics?.china_oil_credit_haircut)).join('; '));
}

function renderAccessibleSvgCharts(records){
  // SVG mirrors the frozen scored forecast data; legacy FX remains excluded.
  // Keep canvas for the existing chart regression suite and use SVG for robust
  // mobile/webview rendering and a machine-readable accessible description.
  if(typeof document==='undefined'||typeof document.createElementNS!=='function')return;
  const ns='http://www.w3.org/2000/svg';
  function node(tag,attrs,text){
    const e=document.createElementNS(ns,tag);
    Object.entries(attrs||{}).forEach(([k,v])=>e.setAttribute(k,String(v)));
    if(text!==undefined)e.textContent=String(text);
    return e;
  }
  function make(canvas,rows,series,max,description){
    if(!canvas||!canvas.parentElement||!rows.length)return;
    const W=900,H=300,p=48;
    const dates=rows.map(r=>Date.parse(r.date+'T00:00:00Z'));
    if(dates.some(t=>!Number.isFinite(t)))return;
    const first=Math.min(...dates),last=Math.max(...dates);
    const X=i=>p+(W-2*p)*(first===last?0.5:(dates[i]-first)/(last-first));
    const Y=v=>H-p-(H-2*p)*v/max;
    const svg=node('svg',{viewBox:'0 0 900 300',width:'100%',role:'img','aria-label':description});
    svg.appendChild(node('title',{},description));
    for(let t=0;t<=4;t++){
      const value=max*t/4,y=Y(value);
      svg.appendChild(node('line',{x1:p,y1:y,x2:W-p,y2:y,stroke:'#cfd6dc'}));
      svg.appendChild(node('text',{x:4,y:y+4,fill:'#64717d','font-size':13},Math.round(value)+'%'));
    }
    const labelIndices=[0,rows.length-1];
    if(rows.length>2)for(let i=1;i<rows.length-1;i++)if(X(i)-X(labelIndices.at(-1))>=115&&X(rows.length-1)-X(i)>=115)labelIndices.splice(labelIndices.length-1,0,i);
    [...new Set(labelIndices)].forEach(i=>{
      svg.appendChild(node('text',{x:X(i),y:H-12,fill:'#475562','font-size':12,'text-anchor':i===0?'start':i===rows.length-1?'end':'middle'},rows[i].date));
    });
    series.forEach(([key,color,label],j)=>{
      const points=rows.map((r,i)=>({v:r.metrics?.[key],x:X(i)})).filter(z=>typeof z.v==='number'&&Number.isFinite(z.v));
      if(points.length){
        svg.appendChild(node('polyline',{points:points.map(z=>z.x+','+Y(z.v)).join(' '),fill:'none',stroke:color,'stroke-width':3}));
        points.forEach(z=>svg.appendChild(node('circle',{cx:z.x,cy:Y(z.v),r:4,fill:color})));
      }
      svg.appendChild(node('text',{x:p+j*(series.length===1?0:190),y:20,fill:color,'font-size':14},label));
    });
    canvas.parentElement.appendChild(svg);
    canvas.style.display='none';
  }
  const keys=['regional_escalation_90d','regime_end_12m','currency_crisis_12m','external_payments_crisis_12m'];
  const scored=records.map(r=>{
    const f=(r.forecasts||[]).filter(q=>q.scored===true&&keys.includes(q.event_id));
    if(f.length!==4||new Set(f.map(q=>q.event_id)).size!==4)return null;
    return {date:r.date,metrics:Object.fromEntries(f.map(q=>[q.event_id,q.p]))};
  }).filter(Boolean);
  make(document.getElementById('chart'),scored,[
    [keys[0],'#a92c2c','Escalation'],[keys[1],'#9a6415','Regime end'],
    [keys[2],'#245c83','Currency crisis'],[keys[3],'#28734b','Payments crisis']
  ],100,'Four scored Protocol v1.0 forecasts by date: '+scored.map(r=>r.date+' '+keys.map(k=>k+' '+r.metrics[k]+'%').join(', ')).join('; '));
  make(document.getElementById('haircutChart'),records,[['china_oil_credit_haircut','#28734b','Model estimate']],60,
    'Iran–China oil-credit haircut by date: '+records.map(r=>r.date+' '+r.metrics.china_oil_credit_haircut+'%').join('; '));
}
