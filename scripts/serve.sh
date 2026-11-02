#!/bin/bash
# 온트윈 서버 켜기 (WSL). 바탕화면의 온트윈.bat이 부른다.
cd ~/ontwin || exit 1
# 이미 켜져 있고 최신 버전이면 그대로 둔다. 옛 버전(업데이트 전)이면 끄고 새로 켠다.
HEAD=$(git rev-parse --short HEAD 2>/dev/null)
RUN=$(curl -s -m 2 http://localhost:8501/ow/api/version | sed -n 's/.*"commit":"\([^"]*\)".*/\1/p')
if [ -n "$RUN" ] && [ "$RUN" = "$HEAD" ]; then
  echo "  온트윈이 이미 켜져 있어요(최신 $HEAD). 창만 엽니다."
  exit 0
fi
if curl -s -o /dev/null -m 2 http://localhost:8501/ow/; then
  echo "  옛 버전 온트윈(${RUN:-확인 불가})을 끄고 최신($HEAD)으로 다시 켭니다."
  pkill -f "python3 -m app serv[e]"
  sleep 2
fi
source .venv/bin/activate
# ERPNext가 응답할 때까지 최대 3분 기다림
for i in $(seq 1 60); do
  curl -s -o /dev/null -m 3 http://localhost:8080/api/method/ping && break
  sleep 3
done
echo "  ERP 준비 완료. 온트윈 서버 시작"
exec python3 -m app serve
