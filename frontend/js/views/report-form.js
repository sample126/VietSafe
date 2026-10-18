/** Hộp thoại "Gửi phản ánh" của người dân: GPS / địa chỉ / ghim trên bản đồ, ảnh, nháp tự lưu, gửi. */
import { api, post } from "../api.js";
import { refresh } from "../dashboard.js";
import { map, selectionLayer } from "../map.js";
import { setView } from "../navigation.js";
import { authState, state } from "../state.js";
import { $, $$, inPilotArea, toast } from "../utils.js";

let selectedReportImage = null;
let reportSubmitting = false;
let roadNames = [];

/** Các loại phản ánh đang được tick (checkbox) — gửi dạng "flood,traffic". */
function selectedReportTypes() {
  return $$('input[name="type"]:checked').map((i) => i.value);
}

// === Draft auto-save ===
const DRAFT_KEY = "vietsafe_report_draft";
let draftSaveTimer = null;
let geocodeTimer = null;

function saveDraft() {
  const draft = {
    address: $("#report-address")?.value || "",
    type: selectedReportTypes().join(",") || "flood",
    severity: $("#report-severity")?.value || "2",
    description: $("#report-description")?.value || "",
    position: state.reportPosition,
    savedAt: Date.now(),
  };
  localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
}

function loadDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem(DRAFT_KEY));
    if (!draft) return;
    // Chỉ restore draft trong 30 phút
    if (Date.now() - draft.savedAt > 30 * 60 * 1000) {
      localStorage.removeItem(DRAFT_KEY);
      return;
    }
    if (draft.address) $("#report-address").value = draft.address;
    if (draft.type) {
      const saved = String(draft.type).split(",").filter((t) => t);
      $$('input[name="type"]').forEach((box) => {
        box.checked = saved.includes(box.value);
      });
      if (!$$('input[name="type"]:checked').length) {
        const first = $('input[name="type"]');
        if (first) first.checked = true;
      }
    }
    if (draft.severity) $("#report-severity").value = draft.severity;
    if (draft.description) $("#report-description").value = draft.description;
    if (draft.position) {
      state.reportPosition = draft.position;
      setReportPosition(draft.position.lat, draft.position.lng);
    }
    updateCharCount();
    toast("Đã khôi phục nháp phản ánh.");
  } catch { /* ignore */ }
}

function clearDraft() {
  localStorage.removeItem(DRAFT_KEY);
}

function updateCharCount() {
  const desc = $("#report-description")?.value || "";
  const counter = $("#report-char-count");
  if (counter) {
    counter.textContent = `${desc.length}/1200`;
    counter.classList.toggle("near-limit", desc.length > 1100);
  }
}

// === Image preview ===
function updateImagePreview(file) {
  const preview = $("#report-image-preview");
  if (!preview) return;
  if (!file) {
    preview.innerHTML = "";
    preview.hidden = true;
    return;
  }
  const url = URL.createObjectURL(file);
  preview.innerHTML = `<img src="${url}" alt="Ảnh xem trước">`;
  preview.hidden = false;
}

// === Offline queue ===
const OFFLINE_QUEUE_KEY = "vietsafe_offline_queue";

function getOfflineQueue() {
  try { return JSON.parse(localStorage.getItem(OFFLINE_QUEUE_KEY)) || []; }
  catch { return []; }
}

function saveOfflineQueue(queue) {
  localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue));
}

function addToOfflineQueue(reportData) {
  const queue = getOfflineQueue();
  queue.push({ ...reportData, queuedAt: Date.now() });
  saveOfflineQueue(queue);
  toast("Đã lưu phản ánh tạm. Sẽ tự động gửi khi có mạng.");
}

async function flushOfflineQueue() {
  const queue = getOfflineQueue();
  if (!queue.length || !navigator.onLine) return;
  const remaining = [];
  for (const item of queue) {
    try {
      await post("/api/reports", item);
    } catch {
      remaining.push(item);
    }
  }
  saveOfflineQueue(remaining);
  if (remaining.length < queue.length) toast("Đã gửi xếp các phản ánh đã lưu.");
}

