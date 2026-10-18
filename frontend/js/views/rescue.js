/**
 * Trang "Ứng cứu": danh bạ cứu hộ và form yêu cầu.
 */
import { api } from "../api.js";
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

    const addressLine = document.createElement("p");
    addressLine.className = "rescue-card-address";
    addressLine.textContent = service.address;

    const summary = document.createElement("p");
    summary.className = "rescue-card-summary";
    summary.textContent = service.summary;
    const call = document.createElement("a");
    call.className = "button primary full rescue-card-call";
    call.href = service.tel;
    call.innerHTML = `${icon("phone")}Gọi ${esc(service.hotline)}`;

    const details = document.createElement("details");
    details.className = "rescue-card-details";
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "Thông tin dịch vụ";
    const website = document.createElement("a");
    website.className = "service-link";
    website.textContent = service.websiteLabel;
    website.href = service.website;
    website.target = "_blank";
    website.rel = "noopener";
    website.append(document.createTextNode(" "));
    website.insertAdjacentHTML("beforeend", icon("external"));
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
    addFact("Thời gian", document.createTextNode(service.hours));
    addFact("Chi phí", document.createTextNode(service.cost));

    details.append(detailsSummary, website, description, info);
    card.append(heading, addressLine, distance, summary, call, details);
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
  const setRescueOrigin = (lat, lng, description = "vị trí hiện tại") => {
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
    if (!document.querySelector(".rescue-card[data-rescue-service]") && rescueServices.length) {
      renderRescueServices(rescueServices, rescueServiceList);
    }
    rescueDistanceStatus.textContent = `Danh sách đơn vị cứu hộ đã được sắp xếp theo ${description}.`;
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
  const rescueSuggestions = $("#rescue-origin-suggestions");
  let searchTimer;
  let searchSerial = 0;

  const showRescueSuggestions = (results) => {
    rescueSuggestions.replaceChildren();
    if (!results.length) {
      rescueSuggestions.hidden = true;
      return;
    }
    for (const place of results) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "rescue-suggestion-item";
      item.textContent = place.name;
      item.addEventListener("click", () => {
        if (
          typeof place.name === "string" &&
          Number.isFinite(place.lat) &&
          Number.isFinite(place.lng)
        ) {
          if (setRescueOrigin(place.lat, place.lng, `địa điểm ${place.name}`)) {
            $("#rescue-address").value = place.name;
            rescueDistanceStatus.textContent +=
              " Khoảng cách tới các điểm cứu hộ là ước tính theo tọa độ tham chiếu.";
          }
        }
        $("#rescue-origin-address").value = place.name;
        rescueSuggestions.hidden = true;
      });
      rescueSuggestions.append(item);
    }
    rescueSuggestions.hidden = false;
  };

  const searchRescueSuggestions = async (query) => {
    const serial = ++searchSerial;
    try {
      const { results } = await api(
        `/api/search?q=${encodeURIComponent(query)}`,
      );
      if (serial !== searchSerial) return;
      if (!Array.isArray(results)) return;
      showRescueSuggestions(results);
    } catch {
      rescueSuggestions.hidden = true;
    }
  };

  const searchRescueOrigin = async () => {
    const input = $("#rescue-origin-address");
    const button = $("#rescue-search-address");
    const query = input.value.trim();
    if (!query) {
      rescueDistanceStatus.textContent =
        "Vui lòng nhập tên địa điểm hoặc đường phố.";
      input.focus();
      return;
    }

    button.disabled = true;
    button.textContent = "Đang tìm địa điểm...";
    rescueDistanceStatus.textContent =
      "Đang tìm địa điểm trong danh mục bản đồ...";
    try {
      const { results } = await api(
        `/api/search?q=${encodeURIComponent(query)}`,
      );
      if (!Array.isArray(results)) {
        throw new Error("Dữ liệu địa điểm trả về không hợp lệ.");
      }
      const normalize = (value) =>
        value
          .normalize("NFD")
          .replace(/[\u0300-\u036f]/g, "")
          .replace(/[đĐ]/g, (letter) => (letter === "Đ" ? "D" : "d"))
          .toLocaleLowerCase("vi");
      const exactMatches = results.filter(
        (place) => normalize(place.name) === normalize(query),
      );
      const matches = exactMatches.length ? exactMatches : results;
      if (!matches.length) {
        rescueDistanceStatus.textContent =
          "Không tìm thấy địa điểm. Hãy thử tên nút giao hoặc đường phố khác. Vị trí đang dùng chưa thay đổi.";
        return;
      }
      if (matches.length > 1) {
        rescueDistanceStatus.textContent =
          "Có nhiều địa điểm phù hợp. Hãy chọn một gợi ý từ danh sách.";
        showRescueSuggestions(matches);
        return;
      }

      const [place] = matches;
      if (
        typeof place.name !== "string" ||
        !Number.isFinite(place.lat) ||
        !Number.isFinite(place.lng)
      ) {
        throw new Error("Địa điểm này chưa có tọa độ để tính khoảng cách.");
      }
      if (setRescueOrigin(place.lat, place.lng, `địa điểm ${place.name}`)) {
        $("#rescue-address").value = place.name;
        rescueDistanceStatus.textContent +=
          " Khoảng cách tới các điểm cứu hộ là ước tính theo tọa độ tham chiếu.";
      }
    } catch (error) {
      rescueDistanceStatus.textContent =
        error.message || "Không thể tìm địa điểm lúc này.";
    } finally {
      button.disabled = false;
      button.textContent = "Tìm theo địa điểm";
    }
  };
  $("#rescue-search-address").addEventListener("click", searchRescueOrigin);
  $("#rescue-origin-address").addEventListener("input", () => {
    clearTimeout(searchTimer);
    const query = $("#rescue-origin-address").value.trim();
    if (query.length < 2) {
      rescueSuggestions.hidden = true;
      return;
    }
    searchTimer = setTimeout(() => {
      searchRescueSuggestions(query);
    }, 300);
  });

  $("#rescue-origin-address").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      rescueSuggestions.hidden = true;
      searchRescueOrigin();
    }
    if (event.key === "Escape") {
      rescueSuggestions.hidden = true;
    }
  });

  document.addEventListener("click", (event) => {
    if (
      !event.target.closest("#rescue-origin-address") &&
      !event.target.closest("#rescue-origin-suggestions")
    ) {
      rescueSuggestions.hidden = true;
    }
  });

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
      rescueServiceList.innerHTML =
        '<p class="muted rescue-list-placeholder">Nhập địa điểm hoặc dùng GPS để xem danh sách cứu hộ gần bạn.</p>';
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
      const srv = services.find((service) => service.vehicle === vehicle);
      if (!srv) {
        toast("Chưa có đơn vị cứu hộ cho loại phương tiện đã chọn.");
        return;
      }
      const resultBox = $("#rescue-form-result");
      resultBox.hidden = false;
      resultBox.textContent = `Đã ghi nhận yêu cầu cứu hộ cho ${srv.name}. Đơn vị sẽ liên hệ với bạn qua số điện thoại đã cung cấp.`;
      toast("Đã gửi yêu cầu cứu hộ.");
    });
  }
}
