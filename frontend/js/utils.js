/** Tiện ích DOM / định dạng nhỏ dùng ở mọi nơi. */
import { PILOT_BOUNDS } from "./config.js";

/** Shorthand cho querySelector / querySelectorAll (trả về mảng). */
export const $ = (s, parent = document) => parent.querySelector(s);
export const $$ = (s, parent = document) => [...parent.querySelectorAll(s)];

/** Escape HTML. BẮT BUỘC dùng với mọi dữ liệu động chèn vào innerHTML (chống XSS). */
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

/** Trả về thẻ <svg> dùng symbol `#i-<name>` khai báo trong index.html. */
export const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;

/** Giờ dạng HH:MM:SS theo vi-VN. */
export const timeText = (unix) =>
  new Date(unix * 1000).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

/** "Vừa cập nhật" / "N phút trước". */
export const ago = (unix) => {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - unix));
  return s < 60 ? "Vừa cập nhật" : `${Math.floor(s / 60)} phút trước`;
};

let toastTimer;

/** Hiện thông báo nhỏ ở góc màn hình trong ~5 giây. */
export function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 5200);
}

/** Tọa độ có nằm trong vùng thử nghiệm nội thành Hà Nội không (khớp kiểm tra của backend). */
export const inPilotArea = (lat, lng) =>
  lat >= PILOT_BOUNDS.lat[0] &&
  lat <= PILOT_BOUNDS.lat[1] &&
  lng >= PILOT_BOUNDS.lng[0] &&
  lng <= PILOT_BOUNDS.lng[1];
