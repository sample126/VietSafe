'use strict';
const $ = (s, parent=document) => parent.querySelector(s);
const $$ = (s, parent=document) => [...parent.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const typeNames = {flood:'Ngập đường',traffic:'Ùn tắc',incident:'Sự cố giao thông'};
const typeIcons = {flood:'water',traffic:'car',incident:'alert'};
const typeColors = {flood:'blue',traffic:'orange',incident:'red'};
const statuses = {pending:'Chờ xác minh',verified:'Đã xác minh',resolved:'Đã xử lý',rejected:'Đã từ chối',expired:'Hết hạn'};
const state = {data:null,view:'map',filter:'all',horizon:0,selected:'HN-019',layers:{flood:true,traffic:true,incident:true,pending:true},
  reportPosition:null,picking:false,reports:[],routes:null,routeIndex:0,connected:false,lastGood:0};
let map, baseTiles, roadLayer, eventLayer, routeLayer, selectionLayer, placeLayer;
let refreshing=false, searchTimer, toastTimer, tileErrorCount=0, searchSerial=0;
const timeText = unix => new Date(unix*1000).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const ago = unix => {const s=Math.max(0,Math.floor(Date.now()/1000-unix));return s<60?'Vừa cập nhật':`${Math.floor(s/60)} phút trước`;};

// === Auth state ===
const authState = { user: null, token: localStorage.getItem('vietsafe_token') };

// === Tile providers ===
const TILE_PROVIDERS = {
  osm: { url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', attr:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>', maxZoom:19 },
  // To use TrackAsia: replace YOUR_KEY with your API key from https://track-asia.com
  // trackasia: { url:'https://tiles.track-asia.com/tiles/v3/{z}/{x}/{y}.png?key=YOUR_KEY', attr:'&copy; <a href="https://track-asia.com">TrackAsia</a> &copy; OpenStreetMap', maxZoom:19 }
};
const activeTileConfig = TILE_PROVIDERS.osm;

async function api(path, options={}) {
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),12000);
  const authHeaders = authState.token ? {'X-VietSafe-Session': authState.token} : {};
  try {
    const response=await fetch(path,{...options,signal:controller.signal,headers:{'X-VietSafe':'local',...authHeaders,...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});
    const data=await response.json();
    if(!response.ok) throw new Error(data.error || 'Không thể xử lý yêu cầu.');
    return data;
  } catch(e) {if(e.name==='AbortError') throw new Error('Máy chủ phản hồi chậm. Hãy thử lại.'); throw e;}
  finally {clearTimeout(timeout);}
}
const post = (path, body) => api(path,{method:'POST',body:JSON.stringify(body)});
function toast(message) {$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,5200);}

function initializeMap() {
  map=L.map('map',{zoomControl:false,minZoom:11,maxZoom:18}).setView([21.025,105.830],13);
  L.control.zoom({position:'bottomright'}).addTo(map);
  baseTiles=L.tileLayer(activeTileConfig.url,{
    maxZoom:activeTileConfig.maxZoom,attribution:activeTileConfig.attr});
  baseTiles.on('tileerror',()=>{if(++tileErrorCount>=6 && map.hasLayer(baseTiles)){
    map.removeLayer(baseTiles);$('#base-tiles').checked=false;$('#map-footnote').textContent='Sơ đồ ngoại tuyến · Mạng đường giản lược · Không dùng để dẫn đường';toast('Không tải được bản đồ nền. Đang hiển thị sơ đồ ngoại tuyến.');
  }});
  baseTiles.addTo(map);
  const geography=L.layerGroup().addTo(map);
  const lakes=[['Hồ Tây',[[21.043,105.825],[21.048,105.817],[21.058,105.812],[21.070,105.819],[21.073,105.835],[21.060,105.842],[21.048,105.839]]],['Hồ Hoàn Kiếm',[[21.0313,105.852],[21.0300,105.8537],[21.026,105.8537],[21.0252,105.8518],[21.028,105.8509]]],['Hồ Bảy Mẫu',[[21.0135,105.8443],[21.0134,105.8470],[21.009,105.8477],[21.0074,105.8460],[21.008,105.8444]]],['Hồ Thủ Lệ',[[21.0335,105.8006],[21.0339,105.8060],[21.0308,105.8078],[21.0300,105.8028]]]];
  for(const [name,shape] of lakes)L.polygon(shape,{color:'#b7d1d0',fillColor:'#c7dddd',fillOpacity:.8,weight:1,interactive:false}).addTo(geography).bindTooltip(name,{permanent:true,direction:'center',className:'water-label'});
  placeLayer=L.layerGroup().addTo(map);
  roadLayer=L.layerGroup().addTo(map);
  routeLayer=L.layerGroup().addTo(map);
  eventLayer=L.layerGroup().addTo(map);
  selectionLayer=L.layerGroup().addTo(map);
  map.on('click', e=>{if(state.picking) finishPick(e.latlng.lat,e.latlng.lng);});
  map.on('movestart',()=>$('#search-results').hidden=true);
}

