export default function(component) {
  const {data,parentElement,setStateValue}=component;
  const svg=parentElement.querySelector('.world-map');
  const ns='http://www.w3.org/2000/svg';
  const selected=data.stations.find(s=>s.station===data.selected);
  const handlers=[];
  const listen=(el,event,fn)=>{el.addEventListener(event,fn);handlers.push(()=>el.removeEventListener(event,fn));};
  const node=(tag,attrs,content)=>{const el=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v)));if(content!==undefined)el.textContent=content;return el;};
  const world=data.view||[-15,-15,1030,530];
  let view=svg.getAttribute('data-gas')===data.gas?svg.getAttribute('viewBox').split(' ').map(Number):world.slice();
  svg.setAttribute('data-gas',data.gas);
  svg.replaceChildren();
  const setView=(next)=>{view=next;svg.setAttribute('viewBox',next.join(' '));svg.setAttribute('data-zoom',(1030/next[2]).toFixed(2));
    const ratio=next[2]/1030;
    svg.querySelectorAll('.marker').forEach(g=>{const x=Number(g.dataset.x),y=Number(g.dataset.y),shift=y>470?-12:15;
      g.querySelector('circle').setAttribute('r',(g.classList.contains('selected')?8:6)*ratio);
      const text=g.querySelector('text');text.style.fontSize=(18*ratio)+'px';text.style.strokeWidth=(3*ratio)+'px';text.setAttribute('x',x+12*ratio);text.setAttribute('y',y+shift*ratio);
      const hit=g.querySelector('rect');hit.setAttribute('x',x-10*ratio);hit.setAttribute('y',y+Math.min(-10,shift-15)*ratio);
      hit.setAttribute('width',Number(g.dataset.hitWidth)*ratio);hit.setAttribute('height',(Math.abs(shift)+20)*ratio);
    });};
  setView(view);
  for(let lat=-90;lat<=90;lat+=30)svg.append(node('line',{x1:0,y1:(90-lat)*500/180,x2:1000,y2:(90-lat)*500/180,class:'graticule'}));
  for(let lon=-180;lon<=180;lon+=30)svg.append(node('line',{x1:(lon+180)*1000/360,y1:0,x2:(lon+180)*1000/360,y2:500,class:'graticule'}));
  data.paths.forEach(d=>svg.append(node('path',{d,class:'country','fill-rule':'evenodd'})));
  data.stations.filter(s=>s.bounds).forEach(s=>{
    const [x,y,width,height]=s.bounds;
    svg.append(node('rect',{x,y,width,height,fill:s.station===data.selected?'#c7ed9f':'#6fb8d0',
      'fill-opacity':.18,stroke:s.station===data.selected?'#c7ed9f':'#6fb8d0',
      'stroke-width':1,'vector-effect':'non-scaling-stroke','pointer-events':'none'}));
  });
  const choose=(s)=>{if(s.station!=='LOCAL')setStateValue('selected',{gas:data.gas,station:s.station});
    else setView([s.x-100,s.y-51.46,200,102.92]);};
  const picker=parentElement.querySelector('.station-picker');picker.replaceChildren();
  data.stations.forEach(s=>{
    const group=node('g',{class:'marker'+(s.station===data.selected?' selected':''),role:'button',tabindex:0,
      'aria-label':'Select '+s.name,'data-station':s.station,'data-x':s.x,'data-y':s.y,'data-hit-width':s.short_name.length*10+35});
    group.append(node('rect',{x:s.x-10,y:s.y-10,width:s.short_name.length*7+30,height:35,fill:'transparent','pointer-events':'all'}));
    group.append(node('circle',{cx:s.x,cy:s.y,r:s.station===data.selected?6:4.5}));
    const shift=s.y>470?-12:15;
    group.append(node('text',{x:s.x+9,y:s.y+shift},s.short_name));
    group.append(node('title',{},`${s.name} · ${s.value.toFixed(2)} ${data.unit} · ${s.last}`));
    listen(group,'click',()=>choose(s));
    listen(group,'keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(s);}});
    svg.append(group);
    const button=document.createElement('button');button.type='button';button.textContent=s.short_name;
    button.setAttribute('aria-label','Select station '+s.name);button.setAttribute('aria-pressed',String(s.station===data.selected));
    listen(button,'click',()=>choose(s));picker.append(button);
  });
  setView(view);
  parentElement.querySelector('.site-title').textContent=selected?.name||'Select a monitoring station';
  parentElement.querySelector('.site-detail').textContent=selected?`${selected.value.toFixed(2)} ${data.unit} · ${selected.last} · ${selected.latitude.toFixed(2)}°, ${selected.longitude.toFixed(2)}°`:'No measurements are inferred between sites.';
  const zoom=(factor)=>{const w=Math.max(3,Math.min(1030,view[2]*factor)),h=w*530/1030;
    setView([view[0]+(view[2]-w)/2,view[1]+(view[3]-h)/2,w,h]);};
  listen(parentElement.querySelector('[data-action=in]'),'click',()=>zoom(.65));
  listen(parentElement.querySelector('[data-action=out]'),'click',()=>zoom(1/.65));
  listen(parentElement.querySelector('[data-action=fit]'),'click',()=>setView(world.slice()));
  listen(parentElement.querySelector('[data-action=focus]'),'click',()=>{if(selected){const width=data.view?22:200;
    setView([selected.x-width/2,selected.y-width*.2573,width,width*.5146]);}});
  let drag=null;
  listen(svg,'pointerdown',e=>{if(e.target.closest('.marker'))return;drag={x:e.clientX,y:e.clientY,view:view.slice()};svg.setPointerCapture(e.pointerId);});
  listen(svg,'pointermove',e=>{if(!drag)return;const rect=svg.getBoundingClientRect();
    const scale=Math.min(rect.width/drag.view[2],rect.height/drag.view[3]);
    setView([drag.view[0]-(e.clientX-drag.x)/scale,drag.view[1]-(e.clientY-drag.y)/scale,drag.view[2],drag.view[3]]);});
  const endDrag=()=>{drag=null;};listen(svg,'pointerup',endDrag);listen(svg,'pointercancel',endDrag);
  return ()=>handlers.forEach(dispose=>dispose());
}
