/** Thẻ "Nhìn trước hành trình" cho đoạn đường đang chọn (biểu đồ cột mini 0-60 phút). */
import { state } from "../state.js";
import { $ } from "../utils.js";

export function renderInsight() {
  const road = state.data.roads.find((r) => r.id === state.selected) || state.data.roads[0];
  $("#insight-road").textContent = road.name;
  const last = road.forecast[4];
  $("#insight-summary").textContent = road.known
    ? `Sau 60 phút: nguy cơ ngập ${last.flood_risk}/100, tốc độ ước tính ${last.speed} km/h. Chọn một đoạn trên bản đồ để xem thêm.`
    : "Đoạn đường chưa đủ dữ liệu. Hệ thống không suy diễn thành trạng thái an toàn.";
  $("#mini-forecast").innerHTML = road.forecast
    .map(
      (f, i) =>
        `<div class="mini-column ${i === 2 || i === 4 ? "focus" : ""}"><b>${f.flood_risk ?? "—"}</b><div class="bar" style="height:${f.flood_risk ?? 0}%"></div><span>${f.horizon ? "+" + f.horizon + " phút" : "Hiện tại"}</span></div>`,
    )
    .join("");
}