async function refresh() {
  if(refreshing){await refreshing;return refresh();}
  let complete;
  refreshing=new Promise(resolve=>complete=resolve);
  try {
    const first=!state.data;
    state.data=await api('/api/snapshot');state.connected=true;state.lastGood=Date.now();
    $('#connection-error').hidden=true;
    $('#sync-status').textContent='Kết nối local · Dữ liệu mô phỏng';
    $('.status-dot').style.background='#49a68b';
    if(first) populateControls();
    updateDashboard();
    if(state.view==='reports') await loadReports();
  } catch(e) {
    state.connected=false;$('#connection-error').hidden=false;
    $('#sync-status').textContent=state.data?'Mất kết nối · Dữ liệu đã cũ':'Chưa kết nối máy chủ';
    $('.status-dot').style.background='#d86b5c';
  } finally {refreshing=false;complete();}
}

function populateControls() {
  const options=state.data.nodes.map(n=>`<option value="${esc(n.id)}">${esc(n.name)}</option>`).join('');
  $('#route-origin').innerHTML=options;$('#route-destination').innerHTML=options;
  $('#route-origin').value='caugiay';$('#route-destination').value='hoankiem';
  $('#forecast-road').innerHTML=state.data.roads.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join('');
  $('#forecast-road').value=state.selected;
  $('#address-options').innerHTML=state.data.nodes.map(n=>`<option value="${esc(n.name)}"></option>`).join('');
  for(const n of state.data.nodes) {
    L.circleMarker([n.lat,n.lng],{radius:2,weight:1,color:'#a5b8ab',fillOpacity:1,interactive:false}).addTo(placeLayer)
      .bindTooltip(esc(n.name),{permanent:true,direction:'bottom',className:'place-label',offset:[0,4]});
  }
  renderSources();
}

function updateDashboard() {
  const d=state.data;
  for(const type of ['flood','traffic','incident']) $(`#stat-${type}`).textContent=String(d.counts[type]).padStart(2,'0');
  $('#stat-rain').innerHTML=`${d.rainfall}<em>mm/h</em>`;
  $('#weather-caption').textContent=`${{normal:'Trời khô',rain:'Mưa lớn',storm:'Mưa rất lớn'}[d.scenario]} · ${d.temperature}°C`;
  $('#map-clock').textContent=timeText(d.generated_at);
  $('#event-total').textContent=d.events.length;
  $('#nav-count').textContent=d.pending;$('#nav-count').hidden=!d.pending;
  $('#forecast-scenario').value=d.scenario;$('#source-scenario').value=d.scenario;
  renderMap();renderEvents();renderInsight();
  if(state.view==='forecast') renderForecast();
  if(state.routes) {
    const label=$('#route-calculation-note');
    if(label) label.textContent=`Tính lúc ${timeText(state.routes.calculated_at)} · Bấm tìm tuyến để cập nhật.`;
  }
}

function roadColor(r) {
  if(!r.known) return '#aab5af';
  if(state.horizon) {
    const risk=r.forecast[state.horizon/15].risk;
    return risk>=65?'#d76e62':risk>=35?'#daa34d':'#74ad92';
  }
  if(r.blocked) return '#c95650';
  if(r.event_type && state.layers[r.event_type]) return {flood:'#568eeb',traffic:'#e9a34d',incident:'#df7469'}[r.event_type];
  return '#86b9a0';
}

function renderMap() {
  roadLayer.clearLayers();eventLayer.clearLayers();
  for(const r of state.data.roads) {
    const f=r.forecast[state.horizon/15];
    const color=roadColor(r), weight=r.id===state.selected?7:4;
    const line=L.polyline(r.coordinates,{color,weight,opacity:.88,dashArray:r.known?null:'5 6'}).addTo(roadLayer);
    line.bindTooltip(`<strong>${esc(r.name)}</strong><br>${!r.known?'Chưa đủ dữ liệu':state.horizon?`Dự báo +${state.horizon} phút · Nguy cơ ${f.risk}/100`:`${r.speed} km/h · ${r.blocked?'Đóng trong kịch bản':'Dữ liệu thử nghiệm'}`}`);
    line.on('click',e=>{L.DomEvent.stopPropagation(e);if(state.picking)finishPick(e.latlng.lat,e.latlng.lng);else selectRoad(r.id,true);});
  }
  if(!state.horizon) for(const e of state.data.events) {
    if(!state.layers[e.type] || (e.status==='pending'&&!state.layers.pending)) continue;
    const marker=L.marker([e.lat,e.lng],{icon:L.divIcon({className:`event-marker ${e.type} ${e.status==='pending'?'pending':''}`,html:icon(typeIcons[e.type]),iconSize:[32,32]}),title:`${typeNames[e.type]}: ${e.name}`}).addTo(eventLayer);
    marker.bindTooltip(`${esc(e.name)} · ${e.status==='pending'?'Chờ xác minh':typeNames[e.type]}`);
    marker.on('click',()=>state.picking?finishPick(e.lat,e.lng):showEvent(e.id));
  }
  $('#map-mode-label').hidden=!state.horizon;
  $('#map-mode-label').textContent=`Dự báo +${state.horizon} phút · Nguy cơ thấp → trung bình → cao`;
  $('.map-legend').innerHTML=state.horizon?
    '<span><i class="legend-dot green"></i>Thấp &lt;35</span><span><i class="legend-dot orange-bg"></i>Trung bình 35–64</span><span><i class="legend-dot red-bg"></i>Cao ≥65</span><span><i class="legend-dot gray-bg"></i>Chưa đủ dữ liệu</span>':
    '<span><i class="legend-dot green"></i>Thông thoáng</span><span><i class="legend-dot orange-bg"></i>Ùn tắc</span><span><i class="legend-dot blue-bg"></i>Ngập</span><span><i class="legend-dot red-bg"></i>Sự cố / đóng</span><span><i class="legend-dot gray-bg"></i>Chưa có dữ liệu</span>';
}

