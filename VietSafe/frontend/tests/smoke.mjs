/**
 * Smoke test frontend: nạp các ES module THẬT của ứng dụng trong jsdom, nối vào backend Python
 * THẬT (DB tạm), rồi thao tác như người dùng: xem bản đồ, mở dự báo, tìm tuyến, đăng nhập admin,
 * mở trang phản ánh, đổi kịch bản, gửi yêu cầu cứu hộ.
 *
 * Mục đích: bắt lỗi "import thiếu/sai tên", vòng phụ thuộc, selector/id bị đổi, API đổi hình dạng.
 * Chạy: npm run test:frontend   (cần Python 3.10+ và `npm install`)
 */
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

const ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const FRONTEND = path.join(ROOT, "frontend");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const failures = [];
let passed = 0;
function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${name}`);
  } else {
    failures.push(name);
    console.log(`  FAIL ${name} ${detail}`);
  }
}
async function waitFor(fn, { timeout = 8000, label = "điều kiện" } = {}) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try {
      if (await fn()) return true;
    } catch {
      /* thử lại */
    }
    await sleep(60);
  }
  console.log(`  ... hết giờ chờ: ${label}`);
  return false;
}
const freePort = () =>
  new Promise((resolve) => {
    const s = net.createServer().listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });

// --- 1. Khởi động backend thật ---------------------------------------------------------
const port = await freePort();
const BASE = `http://127.0.0.1:${port}`;
const tmp = mkdtempSync(path.join(tmpdir(), "vietsafe-smoke-"));
const python = process.env.PYTHON || "python3";
const server = spawn(
  python,
  ["-m", "vietsafe", "--host", "127.0.0.1", "--port", String(port)],
  {
    cwd: path.join(ROOT, "backend"),
    env: { ...process.env, VIETSAFE_DB: path.join(tmp, "smoke.sqlite3") },
    stdio: ["ignore", "ignore", "pipe"],
  },
);
let serverErr = "";
server.stderr.on("data", (d) => (serverErr += d));
const cleanup = () => {
  server.kill();
  rmSync(tmp, { recursive: true, force: true });
};
process.on("exit", cleanup);

const ready = await waitFor(
  async () => (await fetch(`${BASE}/api/health`)).ok,
  {
    label: "backend khởi động",
  },
);
if (!ready) {
  console.error("Backend không khởi động được:\n" + serverErr);
  process.exit(1);
}

// --- 2. Dựng môi trường trình duyệt giả (jsdom) -------------------------------------------
const html = readFileSync(path.join(FRONTEND, "index.html"), "utf8");
const dom = new JSDOM(html, {
  url: BASE + "/",
  pretendToBeVisual: true,
  runScripts: "outside-only",
});
const { window } = dom;
for (const key of Object.getOwnPropertyNames(window)) {
  if (!(key in globalThis)) {
    Object.defineProperty(globalThis, key, {
      get: () => window[key],
      configurable: true,
    });
  }
}
for (const key of ["window", "document", "localStorage", "navigator"]) {
  Object.defineProperty(globalThis, key, {
    value: window[key] ?? window,
    configurable: true,
  });
}
// jsdom chưa cài đặt một số API trình duyệt mà ứng dụng/Leaflet dùng:
window.SVGElement.prototype.createSVGRect = () => ({});
window.Element.prototype.scrollIntoView = () => {};
window.scrollTo = () => {};
const confirmationMessages = [];
let confirmationDecision = true;
window.confirm = (message) => {
  confirmationMessages.push(message);
  return confirmationDecision;
};
const promptMessages = [];
let promptResult = "Thông tin chưa đủ để xác minh.";
window.prompt = (message) => {
  promptMessages.push(message);
  return promptResult;
};
window.matchMedia ??= () => ({
  matches: false,
  addEventListener() {},
  removeEventListener() {},
});
const dialogProto =
  window.HTMLDialogElement?.prototype ?? window.HTMLElement.prototype;
dialogProto.showModal = function () {
  this.setAttribute("open", "");
};
dialogProto.close = function () {
  this.removeAttribute("open");
};
// fetch của Node cần URL tuyệt đối; ứng dụng gọi đường dẫn tương đối như ở trình duyệt.
const nodeFetch = globalThis.fetch;
let reportFetchOverride = null;
let snapshotFetchOverride = null;
const reportRequestBodies = [];
globalThis.fetch = (url, opts) => {
  const absoluteUrl = String(url).startsWith("/") ? BASE + url : url;
  if (absoluteUrl === `${BASE}/api/reports` && opts?.method === "POST") {
    reportRequestBodies.push(JSON.parse(opts.body));
  }
  if (
    reportFetchOverride &&
    absoluteUrl === `${BASE}/api/reports` &&
    opts?.method === "POST"
  ) {
    return reportFetchOverride(absoluteUrl, opts);
  }
  if (
    snapshotFetchOverride &&
    absoluteUrl === `${BASE}/api/snapshot` &&
    (!opts?.method || opts.method === "GET")
  ) {
    const override = snapshotFetchOverride;
    snapshotFetchOverride = null;
    return override(absoluteUrl, opts);
  }
  return nodeFetch(absoluteUrl, opts);
};
// Leaflet là script cổ điển nạp bằng <script> trong index.html
window.eval(readFileSync(path.join(FRONTEND, "vendor/leaflet.js"), "utf8"));
globalThis.L = window.L;

