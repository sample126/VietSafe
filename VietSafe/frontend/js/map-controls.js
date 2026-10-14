/** Điều khiển trên bản đồ: lớp hiển thị, nền bản đồ, thu phóng, vị trí của tôi, mốc thời gian. */
import { map, renderMap, setBaseTiles } from "./map.js";
import { state } from "./state.js";
import { $, $$ } from "./utils.js";
import { geolocate } from "./views/report-form.js";

export function initMapControls() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (button && button.dataset.horizon) {
      state.horizon = Number(button.dataset.horizon);
      $$("#map-horizon button").forEach((b) => b.classList.toggle("active", b === button));
      if (state.data) renderMap();
    }
  });
  $("#toggle-layers").addEventListener(
    "click",
    () => ($("#layer-menu").hidden = !$("#layer-menu").hidden),
  );
  $$("[data-layer]").forEach((el) =>
    el.addEventListener("change", () => {
      state.layers[el.dataset.layer] = el.checked;
      if (state.data) renderMap();
    }),
  );
  $("#base-tiles").addEventListener("change", (e) => setBaseTiles(e.target.checked));
  $("#fit-map").addEventListener("click", () => {
    if (state.data)
      map.fitBounds(
        state.data.nodes.map((n) => [n.lat, n.lng]),
        { padding: [40, 55] },
      );
  });
  $("#my-location").addEventListener("click", () => geolocate());
}
