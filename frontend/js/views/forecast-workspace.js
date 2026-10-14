/** Native forecast panels inside the team's existing view/navigation system. */
const modes = {
  simulation: {
    page: "/flood-simulator.html",
    rootClass: "flood-simulator-page",
    load: () => import("./flood-simulator.js"),
    start: (module) => module.initSimulator(),
  },
  ai: {
    page: "/forecast-lab.html",
    rootClass: "ai-forecast-page",
    load: () => import("./ai-forecast.js"),
    start: (module) => module.initAI(),
  },
};
const loading = new Map();
let activeMode = "simulation";

async function mount(mode) {
  if (!modes[mode]) return;
  if (loading.has(mode)) return loading.get(mode);
  const host = document.getElementById(`forecast-${mode}-panel`);
  const config = modes[mode];
  const operation = (async () => {
    host.setAttribute("aria-busy", "true");
    host.innerHTML =
      '<p class="forecast-loading" role="status">Đang tải công cụ dự báo…</p>';
    try {
      const response = await fetch(config.page);
      if (!response.ok)
        throw new Error("Không tải được giao diện dự báo. Vui lòng thử lại.");
      // Reuse the owned HTML's main content; scripts, header and page shell stay outside.
      const source = new window.DOMParser().parseFromString(
        await response.text(),
        "text/html",
      );
      const content = source.querySelector("main");
      if (!content)
        throw new Error("Giao diện dự báo chưa sẵn sàng. Vui lòng thử lại.");
      const wrapper = document.createElement("div");
      wrapper.className = `${config.rootClass} forecast-embedded`;
      const body = document.createElement("div");
      body.className = "forecast-module-content";
      body.append(
        ...Array.from(content.childNodes, (node) =>
          document.importNode(node, true),
        ),
      );
      body
        .querySelectorAll("script, style, link")
        .forEach((node) => node.remove());
      for (const heading of body.querySelectorAll("h1")) {
        const title = document.createElement("h2");
        title.className = "module-title";
        title.textContent = heading.textContent;
        heading.replaceWith(title);
      }
      // Cross-links switch panels without leaving the app or losing the map/session.
      for (const link of body.querySelectorAll("a[href]")) {
        const target = Object.entries(modes).find(
          ([, item]) => item.page === link.getAttribute("href"),
        );
        if (!target) continue;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "forecast-inline-link";
        button.dataset.forecastMode = target[0];
        button.textContent = link.textContent;
        link.replaceWith(button);
      }
      wrapper.append(body);
      host.replaceChildren(wrapper);
      await config.start(await config.load());
    } catch (error) {
      loading.delete(mode);
      const message = document.createElement("p");
      message.className = "forecast-loading";
      message.setAttribute("role", "alert");
      message.textContent = error.message;
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "button secondary";
      retry.textContent = "Thử tải lại";
      retry.dataset.forecastMode = mode;
      host.replaceChildren(message, retry);
    } finally {
      host.removeAttribute("aria-busy");
    }
  })();
  loading.set(mode, operation);
  return operation;
}

export async function showForecastWorkspace(mode = activeMode) {
  if (!Object.hasOwn(modes, mode) && mode !== "map") return;
  activeMode = mode;
  for (const panel of document.querySelectorAll("[data-forecast-panel]"))
    panel.hidden = panel.dataset.forecastPanel !== mode;
  for (const button of document.querySelectorAll(
    '[role="tab"][data-forecast-mode]',
  )) {
    const selected = button.dataset.forecastMode === mode;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  await mount(mode);
  // Re-measure charts after a previously hidden panel becomes visible.
  window.dispatchEvent(new window.Event("resize"));
}

export function initForecastWorkspace() {
  const view = document.getElementById("forecast-view");
  view.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-forecast-mode]");
    if (button) void showForecastWorkspace(button.dataset.forecastMode);
  });
  view
    .querySelector('[role="tablist"]')
    .addEventListener("keydown", (event) => {
      const tabs = [...view.querySelectorAll('[role="tab"]')];
      const index = tabs.indexOf(event.target);
      if (index < 0) return;
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft")
        next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      tabs[next].focus();
      void showForecastWorkspace(tabs[next].dataset.forecastMode);
    });
}