const $ = (s) => window.document.querySelector(s);
const $$ = (s) => [...window.document.querySelectorAll(s)];
const click = (el) =>
  el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
const submit = (el) =>
  el.dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
const change = (el) =>
  el.dispatchEvent(new window.Event("change", { bubbles: true }));
const visible = (el) => el && !el.hidden;

// --- 3. Nạp ứng dụng thật ----------------------------------------------------------------
console.log("\n[1] Khởi động ứng dụng");
const url = (f) => pathToFileURL(path.join(FRONTEND, "js", f)).href;
let loadError = null;
try {
  await import(url("main.js"));
} catch (e) {
  loadError = e;
}
check(
  "tất cả module nạp được (không lỗi import / vòng phụ thuộc)",
  !loadError,
  String(loadError),
);
if (loadError) {
  console.error(loadError);
  process.exit(1);
}
const { state, authState } = await import(url("state.js"));
const mapModule = await import(url("map.js"));

const loaded = await waitFor(() => state.data, { label: "snapshot đầu tiên" });
check("lấy được snapshot từ API", loaded);
check("snapshot có 36 đoạn đường", state.data?.roads?.length === 36);
check(
  "thông báo prototype luôn phân biệt mô phỏng với phản ánh đã xác minh",
  $(".prototype-notice")?.textContent.includes(
    "không dùng cho quyết định đi đường",
  ) &&
    $(".prototype-notice")?.textContent.includes(
      "không phải dữ liệu quan trắc trực tiếp",
    ) &&
    $(".prototype-notice")?.textContent.includes("phản ánh đã xác minh"),
);
check(
  "thẻ thống kê được điền",
  /\d/.test($("#stat-flood").textContent),
  $("#stat-flood").textContent,
);
check(
  "nhãn bản đồ và thời tiết nói rõ dữ liệu mô phỏng",
  $(".map-title").textContent.includes("Mạng đường mô phỏng") &&
    $("#weather-caption").textContent.includes("Mô phỏng:"),
);
check("danh sách sự kiện có phần tử", $$("#event-list button").length > 0);
check(
  "bản đồ vẽ đủ lớp đoạn đường",
  mapModule.roadLayer?.getLayers().length >= 36,
  `roadLayer=${mapModule.roadLayer?.getLayers().length}`,
);
check(
  "thẻ 'Nhìn trước hành trình' được điền",
  $("#insight-road").textContent.trim().length > 0,
);
check("ô tìm tuyến có danh sách điểm", $("#route-origin").options.length > 2);

console.log("\n[2] Điều hướng & dự báo");
click($('[data-view="forecast"]'));
check(
  "mở trang Dự báo",
  visible($("#forecast-view")) && !visible($("#map-view")),
);
check(
  "biểu đồ dự báo được vẽ",
  $("#forecast-chart").innerHTML.includes("<svg"),
);
check(
  "dự báo gắn nhãn mô phỏng và AI nghiên cứu không phát cảnh báo",
  $("#forecast-chart").textContent.includes("không phải số đo hiện trường") &&
    $("#forecast-view .section-title p")
      .textContent.replace(/\s+/g, " ")
      .includes("không phát cảnh báo công khai"),
);
click($('[data-view="rescue"]'));
check("mở trang Ứng cứu", visible($("#rescue-view")));
click($('[data-view="map"]'));
check("quay lại trang Bản đồ", visible($("#map-view")));

console.log("\n[3] Tìm tuyến");
click($("#open-route"));
check(
  "mở bảng tìm tuyến",
  visible($("#route-panel")) && !visible($("#event-panel")),
);
$("#route-origin").value = "caugiay";
$("#route-destination").value = "hoankiem";
submit($("#route-form"));
check(
  "nhận và hiển thị kết quả tuyến",
  (await waitFor(() => $$("#route-results .route-choice").length > 0, {
    label: "kết quả tuyến",
  })) &&
    $("#route-results").textContent.includes("Minh họa") &&
    $("#route-results").textContent.includes("Không phải chỉ dẫn đi đường"),
);
click($("#close-route"));
check(
  "đóng bảng tìm tuyến",
  !visible($("#route-panel")) && visible($("#event-panel")),
);

