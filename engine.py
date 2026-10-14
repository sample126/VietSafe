"""Explainable demonstration baseline, not trained T-GCN or calibrated probability."""
import heapq
import math
import time
from network import ROADS, NODES

MODEL_VERSION = 'spatial-rule-demo-1.0'
SCENARIOS = {'normal': ('Trời khô', 0), 'rain': ('Mưa lớn', 28), 'storm': ('Mưa rất lớn', 55)}


def clamp(x, low=0, high=100):
    return max(low, min(high, x))


def forecast(road, current, neighbor_speed, rain, horizon):
    h = horizon / 60
    if not current['known']:
        return dict(horizon=horizon, flood_risk=None, speed=None, risk=None, label='Chưa đủ dữ liệu')
    # Rainfall, susceptibility, current flood, spatial neighbor congestion and time horizon.
    flood = clamp(current['flood_risk'] + h*(rain*road['susceptibility']*.8 - (9 if rain == 0 else 0)))
    speed = max(3, current['speed']*(1-.22*h) + .12*h*(neighbor_speed-current['speed'])
                - rain*.08*h - (4*h if current['incident'] else 0))
    if rain == 0:
        speed = min(road['free_speed'], current['speed']+h*4)
    congestion = clamp((1-speed/road['free_speed'])*100)
    risk = round(max(flood, congestion*.85, 72 if current['incident'] else 0))
    return dict(horizon=horizon, flood_risk=round(flood), speed=round(speed, 1), risk=risk,
                label='Cao' if risk >= 65 else 'Trung bình' if risk >= 35 else 'Thấp')


