'use strict';
import { $, $$ } from '../data/dom.js';
import { createApi } from '../data/api.js';
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const typeNames = {flood:'Ngập đường',traffic:'Ùn tắc',incident:'Sự cố giao thông'};
const typeIcons = {flood:'water',traffic:'car',incident:'alert'};
const typeColors = {flood:'blue',traffic:'orange',incident:'red'};
const statuses = {pending:'Chờ xác minh',verified:'Đã xác minh',resolved:'Đã xử lý',rejected:'Đã từ chối',expired:'Hết hạn'};
const state = {data:null,view:'map',filter:'all',horizon:0,selected:'HN-019',layers:{flood:true,traffic:true,incident:true,pending:true},
  reportPosition:null,picking:false,reports:[],routes:null,connected:false,lastGood:0,locationFocus:null,tomtomFlows:{},liveStatus:null,lastTomtomSegment:null,demoEvents:[]};
const REAL_DATA_ONLY=true;
let map, baseTiles, roadLayer, eventLayer, routeLayer, selectionLayer, placeLayer;
let gpmRainLayer, gpmRainData=null, gpmError=null, gpsLocationMarker=null, gpmRequest=null;
let tomtomTrafficLayer, tomtomSegmentLayer, tomtomTrafficEnabled=true, tomtomSegmentRequest=null;
let refreshing=false, searchTimer, toastTimer, tileErrorCount=0, searchSerial=0, roadClickTimer,tomtomError=null,sourcesRendered=false;
let mapExpanded=false;
let verifiedFloodLayer=null;
let verifiedReports=[], verifiedFloodCount=0;
let hanoiBounds=null, hanoiBoundaryRings=[];
function ensureMapState(){
  if(!state.data)state.data={generated_at:Date.now()/1000,mode:'live-only',roads:[],events:[],nodes:[],counts:{flood:0,traffic:0,incident:0},pending:0,rainfall:null};
}
const timeText = unix => new Date(unix*1000).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const ago = unix => {const s=Math.max(0,Math.floor(Date.now()/1000-unix));return s<60?'Vừa cập nhật':`${Math.floor(s/60)} phút trước`;};
function gpmCellAt(point){
  if(!gpmRainData?.cells?.length)return null;
  let closest=null,distance=Infinity;
  for(const cell of gpmRainData.cells){
    const dy=(point[0]-cell.lat)*111;
    const dx=(point[1]-cell.lng)*111*Math.cos(point[0]*Math.PI/180);
    const d=Math.hypot(dx,dy);
    if(d<distance){closest=cell;distance=d;}
  }
  return closest&&distance<=gpmRainData.resolution_km_approx*.9?closest:null;
}
function formatGpmRate(value){
  return value==null?'Không có số đo':`${Number(value).toFixed(2)} mm/h`;
}
function gpmCellColor(value){
  if(value==null)return {color:'#8b9692',fillColor:'#8b9692',fillOpacity:.18};
  if(value<.1)return {color:'#9db9c3',fillColor:'#dbeaf0',fillOpacity:.12};
  if(value<1)return {color:'#84b7ca',fillColor:'#b8dce8',fillOpacity:.28};
  if(value<2.5)return {color:'#669fbd',fillColor:'#81c3da',fillOpacity:.36};
  if(value<7.5)return {color:'#4e8cbb',fillColor:'#468fca',fillOpacity:.43};
  if(value<15)return {color:'#c18f3b',fillColor:'#f0b94d',fillOpacity:.48};
  return {color:'#bd5149',fillColor:'#e6655e',fillOpacity:.53};
}
function renderTomtomTrafficStatus(){
  const status=$('#tomtom-traffic-status');
  if(status)status.textContent=!state.liveStatus?.traffic?.configured
    ?'Chưa cấu hình nguồn giao thông trực tiếp'
    :tomtomError||'Nhấn vào bản đồ để lấy số đo cho một đoạn đường';
}
function setMapExpanded(expanded){
  mapExpanded=expanded;
  document.body.classList.toggle('map-expanded',expanded);
  const zoomIn=$('#zoom-map-in');
  const zoomOut=$('#zoom-map-out');
  if(zoomIn)zoomIn.hidden=expanded;
  if(zoomOut)zoomOut.hidden=!expanded;
  if(map){requestAnimationFrame(()=>map.invalidateSize());}
}
function cachedTomtomFlow(flowKey){
  const segment=state.tomtomFlows[flowKey];
  if(!segment)return null;
  const sampledAt=Date.parse(segment.sampled_at);
  if(!Number.isFinite(sampledAt)||Date.now()-sampledAt>=5*60*1000){
    delete state.tomtomFlows[flowKey];
    return null;
  }
  return segment;
}
function setTomtomTrafficVisible(visible){
  tomtomTrafficEnabled=visible;
  if(!map||!tomtomTrafficLayer)return;
  const status=$('#tomtom-traffic-status');
  if(visible&&state.liveStatus?.traffic?.configured){
    if(!map.hasLayer(tomtomTrafficLayer))tomtomTrafficLayer.addTo(map);
    renderTomtomTrafficStatus();
  }else{
    if(map.hasLayer(tomtomTrafficLayer))map.removeLayer(tomtomTrafficLayer);
    if(tomtomSegmentLayer)tomtomSegmentLayer.clearLayers();
    if(status)status.textContent=visible
      ?'Chưa cấu hình nguồn giao thông trực tiếp'
      :'Đã tắt lớp giao thông';
  }
  renderMap();
}
async function loadTomtomSegment(point){
  if(!tomtomTrafficEnabled||state.picking)return;
  const flowKey=`${point.lat.toFixed(4)},${point.lng.toFixed(4)}`;
  const cached=cachedTomtomFlow(flowKey);
  if(cached){
    showTomtomSegment(point,cached);
    return cached;
  }
  if(tomtomSegmentRequest)return tomtomSegmentRequest;
  tomtomSegmentRequest=(async()=>{
    renderTomtomTrafficStatus();
    const status=$('#tomtom-traffic-status');
    if(status)status.textContent='Đang truy vấn số liệu lưu lượng trực tiếp…';
    try{
      const zoom=Math.round(map.getZoom());
      const segment=await api(`/api/tomtom/segment?lat=${encodeURIComponent(point.lat)}&lng=${encodeURIComponent(point.lng)}&zoom=${zoom}`,{timeoutMs:30000});
      tomtomError=null;
      state.tomtomFlows[flowKey]=segment;
      showTomtomSegment(point,segment);
      if(status)status.textContent=segment.street_name
        ?`${segment.street_name} · ${segment.current_speed_kmh} km/h`
        :`Đã đo ${segment.current_speed_kmh} km/h · ${segment.street_name_error||'chưa xác định được tên đường'}`;
    }catch(error){
      tomtomError=error.message;
      if($('#tomtom-traffic-status'))$('#tomtom-traffic-status').textContent=error.message;
      console.error('Không lấy được đoạn TomTom tại vị trí đã chọn:',error);
    }finally{
      tomtomSegmentRequest=null;
    }
  })();
  return tomtomSegmentRequest;
}
function showTomtomSegment(point,segment){
  state.lastTomtomSegment={point,segment,roadName:segment.street_name||null};
  tomtomSegmentLayer.clearLayers();
  const flowColor=segment.road_closure?'#a82435':segment.speed_ratio>=.85?'#00a86b':segment.speed_ratio>=.65?'#f2c230':segment.speed_ratio>=.4?'#f28c28':'#d92332';
  L.polyline(segment.coordinates,{pane:'tomtomSegmentPane',color:'#465965',weight:10,opacity:.95,lineCap:'round',lineJoin:'round',interactive:false}).addTo(tomtomSegmentLayer);
  L.polyline(segment.coordinates,{pane:'tomtomSegmentPane',color:flowColor,weight:6,opacity:1,lineCap:'round',lineJoin:'round',interactive:false}).addTo(tomtomSegmentLayer);
  const speedRatio=Math.round(segment.speed_ratio*100);
  const closure=segment.road_closure?' · ĐÓNG ĐƯỜNG':'';
  const streetName=segment.street_name
    ?`<strong>${esc(segment.street_name)}</strong>${segment.street_name_source==='OpenStreetMap'?'<br><small>Tên đường tra cứu từ OpenStreetMap</small>':''}<br>`
    :`<strong>Tên đường chưa xác định</strong><br>${segment.street_name_error?`<small>${esc(segment.street_name_error)}</small><br>`:''}`;
  const details=`<strong>Thông tin tuyến đường</strong><br>${streetName}Tốc độ hiện tại: ${segment.current_speed_kmh} km/h<br>Tốc độ thông thoáng: ${segment.free_flow_speed_kmh} km/h<br>Lưu lượng: ${speedRatio}% tốc độ thông thoáng${closure}<br>Độ tin cậy: ${Math.round(segment.confidence*100)}%<br>Thời gian: ${new Date(segment.sampled_at).toLocaleString('vi-VN')}`;
  L.popup({maxWidth:280}).setLatLng(point).setContent(details).openOn(map);
  updateDashboard();
}
function renderGpmSummary(){
  if(!gpmRainData){
    $('#stat-rain').innerHTML='—<em>mm/h</em>';
    $('#weather-caption').textContent=gpmError||'Chưa có dữ liệu NASA GPM';
    return;
  }
  const point=state.locationFocus?[state.locationFocus.lat,state.locationFocus.lng]:map.getCenter();
  const cell=gpmCellAt(point);
  $('#stat-rain').innerHTML=cell?.rainfall_mm_hr==null?'—<em>mm/h</em>':`${Number(cell.rainfall_mm_hr).toFixed(2)}<em>mm/h</em>`;
  const where=state.locationFocus?'GPS':'tâm bản đồ';
  const updated=new Date(gpmRainData.time_start).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour12:false});
  $('#weather-caption').textContent=cell
    ?`${where} · ô lưới ${gpmRainData.resolution_degrees}° (~${gpmRainData.resolution_km_approx} km) · ${updated}${gpmRainData.stale?' · dữ liệu cũ':''}`
    :'Chưa có ô đo GPM tại tọa độ này';
  if(gpsLocationMarker&&state.locationFocus){
    gpsLocationMarker.setTooltipContent(`Vị trí GPS · mưa NASA GPM: ${formatGpmRate(cell?.rainfall_mm_hr)} · ô lưới ${gpmRainData.resolution_degrees}° (~${gpmRainData.resolution_km_approx} km)`);
  }
}
function renderGpmRainLayer(){
  if(!gpmRainLayer)return;
  gpmRainLayer.clearLayers();
  if(!gpmRainData)return;
  for(const cell of gpmRainData.cells){
    const style=gpmCellColor(cell.rainfall_mm_hr);
    L.rectangle([[cell.south,cell.west],[cell.north,cell.east]],{
      ...style,weight:.5,interactive:true,pane:'rainfallPane'
    }).addTo(gpmRainLayer).bindTooltip(
      `NASA GPM IMERG · ${formatGpmRate(cell.rainfall_mm_hr)}<br>Ô lưới ${gpmRainData.resolution_degrees}° (~${gpmRainData.resolution_km_approx} km)<br>${gpmRainData.time_start}${gpmRainData.stale?' · dữ liệu cũ':''}`
    );
  }
  renderGpmSummary();
}
function setGpmRainLayerVisible(visible){
  if(!map||!gpmRainLayer)return;
  if(visible){if(!map.hasLayer(gpmRainLayer))gpmRainLayer.addTo(map);}
  else if(map.hasLayer(gpmRainLayer))map.removeLayer(gpmRainLayer);
}
async function loadGpmRainfall(force=false){
  if(gpmRequest)return gpmRequest;
  gpmRequest=(async()=>{
    gpmError=null;
    $('#weather-caption').textContent='Đang truy vấn NASA GPM IMERG…';
    try{
      gpmRainData=await api(`/api/gpm/rainfall${force?'?refresh=1':''}`,{timeoutMs:150000});
      renderGpmRainLayer();
      renderMap();
    }catch(error){
      gpmRainData=null;
      gpmError=error.message;
      renderGpmSummary();
      console.error('Không lấy được mưa NASA GPM:',error);
      if(gpsLocationMarker)gpsLocationMarker.setTooltipContent(`Vị trí GPS · chưa lấy được mưa NASA GPM: ${esc(error.message)}`);
    }finally{gpmRequest=null;}
  })();
  return gpmRequest;
}
function distanceToRoadKm(point,road){
  let closest=Infinity;
  for(let i=1;i<road.coordinates.length;i++){
    const [lat1,lng1]=road.coordinates[i-1], [lat2,lng2]=road.coordinates[i];
    const scale=Math.cos(point[0]*Math.PI/180);
    const dx=(lng2-lng1)*scale,dy=lat2-lat1,px=(point[1]-lng1)*scale,py=point[0]-lat1;
    const fraction=Math.max(0,Math.min(1,(px*dx+py*dy)/(dx*dx+dy*dy||1)));
    const lat=lat1+fraction*dy,lng=lng1+fraction*(lng2-lng1);
    closest=Math.min(closest,Math.hypot((point[0]-lat)*111,(point[1]-lng)*111*scale));
  }
  return closest;
}
function visibleModelRoads(){
  const roads=state.data?.roads||[];
  if(!state.locationFocus)return roads;
  const point=[state.locationFocus.lat,state.locationFocus.lng];
  return roads.filter(road=>distanceToRoadKm(point,road)<=state.locationFocus.radiusKm);
}
// === Auth state ===
const authState = { user: null, token: localStorage.getItem('vietsafe_token') };

