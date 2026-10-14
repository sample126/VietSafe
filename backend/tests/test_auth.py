"""Auth regression without externally connected server or built-in passwords."""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'backend'))
from vietsafe import auth, db

class AuthTests(unittest.TestCase):
    def test_session_lifecycle(self):
        with TemporaryDirectory() as directory:
            old=db.DB_PATH
            try:
                db.DB_PATH=Path(directory)/'accounts.sqlite3'
                db.init_db()
                with db.connect() as conn:
                    conn.execute('INSERT INTO users VALUES(?,?,?,?)',('citizen',auth.hash_password('password'),'Citizen','citizen'))
                token=auth.create_session('citizen')
                self.assertEqual(auth.get_user_by_session(token)['role'],'citizen')
                self.assertIsNone(auth.get_user_by_session('invalid'))
            finally:
                db.DB_PATH=old

if __name__=='__main__': unittest.main()
