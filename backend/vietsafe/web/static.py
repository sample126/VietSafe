"""Safely serve the offline frontend; never expose backend, data or secrets."""
import mimetypes
from pathlib import Path
from urllib.parse import unquote
from ..config import PUBLIC
from .router import Response

def serve_static(path):
    public=Path(PUBLIC).resolve()
    try:
        target=(public / unquote(path).lstrip('/')).resolve() if path!='/' else public/'index.html'
        if not target.is_relative_to(public) or not target.is_file():
            return Response({'error':'Không tìm thấy tài nguyên.'},404)
        media=mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        if target.suffix in ('.js','.mjs'):
            media='application/javascript; charset=utf-8'
        elif target.suffix=='.json':
            media='application/json; charset=utf-8'
        elif target.suffix=='.css':
            media='text/css; charset=utf-8'
        return Response(target.read_bytes(),content_type=media)
    except (OSError,ValueError):
        return Response({'error':'Không tìm thấy tài nguyên.'},404)
