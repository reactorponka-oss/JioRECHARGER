#!/bin/bash
set -e

echo "📦 Installing dependencies..."
pip install --no-cache-dir -r requirements.txt

echo "🤖 Starting bot..."
python bot.py
