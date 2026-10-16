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
export const FOOTNOTE_SATELLITE =
  "Ảnh vệ tinh Esri · Mạng đường giản lược · Không dùng để dẫn đường thực tế";
export const FOOTNOTE_OFFLINE =
  "Sơ đồ ngoại tuyến · Mạng đường giản lược · Không dùng để dẫn đường";

// === Tile providers ===
// Nhà cung cấp tile (miễn phí, không cần key). Lưu ý: `tile.openstreetmap.org` BỊ CHẶN DNS
// ở một số môi trường/mạng, nên nền mặc định dùng Esri (chạy ổn định và chi tiết "thật").
// - esriStreet : Esri World Street Map - bản đồ đường phố chi tiết, nhiều màu, dễ đọc (mặc định).
// - esri       : Esri World Imagery - ảnh vệ tinh thực tế (chế độ Vệ tinh).
// - stadia     : Stadia "Alidade Smooth" - nền xám, giữ làm lớp dự phòng khi Esri lỗi.
// - osm        : OpenStreetMap chuẩn - giữ lại cho máy cá nhân (có thể bị chặn ở một số mạng).
// Nếu một nhà cung cấp lỗi, app tự rơi xuống nhà cung cấp kế tiếp rồi tới sơ đồ ngoại tuyến.
export const STADIA_API_KEY = "";
export const TILE_PROVIDERS = {
  esriStreet: {
    // Esri dùng thứ tự tham số {z}/{y}/{x} (khác OSM) theo chuẩn tile ArcGIS.
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    attr: 'Bản đồ &copy; <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a>, HERE, Garmin, OpenStreetMap cộng đồng',
    maxZoom: 19,
  },
  esri: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr: 'Ảnh &copy; <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a>, Maxar, Earthstar Geographics và cộng đồng nguồn',
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
    attr: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
};
// Chuỗi dự phòng cho lớp "Đường phố" khi tile lỗi (esriStreet -> stadia -> ngoại tuyến).
export const TILE_ORDER = ["esriStreet", "stadia"];

// Các kiểu nền bản đồ người dùng chọn được (radio trong menu Lớp).
// `provider`: khóa trong TILE_PROVIDERS; null = sơ đồ ngoại tuyến vẽ tay, không tải tile.
export const BASE_STYLES = [
  { id: "street", label: "Đường phố", provider: "esriStreet" },
  { id: "satellite", label: "Vệ tinh", provider: "esri" },
  { id: "offline", label: "Ngoại tuyến", provider: null },
];
// Khóa vùng nhìn trong Hà Nội: tránh kéo bản đồ ra vùng biển đảo mà tile toàn cầu ghi nhãn không theo quy ước Việt Nam.
export const HANOI_BOUNDS = [
  [20.9, 105.65],
  [21.15, 106.02],
];
