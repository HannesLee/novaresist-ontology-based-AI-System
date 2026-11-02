#!/bin/bash
# 온트윈 서버 켜기 (WSL). 바탕화면의 온트윈.bat이 부른다.
cd ~/ontwin || exit 1
# 이미 켜져 있으면 새로 켜지 않는다(이전 창을 닫아도 WSL 안에서 계속 도는 경우)
if curl -s -o /dev/null -m 2 http://localhost:8501/ow/; then
  echo "  온트윈이 이미 켜져 있어요. 창만 엽니다."
  sleep 5; exit 0
fi
source .venv/bin/activate
# ERPNext가 응답할 때까지 최대 3분 기다림
for i in $(seq 1 60); do
  curl -s -o /dev/null -m 3 http://localhost:8080/api/method/ping && break
  sleep 3
done
echo "  ERP 준비 완료. 온트윈 서버 시작"
exec python3 -m app serve