def build_snapshot(scenario='rain', reports=(), now=None):
    now = time.time() if now is None else now
    tick = int(now//10)
    rain = SCENARIOS[scenario][1]
    states = []
    for i, road in enumerate(ROADS):
        seed = road['seed_event']
        wave = math.sin(tick*.17+i)*2
        flooded = seed == 'flood' and rain > 0
        depth = round(max(0, (13 if scenario == 'rain' else 31) + road['susceptibility']*9 + wave), 1) if flooded else 0
        severity = 3 if depth >= 30 else 2 if depth >= 15 or seed in ('traffic','incident') else 1
        incident = seed == 'incident'
        speed = max(4, road['free_speed']-(19 if seed == 'traffic' else 5)-rain*.13+wave)
        if flooded:
            speed = max(3, speed-depth*.37)
        state = dict(road, known=seed != 'unknown', speed=round(speed, 1), depth=depth,
                     flood_risk=round(clamp(depth*2.2 + rain*road['susceptibility']*.45)),
                     incident=incident, blocked=depth>=30, severity=severity,
                     event_type='flood' if flooded else seed if seed in ('traffic', 'incident') else None,
                     updated_at=tick*10, sources=['Bộ mô phỏng tại máy'], evidence=['Quan sát tạo bởi kịch bản '+SCENARIOS[scenario][0]],
                     origin='demo', report_id=None)
        # Pending reports NEVER change road status or route costs.
        for report in sorted(reports, key=lambda r: r['created_at']):
            if report['road_id'] != road['id'] or report['status'] != 'verified' or report['expires_at'] <= now:
                continue
            state.update(known=True, event_type=report['type'], severity=report['severity'],
                         updated_at=report['created_at'], origin='local_report', report_id=report['id'])
            state['sources'] = ['Phản ánh tại máy • đã xác minh thủ công']
            state['evidence'] = [report['description']]
            if report['type'] == 'flood':
                state.update(flood_risk=max(state['flood_risk'], report['severity']*28), blocked=state['blocked'] or report['severity']==3)
            elif report['type'] == 'incident':
                state.update(incident=True, blocked=state['blocked'] or report['severity']==3)
            elif report['type'] == 'traffic':
                state['speed'] = min(state['speed'], 22-report['severity']*5)
        states.append(state)
    for state in states:
        neighbors = [s['speed'] for s in states if s['id'] != state['id'] and s['known'] and
                     {s['a'], s['b']} & {state['a'], state['b']}]
        state['forecast'] = [forecast(state, state, sum(neighbors)/len(neighbors) if neighbors else state['speed'], rain, h)
                             for h in (0, 15, 30, 45, 60)]
        state['risk'] = state['forecast'][0]['risk']
    events = []
    for s in states:
        if s['event_type'] and s['known']:
            events.append(dict(id=s['report_id'] or 'demo-'+s['id'], road_id=s['id'], name=s['name'],
                               type=s['event_type'], severity=s['severity'],
                               lat=sum(c[0] for c in s['coordinates'])/2, lng=sum(c[1] for c in s['coordinates'])/2,
                               depth=s['depth'] if s['origin']=='demo' else None, speed=s['speed'],
                               updated_at=s['updated_at'], sources=s['sources'], evidence=s['evidence'],
                               origin=s['origin'], status='verified', blocked=s['blocked']))
    for r in reports:
        if r['status']=='pending' and r['expires_at']>now:
            events.append(dict(id=r['id'], road_id=r['road_id'], name=r['address'], type=r['type'],
                               severity=r['severity'], lat=r['lat'], lng=r['lng'], updated_at=r['created_at'],
                               sources=['Phản ánh tại máy'], evidence=[r['description']], origin='local_report', status='pending', blocked=False))
    events.sort(key=lambda e: (e['status']=='pending', -e['severity'], -e['updated_at']))
    return dict(generated_at=now, mode='demo', scenario=scenario, model_version=MODEL_VERSION,
                rainfall=rain, temperature=27 if rain else 31, roads=states, events=events,
                nodes=list(NODES.values()), counts={t:sum(e['type']==t and e['status']=='verified' for e in events)
                                                   for t in ('flood','traffic','incident')},
                pending=sum(r['status']=='pending' and r['expires_at']>now for r in reports),
                source_notice='Chưa kết nối VOV, camera hoặc cơ quan khí tượng/thoát nước.',
                forecast_notice='Điểm nguy cơ theo quy tắc minh họa; không phải xác suất hoặc kết quả AI đã huấn luyện.')


def calculate_routes(snapshot, origin, destination, horizon=0, vehicle='motorbike'):
    if origin not in NODES or destination not in NODES:
        raise ValueError('Hãy chọn điểm đi và đến trong khu vực thử nghiệm.')
    if origin == destination:
        raise ValueError('Điểm đi và điểm đến phải khác nhau.')
    if horizon not in (0, 30, 60) or vehicle not in ('motorbike', 'car'):
        raise ValueError('Thời điểm hoặc phương tiện không hợp lệ.')
    roads = {s['id']:s for s in snapshot['roads']}
    graph = {n:[] for n in NODES}
    for r in roads.values():
        # Unknown and confirmed blocked edges are never offered as traversable.
        if r['blocked'] or not r['known']:
            continue
        graph[r['a']].append((r['b'],r['id']))
        graph[r['b']].append((r['a'],r['id']))

    def solve(policy):
        queue=[(0, 0, origin, [], [origin])]
        best={origin:0}
        while queue:
            cost, elapsed, node, edgepath, nodepath=heapq.heappop(queue)
            if cost>best[node]+1e-9:
                continue
            if node==destination:
                return edgepath,nodepath,elapsed
            for nxt,rid in graph[node]:
                r=roads[rid]
                # Use forecast for estimated edge arrival, conservatively rounded upward.
                at=min(60, horizon+elapsed)
                f=next((f for f in r['forecast'] if f['horizon']>=at),r['forecast'][-1])
                if f['flood_risk'] >= (82 if vehicle=='motorbike' else 88):
                    continue
                minutes=r['length_km']/max(3,f['speed'])*60
                penalty=(f['risk']/100)**2 * r['length_km'] * (20 if policy=='cautious' else 1)
                new=cost+minutes+penalty
                if new<best.get(nxt,float('inf')):
                    best[nxt]=new
                    heapq.heappush(queue,(new,elapsed+minutes,nxt,edgepath+[rid],nodepath+[nxt]))
        return None
    result=[]
    for policy in ('cautious','fast'):
        solved=solve(policy)
        if not solved:
            continue
        ids,nodes,elapsed=solved
        if any(r['road_ids']==ids for r in result):
            continue
        traversed=[roads[i] for i in ids]
        result.append(dict(id=policy,title='Ưu tiên ít rủi ro' if policy=='cautious' else 'Ưu tiên thời gian',
                           road_ids=ids, coordinates=[[NODES[n]['lat'],NODES[n]['lng']] for n in nodes],
                           distance_km=round(sum(r['length_km'] for r in traversed),1), eta_minutes=round(elapsed,1),
                           max_risk=max(r['forecast'][horizon//15]['risk'] for r in traversed),
                           steps=[r['name'] for r in traversed],
                           warnings=[r['name'] for r in traversed if r['event_type']]))
    return dict(routes=result, calculated_at=snapshot['generated_at'],
                excluded=sum(r['blocked'] or not r['known'] for r in roads.values()),
                message='Mạng đường giản lược và dữ liệu thử nghiệm; không dùng để dẫn đường thực tế.' if result else
                'Không tìm được tuyến đáp ứng điều kiện trên mạng thử nghiệm. Hãy đổi điểm hoặc thời điểm.')
