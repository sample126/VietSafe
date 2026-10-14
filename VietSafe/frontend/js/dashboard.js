/**
 * Vòng cập nhật dữ liệu: gọi /api/snapshot định kỳ rồi vẽ lại các thành phần.
 * Đây là "bộ điều phối" - muốn thêm một thành phần tự cập nhật, hãy gọi hàm render của nó
 * trong updateDashboard().
 */
import { api } from "./api.js";
import { placeLayer, renderMap } from "./map.js";
import { state } from "./state.js";
import { $, esc, timeText } from "./utils.js";
import { renderEvents } from "./views/events-panel.js";
import { renderForecast } from "./views/forecast.js";
import { renderInsight } from "./views/insight.js";
import { updateAlertBanner } from "./views/alert-banner.js";
import { loadReports } from "./views/reports.js";
import { renderSources } from "./views/sources.js";

let refreshing = false;

export async function refresh() {
  if (refreshing) {
    await refreshing;
    return refresh();
  }
  let complete;
  refreshing = new Promise((resolve) => (complete = resolve));
  try {
    const first = !state.data;
    state.data = await api("/api/snapshot");
    state.connected = true;
    state.lastGood = Date.now();
    $("#connection-error").hidden = true;
    $("#sync-status").textContent = "Kết nối local · Dữ liệu mô phỏng";
    $(".status-dot").style.background = "#49a68b";
    if (first) populateControls();
    updateDashboard();
    updateAlertBanner();
    if (state.view === "reports") await loadReports();
  } catch (e) {
    // Lỗi trong lúc VẼ cũng rơi vào đây và hiện như "mất kết nối" - nên luôn ghi ra console.
    console.error("refresh thất bại:", e);
    state.connected = false;
    $("#connection-error").hidden = false;
    $("#sync-status").textContent = state.data
      ? "Mất kết nối · Dữ liệu đã cũ"
      : "Chưa kết nối máy chủ";
    $(".status-dot").style.background = "#d86b5c";
  } finally {
    refreshing = false;
    complete();
  }
}

export function populateControls() {
  const options = state.data.nodes
    .map((n) => `<option value="${esc(n.id)}">${esc(n.name)}</option>`)
    .join("");
  $("#route-origin").innerHTML = options;
  $("#route-destination").innerHTML = options;
  $("#route-origin").value = "caugiay";
  $("#route-destination").value = "hoankiem";
  $("#forecast-road").innerHTML = state.data.roads
    .map((r) => `<option value="${r.id}">${esc(r.name)}</option>`)
    .join("");
  $("#forecast-road").value = state.selected;
  $("#address-options").innerHTML = state.data.nodes
    .map((n) => `<option value="${esc(n.name)}"></option>`)
    .join("");
  for (const n of state.data.nodes) {
    L.circleMarker([n.lat, n.lng], {
      radius: 2,
      weight: 1,
      color: "#a5b8ab",
      fillOpacity: 1,
      interactive: false,
    })
      .addTo(placeLayer)
      .bindTooltip(esc(n.name), {
        permanent: true,
        direction: "bottom",
        className: "place-label",
        offset: [0, 4],
      });
  }
  renderSources();
}

export function updateDashboard() {
  const d = state.data;
  for (const type of ["flood", "traffic", "incident"])
    $(`#stat-${type}`).textContent = String(d.counts[type]).padStart(2, "0");
  $("#stat-rain").innerHTML = `${d.rainfall}<em>mm/h</em>`;
  $("#weather-caption").textContent =
    `${{ normal: "Trời khô", rain: "Mưa lớn", storm: "Mưa rất lớn" }[d.scenario]} · ${d.temperature}°C`;
  $("#map-clock").textContent = timeText(d.generated_at);
  $("#event-total").textContent = d.events.length;
  $("#nav-count").textContent = d.pending;
  $("#nav-count").hidden = !d.pending;
  $("#forecast-scenario").value = d.scenario;
  $("#source-scenario").value = d.scenario;
  renderMap();
  renderEvents();
  renderInsight();
  if (state.view === "forecast") renderForecast();
  if (state.routes) {
    const label = $("#route-calculation-note");
    if (label)
      label.textContent = `Tính lúc ${timeText(state.routes.calculated_at)} · Bấm tìm tuyến để cập nhật.`;
  }
}
