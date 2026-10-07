/**
 * Điểm vào của frontend (nạp bởi index.html bằng <script type="module">).
 * Thứ tự: gắn sự kiện cho các thành phần -> khởi tạo bản đồ -> kiểm tra đăng nhập -> vòng cập nhật.
 */
import { checkAuth, initAuth } from "./auth.js";
import { REFRESH_INTERVAL_MS } from "./config.js";
import { initDialogs } from "./dialogs.js";
import { refresh } from "./dashboard.js";
import { initMapControls } from "./map-controls.js";
import { initializeMap } from "./map.js";
import { initNavigation } from "./navigation.js";
import { $ } from "./utils.js";
import { initAlertBanner } from "./views/alert-banner.js";
import { initEventsPanel } from "./views/events-panel.js";
import { initForecast } from "./views/forecast.js";
import { initReportForm } from "./views/report-form.js";
import { initReports } from "./views/reports.js";
import { initRescue } from "./views/rescue.js";
import { initRoadDetails } from "./views/road-details.js";
import { initRouting } from "./views/routing.js";
import { initSearch } from "./views/search.js";
import { initSources } from "./views/sources.js";

function initListeners() {
  initNavigation();
  initDialogs();
  initMapControls();
  initEventsPanel();
  initRoadDetails();
  initSearch();
  initRouting();
  initForecast();
  initSources();
  initReportForm();
  initReports();
  initRescue();
  initAlertBanner();
  initAuth();
}

initListeners();

if (typeof L === "undefined") {
  $("#connection-error").hidden = false;
  $("#connection-error").textContent =
    "Thiếu thư viện bản đồ local. Kiểm tra thư mục frontend/vendor.";
} else {
  initializeMap();
  checkAuth();
  refresh();
  setInterval(refresh, REFRESH_INTERVAL_MS);
}
