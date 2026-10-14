#!/usr/bin/env python3
import http.server, socketserver, subprocess, json, time, os, urllib.parse

PORT=10086; BIND="127.0.0.1"
CONTAINER="amnezia-awg"; IFACE="wg0"
NAMES_FILE="/root/awg_names.json"; CLIENTS_DIR="/root/awg_clients"
_prev={}; _prev_ts=None

def load_names():
    try:
        with open(NAMES_FILE) as f: return json.load(f)
    except: return {}
def save_names(d):
    with open(NAMES_FILE,"w") as f: json.dump(d,f,ensure_ascii=False,indent=2)
def human_bytes(n):
    n=float(n)
    for u in ['B','KB','MB','GB','TB']:
        if n<1024: return f"{n:.1f} {u}"
        n/=1024
    return f"{n:.1f} PB"
def human_speed(bps):
    if bps<1: return "—"
    n=float(bps)
    for u in ['B/s','KB/s','MB/s']:
        if n<1024: return f"{n:.1f} {u}"
        n/=1024
    return f"{n:.1f} GB/s"
def human_time(sec):
    if sec is None: return "никогда"
    sec=int(sec)
    if sec<60: return f"{sec} сек назад"
    if sec<3600: return f"{sec//60} мин назад"
    if sec<86400: return f"{sec//3600} ч назад"
    return f"{sec//86400} дн назад"

def get_data():
    global _prev,_prev_ts
    try:
        out=subprocess.check_output(["docker","exec",CONTAINER,"wg","show",IFACE,"dump"],
            stderr=subprocess.DEVNULL,timeout=5).decode()
    except Exception as e:
        return {"error":str(e),"peers":[]}
    names=load_names(); lines=out.strip().split("\n")
    now=time.time(); dt=(now-_prev_ts) if _prev_ts else None
    peers=[]; new_prev={}
    for ln in lines[1:]:
        f=ln.split("\t")
        if len(f)<8: continue
        pub,psk,endpoint,aips,hs,rx,tx,ka=f[:8]
        rx,tx=int(rx),int(tx)
        ip=aips.split("/")[0]; num=ip.split(".")[-1]
        new_prev[pub]=(rx,tx,now)
        down=up=0
        if pub in _prev and dt and dt>0:
            prx,ptx,_=_prev[pub]
            down=max(0,(rx-prx)/dt); up=max(0,(tx-ptx)/dt)
        hs_ago=(int(now)-int(hs)) if hs!="0" else None
        online=(hs_ago is not None and hs_ago<180)
        peers.append({"pub":pub,"num":num,"name":names.get(pub,f"client{num}"),
            "ip":ip,"endpoint":endpoint if endpoint!="(none)" else "—",
            "handshake":human_time(hs_ago),"online":online,
            "rx":human_bytes(rx),"tx":human_bytes(tx),
            "down":human_speed(down),"up":human_speed(up),
            "has_cfg":os.path.exists(f"{CLIENTS_DIR}/client{num}.conf"),
            "has_qr":os.path.exists(f"{CLIENTS_DIR}/client{num}.png")})
    _prev=new_prev; _prev_ts=now
    peers.sort(key=lambda p:int(p["num"]))
    return {"error":None,"peers":peers,"ts":time.strftime("%H:%M:%S")}

