// Read-only account inventory. Actual data stays in memory, outside distributable files.
window.receiveMijiaInventory = function(data) {
 if(data.status!=='ready')return;
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let assignments={};try{assignments=JSON.parse(localStorage.getItem('bluehome-floors-v1'))||{}}catch{}
 let selectedHome=data.homes[0]?.name||'未分组/共享设备', selectedFloor='全部楼层', selectedRoom='全部房间';
 const floorOf=d=>assignments[JSON.stringify([d.home,d.room])]||d.floor_hint||'待分配';
 const homes=[...new Set([...data.homes.map(h=>h.name),...data.devices.map(d=>d.home)])];
 const panel=document.querySelector('#floor-panel');panel.hidden=false;
 document.querySelector('.sidebar-note').innerHTML='<span class="dot"></span> 米家已接入<p>只读设备清单 · 开关未读取</p>';
 document.querySelector('.hero-text h2').textContent='你的家，一层层展开。';
 document.querySelector('.hero-text p').textContent='楼层、房间、设备，井然有序。';
 const mainAction=document.querySelector('#relax');mainAction.textContent='管理楼层 ↗';
 document.querySelector('.hero-text small').textContent='设备清单已接入 · 仅查看，不控制';
 document.querySelector('#reset').textContent='楼层设置';
 document.querySelector('.section-title h2').textContent='我的真实设备';
 document.querySelector('.section-title p').textContent='家庭 → 楼层 → 房间 · 在线状态不代表开关状态';
 document.querySelector('footer').textContent='● 米家只读清单 · 在线状态为接入时快照 · 电源状态尚未读取';
 document.querySelector('#device-count').nextElementSibling.textContent='当前家庭设备';
 document.querySelector('#on-count').nextElementSibling.textContent='在线设备 · 非开启数量';
 document.querySelector('.stats>div:last-child small').textContent='已发现两台 · 控制尚未接入';
 document.querySelector('#scene-view .heading p').textContent='真实场景尚未接入。当前只读查看，不发送设备指令。';
 document.querySelector('#scenes').innerHTML='<article class="scene-card"><div class="emoji">◈</div><h2>让每层楼，各有节奏。</h2><p>先完成楼层与房间分组，再接入真实设备控制和场景。</p><small>当前没有运行真实场景</small></article>';
 document.querySelector('#about').onclick=()=>{document.querySelector('#detail-body').innerHTML='<h2>米家已接入 · 只读</h2><p>设备名称、型号、房间与在线状态来自本次接入。尚未读取实际电源状态，也不发送控制指令。</p><p>楼层来自房间名称识别或本浏览器的手动设置，不会改动原有米家房间。</p>';document.querySelector('#details').showModal()};
 function type(d){return window.deviceIconType(d)}
 function render(){
  const homeDevices=data.devices.filter(d=>d.home===selectedHome);
  const floors=[...new Set(homeDevices.map(floorOf))].sort((a,b)=>a.localeCompare(b,'zh-CN',{numeric:true}));
  panel.innerHTML='<div class="inventory-toolbar"><label>家庭 <select id="home-select">'+homes.map(h=>`<option ${h===selectedHome?'selected':''}>${esc(h)}</option>`).join('')+'</select></label><span class="read-only-tag">已连接 · 只读</span></div><div class="floor-tabs">'+['全部楼层',...floors].map(f=>`<button data-floor="${esc(f)}" class="${f===selectedFloor?'active':''}">${esc(f)}<small>${homeDevices.filter(d=>f==='全部楼层'||floorOf(d)===f).length}</small></button>`).join('')+'</div>';
  document.querySelector('#home-select').onchange=e=>{selectedHome=e.target.value;selectedFloor='全部楼层';selectedRoom='全部房间';render()};
  panel.querySelectorAll('[data-floor]').forEach(b=>b.onclick=()=>{selectedFloor=b.dataset.floor;selectedRoom='全部房间';render()});
  const levelDevices=homeDevices.filter(d=>selectedFloor==='全部楼层'||floorOf(d)===selectedFloor);
  const rooms=['全部房间',...new Set(levelDevices.map(d=>d.room))];
  const filters=document.querySelector('#filters');filters.innerHTML=rooms.map(r=>`<button data-room-name="${esc(r)}" class="${r===selectedRoom?'active':''}">${esc(r)}</button>`).join('');
  filters.onclick=e=>{const b=e.target.closest('[data-room-name]');if(b){selectedRoom=b.dataset.roomName;render()}};
  document.querySelector('#device-count').textContent=homeDevices.length;document.querySelector('#on-count').textContent=homeDevices.filter(d=>d.online===true).length;
  document.querySelector('.profile span').innerHTML=esc(selectedHome)+'<small>已连接的家庭</small>';
  const list=document.querySelector('#devices');
  list.innerHTML=levelDevices.filter(d=>selectedRoom==='全部房间'||d.room===selectedRoom).map(d=>{const ir=d.model.startsWith('miir.');return `<article class="device"><div class="device-top"><span class="device-icon"><svg viewBox="0 0 24 24" aria-hidden="true">${icons[type(d)]}</svg></span><button class="more" data-live-detail="${d.key}" aria-label="${esc(d.name)}详情">···</button></div><h3>${esc(d.name)}</h3><div class="location">${esc(floorOf(d))} · ${esc(d.room)}</div><div class="device-bottom"><div class="state">${d.online===true?'● 在线':d.online===false?'○ 离线':'○ 在线情况未知'}<small>${ir?'红外设备 · 电源状态未知':'电源状态尚未读取'}</small></div><span class="read-only-tag">${ir?'红外':'只读'}</span></div></article>`}).join('')||'<p class="empty-state">当前分组暂无设备</p>';
  list.onclick=e=>{const b=e.target.closest('[data-live-detail]');if(!b)return;const d=data.devices.find(d=>d.key===Number(b.dataset.liveDetail));document.querySelector('#detail-body').innerHTML=`<div class="eyebrow">CONNECTED DEVICE</div><h2>${esc(d.name)}</h2><p>${esc(d.home)}<br>${esc(floorOf(d))} / ${esc(d.room)}<br>型号：${esc(d.model)}<br>接入时在线状态：${d.online===true?'在线':d.online===false?'离线':'未知'}</p><p>电源开关状态尚未读取。此页面不发送控制指令。${d.model.startsWith('miir.')?'红外遥控器在线不代表被控电器已开启。':''}</p>`;document.querySelector('#details').showModal()};
  if(window.updateSpatialHome)window.updateSpatialHome({home:selectedHome,rooms:(data.homes.find(h=>h.name===selectedHome)?.rooms||[]).map(r=>({name:r.name,floor:assignments[JSON.stringify([selectedHome,r.name])]||r.floor_hint||'待分配'})),devices:homeDevices.map(d=>({...d,floor:floorOf(d)})),floor:selectedFloor,onRoom:(floor,name)=>{selectedFloor=floor;selectedRoom=name;render()}});
  if(window.paintDeviceDashboard)window.paintDeviceDashboard();
 }
 function manage(){const h=data.homes.find(h=>h.name===selectedHome);const rooms=h?.rooms||[...new Set(data.devices.filter(d=>d.home===selectedHome).map(d=>d.room))].map(name=>({name}));document.querySelector('#detail-body').innerHTML='<div class="eyebrow">FLOOR ORGANIZATION</div><h2>每个房间，都有归属。</h2><p>'+esc(selectedHome)+' · 留空使用名称识别结果。只修改本浏览器分组。</p><form id="floor-form">'+rooms.map((r,i)=>'<label class="floor-field"><span>'+esc(r.name)+'</span><input data-floor-room="'+i+'" maxlength="20" placeholder="'+esc(r.floor_hint||'例如：2楼')+'" value="'+esc(assignments[JSON.stringify([selectedHome,r.name])]||'')+'"></label>').join('')+'<button class="primary" type="submit">保存楼层分组</button></form>';document.querySelector('#floor-form').onsubmit=e=>{e.preventDefault();const next={...assignments};document.querySelectorAll('[data-floor-room]').forEach(input=>{const key=JSON.stringify([selectedHome,rooms[Number(input.dataset.floorRoom)].name]);if(input.value.trim())next[key]=input.value.trim();else delete next[key]});try{localStorage.setItem('bluehome-floors-v1',JSON.stringify(next))}catch{toast('无法保存，请检查浏览器存储设置');return}assignments=next;selectedFloor='全部楼层';selectedRoom='全部房间';render();document.querySelector('#details').close();toast('楼层分组已保存 · 原有米家房间未改动')};document.querySelector('#details').showModal()}
 mainAction.onclick=manage;document.querySelector('#reset').onclick=manage;
 document.querySelectorAll('[data-nav]').forEach(b=>{const previous=b.onclick;b.onclick=()=>{previous();if(b.dataset.nav==='devices'){selectedFloor='全部楼层';selectedRoom='全部房间';render()}}});
 if(window.initDeviceDashboard)window.initDeviceDashboard({data,floorOf,scope:()=>({home:selectedHome,floor:selectedFloor,room:selectedRoom}),choose:(home,floor,room)=>{selectedHome=home;selectedFloor=floor||'全部楼层';selectedRoom=room||'全部房间';render()}});
 render();
};
{const script=document.createElement('script');script.src='/inventory.js';script.onerror=()=>{};document.head.append(script)}
