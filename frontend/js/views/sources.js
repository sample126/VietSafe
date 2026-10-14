/** Trang "Nguồn dữ liệu": thẻ nguồn, điều khiển kịch bản mô phỏng, trạng thái pipeline. */
import { DATA_SOURCES } from "../data/sources.js";
import { $, icon } from "../utils.js";
import { changeScenario } from "../scenario.js";

export function renderSources() {
  $("#source-grid").innerHTML = DATA_SOURCES.map(
    ([i, n, s, c, d, plan]) =>
      `<article class="source-card">${icon(i)}<h3>${n}</h3><span class="tag tag-${c}">${s}</span><p>${d}</p>${plan !== "—" ? `<p class="source-plan"><strong>Kế hoạch thu thập:</strong> ${plan}</p>` : ""}</article>`,
  ).join("");
}

export function initSources() {
  $("#source-scenario").addEventListener("change", (e) => changeScenario(e.target.value));
}
