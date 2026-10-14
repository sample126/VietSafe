/**
 * Trạng thái dùng chung của ứng dụng (một object duy nhất, sửa trực tiếp thuộc tính).
 * Mô hình không tự "reactive": sau khi đổi state hãy gọi hàm render tương ứng.
 */
import { DEFAULT_SELECTED_ROAD, TOKEN_STORAGE_KEY } from "./config.js";

export const state = {
  data: null,
  view: "map",
  filter: "all",
  horizon: 0,
  selected: DEFAULT_SELECTED_ROAD,
  layers: { flood: true, traffic: true, incident: true, pending: true },
  reportPosition: null,
  picking: false,
  reports: [],
  routes: null,
  routeIndex: 0,
  connected: false,
  lastGood: 0,
};

/** Người dùng đăng nhập hiện tại (user = null nếu là khách). */
export const authState = { user: null, token: localStorage.getItem(TOKEN_STORAGE_KEY) };
