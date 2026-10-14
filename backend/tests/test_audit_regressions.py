"""Regression tests for migration omissions identified in audit."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from vietsafe import db, auth
from vietsafe.providers import nasa_gpm
from vietsafe.web.static import serve_static
from vietsafe.web.router import Request, dispatch
from vietsafe.web.controllers import system

class AuditRegressions(unittest.TestCase):
    def test_missing_hdf5_fails_before_nasa_network(self):
        with patch.object(nasa_gpm,'h5py',None),patch.object(nasa_gpm,'np',None), \
             patch.dict('os.environ', {'NASA_EARTHDATA_TOKEN':'example-for-local-test'}), \
             patch.object(nasa_gpm,'_latest_granule') as fetch:
            with self.assertRaisesRegex(nasa_gpm.GpmUnavailable,'h5py/numpy'):
                nasa_gpm.get_latest_rainfall(force=True)
            fetch.assert_not_called()

    def test_live_status_discloses_local_reader_readiness(self):
        req=Request('GET','/api/live-status',{}, {},None,'127.0.0.1')
        data=dispatch(req).data
        self.assertIn('hdf5_reader_installed',data['rainfall'])

    def test_static_root_serves_site_but_not_env(self):
        self.assertEqual(serve_static('/').status,200)
        self.assertEqual(serve_static('/.env').status,404)
        self.assertEqual(serve_static('/%2e%2e/.env').status,404)

    def test_password_hashes_salted_and_legacy_compatible(self):
        import hashlib
        one=auth.hash_password('secure-password')
        two=auth.hash_password('secure-password')
        self.assertNotEqual(one,two)
        self.assertTrue(auth.verify_password('secure-password',one))
        self.assertFalse(auth.verify_password('wrong-password',one))
        self.assertTrue(auth.verify_password('old-password',hashlib.sha256(b'old-password').hexdigest()))

    def test_legacy_login_transparently_upgrades_password_hash(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            old=db.DB_PATH
            try:
                db.DB_PATH=Path(folder)/'upgrade.sqlite3'
                db.init_db()
                legacy=hashlib.sha256(b'legacy-password').hexdigest()
                with db.connect() as connection:
                    connection.execute('INSERT INTO users VALUES (?,?,?,?)',
                                       ('legacy',legacy,'Legacy User','citizen'))
                req=Request('POST','/api/auth/login',{}, {},
                            {'username':'legacy','password':'legacy-password'},'127.0.0.1')
                result=dispatch(req)
                self.assertEqual(result.status,200)
                self.assertIn('token',result.data)
                with db.connect() as connection:
                    row=connection.execute('SELECT password_hash FROM users WHERE username=?',('legacy',)).fetchone()
                self.assertTrue(row['password_hash'].startswith('pbkdf2_sha256$'))
                self.assertTrue(auth.verify_password('legacy-password',row['password_hash']))
            finally:
                db.DB_PATH=old

    def test_admin_setup_with_password_in_isolated_database(self):
        with tempfile.TemporaryDirectory() as folder:
            old=db.DB_PATH
            try:
                db.DB_PATH=Path(folder)/'test.sqlite3'
                import scripts.create_admin as admin_script
                with patch('getpass.getpass',side_effect=['very-long-test-password','very-long-test-password']):
                    self.assertEqual(admin_script.create_admin(),0)
                with db.connect() as connection:
                    row=connection.execute('SELECT password_hash,role FROM users WHERE username=?',('admin',)).fetchone()
                self.assertEqual(row['role'],'admin')
                self.assertTrue(auth.verify_password('very-long-test-password',row['password_hash']))
                self.assertFalse(auth.verify_password('not-correct',row['password_hash']))
                self.assertTrue(row['password_hash'].startswith('pbkdf2_sha256$'))
                self.assertEqual(admin_script.create_admin(),1)
            finally:
                db.DB_PATH=old

if __name__=='__main__':unittest.main()
