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
 * Vùng thử nghiệm nội thành Hà Nội: [lat thấp, lat cao], [lng thấp, lng cao].
 * Phải khớp backend: backend/vietsafe/config.py (PILOT_LAT_RANGE / PILOT_LNG_RANGE).
 */
export const PILOT_BOUNDS = { lat: [20.98, 21.065], lng: [105.77, 105.88] };

export const typeNames = { flood: "Ngập đường", traffic: "Ùn tắc", incident: "Sự cố giao thông" };
export const typeIcons = { flood: "water", traffic: "car", incident: "alert" };
export const typeColors = { flood: "blue", traffic: "orange", incident: "red" };
export const statuses = {
  pending: "Chờ xác minh",
  verified: "Đã xác minh",
  resolved: "Đã xử lý",
  rejected: "Đã từ chối",
  expired: "Hết hạn",
};

export const FOOTNOTE_ONLINE = "Mạng đường giản lược · Không dùng để dẫn đường thực tế";
export const FOOTNOTE_OFFLINE =
  "Sơ đồ ngoại tuyến · Mạng đường giản lược · Không dùng để dẫn đường";

// === Tile providers ===
// Nền chính: Stadia Maps "Alidade Smooth" (dữ liệu OSM, nền xám nhạt để lớp đoạn đường nổi rõ).
// Gói free 200.000 tile/tháng, phi thương mại. Chạy trên localhost/127.0.0.1 không cần key.
// Deploy lên domain thật: đăng ký domain tại https://client.stadiamaps.com hoặc điền API key vào STADIA_API_KEY.
// Nếu Stadia lỗi, tự chuyển sang tile OSM, rồi mới rơi xuống sơ đồ ngoại tuyến.
export const STADIA_API_KEY = "";
export const TILE_PROVIDERS = {
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
export const TILE_ORDER = ["stadia", "osm"];
// Khóa vùng nhìn trong Hà Nội: tránh kéo bản đồ ra vùng biển đảo mà tile toàn cầu ghi nhãn không theo quy ước Việt Nam.
export const HANOI_BOUNDS = [
  [20.9, 105.65],
  [21.15, 106.02],
];
