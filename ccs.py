#!/usr/bin/env python3

import os
import sys
import json
import time
import uuid
import socket
import hashlib
import secrets
import getpass
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import psutil
import dns.resolver

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn


# ============================================================
# CCS ENTERPRISE
# CHITRAL CYBER SQUAD
# Defensive Security & Incident Investigation Platform
# ============================================================

APP_NAME = "CHITRAL CYBER SQUAD"
APP = "CCS Enterprise Investigator"
VERSION = "3.0.0"

BASE = Path.home() / ".ccs-enterprise"
CONFIG = BASE / "config.json"
AUDIT = BASE / "audit.log"
CASES = BASE / "cases"
EVIDENCE = BASE / "evidence"

CONTACT = "ChitralCyberSquad@gmail.com"

console = Console()


# ============================================================
# UI
# ============================================================

def banner():
    console.clear()

    logo = r"""
 ██████╗ ██████╗ ███████╗
██╔════╝██╔════╝ ██╔════╝
██║     ██║      ███████╗
██║     ██║      ╚════██║
╚██████╗╚██████╗ ███████║
 ╚═════╝ ╚═════╝ ╚══════╝

      C H I T R A L   C Y B E R   S Q U A D
              ENTERPRISE INVESTIGATOR
"""

    console.print(
        Panel(
            Text(logo, style="bold cyan"),
            subtitle=f"v{VERSION}  •  Defensive Security",
            border_style="cyan",
        )
    )

    console.print(
        f"[dim]Authorized security investigation platform[/dim]\n"
        f"[dim]{CONTACT}[/dim]\n"
    )


def section(title):
    console.print()
    console.rule(f"[bold cyan]{title}[/bold cyan]")


def ok(msg):
    console.print(f"[bold green][+][/bold green] {msg}")


def info(msg):
    console.print(f"[bold cyan][i][/bold cyan] {msg}")


def warn(msg):
    console.print(f"[bold yellow][!][/bold yellow] {msg}")


def bad(msg):
    console.print(f"[bold red][-][/bold red] {msg}")


# ============================================================
# FILESYSTEM / AUDIT
# ============================================================

def initialize():
    BASE.mkdir(mode=0o700, exist_ok=True)
    CASES.mkdir(mode=0o700, exist_ok=True)
    EVIDENCE.mkdir(mode=0o700, exist_ok=True)

    for p in [BASE, CASES, EVIDENCE]:
        try:
            os.chmod(p, 0o700)
        except Exception:
            pass


def audit(event, details=""):
    initialize()

    stamp = datetime.now(timezone.utc).isoformat()

    with open(AUDIT, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "time": stamp,
                    "event": event,
                    "details": details,
                }
            )
            + "\n"
        )

    try:
        os.chmod(AUDIT, 0o600)
    except Exception:
        pass


# ============================================================
# PASSWORD
# ============================================================

def password_hash(password, salt):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600000,
    )

    return kdf.derive(password.encode()).hex()


def setup_admin():
    initialize()

    if CONFIG.exists():
        return

    section("FIRST-RUN SECURITY SETUP")

    console.print(
        Panel(
            "Create the local CCS administrator.\n"
            "The password is never stored as plaintext.",
            border_style="yellow",
        )
    )

    while True:
        p1 = getpass.getpass("Create CCS admin password: ")
        p2 = getpass.getpass("Repeat password: ")

        if len(p1) < 12:
            bad("Use at least 12 characters.")
            continue

        if p1 != p2:
            bad("Passwords do not match.")
            continue

        break

    salt = secrets.token_bytes(32)

    installation_id = str(uuid.uuid4())

    config = {
        "organization": "ChitralCyberSquad",
        "product": APP,
        "version": VERSION,
        "installation_id": installation_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "password_salt": salt.hex(),
        "password_hash": password_hash(p1, salt),

        # License service can be configured later.
        "license": {
            "mode": "LOCAL_DEVELOPMENT",
            "status": "ACTIVE",
            "license_id": "CCS-DEV",
            "edition": "DEVELOPMENT"
        },

        "settings": {
            "authorized_server_mode": True,
            "terminal_evidence": True
        }
    }

    CONFIG.write_text(
        json.dumps(config, indent=2),
        encoding="utf-8"
    )

    try:
        os.chmod(CONFIG, 0o600)
    except Exception:
        pass

    audit(
        "INITIAL_SETUP",
        f"installation={installation_id}"
    )

    ok("Administrator created.")
    ok(f"Installation ID: {installation_id}")
    ok("Local development license activated.")


