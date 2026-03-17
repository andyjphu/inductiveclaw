"""Dashboard frontend — single HTML page with inline CSS/JS."""

from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>InductiveClaw Mission Control</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0e17;--surface:#111827;--border:#1e293b;--text:#e2e8f0;
--dim:#64748b;--accent:#f97316;--green:#22c55e;--red:#ef4444;--blue:#3b82f6;
--purple:#a855f7;--cyan:#06b6d4;--yellow:#eab308}
body{background:var(--bg);color:var(--text);font-family:'SF Mono',Monaco,
'Cascadia Code',monospace;font-size:13px;line-height:1.5;overflow-x:hidden}
.header{display:flex;align-items:center;justify-content:space-between;
padding:12px 20px;border-bottom:1px solid var(--border);background:var(--surface)}
.header h1{font-size:14px;letter-spacing:2px;color:var(--accent);font-weight:700}
.header .goal{color:var(--dim);font-size:12px;max-width:400px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.header .controls{display:flex;gap:8px}
.btn{padding:4px 12px;border:1px solid var(--border);border-radius:4px;
background:var(--surface);color:var(--text);cursor:pointer;font-size:12px;
font-family:inherit;transition:all .15s}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.danger{border-color:var(--red);color:var(--red)}
.btn.danger:hover{background:var(--red);color:#fff}
.btn.active{background:var(--accent);color:#000;border-color:var(--accent)}
.grid{display:grid;grid-template-columns:280px 1fr 260px;grid-template-rows:1fr;
gap:0;height:calc(100vh - 49px)}
.panel{border-right:1px solid var(--border);overflow-y:auto;padding:12px}
.panel:last-child{border-right:none}
.panel-title{font-size:11px;letter-spacing:1.5px;color:var(--dim);
margin-bottom:8px;text-transform:uppercase}
/* Branches */
.branch-card{background:var(--surface);border:1px solid var(--border);
border-radius:6px;padding:10px;margin-bottom:8px;position:relative}
.branch-card.active{border-color:var(--accent)}
.branch-card .bid{font-weight:700;color:var(--cyan);font-size:14px}
.branch-card .score{font-size:24px;font-weight:700;color:var(--green);
float:right;margin-top:-4px}
.branch-card .meta{color:var(--dim);font-size:11px;margin-top:4px}
.branch-card .tool{color:var(--yellow);font-size:11px;margin-top:2px;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px}
.dot.running{background:var(--green);animation:pulse 1.5s infinite}
.dot.paused{background:var(--yellow)}
.dot.done{background:var(--dim)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
/* Activity feed */
.feed{font-size:12px}
.feed-item{padding:3px 0;border-bottom:1px solid var(--border);display:flex;gap:8px}
.feed-item .ts{color:var(--dim);flex-shrink:0;width:40px}
.feed-item .bid{color:var(--cyan);flex-shrink:0;width:24px;text-align:center}
.feed-item .msg{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.feed-item.error .msg{color:var(--red)}
.feed-item.feature .msg{color:var(--green)}
.feed-item.score .msg{color:var(--accent)}
/* Stats */
.stat-row{display:flex;justify-content:space-between;padding:6px 0;
border-bottom:1px solid var(--border)}
.stat-row .label{color:var(--dim)}
.stat-row .value{font-weight:600}
/* Budget bar */
.budget-bar{height:6px;background:var(--border);border-radius:3px;margin:8px 0;
overflow:hidden}
.budget-fill{height:100%;background:var(--green);border-radius:3px;
transition:width .3s,background .3s}
.budget-fill.warning{background:var(--yellow)}
.budget-fill.exceeded{background:var(--red)}
/* Sparkline */
canvas.sparkline{width:100%;height:60px;margin:8px 0;display:block}
/* Features */
.feature-item{padding:3px 0;font-size:12px}
.feature-item::before{content:'\\2713 ';color:var(--green)}
/* Steering */
.steer-group{margin-bottom:12px}
.steer-group label{display:block;color:var(--dim);font-size:11px;
text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.threshold-ctrl{display:flex;align-items:center;gap:8px}
.threshold-ctrl .val{font-size:18px;font-weight:700;color:var(--accent);
min-width:24px;text-align:center}
.hint-input{width:100%;padding:6px 8px;background:var(--bg);border:1px solid var(--border);
border-radius:4px;color:var(--text);font-family:inherit;font-size:12px}
.hint-input:focus{outline:none;border-color:var(--accent)}
/* Browser health */
.health{display:flex;gap:12px;flex-wrap:wrap}
.health-item{text-align:center;padding:6px 10px;background:var(--surface);
border:1px solid var(--border);border-radius:4px;min-width:70px}
.health-item .val{font-size:18px;font-weight:700}
.health-item .lbl{font-size:10px;color:var(--dim);text-transform:uppercase}
/* Responsive */
@media(max-width:900px){.grid{grid-template-columns:1fr;grid-template-rows:auto}}
/* Connection */
.disconnected{position:fixed;top:0;left:0;right:0;padding:8px;
background:var(--red);color:#fff;text-align:center;font-size:12px;
z-index:100;display:none}
.disconnected.show{display:block}
/* Rounds */
.round-badge{display:inline-block;padding:2px 8px;border-radius:10px;
font-size:11px;background:var(--surface);border:1px solid var(--border);
margin:2px}
.round-badge.winner{border-color:var(--green);color:var(--green)}
</style>
</head>
<body>
<div class="disconnected" id="dc-banner">Reconnecting...</div>
<div class="header">
  <div>
    <h1>INDUCTIVECLAW MISSION CONTROL</h1>
    <div class="goal" id="goal"></div>
  </div>
  <div class="controls">
    <button class="btn" id="btn-pause" onclick="sendCmd('pause')">Pause</button>
    <button class="btn danger" id="btn-stop" onclick="sendCmd('stop_all')">Stop</button>
  </div>
</div>
<div class="grid">
  <!-- Left: Branches + Stats -->
  <div class="panel">
    <div class="panel-title">Branches</div>
    <div id="branches"></div>
    <div class="panel-title" style="margin-top:16px">Stats</div>
    <div id="stats"></div>
    <div class="panel-title" style="margin-top:16px">Budget</div>
    <div id="budget-info"></div>
    <div class="budget-bar"><div class="budget-fill" id="budget-fill"></div></div>
    <div class="panel-title" style="margin-top:16px">Quality</div>
    <canvas class="sparkline" id="sparkline"></canvas>
    <div class="panel-title" style="margin-top:16px">Browser Health</div>
    <div class="health" id="health"></div>
  </div>
  <!-- Center: Activity feed -->
  <div class="panel">
    <div class="panel-title">Activity</div>
    <div class="feed" id="feed"></div>
  </div>
  <!-- Right: Features + Steering -->
  <div class="panel">
    <div class="panel-title">Features</div>
    <div id="features"></div>
    <div class="panel-title" style="margin-top:16px">Steering</div>
    <div class="steer-group">
      <label>Threshold</label>
      <div class="threshold-ctrl">
        <button class="btn" onclick="adjThreshold(-1)">-</button>
        <span class="val" id="threshold">8</span>
        <button class="btn" onclick="adjThreshold(1)">+</button>
        <span style="color:var(--dim)">/10</span>
      </div>
    </div>
    <div class="steer-group">
      <label>Hint</label>
      <input class="hint-input" id="hint" placeholder="e.g. Focus on accessibility..."
        onkeydown="if(event.key==='Enter')sendHint()">
      <button class="btn" style="margin-top:4px;width:100%" onclick="sendHint()">Send Hint</button>
    </div>
    <div class="panel-title" style="margin-top:16px">Rounds</div>
    <div id="rounds"></div>
  </div>
</div>
<script>
let ws,state={},retryMs=1000;
const $=id=>document.getElementById(id);

function connect(){
  const proto=location.protocol==='https:'?'wss:':'ws:';
  ws=new WebSocket(proto+'//'+location.host);
  ws.onopen=()=>{$('dc-banner').classList.remove('show');retryMs=1000};
  ws.onclose=()=>{$('dc-banner').classList.add('show');setTimeout(connect,retryMs);retryMs=Math.min(retryMs*2,10000)};
  ws.onmessage=e=>{const m=JSON.parse(e.data);handle(m)};
}

function handle(m){
  if(m.type==='snapshot'){state=m.data;renderAll()}
  else if(m.type==='event'){applyEvent(m);renderIncremental(m)}
  else if(m.type==='round_complete'){state.rounds=state.rounds||[];state.rounds.push(m.data);renderRounds()}
  else if(m.type==='budget'){Object.assign(state,{total_cost_usd:m.data.spent,budget_fraction:m.data.fraction,budget_status:m.data.status});renderBudget()}
  else if(m.type==='browser_eval'){state.browser_eval=m.data;renderHealth()}
}

function applyEvent(m){
  const b=state.branches=state.branches||{};
  if(!b[m.branch_id])b[m.branch_id]={branch_id:m.branch_id,iteration:0,score:null,score_history:[],features:[],cost_usd:0,status:'running',errors:[]};
  const br=b[m.branch_id],d=m.data||{};
  if(m.event==='iteration_start'){br.iteration=d.iteration||br.iteration;br.status='running'}
  else if(m.event==='tool_call'){br.last_tool=d.name}
  else if(m.event==='text_preview'){br.last_text=(d.text||'').slice(0,200)}
  else if(m.event==='feature'){if(d.name&&!br.features.includes(d.name))br.features.push(d.name)}
  else if(m.event==='score'){br.score=d.score;br.score_history=br.score_history||[];br.score_history.push(d.score)}
  else if(m.event==='error'){br.errors=(br.errors||[]);br.errors.push((d.message||'').slice(0,200))}
  else if(m.event==='done'){br.status='done';br.stop_reason=d.reason}
}

function renderAll(){
  $('goal').textContent=state.goal||'';
  $('threshold').textContent=state.threshold||8;
  renderBranches();renderStats();renderBudget();renderSparkline();
  renderFeatures();renderHealth();renderRounds();renderFeed(state.activity_log||[]);
  if(state.paused){$('btn-pause').textContent='Resume';$('btn-pause').classList.add('active')}
}

function renderIncremental(m){
  renderBranches();renderStats();renderSparkline();
  if(m.event==='feature')renderFeatures();
  addFeedItem(m);
}

function renderBranches(){
  const el=$('branches');let h='';
  for(const[id,b]of Object.entries(state.branches||{})){
    const sc=b.score!==null?b.score:'--';
    const cls=b.status==='running'?'active':'';
    h+=`<div class="branch-card ${cls}"><span class="dot ${b.status}"></span><span class="bid">${id}</span>
    <span class="score">${sc}</span><div class="meta">iter ${b.iteration} | $${(b.cost_usd||0).toFixed(3)}</div>
    <div class="tool">${b.last_tool||''}</div></div>`;
  }
  el.innerHTML=h;
}

function renderStats(){
  const bs=Object.values(state.branches||{});
  const iters=bs.reduce((s,b)=>s+b.iteration,0);
  const cost=bs.reduce((s,b)=>s+(b.cost_usd||0),0);
  $('stats').innerHTML=`
    <div class="stat-row"><span class="label">Iterations</span><span class="value">${iters}</span></div>
    <div class="stat-row"><span class="label">Cost</span><span class="value">$${cost.toFixed(4)}</span></div>
    <div class="stat-row"><span class="label">Branches</span><span class="value">${bs.length}</span></div>
    <div class="stat-row"><span class="label">Mode</span><span class="value">${state.mode||'single'}</span></div>`;
}

function renderBudget(){
  const f=state.budget_fraction;const s=state.budget_status||'ok';
  const bud=state.budget_usd;const spent=state.total_cost_usd||0;
  $('budget-info').innerHTML=bud?`$${spent.toFixed(2)} / $${bud.toFixed(2)}`:'No budget set';
  const fill=$('budget-fill');
  fill.style.width=f?Math.min(f*100,100)+'%':'0%';
  fill.className='budget-fill'+(s==='warning'?' warning':s==='exceeded'?' exceeded':'');
}

function renderSparkline(){
  const c=$('sparkline'),ctx=c.getContext('2d');
  c.width=c.offsetWidth*2;c.height=120;ctx.scale(2,2);
  const w=c.offsetWidth,h=60;
  // Collect all scores across branches
  let pts=[];
  for(const b of Object.values(state.branches||{})){pts=pts.concat(b.score_history||[])}
  if(!pts.length)return;
  ctx.clearRect(0,0,w,h);
  const max=10,step=w/(Math.max(pts.length-1,1));
  ctx.beginPath();ctx.strokeStyle='#f97316';ctx.lineWidth=1.5;
  pts.forEach((v,i)=>{const x=i*step,y=h-4-(v/max)*(h-8);i===0?ctx.moveTo(x,y):ctx.lineTo(x,y)});
  ctx.stroke();
  // Threshold line
  const ty=h-4-(state.threshold/max)*(h-8);
  ctx.beginPath();ctx.strokeStyle='#22c55e44';ctx.setLineDash([4,4]);
  ctx.moveTo(0,ty);ctx.lineTo(w,ty);ctx.stroke();ctx.setLineDash([]);
}

function renderFeatures(){
  const feats=new Set();
  for(const b of Object.values(state.branches||{}))for(const f of(b.features||[]))feats.add(f);
  $('features').innerHTML=[...feats].map(f=>`<div class="feature-item">${esc(f)}</div>`).join('');
}

function renderHealth(){
  const h=state.browser_eval;
  if(!h){$('health').innerHTML='<span style="color:var(--dim)">No eval yet</span>';return}
  $('health').innerHTML=`
    <div class="health-item"><div class="val" style="color:${h.health_score>=7?'var(--green)':h.health_score>=4?'var(--yellow)':'var(--red)'}">${h.health_score}</div><div class="lbl">Health</div></div>
    <div class="health-item"><div class="val" style="color:var(--red)">${h.console_errors||0}</div><div class="lbl">Errors</div></div>
    <div class="health-item"><div class="val" style="color:var(--yellow)">${h.keybinding_conflicts||0}</div><div class="lbl">Conflicts</div></div>`;
}

function renderRounds(){
  const rs=state.rounds||[];
  if(!rs.length){$('rounds').innerHTML='<span style="color:var(--dim)">No rounds yet</span>';return}
  $('rounds').innerHTML=rs.map(r=>{
    const results=(r.results||[]).map(res=>`<span class="round-badge ${res.branch_id===r.winner?'winner':''}">${res.branch_id}: ${res.final_score||'?'}</span>`).join('');
    return`<div style="margin-bottom:6px"><span style="color:var(--dim)">R${r.round_num}</span> ${results}</div>`;
  }).join('');
}

function renderFeed(items){
  const el=$('feed');
  el.innerHTML=(items||[]).slice(-100).map(i=>feedHTML(i)).join('');
  el.scrollTop=el.scrollHeight;
}

function addFeedItem(m){
  const el=$('feed');
  el.innerHTML+=feedHTML({branch_id:m.branch_id,event:m.event,...(m.data||{})});
  if(el.children.length>200){const first=el.firstChild;if(first)first.remove()}
  el.scrollTop=el.scrollHeight;
}

function feedHTML(i){
  const t=new Date().toLocaleTimeString().slice(0,5);
  const cls=i.event==='error'?'error':i.event==='feature'?'feature':i.event==='score'?'score':'';
  let msg=i.event;
  if(i.event==='tool_call')msg='tool: '+(i.name||'');
  else if(i.event==='feature')msg='completed: '+(i.name||'');
  else if(i.event==='score')msg='score: '+(i.score||'')+'/10';
  else if(i.event==='iteration_start')msg='iteration '+(i.iteration||'');
  else if(i.event==='error')msg='error: '+(i.message||'').slice(0,80);
  else if(i.event==='done')msg='done ('+( i.reason||'')+')';
  else if(i.event==='text_preview')msg=(i.text||'').slice(0,80);
  return`<div class="feed-item ${cls}"><span class="ts">${t}</span><span class="bid">${i.branch_id||''}</span><span class="msg">${esc(msg)}</span></div>`;
}

function sendCmd(type,data){
  if(!ws||ws.readyState!==1)return;
  const msg={type,...(data||{})};ws.send(JSON.stringify(msg));
  if(type==='pause'){$('btn-pause').textContent='Resume';$('btn-pause').classList.add('active');$('btn-pause').onclick=()=>sendCmd('resume')}
  else if(type==='resume'){$('btn-pause').textContent='Pause';$('btn-pause').classList.remove('active');$('btn-pause').onclick=()=>sendCmd('pause')}
}

function adjThreshold(d){
  const cur=parseInt($('threshold').textContent)||8;
  const nv=Math.max(1,Math.min(10,cur+d));
  $('threshold').textContent=nv;
  sendCmd('set_threshold',{value:nv});
}

function sendHint(){
  const inp=$('hint');const t=inp.value.trim();
  if(!t)return;
  sendCmd('inject_hint',{text:t});
  inp.value='';
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

connect();
</script>
</body>
</html>"""
