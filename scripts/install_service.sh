#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="hydrex-form-assistant.service"
SERVICE_TEMPLATE="deploy/systemd/hydrex-form-assistant.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
WORKDIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$USER}"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo ./scripts/install_service.sh"
  exit 1
fi

if [[ ! -f "$SERVICE_TEMPLATE" ]]; then
  echo "Missing service template: $SERVICE_TEMPLATE"
  exit 1
fi

cp "$SERVICE_TEMPLATE" "$SERVICE_PATH"
sed -i "s|__SERVICE_USER__|${SERVICE_USER}|g" "$SERVICE_PATH"
sed -i "s|__WORKDIR__|${WORKDIR}|g" "$SERVICE_PATH"

systemctl daemon-reload
systemctl enable hydrex-form-assistant
systemctl restart hydrex-form-assistant

systemctl status hydrex-form-assistant --no-pager
