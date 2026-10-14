'use strict';
// Các cải tiến được gắn lên đúng giao diện gốc VietSafe thay vì thay design system.
(function(){
  const demoPosition=[21.0287,105.8342];
  let protoLayers, heatLayer, zoneLayer, infraLayer, trackingLayer;
  let playTimer=null, routePriority='safe', avoidFlood=true, nearbyKm=3, tracking=false;
  const layerState={heatmap:false,floodzone:true,camera:true,sensor:true,rescue:true};

  function ensureGroups(){
    if(protoLayers)return;
    heatLayer=L.layerGroup().addTo(map); zoneLayer=L.layerGroup().addTo(map); infraLayer=L.layerGroup().addTo(map); trackingLayer=L.layerGroup().addTo(map);
    protoLayers={heatLayer,zoneLayer,infraLayer,trackingLayer};
    if(!$('#model-coverage'))$('.map-surface')?.insertAdjacentHTML('beforeend','<div id="model-coverage" class="model-coverage" hidden></div>');
  }

  function addTimeline(){
    const seg=$('#map-horizon'); if(!seg)return;
    const b30=seg.querySelector('[data-horizon="30"]');
    if(b30&&!seg.querySelector('[data-horizon="15"]')) b30.insertAdjacentHTML('beforebegin','<button data-horizon="15">+15 phút</button>');
    const b60=seg.querySelector('[data-horizon="60"]');
    if(b60&&!seg.querySelector('[data-horizon="45"]')) b60.insertAdjacentHTML('beforebegin','<button data-horizon="45">+45 phút</button>');
    if(!$('#forecast-play')) seg.insertAdjacentHTML('beforeend',`<button class="timeline-play" id="forecast-play" title="Phát dự báo 0–60 phút">${icon('arrow')}<span>Phát</span></button>`);
    $('#forecast-play').addEventListener('click',()=>{
      if(playTimer){clearInterval(playTimer);playTimer=null;$('#forecast-play').classList.remove('playing');$('#forecast-play span').textContent='Phát';return;}
      const steps=[0,15,30,45,60];let i=Math.max(0,steps.indexOf(state.horizon));
      $('#forecast-play').classList.add('playing');$('#forecast-play span').textContent='Dừng';
      const step=()=>{state.horizon=steps[i%steps.length];$$('#map-horizon [data-horizon]').forEach(b=>b.classList.toggle('active',Number(b.dataset.horizon)===state.horizon));renderMap();i++;};
      step();playTimer=setInterval(step,1200);
    });
  }

  function addLayerOptions(){
    const menu=$('#layer-menu');if(!menu||menu.querySelector('[data-proto-layer]'))return;
    menu.querySelector('small').insertAdjacentHTML('beforebegin',`<span class="layer-section-title">PHÂN TÍCH & HẠ TẦNG</span>
      <label class="new-layer-label"><input type="checkbox" data-proto-layer="heatmap"><i class="layer-swatch heat"></i>Nguy cơ trên tuyến <span>mô phỏng</span></label>
      <label class="new-layer-label"><input type="checkbox" data-proto-layer="tomtom" checked><i class="layer-swatch tomtom-flow"></i>Mô hình giao thông <span>OSM + dữ liệu lưu lượng</span></label>
      <label class="new-layer-label"><input type="checkbox" data-proto-layer="gpm" checked><i class="layer-swatch gpm-rain"></i>Mưa NASA GPM · IMERG</label>
      <label class="new-layer-label"><input type="checkbox" data-proto-layer="floodzone" checked><i class="layer-swatch zone"></i>Đoạn ngập dự báo <span>mô phỏng</span></label>
      <label class="new-layer-label"><input type="checkbox" data-proto-layer="camera" checked><i class="layer-swatch camera"></i>Camera giao thông <span>mô phỏng</span></label>
      <label class="new-layer-label"><input type="checkbox" data-proto-layer="sensor" checked><i class="layer-swatch sensor"></i>Cảm biến IoT <span>mô phỏng</span></label>
      <label class="new-layer-label"><input type="checkbox" data-proto-layer="rescue" checked><i class="layer-swatch rescue"></i>Điểm cứu hộ <span>mô phỏng</span></label>
      <small class="layer-data-note">Hình học tuyến lấy từ OpenStreetMap; lớp dữ liệu lưu lượng trực tiếp hiển thị trên toàn bản đồ. Rê chuột hoặc nhấn một lần vào tuyến để xem số đo trực tiếp và gắn vào bản ghi OSM gần nhất (nếu có). Kết quả giữ 5 phút; tuyến chưa được đo trực tiếp và dự báo/nguy cơ vẫn là mô phỏng.</small>`);
    $$('[data-proto-layer]',menu).forEach(cb=>cb.addEventListener('change',()=>{
      if(cb.dataset.protoLayer==='gpm'){setGpmRainLayerVisible(cb.checked);return;}
      if(cb.dataset.protoLayer==='tomtom'){setTomtomTrafficVisible(cb.checked);return;}
      layerState[cb.dataset.protoLayer]=cb.checked;renderPrototypeLayers();
    }));
  }

  function nearestRoadPoint(point, roads=state.data.roads){
    let best=null;
    for(const road of roads){
      for(let i=1;i<road.coordinates.length;i++){
        const [lat1,lng1]=road.coordinates[i-1], [lat2,lng2]=road.coordinates[i];
        const scale=Math.cos(point[0]*Math.PI/180);
        const dx=(lng2-lng1)*scale, dy=lat2-lat1;
        const px=(point[1]-lng1)*scale, py=point[0]-lat1;
        const t=Math.max(0,Math.min(1,(px*dx+py*dy)/(dx*dx+dy*dy||1)));
        const snapped=[lat1+t*dy,lng1+t*(lng2-lng1)];
        const distanceKm=Math.hypot((point[0]-snapped[0])*111,(point[1]-snapped[1])*111*scale);
        if(!best||distanceKm<best.distanceKm)best={road,point:snapped,distanceKm};
      }
    }
    return best;
  }

  function renderPrototypeLayers(){
    if(!state.data||!map)return;ensureGroups();heatLayer.clearLayers();zoneLayer.clearLayers();infraLayer.clearLayers();
    const roads=visibleModelRoads();
    const roadIds=new Set(roads.map(road=>road.id));
    const coverage=$('#model-coverage');
    if(coverage){
      coverage.hidden=!state.locationFocus;
      if(state.locationFocus)coverage.textContent=roads.length
        ?`Mô hình đường quanh GPS · ${roads.length} đoạn trong ${state.locationFocus.radiusKm} km · rủi ro mô phỏng`
        :'Chưa có tuyến mô hình gần GPS này; hiện có dữ liệu đường OSM chi tiết tại Hà Nội và khu vực Bắc Ninh trung tâm';
      coverage.classList.toggle('empty',!roads.length);
    }
    const idx=Math.max(0,Math.min(4,Math.round(state.horizon/15)));
    if(layerState.heatmap){
      for(const road of roads){
        if(!road.known)continue;
        const risk=road.forecast[idx].risk;if(risk<28)continue;
        const color=risk>=65?'#d9685f':risk>=45?'#e5aa48':'#62ad91';
        L.polyline(road.coordinates,{color,weight:15,opacity:.28,lineCap:'round',lineJoin:'round',interactive:false}).addTo(heatLayer)
          .bindTooltip(`${esc(road.name)} · nguy cơ ${risk}/100 · mô phỏng`);
      }
    }
    if(layerState.floodzone){
      for(const event of state.data.events.filter(item=>item.type==='flood'&&item.status!=='pending'&&roadIds.has(item.road_id))){
        const road=state.data.roads.find(item=>item.id===event.road_id);if(!road?.coordinates?.length)continue;
        const risk=road.forecast[idx]?.flood_risk??road.flood_risk??55;
        const snapped=nearestRoadPoint([event.lat,event.lng],[road]);
        L.polyline(road.coordinates,{color:'#5188d7',weight:12,opacity:.22,lineCap:'round',lineJoin:'round',interactive:false}).addTo(zoneLayer);
        L.polyline(road.coordinates,{color:'#5188d7',weight:3,opacity:.72,dashArray:'5 5',lineCap:'round',lineJoin:'round',interactive:false}).addTo(zoneLayer)
          .bindTooltip(`${esc(road.name)} · nguy cơ ngập ${risk}/100 · mô phỏng`);
        if(snapped&&(event.depth||0)>0)L.tooltip({permanent:true,direction:'top',className:'proto-depth-label',offset:[0,-8]}).setLatLng(snapped.point).setContent(`${Math.round(event.depth)} cm`).addTo(zoneLayer);
      }
    }
    const infra=[
      ['camera',21.0348,105.8178,'CAM','Camera Kim Mã'],['camera',21.0186,105.8349,'CAM','Camera Xã Đàn'],['camera',21.0414,105.8116,'CAM','Camera Bưởi'],
      ['sensor',21.0289,105.8502,'IoT','Cảm biến Hoàn Kiếm'],['sensor',21.0148,105.8252,'IoT','Cảm biến Thái Hà'],['sensor',21.0475,105.8330,'IoT','Cảm biến Tây Hồ'],
      ['rescue',21.0261,105.8075,'+','Điểm cứu hộ Cầu Giấy'],['rescue',21.0205,105.8491,'+','Điểm cứu hộ Hai Bà Trưng']
    ];
    for(const [type,lat,lng,label,name] of infra){
      if(!layerState[type])continue;
      const snapped=nearestRoadPoint([lat,lng],roads);if(!snapped)continue;
      if(state.locationFocus&&snapped.distanceKm>state.locationFocus.radiusKm)continue;
      const m=L.marker(snapped.point,{icon:L.divIcon({className:'',html:`<div class="proto-map-marker ${type}"><strong>${label}</strong></div>`,iconSize:[27,27],iconAnchor:[13,13]})}).addTo(infraLayer);
      m.bindTooltip(`${name} · ghim lên ${esc(snapped.road.name)} · vị trí mô phỏng`);
    }
  }

  function addSOS(){
    const surface=$('.map-surface');if(!surface||$('#map-sos'))return;
    surface.insertAdjacentHTML('beforeend','<button id="map-sos" class="sos-map-button" title="Hỗ trợ khẩn cấp">SOS</button>');
    document.body.insertAdjacentHTML('beforeend',`<dialog id="sos-dialog"><div class="dialog-heading"><div><div class="eyebrow teal-text">HỖ TRỢ NHANH</div><h2>SOS · Bạn cần hỗ trợ gì?</h2></div><button class="icon-button close-dialog" aria-label="Đóng">${icon('close')}</button></div><p class="dialog-intro">Liên kết nhanh từ bản đồ sang chức năng ứng cứu hiện có.</p><div class="sos-location">${icon('pin')} Vị trí mô phỏng: khu vực trung tâm Hà Nội · 21.0287, 105.8342</div><div class="sos-grid"><button class="sos-option" data-sos="rescue"><strong>🚗 Cứu hộ phương tiện</strong><span>Xe chết máy, ngập nước, hỏng lốp</span></button><button class="sos-option" data-sos="medical"><strong>🚑 Cấp cứu</strong><span>Chuyển sang số khẩn cấp 115</span></button><button class="sos-option" data-sos="police"><strong>👮 Cảnh sát</strong><span>Chuyển sang số khẩn cấp 113</span></button><button class="sos-option" data-sos="share"><strong>📍 Chia sẻ vị trí</strong><span>Sao chép tọa độ hiện tại</span></button></div><div class="dialog-footer"><span>${icon('shield')}Không thay thế dịch vụ khẩn cấp chính thức</span><button class="button primary" data-sos="rescue">Mở trang Ứng cứu ${icon('arrow')}</button></div></dialog>`);
    $('#map-sos').addEventListener('click',()=>$('#sos-dialog').showModal());
  }

  function addNearbyControl(){
    const panel=$('#event-panel');const tabs=$('#event-filters');if(!panel||!tabs||panel.querySelector('.nearby-radius'))return;
    tabs.insertAdjacentHTML('beforebegin','<div class="nearby-radius"><span id="nearby-caption">Cảnh báo quanh vị trí mẫu</span><button data-radius="1">1 km</button><button class="active" data-radius="3">3 km</button><button data-radius="5">5 km</button><button data-radius="99">Toàn vùng</button></div>');
    $$('.nearby-radius button').forEach(b=>b.addEventListener('click',()=>{
      nearbyKm=Number(b.dataset.radius);
      $$('.nearby-radius button').forEach(x=>x.classList.toggle('active',x===b));
      if(state.locationFocus)state.locationFocus.radiusKm=nearbyKm;
      renderMap();renderEvents();renderInsight();if(state.view==='forecast')renderForecast();
    }));
  }
  function km(a,b){const dy=(a[0]-b[0])*111;const dx=(a[1]-b[1])*111*Math.cos(a[0]*Math.PI/180);return Math.hypot(dx,dy);}

  const baseRenderEvents=renderEvents;
  renderEvents=function(){
    if(!state.data)return;const originalFilter=state.filter;
    const all=state.data.events;
    const center=state.locationFocus?[state.locationFocus.lat,state.locationFocus.lng]:demoPosition;
    const subset=all.filter(e=>(!state.locationFocus||state.visibleModelRoadIds?.has(e.road_id))&&(originalFilter==='all'||e.type===originalFilter)&&km(center,[e.lat,e.lng])<=nearbyKm);
    const old=state.data.events;state.data.events=subset;baseRenderEvents();state.data.events=old;
    $$('.event-item').forEach(btn=>{const e=all.find(x=>x.id===btn.dataset.event);if(!e)return;const meta=btn.querySelector('.event-meta');if(meta)meta.insertAdjacentHTML('beforeend',`<span class="event-distance">· ${km(center,[e.lat,e.lng]).toFixed(1)} km</span>`);});
    if(!subset.length)$('#event-list').innerHTML=`<div class="empty-state">${state.locationFocus&&!state.visibleModelRoadIds?.size?'Chưa có dữ liệu mô hình quanh GPS này.':'Không có cảnh báo trong bán kính đang chọn. Hãy tăng phạm vi.'}</div>`;
    const caption=$('#nearby-caption');if(caption)caption.textContent=state.locationFocus?'Cảnh báo quanh GPS':'Cảnh báo quanh tâm Hà Nội (mô phỏng)';
  };

  function addRouteOptions(){
    const form=$('#route-form');if(!form||form.querySelector('.route-prototype-options'))return;
    const submit=$('button[type=submit]',form);
    submit.insertAdjacentHTML('beforebegin',`<div class="route-prototype-options"><label>Ưu tiên tìm tuyến</label><div class="route-priority"><button type="button" class="active" data-priority="safe">An toàn nhất</button><button type="button" data-priority="fast">Nhanh nhất</button><button type="button" data-priority="balanced">Cân bằng</button></div><label class="route-toggle"><input type="checkbox" id="avoid-flood" checked><span><strong>Tránh khu vực nguy cơ ngập cao</strong><br><small>Tự loại các đoạn vượt ngưỡng an toàn theo phương tiện.</small></span></label></div>`);
    $$('.route-priority button').forEach(b=>b.addEventListener('click',()=>{routePriority=b.dataset.priority;$$('.route-priority button').forEach(x=>x.classList.toggle('active',x===b));}));
    $('#avoid-flood').addEventListener('change',e=>avoidFlood=e.target.checked);
    const originalFind=findRoutes;form.removeEventListener('submit',originalFind);form.addEventListener('submit',enhancedFindRoutes);
  }
  async function enhancedFindRoutes(e){
    e.preventDefault();const button=$('button[type=submit]',$('#route-form'));button.disabled=true;button.textContent='Đang phân tích an toàn…';
    try{const query=new URLSearchParams({origin:$('#route-origin').value,destination:$('#route-destination').value,horizon:$('#route-time').value,vehicle:$('#route-vehicle').value,priority:routePriority,avoid_flood:avoidFlood?'1':'0'});state.routes=await api('/api/routes?'+query);state.routeIndex=0;renderRoutes();}
    catch(err){clearRoutes();$('#route-results').innerHTML=`<div class="empty-state">${esc(err.message)}</div>`;}
    finally{button.disabled=false;button.innerHTML=icon('route')+'Tìm tuyến gợi ý';}
  }

  renderRoutes=function(){
    routeLayer.clearLayers();const result=state.routes;if(!result?.routes?.length){$('#route-results').innerHTML=`<div class="empty-state">${icon('alert')}${esc(result?.message||'Không có tuyến phù hợp.')}</div>`;return;}
    $('#route-results').innerHTML=result.routes.map((r,i)=>{const level=r.max_risk>=65?'high':r.max_risk>=35?'mid':'low';return `<button class="route-choice ${i===state.routeIndex?'selected':''}" data-route-index="${i}"><div class="route-card-top"><h3>${esc(r.title)}</h3><span class="route-risk ${level}">Rủi ro ${r.max_risk}/100</span></div><strong>${Math.ceil(r.eta_minutes)}<small>phút</small></strong><span class="data-label">${r.distance_km} km</span><p>${esc(r.steps.join(' → '))}</p><p>${r.warnings.length?'Có '+r.warnings.length+' đoạn cần lưu ý':'Không đi qua sự kiện đang hiển thị'}</p></button>`;}).join('')+`<div class="route-start-box"><div class="route-start-summary"><span>Tuyến đang chọn</span><strong>${esc(result.routes[state.routeIndex].title)} · ${result.routes[state.routeIndex].max_risk}/100</strong></div><button class="button primary full" id="start-navigation">${icon('target')}Bắt đầu theo dõi hành trình</button></div><p class="route-timestamp" id="route-calculation-note">Tính lúc ${timeText(result.calculated_at)} · Loại ${result.excluded} đoạn đóng / thiếu dữ liệu.</p>`;
    const chosen=result.routes[state.routeIndex];for(const [i,r] of result.routes.entries())if(i!==state.routeIndex)L.polyline(r.coordinates,{color:'#adb7b4',weight:6,opacity:.75,dashArray:'7 6'}).addTo(routeLayer);L.polyline(chosen.coordinates,{color:'white',weight:10,opacity:.95}).addTo(routeLayer);const line=L.polyline(chosen.coordinates,{color:'#0c7665',weight:6,opacity:1}).addTo(routeLayer);for(const [coord,label] of [[chosen.coordinates[0],'A'],[chosen.coordinates.at(-1),'B']])L.marker(coord,{icon:L.divIcon({className:'event-marker',html:`<strong>${label}</strong>`,iconSize:[32,32]})}).addTo(routeLayer);map.fitBounds(line.getBounds(),{padding:[60,75],maxZoom:14});
  };

  function startTracking(){
    if(!state.routes?.routes?.length)return;tracking=true;const chosen=state.routes.routes[state.routeIndex];$('#route-form').hidden=true;$('#route-results').hidden=true;const panel=$('#route-panel');$('.panel-heading h2',panel).textContent='Theo dõi hành trình';$('.panel-heading p',panel).textContent='Cảnh báo rủi ro theo thời gian thực';panel.insertAdjacentHTML('beforeend',`<div class="tracking-ui" id="tracking-ui"><div class="tracking-alert">${icon('alert')}<span><strong>Phát hiện nguy cơ ngập phía trước</strong><br>Khoảng 650 m · hệ thống đề xuất chuẩn bị tuyến tránh.</span></div><div class="tracking-stats"><div><span>Còn lại</span><strong>${Math.ceil(chosen.eta_minutes)} phút</strong></div><div><span>Quãng đường</span><strong>${chosen.distance_km} km</strong></div><div><span>Rủi ro tuyến</span><strong>${chosen.max_risk}/100</strong></div><div><span>Tốc độ mô phỏng</span><strong>31 km/h</strong></div></div><div class="tracking-next"><div class="eyebrow teal-text">CHỈ DẪN TIẾP THEO</div><strong>300 m · Tiếp tục theo ${esc(chosen.steps[0]||'tuyến đã chọn')}</strong><p>Sau đó chú ý cảnh báo ngập và làm theo đề xuất đổi tuyến nếu cần.</p></div><div class="tracking-actions"><button class="button secondary" id="reroute-safe">${icon('route')}Tìm đường tránh</button><button class="button primary" id="stop-navigation">Kết thúc theo dõi</button></div></div>`);
    ensureGroups();trackingLayer.clearLayers();const mid=chosen.coordinates[Math.min(1,chosen.coordinates.length-1)];L.marker(mid,{icon:L.divIcon({className:'',html:'<div class="user-route-dot"></div>',iconSize:[23,23],iconAnchor:[11,11]})}).addTo(trackingLayer);const mapSurface=$('.map-surface');mapSurface.insertAdjacentHTML('beforeend',`<div class="journey-banner" id="journey-banner">${icon('alert')} Nguy cơ ngập phía trước khoảng 650 m · Có thể đổi tuyến an toàn hơn</div>`);$('#alert-text').textContent='Đang theo dõi hành trình: có cảnh báo ngập phía trước. Bạn có thể tìm đường tránh ngay.';$('#alert-banner').hidden=false;toast('Đã bật chế độ theo dõi hành trình.');
  }
  function stopTracking(){tracking=false;$('#tracking-ui')?.remove();$('#journey-banner')?.remove();$('#route-form').hidden=false;$('#route-results').hidden=false;trackingLayer?.clearLayers();const panel=$('#route-panel');$('.panel-heading h2',panel).textContent='Hành trình của bạn';$('.panel-heading p',panel).textContent='Tìm tuyến trên mạng đường thử nghiệm';renderRoutes();}
  function rerouteSafe(){if(!state.routes)return;let best=0;state.routes.routes.forEach((r,i)=>{if(r.max_risk<state.routes.routes[best].max_risk)best=i;});state.routeIndex=best;stopTracking();renderRoutes();startTracking();toast('Đã chuyển sang tuyến có chỉ số rủi ro thấp nhất trong các tuyến hiện có.');}

  const baseDetail=showRoadDetails;
  showRoadDetails=function(id,event=null){
    const r=state.data.roads.find(r=>r.id===id);if(!r)return;const f=r.forecast[2];const confidence=event?.status==='pending'?42:event?.origin==='local_report'?94:91;const sources=event?.sources||r.sources;const evidence=event?.evidence||r.evidence;
    $('#detail-content').innerHTML=`<div class="dialog-heading"><div><div class="eyebrow teal-text">${event?.status==='pending'?'PHẢN ÁNH CHỜ XÁC MINH':'CHI TIẾT ĐOẠN ĐƯỜNG'}</div><h2>${esc(event?.name||r.name)}</h2></div><button class="icon-button close-dialog" aria-label="Đóng chi tiết">${icon('close')}</button></div><span class="tag tag-${event?.status==='pending'?'gray':'teal'}">${event?.status==='pending'?'Chưa ảnh hưởng định tuyến':r.blocked?'Rủi ro cao · đang hạn chế':'Đang được theo dõi'}</span><div class="detail-stats"><div><span>Tốc độ hiện tại</span><strong>${r.known?r.speed+' km/h':'Chưa rõ'}</strong></div><div><span>Nguy cơ ngập +30p</span><strong>${f.flood_risk==null?'Chưa rõ':f.flood_risk+'/100'}</strong></div><div><span>Độ sâu mô phỏng</span><strong>${r.depth?Math.round(r.depth)+' cm':'—'}</strong></div></div><p class="data-label">${esc(sources.join(' · '))} · ${timeText(event?.updated_at||r.updated_at)}</p><div class="detail-evidence">${esc(evidence.join('\n'))}</div><div class="confidence-block"><div class="confidence-head"><span>Độ tin cậy cảnh báo</span><strong>${confidence}%</strong></div><div class="confidence-track"><i style="width:${confidence}%"></i></div><div class="confidence-sources"><div class="confidence-source"><strong>✓ Mô hình VietSafe</strong>Dữ liệu hiện trạng + dự báo</div><div class="confidence-source"><strong>✓ Dữ liệu mưa</strong>Kịch bản ${state.data.rainfall} mm/h</div><div class="confidence-source"><strong>✓ Camera / IoT</strong>Nguồn bổ sung</div><div class="confidence-source"><strong>${event?.status==='pending'?'○':'✓'} Cộng đồng</strong>${event?.status==='pending'?'Chờ xác minh':'Đã tổng hợp bằng chứng'}</div></div></div><p class="muted">Độ tin cậy và các nguồn Camera/IoT hiện là dữ liệu mô phỏng; không dùng để quyết định đi qua vùng ngập thực tế.</p><div class="dialog-footer three-actions"><button class="button secondary" data-focus-road="${r.id}">${icon('pin')}Xem trên bản đồ</button><button class="button danger-action" data-avoid-road="${r.id}">${icon('route')}Tìm đường tránh</button><button class="button primary" data-forecast-detail="${r.id}">Xem dự báo ${icon('arrow')}</button></div>`;if(!$('#detail-dialog').open)$('#detail-dialog').showModal();
  };

  const baseRenderMap=renderMap;
  renderMap=function(){baseRenderMap();renderPrototypeLayers();};

  // Never substitute a demo coordinate for the user's real location.
  geolocate=function(forReport=false){
    if(!navigator.geolocation){toast('Trình duyệt không hỗ trợ định vị GPS.');return;}
    toast('Đang lấy vị trí GPS chính xác. Hãy bật dịch vụ định vị và cho phép trình duyệt truy cập vị trí.');
    navigator.geolocation.getCurrentPosition(position=>{
      const {latitude:lat,longitude:lng,accuracy}=position.coords;
      if(forReport&&(lat<20.98||lat>21.065||lng<105.77||lng>105.88)){
        toast('GPS thật nằm ngoài vùng phản ánh thử nghiệm Hà Nội. Chưa đặt vị trí; hãy chọn ghim trong vùng được hỗ trợ.');
        return;
      }
      if(!forReport&&(lat<MAP_BOUNDS[0][0]||lat>MAP_BOUNDS[1][0]||lng<MAP_BOUNDS[0][1]||lng>MAP_BOUNDS[1][1])){
        toast('GPS thật nằm ngoài phạm vi bản đồ Hà Nội–Bắc Ninh. Không thay bằng vị trí mô phỏng.');
        return;
      }
      if(forReport){
        setReportPosition(lat,lng,'Vị trí GPS của tôi');
        toast(`Đã lấy GPS: sai số khoảng ${Math.round(accuracy)} m.`);
        return;
      }
      nearbyKm=3;
      state.locationFocus={lat,lng,radiusKm:nearbyKm,accuracy};
      $('#map-region').value='gps';
      $$('.nearby-radius button').forEach(button=>button.classList.toggle('active',Number(button.dataset.radius)===nearbyKm));
      const closest=visibleModelRoads().map(road=>({road,distance:distanceToRoadKm([lat,lng],road)})).sort((a,b)=>a.distance-b.distance)[0];
      if(closest&&closest.distance<=nearbyKm){
        state.selected=closest.road.id;
        $('#forecast-road').value=state.selected;
      }
      renderInsight();
      renderForecast();
      map.setView([lat,lng],16);
      selectionLayer.clearLayers();
      L.circle([lat,lng],{radius:accuracy,color:'#087f72',weight:1,fillColor:'#087f72',fillOpacity:.12}).addTo(selectionLayer);
      gpsLocationMarker=L.circleMarker([lat,lng],{radius:7,color:'#087f72',weight:3,fillColor:'#fff',fillOpacity:1}).addTo(selectionLayer)
        .bindTooltip(`Vị trí GPS · sai số khoảng ${Math.round(accuracy)} m`,{direction:'top'});
      renderGpmSummary();
      loadGpmRainfall();
      renderMap();
      renderEvents();
      toast(closest&&closest.distance<=nearbyKm
        ?`Đã hiển thị mô hình ${visibleModelRoads().length} tuyến quanh GPS · sai số vị trí ${Math.round(accuracy)} m.`
        :'Đã hiển thị GPS thật. Khu vực này chưa có tuyến trong mô hình thử nghiệm; nền OpenStreetMap vẫn hiển thị.');
    },error=>{
      const message=error.code===1?'Bạn chưa cấp quyền định vị.':error.code===2?'Thiết bị chưa xác định được vị trí.':'Hết thời gian chờ GPS.';
      toast(`${message} Không dùng vị trí mô phỏng. Hãy thử lại ngoài trời hoặc đặt ghim thủ công.`);
    },{enableHighAccuracy:true,timeout:20000,maximumAge:0});
  };

  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.id==='start-navigation')startTracking();
    if(b.id==='stop-navigation')stopTracking();
    if(b.id==='reroute-safe')rerouteSafe();
    if(b.dataset.avoidRoad){$('#detail-dialog').close();setView('map');openRoute();toast('Đã mở tìm tuyến. Bật “Tránh khu vực nguy cơ ngập cao” để ưu tiên đi vòng đoạn cảnh báo.');}
    if(b.dataset.sos==='rescue'){$('#sos-dialog')?.close();setView('rescue');}
    if(b.dataset.sos==='medical'){toast('Trong tình huống thực tế: gọi 115 để cấp cứu y tế.');}
    if(b.dataset.sos==='police'){toast('Trong tình huống thực tế: gọi 113 để liên hệ công an.');}
    if(b.dataset.sos==='share'){navigator.clipboard?.writeText('21.0287, 105.8342');toast('Đã sao chép tọa độ mô phỏng: 21.0287, 105.8342');}
  });

  // Đánh dấu bản giao diện đã tích hợp tính năng nâng cấp.
  $('.demo-chip')?.insertAdjacentHTML('afterend','<span class="prototype-badge">Bản đồ nâng cấp + T-GCN</span>');
  addTimeline();addLayerOptions();addSOS();addNearbyControl();addRouteOptions();ensureGroups();
  $('#close-route')?.addEventListener('click',()=>{if(tracking)stopTracking();});
  // chờ snapshot đầu tiên tải xong rồi render lớp phụ.
  const wait=setInterval(()=>{if(state.data){clearInterval(wait);renderPrototypeLayers();renderEvents();}},60);
})();
