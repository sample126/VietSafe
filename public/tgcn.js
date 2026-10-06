'use strict';
(function(){
  let tgcnLayer=null;
  let tgcnEnabled=true;
  let autoReroute=true;
  let simulatedShock=0;
  let lastAutoReroute=0;

  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const avg=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:0;
  const horizonIndex=h=>clamp(Math.round(Number(h||0)/15),0,4);
  const dist2=(a,b)=>{const dy=(a[0]-b[0])*111;const dx=(a[1]-b[1])*111*Math.cos((a[0]+b[0])*.5*Math.PI/180);return Math.hypot(dx,dy)};
  const midpointRoad=r=>r.coordinates[Math.floor(r.coordinates.length/2)];

  function neighborsOf(road){
    if(!state.data?.roads)return [];
    return state.data.roads.filter(x=>x.id!==road.id&&(x.a===road.a||x.a===road.b||x.b===road.a||x.b===road.b));
  }

  // Mô phỏng đầu ra T-GCN: thành phần thời gian (forecast hiện có) + lân cận đồ thị + mưa/ngập.
  // Đây là prototype UI, không phải trọng số của mô hình T-GCN đã huấn luyện.
  function predictRoad(road,horizon=30){
    const idx=horizonIndex(horizon);
    const base=road.forecast?.[idx]||road.forecast?.at(-1)||{};
    if(!road.known) return {speed:null,trafficRisk:55,floodRisk:base.flood_risk??road.flood_risk??0,risk:60,confidence:45,trend:'Chưa đủ dữ liệu'};
    const ns=neighborsOf(road).filter(x=>x.known);
    const nSpeeds=ns.map(n=>(n.forecast?.[idx]?.speed??n.speed)).filter(Number.isFinite);
    const neighborSpeed=nSpeeds.length?avg(nSpeeds):road.speed;
    const temporal=Number.isFinite(base.speed)?base.speed:road.speed;
    const rain=Number(state.data?.rainfall||0);
    const flood=Number(base.flood_risk??road.flood_risk??0);
    const rainPenalty=Math.min(10,rain*(road.susceptibility||.2)*.11);
    const shockPenalty=simulatedShock*(.55+(road.susceptibility||.2));
    let speed=.64*temporal+.24*neighborSpeed+.12*road.speed-rainPenalty-shockPenalty;
    if(road.incident)speed*=.76;
    if(road.blocked)speed=Math.min(speed,3);
    speed=clamp(speed,0,road.free_speed||45);
    const ratio=(road.free_speed||35)>0?speed/(road.free_speed||35):.5;
    const trafficRisk=clamp(Math.round((1-ratio)*92+(road.incident?18:0)+simulatedShock*2.2),0,100);
    const modelRisk=Math.round(.62*trafficRisk+.25*flood+(road.incident?12:0)+(road.blocked?30:0));const risk=clamp(Math.max(Number(base.risk||0),modelRisk),0,100);
    const confidence=clamp(Math.round(78+Math.min(12,ns.length*3)-(road.origin==='demo'?3:0)-(horizon/60)*8),55,96);
    const delta=speed-road.speed;
    const trend=delta<-5?'Giảm mạnh':delta<-1.5?'Giảm':delta>3?'Tăng':'Ổn định';
    return {speed:+speed.toFixed(1),trafficRisk,floodRisk:flood,risk,confidence,trend,neighborCount:ns.length};
  }

  function allPredictions(horizon){
    return (state.data?.roads||[]).map(r=>({road:r,...predictRoad(r,horizon)}));
  }

  function riskClass(r){return r>=65?'high':r>=35?'mid':'low'}
  function riskColor(r){return r>=65?'#d45e55':r>=35?'#e2a341':'#3f9a78'}

  function ensureTgcnOverview(){
    if($('#tgcn-overview'))return;
    const stats=$('#map-view .stats');if(!stats)return;
    stats.insertAdjacentHTML('afterend',`<section class="tgcn-overview" id="tgcn-overview">
      <div class="tgcn-main"><div class="tgcn-ai-icon">T-GCN</div><div><strong>Dự báo giao thông AI <span class="tgcn-live">THỬ NGHIỆM</span></strong><p>Học quan hệ giữa các đoạn đường + biến động theo thời gian để dự báo tốc độ và ùn tắc 15/30/60 phút.</p></div><button class="tgcn-open" id="tgcn-open-model">Chi tiết mô hình →</button></div>
      <div class="tgcn-kpi"><span>Điểm nóng +30p</span><strong id="tgcn-hotspots">—</strong><small>đoạn có rủi ro ≥ 65</small></div>
      <div class="tgcn-kpi"><span>Tốc độ TB +30p</span><strong id="tgcn-avg-speed">—</strong><small>km/h · trên đoạn có dữ liệu</small></div>
      <div class="tgcn-kpi"><span>Độ tin cậy TB</span><strong id="tgcn-confidence">—</strong><small>ước lượng thử nghiệm</small></div>
    </section>`);
    const title=$('.map-title');if(title&&!$('#tgcn-map-toggle'))title.insertAdjacentHTML('beforeend','<button id="tgcn-map-toggle" class="tgcn-map-chip" title="Bật/tắt lớp dự báo T-GCN">T-GCN ON</button>');
    const menu=$('#layer-menu');if(menu&&!menu.querySelector('[data-proto-layer="tgcn"]')){
      const small=menu.querySelector('small');small?.insertAdjacentHTML('beforebegin','<label class="new-layer-label"><input type="checkbox" data-proto-layer="tgcn" checked><i class="layer-swatch" style="background:#087f72"></i>Dự báo T-GCN <span>AI</span></label>');
      menu.querySelector('[data-proto-layer="tgcn"]')?.addEventListener('change',e=>{tgcnEnabled=e.target.checked;syncTgcnToggle();renderTgcnLayer();});
    }
    $('.map-surface')?.insertAdjacentHTML('beforeend','<div class="tgcn-overlay-legend" id="tgcn-overlay-legend"><i></i><span>T-GCN: tốc độ/rủi ro dự báo</span></div>');
  }

  function ensureModelDialog(){
    if($('#tgcn-model-dialog'))return;
    document.body.insertAdjacentHTML('beforeend',`<dialog id="tgcn-model-dialog" class="tgcn-model-dialog"><div class="dialog-heading"><div><div class="eyebrow teal-text">TEMPORAL GRAPH CONVOLUTIONAL NETWORK</div><h2>T-GCN · Dự báo giao thông VietSafe</h2></div><button class="icon-button close-dialog" aria-label="Đóng">${icon('close')}</button></div><p class="dialog-intro">Màn hình này mô phỏng cách T-GCN sẽ được tích hợp. Chỉ số đánh giá bên dưới là dữ liệu prototype, chưa phải kết quả huấn luyện thực tế.</p><div class="tgcn-dialog-grid"><div class="tgcn-box"><h3>Luồng dữ liệu mô hình</h3><div class="tgcn-arch"><span>Graph đường Hà Nội</span><i>→</i><span>GCN không gian</span><i>→</i><span>GRU thời gian</span><i>→</i><span>Speed + Congestion Risk</span></div><div class="tgcn-inputs"><span>Tốc độ</span><span>Đoạn lân cận</span><span>Lượng mưa</span><span>Nguy cơ ngập</span><span>Sự cố</span><span>Khung giờ</span></div></div><div class="tgcn-box"><h3>Đánh giá offline · thử nghiệm</h3><div class="tgcn-metrics"><div class="tgcn-metric"><span>MAE</span><strong>3.2</strong><small>km/h</small></div><div class="tgcn-metric"><span>RMSE</span><strong>4.7</strong><small>km/h</small></div><div class="tgcn-metric"><span>MAPE</span><strong>10.8%</strong><small>demo</small></div></div></div></div><div class="tgcn-box" style="margin-top:14px"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px"><h3 style="margin:0">Các đoạn có nguy cơ ùn tắc cao nhất</h3><button id="tgcn-simulate-shock" class="tgcn-spike" style="width:auto;margin:0">Mô phỏng ùn tắc tăng +30p</button></div><table class="tgcn-table"><thead><tr><th>Đoạn đường</th><th>+30p</th><th>Tốc độ</th><th>Rủi ro</th><th>Tin cậy</th></tr></thead><tbody id="tgcn-top-table"></tbody></table></div><div class="dialog-footer"><span>Chế độ thử nghiệm · cần model T-GCN đã huấn luyện để sử dụng dự báo thực tế.</span><button class="button primary close-dialog">Đóng</button></div></dialog>`);
  }

  function ensureForecastPanel(){
    const view=$('#forecast-view');if(!view||$('#tgcn-forecast-panel'))return;
    view.insertAdjacentHTML('beforeend',`<section class="tgcn-forecast-panel" id="tgcn-forecast-panel"><div class="tgcn-forecast-head"><div><div class="eyebrow teal-text">AI TRAFFIC FORECAST</div><h2>Dự báo T-GCN theo đoạn đường</h2><p>So sánh biến động tốc độ và nguy cơ ùn tắc trong 60 phút tới.</p></div><span class="tgcn-status">T-GCN thử nghiệm</span></div><div class="tgcn-forecast-grid" id="tgcn-forecast-grid"></div><div class="tgcn-inputs"><span>Speed(t)</span><span>Graph neighbors</span><span>Rainfall</span><span>Flood risk</span><span>Incident</span><span>Time features</span></div></section>`);
  }

  function selectedForecastRoad(){
    const id=$('#forecast-road')?.value;
    return state.data?.roads?.find(r=>r.id===id)||state.data?.roads?.find(r=>r.known)||null;
  }

  function updateForecastPanel(){
    const road=selectedForecastRoad();const grid=$('#tgcn-forecast-grid');if(!road||!grid)return;
    grid.innerHTML=[15,30,60].map(h=>{const p=predictRoad(road,h);return `<article class="tgcn-horizon-card"><span class="h">+${h} phút · ${esc(road.name)}</span><strong>${p.speed==null?'—':p.speed+' km/h'}</strong><p>Nguy cơ ùn tắc: <b>${p.trafficRisk}/100</b> · ${p.trend}<br>Risk tổng hợp: <b>${p.risk}/100</b> · Tin cậy ${p.confidence}%</p><div class="tgcn-bar"><i style="width:${p.risk}%;background:${riskColor(p.risk)}"></i></div></article>`}).join('');
  }

  function updateTgcnOverview(){
    if(!state.data)return;
    const p=allPredictions(30).filter(x=>x.speed!=null);
    if(!p.length)return;
    $('#tgcn-hotspots').textContent=p.filter(x=>x.risk>=65).length;
    $('#tgcn-avg-speed').textContent=avg(p.map(x=>x.speed)).toFixed(1);
    $('#tgcn-confidence').textContent=Math.round(avg(p.map(x=>x.confidence)))+'%';
    const tbody=$('#tgcn-top-table');if(tbody){tbody.innerHTML=[...p].sort((a,b)=>b.risk-a.risk).slice(0,6).map(x=>`<tr><td><strong>${esc(x.road.name)}</strong></td><td>${x.trend}</td><td>${x.speed} km/h</td><td><span class="tgcn-risk-pill ${riskClass(x.risk)}">${x.risk}/100</span></td><td>${x.confidence}%</td></tr>`).join('');}
    updateForecastPanel();
  }

  function ensureTgcnLayer(){
    if(!map||tgcnLayer)return;
    tgcnLayer=L.layerGroup().addTo(map);
  }

  function syncTgcnToggle(){
    const b=$('#tgcn-map-toggle');if(b){b.textContent='T-GCN '+(tgcnEnabled?'ON':'OFF');b.classList.toggle('off',!tgcnEnabled)}
    const l=$('#tgcn-overlay-legend');if(l)l.hidden=!tgcnEnabled;
    const cb=$('#layer-menu [data-proto-layer="tgcn"]');if(cb)cb.checked=tgcnEnabled;
  }

  function renderTgcnLayer(){
    if(!state.data||!map)return;ensureTgcnLayer();tgcnLayer.clearLayers();syncTgcnToggle();if(!tgcnEnabled)return;
    const h=state.horizon||15;
    for(const r of state.data.roads){
      const p=predictRoad(r,h);if(p.speed==null)continue;
      const line=L.polyline(r.coordinates,{color:riskColor(p.risk),weight:3.5,opacity:.68,dashArray:h?null:'5 4',interactive:true}).addTo(tgcnLayer);
      line.bindTooltip(`<div class="tgcn-road-tooltip"><strong>${esc(r.name)} · T-GCN +${h||0}p</strong><div>Tốc độ dự báo: <b>${p.speed} km/h</b><br>Nguy cơ ùn tắc: <b>${p.trafficRisk}/100</b><br>Risk tổng hợp: <b>${p.risk}/100</b><br>Độ tin cậy: <b>${p.confidence}%</b></div></div>`,{sticky:true});
    }
  }

  function routeRoads(route){
    const roads=state.data?.roads||[];const found=[];
    for(const c of (route.coordinates||[])){
      let best=null,bd=Infinity;
      for(const r of roads){const d=dist2(c,midpointRoad(r));if(d<bd){bd=d;best=r}}
      if(best&&!found.some(x=>x.id===best.id))found.push(best);
    }
    return found;
  }

  function applyTgcnRoutes(){
    const rs=state.routes?.routes;if(!rs?.length||!state.data)return;
    const start=Number($('#route-time')?.value||0);const h=Math.max(15,start||30);
    for(const r of rs){
      if(r._tgcnSourceKey!==state.routes.calculated_at){r._tgcnBaseEta=r.eta_minutes;r._tgcnBaseRisk=r.max_risk;r._tgcnSourceKey=state.routes.calculated_at}
      const roads=routeRoads(r);const ps=roads.map(x=>predictRoad(x,h));
      const valid=ps.filter(x=>x.speed!=null);const trafficRisk=valid.length?Math.max(...valid.map(x=>x.trafficRisk)):r._tgcnBaseRisk;
      const predRisk=valid.length?Math.max(...valid.map(x=>x.risk)):r._tgcnBaseRisk;
      const predSpeed=valid.length?avg(valid.map(x=>x.speed)):25;
      const currentSpeed=roads.filter(x=>x.known).length?avg(roads.filter(x=>x.known).map(x=>x.speed)):predSpeed;
      const etaFactor=clamp(currentSpeed/Math.max(5,predSpeed),.85,1.45);
      r.tgcn_risk=clamp(Math.round(.7*predRisk+.3*r._tgcnBaseRisk),0,100);
      r.tgcn_traffic_risk=trafficRisk;r.tgcn_horizon=h;r.tgcn_speed=+predSpeed.toFixed(1);
      r.max_risk=Math.max(r._tgcnBaseRisk,r.tgcn_risk);
      r.eta_minutes=+(r._tgcnBaseEta*etaFactor).toFixed(1);
    }
    const priority=(document.querySelector('.route-priority button.active')?.dataset.priority)||'safe';
    rs.sort((a,b)=>priority==='fast'?(a.eta_minutes-b.eta_minutes)||((a.tgcn_risk||0)-(b.tgcn_risk||0)):priority==='balanced'?((a.eta_minutes*.8+(a.tgcn_risk||0)*.22)-(b.eta_minutes*.8+(b.tgcn_risk||0)*.22)):((a.tgcn_risk||0)-(b.tgcn_risk||0))||(a.eta_minutes-b.eta_minutes));
    state.routeIndex=clamp(state.routeIndex||0,0,rs.length-1);
  }

  function decorateRouteCards(){
    const rs=state.routes?.routes||[];
    $$('.route-choice').forEach((card,i)=>{const r=rs[i];if(!r||card.querySelector('.tgcn-route-line'))return;const p=card.querySelector('p:last-of-type');p?.insertAdjacentHTML('afterend',`<div class="tgcn-route-line"><span class="tgcn-badge-track">T-GCN +${r.tgcn_horizon||30}p</span><span>Tốc độ dự báo <b>${r.tgcn_speed??'—'} km/h</b> · ùn tắc <b>${r.tgcn_traffic_risk??'—'}/100</b></span></div>`)});
    const box=$('.route-start-box');if(box&&!$('#tgcn-auto-reroute'))box.insertAdjacentHTML('beforeend',`<label class="tgcn-auto"><input id="tgcn-auto-reroute" type="checkbox" ${autoReroute?'checked':''}><span><strong>Tự động đề xuất đổi tuyến bằng T-GCN</strong><br><small>Khi rủi ro dự báo tăng cao trên tuyến đang đi.</small></span></label>`);
    $('#tgcn-auto-reroute')?.addEventListener('change',e=>autoReroute=e.target.checked,{once:true});
  }

  function maybeDecorateTracking(){
    const ui=$('#tracking-ui');if(!ui)return;
    const chosen=state.routes?.routes?.[state.routeIndex];
    const alert=$('.tracking-alert',ui);if(alert&&chosen)alert.innerHTML=`${icon('alert')}<span><strong>T-GCN cảnh báo ùn tắc/ngập phía trước</strong><br>Risk dự báo +${chosen.tgcn_horizon||30} phút: ${chosen.tgcn_risk??chosen.max_risk}/100 · tốc độ tuyến khoảng ${chosen.tgcn_speed??'—'} km/h.</span>`;
    if(!ui.dataset.tgcn){ui.dataset.tgcn='1';ui.insertAdjacentHTML('beforeend','<button class="tgcn-spike" id="tgcn-trip-shock">Mô phỏng: giao thông xấu đi sau 30 phút</button>');}
  }

  function simulateShock(){
    simulatedShock=simulatedShock?0:8;
    updateTgcnOverview();renderTgcnLayer();
    const b=$('#tgcn-simulate-shock');if(b)b.textContent=simulatedShock?'Khôi phục giao thông bình thường':'Mô phỏng ùn tắc tăng +30p';
    const tb=$('#tgcn-trip-shock');if(tb)tb.textContent=simulatedShock?'Đã mô phỏng: ùn tắc tăng · T-GCN đang đánh giá lại':'Mô phỏng: giao thông xấu đi sau 30 phút';
    if(state.routes?.routes?.length){applyTgcnRoutes();const before=state.routeIndex;renderRoutes();decorateRouteCards();if($('#tracking-ui'))maybeDecorateTracking();
      const chosen=state.routes.routes[state.routeIndex];
      if(autoReroute&&simulatedShock&&chosen?.tgcn_risk>=60&&Date.now()-lastAutoReroute>2000){lastAutoReroute=Date.now();toast('T-GCN phát hiện rủi ro tuyến tăng. Đang chuyển sang tuyến an toàn hơn.');if($('#tracking-ui'))setTimeout(()=>$('#reroute-safe')?.click(),120);}
    }
    toast(simulatedShock?'Đã mô phỏng ùn tắc tăng. Dự báo T-GCN được tính lại.':'Đã khôi phục kịch bản T-GCN bình thường.');
  }

  function initTgcn(){
    ensureTgcnOverview();ensureModelDialog();ensureForecastPanel();ensureTgcnLayer();syncTgcnToggle();updateTgcnOverview();renderTgcnLayer();
    $('#tgcn-map-toggle')?.addEventListener('click',()=>{tgcnEnabled=!tgcnEnabled;renderTgcnLayer()});
    $('#tgcn-open-model')?.addEventListener('click',()=>{updateTgcnOverview();$('#tgcn-model-dialog').showModal()});
    $('#forecast-road')?.addEventListener('change',updateForecastPanel);
    $('#forecast-scenario')?.addEventListener('change',()=>setTimeout(updateForecastPanel,80));
  }

  const prevShowRoadDetailsTgcn=showRoadDetails;
  showRoadDetails=function(id,event=null){
    prevShowRoadDetailsTgcn(id,event);
    const r=state.data?.roads?.find(x=>x.id===id);const content=$('#detail-content');if(!r||!content)return;
    const p15=predictRoad(r,15),p30=predictRoad(r,30),p60=predictRoad(r,60);
    const target=content.querySelector('.muted')||content.querySelector('.dialog-footer');
    target?.insertAdjacentHTML('beforebegin',`<div class="tgcn-box" style="margin-top:13px"><div style="display:flex;align-items:center;justify-content:space-between;gap:8px"><h3 style="margin:0">T-GCN · Dự báo giao thông</h3><span class="tgcn-status">AI thử nghiệm</span></div><div class="tgcn-forecast-grid" style="margin-top:9px"><article class="tgcn-horizon-card"><span class="h">+15 phút</span><strong>${p15.speed??'—'}${p15.speed!=null?' km/h':''}</strong><p>Ùn tắc ${p15.trafficRisk}/100 · Risk ${p15.risk}/100</p></article><article class="tgcn-horizon-card"><span class="h">+30 phút</span><strong>${p30.speed??'—'}${p30.speed!=null?' km/h':''}</strong><p>Ùn tắc ${p30.trafficRisk}/100 · Risk ${p30.risk}/100</p></article><article class="tgcn-horizon-card"><span class="h">+60 phút</span><strong>${p60.speed??'—'}${p60.speed!=null?' km/h':''}</strong><p>Ùn tắc ${p60.trafficRisk}/100 · Risk ${p60.risk}/100</p></article></div><div class="tgcn-inputs"><span>${p30.neighborCount??0} đoạn lân cận</span><span>Mưa ${state.data.rainfall} mm/h</span><span>Tin cậy +30p ${p30.confidence}%</span></div></div>`);
  };

  // Gắn vào renderMap/renderRoutes hiện hữu để T-GCN thực sự cập nhật cùng timeline và tìm tuyến.
  const prevRenderMap=renderMap;
  renderMap=function(){prevRenderMap();updateTgcnOverview();renderTgcnLayer();};
  const prevRenderRoutes=renderRoutes;
  renderRoutes=function(){applyTgcnRoutes();prevRenderRoutes();decorateRouteCards();};

  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.id==='tgcn-simulate-shock'||b.id==='tgcn-trip-shock'){e.preventDefault();simulateShock();}
    if(b.id==='start-navigation')setTimeout(maybeDecorateTracking,0);
    if(b.dataset.routeIndex!=null)setTimeout(decorateRouteCards,0);
  });

  const wait=setInterval(()=>{if(typeof map!=='undefined'&&map&&typeof state!=='undefined'&&state.data){clearInterval(wait);initTgcn()}},80);
  setInterval(()=>{if(state?.data){updateTgcnOverview();if($('#tracking-ui'))maybeDecorateTracking()}},2500);
})();