// === Tile providers ===
// KHÔNG gọi trực tiếp tile.openstreetmap.org trong prototype.
// Máy chủ tile chuẩn của OpenStreetMap là hạ tầng cộng đồng và có thể trả 403 khi
// môi trường preview/proxy không đáp ứng chính sách sử dụng tile. Dữ liệu nền vẫn là
// Lớp nền sáng Carto dùng dữ liệu OpenStreetMap và luôn giữ attribution.
// Nếu các nguồn tile lỗi, VietSafe tự chuyển sang sơ đồ ngoại tuyến.
const TILE_PROVIDERS = {
  osmde: {
    url:'https://tile.openstreetmap.de/{z}/{x}/{y}.png',
    attr:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a> · tiles: <a href="https://www.openstreetmap.de/" target="_blank" rel="noopener">OSM Deutschland</a>',
    maxZoom:19
  },
  osmfr: {
    url:'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
    attr:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a> · tiles: <a href="https://www.openstreetmap.fr/" target="_blank" rel="noopener">OpenStreetMap France</a>',
    maxZoom:19
  }
};
const TILE_ORDER = ['osmde','osmfr'];
const REPORT_BOUNDS = [[20.98,105.77],[21.065,105.88]];
let tileProviderIndex = 0;

const api = createApi(() => authState.token);
const post = (path, body) => api(path,{method:'POST',body:JSON.stringify(body)});
function toast(message) {$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,5200);}