def load_config():
    if not CONFIG.exists():
        setup_admin()

    return json.loads(
        CONFIG.read_text(encoding="utf-8")
    )


def authenticate():
    config = load_config()

    section("ADMIN AUTHENTICATION")

    for attempt in range(3):
        password = getpass.getpass("CCS Administrator Password: ")

        salt = bytes.fromhex(
            config["password_salt"]
        )

        supplied = password_hash(password, salt)

        if secrets.compare_digest(
            supplied,
            config["password_hash"]
        ):
            audit("ADMIN_LOGIN", "success")
            ok("Administrator authenticated.")
            return True

        audit("ADMIN_LOGIN", "failed")
        bad(f"Authentication failed ({attempt + 1}/3).")

    audit("ADMIN_LOCKOUT", "three failed attempts")
    bad("Authentication failed.")
    return False


# ============================================================
# LICENSE
# ============================================================

def license_status():
    config = load_config()
    lic = config.get("license", {})

    table = Table(
        title="CCS License",
        border_style="cyan"
    )

    table.add_column("Property")
    table.add_column("Value")

    table.add_row(
        "Status",
        str(lic.get("status"))
    )

    table.add_row(
        "Edition",
        str(lic.get("edition"))
    )

    table.add_row(
        "License ID",
        str(lic.get("license_id"))
    )

    table.add_row(
        "Installation",
        config.get("installation_id", "")
    )

    console.print(table)

    console.print(
        "\n[dim]Production licensing will use a signed "
        "license-service response rather than embedding "
        "your private signing key in CCS.[/dim]"
    )


# ============================================================
# TARGET NORMALIZATION
# ============================================================

def normalize_url(target):
    target = target.strip()

    if not target.startswith(("http://", "https://")):
        target = "https://" + target

    return target.rstrip("/")


def hostname_from_target(target):
    parsed = urlparse(normalize_url(target))
    return parsed.hostname


# ============================================================
# DNS
# ============================================================

def dns_lookup(host):
    section("DNS INTELLIGENCE")

    record_types = [
        "A",
        "AAAA",
        "MX",
        "NS",
        "TXT",
        "CNAME",
        "SOA",
        "CAA",
    ]

    table = Table(border_style="cyan")
    table.add_column("Record")
    table.add_column("Value")

    for record in record_types:
        try:
            answers = dns.resolver.resolve(
                host,
                record,
                lifetime=4
            )

            for answer in answers:
                table.add_row(
                    record,
                    str(answer)
                )

        except Exception:
            pass

    console.print(table)


# ============================================================
# HTTP
# ============================================================

def web_probe(target):
    section("WEB INVESTIGATION")

    url = normalize_url(target)

    try:
        r = requests.get(
            url,
            timeout=12,
            allow_redirects=True,
            headers={
                "User-Agent":
                "CCS-Enterprise-Investigator/3.0"
            }
        )

        table = Table(border_style="cyan")
        table.add_column("Property")
        table.add_column("Value")

        table.add_row("Requested", url)
        table.add_row("Final URL", r.url)
        table.add_row("Status", str(r.status_code))
        table.add_row(
            "Content-Type",
            r.headers.get("Content-Type", "unknown")
        )
        table.add_row(
            "Server",
            r.headers.get("Server", "not disclosed")
        )
        table.add_row(
            "Content-Length",
            r.headers.get("Content-Length", "unknown")
        )

        console.print(table)

        section("SECURITY HEADERS")

        headers = [
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "X-Frame-Options",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "Permissions-Policy",
        ]

        ht = Table(border_style="cyan")
        ht.add_column("Header")
        ht.add_column("Status")
        ht.add_column("Value")

        for h in headers:
            value = r.headers.get(h)

            if value:
                ht.add_row(
                    h,
                    "[green]PRESENT[/green]",
                    value
                )
            else:
                ht.add_row(
                    h,
                    "[yellow]MISSING[/yellow]",
                    "-"
                )

        console.print(ht)

        return r

    except Exception as e:
        bad(f"HTTP investigation failed: {e}")
        return None


