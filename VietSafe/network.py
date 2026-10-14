"""Small, hand-authored Hanoi demo graph. Not a navigation-grade road network."""
import math

NODE_ROWS = [
    ('caugiay', 'Cầu Giấy', 21.0313, 105.8006),
    ('buoi', 'Bưởi – Đào Tấn', 21.0408, 105.8067),
    ('lotte', 'Liễu Giai – Đào Tấn', 21.0355, 105.8128),
    ('kimma', 'Kim Mã – Núi Trúc', 21.0318, 105.8247),
    ('giangvo', 'Giảng Võ – Cát Linh', 21.0282, 105.8268),
    ('vanmieu', 'Văn Miếu', 21.0274, 105.8355),
    ('cuanam', 'Cửa Nam', 21.0263, 105.8417),
    ('hoankiem', 'Hồ Hoàn Kiếm', 21.0285, 105.8521),
    ('bachdang', 'Trần Quang Khải', 21.0272, 105.8600),
    ('hoanghoa', 'Hoàng Hoa Thám', 21.0435, 105.8220),
    ('ngocha', 'Ngọc Hà – Đội Cấn', 21.0366, 105.8310),
    ('badinh', 'Ba Đình', 21.0374, 105.8382),
    ('hangdau', 'Hàng Đậu', 21.0400, 105.8489),
    ('lang', 'Đường Láng – Nguyễn Chí Thanh', 21.0182, 105.8053),
    ('langha', 'Láng Hạ – Huỳnh Thúc Kháng', 21.0163, 105.8132),
    ('thaiha', 'Thái Hà – Hoàng Cầu', 21.0126, 105.8211),
    ('odancho', 'Ô Chợ Dừa', 21.0181, 105.8290),
    ('khamthien', 'Khâm Thiên', 21.0184, 105.8393),
    ('tranhungdao', 'Trần Hưng Đạo – Quang Trung', 21.0200, 105.8475),
    ('nhahat', 'Nhà hát Lớn', 21.0242, 105.8571),
    ('ngatuso', 'Ngã Tư Sở', 21.0030, 105.8200),
    ('tonthatung', 'Tôn Thất Tùng – Chùa Bộc', 21.0064, 105.8292),
    ('xadan', 'Xã Đàn – Phạm Ngọc Thạch', 21.0095, 105.8352),
    ('daicoviet', 'Đại Cồ Việt – Giải Phóng', 21.0078, 105.8422),
    ('baymau', 'Công viên Thống Nhất', 21.0102, 105.8482),
]
NODES = {i: {'id': i, 'name': n, 'lat': lat, 'lng': lng} for i, n, lat, lng in NODE_ROWS}
# name, endpoints, flood susceptibility, normal speed, demonstration event
EDGE_ROWS = [
    ('Cầu Giấy', 'caugiay', 'buoi', .25, 35, ''),
    ('Đào Tấn', 'buoi', 'lotte', .2, 35, ''),
    ('Kim Mã', 'caugiay', 'lotte', .2, 35, ''),
    ('Kim Mã – Núi Trúc', 'lotte', 'kimma', .3, 35, 'traffic'),
    ('Núi Trúc', 'kimma', 'giangvo', .25, 30, ''),
    ('Nguyễn Thái Học', 'giangvo', 'vanmieu', .3, 30, ''),
    ('Nguyễn Thái Học – Cửa Nam', 'vanmieu', 'cuanam', .25, 30, 'traffic'),
    ('Tràng Thi', 'cuanam', 'hoankiem', .2, 30, ''),
    ('Hàng Khay – Tràng Tiền', 'hoankiem', 'nhahat', .25, 25, ''),
    ('Tràng Tiền', 'nhahat', 'bachdang', .2, 30, ''),
    ('Hoàng Hoa Thám', 'buoi', 'hoanghoa', .2, 30, ''),
    ('Đội Cấn', 'lotte', 'ngocha', .3, 25, ''),
    ('Ngọc Hà', 'ngocha', 'badinh', .2, 25, ''),
    ('Hoàng Diệu', 'badinh', 'vanmieu', .15, 30, ''),
    ('Phan Đình Phùng', 'badinh', 'hangdau', .2, 30, ''),
    ('Hàng Đào – Hàng Ngang', 'hangdau', 'hoankiem', .3, 25, ''),
    ('Đường Láng', 'caugiay', 'lang', .8, 40, 'flood'),
    ('Huỳnh Thúc Kháng', 'lang', 'langha', .65, 30, ''),
    ('Láng Hạ', 'langha', 'giangvo', .8, 35, 'flood'),
    ('Thái Hà', 'langha', 'thaiha', .7, 30, 'traffic'),
    ('Hoàng Cầu', 'thaiha', 'odancho', .55, 30, ''),
    ('Tôn Đức Thắng', 'odancho', 'vanmieu', .4, 30, ''),
    ('Khâm Thiên', 'odancho', 'khamthien', .65, 25, 'flood'),
    ('Lê Duẩn', 'khamthien', 'cuanam', .35, 35, ''),
    ('Trần Hưng Đạo', 'cuanam', 'tranhungdao', .35, 30, ''),
    ('Trần Hưng Đạo – Phan Chu Trinh', 'tranhungdao', 'nhahat', .25, 30, ''),
    ('Đường Láng – Ngã Tư Sở', 'lang', 'ngatuso', .6, 40, ''),
    ('Tây Sơn', 'ngatuso', 'thaiha', .45, 35, ''),
    ('Chùa Bộc', 'ngatuso', 'tonthatung', .4, 30, 'unknown'),
    ('Phạm Ngọc Thạch', 'tonthatung', 'xadan', .4, 30, ''),
    ('Xã Đàn', 'odancho', 'xadan', .4, 35, 'incident'),
    ('Xã Đàn – Đại Cồ Việt', 'xadan', 'daicoviet', .3, 35, ''),
    ('Lê Duẩn – Công viên Thống Nhất', 'daicoviet', 'khamthien', .35, 35, ''),
    ('Đại Cồ Việt', 'daicoviet', 'baymau', .35, 35, ''),
    ('Quang Trung', 'baymau', 'tranhungdao', .35, 30, ''),
    ('Hoàng Hoa Thám – Ngọc Hà', 'hoanghoa', 'ngocha', .2, 25, ''),
]


def distance(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2-lat1, math.radians(b[1]-a[1])
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


ROADS = []
for idx, (name, a, b, susceptibility, speed, event) in enumerate(EDGE_ROWS):
    coordinates = [[NODES[n]['lat'], NODES[n]['lng']] for n in (a, b)]
    ROADS.append(dict(id=f'HN-{idx+1:03}', name=name, a=a, b=b,
                      coordinates=coordinates, length_km=round(distance(*coordinates), 3),
                      susceptibility=susceptibility, free_speed=speed, seed_event=event))
ROAD_INDEX = {r['id']: r for r in ROADS}


def nearest_road(lat, lng):
    """Project onto each short segment in local equirectangular coordinates."""
    best = None
    for r in ROADS:
        (ay, ax), (by, bx) = r['coordinates']
        scale = math.cos(math.radians(lat))
        dx, dy = (bx-ax)*scale, by-ay
        t = max(0, min(1, (((lng-ax)*scale)*dx+(lat-ay)*dy)/(dx*dx+dy*dy)))
        point = [ay+t*(by-ay), ax+t*(bx-ax)]
        km = distance([lat, lng], point)
        if best is None or km < best[0]:
            best = (km, r, point)
    return best
