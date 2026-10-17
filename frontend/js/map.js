/** Bản đồ Leaflet: khởi tạo, nền (tile), các lớp (layer) và vẽ đoạn đường / sự kiện. */
import {
  FOOTNOTE_OFFLINE,
  FOOTNOTE_ONLINE,
  HANOI_BOUNDS,
  TILE_ORDER,
  TILE_PROVIDERS,
  typeIcons,
  typeNames,
} from "./config.js";
import { state } from "./state.js";
import { $, esc, icon, toast } from "./utils.js";
import { showEvent } from "./views/events-panel.js";
import { finishPick } from "./views/report-form.js";
import { selectRoad } from "./views/road-details.js";

/*
 * Các biến dưới đây được gán trong initializeMap(). Module khác chỉ ĐỌC chúng
 * (import <class 'map'> ...) - ES module cho phép đọc giá trị mới nhất ("live binding").
 */
export let map,
  baseTiles,
  roadLayer,
  eventLayer,
  routeLayer,
  selectionLayer,
  placeLayer;
let geographyLayer;
let majorRoadLines = {};
let tileErrorCount = 0;
let tileProviderIndex = 0;
let maptilerKey = "";
let lastRenderKey = "";

function nextTileProvider(after) {
  for (let i = after + 1; i < TILE_ORDER.length; i++) {
    if (
      TILE_ORDER[i] === "openfreemap" &&
      (!window.VietSafeVectorMaps || !window.WebGL2RenderingContext)
    )
      continue;
    if (TILE_ORDER[i] === "openmaptiles" && !maptilerKey) continue;
    return i;
  }
  return -1;
}

function buildTileLayer(key) {
  const cfg = TILE_PROVIDERS[key];
  if (key === "openfreemap") {
    return window.VietSafeVectorMaps.maplibreGL({
      style: cfg.style,
      interactive: false,
      attributionControl: { customAttribution: cfg.attr },
    });
  }
  const url =
    key === "openmaptiles"
      ? cfg.url.replace("{key}", encodeURIComponent(maptilerKey))
      : cfg.url;
  const layer = L.tileLayer(url, {
    maxZoom: cfg.maxZoom,
    attribution: cfg.attr,
  });
  layer.on("tileerror", () => {
    if (++tileErrorCount >= 6 && map.hasLayer(layer)) switchTileProvider();
  });
  return layer;
}

function addBaseLayer() {
  try {
    baseTiles.addTo(map);
  } catch (error) {
    if (TILE_ORDER[tileProviderIndex] !== "openfreemap") throw error;
    switchTileProvider();
    return;
  }
  map
    .getContainer()
    .classList.toggle(
      "map-vector",
      TILE_ORDER[tileProviderIndex] === "openfreemap",
    );
  if (TILE_ORDER[tileProviderIndex] !== "openfreemap") return;
  const layer = baseTiles;
  const gl = layer.getMaplibreMap();
  let loaded = false;
  const timeout = setTimeout(() => {
    if (!loaded && map.hasLayer(layer)) switchTileProvider();
  }, 10000);
  gl.once("load", () => {
    loaded = true;
    clearTimeout(timeout);
    for (const id of [
      "label_city",
      "label_city_capital",
      "label_town",
      "water_name_point_label",
      "water_name_line_label",
    ]) {
      if (gl.getLayer(id))
        gl.setLayoutProperty(id, "text-field", [
          "coalesce",
          ["get", "name:vi"],
          ["get", "name"],
          ["get", "name_en"],
        ]);
    }
  });
  gl.on("error", () => {
    if (!loaded && map.hasLayer(layer)) {
      clearTimeout(timeout);
      switchTileProvider();
    }
  });
}

// Hết nhà cung cấp tile thì rơi xuống sơ đồ ngoại tuyến (nền lưới CSS + hồ vẽ tay).
function switchTileProvider() {
  map.removeLayer(baseTiles);
  tileErrorCount = 0;
  const next = nextTileProvider(tileProviderIndex);
  if (next !== -1) {
    tileProviderIndex = next;
    baseTiles = buildTileLayer(TILE_ORDER[tileProviderIndex]);
    addBaseLayer();
    return;
  }
  tileProviderIndex = nextTileProvider(-1);
  baseTiles = buildTileLayer(TILE_ORDER[tileProviderIndex]);
  setBaseTiles(false);
  $("#base-tiles").checked = false;
  toast("Không tải được bản đồ nền. Đang hiển thị sơ đồ ngoại tuyến.");
}

