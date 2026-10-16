/** Hộp thoại "Gửi phản ánh" của người dân: GPS, ảnh và gửi. */
import { post } from "../api.js";
import { authState, state } from "../state.js";
import { map, selectionLayer } from "../map.js";
import { $, inPilotArea, toast } from "../utils.js";
import { refresh } from "../dashboard.js";

let selectedReportImage = null;
let reportSubmitting = false;

function resetReportLocationConfirmation() {
  const confirmation = $("#report-location-confirm");
  confirmation.checked = false;
  confirmation.disabled = !state.reportPosition;
  $("#report-location-confirm-hint").hidden = true;
  $("#report-location-confirm-hint").textContent = "";
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
  resetReportLocationConfirmation();
  $("#report-dialog").showModal();
}

export function setReportPosition(lat, lng, address, acquiredAt = Date.now()) {
  state.reportPosition = { lat, lng };
  if (address) $("#report-address").value = address;
  $("#report-coordinates").textContent =
    `Vị trí GPS: ${lat.toFixed(5)}, ${lng.toFixed(5)} · Lấy lúc ${new Date(acquiredAt).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })}.`;
  $("#report-coordinates").classList.add("valid");
  resetReportLocationConfirmation();
}

export function geolocate(forReport = false) {
  if (!navigator.geolocation) {
    toast(
      forReport
        ? "Trình duyệt không hỗ trợ GPS nên chưa thể gửi phản ánh."
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

export async function submitReport(event) {
  event.preventDefault();
  if (reportSubmitting) return;
  $("#report-error").hidden = true;
  $("#report-error").textContent = "";
  if (!state.reportPosition) {
    $("#report-error").textContent =
      "Hãy dùng GPS để xác định vị trí trước khi gửi.";
    $("#report-error").hidden = false;
    return;
  }
  if (!$("#report-location-confirm").checked) {
    $("#report-error").textContent =
      "Hãy kiểm tra vị trí GPS và địa chỉ bổ sung, rồi xác nhận trước khi gửi.";
    $("#report-error").hidden = false;
    $("#report-location-confirm").focus();
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
      ...state.reportPosition,
      address: $("#report-address").value,
      type: $("input[name=type]:checked").value,
      severity: Number($("#report-severity").value),
      description: $("#report-description").value,
      image,
    });
  } catch (e) {
    const isNetworkError =
      e?.name === "TypeError" ||
      navigator.onLine === false ||
      e?.message?.includes("Máy chủ phản hồi chậm");
    $("#report-error").textContent = isNetworkError
      ? "Chưa gửi được do mất kết nối hoặc máy chủ phản hồi chậm. Hãy kiểm tra mạng rồi nhấn “Gửi phản ánh” để thử lại; thông tin bạn đã nhập vẫn được giữ."
      : e.message || "Không thể gửi phản ánh lúc này. Vui lòng thử lại.";
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
  state.reportPosition = null;
  $("#report-coordinates").textContent = "Chưa chọn tọa độ.";
  $("#report-coordinates").classList.remove("valid");
  resetReportLocationConfirmation();
  toast(
    result.duplicate
      ? "Phản ánh trùng đã được lưu trước đó."
      : `Đã lưu ${result.id}. Phản ánh đang chờ xác minh.`,
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
  $("#report-camera").addEventListener("change", (event) =>
    updateReportImage(event.currentTarget.files[0], "camera"),
  );
  $("#report-image").addEventListener("change", (event) =>
    updateReportImage(event.currentTarget.files[0], "picker"),
  );
  $("#report-remove-image").addEventListener("click", clearReportImage);
  $("#report-gps").addEventListener("click", () => geolocate(true));
  $("#report-address").addEventListener("input", () => {
    const confirmation = $("#report-location-confirm");
    if (confirmation.checked) {
      confirmation.checked = false;
      const hint = $("#report-location-confirm-hint");
      hint.textContent =
        "Địa chỉ đã thay đổi. Vui lòng kiểm tra vị trí và xác nhận lại.";
      hint.hidden = false;
    }
  });
  $("#report-location-confirm").addEventListener("change", () => {
    $("#report-location-confirm-hint").hidden = true;
    $("#report-location-confirm-hint").textContent = "";
    $("#report-error").hidden = true;
    $("#report-error").textContent = "";
  });
  $("#report-form").addEventListener("submit", submitReport);
}
