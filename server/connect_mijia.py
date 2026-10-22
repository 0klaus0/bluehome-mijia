"""Local inventory and property bridge with validated user-operated controls."""
import io
import ipaddress
import json
import logging
import mimetypes
import os
import re
import secrets
import socket
import sys
import threading
import time
import webbrowser
from urllib.parse import parse_qs
from device_bridge import DeviceBridge
from model_client import ModelClient
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import qrcode
import requests
from mijiaAPI import mijiaAPI

ROOT = Path(__file__).resolve().parent
WEB = Path(getattr(sys, '_MEIPASS', ROOT.parent)) / 'web'
PRIVATE = Path(os.environ['BLUEHOME_DATA_DIR']) if os.environ.get('BLUEHOME_DATA_DIR') else Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.bluehome')) / 'Bluehome'
PRIVATE.mkdir(exist_ok=True)
LAN_HOST = None
TAILSCALE_RANGE = ipaddress.IPv4Network('100.64.0.0/10')
def allowed_remote_host(address):
    return (address.is_private and not address.is_loopback) or address in TAILSCALE_RANGE
PAIR_CODE = f'{secrets.randbelow(100_000_000):08d}'
PAIR_COOKIE = secrets.token_urlsafe(32)
PAIR_FAILURES = {}
logging.getLogger('mijiaAPI').disabled = True
# Bound upstream requests that otherwise omit timeouts.
original_request = requests.sessions.Session.request
def bounded_request(self, method, url, **kwargs):
    kwargs.setdefault('timeout', 30)
    return original_request(self, method, url, **kwargs)
requests.sessions.Session.request = bounded_request
state = {'status': 'starting', 'message': '正在准备扫码登录'}
qr_png = None
lock = threading.Lock()
bridge = None
model_client = ModelClient(PRIVATE)

