"""Restricted administrative routes, exports and verified observations."""
import csv
import io
import json
from ...core.engine import SCENARIOS, MODEL_VERSION
from ...db import connect
from ...reports import review_report, get_reports, get_flood_observations, add_flood_observation
from ..router import route, Response

@route('GET','/api/flood/observations')
def observations(req):
    return Response(get_flood_observations())

@route('POST','/api/flood/observations',role='admin')
def add_observation(req):
    return Response(add_flood_observation(req.body),201)

@route('POST','/api/scenario',role='admin')
def change_scenario(req):
    value=req.body.get('scenario')
    if value not in SCENARIOS:
        raise ValueError('Kịch bản không hợp lệ.')
    with connect() as db:
        db.execute("UPDATE settings SET value=? WHERE key='scenario'",(value,))
    return Response({'scenario':value})

@route('POST','/api/reports/<rid>',role='admin')
def review(req,rid):
    return Response(review_report(rid,req.body.get('status')))

@route('GET','/api/export/predictions',role='admin')
def export_predictions(req):
    with connect() as db:
        rows=[dict(row) for row in db.execute('SELECT * FROM prediction_logs ORDER BY tick DESC LIMIT 500')]
    return Response({'mode':'demo','model_version':MODEL_VERSION,'logs':rows},headers={'Content-Disposition':'attachment; filename="vietsafe-predictions.json"'})

@route('GET','/api/export/reports',role='admin')
def export_reports(req):
    stream=io.StringIO()
    fields=['id','road_id','type','severity','address','description','status','created_at']
    writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
    for report in get_reports():
        writer.writerow({key:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v
                         for key,v in report.items()})
    return Response(('\ufeff'+stream.getvalue()).encode('utf-8'),content_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':'attachment; filename="vietsafe-reports.csv"'})
