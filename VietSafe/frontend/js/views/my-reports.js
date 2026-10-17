/** Trang "Phản ánh của tôi": người dân xem lịch sử phản ánh đã gửi và trạng thái hiện tại. */
import { api } from "../api.js";
import { statuses, typeNames } from "../config.js";
import { refresh } from "../dashboard.js";
import { state } from "../state.js";
import { $, esc, toast } from "../utils.js";
import { clearRoutes } from "./routing.js";

export async function loadMyReports() {
  try {
    state.myReports = (await api("/api/my-reports")).reports;
    renderMyReports();
  } catch (e) {
    $("#my-reports-list").innerHTML =
      `<div class="empty-state">${esc(e.message)}</div>`;
  }
}

export function renderMyReports() {
  const reports = state.myReports || [];
  $("#my-reports-count").textContent = reports.length;

  const filtered = reports
    .filter((r) => state.myReportsFilter === "all" || r.status === state.myReportsFilter)
    .sort((a, b) => b.created_at - a.created_at);

  $("#my-reports-list").innerHTML = filtered.length
    ? filtered.map((r) => renderMyReportCard(r)).join("")
    : `<div class="empty-state">Chưa có phản ánh nào.</div>`;
}

function renderMyReportCard(report) {
  const id = esc(report.id);
  const statusClass =
    report.status === "verified" ? "teal" :
    report.status === "pending" ? "orange" :
    report.status === "rejected" ? "red" : "gray";
  return `<article class="review-card">
    <div class="review-top">
      <h3>${esc(report.address)} <span class="data-label">· ${typeNames[report.type]}</span></h3>
      <span class="tag tag-${statusClass}">${statuses[report.status]}</span>
    </div>
    <p>${esc(report.description)}</p>
    <div class="review-evidence">
      <span><strong>Vị trí:</strong> ${report.lat.toFixed(5)}, ${report.lng.toFixed(5)}</span>
      <span><strong>Mức độ:</strong> ${report.severity}/3</span>
    </div>
    <div class="review-meta">
      ${id} · ${new Date(report.created_at * 1000).toLocaleString("vi-VN")}
      ${report.expires_at ? ` · Hết hạn: ${new Date(report.expires_at * 1000).toLocaleString("vi-VN")}` : ""}
    </div>
    ${report.media_url ? `<a href="${esc(report.media_url)}" target="_blank" rel="noopener"><img class="review-image" src="${esc(report.media_url)}" alt="Ảnh hiện trường"></a>` : ""}
    <div class="review-actions">
      <button data-my-report-map="${id}">Xem vị trí</button>
    </div>
  </article>`;
}

export function initMyReports() {
  $("#my-reports-filter")?.addEventListener("change", (e) => {
    state.myReportsFilter = e.target.value;
    renderMyReports();
  });
  $("#refresh-my-reports")?.addEventListener("click", loadMyReports);

  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if (button.dataset.myReportMap) {
      const r = state.myReports?.find((r) => r.id === button.dataset.myReportMap);
      if (r) {
        import("../navigation.js").then(({ setView }) => {
          setView("map");
          import("../map.js").then(({ map, selectionLayer }) => {
            map.setView([r.lat, r.lng], 15);
            selectionLayer.clearLayers();
            L.circleMarker([r.lat, r.lng], { radius: 10, color: "#087f72" }).addTo(selectionLayer);
          });
        });
      }
    }
  });
}