# ============================================================
# PUBLIC FILE INSPECTOR
# ============================================================

COMMON_PUBLIC_FILES = [
    "/robots.txt",
    "/sitemap.xml",
    "/security.txt",
    "/.well-known/security.txt",
    "/openapi.json",
    "/swagger.json",
    "/api-docs",
    "/package.json",
    "/composer.json",
    "/config.json",
    "/.env",
    "/.git/HEAD",
]


def public_file_scan(target):
    section("PUBLIC FILE EXPOSURE")

    base = normalize_url(target)

    table = Table(border_style="cyan")
    table.add_column("Path")
    table.add_column("HTTP")
    table.add_column("Type")
    table.add_column("Size")

    found = []

    for path in COMMON_PUBLIC_FILES:
        url = base + path

        try:
            r = requests.get(
                url,
                timeout=8,
                allow_redirects=False,
                headers={
                    "User-Agent":
                    "CCS-Enterprise-Investigator/3.0"
                }
            )

            if r.status_code < 400:

                content_type = r.headers.get(
                    "Content-Type",
                    "unknown"
                )

                size = len(r.content)

                table.add_row(
                    path,
                    str(r.status_code),
                    content_type,
                    str(size)
                )

                found.append(
                    {
                        "path": path,
                        "url": url,
                        "status": r.status_code,
                        "content_type": content_type,
                        "content": r.content,
                        "size": size,
                    }
                )

        except Exception:
            pass

    if found:
        console.print(table)
        return found

    info("No accessible candidate files detected.")
    return []


def inspect_public_file(item):
    section("ADMIN EVIDENCE INSPECTOR")

    console.print(
        Panel(
            f"Resource: {item['url']}\n"
            f"HTTP: {item['status']}\n"
            f"Type: {item['content_type']}\n"
            f"Size: {item['size']} bytes\n"
            f"Access: ADMIN AUTHENTICATED",
            border_style="yellow"
        )
    )

    content = item["content"]

    if len(content) > 100000:
        warn(
            "Large response. Showing first 100,000 bytes."
        )
        content = content[:100000]

    try:
        text = content.decode(
            "utf-8",
            errors="replace"
        )

        console.print(
            Panel(
                text,
                title="FULL EVIDENCE CONTENT",
                border_style="red"
            )
        )

    except Exception:
        console.print(
            Panel(
                content.hex(),
                title="BINARY EVIDENCE",
                border_style="red"
            )
        )

    sha = hashlib.sha256(
        item["content"]
    ).hexdigest()

    console.print(
        f"\n[bold]SHA-256:[/bold] {sha}"
    )

    audit(
        "PUBLIC_EVIDENCE_VIEW",
        item["url"]
    )


# ============================================================
# SERVER INFORMATION
# ============================================================

def server_information():
    section("SERVER INFORMATION")

    table = Table(border_style="cyan")
    table.add_column("Property")
    table.add_column("Value")

    table.add_row(
        "Hostname",
        socket.gethostname()
    )

    table.add_row(
        "Platform",
        sys.platform
    )

    table.add_row(
        "Python",
        sys.version.split()[0]
    )

    table.add_row(
        "CPU",
        str(psutil.cpu_count())
    )

    memory = psutil.virtual_memory()

    table.add_row(
        "Memory",
        f"{memory.total / 1024**3:.2f} GB"
    )

    disk = psutil.disk_usage("/")

    table.add_row(
        "Disk",
        f"{disk.used / disk.total * 100:.1f}% used"
    )

    console.print(table)


