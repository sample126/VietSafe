/** Bảng "Tìm tuyến thay thế": chọn điểm đi/đến, phương tiện, thời điểm và hiển thị tuyến. */
import { api } from "../api.js";
import { map, routeLayer } from "../map.js";
import { state } from "../state.js";
import { $, esc, icon, timeText, toast } from "../utils.js";

export function clearRoutes() {
  routeLayer.clearLayers();
  state.routes = null;
  $("#route-results").innerHTML =
    '<div class="empty-state">Chọn điểm đi và đến, sau đó tìm tuyến theo dữ liệu mới nhất.</div>';
}

export function openRoute() {
  if (!state.data) {
    toast("Đang tải dữ liệu, vui lòng thử lại.");
    return;
  }
  $("#event-panel").hidden = true;
  $("#route-panel").hidden = false;
  requestAnimationFrame(() => map.invalidateSize());
}

export async function findRoutes(e) {
  e.preventDefault();
  if (!state.connected) {
    toast("Cần kết nối máy chủ để tính tuyến mới.");
    return;
  }
  const button = $("button[type=submit]", $("#route-form"));
  button.disabled = true;
  button.textContent = "Đang tính tuyến…";
  try {
    const query = new URLSearchParams({
      origin: $("#route-origin").value,
      destination: $("#route-destination").value,
      horizon: $("#route-time").value,
      vehicle: $("#route-vehicle").value,
    });
    state.routes = await api("/api/routes?" + query);
    state.routeIndex = 0;
    renderRoutes();
  } catch (err) {
    clearRoutes();
    $("#route-results").innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
  } finally {
    button.disabled = false;
    button.innerHTML = icon("route") + "Tìm tuyến gợi ý";
  }
}

export function renderRoutes() {
  routeLayer.clearLayers();
  const result = state.routes;
  if (!result.routes.length) {
    $("#route-results").innerHTML =
      `<div class="empty-state">${icon("alert")}${esc(result.message)}</div>`;
    return;
  }
  $("#route-results").innerHTML =
    result.routes
      .map(
        (r, i) =>
          `<button class="route-choice ${i === state.routeIndex ? "selected" : ""}" data-route-index="${i}"><h3>${esc(r.title)}</h3><strong>${Math.ceil(r.eta_minutes)}<small>phút</small></strong><span class="data-label">${r.distance_km} km</span><p>${esc(r.steps.join(" → "))}</p><p>${r.warnings.length ? "Còn cảnh báo trên " + r.warnings.length + " đoạn" : "Không đi qua sự kiện đang hiển thị"} · Mô phỏng</p></button>`,
      )
      .join("") +
    `<p class="route-timestamp" id="route-calculation-note">Tính lúc ${timeText(result.calculated_at)} · Loại ${result.excluded} đoạn đóng / thiếu dữ liệu.</p>`;
  const chosen = result.routes[state.routeIndex];
  for (const [i, r] of result.routes.entries())
    if (i !== state.routeIndex)
      L.polyline(r.coordinates, {
        color: "#adb7b4",
        weight: 6,
        opacity: 0.8,
        dashArray: "7 6",
      }).addTo(routeLayer);
  L.polyline(chosen.coordinates, { color: "white", weight: 10, opacity: 0.95 }).addTo(routeLayer);
  const line = L.polyline(chosen.coordinates, { color: "#0c7665", weight: 6, opacity: 1 }).addTo(
    routeLayer,
  );
  for (const [coord, label] of [
    [chosen.coordinates[0], "A"],
    [chosen.coordinates.at(-1), "B"],
  ])
    L.marker(coord, {
      icon: L.divIcon({
        className: "event-marker",
        html: `<strong>${label}</strong>`,
        iconSize: [32, 32],
      }),
    }).addTo(routeLayer);
  map.fitBounds(line.getBounds(), { padding: [60, 75], maxZoom: 14 });
}

export function initRouting() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (button && button.dataset.routeIndex) {
      state.routeIndex = Number(button.dataset.routeIndex);
      renderRoutes();
    }
  });
  $("#open-route").addEventListener("click", openRoute);
  $("#close-route").addEventListener("click", () => {
    $("#route-panel").hidden = true;
    $("#event-panel").hidden = false;
    routeLayer.clearLayers();
  });
  $("#route-form").addEventListener("submit", findRoutes);
}
