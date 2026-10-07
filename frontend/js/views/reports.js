/** Trang "Phản ánh" (admin): danh sách, bộ lọc, duyệt / từ chối / đánh dấu đã xử lý, xuất dữ liệu. */
import { api, post } from "../api.js";
import { statuses, typeNames } from "../config.js";
import { refresh } from "../dashboard.js";
import { map, selectionLayer } from "../map.js";
import { setView } from "../navigation.js";
import { state } from "../state.js";
import { $, esc, icon, toast } from "../utils.js";
import { clearRoutes } from "./routing.js";

export async function loadReports() {
  try {
    state.reports = (await api("/api/reports")).reports;
    renderReports();
  } catch (e) {
    $("#reports-list").innerHTML = `<div class="empty-state">${esc(e.message)}</div>`;
  }
}

export function renderReports() {
  const filter = $("#report-status-filter").value,
    reports = state.reports.filter((r) => filter === "all" || r.status === filter);
  $("#reports-list").innerHTML = reports.length
    ? reports
        .map(
          (r) =>
            `<article class="review-card"><div class="review-top"><h3>${esc(r.address)} <span class="data-label">· ${typeNames[r.type]}</span></h3><span class="tag tag-${r.status === "verified" ? "teal" : r.status === "pending" ? "orange" : "gray"}">${statuses[r.status]}</span></div><p>${esc(r.description)}</p><div class="review-meta">${esc(r.id)} · ${esc(r.road_id)} · Mức ${r.severity}/3 · ${new Date(r.created_at * 1000).toLocaleString("vi-VN")} · ${r.lat.toFixed(5)}, ${r.lng.toFixed(5)}</div>${r.media_url ? `<a href="${esc(r.media_url)}" target="_blank" rel="noopener"><img class="review-image" src="${esc(r.media_url)}" alt="Ảnh hiện trường do người dùng cung cấp"></a>` : ""}<div class="review-actions">${r.status === "pending" ? `<button class="approve" data-review-id="${esc(r.id)}" data-status="verified">Xác minh phản ánh</button><button data-review-id="${esc(r.id)}" data-status="rejected">Từ chối</button>` : r.status === "verified" ? `<button class="approve" data-review-id="${esc(r.id)}" data-status="resolved">Đánh dấu đã xử lý</button>` : ""}<button data-report-map="${esc(r.id)}">Xem vị trí</button></div></article>`,
        )
        .join("")
    : `<div class="empty-state">${icon("report")}${state.reports.length ? "Chưa có phản ánh thuộc trạng thái này." : "Chưa có phản ánh tại máy. Nhấn “Gửi phản ánh” để đóng góp thông tin đầu tiên."}</div>`;
}

export function initReports() {
  document.addEventListener("click", async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if (button.dataset.reviewId) {
      button.disabled = true;
      try {
        await post("/api/reports/" + button.dataset.reviewId, { status: button.dataset.status });
        await loadReports();
        await refresh();
        clearRoutes();
        toast("Đã cập nhật trạng thái phản ánh.");
      } catch (err) {
        toast(err.message);
        button.disabled = false;
      }
    }
    if (button.dataset.reportMap) {
      const r = state.reports.find((r) => r.id === button.dataset.reportMap);
      setView("map");
      map.setView([r.lat, r.lng], 15);
      selectionLayer.clearLayers();
      L.circleMarker([r.lat, r.lng], { radius: 10, color: "#087f72" }).addTo(selectionLayer);
    }
  });
  $("#refresh-reports").addEventListener("click", loadReports);
  $("#report-status-filter").addEventListener("change", renderReports);
}
