/**
 * Hằng số cấu hình dùng chung của frontend.
 * Muốn đổi nhãn, khoảng thời gian cập nhật, nhà cung cấp bản đồ... hãy sửa ở đây.
 */

/** Chu kỳ tự cập nhật dữ liệu từ /api/snapshot (ms). */
export const REFRESH_INTERVAL_MS = 10000;

/** Khóa localStorage lưu token đăng nhập. */
export const TOKEN_STORAGE_KEY = "vietsafe_token";

/** Các trang chỉ admin được xem (khớp class `admin-only` của nút menu trong index.html). */
export const ADMIN_VIEWS = ["sources", "reports"];

/** Đoạn đường được chọn mặc định khi mở ứng dụng. */
export const DEFAULT_SELECTED_ROAD = "HN-019";

/**
 * Vùng thử nghiệm diện rộng Hà Nội: [lat thấp, lat cao], [lng thấp, lng cao].
 * Phải khớp backend: backend/vietsafe/config.py (PILOT_LAT_RANGE / PILOT_LNG_RANGE).
 */
export const PILOT_BOUNDS = { lat: [20.68, 21.31], lng: [105.33, 106.0] };

export const typeNames = { flood: "Ngập đường", traffic: "Ùn tắc", incident: "Sự cố giao thông" };
export const typeIcons = { flood: "water", traffic: "car", incident: "alert" };
export const typeColors = { flood: "blue", traffic: "orange", incident: "red" };

/** Loại chính (dùng cho icon/màu/lớp bản đồ) khi phản ánh có nhiều loại. */
export const primaryType = (type) => String(type || "").split(",")[0];

/** Nhãn hiển thị "Ngập đường · Ùn tắc" cho trường type nhiều giá trị. */
export const typeLabel = (type) =>
  String(type || "")
    .split(",")
    .filter((t) => typeNames[t])
    .map((t) => typeNames[t])
    .join(" · ") || "Không rõ loại";
export const statuses = {
  pending: "Chờ xác minh",
  verified: "Đã xác minh",
  resolved: "Đã xử lý",
  rejected: "Đã từ chối",
  expired: "Hết hạn",
};

export const FOOTNOTE_ONLINE = "Tuyến đường OSM · Dữ liệu cảnh báo mô phỏng · Không dùng để dẫn đường";
export const FOOTNOTE_OFFLINE =
  "Nền ngoại tuyến · Tuyến đường OSM · Cảnh báo mô phỏng";

// === Tile providers ===
// Nền chính: OpenFreeMap Positron (vector OpenMapTiles, không cần khóa).
// Khi WebGL/tile lỗi: MapTiler nếu có khóa, Stadia, OSM, rồi sơ đồ ngoại tuyến.
export const STADIA_API_KEY = "";
export const TILE_PROVIDERS = {
  openfreemap: {
    style: "https://tiles.openfreemap.org/styles/positron",
    attr: '&copy; <a href="https://openfreemap.org/" target="_blank" rel="noopener">OpenFreeMap</a> &copy; <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
  },
  openmaptiles: {
    url: "https://api.maptiler.com/maps/openstreetmap/{z}/{x}/{y}.png?key={key}",
    attr: '&copy; <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>',
    maxZoom: 19,
  },
  stadia: {
    url:
      "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png" +
      (STADIA_API_KEY ? `?api_key=${encodeURIComponent(STADIA_API_KEY)}` : ""),
    attr: '&copy; <a href="https://www.stadiamaps.com/" target="_blank" rel="noopener">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
    maxZoom: 20,
  },
  osm: {
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
    maxZoom: 19,
  },
};
export const TILE_ORDER = ["openfreemap", "openmaptiles", "stadia", "osm"];
// Khóa vùng nhìn trong Hà Nội: tránh kéo bản đồ ra vùng biển đảo mà tile toàn cầu ghi nhãn không theo quy ước Việt Nam.
export const HANOI_BOUNDS = [
  [20.58, 105.27],
  [21.36, 106.08],
];
