/** Bảng "Sự kiện" bên phải trang Bản đồ: danh sách cảnh báo, bộ lọc, mở chi tiết. */
import { typeColors, typeIcons, typeNames } from "../config.js";
import { state } from "../state.js";
import { $, $$, ago, esc, icon } from "../utils.js";
import { map } from "../map.js";
import { selectRoad, showRoadDetails } from "./road-details.js";

export function renderEvents() {
  if (!state.data) return;
  const events = state.data.events.filter((e) => state.filter === "all" || e.type === state.filter);
  $("#event-list").innerHTML = events.length
    ? events
        .map((e) => {
          const summary =
            e.status === "pending"
              ? "Chưa được dùng cho cảnh báo tuyến"
              : e.blocked
                ? "Không thể lưu thông trong kịch bản"
                : e.type === "flood"
                  ? `Độ sâu mô phỏng ${e.depth ?? "chưa đo"}${e.depth != null ? " cm" : ""}`
                  : e.type === "traffic"
                    ? `Tốc độ mô phỏng ${e.speed} km/h`
                    : "Phương tiện dừng gây cản trở";
          return `<button class="event-item" data-event="${esc(e.id)}"><span class="event-type-icon ${typeColors[e.type]}">${icon(typeIcons[e.type])}</span><div class="event-copy"><h3>${esc(e.name)}</h3><p>${esc(summary)}</p><div class="event-meta"><span class="tag tag-${e.status === "pending" ? "gray" : typeColors[e.type]}">${e.status === "pending" ? "Chờ xác minh" : typeNames[e.type]}</span><span>${e.origin === "demo" ? "Mô phỏng" : "Tại máy"} · ${ago(e.updated_at)}</span></div></div></button>`;
        })
        .join("")
    : `<div class="empty-state">${icon("check")}Không có cảnh báo thuộc nhóm này trong kịch bản hiện tại.</div>`;
}

export function showEvent(id) {
  const e = state.data.events.find((e) => e.id === id);
  if (!e) return;
  selectRoad(e.road_id);
  map.setView([e.lat, e.lng], 15);
  showRoadDetails(e.road_id, e);
}

export function initEventsPanel() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if (button.dataset.filter) {
      state.filter = button.dataset.filter;
      $$("#event-filters button").forEach((b) =>
        b.classList.toggle("active", b.dataset.filter === state.filter),
      );
      renderEvents();
    }
    if (button.dataset.event) showEvent(button.dataset.event);
  });
}
