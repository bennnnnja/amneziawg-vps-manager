#!/bin/bash
LOG="/root/awg_health.log"
NOTIFY="/root/awg_notify.sh"
STAMP_DIR="/root/.awg_alert_stamps"
mkdir -p "$STAMP_DIR"
TS=$(date '+%Y-%m-%d %H:%M:%S')
log(){ echo "$TS | $1" >> "$LOG"; }

# алерт с антиспамом: повтор той же проблемы не чаще раза в час
alert(){
    local key="$1" msg="$2"
    local stamp="$STAMP_DIR/$key"
    local now=$(date +%s)
    if [ -f "$stamp" ]; then
        local last=$(cat "$stamp")
        [ $((now - last)) -lt 3600 ] && return
    fi
    echo "$now" > "$stamp"
    "$NOTIFY" "$msg"
}
# восстановление: шлём ✅ только если до этого была активная проблема
recover(){
    local key="$1" msg="$2"
    if [ -f "$STAMP_DIR/$key" ]; then
        rm -f "$STAMP_DIR/$key"
        "$NOTIFY" "$msg"
    fi
}

# 1. Контейнер запущен?
if ! docker ps --format '{{.Names}}' | grep -q '^amnezia-awg$'; then
    log "ПРОБЛЕМА: контейнер amnezia-awg не запущен — пробую поднять"
    alert "container" "❌ Контейнер amnezia-awg упал — пробую поднять"
    if docker start amnezia-awg; then
        log "OK: контейнер запущен"; "$NOTIFY" "✅ Контейнер amnezia-awg восстановлен"
        rm -f "$STAMP_DIR/container"
    else
        log "ОШИБКА: не удалось запустить контейнер"; "$NOTIFY" "🚨 НЕ удалось запустить amnezia-awg!"
    fi
    exit 0
fi
recover "container" "✅ Контейнер amnezia-awg снова работает"

# 2. wg0 отвечает?
if ! docker exec amnezia-awg wg show wg0 >/dev/null 2>&1; then
    log "ПРОБЛЕМА: wg show wg0 не отвечает — перезапускаю контейнер"
    alert "wg0" "❌ wg0 не отвечает — перезапускаю контейнер"
    docker restart amnezia-awg && log "OK: контейнер перезапущен" || log "ОШИБКА: рестарт не удался"
    exit 0
fi
recover "wg0" "✅ wg0 снова отвечает"

# 3. Есть ли пиры?
PEERS=$(docker exec amnezia-awg wg show wg0 peers 2>/dev/null | wc -l)
if [ "$PEERS" -eq 0 ]; then
    log "ПРОБЛЕМА: wg0 без пиров — восстанавливаю конфиг"
    alert "peers" "❌ wg0 потерял всех пиров — восстанавливаю конфиг"
    docker exec amnezia-awg sh -c 'wg syncconf wg0 <(wg-quick strip /opt/amnezia/awg/wg0.conf)' 2>/dev/null \
        && log "OK: конфиг восстановлен" || log "ОШИБКА: не удалось восстановить"
    exit 0
fi
recover "peers" "✅ Пиры wg0 восстановлены ($PEERS шт.)"

# 4. Дашборд отвечает?
if ! curl -s -o /dev/null --max-time 5 http://127.0.0.1:10086/data; then
    log "ПРОБЛЕМА: дашборд не отвечает — перезапускаю сервис"
    alert "dashboard" "❌ Дашборд не отвечает — перезапускаю"
    systemctl restart awg-dashboard && log "OK: дашборд перезапущен" || log "ОШИБКА: рестарт дашборда не удался"
    exit 0
fi
recover "dashboard" "✅ Дашборд снова отвечает"


# 5. Бот работает?
if ! systemctl is-active --quiet awg-bot; then
    log "ПРОБЛЕМА: awg-bot не активен — перезапускаю"
    alert "bot" "❌ Telegram-бот упал — перезапускаю"
    systemctl restart awg-bot && log "OK: бот перезапущен" || log "ОШИБКА: рестарт бота не удался"
    exit 0
fi
recover "bot" "✅ Telegram-бот снова работает"

[ "$(date +%M)" = "00" ] && log "OK: всё работает ($PEERS пиров)"
exit 0
