/** Research replay UI. Independent from Hanoi demo state and routing decisions. */
import { esc } from "../utils.js";

const $ = (id) => document.getElementById(id);
let tasks = [],
  selected,
  sites = [],
  result,
  revision = 0,
  pending;

export function formatValue(value, unit) {
  if (value === null || !Number.isFinite(value)) return "Thiếu dữ liệu";
  if (unit === "probability") return `${(value * 100).toFixed(1)} %`;
  return `${value.toFixed(3)} ${unit === "m" ? "m" : "(thang gốc)"}`;
}

async function request(path, body, signal) {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    signal,
    headers: {
      "X-VietSafe": "local",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Không đọc được dữ liệu AI.");
  return data;
}

function status(message, error = false) {
  $("ai-status").textContent = message;
  $("ai-status").dataset.error = String(error);
}

function invalidate() {
  revision += 1;
  pending?.abort();
  pending = new AbortController();
  result = null;
  $("ai-result").hidden = true;
  $("ai-run").disabled = true;
  return { id: revision, signal: pending.signal };
}

function options(id, values, preferred) {
  const select = $(id);
  select.replaceChildren(
    ...values.map(({ id: value, label }) => new Option(label, value)),
  );
  if (values.some((row) => row.id === preferred)) select.value = preferred;
  select.disabled = values.length === 0;
}

async function loadTimes(preferred, context = invalidate()) {
  options("ai-origin", []);
  status("Đang đọc các thời điểm đủ dữ liệu…");
  try {
    const query = new URLSearchParams({
      task: selected.id,
      site_id: $("ai-site").value,
      day: $("ai-day").value,
    });
    const data = await request(`/api/ai/times?${query}`, null, context.signal);
    if (context.id !== revision) return;
    options("ai-origin", data.times, preferred);
    $("ai-run").disabled = data.times.length === 0;
    status(
      data.times.length
        ? "Sẵn sàng. Chọn thời điểm rồi chạy mô hình."
        : "Không có cửa sổ hợp lệ trong ngày này.",
    );
  } catch (error) {
    if (context.id === revision && error.name !== "AbortError")
      status(error.message, true);
  }
}

function loadDays(preferred, origin, context) {
  const site = sites.find((row) => row.id === $("ai-site").value);
  options(
    "ai-day",
    (site?.days || []).map((day) => ({
      id: day,
      label: day === "test" ? "Tập kiểm thử (chỉ số dòng)" : day,
    })),
    preferred,
  );
  return loadTimes(origin, context);
}

async function selectTask(task) {
  const context = invalidate();
  selected = task;
  for (const button of $("ai-tasks").children)
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.task === task.id),
    );
  $("ai-heading").textContent = task.title;
  $("ai-description").textContent = task.description;
  $("ai-day-label").textContent = task.date_label;
  ["ai-site", "ai-day", "ai-origin"].forEach((id) => options(id, []));
  if (!["available", "ready"].includes(task.status))
    return status(task.message, true);
  status("Đang xác minh tệp và nạp mô hình. Lần đầu có thể mất vài giây…");
  try {
    const data = await request(
      `/api/ai/sites?task=${task.id}`,
      null,
      context.signal,
    );
    if (context.id !== revision) return;
    sites = data.sites;
    options(
      "ai-site",
      sites.map((site) => ({ id: site.id, label: site.name })),
      data.default.site_id,
    );
    await loadDays(data.default.day, data.default.origin, context);
  } catch (error) {
    if (context.id === revision && error.name !== "AbortError")
      status(error.message, true);
  }
}

