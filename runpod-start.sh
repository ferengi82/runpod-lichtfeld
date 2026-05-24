#!/usr/bin/env bash
set -Eeuo pipefail

LOG_DIR="${RUNPOD_LOG_DIR:-/workspace/logs}"
mkdir -p "$LOG_DIR" /workspace/data /workspace/output /run/sshd
MAIN_LOG="$LOG_DIR/runpod-start.log"
SERVICES_LOG="$LOG_DIR/services.log"
GPU_LOG="$LOG_DIR/gpu-monitor.log"
CREDS_FILE="$LOG_DIR/credentials.txt"

# Mirror startup output to stdout and a persistent log file.
exec > >(tee -a "$MAIN_LOG") 2>&1

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

random_password() {
  tr -dc 'A-Za-z0-9_@%+=:.,-' </dev/urandom | head -c 24 || true
}

print_banner() {
  log "LichtFeld RunPod container starting"
  log "Image CUDA requirement: ${CUDA_VERSION:-12.8.0}; BUILD_CUDA_MIN_SM=${BUILD_CUDA_MIN_SM:-unknown}; LICHTFELD_REF=${LICHTFELD_REF:-unknown}"
  log "Workspace: /workspace"
  log "Logs: $LOG_DIR"
  log "Upstream revision: $(cat /opt/lichtfeld-upstream-revision.txt 2>/dev/null || echo unknown)"
  if command -v nvidia-smi >/dev/null 2>&1; then
    log "nvidia-smi snapshot:"
    nvidia-smi || log "nvidia-smi failed; host driver/GPU may not be available yet"
  else
    log "nvidia-smi not found"
  fi
}

start_gpu_monitor() {
  if [[ "${RUNPOD_ENABLE_GPU_MONITOR:-1}" != "1" ]]; then
    log "GPU monitor disabled"
    return 0
  fi
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    log "GPU monitor skipped: nvidia-smi not available"
    return 0
  fi
  local interval="${RUNPOD_GPU_MONITOR_INTERVAL:-30}"
  (
    while true; do
      echo "===== $(date -Is) ====="
      nvidia-smi || true
      sleep "$interval"
    done
  ) >> "$GPU_LOG" 2>&1 &
  log "GPU monitor started: $GPU_LOG every ${interval}s"
}

start_filebrowser() {
  if [[ "${RUNPOD_ENABLE_FILEBROWSER:-1}" != "1" ]]; then
    log "File Browser disabled"
    return 0
  fi
  if ! command -v filebrowser >/dev/null 2>&1; then
    log "File Browser not installed; skipping"
    return 0
  fi
  local port="${RUNPOD_FILEBROWSER_PORT:-8080}"
  local root="${RUNPOD_FILEBROWSER_ROOT:-/workspace}"
  local db="$LOG_DIR/filebrowser.db"
  local args=(--address 0.0.0.0 --port "$port" --root "$root" --database "$db")

  if [[ "${RUNPOD_FILEBROWSER_NOAUTH:-1}" == "1" ]]; then
    args+=(--noauth)
    log "File Browser auth: disabled (RunPod proxy URL is the access boundary). Set RUNPOD_FILEBROWSER_NOAUTH=0 to use username/password."
  else
    local user="${RUNPOD_FILEBROWSER_USER:-admin}"
    local pass="${RUNPOD_FILEBROWSER_PASSWORD:-}"
    if [[ -z "$pass" ]]; then
      pass="$(random_password)"
      {
        echo "File Browser username: $user"
        echo "File Browser password: $pass"
      } >> "$CREDS_FILE"
      chmod 600 "$CREDS_FILE" || true
    fi
    filebrowser config init --database "$db" >/dev/null 2>&1 || true
    filebrowser config set --database "$db" --address 0.0.0.0 --port "$port" --root "$root" >/dev/null
    filebrowser users add "$user" "$pass" --database "$db" --perm.admin >/dev/null 2>&1 || \
      filebrowser users update "$user" --password "$pass" --database "$db" --perm.admin >/dev/null
    args=(--database "$db")
    log "File Browser auth: enabled, user=$user; password in $CREDS_FILE unless provided via env"
  fi

  filebrowser "${args[@]}" >> "$SERVICES_LOG" 2>&1 &
  log "File Browser started on port $port, root=$root"
}

