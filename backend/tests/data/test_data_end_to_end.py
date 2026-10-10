import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from vietsafe.data_pipeline.audit import audit_artifacts,main
from vietsafe.data_pipeline.end_to_end import build_fixture_artifacts,run_fixture_pipeline


class DataEndToEndTests(unittest.TestCase):
    def test_all_stages_and_nonempty_dataset(self):
        artifacts=build_fixture_artifacts()
        self.assertEqual(len(artifacts['registry']),12)
        self.assertTrue(artifacts['alignment'].static)
        self.assertTrue(artifacts['feature_rows'])
        self.assertEqual(len(artifacts['dataset'].samples),1)
        result=run_fixture_pipeline().to_dict()
        self.assertEqual(result['errors'],0)
        self.assertGreater(result['warnings'],0)

    def test_repeated_runs_identical(self):
        a,b=run_fixture_pipeline(),run_fixture_pipeline()
        self.assertEqual(a.to_json(),b.to_json())
        for key in ('registry_checksum','alignment_checksum','feature_checksum','graph_checksum',
                    'dataset_checksum','split_checksum','quality_checksum'):
            self.assertEqual(a.to_dict()[key],b.to_dict()[key])

    def test_order_independence(self):
        self.assertEqual(run_fixture_pipeline().to_json(),run_fixture_pipeline(reverse_inputs=True).to_json())

    def test_no_network_no_writes(self):
        real_open=Path.open
        def read_only(path,mode='r',*args,**kwargs):
            if any(flag in mode for flag in ('w','a','x','+')):
                raise AssertionError('No writes')
            return real_open(path,mode,*args,**kwargs)
        with patch('socket.socket',side_effect=AssertionError('No network')), \
                patch('urllib.request.urlopen',side_effect=AssertionError('No HTTP')), \
                patch('vietsafe.data_pipeline.ingestion.osm.urlopen',side_effect=AssertionError('No Overpass')), \
                patch.object(Path,'open',read_only), \
                patch.object(Path,'mkdir',side_effect=AssertionError('No directories')):
            self.assertEqual(run_fixture_pipeline().to_dict()['errors'],0)

    def test_input_objects_not_mutated(self):
        artifacts=build_fixture_artifacts()
        def snapshot():
            return {key:[x.to_dict() for x in value] if isinstance(value,tuple) else value.to_dict()
                    for key,value in artifacts.items()}
        before=snapshot()
        audit_artifacts(**artifacts)
        self.assertEqual(before,snapshot())

    def test_import_safety_and_no_external_module_imports(self):
        script='''
import builtins, socket, urllib.request, pathlib
from unittest.mock import patch
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith(('vietsafe.core','vietsafe.web','torch','tensorflow','sklearn')):
        raise AssertionError('Forbidden module '+name)
    return original(name,*args,**kwargs)
with patch('socket.socket',side_effect=AssertionError('network')), patch('urllib.request.urlopen',side_effect=AssertionError('HTTP')), patch.object(pathlib.Path,'mkdir',side_effect=AssertionError('mkdir')), patch.object(pathlib.Path,'write_text',side_effect=AssertionError('write')), patch.object(pathlib.Path,'write_bytes',side_effect=AssertionError('write')), patch('builtins.__import__',side_effect=guarded):
    import vietsafe.data_pipeline.audit
    import vietsafe.data_pipeline.end_to_end
    assert vietsafe.data_pipeline.end_to_end.run_fixture_pipeline().to_dict()['errors'] == 0
'''
        run=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_cli_help_and_demo(self):
        run=subprocess.run([sys.executable,'-m','vietsafe.data_pipeline.audit','--help'],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            status=main(['--fixture-demo'])
        self.assertEqual(status,0)
        self.assertEqual(json.loads(stream.getvalue())['errors'],0)