console.log("\n[4] Đăng nhập & phân quyền");
check("ban đầu là khách", authState.user === null);
click($("#auth-button"));
check("mở hộp thoại đăng nhập", $("#login-dialog").hasAttribute("open"));
$("#login-username").value = "admin";
$("#login-password").value = "sai-mat-khau";
submit($("#login-form"));
check(
  "sai mật khẩu -> báo lỗi",
  await waitFor(() => $("#login-error").textContent.trim().length > 0, {
    label: "báo lỗi",
  }),
);
$("#login-password").value = "vietsafe2026";
submit($("#login-form"));
check(
  "đăng nhập admin thành công",
  await waitFor(() => authState.user?.role === "admin", { label: "đăng nhập" }),
);
check(
  "token được lưu vào localStorage",
  Boolean(localStorage.getItem("vietsafe_token")),
);
check(
  "menu admin hiện ra",
  $$(".admin-only").length > 0 && $$(".admin-only").every((el) => !el.hidden),
);

console.log("\n[5] Trang quản trị");
click($('[data-view="reports"]'));
check("mở trang Phản ánh (admin)", visible($("#reports-view")));
check("ẩn nút gửi phản ánh trên trang admin", $("#open-report").hidden);
check(
  "danh sách phản ánh được vẽ",
  await waitFor(() => $("#reports-list").innerHTML.trim().length > 0, {
    label: "danh sách phản ánh",
  }),
);
const { renderReports } = await import(url("views/reports.js"));
const originalReports = state.reports;
const sampleReport = (id, status, created_at) => ({
  id,
  status,
  created_at,
  address: id,
  type: "flood",
  description: id,
  road_id: "HN-001",
  severity: 1,
  lat: 21,
  lng: 105,
});
state.reports = [
  sampleReport("R-PENDING-OLD", "pending", 100),
  sampleReport("R-VERIFIED", "verified", 300),
  sampleReport("R-PENDING-NEW", "pending", 200),
];
state.reports[0].address = "Cầu Giấy";
state.reports[0].description = "Nước ngập";
state.reports[0].media_url = "/api/report-media/R-PENDING-OLD";
state.reports[2].address = "Đường Láng";
state.reports[2].description = "Ùn tắc";
renderReports();
const sortedReportIds = $$("#reports-list .review-meta").map(
  (el) => el.textContent.split(" · ")[0],
);
check(
  "xếp phản ánh chờ xác minh trước và mới nhất lên đầu",
  sortedReportIds.join(",") === "R-PENDING-NEW,R-PENDING-OLD,R-VERIFIED",
);
const oldPendingCard = $$("#reports-list .review-card").find((card) =>
  card.textContent.includes("R-PENDING-OLD"),
);
check(
  "mỗi thẻ làm rõ nguồn người gửi và bằng chứng đính kèm",
  oldPendingCard?.textContent.includes(
    "Nguồn: Phản ánh cộng đồng do người dùng gửi",
  ) &&
    oldPendingCard.textContent.includes(
      "Bằng chứng: Mô tả người gửi · Có ảnh đính kèm",
    ) &&
    Boolean(
      oldPendingCard.querySelector(
        'img[alt="Ảnh hiện trường do người dùng cung cấp"]',
      ),
    ),
);
const statusCounts = Object.fromEntries(
  $$("#report-status-counts [data-status]").map((el) => [
    el.dataset.status,
    Number(el.querySelector("strong").textContent),
  ]),
);
check(
  "hiển thị tổng số và số lượng từng trạng thái",
  statusCounts.total === 3 &&
    statusCounts.pending === 2 &&
    statusCounts.verified === 1 &&
    statusCounts.resolved === 0,
);
$("#report-search").value = "cau giay";
$("#report-search").dispatchEvent(new window.Event("input", { bubbles: true }));
check(
  "tìm phản ánh theo địa chỉ không phân biệt dấu",
  $$("#reports-list .review-meta").length === 1 &&
    $("#reports-list .review-meta").textContent.startsWith("R-PENDING-OLD"),
);
$("#report-status-filter").value = "verified";
change($("#report-status-filter"));
check(
  "tìm kiếm kết hợp với bộ lọc trạng thái",
  $("#reports-list").textContent.includes(
    "Không tìm thấy phản ánh khớp với nội dung tìm kiếm.",
  ),
);
$("#report-search").value = "";
$("#report-search").dispatchEvent(new window.Event("input", { bubbles: true }));
$("#report-status-filter").value = "all";
change($("#report-status-filter"));
state.reports = originalReports;
renderReports();
click($('[data-view="sources"]'));
check("mở trang Nguồn dữ liệu", visible($("#sources-view")));
check("thẻ nguồn dữ liệu được vẽ", $$("#source-grid .source-card").length >= 5);
$("#source-scenario").value = "storm";
change($("#source-scenario"));
check(
  "đổi kịch bản -> snapshot cập nhật (mưa 55 mm/h)",
  await waitFor(() => state.data?.rainfall === 55, { label: "đổi kịch bản" }),
);

