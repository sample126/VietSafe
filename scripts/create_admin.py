"""Interactive admin setup; password is never written into source files or echoed."""
import getpass
import hmac
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from vietsafe import db
from vietsafe.auth import hash_password


def create_admin(username='admin'):
    db.init_db()
    with db.connect() as connection:
        row = connection.execute('SELECT role FROM users WHERE username=?', (username,)).fetchone()
    if row:
        print('Tài khoản admin đã tồn tại. Không thay đổi mật khẩu hoặc quyền hiện tại.')
        return 1
    password = getpass.getpass('Đặt mật khẩu quản trị (từ 12 ký tự): ')
    confirmation = getpass.getpass('Nhập lại mật khẩu: ')
    if len(password) < 12 or not hmac.compare_digest(password, confirmation):
        print('Mật khẩu phải có ít nhất 12 ký tự và trùng khớp.')
        return 2
    with db.connect() as connection:
        connection.execute('INSERT INTO users VALUES (?,?,?,?)',
                           (username, hash_password(password), 'Quản trị viên', 'admin'))
    print('Đã tạo tài khoản admin trong cơ sở dữ liệu SQLite. Không ghi mật khẩu ra .env.')
    return 0

if __name__ == '__main__':
    raise SystemExit(create_admin())
