"""Community report read/write endpoints."""
from ...db import connect
from ...reports import get_reports, create_report
from ..router import route, Response
from ..ratelimit import reports_limiter

@route('GET','/api/reports')
def list_reports(req):
    return Response({'reports':get_reports()})

@route('GET','/api/report-media/<rid>')
def report_media(req,rid):
    with connect() as db:
        row=db.execute('SELECT media,media_type FROM reports WHERE id=?',(rid,)).fetchone()
    if not row or not row['media']:
        return Response({'error':'Không có ảnh.'},404)
    return Response(row['media'],content_type=row['media_type'])

@route('POST','/api/reports',role='citizen')
def submit_report(req):
    if not reports_limiter.allow(req.client_ip):
        return Response({'error':'Bạn đã gửi nhiều phản ánh. Vui lòng chờ một phút.'},429)
    return Response(create_report(req.body),201)
