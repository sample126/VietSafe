'use strict';
const $ = (s, parent=document) => parent.querySelector(s);
const $$ = (s, parent=document) => [...parent.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const typeNames = {flood:'Ngập đường',traffic:'Ùn tắc',incident:'Sự cố giao thông'};
const typeIcons = {flood:'water',traffic:'car',incident:'alert'};
const typeColors = {flood:'blue',traffic:'orange',incident:'red'};
const statuses = {pending:'Chờ xác minh',verified:'Đã xác minh',resolved:'Đã xử lý',rejected:'Đã từ chối',expired:'Hết hạn'};
const state = {data:null,view:'map',filter:'all',horizon:0,selected:'HN-019',layers:{flood:true,traffic:true,incident:true,pending:true,majorRoads:true,demoRoads:true},
  reportPosition:null,picking:false,routePicking:null,reports:[],routes:null,routeIndex:0,connected:false,lastGood:0};
let map, baseTiles, roadLayer, eventLayer, routeLayer, selectionLayer, placeLayer;
let majorRoadLines={};
let refreshing=false, searchTimer, toastTimer, tileErrorCount=0, searchSerial=0;
let lastRenderKey='';
const timeText = unix => new Date(unix*1000).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const ago = unix => {const s=Math.max(0,Math.floor(Date.now()/1000-unix));return s<60?'Vừa cập nhật':`${Math.floor(s/60)} phút trước`;};

// === Auth state ===
const authState = { user: null, token: localStorage.getItem('vietsafe_token') };

// === Tile providers ===
// Nền chính: OpenFreeMap Positron (vector OpenMapTiles, không cần khóa).
// Khi WebGL/tile lỗi: MapTiler nếu có khóa, Stadia, OSM, rồi sơ đồ ngoại tuyến.
const STADIA_API_KEY = '';
const TILE_PROVIDERS = {
  openfreemap: { style:'https://tiles.openfreemap.org/styles/positron',
    attr:'&copy; <a href="https://openfreemap.org/" target="_blank" rel="noopener">OpenFreeMap</a> &copy; <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' },
  openmaptiles: { url:'https://api.maptiler.com/maps/openstreetmap/{z}/{x}/{y}.png?key={key}',
    attr:'&copy; <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>', maxZoom:19 },
  stadia: { url:'https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png'+(STADIA_API_KEY?`?api_key=${encodeURIComponent(STADIA_API_KEY)}`:''),
    attr:'&copy; <a href="https://www.stadiamaps.com/" target="_blank" rel="noopener">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>', maxZoom:20 },
  osm: { url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', attr:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>', maxZoom:19 },
};
const TILE_ORDER = ['openfreemap','openmaptiles','stadia','osm'];
// Khóa vùng nhìn trong Hà Nội: tránh kéo bản đồ ra vùng biển đảo mà tile toàn cầu ghi nhãn không theo quy ước Việt Nam.
const HANOI_BOUNDS = [[20.58,105.27],[21.36,106.08]];
let tileProviderIndex = 0;
let maptilerKey = '';
function nextTileProvider(after){for(let i=after+1;i<TILE_ORDER.length;i++){if(TILE_ORDER[i]==='openfreemap'&&(!window.VietSafeVectorMaps||!window.WebGL2RenderingContext))continue;if(TILE_ORDER[i]==='openmaptiles'&&!maptilerKey)continue;return i;}return -1;}

async function api(path, options={}) {
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),options.timeoutMs??12000);
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

