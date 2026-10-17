import { chromium } from "playwright-core";

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--enable-unsafe-swiftshader"],
});
const mobile = process.argv.includes("--mobile");
const page = await browser.newPage({
  viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
});
page.on("console", (message) => {
  if (message.type() === "error") console.log("console:", message.text());
});
page.on("pageerror", (error) => console.log("pageerror:", error.message));
page.on("requestfailed", (request) =>
  console.log("requestfailed:", request.url(), request.failure()?.errorText),
);
await page.goto(process.argv[2] || "http://127.0.0.1:8765/", {
  waitUntil: "domcontentloaded",
});
await page.waitForTimeout(12000);
if (process.argv.includes("--zoom13")) {
  await page.evaluate(async () => (await import("/js/map.js")).map.setZoom(13));
  await page.waitForTimeout(1000);
}
if (process.argv.includes("--toggle-major")) {
  await page.locator("#toggle-layers").click();
  await page.locator("#major-roads").uncheck();
  await page.locator("#toggle-layers").click();
  await page.waitForTimeout(300);
}
if (process.argv.includes("--route")) {
  await page.locator("#open-route").click();
  await page.locator("#route-form button[type=submit]").click();
  await page.locator("#route-results .route-choice").first().waitFor();
  await page.waitForTimeout(1500);
  if (mobile) await page.locator("#map").scrollIntoViewIfNeeded();
}
const result = await page.evaluate(() => ({
  vectorVendor: !!window.VietSafeVectorMaps,
  webgl2: !!window.WebGL2RenderingContext,
  vector: document.querySelector("#map")?.classList.contains("map-vector"),
  canvas: !!document.querySelector("#map canvas"),
  majorPaths: document.querySelectorAll(".leaflet-majorRoad-pane path").length,
  majorDisabled: document.querySelector("#major-roads")?.disabled,
  majorPane: document.querySelector(".leaflet-majorRoad-pane")
    ?.childElementCount,
  routeKey: !document.querySelector("#route-map-key")?.hidden,
  attribution: document.querySelector(".leaflet-control-attribution")
    ?.textContent,
}));
if (process.argv.includes("--route")) {
  const routeState = await page.evaluate(async () => {
    const mapModule = await import("/js/map.js");
    const stateModule = await import("/js/state.js");
    const m = mapModule.map;
    const route =
      stateModule.state.routes?.routes[stateModule.state.routeIndex];
    return {
      zoom: m.getZoom(),
      bounds: m.getBounds().toBBoxString(),
      start: route?.coordinates[0],
      end: route?.coordinates.at(-1),
    };
  });
  console.log(routeState);
}
console.log(result);
await page.screenshot({
  path: process.argv.includes("--route")
    ? mobile
      ? "data/map-route-mobile.png"
      : "data/map-route.png"
    : mobile
      ? "data/map-check-mobile.png"
      : "data/map-check.png",
});
await browser.close();
if (!result.vector || !result.canvas) process.exitCode = 1;
