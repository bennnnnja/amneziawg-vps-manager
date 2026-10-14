#!/bin/bash
set -e
CONTAINER="amnezia-awg"
CONF="/opt/amnezia/awg/wg0.conf"
CLIENTS_DIR="/root/awg_clients"
SERVER_PUB="<SERVER_PUBLIC_KEY>"
ENDPOINT="<SERVER_PUBLIC_IP>:<PORT>"
DNS="1.1.1.1, 1.0.0.1"
JC=6; JMIN=10; JMAX=50; S1=83; S2=148
H1=2035097030; H2=1885924146; H3=1511196280; H4=964510712

docker exec "$CONTAINER" cat "$CONF" > "/root/wg0.conf.backup.$(date +%s)"

MAX=$(docker exec "$CONTAINER" sh -c "grep -oE '10\.8\.1\.[0-9]+' $CONF | awk -F. '{print \$4}' | sort -n | tail -1")
NEXT=$((MAX + 1))
CLIENT_IP="10.8.1.$NEXT"

PSK=$(docker exec "$CONTAINER" sh -c "grep -m1 'PresharedKey' $CONF | awk '{print \$3}'")

PRIV=$(docker exec "$CONTAINER" wg genkey)
PUB=$(echo "$PRIV" | docker exec -i "$CONTAINER" wg pubkey)

PEER_BLOCK=$(printf '\n[Peer]\nPublicKey = %s\nPresharedKey = %s\nAllowedIPs = %s/32\n' "$PUB" "$PSK" "$CLIENT_IP")
printf '%s' "$PEER_BLOCK" | docker exec -i "$CONTAINER" sh -c "cat >> $CONF"

# проверяем, что пир реально дописался
CNT=$(docker exec "$CONTAINER" grep -c '\[Peer\]' "$CONF")
echo "пиров в конфиге после записи: $CNT"

# применяем без рестарта
docker exec "$CONTAINER" sh -c "wg syncconf wg0 <(wg-quick strip $CONF)" 2>/dev/null

# клиентский конфиг
mkdir -p "$CLIENTS_DIR"
cat > "$CLIENTS_DIR/client$NEXT.conf" << CFGEOF
[Interface]
PrivateKey = $PRIV
Address = $CLIENT_IP/32
DNS = $DNS
Jc = $JC
Jmin = $JMIN
Jmax = $JMAX
S1 = $S1
S2 = $S2
H1 = $H1
H2 = $H2
H3 = $H3
H4 = $H4

[Peer]
PublicKey = $SERVER_PUB
PresharedKey = $PSK
AllowedIPs = 0.0.0.0/0
Endpoint = $ENDPOINT
PersistentKeepalive = 25
CFGEOF

qrencode -t png -o "$CLIENTS_DIR/client$NEXT.png" < "$CLIENTS_DIR/client$NEXT.conf"
echo "client$NEXT $CLIENT_IP"
