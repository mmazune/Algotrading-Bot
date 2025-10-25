#!/usr/bin/env bash
# AXFL daily runner wrapper for systemd
set -Eeuo pipefail

# Resolve repo root (script lives in repo/scripts)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Load environment from /etc/axfl/axfl.env if present
if [[ -f /etc/axfl/axfl.env ]]; then
  # Export all sourced vars
  set -a
  # shellcheck disable=SC1091
  source /etc/axfl/axfl.env
  set +a
fi

# Prefer local virtualenv if present
if [[ -f ".venv/bin/activate" ]]; then
  echo "[axfl] activating venv at ${REPO_DIR}/.venv" >&2
  # shellcheck disable=SC1091
  . ".venv/bin/activate"
else
  echo "[axfl] .venv not found; using system python" >&2
fi

# Unbuffer Python output so journald gets lines immediately
export PYTHONUNBUFFERED=1

echo "[axfl] starting daily runner..." >&2
exec python -m axfl.cli daily-runner --cfg axfl/config/sessions.yaml --profile portfolio
