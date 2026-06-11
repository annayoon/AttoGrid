#!/bin/bash
# AttoGrid 사내 서버 설치 스크립트
#
# 사용법:
#   cd /path/to/dwg
#   bash deploy/setup.sh
#
# 수행 작업:
#   1. Python 가상환경 + 의존성 설치
#   2. Ollama 설치 + 모델 다운로드
#   3. systemd 서비스 등록
#   4. nginx 리버스 프록시 설정
#
# 요구 사항:
#   - Ubuntu 20.04+ / CentOS 8+ / RHEL 8+
#   - Python 3.10+
#   - sudo 권한

set -e

# ── 색상 출력 ─────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'
ok()   { echo -e "${GREEN}✔${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✘ $1${NC}"; exit 1; }

echo -e "\n${BOLD}AttoGrid 서버 설치${NC} (by ATTO Research)\n"

# ── 경로 설정 ─────────────────────────────────────────────────────
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$(whoami)}"
PORT=5000

info "설치 경로: $INSTALL_DIR"
info "서비스 사용자: $SERVICE_USER"

# ── libredwg (dwgread) ───────────────────────────────────────────
echo -e "\n${BOLD}[0/4] libredwg 설치 (DWG 파일 읽기)${NC}"
if command -v dwgread &>/dev/null; then
    ok "dwgread 이미 설치됨: $(dwgread --version 2>&1 | head -1)"
else
    info "libredwg 소스 빌드 중... (EPEL 미포함 — 약 1분)"
    if [ "$EUID" -eq 0 ]; then
        dnf install -y autoconf automake libtool gcc make pkg-config 2>&1 | tail -2
    fi
    LIBREDWG_VER="0.12.5"
    LIBREDWG_DIR="/tmp/libredwg-${LIBREDWG_VER}"
    curl -sL "https://ftp.gnu.org/gnu/libredwg/libredwg-${LIBREDWG_VER}.tar.xz" \
         -o /tmp/libredwg.tar.xz
    tar xf /tmp/libredwg.tar.xz -C /tmp
    cd "$LIBREDWG_DIR"
    ./configure --disable-bindings --disable-python 2>&1 | tail -2
    make -j"$(nproc)" 2>&1 | tail -2
    [ "$EUID" -eq 0 ] && make install && ldconfig
    cd "$INSTALL_DIR"
    ok "dwgread $(dwgread --version 2>&1 | head -1) 설치 완료"
fi

# ── Python 가상환경 ───────────────────────────────────────────────
echo -e "\n${BOLD}[1/4] Python 환경 설정${NC}"
if [ ! -d "$INSTALL_DIR/.venv" ]; then
    info "가상환경 생성..."
    python3 -m venv "$INSTALL_DIR/.venv"
fi
source "$INSTALL_DIR/.venv/bin/activate"
info "패키지 설치..."
pip install -q --upgrade pip
pip install -q flask ezdxf matplotlib
ok "Python 환경 완료"

# ── Ollama ────────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/4] Ollama 설치${NC}"
if command -v ollama &>/dev/null; then
    ok "Ollama 이미 설치됨: $(ollama --version 2>/dev/null | head -1)"
else
    info "Ollama 설치 중..."
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama 설치 완료"
fi

# Ollama 서비스 시작 (백그라운드)
systemctl is-active --quiet ollama 2>/dev/null || {
    info "Ollama 서비스 시작..."
    systemctl enable --now ollama 2>/dev/null || ollama serve &>/dev/null &
    sleep 2
}

# 모델 선택
echo ""
echo "  번역 모델을 선택하세요:"
echo "  1) qwen2.5:14b  — 추천 (10GB, 품질·속도 균형)"
echo "  2) qwen2.5:32b  — 고품질 (20GB, 느림)"
echo "  3) qwen2.5:7b   — 경량 (5GB, 빠름)"
echo "  4) 건너뜀       — 나중에 수동으로 설치"
read -p "  선택 [1]: " MODEL_CHOICE
MODEL_CHOICE="${MODEL_CHOICE:-1}"

case "$MODEL_CHOICE" in
    1) MODEL="qwen2.5:14b"  ;;
    2) MODEL="qwen2.5:32b"  ;;
    3) MODEL="qwen2.5:7b"   ;;
    4) MODEL=""; warn "모델 설치 건너뜀. 나중에: ollama pull qwen2.5:14b" ;;
    *) MODEL="qwen2.5:14b"  ;;
esac

if [ -n "$MODEL" ]; then
    info "모델 다운로드: $MODEL (시간이 걸릴 수 있습니다)"
    ollama pull "$MODEL"
    ok "모델 준비 완료: $MODEL"
fi

# ── systemd 서비스 ────────────────────────────────────────────────
echo -e "\n${BOLD}[3/4] systemd 서비스 등록${NC}"

if [ "$EUID" -ne 0 ]; then
    warn "root 권한이 없어 systemd 설정을 건너뜁니다."
    warn "나중에 sudo로 실행하거나 수동으로 설치하세요:"
    warn "  sudo bash deploy/setup.sh"
else
    SERVICE_FILE="/etc/systemd/system/attogrid.service"
    sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        -e "s|__SERVICE_USER__|$SERVICE_USER|g" \
        "$INSTALL_DIR/deploy/attogrid.service" > "$SERVICE_FILE"

    systemctl daemon-reload
    systemctl enable attogrid
    systemctl restart attogrid
    sleep 2

    if systemctl is-active --quiet attogrid; then
        ok "attogrid 서비스 실행 중"
    else
        warn "서비스 시작 실패. 로그 확인: journalctl -u attogrid -n 20"
    fi
fi

# ── nginx ─────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/4] nginx 리버스 프록시${NC}"

if ! command -v nginx &>/dev/null; then
    warn "nginx가 설치되지 않았습니다."
    if [ "$EUID" -eq 0 ]; then
        read -p "  nginx를 설치할까요? [Y/n]: " INSTALL_NGINX
        if [[ "${INSTALL_NGINX:-Y}" =~ ^[Yy]$ ]]; then
            if command -v apt-get &>/dev/null; then
                apt-get install -y nginx -q
            elif command -v yum &>/dev/null; then
                yum install -y nginx -q
            fi
            ok "nginx 설치 완료"
        fi
    fi
fi

if command -v nginx &>/dev/null && [ "$EUID" -eq 0 ]; then
    NGINX_CONF="/etc/nginx/sites-available/attogrid"
    sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        "$INSTALL_DIR/deploy/nginx.conf" > "$NGINX_CONF"

    # sites-enabled 심볼릭 링크
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/attogrid 2>/dev/null || true
    # default 비활성화 (포트 80 충돌 방지)
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

    nginx -t && systemctl reload nginx
    ok "nginx 설정 완료"
elif command -v nginx &>/dev/null && [ "$EUID" -ne 0 ]; then
    warn "nginx 설정은 root 권한이 필요합니다. 나중에:"
    warn "  sudo bash deploy/setup.sh"
fi

# ── 완료 ─────────────────────────────────────────────────────────
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "서버_IP")
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  설치 완료!${NC}"
echo ""
echo -e "  접속 주소:  ${BOLD}http://${SERVER_IP}${NC}  (nginx)"
echo -e "  직접 접속:  http://${SERVER_IP}:${PORT}  (Flask)"
echo ""
echo "  서비스 관리:"
echo "    sudo systemctl status  attogrid"
echo "    sudo systemctl restart attogrid"
echo "    sudo journalctl -u attogrid -f   (로그)"
echo ""
if [ -n "$MODEL" ]; then
echo "  Ollama 번역: 번역 탭 → '${MODEL}' 선택"
fi
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