console.log(
  "\n[5b] Luồng phản ánh: gửi -> admin duyệt -> bản đồ đổi trạng thái",
);
const node0 = state.data.nodes.find((n) => n.name);
click($("#open-report"));
check("mở hộp thoại gửi phản ánh", $("#report-dialog").hasAttribute("open"));
check(
  "không cần GPS nếu nhập địa chỉ, bước xác nhận đã được bỏ",
  !$("#report-location-confirm") &&
    !$("#report-location-confirm-hint") &&
    !state.reportPosition,
);
check(
  "chỉ còn lựa chọn vị trí của tôi bằng GPS",
  $("#report-gps").textContent.includes("Vị trí của tôi") &&
    !$("#report-pick") &&
    !$("#report-find"),
);
check(
  "biểu mẫu có nút chụp ảnh và chọn ảnh",
  $("#report-take-photo") && $("#report-choose-image"),
);
check(
  "nút chụp ảnh mở bộ chọn camera phía sau",
  $("#report-camera").getAttribute("capture") === "environment",
);
const reportPhoto = new window.File(["ảnh thử nghiệm"], "hien-truong.jpg", {
  type: "image/jpeg",
});
Object.defineProperty($("#report-camera"), "files", {
  configurable: true,
  value: [reportPhoto],
});
change($("#report-camera"));
check(
  "ảnh chụp được nhận vào biểu mẫu",
  $("#report-image-status").textContent.includes("hien-truong.jpg"),
);
click($("#report-remove-image"));
check(
  "có thể xóa ảnh đã chọn",
  $("#report-image-status").textContent === "Chưa có ảnh được thêm." &&
    $("#report-remove-image").hidden,
);
Object.defineProperty(window.navigator, "geolocation", {
  configurable: true,
  value: {
    getCurrentPosition(onSuccess) {
      onSuccess({
        coords: { latitude: node0.lat, longitude: node0.lng },
      });
    },
  },
});
click($("#report-gps"));
check(
  "xác định tọa độ phản ánh bằng GPS",
  state.reportPosition?.lat === node0.lat &&
    state.reportPosition?.lng === node0.lng &&
    /Lấy lúc \d{1,2}:\d{2}/.test($("#report-coordinates").textContent),
);
$("#report-dialog").close();
click($("#open-report"));
check(
  "mở lại biểu mẫu vẫn cho dùng địa chỉ thay GPS",
  !$("#report-location-confirm") &&
    $("#report-coordinates").textContent.includes("Lấy lúc"),
);
$("#report-address").value = node0.name;
$("#report-severity").value = "3";
$("#report-description").value = "Nước ngập sâu, xe máy không thể đi qua được.";
let rejectPendingReport;
let reportRequestCount = 0;
const savedReportPosition = state.reportPosition;
state.reportPosition = null;
$("#report-address").value = "";
submit($("#report-form"));
check(
  "chặn gửi nếu chưa có GPS và cũng chưa nhập địa chỉ",
  !$("#report-error").hidden &&
    $("#report-error").textContent.includes("nhập địa chỉ") &&
    reportRequestCount === 0,
);
state.reportPosition = savedReportPosition;
$("#report-address").value = node0.name;
$("#report-address").value = `${node0.name} (gần cổng)`;
$("#report-address").dispatchEvent(
  new window.Event("input", { bubbles: true }),
);
check(
  "có thể chỉnh địa chỉ mà không cần bước xác nhận bổ sung",
  !$("#report-location-confirm") &&
    $("#report-address").value === `${node0.name} (gần cổng)`,
);
$("#report-address").value = node0.name;
$("#report-address").dispatchEvent(
  new window.Event("input", { bubbles: true }),
);
reportFetchOverride = () => {
  reportRequestCount += 1;
  return new Promise((resolve, reject) => {
    rejectPendingReport = reject;
  });
};
const retryPhoto = new window.File(
  [Uint8Array.of(0xff, 0xd8, 0xff)],
  "vi-tri-ngap.jpg",
  { type: "image/jpeg" },
);
Object.defineProperty($("#report-camera"), "files", {
  configurable: true,
  value: [retryPhoto],
});
change($("#report-camera"));
submit($("#report-form"));
const reportButton = $("#submit-report");
check(
  "hiển thị trạng thái đang gửi và khóa nút gửi",
  await waitFor(
    () =>
      reportButton.disabled &&
      reportButton.getAttribute("aria-busy") === "true" &&
      $("#report-submit-status").textContent.includes("Đang gửi"),
    { label: "trạng thái gửi phản ánh" },
  ),
);
submit($("#report-form"));
check(
  "không gửi lặp khi đang chờ phản hồi máy chủ",
  await waitFor(() => reportRequestCount === 1, {
    label: "ngăn gửi phản ánh lặp",
  }),
);
rejectPendingReport(new TypeError("Failed to fetch"));
check(
  "lỗi mạng hướng dẫn thử lại và giữ nguyên nội dung",
  await waitFor(
    () =>
      !reportButton.disabled &&
      $("#report-submit-status").hidden &&
      !$("#report-error").hidden &&
      $("#report-error").textContent.includes("thử lại") &&
      $("#report-dialog").hasAttribute("open") &&
      $("#report-description").value ===
        "Nước ngập sâu, xe máy không thể đi qua được." &&
      $("#report-address").value === node0.name &&
      $("#report-image-status").textContent.includes("vi-tri-ngap.jpg") &&
      state.reportPosition?.lat === node0.lat &&
      reportButton.textContent.includes("Gửi phản ánh"),
    { label: "hướng dẫn thử lại khi mất mạng" },
  ),
);
rejectPendingReport = null;
reportFetchOverride = () =>
  new Promise((resolve, reject) => {
    rejectPendingReport = reject;
  });