# ============================================================
# PROCESSES
# ============================================================

def process_investigation():
    section("RUNNING PROCESSES")

    table = Table(border_style="cyan")

    table.add_column("PID")
    table.add_column("USER")
    table.add_column("NAME")
    table.add_column("COMMAND")

    rows = []

    for proc in psutil.process_iter(
        ["pid", "username", "name", "cmdline"]
    ):
        try:
            data = proc.info

            cmd = " ".join(
                data.get("cmdline") or []
            )

            rows.append(
                (
                    data.get("pid"),
                    data.get("username") or "-",
                    data.get("name") or "-",
                    cmd[:100]
                )
            )

        except Exception:
            pass

    rows.sort(
        key=lambda x: x[0] or 0
    )

    for row in rows[:200]:
        table.add_row(
            str(row[0]),
            row[1],
            row[2],
            row[3]
        )

    console.print(table)

    info(f"Displayed {min(len(rows), 200)} processes.")


# ============================================================
# NETWORK CONNECTIONS
# ============================================================

def network_investigation():
    section("NETWORK CONNECTIONS")

    table = Table(border_style="cyan")

    table.add_column("PID")
    table.add_column("LOCAL")
    table.add_column("REMOTE")
    table.add_column("STATUS")

    count = 0

    try:
        connections = psutil.net_connections(
            kind="inet"
        )

        for c in connections:

            local = (
                f"{c.laddr.ip}:{c.laddr.port}"
                if c.laddr else "-"
            )

            remote = (
                f"{c.raddr.ip}:{c.raddr.port}"
                if c.raddr else "-"
            )

            table.add_row(
                str(c.pid or "-"),
                local,
                remote,
                c.status
            )

            count += 1

            if count >= 200:
                break

        console.print(table)

    except Exception as e:
        bad(f"Could not inspect connections: {e}")


# ============================================================
# SERVICES / SYSTEMD
# ============================================================

def service_investigation():
    section("SERVICES")

    commands = [
        ["systemctl", "--no-pager", "--type=service", "--state=running"],
    ]

    for command in commands:

        if subprocess.run(
            ["which", command[0]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        ).returncode != 0:
            warn(f"{command[0]} not installed.")
            continue

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=15
            )

            console.print(
                Panel(
                    result.stdout[:30000],
                    title="RUNNING SERVICES",
                    border_style="cyan"
                )
            )

        except Exception as e:
            bad(str(e))


# ============================================================
# CRON / SYSTEMD TIMERS
# ============================================================

