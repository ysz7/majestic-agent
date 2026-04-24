#!/usr/bin/env bash
# Parallax startup — activate venv and launch CLI
cd "$(dirname "$0")"
source .venv/bin/activate
python cli.py
exec bash
