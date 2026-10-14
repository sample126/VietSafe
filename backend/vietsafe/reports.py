"""Community reports and verified point observations."""
import base64
import binascii
import math
import secrets
import time
from .db import connect
from .core.network import nearest_road, ROAD_INDEX

def get_reports():
    with connect() as db:
        db.execute("UPDATE reports SET status='expired' WHERE expires_at<? AND status IN ('pending','verified')",(time.time(),))
        rows=db.execute('SELECT id,road_id,type,severity,lat,lng,address,description,status,created_at,expires_at,reviewed_at,media_type FROM reports ORDER BY created_at DESC LIMIT 500').fetchall()
    return [dict(r,media_url='/api/report-media/'+r['id'] if r['media_type'] else None) for r in rows]


def create_report(body):
    if not isinstance(body,dict):
        raise ValueError('Nội dung phản ánh không hợp lệ.')
    if body.get('type') not in ('flood','traffic','incident'):
        raise ValueError('Loại phản ánh không hợp lệ.')
    if type(body.get('severity')) is not int or body['severity'] not in (1,2,3):
        raise ValueError('Hãy chọn mức độ 1–3.')
    try:
        lat,lng=float(body['lat']),float(body['lng'])
    except (KeyError,TypeError,ValueError):
        raise ValueError('Hãy chọn vị trí trên bản đồ.')
    if not math.isfinite(lat) or not math.isfinite(lng) or not (20.98<=lat<=21.065 and 105.77<=lng<=105.88):
        raise ValueError('Vị trí nằm ngoài vùng thử nghiệm nội thành Hà Nội.')
    km,road,_=nearest_road(lat,lng)
    if km>1:
        raise ValueError('Vị trí cách mạng đường thử nghiệm hơn 1 km. Hãy chọn một đoạn đường gần hơn.')
    description=body.get('description','')
    if not isinstance(description,str) or not 10<=len(description.strip())<=1200:
        raise ValueError('Mô tả cần từ 10 đến 1.200 ký tự.')
    address=body.get('address','')
    if not isinstance(address,str) or len(address)>200:
        raise ValueError('Địa chỉ tối đa 200 ký tự.')
    media=None
    media_type=None
    if body.get('image'):
        try:
            header,encoded=body['image'].split(',',1)
            media_type=header.removeprefix('data:').removesuffix(';base64')
            if media_type not in ('image/jpeg','image/png','image/webp'):
                raise ValueError()
            media=base64.b64decode(encoded,validate=True)
            signatures={'image/jpeg':media.startswith(b'\xff\xd8\xff'), 'image/png':media.startswith(b'\x89PNG\r\n\x1a\n'),
                        'image/webp':media.startswith(b'RIFF') and media[8:12]==b'WEBP'}
            if len(media)>1_500_000 or not signatures[media_type]:
                raise ValueError()
        except (ValueError,TypeError,AttributeError,binascii.Error):
            raise ValueError('Ảnh phải là JPG, PNG hoặc WebP, tối đa 1,5 MB.')
    now=time.time()
    with connect() as db:
        # Serialize duplicate-check and insert even for simultaneous requests.
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute("SELECT id FROM reports WHERE road_id=? AND type=? AND description=? AND created_at>? AND status='pending'",
                            (road['id'],body['type'],description.strip(),now-300)).fetchone()
        if existing:
            return {'id':existing[0],'duplicate':True,'status':'pending'}
        rid='R-'+secrets.token_hex(4).upper()
        db.execute('INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (rid,road['id'],body['type'],body['severity'],lat,lng,address.strip() or road['name'],description.strip(),
                    'pending',now,now+7200,media,media_type,None))
        db.execute('INSERT INTO audit(report_id,action,timestamp) VALUES(?,?,?)',(rid,'created',now))
    return {'id':rid,'status':'pending','road_id':road['id'],'duplicate':False}


def review_report(rid, status):
    if status not in ('verified','rejected','resolved'):
        raise ValueError('Trạng thái không hợp lệ.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        r=db.execute('SELECT status,expires_at FROM reports WHERE id=?',(rid,)).fetchone()
        if not r:
            raise ValueError('Không tìm thấy phản ánh.')
        allowed={'pending':('verified','rejected'), 'verified':('resolved',)}
        if r['expires_at']<=time.time() or status not in allowed.get(r['status'],()):
            raise ValueError('Phản ánh đã hết hạn hoặc không thể chuyển sang trạng thái này.')
        db.execute('UPDATE reports SET status=?,reviewed_at=? WHERE id=?',(status,time.time(),rid))
        db.execute('INSERT INTO audit(report_id,action,timestamp) VALUES(?,?,?)',(rid,status,time.time()))
    return {'id':rid,'status':status}


def get_flood_observations():
    """Only verified, recently observed station readings, never inferred road depths."""
    with connect() as db:
        rows = db.execute("""SELECT id,road_id,lat,lng,depth_cm,observed_at,received_at,
                            source,source_reference,notes,verification_status
                            FROM flood_observations WHERE verification_status='verified'
                            AND observed_at>=? ORDER BY observed_at DESC LIMIT 500""",
                          (time.time()-7200,)).fetchall()
    return {'source':'verified_import_or_station', 'kind':'point_observations',
            'coverage':'only_registered_observation_points', 'observations':[dict(r) for r in rows]}


def add_flood_observation(body):
    """Manual ingestion requires administrator approval and an identifiable source."""
    try:
        lat, lng = float(body['lat']), float(body['lng'])
        depth = float(body['depth_cm'])
        observed_at = float(body['observed_at'])
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError('Cần lat, lng, depth_cm và observed_at hợp lệ.') from exc
    if not all(map(math.isfinite, (lat,lng,depth,observed_at))):
        raise ValueError('Giá trị số không hợp lệ.')
    if not (-90 <= lat <= 90 and -180 <= lng <= 180 and 0 <= depth <= 1000):
        raise ValueError('Tọa độ hoặc độ sâu nằm ngoài phạm vi.')
    now = time.time()
    if not now-7*86400 <= observed_at <= now+300:
        raise ValueError('Thời gian quan trắc không hợp lệ hoặc quá cũ.')
    source = body.get('source')
    reference = body.get('source_reference')
    if not isinstance(source,str) or not 3 <= len(source.strip()) <= 100:
        raise ValueError('Nguồn đo bắt buộc (3–100 ký tự).')
    if not isinstance(reference,str) or not 3 <= len(reference.strip()) <= 200:
        raise ValueError('Mã cảm biến hoặc tham chiếu nguồn bắt buộc.')
    notes = body.get('notes','')
    if not isinstance(notes,str) or len(notes)>500:
        raise ValueError('Ghi chú tối đa 500 ký tự.')
    road_id=body.get('road_id')
    if road_id is not None and (not isinstance(road_id,str) or road_id not in ROAD_INDEX):
        raise ValueError('Mã đường không tồn tại trong mạng đường thử nghiệm.')
    rid='FO-'+secrets.token_hex(8)
    with connect() as db:
        db.execute('INSERT INTO flood_observations VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (rid,road_id,lat,lng,depth,observed_at,now,source.strip(),reference.strip(),notes,'verified'))
    return {'id':rid,'status':'verified', 'kind':'point_observation'}