def scheduled_tasks():
    section("SCHEDULED TASKS")

    if os.geteuid() == 0:
        cron = subprocess.run(
            ["sh", "-c", "cat /etc/crontab 2>/dev/null"],
            capture_output=True,
            text=True
        )

        console.print(
            Panel(
                cron.stdout or "No /etc/crontab content.",
                title="/etc/crontab",
                border_style="cyan"
            )
        )
    else:
        info(
            "Running without root. "
            "Only user-level information is available."
        )

    if subprocess.run(
        ["which", "systemctl"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode == 0:

        try:
            result = subprocess.run(
                [
                    "systemctl",
                    "--no-pager",
                    "list-timers",
                    "--all"
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            console.print(
                Panel(
                    result.stdout[:30000],
                    title="SYSTEMD TIMERS",
                    border_style="cyan"
                )
            )

        except Exception:
            pass


# ============================================================
# LOG INVESTIGATION
# ============================================================

def read_log(path, lines=80):
    p = Path(path)

    if not p.exists():
        warn(f"Not found: {path}")
        return

    if not p.is_file():
        warn(f"Not a file: {path}")
        return

    section(f"LOG: {path}")

    try:
        content = p.read_text(
            encoding="utf-8",
            errors="replace"
        )

        data = content.splitlines()

        console.print(
            Panel(
                "\n".join(data[-lines:]),
                border_style="cyan"
            )
        )

    except PermissionError:
        bad(
            "Permission denied. "
            "Run the authorized investigator with appropriate privileges."
        )

    except Exception as e:
        bad(str(e))


def log_investigation():
    section("COMMON SERVER LOGS")

    candidates = [
        "/var/log/auth.log",
        "/var/log/secure",
        "/var/log/syslog",
        "/var/log/messages",
        "/var/log/nginx/access.log",
        "/var/log/nginx/error.log",
        "/var/log/apache2/access.log",
        "/var/log/apache2/error.log",
    ]

    available = [
        p for p in candidates
        if Path(p).exists()
    ]

    if not available:
        info("No common log paths detected.")
        return

    for i, p in enumerate(available, 1):
        console.print(
            f"[{i}] {p}"
        )

    choice = Prompt.ask(
        "Select log",
        choices=[
            str(i)
            for i in range(1, len(available) + 1)
        ]
    )

    read_log(
        available[int(choice) - 1]
    )


# ============================================================
# KALI TOOLS
# ============================================================

KALI_TOOLS = [
    "nmap",
    "nuclei",
    "httpx",
    "whatweb",
    "nikto",
    "amass",
    "subfinder",
    "curl",
    "openssl",
    "dig",
]


def kali_environment():
    section("KALI TOOLCHAIN")

    table = Table(border_style="cyan")

    table.add_column("Tool")
    table.add_column("Status")
    table.add_column("Location")

    for tool in KALI_TOOLS:

        result = subprocess.run(
            ["which", tool],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            table.add_row(
                tool,
                "[green]AVAILABLE[/green]",
                result.stdout.strip()
            )
        else:
            table.add_row(
                tool,
                "[yellow]NOT INSTALLED[/yellow]",
                "-"
            )

    console.print(table)


def nmap_scan(target):
    section("AUTHORIZED NETWORK ASSESSMENT")

    if subprocess.run(
        ["which", "nmap"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode != 0:
        bad("Nmap is not installed.")
        return

    if not Confirm.ask(
        "Confirm this target is yours/authorized"
    ):
        warn("Network assessment cancelled.")
        return

    console.print(
        "[yellow]Running limited top-port discovery.[/yellow]"
    )

    try:
        result = subprocess.run(
            [
                "nmap",
                "-Pn",
                "--top-ports",
                "100",
                "--open",
                target
            ],
            capture_output=True,
            text=True,
            timeout=180
        )

        console.print(
            Panel(
                result.stdout[:40000],
                title="NMAP RESULT",
                border_style="cyan"
            )
        )

        audit(
            "AUTHORIZED_NMAP",
            target
        )

    except subprocess.TimeoutExpired:
        bad("Nmap timed out.")

    except Exception as e:
        bad(str(e))


# ============================================================
# INCIDENT TIMELINE
# ============================================================

def incident_timeline():
    section("INCIDENT TIMELINE")

    console.print(
        Panel(
            "CCS correlates available evidence into a timeline.\n\n"
            "Evidence categories:\n"
            "  HTTP requests\n"
            "  Log events\n"
            "  File changes\n"
            "  Process activity\n"
            "  Network activity\n"
            "  Configuration changes\n\n"
            "The current foundation records investigation events. "
            "The advanced correlation engine will connect these "
            "events by timestamp, source and relationship.",
            border_style="cyan"
        )
    )


# ============================================================
# SYSTEM MENU
# ============================================================

def system_menu():
    section("SYSTEM / LICENSE")

    license_status()

    console.print()
    console.print(
        f"[dim]CCS version: {VERSION}[/dim]"
    )
    console.print(
        f"[dim]Organization: ChitralCyberSquad[/dim]"
    )
    console.print(
        f"[dim]Contact: {CONTACT}[/dim]"
    )


# ============================================================
# WEB INVESTIGATION FLOW
# ============================================================

def web_investigation():

    target = Prompt.ask(
        "Target domain / URL"
    ).strip()

    if not target:
        return

    host = hostname_from_target(target)

    if not host:
        bad("Invalid target.")
        return

    info(f"Target: {host}")

    dns_lookup(host)

    response = web_probe(target)

    findings = public_file_scan(target)

    if findings:
        section("ADMIN FILE INSPECTOR")

        for i, item in enumerate(findings, 1):
            console.print(
                f"[{i}] {item['path']} "
                f"({item['status']}, {item['size']} bytes)"
            )

        console.print(
            "[0] Return"
        )

        choice = Prompt.ask(
            "Open exposed file",
            default="0"
        )

        if choice.isdigit():
            n = int(choice)

            if 1 <= n <= len(findings):
                inspect_public_file(
                    findings[n - 1]
                )


# ============================================================
# SERVER INVESTIGATION FLOW
# ============================================================

def server_investigation():

    section("AUTHORIZED SERVER INVESTIGATION")

    if not Confirm.ask(
        "Confirm this is your server / authorized environment"
    ):
        warn("Investigation cancelled.")
        return

    server_information()
    process_investigation()
    network_investigation()
    service_investigation()
    scheduled_tasks()
    log_investigation()
    incident_timeline()


# ============================================================
# MAIN MENU
# ============================================================

def main_menu():

    while True:

        section("CCS COMMAND CENTER")

        menu = Table(
            show_header=False,
            box=None
        )

        menu.add_row(
            "[1]",
            "🌐 Web Security Investigation"
        )

        menu.add_row(
            "[2]",
            "🖥️  Authorized Server Investigation"
        )

        menu.add_row(
            "[3]",
            "🔐 Admin Evidence Inspector"
        )

        menu.add_row(
            "[4]",
            "🧠 Incident Timeline"
        )

        menu.add_row(
            "[5]",
            "🛡️  Kali Toolchain"
        )

        menu.add_row(
            "[6]",
            "🔎 Authorized Nmap Assessment"
        )

        menu.add_row(
            "[7]",
            "🔑 License / System"
        )

        menu.add_row(
            "[8]",
            "📜 CCS Audit Log"
        )

        menu.add_row(
            "[0]",
            "Exit"
        )

        console.print(menu)

        choice = Prompt.ask(
            "CCS",
            choices=[
                "1",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "0"
            ]
        )

        if choice == "1":
            web_investigation()

        elif choice == "2":
            server_investigation()

        elif choice == "3":
            info(
                "Evidence is displayed directly during "
                "authenticated investigations."
            )

        elif choice == "4":
            incident_timeline()

        elif choice == "5":
            kali_environment()

        elif choice == "6":
            target = Prompt.ask(
                "Authorized target"
            )

            nmap_scan(target)

        elif choice == "7":
            system_menu()

        elif choice == "8":
            section("CCS AUDIT LOG")

            if AUDIT.exists():
                console.print(
                    Panel(
                        AUDIT.read_text(
                            encoding="utf-8",
                            errors="replace"
                        )[-30000:],
                        border_style="cyan"
                    )
                )
            else:
                info("No audit events.")

        elif choice == "0":
            audit("EXIT")
            console.print(
                "\n[bold cyan]CCS shutting down.[/bold cyan]"
            )
            break


# ============================================================
# START
# ============================================================

def main():

    initialize()
    banner()
    setup_admin()

    if not authenticate():
        sys.exit(1)

    config = load_config()

    section("SECURITY STATUS")

    ok("Administrator authenticated")
    ok("Installation identity loaded")
    ok(
        f"Installation: "
        f"{config['installation_id']}"
    )
    ok(
        f"License: "
        f"{config['license']['status']}"
    )
    ok(
        "Terminal evidence mode: ENABLED"
    )

    audit(
        "SESSION_START",
        config["installation_id"]
    )

    main_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print(
            "\n\n[yellow]CCS interrupted.[/yellow]"
        )
    except Exception as e:
        console.print(
            f"\n[bold red]CCS ERROR:[/bold red] {e}"
        )
        audit(
            "UNHANDLED_ERROR",
            repr(e)
        )
