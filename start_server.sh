#!/bin/bash
# AttoGrid 웹 서버 — 사내 서버 배포용
#
# 사용법:
#   ./start_server.sh                  # 기본 (0.0.0.0:5000)
#   ./start_server.sh --port 8080      # 포트 변경
#   ./start_server.sh --daemon         # 백그라운드 실행
#
# 사내 접속: http://<서버_IP>:5000
# Ollama 설치 (1회):
#   curl -fsSL https://ollama.com/install.sh | sh
#   ollama pull qwen2.5:14b

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 가상환경 활성화
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Flask 설치 확인
python -c "import flask" 2>/dev/null || {
    echo "Flask 설치 중..."
    pip install flask -q
}

# 데몬 모드 처리
DAEMON=0
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--daemon" ]; then
        DAEMON=1
    else
        ARGS+=("$arg")
    fi
done

if [ $DAEMON -eq 1 ]; then
    LOG="$SCRIPT_DIR/attogrid_web.log"
    nohup python web_app.py "${ARGS[@]}" > "$LOG" 2>&1 &
    echo "AttoGrid 웹 서버 백그라운드 시작 (PID: $!)"
    echo "로그: $LOG"
    echo "접속: http://$(hostname -I | awk '{print $1}'):5000"
else
    python web_app.py "${ARGS[@]}"
fi
