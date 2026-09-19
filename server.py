"""VietSafe local server: Python standard library + SQLite, no pip installation."""
import argparse
import base64
import binascii
import csv
from contextlib import contextmanager
import io
import hashlib
import json
import math
import mimetypes
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

from engine import build_snapshot, calculate_routes, SCENARIOS, MODEL_VERSION
from network import NODES, ROADS, ROAD_INDEX, nearest_road

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT/'public'
DB_PATH = ROOT/'data'/'vietsafe.sqlite3'
MAX_BODY = 2_200_000


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO settings VALUES ('scenario','rain');
        CREATE TABLE IF NOT EXISTS reports(
          id TEXT PRIMARY KEY, road_id TEXT NOT NULL, type TEXT NOT NULL, severity INTEGER NOT NULL,
          lat REAL NOT NULL, lng REAL NOT NULL, address TEXT NOT NULL, description TEXT NOT NULL,
          status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
          media BLOB, media_type TEXT, reviewed_at REAL);
        CREATE TABLE IF NOT EXISTS prediction_logs(
          tick INTEGER PRIMARY KEY, created_at REAL, model_version TEXT, scenario TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, report_id TEXT, action TEXT, timestamp REAL);
        CREATE TABLE IF NOT EXISTS users(
          username TEXT PRIMARY KEY,
          password_hash TEXT NOT NULL,
          display_name TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'citizen'
        );
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          created_at REAL NOT NULL,
          expires_at REAL NOT NULL
        );
        ''')

    # Seed default demo accounts
    with connect() as db:
        for uname, pwd, display, role in [
            ('admin', 'vietsafe2026', 'Quản trị viên', 'admin'),
            ('nguoidan', 'matkhau123', 'Nguyễn Văn A', 'citizen'),
        ]:
            h = hashlib.sha256(pwd.encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?)', (uname, h, display, role))


def get_reports():
    with connect() as db:
        db.execute("UPDATE reports SET status='expired' WHERE expires_at<? AND status IN ('pending','verified')",(time.time(),))
        rows=db.execute('SELECT id,road_id,type,severity,lat,lng,address,description,status,created_at,expires_at,reviewed_at,media_type FROM reports ORDER BY created_at DESC LIMIT 500').fetchall()
    return [dict(r,media_url='/api/report-media/'+r['id'] if r['media_type'] else None) for r in rows]


def snapshot():
    with connect() as db:
        scenario=db.execute("SELECT value FROM settings WHERE key='scenario'").fetchone()[0]
    result=build_snapshot(scenario,get_reports())
    with connect() as db:
        # At most one log per ten seconds, retained for later evaluation with actual observations.
        tick=int(result['generated_at']//10)
        payload=[dict(road_id=r['id'],forecast=r['forecast']) for r in result['roads']]
        db.execute('INSERT OR IGNORE INTO prediction_logs VALUES(?,?,?,?,?)',
                   (tick,result['generated_at'],MODEL_VERSION,scenario,json.dumps(payload)))
        db.execute('DELETE FROM prediction_logs WHERE tick < ?',(tick-8640,))
    return result


def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFD',s.lower().replace('đ','d')) if unicodedata.category(c)!='Mn')


def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def create_session(username):
    token = secrets.token_hex(32)
    now = time.time()
    with connect() as db:
        # Clean expired sessions
        db.execute('DELETE FROM sessions WHERE expires_at < ?', (now,))
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token, username, now, now + 86400))
    return token

def get_user_by_session(token):
    if not token:
        return None
    with connect() as db:
        row = db.execute(
            'SELECT u.username, u.display_name, u.role FROM sessions s '
            'JOIN users u ON s.username=u.username WHERE s.token=? AND s.expires_at>?',
            (token, time.time())
        ).fetchone()
    return dict(row) if row else None


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


class Handler(BaseHTTPRequestHandler):
    server_version='VietSafeLocal/1.0'
    rates={}
    rate_lock=threading.Lock()

    def log_message(self, fmt, *args):
        # Keep logs concise, no report payloads or location details.
        if args and str(args[0]).startswith('GET /api/snapshot'):
            return
        super().log_message(fmt,*args)

    def respond(self, data, code=200, content_type='application/json; charset=utf-8', headers=None):
        payload=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8') if content_type.startswith('application/json') else data
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'no-cache')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tiles.stadiamaps.com https://*.tile.openstreetmap.org; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        for key,value in (headers or {}).items(): self.send_header(key,value)
        self.end_headers()
        try: self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError): pass

    def valid_host(self):
        h = self.headers.get('Host', '')
        if h in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            return True
        # Allow known tunnel and hosting domains
        domain = h.split(':')[0].lower()
        if any(domain.endswith(t) for t in ('.trycloudflare.com', '.loca.lt', '.ngrok.io', '.ngrok-free.app', '.onrender.com')):
            return True
        return False

    def get_current_user(self):
        token = self.headers.get('X-VietSafe-Session')
        return get_user_by_session(token) if token else None

    def do_GET(self):
        if not self.valid_host():
            return self.respond({'error':'Local access only.'},403)
        u=urlparse(self.path)
        q=parse_qs(u.query)
        try:
            if u.path=='/api/snapshot': return self.respond(snapshot())
            if u.path=='/api/reports': return self.respond({'reports':get_reports()})
            if u.path=='/api/health': return self.respond({'ok':True,'mode':'demo','model_version':MODEL_VERSION})
            if u.path == '/api/auth/me':
                user = self.get_current_user()
                return self.respond({'user': user})
            if u.path=='/api/search':
                term=normalize(q.get('q',[''])[0])[:150]
                matches=[dict(n,kind='node') for n in NODES.values() if term in normalize(n['name'])]
                matches += [dict(id=r['id'],name=r['name'],lat=sum(c[0] for c in r['coordinates'])/2,
                                 lng=sum(c[1] for c in r['coordinates'])/2,kind='road') for r in ROADS if term in normalize(r['name'])]
                return self.respond({'results':matches[:12]})
            if u.path=='/api/routes':
                return self.respond(calculate_routes(snapshot(),q.get('origin',[''])[0],q.get('destination',[''])[0],
                                                     int(q.get('horizon',['0'])[0]),q.get('vehicle',['motorbike'])[0]))
            if u.path=='/api/export/predictions':
                user = self.get_current_user()
                if not user or user['role'] != 'admin':
                    return self.respond({'error': 'Chỉ quản trị viên mới có thể xuất dữ liệu.'}, 403)
                with connect() as db: rows=[dict(r) for r in db.execute('SELECT * FROM prediction_logs ORDER BY tick DESC LIMIT 500')]
                return self.respond({'mode':'demo','model_version':MODEL_VERSION,'logs':rows},headers={'Content-Disposition':'attachment; filename="vietsafe-predictions.json"'})
            if u.path=='/api/export/reports':
                user = self.get_current_user()
                if not user or user['role'] != 'admin':
                    return self.respond({'error': 'Chỉ quản trị viên mới có thể xuất dữ liệu.'}, 403)
                stream=io.StringIO()
                fields=['id','road_id','type','severity','address','description','status','created_at']
                writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
                for r in get_reports():
                    # Prevent spreadsheet formula injection in exported user input.
                    writer.writerow({k: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for k,v in r.items()})
                return self.respond(('\ufeff'+stream.getvalue()).encode('utf-8'),content_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="vietsafe-reports.csv"'})
            if u.path.startswith('/api/report-media/'):
                rid=u.path.rsplit('/',1)[-1]
                with connect() as db: r=db.execute('SELECT media,media_type FROM reports WHERE id=?',(rid,)).fetchone()
                if not r or not r['media']: return self.respond({'error':'Không có ảnh.'},404)
                return self.respond(r['media'],content_type=r['media_type'])
            if u.path.startswith('/api/'): return self.respond({'error':'API không tồn tại.'},404)
            target=(PUBLIC/unquote(u.path).lstrip('/')).resolve() if u.path!='/' else PUBLIC/'index.html'
            if not target.is_relative_to(PUBLIC) or not target.is_file():
                return self.respond({'error':'Không tìm thấy tài nguyên.'},404)
            mime=mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
            if target.suffix=='.js': mime='application/javascript'
            return self.respond(target.read_bytes(),content_type=mime)
        except (ValueError,TypeError) as e: return self.respond({'error':str(e)},400)
        except Exception:
            import traceback;traceback.print_exc()
            return self.respond({'error':'Lỗi xử lý dữ liệu tại máy. Kiểm tra cửa sổ máy chủ.'},500)

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        origin=self.headers.get('Origin')
        host=self.headers.get('Host','')
        allowed=(f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}',f'http://{host}',f'https://{host}')
        if not self.valid_host() or (origin and origin not in allowed) or self.headers.get('X-VietSafe')!='local':
            return self.respond({'error':'Yêu cầu phải được gửi từ website hợp lệ.'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>MAX_BODY: return self.respond({'error':'Nội dung quá lớn hoặc trống.'},413)
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('JSON phải là một đối tượng.')
            
            if self.path == '/api/auth/login':
                uname = body.get('username', '').strip()
                pwd = body.get('password', '')
                if not uname or not pwd:
                    raise ValueError('Vui lòng nhập tên đăng nhập và mật khẩu.')
                with connect() as db:
                    row = db.execute('SELECT username, display_name, role, password_hash FROM users WHERE username=?', (uname,)).fetchone()
                if not row or row['password_hash'] != hash_password(pwd):
                    return self.respond({'error': 'Sai tên đăng nhập hoặc mật khẩu.'}, 401)
                token = create_session(row['username'])
                user = {'username': row['username'], 'display_name': row['display_name'], 'role': row['role']}
                return self.respond({'user': user, 'token': token})
            
            if self.path == '/api/auth/register':
                uname = body.get('username', '').strip()
                pwd = body.get('password', '')
                display = body.get('display_name', '').strip()
                if not uname or len(uname) < 3 or len(uname) > 30:
                    raise ValueError('Tên đăng nhập cần từ 3 đến 30 ký tự.')
                if not pwd or len(pwd) < 6:
                    raise ValueError('Mật khẩu cần ít nhất 6 ký tự.')
                if not display or len(display) > 50:
                    raise ValueError('Tên hiển thị cần từ 1 đến 50 ký tự.')
                h = hash_password(pwd)
                try:
                    with connect() as db:
                        db.execute('INSERT INTO users VALUES(?,?,?,?)', (uname, h, display, 'citizen'))
                except sqlite3.IntegrityError:
                    raise ValueError('Tên đăng nhập đã tồn tại.')
                token = create_session(uname)
                user = {'username': uname, 'display_name': display, 'role': 'citizen'}
                return self.respond({'user': user, 'token': token})
            
            if self.path == '/api/auth/logout':
                token = self.headers.get('X-VietSafe-Session')
                if token:
                    with connect() as db:
                        db.execute('DELETE FROM sessions WHERE token=?', (token,))
                return self.respond({'ok': True})

            if self.path=='/api/reports':
                user = self.get_current_user()
                if not user:
                    return self.respond({'error': 'Vui lòng đăng nhập để gửi phản ánh.'}, 401)
                with self.rate_lock:
                    now=time.time(); recent=[t for t in self.rates.get(self.client_address[0],[]) if t>now-60]
                    if len(recent)>=10: return self.respond({'error':'Bạn đã gửi nhiều phản ánh. Vui lòng chờ một phút.'},429)
                    self.rates[self.client_address[0]]=recent+[now]
                return self.respond(create_report(body),201)
            if self.path=='/api/scenario':
                user = self.get_current_user()
                if not user or user['role'] != 'admin':
                    return self.respond({'error': 'Chỉ quản trị viên mới có thể đổi kịch bản.'}, 403)
                value=body.get('scenario')
                if value not in SCENARIOS: raise ValueError('Kịch bản không hợp lệ.')
                with connect() as db: db.execute("UPDATE settings SET value=? WHERE key='scenario'",(value,))
                return self.respond({'scenario':value})
            if self.path.startswith('/api/reports/'):
                user = self.get_current_user()
                if not user or user['role'] != 'admin':
                    return self.respond({'error': 'Chỉ quản trị viên mới có thể duyệt phản ánh.'}, 403)
                return self.respond(review_report(self.path.rsplit('/',1)[-1],body.get('status')))
            return self.respond({'error':'API không tồn tại.'},404)
        except (ValueError,TypeError,KeyError,UnicodeDecodeError) as e: return self.respond({'error':str(e)},400)
        except Exception:
            import traceback;traceback.print_exc()
            return self.respond({'error':'Không thể lưu dữ liệu. Kiểm tra máy chủ.'},500)


def main():
    parser=argparse.ArgumentParser(description='VietSafe local demo')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--host',type=str,default='127.0.0.1')
    args=parser.parse_args()
    init_db()
    try: server=ThreadingHTTPServer((args.host,args.port),Handler)
    except OSError:
        print(f'Port {args.port} unavailable. Open http://127.0.0.1:{args.port} or use --port 8766.');raise SystemExit(1)
    print(f'VietSafe is running at http://127.0.0.1:{args.port}',flush=True)
    print('Local demo only. Press Ctrl+C to stop.',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
