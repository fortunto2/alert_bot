#!/bin/bash
# Setup cron job for multi-crypto crash monitor

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
UV_PATH="/home/rustam/.local/bin/uv"
MONITOR_SCRIPT="$SCRIPT_DIR/multi_crash_monitor.py"
LOG_FILE="/tmp/multi_crypto_monitor.log"

echo "=================================================="
echo "Multi-Crypto Crash Monitor - Cron Setup"
echo "=================================================="
echo ""
echo "Script location: $MONITOR_SCRIPT"
echo "UV path: $UV_PATH"
echo "Log file: $LOG_FILE"
echo ""

# Check if uv is installed
if [ ! -f "$UV_PATH" ]; then
    echo "⚠️  WARNING: uv not found at $UV_PATH"
    echo ""
    echo "Please install uv first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    exit 1
fi

# Check if .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "⚠️  WARNING: .env file not found!"
    echo ""
    echo "Please create .env file first:"
    echo "  cd $SCRIPT_DIR"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    exit 1
fi

# Test the script
echo "🔍 Testing multi-crypto monitor..."
cd "$SCRIPT_DIR"
if $UV_PATH run python multi_crash_monitor.py; then
    echo "✅ Test successful!"
else
    echo "❌ Test failed. Please fix errors before setting up cron."
    exit 1
fi

echo ""
echo "=================================================="
echo "Cron Configuration"
echo "=================================================="
echo ""
echo "The following line will be added to your crontab:"
echo ""
echo "# Multi-Crypto Crash Monitor - runs every hour"
echo "0 * * * * cd $SCRIPT_DIR && $UV_PATH run python multi_crash_monitor.py >> $LOG_FILE 2>&1"
echo ""
read -p "Add this to crontab? [y/N] " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Backup current crontab
    crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null

    # Add new job (check if not already exists - remove both old and new monitor entries)
    (crontab -l 2>/dev/null | grep -v "crash_monitor.py" | grep -v "multi_crash_monitor.py"; echo "# Multi-Crypto Crash Monitor - runs every hour"; echo "0 * * * * cd $SCRIPT_DIR && $UV_PATH run python multi_crash_monitor.py >> $LOG_FILE 2>&1") | crontab -

    echo "✅ Cron job added!"
    echo ""
    echo "To view your crontab:"
    echo "  crontab -l"
    echo ""
    echo "To view logs:"
    echo "  tail -f $LOG_FILE"
    echo ""
    echo "To remove the job:"
    echo "  crontab -e"
    echo "  (then delete the multi_crash_monitor line)"
else
    echo "Cancelled."
    echo ""
    echo "To add manually, run:"
    echo "  crontab -e"
    echo ""
    echo "And add this line:"
    echo "  0 * * * * cd $SCRIPT_DIR && $UV_PATH run python multi_crash_monitor.py >> $LOG_FILE 2>&1"
fi

echo ""
echo "=================================================="
echo "Setup complete!"
echo "=================================================="
