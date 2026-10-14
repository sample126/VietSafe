/**
 * Trang "Ứng cứu": hotline cứu hộ và form yêu cầu cứu hộ.
 * Hiện CHỈ chạy ở phía trình duyệt (tra dịch vụ theo loại xe rồi hướng dẫn gọi hotline);
 * chưa có API điều phối ở backend.
 */
import { rescueProblemTypes } from "../data/rescue.js";
import { state } from "../state.js";
import { $, esc, icon, toast } from "../utils.js";

const rescueVehicles = new Set(["motorbike", "car", "truck"]);
const rescueTagClasses = new Set(["tag-teal", "tag-blue", "tag-red"]);

function haversineKm(lat1, lng1, lat2, lng2) {
  const radians = (degrees) => (degrees * Math.PI) / 180;
  const dLat = radians(lat2 - lat1);
  const dLng = radians(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLng / 2) ** 2;
  const boundedA = Math.min(1, Math.max(0, a));
  return 6371 * 2 * Math.atan2(Math.sqrt(boundedA), Math.sqrt(1 - boundedA));
}

function validateRescueServices(data) {
  if (!Array.isArray(data) || data.length === 0) {
    throw new Error("Danh sách cứu hộ phải là một mảng không rỗng.");
  }
  return data.map((service) => {
    if (
      !service ||
      typeof service !== "object" ||
      !rescueVehicles.has(service.vehicle)
    ) {
      throw new Error("Mỗi đơn vị cứu hộ phải có loại phương tiện hợp lệ.");
    }
    if (
      service.simulated !== undefined &&
      typeof service.simulated !== "boolean"
    ) {
      throw new Error(
        `Cờ dữ liệu giả định không hợp lệ ở đơn vị ${service.vehicle}.`,
      );
    }
    for (const field of [
      "category",
      "name",
      "summary",
      "hotline",
      "websiteLabel",
      "description",
      "location",
      "address",
      "mapsQuery",
      "referenceNote",
      "hours",
      "cost",
    ]) {
      if (typeof service[field] !== "string" || !service[field].trim()) {
        throw new Error(
          `Thông tin "${field}" còn thiếu ở đơn vị ${service.vehicle}.`,
        );
      }
    }
    if (!rescueTagClasses.has(service.categoryClass)) {
      throw new Error(`Màu nhãn không hợp lệ ở đơn vị ${service.vehicle}.`);
    }
    if (
      !Number.isFinite(service.referenceLat) ||
      service.referenceLat < -90 ||
      service.referenceLat > 90 ||
      !Number.isFinite(service.referenceLng) ||
      service.referenceLng < -180 ||
      service.referenceLng > 180
    ) {
      throw new Error(
        `Tọa độ mốc tham chiếu không hợp lệ ở đơn vị ${service.vehicle}.`,
      );
    }
    if (service.simulated) {
      if (service.tel !== null || service.website !== null) {
        throw new Error(
          `Đơn vị giả định không được có liên kết gọi hoặc website ở đơn vị ${service.vehicle}.`,
        );
      }
    } else {
      if (
        typeof service.tel !== "string" ||
        !/^tel:\+?[0-9]+$/.test(service.tel)
      ) {
        throw new Error(
          `Số điện thoại không hợp lệ ở đơn vị ${service.vehicle}.`,
        );
      }
      let website;
      try {
        website = new URL(service.website);
      } catch {
        throw new Error(
          `Địa chỉ website không hợp lệ ở đơn vị ${service.vehicle}.`,
        );
      }
      if (website.protocol !== "https:") {
        throw new Error(
          `Website phải sử dụng HTTPS ở đơn vị ${service.vehicle}.`,
        );
      }
    }
    return service;
  });
}

