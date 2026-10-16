/** Banner đỏ cảnh báo khi có đoạn đường bị chặn. */
import { state } from "../state.js";
import { $ } from "../utils.js";

// === Alert banner ===
export function updateAlertBanner() {
  if (!state.data) return;
  const blocked = state.data.roads.filter((r) => r.blocked);
  if (blocked.length > 0) {
    $("#alert-text").textContent =
      `Trong kịch bản mô phỏng, ${blocked.length} đoạn được đánh dấu đóng: ${blocked.map((r) => r.name).join(", ")}. Đây không phải thông tin hiện trường; không dùng để quyết định lộ trình.`;
    $("#alert-banner").hidden = false;
  } else {
    $("#alert-banner").hidden = true;
  }
}

export function initAlertBanner() {
  $("#dismiss-alert").addEventListener(
    "click",
    () => ($("#alert-banner").hidden = true),
  );
}