export function setBaseTiles(on) {
  if (on) {
    if (!map.hasLayer(baseTiles)) {
      tileErrorCount = 0;
      addBaseLayer();
    }
    map.removeLayer(geographyLayer);
    $("#map-footnote").textContent = FOOTNOTE_ONLINE;
  } else {
    if (map.hasLayer(baseTiles)) map.removeLayer(baseTiles);
    map.getContainer().classList.remove("map-vector");
    geographyLayer.addTo(map);
    $("#map-footnote").textContent = FOOTNOTE_OFFLINE;
  }
}

export function initializeMap(key = "") {
  maptilerKey = key;
  tileProviderIndex = nextTileProvider(-1);
  map = L.map("map", {
    zoomControl: false,
    minZoom: 9,
    maxZoom: 18,
    maxBounds: HANOI_BOUNDS,
    maxBoundsViscosity: 1,
  }).setView([21.02, 105.79], 10);
  const syncLabelVisibility = () =>
    map.getContainer().classList.toggle("map-wide", map.getZoom() < 12);
  map.on("zoomend", syncLabelVisibility);
  syncLabelVisibility();
  L.control.zoom({ position: "bottomright" }).addTo(map);
  baseTiles = buildTileLayer(TILE_ORDER[tileProviderIndex]);
  addBaseLayer();
  // Hồ vẽ tay chỉ dùng cho sơ đồ ngoại tuyến; trên nền tile thật hồ đã được vẽ đúng hình.
  geographyLayer = L.layerGroup();
  const lakes = [
    [
      "Hồ Tây",
      [
        [21.043, 105.825],
        [21.048, 105.817],
        [21.058, 105.812],
        [21.07, 105.819],
        [21.073, 105.835],
        [21.06, 105.842],
        [21.048, 105.839],
      ],
    ],
    [
      "Hồ Hoàn Kiếm",
      [
        [21.0313, 105.852],
        [21.03, 105.8537],
        [21.026, 105.8537],
        [21.0252, 105.8518],
        [21.028, 105.8509],
      ],
    ],
    [
      "Hồ Bảy Mẫu",
      [
        [21.0135, 105.8443],
        [21.0134, 105.847],
        [21.009, 105.8477],
        [21.0074, 105.846],
        [21.008, 105.8444],
      ],
    ],
    [
      "Hồ Thủ Lệ",
      [
        [21.0335, 105.8006],
        [21.0339, 105.806],
        [21.0308, 105.8078],
        [21.03, 105.8028],
      ],
    ],
  ];
  for (const [name, shape] of lakes)
    L.polygon(shape, {
      color: "#b7d1d0",
      fillColor: "#c7dddd",
      fillOpacity: 0.8,
      weight: 1,
      interactive: false,
    })
      .addTo(geographyLayer)
      .bindTooltip(name, {
        permanent: true,
        direction: "center",
        className: "water-label",
      });
  placeLayer = L.layerGroup().addTo(map);
  map.createPane("majorRoadPane");
  map.getPane("majorRoadPane").style.zIndex = 390;
  roadLayer = L.layerGroup().addTo(map);
  routeLayer = L.layerGroup().addTo(map);
  eventLayer = L.layerGroup().addTo(map);
  selectionLayer = L.layerGroup().addTo(map);
  map.on("click", (e) => {
    if (state.picking) finishPick(e.latlng.lat, e.latlng.lng);
    else if (state.routePicking)
      window.dispatchEvent(
        new CustomEvent("route-point-picked", {
          detail: { lat: e.latlng.lat, lng: e.latlng.lng },
        }),
      );
  });
  map.on("movestart", () => ($("#search-results").hidden = true));
  map.on("zoomend", syncMajorRoads);
  map.on("moveend", () => {
    if (state.data) renderMap();
  });
  fetch("/api/major-roads")
    .then((response) =>
      response.ok
        ? response.json()
        : Promise.reject(new Error("major roads unavailable")),
    )
    .then((data) => {
      for (const [kind, shapes] of Object.entries(data.classes))
        majorRoadLines[kind] = L.polyline(shapes, {
          pane: "majorRoadPane",
          color: "#667783",
          weight:
            kind === "motorway" || kind === "trunk"
              ? 2.5
              : kind === "tertiary"
                ? 1.4
                : 1.8,
          opacity: 0.4,
          interactive: false,
          smoothFactor: 1.5,
        });
      syncMajorRoads();
    })
    .catch(() => {
      $("#major-roads").disabled = true;
    });
}