const FOOTNOTE_ONLINE='Tuyến đường OSM · Dữ liệu cảnh báo mô phỏng · Không dùng để dẫn đường';
const FOOTNOTE_OFFLINE='Nền ngoại tuyến · Tuyến đường OSM · Cảnh báo mô phỏng';
function buildTileLayer(key) {
  const cfg=TILE_PROVIDERS[key];
  if(key==='openfreemap')return window.VietSafeVectorMaps.maplibreGL({style:cfg.style,interactive:false,attributionControl:{customAttribution:cfg.attr}});
  const url=key==='openmaptiles'?cfg.url.replace('{key}',encodeURIComponent(maptilerKey)):cfg.url;
  const layer=L.tileLayer(url,{maxZoom:cfg.maxZoom,attribution:cfg.attr});
  layer.on('tileerror',()=>{if(++tileErrorCount>=6 && map.hasLayer(layer)) switchTileProvider();});
  return layer;
}
function addBaseLayer(){try{baseTiles.addTo(map);}catch(error){if(TILE_ORDER[tileProviderIndex]!=='openfreemap')throw error;switchTileProvider();return;}map.getContainer().classList.toggle('map-vector',TILE_ORDER[tileProviderIndex]==='openfreemap');if(TILE_ORDER[tileProviderIndex]!=='openfreemap')return;const layer=baseTiles,gl=layer.getMaplibreMap();let loaded=false;const timeout=setTimeout(()=>{if(!loaded&&map.hasLayer(layer))switchTileProvider();},10000);gl.once('load',()=>{loaded=true;clearTimeout(timeout);for(const id of ['label_city','label_city_capital','label_town','water_name_point_label','water_name_line_label'])if(gl.getLayer(id))gl.setLayoutProperty(id,'text-field',['coalesce',['get','name:vi'],['get','name'],['get','name_en']]);});gl.on('error',()=>{if(!loaded&&map.hasLayer(layer)){clearTimeout(timeout);switchTileProvider();}});}
// Hết nhà cung cấp tile thì rơi xuống sơ đồ ngoại tuyến (nền lưới CSS + hồ vẽ tay).
function switchTileProvider() {
  map.removeLayer(baseTiles);tileErrorCount=0;
  const next=nextTileProvider(tileProviderIndex);
  if(next!==-1){tileProviderIndex=next;baseTiles=buildTileLayer(TILE_ORDER[tileProviderIndex]);addBaseLayer();return;}
  tileProviderIndex=nextTileProvider(-1);baseTiles=buildTileLayer(TILE_ORDER[tileProviderIndex]);
  setBaseTiles(false);$('#base-tiles').checked=false;toast('Không tải được bản đồ nền. Đang hiển thị sơ đồ ngoại tuyến.');
}
function setBaseTiles(on) {
  if(on){if(!map.hasLayer(baseTiles)){tileErrorCount=0;addBaseLayer();}map.removeLayer(geographyLayer);$('#map-footnote').textContent=FOOTNOTE_ONLINE;}
  else{if(map.hasLayer(baseTiles))map.removeLayer(baseTiles);map.getContainer().classList.remove('map-vector');geographyLayer.addTo(map);$('#map-footnote').textContent=FOOTNOTE_OFFLINE;}
}
let geographyLayer;
function initializeMap(key='') {
  maptilerKey=key;tileProviderIndex=nextTileProvider(-1);
  map=L.map('map',{zoomControl:false,minZoom:9,maxZoom:18,maxBounds:HANOI_BOUNDS,maxBoundsViscosity:1}).setView([21.02,105.79],10);
  const syncLabelVisibility=()=>map.getContainer().classList.toggle('map-wide',map.getZoom()<12);
  map.on('zoomend',syncLabelVisibility);syncLabelVisibility();
  L.control.zoom({position:'bottomright'}).addTo(map);
  baseTiles=buildTileLayer(TILE_ORDER[tileProviderIndex]);
  addBaseLayer();
  // Hồ vẽ tay chỉ dùng cho sơ đồ ngoại tuyến; trên nền tile thật hồ đã được vẽ đúng hình.
  geographyLayer=L.layerGroup();
  const lakes=[['Hồ Tây',[[21.043,105.825],[21.048,105.817],[21.058,105.812],[21.070,105.819],[21.073,105.835],[21.060,105.842],[21.048,105.839]]],['Hồ Hoàn Kiếm',[[21.0313,105.852],[21.0300,105.8537],[21.026,105.8537],[21.0252,105.8518],[21.028,105.8509]]],['Hồ Bảy Mẫu',[[21.0135,105.8443],[21.0134,105.8470],[21.009,105.8477],[21.0074,105.8460],[21.008,105.8444]]],['Hồ Thủ Lệ',[[21.0335,105.8006],[21.0339,105.8060],[21.0308,105.8078],[21.0300,105.8028]]]];
  for(const [name,shape] of lakes)L.polygon(shape,{color:'#b7d1d0',fillColor:'#c7dddd',fillOpacity:.8,weight:1,interactive:false}).addTo(geographyLayer).bindTooltip(name,{permanent:true,direction:'center',className:'water-label'});
  placeLayer=L.layerGroup().addTo(map);
  map.createPane('majorRoadPane');map.getPane('majorRoadPane').style.zIndex=390;
  roadLayer=L.layerGroup().addTo(map);
  routeLayer=L.layerGroup().addTo(map);
  eventLayer=L.layerGroup().addTo(map);
  selectionLayer=L.layerGroup().addTo(map);
  map.on('click', e=>{if(state.picking) finishPick(e.latlng.lat,e.latlng.lng);else if(state.routePicking)setPickedPoint(state.routePicking,e.latlng.lat,e.latlng.lng);});
  map.on('movestart',()=>$('#search-results').hidden=true);
  map.on('zoomend',syncMajorRoads);
  map.on('moveend',()=>{if(state.data)renderMap();});
  fetch('/api/major-roads').then(response=>response.ok?response.json():Promise.reject(new Error('major roads unavailable'))).then(data=>{
    for(const [kind,shapes] of Object.entries(data.classes))majorRoadLines[kind]=L.polyline(shapes,{pane:'majorRoadPane',color:'#667783',weight:kind==='motorway'||kind==='trunk'?2.5:kind==='tertiary'?1.4:1.8,opacity:.4,interactive:false,smoothFactor:1.5});
    syncMajorRoads();
  }).catch(()=>{$('#major-roads').disabled=true;});
}

function syncMajorRoads(){
  const minimumZoom={motorway:9,trunk:9,primary:9,secondary:11,tertiary:13};
  for(const [kind,line] of Object.entries(majorRoadLines)){
    const visible=state.layers.majorRoads&&map.getZoom()>=minimumZoom[kind];
    line.setStyle({opacity:kind==='tertiary'?.34:map.getZoom()>=11?.56:.4});
    if(visible&&!map.hasLayer(line))line.addTo(map);
    if(!visible&&map.hasLayer(line))map.removeLayer(line);
  }
}

