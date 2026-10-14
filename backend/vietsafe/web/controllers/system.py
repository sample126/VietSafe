"""System, search, weather, traffic and public data endpoints."""
import os
from ...service import demo_events, normalize
from ...core.network import NODES, ROADS, road_midpoint
from ...providers.openmeteo_weather import WeatherUnavailable, get_rain_forecast
from ...providers.nasa_gpm import GpmUnavailable, get_latest_rainfall, h5py, np
from ...providers.tomtom_traffic import (
    TomTomUnavailable, TomTomPermissionDenied, RoadNameUnavailable,
    get_flow_tile, get_flow_segment, get_road_name, get_osm_road_name,
)
from ..router import route, Response

@route('GET','/api/health')
def health(req):
    return Response({'ok':True,'mode':'live-only','forecast_available':False})

@route('GET','/api/live-status')
def live_status(req):
    return Response({
        'mode':'live-only',
        'traffic':{'provider':'TomTom Traffic Flow','configured':bool(os.environ.get('TOMTOM_API_KEY','').strip())},
        'weather_forecast':{'provider':'Open-Meteo','configured':True,'kind':'forecast'},
        'flood_observations':{'source':'verified_import_or_station','connected':False},
        'rainfall':{'provider':'NASA GPM IMERG','configured':bool(os.environ.get('NASA_EARTHDATA_TOKEN','').strip()),
                    'hdf5_reader_installed': h5py is not None and np is not None},
        'traffic_forecast_model':False,'gemini':False,
        'image_recognition_model':False,'transport_classifier':False,
    })

@route('GET','/api/snapshot')
def snapshot_disabled(req):
    return Response({'error':'Mô phỏng đã tắt trong chế độ dữ liệu thực.','mode':'live-only'},409)

@route('GET','/api/routes')
def routes_disabled(req):
    return Response({'error':'Định tuyến mô phỏng đã tắt; chưa có bộ định tuyến thực.'},501)

@route('GET','/api/demo/events')
def demo(req):
    return Response(demo_events())

@route('GET','/api/search')
def search(req):
    term=normalize(req.query.get('q',[''])[0])[:150]
    matches=[dict(n,kind='node') for n in NODES.values() if term in normalize(n['name'])]
    matches += [dict(id=r['id'],name=r['name'],lat=road_midpoint(r['coordinates'])[0],
                 lng=road_midpoint(r['coordinates'])[1],kind='road') for r in ROADS if term in normalize(r['name'])]
    return Response({'results':matches[:12]})

@route('GET','/api/weather/forecast')
def weather(req):
    try:
        lat=float(req.query.get('lat',['21.0285'])[0]);lng=float(req.query.get('lng',['105.8542'])[0])
        hours=int(req.query.get('hours',['24'])[0])
        return Response(get_rain_forecast(lat,lng,hours))
    except WeatherUnavailable as error:
        return Response({'error':str(error),'source':'Open-Meteo'},503)

@route('GET','/api/gpm/rainfall')
def gpm(req):
    try:
        return Response(get_latest_rainfall(force=req.query.get('refresh',['0'])[0]=='1'))
    except GpmUnavailable as error:
        return Response({'error':str(error),'source':'NASA GPM IMERG Early Run V07'},503)

@route('GET','/api/tomtom/flow/<zoom>/<x>/<file>')
def flow_tile(req,zoom,x,file):
    try:
        if not file.endswith('.png'):
            return Response({'error':'Đường dẫn ô giao thông TomTom không hợp lệ.'},400)
        zoom=int(zoom);x=int(x);y=int(file[:-4])
        if not 0<=zoom<=22 or not 0<=x<(1<<zoom) or not 0<=y<(1<<zoom):
            return Response({'error':'Tọa độ ô bản đồ TomTom nằm ngoài phạm vi.'},400)
        return Response(get_flow_tile(zoom,x,y),content_type='image/png',headers={'Cache-Control':'public, max-age=180'})
    except ValueError:
        return Response({'error':'Tọa độ ô bản đồ TomTom không hợp lệ.'},400)
    except TomTomUnavailable as error:
        return Response({'error':str(error),'source':'TomTom Traffic Flow Tiles API v4'},502)

@route('GET','/api/tomtom/segment')
def flow_segment(req):
    try:
        latitude=float(req.query.get('lat',[''])[0]);longitude=float(req.query.get('lng',[''])[0])
        zoom=int(req.query.get('zoom',['15'])[0])
        segment=dict(get_flow_segment(latitude,longitude,zoom))
        try:
            street_name=get_road_name(latitude,longitude)
            if street_name:
                segment['street_name']=street_name;segment['street_name_source']='TomTom'
            else:
                try:
                    street_name=get_osm_road_name(latitude,longitude)
                    if street_name:
                        segment['street_name']=street_name;segment['street_name_source']='OpenStreetMap'
                    else:
                        segment['street_name_error']='Không tìm thấy tên đường từ TomTom hoặc OpenStreetMap.'
                except RoadNameUnavailable as error:
                    segment['street_name_error']=str(error)
        except TomTomPermissionDenied as error:
            try:
                street_name=get_osm_road_name(latitude,longitude)
                if street_name:
                    segment['street_name']=street_name;segment['street_name_source']='OpenStreetMap'
                else:
                    segment['street_name_error']='TomTom từ chối API key và OpenStreetMap không tìm thấy tên đường.'
            except RoadNameUnavailable as fallback_error:
                segment['street_name_error']=f'{error} OpenStreetMap dự phòng: {fallback_error}'
        except TomTomUnavailable as error:
            segment['street_name_error']=str(error)
        return Response(segment)
    except (ValueError,TypeError):
        return Response({'error':'Cần lat/lng dạng số và zoom hợp lệ.'},400)
    except TomTomUnavailable as error:
        return Response({'error':str(error),'source':'TomTom Traffic Flow Segment Data API v4'},502)
