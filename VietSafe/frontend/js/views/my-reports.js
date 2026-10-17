/** Trang "Phản ánh của tôi": người dân xem lịch sử phản ánh đã gửi và trạng thái hiện tại. */
import { api } from "../api.js";
import { statuses, typeNames } from "../config.js";
import { state } from "../state.js";
import { $, esc, timeAgo } from "../utils.js";

const STEPS = [
  { key: "created", label: "Tiếp nhận" },
  { key: "verified", label: "Xác minh" },
  { key: "resolved", label: "Xử lý" },
];

function currentStep(status) {
  switch (status) {
    case "pending": return 0;
    case "verified": return 1;
    case "resolved": return 2;
    case "rejected": return -1;
    case "expired": return -1;
    default: return 0;
  }
}

function renderStepper(status) {
  const step = currentStep(status);
  if (step === -1) {
    const cls = status === "rejected" ? "rejected" : "expired";
    const label = status === "rejected" ? "Bị từ chối" : "Hết hạn";
    return `<div class="stepper stepper-${cls}"><span class="stepper-end">${label}</span></div>`;
  }
  return `<div class="stepper">` + STEPS.map((s, i) => {
    const done = i < step;
    const active = i === step;
    return `<div class="stepper-step ${done ? "done" : ""} ${active ? "active" : ""}">
      <div class="stepper-dot"></div>
      <span class="stepper-label">${s.label}</span>
    </div>`;
  }).join(`<div class="stepper-line"></div>`) + `</div>`;
}

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
  renderMyStats(reports);

  const filtered = reports
    .filter((r) => state.myReportsFilter === "all" || r.status === state.myReportsFilter)
    .sort((a, b) => b.created_at - a.created_at);

  $("#my-reports-count").textContent = filtered.length;

  $("#my-reports-list").innerHTML = filtered.length
    ? filtered.map((r) => renderMyReportCard(r)).join("")
    : renderEmptyState(reports.length);
}

function renderMyStats(reports) {
  const counts = reports.reduce((acc, r) => {
    acc[r.status] = (acc[r.status] || 0) + 1;
    return acc;
  }, {});
  $("#my-reports-stats").innerHTML = `
    <div class="my-stat"><strong>${reports.length}</strong><span>Tổng số</span></div>
    <div class="my-stat my-stat-pending"><strong>${counts.pending || 0}</strong><span>Chờ xác minh</span></div>
    <div class="my-stat my-stat-verified"><strong>${counts.verified || 0}</strong><span>Đã xác minh</span></div>
    <div class="my-stat my-stat-resolved"><strong>${counts.resolved || 0}</strong><span>Đã xử lý</span></div>
    <div class="my-stat my-stat-rejected"><strong>${counts.rejected || 0}</strong><span>Đã từ chối</span></div>
  `;
}

function renderEmptyState(total) {
  if (total === 0) {
    return `<div class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
      <p>Bạn chưa gửi phản ánh nào.</p>
      <p>Hãy chia sẻ tình trạng đường phố để cộng đồng cùng biết!</p>
      <button class="button primary" id="empty-report-cta">Gửi phản ánh đầu tiên</button>
    </div>`;
  }
  return `<div class="empty-state">
    <p>Không có phản ánh nào khớp bộ lọc.</p>
  </div>`;
}

const SEVERITY_LABELS = { 1: "Nhẹ", 2: "Trung bình", 3: "Nghiêm trọng" };
const SEVERITY_COLORS = { 1: "green", 2: "orange", 3: "red" };

const DESC_CLAMP_THRESHOLD = 180;

function renderDescription(desc) {
  if (!desc) return "";
  if (desc.length <= DESC_CLAMP_THRESHOLD) {
    return `<p class="my-desc">${esc(desc)}</p>`;
  }
  return `<p class="my-desc clampable">${esc(desc)}</p>
    <button class="desc-toggle" data-desc-toggle>Xem thêm</button>`;
}

function renderMyReportCard(report) {
  const id = esc(report.id);
  const statusClass =
    report.status === "verified" ? "teal" :
    report.status === "pending" ? "orange" :
    report.status === "rejected" ? "red" : "gray";
  const sevColor = SEVERITY_COLORS[report.severity] || "green";
  const reasonHtml = report.status === "rejected" && report.reason
    ? `<div class="reject-reason"><strong>Lý do từ chối:</strong> ${esc(report.reason)}</div>`
    : "";
  return `<article class="review-card">
    <div class="review-top">
      <h3>${esc(report.address)} <span class="data-label">· ${typeNames[report.type]}</span></h3>
      <span class="tag tag-${statusClass}">${statuses[report.status]}</span>
    </div>
    ${renderStepper(report.status)}
    ${renderDescription(report.description)}
    <div class="review-evidence">
      <span><strong>Mức độ:</strong> <span class="severity-${sevColor}">${report.severity}/3 — ${SEVERITY_LABELS[report.severity]}</span></span>
      <span><strong>Gửi lúc:</strong> ${timeAgo(report.created_at)}</span>
    </div>
    ${reasonHtml}
    <div class="review-meta">
      ${id} · ${new Date(report.created_at * 1000).toLocaleString("vi-VN")}
      ${report.expires_at && (report.status === "pending" || report.status === "verified") ? ` · Hết hạn: ${new Date(report.expires_at * 1000).toLocaleString("vi-VN")}` : ""}
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
    // CTA trong empty state
    if (e.target.id === "empty-report-cta") {
      import("./report-form.js").then((m) => m.openReport());
      return;
    }
    // Bấm "Xem thêm" / "Thu gọn" mô tả dài
    if (e.target.closest("[data-desc-toggle]")) {
      const btn = e.target.closest("[data-desc-toggle]");
      const desc = btn.previousElementSibling;
      const clamped = desc.classList.toggle("clampable");
      btn.textContent = clamped ? "Xem thêm" : "Thu gọn";
      return;
    }
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