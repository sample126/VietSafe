/** Banner đỏ cảnh báo khi có đoạn đường bị chặn. */
import { state } from "../state.js";
import { $ } from "../utils.js";

// === Alert banner ===
export function updateAlertBanner() {
  if (!state.data) return;
  const blocked = state.data.roads.filter((r) => r.blocked);
  // Banner cảnh báo đoạn đường bị chặn là thông tin của bản đồ:
  // chỉ hiển thị khi đang ở trang Bản đồ, ẩn trên các trang còn lại.
  if (blocked.length > 0 && state.view === "map") {
    $("#alert-text").textContent =
      `⚠ ${blocked.length} đoạn đường bị chặn: ${blocked.map((r) => r.name).join(", ")}. Hãy kiểm tra tuyến trước khi di chuyển.`;
    $("#alert-banner").hidden = false;
  } else {
    $("#alert-banner").hidden = true;
  }
}

export function initAlertBanner() {
  $("#dismiss-alert").addEventListener("click", () => ($("#alert-banner").hidden = true));
}
