#!/bin/bash
echo "Starting Samshodhana Sanskrit STT Telegram Bot..."

if [ -f "../../../venv/bin/activate" ]; then
    source ../../../venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

python3 telegram_bot.py