async function refresh() {
  if(refreshing){await refreshing;return refresh();}
  let complete;
  refreshing=new Promise(resolve=>complete=resolve);
  try {
    const first=!state.data;
    state.data=await api('/api/snapshot');state.connected=true;state.lastGood=Date.now();
    $('#connection-error').hidden=true;
  $('#sync-status').textContent=`Kết nối local · Dữ liệu mô phỏng${state.data.simulation_speed!==1?` · ${state.data.simulation_speed}×`:''}`;
    $('.status-dot').style.background='#49a68b';
    if(first) populateControls();
    updateDashboard();
    updateAlertBanner();
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
    return risk>=65?'#cf5149':risk>=35?'#cc8a2b':'#288d6d';
  }
  if(r.blocked) return '#cf5149';
  if(r.event_type && state.layers[r.event_type]) return {flood:'#347ec5',traffic:'#cc8a2b',incident:'#cf5149'}[r.event_type];
  return '#288d6d';
}

function renderMap() {
  if(!state.data)return;
  const bounds=(map.getSize().x&&map.getSize().y?map.getBounds():L.latLngBounds(HANOI_BOUNDS)).pad(.12);
  const key=[state.data.scenario,state.data.roads[0]?.simulated_timestamp,state.data.events.map(e=>`${e.id}:${e.updated_at}`).join('|'),state.horizon,state.selected,map.getZoom(),Math.round(bounds.getCenter().lat*200),Math.round(bounds.getCenter().lng*200),JSON.stringify(state.layers),map.getContainer().classList.contains('route-active')].join(':');
  if(key===lastRenderKey)return;
  lastRenderKey=key;
  roadLayer.clearLayers();eventLayer.clearLayers();
  for(const r of state.data.roads) {
    if(!state.layers.demoRoads||!bounds.intersects(L.latLngBounds(r.coordinates)))continue;
    if(map.getContainer().classList.contains('route-active')&&!r.event_type&&r.id!==state.selected)continue;
    if(map.getZoom()<12&&r.id!==state.selected&&!r.event_type)continue;
    const f=r.forecast[state.horizon/15];
    const color=roadColor(r), weight=r.id===state.selected?6:4;
    L.polyline(r.coordinates,{color:'#fff',weight:weight+3,opacity:.94,interactive:false}).addTo(roadLayer);
    const line=L.polyline(r.coordinates,{color,weight,opacity:.98,dashArray:r.known?null:'5 6'}).addTo(roadLayer);
    line.bindTooltip(`<strong>${esc(r.name)}</strong><br>${!r.known?'Chưa đủ dữ liệu':state.horizon?`Dự báo +${state.horizon} phút · Nguy cơ ${f.risk}/100`:`${r.speed} km/h · ${r.blocked?'Đóng trong kịch bản':'Dữ liệu thử nghiệm'}`}`);
    line.on('click',e=>{L.DomEvent.stopPropagation(e);if(state.picking)finishPick(e.latlng.lat,e.latlng.lng);else if(state.routePicking)setPickedPoint(state.routePicking,e.latlng.lat,e.latlng.lng);else selectRoad(r.id,true);});
  }
  const markers=[];
  if(!state.horizon) for(const e of state.data.events) {
    if(!state.layers[e.type] || (e.status==='pending'&&!state.layers.pending)) continue;
    if(!bounds.contains([e.lat,e.lng]))continue;
    markers.push({lat:e.lat,lng:e.lng,type:e.type,pending:e.status==='pending',title:`${typeNames[e.type]}: ${e.name}`,tooltip:`${esc(e.name)} · ${e.status==='pending'?'Chờ xác minh':typeNames[e.type]}`,click:()=>state.picking?finishPick(e.lat,e.lng):showEvent(e.id)});
  }
  else for(const r of state.data.roads) {
    if(!r.known||!bounds.contains(r.center))continue;
    const f=r.forecast[state.horizon/15];
    const [type,score]=[['flood',f.flood_risk],['traffic',f.traffic_risk],['incident',f.incident_risk]].reduce((best,item)=>item[1]>best[1]?item:best);
    if(score<65||!state.layers[type])continue;
    const [lat,lng]=r.center;
    markers.push({lat,lng,type,title:`${typeNames[type]} · dự báo +${state.horizon} phút`,tooltip:`${esc(r.name)} · ${typeNames[type]} ${score}/100 (mô phỏng)`,click:()=>state.picking?finishPick(lat,lng):selectRoad(r.id,true)});
  }
  const groups=new Map();
  for(const item of markers){const p=map.latLngToContainerPoint([item.lat,item.lng]);const key=map.getZoom()<13?`${Math.floor(p.x/54)}:${Math.floor(p.y/54)}`:`${item.lat}:${item.lng}:${item.title}`;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(item);}
  for(const group of groups.values()){
    if(group.length>1&&map.getZoom()<13){const lat=group.reduce((sum,e)=>sum+e.lat,0)/group.length,lng=group.reduce((sum,e)=>sum+e.lng,0)/group.length;L.marker([lat,lng],{icon:L.divIcon({className:'',html:`<span class="event-cluster">${group.length}</span>`,iconSize:[35,35]}),title:`${group.length} cảnh báo mô phỏng`}).addTo(eventLayer).on('click',()=>map.setView([lat,lng],Math.min(15,map.getZoom()+2)));continue;}
    const e=group[0];const marker=L.marker([e.lat,e.lng],{icon:L.divIcon({className:`event-marker ${e.type} ${e.pending?'pending':''}`,html:icon(typeIcons[e.type]),iconSize:[32,32]}),title:e.title}).addTo(eventLayer);marker.bindTooltip(e.tooltip);marker.on('click',()=>state.routePicking?setPickedPoint(state.routePicking,e.lat,e.lng):e.click());
  }
  $('#map-mode-label').hidden=!state.horizon;
  $('#map-mode-label').textContent=`Dự báo +${state.horizon} phút · Nguy cơ thấp → trung bình → cao`;
  $('.map-legend').innerHTML=state.horizon?
    '<span><i class="legend-dot green"></i>Thấp &lt;35</span><span><i class="legend-dot orange-bg"></i>Trung bình 35–64</span><span><i class="legend-dot red-bg"></i>Cao ≥65</span><span><i class="legend-dot gray-bg"></i>Chưa đủ dữ liệu</span><span><i class="legend-line"></i>Đường chính OSM</span>':
    '<span><i class="legend-dot green"></i>Thông thoáng</span><span><i class="legend-dot orange-bg"></i>Ùn tắc</span><span><i class="legend-dot blue-bg"></i>Ngập</span><span><i class="legend-dot red-bg"></i>Sự cố / đóng</span><span><i class="legend-dot gray-bg"></i>Chưa có dữ liệu</span><span><i class="legend-line"></i>Đường chính OSM</span>';
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
  $('#insight-summary').textContent=road.known?`Sau 60 phút: ngập ${last.flood_risk}, ùn tắc ${last.traffic_risk}, sự cố ${last.incident_risk}/100; tốc độ ước tính ${last.speed} km/h.`:'Đoạn đường chưa đủ dữ liệu. Hệ thống không suy diễn thành trạng thái an toàn.';
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
  $('#detail-content').innerHTML=`<div class="dialog-heading"><div><div class="eyebrow teal-text">${event?.status==='pending'?'PHẢN ÁNH CHỜ XÁC MINH':'CHI TIẾT ĐOẠN ĐƯỜNG'}</div><h2>${esc(event?.name||r.name)}</h2></div><button class="icon-button close-dialog" aria-label="Đóng chi tiết">${icon('close')}</button></div><span class="tag tag-${event?.status==='pending'?'gray':'teal'}">${event?.status==='pending'?'Chưa ảnh hưởng định tuyến':r.origin==='demo'?'Dữ liệu mô phỏng':'Phản ánh đã xác minh tại máy'}</span><div class="detail-stats"><div><span>Tốc độ hiện tại</span><strong>${r.known?r.speed+' km/h':'Chưa rõ'}</strong></div><div><span>Nguy cơ ngập +30p</span><strong>${f.flood_risk==null?'Chưa rõ':f.flood_risk+'/100'}</strong></div><div><span>Lưu thông</span><strong>${!r.known?'Chưa rõ':r.blocked?'Bị chặn':'Có thể đi*'}</strong></div></div><p class="muted">+30 phút · Ngập ${f.flood_risk??'—'} · Ùn tắc ${f.traffic_risk??'—'} · Sự cố ${f.incident_risk??'—'} /100</p><p class="data-label">${esc((event?.sources||r.sources).join(' · '))} · ${timeText(event?.updated_at||r.updated_at)}</p><div class="detail-evidence">${esc((event?.evidence||r.evidence).join('\n'))}</div>${r.reference_url&&r.origin==='demo'?`<a href="${esc(r.reference_url)}" target="_blank" rel="noopener">Nguồn tham khảo địa điểm</a>`:''}<p class="muted">*Trạng thái trong mạng thử nghiệm. Điểm nguy cơ là chỉ số theo quy tắc, không phải xác suất. Không dùng kết quả để quyết định đi qua vùng ngập thực tế.</p><div class="dialog-footer"><button class="button secondary" data-focus-road="${r.id}">${icon('pin')}Xem trên bản đồ</button><button class="button primary" data-forecast-detail="${r.id}">Xem dự báo ${icon('arrow')}</button></div>`;
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
  let svg=`<svg class="large-chart" viewBox="0 0 950 245" role="img" aria-label="Dự báo nguy cơ ngập, ùn tắc và sự cố cho ${esc(r.name)}">`;
  for(const v of [0,25,50,75,100])svg+=`<line x1="65" y1="${y(v)}" x2="885" y2="${y(v)}" stroke="#e7ede7" stroke-dasharray="4 5"/><text x="30" y="${y(v)+4}" fill="#91a494">${v}</text>`;
  svg+=`<path d="${path('flood_risk')} L885,205 L65,205 Z" fill="#edf3fd" stroke="none"/><path d="${path('flood_risk')}" fill="none" stroke="#347ec5" stroke-width="3"/><path d="${path('traffic_risk')}" fill="none" stroke="#cc8a2b" stroke-width="3"/><path d="${path('incident_risk')}" fill="none" stroke="#cf5149" stroke-width="3"/>`;
  r.forecast.forEach((f,i)=>{svg+=`<circle cx="${xs[i]}" cy="${y(f.flood_risk)}" r="5" fill="white" stroke="#5188d7" stroke-width="2"/><text x="${xs[i]}" y="234" text-anchor="middle" fill="#89a18e">${f.horizon?'+'+f.horizon+' phút':'Hiện tại'}</text>`;});
  svg+='</svg>';
  $('#forecast-chart').innerHTML=svg+`<div class="chart-legend"><span><i class="legend-dot blue-bg"></i>Ngập</span><span><i class="legend-dot orange-bg"></i>Ùn tắc</span><span><i class="legend-dot red-bg"></i>Sự cố</span></div><div class="forecast-table-wrap"><table class="forecast-table"><thead><tr><th>Thời điểm</th><th>Ngập</th><th>Ùn tắc</th><th>Sự cố</th><th>Tốc độ</th><th>Tổng hợp</th></tr></thead><tbody>${r.forecast.map(f=>`<tr><td>${f.horizon?'Sau '+f.horizon+' phút':'Hiện tại'}</td><td>${f.flood_risk}/100</td><td>${f.traffic_risk}/100</td><td>${f.incident_risk}/100</td><td>${f.speed} km/h</td><td><span class="tag tag-${f.risk>=65?'red':f.risk>=35?'orange':'teal'}">${f.label} · ${f.risk}/100</span></td></tr>`).join('')}</tbody></table></div>`;
}

