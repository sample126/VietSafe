/** Trang "Phản ánh" (admin): danh sách, bộ lọc, duyệt / từ chối / đánh dấu đã xử lý, xuất dữ liệu. */
import { api, post } from "../api.js";
import { statuses, typeNames } from "../config.js";
import { refresh } from "../dashboard.js";
import { map, selectionLayer } from "../map.js";
import { setView } from "../navigation.js";
import { state } from "../state.js";
import { $, $$, esc, icon, toast, timeAgo } from "../utils.js";
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

const REPORTS_PAGE_SIZE = 10;

export function renderReports() {
  const filter = $("#report-status-filter")?.value || "all";
  const severityFilter = $("#report-severity-filter")?.value;
  const dateFrom = $("#report-date-from")?.value;
  const dateTo = $("#report-date-to")?.value;
  const query = normalizeSearch($("#report-search")?.value || "");
  const onlyPending = $("#only-pending-toggle")?.checked;
  const sortBy = $("#report-sort")?.value || "newest";

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
  let reports = state.reports
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
    );

  // Sort
  reports.sort((a, b) => {
    if (sortBy === "severity") return b.severity - a.severity;
    if (sortBy === "oldest") return a.created_at - b.created_at;
    // newest (default)
    return b.created_at - a.created_at;
  });

  // Phân trang: cắt theo trang hiện tại
  const totalPages = Math.max(1, Math.ceil(reports.length / REPORTS_PAGE_SIZE));
  if (state.reportsPage > totalPages) state.reportsPage = totalPages;
  if (state.reportsPage < 1) state.reportsPage = 1;
  const pageReports = reports.slice(
    (state.reportsPage - 1) * REPORTS_PAGE_SIZE,
    state.reportsPage * REPORTS_PAGE_SIZE,
  );

  $("#reports-list").innerHTML = pageReports.length
    ? pageReports.map((r) => renderReportCard(r)).join("")
    : `<div class="empty-state">${icon("report")}${query ? "Không tìm thấy phản ánh khớp với nội dung tìm kiếm." : state.reports.length ? "Chưa có phản ánh thuộc trạng thái này." : "Chưa có phản ánh tại máy."}</div>`;
  renderReportsPagination(totalPages, reports.length);
  updateBulkActions();
}

/** Tạo dãy số trang, rút gọn bằng "…" khi quá nhiều trang. */
function pageNumbersHtml(page, totalPages) {
  const pages = [...new Set([1, totalPages, page - 1, page, page + 1])]
    .filter((p) => p >= 1 && p <= totalPages)
    .sort((a, b) => a - b);
  let html = "";
  let prev = 0;
  for (const p of pages) {
    if (p - prev > 1) html += `<span class="page-ellipsis">…</span>`;
    html += `<button data-page="${p}" class="${p === page ? "active" : ""}" ${p === page ? 'aria-current="page"' : ""}>${p}</button>`;
    prev = p;
  }
  return html;
}

function renderReportsPagination(totalPages, totalItems) {
  const box = $("#reports-pagination");
  if (!box) return;
  if (totalPages <= 1) {
    box.innerHTML = "";
    return;
  }
  const page = state.reportsPage;
  box.innerHTML = `
    <div class="pagination-info">Trang ${page}/${totalPages} · ${totalItems} phản ánh</div>
    <div class="pagination">
      <button data-page="${page - 1}" ${page === 1 ? "disabled" : ""} aria-label="Trang trước">‹</button>
      ${pageNumbersHtml(page, totalPages)}
      <button data-page="${page + 1}" ${page === totalPages ? "disabled" : ""} aria-label="Trang sau">›</button>
    </div>`;
}

