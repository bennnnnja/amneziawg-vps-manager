#!/bin/bash
set -euo pipefail

CONTAINER="amnezia-awg"
CONF="/opt/amnezia/awg/wg0.conf"
CLIENTS_DIR="/root/awg_clients"
NAMES_FILE="/root/awg_names.json"
NUM="${1:-}"

[ -z "$NUM" ] && { echo "Использование: $0 <номер>"; exit 1; }

CLIENT_IP="10.8.1.$NUM"
BACKUP_FILE="/root/wg0.conf.backup.$(date +%s)"

docker cp "$CONTAINER:$CONF" "$BACKUP_FILE"

PUBKEY=""
if [ -f "$CLIENTS_DIR/client$NUM.conf" ]; then
    PRIV=$(grep -E '^[[:space:]]*PrivateKey' "$CLIENTS_DIR/client$NUM.conf" | awk -F '=' '{print $2}' | tr -d ' \r')
    if [ -n "$PRIV" ]; then
        PUBKEY=$(docker exec "$CONTAINER" sh -c "echo '$PRIV' | wg pubkey" 2>/dev/null || true)
    fi
fi

if [ -n "$PUBKEY" ]; then
    docker exec "$CONTAINER" wg set wg0 peer "$PUBKEY" remove 2>/dev/null || true
fi

python3 -c "
import sys, re
with open('$BACKUP_FILE', 'r') as f:
    text = f.read()
blocks = re.split(r'(?=\n\[Peer\])', text)
header = blocks[0]
peers = [b for b in blocks[1:] if '$CLIENT_IP/32' not in b]
with open('/tmp/wg0_clean.conf', 'w') as f:
    f.write(header + ''.join(peers))
"

docker cp /tmp/wg0_clean.conf "$CONTAINER:$CONF"
rm -f /tmp/wg0_clean.conf

rm -f "$CLIENTS_DIR/client$NUM.conf" "$CLIENTS_DIR/client$NUM.png"

if [ -n "$PUBKEY" ] && [ -f "$NAMES_FILE" ]; then
    python3 -c "
import json
try:
    d = json.load(open('$NAMES_FILE'))
    d.pop('$PUBKEY', None)
    json.dump(d, open('$NAMES_FILE', 'w'), ensure_ascii=False, indent=2)
except Exception: pass
" 2>/dev/null || true
fi

echo "client$NUM ($CLIENT_IP) успешно удалён"