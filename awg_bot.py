#!/usr/bin/env python3
import requests, subprocess, json, os, time, sys

# читаем токен и chat_id из конфига
CONF = {}
with open("/root/awg_telegram.conf") as f:
    for ln in f:
        ln = ln.strip()
        if "=" in ln:
            k, v = ln.split("=", 1)
            CONF[k.strip()] = v.strip().strip('"')
TOKEN = CONF["TG_TOKEN"]
ALLOWED = str(CONF["TG_CHAT"])
API = f"https://api.telegram.org/bot{TOKEN}"

CONTAINER = "amnezia-awg"
IFACE = "wg0"
NAMES_FILE = "/root/awg_names.json"
CLIENTS_DIR = "/root/awg_clients"
HEALTH_LOG = "/root/awg_health.log"
ADDSCRIPT = "/root/awg_addclient.sh"

def sh(cmd, timeout=30):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=timeout).decode().strip()
    except Exception:
        return ""

def load_names():
    try:
        with open(NAMES_FILE) as f: return json.load(f)
    except: return {}

def human_bytes(n):
    n=float(n)
    for u in ['B','KB','MB','GB','TB']:
        if n<1024: return f"{n:.1f} {u}"
        n/=1024
    return f"{n:.1f} PB"

def human_time(sec):
    if sec is None: return "никогда"
    sec=int(sec)
    if sec<60: return f"{sec} сек назад"
    if sec<3600: return f"{sec//60} мин назад"
    if sec<86400: return f"{sec//3600} ч назад"
    return f"{sec//86400} дн назад"

def send(chat, text, parse="HTML"):
    requests.post(f"{API}/sendMessage", data={"chat_id":chat,"text":text,"parse_mode":parse}, timeout=15)

def send_photo(chat, path, caption=""):
    with open(path,"rb") as ph:
        requests.post(f"{API}/sendPhoto", data={"chat_id":chat,"caption":caption}, files={"photo":ph}, timeout=30)

def cmd_status(chat):
    cont = "✅ работает" if sh(f"docker ps --format '{{{{.Names}}}}' | grep -x {CONTAINER}") else "❌ упал"
    peers = sh(f"docker exec {CONTAINER} wg show {IFACE} peers | wc -l") or "?"
    up = sh("uptime -p") or sh("uptime")
    load = sh("cat /proc/loadavg | awk '{print $1, $2, $3}'")
    disk = sh("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")\"}'")
    dash = "✅" if sh("curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:10086/data")=="200" else "❌"
    bot = "✅"
    txt = (f"<b>📊 Статус сервера</b>\n\n"
           f"AmneziaWG: {cont}\n"
           f"Пиры (клиенты): <b>{peers}</b>\n"
           f"Дашборд: {dash}\n"
           f"Бот: {bot}\n\n"
           f"⏱ Аптайм: {up}\n"
           f"📈 Load: {load}\n"
           f"💾 Диск: {disk}")
    send(chat, txt)

def cmd_clients(chat):
    dump = sh(f"docker exec {CONTAINER} wg show {IFACE} dump")
    if not dump:
        send(chat, "Не удалось получить данные wg0"); return
    names = load_names()
    now = int(time.time())
    lines = dump.split("\n")[1:]  # пропускаем интерфейс
    rows = []
    online = 0
    for ln in lines:
        f = ln.split("\t")
        if len(f) < 8: continue
        pub, psk, endpoint, aips, hs, rx, tx, ka = f[:8]
        ip = aips.split("/")[0]; num = ip.split(".")[-1]
        name = names.get(pub, f"client{num}")
        hs_ago = (now-int(hs)) if hs!="0" else None
        is_on = hs_ago is not None and hs_ago < 180
        if is_on: online += 1
        dot = "🟢" if is_on else "⚪"
        rows.append(f"{dot} <b>{name}</b> ({ip})\n   ↓{human_bytes(rx)} ↑{human_bytes(tx)} · {human_time(hs_ago)}")
    txt = f"<b>👥 Клиенты ({online} онлайн из {len(rows)})</b>\n\n" + "\n".join(rows)
    send(chat, txt)

def cmd_addclient(chat):
    send(chat, "⏳ Создаю клиента...")
    out = sh(ADDSCRIPT, timeout=40)
    # скрипт выводит последней строкой "clientN 10.8.1.N"
    last = out.strip().split("\n")[-1] if out else ""
    parts = last.split()
    if len(parts) >= 2 and parts[0].startswith("client"):
        cname = parts[0]; cip = parts[1]
        num = cname.replace("client","")
        conf_path = f"{CLIENTS_DIR}/{cname}.conf"
        qr_path = f"{CLIENTS_DIR}/{cname}.png"
        # конфиг текстом
        cfg = ""
        try: cfg = open(conf_path).read()
        except: pass
        send(chat, f"✅ Создан <b>{cname}</b> ({cip})\n\n<pre>{cfg}</pre>")
        # QR картинкой
        if os.path.exists(qr_path):
            send_photo(chat, qr_path, caption=f"QR для {cname}")
    else:
        send(chat, f"❌ Ошибка создания клиента:\n<pre>{out}</pre>")

def cmd_health(chat):
    log = sh(f"tail -15 {HEALTH_LOG}")
    if not log: log = "Лог пуст — проблем не было."
    send(chat, f"<b>🩺 Health-лог (последние записи)</b>\n\n<pre>{log}</pre>")

def cmd_help(chat):
    txt = ("<b>🛡 AmneziaWG бот</b>\n\n"
           "/status — состояние сервера и сервисов\n"
           "/clients — список клиентов и трафик\n"
           "/addclient — создать клиента (пришлю QR)\n"
           "/health — последние записи мониторинга\n"
           "/help — эта справка")
    send(chat, txt)

HANDLERS = {
    "/start": cmd_help, "/help": cmd_help,
    "/status": cmd_status, "/clients": cmd_clients,
    "/addclient": cmd_addclient, "/health": cmd_health,
}

def main():
    offset = None
    while True:
        try:
            r = requests.get(f"{API}/getUpdates", params={"offset":offset,"timeout":30}, timeout=40)
            data = r.json()
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg: continue
                chat = str(msg["chat"]["id"])
                text = msg.get("text","").strip()
                # ПРОВЕРКА ДОСТУПА — реагируем только на разрешённый chat_id
                if chat != ALLOWED:
                    send(chat, "⛔ Доступ запрещён.")
                    continue
                cmd = text.split()[0].split("@")[0] if text else ""
                handler = HANDLERS.get(cmd)
                if handler: handler(chat)
                elif text: send(chat, "Неизвестная команда. /help — список.")
        except Exception as e:
            time.sleep(5)

if __name__ == "__main__":
    main()