def run():
    global qr_png, state, bridge
    try:
        api = mijiaAPI(auth_data_path=str(PRIVATE / 'auth.json'))
        if not api.available:
            data = api._get_qr_login_data()
            if not data.get('refreshed'):
                buf = io.BytesIO()
                qrcode.make(data['loginUrl']).save(buf, format='PNG')
                with lock:
                    qr_png = buf.getvalue()
                    state = {'status': 'waiting', 'message': '请使用米家 App 扫码，并在手机上确认登录'}
                api._complete_qr_login(data)
        with lock:
            qr_png = None
            state = {'status': 'reading', 'message': '已登录，正在只读获取家庭、房间和设备'}
        homes = api.get_homes_list()
        items = api.get_devices_list()
        items += api.get_shared_devices_list()
        home_rows = []
        locations = {}
        for home in homes:
            rooms = []
            for room in home.get('roomlist', []) or []:
                name = str(room.get('name', '未命名房间'))
                match = re.search(r'(地下[一二三四五六七八九十\d]+[层楼]|[一二三四五六七八九十\d]+[层楼]|[Bb]?\d+\s*[Ff])', name)
                hint = match.group(0) if match else None
                rooms.append({'name': name, 'floor_hint': hint})
                for did in room.get('dids', []) or []:
                    locations[str(did)] = {'home': home.get('name', ''), 'room': name, 'floor_hint': hint}
            home_rows.append({'name': home.get('name', ''), 'rooms': rooms,
                              'floor_field_names': [k for k in home if 'floor' in k.lower()]})
        rows = []
        seen = set()
        for dev in items:
            did = str(dev.get('did', ''))
            if did in seen:
                continue
            seen.add(did)
            rows.append({'key': len(rows) + 1, 'name': dev.get('name', ''), 'model': dev.get('model', ''),
                         'online': dev.get('isOnline'), 'spec_type': dev.get('spec_type'),
                         **locations.get(did, {'home': '未分组/共享设备', 'room': '未分组', 'floor_hint': None})})
        result = {'homes': home_rows, 'devices': rows}
        # Whitelisted data only: omit tokens, IDs, MACs, IPs, coordinates.
        (PRIVATE / 'inventory-summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        bridge = DeviceBridge(api, items, rows, PRIVATE)
        with lock:
            state = {'status': 'ready', 'message': f'已读取 {len(home_rows)} 个家庭、{len(rows)} 台设备', **result}
    except Exception as exc:
        with lock:
            qr_png = None
            state = {'status': 'error', 'message': '连接未完成，可能是二维码过期或网络请求失败。', 'error_type': type(exc).__name__}

PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>栖居 · 接入米家</title><style>body{margin:0;background:#f5f7fb;color:#253047;font:14px/1.8 "Microsoft YaHei",sans-serif}main{max-width:850px;margin:50px auto;padding:30px}section{background:white;border:1px solid #e6ebf4;border-radius:20px;padding:30px}h1{font-size:30px}small{color:#8a95a8}#qr{width:240px;max-width:100%;display:block;margin:20px auto}#login{text-align:center}a{color:#2563ff}</style><main><h1>栖居 · 接入米家</h1><section id="login"><h2 id="status">正在连接…</h2><img id="qr" hidden alt="米家登录二维码"><p>使用米家 App 扫码并在手机确认。</p><small>登录凭据只保存在当前连接器设备上。</small></section><p><a href="/app/">进入家庭控制台 ↗</a></p></main><script>const $=s=>document.querySelector(s);async function poll(){try{const s=await(await fetch('/state',{cache:'no-store'})).json();$('#status').textContent=s.message;if(s.status==='waiting'){$('#qr').src='/qr';$('#qr').hidden=false}else $('#qr').hidden=true;if(s.status==='ready'){location.replace('/app/');return}if(s.status==='error')return}catch{$('#status').textContent='连接中断'}setTimeout(poll,2000)}poll();</script></html>'''
PAIR_PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>栖居 · 手机配对</title><style>body{font:15px/1.8 sans-serif;background:#f5f8fd;color:#30435e;padding:35px}main{max-width:420px;margin:10vh auto;background:#fff;border-radius:20px;padding:28px;box-shadow:0 15px 50px #20375512}input,button{font:inherit;width:100%;padding:12px;border-radius:9px;margin:8px 0}input{border:1px solid #d8e3f3}button{border:0;background:#2563ff;color:white}small{color:#8598b0}</style><main><h1>连接栖居</h1><p>输入连接器日志中显示的八位配对码。</p><form method="post" action="/pair"><input name="code" inputmode="numeric" pattern="[0-9]{8}" maxlength="8" required autocomplete="one-time-code"><button>配对并进入</button></form><small>手机与连接器需处于同一可信局域网；连接器需保持运行。</small></main></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def valid_host(self):
        host = self.headers.get('Host', '')
        if host in ('localhost:4174', '127.0.0.1:4174'):
            return True
        if not LAN_HOST or not host.endswith(':4174'):
            return False
        try:
            address = ipaddress.IPv4Address(host.removesuffix(':4174'))
            return allowed_remote_host(address) and (LAN_HOST == 'auto' or host == f'{LAN_HOST}:4174')
        except ValueError:
            return False

    def local_client(self):
        return self.client_address[0] in ('127.0.0.1', '::1')

    def paired(self):
        cookies = self.headers.get('Cookie', '').split(';')
        return self.local_client() or any(secrets.compare_digest(part.strip(), 'bluehome_pair=' + PAIR_COOKIE) for part in cookies)

    def response(self, body, kind='text/html; charset=utf-8', status=200):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.valid_host():
            self.send_error(403)
            return
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send_error(403)
            return
        if self.path == '/pair' and LAN_HOST:
            self.response(PAIR_PAGE.encode())
            return
        if not self.paired():
            self.send_response(302)
            self.send_header('Location', '/pair')
            self.send_header('Content-Length', '0')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return
        if self.path == '/':
            body, kind = PAGE.encode(), 'text/html; charset=utf-8'
        elif self.path in ('/app', '/app/'):
            body, kind = (WEB / 'index.html').read_bytes(), 'text/html; charset=utf-8'
        elif self.path.startswith('/app/') and self.path.count('/') == 2:
            filename = self.path.removeprefix('/app/')
            if filename not in {'style.css','model.css','app.js','device-icons.js','dashboard.js','model.js','assistant.js','spatial.js','inventory.js'}:
                self.send_error(404); return
            body, kind = (WEB / filename).read_bytes(), mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        elif self.path == '/state':
            with lock:
                body = json.dumps(state, ensure_ascii=False).encode()
            kind = 'application/json; charset=utf-8'
        elif self.path == '/inventory.js':
            with lock:
                inventory = {**state, 'control_token': bridge.token if bridge else None} if state.get('status') == 'ready' else {'status': state.get('status')}
                body = ('window.receiveMijiaInventory(' + json.dumps(inventory, ensure_ascii=True) + ');').encode()
            kind = 'text/javascript; charset=utf-8'
        elif self.path == '/live' and bridge:
            body = json.dumps(bridge.snapshot(), ensure_ascii=False).encode()
            kind = 'application/json; charset=utf-8'
        elif self.path == '/assistant' and bridge:
            body = json.dumps(bridge.assistant.snapshot(), ensure_ascii=False).encode()
            kind = 'application/json; charset=utf-8'
        elif self.path == '/model' and bridge:
            body = json.dumps(model_client.status(), ensure_ascii=False).encode()
            kind = 'application/json; charset=utf-8'
        elif self.path == '/qr' and qr_png:
            body, kind = qr_png, 'image/png'
        else:
            self.send_error(404)
            return
        self.response(body, kind)

    def do_OPTIONS(self):
        self.send_error(403)

    def do_POST(self):
        if not self.valid_host():
            self.send_error(403);return
        if self.path == '/pair' and LAN_HOST and not self.local_client():
            # The session pairing code protects this form. Some NAS launchers
            # omit or rewrite Origin; do not apply the control API's Origin rule.
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                self.send_error(403);return
            ip = self.client_address[0]
            recent = [t for t in PAIR_FAILURES.get(ip, []) if time.time()-t < 600]
            if len(recent) >= 8:
                self.send_error(429);return
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 1 <= length <= 100: raise ValueError()
                code = parse_qs(self.rfile.read(length).decode()).get('code',[''])[0]
            except (ValueError, UnicodeError):
                code = ''
            if not secrets.compare_digest(code, PAIR_CODE):
                recent.append(time.time());PAIR_FAILURES[ip] = recent
                self.response('配对码无效，请返回重试。'.encode(),status=403);return
            PAIR_FAILURES.pop(ip,None)
            self.send_response(303)
            self.send_header('Set-Cookie','bluehome_pair='+PAIR_COOKIE+'; HttpOnly; SameSite=Strict; Path=/')
            with lock:
                destination = '/app/' if state.get('status') == 'ready' else '/'
            self.send_header('Location',destination)
            self.send_header('Content-Length','0')
            self.send_header('Cache-Control','no-store')
            self.end_headers();return
        if self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
            self.send_error(403);return
        if (self.path not in ('/control','/assistant','/model') or not bridge or not self.paired()
            or self.headers.get('X-Bluehome-Session')!=bridge.token):
            self.send_error(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>4096:raise ValueError('请求大小无效')
            payload=json.loads(self.rfile.read(length))
            if self.path == '/assistant':
                result = bridge.assistant.operate(payload)
            elif self.path == '/model':
                op = payload.get('op')
                if op == 'configure': result = model_client.configure(payload)
                elif op == 'disconnect': result = model_client.disconnect()
                elif op in ('test', 'chat'):
                    context = None
                    if op == 'chat' and model_client.status()['share_home_context']:
                        home = payload.get('home')
                        if home not in {d['home'] for d in bridge.rows.values()}: raise ValueError('家庭不存在')
                        live = bridge.snapshot()['devices']
                        context = [{'name':d['name'][:80], 'room':d['room'][:60], 'online':live.get(str(k),{}).get('online')}
                                   for k,d in bridge.rows.items() if d['home'] == home][:40]
                    result = model_client.chat('测试连接' if op == 'test' else payload.get('question'), test=op == 'test', home_context=context)
                else: raise ValueError('不支持的模型操作')
            else:
                result = bridge.control(int(payload['key']),str(payload['property']),payload['value'])
        except ValueError as exc:result={'ok':False,'message':str(exc)[:150]}
        except (KeyError,TypeError):result={'ok':False,'message':'不支持此操作或参数无效'}
        except Exception:result={'ok':False,'message':'设备控制请求失败，请稍后重试'}
        body=json.dumps(result,ensure_ascii=False).encode()
        self.response(body,'application/json; charset=utf-8')

if __name__ == '__main__':
    if '--lan' in sys.argv:
        LAN_HOST = os.environ.get('BLUEHOME_PUBLIC_HOST')
        if not LAN_HOST:
            try:
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                    sock.connect(('8.8.8.8',80));LAN_HOST=sock.getsockname()[0]
            except OSError:
                raise SystemExit('未找到局域网 IP；请设置 BLUEHOME_PUBLIC_HOST')
        if LAN_HOST != 'auto':
            try:
                address = ipaddress.IPv4Address(LAN_HOST)
                if not allowed_remote_host(address):
                    raise ValueError()
            except ValueError:
                raise SystemExit('BLUEHOME_PUBLIC_HOST 必须是局域网或 Tailscale IPv4 地址，或 auto')
    threading.Thread(target=run, daemon=True).start()
    print('栖居连接器: http://localhost:4174/', flush=True)
    if LAN_HOST:
        print(f'局域网地址: http://{LAN_HOST if LAN_HOST != "auto" else "<NAS局域网IP>"}:4174/app/', flush=True)
        print(f'局域网配对码: {PAIR_CODE}', flush=True)
    if not os.environ.get('BLUEHOME_NO_BROWSER'):
        threading.Timer(1, lambda: webbrowser.open('http://localhost:4174/')).start()
    ThreadingHTTPServer(('0.0.0.0' if LAN_HOST else '127.0.0.1', 4174), Handler).serve_forever()
