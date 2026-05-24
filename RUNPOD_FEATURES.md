# RunPod helper services

The image starts helper services by default via `runpod-start.sh services`.

## Ports

- `8080`: File Browser for uploads/downloads under `/workspace`
- `7681`: ttyd web terminal (`bash -l`)
- `7860`: LichtFeld Studio WebUI for dataset selection, training, logs and GPU status
- `22`: OpenSSH server

In RunPod, expose HTTP ports `8080`, `7681` and `7860`. Expose TCP port `22` if you want native SSH.

## Logs

Logs are written under `/workspace/logs`:

- `runpod-start.log`: startup banner, environment summary, service status
- `services.log`: File Browser, ttyd and sshd output
- `gpu-monitor.log`: periodic `nvidia-smi` snapshots
- `lichtfeld-webui.log`: LichtFeld WebUI backend output
- `credentials.txt`: generated passwords when password auth is enabled/generated

## Environment variables

- `RUNPOD_ENABLE_FILEBROWSER=1|0`
- `RUNPOD_FILEBROWSER_PORT=8080`
- `RUNPOD_FILEBROWSER_ROOT=/workspace`
- `RUNPOD_FILEBROWSER_NOAUTH=1|0`
- `RUNPOD_FILEBROWSER_USER=admin`
- `RUNPOD_FILEBROWSER_PASSWORD=<password>`
- `RUNPOD_ENABLE_TTYD=1|0`
- `RUNPOD_TTYD_PORT=7681`
- `RUNPOD_TTYD_CREDENTIAL=user:password` for optional ttyd basic auth
- `RUNPOD_ENABLE_SSHD=1|0`
- `RUNPOD_SSH_PASSWORD=<password>`; if omitted, a random root password is written to `/workspace/logs/credentials.txt`
- `RUNPOD_ENABLE_GPU_MONITOR=1|0`
- `RUNPOD_GPU_MONITOR_INTERVAL=30`
- `RUNPOD_ENABLE_LICHTFELD_WEBUI=1|0`
- `RUNPOD_LICHTFELD_WEBUI_PORT=7860`
- `RUNPOD_LOG_DIR=/workspace/logs`

## Commands

- default: `services` starts helper services and keeps the container alive
- `version`: prints image/LichtFeld info and LichtFeld help
- `lichtfeld <args>`: runs `/opt/lichtfeld-dist/bin/run_lichtfeld.sh <args>`
- `train <args>`: alias for the same LichtFeld runner
- `bash`: starts helper services and opens an interactive shell