HTML=r"""<!DOCTYPE html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>AmneziaWG Dashboard</title>
<style>
body{background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:19px;margin:0 0 4px}.sub{color:#8b949e;font-size:13px;margin-bottom:16px}
table{width:100%;border-collapse:collapse;background:#161b22;border-radius:10px;overflow:hidden}
th,td{padding:10px 12px;text-align:left;font-size:13px;border-bottom:1px solid #21262d;vertical-align:top}
th{color:#8b949e;font-weight:600;font-size:11px;text-transform:uppercase}
tr:last-child td{border-bottom:none}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.on{background:#3fb950;box-shadow:0 0 8px #3fb950}.off{background:#484f58}
.name{font-weight:600;cursor:pointer;border-bottom:1px dashed #484f58}
.name:hover{color:#58a6ff}.ip{color:#8b949e;font-size:11px}
.rx{color:#58a6ff}.tx{color:#3fb950}.spd{font-weight:600}.err{color:#f85149;padding:20px}
.foot{color:#484f58;font-size:12px;margin-top:14px;text-align:center}
.btn{display:inline-block;background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:4px 8px;font-size:12px;cursor:pointer;text-decoration:none;margin:2px 2px 0 0}
.btn:hover{background:#30363d;border-color:#58a6ff}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:9;align-items:center;justify-content:center;padding:20px}
.modal.show{display:flex}
.mbox{background:#fff;padding:16px;border-radius:12px;max-width:90vw;text-align:center}
.mbox img{max-width:280px;width:100%;display:block}
.mbox pre{background:#161b22;color:#e6edf3;text-align:left;padding:12px;border-radius:8px;font-size:11px;overflow:auto;max-height:50vh;white-space:pre-wrap;word-break:break-all}
</style></head><body>
<h1>AmneziaWG — клиенты</h1>
<div class=sub>Раздача конфигов · клик на имя = переименовать · обновление 2с</div>
<button class=btn style="margin-bottom:12px;background:#238636;border-color:#2ea043" onclick="addClient()">+ Добавить клиента</button>
<div id=app></div>
<div class=foot id=ts></div>
<div class=modal id=modal><div class=mbox><div id=mcontent></div>
<button class=btn style="margin-top:10px" onclick="closeM()">Закрыть</button></div></div>
<script>
function closeM(){document.getElementById('modal').classList.remove('show');}
document.getElementById('modal').addEventListener('click',function(e){if(e.target.id=='modal')closeM();});
function showQR(num,name){
 document.getElementById('mcontent').innerHTML='<div style="color:#161b22;font-weight:600;margin-bottom:8px">'+name+'</div><img src="/qr?n='+num+'&t='+Date.now()+'">';
 document.getElementById('modal').classList.add('show');
}
function showCfg(num,name){
 fetch('/conf?n='+num).then(function(r){return r.text();}).then(function(t){
  var esc=t.replace(/&/g,'&amp;').replace(/</g,'&lt;');
  document.getElementById('mcontent').innerHTML='<div style="color:#161b22;font-weight:600;margin-bottom:8px">'+name+'</div><pre>'+esc+'</pre>';
  document.getElementById('modal').classList.add('show');
 });
}
function rename(pub,cur){
 var name=prompt('Новое имя клиента:',cur);
 if(name===null||name===cur)return;
 fetch('/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pub:pub,name:name})}).then(tick);
}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;');}
function delClient(num,name){
 if(!confirm('Удалить клиента "'+name+'"? Это НЕМЕДЛЕННО отключит устройство. Отменить нельзя.'))return;
 fetch('/delclient',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({num:num})}).then(function(r){return r.json();}).then(function(d){
  if(d.ok){tick();}else{alert('Ошибка: '+d.msg);}
 });
}
function addClient(){
 if(!confirm('Создать нового клиента?'))return;
 fetch('/addclient',{method:'POST'}).then(function(r){return r.json();}).then(function(d){
  if(d.ok){alert('Создан: '+d.msg);tick();}else{alert('Ошибка: '+d.msg);}
 });
}
function tick(){
 fetch('/data').then(function(r){return r.json();}).then(function(d){
  if(d.error){document.getElementById('app').innerHTML='<div class=err>Ошибка: '+d.error+'</div>';return;}
  var on=d.peers.filter(function(p){return p.online;}).length;
  var rows=d.peers.map(function(p){
   var pub=esc(p.pub), nm=esc(p.name);
   var act='';
   if(p.has_qr)act+='<span class=btn onclick="showQR(\''+p.num+'\',\''+nm+'\')">QR</span>';
   if(p.has_cfg)act+='<a class=btn href="/download?n='+p.num+'">скачать</a>';
   if(p.has_cfg)act+='<span class=btn onclick="showCfg(\''+p.num+'\',\''+nm+'\')">текст</span>';
   act+='<span class="btn" style="background:#3a1618;border-color:#f85149;color:#f85149" onclick="delClient(\''+p.num+'\',\''+nm+'\')">✕</span>';
   return '<tr><td><span class=name onclick="rename(\''+pub+'\',\''+nm+'\')">'+nm+'</span><br><span class=ip>'+p.ip+'</span></td>'+
    '<td><span class="dot '+(p.online?'on':'off')+'"></span>'+(p.online?'онлайн':'оффлайн')+'<br><span class=ip>'+p.handshake+'</span></td>'+
    '<td><span class="spd rx">v '+p.down+'</span><br><span class="spd tx">^ '+p.up+'</span></td>'+
    '<td><span class=rx>v '+p.rx+'</span><br><span class=tx>^ '+p.tx+'</span></td>'+
    '<td>'+act+'</td></tr>';
  }).join('');
  document.getElementById('app').innerHTML='<table><tr><th>Клиент</th><th>Статус</th><th>Скорость</th><th>Всего</th><th>Раздать</th></tr>'+rows+'</table>';
  document.getElementById('ts').textContent='Онлайн: '+on+' из '+d.peers.length+' · '+d.ts;
 }).catch(function(e){});
}
tick();setInterval(tick,2000);
</script></body></html>"""

