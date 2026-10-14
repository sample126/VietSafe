"""Application services join persistence and pure modeling."""
import json
import time
import unicodedata
from .db import connect
from .core.engine import build_snapshot, MODEL_VERSION
from .core.network import NODES, ROADS, road_midpoint
from .reports import get_reports

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


def demo_events():
    with connect() as db:
        scenario=db.execute("SELECT value FROM settings WHERE key='scenario'").fetchone()[0]
    result=build_snapshot(scenario, reports=[])
    return {
        'mode':'demo',
        'scenario':scenario,
        'generated_at':result['generated_at'],
        'notice':'Sự kiện mô phỏng chỉ để minh họa, không phải cảnh báo giao thông thực tế.',
        'events':[event for event in result['events'] if event['origin']=='demo'],
    }


def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFD',s.lower().replace('đ','d')) if unicodedata.category(c)!='Mn')
