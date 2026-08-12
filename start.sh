#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DISCORD_TOKEN:-}" ]]; then
  echo "خطأ: عرّف DISCORD_TOKEN قبل التشغيل."
  echo "مثال: export DISCORD_TOKEN='توكن_البوت'"
  exit 1
fi

python3 bot.py