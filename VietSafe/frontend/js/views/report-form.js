/** Hộp thoại "Gửi phản ánh" của người dân: GPS, ảnh và gửi. */
import { post } from "../api.js";
import { authState, state } from "../state.js";
import { map, selectionLayer } from "../map.js";
import { $, inPilotArea, toast } from "../utils.js";
import { refresh } from "../dashboard.js";

let selectedReportImage = null;

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
  $("#report-dialog").showModal();
}

export function setReportPosition(lat, lng, address) {
  state.reportPosition = { lat, lng };
  if (address) $("#report-address").value = address;
  $("#report-coordinates").textContent =
    `Đã đặt vị trí: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  $("#report-coordinates").classList.add("valid");
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
      if (forReport) setReportPosition(lat, lng);
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
  $("#report-error").hidden = true;
  if (!state.reportPosition) {
    $("#report-error").textContent =
      "Hãy dùng GPS để xác định vị trí trước khi gửi.";
    $("#report-error").hidden = false;
    return;
  }
  const button = $("#submit-report");
  button.disabled = true;
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
    const result = await post("/api/reports", {
      ...state.reportPosition,
      address: $("#report-address").value,
      type: $("input[name=type]:checked").value,
      severity: Number($("#report-severity").value),
      description: $("#report-description").value,
      image,
    });
    $("#report-dialog").close();
    $("#report-form").reset();
    clearReportImage();
    state.reportPosition = null;
    $("#report-coordinates").textContent = "Chưa chọn tọa độ.";
    $("#report-coordinates").classList.remove("valid");
    toast(
      result.duplicate
        ? "Phản ánh trùng đã được lưu trước đó."
        : `Đã lưu ${result.id}. Phản ánh đang chờ xác minh.`,
    );
    await refresh();
  } catch (e) {
    $("#report-error").textContent = e.message;
    $("#report-error").hidden = false;
  } finally {
    button.disabled = false;
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
  $("#report-form").addEventListener("submit", submitReport);
}