// Load road names for autocomplete
async function loadRoadNames() {
  try {
    const data = await api("/api/roads");
    roadNames = data.roads || [];
    const datalist = $("#address-options");
    if (datalist) {
      datalist.innerHTML = roadNames.map((r) => `<option value="${r}">`).join("");
    }
  } catch { /* ignore */ }
}

function updateReportImage(file, source) {
  if (!file) return;
  selectedReportImage = file;
  if (source === "camera") $("#report-image").value = "";
  else $("#report-camera").value = "";
  $("#report-image-status").textContent =
    `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
  $("#report-remove-image").hidden = false;
}

function clearReportImage() {
  selectedReportImage = null;
  $("#report-camera").value = "";
  $("#report-image").value = "";
  $("#report-image-status").textContent = "Chưa có ảnh được thêm.";
  $("#report-remove-image").hidden = true;
}

export function openReport() {
  if (!state.data) {
    toast("Đang tải dữ liệu, vui lòng thử lại.");
    return;
  }
  if (!authState.user) {
    $("#login-dialog").showModal();
    return;
  }
  $("#report-error").hidden = true;
  $("#report-error").textContent = "";
  $("#report-submit-status").hidden = true;
  $("#report-submit-status").textContent = "";
  updateCharCount();
  updateImagePreview(null);
  loadDraft();
  $("#report-dialog").showModal();
}

export function setReportPosition(lat, lng, address, acquiredAt = Date.now()) {
  state.reportPosition = { lat, lng };
  if (address) $("#report-address").value = address;
  $("#report-coordinates").textContent =
    `Đã đặt vị trí: ${lat.toFixed(5)}, ${lng.toFixed(5)} · Lấy lúc ${new Date(acquiredAt).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })}.`;
  $("#report-coordinates").classList.add("valid");
}

/** Đóng hộp thoại và cho phép chọn vị trí bằng cách bấm trên bản đồ. */
export function startPick() {
  state.picking = true;
  $("#report-dialog").close();
  setView("map");
  $("#pick-banner").hidden = false;
  $(".map-surface").classList.add("picking");
  $("#map").scrollIntoView({ behavior: "smooth", block: "center" });
}

/** Gọi từ map.js khi người dùng bấm một vị trí trên bản đồ. */
export function finishPick(lat, lng) {
  if (!inPilotArea(lat, lng)) {
    toast("Hãy chọn vị trí trong vùng thử nghiệm Hà Nội.");
    return;
  }
  state.picking = false;
  $("#pick-banner").hidden = true;
  $(".map-surface").classList.remove("picking");
  const nearest = state.data.roads
    .map((r) => ({
      r,
      d: Math.hypot(lat - r.center[0], lng - r.center[1]),
    }))
    .sort((a, b) => a.d - b.d)[0].r;
  setReportPosition(lat, lng, nearest.name);
  selectionLayer.clearLayers();
  L.circleMarker([lat, lng], {
    radius: 9,
    color: "#087f72",
    fillOpacity: 0.3,
  }).addTo(selectionLayer);
  $("#report-dialog").showModal();
}

export function geolocate(forReport = false) {
  if (!navigator.geolocation) {
    toast(
      forReport
        ? "Trình duyệt không hỗ trợ GPS. Bạn có thể nhập tên đường hoặc nút giao trong vùng thử nghiệm."
        : "Trình duyệt không hỗ trợ định vị.",
    );
    return;
  }
  toast(
    "Đang xác định vị trí. Cho phép trình duyệt truy cập vị trí nếu được hỏi.",
  );
  navigator.geolocation.getCurrentPosition(
    (p) => {
      const { latitude: lat, longitude: lng } = p.coords;
      if (!inPilotArea(lat, lng)) {
        toast("Vị trí GPS của bạn nằm ngoài vùng thử nghiệm Hà Nội.");
        return;
      }
      if (forReport) setReportPosition(lat, lng, undefined, p.timestamp);
      else {
        map.setView([lat, lng], 15);
        selectionLayer.clearLayers();
        L.circleMarker([lat, lng], { radius: 9, color: "#087f72" }).addTo(
          selectionLayer,
        );
      }
    },
    () =>
      toast(
        forReport
          ? "Chưa lấy được GPS. Hãy cho phép truy cập vị trí rồi thử lại."
          : "Chưa lấy được GPS.",
      ),
    { timeout: 10000, maximumAge: 60000 },
  );
}

/** Tự động định vị địa chỉ đang nhập bằng API tìm kiếm nội bộ (không ghi đè ô nhập). */
export async function locateReportAddress() {
  const value = $("#report-address").value.trim();
  if (value.length < 3) return;
  let result;
  try {
    result = await api("/api/search?q=" + encodeURIComponent(value));
  } catch {
    return;
  }
  if ($("#report-address").value.trim() !== value) return;
  const exact = result.results.find(
    (p) => p.name.toLocaleLowerCase("vi") === value.toLocaleLowerCase("vi"),
  );
  if (exact || result.results.length === 1) {
    const p = exact || result.results[0];
    setReportPosition(p.lat, p.lng);
  } else if (result.results.length > 1) {
    $("#report-coordinates").classList.remove("valid");
    $("#report-coordinates").textContent =
      "Có nhiều địa điểm phù hợp: " +
      result.results
        .slice(0, 3)
        .map((p) => p.name)
        .join("; ") +
      " — gõ thêm hoặc chọn trên bản đồ.";
  } else {
    $("#report-coordinates").classList.remove("valid");
    $("#report-coordinates").textContent =
      "Chưa tìm thấy địa chỉ trong danh mục — dùng GPS hoặc chọn trên bản đồ.";
  }
}

export async function submitReport(event) {
  event.preventDefault();
  if (reportSubmitting) return;
  $("#report-error").hidden = true;
  $("#report-error").textContent = "";
  if (!selectedReportTypes().length) {
    $("#report-error").textContent = "Hãy chọn ít nhất một loại phản ánh.";
    $("#report-error").hidden = false;
    return;
  }
  const address = $("#report-address").value.trim();
  if (!state.reportPosition && !address) {
    $("#report-error").textContent =
      "Hãy dùng GPS, nhập địa chỉ/địa điểm hoặc chọn trên bản đồ trước khi gửi.";
    $("#report-error").hidden = false;
    return;
  }
  const button = $("#submit-report");
  const status = $("#report-submit-status");
  const originalButtonContent = button.innerHTML;
  reportSubmitting = true;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = "Đang gửi…";
  status.textContent = "Đang gửi phản ánh của bạn…";
  status.hidden = false;
  let result;
  try {
    let image = null;
    const file = selectedReportImage;
    if (file) {
      if (
        file.size > 1500000 ||
        !["image/jpeg", "image/png", "image/webp"].includes(file.type)
      )
        throw new Error("Ảnh JPG, PNG hoặc WebP tối đa 1,5 MB.");
      image = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error("Không đọc được ảnh."));
        reader.readAsDataURL(file);
      });
    }
    result = await post("/api/reports", {
      ...(state.reportPosition || {}),
      address,
      type: selectedReportTypes().join(","),
      severity: Number($("#report-severity").value),
      description: $("#report-description").value,
      image,
    });
  } catch (e) {
    const isNetworkError =
      e?.name === "TypeError" ||
      navigator.onLine === false ||
      e?.message?.includes("Máy chủ phản hồi chậm");
    if (isNetworkError) {
      // Lưu vào offline queue
      const reportData = {
        ...(state.reportPosition || {}),
        address,
        type: selectedReportTypes().join(","),
        severity: Number($("#report-severity").value),
        description: $("#report-description").value,
      };
      if (selectedReportImage) {
        reportData.image = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error("Không đọc được ảnh."));
          reader.readAsDataURL(selectedReportImage);
        });
      }
      addToOfflineQueue(reportData);
      $("#report-dialog").close();
      $("#report-form").reset();
      clearReportImage();
      state.reportPosition = null;
      $("#report-coordinates").textContent = "Chưa chọn tọa độ.";
      $("#report-coordinates").classList.remove("valid");
      return;
    }
    $("#report-error").textContent = e.message || "Không thể gửi phản ánh lúc này. Vui lòng thử lại.";
    $("#report-error").hidden = false;
    return;
  } finally {
    reportSubmitting = false;
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.innerHTML = originalButtonContent;
    status.hidden = true;
    status.textContent = "";
  }

  $("#report-dialog").close();
  $("#report-form").reset();
  clearReportImage();
  updateImagePreview(null);
  state.reportPosition = null;
  $("#report-coordinates").textContent = "Chưa chọn tọa độ.";
  $("#report-coordinates").classList.remove("valid");
  clearDraft();
  toast(
    `${
      result.duplicate
        ? "Phản ánh trùng đã được lưu trước đó."
        : `Đã lưu ${result.id}. Phản ánh đang chờ xác minh.`
    }${
      result.location_source === "address" && result.resolved_place
        ? ` Địa chỉ được ghép với ${result.resolved_place} trong mạng thử nghiệm (vị trí ước tính).`
        : ""
    }`,
  );
  try {
    const refreshed = await refresh();
    if (!refreshed) {
      toast(
        "Phản ánh đã được gửi và lưu thành công. Bản đồ chưa cập nhật được vì mất kết nối; dữ liệu sẽ được làm mới khi kết nối trở lại.",
      );
    }
  } catch (error) {
    toast(
      `Phản ánh đã được gửi và lưu thành công. Bản đồ chưa cập nhật được: ${error.message || "lỗi kết nối"}. Dữ liệu sẽ được làm mới khi kết nối trở lại.`,
    );
  }
}

export function initReportForm() {
  $("#open-report").addEventListener("click", openReport);
  $("#report-take-photo").addEventListener("click", () =>
    $("#report-camera").click(),
  );
  $("#report-choose-image").addEventListener("click", () =>
    $("#report-image").click(),
  );
  $("#report-camera").addEventListener("change", (event) => {
    const file = event.currentTarget.files[0];
    updateReportImage(file, "camera");
    updateImagePreview(file);
  });
  $("#report-image").addEventListener("change", (event) => {
    const file = event.currentTarget.files[0];
    updateReportImage(file, "picker");
    updateImagePreview(file);
  });
  $("#report-remove-image").addEventListener("click", () => {
    clearReportImage();
    updateImagePreview(null);
  });
  $("#report-gps").addEventListener("click", () => geolocate(true));
  $("#report-pick").addEventListener("click", startPick);
  $("#cancel-pick").addEventListener("click", () => {
    state.picking = false;
    $("#pick-banner").hidden = true;
    $(".map-surface").classList.remove("picking");
    $("#report-dialog").showModal();
  });
  $("#report-form").addEventListener("submit", submitReport);
  // Character counter
  $("#report-description")?.addEventListener("input", updateCharCount);
  // Auto-save draft (debounce 1s) + tự động định vị địa chỉ khi ngừng gõ (debounce 400ms)
  const onAddressInput = () => {
    clearTimeout(draftSaveTimer);
    draftSaveTimer = setTimeout(saveDraft, 1000);
    if (state.reportPosition) state.reportPosition = null;
    const value = $("#report-address").value.trim();
    $("#report-coordinates").classList.remove("valid");
    $("#report-coordinates").textContent =
      value.length >= 3 ? "Đang định vị địa chỉ…" : "";
    clearTimeout(geocodeTimer);
    if (value.length < 3) return;
    geocodeTimer = setTimeout(() => void locateReportAddress(), 400);
  };
  $("#report-address")?.addEventListener("input", onAddressInput);
  $("#report-description")?.addEventListener("input", () => {
    clearTimeout(draftSaveTimer);
    draftSaveTimer = setTimeout(saveDraft, 1000);
  });
  // Load road names for autocomplete
  loadRoadNames();
  // Flush offline queue when online
  window.addEventListener("online", flushOfflineQueue);
  if (navigator.onLine) flushOfflineQueue();
}
