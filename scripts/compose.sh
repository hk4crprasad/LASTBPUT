#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -z "${DOCKER_HOST:-}" ] && ! docker info >/dev/null 2>&1; then
  command -v podman >/dev/null || { echo 'Docker access or rootless Podman is required.' >&2; exit 1; }
  mkdir -p .local
  task_socket="$(pwd)/.local/greenops-podman.sock"
  if ! DOCKER_HOST="unix://$task_socket" docker info >/dev/null 2>&1; then
    rm -f "$task_socket"
    if command -v setsid >/dev/null 2>&1; then
      setsid nohup podman system service --time=0 "unix://$task_socket" > .local/podman-api.log 2>&1 </dev/null &
    else
      nohup podman system service --time=0 "unix://$task_socket" > .local/podman-api.log 2>&1 </dev/null &
    fi
    task_attempt=0
    while ! DOCKER_HOST="unix://$task_socket" docker info >/dev/null 2>&1 && [ "$task_attempt" -lt 20 ]; do sleep 0.2; task_attempt=$((task_attempt+1)); done
  fi
  DOCKER_HOST="unix://$task_socket"
  export DOCKER_HOST
fi
exec docker compose "$@"
