let accuracyData, accuracyBoard, accuracyLoadError = false, scoreMode = 'cumulative', scoreSelection = '';

function drawAccuracy() {
  const stage = accuracyData?.stages?.at(-1);
  const svg = document.querySelector('#accuracy-chart');
  const legend = document.querySelector('#accuracy-legend');
  svg.replaceChildren(); legend.replaceChildren();
  const points = stage?.[scoreMode] || [];
  const cycles = stage?.cycles || [];
  setText('#accuracy-ranking-title', scoreMode === 'cumulative' ? 'Clasificación acumulada' : 'Clasificación · últimos 6 ciclos');
  setText('#accuracy-explanation', scoreMode === 'cumulative'
    ? 'Acumulada desde el Corte 1: 25 de septiembre, 00:00 hora de Bogotá. Los ciclos anteriores no cuentan.'
    : 'Cada punto recalcula el WAPE de los últimos seis ciclos resueltos desde el Corte 1.');
  document.querySelectorAll('[data-score-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.scoreMode === scoreMode)));
  const x = i => 60 + i / Math.max(1, cycles.length-1) * 850;
  const y = value => 350 - value * 3;
  for (let value=0; value<=100; value+=20) {
    svg.append(svgElement('line', {x1:60,x2:910,y1:y(value),y2:y(value),class:'chart-grid'}));
    const label = svgElement('text',{x:48,y:y(value)+4,'text-anchor':'end',class:'chart-axis-label'});
    label.textContent = value+'%'; svg.append(label);
  }
  if (scoreMode === 'rolling6' && cycles.length) svg.append(svgElement('rect',{
    x:x(Math.max(0,cycles.length-6)),y:50,width:910-x(Math.max(0,cycles.length-6)),height:300,fill:'#1b5e3b',opacity:'.05'
  }));
  cycles.forEach((cycle,i) => {
    if (i % Math.max(1,Math.ceil(cycles.length/6)) && i!==cycles.length-1) return;
    const label=svgElement('text',{x:x(i),y:377,'text-anchor':'middle',class:'chart-axis-label'});
    label.textContent=new Date(cycle.at).toLocaleString('es-CO',{timeZone:'America/Bogota',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
    svg.append(label);
  });
  const details = (row,p) => `${row.display_name} · ${Number(p.accuracy).toFixed(1)}% · Cobertura ${(p.coverage*100).toFixed(0)}% · ${p.delivered_cycles}/${p.window_cycles} ciclos entregados · ${formatDate(p.at)} · ${p.cycle_id} · Modelos: ${(p.model_versions||[]).join(', ') || '—'}`;
  const endpoints=[];
  const lastScore = new Map();
  points.forEach(point => lastScore.set(point.participant_id, point));
  const ranked = rankedStudents(accuracyBoard.data);
  if (scoreMode === 'rolling6' && points.length) ranked.sort((a,b) =>
    Number(lastScore.get(b.participant_id)?.accuracy || 0) - Number(lastScore.get(a.participant_id)?.accuracy || 0)
    || Number(lastScore.get(b.participant_id)?.coverage || 0) - Number(lastScore.get(a.participant_id)?.coverage || 0)
    || a.display_name.localeCompare(b.display_name, 'es'));
  ranked.forEach((row,i)=>{
    const history=points.filter(p=>p.participant_id===row.participant_id);
    const color=RUNNER_COLORS[(row.avatar_index??i)%RUNNER_COLORS.length];
    const active=!scoreSelection || scoreSelection===row.participant_id;
    const button=document.createElement('button');button.type='button';
    button.className='accuracy-person';button.style.setProperty('--runner-color',color);
    button.setAttribute('aria-pressed',String(scoreSelection===row.participant_id));
    const rank=document.createElement('strong');rank.className='accuracy-rank';
    rank.textContent=accuracyBoard.resolved_cycles ? String(scoreMode === 'cumulative' ? (row.rank || i+1) : i+1).padStart(2,'0') : '—';
    button.append(rank);
    button.append(avatarNode(row.avatar_index,row.display_name));
    const text=document.createElement('span');text.textContent=row.display_name;
    const current=history.length && history.at(-1).index===cycles.length-1;
    const score=document.createElement('small');
    score.textContent=accuracyBoard.resolved_cycles
      ? `${Number(current ? history.at(-1).accuracy : (scoreMode === 'cumulative' ? row.accuracy : 0) || 0).toFixed(1)}%`
      : 'Sin ciclos resueltos';
    button.append(text,score);legend.append(button);
    button.onclick=()=>{scoreSelection=scoreSelection===row.participant_id?'':row.participant_id;drawAccuracy();setText('#accuracy-detail',history.length?details(row,history.at(-1)):`${row.display_name} · Sin entregas evaluadas en esta ventana.`);};
    if (!history.length) return;
    const group=svgElement('g',{opacity:active?'.85':'.12'});
    const path=history.map((p,j)=>`${j && p.index===history[j-1].index+1?'L':'M'}${x(p.index)},${y(p.accuracy)}`).join(' ');
    group.append(svgElement('path',{d:path,fill:'none',stroke:color,'stroke-width':scoreSelection===row.participant_id?3.5:2}));
    history.forEach(p=>{
      const dot=svgElement('circle',{cx:x(p.index),cy:y(p.accuracy),r:5,fill:color,tabindex:'0',role:'img','aria-label':details(row,p)});
      const title=svgElement('title');title.textContent=details(row,p);dot.append(title);
      dot.onmouseenter=dot.onfocus=()=>setText('#accuracy-detail',details(row,p));
      group.append(dot);
    });
    svg.append(group);
    if(active) endpoints.push({row,color,p:history.at(-1)});
  });
  endpoints.sort((a,b)=>b.p.accuracy-a.p.accuracy);
  // Collision-spaced labels; full cohort is always available in the legend.
  let lastY=35;
  endpoints.slice(0,8).forEach(({row,color,p},i,visible)=>{
    const labelY=Math.max(lastY+30,Math.min(350-(visible.length-i-1)*30,y(p.accuracy)));lastY=labelY;
    svg.append(svgElement('line',{x1:x(p.index),y1:y(p.accuracy),x2:933,y2:labelY,stroke:color,'stroke-width':1,opacity:'.5'}));
    const avatar=svgElement('foreignObject',{x:934,y:labelY-14,width:30,height:30});
    avatar.append(avatarNode(row.avatar_index,row.display_name,'avatar-small'));svg.append(avatar);
    const label=svgElement('text',{x:972,y:labelY+4,fill:color,'font-size':12});
    label.textContent=`${row.display_name.split(' ')[0]} ${Number(p.accuracy).toFixed(1)}`;svg.append(label);
  });
  if(!points.length){const empty=svgElement('text',{x:500,y:205,'text-anchor':'middle',class:'chart-axis-label'});empty.textContent=accuracyLoadError?'Trayectoria temporal no disponible':accuracyData?'Esperando ciclos evaluados':'Cargando trayectorias…';svg.append(empty);}
}

async function loadAccuracy(board){
  accuracyBoard=board;
  accuracyData=null;
  accuracyLoadError=false;
  drawAccuracy();
  setText('#accuracy-detail','Cargando trayectorias…');
  try {
    accuracyData=await api('/v1/portal/accuracy-chart');
    document.querySelectorAll('[data-score-mode]').forEach(b=>b.onclick=()=>{scoreMode=b.dataset.scoreMode;drawAccuracy();});
    drawAccuracy();
    setText('#accuracy-detail',accuracyData.stages.length
      ? 'Selecciona un estudiante o un punto para explorar los resultados.'
      : 'Esperando ciclos evaluados desde el inicio del corte.');
  } catch(error){accuracyLoadError=true;drawAccuracy();setText('#accuracy-detail','No se pudo cargar la trayectoria. La clasificación sigue disponible; usa Actualizar datos para reintentar.');}
}
