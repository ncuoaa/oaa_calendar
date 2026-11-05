"""Windows user-session supervisor for the calendar API and public tunnel."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / '.local'
LOCAL.mkdir(exist_ok=True)
logger = logging.getLogger('calendar-service')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOCAL / 'service.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
logger.addHandler(handler)
FLAGS = subprocess.CREATE_NO_WINDOW
SHELL = None
OWNED = {}


def remember_process(name, process):
    command = "$p=Get-Process -Id " + str(process.pid) + " -ErrorAction SilentlyContinue; if($p){ @{id=$p.Id;started=$p.StartTime.ToUniversalTime().Ticks;image=$p.Path} | ConvertTo-Json -Compress }"
    result = subprocess.run([SHELL, '-NoProfile', '-NonInteractive', '-Command', command], capture_output=True, text=True, timeout=15, creationflags=FLAGS)
    if result.returncode or not result.stdout.strip():
        return
    OWNED[name] = json.loads(result.stdout)
    temporary = LOCAL / 'owned-processes.tmp'
    temporary.write_text(json.dumps(list(OWNED.values())), encoding='utf-8')
    temporary.replace(LOCAL / 'owned-processes.json')


def clean_previous_processes():
    if not (LOCAL / 'owned-processes.json').exists():
        return
    # Compare both executable and process creation time to avoid PID-reuse mistakes.
    command = "$items=Get-Content -LiteralPath '.local/owned-processes.json' -Raw | ConvertFrom-Json; foreach($item in $items){$p=Get-Process -Id $item.id -ErrorAction SilentlyContinue; if($p -and $p.Path -eq $item.image -and $p.StartTime.ToUniversalTime().Ticks -eq $item.started){ & (Join-Path $env:SystemRoot 'System32/taskkill.exe') /PID $p.Id /T /F | Out-Null }}"
    subprocess.run([SHELL, '-NoProfile', '-NonInteractive', '-Command', command], cwd=ROOT, capture_output=True, text=True, timeout=30, creationflags=FLAGS)


def load_secret(shell, filename):
    command = "$secure=Import-Clixml -LiteralPath '.local/" + filename + "'; $credential=New-Object System.Management.Automation.PSCredential('service',$secure); [Console]::Write($credential.GetNetworkCredential().Password)"
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command], cwd=ROOT, capture_output=True, text=True, timeout=30, creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError('Could not decrypt local configuration')
    return json.loads(result.stdout)


def launch(args, name, env=None):
    # Each restart keeps one previous process log; OAuth values never appear in arguments.
    for suffix in ('stdout', 'stderr'):
        path = LOCAL / f'{name}-{suffix}.log'
        if path.exists():
            path.replace(LOCAL / f'{name}-{suffix}.previous.log')
    with (LOCAL / f'{name}-stdout.log').open('wb') as out, (LOCAL / f'{name}-stderr.log').open('wb') as err:
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=out, stderr=err, creationflags=FLAGS)
    logger.info('Started %s pid=%s', name, process.pid)
    remember_process(name, process)
    return process


def stop(process):
    if process is not None and process.poll() is None:
        subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/taskkill.exe'), '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=FLAGS, timeout=15)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def healthy(url, public=False):
    try:
        response = requests.get(url + '/health', headers={'ngrok-skip-browser-warning': 'true'} if public else {}, timeout=8 if public else 4)
        return response.status_code == 200 and response.json().get('status') == 'ok'
    except (requests.RequestException, ValueError):
        return False


def publish_origin(config, origin):
    repo = config['repository']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise RuntimeError('Invalid repository')
    parsed = urlparse(origin)
    if parsed.scheme != 'https' or parsed.path not in ('', '/') or not parsed.netloc:
        raise RuntimeError('Invalid API origin')
    credential_input = 'protocol=https\nhost=github.com\n'
    if config.get('credential_username'):
        credential_input += 'username=' + config['credential_username'] + '\n'
    result = subprocess.run([config['git'], '-c', 'credential.interactive=false', 'credential', 'fill'], input=credential_input + '\n', capture_output=True, text=True, timeout=30, env=dict(os.environ, GIT_TERMINAL_PROMPT='0'), creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError('GitHub connection unavailable')
    credentials = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    session = requests.Session()
    session.headers.update({'Authorization': 'Bearer ' + credentials['password'], 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    url = f'https://api.github.com/repos/{repo}/contents/docs/api-config.json'
    response = session.get(url, params={'ref': 'main'}, timeout=20)
    response.raise_for_status()
    current = response.json()
    previous = json.loads(base64.b64decode(current['content']))
    if previous.get('baseUrl') != origin:
        content = base64.b64encode((json.dumps({'baseUrl': origin}) + '\n').encode()).decode()
        response = session.put(url, json={'message': 'Update supervised API connection', 'content': content, 'sha': current['sha'], 'branch': 'main'}, timeout=20)
        response.raise_for_status()
        logger.info('Updated Pages API configuration: %s', origin)
    return True


def run(config):
    global SHELL
    SHELL = config['powershell']
    lock = (LOCAL / 'service.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1):
        lock.write(b'0')
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return  # Another supervisor already owns these services.
    clean_previous_processes()
    api = tunnel = None
    mode = origin = None
    published = None
    api_failures = tunnel_failures = 0
    next_publish = next_tunnel = next_public_check = tunnel_started = 0
    public_ok = False
    logger.info('Supervisor started pid=%s', os.getpid())
    try:
        while not (LOCAL / 'stop-service.flag').exists():
            try:
                ngrok_file = LOCAL / 'ngrok-auth.xml'
                wanted_mode = 'ngrok' if ngrok_file.exists() else 'cloudflare'
                if mode != wanted_mode:
                    stop(tunnel)
                    tunnel = None
                    origin = None
                    published = None
                    next_tunnel = 0
                    next_public_check = 0
                    public_ok = False
                    mode = wanted_mode
                    logger.info('Tunnel mode: %s', mode)
                if api is None or api.poll() is not None:
                    env = dict(os.environ)
                    env.update(load_secret(config['powershell'], 'google-oauth.xml'))
                    env.update(load_secret(config['powershell'], 'web-access.xml'))
                    env['PYTHONPATH'] = config['site_packages']
                    env['ALLOWED_ORIGINS'] = config['pages_origin'] + ',http://127.0.0.1:8080'
                    if ngrok_file.exists():
                        env['ALLOWED_ORIGINS'] += ',' + load_secret(config['powershell'], 'ngrok-auth.xml')['API_ORIGIN']
                    api = launch([config['base_python'], '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8080'], 'api', env)
                    env.clear()
                    api_failures = 0
                if (tunnel is None or tunnel.poll() is not None) and time.monotonic() >= next_tunnel:
                    stop(tunnel)
                    if mode == 'ngrok':
                        settings = load_secret(config['powershell'], 'ngrok-auth.xml')
                        origin = settings['API_ORIGIN']
                        env = dict(os.environ, NGROK_AUTHTOKEN=settings['NGROK_AUTHTOKEN'])
                        tunnel = launch([config['ngrok'], 'http', 'http://127.0.0.1:8080', '--url', origin, '--inspect=false', '--log', 'stdout', '--log-format', 'json'], 'tunnel', env)
                        env.clear()
                    else:
                        origin = None
                        tunnel = launch([config['cloudflared'], 'tunnel', '--url', 'http://127.0.0.1:8080', '--no-autoupdate', '--protocol', 'http2'], 'tunnel')
                    tunnel_failures = 0
                    published = None
                    next_tunnel = time.monotonic() + 60
                    tunnel_started = time.monotonic()
                    next_public_check = 0
                    public_ok = False
                if mode == 'cloudflare' and not origin:
                    log = (LOCAL / 'tunnel-stderr.log').read_text(encoding='utf-8', errors='replace') if (LOCAL / 'tunnel-stderr.log').exists() else ''
                    match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', log)
                    if match:
                        origin = match.group(0)
                api_ok = healthy('http://127.0.0.1:8080')
                api_failures = 0 if api_ok else api_failures + 1
                if api_failures >= 3:
                    logger.warning('API health failed; restarting')
                    stop(api)
                    api = None
                if not api_ok:
                    public_ok = False
                    next_public_check = 0
                if origin and api_ok and time.monotonic() >= next_public_check:
                    public_ok = healthy(origin, public=True)
                    tunnel_failures = 0 if public_ok else tunnel_failures + 1
                    # Public checks use tunnel quota; local/process checks still run every 10s.
                    next_public_check = time.monotonic() + (300 if public_ok else 30)
                if tunnel_failures >= 3 and time.monotonic() - tunnel_started >= 180:
                    logger.warning('Public connection health failed; restarting tunnel')
                    stop(tunnel)
                    tunnel = None
                    origin = None
                    tunnel_failures = 0
                if public_ok and published != origin and time.monotonic() >= next_publish:
                    try:
                        publish_origin(config, origin)
                        published = origin
                        (LOCAL / 'public-url.txt').write_text(origin + '/availability', encoding='utf-8')
                    except Exception:
                        logger.warning('Pages configuration update pending; retrying in 60 seconds')
                    next_publish = time.monotonic() + 60
                status = {'updated_at': datetime.now(timezone.utc).isoformat(), 'supervisor_pid': os.getpid(), 'api_pid': api.pid if api else None, 'tunnel_pid': tunnel.pid if tunnel else None, 'mode': mode, 'origin': origin, 'api_healthy': api_ok, 'public_healthy': public_ok, 'pages_updated': published == origin and bool(origin)}
                temporary = LOCAL / 'service-status.tmp'
                temporary.write_text(json.dumps(status), encoding='utf-8')
                temporary.replace(LOCAL / 'service-status.json')
            except Exception:
                logger.exception('Service monitoring cycle failed')
            time.sleep(10)
    finally:
        stop(tunnel)
        stop(api)
        logger.info('Supervisor stopped')
        lock.close()


if __name__ == '__main__':
    os.chdir(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(LOCAL / 'service-config.json'))
    arguments = parser.parse_args()
    run(json.loads(Path(arguments.config).read_text(encoding='utf-8-sig')))
