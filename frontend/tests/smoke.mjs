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

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
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
const server = spawn(python, ["-m", "vietsafe", "--host", "127.0.0.1", "--port", String(port)], {
  cwd: path.join(ROOT, "backend"),
  env: { ...process.env, VIETSAFE_DB: path.join(tmp, "smoke.sqlite3") },
  stdio: ["ignore", "ignore", "pipe"],
});
let serverErr = "";
server.stderr.on("data", (d) => (serverErr += d));
const cleanup = () => {
  server.kill();
  rmSync(tmp, { recursive: true, force: true });
};
process.on("exit", cleanup);

const ready = await waitFor(async () => (await fetch(`${BASE}/api/health`)).ok, {
  label: "backend khởi động",
});
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
    Object.defineProperty(globalThis, key, { get: () => window[key], configurable: true });
  }
}
for (const key of ["window", "document", "localStorage"]) {
  Object.defineProperty(globalThis, key, { value: window[key] ?? window, configurable: true });
}
// jsdom chưa cài đặt một số API trình duyệt mà ứng dụng/Leaflet dùng:
window.SVGElement.prototype.createSVGRect = () => ({});
window.Element.prototype.scrollIntoView = () => {};
window.scrollTo = () => {};
window.matchMedia ??= () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
const dialogProto = window.HTMLDialogElement?.prototype ?? window.HTMLElement.prototype;
dialogProto.showModal = function () {
  this.setAttribute("open", "");
};
dialogProto.close = function () {
  this.removeAttribute("open");
};
// fetch của Node cần URL tuyệt đối; ứng dụng gọi đường dẫn tương đối như ở trình duyệt.
const nodeFetch = globalThis.fetch;
globalThis.fetch = (url, opts) => nodeFetch(String(url).startsWith("/") ? BASE + url : url, opts);
// Leaflet là script cổ điển nạp bằng <script> trong index.html
window.eval(readFileSync(path.join(FRONTEND, "vendor/leaflet.js"), "utf8"));
globalThis.L = window.L;

const $ = (s) => window.document.querySelector(s);
const $$ = (s) => [...window.document.querySelectorAll(s)];
const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
const submit = (el) =>
  el.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
const change = (el) => el.dispatchEvent(new window.Event("change", { bubbles: true }));
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
check("tất cả module nạp được (không lỗi import / vòng phụ thuộc)", !loadError, String(loadError));
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
  "thẻ thống kê được điền",
  /\d/.test($("#stat-flood").textContent),
  $("#stat-flood").textContent,
);
check("danh sách sự kiện có phần tử", $$("#event-list button").length > 0);
check(
  "bản đồ vẽ đủ lớp đoạn đường",
  mapModule.roadLayer?.getLayers().length >= 36,
  `roadLayer=${mapModule.roadLayer?.getLayers().length}`,
);
check("thẻ 'Nhìn trước hành trình' được điền", $("#insight-road").textContent.trim().length > 0);
check("ô tìm tuyến có danh sách điểm", $("#route-origin").options.length > 2);

console.log("\n[2] Điều hướng & dự báo");
click($('[data-view="forecast"]'));
check("mở trang Dự báo", visible($("#forecast-view")) && !visible($("#map-view")));
check("biểu đồ dự báo được vẽ", $("#forecast-chart").innerHTML.includes("<svg"));
click($('[data-view="rescue"]'));
check("mở trang Ứng cứu", visible($("#rescue-view")));
click($('[data-view="map"]'));
check("quay lại trang Bản đồ", visible($("#map-view")));

console.log("\n[3] Tìm tuyến");
click($("#open-route"));
check("mở bảng tìm tuyến", visible($("#route-panel")) && !visible($("#event-panel")));
$("#route-origin").value = "caugiay";
$("#route-destination").value = "hoankiem";
submit($("#route-form"));
check(
  "nhận và hiển thị kết quả tuyến",
  await waitFor(() => $$("#route-results .route-choice").length > 0, { label: "kết quả tuyến" }),
);
click($("#close-route"));
check("đóng bảng tìm tuyến", !visible($("#route-panel")) && visible($("#event-panel")));

