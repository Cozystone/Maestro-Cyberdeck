#!/bin/bash
# ATANOR 사이버덱 투명 Tor 라우팅 토글.
# 바깥으로 나가는 인터넷 통신을 기본으로 Tor를 거치게 해 추적을 막는다.
# 제외(그대로 직결): 로컬(두뇌·게이트·STT), LAN(공유기·내부 스캔·들어오는 SSH 응답), tor 자신.
# on | off | status
set -e

TOR_UID="$(id -u debian-tor)"
DNS_PORT=5353
TRANS_PORT=9040

del_rules() {
  nft delete chain inet atanor tor_nat  2>/dev/null || true
  nft delete chain inet atanor tor_leak 2>/dev/null || true
}

add_rules() {
  del_rules
  nft -f - <<NFT
table inet atanor {
  chain tor_nat {
    type nat hook output priority -100; policy accept;
    meta skuid $TOR_UID return
    oifname "lo" return
    ip daddr 127.0.0.0/8 return
    ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 224.0.0.0/4, 255.255.255.255 } return
    meta l4proto { tcp, udp } th dport 53 redirect to :$DNS_PORT
    meta l4proto tcp redirect to :$TRANS_PORT
  }
  chain tor_leak {
    type filter hook output priority -50; policy accept;
    meta skuid $TOR_UID accept
    oifname "lo" accept
    ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 224.0.0.0/4 } accept
    udp dport 53 accept
    udp sport 68 udp dport 67 accept
    meta l4proto udp ct state new drop
    ip6 daddr != { ::1, fe80::/10, fc00::/7 } meta l4proto { tcp, udp } ct state new drop
  }
}
NFT
}

case "${1:-}" in
  on)  add_rules; echo "tor-route ON" ;;
  off) del_rules; echo "tor-route OFF" ;;
  status)
    if nft list chain inet atanor tor_nat >/dev/null 2>&1; then echo "ON"; else echo "OFF"; fi ;;
  *) echo "usage: $0 on|off|status"; exit 1 ;;
esac
