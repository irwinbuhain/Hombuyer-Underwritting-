#!/bin/bash
# setup.sh — One-time setup for HomeBuyer+ redfin-comps skill
# Run: bash setup.sh
set -e

echo "🔧 Setting up HomeBuyer+ redfin-comps dependencies..."

# 1. Check for a usable Python 3.9+
PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" &>/dev/null; then
        VER=$("$candidate" --version 2>&1 | awk '{print $2}')
        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 9 ]; then
            PYTHON="$candidate"
            echo "✅ Found Python: $PYTHON ($VER)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo ""
    echo "❌ Python 3.9+ not found. Please install Python first:"
    echo "   brew install python@3.12"
    echo "   OR download from https://www.python.org/downloads/"
    echo ""
    echo "If you don't have Homebrew, install it first:"
    echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# 2. Create a virtual environment
ENV_DIR="$(dirname "$0")/.venv"
if [ ! -d "$ENV_DIR" ]; then
    echo "📦 Creating virtual environment at .venv..."
    "$PYTHON" -m venv "$ENV_DIR"
else
    echo "✅ Virtual environment already exists at .venv"
fi

# 3. Install dependencies
echo "📥 Installing Python packages..."
"$ENV_DIR/bin/pip" install --quiet --upgrade pip
"$ENV_DIR/bin/pip" install --quiet firecrawl-py geopy python-dotenv requests

echo ""
echo "✅ All dependencies installed!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NEXT: Fill in your API keys in .env"
echo "    FIRECRAWL_API_KEY=  → get at https://firecrawl.dev"
echo "    GOOGLE_MAPS_API_KEY= → optional, improves geocoding"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  THEN run comps like this:"
echo '  .venv/bin/python redfin-comps/scripts/fetch_redfin_comps.py \'
echo '    --address "3456 Quilliams Rd, Cleveland Heights, OH 44121" \'
echo '    --lookback-days 180 --radius-miles 1.0'
echo ""
