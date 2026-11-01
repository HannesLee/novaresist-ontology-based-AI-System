#!/bin/bash
# 온트윈 서버 켜기 (WSL). 바탕화면의 온트윈.bat이 부른다.
cd ~/ontwin || exit 1
source .venv/bin/activate
# ERPNext가 응답할 때까지 최대 3분 기다림
for i in $(seq 1 60); do
  curl -s -o /dev/null -m 3 http://localhost:8080/api/method/ping && break
  sleep 3
done
exec python3 -m app serve
