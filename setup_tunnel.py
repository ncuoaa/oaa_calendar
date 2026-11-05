"""Local-only ngrok token and fixed-domain setup. No credentials in Git history."""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
from http.server import HTTPServer
from urllib.parse import parse_qs, urlparse

from setup_access import Handler as ResponseHandler

ROOT = Path(__file__).resolve().parent
NONCE = secrets.token_urlsafe(24)
FORM = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>設定固定 API 網址</title>
<style>body{font:17px/1.7 system-ui;background:#f6f7f3;margin:30px auto;max-width:580px;padding:24px}input,button{display:block;width:100%;box-sizing:border-box;padding:12px;margin:8px 0 18px;border:1px solid #aaa;border-radius:8px}button{background:#276b51;color:white}small{display:block}</style>
<h1>設定固定 API 網址</h1><p>從自己的 ngrok 帳號取得以下兩個設定。授權權杖只會加密儲存在這台電腦。</p>
<form method="post"><label>固定開發網域網址（含 https://）<input name="origin" type="url" placeholder="https://你的固定網域.ngrok-free.dev" required autocomplete="off"></label>
<small>ngrok 控制台 → Gateway → Domains</small><label>ngrok Authtoken<input name="token" type="password" required minlength="20" maxlength="256" autocomplete="off"></label>
<small>ngrok 控制台 → Your Authtoken。請勿貼在對話或 GitHub 程式碼中。</small><button>加密儲存並切換固定網址</button></form></html>'''


class Handler(ResponseHandler):
    def do_GET(self):
        if self.path != '/' + NONCE:
            return self.respond(404, 'Not found')
        self.respond(200, FORM)

    def do_POST(self):
        if self.path != '/' + NONCE or self.headers.get('Origin') != f'http://127.0.0.1:{self.server.server_port}':
            return self.respond(403, 'Forbidden')
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 4096:
            return self.respond(400, 'Invalid request')
        fields = parse_qs(self.rfile.read(length).decode())
        origin = fields.get('origin', [''])[0].strip().rstrip('/')
        token = fields.get('token', [''])[0].strip()
        if not re.fullmatch(r'https://[a-z0-9-]+\.ngrok-free\.(dev|app)', origin) or not 20 <= len(token) <= 256 or any(c.isspace() for c in token):
            return self.respond(400, '網址或權杖格式錯誤，請返回上一頁檢查。網址應以 https:// 開頭，且沒有額外路徑。')
        data = json.dumps({'API_ORIGIN':origin, 'NGROK_AUTHTOKEN':token})
        shell = shutil.which('pwsh') or shutil.which('powershell') or str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')
        command = "$value=[Console]::In.ReadToEnd(); ConvertTo-SecureString -String $value -AsPlainText -Force | Export-Clixml -LiteralPath '.local/ngrok-auth.xml'"
        try:
            result = subprocess.run([shell,'-NoProfile','-NonInteractive','-Command',command],input=data,text=True,capture_output=True,timeout=30)
        except (OSError,subprocess.SubprocessError):
            return self.respond(500, '本機加密儲存失敗，請通知管理者。')
        if result.returncode:
            return self.respond(500, '本機加密儲存失敗，請通知管理者。')
        self.respond(200, '固定網址設定已加密儲存。監控服務將自動切換，請回到對話告知「固定網址已設定」。')
        print('Fixed tunnel settings saved with Windows encryption.',flush=True)
        threading.Thread(target=self.server.shutdown,daemon=True).start()


if __name__ == '__main__':
    os.chdir(ROOT)
    (ROOT/'.local').mkdir(exist_ok=True)
    server = HTTPServer(('127.0.0.1',0),Handler)
    url = f'http://127.0.0.1:{server.server_port}/{NONCE}'
    path = ROOT/'.local/tunnel-setup-url.txt'
    path.write_text(url,encoding='utf-8')
    print('Local fixed-tunnel setup is ready.',flush=True)
    server.serve_forever()
    server.server_close()
    path.unlink(missing_ok=True)
