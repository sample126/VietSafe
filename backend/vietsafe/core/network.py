"""Hand-authored Hanoi demo graph with cached OSM road geometry."""

import json
import math
from pathlib import Path

NODE_ROWS = [
    ("caugiay", "Cầu Giấy", 21.0313, 105.8006),
    ("buoi", "Bưởi – Đào Tấn", 21.0408, 105.8067),
    ("lotte", "Liễu Giai – Đào Tấn", 21.0355, 105.8128),
    ("kimma", "Kim Mã – Núi Trúc", 21.0318, 105.8247),
    ("giangvo", "Giảng Võ – Cát Linh", 21.0282, 105.8268),
    ("vanmieu", "Văn Miếu", 21.0274, 105.8355),
    ("cuanam", "Cửa Nam", 21.0263, 105.8417),
    ("hoankiem", "Hồ Hoàn Kiếm", 21.0285, 105.8521),
    ("bachdang", "Trần Quang Khải", 21.0272, 105.8600),
    ("hoanghoa", "Hoàng Hoa Thám", 21.0435, 105.8220),
    ("ngocha", "Ngọc Hà – Đội Cấn", 21.0366, 105.8310),
    ("badinh", "Ba Đình", 21.0374, 105.8382),
    ("hangdau", "Hàng Đậu", 21.0400, 105.8489),
    ("lang", "Đường Láng – Nguyễn Chí Thanh", 21.0182, 105.8053),
    ("langha", "Láng Hạ – Huỳnh Thúc Kháng", 21.0163, 105.8132),
    ("thaiha", "Thái Hà – Hoàng Cầu", 21.0126, 105.8211),
    ("odancho", "Ô Chợ Dừa", 21.0181, 105.8290),
    ("khamthien", "Khâm Thiên", 21.0184, 105.8393),
    ("tranhungdao", "Trần Hưng Đạo – Quang Trung", 21.0200, 105.8475),
    ("nhahat", "Nhà hát Lớn", 21.0242, 105.8571),
    ("ngatuso", "Ngã Tư Sở", 21.0030, 105.8200),
    ("tonthatung", "Tôn Thất Tùng – Chùa Bộc", 21.0064, 105.8292),
    ("xadan", "Xã Đàn – Phạm Ngọc Thạch", 21.0095, 105.8352),
    ("daicoviet", "Đại Cồ Việt – Giải Phóng", 21.0078, 105.8422),
    ("baymau", "Công viên Thống Nhất", 21.0102, 105.8482),
    ("thuykhue", "Thụy Khuê", 21.0464, 105.8219),
    ("caobaquat", "Cao Bá Quát", 21.0329, 105.8350),
    ("nguyenkhuyen", "Nguyễn Khuyến", 21.0300, 105.8353),
    ("phanboichau", "Phan Bội Châu – Lý Thường Kiệt", 21.0242, 105.8423),
    ("duongthanh", "Đường Thành – Bát Đàn", 21.0333, 105.8457),
    ("phamvandong", "Phạm Văn Đồng", 21.0650, 105.7850),
    ("conhue", "Cổ Nhuế", 21.0770, 105.7830),
    ("xuanla", "Xuân La", 21.0610, 105.8020),
    ("vochicong", "Võ Chí Công", 21.0740, 105.8070),
    ("nhattan", "Cầu Nhật Tân", 21.0930, 105.8270),
    ("donganh", "Đông Anh", 21.1380, 105.8430),
    ("melinh", "Mê Linh", 21.1640, 105.7330),
    ("noibai", "Nội Bài", 21.2160, 105.8050),
    ("socson", "Sóc Sơn", 21.2610, 105.8510),
    ("nhon", "Nhổn", 21.0520, 105.7480),
    ("mydinh", "Mỹ Đình", 21.0290, 105.7740),
    ("metri", "Mễ Trì", 21.0130, 105.7760),
    ("levanluong", "Lê Văn Lương", 21.0100, 105.8010),
    ("khuatduytien", "Khuất Duy Tiến", 21.0070, 105.7950),
    ("nguyentuan", "Nguyễn Tuân", 21.0020, 105.8080),
    ("quannhan", "Quan Nhân", 21.0090, 105.8110),
    ("nguyentrai", "Nguyễn Trãi", 20.9940, 105.8110),
    ("trungvan", "Trung Văn", 20.9950, 105.7850),
    ("hadong", "Hà Đông", 20.9710, 105.7780),
    ("yenghia", "Yên Nghĩa", 20.9460, 105.7460),
    ("taymo", "Tây Mỗ", 21.0050, 105.7460),
    ("ankhanh", "An Khánh", 21.0050, 105.7070),
    ("hoaibac", "Hoài Đức", 21.0400, 105.6970),
    ("quocoai", "Quốc Oai", 20.9880, 105.6450),
    ("hoalac", "Hòa Lạc", 21.0070, 105.5340),
    ("sontay", "Sơn Tây", 21.1390, 105.5040),
    ("bavi", "Ba Vì", 21.1770, 105.3740),
    ("chuongmy", "Chương Mỹ", 20.9490, 105.6180),
    ("myduc", "Mỹ Đức", 20.7270, 105.7440),
    ("truongchinh", "Trường Chinh", 21.0010, 105.8300),
    ("vong", "Ngã Tư Vọng", 20.9980, 105.8430),
    ("nguyenxien", "Nguyễn Xiển", 20.9830, 105.8100),
    ("linhdam", "Linh Đàm", 20.9720, 105.8270),
    ("dinhcong", "Định Công", 20.9900, 105.8380),
    ("giapbat", "Giáp Bát", 20.9830, 105.8470),
    ("minhkhai", "Minh Khai", 20.9980, 105.8640),
    ("linhnam", "Lĩnh Nam", 20.9790, 105.8820),
    ("phapvan", "Pháp Vân", 20.9610, 105.8500),
    ("thanhtri", "Thanh Trì", 20.9400, 105.8570),
    ("thuongtin", "Thường Tín", 20.8690, 105.8650),
    ("phuxuyen", "Phú Xuyên", 20.7340, 105.9030),
    ("chuongduong", "Cầu Chương Dương", 21.0370, 105.8660),
    ("ngoclam", "Ngọc Lâm", 21.0420, 105.8780),
    ("longbien", "Long Biên", 21.0420, 105.8920),
    ("saidong", "Sài Đồng", 21.0340, 105.9130),
    ("thachban", "Thạch Bàn", 21.0150, 105.9300),
    ("gialam", "Gia Lâm", 21.0480, 105.9350),
    ("yenvien", "Yên Viên", 21.0850, 105.9500),
    ("battrang", "Bát Tràng", 20.9770, 105.9240),
]
NODES = {i: {"id": i, "name": n, "lat": lat, "lng": lng} for i, n, lat, lng in NODE_ROWS}
# name, endpoints, flood susceptibility, normal speed, demonstration event
EDGE_ROWS = [
    ("Cầu Giấy", "caugiay", "buoi", 0.25, 35, ""),
    ("Đào Tấn", "buoi", "lotte", 0.2, 35, ""),
    ("Kim Mã", "caugiay", "lotte", 0.2, 35, ""),
    ("Kim Mã – Núi Trúc", "lotte", "kimma", 0.3, 35, "traffic"),
    ("Núi Trúc", "kimma", "giangvo", 0.25, 30, ""),
    ("Nguyễn Thái Học", "giangvo", "vanmieu", 0.3, 30, ""),
    ("Nguyễn Thái Học – Cửa Nam", "vanmieu", "cuanam", 0.25, 30, "traffic"),
    ("Tràng Thi", "cuanam", "hoankiem", 0.2, 30, ""),
    ("Hàng Khay – Tràng Tiền", "hoankiem", "nhahat", 0.25, 25, ""),
    ("Tràng Tiền", "nhahat", "bachdang", 0.2, 30, ""),
    ("Hoàng Hoa Thám", "buoi", "hoanghoa", 0.2, 30, ""),
    ("Đội Cấn", "lotte", "ngocha", 0.3, 25, ""),
    ("Ngọc Hà", "ngocha", "badinh", 0.2, 25, ""),
    ("Hoàng Diệu", "badinh", "vanmieu", 0.15, 30, ""),
    ("Phan Đình Phùng", "badinh", "hangdau", 0.2, 30, ""),
    ("Hàng Đào – Hàng Ngang", "hangdau", "hoankiem", 0.3, 25, ""),
    ("Đường Láng", "caugiay", "lang", 0.8, 40, "flood"),
    ("Huỳnh Thúc Kháng", "lang", "langha", 0.65, 30, ""),
    ("Láng Hạ", "langha", "giangvo", 0.8, 35, "flood"),
    ("Thái Hà", "langha", "thaiha", 0.7, 30, "traffic"),
    ("Hoàng Cầu", "thaiha", "odancho", 0.55, 30, ""),
    ("Tôn Đức Thắng", "odancho", "vanmieu", 0.4, 30, ""),
    ("Khâm Thiên", "odancho", "khamthien", 0.65, 25, "flood"),
    ("Lê Duẩn", "khamthien", "cuanam", 0.35, 35, ""),
    ("Trần Hưng Đạo", "cuanam", "tranhungdao", 0.35, 30, ""),
    ("Trần Hưng Đạo – Phan Chu Trinh", "tranhungdao", "nhahat", 0.25, 30, ""),
    ("Đường Láng – Ngã Tư Sở", "lang", "ngatuso", 0.6, 40, ""),
    ("Tây Sơn", "ngatuso", "thaiha", 0.45, 35, ""),
    ("Chùa Bộc", "ngatuso", "tonthatung", 0.4, 30, "unknown"),
    ("Phạm Ngọc Thạch", "tonthatung", "xadan", 0.4, 30, ""),
    ("Xã Đàn", "odancho", "xadan", 0.4, 35, "incident"),
    ("Xã Đàn – Đại Cồ Việt", "xadan", "daicoviet", 0.3, 35, ""),
    ("Lê Duẩn – Công viên Thống Nhất", "daicoviet", "khamthien", 0.35, 35, ""),
    ("Đại Cồ Việt", "daicoviet", "baymau", 0.35, 35, ""),
    ("Quang Trung", "baymau", "tranhungdao", 0.35, 30, ""),
    ("Hoàng Hoa Thám – Ngọc Hà", "hoanghoa", "ngocha", 0.2, 25, ""),
    ("Thụy Khuê", "hoanghoa", "thuykhue", 0.88, 30, "flood"),
    ("Thụy Khuê – Bưởi", "thuykhue", "buoi", 0.65, 30, ""),
    ("Cao Bá Quát", "badinh", "caobaquat", 0.85, 25, "flood"),
    ("Nguyễn Khuyến", "caobaquat", "nguyenkhuyen", 0.9, 25, "flood"),
    ("Văn Miếu – Nguyễn Khuyến", "nguyenkhuyen", "vanmieu", 0.65, 25, ""),
    ("Phan Bội Châu – Lý Thường Kiệt", "cuanam", "phanboichau", 0.95, 25, "flood"),
    ("Phan Bội Châu – Trần Hưng Đạo", "phanboichau", "tranhungdao", 0.75, 25, ""),
    ("Đường Thành – Bát Đàn", "hangdau", "duongthanh", 0.88, 25, "flood"),
    ("Đường Thành – Cửa Nam", "duongthanh", "cuanam", 0.5, 25, ""),
    ("Phạm Văn Đồng – Cầu Giấy", "caugiay", "phamvandong", 0.4, 40, "traffic"),
    ("Phạm Văn Đồng – Cổ Nhuế", "phamvandong", "conhue", 0.5, 45, "traffic"),
    ("Cổ Nhuế – Nhổn", "conhue", "nhon", 0.35, 40, ""),
    ("Bưởi – Xuân La", "buoi", "xuanla", 0.4, 35, ""),
    ("Võ Chí Công – Xuân La", "xuanla", "vochicong", 0.4, 45, "traffic"),
    ("Võ Chí Công – Nhật Tân", "vochicong", "nhattan", 0.3, 55, ""),
    ("Cầu Nhật Tân", "nhattan", "donganh", 0.25, 60, "incident"),
    ("Đông Anh – Nội Bài", "donganh", "noibai", 0.25, 65, ""),
    ("Nội Bài – Sóc Sơn", "noibai", "socson", 0.3, 60, ""),
    ("Mê Linh – Nội Bài", "melinh", "noibai", 0.3, 55, ""),
    ("Mê Linh – Đông Anh", "melinh", "donganh", 0.3, 50, ""),
    ("Nhổn – Mỹ Đình", "nhon", "mydinh", 0.45, 45, "traffic"),
    ("Xuân Thủy – Mỹ Đình", "caugiay", "mydinh", 0.4, 40, ""),
    ("Mỹ Đình – Mễ Trì", "mydinh", "metri", 0.55, 40, "traffic"),
    ("Mễ Trì – Trung Văn", "metri", "trungvan", 0.5, 40, ""),
    ("Lê Văn Lương – Khuất Duy Tiến", "levanluong", "khuatduytien", 0.55, 35, "traffic"),
    ("Lê Văn Lương – Láng Hạ", "levanluong", "langha", 0.5, 35, ""),
    ("Khuất Duy Tiến – Mễ Trì", "khuatduytien", "metri", 0.5, 45, ""),
    ("Nguyễn Tuân – Quan Nhân", "nguyentuan", "quannhan", 0.55, 30, "traffic"),
    ("Quan Nhân – Lê Văn Lương", "quannhan", "levanluong", 0.65, 30, "flood"),
    ("Nguyễn Tuân – Nguyễn Trãi", "nguyentuan", "nguyentrai", 0.5, 30, ""),
    ("Nguyễn Trãi – Ngã Tư Sở", "nguyentrai", "ngatuso", 0.55, 35, "traffic"),
    ("Nguyễn Trãi – Khuất Duy Tiến", "nguyentrai", "khuatduytien", 0.6, 40, "incident"),
    ("Trung Văn – Nguyễn Trãi", "trungvan", "nguyentrai", 0.6, 35, ""),
    ("Trung Văn – Hà Đông", "trungvan", "hadong", 0.65, 40, "traffic"),
    ("Quang Trung – Hà Đông", "hadong", "yenghia", 0.7, 40, ""),
    ("Yên Nghĩa – Chương Mỹ", "yenghia", "chuongmy", 0.7, 50, ""),
    ("Tây Mỗ – Hà Đông", "taymo", "hadong", 0.55, 45, ""),
    ("Đại lộ Thăng Long – An Khánh", "taymo", "ankhanh", 0.92, 65, "flood"),
    ("Đại lộ Thăng Long – Mễ Trì", "metri", "taymo", 0.8, 60, ""),
    ("An Khánh – Hoài Đức", "ankhanh", "hoaibac", 0.55, 50, ""),
    ("Nhổn – Hoài Đức", "nhon", "hoaibac", 0.45, 45, ""),
    ("An Khánh – Quốc Oai", "ankhanh", "quocoai", 0.6, 60, ""),
    ("Quốc Oai – Hòa Lạc", "quocoai", "hoalac", 0.55, 60, ""),
    ("Hòa Lạc – Sơn Tây", "hoalac", "sontay", 0.4, 60, ""),
    ("Sơn Tây – Ba Vì", "sontay", "bavi", 0.45, 55, ""),
    ("Hoài Đức – Sơn Tây", "hoaibac", "sontay", 0.4, 60, ""),
    ("Quốc Oai – Chương Mỹ", "quocoai", "chuongmy", 0.6, 50, ""),
    ("Chương Mỹ – Mỹ Đức", "chuongmy", "myduc", 0.7, 50, ""),
    ("Yên Nghĩa – Mỹ Đức", "yenghia", "myduc", 0.7, 50, ""),
    ("Trường Chinh – Ngã Tư Sở", "ngatuso", "truongchinh", 0.9, 35, "flood"),
    ("Trường Chinh – Ngã Tư Vọng", "truongchinh", "vong", 0.78, 35, "traffic"),
    ("Ngã Tư Vọng – Đại Cồ Việt", "vong", "daicoviet", 0.4, 35, ""),
    ("Nguyễn Xiển – Khuất Duy Tiến", "khuatduytien", "nguyenxien", 0.86, 40, "flood"),
    ("Nguyễn Xiển – Linh Đàm", "nguyenxien", "linhdam", 0.82, 40, "traffic"),
    ("Linh Đàm – Định Công", "linhdam", "dinhcong", 0.7, 35, ""),
    ("Định Công – Ngã Tư Vọng", "dinhcong", "vong", 0.55, 35, ""),
    ("Giáp Bát – Ngã Tư Vọng", "giapbat", "vong", 0.55, 35, "traffic"),
    ("Giáp Bát – Linh Đàm", "giapbat", "linhdam", 0.7, 40, ""),
    ("Minh Khai – Đại Cồ Việt", "minhkhai", "daicoviet", 0.75, 35, "flood"),
    ("Minh Khai – Lĩnh Nam", "minhkhai", "linhnam", 0.7, 35, ""),
    ("Lĩnh Nam – Pháp Vân", "linhnam", "phapvan", 0.7, 40, ""),
    ("Pháp Vân – Linh Đàm", "phapvan", "linhdam", 0.55, 50, ""),
    ("Giáp Bát – Pháp Vân", "giapbat", "phapvan", 0.6, 50, "incident"),
    ("Pháp Vân – Thanh Trì", "phapvan", "thanhtri", 0.6, 55, "traffic"),
    ("Thanh Trì – Thường Tín", "thanhtri", "thuongtin", 0.55, 55, ""),
    ("Thường Tín – Phú Xuyên", "thuongtin", "phuxuyen", 0.55, 60, ""),
    ("Cầu Chương Dương", "bachdang", "chuongduong", 0.2, 40, "traffic"),
    ("Chương Dương – Ngọc Lâm", "chuongduong", "ngoclam", 0.25, 40, ""),
    ("Ngọc Lâm – Long Biên", "ngoclam", "longbien", 0.4, 40, ""),
    ("Long Biên – Sài Đồng", "longbien", "saidong", 0.45, 45, "traffic"),
    ("Sài Đồng – Thạch Bàn", "saidong", "thachban", 0.55, 45, ""),
    ("Long Biên – Gia Lâm", "longbien", "gialam", 0.4, 50, ""),
    ("Gia Lâm – Yên Viên", "gialam", "yenvien", 0.45, 50, ""),
    ("Đông Anh – Yên Viên", "donganh", "yenvien", 0.4, 50, ""),
    ("Thạch Bàn – Bát Tràng", "thachban", "battrang", 0.55, 45, ""),
]

