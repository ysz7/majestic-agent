#!/usr/bin/env bash
set -e

echo "Installing Majestic..."

# Check Python 3.11+
python3 --version | grep -E "3\.(1[1-9]|[2-9][0-9])" || { echo "Python 3.11+ required"; exit 1; }

# Install
pip install -e . --quiet

echo "✓ Majestic installed. Run 'majestic setup' to get started."
