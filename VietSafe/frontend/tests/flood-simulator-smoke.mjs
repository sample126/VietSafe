/** Full HTTP + real UI module with synthetic-only data, including stale-response handling. */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import net from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const temp = mkdtempSync(path.join(tmpdir(), "vietsafe-scenario-smoke-"));
const port = await new Promise((resolve) => {
  const socket = net.createServer().listen(0, "127.0.0.1", () => {
    const assigned = socket.address().port;
    socket.close(() => resolve(assigned));
  });
});
const base = `http://127.0.0.1:${port}`;
const server = spawn(
  process.env.PYTHON || "python",
  ["-m", "vietsafe", "--host", "127.0.0.1", "--port", String(port)],
  {
    cwd: path.join(root, "backend"),
    stdio: ["ignore", "ignore", "pipe"],
    env: {
      ...process.env,
      VIETSAFE_DB: path.join(temp, "test.sqlite3"),
      PYTHONUTF8: "1",
      VIETSAFE_AI_RESEARCH_ROOT: "",
    },
  },
);
let stderr = "";
server.stderr.on("data", (chunk) => {
  stderr += chunk;
});
async function waitFor(fn) {
  const stop = Date.now() + 20000;
  while (Date.now() < stop) {
    try {
      if (await fn()) return;
    } catch {
      /* server starting */
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Timeout\n${stderr.slice(-2000)}`);
}
let checks = 0;
function check(value, label) {
  assert.ok(value, label);
  checks++;
  console.log(`ok ${label}`);
}
const realFetch = globalThis.fetch;
try {
  await waitFor(async () => (await realFetch(`${base}/api/health`)).ok);
  const dom = new JSDOM(
    readFileSync(path.join(root, "frontend/flood-simulator.html"), "utf8"),
    { url: base },
  );
  globalThis.document = dom.window.document;
  globalThis.window = dom.window;
  globalThis.fetch = (url, options) => realFetch(new URL(url, base), options);
  const normalFetch = globalThis.fetch;
  const $ = (id) => document.getElementById(id);
  const input = (id, value) => {
    $(id).value = value;
    $(id).dispatchEvent(new window.Event("input", { bubbles: true }));
  };
  const mod = await import(
    pathToFileURL(path.join(root, "frontend/js/views/flood-simulator.js"))
  );
  await waitFor(() => !$("scenario-result").hidden);
  check($("scenario-preset").options.length === 4, "four presets");
  check(
    document.querySelectorAll("#rain-inputs input").length === 12,
    "twelve five-minute intervals",
  );
  check(
    document.querySelectorAll(".horizon").length === 2,
    "two depth and onset cards",
  );
  check(
    document.querySelectorAll("svg").length === 2,
    "depth and rainfall charts",
  );
  check(
    $("scenario-summary").textContent.includes("xác nhận"),
    "onset timing explained",
  );
  check(
    $("scenario-input-details").textContent.includes(
      '"uses_trained_ai": false',
    ),
    "no fabricated AI claim",
  );
  for (const [preset, expectation] of [
    ["dry", "Chưa xác nhận"],
    ["light", "Chưa xác nhận"],
    ["receding", "Đã vượt ngưỡng"],
    ["heavy", "Có xuất hiện"],
  ]) {
    $("scenario-preset").value = preset;
    $("scenario-preset").dispatchEvent(new window.Event("change"));
    await waitFor(() => !$("scenario-result").hidden);
    check(
      $("horizon-cards").textContent.includes(expectation),
      `${preset} expected event status`,
    );
    if (preset === "dry")
      check(
        [...document.querySelectorAll(".depth-value")].every((el) =>
          el.textContent.includes("0,0"),
        ),
        "dry remains exactly zero",
      );
  }
  input("initial_depth_cm", "2");
  check($("scenario-result").hidden, "editing hides stale output");
  await mod.runScenario();
  check(!$("scenario-result").hidden, "edited inputs recompute");
  input("catchment_area_ha", "0.1");
  await mod.runScenario();
  check(
    $("scenario-status").dataset.error === "true" &&
      $("scenario-result").hidden,
    "invalid area relationship rejected without old result",
  );
  input("catchment_area_ha", "2");
  globalThis.fetch = async () => {
    throw new Error("Test connection failed");
  };
  await mod.runScenario();
  check(
    $("scenario-status").dataset.error === "true" &&
      !$("scenario-run").disabled,
    "network failure remains retryable",
  );
  globalThis.fetch = normalFetch;
  await mod.runScenario();
  const fixture = await (
    await normalFetch("/api/flood-simulation/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-VietSafe": "local" },
      body: JSON.stringify(mod.readInputs()),
    })
  ).json();
  const csv = mod.toCSV(fixture);
  check(
    csv.split("\r\n").length === 62 && csv.includes("synthetic,model_version"),
    "CSV has provenance and 61 time points",
  );
  let downloadedBlob;
  let filename;
  window.URL.createObjectURL = (blob) => {
    downloadedBlob = blob;
    return "blob:test";
  };
  window.URL.revokeObjectURL = () => {};
  window.HTMLAnchorElement.prototype.click = function () {
    filename = this.download;
  };
  $("download-json").click();
  check(
    filename.endsWith(".json") &&
      JSON.parse(await downloadedBlob.text()).synthetic,
    "download JSON carries synthetic flag",
  );
  $("download-csv").click();
  check(
    filename.endsWith(".csv") &&
      (await downloadedBlob.text()).startsWith("synthetic,"),
    "download CSV carries synthetic flag",
  );
  let release;
  globalThis.fetch = () =>
    new Promise((resolve) => {
      release = resolve;
    });
  const pending = mod.runScenario();
  await waitFor(() => Boolean(release));
  input("initial_depth_cm", "8");
  release({ ok: true, json: async () => fixture });
  await pending;
  check(
    $("scenario-result").hidden,
    "late response cannot overwrite edited input state",
  );
  globalThis.fetch = normalFetch;
  await mod.runScenario();
  check(
    $("scenario-summary").textContent.includes("Ban đầu"),
    "recovers after cancelled request with current inputs",
  );
  console.log(`PASS ${checks} frontend checks`);
} finally {
  globalThis.fetch = realFetch;
  server.kill();
  await new Promise((resolve) => {
    if (server.exitCode !== null) resolve();
    else {
      server.once("exit", resolve);
      setTimeout(resolve, 4000);
    }
  });
  rmSync(temp, { recursive: true, force: true });
}
