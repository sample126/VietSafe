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
    $("#reports-list").innerHTML =
      `<div class="empty-state">${esc(e.message)}</div>`;
  }
}

function normalizeSearch(value) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[đĐ]/g, "d")
    .toLocaleLowerCase("vi-VN")
    .trim();
}

export function renderReports() {
  const filter = $("#report-status-filter").value;
  const query = normalizeSearch($("#report-search").value);
  const counts = state.reports.reduce(
    (result, report) => {
      result[report.status] = (result[report.status] || 0) + 1;
      return result;
    },
    { total: state.reports.length },
  );
  $("#report-status-counts").innerHTML = [
    `<div class="report-status-count" data-status="total"><span>Tổng phản ánh</span><strong>${counts.total}</strong></div>`,
    ...Object.entries(statuses).map(
      ([status, label]) =>
        `<div class="report-status-count" data-status="${status}"><span>${label}</span><strong>${counts[status] || 0}</strong></div>`,
    ),
  ].join("");

  const reports = state.reports
    .filter((r) => filter === "all" || r.status === filter)
    .filter(
      (r) =>
        !query ||
        normalizeSearch(`${r.address} ${r.description}`).includes(query),
    )
    .sort(
      (a, b) =>
        Number(b.status === "pending") - Number(a.status === "pending") ||
        b.created_at - a.created_at,
    );
  $("#reports-list").innerHTML = reports.length
    ? reports.map((r) => renderReportCard(r)).join("")
    : `<div class="empty-state">${icon("report")}${query ? "Không tìm thấy phản ánh khớp với nội dung tìm kiếm." : state.reports.length ? "Chưa có phản ánh thuộc trạng thái này." : "Chưa có phản ánh tại máy."}</div>`;
}

const HISTORY_LABELS = {
  created: "Tiếp nhận phản ánh",
  verified: "Đã xác minh",
  rejected: "Đã từ chối",
  resolved: "Đã xử lý",
  expired: "Hết hạn",
};

function renderReportCard(report) {
  const id = esc(report.id);
  const actions =
    report.status === "pending"
      ? `<button class="approve" data-review-id="${id}" data-status="verified">Xác minh phản ánh</button><button data-review-id="${id}" data-status="rejected">Từ chối</button>`
      : report.status === "verified"
        ? `<button class="approve" data-review-id="${id}" data-status="resolved">Đánh dấu đã xử lý</button>`
        : "";
  return `<article class="review-card"><div class="review-top"><h3>${esc(report.address)} <span class="data-label">· ${typeNames[report.type]}</span></h3><span class="tag tag-${report.status === "verified" ? "teal" : report.status === "pending" ? "orange" : "gray"}">${statuses[report.status]}</span></div><p>${esc(report.description)}</p><div class="review-evidence"><span><strong>Nguồn:</strong> Phản ánh cộng đồng do người dùng gửi</span><span><strong>Bằng chứng:</strong> Mô tả người gửi · ${report.media_url ? "Có ảnh đính kèm" : "Không có ảnh đính kèm"}</span></div><div class="review-meta">${id} · ${esc(report.road_id)} · Mức ${report.severity}/3 · ${new Date(report.created_at * 1000).toLocaleString("vi-VN")} · ${report.lat.toFixed(5)}, ${report.lng.toFixed(5)}</div>${report.media_url ? `<a href="${esc(report.media_url)}" target="_blank" rel="noopener"><img class="review-image" src="${esc(report.media_url)}" alt="Ảnh hiện trường do người dùng cung cấp"></a>` : ""}<div class="review-actions">${actions}<button data-report-map="${id}">Xem vị trí</button><button data-report-history="${id}" aria-expanded="false">Lịch sử xử lý</button></div><div class="review-history" data-history-for="${id}" hidden></div></article>`;
}

export function initReports() {
  document.addEventListener("click", async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    if (button.dataset.reportHistory) {
      const reportId = button.dataset.reportHistory;
      const panel = [...document.querySelectorAll("[data-history-for]")].find(
        (element) => element.dataset.historyFor === reportId,
      );
      const isOpening = panel.hidden;
      panel.hidden = !isOpening;
      button.setAttribute("aria-expanded", String(isOpening));
      if (!isOpening) return;

      panel.innerHTML = `<p>Đang tải lịch sử…</p>`;
      button.disabled = true;
      try {
        const { history } = await api(
          `/api/reports/${encodeURIComponent(reportId)}/history`,
        );
        panel.innerHTML = history.length
          ? `<ol>${history
              .map(
                (event) =>
                  `<li><strong>${esc(HISTORY_LABELS[event.action] || event.action)}</strong><time>${new Date(event.timestamp * 1000).toLocaleString("vi-VN")}</time>${event.detail ? `<p>${esc(event.detail)}</p>` : ""}</li>`,
              )
              .join("")}</ol>`
          : "<p>Chưa có lịch sử xử lý.</p>";
      } catch (err) {
        panel.innerHTML = `<p class="history-error">${esc(err.message)}</p>`;
        panel.hidden = false;
        button.setAttribute("aria-expanded", "true");
      } finally {
        button.disabled = false;
      }
      return;
    }
    if (button.dataset.reviewId) {
      const { reviewId, status } = button.dataset;
      let reason;
      if (status === "rejected") {
        reason = window
          .prompt("Nhập lý do từ chối (tối đa 240 ký tự):")
          ?.trim();
        if (!reason) return;
        if (reason.length > 240) {
          toast("Lý do từ chối tối đa 240 ký tự.");
          return;
        }
      }
      const confirmation =
        status === "verified"
          ? "Hãy kiểm tra mô tả, vị trí và ảnh đính kèm (nếu có) trước khi xác minh phản ánh này. Tiếp tục?"
          : status === "resolved"
            ? "Xác nhận đánh dấu phản ánh này là đã xử lý?"
            : status === "rejected"
              ? `Xác nhận từ chối phản ánh với lý do: ${reason}`
              : null;
      if (confirmation && !window.confirm(confirmation)) return;
      button.disabled = true;
      try {
        await post("/api/reports/" + reviewId, { status, reason });
        await loadReports();
        await refresh();
        clearRoutes();
        toast(
          status === "resolved"
            ? "Đã đánh dấu phản ánh là đã xử lý."
            : status === "verified"
              ? "Đã xác minh phản ánh."
              : "Đã từ chối phản ánh.",
        );
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
      L.circleMarker([r.lat, r.lng], { radius: 10, color: "#087f72" }).addTo(
        selectionLayer,
      );
    }
  });
  $("#refresh-reports").addEventListener("click", loadReports);
  $("#report-status-filter").addEventListener("change", renderReports);
  $("#report-search").addEventListener("input", renderReports);
}
