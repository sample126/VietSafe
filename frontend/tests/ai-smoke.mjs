/** Real backend + real ES module. Optional real artifacts; no training. */
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
const temp = mkdtempSync(path.join(tmpdir(), "vietsafe-ai-smoke-"));
const port = await new Promise((resolve) => {
  const s = net.createServer().listen(0, "127.0.0.1", () => {
    const assigned = s.address().port;
    s.close(() => resolve(assigned));
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
      OMP_NUM_THREADS: "2",
      PYTHONUTF8: "1",
      OPENBLAS_NUM_THREADS: "2",
    },
  },
);
let stderr = "";
server.stderr.on("data", (data) => {
  stderr += data;
});
async function waitFor(fn, label) {
  const stop = Date.now() + 60000;
  while (Date.now() < stop) {
    try {
      if (await fn()) return;
    } catch {
      /* server may still be loading */
    }
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
  throw new Error(`Timeout: ${label}\n${stderr.slice(-2000)}`);
}
let count = 0;
function check(condition, label) {
  assert.ok(condition, label);
  count++;
  console.log(`ok ${label}`);
}
try {
  await waitFor(async () => (await fetch(`${base}/api/health`)).ok, "backend");
  const dom = new JSDOM(
    readFileSync(path.join(root, "frontend/forecast-lab.html"), "utf8"),
    { url: base },
  );
  globalThis.document = dom.window.document;
  globalThis.window = dom.window;
  globalThis.Option = dom.window.Option;
  const realFetch = globalThis.fetch;
  globalThis.fetch = (url, options) => realFetch(new URL(url, base), options);
  const $ = (id) => document.getElementById(id);
  const change = (element) =>
    element.dispatchEvent(new window.Event("change", { bubbles: true }));
  const module = await import(
    pathToFileURL(path.join(root, "frontend/js/views/ai-forecast.js"))
  );
  await waitFor(
    () => document.querySelectorAll(".task").length === 3,
    "catalog",
  );
  check(
    module.formatValue(null, "m") === "Thiếu dữ liệu",
    "missing is not zero",
  );
  check(
    !module.formatValue(23, "source_speed_scale").includes("km/h"),
    "no invented speed unit",
  );
  check(
    module.formatValue(0.4, "probability") === "40.0 %",
    "probability displayed as percent",
  );
  if (!process.env.VIETSAFE_AI_VERIFY_ROOT) {
    await waitFor(
      () => $("ai-status").textContent.includes("VIETSAFE_AI_RESEARCH_ROOT"),
      "unconfigured message",
    );
    check($("ai-run").disabled, "run disabled without artifacts");
    check($("ai-result").hidden, "no synthetic result");
  } else {
    for (const task of ["bellinge", "floodnet", "sztaxi"]) {
      document.querySelector(`[data-task="${task}"]`).click();
      await waitFor(() => !$("ai-run").disabled, `${task} options`);
      check($("ai-site").options.length > 0, `${task} known sites`);
      $("ai-form").dispatchEvent(
        new window.Event("submit", { cancelable: true }),
      );
      await waitFor(() => !$("ai-result").hidden, `${task} result`);
      check(
        $("ai-values").children.length === (task === "sztaxi" ? 4 : 3),
        `${task} horizon cards`,
      );
      check(
        $("ai-details").textContent.includes('"public_alert_allowed": false'),
        `${task} research flags`,
      );
      check(
        !$("ai-values").textContent.includes("NaN"),
        `${task} finite values`,
      );
      if (task === "floodnet")
        check(
          $("ai-values").textContent.includes("62.7 %"),
          "frozen FloodNet example",
        );
      if (task === "sztaxi")
        check(
          !$("ai-values").textContent.includes("km/h"),
          "source speed unit in UI",
        );
      $("ai-origin").selectedIndex = 1;
      change($("ai-origin"));
      check(
        $("ai-result").hidden && !$("ai-run").disabled,
        `${task} stale result cleared on time change`,
      );
    }
    // A slow response must not overwrite a newer selection even if transport ignores abort.
    let release;
    globalThis.fetch = (_url, _options) =>
      new Promise((resolve) => {
        release = resolve;
      });
    $("ai-form").dispatchEvent(
      new window.Event("submit", { cancelable: true }),
    );
    $("ai-origin").selectedIndex = 2;
    change($("ai-origin"));
    release({ ok: true, json: async () => ({ bad: "stale" }) });
    await new Promise((resolve) => setTimeout(resolve, 50));
    check(
      $("ai-result").hidden,
      "late response discarded after selection change",
    );
  }
  console.log(`PASS ${count} AI frontend checks`);
} finally {
  server.kill();
  await new Promise((resolve) =>
    server.exitCode !== null ? resolve() : server.once("exit", resolve),
  );
  assert.equal(path.dirname(path.resolve(temp)), path.resolve(tmpdir()));
  assert.ok(path.basename(temp).startsWith("vietsafe-ai-smoke-"));
  rmSync(temp, { recursive: true, force: true });
}
