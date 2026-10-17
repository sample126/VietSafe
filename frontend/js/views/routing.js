/** Bảng "Tìm tuyến thay thế": chọn điểm đi/đến, phương tiện, thời điểm và hiển thị tuyến. */
import { api } from "../api.js";
import { map, renderMap, routeLayer } from "../map.js";
import { state } from "../state.js";
import { $, esc, icon, timeText, toast } from "../utils.js";

export function clearRoutes() {
  routeLayer.clearLayers();
  map.getContainer().classList.remove("route-active");
  if (state.data) renderMap();
  $("#route-map-key").hidden = true;
  state.routes = null;
  $("#route-results").innerHTML =
    '<div class="empty-state">Chọn điểm đi và đến, sau đó tìm tuyến theo dữ liệu mới nhất.</div>';
}

function setPickedPoint(field, lat, lng) {
  const select = $(`#route-${field}`);
  select.querySelector('[data-picked="true"]')?.remove();
  const option = new Option(
    `Điểm trên bản đồ · ${lat.toFixed(4)}, ${lng.toFixed(4)}`,
    `${lat.toFixed(6)},${lng.toFixed(6)}`,
  );
  option.dataset.picked = "true";
  select.add(option);
  select.value = option.value;
  state.routePicking = null;
  document
    .querySelectorAll(".route-pick")
    .forEach((button) => button.classList.remove("active"));
  $("#route-pick-hint")?.remove();
}

export function openRoute() {
  if (!state.data) {
    toast("Đang tải dữ liệu, vui lòng thử lại.");
    return;
  }
  $("#event-panel").hidden = true;
  $("#event-panel").classList.add("is-closed");
  $("#route-panel").hidden = false;
  $("#open-route").classList.add("active");
  $("#toggle-event-panel").classList.remove("active");
}

export function closeRoute() {
  $("#route-panel").hidden = true;
  $("#open-route").classList.remove("active");
  routeLayer.clearLayers();
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
    state.routes = await api("/api/routes?" + query, { timeoutMs: 30000 });
    state.routeIndex = 0;
    state.horizon = Number($("#route-time").value);
    document
      .querySelectorAll("#map-horizon button")
      .forEach((item) =>
        item.classList.toggle(
          "active",
          Number(item.dataset.horizon) === state.horizon,
        ),
      );
    renderMap();
    renderRoutes();
  } catch (err) {
    clearRoutes();
    $("#route-results").innerHTML =
      `<div class="empty-state">${esc(err.message)}</div>`;
  } finally {
    button.disabled = false;
    button.innerHTML = icon("route") + "Tìm tuyến gợi ý";
  }
}

export function renderRoutes() {
  routeLayer.clearLayers();
  const result = state.routes;
  if (!result.routes.length) {
    map.getContainer().classList.remove("route-active");
    renderMap();
    $("#route-map-key").hidden = true;
    $("#route-results").innerHTML =
      `<div class="empty-state">${icon("alert")}${esc(result.message)}</div>`;
    return;
  }
  $("#route-results").innerHTML =
    result.routes
      .map(
        (r, i) =>
          `<button class="route-choice ${i === state.routeIndex ? "selected" : ""}" data-route-index="${i}" type="button"><div class="route-summary"><h3>${esc(r.title)}</h3><strong>${Math.ceil(r.eta_minutes)}<small>phút</small></strong></div><p class="route-meta">${r.distance_km} km · ${esc({ motorbike: "Xe máy", car: "Ô tô", walk: "Đi bộ" }[r.vehicle])} · Nguy cơ ${r.max_risk}/100</p><p class="route-warnings">${r.warnings.length ? `${r.warnings.length} cảnh báo trên tuyến` : "Không có cảnh báo trên tuyến"}</p></button>`,
      )
      .join("") +
    `<div class="route-forecast" aria-label="So sánh cùng tuyến theo thời điểm">${result.routes[state.routeIndex].forecast_timeline.map((point) => `<button type="button" data-route-horizon="${point.horizon}" class="${Number($("#route-time").value) === point.horizon ? "active" : ""}"><span>${point.horizon ? `+${point.horizon} phút` : "Hiện tại"}</span><strong>${Math.ceil(point.eta_minutes)} phút</strong><small>${point.congested_segments} ùn tắc · ${point.flooded_segments} ngập</small></button>`).join("")}</div>` +
    `<details class="route-details"><summary>Chi tiết hành trình</summary><p><strong>${esc(result.routes[state.routeIndex].origin_name)}</strong> → <strong>${esc(result.routes[state.routeIndex].destination_name)}</strong></p><p>Đoạn cần lưu ý: ${result.routes[state.routeIndex].warnings.length ? esc(result.routes[state.routeIndex].warnings.join(", ")) : "Không có cảnh báo mô phỏng trên tuyến."}</p><ol>${result.routes[state.routeIndex].steps.map((name) => `<li>${esc(name)}</li>`).join("")}</ol></details>` +
    `<p class="route-timestamp" id="route-calculation-note">Tính lúc ${timeText(result.calculated_at)} · Loại ${result.excluded} đoạn đóng / thiếu dữ liệu.</p>`;
  const chosen = result.routes[state.routeIndex];
  map.getContainer().classList.add("route-active");
  renderMap();
  $("#route-map-key").hidden = false;
  $("#route-alternative-key").hidden = result.routes.length < 2;
  for (const [i, r] of result.routes.entries())
    if (i !== state.routeIndex)
      L.polyline(r.coordinates, {
        color: "#7f7696",
        weight: 4,
        opacity: 0.85,
        dashArray: "8 7",
      }).addTo(routeLayer);
  L.polyline(chosen.coordinates, {
    color: "white",
    weight: 12,
    opacity: 0.98,
    interactive: false,
  }).addTo(routeLayer);
  const line = L.polyline(chosen.coordinates, {
    color: "#6940cf",
    weight: 7,
    opacity: 1,
  }).addTo(routeLayer);
  for (const [coord, label] of [
    [chosen.coordinates[0], "A"],
    [chosen.coordinates.at(-1), "B"],
  ])
    L.marker(coord, {
      zIndexOffset: 2000,
      icon: L.divIcon({
        className: `route-endpoint route-${label.toLowerCase()}`,
        html: `<strong>${label}</strong>`,
        iconSize: [32, 32],
      }),
    }).addTo(routeLayer);
  map.fitBounds(line.getBounds(), { padding: [60, 75], maxZoom: 14 });
}

