#!/bin/bash
set -e

SERVER_PUB="<SERVER_PUBLIC_KEY>"
ENDPOINT="<SERVER_PUBLIC_IP>:<PORT>"
DNS="1.1.1.1, 1.0.0.1"
COUNT=10
OUTDIR="/root/awg_clients"

JC=6; JMIN=10; JMAX=50; S1=83; S2=148
H1=2035097030; H2=1885924146; H3=1511196280; H4=964510712

# qrencode
which qrencode >/dev/null 2>&1 || apt-get install -y qrencode >/dev/null 2>&1

mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/*.conf "$OUTDIR"/*.png 2>/dev/null || true

# бэкап текущего серверного конфига
docker exec amnezia-awg cat /opt/amnezia/awg/wg0.conf > /root/wg0.conf.backup.$(date +%s)
echo "Бэкап серверного конфига сохранён в /root/"

PSK=$(docker exec amnezia-awg wg genpsk)

SERVER_PRIV="<SERVER_PRIVATE_KEY>"

SERVER_CONF="[Interface]
PrivateKey = $SERVER_PRIV
Address = 10.8.1.0/24
ListenPort = 37327
Jc = $JC
Jmin = $JMIN
Jmax = $JMAX
S1 = $S1
S2 = $S2
H1 = $H1
H2 = $H2
H3 = $H3
H4 = $H4
"

for i in $(seq 1 $COUNT); do
  CLIENT_IP="10.8.1.$i"
  PRIV=$(docker exec amnezia-awg wg genkey)
  PUB=$(echo "$PRIV" | docker exec -i amnezia-awg wg pubkey)

  SERVER_CONF="$SERVER_CONF
[Peer]
PublicKey = $PUB
PresharedKey = $PSK
AllowedIPs = $CLIENT_IP/32
"

  cat > "$OUTDIR/client$i.conf" << EOF
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
EOF

  qrencode -t png -o "$OUTDIR/client$i.png" < "$OUTDIR/client$i.conf"
  echo "client$i.conf + QR создан ($CLIENT_IP)"
done

echo "$SERVER_CONF" | docker exec -i amnezia-awg tee /opt/amnezia/awg/wg0.conf > /dev/null
docker exec amnezia-awg sh -c 'wg syncconf wg0 <(wg-quick strip wg0)'

echo ""
echo "=== Готово. 10 клиентов в $OUTDIR ==="
docker exec amnezia-awg wg show wg0 | head -5
