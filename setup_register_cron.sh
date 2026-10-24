#!/bin/bash
# Instala (idempotente) las tareas cron del registro de integrantes:
#   - republicar el botón cada 12 h (el grupo auto-borra los mensajes a las 24 h)
#   - keepalive del listener cada 10 min
set -e

DIR="/home/cpgadmin/script_reporte_tickeria"
KEEP="$DIR/register_keepalive.sh"
PY="$DIR/venv/bin/python3"
LOG="$DIR/logs/register.log"

chmod +x "$KEEP" 2>/dev/null || true
mkdir -p "$DIR/logs"

CUR="$(crontab -l 2>/dev/null || true)"
# Quitar entradas previas nuestras (por marcador o por comando).
CLEAN="$(printf '%s\n' "$CUR" | grep -v -e 'reporte_tickets:' -e 'telegram_register.py --post' -e 'register_keepalive.sh' || true)"

BLOCK="# reporte_tickets: button (republicar botón de altas cada 12 h)
0 */12 * * * cd $DIR && $PY $DIR/telegram_register.py --post >> $LOG 2>&1
# reporte_tickets: keepalive (relanzar listener si se cae)
*/10 * * * * $KEEP >> $LOG 2>&1"

CLEAN="$(printf '%s' "$CLEAN" | sed '/^[[:space:]]*$/d')"
printf '%s\n%s\n' "$CLEAN" "$BLOCK" | crontab -

echo "cron instalado:"
crontab -l | grep -e 'reporte_tickets:' -e 'telegram_register.py --post' -e 'register_keepalive.sh'
