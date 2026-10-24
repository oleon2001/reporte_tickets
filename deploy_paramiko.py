"""
Despliegue del reporte de tickets hacia el servidor Linux vía SSH/SFTP.

Usa paramiko (autenticación por contraseña, sin depender de PuTTY/OpenSSH
interactivo). Reemplaza a deploy.ps1 / deploy_with_putty.ps1 en entornos donde
no hay plink/pscp ni sshpass.

Uso:
    python deploy_paramiko.py --recon      # solo inspecciona el servidor
    python deploy_paramiko.py --deploy     # sube archivos y configura (venv+cron)
    python deploy_paramiko.py --deploy --no-cron
"""
import argparse
import datetime
import os
import posixpath
import sys

import paramiko

SERVER = "10.48.63.60"
USER = "cpgadmin"
PASSWORD = "Cpgretail01"
REMOTE = "/home/cpgadmin/script_reporte_tickeria"
VENV = posixpath.join(REMOTE, "venv")
LOGS = posixpath.join(REMOTE, "logs")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES = [
    "main.py",
    "config.py",
    "glpi_db.py",
    "charts.py",
    "telegram_client.py",
    "telegram_register.py",
    "test_local.py",
    "requirements.txt",
    ".env",
    "deploy_server.sh",
    "register_keepalive.sh",
    "setup_register_cron.sh",
    "telegram_members.json.example",
]

CRON_CMD = (
    f"0 */6 * * * cd {REMOTE} && {VENV}/bin/python3 {REMOTE}/main.py --once "
    f">> {LOGS}/cron.log 2>&1"
)


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        SERVER, username=USER, password=PASSWORD,
        timeout=25, look_for_keys=False, allow_agent=False,
    )
    return client


def run(client, cmd, timeout=900):
    _stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def show(title, rc, out, err):
    print(f"\n$ {title}")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print("STDERR:", err.rstrip())
    print(f"[exit={rc}]")


def recon(client):
    for cmd in (
        "hostname; whoami; uname -a",
        "python3 --version; which python3",
        f"ls -la {REMOTE} 2>/dev/null || echo 'NO EXISTE {REMOTE}'",
        f"test -d {VENV} && echo 'venv EXISTE' || echo 'venv NO EXISTE'",
        "crontab -l 2>/dev/null || echo 'SIN CRONTAB'",
    ):
        rc, out, err = run(client, cmd)
        show(cmd, rc, out, err)


def ensure_remote_dir(sftp):
    parts = REMOTE.strip("/").split("/")
    path = ""
    for part in parts:
        path = f"{path}/{part}"
        try:
            sftp.stat(path)
        except IOError:
            sftp.mkdir(path)


def upload(client):
    sftp = client.open_sftp()
    ensure_remote_dir(sftp)
    for name in FILES:
        local = os.path.join(BASE_DIR, name)
        if not os.path.exists(local):
            print(f"  ! falta {name}, se omite")
            continue
        print(f"  -> {name}")
        sftp.put(local, posixpath.join(REMOTE, name))
    sftp.close()
    print("Archivos transferidos.")


def configure(client, do_cron=True):
    steps = [
        f"mkdir -p {REMOTE} {LOGS}",
        f"rm -f {REMOTE}/monitor.py && echo 'monitor.py eliminado (obsoleto)'",
        f"rm -rf {REMOTE}/__pycache__",
        f"cd {REMOTE} && test -d {VENV} || python3 -m venv {VENV}",
        f"{VENV}/bin/pip install --upgrade pip",
        f"{VENV}/bin/pip install -r {REMOTE}/requirements.txt",
        f"chmod +x {REMOTE}/main.py; chmod 600 {REMOTE}/.env",
    ]
    for cmd in steps:
        rc, out, err = run(client, cmd)
        show(cmd, rc, out, err)
        if rc != 0:
            print("  ERROR en el paso anterior.")
            return False

    if do_cron:
        rc, out, _ = run(client, "crontab -l 2>/dev/null")
        current = out or ""
        if f"{REMOTE}/main.py" in current:
            print("\ncron: ya existe un job para el reporte (no se modifica).")
        else:
            new_cron = (current.rstrip("\n") + "\n" + CRON_CMD + "\n").lstrip("\n")
            cmd = f"crontab - <<'CRON_EOF'\n{new_cron}CRON_EOF"
            rc, out, err = run(client, cmd)
            show("instalar cron (cada 6h)", rc, out, err)

    return True


def smoke_test(client):
    cmd = f"cd {REMOTE} && {VENV}/bin/python3 main.py --once --mock --dry-run"
    rc, out, err = run(client, cmd)
    show("prueba (mock, sin envío)", rc, out[-1500:], err[-800:])
    return rc == 0


def main():
    parser = argparse.ArgumentParser(description="Despliegue SSH/SFTP del reporte de tickets")
    parser.add_argument("--recon", action="store_true", help="solo inspecciona el servidor")
    parser.add_argument("--deploy", action="store_true", help="sube y configura")
    parser.add_argument("--no-cron", action="store_true", help="no instalar/actualizar cron")
    parser.add_argument("--skip-tests", action="store_true", help="no correr la prueba mock")
    parser.add_argument("--real", action="store_true", help="ejecuta el reporte real (envía a Telegram)")
    parser.add_argument("--register", type=int, default=0, metavar="SEGUNDOS",
                        help="publica el botón de registro y escucha N s en segundo plano")
    args = parser.parse_args()

    if not (args.recon or args.deploy or args.real or args.register):
        parser.error("indica --recon, --deploy, --real o --register")

    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] Conectando a {USER}@{SERVER}...")
    client = connect()
    print("Conectado.")
    try:
        if args.recon:
            recon(client)
        if args.deploy:
            print("\n=== SUBIENDO ARCHIVOS ===")
            upload(client)
            print("\n=== CONFIGURANDO SERVIDOR ===")
            ok = configure(client, do_cron=not args.no_cron)
            if ok and not args.skip_tests:
                print("\n=== PRUEBA ===")
                smoke_test(client)
        if args.real:
            print("\n=== REPORTE REAL (envía a Telegram) ===")
            cmd = f"cd {REMOTE} && {VENV}/bin/python3 main.py --once"
            _rc, out, err = run(client, cmd)
            show("main.py --once", _rc, out[-2000:], err[-1500:])
        if args.register:
            print("\n=== BOTÓN DE REGISTRO ===")
            rc, out, err = run(
                client, f"cd {REMOTE} && {VENV}/bin/python3 telegram_register.py --post"
            )
            show("telegram_register.py --post", rc, out, err)
            print("\n=== LISTENER (segundo plano) ===")
            cmd = (f"cd {REMOTE} && nohup {VENV}/bin/python3 telegram_register.py "
                   f"--listen {args.register} >> {LOGS}/register.log 2>&1 & echo PID $!")
            rc, out, err = run(client, cmd)
            show(f"listener {args.register}s", rc, out, err)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