console.log("\n[4] Đăng nhập & phân quyền");
check("ban đầu là khách", authState.user === null);
click($("#auth-button"));
check("mở hộp thoại đăng nhập", $("#login-dialog").hasAttribute("open"));
$("#login-username").value = "admin";
$("#login-password").value = "sai-mat-khau";
submit($("#login-form"));
check(
  "sai mật khẩu -> báo lỗi",
  await waitFor(() => $("#login-error").textContent.trim().length > 0, { label: "báo lỗi" }),
);
$("#login-password").value = "vietsafe2026";
submit($("#login-form"));
check(
  "đăng nhập admin thành công",
  await waitFor(() => authState.user?.role === "admin", { label: "đăng nhập" }),
);
check("token được lưu vào localStorage", Boolean(localStorage.getItem("vietsafe_token")));
check(
  "menu admin hiện ra",
  $$(".admin-only").length > 0 && $$(".admin-only").every((el) => !el.hidden),
);

console.log("\n[5] Trang quản trị");
click($('[data-view="reports"]'));
check("mở trang Phản ánh (admin)", visible($("#reports-view")));
check(
  "danh sách phản ánh được vẽ",
  await waitFor(() => $("#reports-list").innerHTML.trim().length > 0, {
    label: "danh sách phản ánh",
  }),
);
click($('[data-view="sources"]'));
check("mở trang Nguồn dữ liệu", visible($("#sources-view")));
check("thẻ nguồn dữ liệu được vẽ", $$("#source-grid .source-card").length >= 5);
$("#source-scenario").value = "storm";
change($("#source-scenario"));
check(
  "đổi kịch bản -> snapshot cập nhật (mưa 55 mm/h)",
  await waitFor(() => state.data?.rainfall === 55, { label: "đổi kịch bản" }),
);

console.log("\n[5b] Luồng phản ánh: gửi -> admin duyệt -> bản đồ đổi trạng thái");
const node0 = state.data.nodes.find((n) => n.name);
click($("#open-report"));
check("mở hộp thoại gửi phản ánh", $("#report-dialog").hasAttribute("open"));
$("#report-address").value = node0.name; // khớp tên nút giao -> tự đặt tọa độ
$("#report-address").dispatchEvent(new window.Event("input", { bubbles: true }));
check("chọn địa chỉ đặt được vị trí", Boolean(state.reportPosition));
$("#report-severity").value = "3";
$("#report-description").value = "Nước ngập sâu, xe máy không thể đi qua được.";
submit($("#report-form"));
check(
  "gửi phản ánh thành công (chờ xác minh)",
  await waitFor(() => $("#toast").textContent.includes("Đã lưu"), { label: "thông báo đã lưu" }),
);
click($('[data-view="reports"]'));
const reviewBtn = () => $('[data-review-id][data-status="verified"]');
check("admin thấy nút 'xác minh'", await waitFor(reviewBtn, { label: "nút xác minh" }));
const reportId = reviewBtn().dataset.reviewId;
click(reviewBtn());
check(
  "xác minh -> đường bị chặn trên snapshot (nguồn local_report)",
  await waitFor(() => state.data.roads.some((r) => r.origin === "local_report" && r.blocked), {
    label: "snapshot phản ánh verified",
  }),
);
check(
  "trạng thái phản ánh là 'verified'",
  state.reports.find((r) => r.id === reportId)?.status === "verified",
);
click($('[data-view="map"]'));

console.log("\n[6] Ứng cứu");
click($('[data-view="rescue"]'));
$("#rescue-vehicle").value = "motorbike";
$("#rescue-address").value = "Phố Giảng Võ";
$("#rescue-phone").value = "0900000000";
submit($("#rescue-request-form"));
check("form cứu hộ trả kết quả", $("#rescue-form-result").innerHTML.trim().length > 0);

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