const FOOTNOTE_OFFLINE='Không tải được ô nền trực tuyến · không có lớp đường ngoại tuyến';
function buildTileLayer(key) {
  const cfg=TILE_PROVIDERS[key];
  const layer=L.tileLayer(cfg.url,{maxZoom:cfg.maxZoom,attribution:cfg.attr,crossOrigin:true,updateWhenIdle:true,keepBuffer:3});
  layer.on('tileerror',()=>{if(++tileErrorCount>=6 && map.hasLayer(layer)) switchTileProvider();});
  return layer;
}
// Hết nhà cung cấp tile thì rơi xuống sơ đồ ngoại tuyến (nền lưới CSS + hồ vẽ tay).
function switchTileProvider() {
  map.removeLayer(baseTiles);tileErrorCount=0;
  if(++tileProviderIndex<TILE_ORDER.length){baseTiles=buildTileLayer(TILE_ORDER[tileProviderIndex]);baseTiles.addTo(map);toast('Nguồn bản đồ chính không phản hồi. VietSafe đang chuyển sang nguồn bản đồ dự phòng.');return;}
  tileProviderIndex=0;baseTiles=buildTileLayer(TILE_ORDER[0]);
  setBaseTiles(false);$('#base-tiles').checked=false;toast('Không tải được ô bản đồ trực tuyến. Các đường đã lưu vẫn được hiển thị, không suy diễn giao thông.');
}
function setBaseTiles(on) {
  if(on){if(!map.hasLayer(baseTiles)){tileErrorCount=0;baseTiles.addTo(map);}map.removeLayer(geographyLayer);$('#map-footnote').textContent='';}
  else{if(map.hasLayer(baseTiles))map.removeLayer(baseTiles);if(!REAL_DATA_ONLY)geographyLayer.addTo(map);$('#map-footnote').textContent=REAL_DATA_ONLY?'Bản đồ nền chưa tải được · không thay bằng sơ đồ minh họa':FOOTNOTE_OFFLINE;}
}
let geographyLayer;
async function initializeMap() {
  const boundaryResponse=await fetch('/js/data/hanoi-boundary.json',{headers:{'X-VietSafe':'local'}});
  if(!boundaryResponse.ok)throw new Error(`Không tải được ranh giới Hà Nội (HTTP ${boundaryResponse.status}).`);
  const boundaryData=await boundaryResponse.json();
  const boundaryFeature=boundaryData.features?.find(feature=>
    feature.properties?.name==='Hà Nội'&&feature.geometry?.type==='Polygon'
  );
  if(!boundaryFeature)throw new Error('Tệp ranh giới hành chính Hà Nội không hợp lệ.');
  hanoiBoundaryRings=boundaryFeature.geometry.coordinates.map(ring=>
    ring.map(([longitude,latitude])=>[latitude,longitude])
  );
  const hanoiBoundary=L.geoJSON(boundaryFeature);
  hanoiBounds=hanoiBoundary.getBounds();
  if(!hanoiBounds.isValid()||!hanoiBoundaryRings.length)throw new Error('Không đọc được tọa độ ranh giới Hà Nội.');
  map=L.map('map',{zoomControl:false,minZoom:2,maxZoom:18,maxBounds:hanoiBounds,maxBoundsViscosity:1});
  map.setMinZoom(Math.max(2,map.getBoundsZoom(hanoiBounds,false,L.point(48,48))));
  $('#map-region').value='hanoi';
  map.fitBounds(hanoiBounds,{padding:[24,24]});
  L.control.zoom({position:'bottomright'}).addTo(map);
  baseTiles=buildTileLayer(TILE_ORDER[tileProviderIndex]);
  // Hồ vẽ tay chỉ dùng cho sơ đồ ngoại tuyến; trên nền tile thật hồ đã được vẽ đúng hình.
  geographyLayer=L.layerGroup();
  // Sơ đồ giản lược ngoại tuyến: dùng khi tile trực tuyến không tải được.
  const districts=[
    ['Tây Hồ',[[21.044,105.795],[21.083,105.799],[21.085,105.856],[21.050,105.855]]],
    ['Cầu Giấy',[[21.001,105.780],[21.044,105.784],[21.047,105.819],[21.005,105.822]]],
    ['Ba Đình',[[21.020,105.813],[21.047,105.814],[21.049,105.846],[21.021,105.846]]],
    ['Hoàn Kiếm',[[21.013,105.840],[21.043,105.840],[21.043,105.866],[21.014,105.868]]],
    ['Đống Đa',[[20.994,105.808],[21.025,105.809],[21.026,105.844],[20.996,105.846]]],
    ['Hai Bà Trưng',[[20.990,105.838],[21.021,105.839],[21.022,105.872],[20.992,105.873]]]
  ];
  for(const [name,shape] of districts){
    L.polygon(shape,{color:'#d7dfdb',fillColor:'#f6f8f6',fillOpacity:.72,weight:1,interactive:false}).addTo(geographyLayer);
    const lat=shape.reduce((a,p)=>a+p[0],0)/shape.length,lng=shape.reduce((a,p)=>a+p[1],0)/shape.length;
    L.marker([lat,lng],{interactive:false,icon:L.divIcon({className:'district-label',html:`<span>${name}</span>`,iconSize:[90,22],iconAnchor:[45,11]})}).addTo(geographyLayer);
  }
  for(const [name,point] of [['Hà Nội',[21.0285,105.8420]]]){
    L.marker(point,{interactive:false,icon:L.divIcon({className:'regional-label',html:`<span>${name}</span>`,iconSize:[100,26],iconAnchor:[50,13]})}).addTo(geographyLayer);
  }
  const lakes=[['Hồ Tây',[[21.043,105.825],[21.048,105.817],[21.058,105.812],[21.070,105.819],[21.073,105.835],[21.060,105.842],[21.048,105.839]]],['Hồ Hoàn Kiếm',[[21.0313,105.852],[21.0300,105.8537],[21.026,105.8537],[21.0252,105.8518],[21.028,105.8509]]],['Hồ Bảy Mẫu',[[21.0135,105.8443],[21.0134,105.8470],[21.009,105.8477],[21.0074,105.8460],[21.008,105.8444]]],['Hồ Thủ Lệ',[[21.0335,105.8006],[21.0339,105.8060],[21.0308,105.8078],[21.0300,105.8028]]]];
  for(const [name,shape] of lakes)L.polygon(shape,{color:'#8ebfc0',fillColor:'#b9dada',fillOpacity:.9,weight:1.2,interactive:false}).addTo(geographyLayer).bindTooltip(name,{permanent:true,direction:'center',className:'water-label'});
  const axes=[
    [[21.0313,105.8006],[21.0318,105.8247],[21.0274,105.8355],[21.0263,105.8417],[21.0285,105.8521],[21.0272,105.8600]],
    [[21.0182,105.8053],[21.0163,105.8132],[21.0126,105.8211],[21.0181,105.8290],[21.0184,105.8393],[21.0200,105.8475],[21.0242,105.8571]],
    [[21.0435,105.8220],[21.0366,105.8310],[21.0374,105.8382],[21.0400,105.8489]],
    [[21.0030,105.8200],[21.0064,105.8292],[21.0095,105.8352],[21.0078,105.8422],[21.0102,105.8482]]
  ];
  for(const line of axes)L.polyline(line,{color:'#c7cfcb',weight:5,opacity:.9,interactive:false}).addTo(geographyLayer);
  // Ưu tiên bản đồ nền Hà Nội trực tuyến; sơ đồ trên chỉ là dự phòng.
  baseTiles.addTo(map);
  $('#base-tiles').checked=true;
  map.createPane('rainfallPane');
  map.getPane('rainfallPane').style.zIndex=350;
  map.getPane('rainfallPane').style.pointerEvents='auto';
  map.createPane('tomtomTrafficPane');
  map.getPane('tomtomTrafficPane').style.zIndex=390;
  map.createPane('hanoiMaskPane');
  map.getPane('hanoiMaskPane').style.zIndex=450;
  map.getPane('hanoiMaskPane').style.pointerEvents='none';
  map.createPane('hanoiBoundaryPane');
  map.getPane('hanoiBoundaryPane').style.zIndex=460;
  map.getPane('hanoiBoundaryPane').style.pointerEvents='none';
  map.createPane('tomtomSegmentPane');
  map.getPane('tomtomSegmentPane').style.zIndex=625;
  const maskPadding=10;
  const maskSouth=Math.max(-85,hanoiBounds.getSouth()-maskPadding);
  const maskNorth=Math.min(85,hanoiBounds.getNorth()+maskPadding);
  const maskWest=hanoiBounds.getWest()-maskPadding;
  const maskEast=hanoiBounds.getEast()+maskPadding;
  const maskOuter=[[maskSouth,maskWest],[maskSouth,maskEast],[maskNorth,maskEast],[maskNorth,maskWest]];
  L.polygon([maskOuter,...hanoiBoundaryRings],{
    pane:'hanoiMaskPane',color:'#f5f8f7',fillColor:'#f5f8f7',
    fillOpacity:1,opacity:0,weight:0,fillRule:'evenodd',interactive:false
  }).addTo(map);
  L.polyline(hanoiBoundaryRings[0],{
    pane:'hanoiBoundaryPane',color:'#087f72',weight:2,opacity:.9,interactive:false
  }).addTo(map);
  gpmRainLayer=L.layerGroup().addTo(map);
  tomtomTrafficLayer=L.tileLayer('/api/tomtom/flow/{z}/{x}/{y}.png',{
    minZoom:9,maxZoom:18,pane:'tomtomTrafficPane',opacity:.95,
    attribution:'Traffic flow © nguồn lưu lượng',updateWhenIdle:true,keepBuffer:3
  });
  tomtomTrafficLayer.on('tileerror',()=>{
    tomtomError='Nguồn lưu lượng không trả dữ liệu · kiểm tra quyền API, quota hoặc kết nối';
    renderTomtomTrafficStatus();
  });
  tomtomTrafficLayer.on('tileload',()=>{tomtomError=null;renderTomtomTrafficStatus();});
  if(state.liveStatus?.traffic?.configured)tomtomTrafficLayer.addTo(map);
  tomtomSegmentLayer=L.layerGroup().addTo(map);
  placeLayer=L.layerGroup().addTo(map);
  roadLayer=L.layerGroup().addTo(map);
  routeLayer=L.layerGroup().addTo(map);
  eventLayer=L.layerGroup().addTo(map);
  selectionLayer=L.layerGroup().addTo(map);
  map.on('click', e=>{
    if(!isWithinHanoi(e.latlng.lat,e.latlng.lng))return;
    if(state.picking){finishPick(e.latlng.lat,e.latlng.lng);return;}
    if(REAL_DATA_ONLY)loadTomtomSegment(e.latlng);
  });
  map.on('movestart',()=>$('#search-results').hidden=true);
  map.on('moveend',renderGpmSummary);
  $('.map-left-bottom').insertAdjacentHTML('beforeend','<div class="gpm-map-legend"><span>Mưa IMERG (mm/h)</span><i></i><small>0 · 1 · 2,5 · 7,5 · 15+</small></div>');
  $('.map-left-bottom').insertAdjacentHTML('beforeend','<div class="tomtom-map-legend"><span>Lưu lượng hiện tại</span><i></i><small id="tomtom-traffic-status">Đang kiểm tra nguồn dữ liệu trực tiếp…</small></div>');
}