export function syncMajorRoads() {
  const minimumZoom = {
    motorway: 9,
    trunk: 9,
    primary: 9,
    secondary: 11,
    tertiary: 13,
  };
  for (const [kind, line] of Object.entries(majorRoadLines)) {
    const visible =
      state.layers.majorRoads && map.getZoom() >= minimumZoom[kind];
    line.setStyle({
      opacity: kind === "tertiary" ? 0.34 : map.getZoom() >= 11 ? 0.56 : 0.4,
    });
    if (visible && !map.hasLayer(line)) line.addTo(map);
    if (!visible && map.hasLayer(line)) map.removeLayer(line);
  }
}

export function roadColor(r) {
  if (!r.known) return "#aab5af";
  if (state.horizon) {
    const risk = r.forecast[state.horizon / 15].risk;
    return risk >= 65 ? "#cf5149" : risk >= 35 ? "#cc8a2b" : "#288d6d";
  }
  if (r.blocked) return "#cf5149";
  if (r.event_type && state.layers[r.event_type])
    return { flood: "#347ec5", traffic: "#cc8a2b", incident: "#cf5149" }[
      r.event_type
    ];
  return "#288d6d";
}

export function renderMap() {
  if (!state.data) return;
  const bounds = (
    map.getSize().x && map.getSize().y
      ? map.getBounds()
      : L.latLngBounds(HANOI_BOUNDS)
  ).pad(0.12);
  const key = [
    state.data.scenario,
    state.data.roads[0]?.simulated_timestamp,
    state.data.events
      .map((event) => `${event.id}:${event.updated_at}`)
      .join("|"),
    state.horizon,
    state.selected,
    map.getZoom(),
    Math.round(bounds.getCenter().lat * 200),
    Math.round(bounds.getCenter().lng * 200),
    JSON.stringify(state.layers),
    map.getContainer().classList.contains("route-active"),
  ].join(":");
  if (key === lastRenderKey) return;
  lastRenderKey = key;
  roadLayer.clearLayers();
  eventLayer.clearLayers();
  for (const r of state.data.roads) {
    if (
      !state.layers.demoRoads ||
      !bounds.intersects(L.latLngBounds(r.coordinates))
    )
      continue;
    if (
      map.getContainer().classList.contains("route-active") &&
      !r.event_type &&
      r.id !== state.selected
    )
      continue;
    if (map.getZoom() < 12 && r.id !== state.selected && !r.event_type)
      continue;
    const f = r.forecast[state.horizon / 15];
    const color = roadColor(r),
      weight = r.id === state.selected ? 6 : 4;
    L.polyline(r.coordinates, {
      color: "#fff",
      weight: weight + 3,
      opacity: 0.94,
      interactive: false,
    }).addTo(roadLayer);
    const line = L.polyline(r.coordinates, {
      color,
      weight,
      opacity: 0.98,
      dashArray: r.known ? null : "5 6",
    }).addTo(roadLayer);
    line.bindTooltip(
      `<strong>${esc(r.name)}</strong><br>${!r.known ? "Chưa đủ dữ liệu" : state.horizon ? `Dự báo +${state.horizon} phút · Nguy cơ ${f.risk}/100` : `${r.speed} km/h · ${r.blocked ? "Đóng trong kịch bản" : "Dữ liệu thử nghiệm"}`}`,
    );
    line.on("click", (e) => {
      L.DomEvent.stopPropagation(e);
      if (state.picking) finishPick(e.latlng.lat, e.latlng.lng);
      else if (state.routePicking)
        window.dispatchEvent(
          new CustomEvent("route-point-picked", {
            detail: { lat: e.latlng.lat, lng: e.latlng.lng },
          }),
        );
      else selectRoad(r.id, true);
    });
  }
  const markers = [];
  if (!state.horizon)
    for (const e of state.data.events) {
      if (
        !state.layers[e.type] ||
        (e.status === "pending" && !state.layers.pending)
      )
        continue;
      if (!bounds.contains([e.lat, e.lng])) continue;
      markers.push({
        lat: e.lat,
        lng: e.lng,
        type: e.type,
        title: `${typeNames[e.type]}: ${e.name}`,
        tooltip: `${esc(e.name)} · ${e.status === "pending" ? "Chờ xác minh" : typeNames[e.type]}`,
        pending: e.status === "pending",
        click: () =>
          state.picking ? finishPick(e.lat, e.lng) : showEvent(e.id),
      });
    }
  else
    for (const r of state.data.roads) {
      if (!r.known || !bounds.contains(r.center)) continue;
      const predicted = r.forecast[state.horizon / 15];
      const [type, score] = [
        ["flood", predicted.flood_risk],
        ["traffic", predicted.traffic_risk],
        ["incident", predicted.incident_risk],
      ].reduce((best, item) => (item[1] > best[1] ? item : best));
      if (score < 65 || !state.layers[type]) continue;
      const [lat, lng] = r.center;
      markers.push({
        lat,
        lng,
        type,
        title: `${typeNames[type]} · dự báo +${state.horizon} phút`,
        tooltip: `${esc(r.name)} · ${typeNames[type]} ${score}/100 (mô phỏng)`,
        click: () =>
          state.picking ? finishPick(lat, lng) : selectRoad(r.id, true),
      });
    }
  const groups = new Map();
  for (const item of markers) {
    const p = map.latLngToContainerPoint([item.lat, item.lng]);
    const key =
      map.getZoom() < 13
        ? `${Math.floor(p.x / 54)}:${Math.floor(p.y / 54)}`
        : `${item.lat}:${item.lng}:${item.title}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  for (const group of groups.values()) {
    if (group.length > 1 && map.getZoom() < 13) {
      const lat = group.reduce((sum, item) => sum + item.lat, 0) / group.length;
      const lng = group.reduce((sum, item) => sum + item.lng, 0) / group.length;
      const cluster = L.marker([lat, lng], {
        icon: L.divIcon({
          className: "",
          html: `<span class="event-cluster">${group.length}</span>`,
          iconSize: [35, 35],
        }),
        title: `${group.length} cảnh báo mô phỏng`,
      }).addTo(eventLayer);
      cluster.on("click", () =>
        map.setView([lat, lng], Math.min(15, map.getZoom() + 2)),
      );
      continue;
    }
    const e = group[0];
    const marker = L.marker([e.lat, e.lng], {
      icon: L.divIcon({
        className: `event-marker ${e.type} ${e.pending ? "pending" : ""}`,
        html: icon(typeIcons[e.type]),
        iconSize: [32, 32],
      }),
      title: e.title,
    }).addTo(eventLayer);
    marker.bindTooltip(e.tooltip);
    marker.on("click", () => {
      if (state.routePicking)
        window.dispatchEvent(
          new CustomEvent("route-point-picked", {
            detail: { lat: e.lat, lng: e.lng },
          }),
        );
      else e.click();
    });
  }
  $("#map-mode-label").hidden = !state.horizon;
  $("#map-mode-label").textContent =
    `Dự báo +${state.horizon} phút · Nguy cơ thấp → trung bình → cao`;
  $(".map-legend").innerHTML = state.horizon
    ? '<span><i class="legend-dot green"></i>Thấp &lt;35</span><span><i class="legend-dot orange-bg"></i>Trung bình 35–64</span><span><i class="legend-dot red-bg"></i>Cao ≥65</span><span><i class="legend-dot gray-bg"></i>Chưa đủ dữ liệu</span><span><i class="legend-line"></i>Đường chính OSM</span>'
    : '<span><i class="legend-dot green"></i>Thông thoáng</span><span><i class="legend-dot orange-bg"></i>Ùn tắc</span><span><i class="legend-dot blue-bg"></i>Ngập</span><span><i class="legend-dot red-bg"></i>Sự cố / đóng</span><span><i class="legend-dot gray-bg"></i>Chưa có dữ liệu</span><span><i class="legend-line"></i>Đường chính OSM</span>';
}
