/** Hành vi chung của <dialog>: nút đóng (.close-dialog), bấm ra ngoài để đóng, hộp "Giới thiệu". */
import { $, $$ } from "./utils.js";

export function initDialogs() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest("button");
    if (button && button.classList.contains("close-dialog")) button.closest("dialog").close();
  });
  $("#about-button").addEventListener("click", () => $("#about-dialog").showModal());
  $$("dialog").forEach((dialog) =>
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) {
        const rect = dialog.getBoundingClientRect();
        if (
          e.clientX < rect.left ||
          e.clientX > rect.right ||
          e.clientY < rect.top ||
          e.clientY > rect.bottom
        )
          dialog.close();
      }
    }),
  );
}
