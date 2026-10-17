/** Điều khiển trên bản đồ: lớp hiển thị, nền bản đồ, thu phóng, vị trí của tôi, mốc thời gian. */
import { map, renderMap, setBaseTiles, syncMajorRoads } from "./map.js";
import { state } from "./state.js";
import { $, $$ } from "./utils.js";
import { geolocate } from "./views/report-form.js";

export function initMapControls() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (button && button.dataset.horizon) {
      state.horizon = Number(button.dataset.horizon);
      $$("#map-horizon button").forEach((b) =>
        b.classList.toggle("active", b === button),
      );
      if (state.data) renderMap();
    }
  });
  $("#toggle-layers").addEventListener(
    "click",
    () => ($("#layer-menu").hidden = !$("#layer-menu").hidden),
  );
  let panelBusy = false;
  $("#toggle-event-panel").addEventListener("click", () => {
    const panel = $("#event-panel");

    if (panelBusy) return;
    $("#route-panel").hidden = true;

    if (panel.classList.contains("is-closed")) {
      panel.classList.remove("is-closed"); // hiện lại -> CSS tự chạy panel-in
      $("#open-route").classList.remove("active");
      $("#toggle-event-panel").classList.add("active");
      panel.hidden = false;
      requestAnimationFrame(() => map.invalidateSize());
    } else {
      panelBusy = true;
      panel.classList.add("is-closing"); // chạy panel-out
      $("#toggle-event-panel").classList.remove("active");
      setTimeout(() => {
        panel.classList.remove("is-closing");
        panel.classList.add("is-closed"); // sau khi trượt xong mới display:none
        panelBusy = false;
        map.invalidateSize();
      }, 300); // = thời gian animation trong CSS
    }
  });
  $$("[data-layer]").forEach((el) =>
    el.addEventListener("change", () => {
      state.layers[el.dataset.layer] = el.checked;
      if (el.dataset.layer === "majorRoads") {
        syncMajorRoads();
        return;
      }
      if (state.data) renderMap();
    }),
  );
  $("#base-tiles").addEventListener("change", (e) =>
    setBaseTiles(e.target.checked),
  );
  $("#fit-map").addEventListener("click", () => {
    if (state.data)
      map.fitBounds(
        state.data.nodes.map((n) => [n.lat, n.lng]),
        { padding: [40, 55] },
      );
  });
  $("#my-location").addEventListener("click", () => geolocate());
}