export function initRouting() {
  let searchTimer;
  let searchSerial = 0;
  $("#route-place-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    const serial = ++searchSerial;
    const query = $("#route-place-search").value.trim();
    const container = $("#route-place-results");
    if (query.length < 2) {
      container.hidden = true;
      return;
    }
    searchTimer = setTimeout(async () => {
      try {
        const { results } = await api(
          "/api/search?q=" + encodeURIComponent(query),
        );
        if (serial !== searchSerial) return;
        container.replaceChildren();
        if (!results.length) {
          container.textContent =
            "Không tìm thấy địa điểm trong dữ liệu OSM cục bộ.";
          container.hidden = false;
          return;
        }
        for (const place of results) {
          const row = document.createElement("div");
          row.className = "route-place-item";
          const label = document.createElement("span");
          label.textContent = place.name;
          row.append(label);
          for (const [field, letter] of [
            ["origin", "A"],
            ["destination", "B"],
          ]) {
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = letter;
            button.title = `Chọn làm điểm ${field === "origin" ? "đi" : "đến"}`;
            button.addEventListener("click", () => {
              if (place.kind === "node") $("#route-" + field).value = place.id;
              else setPickedPoint(field, place.lat, place.lng);
              $("#route-place-search").value = place.name;
              container.hidden = true;
            });
            row.append(button);
          }
          container.append(row);
        }
        container.hidden = false;
      } catch (error) {
        toast(error.message);
      }
    }, 300);
  });
  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (button && button.dataset.routeHorizon !== undefined) {
      $("#route-time").value = button.dataset.routeHorizon;
      findRoutes(new Event("submit"));
      return;
    }
    if (button && button.dataset.routeIndex) {
      state.routeIndex = Number(button.dataset.routeIndex);
      renderRoutes();
    }
  });
  $("#open-route").addEventListener("click", () => {
    if ($("#route-panel").hidden) openRoute();
    else closeRoute();
  });
  $("#route-swap").addEventListener("click", () => {
    const a = $("#route-origin"),
      b = $("#route-destination");
    const old = a.value;
    for (const [source, target] of [
      [a, b],
      [b, a],
    ]) {
      const picked = source.querySelector('[data-picked="true"]');
      if (
        picked &&
        ![...target.options].some((option) => option.value === picked.value)
      )
        target.add(picked.cloneNode(true));
    }
    a.value = b.value;
    b.value = old;
  });
  document.querySelectorAll(".route-pick").forEach((button) =>
    button.addEventListener("click", () => {
      state.routePicking = button.dataset.routePick;
      document
        .querySelectorAll(".route-pick")
        .forEach((item) => item.classList.toggle("active", item === button));
      $("#route-pick-hint")?.remove();
      button
        .closest(".route-panel")
        .querySelector("#route-form")
        .insertAdjacentHTML(
          "beforeend",
          '<p id="route-pick-hint" class="route-pick-hint">Chạm vào bản đồ để chọn vị trí.</p>',
        );
      toast("Chạm vào bản đồ để chọn điểm.");
    }),
  );
  window.addEventListener("route-point-picked", (event) =>
    setPickedPoint(state.routePicking, event.detail.lat, event.detail.lng),
  );
  $("#route-form").addEventListener("submit", findRoutes);
}