submit($("#report-form"));
check(
  "máy chủ phản hồi chậm cũng hướng dẫn thử lại",
  await waitFor(() => reportButton.disabled && Boolean(rejectPendingReport), {
    label: "chờ phản hồi máy chủ chậm",
  }),
);
rejectPendingReport(new Error("Máy chủ phản hồi chậm. Hãy thử lại."));
check(
  "lỗi máy chủ chậm vẫn giữ ảnh, địa chỉ và vị trí",
  await waitFor(
    () =>
      !reportButton.disabled &&
      !$("#report-error").hidden &&
      $("#report-error").textContent.includes("kiểm tra mạng") &&
      $("#report-description").value ===
        "Nước ngập sâu, xe máy không thể đi qua được." &&
      $("#report-address").value === node0.name &&
      $("#report-image-status").textContent.includes("vi-tri-ngap.jpg") &&
      state.reportPosition?.lat === node0.lat,
    { label: "giữ dữ liệu sau timeout" },
  ),
);
reportFetchOverride = null;
snapshotFetchOverride = () =>
  Promise.resolve(
    new Response(JSON.stringify({ error: "Tạm mất kết nối" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    }),
  );
submit($("#report-form"));
check(
  "gửi lại thành công với ảnh, vị trí và nội dung được giữ nguyên",
  await waitFor(
    () =>
      reportRequestBodies.length === 3 &&
      reportRequestBodies[2].image?.startsWith("data:image/jpeg;base64,") &&
      reportRequestBodies[2].lat === node0.lat &&
      reportRequestBodies[2].lng === node0.lng &&
      reportRequestBodies[2].description ===
        "Nước ngập sâu, xe máy không thể đi qua được." &&
      $("#toast").textContent.includes(
        "Phản ánh đã được gửi và lưu thành công",
      ),
    { label: "gửi lại phản ánh sau khi có mạng" },
  ),
);
check(
  "lỗi cập nhật bản đồ không làm mất báo gửi thành công",
  await waitFor(
    () =>
      $("#connection-error").hidden === false &&
      $("#toast").textContent.includes("Bản đồ chưa cập nhật được"),
    { label: "thông báo riêng lỗi cập nhật bản đồ" },
  ),
);
click($('[data-view="reports"]'));
const reviewBtn = () => $('[data-review-id][data-status="verified"]');
check(
  "admin thấy nút 'xác minh'",
  await waitFor(reviewBtn, { label: "nút xác minh" }),
);
const reportId = reviewBtn().dataset.reviewId;
confirmationDecision = false;
click(reviewBtn());
check(
  "hủy xác minh thì không thay đổi phản ánh",
  state.reports.find((r) => r.id === reportId)?.status === "pending" &&
    !reviewBtn().disabled &&
    confirmationMessages.at(-1).includes("kiểm tra mô tả, vị trí và ảnh"),
);
confirmationDecision = true;
click(reviewBtn());
check(
  "xác minh -> đường bị chặn trên snapshot (nguồn local_report)",
  await waitFor(
    () =>
      state.data.roads.some((r) => r.origin === "local_report" && r.blocked),
    {
      label: "snapshot phản ánh verified",
    },
  ),
);
check(
  "trạng thái phản ánh là 'verified'",
  state.reports.find((r) => r.id === reportId)?.status === "verified",
);
check(
  "xác minh có thông báo thành công rõ ràng",
  $("#toast").textContent.includes("Đã xác minh phản ánh."),
);
click($(`[data-review-id="${reportId}"][data-status="resolved"]`));
check(
  "đánh dấu đã xử lý có xác nhận và cập nhật thành công",
  await waitFor(
    () =>
      state.reports.find((r) => r.id === reportId)?.status === "resolved" &&
      $("#toast").textContent.includes("Đã đánh dấu phản ánh là đã xử lý.") &&
      confirmationMessages.at(-1).includes("đánh dấu phản ánh này là đã xử lý"),
    { label: "xác nhận và cập nhật đã xử lý" },
  ),
);
const citizenLoginResponse = await nodeFetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-VietSafe": "local",
    Origin: BASE,
  },
  body: JSON.stringify({ username: "nguoidan", password: "matkhau123" }),
});
const citizenToken = (await citizenLoginResponse.json()).token;
const newReportResponse = await nodeFetch(`${BASE}/api/reports`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-VietSafe": "local",
    "X-VietSafe-Session": citizenToken,
    Origin: BASE,
  },
  body: JSON.stringify({
    type: "flood",
    severity: 2,
    lat: node0.lat,
    lng: node0.lng,
    address: node0.name,
    description: "Phản ánh thứ hai để kiểm thử lý do từ chối.",
  }),
});
const rejectionTarget = await newReportResponse.json();
await import(url("views/reports.js")).then(({ loadReports }) => loadReports());
const rejectButton = () =>
  $(`[data-review-id="${rejectionTarget.id}"][data-status="rejected"]`);
