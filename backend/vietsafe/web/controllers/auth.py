"""Authentication endpoints."""
import sqlite3
from ...auth import hash_password, verify_password, create_session, get_user_by_session
from ...db import connect
from ..router import route, Response

@route('GET','/api/auth/me')
def me(req):
    return Response({'user':get_user_by_session(req.headers.get('X-VietSafe-Session'))})

@route('POST','/api/auth/login')
def login(req):
    body=req.body
    uname=body.get('username','');pwd=body.get('password','')
    if not isinstance(uname,str) or not isinstance(pwd,str) or not uname.strip() or not pwd:
        raise ValueError('Vui lòng nhập tên đăng nhập và mật khẩu.')
    uname=uname.strip()
    with connect() as db:
        row=db.execute('SELECT username, display_name, role, password_hash FROM users WHERE username=?',(uname,)).fetchone()
    if not row or not verify_password(pwd,row['password_hash']):
        return Response({'error':'Sai tên đăng nhập hoặc mật khẩu.'},401)
    if not row['password_hash'].startswith('pbkdf2_sha256$'):
        with connect() as db:
            db.execute('UPDATE users SET password_hash=? WHERE username=?',
                       (hash_password(pwd),uname))
    user={'username':row['username'],'display_name':row['display_name'],'role':row['role']}
    return Response({'user':user,'token':create_session(uname)})

@route('POST','/api/auth/register')
def register(req):
    body=req.body
    uname=body.get('username','');pwd=body.get('password','');display=body.get('display_name','')
    if not isinstance(uname,str) or not 3<=len(uname.strip())<=30:
        raise ValueError('Tên đăng nhập cần từ 3 đến 30 ký tự.')
    if not isinstance(pwd,str) or len(pwd)<6:
        raise ValueError('Mật khẩu cần ít nhất 6 ký tự.')
    if not isinstance(display,str) or not 1<=len(display.strip())<=50:
        raise ValueError('Tên hiển thị cần từ 1 đến 50 ký tự.')
    uname=uname.strip();display=display.strip()
    try:
        with connect() as db:
            db.execute('INSERT INTO users VALUES(?,?,?,?)',(uname,hash_password(pwd),display,'citizen'))
    except sqlite3.IntegrityError:
        raise ValueError('Tên đăng nhập đã tồn tại.')
    user={'username':uname,'display_name':display,'role':'citizen'}
    return Response({'user':user,'token':create_session(uname)})

@route('POST','/api/auth/logout')
def logout(req):
    token=req.headers.get('X-VietSafe-Session')
    if token:
        with connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?',(token,))
    return Response({'ok':True})
