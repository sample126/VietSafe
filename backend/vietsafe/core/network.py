"""Hand-authored Hanoi demo graph following imported OpenStreetMap road geometry."""
import json
import math
from pathlib import Path

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


def decode_polyline6(encoded):
    coordinates=[]
    index=latitude=longitude=0
    while index<len(encoded):
        deltas=[]
        for _ in range(2):
            result=shift=0
            while True:
                value=ord(encoded[index])-63
                index+=1
                result|=(value&0x1f)<<shift
                shift+=5
                if value<0x20:
                    break
            deltas.append(~(result>>1) if result&1 else result>>1)
        latitude+=deltas[0]
        longitude+=deltas[1]
        coordinates.append([latitude/1_000_000,longitude/1_000_000])
    return coordinates


with (Path(__file__).parent / 'data' / 'osm_road_geometry.json').open(encoding='utf-8') as geometry_file:
    ROAD_GEOMETRY_DATA=json.load(geometry_file)
ROAD_GEOMETRIES=ROAD_GEOMETRY_DATA['roads']


def road_midpoint(coordinates):
    """Return the point halfway along a road's polyline by geographic distance."""
    if len(coordinates)<2:
        raise ValueError('Hình học tuyến đường cần ít nhất hai điểm.')
    lengths=[distance(a,b) for a,b in zip(coordinates,coordinates[1:])]
    halfway=sum(lengths)/2
    for start,end,length in zip(coordinates,coordinates[1:],lengths):
        if halfway<=length:
            fraction=halfway/length if length else 0
            return [start[0]+(end[0]-start[0])*fraction,
                    start[1]+(end[1]-start[1])*fraction]
        halfway-=length
    return list(coordinates[-1])


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
    road_id=f'HN-{idx+1:03}'
    geometry=ROAD_GEOMETRIES[road_id]
    coordinates=decode_polyline6(geometry['geometry'])
    if len(coordinates)<3:
        raise ValueError(f'Hình học OSM của {road_id} không có đủ điểm trên tuyến.')
    for node_id, point in ((a,coordinates[0]),(b,coordinates[-1])):
        NODES[node_id]['lat']=point[0]
        NODES[node_id]['lng']=point[1]
    ROADS.append(dict(id=f'HN-{idx+1:03}', name=name, a=a, b=b,
                      coordinates=coordinates, length_km=round(geometry['length_m']/1000, 3),
                      susceptibility=susceptibility, free_speed=speed, seed_event=event))
ROAD_INDEX = {r['id']: r for r in ROADS}


def nearest_road(lat, lng):
    """Project onto the closest segment of the OSM road polylines."""
    best = None
    for r in ROADS:
        for start,end in zip(r['coordinates'],r['coordinates'][1:]):
            scale=math.cos(math.radians(lat))
            dx,dy=(end[1]-start[1])*scale,end[0]-start[0]
            px,py=(lng-start[1])*scale,lat-start[0]
            fraction=max(0,min(1,(px*dx+py*dy)/(dx*dx+dy*dy or 1)))
            point=[start[0]+fraction*(end[0]-start[0]),
                   start[1]+fraction*(end[1]-start[1])]
            km=distance([lat,lng],point)
            if best is None or km<best[0]:
                best=(km,r,point)
    return best