function renderEvents() {
  if(!state.data)return;
  const events=state.data.events.filter(e=>state.filter==='all'||e.type===state.filter);
  $('#event-list').innerHTML=events.length?events.map(e=>{
    const summary=e.status==='pending'?'Chưa được dùng cho cảnh báo tuyến':e.blocked?'Không thể lưu thông trong kịch bản':e.type==='flood'?`Độ sâu mô phỏng ${e.depth??'chưa đo'}${e.depth!=null?' cm':''}`:e.type==='traffic'?`Tốc độ mô phỏng ${e.speed} km/h`:'Phương tiện dừng gây cản trở';
    return `<button class="event-item" data-event="${esc(e.id)}"><span class="event-type-icon ${typeColors[e.type]}">${icon(typeIcons[e.type])}</span><div class="event-copy"><h3>${esc(e.name)}</h3><p>${esc(summary)}</p><div class="event-meta"><span class="tag tag-${e.status==='pending'?'gray':typeColors[e.type]}">${e.status==='pending'?'Chờ xác minh':typeNames[e.type]}</span><span>${e.origin==='demo'?'Mô phỏng':'Tại máy'} · ${ago(e.updated_at)}</span></div></div></button>`;
  }).join(''):`<div class="empty-state">${icon('check')}Không có cảnh báo thuộc nhóm này trong kịch bản hiện tại.</div>`;
}

function renderInsight() {
  const road=state.data.roads.find(r=>r.id===state.selected)||state.data.roads[0];
  $('#insight-road').textContent=road.name;
  const last=road.forecast[4];
  $('#insight-summary').textContent=road.known?`Sau 60 phút: nguy cơ ngập ${last.flood_risk}/100, tốc độ ước tính ${last.speed} km/h. Chọn một đoạn trên bản đồ để xem thêm.`:'Đoạn đường chưa đủ dữ liệu. Hệ thống không suy diễn thành trạng thái an toàn.';
  $('#mini-forecast').innerHTML=road.forecast.map((f,i)=>`<div class="mini-column ${i===2||i===4?'focus':''}"><b>${f.flood_risk??'—'}</b><div class="bar" style="height:${f.flood_risk??0}%"></div><span>${f.horizon?'+'+f.horizon+' phút':'Hiện tại'}</span></div>`).join('');
}

function selectRoad(id,details=false) {
  state.selected=id;$('#forecast-road').value=id;renderInsight();renderMap();
  if(state.view==='forecast')renderForecast();
  if(details)showRoadDetails(id);
}

function showRoadDetails(id,event=null) {
  const r=state.data.roads.find(r=>r.id===id);if(!r)return;
  const f=r.forecast[2];
  $('#detail-content').innerHTML=`<div class="dialog-heading"><div><div class="eyebrow teal-text">${event?.status==='pending'?'PHẢN ÁNH CHỜ XÁC MINH':'CHI TIẾT ĐOẠN ĐƯỜNG'}</div><h2>${esc(event?.name||r.name)}</h2></div><button class="icon-button close-dialog" aria-label="Đóng chi tiết">${icon('close')}</button></div><span class="tag tag-${event?.status==='pending'?'gray':'teal'}">${event?.status==='pending'?'Chưa ảnh hưởng định tuyến':r.origin==='demo'?'Dữ liệu mô phỏng':'Phản ánh đã xác minh tại máy'}</span><div class="detail-stats"><div><span>Tốc độ hiện tại</span><strong>${r.known?r.speed+' km/h':'Chưa rõ'}</strong></div><div><span>Nguy cơ ngập +30p</span><strong>${f.flood_risk==null?'Chưa rõ':f.flood_risk+'/100'}</strong></div><div><span>Lưu thông</span><strong>${!r.known?'Chưa rõ':r.blocked?'Bị chặn':'Có thể đi*'}</strong></div></div><p class="data-label">${esc((event?.sources||r.sources).join(' · '))} · ${timeText(event?.updated_at||r.updated_at)}</p><div class="detail-evidence">${esc((event?.evidence||r.evidence).join('\n'))}</div><p class="muted">*Trạng thái trong mạng thử nghiệm. Điểm nguy cơ là chỉ số theo quy tắc, không phải xác suất. Không dùng kết quả để quyết định đi qua vùng ngập thực tế.</p><div class="dialog-footer"><button class="button secondary" data-focus-road="${r.id}">${icon('pin')}Xem trên bản đồ</button><button class="button primary" data-forecast-detail="${r.id}">Xem dự báo ${icon('arrow')}</button></div>`;
  if(!$('#detail-dialog').open)$('#detail-dialog').showModal();
}
function showEvent(id) {const e=state.data.events.find(e=>e.id===id);if(!e)return;selectRoad(e.road_id);map.setView([e.lat,e.lng],15);showRoadDetails(e.road_id,e);}