check(
  "từ chối yêu cầu nhập lý do và xác nhận thao tác",
  await waitFor(rejectButton, { label: "nút từ chối mới" }),
);
confirmationDecision = false;
click(rejectButton());
check(
  "hủy xác nhận từ chối giữ nguyên trạng thái",
  state.reports.find((r) => r.id === rejectionTarget.id)?.status ===
    "pending" && promptMessages.at(-1).includes("lý do từ chối"),
);
confirmationDecision = true;
click(rejectButton());
check(
  "lý do từ chối được lưu và hiển thị trong lịch sử",
  await waitFor(
    () =>
      state.reports.find((r) => r.id === rejectionTarget.id)?.status ===
        "rejected" && $("#toast").textContent.includes("Đã từ chối phản ánh."),
    { label: "từ chối có lý do" },
  ),
);
const historyButton = () => $(`[data-report-history="${rejectionTarget.id}"]`);
click(historyButton());
check(
  "lịch sử hiển thị thời điểm và lý do từ chối",
  await waitFor(
    () =>
      $(`[data-history-for="${rejectionTarget.id}"]`).textContent.includes(
        "Thông tin chưa đủ để xác minh.",
      ) &&
      $(`[data-history-for="${rejectionTarget.id}"]`).textContent.includes(
        "Đã từ chối",
      ) &&
      $(`[data-history-for="${rejectionTarget.id}"]`).textContent.includes(
        "Tiếp nhận phản ánh",
      ) &&
      Boolean($(`[data-history-for="${rejectionTarget.id}"] time`)),
    { label: "lịch sử báo cáo có từ chối" },
  ),
  $(`[data-history-for="${rejectionTarget.id}"]`).textContent,
);
click($('[data-view="map"]'));
click($("#open-report"));
$("#report-address").value = "Cầu Giấy";
$("#report-description").value =
  "Địa chỉ thủ công trong thử nghiệm, không dùng GPS.";
state.reportPosition = null;
reportFetchOverride = () =>
  Promise.resolve(
    new Response(
      JSON.stringify({
        id: "R-MANUAL-ADDRESS",
        status: "pending",
        location_source: "address",
        resolved_place: "Cầu Giấy",
      }),
      { status: 201, headers: { "Content-Type": "application/json" } },
    ),
  );
submit($("#report-form"));
check(
  "gửi phản ánh chỉ với địa chỉ mà không gửi tọa độ GPS",
  await waitFor(
    () =>
      reportRequestBodies.length === 4 &&
      !("lat" in reportRequestBodies[3]) &&
      !("lng" in reportRequestBodies[3]) &&
      reportRequestBodies[3].address === "Cầu Giấy" &&
      $("#toast").textContent.includes("vị trí ước tính"),
    { label: "gửi phản ánh bằng địa chỉ" },
  ),
);
reportFetchOverride = null;