function renderRescueServices(services, container) {
  const fragment = document.createDocumentFragment();
  for (const [index, service] of services.entries()) {
    const card = document.createElement("article");
    card.className = "rescue-card";
    card.dataset.rescueService = service.vehicle;
    card.dataset.rescueIndex = String(index);
    card.dataset.defaultOrder = String(index);

    const heading = document.createElement("div");
    heading.className = "rescue-card-top";
    const category = document.createElement("span");
    category.className = `tag ${service.categoryClass}`;
    category.textContent = service.category;
    const name = document.createElement("h4");
    name.textContent = service.name;
    const match = document.createElement("span");
    match.className = "rescue-match-label";
    match.hidden = true;
    match.textContent = "Phù hợp với xe đã chọn";
    const distance = document.createElement("span");
    distance.className = "rescue-distance-label";
    distance.hidden = true;
    heading.append(category, name, match, distance);

    const summary = document.createElement("p");
    summary.className = "rescue-card-summary";
    summary.textContent = service.summary;
    const call = document.createElement(service.simulated ? "button" : "a");
    call.className = "button primary full rescue-card-call";
    if (service.simulated) {
      call.type = "button";
      call.disabled = true;
      call.textContent = `Số giả định: ${service.hotline} — không thể gọi`;
    } else {
      call.href = service.tel;
      call.innerHTML = `${icon("phone")}Gọi ${esc(service.hotline)}`;
    }

    const details = document.createElement("details");
    details.className = "rescue-card-details";
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "Thông tin dịch vụ";
    const website = document.createElement(service.simulated ? "span" : "a");
    website.className = "service-link";
    website.textContent = service.websiteLabel;
    if (!service.simulated) {
      website.href = service.website;
      website.target = "_blank";
      website.rel = "noopener";
      website.append(document.createTextNode(" "));
      website.insertAdjacentHTML("beforeend", icon("external"));
    }
    const description = document.createElement("p");
    description.textContent = service.description;
    const info = document.createElement("div");
    info.className = "rescue-info-row";

    const addFact = (label, value) => {
      const fact = document.createElement("div");
      fact.className = "rescue-service-fact";
      const factLabel = document.createElement("strong");
      factLabel.textContent = label;
      fact.append(factLabel, value);
      info.append(fact);
    };
    addFact("Khu vực", document.createTextNode(service.location));
    addFact("Địa chỉ", document.createTextNode(service.address));
    addFact("Thời gian", document.createTextNode(service.hours));
    addFact("Chi phí", document.createTextNode(service.cost));
    addFact("Độ chính xác", document.createTextNode(service.referenceNote));

    const mapsLink = document.createElement("a");
    mapsLink.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(service.mapsQuery)}`;
    mapsLink.target = "_blank";
    mapsLink.rel = "noopener";
    mapsLink.textContent = `Tìm “${service.name}” trên Google Maps`;
    addFact("Bản đồ", mapsLink);

    details.append(detailsSummary, website, description, info);
    if (service.simulated) {
      const notice = document.createElement("p");
      notice.className = "rescue-demo-notice";
      notice.textContent =
        "Thông tin giả định để minh họa, không phải dịch vụ thật.";
      card.append(heading, notice, summary, call, details);
    } else {
      card.append(heading, summary, call, details);
    }
    fragment.append(card);
  }
  container.replaceChildren(fragment);
}

export function initRescue() {
  const rescueVehicleSelect = $("#rescue-vehicle");
  const rescueServiceList = $("#rescue-service-list");
  const rescueDistanceStatus = $("#rescue-distance-status");
  const mobileRescueLayout = window.matchMedia("(max-width: 600px)");
  let userLocation = null;
  let rescueServices = [];

  const updateRescueCardPriority = () => {
    const selectedVehicle = rescueVehicleSelect.value;
    const rescueCards = [
      ...document.querySelectorAll(".rescue-card[data-rescue-service]"),
    ];
    rescueCards.forEach((card, index) => {
      const service = rescueServices[Number(card.dataset.rescueIndex)];
      const isRecommended =
        mobileRescueLayout.matches &&
        card.dataset.rescueService === selectedVehicle;
      card.style.order =
        !userLocation && mobileRescueLayout.matches
          ? String(isRecommended ? 2 : 3 + index)
          : "";
      card.classList.toggle("is-recommended", isRecommended);
      card.querySelector(".rescue-match-label").hidden = !isRecommended;
      const distanceLabel = card.querySelector(".rescue-distance-label");
      distanceLabel.hidden = !userLocation || !service;
      if (userLocation && service) {
        const distance = haversineKm(
          userLocation.lat,
          userLocation.lng,
          service.referenceLat,
          service.referenceLng,
        );
        distanceLabel.textContent =
          distance < 0.1
            ? "≈ <0,1 km đến mốc tham chiếu"
            : `≈ ${distance.toFixed(1)} km đến mốc tham chiếu`;
        card.dataset.distanceKm = String(distance);
      } else {
        delete card.dataset.distanceKm;
      }
    });
    if (userLocation) {
      const sortedCards = [...rescueCards].sort(
        (a, b) => Number(a.dataset.distanceKm) - Number(b.dataset.distanceKm),
      );
      sortedCards.forEach((card) => rescueServiceList.append(card));
    } else {
      rescueCards
        .sort(
          (a, b) =>
            Number(a.dataset.defaultOrder) - Number(b.dataset.defaultOrder),
        )
        .forEach((card) => rescueServiceList.append(card));
    }
  };
  const setRescueOrigin = (lat, lng) => {
    if (
      !Number.isFinite(lat) ||
      lat < -90 ||
      lat > 90 ||
      !Number.isFinite(lng) ||
      lng < -180 ||
      lng > 180
    ) {
      userLocation = null;
      updateRescueCardPriority();
      rescueDistanceStatus.textContent =
        "Tọa độ không hợp lệ. Vĩ độ phải từ -90 đến 90, kinh độ từ -180 đến 180.";
      toast("Không thể xác định vị trí hiện tại.");
      return false;
    }
    userLocation = { lat, lng };
    rescueDistanceStatus.textContent =
      "Danh sách đơn vị cứu hộ đã được sắp xếp theo vị trí hiện tại.";
    updateRescueCardPriority();
    return true;
  };
  const getGpsErrorMessage = (error) => {
    if (error.code === error.PERMISSION_DENIED) {
      return "Bạn chưa cấp quyền vị trí. Hãy cho phép trình duyệt truy cập vị trí rồi thử lại.";
    }
    if (error.code === error.POSITION_UNAVAILABLE) {
      return "Thiết bị chưa xác định được vị trí. Hãy bật dịch vụ vị trí/GPS và thử lại.";
    }
    if (error.code === error.TIMEOUT) {
      return "Lấy vị trí quá thời gian chờ. Hãy thử lại ở nơi có tín hiệu GPS tốt hơn.";
    }
    return `Không lấy được vị trí GPS: ${error.message || "Lỗi không xác định."}`;
  };
  const requestRescueOriginGps = (
    button,
    buttonLabel = "Dùng vị trí hiện tại",
  ) => {
    if (window.isSecureContext === false) {
      rescueDistanceStatus.textContent =
        "Trình duyệt chỉ cho phép dùng GPS trên HTTPS hoặc localhost. Hãy mở trang bằng kết nối HTTPS trên điện thoại.";
      toast(rescueDistanceStatus.textContent);
      return;
    }
    if (!navigator.geolocation) {
      rescueDistanceStatus.textContent =
        "Trình duyệt không hỗ trợ định vị GPS.";
      toast(rescueDistanceStatus.textContent);
      return;
    }
    button.disabled = true;
    button.textContent = "Đang lấy vị trí GPS…";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        if (setRescueOrigin(latitude, longitude)) {
          const accuracyText = Number.isFinite(accuracy)
            ? ` Độ chính xác thiết bị khoảng ${Math.round(accuracy)} m.`
            : "";
          rescueDistanceStatus.textContent += `${accuracyText} Khoảng cách tới các điểm cứu hộ là ước tính theo tọa độ tham chiếu.`;
          let nearestName = "";
          if (state.data && state.data.roads) {
            let minDist = Infinity;
            for (const road of state.data.roads) {
              const distance = Math.hypot(
                (road.coordinates[0][0] + road.coordinates[1][0]) / 2 -
                  latitude,
                (road.coordinates[0][1] + road.coordinates[1][1]) / 2 -
                  longitude,
              );
              if (distance < minDist) {
                minDist = distance;
                nearestName = road.name;
              }
            }
          }
          $("#rescue-address").value = nearestName
            ? `Gần ${nearestName} (Tọa độ: ${latitude.toFixed(4)}, ${longitude.toFixed(4)})`
            : `Tọa độ: ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
        }
        button.disabled = false;
        button.innerHTML = `${icon("target")}${buttonLabel}`;
      },
      (error) => {
        button.disabled = false;
        button.innerHTML = `${icon("target")}${buttonLabel}`;
        rescueDistanceStatus.textContent = getGpsErrorMessage(error);
        toast(rescueDistanceStatus.textContent);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  };
  $("#rescue-sort-gps").addEventListener("click", (event) =>
    requestRescueOriginGps(event.currentTarget),
  );

  const rescueServicesPromise = fetch("/data/rescue-services.json")
    .then((response) => {
      if (!response.ok) {
        throw new Error(
          `Không tải được danh sách cứu hộ (HTTP ${response.status}).`,
        );
      }
      return response.json();
    })
    .then((data) => {
      rescueServices = validateRescueServices(data);
      renderRescueServices(rescueServices, rescueServiceList);
      updateRescueCardPriority();
      return rescueServices;
    })
    .catch((error) => {
      console.error("Không tải được dữ liệu cứu hộ:", error);
      rescueServiceList.textContent =
        "Không tải được danh sách cứu hộ. Vui lòng tải lại trang.";
      rescueServiceList.className = "form-error";
      return null;
    });
  rescueVehicleSelect.addEventListener("change", updateRescueCardPriority);
  mobileRescueLayout.addEventListener("change", updateRescueCardPriority);

  const rescueLocBtn = $("#rescue-loc-btn");
  if (rescueLocBtn) {
    rescueLocBtn.addEventListener("click", () => {
      requestRescueOriginGps(rescueLocBtn, "Lấy vị trí GPS hiện tại");
    });
  }
  const rescueForm = $("#rescue-request-form");
  if (rescueForm) {
    rescueForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const services = await rescueServicesPromise;
      if (!services) {
        toast("Chưa thể gửi yêu cầu vì không tải được danh sách cứu hộ.");
        return;
      }
      const vehicle = $("#rescue-vehicle").value;
      const typeKey = $("#rescue-type").value;
      const address = $("#rescue-address").value.trim();
      const phone = $("#rescue-phone").value.trim();
      const note = $("#rescue-note").value.trim();
      const srv = services.find((service) => service.vehicle === vehicle);
      if (!srv) {
        toast("Chưa có đơn vị cứu hộ cho loại phương tiện đã chọn.");
        return;
      }
      const probLabel = rescueProblemTypes[typeKey] || "Sự cố ngập nước";

      const resultBox = $("#rescue-form-result");
      resultBox.hidden = false;
      resultBox.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
          <span style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:#087f72;color:white;flex-shrink:0;">${icon("check")}</span>
          <div>
            <strong style="font-size:14px;color:#087f72;display:block;">Đã tiếp nhận yêu cầu ứng cứu!</strong>
            <span style="font-size:11px;color:#537365;">Đơn vị phụ trách đề xuất: <b>${esc(srv.name)}</b></span>
          </div>
        </div>
        <div style="font-size:11px;line-height:1.6;background:white;padding:10px 12px;border-radius:8px;border:1px solid #d0e7dc;margin-bottom:12px;color:#354e43;">
          <div>📍 <b>Vị trí:</b> ${esc(address)}</div>
          <div>📞 <b>SĐT liên hệ:</b> ${esc(phone)}</div>
          <div>⚠️ <b>Tình trạng:</b> ${esc(probLabel)}${note ? " (" + esc(note) + ")" : ""}</div>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <a href="${esc(srv.tel)}" class="button primary" style="background:#de4c3c!important;flex:1;min-height:38px;justify-content:center;text-decoration:none;">
            ${icon("phone")}Bấm gọi Hotline: ${srv.hotline}
          </a>
          <a href="${esc(srv.website)}" target="_blank" rel="noopener" class="button secondary" style="min-height:38px;justify-content:center;text-decoration:none;">
            ${icon("external")}Mở website
          </a>
        </div>
        <div style="margin-top:10px;font-size:10px;color:#6b8577;line-height:1.5;">
          💡 <b>Lưu ý an toàn:</b> Nhấn nút <i>"Bấm gọi Hotline"</i> để tổng đài viên điều xe cứu hộ gần nhất tiếp cận hiện trường nhanh nhất (15–20 phút).
        </div>
      `;

      toast(
        `Đã tiếp nhận! Vui lòng gọi hotline ${srv.hotline} để được cứu hộ hỗ trợ tức thì.`,
      );
    });
  }
}
