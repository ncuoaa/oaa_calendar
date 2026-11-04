"""Local-only account setup UI; this port is never exposed by the public tunnel."""

import json
import secrets
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from access_auth import hash_password

NONCE = secrets.token_urlsafe(24)
FORM = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>設定查詢帳密</title>
<style>body{font:17px/1.7 system-ui;background:#f6f7f3;margin:40px auto;max-width:500px;padding:24px}input,button{display:block;width:100%;box-sizing:border-box;padding:12px;margin:8px 0 18px;border:1px solid #aaa;border-radius:8px}button{background:#276b51;color:white}</style>
<h1>設定查詢帳號密碼</h1><p>僅在這台電腦設定。這組帳密供網站登入使用。</p>
<form method="post"><label>登入帳號<input name="username" value="oaa" required maxlength="100" autocomplete="username"></label>
<label>登入密碼（至少 12 個字元）<input type="password" name="password" required minlength="12" maxlength="256" autocomplete="new-password"></label>
<label>再次輸入密碼<input type="password" name="confirm" required autocomplete="new-password"></label><button>儲存帳密</button></form></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, content):
        payload = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path != '/' + NONCE:
            return self.respond(404, 'Not found')
        self.respond(200, FORM)

    def do_POST(self):
        if self.path != '/' + NONCE or self.headers.get('Origin') != f'http://127.0.0.1:{self.server.server_port}':
            return self.respond(403, 'Forbidden')
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0 or length > 4096:
            return self.respond(400, 'Invalid request')
        values = parse_qs(self.rfile.read(length).decode('utf-8'))
        username = values.get('username', [''])[0].strip()
        password = values.get('password', [''])[0]
        if not username or len(username) > 100 or not 12 <= len(password) <= 256 or password != values.get('confirm', [''])[0]:
            return self.respond(400, '帳號或密碼格式錯誤，請返回上一頁重試。')
        encrypted = json.dumps({'WEB_USERNAME':username, 'WEB_PASSWORD_HASH':hash_password(password)})
        Path('.local').mkdir(exist_ok=True)
        command = "$value=[Console]::In.ReadToEnd(); ConvertTo-SecureString -String $value -AsPlainText -Force | Export-Clixml -LiteralPath '.local/web-access.xml'"
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command], input=encrypted, text=True, capture_output=True)
        if result.returncode:
            return self.respond(500, '儲存失敗，請通知管理者。')
        self.respond(200, '帳密已加密儲存。可以關閉此頁，並回到對話告知「設定完成」。')
        print('Website account saved with Windows encryption.', flush=True)
        threading.Thread(target=self.server.shutdown, daemon=True).start()


if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/{NONCE}'
    Path('.local').mkdir(exist_ok=True)
    Path('.local/access-setup-url.txt').write_text(url, encoding='utf-8')
    print('Local account setup is ready.', flush=True)
    server.serve_forever()
    server.server_close()
    Path('.local/access-setup-url.txt').unlink(missing_ok=True)
