/** Chọn một đoạn đường và hiện hộp thoại chi tiết (số liệu hiện tại + dự báo). */
import { state } from "../state.js";
import { $, esc, icon, timeText } from "../utils.js";
import { map, renderMap } from "../map.js";
import { setView } from "../navigation.js";
import { renderForecast } from "./forecast.js";
import { renderInsight } from "./insight.js";

export function selectRoad(id, details = false) {
  state.selected = id;
  $("#forecast-road").value = id;
  renderInsight();
  renderMap();
  if (state.view === "forecast") renderForecast();
  if (details) showRoadDetails(id);
}

export function showRoadDetails(id, event = null) {
  const r = state.data.roads.find((r) => r.id === id);
  if (!r) return;
  const f = r.forecast[2];
  $("#detail-content").innerHTML =
    `<div class="dialog-heading"><div><div class="eyebrow teal-text">${event?.status === "pending" ? "PHẢN ÁNH CHỜ XÁC MINH" : "CHI TIẾT ĐOẠN ĐƯỜNG"}</div><h2>${esc(event?.name || r.name)}</h2></div><button class="icon-button close-dialog" aria-label="Đóng chi tiết">${icon("close")}</button></div><span class="tag tag-${event?.status === "pending" ? "gray" : "teal"}">${event?.status === "pending" ? "Phản ánh chờ xác minh · chưa ảnh hưởng định tuyến" : r.origin === "demo" ? "Dữ liệu mô phỏng" : "Phản ánh đã xác minh tại máy · chỉ phản ánh là dữ liệu người dùng"}</span><div class="detail-stats"><div><span>Tốc độ mô phỏng</span><strong>${r.known ? r.speed + " km/h" : "Chưa rõ"}</strong></div><div><span>Nguy cơ ngập mô phỏng +30p</span><strong>${f.flood_risk == null ? "Chưa rõ" : f.flood_risk + "/100"}</strong></div><div><span>Trạng thái mô phỏng</span><strong>${!r.known ? "Chưa rõ" : r.blocked ? "Đóng trong kịch bản" : "Không bị đóng trong kịch bản"}</strong></div></div><p class="data-label">${esc((event?.sources || r.sources).join(" · "))} · ${timeText(event?.updated_at || r.updated_at)}</p><div class="detail-evidence">${esc((event?.evidence || r.evidence).join("\n"))}</div><p class="muted">Giá trị tốc độ, độ sâu và nguy cơ là mô phỏng theo quy tắc, không phải số đo hiện trường hay xác suất. Không dùng kết quả để quyết định đi qua vùng ngập thực tế.</p><div class="dialog-footer"><button class="button secondary" data-focus-road="${r.id}">${icon("pin")}Xem trên bản đồ</button><button class="button primary" data-forecast-detail="${r.id}">Xem thực nghiệm ${icon("arrow")}</button></div>`;
  if (!$("#detail-dialog").open) $("#detail-dialog").showModal();
}

export function initRoadDetails() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if (button.dataset.focusRoad) {
      $("#detail-dialog").close();
      setView("map");
      const r = state.data.roads.find((r) => r.id === button.dataset.focusRoad);
      map.fitBounds(r.coordinates, { padding: [100, 100], maxZoom: 15 });
    }
    if (button.dataset.forecastDetail) {
      $("#detail-dialog").close();
      selectRoad(button.dataset.forecastDetail);
      setView("forecast");
    }
  });
}