function renderSources() {
  const sources=[
    ['route','OpenStreetMap / OSRM','Hình học lưu cục bộ','teal','111 hành lang demo và 17.711 đoạn đường chính tham chiếu bám theo OpenStreetMap. Không bao gồm tốc độ hoặc sự cố thực tế.','Làm mới thủ công bằng scripts/build-hanoi-road-geometry.py và scripts/build-hanoi-major-roads.py.'],
    ['cloud','Vệ tinh NASA GPM (IMERG)','Dữ liệu viễn thám NASA','blue','Lượng mưa radar viễn thám toàn cầu chu kỳ 30 phút, độ phân giải 0.1° (~10km). Đón đầu hướng di chuyển mây dông trước khi mưa chạm đất.','Tải mở hoàn toàn qua cổng NASA Earthdata Search (search.earthdata.nasa.gov) bằng Python script (thư viện earthaccess).'],
    ['water','NASA SMAP & NASADEM (TWI)','Độ ẩm đất & Địa hình NASA','teal','Chỉ số độ ẩm bão hòa đất (SMAP) & Chỉ số trũng địa hình (Topographic Wetness Index - TWI 30m). Xác định các điểm tụ nước tự nhiên.','Khai thác DEM 30m từ NASA SRTM/NASADEM tính TWI; nạp độ ẩm đất SMAP làm biến điều kiện bão hòa dòng chảy mặt.'],
    ['chart','Bộ mô phỏng giao thông','Đang chạy tại máy','teal','Mạng mẫu nhiều khu vực Hà Nội; nguy cơ ngập, ùn tắc và sự cố được tính theo kịch bản mỗi 10 giây.','—'],
    ['report','Phản ánh cộng đồng','Lưu thật tại máy','teal','Vị trí, mô tả, ảnh lưu trong SQLite. Cần xác minh thủ công.','—'],
    ['cloud','API Khí tượng (NCHMF / OpenWeather)','Sẵn sàng tích hợp','orange','Lượng mưa trạm mặt đất, dự báo 3 giờ tới. 3 kịch bản mô phỏng hiện tại.','Đăng ký API key OpenWeatherMap miễn phí (1000 calls/ngày) hoặc crawl bản tin NCHMF.'],
    ['car','VOV Giao thông','Chưa kết nối','gray','Bản tin ùn tắc, tai nạn, đường bị ảnh hưởng theo thời gian thực.','Xin phép API/RSS từ VOV. Hoặc crawl vovgiaothong.vn + NLP trích xuất tên đường, loại sự kiện.'],
    ['water','Hệ thống thoát nước Hà Nội','Chưa kết nối','gray','Mực nước, điểm ngập, vận hành trạm bơm tại các trạm quan trắc.','Hợp tác với Cty TNHH MTV Thoát nước HN. Lấy dữ liệu qua API/SFTP định kỳ.'],
    ['layers','Camera giao thông (AI)','Chưa kết nối','gray','Ước lượng mật độ, phát hiện xe dừng bất thường qua RTSP stream.','Tích hợp RTSP từ hệ thống camera Sở GTVT. YOLO + ByteTrack phân tích.'],
    ['water','Google Flood Hub','Có thể tham khảo','orange','Dự báo lũ lụt Google cho khu vực sông Hồng, sông Tô Lịch.','API công khai tại sites.research.google/floods. Dữ liệu dự báo ngập vùng sông.'],
    ['route','HERE Traffic / TomTom','Chưa kết nối','gray','Lưu lượng giao thông thời gian thực từ API thương mại.','Freemium: HERE 250K calls/tháng. TomTom có tier miễn phí tương tự.'],
    ['alert','Mạng xã hội (Facebook, Zalo)','Chưa kết nối','gray','Bài viết công khai từ các nhóm cộng đồng giao thông Hà Nội.','Thu thập bài viết công khai. NLP phân loại và trích xuất vị trí.'],
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

function clearRoutes(){routeLayer.clearLayers();map.getContainer().classList.remove('route-active');if(state.data)renderMap();$('#route-map-key').hidden=true;state.routes=null;$('#route-results').innerHTML='<div class="empty-state">Chọn điểm đi và đến, sau đó tìm tuyến theo dữ liệu mới nhất.</div>';}
function setPickedPoint(field,lat,lng){const select=$('#route-'+field);select.querySelector('[data-picked="true"]')?.remove();const option=new Option(`Điểm trên bản đồ · ${lat.toFixed(4)}, ${lng.toFixed(4)}`,`${lat.toFixed(6)},${lng.toFixed(6)}`);option.dataset.picked='true';select.add(option);select.value=option.value;state.routePicking=null;$$('.route-pick').forEach(button=>button.classList.remove('active'));$('#route-pick-hint')?.remove();}
function openRoute(){if(!state.data){toast('Đang tải dữ liệu, vui lòng thử lại.');return;}$('#event-panel').hidden=true;$('#route-panel').hidden=false;requestAnimationFrame(()=>map.invalidateSize());}
async function findRoutes(e){
  e.preventDefault();if(!state.connected){toast('Cần kết nối máy chủ để tính tuyến mới.');return;}
  const button=$('button[type=submit]',$('#route-form'));button.disabled=true;button.textContent='Đang tính tuyến…';
  try{
    const query=new URLSearchParams({origin:$('#route-origin').value,destination:$('#route-destination').value,horizon:$('#route-time').value,vehicle:$('#route-vehicle').value});
    state.routes=await api('/api/routes?'+query,{timeoutMs:30000});state.routeIndex=0;state.horizon=Number($('#route-time').value);$$('#map-horizon button').forEach(item=>item.classList.toggle('active',Number(item.dataset.horizon)===state.horizon));renderMap();renderRoutes();
  }catch(err){clearRoutes();$('#route-results').innerHTML=`<div class="empty-state">${esc(err.message)}</div>`;}
  finally{button.disabled=false;button.innerHTML=icon('route')+'Tìm tuyến gợi ý';}
}
function renderRoutes(){
  routeLayer.clearLayers();const result=state.routes;
  if(!result.routes.length){map.getContainer().classList.remove('route-active');renderMap();$('#route-map-key').hidden=true;$('#route-results').innerHTML=`<div class="empty-state">${icon('alert')}${esc(result.message)}</div>`;return;}
  const selected=result.routes[state.routeIndex];
  $('#route-results').innerHTML=result.routes.map((r,i)=>`<button class="route-choice ${i===state.routeIndex?'selected':''}" data-route-index="${i}" type="button"><div class="route-summary"><h3>${esc(r.title)}</h3><strong>${Math.ceil(r.eta_minutes)}<small>phút</small></strong></div><p class="route-meta">${r.distance_km} km · ${esc({motorbike:'Xe máy',car:'Ô tô',walk:'Đi bộ'}[r.vehicle])} · Nguy cơ ${r.max_risk}/100</p><p class="route-warnings">${r.warnings.length?`${r.warnings.length} cảnh báo trên tuyến`:'Không có cảnh báo trên tuyến'}</p></button>`).join('')+`<div class="route-forecast">${selected.forecast_timeline.map(p=>`<button type="button" data-route-horizon="${p.horizon}" class="${Number($('#route-time').value)===p.horizon?'active':''}"><span>${p.horizon?'+'+p.horizon+' phút':'Hiện tại'}</span><strong>${Math.ceil(p.eta_minutes)} phút</strong><small>${p.congested_segments} ùn tắc · ${p.flooded_segments} ngập</small></button>`).join('')}</div><details class="route-details"><summary>Chi tiết hành trình</summary><p><strong>${esc(selected.origin_name)}</strong> → <strong>${esc(selected.destination_name)}</strong></p><p>Đoạn cần lưu ý: ${selected.warnings.length?esc(selected.warnings.join(', ')):'Không có cảnh báo mô phỏng trên tuyến.'}</p><ol>${selected.steps.map(name=>`<li>${esc(name)}</li>`).join('')}</ol></details><p class="route-timestamp" id="route-calculation-note">Tính lúc ${timeText(result.calculated_at)} · Loại ${result.excluded} đoạn đóng / thiếu dữ liệu.</p>`;
  const chosen=result.routes[state.routeIndex];
  map.getContainer().classList.add('route-active');
  renderMap();
  $('#route-map-key').hidden=false;$('#route-alternative-key').hidden=result.routes.length<2;
  for(const [i,r] of result.routes.entries())if(i!==state.routeIndex)L.polyline(r.coordinates,{color:'#7f7696',weight:4,opacity:.85,dashArray:'8 7'}).addTo(routeLayer);
  L.polyline(chosen.coordinates,{color:'white',weight:12,opacity:.98,interactive:false}).addTo(routeLayer);
  const line=L.polyline(chosen.coordinates,{color:'#6940cf',weight:7,opacity:1}).addTo(routeLayer);
  for(const [coord,label] of [[chosen.coordinates[0],'A'],[chosen.coordinates.at(-1),'B']])
    L.marker(coord,{zIndexOffset:2000,icon:L.divIcon({className:`route-endpoint route-${label.toLowerCase()}`,html:`<strong>${label}</strong>`,iconSize:[32,32]})}).addTo(routeLayer);
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
  if(lat<20.68||lat>21.31||lng<105.33||lng>106.0){toast('Hãy chọn vị trí trong vùng thử nghiệm Hà Nội.');return;}
  state.picking=false;$('#pick-banner').hidden=true;$('.map-surface').classList.remove('picking');
  const nearest=state.data.roads.map(r=>({r,d:Math.hypot(lat-r.center[0],lng-r.center[1])})).sort((a,b)=>a.d-b.d)[0].r;
  setReportPosition(lat,lng,nearest.name);selectionLayer.clearLayers();L.circleMarker([lat,lng],{radius:9,color:'#087f72',fillOpacity:.3}).addTo(selectionLayer);$('#report-dialog').showModal();
}
function geolocate(forReport=false){
  if(!navigator.geolocation){toast('Trình duyệt không hỗ trợ định vị. Bạn có thể chọn trên bản đồ.');return;}
  toast('Đang xác định vị trí. Cho phép trình duyệt truy cập vị trí nếu được hỏi.');
  navigator.geolocation.getCurrentPosition(p=>{
    const {latitude:lat,longitude:lng}=p.coords;
    if(lat<20.68||lat>21.31||lng<105.33||lng>106.0){toast('Bạn đang ngoài vùng thử nghiệm Hà Nội. Hãy chọn địa chỉ hoặc ghim trong vùng.');return;}
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
  if(button.dataset.routeHorizon!==undefined){$('#route-time').value=button.dataset.routeHorizon;findRoutes(new Event('submit'));}
  if(button.dataset.reviewId){button.disabled=true;try{await post('/api/reports/'+button.dataset.reviewId,{status:button.dataset.status});await loadReports();await refresh();clearRoutes();toast('Đã cập nhật trạng thái phản ánh.');}catch(err){toast(err.message);button.disabled=false;}}
  if(button.dataset.reportMap){const r=state.reports.find(r=>r.id===button.dataset.reportMap);setView('map');map.setView([r.lat,r.lng],15);selectionLayer.clearLayers();L.circleMarker([r.lat,r.lng],{radius:10,color:'#087f72'}).addTo(selectionLayer);}
});
$('#search-form').addEventListener('submit',e=>{e.preventDefault();searchLocation();});
$('#map-search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(searchLocation,300);});
let routeSearchTimer,routeSearchSerial=0;
$('#route-place-search').addEventListener('input',()=>{clearTimeout(routeSearchTimer);const serial=++routeSearchSerial,query=$('#route-place-search').value.trim(),container=$('#route-place-results');if(query.length<2){container.hidden=true;return;}routeSearchTimer=setTimeout(async()=>{try{const {results}=await api('/api/search?q='+encodeURIComponent(query));if(serial!==routeSearchSerial)return;container.replaceChildren();if(!results.length){container.textContent='Không tìm thấy địa điểm trong dữ liệu OSM cục bộ.';container.hidden=false;return;}for(const place of results){const row=document.createElement('div');row.className='route-place-item';const label=document.createElement('span');label.textContent=place.name;row.append(label);for(const [field,letter] of [['origin','A'],['destination','B']]){const button=document.createElement('button');button.type='button';button.textContent=letter;button.title=`Chọn làm điểm ${field==='origin'?'đi':'đến'}`;button.addEventListener('click',()=>{if(place.kind==='node')$('#route-'+field).value=place.id;else setPickedPoint(field,place.lat,place.lng);$('#route-place-search').value=place.name;container.hidden=true;});row.append(button);}container.append(row);}container.hidden=false;}catch(error){toast(error.message);}},300);});
$('#toggle-layers').addEventListener('click',()=>$('#layer-menu').hidden=!$('#layer-menu').hidden);
$$('[data-layer]').forEach(el=>el.addEventListener('change',()=>{state.layers[el.dataset.layer]=el.checked;if(el.dataset.layer==='majorRoads'){syncMajorRoads();return;}if(state.data)renderMap();}));
$('#base-tiles').addEventListener('change',e=>setBaseTiles(e.target.checked));
$('#fit-map').addEventListener('click',()=>{if(state.data)map.fitBounds(state.data.nodes.map(n=>[n.lat,n.lng]),{padding:[40,55]});});
$('#my-location').addEventListener('click',()=>geolocate());
$('#open-report').addEventListener('click',openReport);
$('#about-button').addEventListener('click',()=>$('#about-dialog').showModal());
$('#open-route').addEventListener('click',openRoute);
$('#route-swap').addEventListener('click',()=>{const a=$('#route-origin'),b=$('#route-destination'),old=a.value;for(const [source,target] of [[a,b],[b,a]]){const picked=source.querySelector('[data-picked="true"]');if(picked&&![...target.options].some(option=>option.value===picked.value))target.add(picked.cloneNode(true));}a.value=b.value;b.value=old;});
$$('.route-pick').forEach(button=>button.addEventListener('click',()=>{state.routePicking=button.dataset.routePick;$$('.route-pick').forEach(item=>item.classList.toggle('active',item===button));$('#route-pick-hint')?.remove();$('#route-form').insertAdjacentHTML('beforeend','<p id="route-pick-hint" class="route-pick-hint">Chạm vào bản đồ để chọn vị trí.</p>');toast('Chạm vào bản đồ để chọn điểm.');}));
$('#close-route').addEventListener('click',()=>{$('#route-panel').hidden=true;$('#event-panel').hidden=false;state.routePicking=null;routeLayer.clearLayers();map.getContainer().classList.remove('route-active');renderMap();$('#route-map-key').hidden=true;});
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

// === Rescue view handlers ===
const rescueServices = {
  motorbike: {
    name: 'Cứu Hộ Xe Máy 247',
    hotline: '0944.883.288',
    tel: 'tel:0944883288',
    url: 'https://cuuhoxemay247.com/'
  },
  car: {
    name: 'Cứu Hộ Ô Tô 24h',
    hotline: '0967.119.119',
    tel: 'tel:0967119119',
    url: 'https://cuuho24h.vn/'
  },
  truck: {
    name: 'Trung Tâm Cứu Hộ Giao Thông 116',
    hotline: '0896.116.116',
    tel: 'tel:0896116116',
    url: 'https://trungtamcuuho116.vn/dich-vu-cuu-ho-giao-thong-116/'
  }
};

const rescueProblemTypes = {
  flood_dead: 'Chết máy do ngập nước',
  hydro: 'Nghi ngờ thủy kích trong nước sâu',
  battery: 'Hỏng bình ắc quy / Không đề nổ',
  tire: 'Hỏng / Nổ lốp giữa đường',
  accident: 'Va chạm / Tai nạn giao thông'
};

const rescueLocBtn = $('#rescue-loc-btn');
if (rescueLocBtn) {
  rescueLocBtn.addEventListener('click', () => {
    if (!navigator.geolocation) {
      toast('Trình duyệt không hỗ trợ định vị GPS.');
      return;
    }
    rescueLocBtn.disabled = true;
    rescueLocBtn.innerHTML = 'Đang định vị GPS…';
    navigator.geolocation.getCurrentPosition(
      pos => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        let nearestName = '';
        if (state.data && state.data.roads) {
          let minDist = Infinity;
          for (const r of state.data.roads) {
            const d = Math.hypot((r.start_lat + r.end_lat)/2 - lat, (r.start_lng + r.end_lng)/2 - lng);
            if (d < minDist) { minDist = d; nearestName = r.name; }
          }
        }
        const text = nearestName ? `Gần ${nearestName} (Tọa độ: ${lat.toFixed(4)}, ${lng.toFixed(4)})` : `Tọa độ: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
        $('#rescue-address').value = text;
        rescueLocBtn.disabled = false;
        rescueLocBtn.innerHTML = `${icon('target')}Lấy vị trí GPS hiện tại`;
        toast('Đã định vị thành công: ' + text);
      },
      err => {
        rescueLocBtn.disabled = false;
        rescueLocBtn.innerHTML = `${icon('target')}Lấy vị trí GPS hiện tại`;
        toast('Không thể lấy vị trí GPS: ' + (err.message || 'Quyền truy cập bị từ chối'));
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  });
}

const rescueForm = $('#rescue-request-form');
if (rescueForm) {
  rescueForm.addEventListener('submit', e => {
    e.preventDefault();
    const vehicle = $('#rescue-vehicle').value;
    const typeKey = $('#rescue-type').value;
    const address = $('#rescue-address').value.trim();
    const phone = $('#rescue-phone').value.trim();
    const note = $('#rescue-note').value.trim();
    const srv = rescueServices[vehicle] || rescueServices.car;
    const probLabel = rescueProblemTypes[typeKey] || 'Sự cố ngập nước';

    const resultBox = $('#rescue-form-result');
    resultBox.hidden = false;
    resultBox.innerHTML = `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
        <span style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:#087f72;color:white;flex-shrink:0;">${icon('check')}</span>
        <div>
          <strong style="font-size:14px;color:#087f72;display:block;">Đã tiếp nhận yêu cầu ứng cứu!</strong>
          <span style="font-size:11px;color:#537365;">Đơn vị phụ trách đề xuất: <b>${esc(srv.name)}</b></span>
        </div>
      </div>
      <div style="font-size:11px;line-height:1.6;background:white;padding:10px 12px;border-radius:8px;border:1px solid #d0e7dc;margin-bottom:12px;color:#354e43;">
        <div>📍 <b>Vị trí:</b> ${esc(address)}</div>
        <div>📞 <b>SĐT liên hệ:</b> ${esc(phone)}</div>
        <div>⚠️ <b>Tình trạng:</b> ${esc(probLabel)}${note ? ' (' + esc(note) + ')' : ''}</div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <a href="${srv.tel}" class="button primary" style="background:#de4c3c!important;flex:1;min-height:38px;justify-content:center;text-decoration:none;">
          ${icon('phone')}Bấm gọi Hotline: ${srv.hotline}
        </a>
        <a href="${srv.url}" target="_blank" rel="noopener" class="button secondary" style="min-height:38px;justify-content:center;text-decoration:none;">
          ${icon('external')}Mở website
        </a>
      </div>
      <div style="margin-top:10px;font-size:10px;color:#6b8577;line-height:1.5;">
        💡 <b>Lưu ý an toàn:</b> Nhấn nút <i>"Bấm gọi Hotline"</i> để tổng đài viên điều xe cứu hộ gần nhất tiếp cận hiện trường nhanh nhất (15–20 phút).
      </div>
    `;

    toast(`Đã tiếp nhận! Vui lòng gọi hotline ${srv.hotline} để được cứu hộ hỗ trợ tức thì.`);
  });
}

// === Init ===
if(typeof L==='undefined'){$('#connection-error').hidden=false;$('#connection-error').textContent='Thiếu thư viện bản đồ local. Kiểm tra thư mục public/vendor.';}
else{fetch('/api/map-config').then(response=>response.ok?response.json():{}).catch(()=>({})).then(config=>{initializeMap(config.maptiler_key||'');checkAuth();refresh();setInterval(refresh,10000);});}

