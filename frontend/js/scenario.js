/** Đổi kịch bản thời tiết mô phỏng (chỉ admin; backend kiểm tra quyền). */
import { post } from "./api.js";
import { refresh } from "./dashboard.js";
import { state } from "./state.js";
import { $, toast } from "./utils.js";
import { clearRoutes } from "./views/routing.js";

export async function changeScenario(value) {
  try {
    await post("/api/scenario", { scenario: value });
    await refresh();
    clearRoutes();
    toast("Đã đổi kịch bản. Bản đồ và dự báo đã cập nhật.");
  } catch (e) {
    toast(e.message);
    if (state.data) {
      $("#source-scenario").value = state.data.scenario;
      $("#forecast-scenario").value = state.data.scenario;
    }
  }
}
