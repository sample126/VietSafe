/** Điều khiển trang xem trước điện thoại: đổi kích thước khung + chuyển màn hình trong iframe. */

const ACCOUNTS = {
  user: { username: "nguoidan", password: "matkhau123" },
  admin: { username: "admin", password: "vietsafe2026" },
};

const TOKEN_KEY = "vietsafe_token";
const frame = () => document.getElementById("preview");

// ---------- Kích thước thiết bị ----------
document.getElementById("size-controls").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-w]");
  if (!btn) return;
  const w = Number(btn.dataset.w);
  const h = Number(btn.dataset.h);
  frame().style.width = w + "px";
  frame().style.height = h + "px";
  document.getElementById("size-label").textContent = w + " × " + h + " px";
  document.querySelectorAll("#size-controls button").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
});

// ---------- Chuyển màn hình ----------
document.getElementById("view-controls").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-view]");
  if (!btn) return;
  const view = btn.dataset.view;
  const role = btn.dataset.role || null;
  btn.disabled = true;
  try {
    await switchView(view, role);
    document.querySelectorAll("#view-controls button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  } catch (err) {
    alert("Không chuyển được màn hình: " + err.message);
  } finally {
    btn.disabled = false;
  }
});

async function switchView(view, role) {
  let f = frame();
  await ensureLoaded(f);
  if (role) {
    const user = await currentUser(f);
    if (!user || user.role !== role) {
      await loginAs(f, role);
      f = frame(); // iframe reload tạo lại window
      await ensureLoaded(f);
    }
  }
  const navBtn = f.contentDocument.querySelector(`[data-view="${view}"]`);
  if (!navBtn) throw new Error("không tìm thấy nút " + view);
  navBtn.click();
}

async function currentUser(f) {
  const token = f.contentWindow.localStorage.getItem(TOKEN_KEY);
  if (!token) return null;
  try {
    const res = await fetch("/api/auth/me", {
      headers: { "X-VietSafe": "local", "X-VietSafe-Session": token },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.user || data;
  } catch {
    return null;
  }
}

async function loginAs(f, role) {
  const acc = ACCOUNTS[role];
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "X-VietSafe": "local", "Content-Type": "application/json" },
    body: JSON.stringify(acc),
  });
  if (!res.ok) throw new Error("đăng nhập thất bại");
  const data = await res.json();
  f.contentWindow.localStorage.setItem(TOKEN_KEY, data.token);
  await reloadFrame();
}

function reloadFrame() {
  const f = frame();
  return new Promise((resolve) => {
    f.addEventListener("load", resolve, { once: true });
    f.src = "/?v=" + Date.now();
  });
}

function ensureLoaded(f) {
  const doc = f.contentDocument;
  if (doc && doc.readyState === "complete") return Promise.resolve();
  return new Promise((resolve) => f.addEventListener("load", resolve, { once: true }));
}