function isWithinHanoi(latitude,longitude){
  if(!hanoiBounds?.contains([latitude,longitude]))return false;
  const insideRing=ring=>{
    let inside=false;
    for(let i=0,j=ring.length-1;i<ring.length;j=i++){
      const [latA,lngA]=ring[i], [latB,lngB]=ring[j];
      if((latA>latitude)!==(latB>latitude)
        &&longitude<(lngB-lngA)*(latitude-latA)/(latB-latA)+lngA)inside=!inside;
    }
    return inside;
  };
  return insideRing(hanoiBoundaryRings[0])
    &&hanoiBoundaryRings.slice(1).every(ring=>!insideRing(ring));
}

async function refresh() {
  if(refreshing){await refreshing;return refresh();}
  let complete;
  refreshing=new Promise(resolve=>complete=resolve);
  try {
    state.liveStatus=await api('/api/live-status');
    ensureMapState();
    state.data.generated_at=Date.now()/1000;
    state.connected=true;state.lastGood=Date.now();
    $('#connection-error').hidden=true;
    $('#sync-status').textContent=state.liveStatus.traffic.configured
      ?'Đã cấu hình nguồn lưu lượng · đang chờ số đo trực tiếp'
      :'Chưa có số đo trực tiếp · cần cấu hình nguồn lưu lượng';
      if(state.liveStatus.traffic.configured&&tomtomTrafficEnabled&&!map.hasLayer(tomtomTrafficLayer))
        tomtomTrafficLayer.addTo(map);
      if(!state.liveStatus.traffic.configured&&map.hasLayer(tomtomTrafficLayer))
        map.removeLayer(tomtomTrafficLayer);
      renderTomtomTrafficStatus();
    $('.status-dot').style.background='#49a68b';
     if(!sourcesRendered){renderSources();sourcesRendered=true;}
    updateDashboard();
    updateAlertBanner();
    if(state.view==='reports') await loadReports();
  } catch(e) {
    state.connected=false;$('#connection-error').hidden=false;
    $('#connection-error').textContent=`Không đọc được trạng thái nguồn dữ liệu: ${e.message}`;
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
  for(const type of ['flood','incident']) $(`#stat-${type}`).textContent='—';
  if(state.lastTomtomSegment&&Date.now()-Date.parse(state.lastTomtomSegment.segment.sampled_at)>=5*60*1000)
    state.lastTomtomSegment=null;
  $('#stat-traffic').textContent=state.lastTomtomSegment
    ?`${state.lastTomtomSegment.segment.current_speed_kmh} km/h`:'—';
  $('#traffic-caption').textContent=state.lastTomtomSegment
    ?`Đoạn đo lưu lượng · độ tin cậy ${Math.round(state.lastTomtomSegment.segment.confidence*100)}%`
    :state.liveStatus?.traffic?.configured?'Chọn một điểm trên bản đồ để đo':'Chưa cấu hình nguồn lưu lượng';
  renderGpmSummary();
  $('#map-clock').textContent=timeText(d.generated_at);
  $('#nav-count').hidden=true;
  renderMap();renderEvents();renderInsight();
  if(state.view==='forecast')renderForecast();
}

function roadColor(r) {
  if(!r.known) return '#aab5af';
  if(tomtomTrafficEnabled&&r.tomtom_flow){
    if(r.tomtom_flow.road_closure)return '#a82435';
    if(r.tomtom_flow.speed_ratio>=.85)return '#369477';
    if(r.tomtom_flow.speed_ratio>=.65)return '#c4a23f';
    if(r.tomtom_flow.speed_ratio>=.4)return '#e58a3a';
    return '#d14c45';
  }
  if(r.id.startsWith('BN-OSM-')){
    const risk=r.forecast[0].risk;
    return risk>=65?'#d76e62':risk>=35?'#daa34d':'#74ad92';
  }
  if(state.horizon) {
    const risk=r.forecast[state.horizon/15].risk;
    return risk>=65?'#d76e62':risk>=35?'#daa34d':'#74ad92';
  }
  if(r.blocked) return '#c95650';
  if(r.event_type && state.layers[r.event_type]) return {flood:'#568eeb',traffic:'#e9a34d',incident:'#df7469'}[r.event_type];
  return '#86b9a0';
}

function renderMap() {
  if(!state.data||!roadLayer||!eventLayer)return;
  roadLayer.clearLayers();eventLayer.clearLayers();
  if(REAL_DATA_ONLY){
    const visible=visibleModelRoads();
    state.visibleModelRoadIds=new Set(visible.map(r=>r.id));
    for(const report of verifiedReports){
      if(!Number.isFinite(report.lat)||!Number.isFinite(report.lng))continue;
      const marker=L.circleMarker([report.lat,report.lng],{radius:7,color:'#ad6b32',fillColor:'#f0a04f',fillOpacity:.9,weight:2}).addTo(eventLayer);
      marker.bindPopup(`<strong>Phản ánh đã duyệt · ${esc(typeNames[report.type]||report.type)}</strong><p>${esc(report.description)}</p><small>${esc(report.address)} · ${new Date(report.created_at*1000).toLocaleString('vi-VN')}</small><p><small>Được duyệt bởi quản trị viên; không đồng nghĩa đã được cơ quan độc lập kiểm chứng.</small></p>`);
    }
    $('#map-mode-label').hidden=true;
    $('.map-legend').innerHTML='<span><i class="legend-dot" style="background:#25886c"></i>Thông thoáng · ≥85%</span><span><i class="legend-dot" style="background:#cea42b"></i>Chậm · 65–84%</span><span><i class="legend-dot" style="background:#dd832f"></i>Ùn tắc · 40–64%</span><span><i class="legend-dot" style="background:#d24d49"></i>Ùn tắc nặng · &lt;40%</span><span><i class="legend-dot" style="background:#c83c3c"></i>Đóng đường</span><span><i class="legend-dot" style="background:#7f919c"></i>Chưa có số đo</span>';
    return;
  }
  const visibleRoads=visibleModelRoads();
  const visibleRoadIds=new Set(visibleRoads.map(road=>road.id));
  state.visibleModelRoadIds=visibleRoadIds;
  for(const r of visibleRoads) {
    if(tomtomTrafficEnabled){
      const liveFlow=cachedTomtomFlow(r.id);
      if(liveFlow)r.tomtom_flow=liveFlow;
      else delete r.tomtom_flow;
    }
    const f=r.forecast[state.horizon/15];
    const color=roadColor(r), hasLiveFlow=tomtomTrafficEnabled&&r.tomtom_flow, weight=r.id===state.selected?7:hasLiveFlow?5:4;
    if(hasLiveFlow)L.polyline(r.coordinates,{color:'#465965',weight:weight+3,opacity:.95,lineCap:'round',lineJoin:'round',interactive:false}).addTo(roadLayer);
    const line=L.polyline(r.coordinates,{color,weight,opacity:.88,dashArray:r.known?null:'5 6'}).addTo(roadLayer);
    const tooltip=hasLiveFlow
      ?`<strong>${esc(r.name)}</strong><br>Lưu lượng trực tiếp: ${r.tomtom_flow.current_speed_kmh} km/h · ${Math.round(r.tomtom_flow.speed_ratio*100)}% tốc độ thông thoáng<br>Độ tin cậy ${Math.round(r.tomtom_flow.confidence*100)}%`
      :r.id.startsWith('BN-OSM-')
      ?`<strong>${esc(r.name)}</strong><br>${r.speed} km/h · Nguy cơ ${f.risk}/100 · mô phỏng`
      :`<strong>${esc(r.name)}</strong><br>${!r.known?'Chưa đủ dữ liệu':state.horizon?`Dự báo +${state.horizon} phút · Nguy cơ ${f.risk}/100 · mô phỏng`:`${r.speed} km/h · ${r.blocked?'Đóng trong kịch bản':'Dữ liệu thử nghiệm'}`}`;
    const midpoint=r.coordinates[Math.floor(r.coordinates.length/2)];
    const rainfall=gpmCellAt(midpoint);
    line.bindTooltip(`${tooltip}${rainfall?`<br>Mưa NASA GPM ở ô gần nhất: ${formatGpmRate(rainfall.rainfall_mm_hr)} · ${gpmRainData.resolution_degrees}°`:''}`);
    line.on('mouseover',e=>{
      if(!tomtomTrafficEnabled||state.picking||r.tomtom_flow)return;
      clearTimeout(tomtomHoverTimer);
      tomtomHoverTimer=setTimeout(()=>loadTomtomSegment(e.latlng,r.id),250);
    });
    line.on('mouseout',()=>clearTimeout(tomtomHoverTimer));
    line.on('click',e=>{
      L.DomEvent.stopPropagation(e);
      if(state.picking){finishPick(e.latlng.lat,e.latlng.lng);return;}
      clearTimeout(roadClickTimer);
      selectRoad(r.id);
      loadTomtomSegment(e.latlng,r.id);
    });
  }
  if(!state.horizon) for(const e of state.data.events) {
    if(!visibleRoadIds.has(e.road_id))continue;
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
  const events=state.demoEvents;
  $('#event-list').innerHTML=events.length?events.map(e=>{
    const summary=e.type==='flood'?`Ngập mô phỏng · độ sâu ${e.depth??'chưa đo'}${e.depth!=null?' cm':''}`:e.type==='traffic'?`Ùn tắc mô phỏng · tốc độ ${e.speed} km/h`:'Sự cố giao thông mô phỏng';
    return `<article class="event-item"><span class="event-type-icon ${typeColors[e.type]}">${icon(typeIcons[e.type])}</span><div class="event-copy"><h3>${esc(e.name)}</h3><p>${esc(summary)}</p><div class="event-meta"><span class="tag tag-${typeColors[e.type]}">${typeNames[e.type]}</span><span>Mô phỏng · ${ago(e.updated_at)}</span></div></div></article>`;
  }).join(''):`<div class="empty-state">${icon('check')}Không có sự kiện trong kịch bản mô phỏng hiện tại.</div>`;
}

function renderInsight() {
  if(REAL_DATA_ONLY){
    $('#insight-road').textContent=state.lastTomtomSegment?.roadName||'Chưa chọn đoạn đường';
    $('#insight-summary').textContent=state.lastTomtomSegment
      ?`Nguồn lưu lượng ghi nhận ${state.lastTomtomSegment.segment.current_speed_kmh} km/h · tốc độ thông thoáng ${state.lastTomtomSegment.segment.free_flow_speed_kmh} km/h. Chưa có mô hình dự báo ETA tương lai.`
      :'Chọn một vị trí trên bản đồ để truy vấn tốc độ giao thông trực tiếp.';
    $('#mini-forecast').replaceChildren();
    return;
  }
  const available=visibleModelRoads();
  if(state.locationFocus&&!available.length){
    $('#insight-road').textContent='Chưa có tuyến mô hình gần GPS';
    $('#insight-summary').textContent='Nền OpenStreetMap vẫn hiển thị, nhưng khu vực này chưa có dữ liệu tuyến thử nghiệm.';
    $('#mini-forecast').innerHTML='';
    return;
  }
  const road=available.find(r=>r.id===state.selected)||available[0];
  state.selected=road.id;
  $('#forecast-road').value=road.id;
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
  $('#detail-content').innerHTML=`<div class="dialog-heading"><div><div class="eyebrow teal-text">${event?.status==='pending'?'PHẢN ÁNH CHỜ XÁC MINH':'CHI TIẾT ĐOẠN ĐƯỜNG'}</div><h2>${esc(event?.name||r.name)}</h2></div><button class="icon-button close-dialog" aria-label="Đóng chi tiết">${icon('close')}</button></div><span class="tag tag-${event?.status==='pending'?'gray':'teal'}">${event?.status==='pending'?'Chưa ảnh hưởng định tuyến':r.origin==='demo'?'Dữ liệu mô phỏng':'Phản ánh đã xác minh tại máy'}</span><div class="detail-stats"><div><span>Tốc độ hiện tại</span><strong>${r.known?r.speed+' km/h · mô phỏng':'Chưa rõ'}</strong></div><div><span>Nguy cơ ngập +30p</span><strong>${f.flood_risk==null?'Chưa rõ':f.flood_risk+'/100'}</strong></div><div><span>Lưu thông</span><strong>${!r.known?'Chưa rõ':r.blocked?'Bị chặn':'Có thể đi*'}</strong></div></div><p class="data-label">${esc((event?.sources||r.sources).join(' · '))} · ${timeText(event?.updated_at||r.updated_at)}</p><div class="detail-evidence">${esc((event?.evidence||r.evidence).join('\n'))}</div>  <p class="muted">*Nguy cơ ngập và dự báo là mô hình thử nghiệm. Rê chuột hoặc nhấn một lần lên tuyến trên bản đồ để xem số đo lưu lượng trực tiếp.</p><div class="dialog-footer"><button class="button secondary" data-focus-road="${r.id}">${icon('pin')}Xem trên bản đồ</button><button class="button primary" data-forecast-detail="${r.id}">Xem dự báo ${icon('arrow')}</button></div>`;  if(!$('#detail-dialog').open)$('#detail-dialog').showModal();
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
  if(REAL_DATA_ONLY){
    $('#forecast-chart').innerHTML='<div class="empty-state">Chưa có dự báo thực tế. Cần tích lũy dữ liệu giao thông lịch sử và triển khai mô hình đã huấn luyện; không hiển thị kết quả mô phỏng.</div>';
    return;
  }
  const roads=visibleModelRoads();
  if(state.locationFocus&&!roads.length){
    $('#forecast-chart').innerHTML='<div class="empty-state">Chưa có tuyến mô hình trong vùng GPS này. Nền OpenStreetMap vẫn khả dụng.</div>';
    return;
  }
  const r=roads.find(r=>r.id===$('#forecast-road').value)||roads[0];if(!r)return;
  state.selected=r.id;$('#forecast-road').value=r.id;
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
    ['cloud','Vệ tinh NASA GPM (IMERG)',state.liveStatus?.rainfall?.configured?'Đã cấu hình':'Chưa cấu hình','blue','IMERG Early Run V07 cung cấp ước lượng mưa nửa giờ theo ô lưới 0,1° (~10 km). Mỗi ô trên bản đồ và vị trí GPS được gán giá trị ô gần nhất; đây không phải đo tại chỗ.','Cần NASA Earthdata Login token trong biến môi trường NASA_EARTHDATA_TOKEN của máy chủ.'],
    ['water','NASA SMAP & NASADEM (TWI)','Độ ẩm đất & Địa hình NASA','teal','Chỉ số độ ẩm bão hòa đất (SMAP) & Chỉ số trũng địa hình (Topographic Wetness Index - TWI 30m). Xác định các điểm tụ nước tự nhiên.','Khai thác DEM 30m từ NASA SRTM/NASADEM tính TWI; nạp độ ẩm đất SMAP làm biến điều kiện bão hòa dòng chảy mặt.'],
    ['chart','Bộ mô phỏng giao thông','Đã tắt trên bản đồ','gray','Các chỉ số dự báo minh họa không được dùng trong chế độ dữ liệu thật.','—'],
    ['report','Phản ánh cộng đồng','Lưu thật tại máy','teal','Vị trí, mô tả, ảnh lưu trong SQLite. Cần xác minh thủ công.','—'],
    ['cloud','API Khí tượng (NCHMF / OpenWeather)','Sẵn sàng tích hợp','orange','Lượng mưa trạm mặt đất, dự báo 3 giờ tới. 3 kịch bản mô phỏng hiện tại.','Đăng ký API key OpenWeatherMap miễn phí (1000 calls/ngày) hoặc sử dụng bản tin NCHMF theo điều kiện cho phép.'],
    ['car','VOV Giao thông','Chưa kết nối','gray','Bản tin ùn tắc, tai nạn, đường bị ảnh hưởng theo thời gian thực.','Xin phép API/RSS từ VOV. Không tự động thu thập khi chưa được cấp phép; trích xuất NLP sau khi có dữ liệu hợp pháp.'],
    ['water','Hệ thống thoát nước Hà Nội','Chưa kết nối','gray','Mực nước, điểm ngập, vận hành trạm bơm tại các trạm quan trắc.','Hợp tác với Cty TNHH MTV Thoát nước HN. Lấy dữ liệu qua API/SFTP định kỳ.'],
    ['layers','Camera giao thông (AI)','Chưa kết nối','gray','Ước lượng mật độ, phát hiện xe dừng bất thường qua RTSP stream.','Tích hợp RTSP từ hệ thống camera Sở GTVT. YOLO + ByteTrack phân tích.'],
    ['water','Google Flood Hub','Có thể tham khảo','orange','Dự báo lũ lụt Google cho khu vực sông Hồng, sông Tô Lịch.','API Flood Hub yêu cầu Google phê duyệt quyền truy cập; cần kiểm tra độ phủ và điều khoản sử dụng.'],
    ['car','Lưu lượng giao thông trực tiếp',state.liveStatus?.traffic?.configured?'Đã cấu hình':'Chưa cấu hình','orange','Lớp lưu lượng hiện tại và dữ liệu đoạn đường được truy vấn từ nguồn lưu lượng trực tiếp; chỉ số không có sẵn sẽ để trống. Không có dự báo giao thông tương lai nếu chưa có model và dữ liệu huấn luyện.','Đặt khóa nguồn lưu lượng trong môi trường máy chủ VietSafe. Lưu lượng/API có thể chịu quota và độ phủ địa phương.'],
    ['alert','Mạng xã hội (Facebook, Zalo)','Chưa kết nối','gray','Bài viết công khai từ các nhóm cộng đồng giao thông Hà Nội.','Chỉ thu thập khi có sự đồng ý/quyền sử dụng, tuân thủ chính sách nền tảng và quyền riêng tư.'],
    ['pin','Cảm biến IoT ngập','Chưa kết nối','gray','Cảm biến siêu âm đo mực nước tại các điểm ngập trọng điểm.','Triển khai cảm biến tại 10–15 điểm ngập. Truyền dữ liệu qua LoRa/4G.'],
  ];
  $('#source-grid').innerHTML=sources.map(([i,n,s,c,d,plan])=>`<article class="source-card">${icon(i)}<h3>${n}</h3><span class="tag tag-${c}">${s}</span><p>${d}</p>${plan!=='—'?`<p class="source-plan"><strong>Kế hoạch thu thập:</strong> ${plan}</p>`:''}</article>`).join('');
}

async function changeScenario(value) {
  if(REAL_DATA_ONLY){toast('Kịch bản mô phỏng đã tắt trong chế độ chỉ dữ liệu thật.');return;}
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
function openRoute(){if(REAL_DATA_ONLY){toast('Định tuyến thực tế chưa khả dụng vì chưa có nguồn ETA/tuyến trực tiếp.');return;}if(!state.data){toast('Đang tải dữ liệu, vui lòng thử lại.');return;}$('#event-panel').hidden=true;$('#route-panel').hidden=false;requestAnimationFrame(()=>map.invalidateSize());}
async function findRoutes(e){
  e.preventDefault();if(REAL_DATA_ONLY){toast('Định tuyến thực tế chưa khả dụng; không dùng tuyến mô phỏng.');return;}if(!state.connected){toast('Cần kết nối máy chủ để tính tuyến mới.');return;}
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
  if(!isWithinReportBounds(lat,lng)){toast('Phản ánh hiện chỉ tiếp nhận trong vùng thử nghiệm nội thành Hà Nội.');return;}
  state.picking=false;$('#pick-banner').hidden=true;$('.map-surface').classList.remove('picking');
  const nearest=state.data.roads.length
    ?state.data.roads.map(r=>({r,d:Math.hypot(lat-(r.coordinates[0][0]+r.coordinates[1][0])/2,lng-(r.coordinates[0][1]+r.coordinates[1][1])/2)})).sort((a,b)=>a.d-b.d)[0].r
    :null;
  setReportPosition(lat,lng,nearest?.name||'Vị trí do người dùng chọn');selectionLayer.clearLayers();L.circleMarker([lat,lng],{radius:9,color:'#087f72',fillOpacity:.3}).addTo(selectionLayer);$('#report-dialog').showModal();
}
function isWithinReportBounds(lat,lng){
  return lat>=REPORT_BOUNDS[0][0]&&lat<=REPORT_BOUNDS[1][0]
    &&lng>=REPORT_BOUNDS[0][1]&&lng<=REPORT_BOUNDS[1][1];
}
function geolocate(forReport=false){
  if(!navigator.geolocation){toast('Trình duyệt không hỗ trợ định vị. Bạn có thể chọn trên bản đồ.');return;}
  toast('Đang xác định vị trí. Cho phép trình duyệt truy cập vị trí nếu được hỏi.');
  navigator.geolocation.getCurrentPosition(p=>{
    const {latitude:lat,longitude:lng}=p.coords;
    if(!isWithinHanoi(lat,lng)){
      toast('Vị trí GPS nằm ngoài phạm vi bản đồ Hà Nội.');
      return;
    }
    if(forReport){
      if(!isWithinReportBounds(lat,lng)){
        toast('GPS nằm ngoài vùng tiếp nhận phản ánh thử nghiệm nội thành Hà Nội. Bạn vẫn có thể xem vị trí này trên bản đồ.');
        return;
      }
      setReportPosition(lat,lng,'Vị trí GPS của tôi');
      return;
    }
    state.locationFocus={lat,lng,radiusKm:3};
    $('#map-region').value='gps';
    map.setView([lat,lng],15);
    selectionLayer.clearLayers();
    gpsLocationMarker=L.circleMarker([lat,lng],{radius:9,color:'#087f72',fillColor:'#fff',fillOpacity:.8,weight:3})
      .addTo(selectionLayer)
      .bindTooltip('Vị trí GPS',{direction:'top'});
    renderGpmSummary();
    if(state.data){renderMap();renderEvents();renderInsight();}
    toast('Đã xác định vị trí GPS trên bản đồ.');
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
$('#zoom-map-in').addEventListener('click',()=>setMapExpanded(true));
$('#zoom-map-out').addEventListener('click',()=>setMapExpanded(false));
$$('[data-layer]').forEach(el=>el.addEventListener('change',()=>{state.layers[el.dataset.layer]=el.checked;if(state.data)renderMap();}));
$('#base-tiles').addEventListener('change',e=>setBaseTiles(e.target.checked));
$('#tomtom-map-layer').addEventListener('change',e=>setTomtomTrafficVisible(e.target.checked));
$('#map-region').addEventListener('change',e=>{
  if(e.target.value==='gps'){
    if(state.locationFocus){
      const point=L.latLng(state.locationFocus.lat,state.locationFocus.lng);
      if(!isWithinHanoi(point.lat,point.lng)){
        state.locationFocus=null;
        $('#map-region').value='hanoi';
        toast('Vị trí GPS nằm ngoài phạm vi bản đồ Hà Nội.');
        map.fitBounds(hanoiBounds,{padding:[24,24]});
        if(state.data){renderMap();renderEvents();}
        return;
      }
      map.setView(point,16);
    }else{$('#map-region').value='hanoi';toast('Nhấn “Vị trí của tôi” để lấy GPS trước.');}
    return;
  }
  state.locationFocus=null;
  selectionLayer.clearLayers();
  if(e.target.value!=='hanoi')return;
  map.fitBounds(hanoiBounds,{padding:[24,24]});
  if(state.data){renderMap();renderEvents();}
});
$('#fit-map').addEventListener('click',()=>{state.locationFocus=null;$('#map-region').value='hanoi';map.fitBounds(hanoiBounds,{padding:[24,24]});if(state.data){renderMap();renderEvents();}});
$('#my-location').addEventListener('click',()=>geolocate());
$('#open-report').addEventListener('click',openReport);
$('#about-button').addEventListener('click',()=>$('#about-dialog').showModal());
$('#open-route').addEventListener('click',openRoute);
$('#close-route').addEventListener('click',()=>{$('#route-panel').hidden=true;$('#event-panel').hidden=false;routeLayer.clearLayers();});
$('#route-form').addEventListener('submit',findRoutes);
$('#forecast-road')?.addEventListener('change',()=>{state.selected=$('#forecast-road').value;renderForecast();renderInsight();});
$('#forecast-scenario')?.addEventListener('change',e=>changeScenario(e.target.value));
$('#source-scenario')?.addEventListener('change',e=>changeScenario(e.target.value));
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
        const text = `GPS: ${lat.toFixed(6)}, ${lng.toFixed(6)} (sai số khoảng ${Math.round(pos.coords.accuracy)} m)`;
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
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
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

// Observations must be verified measurements, not rainfall-derived flood estimates.
async function refreshVerifiedFloodObservations(){
  if(!map)return;
  if(!verifiedFloodLayer)verifiedFloodLayer=L.layerGroup().addTo(map);
  try{
    const result=await api('/api/flood/observations',{timeoutMs:12000});
    verifiedFloodLayer.clearLayers();
    for(const obs of result.observations||[]){
      const marker=L.circleMarker([obs.lat,obs.lng],{radius:8,color:'#146fba',
          fillColor:'#46a7e5',fillOpacity:.8,weight:2});
      marker.bindPopup(`<strong>Điểm đo ngập đã xác minh</strong><p>Độ sâu tại điểm đo: ${Number(obs.depth_cm).toFixed(1)} cm</p><p>Nguồn: ${esc(obs.source)} · ${esc(obs.source_reference)}</p><p>Ghi nhận: ${new Date(obs.observed_at*1000).toLocaleString('vi-VN')}</p><small>Không suy rộng số đo cho toàn bộ tuyến đường.</small>`);
      marker.addTo(verifiedFloodLayer);
    }
    verifiedFloodCount=(result.observations||[]).length;
    const count=$('#stat-flood');if(count)count.textContent=String(verifiedFloodCount);
  }catch(error){
    console.warn('Không tải được dữ liệu điểm đo ngập đã xác minh:',error.message);
  }
}
async function refreshVerifiedReports(){
  try{
    const payload=await api('/api/reports',{timeoutMs:12000});
    const now=Date.now()/1000;
    verifiedReports=(payload.reports||[]).filter(r=>r.status==='verified'&&Number(r.expires_at)>now);
    renderMap();
  }catch(error){console.warn('Không tải được phản ánh đã duyệt:',error.message);}
}
async function refreshDemoEvents(){
  try{
    const result=await api('/api/demo/events',{timeoutMs:12000});
    state.demoEvents=result.events||[];
    renderEvents();
  }catch(error){
    $('#event-list').innerHTML=`<div class="empty-state">Không tải được sự kiện mô phỏng: ${esc(error.message)}</div>`;
    console.error('Không tải được sự kiện mô phỏng:',error);
  }
}
// === Init ===
if(typeof L==='undefined'){$('#connection-error').hidden=false;$('#connection-error').textContent='Thiếu thư viện bản đồ local. Kiểm tra thư mục frontend/vendor.';}
else{
  checkAuth();
  initializeMap().then(()=>{
    ensureMapState();
    refresh().then(()=>{if(state.liveStatus?.rainfall?.configured)loadGpmRainfall();else{gpmError='Chưa cấu hình NASA_EARTHDATA_TOKEN';renderGpmSummary();}});
    refreshVerifiedReports();refreshVerifiedFloodObservations();refreshDemoEvents();
    setInterval(refresh,30000);
    setInterval(()=>{if(state.liveStatus?.rainfall?.configured)loadGpmRainfall(true);},30*60*1000);
    setInterval(refreshVerifiedReports,60000);
    setInterval(refreshVerifiedFloodObservations,60000);
    setInterval(refreshDemoEvents,60000);
  }).catch(error=>{
    $('#connection-error').hidden=false;
    $('#connection-error').textContent=`Không khởi tạo được bản đồ Hà Nội: ${error.message}`;
    console.error('Không khởi tạo được bản đồ Hà Nội:',error);
  });
}