function chart(data) {
  if (!data.history.length)
    return '<p class="chart-note">Mỗi xác suất ứng với một cửa sổ tương lai. Các giá trị này không biểu diễn độ sâu ngập.</p>';
  const history = data.history.filter((p) => p.value !== null);
  const future = data.horizons.map((p) => ({
    offset_minutes: p.minutes,
    value: p.value,
  }));
  const values = [...history, ...future];
  const lo = Math.min(...values.map((p) => p.value)),
    hi = Math.max(...values.map((p) => p.value));
  const start = data.history[0].offset_minutes,
    end = future.at(-1).offset_minutes;
  const x = (v) => 55 + ((v - start) / (end - start)) * 810;
  const y = (v) => 180 - ((v - lo) / (hi - lo || 1)) * 135;
  // Null observations create gaps; never draw them as measured zero or filled observations.
  let pen = false;
  const path = data.history
    .map((p) => {
      if (p.value === null) {
        pen = false;
        return "";
      }
      const command = `${pen ? "L" : "M"}${x(p.offset_minutes)},${y(p.value)}`;
      pen = true;
      return command;
    })
    .join(" ");
  return `<svg class="chart" viewBox="0 0 920 220" role="img" aria-label="Lịch sử quan trắc và các điểm dự báo"><line x1="55" x2="865" y1="185" y2="185" stroke="#ccd9cc"/><line x1="${x(0)}" x2="${x(0)}" y1="20" y2="185" stroke="#aebead" stroke-dasharray="4 5"/><path d="${path}" fill="none" stroke="#3f7960" stroke-width="2.5"/><text x="5" y="48" fill="#657666" font-size="12">${hi.toFixed(2)}</text><text x="5" y="180" fill="#657666" font-size="12">${lo.toFixed(2)}</text>${future.map((p) => `<circle cx="${x(p.offset_minutes)}" cy="${y(p.value)}" r="5" fill="#bb8738"/><text x="${x(p.offset_minutes)}" y="210" text-anchor="middle" fill="#687966" font-size="12">+${p.offset_minutes}′</text>`).join("")}<text x="55" y="210" fill="#687966" font-size="12">${start}′</text><text x="${x(0)}" y="210" text-anchor="middle" fill="#687966" font-size="12">Hiện tại</text></svg><p class="chart-note">Đường xanh: quan trắc quá khứ · Chấm vàng: dự báo. Phần bên phải mốc hiện tại không chứa quan trắc tương lai.</p>`;
}

export function renderResult(data) {
  $("ai-origin-label").textContent =
    `${data.dataset} · ${data.site_id} · ${data.origin}${data.origin_kind === "row_index" ? " (chỉ số dòng)" : data.origin_kind === "source_datetime" ? " (giờ nguồn; chưa quy đổi múi giờ)" : ""}`;
  const cards = [
    {
      label: "Quan trắc hiện tại",
      value: data.current.value,
      unit: data.current.unit,
    },
    ...data.horizons.map((p) => ({
      label: `${data.unit === "probability" ? "Trong" : "Sau"} ${p.minutes} phút`,
      value: p.value,
      unit: data.unit,
    })),
  ];
  $("ai-values").innerHTML = cards
    .map(
      (p) =>
        `<div class="value"><span>${esc(p.label)}</span><strong>${esc(formatValue(p.value, p.unit))}</strong></div>`,
    )
    .join("");
  $("ai-chart").innerHTML = chart(data);
  $("ai-details").textContent = JSON.stringify(
    {
      model: data.model,
      model_version: data.model_version,
      quantity: data.quantity,
      unit: data.unit,
      input_summary: data.input_summary,
      horizon_probabilities_consistent: data.horizon_probabilities_consistent,
      public_alert_allowed: data.public_alert_allowed,
      hanoi_calibrated: data.hanoi_calibrated,
    },
    null,
    2,
  );
  $("ai-result").hidden = false;
}

export async function initAI() {
  $("ai-site").addEventListener("change", () => loadDays());
  $("ai-day").addEventListener("change", () => loadTimes());
  $("ai-origin").addEventListener("change", () => {
    invalidate();
    $("ai-run").disabled = !$("ai-origin").value;
    status("Thời điểm đã thay đổi. Chạy lại để xem kết quả.");
  });
  $("ai-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const context = invalidate();
    status("Đang chạy suy luận trên checkpoint đã huấn luyện…");
    try {
      const data = await request(
        "/api/ai/predict",
        {
          task: selected.id,
          site_id: $("ai-site").value,
          origin: $("ai-origin").value,
        },
        context.signal,
      );
      if (context.id !== revision) return;
      result = data;
      renderResult(data);
      status(
        data.horizon_probabilities_consistent === false
          ? "Hai xác suất theo chân trời chưa nhất quán; xem thông tin mô hình. Giữ nguyên kết quả gốc để rà soát."
          : "Đã chạy xong. Kết quả chỉ phục vụ nghiên cứu trên dữ liệu lịch sử.",
      );
    } catch (error) {
      if (context.id === revision && error.name !== "AbortError")
        status(error.message, true);
    } finally {
      if (context.id === revision) $("ai-run").disabled = !$("ai-origin").value;
    }
  });
  $("ai-download").addEventListener("click", () => {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `vietsafe-ai-${result.task}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  try {
    const data = await request("/api/ai/catalog");
    tasks = data.tasks;
    $("ai-tasks").replaceChildren(
      ...tasks.map((task, i) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "task";
        button.dataset.task = task.id;
        button.innerHTML = `<small>0${i + 1} / ${esc(task.dataset)}</small><strong>${esc(task.title)}</strong><span>${esc(task.horizons_minutes.join(" / "))} phút · ${esc(task.model)}</span>`;
        button.addEventListener("click", () => selectTask(task));
        return button;
      }),
    );
    await selectTask(tasks[0]);
  } catch (error) {
    status(error.message, true);
  }
}

if (document.getElementById("ai-form")) initAI();
