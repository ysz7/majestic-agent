#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"

echo ""
echo "  Installing Majestic Agent..."
echo "  Repo: $REPO_DIR"
echo ""

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "  ✗ python3 not found. Install Python 3.11+ first."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "  ✗ Python $PY_VERSION found, need 3.11+"
    exit 1
fi
echo "  ✓ Python $PY_VERSION"

# ── Virtual environment ────────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
echo "  ✓ Virtual environment: $VENV_DIR"

# ── Dependencies ───────────────────────────────────────────────────────────────
echo "  Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$REPO_DIR/requirements.txt"

# ── Install package (registers `majestic` command) ────────────────────────────
echo "  Registering majestic command..."
pip install --quiet -e "$REPO_DIR"

# ── Verify ────────────────────────────────────────────────────────────────────
if command -v majestic &>/dev/null; then
    echo "  ✓ majestic command available"
else
    VENV_BIN="$VENV_DIR/bin"
    echo "  ✓ majestic installed at $VENV_BIN/majestic"
    echo ""
    echo "  Add to your shell profile to use globally:"
    echo "    export PATH=\"$VENV_BIN:\$PATH\""
fi

echo ""
echo "  ✓ Installation complete. Run: majestic setup"
echo ""

# ── Optional: systemd service for gateway auto-start ──────────────────────────
if [[ "${1:-}" == "--service" ]]; then
    SERVICE_FILE="$HOME/.config/systemd/user/majestic.service"
    mkdir -p "$(dirname "$SERVICE_FILE")"
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Majestic Agent Gateway
After=network.target

[Service]
Type=simple
ExecStart=$VENV_DIR/bin/majestic gateway start
Restart=on-failure
RestartSec=10
Environment=MAJESTIC_HOME=%h/.majestic-agent

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable majestic
    systemctl --user start majestic
    echo "  ✓ systemd service enabled: majestic.service"
    echo "    systemctl --user status majestic"
    echo ""
fi
