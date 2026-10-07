/**
 * Dịch vụ cứu hộ theo loại xe và các loại sự cố cho form điều phối.
 * LƯU Ý: số hotline là thông tin liên quan an toàn - hãy xác minh trước khi triển khai công khai.
 */
// === Rescue view handlers ===
export const rescueServices = {
  motorbike: {
    name: "Cứu Hộ Xe Máy 247",
    hotline: "0944.883.288",
    tel: "tel:0944883288",
    url: "https://cuuhoxemay247.com/",
  },
  car: {
    name: "Cứu Hộ Ô Tô 24h",
    hotline: "0967.119.119",
    tel: "tel:0967119119",
    url: "https://cuuho24h.vn/",
  },
  truck: {
    name: "Trung Tâm Cứu Hộ Giao Thông 116",
    hotline: "0896.116.116",
    tel: "tel:0896116116",
    url: "https://trungtamcuuho116.vn/dich-vu-cuu-ho-giao-thong-116/",
  },
};

export const rescueProblemTypes = {
  flood_dead: "Chết máy do ngập nước",
  hydro: "Nghi ngờ thủy kích trong nước sâu",
  battery: "Hỏng bình ắc quy / Không đề nổ",
  tire: "Hỏng / Nổ lốp giữa đường",
  accident: "Va chạm / Tai nạn giao thông",
};
