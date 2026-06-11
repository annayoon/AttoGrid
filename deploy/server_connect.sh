#!/bin/bash
# AttoGrid 서버 접속 / 배포 헬퍼
#
# 서버:  10.0.112.254 (Service IP)
# IPMI:  10.0.112.23  (원격 전원/콘솔 관리)
# GW:    10.0.112.1

SERVER="10.0.112.254"
SERVER_USER="root"

case "${1:-}" in
  ssh)
    echo "서버 SSH 접속: $SERVER_USER@$SERVER"
    ssh "$SERVER_USER@$SERVER"
    ;;

  deploy)
    echo "코드 업로드 후 설치 실행..."
    # 소스 복사 (git clone이 불가한 경우 rsync 사용)
    rsync -avz --exclude='.venv' --exclude='__pycache__' \
          --exclude='uploads' --exclude='*.json' --exclude='*.dwg' \
          "$(dirname "$0")/../" \
          "$SERVER_USER@$SERVER:/opt/attogrid/"
    # 원격 설치 스크립트 실행
    ssh "$SERVER_USER@$SERVER" "cd /opt/attogrid && bash deploy/setup.sh"
    ;;

  status)
    echo "서비스 상태 확인..."
    ssh "$SERVER_USER@$SERVER" \
      "systemctl status attogrid nginx --no-pager -l | head -30"
    ;;

  log)
    echo "실시간 로그 (Ctrl+C로 종료)..."
    ssh "$SERVER_USER@$SERVER" "journalctl -u attogrid -f"
    ;;

  restart)
    echo "서비스 재시작..."
    ssh "$SERVER_USER@$SERVER" \
      "systemctl restart attogrid && systemctl status attogrid --no-pager"
    ;;

  open)
    echo "브라우저 열기: http://$SERVER"
    open "http://$SERVER" 2>/dev/null || \
    xdg-open "http://$SERVER" 2>/dev/null || \
    echo "브라우저에서 http://$SERVER 를 여세요"
    ;;

  *)
    echo "사용법: $0 {ssh|deploy|status|log|restart|open}"
    echo ""
    echo "  ssh      — 서버 SSH 접속"
    echo "  deploy   — 코드 업로드 + 설치"
    echo "  status   — 서비스 상태 확인"
    echo "  log      — 실시간 로그"
    echo "  restart  — 서비스 재시작"
    echo "  open     — 브라우저로 앱 열기 (http://$SERVER)"
    ;;
esac
