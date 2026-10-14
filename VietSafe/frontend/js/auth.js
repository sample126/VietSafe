/** Đăng nhập / đăng ký / đăng xuất và cập nhật giao diện theo vai trò (khách, người dân, admin). */
import { api, post } from "./api.js";
import { ADMIN_VIEWS, TOKEN_STORAGE_KEY } from "./config.js";
import { setView } from "./navigation.js";
import { authState, state } from "./state.js";
import { $, $$, toast } from "./utils.js";

// === Auth functions ===
export async function checkAuth() {
  if (!authState.token) {
    authState.user = null;
    updateAuthUI();
    return;
  }
  try {
    const data = await api("/api/auth/me");
    authState.user = data.user;
  } catch {
    authState.user = null;
    authState.token = null;
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
  updateAuthUI();
}

export function updateAuthUI() {
  const user = authState.user;
  const btn = $("#auth-button"),
    label = $("#auth-label");
  if (user) {
    btn.classList.add("logged-in");
    label.textContent = user.display_name;
    btn.title = "Tài khoản: " + user.username;
  } else {
    btn.classList.remove("logged-in");
    label.textContent = "Đăng nhập";
    btn.title = "Đăng nhập";
  }
  // Show/hide admin-only nav items
  $$(".admin-only").forEach((el) => {
    el.hidden = !(user && user.role === "admin");
  });
  // If currently on an admin-only view and not admin, switch to map
  if (ADMIN_VIEWS.includes(state.view) && (!user || user.role !== "admin")) setView("map");
  // Close user menu
  $("#user-menu").hidden = true;
  // Update user menu info
  if (user) {
    $("#user-display-name").textContent = user.display_name;
    $("#user-role-label").textContent = user.role === "admin" ? "Quản trị viên" : "Người dân";
  }
}

export async function doLogin(e) {
  e.preventDefault();
  $("#login-error").hidden = true;
  const btn = $("#submit-login");
  btn.disabled = true;
  try {
    const result = await post("/api/auth/login", {
      username: $("#login-username").value,
      password: $("#login-password").value,
    });
    authState.user = result.user;
    authState.token = result.token;
    localStorage.setItem(TOKEN_STORAGE_KEY, result.token);
    updateAuthUI();
    $("#login-dialog").close();
    $("#login-form").reset();
    toast("Xin chào, " + result.user.display_name + "!");
  } catch (err) {
    $("#login-error").textContent = err.message;
    $("#login-error").hidden = false;
  } finally {
    btn.disabled = false;
  }
}

export async function doRegister(e) {
  e.preventDefault();
  $("#register-error").hidden = true;
  const btn = $("#submit-register");
  btn.disabled = true;
  try {
    const result = await post("/api/auth/register", {
      username: $("#reg-username").value,
      password: $("#reg-password").value,
      display_name: $("#reg-display").value,
    });
    authState.user = result.user;
    authState.token = result.token;
    localStorage.setItem(TOKEN_STORAGE_KEY, result.token);
    updateAuthUI();
    $("#register-dialog").close();
    $("#register-form").reset();
    toast("Đăng ký thành công! Xin chào, " + result.user.display_name + "!");
  } catch (err) {
    $("#register-error").textContent = err.message;
    $("#register-error").hidden = false;
  } finally {
    btn.disabled = false;
  }
}

export async function doLogout() {
  try {
    await post("/api/auth/logout", {});
  } catch {
    // Máy chủ không phản hồi: vẫn đăng xuất cục bộ.
  }
  authState.user = null;
  authState.token = null;
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  updateAuthUI();
  $("#user-menu").hidden = true;
  toast("Đã đăng xuất.");
}

export function initAuth() {
  // Auth event listeners
  $("#auth-button").addEventListener("click", () => {
    if (authState.user) {
      $("#user-menu").hidden = !$("#user-menu").hidden;
    } else {
      $("#login-dialog").showModal();
    }
  });
  $("#logout-button").addEventListener("click", doLogout);
  $("#login-form").addEventListener("submit", doLogin);
  $("#register-form").addEventListener("submit", doRegister);
  $("#show-register").addEventListener("click", () => {
    $("#login-dialog").close();
    $("#register-dialog").showModal();
  });
  $("#show-login").addEventListener("click", () => {
    $("#register-dialog").close();
    $("#login-dialog").showModal();
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#user-menu") && !e.target.closest("#auth-button"))
      $("#user-menu").hidden = true;
  });
}
