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
import { selectRoad } from "./views/road-details.js";
import { showEvent } from "./views/events-panel.js";
import { finishPick } from "./views/report-form.js";

/*
 * Các biến dưới đây được gán trong initializeMap(). Module khác chỉ ĐỌC chúng
 * (import <class 'map'> ...) - ES module cho phép đọc giá trị mới nhất ("live binding").
 */
export let map, baseTiles, roadLayer, eventLayer, routeLayer, selectionLayer, placeLayer;
let geographyLayer;
let tileErrorCount = 0;
let tileProviderIndex = 0;

function buildTileLayer(key) {
  const cfg = TILE_PROVIDERS[key];
  const layer = L.tileLayer(cfg.url, { maxZoom: cfg.maxZoom, attribution: cfg.attr });
  layer.on("tileerror", () => {
    if (++tileErrorCount >= 6 && map.hasLayer(layer)) switchTileProvider();
  });
  return layer;
}

// Hết nhà cung cấp tile thì rơi xuống sơ đồ ngoại tuyến (nền lưới CSS + hồ vẽ tay).
function switchTileProvider() {
  map.removeLayer(baseTiles);
  tileErrorCount = 0;
  if (++tileProviderIndex < TILE_ORDER.length) {
    baseTiles = buildTileLayer(TILE_ORDER[tileProviderIndex]);
    baseTiles.addTo(map);
    return;
  }
  tileProviderIndex = 0;
  baseTiles = buildTileLayer(TILE_ORDER[0]);
  setBaseTiles(false);
  $("#base-tiles").checked = false;
  toast("Không tải được bản đồ nền. Đang hiển thị sơ đồ ngoại tuyến.");
}

export function setBaseTiles(on) {
  if (on) {
    if (!map.hasLayer(baseTiles)) {
      tileErrorCount = 0;
      baseTiles.addTo(map);
    }
    map.removeLayer(geographyLayer);
    $("#map-footnote").textContent = FOOTNOTE_ONLINE;
  } else {
    if (map.hasLayer(baseTiles)) map.removeLayer(baseTiles);
    geographyLayer.addTo(map);
    $("#map-footnote").textContent = FOOTNOTE_OFFLINE;
  }
}

export function initializeMap() {
  map = L.map("map", {
    zoomControl: false,
    minZoom: 12,
    maxZoom: 18,
    maxBounds: HANOI_BOUNDS,
    maxBoundsViscosity: 1,
  }).setView([21.025, 105.83], 13);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  baseTiles = buildTileLayer(TILE_ORDER[tileProviderIndex]);
  baseTiles.addTo(map);
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
      .bindTooltip(name, { permanent: true, direction: "center", className: "water-label" });
  placeLayer = L.layerGroup().addTo(map);
  roadLayer = L.layerGroup().addTo(map);
  routeLayer = L.layerGroup().addTo(map);
  eventLayer = L.layerGroup().addTo(map);
  selectionLayer = L.layerGroup().addTo(map);
  map.on("click", (e) => {
    if (state.picking) finishPick(e.latlng.lat, e.latlng.lng);
  });
  map.on("movestart", () => ($("#search-results").hidden = true));
}

export function roadColor(r) {
  if (!r.known) return "#aab5af";
  if (state.horizon) {
    const risk = r.forecast[state.horizon / 15].risk;
    return risk >= 65 ? "#d76e62" : risk >= 35 ? "#daa34d" : "#74ad92";
  }
  if (r.blocked) return "#c95650";
  if (r.event_type && state.layers[r.event_type])
    return { flood: "#568eeb", traffic: "#e9a34d", incident: "#df7469" }[r.event_type];
  return "#86b9a0";
}

export function renderMap() {
  roadLayer.clearLayers();
  eventLayer.clearLayers();
  for (const r of state.data.roads) {
    const f = r.forecast[state.horizon / 15];
    const color = roadColor(r),
      weight = r.id === state.selected ? 7 : 4;
    const line = L.polyline(r.coordinates, {
      color,
      weight,
      opacity: 0.88,
      dashArray: r.known ? null : "5 6",
    }).addTo(roadLayer);
    line.bindTooltip(
      `<strong>${esc(r.name)}</strong><br>${!r.known ? "Chưa đủ dữ liệu" : state.horizon ? `Dự báo +${state.horizon} phút · Nguy cơ ${f.risk}/100` : `${r.speed} km/h · ${r.blocked ? "Đóng trong kịch bản" : "Dữ liệu thử nghiệm"}`}`,
    );
    line.on("click", (e) => {
      L.DomEvent.stopPropagation(e);
      if (state.picking) finishPick(e.latlng.lat, e.latlng.lng);
      else selectRoad(r.id, true);
    });
  }
  if (!state.horizon)
    for (const e of state.data.events) {
      if (!state.layers[e.type] || (e.status === "pending" && !state.layers.pending)) continue;
      const marker = L.marker([e.lat, e.lng], {
        icon: L.divIcon({
          className: `event-marker ${e.type} ${e.status === "pending" ? "pending" : ""}`,
          html: icon(typeIcons[e.type]),
          iconSize: [32, 32],
        }),
        title: `${typeNames[e.type]}: ${e.name}`,
      }).addTo(eventLayer);
      marker.bindTooltip(
        `${esc(e.name)} · ${e.status === "pending" ? "Chờ xác minh" : typeNames[e.type]}`,
      );
      marker.on("click", () => (state.picking ? finishPick(e.lat, e.lng) : showEvent(e.id)));
    }
  $("#map-mode-label").hidden = !state.horizon;
  $("#map-mode-label").textContent =
    `Dự báo +${state.horizon} phút · Nguy cơ thấp → trung bình → cao`;
  $(".map-legend").innerHTML = state.horizon
    ? '<span><i class="legend-dot green"></i>Thấp &lt;35</span><span><i class="legend-dot orange-bg"></i>Trung bình 35–64</span><span><i class="legend-dot red-bg"></i>Cao ≥65</span><span><i class="legend-dot gray-bg"></i>Chưa đủ dữ liệu</span>'
    : '<span><i class="legend-dot green"></i>Thông thoáng</span><span><i class="legend-dot orange-bg"></i>Ùn tắc</span><span><i class="legend-dot blue-bg"></i>Ngập</span><span><i class="legend-dot red-bg"></i>Sự cố / đóng</span><span><i class="legend-dot gray-bg"></i>Chưa có dữ liệu</span>';
}