console.log("\n[6] Ứng cứu");
click($('[data-view="rescue"]'));
const rescueListLoaded = await waitFor(
  () => $$("#rescue-service-list .rescue-card[data-rescue-service]").length > 0,
  { label: "danh sách cứu hộ từ JSON" },
);
check(
  "nguyên tắc vàng thu gọn mặc định và vẫn hiện lời nhắc chính",
  !$(".safety-box").open &&
    $(".safety-box-preview").textContent.includes("không đề nổ lại"),
);
click($(".safety-box-toggle"));
check(
  "mở khung để xem đủ bốn nguyên tắc",
  $(".safety-box").open && $$(".safety-box li").length === 4,
);
click($(".safety-box-toggle"));
check("có thể thu gọn khung nguyên tắc vàng", !$(".safety-box").open);
check(
  "biểu tượng khiên nằm trong khung nguyên tắc, không che danh sách",
  $(".safety-box-heading svg use").getAttribute("href") === "#i-shield" &&
    !$("#safety-quick-access") &&
    !document.querySelector(".safety-quick-access"),
);
$(".safety-box").open = false;
check(
  "danh sách cứu hộ có khung cuộn truy cập được bằng bàn phím",
  $("#rescue-service-list").tabIndex === 0 &&
    $("#rescue-service-list").getAttribute("aria-label").includes("cuộn"),
);
const rescueCards = $$(".rescue-card[data-rescue-service]");
const rescueDataResponse = await fetch(`${BASE}/data/rescue-services.json`);
const rescueData = rescueDataResponse.ok ? await rescueDataResponse.json() : [];
check("tệp JSON danh sách cứu hộ được phục vụ", rescueDataResponse.ok);
check(
  "thẻ cứu hộ được dựng từ dữ liệu JSON",
  rescueListLoaded &&
    rescueCards.length === rescueData.length &&
    rescueData.every((service) =>
      rescueCards.some(
        (card) =>
          card.dataset.rescueService === service.vehicle &&
          card.querySelector("h4").textContent === service.name,
      ),
    ),
);
check(
  "có chín mục, gồm sáu dữ liệu mẫu và ba mục chưa xác minh",
  rescueData.length === 9 &&
    rescueData.filter((service) => service.simulated === true).length === 6 &&
    rescueData.filter((service) => service.verified === false).length === 9,
);
check(
  "dữ liệu mẫu được cảnh báo rõ và không thể gọi",
  rescueData.filter((service) => service.simulated === true).length === 6 &&
    new Set(
      rescueData
        .filter((service) => service.simulated === true)
        .map((service) => service.hotline),
    ).size === 6 &&
    rescueCards
      .filter((card) => rescueData[Number(card.dataset.rescueIndex)].simulated)
      .every(
        (card) =>
          card.querySelector(".rescue-card-call")?.disabled &&
          card
            .querySelector(".rescue-card-call")
            .textContent.includes("Thông tin mẫu") &&
          !card.querySelector('a[href^="tel:"]'),
      ),
);
check(
  "các mục chưa xác minh được cảnh báo và không cung cấp liên kết liên hệ",
  rescueCards
    .filter((card) => !rescueData[Number(card.dataset.rescueIndex)].simulated)
    .every(
      (card) =>
        card
          .querySelector(".rescue-demo-notice")
          ?.textContent.includes("chưa được xác minh") &&
        card.querySelector(".rescue-verification-label")?.textContent ===
          "Chưa xác minh" &&
        card.querySelector(".rescue-card-call")?.disabled &&
        !card.querySelector('a[href^="tel:"]') &&
        !card.querySelector(".service-link[href]"),
    ),
);
check(
  "danh sách cứu hộ không còn hàng hotline trùng",
  !$(".rescue-hotline-bar"),
);
check(
  "chỉ đơn vị đã xác minh mới có nút gọi hoạt động",
  rescueCards.length > 0 &&
    rescueCards.every(
      (card) =>
        card.querySelectorAll('a[href^="tel:"]').length ===
        (rescueData[Number(card.dataset.rescueIndex)].verified ? 1 : 0),
    ),
);
check(
  "thông tin dịch vụ mở rộng đóng mặc định",
  rescueCards.every((card) => !card.querySelector("details")?.open),
);
check(
  "chi tiết chỉ hiển thị khu vực, địa chỉ, giờ và chi phí",
  rescueCards.length === rescueData.length &&
    rescueCards.every((card) => {
      const details = card.querySelector(".rescue-card-details");
      const facts = [...details.querySelectorAll(".rescue-service-fact")];
      return (
        ["Khu vực", "Địa chỉ", "Thời gian", "Chi phí"].every((label) =>
          facts.some(
            (fact) => fact.querySelector("strong")?.textContent === label,
          ),
        ) &&
        !facts.some((fact) =>
          ["Độ chính xác", "Bản đồ"].includes(
            fact.querySelector("strong")?.textContent,
          ),
        ) &&
        !details.querySelector('a[href^="https://www.google.com/maps/search/"]')
      );
    }),
);
check(
  "mỗi đơn vị có tọa độ tham chiếu hợp lệ",
  rescueData.length === rescueCards.length &&
    rescueData.every(
      (service) =>
        Number.isFinite(service.referenceLat) &&
        Number.isFinite(service.referenceLng) &&
        service.referenceNote,
    ),
);
check(
  "tìm cứu hộ không yêu cầu người dùng nhập tọa độ",
  !$("#rescue-origin-lat") &&
    !$("#rescue-origin-lng") &&
    !$("#rescue-sort-coordinates") &&
    $("#rescue-distance-status").textContent === "",
);
Object.defineProperty(window, "isSecureContext", {
  configurable: true,
  value: false,
});
let gpsRequestCount = 0;
const geolocation = {
  getCurrentPosition(onSuccess) {
    gpsRequestCount += 1;
    onSuccess({
      coords: {
        latitude: motorbikeReference?.referenceLat,
        longitude: motorbikeReference?.referenceLng,
        accuracy: 24,
      },
    });
  },
};
Object.defineProperty(window.navigator, "geolocation", {
  configurable: true,
  value: geolocation,
});
click($("#rescue-sort-gps"));
check(
  "không gọi GPS qua HTTP không an toàn và hướng dẫn dùng HTTPS",
  gpsRequestCount === 0 &&
    $("#rescue-distance-status").textContent.includes("HTTPS"),
);
Object.defineProperty(window, "isSecureContext", {
  configurable: true,
  value: true,
});
const motorbikeReference = rescueData.find(
  (service) => service.vehicle === "motorbike",
);
geolocation.getCurrentPosition = (onSuccess) => {
  gpsRequestCount += 1;
  onSuccess({
    coords: {
      latitude: motorbikeReference.referenceLat,
      longitude: motorbikeReference.referenceLng,
      accuracy: 24,
    },
  });
};
click($("#rescue-sort-gps"));
check(
  "dùng GPS nhận tọa độ và tự sắp xếp cứu hộ gần nhất lên đầu",
  $("#rescue-service-list .rescue-card").dataset.rescueService ===
    "motorbike" &&
    $("#rescue-distance-status").textContent.includes("đã được sắp xếp") &&
    $("#rescue-distance-status").textContent.includes("24 m") &&
    $("#rescue-distance-status").textContent.includes("ước tính"),
);
check(
  "hiển thị khoảng cách ước tính sau khi lấy GPS",
  rescueCards.every(
    (card) =>
      !card.querySelector(".rescue-distance-label").hidden &&
      card.querySelector(".rescue-distance-label").textContent.includes("km"),
  ),
);
$("#rescue-origin-address").value = "Ngã Tư Sở";
click($("#rescue-search-address"));
check(
  "nhập địa điểm tìm được sắp xếp cứu hộ và điền địa chỉ yêu cầu",
  (await waitFor(
    () =>
      $("#rescue-distance-status").textContent.includes("địa điểm Ngã Tư Sở"),
    { label: "tìm địa điểm cứu hộ" },
  )) &&
    $("#rescue-address").value === "Ngã Tư Sở" &&
    $("#rescue-distance-status").textContent.includes("ước tính") &&
    rescueCards.every(
      (card) => !card.querySelector(".rescue-distance-label").hidden,
    ),
);
$("#rescue-origin-address").value = "Cầu Giấy";
click($("#rescue-search-address"));
check(
  "địa điểm trùng tên yêu cầu nhập cụ thể hơn mà không báo thành công",
  (await waitFor(
    () =>
      $("#rescue-distance-status").textContent.includes(
        "Có nhiều địa điểm phù hợp",
      ),
    { label: "xử lý địa điểm mơ hồ" },
  )) &&
    $("#rescue-distance-status").textContent.includes(
      "Vị trí đang dùng chưa thay đổi",
    ),
);
$("#rescue-origin-address").value = "dia-diem-khong-ton-tai-vietsafe";
click($("#rescue-search-address"));
check(
  "địa điểm không tìm thấy hiển thị hướng dẫn rõ ràng",
  (await waitFor(
    () =>
      $("#rescue-distance-status").textContent.includes(
        "Không tìm thấy địa điểm",
      ),
    { label: "địa điểm không tồn tại" },
  )) &&
    $("#rescue-distance-status").textContent.includes(
      "Vị trí đang dùng chưa thay đổi",
    ),
);
$("#rescue-vehicle").value = "motorbike";
$("#rescue-address").value = "Phố Giảng Võ";
$("#rescue-phone").value = "0900000000";
submit($("#rescue-request-form"));
check(
  "form cứu hộ cảnh báo rằng bản demo không gửi yêu cầu",
  (await waitFor(() => $("#rescue-form-result").innerHTML.trim().length > 0, {
    label: "kết quả yêu cầu cứu hộ",
  })) &&
    $("#rescue-form-result").textContent.includes("yêu cầu chưa được gửi") &&
    !$("#rescue-form-result").querySelector('a[href^="tel:"]') &&
    !$("#rescue-form-result").textContent.includes($("#rescue-phone").value),
);

console.log("\n[7] Đăng xuất");
click($("#logout-button"));
check(
  "đăng xuất xóa phiên",
  (await waitFor(() => authState.user === null, { label: "đăng xuất" })) &&
    !localStorage.getItem("vietsafe_token"),
);

console.log(`\n${passed} đạt, ${failures.length} lỗi`);
if (serverErr.includes("Traceback")) {
  console.log("\nBackend ghi lỗi:\n" + serverErr);
  failures.push("backend traceback");
}
cleanup();
process.exit(failures.length ? 1 : 0);