FLOOD_REFERENCES = {
    **dict.fromkeys(
        (
            "Cao Bá Quát", "Nguyễn Khuyến", "Phan Bội Châu – Lý Thường Kiệt",
            "Đường Thành – Bát Đàn", "Đại lộ Thăng Long – An Khánh",
            "Trường Chinh – Ngã Tư Sở",
        ),
        "https://thoatnuochanoi.vn/tin-tuc-chi-tiet/8139/ha-noi-con-12-diem-ung-ngap-tren-cac-tuyen-pho-chinh",
    ),
    **dict.fromkeys(
        ("Thụy Khuê", "Nguyễn Xiển – Khuất Duy Tiến", "Minh Khai – Đại Cồ Việt"),
        "https://thoatnuochanoi.vn/tin-tuc-chi-tiet/21283/du-an-thi-cong-do-dang-can-tro-thoat-nuoc-mua-o-ha-noi",
    ),
}


def distance(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def polyline_midpoint(coordinates):
    lengths = [distance(a, b) for a, b in zip(coordinates, coordinates[1:])]
    halfway = sum(lengths) / 2
    passed = 0
    for (a, b), length in zip(zip(coordinates, coordinates[1:]), lengths):
        if passed + length >= halfway:
            fraction = (halfway - passed) / length if length else 0
            return [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction]
        passed += length
    return coordinates[-1]


_geometry_file = Path(__file__).with_name("hanoi_roads_osrm.json")
_geometry = json.loads(_geometry_file.read_text(encoding="utf-8"))["routes"] if _geometry_file.exists() else {}


ROADS = []
for idx, (name, a, b, susceptibility, speed, event) in enumerate(EDGE_ROWS):
    road_id = f"HN-{idx + 1:03}"
    shape = _geometry.get(road_id)
    coordinates = shape["coordinates"] if shape else [[NODES[n]["lat"], NODES[n]["lng"]] for n in (a, b)]
    ROADS.append(
        dict(
            id=road_id,
            name=name,
            a=a,
            b=b,
            coordinates=coordinates,
            length_km=shape["length_km"] if shape else round(distance(*coordinates), 3),
            center=polyline_midpoint(coordinates),
            geometry_source="osm_osrm" if shape else "demo_straight",
            susceptibility=susceptibility,
            free_speed=speed,
            seed_event=event,
            traffic_hotspot=0.85 if event == "traffic" else 0.45 if event == "incident" else 0.15,
            incident_hotspot=0.85 if event == "incident" else 0.35 if event == "traffic" else 0.15,
            reference_url=FLOOD_REFERENCES.get(name),
        )
    )
ROAD_INDEX = {r["id"]: r for r in ROADS}


def nearest_road(lat, lng):
    """Project onto every segment of each cached road polyline."""
    best = None
    for r in ROADS:
        for (ay, ax), (by, bx) in zip(r["coordinates"], r["coordinates"][1:]):
            scale = math.cos(math.radians(lat))
            dx, dy = (bx - ax) * scale, by - ay
            denominator = dx * dx + dy * dy
            t = max(0, min(1, (((lng - ax) * scale) * dx + (lat - ay) * dy) / denominator)) if denominator else 0
            point = [ay + t * (by - ay), ax + t * (bx - ax)]
            km = distance([lat, lng], point)
            if best is None or km < best[0]:
                best = (km, r, point)
    return best
