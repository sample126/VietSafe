"""HTTP transport, Host/Origin enforcement, safe headers and static frontend."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import traceback
from urllib.parse import urlparse, parse_qs
from ..config import MAX_BODY
from .router import Request, Response, dispatch
from .static import serve_static

class Handler(BaseHTTPRequestHandler):
    server_version='VietSafeLocal/2.0'

    def log_message(self,fmt,*args):
        if args and str(args[0]).startswith('GET /api/snapshot'):
            return
        super().log_message(fmt,*args)

    def valid_host(self):
        host=self.headers.get('Host','').lower().strip()
        if not host or any(c in host for c in ('/','@','\\',' ', '\t', '\n', '\r')):
            return False
        if host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
            return True
        domain=host.split(':')[0]
        allow_suffixes=('.trycloudflare.com','.loca.lt','.ngrok.io','.ngrok-free.app','.onrender.com')
        allowed_custom={x.strip().lower() for x in os.environ.get('VIETSAFE_ALLOWED_HOSTS','').split(',') if x.strip()}
        return domain in allowed_custom or any(domain.endswith(suffix) for suffix in allow_suffixes)

    def respond(self, response):
        data=response.data
        if isinstance(data,(bytes,bytearray)):
            payload=bytes(data)
        elif response.content_type.startswith('application/json'):
            payload=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        else:
            payload=data.encode('utf-8') if isinstance(data,str) else data
        self.send_response(response.status)
        self.send_header('Content-Type',response.content_type)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control',response.headers.get('Cache-Control','no-store' if self.path.startswith('/api/') else 'no-cache'))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tiles.stadiamaps.com https://*.tile.openstreetmap.org https://tile.openstreetmap.de https://*.tile.openstreetmap.fr; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        for name,value in response.headers.items():
            if name.lower()!='cache-control':
                self.send_header(name,value)
        self.end_headers()
        if self.command!='HEAD':
            try:
                self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError):
                pass

    def serve(self):
        if not self.valid_host():
            return self.respond(Response({'error':'Local access only.'},403))
        parsed=urlparse(self.path)
        if self.command=='POST':
            host=self.headers.get('Host','')
            origin=self.headers.get('Origin')
            allowed={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}',f'http://{host}',f'https://{host}'}
            if (origin and origin not in allowed) or self.headers.get('X-VietSafe')!='local':
                return self.respond(Response({'error':'Yêu cầu phải được gửi từ website hợp lệ.'},403))
        try:
            body=None
            if self.command=='POST':
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>MAX_BODY:
                    return self.respond(Response({'error':'Nội dung quá lớn hoặc trống.'},413))
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict):
                    raise ValueError('JSON phải là một đối tượng.')
            if parsed.path.startswith('/api/'):
                request=Request(method='GET' if self.command=='HEAD' else self.command,
                                path=parsed.path,query=parse_qs(parsed.query),
                                headers=self.headers,body=body,client_ip=self.client_address[0])
                return self.respond(dispatch(request))
            if self.command not in ('GET','HEAD'):
                return self.respond(Response({'error':'API không tồn tại.'},404))
            return self.respond(serve_static(parsed.path))
        except (ValueError,TypeError,KeyError,UnicodeDecodeError) as error:
            return self.respond(Response({'error':str(error)},400))
        except Exception:
            traceback.print_exc()
            return self.respond(Response({'error':'Lỗi xử lý dữ liệu tại máy. Kiểm tra cửa sổ máy chủ.'},500))

    def do_GET(self):
        return self.serve()
    def do_HEAD(self):
        return self.serve()
    def do_POST(self):
        return self.serve()

__all__=['Handler','ThreadingHTTPServer']