def safe_num(q):
    n=urllib.parse.parse_qs(q).get("n",[""])[0]
    return n if n.isdigit() else None

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        p=urllib.parse.urlparse(self.path)
        if p.path=="/data":
            b=json.dumps(get_data()).encode()
            self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(b)
        elif p.path=="/qr":
            n=safe_num(p.query); fp=f"{CLIENTS_DIR}/client{n}.png" if n else None
            if fp and os.path.exists(fp):
                self.send_response(200);self.send_header("Content-Type","image/png");self.end_headers();self.wfile.write(open(fp,"rb").read())
            else: self.send_response(404);self.end_headers()
        elif p.path=="/conf":
            n=safe_num(p.query); fp=f"{CLIENTS_DIR}/client{n}.conf" if n else None
            if fp and os.path.exists(fp):
                self.send_response(200);self.send_header("Content-Type","text/plain; charset=utf-8");self.end_headers();self.wfile.write(open(fp,"rb").read())
            else: self.send_response(404);self.end_headers()
        elif p.path=="/download":
            n=safe_num(p.query); fp=f"{CLIENTS_DIR}/client{n}.conf" if n else None
            if fp and os.path.exists(fp):
                self.send_response(200);self.send_header("Content-Type","application/octet-stream")
                self.send_header("Content-Disposition",f'attachment; filename="amneziawg-client{n}.conf"');self.end_headers();self.wfile.write(open(fp,"rb").read())
            else: self.send_response(404);self.end_headers()
        else:
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(HTML.encode())
    def do_POST(self):
        if self.path=="/addclient":
            try:
                out=subprocess.check_output(["/root/awg_addclient.sh"],stderr=subprocess.STDOUT,timeout=30).decode()
                self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"ok":True,"msg":out.strip()}).encode())
            except Exception as e:
                self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"ok":False,"msg":str(e)}).encode())
            return
        if self.path=="/delclient":
            ln=int(self.headers.get("Content-Length",0))
            data=json.loads(self.rfile.read(ln).decode())
            num=str(data.get("num",""))
            if not num.isdigit():
                self.send_response(400);self.end_headers();return
            try:
                out=subprocess.check_output(["/root/awg_delclient.sh",num],stderr=subprocess.STDOUT,timeout=20).decode()
                self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"ok":True,"msg":out.strip()}).encode())
            except Exception as e:
                self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"ok":False,"msg":str(e)}).encode())
            return
        if self.path=="/rename":
            ln=int(self.headers.get("Content-Length",0))
            data=json.loads(self.rfile.read(ln).decode())
            names=load_names(); nm=data.get("name","").strip()
            if nm: names[data["pub"]]=nm
            else: names.pop(data["pub"],None)
            save_names(names)
            self.send_response(200);self.end_headers();self.wfile.write(b"ok")
        else:
            self.send_response(404);self.end_headers()

socketserver.TCPServer.allow_reuse_address=True

class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

with ThreadingServer((BIND, PORT), H) as httpd:
    print(f"Dashboard на http://{BIND}:{PORT}")
    httpd.serve_forever()
