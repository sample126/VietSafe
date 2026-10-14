/** Exercise the real single-page forecast panels against the real backend. */
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
const temp = mkdtempSync(path.join(tmpdir(), "vietsafe-inline-smoke-"));
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
      VIETSAFE_AI_RESEARCH_ROOT: process.env.VIETSAFE_AI_VERIFY_ROOT || "",
      PYTHONUTF8: "1",
      OMP_NUM_THREADS: "2",
      OPENBLAS_NUM_THREADS: "2",
    },
  },
);
let errors = "";
server.stderr.on("data", (chunk) => {
  errors += chunk;
});
async function waitFor(fn) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      if (await fn()) return;
    } catch {
      /* wait for startup / pending response */
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Timed out: ${errors.slice(-1500)}`);
}
let checks = 0;
function check(value, label) {
  assert.ok(value, label);
  checks++;
  console.log(`ok ${label}`);
}
try {
  await waitFor(async () => (await fetch(`${base}/api/health`)).ok);
  const dom = new JSDOM(
    readFileSync(path.join(root, "frontend/index.html"), "utf8"),
    { url: base },
  );
  globalThis.document = dom.window.document;
  globalThis.window = dom.window;
  const $ = (id) => document.getElementById(id);
  const shell = document.querySelector(".rail");
  const map = $("map");
  window.localStorage.setItem("session-test", "preserved");
  const realFetch = globalThis.fetch;
  let failTemplate = true,
    releaseAI;
  let simulatorRuns = 0;
  const templateRequests = [];
  globalThis.fetch = async (url, options) => {
    if (url === "/api/flood-simulation/predict") simulatorRuns++;
    if (url.endsWith(".html")) templateRequests.push(url);
    if (url === "/flood-simulator.html" && failTemplate) {
      failTemplate = false;
      return { ok: false };
    }
    if (url === "/forecast-lab.html")
      await new Promise((resolve) => {
        releaseAI = resolve;
      });
    return realFetch(new URL(url, base), options);
  };
  const workspace = await import(
    pathToFileURL(path.join(root, "frontend/js/views/forecast-workspace.js"))
  );
  workspace.initForecastWorkspace();
  check(
    templateRequests.length === 0,
    "no forecasting downloads before opening the tab",
  );
  $("forecast-view").hidden = false;
  await workspace.showForecastWorkspace();
  check(
    !!document.querySelector('#forecast-simulation-panel [role="alert"]'),
    "template failure is explained",
  );
  document.querySelector("#forecast-simulation-panel button").click();
  await waitFor(() => $("scenario-result") && !$("scenario-result").hidden);
  check(
    $("forecast-simulation-panel").contains($("scenario-form")),
    "simulator form is inside main forecast view",
  );
  check(
    $("horizon-cards").children.length === 2,
    "simulation returns both horizons inline",
  );
  check(simulatorRuns === 1, "retry starts exactly one prediction");
  check(
    document.querySelectorAll("iframe").length === 0,
    "native panels without iframe",
  );
  check(
    document.querySelectorAll("main").length === 1,
    "one application shell",
  );

  const aiLoading = workspace.showForecastWorkspace("ai");
  await waitFor(() => !!releaseAI);
  await workspace.showForecastWorkspace("map");
  releaseAI();
  await aiLoading;
  check(
    !$("forecast-map-panel").hidden && $("forecast-ai-panel").hidden,
    "late panel load cannot override user's newer tab",
  );
  check(
    $("forecast-map-tab").getAttribute("aria-selected") === "true",
    "selected tab remains in sync",
  );
  await workspace.showForecastWorkspace("ai");
  check(
    $("forecast-ai-panel").contains($("ai-form")),
    "AI form is inside main forecast view",
  );
  check(
    document.querySelectorAll("#ai-tasks .task").length === 3,
    "research tasks loaded inline",
  );
  if (process.env.VIETSAFE_AI_VERIFY_ROOT) {
    check(!$("ai-run").disabled, "real model ready inside the app");
    $("ai-form").dispatchEvent(
      new window.Event("submit", { cancelable: true }),
    );
    await waitFor(() => !$("ai-result").hidden);
    check(
      $("ai-values").children.length === 3,
      "real AI result rendered inline",
    );
    check(
      $("ai-details").textContent.includes('"hanoi_calibrated": false'),
      "research provenance retained",
    );
  } else {
    check(
      $("ai-run").disabled,
      "unconfigured AI disabled without breaking the app",
    );
    check(
      $("ai-status").textContent.includes("VIETSAFE_AI_RESEARCH_ROOT"),
      "missing model explained inline",
    );
    check($("ai-result").hidden, "no fabricated AI result");
  }
  await workspace.showForecastWorkspace("simulation");
  $("initial_depth_cm").value = "12";
  $("initial_depth_cm").dispatchEvent(
    new window.Event("input", { bubbles: true }),
  );
  await workspace.showForecastWorkspace("ai");
  await workspace.showForecastWorkspace("simulation");
  check(
    $("initial_depth_cm").value === "12",
    "inputs preserved when switching tabs",
  );
  check($("scenario-result").hidden, "editing input still hides stale results");
  check(
    $("scenario-preset").options.length === 4 &&
      $("rain-inputs").children.length === 12,
    "repeated navigation does not duplicate controls",
  );
  $("scenario-form").dispatchEvent(
    new window.Event("submit", { cancelable: true }),
  );
  await waitFor(() => !$("scenario-result").hidden);
  check(
    simulatorRuns === 2,
    "repeated navigation does not duplicate submit handlers",
  );
  document
    .querySelector('#forecast-simulation-panel [data-forecast-mode="ai"]')
    .click();
  check(
    !$("forecast-ai-panel").hidden,
    "cross-link switches panels in the same page",
  );
  $("forecast-ai-tab").dispatchEvent(
    new window.KeyboardEvent("keydown", {
      key: "ArrowRight",
      bubbles: true,
      cancelable: true,
    }),
  );
  check(
    document.activeElement === $("forecast-map-tab") &&
      !$("forecast-map-panel").hidden,
    "keyboard tab navigation works",
  );
  check(
    document.querySelector(".rail") === shell && $("map") === map,
    "navigation and map DOM stay intact",
  );
  check(
    window.localStorage.getItem("session-test") === "preserved",
    "session state preserved",
  );
  check(window.location.href === base + "/", "no document navigation");
  const ids = [...document.querySelectorAll("[id]")].map((node) => node.id);
  check(
    new Set(ids).size === ids.length,
    "integrated panels introduce no duplicate IDs",
  );
  check(
    templateRequests.filter((url) => url === "/forecast-lab.html").length === 1,
    "AI content reused after first load",
  );
  console.log(`PASS ${checks} integrated forecast checks`);
} finally {
  server.kill();
  await new Promise((resolve) =>
    server.exitCode !== null ? resolve() : server.once("exit", resolve),
  );
  assert.equal(path.dirname(path.resolve(temp)), path.resolve(tmpdir()));
  assert.ok(path.basename(temp).startsWith("vietsafe-inline-smoke-"));
  rmSync(temp, { recursive: true, force: true });
}
