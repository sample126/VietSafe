/** Điều hướng giữa các trang (view). Nút `data-view="X"` hiện `<section id="X-view">`. */
import { ADMIN_VIEWS } from "./config.js";
import { map } from "./map.js";
import { authState, state } from "./state.js";
import { $$, toast } from "./utils.js";
import { updateAlertBanner } from "./views/alert-banner.js";
import { showForecastWorkspace } from "./views/forecast-workspace.js";
import { renderForecast } from "./views/forecast.js";
import { loadMyReports } from "./views/my-reports.js";
import { loadReports } from "./views/reports.js";

export function setView(view, forecastMode) {
  // Admin-only views
  if (
    ADMIN_VIEWS.includes(view) &&
    (!authState.user || authState.user.role !== "admin")
  ) {
    toast("Vui lòng đăng nhập tài khoản quản trị để truy cập.");
    return;
  }
  state.view = view;
  $$(".view").forEach((el) => (el.hidden = el.id !== view + "-view"));
  window.scrollTo({ top: 0, behavior: "instant" });
  $$(".nav-item[data-view]").forEach((el) =>
    el.classList.toggle("active", el.dataset.view === view),
  );
  if (view === "map") requestAnimationFrame(() => map.invalidateSize());
  if (view === "forecast" && state.data) renderForecast();
  if (view === "forecast") void showForecastWorkspace(forecastMode);
  if (view === "reports") loadReports();
  if (view === "my-reports") loadMyReports();
  // Banner chặn đường chỉ dành cho trang Bản đồ: cập nhật lại mỗi lần đổi view.
  updateAlertBanner();
}

export function initNavigation() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (button && button.dataset.view)
      setView(button.dataset.view, button.dataset.forecastMode);
  });
}
