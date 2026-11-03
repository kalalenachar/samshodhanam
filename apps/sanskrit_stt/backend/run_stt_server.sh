#!/usr/bin/env bash
echo "============================================================"
echo "Samshodhana Sanskrit Speech-to-Text Service"
echo "Configured to use Central Cloud STT API:"
echo "http://localhost:5001/api/v1/stt"
echo "============================================================"
echo "Starting Telegram STT Bot..."
python3 telegram_bot.py