/** Đổi bộ lọc → về trang 1 rồi render. */
function resetPageAndRender() {
  state.reportsPage = 1;
  renderReports();
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
  // Color-coded severity
  const severityColor = report.severity === 3 ? "red" : report.severity === 2 ? "orange" : "green";
  const severityLabel = report.severity === 3 ? "Nghiêm trọng" : report.severity === 2 ? "Trung bình" : "Nhẹ";
  const actions =
    report.status === "pending"
      ? `<button class="approve" data-review-id="${id}" data-status="verified">Xác minh</button><button data-review-id="${id}" data-status="rejected">Từ chối</button>`
      : report.status === "verified"
        ? `<button class="approve" data-review-id="${id}" data-status="resolved">Đã xử lý</button>`
        : "";
  return `<article class="review-card">
    <div class="review-top">
      ${checkbox}
      <h3>${esc(report.address)} <span class="data-label">· ${typeNames[report.type]}</span></h3>
      <span class="tag tag-${report.status === "verified" ? "teal" : report.status === "pending" ? "orange" : "gray"}">${statuses[report.status]}</span>
      ${newBadge}
    </div>
    <p class="review-desc">${esc(report.description)}</p>
    <div class="review-meta">
      <span class="review-id">${id}</span>
      <span>${esc(report.road_id)}</span>
      <span class="severity-${severityColor}">Mức ${report.severity}/3</span>
      <span>${timeAgo(report.created_at)}</span>
    </div>
    ${report.media_url ? `<a href="${esc(report.media_url)}" target="_blank" rel="noopener"><img class="review-image" src="${esc(report.media_url)}" alt="Ảnh hiện trường"></a>` : ""}
    <div class="review-actions">${actions}<button data-report-map="${id}">Vị trí</button><button data-report-history="${id}" aria-expanded="false">Lịch sử</button></div>
    <div class="review-history" data-history-for="${id}" hidden></div>
  </article>`;
}

export function initReports() {
  document.addEventListener("click", async (e) => {
    const button = e.target.closest("button");
    if (!button) return;
    // Phân trang
    if (button.dataset.page) {
      const page = Number(button.dataset.page);
      if (page >= 1 && page !== state.reportsPage) {
        state.reportsPage = page;
        renderReports();
        $("#reports-list")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return;
    }
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
  // Nút "Làm mới" đã bỏ — auto-refresh 5s đủ để cập nhật
  // Tất cả filter đều render client-side tức thì (không fetch lại)
  $("#report-status-filter")?.addEventListener("change", resetPageAndRender);
  $("#report-search")?.addEventListener("input", resetPageAndRender);
  $("#report-severity-filter")?.addEventListener("change", resetPageAndRender);
  $("#report-date-from")?.addEventListener("change", resetPageAndRender);
  $("#report-date-to")?.addEventListener("change", resetPageAndRender);
  $("#only-pending-toggle")?.addEventListener("change", resetPageAndRender);
  $("#report-sort")?.addEventListener("change", resetPageAndRender);

  // Keyboard shortcuts: V=verify, R=reject, S=resolve, M=map
  document.addEventListener("keydown", (e) => {
    if (state.view !== "reports") return;
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
    const card = e.target.closest(".review-card");
    if (!card) return;
    const reviewId = card.querySelector("[data-review-id]")?.dataset?.reviewId;
    const status = card.querySelector("[data-review-id]")?.dataset?.status;
    if (!reviewId) return;
    if (e.key === "v" || e.key === "V") {
      e.preventDefault();
      if (status === "verified") return;
      const btn = card.querySelector('[data-review-id][data-status="verified"]');
      if (btn) btn.click();
    } else if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      if (status === "rejected") return;
      const btn = card.querySelector('[data-review-id][data-status="rejected"]');
      if (btn) btn.click();
    } else if (e.key === "s" || e.key === "S") {
      e.preventDefault();
      if (status === "resolved") return;
      const btn = card.querySelector('[data-review-id][data-status="resolved"]');
      if (btn) btn.click();
    } else if (e.key === "m" || e.key === "M") {
      e.preventDefault();
      const mapBtn = card.querySelector("[data-report-map]");
      if (mapBtn) mapBtn.click();
    }
  });
  // Bulk select từng thẻ: cập nhật thanh thao tác khi tick/bỏ tick
  document.addEventListener("change", (e) => {
    const box = e.target.closest("input[data-bulk-select]");
    if (box) updateBulkActions();
  });
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
