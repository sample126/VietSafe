"""VietSafe server entrypoint (python backend/run.py)."""
import argparse
import os
from .db import init_db
from .web.server import Handler, ThreadingHTTPServer

def main(argv=None):
    parser=argparse.ArgumentParser(description='VietSafe local map server')
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8765')))
    parser.add_argument('--host',default=os.environ.get('HOST','127.0.0.1'))
    args=parser.parse_args(argv)
    init_db()
    try:
        server=ThreadingHTTPServer((args.host,args.port),Handler)
    except OSError:
        parser.exit(1,f'Port {args.port} unavailable. Try --port 8766.\n')
    print(f'VietSafe is running at http://{args.host}:{args.port}',flush=True)
    print('Local demo only. Press Ctrl+C to stop.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__=='__main__':
    main()
