"""Old Render/Windows commands must serve the modular app, not public/."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class LegacyEntrypointTests(unittest.TestCase):
    def test_cli_and_environment_start_the_modular_app(self):
        root = Path(__file__).resolve().parents[2]
        for use_cli in (True, False):
            with self.subTest(use_cli=use_cli), tempfile.TemporaryDirectory() as temp:
                with socket.socket() as listener:
                    listener.bind(('127.0.0.1', 0))
                    port = listener.getsockname()[1]
                env = dict(os.environ)
                env.update(
                    HOST='127.0.0.1', PORT=str(port), PYTHONUTF8='1',
                    VIETSAFE_DB=str(Path(temp) / 'test.sqlite3'),
                    VIETSAFE_FRONTEND_DIR=str(root / 'frontend'),
                    VIETSAFE_AI_RESEARCH_ROOT='',
                )
                args = [sys.executable, '-S', str(root / 'server.py')]
                if use_cli:
                    args += ['--host', '127.0.0.1', '--port', str(port)]
                base = f'http://127.0.0.1:{port}'
                process = subprocess.Popen(
                    args, cwd=temp, env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                )
                try:
                    deadline = time.monotonic() + 15
                    while True:
                        try:
                            with urllib.request.urlopen(base + '/api/health', timeout=1) as r:
                                self.assertTrue(json.load(r)['ok'])
                            break
                        except (OSError, urllib.error.URLError):
                            if process.poll() is not None or time.monotonic() > deadline:
                                self.fail('Legacy entry point did not start the HTTP server')
                            time.sleep(0.1)
                    with urllib.request.urlopen(base, timeout=3) as r:
                        page = r.read()
                    self.assertIn(b'/js/main.js', page)
                    self.assertIn(b'/forecast-lab.html', page)
                    self.assertIn(b'/flood-simulator.html', page)
                    for path in ('/forecast-lab.html', '/flood-simulator.html'):
                        with urllib.request.urlopen(base + path, timeout=3) as r:
                            self.assertEqual(r.status, 200)
                    with urllib.request.urlopen(base + '/api/ai/catalog', timeout=3) as r:
                        catalog = json.load(r)
                    self.assertTrue(all(t['status'] == 'not_configured' for t in catalog['tasks']))
                    with urllib.request.urlopen(base + '/api/flood-simulation/catalog', timeout=3) as r:
                        self.assertTrue(json.load(r)['synthetic'])
                    self.assertTrue((Path(temp) / 'test.sqlite3').exists())
                finally:
                    process.terminate()
                    try:
                        _, errors = process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        _, errors = process.communicate()
                    if process.returncode not in (0, 1, -15, 15):
                        print(errors.decode(errors='replace'))
