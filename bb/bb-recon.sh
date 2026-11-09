#!/bin/bash
# ATANOR 버그바운티 정찰 파이프라인 (Kali 컨테이너 안에서 실행).
# 정찰 + 알려진 취약점 템플릿 스캔까지만 한다 — 익스플로잇·공격·제출은 하지 않는다(사람이 확인).
# 사용: bb-recon.sh <스코프-도메인> [normal|deep]
# 결과: /root/bb/<도메인>/ (subs.txt, resolved.txt, live.txt, nuclei.txt, urls.txt)
# 반드시 버그바운티 프로그램 스코프에 포함된 도메인에만 쓴다.
set -u
D="${1:?스코프 도메인이 필요하다}"
MODE="${2:-normal}"
HDR="${BB_HEADER:-X-Bug-Bounty: atanor-recon}"
O="/root/bb/$D"; mkdir -p "$O"
export PATH="$PATH:/root/go/bin"

echo "[*] 1/5 서브도메인 수집: $D"
subfinder -d "$D" -silent -all 2>/dev/null | sort -u > "$O/subs.txt"
echo "    서브도메인 $(wc -l < "$O/subs.txt")개"

echo "[*] 2/5 DNS 해석"
dnsx -silent -l "$O/subs.txt" 2>/dev/null | sort -u > "$O/resolved.txt"
echo "    해석됨 $(wc -l < "$O/resolved.txt")개"

echo "[*] 3/5 라이브 HTTP 서비스 + 기술 식별 (정중한 속도)"
httpx -silent -l "$O/resolved.txt" -rl 20 -timeout 8 -title -tech-detect -status-code -H "$HDR" 2>/dev/null > "$O/live.txt"
httpx -silent -l "$O/resolved.txt" -rl 20 -timeout 8 -H "$HDR" 2>/dev/null | sort -u > "$O/live_urls.txt"
echo "    라이브 $(wc -l < "$O/live_urls.txt")개"

if [ "$MODE" = "deep" ] && [ -s "$O/live_urls.txt" ]; then
  echo "[*] (deep) URL 수집: katana + gau"
  katana -silent -list "$O/live_urls.txt" -d 2 -rl 20 -H "$HDR" 2>/dev/null > "$O/urls.txt" || true
  gau --threads 5 < "$O/live_urls.txt" 2>/dev/null >> "$O/urls.txt" || true
  [ -f "$O/urls.txt" ] && sort -u -o "$O/urls.txt" "$O/urls.txt"
  echo "    URL $(wc -l < "$O/urls.txt" 2>/dev/null || echo 0)개"
fi

echo "[*] 4/5 알려진 취약점 템플릿 스캔 (nuclei, 정중한 속도)"
if [ -s "$O/live_urls.txt" ]; then
  nuclei -silent -l "$O/live_urls.txt" -rl 30 -c 25 -timeout 8 \
    -severity low,medium,high,critical -H "$HDR" -o "$O/nuclei.txt" 2>/dev/null || true
fi
touch "$O/nuclei.txt"

echo "[*] 5/5 요약"
CRIT=$(grep -ciE '\[critical\]' "$O/nuclei.txt" 2>/dev/null || echo 0)
HIGH=$(grep -ciE '\[high\]'     "$O/nuclei.txt" 2>/dev/null || echo 0)
MED=$(grep -ciE '\[medium\]'    "$O/nuclei.txt" 2>/dev/null || echo 0)
echo "================ 정찰 요약: $D ================"
echo "서브도메인 $(wc -l < "$O/subs.txt")개 · 라이브 $(wc -l < "$O/live_urls.txt")개"
echo "nuclei 발견  critical=$CRIT  high=$HIGH  medium=$MED"
echo "---- 심각/높음 (사람이 먼저 확인할 것) ----"
grep -iE '\[(critical|high)\]' "$O/nuclei.txt" 2>/dev/null | head -25
echo "[*] 흥미로운 기술/제목(라이브) 상위:"
head -15 "$O/live.txt" 2>/dev/null
echo "---- 결과 파일: $O/ ----"