function setView(view) {
  // Admin-only views
  if((view==='sources'||view==='reports')&&(!authState.user||authState.user.role!=='admin')){
    toast('Vui lòng đăng nhập tài khoản quản trị để truy cập.');return;
  }
  state.view=view;$$('.view').forEach(el=>el.hidden=el.id!==view+'-view');
  window.scrollTo({top:0,behavior:'instant'});
  $$('.nav-item[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  if(view==='map') requestAnimationFrame(()=>map.invalidateSize());
  if(view==='forecast'&&state.data)renderForecast();
  if(view==='reports')loadReports();
}

function renderForecast() {
  const r=state.data.roads.find(r=>r.id===$('#forecast-road').value);if(!r)return;
  if(!r.known){$('#forecast-chart').innerHTML='<div class="empty-state">Chưa đủ dữ liệu để dự báo đoạn đường này. Không có dữ liệu không có nghĩa là không có nguy cơ.</div>';return;}
  const xs=[65,270,475,680,885],y=v=>205-v*1.75;
  const path=key=>r.forecast.map((f,i)=>`${i?'L':'M'}${xs[i]},${y(f[key])}`).join(' ');
  let svg=`<svg class="large-chart" viewBox="0 0 950 245" role="img" aria-label="Dự báo điểm nguy cơ ngập và rủi ro tổng hợp cho ${esc(r.name)}">`;
  for(const v of [0,25,50,75,100])svg+=`<line x1="65" y1="${y(v)}" x2="885" y2="${y(v)}" stroke="#e7ede7" stroke-dasharray="4 5"/><text x="30" y="${y(v)+4}" fill="#91a494">${v}</text>`;
  svg+=`<path d="${path('flood_risk')} L885,205 L65,205 Z" fill="#edf3fd" stroke="none"/><path d="${path('flood_risk')}" fill="none" stroke="#5188d7" stroke-width="3"/><path d="${path('risk')}" fill="none" stroke="#dfaa5c" stroke-width="3" stroke-dasharray="7 5"/>`;
  r.forecast.forEach((f,i)=>{svg+=`<circle cx="${xs[i]}" cy="${y(f.flood_risk)}" r="5" fill="white" stroke="#5188d7" stroke-width="2"/><text x="${xs[i]}" y="234" text-anchor="middle" fill="#89a18e">${f.horizon?'+'+f.horizon+' phút':'Hiện tại'}</text>`;});
  svg+='</svg>';
  $('#forecast-chart').innerHTML=svg+`<div class="chart-legend"><span><i class="legend-dot blue-bg"></i>Nguy cơ ngập /100</span><span><i class="legend-dot orange-bg"></i>Rủi ro tổng hợp /100</span></div><div class="forecast-table-wrap"><table class="forecast-table"><thead><tr><th>Thời điểm</th><th>Nguy cơ ngập</th><th>Tốc độ ước tính</th><th>Rủi ro tổng hợp</th></tr></thead><tbody>${r.forecast.map(f=>`<tr><td>${f.horizon?'Sau '+f.horizon+' phút':'Hiện tại'}</td><td>${f.flood_risk}/100</td><td>${f.speed} km/h</td><td><span class="tag tag-${f.risk>=65?'red':f.risk>=35?'orange':'teal'}">${f.label} · ${f.risk}/100</span></td></tr>`).join('')}</tbody></table></div>`;
}

function renderSources() {
  const sources=[
    ['chart','Bộ mô phỏng giao thông','Đang chạy tại máy','teal','36 đoạn đường, 25 nút. Cập nhật mỗi 10 giây theo kịch bản.','—'],
    ['report','Phản ánh cộng đồng','Lưu thật tại máy','teal','Vị trí, mô tả, ảnh lưu trong SQLite. Cần xác minh thủ công.','—'],
    ['cloud','API Thời tiết (OpenWeather / NCHMF)','Sẵn sàng tích hợp','orange','Lượng mưa thực, dự báo 3 giờ tới. 3 kịch bản mô phỏng hiện tại.','Đăng ký API key OpenWeatherMap miễn phí (1000 calls/ngày) hoặc crawl bản tin NCHMF.'],
    ['car','VOV Giao thông','Chưa kết nối','gray','Bản tin ùn tắc, tai nạn, đường bị ảnh hưởng theo thời gian thực.','Xin phép API/RSS từ VOV. Hoặc crawl vovgiaothong.vn + NLP trích xuất tên đường, loại sự kiện.'],
    ['water','Hệ thống thoát nước Hà Nội','Chưa kết nối','gray','Mực nước, điểm ngập, vận hành trạm bơm tại các trạm quan trắc.','Hợp tác với Cty TNHH MTV Thoát nước HN. Lấy dữ liệu qua API/SFTP định kỳ.'],
    ['layers','Camera giao thông (AI)','Chưa kết nối','gray','Ước lượng mật độ, phát hiện xe dừng bất thường qua RTSP stream.','Tích hợp RTSP từ hệ thống camera Sở GTVT. YOLO + ByteTrack phân tích.'],
    ['water','Google Flood Hub','Có thể tham khảo','orange','Dự báo lũ lụt Google cho khu vực sông Hồng, sông Tô Lịch.','API công khai tại sites.research.google/floods. Dữ liệu dự báo ngập vùng sông.'],
    ['alert','Mạng xã hội (Facebook, Zalo)','Chưa kết nối','gray','Bài viết công khai từ các nhóm cộng đồng giao thông Hà Nội.','Thu thập bài viết công khai. NLP phân loại và trích xuất vị trí.'],
    ['route','HERE Traffic / TomTom','Chưa kết nối','gray','Lưu lượng giao thông thời gian thực từ API thương mại.','Freemium: HERE 250K calls/tháng. TomTom có tier miễn phí tương tự.'],
    ['pin','Cảm biến IoT ngập','Chưa kết nối','gray','Cảm biến siêu âm đo mực nước tại các điểm ngập trọng điểm.','Triển khai cảm biến tại 10–15 điểm ngập. Truyền dữ liệu qua LoRa/4G.'],
  ];
  $('#source-grid').innerHTML=sources.map(([i,n,s,c,d,plan])=>`<article class="source-card">${icon(i)}<h3>${n}</h3><span class="tag tag-${c}">${s}</span><p>${d}</p>${plan!=='—'?`<p class="source-plan"><strong>Kế hoạch thu thập:</strong> ${plan}</p>`:''}</article>`).join('');
}

async function changeScenario(value) {
  try {await post('/api/scenario',{scenario:value});await refresh();clearRoutes();toast('Đã đổi kịch bản. Bản đồ và dự báo đã cập nhật.');}
  catch(e){toast(e.message);if(state.data){$('#source-scenario').value=state.data.scenario;$('#forecast-scenario').value=state.data.scenario;}}
}

async function searchLocation() {
  const serial=++searchSerial,query=$('#map-search').value.trim();
  if(!query){$('#search-results').hidden=true;return;}
  try {
    const result=await api('/api/search?q='+encodeURIComponent(query));if(serial!==searchSerial)return;
    const container=$('#search-results');container.replaceChildren();container.hidden=false;
    if(!result.results.length){container.innerHTML='<p>Chưa có địa điểm này trong vùng thử nghiệm. Thử “Láng Hạ”, “Cầu Giấy”, “Hoàn Kiếm”…</p>';return;}
    for(const place of result.results){const btn=document.createElement('button');btn.type='button';btn.textContent=place.name;btn.addEventListener('click',()=>{
      map.setView([place.lat,place.lng],15);$('#map-search').value=place.name;container.hidden=true;
      selectionLayer.clearLayers();L.circleMarker([place.lat,place.lng],{radius:9,color:'#087f72',fillOpacity:.2}).addTo(selectionLayer);
      if(place.kind==='road')selectRoad(place.id);
    });container.append(btn);}
  }catch(e){toast(e.message);}
}

function clearRoutes(){routeLayer.clearLayers();state.routes=null;$('#route-results').innerHTML='<div class="empty-state">Chọn điểm đi và đến, sau đó tìm tuyến theo dữ liệu mới nhất.</div>';}
function openRoute(){if(!state.data){toast('Đang tải dữ liệu, vui lòng thử lại.');return;}$('#event-panel').hidden=true;$('#route-panel').hidden=false;requestAnimationFrame(()=>map.invalidateSize());}
async function findRoutes(e){
  e.preventDefault();if(!state.connected){toast('Cần kết nối máy chủ để tính tuyến mới.');return;}
  const button=$('button[type=submit]',$('#route-form'));button.disabled=true;button.textContent='Đang tính tuyến…';
  try{
    const query=new URLSearchParams({origin:$('#route-origin').value,destination:$('#route-destination').value,horizon:$('#route-time').value,vehicle:$('#route-vehicle').value});
    state.routes=await api('/api/routes?'+query);state.routeIndex=0;renderRoutes();
  }catch(err){clearRoutes();$('#route-results').innerHTML=`<div class="empty-state">${esc(err.message)}</div>`;}
  finally{button.disabled=false;button.innerHTML=icon('route')+'Tìm tuyến gợi ý';}
}
function renderRoutes(){
  routeLayer.clearLayers();const result=state.routes;
  if(!result.routes.length){$('#route-results').innerHTML=`<div class="empty-state">${icon('alert')}${esc(result.message)}</div>`;return;}
  $('#route-results').innerHTML=result.routes.map((r,i)=>`<button class="route-choice ${i===state.routeIndex?'selected':''}" data-route-index="${i}"><h3>${esc(r.title)}</h3><strong>${Math.ceil(r.eta_minutes)}<small>phút</small></strong><span class="data-label">${r.distance_km} km</span><p>${esc(r.steps.join(' → '))}</p><p>${r.warnings.length?'Còn cảnh báo trên '+r.warnings.length+' đoạn':'Không đi qua sự kiện đang hiển thị'} · Mô phỏng</p></button>`).join('')+`<p class="route-timestamp" id="route-calculation-note">Tính lúc ${timeText(result.calculated_at)} · Loại ${result.excluded} đoạn đóng / thiếu dữ liệu.</p>`;
  const chosen=result.routes[state.routeIndex];
  for(const [i,r] of result.routes.entries())if(i!==state.routeIndex)L.polyline(r.coordinates,{color:'#adb7b4',weight:6,opacity:.8,dashArray:'7 6'}).addTo(routeLayer);
  L.polyline(chosen.coordinates,{color:'white',weight:10,opacity:.95}).addTo(routeLayer);
  const line=L.polyline(chosen.coordinates,{color:'#0c7665',weight:6,opacity:1}).addTo(routeLayer);
  for(const [coord,label] of [[chosen.coordinates[0],'A'],[chosen.coordinates.at(-1),'B']])
    L.marker(coord,{icon:L.divIcon({className:'event-marker',html:`<strong>${label}</strong>`,iconSize:[32,32]})}).addTo(routeLayer);
  map.fitBounds(line.getBounds(),{padding:[60,75],maxZoom:14});
}

function openReport(){if(!state.data){toast('Đang tải dữ liệu, vui lòng thử lại.');return;}if(!authState.user){$('#login-dialog').showModal();return;}$('#report-error').hidden=true;$('#report-dialog').showModal();}
function setReportPosition(lat,lng,address){
  state.reportPosition={lat,lng};if(address)$('#report-address').value=address;
  $('#report-coordinates').textContent=`Đã đặt vị trí: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  $('#report-coordinates').classList.add('valid');
}
function startPick(){state.picking=true;$('#report-dialog').close();setView('map');$('#pick-banner').hidden=false;$('.map-surface').classList.add('picking');$('#map').scrollIntoView({behavior:'smooth',block:'center'});}
function finishPick(lat,lng){
  if(lat<20.98||lat>21.065||lng<105.77||lng>105.88){toast('Hãy chọn vị trí trong vùng thử nghiệm Hà Nội.');return;}
  state.picking=false;$('#pick-banner').hidden=true;$('.map-surface').classList.remove('picking');
  const nearest=state.data.roads.map(r=>({r,d:Math.hypot(lat-(r.coordinates[0][0]+r.coordinates[1][0])/2,lng-(r.coordinates[0][1]+r.coordinates[1][1])/2)})).sort((a,b)=>a.d-b.d)[0].r;
  setReportPosition(lat,lng,nearest.name);selectionLayer.clearLayers();L.circleMarker([lat,lng],{radius:9,color:'#087f72',fillOpacity:.3}).addTo(selectionLayer);$('#report-dialog').showModal();
}
function geolocate(forReport=false){
  if(!navigator.geolocation){toast('Trình duyệt không hỗ trợ định vị. Bạn có thể chọn trên bản đồ.');return;}
  toast('Đang xác định vị trí. Cho phép trình duyệt truy cập vị trí nếu được hỏi.');
  navigator.geolocation.getCurrentPosition(p=>{
    const {latitude:lat,longitude:lng}=p.coords;
    if(lat<20.98||lat>21.065||lng<105.77||lng>105.88){toast('Bạn đang ngoài vùng thử nghiệm Hà Nội. Hãy chọn địa chỉ hoặc ghim trong vùng.');return;}
    if(forReport)setReportPosition(lat,lng,'Vị trí GPS của tôi');
    else{map.setView([lat,lng],15);selectionLayer.clearLayers();L.circleMarker([lat,lng],{radius:9,color:'#087f72'}).addTo(selectionLayer);}
  },()=>toast('Chưa lấy được GPS. Hãy nhập địa điểm hoặc chọn vị trí trên bản đồ.'),{timeout:10000,maximumAge:60000});
}
async function locateReportAddress(){
  const value=$('#report-address').value.trim();if(!value){toast('Hãy nhập tên đường hoặc địa điểm.');return;}
  try{const result=await api('/api/search?q='+encodeURIComponent(value));const exact=result.results.find(p=>p.name.toLocaleLowerCase('vi')===value.toLocaleLowerCase('vi'));
    if(exact||result.results.length===1){const p=exact||result.results[0];setReportPosition(p.lat,p.lng,p.name);}
    else if(result.results.length>1){$('#report-error').textContent='Có nhiều địa điểm phù hợp: '+result.results.slice(0,4).map(p=>p.name).join('; ')+'. Chọn tên đầy đủ hoặc đặt ghim.';$('#report-error').hidden=false;}
    else{toast('Địa chỉ chưa có trong danh mục local. Dùng “Chọn trên bản đồ” để đặt vị trí chính xác.');}
  }catch(e){toast(e.message);}
}

async function submitReport(event){
  event.preventDefault();$('#report-error').hidden=true;
  if(!state.reportPosition){$('#report-error').textContent='Hãy định vị địa chỉ, dùng GPS hoặc chọn trên bản đồ trước khi gửi.';$('#report-error').hidden=false;return;}
  const button=$('#submit-report');button.disabled=true;
  try{
    let image=null;const file=$('#report-image').files[0];
    if(file){if(file.size>1500000||!['image/jpeg','image/png','image/webp'].includes(file.type))throw new Error('Ảnh JPG, PNG hoặc WebP tối đa 1,5 MB.');
      image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Không đọc được ảnh.'));reader.readAsDataURL(file);});}
    const result=await post('/api/reports',{...state.reportPosition,address:$('#report-address').value,type:$('input[name=type]:checked').value,
      severity:Number($('#report-severity').value),description:$('#report-description').value,image});
    $('#report-dialog').close();$('#report-form').reset();state.reportPosition=null;$('#report-coordinates').textContent='Chưa chọn tọa độ.';$('#report-coordinates').classList.remove('valid');
    toast(result.duplicate?'Phản ánh trùng đã được lưu trước đó.':`Đã lưu ${result.id}. Phản ánh đang chờ xác minh.`);await refresh();
  }catch(e){$('#report-error').textContent=e.message;$('#report-error').hidden=false;}
  finally{button.disabled=false;}
}

async function loadReports(){
  try{state.reports=(await api('/api/reports')).reports;renderReports();}catch(e){$('#reports-list').innerHTML=`<div class="empty-state">${esc(e.message)}</div>`;}
}
function renderReports(){
  const filter=$('#report-status-filter').value, reports=state.reports.filter(r=>filter==='all'||r.status===filter);
  $('#reports-list').innerHTML=reports.length?reports.map(r=>`<article class="review-card"><div class="review-top"><h3>${esc(r.address)} <span class="data-label">· ${typeNames[r.type]}</span></h3><span class="tag tag-${r.status==='verified'?'teal':r.status==='pending'?'orange':'gray'}">${statuses[r.status]}</span></div><p>${esc(r.description)}</p><div class="review-meta">${esc(r.id)} · ${esc(r.road_id)} · Mức ${r.severity}/3 · ${new Date(r.created_at*1000).toLocaleString('vi-VN')} · ${r.lat.toFixed(5)}, ${r.lng.toFixed(5)}</div>${r.media_url?`<a href="${esc(r.media_url)}" target="_blank" rel="noopener"><img class="review-image" src="${esc(r.media_url)}" alt="Ảnh hiện trường do người dùng cung cấp"></a>`:''}<div class="review-actions">${r.status==='pending'?`<button class="approve" data-review-id="${esc(r.id)}" data-status="verified">Xác minh phản ánh</button><button data-review-id="${esc(r.id)}" data-status="rejected">Từ chối</button>`:r.status==='verified'?`<button class="approve" data-review-id="${esc(r.id)}" data-status="resolved">Đánh dấu đã xử lý</button>`:''}<button data-report-map="${esc(r.id)}">Xem vị trí</button></div></article>`).join(''):`<div class="empty-state">${icon('report')}${state.reports.length?'Chưa có phản ánh thuộc trạng thái này.':'Chưa có phản ánh tại máy. Nhấn “Gửi phản ánh” để đóng góp thông tin đầu tiên.'}</div>`;
}

document.addEventListener('click',async e=>{
  const button=e.target.closest('button');if(!button)return;
  if(button.dataset.view)setView(button.dataset.view);
  if(button.classList.contains('close-dialog'))button.closest('dialog').close();
  if(button.dataset.filter){state.filter=button.dataset.filter;$$('#event-filters button').forEach(b=>b.classList.toggle('active',b.dataset.filter===state.filter));renderEvents();}
  if(button.dataset.horizon){state.horizon=Number(button.dataset.horizon);$$('#map-horizon button').forEach(b=>b.classList.toggle('active',b===button));if(state.data)renderMap();}
  if(button.dataset.event)showEvent(button.dataset.event);
  if(button.dataset.focusRoad){$('#detail-dialog').close();setView('map');const r=state.data.roads.find(r=>r.id===button.dataset.focusRoad);map.fitBounds(r.coordinates,{padding:[100,100],maxZoom:15});}
  if(button.dataset.forecastDetail){$('#detail-dialog').close();selectRoad(button.dataset.forecastDetail);setView('forecast');}
  if(button.dataset.routeIndex){state.routeIndex=Number(button.dataset.routeIndex);renderRoutes();}
  if(button.dataset.reviewId){button.disabled=true;try{await post('/api/reports/'+button.dataset.reviewId,{status:button.dataset.status});await loadReports();await refresh();clearRoutes();toast('Đã cập nhật trạng thái phản ánh.');}catch(err){toast(err.message);button.disabled=false;}}
  if(button.dataset.reportMap){const r=state.reports.find(r=>r.id===button.dataset.reportMap);setView('map');map.setView([r.lat,r.lng],15);selectionLayer.clearLayers();L.circleMarker([r.lat,r.lng],{radius:10,color:'#087f72'}).addTo(selectionLayer);}
});
$('#search-form').addEventListener('submit',e=>{e.preventDefault();searchLocation();});
$('#map-search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(searchLocation,300);});
$('#toggle-layers').addEventListener('click',()=>$('#layer-menu').hidden=!$('#layer-menu').hidden);
$$('[data-layer]').forEach(el=>el.addEventListener('change',()=>{state.layers[el.dataset.layer]=el.checked;if(state.data)renderMap();}));
$('#base-tiles').addEventListener('change',e=>{if(e.target.checked){tileErrorCount=0;baseTiles.addTo(map);$('#map-footnote').textContent='Mạng đường giản lược · Không dùng để dẫn đường thực tế';}else{map.removeLayer(baseTiles);$('#map-footnote').textContent='Sơ đồ ngoại tuyến · Mạng đường giản lược · Không dùng để dẫn đường';}});
$('#fit-map').addEventListener('click',()=>{if(state.data)map.fitBounds(state.data.nodes.map(n=>[n.lat,n.lng]),{padding:[40,55]});});
$('#my-location').addEventListener('click',()=>geolocate());
$('#open-report').addEventListener('click',openReport);
$('#about-button').addEventListener('click',()=>$('#about-dialog').showModal());
$('#open-route').addEventListener('click',openRoute);
$('#close-route').addEventListener('click',()=>{$('#route-panel').hidden=true;$('#event-panel').hidden=false;routeLayer.clearLayers();});
$('#route-form').addEventListener('submit',findRoutes);
$('#forecast-road').addEventListener('change',()=>{state.selected=$('#forecast-road').value;renderForecast();renderInsight();});
$('#forecast-scenario').addEventListener('change',e=>changeScenario(e.target.value));
$('#source-scenario').addEventListener('change',e=>changeScenario(e.target.value));
$('#report-pick').addEventListener('click',startPick);
$('#cancel-pick').addEventListener('click',()=>{state.picking=false;$('#pick-banner').hidden=true;$('.map-surface').classList.remove('picking');$('#report-dialog').showModal();});
$('#report-gps').addEventListener('click',()=>geolocate(true));
$('#report-find').addEventListener('click',locateReportAddress);
$('#report-address').addEventListener('input',()=>{state.reportPosition=null;$('#report-coordinates').textContent='Địa chỉ đã thay đổi. Hãy định vị lại hoặc chọn trên bản đồ.';$('#report-coordinates').classList.remove('valid');const n=state.data.nodes.find(n=>n.name===$('#report-address').value);if(n)setReportPosition(n.lat,n.lng);});
$('#report-form').addEventListener('submit',submitReport);
$('#refresh-reports').addEventListener('click',loadReports);
$('#report-status-filter').addEventListener('change',renderReports);
$$('dialog').forEach(dialog=>dialog.addEventListener('click',e=>{if(e.target===dialog){const rect=dialog.getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)dialog.close();}}));

// === Auth functions ===
async function checkAuth() {
  if(!authState.token){authState.user=null;updateAuthUI();return;}
  try{const data=await api('/api/auth/me');authState.user=data.user;} catch{authState.user=null;authState.token=null;localStorage.removeItem('vietsafe_token');}
  updateAuthUI();
}
function updateAuthUI() {
  const user=authState.user;
  const btn=$('#auth-button'), label=$('#auth-label');
  if(user){
    btn.classList.add('logged-in');
    label.textContent=user.display_name;
    btn.title='Tài khoản: '+user.username;
  } else {
    btn.classList.remove('logged-in');
    label.textContent='Đăng nhập';
    btn.title='Đăng nhập';
  }
  // Show/hide admin-only nav items
  $$('.admin-only').forEach(el=>{el.hidden=!(user&&user.role==='admin');});
  // If currently on an admin-only view and not admin, switch to map
  if((state.view==='sources'||state.view==='reports')&&(!user||user.role!=='admin'))setView('map');
  // Close user menu
  $('#user-menu').hidden=true;
  // Update user menu info
  if(user){
    $('#user-display-name').textContent=user.display_name;
    $('#user-role-label').textContent=user.role==='admin'?'Quản trị viên':'Người dân';
  }
}
async function doLogin(e) {
  e.preventDefault();$('#login-error').hidden=true;
  const btn=$('#submit-login');btn.disabled=true;
  try {
    const result=await post('/api/auth/login',{username:$('#login-username').value,password:$('#login-password').value});
    authState.user=result.user;authState.token=result.token;localStorage.setItem('vietsafe_token',result.token);
    updateAuthUI();$('#login-dialog').close();$('#login-form').reset();
    toast('Xin chào, '+result.user.display_name+'!');
  } catch(err){$('#login-error').textContent=err.message;$('#login-error').hidden=false;}
  finally{btn.disabled=false;}
}
async function doRegister(e) {
  e.preventDefault();$('#register-error').hidden=true;
  const btn=$('#submit-register');btn.disabled=true;
  try {
    const result=await post('/api/auth/register',{username:$('#reg-username').value,password:$('#reg-password').value,display_name:$('#reg-display').value});
    authState.user=result.user;authState.token=result.token;localStorage.setItem('vietsafe_token',result.token);
    updateAuthUI();$('#register-dialog').close();$('#register-form').reset();
    toast('Đăng ký thành công! Xin chào, '+result.user.display_name+'!');
  } catch(err){$('#register-error').textContent=err.message;$('#register-error').hidden=false;}
  finally{btn.disabled=false;}
}
async function doLogout() {
  try{await post('/api/auth/logout',{});}catch{}
  authState.user=null;authState.token=null;localStorage.removeItem('vietsafe_token');
  updateAuthUI();$('#user-menu').hidden=true;toast('Đã đăng xuất.');
}

// === Alert banner ===
function updateAlertBanner() {
  if(!state.data) return;
  const blocked=state.data.roads.filter(r=>r.blocked);
  if(blocked.length>0){
    $('#alert-text').textContent=`⚠ ${blocked.length} đoạn đường bị chặn: ${blocked.map(r=>r.name).join(', ')}. Hãy kiểm tra tuyến trước khi di chuyển.`;
    $('#alert-banner').hidden=false;
  } else {
    $('#alert-banner').hidden=true;
  }
}

// Auth event listeners
$('#auth-button').addEventListener('click',()=>{
  if(authState.user){$('#user-menu').hidden=!$('#user-menu').hidden;}
  else{$('#login-dialog').showModal();}
});
$('#logout-button').addEventListener('click',doLogout);
$('#login-form').addEventListener('submit',doLogin);
$('#register-form').addEventListener('submit',doRegister);
$('#show-register').addEventListener('click',()=>{$('#login-dialog').close();$('#register-dialog').showModal();});
$('#show-login').addEventListener('click',()=>{$('#register-dialog').close();$('#login-dialog').showModal();});
$('#dismiss-alert').addEventListener('click',()=>$('#alert-banner').hidden=true);
document.addEventListener('click',e=>{if(!e.target.closest('#user-menu')&&!e.target.closest('#auth-button'))$('#user-menu').hidden=true;});

// Hook alert banner into refresh cycle
const _originalRefresh = refresh;
refresh = async function() { await _originalRefresh(); updateAlertBanner(); };

// === Init ===
if(typeof L==='undefined'){$('#connection-error').hidden=false;$('#connection-error').textContent='Thiếu thư viện bản đồ local. Kiểm tra thư mục public/vendor.';}
else{initializeMap();checkAuth();refresh();setInterval(refresh,10000);}
