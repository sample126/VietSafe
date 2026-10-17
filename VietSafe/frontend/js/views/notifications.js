/** Hệ thống thông báo: polling, bell icon, danh sách thông báo. */
import { api, post } from "../api.js";
import { authState, state } from "../state.js";
import { $, $$, esc, toast } from "../utils.js";

const POLL_INTERVAL = 30000; // 30 giây

let pollTimer = null;

export async function loadNotifications() {
  if (!authState.user) return;
  try {
    const data = await api("/api/notifications");
    state.notifications = data.notifications || [];
    const countData = await api("/api/notifications/unread-count");
    state.unreadCount = countData.count || 0;
    updateNotificationBell();
  } catch { /* ignore */ }
}

function updateNotificationBell() {
  const bell = $("#notification-bell");
  if (!bell) return;
  const badge = $("#notification-badge");
  if (state.unreadCount > 0) {
    badge.textContent = state.unreadCount > 99 ? "99+" : state.unreadCount;
    badge.hidden = false;
    bell.classList.add("has-unread");
  } else {
    badge.hidden = true;
    bell.classList.remove("has-unread");
  }
}

export function renderNotificationPanel() {
  const panel = $("#notification-panel");
  if (!panel) return;
  if (!state.notifications.length) {
    panel.innerHTML = `<div class="empty-state">Chưa có thông báo nào.</div>`;
    return;
  }
  panel.innerHTML = state.notifications.map((n) => `
    <div class="notification-item ${n.read ? "" : "unread"}" data-notification-id="${n.id}">
      <p>${esc(n.message)}</p>
      <time>${new Date(n.created_at * 1000).toLocaleString("vi-VN")}</time>
    </div>
  `).join("");
}

export async function markAllRead() {
  if (!authState.user) return;
  try {
    await post("/api/notifications/read", {});
    state.unreadCount = 0;
    state.notifications.forEach((n) => (n.read = 1));
    updateNotificationBell();
    renderNotificationPanel();
  } catch (e) {
    toast(e.message);
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(loadNotifications, POLL_INTERVAL);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

export function initNotifications() {
  // Bell click toggle panel
  $("#notification-bell")?.addEventListener("click", () => {
    const panel = $("#notification-panel");
    if (!panel) return;
    const isOpen = !panel.hidden;
    panel.hidden = isOpen;
    if (!isOpen) renderNotificationPanel();
  });

  // Mark all read button
  $("#mark-all-read")?.addEventListener("click", markAllRead);

  // Close panel when clicking outside
  document.addEventListener("click", (e) => {
    const panel = $("#notification-panel");
    const bell = $("#notification-bell");
    if (panel && bell && !panel.hidden && !e.target.closest("#notification-panel") && !e.target.closest("#notification-bell")) {
      panel.hidden = true;
    }
  });

  // Start polling if logged in
  if (authState.user) {
    loadNotifications();
    startPolling();
  }
}

// Export for auth.js to call on login/logout
export function onAuthChange() {
  if (authState.user) {
    loadNotifications();
    startPolling();
  } else {
    stopPolling();
    state.notifications = [];
    state.unreadCount = 0;
    updateNotificationBell();
  }
}
