const $ = (id) => document.getElementById(id);
const scalarFields = [
  "initial_depth_cm",
  "catchment_area_ha",
  "ponding_area_m2",
  "runoff_coefficient",
  "drainage_capacity_lps",
  "blockage_percent",
  "threshold_cm",
  "sustain_minutes",
];
let catalog;
let latest = null;
let revision = 0;
let requestController;

const format = (value, digits = 1) =>
  Number(value).toLocaleString("vi-VN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

function textNode(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function status(message, error = false) {
  $("scenario-status").textContent = message;
  $("scenario-status").dataset.error = String(error);
}

function invalidate() {
  revision++;
  requestController?.abort();
  latest = null;
  $("scenario-result").hidden = true;
  $("scenario-empty").hidden = false;
  $("scenario-run").disabled = !catalog;
  status("Thông số đã thay đổi. Bấm tính để xem kết quả mới.");
}

function fillPreset(id) {
  const preset = catalog.presets.find((p) => p.id === id);
  if (!preset) return;
  invalidate();
  for (const field of scalarFields) $(field).value = preset.inputs[field];
  preset.inputs.rain_mm_h.forEach((r, i) => {
    $(`rain-${i}`).value = r;
  });
}

export function readInputs() {
  const inputs = Object.fromEntries(
    scalarFields.map((field) => [field, Number($(field).value)]),
  );
  inputs.rain_mm_h = Array.from({ length: 12 }, (_, i) =>
    Number($(`rain-${i}`).value),
  );
  return inputs;
}

export function toCSV(result) {
  const rows = [
    "synthetic,model_version,minute,depth_cm,comparison_depth_cm,rain_mm_h_next_interval,inflow_cumulative_m3,outflow_cumulative_m3",
  ];
  for (const point of result.trajectory) {
    rows.push(
      [
        true,
        result.model_version,
        point.minute,
        point.depth_cm,
        result.comparison.trajectory[point.minute].depth_cm,
        point.minute < 60
          ? result.inputs.rain_mm_h[Math.floor(point.minute / 5)]
          : "",
        point.inflow_cumulative_m3,
        point.outflow_cumulative_m3,
      ].join(","),
    );
  }
  return rows.join("\r\n");
}

function chart(result) {
  const w = Math.max(300, $("depth-chart").clientWidth || 720),
    h = 265,
    left = 43,
    right = 18,
    top = 15,
    bottom = 37;
  const max = Math.max(
    result.comparison.max_depth_cm,
    result.max_depth_cm,
    result.inputs.threshold_cm,
    1,
  );
  const limit = Math.ceil((max * 1.15) / 5) * 5;
  const x = (m) => left + (m / 60) * (w - left - right);
  const y = (cm) => h - bottom - (cm / limit) * (h - top - bottom);
  const path = (points) =>
    points
      .map(
        (p, i) =>
          `${i ? "L" : "M"}${x(p.minute).toFixed(2)},${y(p.depth_cm).toFixed(2)}`,
      )
      .join(" ");
  let grid = "";
  for (let i = 0; i <= 4; i++) {
    const value = (limit * i) / 4;
    grid += `<line x1="${left}" y1="${y(value)}" x2="${w - right}" y2="${y(value)}" stroke="#e6ece9"/><text x="${left - 9}" y="${y(value) + 4}" text-anchor="end" fill="#82948b" font-size="11">${format(value)}</text>`;
  }
  for (let minute = 0; minute <= 60; minute += 10) {
    grid += `<text x="${x(minute)}" y="${h - 12}" text-anchor="middle" fill="#82948b" font-size="11">${minute}′</text>`;
  }
  const basePath = path(result.trajectory);
  const markers = result.horizons
    .map(
      (p) =>
        `<circle cx="${x(p.minutes)}" cy="${y(p.depth_cm)}" r="4" fill="#187c66" stroke="white" stroke-width="2"/>`,
    )
    .join("");
  $("depth-chart").innerHTML =
    `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Độ sâu mô phỏng từng phút, đường xanh là kịch bản chọn, đường cam là khi công suất thoát giảm một nửa"><defs><linearGradient id="depth-fill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#27967b" stop-opacity=".18"/><stop offset="1" stop-color="#27967b" stop-opacity=".02"/></linearGradient></defs>${grid}<path d="${basePath} L${x(60)},${y(0)} L${x(0)},${y(0)} Z" fill="url(#depth-fill)"/><line x1="${left}" x2="${w - right}" y1="${y(result.inputs.threshold_cm)}" y2="${y(result.inputs.threshold_cm)}" stroke="#96a398" stroke-dasharray="5 4"/><path d="${path(result.comparison.trajectory)}" stroke="#c78b46" stroke-width="2" fill="none"/><path d="${basePath}" stroke="#15816b" stroke-width="2.7" fill="none"/>${markers}</svg>`;
  const rainMax = Math.max(...result.inputs.rain_mm_h, 10);
  const bars = result.inputs.rain_mm_h
    .map((value, i) => {
      const height = (value / rainMax) * 60;
      const label =
        w >= 600 || i % 2 === 0
          ? `<text x="${x(i * 5 + 2.5)}" y="91" text-anchor="middle" font-size="9" fill="#8b9e93">${i * 5}–${i * 5 + 5}′</text>`
          : "";
      return `<rect x="${x(i * 5) + 4}" y="${72 - height}" width="${(w - left - right) / 12 - 8}" height="${height}" rx="2" fill="#9ecac0"/><text x="${x(i * 5 + 2.5)}" y="${Math.max(10, 67 - height)}" text-anchor="middle" font-size="10" fill="#5e8478">${value}</text>${label}`;
    })
    .join("");
  $("rain-chart").innerHTML =
    `<svg viewBox="0 0 ${w} 100" role="img" aria-label="Cường độ mưa giả định mm/h trong từng khoảng 5 phút">${bars}</svg>`;
}

function render(result) {
  const already = result.initially_above_threshold;
  const onset = result.first_onset_minute;
  $("scenario-summary").textContent = already
    ? `Ban đầu nước đã đạt ngưỡng ${format(result.inputs.threshold_cm)} cm. Theo dõi độ sâu tăng hoặc rút; không tính là một đợt xuất hiện ngập mới từ trạng thái dưới ngưỡng.`
    : onset === null
      ? `Trong kịch bản này, chưa đủ điều kiện xác nhận xuất hiện ngập trong 60 phút: độ sâu cần đạt ${format(result.inputs.threshold_cm)} cm và duy trì ${result.inputs.sustain_minutes} phút.`
      : `Nước bắt đầu đạt ngưỡng ở phút ${format(onset)}; đủ thời gian duy trì để xác nhận ở phút ${format(result.confirmed_at_minute)}. Đây là thời gian trong mô phỏng.`;
  $("horizon-cards").replaceChildren();
  for (const horizon of result.horizons) {
    const card = textNode("article", "", "horizon");
    card.append(textNode("p", `SAU ${horizon.minutes} PHÚT`, "eyebrow"));
    const depth = textNode(
      "div",
      `${format(horizon.depth_cm)} `,
      "depth-value",
    );
    depth.append(textNode("span", "cm"));
    card.append(
      depth,
      textNode("p", "Độ sâu tại đúng thời điểm này", "depth-caption"),
    );
    const confirmed = horizon.onset_status === "onset_confirmed";
    card.append(
      textNode(
        "div",
        already
          ? "Đã vượt ngưỡng lúc bắt đầu"
          : confirmed
            ? "Có xuất hiện ngập mới"
            : "Chưa xác nhận ngập mới",
        `event-label ${already ? "initial" : confirmed ? "flood" : ""}`,
      ),
    );
    card.append(
      textNode(
        "p",
        already
          ? "Kịch bản bắt đầu khi đã có nước trên ngưỡng."
          : `Xét toàn bộ ${horizon.minutes} phút, gồm điều kiện duy trì ${result.inputs.sustain_minutes} phút.`,
        "event-help",
      ),
    );
    $("horizon-cards").append(card);
  }
  $("scenario-result").hidden = false;
  chart(result);
  $("rain-total").textContent =
    `${format(result.rainfall_total_mm)} mm / 60 phút · cột: mm/h`;
  const table = document.createElement("table");
  const header = table.createTHead().insertRow();
  for (const text of ["Kịch bản", "+30 phút", "+60 phút"])
    header.append(textNode("th", text));
  const body = table.createTBody();
  for (const [label, horizons] of [
    ["Bạn chọn", result.horizons],
    ["Thoát nước giảm một nửa", result.comparison.horizons],
  ]) {
    const row = body.insertRow();
    row.append(textNode("td", label));
    for (const horizon of horizons)
      row.append(textNode("td", `${format(horizon.depth_cm)} cm`));
  }
  $("scenario-comparison").replaceChildren(table);
  $("scenario-limitations").replaceChildren(
    ...result.limitations.map((s) => textNode("li", s)),
  );
  $("scenario-input-details").textContent = JSON.stringify(
    {
      model_version: result.model_version,
      mode: result.mode,
      uses_trained_ai: result.uses_trained_ai,
      hanoi_calibrated: result.hanoi_calibrated,
      probability: result.probability,
      inputs: result.inputs,
      water_balance: result.water_balance,
    },
    null,
    2,
  );
  $("scenario-result").hidden = false;
  $("scenario-empty").hidden = true;
}

export async function runScenario() {
  if (!$("scenario-form").reportValidity()) return;
  invalidate();
  const currentRevision = revision;
  requestController = new AbortController();
  $("scenario-run").disabled = true;
  status("Đang tính cân bằng nước và thời điểm vượt ngưỡng…");
  try {
    const response = await fetch("/api/flood-simulation/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-VietSafe": "local" },
      signal: requestController.signal,
      body: JSON.stringify(readInputs()),
    });
    const data = await response.json();
    if (currentRevision !== revision) return;
    if (!response.ok) throw new Error(data.error || "Không thể tính kịch bản.");
    latest = data;
    render(data);
    status(
      "Đã tính từ các giả định bên trái · Mô phỏng cân bằng nước, không phải xác suất ngập đã hiệu chỉnh.",
    );
  } catch (error) {
    if (currentRevision !== revision || error.name === "AbortError") return;
    status(error.message || "Không kết nối được máy chủ local.", true);
  } finally {
    if (currentRevision === revision) $("scenario-run").disabled = false;
  }
}

