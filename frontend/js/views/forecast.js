/** Trang "Dự báo": chọn đoạn đường, biểu đồ nguy cơ 0-60 phút và bảng chi tiết. */
import { state } from "../state.js";
import { $, esc } from "../utils.js";
import { changeScenario } from "../scenario.js";
import { renderInsight } from "./insight.js";
import { initForecastWorkspace } from "./forecast-workspace.js";

export function renderForecast() {
  const r = state.data.roads.find((r) => r.id === $("#forecast-road").value);
  if (!r) return;
  if (!r.known) {
    $("#forecast-chart").innerHTML =
      '<div class="empty-state">Chưa đủ dữ liệu để dự báo đoạn đường này. Không có dữ liệu không có nghĩa là không có nguy cơ.</div>';
    return;
  }
  const xs = [65, 270, 475, 680, 885],
    y = (v) => 205 - v * 1.75;
  const path = (key) =>
    r.forecast.map((f, i) => `${i ? "L" : "M"}${xs[i]},${y(f[key])}`).join(" ");
  let svg = `<svg class="large-chart" viewBox="0 0 950 245" role="img" aria-label="Dự báo nguy cơ ngập, ùn tắc và sự cố cho ${esc(r.name)}">`;
  for (const v of [0, 25, 50, 75, 100])
    svg += `<line x1="65" y1="${y(v)}" x2="885" y2="${y(v)}" stroke="#e7ede7" stroke-dasharray="4 5"/><text x="30" y="${y(v) + 4}" fill="#91a494">${v}</text>`;
  svg += `<path d="${path("flood_risk")} L885,205 L65,205 Z" fill="#edf3fd" stroke="none"/><path d="${path("flood_risk")}" fill="none" stroke="#347ec5" stroke-width="3"/><path d="${path("traffic_risk")}" fill="none" stroke="#cc8a2b" stroke-width="3"/><path d="${path("incident_risk")}" fill="none" stroke="#cf5149" stroke-width="3"/>`;
  r.forecast.forEach((f, i) => {
    svg += `<circle cx="${xs[i]}" cy="${y(f.flood_risk)}" r="5" fill="white" stroke="#347ec5" stroke-width="2"/><text x="${xs[i]}" y="234" text-anchor="middle" fill="#89a18e">${f.horizon ? "+" + f.horizon + " phút" : "Hiện tại"}</text>`;
  });
  svg += "</svg>";
  $("#forecast-chart").innerHTML =
    svg +
    `<div class="chart-legend"><span><i class="legend-dot blue-bg"></i>Ngập</span><span><i class="legend-dot orange-bg"></i>Ùn tắc</span><span><i class="legend-dot red-bg"></i>Sự cố</span></div><div class="forecast-table-wrap"><table class="forecast-table"><thead><tr><th>Thời điểm</th><th>Ngập</th><th>Ùn tắc</th><th>Sự cố</th><th>Tốc độ</th><th>Tổng hợp</th></tr></thead><tbody>${r.forecast.map((f) => `<tr><td>${f.horizon ? "Sau " + f.horizon + " phút" : "Hiện tại"}</td><td>${f.flood_risk}/100</td><td>${f.traffic_risk}/100</td><td>${f.incident_risk}/100</td><td>${f.speed} km/h</td><td><span class="tag tag-${f.risk >= 65 ? "red" : f.risk >= 35 ? "orange" : "teal"}">${f.label} · ${f.risk}/100</span></td></tr>`).join("")}</tbody></table></div>`;
}

export function initForecast() {
  initForecastWorkspace();
  $("#forecast-road").addEventListener("change", () => {
    state.selected = $("#forecast-road").value;
    renderForecast();
    renderInsight();
  });
  $("#forecast-scenario").addEventListener("change", (e) =>
    changeScenario(e.target.value),
  );
}