start_ttyd() {
  if [[ "${RUNPOD_ENABLE_TTYD:-1}" != "1" ]]; then
    log "Web terminal/ttyd disabled"
    return 0
  fi
  if ! command -v ttyd >/dev/null 2>&1; then
    log "ttyd not installed; skipping"
    return 0
  fi
  local port="${RUNPOD_TTYD_PORT:-7681}"
  local credential_args=()
  if [[ -n "${RUNPOD_TTYD_CREDENTIAL:-}" ]]; then
    credential_args=(-c "$RUNPOD_TTYD_CREDENTIAL")
    log "ttyd basic auth enabled via RUNPOD_TTYD_CREDENTIAL"
  else
    log "ttyd basic auth disabled (RunPod proxy URL is the access boundary). Set RUNPOD_TTYD_CREDENTIAL=user:pass to enable."
  fi
  ttyd -p "$port" -i 0.0.0.0 -W "${credential_args[@]}" bash -l >> "$SERVICES_LOG" 2>&1 &
  log "Web terminal started on port $port"
}

start_sshd() {
  if [[ "${RUNPOD_ENABLE_SSHD:-1}" != "1" ]]; then
    log "OpenSSH server disabled"
    return 0
  fi
  if ! command -v sshd >/dev/null 2>&1 && [[ ! -x /usr/sbin/sshd ]]; then
    log "sshd not installed; skipping"
    return 0
  fi

  ssh-keygen -A >/dev/null 2>&1 || true

  local password="${RUNPOD_SSH_PASSWORD:-}"
  if [[ -z "$password" ]]; then
    password="$(random_password)"
    {
      echo "SSH username: root"
      echo "SSH password: $password"
    } >> "$CREDS_FILE"
    chmod 600 "$CREDS_FILE" || true
  fi
  echo "root:${password}" | chpasswd

  cat >/etc/ssh/sshd_config.d/99-runpod.conf <<'EOF'
Port 22
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication yes
PermitEmptyPasswords no
UsePAM yes
X11Forwarding no
AllowTcpForwarding yes
ClientAliveInterval 60
ClientAliveCountMax 3
EOF
  /usr/sbin/sshd -D -e >> "$SERVICES_LOG" 2>&1 &
  log "OpenSSH server started on port 22; credentials in $CREDS_FILE unless RUNPOD_SSH_PASSWORD was provided"
}


start_lichtfeld_webui() {
  if [[ "${RUNPOD_ENABLE_LICHTFELD_WEBUI:-1}" != "1" ]]; then
    log "LichtFeld WebUI disabled"
    return 0
  fi
  local port="${RUNPOD_LICHTFELD_WEBUI_PORT:-7860}"
  local webui_log="$LOG_DIR/lichtfeld-webui.log"
  if [[ ! -d /opt/lichtfeld-webui/backend ]]; then
    log "LichtFeld WebUI files not found; skipping"
    return 0
  fi
  PYTHONPATH=/opt/lichtfeld-webui/backend \
  RUNPOD_WORKSPACE=/workspace \
  LICHTFELD_BIN=/opt/lichtfeld-dist/bin/run_lichtfeld.sh \
  /usr/bin/python3 -m uvicorn lichtfeld_webui.app:app --host 0.0.0.0 --port "$port" >> "$webui_log" 2>&1 &
  log "LichtFeld WebUI started on port $port; log=$webui_log"
}

start_services() {
  print_banner
  start_gpu_monitor
  start_filebrowser
  start_ttyd
  start_sshd
  start_lichtfeld_webui
  log "Service log: $SERVICES_LOG"
  log "GPU log: $GPU_LOG"
  log "Suggested RunPod HTTP ports: File Browser=${RUNPOD_FILEBROWSER_PORT:-8080}, Web terminal=${RUNPOD_TTYD_PORT:-7681}, LichtFeld WebUI=${RUNPOD_LICHTFELD_WEBUI_PORT:-7860}; TCP SSH=22"
}

case "${1:-}" in
  train)
    shift
    print_banner
    log "Starting LichtFeld train: /opt/lichtfeld-dist/bin/run_lichtfeld.sh $*"
    exec /opt/lichtfeld-dist/bin/run_lichtfeld.sh "$@"
    ;;
  lichtfeld)
    shift
    print_banner
    log "Starting LichtFeld: /opt/lichtfeld-dist/bin/run_lichtfeld.sh $*"
    exec /opt/lichtfeld-dist/bin/run_lichtfeld.sh "$@"
    ;;
  version)
    print_banner
    /opt/lichtfeld-dist/bin/run_lichtfeld.sh --help || true
    exit 0
    ;;
  services)
    start_services
    log "Keeping container alive. Use RunPod web terminal or SSH to work in /workspace."
    exec tail -F "$MAIN_LOG" "$SERVICES_LOG" "$GPU_LOG"
    ;;
  bash|sh|"")
    start_services
    log "Opening interactive shell"
    exec "${1:-bash}"
    ;;
  *)
    start_services
    log "Executing custom command: $*"
    exec "$@"
    ;;
esac
