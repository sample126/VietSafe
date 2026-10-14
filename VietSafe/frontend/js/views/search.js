/** Ô tìm kiếm địa điểm trên bản đồ (gọi /api/search, có debounce 300ms). */
import { api } from "../api.js";
import { map, selectionLayer } from "../map.js";
import { $, toast } from "../utils.js";
import { selectRoad } from "./road-details.js";

let searchTimer;
let searchSerial = 0;

export async function searchLocation() {
  const serial = ++searchSerial,
    query = $("#map-search").value.trim();
  if (!query) {
    $("#search-results").hidden = true;
    return;
  }
  try {
    const result = await api("/api/search?q=" + encodeURIComponent(query));
    if (serial !== searchSerial) return;
    const container = $("#search-results");
    container.replaceChildren();
    container.hidden = false;
    if (!result.results.length) {
      container.innerHTML =
        "<p>Chưa có địa điểm này trong vùng thử nghiệm. Thử “Láng Hạ”, “Cầu Giấy”, “Hoàn Kiếm”…</p>";
      return;
    }
    for (const place of result.results) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = place.name;
      btn.addEventListener("click", () => {
        map.setView([place.lat, place.lng], 15);
        $("#map-search").value = place.name;
        container.hidden = true;
        selectionLayer.clearLayers();
        L.circleMarker([place.lat, place.lng], {
          radius: 9,
          color: "#087f72",
          fillOpacity: 0.2,
        }).addTo(selectionLayer);
        if (place.kind === "road") selectRoad(place.id);
      });
      container.append(btn);
    }
  } catch (e) {
    toast(e.message);
  }
}

export function initSearch() {
  $("#search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    searchLocation();
  });
  $("#map-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchLocation, 300);
  });
}
