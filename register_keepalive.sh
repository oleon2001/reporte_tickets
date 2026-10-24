#!/bin/bash
# Mantiene vivo el listener de registro de integrantes (telegram_register.py).
# Si el proceso no está corriendo, lo relanza en segundo plano.
DIR="/home/cpgadmin/script_reporte_tickeria"
cd "$DIR" || exit 1

if ! pgrep -f "telegram_register.py --listen" >/dev/null 2>&1; then
    echo "[$(date '+%F %T')] listener ausente; reiniciando..." >> "$DIR/logs/register.log"
    setsid "$DIR/venv/bin/python3" -u "$DIR/telegram_register.py" --listen 2592000 \
        >> "$DIR/logs/register.log" 2>&1 < /dev/null &
fi
