source /root/awg_telegram.conf
MSG="$1"
HOST=$(hostname)
TEXT="🛡 AmneziaWG [$HOST]
$MSG
$(date '+%Y-%m-%d %H:%M:%S')"
curl -s --max-time 10 -X POST \
  "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
  -d chat_id="${TG_CHAT}" \
  --data-urlencode text="$TEXT" \
  -o /dev/null
