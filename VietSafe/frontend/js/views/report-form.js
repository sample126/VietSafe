/** Hộp thoại "Gửi phản ánh" của người dân: chọn vị trí (GPS / địa chỉ / chấm trên bản đồ), ảnh, gửi. */
import { post, api } from "../api.js";
import { authState, state } from "../state.js";
import { map, selectionLayer } from "../map.js";
import { $, inPilotArea, toast } from "../utils.js";
import { refresh } from "../dashboard.js";
import { setView } from "../navigation.js";

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
  $("#report-coordinates").textContent = `Đã đặt vị trí: ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  $("#report-coordinates").classList.add("valid");
}

export function startPick() {
  state.picking = true;
  $("#report-dialog").close();
  setView("map");
  $("#pick-banner").hidden = false;
  $(".map-surface").classList.add("picking");
  $("#map").scrollIntoView({ behavior: "smooth", block: "center" });
}

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
      d: Math.hypot(
        lat - (r.coordinates[0][0] + r.coordinates[1][0]) / 2,
        lng - (r.coordinates[0][1] + r.coordinates[1][1]) / 2,
      ),
    }))
    .sort((a, b) => a.d - b.d)[0].r;
  setReportPosition(lat, lng, nearest.name);
  selectionLayer.clearLayers();
  L.circleMarker([lat, lng], { radius: 9, color: "#087f72", fillOpacity: 0.3 }).addTo(
    selectionLayer,
  );
  $("#report-dialog").showModal();
}

export function geolocate(forReport = false) {
  if (!navigator.geolocation) {
    toast("Trình duyệt không hỗ trợ định vị. Bạn có thể chọn trên bản đồ.");
    return;
  }
  toast("Đang xác định vị trí. Cho phép trình duyệt truy cập vị trí nếu được hỏi.");
  navigator.geolocation.getCurrentPosition(
    (p) => {
      const { latitude: lat, longitude: lng } = p.coords;
      if (!inPilotArea(lat, lng)) {
        toast("Bạn đang ngoài vùng thử nghiệm Hà Nội. Hãy chọn địa chỉ hoặc ghim trong vùng.");
        return;
      }
      if (forReport) setReportPosition(lat, lng, "Vị trí GPS của tôi");
      else {
        map.setView([lat, lng], 15);
        selectionLayer.clearLayers();
        L.circleMarker([lat, lng], { radius: 9, color: "#087f72" }).addTo(selectionLayer);
      }
    },
    () => toast("Chưa lấy được GPS. Hãy nhập địa điểm hoặc chọn vị trí trên bản đồ."),
    { timeout: 10000, maximumAge: 60000 },
  );
}

export async function locateReportAddress() {
  const value = $("#report-address").value.trim();
  if (!value) {
    toast("Hãy nhập tên đường hoặc địa điểm.");
    return;
  }
  try {
    const result = await api("/api/search?q=" + encodeURIComponent(value));
    const exact = result.results.find(
      (p) => p.name.toLocaleLowerCase("vi") === value.toLocaleLowerCase("vi"),
    );
    if (exact || result.results.length === 1) {
      const p = exact || result.results[0];
      setReportPosition(p.lat, p.lng, p.name);
    } else if (result.results.length > 1) {
      $("#report-error").textContent =
        "Có nhiều địa điểm phù hợp: " +
        result.results
          .slice(0, 4)
          .map((p) => p.name)
          .join("; ") +
        ". Chọn tên đầy đủ hoặc đặt ghim.";
      $("#report-error").hidden = false;
    } else {
      toast(
        "Địa chỉ chưa có trong danh mục local. Dùng “Chọn trên bản đồ” để đặt vị trí chính xác.",
      );
    }
  } catch (e) {
    toast(e.message);
  }
}

export async function submitReport(event) {
  event.preventDefault();
  $("#report-error").hidden = true;
  if (!state.reportPosition) {
    $("#report-error").textContent =
      "Hãy định vị địa chỉ, dùng GPS hoặc chọn trên bản đồ trước khi gửi.";
    $("#report-error").hidden = false;
    return;
  }
  const button = $("#submit-report");
  button.disabled = true;
  try {
    let image = null;
    const file = $("#report-image").files[0];
    if (file) {
      if (file.size > 1500000 || !["image/jpeg", "image/png", "image/webp"].includes(file.type))
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
  $("#report-pick").addEventListener("click", startPick);
  $("#cancel-pick").addEventListener("click", () => {
    state.picking = false;
    $("#pick-banner").hidden = true;
    $(".map-surface").classList.remove("picking");
    $("#report-dialog").showModal();
  });
  $("#report-gps").addEventListener("click", () => geolocate(true));
  $("#report-find").addEventListener("click", locateReportAddress);
  $("#report-address").addEventListener("input", () => {
    state.reportPosition = null;
    $("#report-coordinates").textContent =
      "Địa chỉ đã thay đổi. Hãy định vị lại hoặc chọn trên bản đồ.";
    $("#report-coordinates").classList.remove("valid");
    const n = state.data.nodes.find((n) => n.name === $("#report-address").value);
    if (n) setReportPosition(n.lat, n.lng);
  });
  $("#report-form").addEventListener("submit", submitReport);
}
