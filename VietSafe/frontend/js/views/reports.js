/** Trang "Phản ánh" (admin): danh sách, bộ lọc, duyệt / từ chối / đánh dấu đã xử lý, xuất dữ liệu. */
import { api, post } from "../api.js";
import { statuses, typeNames } from "../config.js";
import { refresh } from "../dashboard.js";
import { map, selectionLayer } from "../map.js";
import { setView } from "../navigation.js";
import { state } from "../state.js";
import { $, $$, esc, icon, toast } from "../utils.js";
import { clearRoutes } from "./routing.js";

export async function loadReports() {
  try {
    // Luôn fetch TẤT CẢ phản ánh (không filter) để counts luôn chính xác
    // Filter sẽ được áp dụng client-side trong renderReports()
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
  const filter = $("#report-status-filter")?.value || "all";
  const severityFilter = $("#report-severity-filter")?.value;
  const dateFrom = $("#report-date-from")?.value;
  const dateTo = $("#report-date-to")?.value;
  const query = normalizeSearch($("#report-search")?.value || "");
  const onlyPending = $("#only-pending-toggle")?.checked;

  // Counts luôn tính từ TẤT CẢ phản ánh (không filter)
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

  // Filter client-side cho list
  const reports = state.reports
    .filter((r) => filter === "all" || r.status === filter)
    .filter((r) => !severityFilter || r.severity === Number(severityFilter))
    .filter((r) => !onlyPending || r.status === "pending")
    .filter((r) => {
      if (!dateFrom && !dateTo) return true;
      const created = new Date(r.created_at * 1000);
      if (dateFrom && created < new Date(dateFrom)) return false;
      if (dateTo && created > new Date(dateTo + "T23:59:59")) return false;
      return true;
    })
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
  updateBulkActions();
}

function updateBulkActions() {
  const checkboxes = $$("#reports-list input[type=checkbox][data-bulk-select]");
  const selected = [...checkboxes].filter((c) => c.checked);
  const bulkBar = $("#bulk-actions-bar");
  if (!bulkBar) return;
  bulkBar.hidden = selected.length === 0;
  $("#bulk-selected-count").textContent = selected.length;
}

export async function bulkReview(status) {
  const checkboxes = $$("#reports-list input[type=checkbox][data-bulk-select]:checked");
  const ids = checkboxes.map((c) => c.value);
  if (!ids.length) return;
  let reason;
  if (status === "rejected") {
    reason = window.prompt("Nhập lý do từ chối (tối đa 240 ký tự):")?.trim();
    if (!reason) return;
  }
  try {
    const result = await post("/api/reports/bulk-review", { ids, status, reason });
    toast(`Đã xử lý ${result.success.length} phản ánh.`);
    if (result.failed.length) {
      toast(`${result.failed.length} phản ánh thất bại.`);
    }
    await loadReports();
    await refresh();
    clearRoutes();
  } catch (err) {
    toast(err.message);
  }
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
  const canBulk = report.status === "pending" || report.status === "verified";
  const checkbox = canBulk
    ? `<input type="checkbox" data-bulk-select value="${id}" aria-label="Chọn ${id}">`
    : "";
  // "New" indicator: phản ánh tạo trong 5 phút gần nhất
  const isNew = (Date.now() / 1000 - report.created_at) < 300;
  const newBadge = isNew ? `<span class="new-badge">Mới</span>` : "";
  const actions =
    report.status === "pending"
      ? `<button class="approve" data-review-id="${id}" data-status="verified">Xác minh phản ánh</button><button data-review-id="${id}" data-status="rejected">Từ chối</button>`
      : report.status === "verified"
        ? `<button class="approve" data-review-id="${id}" data-status="resolved">Đánh dấu đã xử lý</button>`
        : "";
  return `<article class="review-card"><div class="review-top">${checkbox}<h3>${esc(report.address)} <span class="data-label">· ${typeNames[report.type]}</span></h3><span class="tag tag-${report.status === "verified" ? "teal" : report.status === "pending" ? "orange" : "gray"}">${statuses[report.status]}</span>${newBadge}</div><p>${esc(report.description)}</p><div class="review-evidence"><span><strong>Nguồn:</strong> Phản ánh cộng đồng do người dùng gửi</span><span><strong>Bằng chứng:</strong> Mô tả người gửi · ${report.media_url ? "Có ảnh đính kèm" : "Không có ảnh đính kèm"}</span></div><div class="review-meta">${id} · ${esc(report.road_id)} · Mức ${report.severity}/3 · ${new Date(report.created_at * 1000).toLocaleString("vi-VN")} · ${report.lat.toFixed(5)}, ${report.lng.toFixed(5)}</div>${report.media_url ? `<a href="${esc(report.media_url)}" target="_blank" rel="noopener" class="image-view-full"><img class="review-image" src="${esc(report.media_url)}" alt="Ảnh hiện trường do người dùng cung cấp"></a>` : ""}<div class="review-actions">${actions}<button data-report-map="${id}">Xem vị trí</button><button data-report-history="${id}" aria-expanded="false">Lịch sử xử lý</button></div><div class="review-history" data-history-for="${id}" hidden></div></article>`;
}

export function initReports() {
  document.addEventListener("click", async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    // Bulk actions
    if (button.dataset.bulkAction) {
      await bulkReview(button.dataset.bulkAction);
      return;
    }
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
      let reason = null;

      if (status === "rejected") {
        // Mở dialog từ chối tùy chỉnh
        const rejectDialog = $("#reject-dialog");
        const reasonInput = $("#reject-reason");
        const charCount = $("#reject-char-count");
        const errorEl = $("#reject-error");
        const rejectForm = $("#reject-form");

        if (!rejectDialog || !reasonInput || !rejectForm) {
          console.error("Reject dialog elements not found");
          toast("Lỗi: không tìm thấy dialog từ chối.");
          return;
        }

        reasonInput.value = "";
        charCount.textContent = "0/240";
        errorEl.hidden = true;

        const result = await new Promise((resolve) => {
          let resolved = false;
          const doResolve = (val) => {
            if (resolved) return;
            resolved = true;
            rejectForm.removeEventListener("submit", onSubmit);
            rejectCancel.removeEventListener("click", onCancel);
            rejectDialog.removeEventListener("cancel", onCancel);
            reasonInput.removeEventListener("input", onInput);
            resolve(val);
          };

          const onSubmit = (e) => {
            e.preventDefault();
            const r = reasonInput.value.trim();
            if (!r) {
              errorEl.textContent = "Vui lòng nhập lý do từ chối.";
              errorEl.hidden = false;
              return;
            }
            if (r.length > 240) {
              errorEl.textContent = "Lý do từ chối tối đa 240 ký tự.";
              errorEl.hidden = false;
              return;
            }
            rejectDialog.close();
            doResolve(r);
          };
          const onCancel = () => {
            rejectDialog.close();
            doResolve(null);
          };
          const onInput = () => {
            const len = reasonInput.value.length;
            charCount.textContent = `${len}/240`;
            charCount.classList.toggle("near-limit", len > 220);
          };

          const rejectCancel = $("#reject-cancel");
          rejectForm.addEventListener("submit", onSubmit);
          rejectCancel.addEventListener("click", onCancel);
          rejectDialog.addEventListener("cancel", onCancel);
          reasonInput.addEventListener("input", onInput);

          rejectDialog.showModal();
        });

        if (!result) return;
        reason = result;
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
  // Tất cả filter đều render client-side tức thì (không fetch lại)
  $("#report-status-filter")?.addEventListener("change", renderReports);
  $("#report-search")?.addEventListener("input", renderReports);
  $("#report-severity-filter")?.addEventListener("change", renderReports);
  $("#report-date-from")?.addEventListener("change", renderReports);
  $("#report-date-to")?.addEventListener("change", renderReports);
  $("#only-pending-toggle")?.addEventListener("change", renderReports);
  // Bulk select all
  $("#bulk-select-all")?.addEventListener("change", (e) => {
    const checked = e.target.checked;
    $$("#reports-list input[type=checkbox][data-bulk-select]").forEach((c) => (c.checked = checked));
    updateBulkActions();
  });
  // Bulk action buttons
  $("#bulk-verify")?.addEventListener("click", () => bulkReview("verified"));
  $("#bulk-reject")?.addEventListener("click", () => bulkReview("rejected"));
  $("#bulk-resolve")?.addEventListener("click", () => bulkReview("resolved"));
}
