#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile app.py
python3 app.py