function download(kind) {
  if (!latest) return;
  const blob = new Blob(
    [kind === "json" ? JSON.stringify(latest, null, 2) : toCSV(latest)],
    {
      type:
        kind === "json"
          ? "application/json;charset=utf-8"
          : "text/csv;charset=utf-8",
    },
  );
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `vietsafe-synthetic-scenario.${kind}`;
  anchor.click();
  setTimeout(() => window.URL.revokeObjectURL(url), 1000);
}

async function init() {
  window.addEventListener("resize", () => {
    if (latest && !$("scenario-result").hidden) chart(latest);
  });
  $("scenario-form").addEventListener("input", invalidate);
  $("scenario-form").addEventListener("submit", (event) => {
    event.preventDefault();
    void runScenario();
  });
  $("scenario-preset").addEventListener("change", () => {
    fillPreset($("scenario-preset").value);
    void runScenario();
  });
  $("download-json").addEventListener("click", () => download("json"));
  $("download-csv").addEventListener("click", () => download("csv"));
  try {
    const response = await fetch("/api/flood-simulation/catalog");
    if (!response.ok)
      throw new Error("Không tải được kịch bản. Kiểm tra máy chủ VietSafe.");
    catalog = await response.json();
    for (let i = 0; i < 12; i++) {
      const label = textNode("label", `${i * 5}–${i * 5 + 5} phút`);
      const input = document.createElement("input");
      input.id = `rain-${i}`;
      input.type = "number";
      input.min = "0";
      input.max = "150";
      input.step = "0.1";
      input.required = true;
      input.setAttribute(
        "aria-label",
        `Cường độ mưa phút ${i * 5} đến ${i * 5 + 5} (mm/h)`,
      );
      label.append(input);
      $("rain-inputs").append(label);
    }
    for (const preset of catalog.presets) {
      const option = textNode("option", preset.name);
      option.value = preset.id;
      $("scenario-preset").append(option);
    }
    $("scenario-preset").disabled = false;
    fillPreset(catalog.presets[0].id);
    await runScenario();
  } catch (error) {
    $("scenario-run").disabled = true;
    status(error.message || "Không kết nối được máy chủ local.", true);
  }
}

void init();
