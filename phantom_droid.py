#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PhantomDroid-Py v1.0
Controlador/Lector Autónomo de Android via ADB + scrcpy

Requiere: Python 3.7+, ADB en PATH, scrcpy (para espejo de pantalla)
  Windows : winget install Google.PlatformTools   (ADB)
            winget install SoftDeluxe.scrcpy       (espejo)
  Linux   : sudo apt install adb scrcpy
  macOS   : brew install android-platform-tools scrcpy
"""

import subprocess
import sys
import os
import time
import re
import threading
import shutil
import queue
from typing import Optional, List, Tuple

# ─── Auto-instalación de dependencias ─────────────────────────────────────
def _auto_install():
    import importlib.util as _ilu
    missing = [pkg for pkg in ("rich",) if _ilu.find_spec(pkg) is None]
    if missing:
        print(f"Instalando dependencias: {', '.join(missing)} ...")
        subprocess.run([sys.executable, "-m", "pip", "install"] + missing + ["-q"])

_auto_install()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.prompt import Prompt, Confirm
from rich import box

console = Console()

# ─── Configuración global ─────────────────────────────────────────────────
VERSION          = "1.0"
ADB_PORT         = 5555
POLLING_INTERVAL = 2          # segundos entre escaneos del watcher

# ─── Estado de la sesión ──────────────────────────────────────────────────
current_device:    Optional[str] = None
wireless_connected: bool         = False
_stop_event = threading.Event()
_input_q:    queue.Queue        = queue.Queue()  # input del usuario


def _stdin_reader():
    """Hilo que lee stdin sin bloquear el loop principal."""
    while not _stop_event.is_set():
        try:
            # readline() bloquea hasta que el usuario presiona Enter;
            # al correr en un hilo separado no congela el resto del programa
            line = sys.stdin.readline()
            if line is not None:
                # Quitar el salto de línea y poner la entrada en la cola compartida
                _input_q.put(line.rstrip("\n\r"))
        except OSError:
            # stdin puede cerrarse si se pierde la consola; esperamos y reintentamos
            time.sleep(0.3)


# ══════════════════════════════════════════════════════════════════════════
#  NÚCLEO ADB
# ══════════════════════════════════════════════════════════════════════════

def run_adb(*args, device: str = None, timeout: int = 30) -> Tuple[bool, str]:
    """Ejecuta un comando ADB y devuelve (éxito, salida)."""
    cmd = ["adb"]
    if device:
        # -s <serial> le dice a ADB a qué dispositivo específico enviar el comando
        # (necesario cuando hay más de uno conectado al mismo tiempo)
        cmd += ["-s", device]
    cmd += list(args)   # agrega los argumentos del comando, ej: ["shell", "getprop"]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
            # capture_output=True → captura stdout y stderr para leerlos desde Python
            # errors="replace" → si hay caracteres raros en la salida no falla
        )
        # returncode == 0 significa que el comando terminó sin error (convención UNIX)
        # unimos stdout + stderr porque ADB a veces manda info útil por stderr
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "Timeout: el comando tardó demasiado."
    except FileNotFoundError:
        # FileNotFoundError ocurre cuando "adb" no existe en el PATH del sistema
        return False, "ADB no encontrado. Instala Android Platform Tools y agrégalo al PATH."


def get_devices() -> List[dict]:
    """Devuelve lista de dispositivos detectados por ADB."""
    ok, out = run_adb("devices", "-l")
    if not ok:
        return []
    devices = []
    # La primera línea es siempre el encabezado "List of devices attached", la saltamos con [1:]
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        # Cada línea tiene formato: "ZY22FVZQQF  device  product:moto_g52 ..."
        #                           ──serial──   status  ────info extra────
        parts = line.split()
        if len(parts) >= 2 and parts[1] in ("device", "offline", "unauthorized"):
            devices.append({
                "serial":   parts[0],
                "status":   parts[1],
                "info":     " ".join(parts[2:]),
                # Los dispositivos WiFi tienen ":" en el serial (ej: "192.168.100.224:5555")
                # Los USB usan un número de serie alfanumérico como "ZY22FVZQQF" (sin ":")
                "wireless": ":" in parts[0],
            })
    return devices


def get_device_ip(serial: str) -> Optional[str]:
    """Obtiene la IP WiFi del dispositivo (3 métodos de fallback)."""
    # ── Método 1: ip route ───────────────────────────────────────────────
    # Salida típica: "192.168.100.0/24 dev wlan0 proto kernel scope link src 192.168.100.224"
    # Buscamos la IP que aparece después de "src"
    ok, out = run_adb("shell", "ip", "route", device=serial)
    if ok:
        m = re.search(r"src\s+([\d.]+)", out)   # r"src\s+[\d.]+" → busca "src" seguido de una IP
        if m:
            return m.group(1)   # group(1) = el primer grupo capturado entre paréntesis

    # ── Método 2: ip addr show wlan0 ────────────────────────────────────
    # Salida típica: "inet 192.168.100.224/24 brd 192.168.100.255 scope global wlan0"
    # Buscamos la IP después de "inet" (termina antes de la máscara "/")
    ok, out = run_adb("shell", "ip", "addr", "show", "wlan0", device=serial)
    if ok:
        m = re.search(r"inet\s+([\d.]+)/", out)
        if m:
            return m.group(1)

    # ── Método 3: ifconfig wlan0 (Android antiguo) ───────────────────────
    # Salida típica: "inet addr:192.168.100.224  Bcast:..."
    # El patrón maneja tanto "inet addr:IP" (Android viejo) como "inet IP" (Linux moderno)
    ok, out = run_adb("shell", "ifconfig", "wlan0", device=serial)
    if ok:
        m = re.search(r"inet(?:\s+addr:)?\s*([\d.]+)", out)
        # Descartamos 127.x.x.x (loopback) porque no sirve para conectarnos por WiFi
        if m and not m.group(1).startswith("127"):
            return m.group(1)

    return None   # ninguno de los 3 métodos funcionó


def setup_wireless_adb(serial: str) -> Tuple[bool, str]:
    """
    Activa ADB sobre TCP/IP y conecta vía WiFi.
    Devuelve (True, "ip:puerto") o (False, "mensaje de error").
    """
    ip = get_device_ip(serial)
    if not ip:
        return False, "No se obtuvo IP. ¿El dispositivo está conectado a WiFi?"

    ok, out = run_adb("tcpip", str(ADB_PORT), device=serial)
    if not ok:
        return False, f"Error al activar tcpip: {out}"

    time.sleep(1.5)   # esperar que el demonio reinicie en modo TCP

    ok, out = run_adb("connect", f"{ip}:{ADB_PORT}")
    if not ok or "failed" in out.lower() or "error" in out.lower():
        return False, f"Error al conectar: {out}"

    return True, f"{ip}:{ADB_PORT}"


# ══════════════════════════════════════════════════════════════════════════
#  WATCHER — detección automática al enchufar el celular
# ══════════════════════════════════════════════════════════════════════════

def _device_watcher():
    """
    Hilo de fondo que detecta dispositivos USB nuevos,
    obtiene su IP y configura ADB inalámbrico automáticamente.
    """
    global current_device, wireless_connected
    known_serials: set  = set()  # seriales USB que ya procesamos (para no repetir el setup)
    known_unauth:  set  = set()  # seriales no autorizados ya avisados (para no repetir el aviso)

    while not _stop_event.is_set():
        devices = get_devices()   # consulta ADB: "adb devices -l"

        # Filtra SOLO los USB autorizados (no wireless y status == "device")
        # Un serial USB es un código alfanumérico como "ZY22FVZQQF" (sin ":")
        # status "device" = autorizado y listo; puede ser también "offline" o "unauthorized"
        usb_ok  = {d["serial"] for d in devices
                   if not d["wireless"] and d["status"] == "device"}

        # Filtra USB presentes pero sin autorización (el usuario no aceptó el popup)
        usb_unauth = {d["serial"] for d in devices
                      if not d["wireless"] and d["status"] == "unauthorized"}

        # Diferencia de conjuntos: solo los seriales que NO estaban en known_unauth antes
        # Así avisamos UNA SOLA VEZ por cada serial, no en cada ciclo del watcher
        for serial in usb_unauth - known_unauth:
            console.print(
                f"\n[bold yellow]📱 Celular detectado ({serial}) pero SIN autorización.[/]")
            console.print(
                "[bold yellow]   ➜ Mira tu celular y acepta el popup\n"
                "     'Permitir depuración USB' → Permitir siempre[/]\n")
        known_unauth = usb_unauth   # actualizamos el conjunto para el próximo ciclo

        # Diferencia de conjuntos: seriales que están en usb_ok pero NO en known_serials
        # = dispositivos recién conectados que aún no procesamos
        new_devices = usb_ok - known_serials
        for serial in new_devices:
            if wireless_connected:
                # Si ya hay WiFi activo, la reconexión USB es solo efecto secundario de
                # haber corrido scrcpy o el comando "tcpip" — la ignoramos completamente
                continue
            console.print(f"\n[bold green]📱 Dispositivo autorizado:[/] {serial}")

            # Paso 1: obtener IP
            console.print("[cyan]   Paso 1/3 — Obteniendo IP WiFi del celular...[/]")
            ip = get_device_ip(serial)
            if not ip:
                console.print("[bold red]   ❌ No se pudo obtener la IP.[/]")
                console.print("[bold yellow]   ¿El celular está conectado a WiFi?[/]")
                console.print("[yellow]   Ambos dispositivos deben estar en la misma red WiFi.[/]")
                console.print("[dim]   Puedes conectar manualmente con la opción 48 del menú.[/]\n")
                current_device     = serial
                wireless_connected = False
                _input_q.put("")   # señal vacía → main() sabe que debe redibujar el menú
                continue

            console.print(f"[green]   ✅ IP detectada: {ip}[/]")

            # Paso 2: cambiar el demonio ADB del celular a modo TCP en el puerto 5555
            # Esto es necesario para que ADB pueda conectarse por red en lugar de USB
            console.print("[cyan]   Paso 2/3 — Activando ADB sobre WiFi (tcpip 5555)...[/]")
            ok2, out2 = run_adb("tcpip", str(ADB_PORT), device=serial)
            if not ok2:
                console.print(f"[bold red]   ❌ Error tcpip: {out2}[/]\n")
                current_device     = serial
                wireless_connected = False
                _input_q.put("")   # señal vacía → fuerza redibujado del menú
                continue
            time.sleep(1.5)   # esperamos que el demonio ADB del celular se reinicie en modo TCP

            # Paso 3: conectar desde esta PC al celular usando su IP y el puerto 5555
            # A partir de aquí ya no necesitamos el cable USB
            console.print(f"[cyan]   Paso 3/3 — Conectando a {ip}:{ADB_PORT}...[/]")
            ok3, out3 = run_adb("connect", f"{ip}:{ADB_PORT}")
            # ADB puede devolver returncode=0 pero igual incluir "failed" en el texto
            if ok3 and "failed" not in out3.lower() and "error" not in out3.lower():
                # Actualizamos el estado global: ahora el dispositivo es la IP, no el serial USB
                current_device     = f"{ip}:{ADB_PORT}"
                wireless_connected = True
                console.print(f"[bold green]   ✅ ADB WiFi listo → {ip}:{ADB_PORT}[/]")
                console.print("[bold yellow]   💡 Ya puedes desconectar el cable USB.[/]\n")
            else:
                console.print(f"[bold red]   ❌ No se pudo conectar por WiFi: {out3}[/]")
                console.print("[yellow]   Verifica que PC y celular estén en la misma red WiFi.[/]\n")
                current_device     = serial
                wireless_connected = False

            time.sleep(2)   # pausa para que el usuario pueda leer los mensajes del setup
            _input_q.put("")   # notifica al loop principal: evento ocurrido → redibujar

        # |= es "unión" de conjuntos: agrega los nuevos sin borrar los anteriores
        # Nunca reseteamos para que una desconexión USB momentánea (ej: scrcpy)
        # no haga que el watcher trate el mismo celular como "nuevo" y repita el setup
        known_serials |= usb_ok
        # wait() es como sleep() pero se puede interrumpir desde otro hilo con _stop_event.set()
        _stop_event.wait(POLLING_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════
#  HELPERS DE UI
# ══════════════════════════════════════════════════════════════════════════

def print_banner():
    title = Text(justify="center")
    title.append(" ____  _           _                  ____            _     _ \n", "bold red")
    title.append("|  _ \\| |__   __ _| |_ ___  _ __ ___|  _ \\_ __ ___ (_) __| |\n", "bold red")
    title.append("| |_) | '_ \\ / _` | __/ _ \\| '_ ` _ \\ | | | '__/ _ \\| |/ _` |\n", "bold red")
    title.append("|  __/| | | | (_| | || (_) | | | | | | |_| | | | (_) | | (_| |\n", "bold red")
    title.append("|_|   |_| |_|\\__,_|\\__\\___/|_| |_| |_|____/|_|  \\___/|_|\\__,_|\n", "bold red")
    title.append(f"\n  v{VERSION}  •  Controlador Autónomo Android  •  ADB + scrcpy\n", "bold cyan")

    if current_device:
        tipo   = "📶 WiFi" if wireless_connected else "🔌 USB"
        status = f"[bold green]✅ {tipo}  →  [bold white]{current_device}[/][/]"
    else:
        status = "[bold yellow]⚠  Sin dispositivo — conecta el celular por USB con Depuración USB activada[/]"

    console.print(Panel(title,  border_style="red",  padding=(0, 1)))
    console.print(Panel(status, border_style="cyan", padding=(0, 2)))


def _col(title: str, style: str, items: list) -> Table:
    t = Table(box=box.SIMPLE, show_header=True,
              header_style=f"bold {style}", padding=(0, 1))
    t.add_column(title, style=style, no_wrap=True, min_width=32)
    for item in items:
        t.add_row(item)
    return t


def print_menu():
    col1 = _col("GESTIÓN DE DISPOSITIVO", "green", [
        "1.  Listar dispositivos",
        "2.  Conectar WiFi",
        "3.  Desconectar dispositivo",
        "4.  Info del dispositivo",
        "5.  Reiniciar ADB",
        "6.  Verificar conexión",
        "7.  Ejecutar comando shell",
        "8.  Ver logs del device",
        "9.  Reiniciar dispositivo",
        "─── MONITOREO DEL SISTEMA ───",
        "28. Batería",
        "29. Memoria",
        "30. CPU",
        "31. Almacenamiento",
        "32. Procesos activos",
        "33. Info de red",
        "34. Propiedades del sistema",
        "35. Apps por tamaño",
        "36. Monitor de rendimiento",
    ])

    col2 = _col("GESTIÓN DE APLICACIONES", "yellow", [
        "10. Instalar APK",
        "11. Desinstalar app",
        "12. Listar paquetes",
        "13. Info de paquete",
        "14. Limpiar datos de app",
        "15. Forzar cierre",
        "16. Iniciar app",
        "17. Backup de app",
        "18. Batch install APKs",
        "─── PANTALLA / SCRCPY ───────",
        "37. Espejo de pantalla",
        "38. Espejo personalizado",
        "39. Detener scrcpy",
        "40. Grabar pantalla (scrcpy)",
        "41. Captura de pantalla",
        "42. Multi capturas",
        "43. Verificar scrcpy",
        "44. Sesiones activas",
        "45. Sync carpeta → PC",
    ])

    col3 = _col("ARCHIVOS  &  WiFi-ADB", "magenta", [
        "19. Screenshot rápido",
        "20. Screenshots múltiples",
        "21. Grabar pantalla (ADB)",
        "22. Subir archivo al device",
        "23. Descargar archivo",
        "24. Listar archivos",
        "25. Crear carpeta",
        "26. Eliminar archivo/carpeta",
        "27. Backup de carpeta",
        "─── GESTIÓN WiFi-ADB ────────",
        "46. Transfer manual WiFi",
        "47. Conectar todos los devices",
        "48. Setup rápido WiFi",
        "49. Estado WiFi",
        "50. Desconectar WiFi-ADB",
        "51. Auto-reconexión",
        "52. Monitor Logcat",
        "53. Estado servicios",
        "54. Ajustes",
    ])

    console.print(Columns([col1, col2, col3]))
    console.print("\n[dim]  99 → Salir[/]")


def require_device() -> Optional[str]:
    """Verifica que haya un dispositivo disponible."""
    if current_device:
        return current_device
    all_devs = get_devices()
    authorized = [d for d in all_devs if d["status"] == "device"]
    if authorized:
        return authorized[0]["serial"]
    # Detectar si hay dispositivos sin autorizar y dar mensaje claro
    unauth = [d for d in all_devs if d["status"] == "unauthorized"]
    if unauth:
        console.print("[bold yellow]⚠ Celular detectado pero sin autorización ADB.[/]")
        console.print("[yellow]  ➜ Mira el celular y acepta 'Permitir depuración USB'[/]")
    else:
        console.print("[bold red]❌ No hay dispositivo conectado.[/]")
        console.print("[dim]  Conecta el celular por USB con Depuración USB activada.[/]")
    return None


def pause():
    console.print("\n[dim]  Presiona Enter para continuar...[/]", end="")
    input()


# ══════════════════════════════════════════════════════════════════════════
#  GESTIÓN DE DISPOSITIVO  (1-9)
# ══════════════════════════════════════════════════════════════════════════

def cmd_list_devices():
    devs = get_devices()
    if not devs:
        console.print("[yellow]No hay dispositivos.[/]"); pause(); return
    t = Table(title="Dispositivos Conectados", box=box.ROUNDED, border_style="green")
    t.add_column("Serial / IP", style="cyan")
    t.add_column("Estado")
    t.add_column("Tipo", style="yellow")
    t.add_column("Info", style="dim")
    for d in devs:
        t.add_row(d["serial"], d["status"],
                  "📶 WiFi" if d["wireless"] else "🔌 USB", d["info"])
    console.print(t)
    pause()


def cmd_connect_wifi():
    global current_device, wireless_connected
    # Filtra solo dispositivos USB autorizados (excluye WiFi y no autorizados)
    # not d["wireless"] → descarta IPs tipo "192.168.x.x:5555" (ya en WiFi)
    # d["status"] == "device" → solo los que aceptaron el popup de depuración USB
    usb = [d for d in get_devices() if not d["wireless"] and d["status"] == "device"]
    if usb:
        with console.status("[bold cyan]Configurando ADB WiFi..."):
            ok, result = setup_wireless_adb(usb[0]["serial"])
        if ok:
            current_device     = result
            wireless_connected = True
            console.print(f"[bold green]✅ Conectado:[/] {result}")
            console.print("[yellow]💡 Puedes desconectar el USB.[/]")
        else:
            console.print(f"[bold red]❌ {result}[/]")
    else:
        ip   = Prompt.ask("IP del dispositivo (modo manual)")
        port = Prompt.ask("Puerto", default=str(ADB_PORT))
        ok, out = run_adb("connect", f"{ip}:{port}")
        console.print(f"[{'green' if 'connected' in out.lower() else 'red'}]{out}[/]")
        if "connected" in out.lower():
            current_device     = f"{ip}:{port}"
            wireless_connected = True
    pause()


def cmd_disconnect():
    global current_device, wireless_connected
    dev = require_device()
    if not dev: pause(); return
    ok, out = run_adb("disconnect", dev)
    console.print(f"[cyan]{out}[/]")
    current_device     = None
    wireless_connected = False
    pause()


def cmd_device_info():
    dev = require_device()
    if not dev: pause(); return
    t = Table(title="Info del Dispositivo", box=box.ROUNDED, border_style="cyan")
    t.add_column("Propiedad", style="cyan")
    t.add_column("Valor",     style="white")
    for name, prop in [
        ("Modelo",       "ro.product.model"),
        ("Marca",        "ro.product.brand"),
        ("Android",      "ro.build.version.release"),
        ("SDK",          "ro.build.version.sdk"),
        ("Arquitectura", "ro.product.cpu.abi"),
        ("Nº serie",     "ro.serialno"),
    ]:
        _, val = run_adb("shell", "getprop", prop, device=dev)
        t.add_row(name, val or "N/A")
    _, sz  = run_adb("shell", "wm", "size",    device=dev)
    _, dpi = run_adb("shell", "wm", "density", device=dev)
    t.add_row("Resolución", sz  or "N/A")
    t.add_row("Densidad",   dpi or "N/A")
    _, ip_out = run_adb("shell", "ip", "route", device=dev)
    m = re.search(r"src\s+([\d.]+)", ip_out or "")
    t.add_row("IP WiFi", m.group(1) if m else "N/A")
    console.print(t)
    pause()


def cmd_restart_adb():
    with console.status("[bold cyan]Reiniciando ADB..."):
        run_adb("kill-server")
        time.sleep(1)
        ok, out = run_adb("start-server")
    console.print(f"[{'green' if ok else 'red'}]ADB reiniciado: {out}[/]")
    pause()


def cmd_check_connection():
    dev = require_device()
    if not dev: pause(); return
    ok, _ = run_adb("shell", "echo", "OK", device=dev)
    console.print(
        f"[bold green]✅ Conexión activa: {dev}[/]" if ok
        else f"[bold red]❌ Sin respuesta de {dev}[/]"
    )
    pause()


def cmd_shell():
    dev = require_device()
    if not dev: pause(); return
    cmd_str = Prompt.ask("Comando shell")
    _, out = run_adb("shell", cmd_str, device=dev)
    console.print(Panel(out or "(sin salida)", title="Resultado", border_style="cyan"))
    pause()


def cmd_logs():
    dev = require_device()
    if not dev: pause(); return
    n = Prompt.ask("Líneas a mostrar", default="50")
    _, out = run_adb("logcat", "-d", "-t", n, device=dev)
    console.print(Panel((out or "")[:4000], title="Logcat reciente", border_style="yellow"))
    pause()


def cmd_reboot():
    dev = require_device()
    if not dev: pause(); return
    mode = Prompt.ask("Modo de reinicio",
                      choices=["normal", "recovery", "bootloader"], default="normal")
    if not Confirm.ask(f"¿Reiniciar en modo [bold]{mode}[/]?"):
        return
    args = ["reboot"] if mode == "normal" else ["reboot", mode]
    _, out = run_adb(*args, device=dev)
    console.print(f"[green]{out or 'Reiniciando...'}[/]")
    pause()


# ══════════════════════════════════════════════════════════════════════════
#  MONITOREO DEL SISTEMA  (28-36)
# ══════════════════════════════════════════════════════════════════════════

def cmd_battery():
    dev = require_device()
    if not dev: pause(); return
    _, out = run_adb("shell", "dumpsys", "battery", device=dev)
    console.print(Panel(out or "", title="Estado de Batería", border_style="green"))
    pause()


def cmd_memory():
    dev = require_device()
    if not dev: pause(); return
    _, out = run_adb("shell", "cat", "/proc/meminfo", device=dev)
    relevant = [l for l in (out or "").splitlines()
                if any(k in l for k in
                       ("MemTotal", "MemFree", "MemAvailable", "Cached:", "SwapTotal", "SwapFree"))]
    console.print(Panel("\n".join(relevant), title="Memoria", border_style="blue"))
    pause()


def cmd_cpu():
    dev = require_device()
    if not dev: pause(); return
    _, out  = run_adb("shell", "cat", "/proc/cpuinfo", device=dev)
    _, freq = run_adb("shell", "cat",
                      "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", device=dev)
    lines = [l for l in (out or "").splitlines()
             if any(k in l.lower() for k in ("processor", "model name", "hardware"))]
    t = Table(title="CPU", box=box.SIMPLE)
    t.add_column("Campo"); t.add_column("Valor")
    for l in lines[:15]:
        parts = l.split(":", 1)
        if len(parts) == 2:
            t.add_row(parts[0].strip(), parts[1].strip())
    try:
        t.add_row("Frecuencia actual", f"{int((freq or '0').strip()) // 1000} MHz")
    except Exception:
        pass
    console.print(t)
    pause()


def cmd_storage():
    dev = require_device()
    if not dev: pause(); return
    _, out = run_adb("shell", "df", "-h", device=dev)
    console.print(Panel(out or "", title="Almacenamiento", border_style="magenta"))
    pause()


def cmd_processes():
    dev = require_device()
    if not dev: pause(); return
    _, out = run_adb("shell", "ps", "-A", device=dev)
    lines = (out or "").splitlines()
    console.print(Panel(
        f"Total: {max(0, len(lines)-1)} procesos\n\n" +
        "\n".join(lines[1:40]) + ("\n..." if len(lines) > 41 else ""),
        title="Procesos activos", border_style="cyan"))
    pause()


def cmd_network_info():
    dev = require_device()
    if not dev: pause(); return
    _, addr  = run_adb("shell", "ip", "addr",  device=dev)
    _, route = run_adb("shell", "ip", "route", device=dev)
    console.print(Panel(
        (addr or "") + "\n\n[bold]Rutas:[/]\n" + (route or ""),
        title="Red", border_style="yellow"))
    pause()


def cmd_sys_props():
    dev = require_device()
    if not dev: pause(); return
    _, out = run_adb("shell", "getprop", device=dev)
    console.print(Panel((out or "")[:3500] + "\n...",
                        title="Propiedades del Sistema", border_style="dim"))
    pause()


def cmd_apps_by_size():
    dev = require_device()
    if not dev: pause(); return
    with console.status("[bold cyan]Calculando tamaños (puede tardar)..."):
        _, out = run_adb("shell", "du", "-sh", "/data/app/*/", device=dev)
    console.print(Panel(out or "Sin datos (puede requerir root)",
                        title="Apps por Tamaño", border_style="magenta"))
    pause()


def cmd_performance():
    dev = require_device()
    if not dev: pause(); return
    console.print("[bold cyan]Monitoreando rendimiento (5 muestras). Ctrl+C para salir.[/]")
    try:
        for i in range(5):
            _, top = run_adb("shell", "top", "-n", "1", "-b", device=dev)
            _, mem = run_adb("shell", "free", "-m", device=dev)
            os.system("cls" if os.name == "nt" else "clear")
            console.print(f"[bold]Muestra {i+1}/5[/]")
            console.print(Panel((top or "")[:600], title="Top CPU",      border_style="red"))
            console.print(Panel(mem or "",          title="Memoria (MB)", border_style="blue"))
            time.sleep(1.5)
    except KeyboardInterrupt:
        pass
    pause()


# ══════════════════════════════════════════════════════════════════════════
#  GESTIÓN DE APLICACIONES  (10-18)
# ══════════════════════════════════════════════════════════════════════════

def cmd_install_apk():
    dev = require_device()
    if not dev: pause(); return
    path = Prompt.ask("Ruta del APK").strip('"').strip("'")
    if not os.path.exists(path):
        console.print("[red]Archivo no encontrado.[/]"); pause(); return
    with console.status(f"[bold cyan]Instalando {os.path.basename(path)}..."):
        ok, out = run_adb("install", "-r", path, device=dev, timeout=120)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


def cmd_uninstall():
    dev = require_device()
    if not dev: pause(); return
    pkg = Prompt.ask("Nombre del paquete")
    if not Confirm.ask(f"¿Desinstalar [bold]{pkg}[/]?"):
        return
    ok, out = run_adb("uninstall", pkg, device=dev)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


def cmd_list_packages():
    dev = require_device()
    if not dev: pause(); return
    choice = Prompt.ask("Mostrar",
                        choices=["todas", "sistema", "usuario"], default="usuario")
    flag_map = {"todas": [], "sistema": ["-s"], "usuario": ["-3"]}
    _, out = run_adb("shell", "pm", "list", "packages", *flag_map[choice], device=dev)
    pkgs = sorted([l.replace("package:", "")
                   for l in (out or "").splitlines() if l.startswith("package:")])
    t = Table(title=f"Paquetes ({len(pkgs)})", box=box.SIMPLE)
    t.add_column("Paquete", style="cyan")
    for p in pkgs:
        t.add_row(p)
    console.print(t)
    pause()


def cmd_package_info():
    dev = require_device()
    if not dev: pause(); return
    pkg = Prompt.ask("Nombre del paquete")
    _, out = run_adb("shell", "dumpsys", "package", pkg, device=dev)
    console.print(Panel((out or "")[:2500], title=f"Info: {pkg}", border_style="yellow"))
    pause()


def cmd_clear_data():
    dev = require_device()
    if not dev: pause(); return
    pkg = Prompt.ask("Nombre del paquete")
    if not Confirm.ask(f"¿Limpiar datos de [bold]{pkg}[/]? (se borrará todo)"):
        return
    ok, out = run_adb("shell", "pm", "clear", pkg, device=dev)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


def cmd_force_stop():
    dev = require_device()
    if not dev: pause(); return
    pkg = Prompt.ask("Nombre del paquete")
    ok, out = run_adb("shell", "am", "force-stop", pkg, device=dev)
    console.print(f"[{'green' if ok else 'red'}]"
                  f"{f'App detenida: {pkg}' if ok else out}[/]")
    pause()


def cmd_start_app():
    dev = require_device()
    if not dev: pause(); return
    pkg = Prompt.ask("Nombre del paquete")
    ok, out = run_adb("shell", "monkey", "-p", pkg, "-c",
                      "android.intent.category.LAUNCHER", "1", device=dev)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


def cmd_backup_app():
    dev = require_device()
    if not dev: pause(); return
    pkg  = Prompt.ask("Nombre del paquete")
    dest = Prompt.ask("Archivo destino", default=f"{pkg}.ab")
    console.print("[dim yellow]Nota: adb backup está deprecado en Android 12+. "
                  "Es posible que debas confirmar en el dispositivo.[/]")
    with console.status("[bold cyan]Creando backup..."):
        ok, out = run_adb("backup", "-f", dest, pkg, device=dev, timeout=120)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


def cmd_batch_install():
    dev = require_device()
    if not dev: pause(); return
    folder = Prompt.ask("Carpeta con APKs").strip('"').strip("'")
    if not os.path.isdir(folder):
        console.print("[red]Carpeta no encontrada.[/]"); pause(); return
    apks = [f for f in os.listdir(folder) if f.lower().endswith(".apk")]
    console.print(f"[cyan]Encontrados {len(apks)} APKs[/]")
    for apk in apks:
        path = os.path.join(folder, apk)
        with console.status(f"[bold cyan]Instalando {apk}..."):
            ok, out = run_adb("install", "-r", path, device=dev, timeout=120)
        console.print(f"{'✅' if ok else '❌'} {apk}: {out}")
    pause()


# ══════════════════════════════════════════════════════════════════════════
#  PANTALLA / SCRCPY  (37-45)
# ══════════════════════════════════════════════════════════════════════════

_SCRCPY_WINGET = (
    r"C:\Users\Gernet\AppData\Local\Microsoft\WinGet\Packages"
    r"\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\scrcpy-win64-v3.3.4\scrcpy.exe"
)

def _scrcpy_path() -> Optional[str]:
    """Devuelve la ruta al ejecutable scrcpy o None si no se encuentra."""
    found = shutil.which("scrcpy")
    if found:
        return found
    if os.path.exists(_SCRCPY_WINGET):
        return _SCRCPY_WINGET
    return None

def _scrcpy_ok() -> bool:
    return _scrcpy_path() is not None


def _scrcpy_hint():
    console.print("[bold red]❌ scrcpy no está instalado.[/]")
    console.print("  Windows : [white]winget install SoftDeluxe.scrcpy[/]")
    console.print("  Linux   : [white]sudo apt install scrcpy[/]")
    console.print("  macOS   : [white]brew install scrcpy[/]")
    console.print("  Manual  : [white]https://github.com/Genymobile/scrcpy/releases[/]")


def cmd_screen_mirror():
    dev = require_device()
    if not dev: pause(); return
    if not _scrcpy_ok():
        _scrcpy_hint(); pause(); return
    console.print("[bold green]🖥 Iniciando espejo de pantalla...[/]")
    subprocess.run([_scrcpy_path(), "-s", dev], check=False)
    pause()


def cmd_screen_mirror_custom():
    dev = require_device()
    if not dev: pause(); return
    if not _scrcpy_ok():
        _scrcpy_hint(); pause(); return
    bitrate  = Prompt.ask("Bitrate video (Mbps)",           default="8")
    maxfps   = Prompt.ask("FPS máximo",                     default="60")
    maxsize  = Prompt.ask("Resolución máx en px (0=auto)",  default="0")
    no_audio = Confirm.ask("¿Deshabilitar audio?",          default=False)
    stay_on  = Confirm.ask("¿Mantener pantalla encendida?", default=True)
    record   = Confirm.ask("¿Grabar la sesión?",            default=False)

    cmd = [_scrcpy_path(), "-s", dev,
           "--video-bit-rate", f"{bitrate}M",
           "--max-fps", maxfps]
    if maxsize != "0":
        cmd += ["--max-size", maxsize]
    if no_audio:
        cmd += ["--no-audio"]
    if stay_on:
        cmd += ["--stay-awake"]
    if record:
        fname = Prompt.ask("Nombre del archivo", default="grabacion.mp4")
        cmd  += ["--record", fname]

    console.print(f"[bold green]Ejecutando: {' '.join(cmd)}[/]")
    subprocess.run(cmd, check=False)
    pause()


def cmd_stop_scrcpy():
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/IM", "scrcpy.exe"],  # noqa: S603
                       capture_output=True, check=False)
    else:
        subprocess.run(["pkill", "-f", "scrcpy"], capture_output=True, check=False)
    console.print("[green]Procesos scrcpy detenidos.[/]")
    pause()


def cmd_record_scrcpy():
    dev = require_device()
    if not dev: pause(); return
    if not _scrcpy_ok():
        _scrcpy_hint(); pause(); return
    fname = Prompt.ask("Guardar grabación como", default="grabacion.mp4")
    console.print("[dim]Cierra la ventana de scrcpy para terminar la grabación.[/]")
    subprocess.run([_scrcpy_path(), "-s", dev, "--record", fname,
                    "--no-display"], check=False)
    pause()


def cmd_screenshot():
    dev = require_device()
    if not dev: pause(); return
    local  = Prompt.ask("Guardar como", default=f"shot_{int(time.time())}.png")
    remote = "/sdcard/_phantom_shot.png"
    with console.status("[bold cyan]Capturando pantalla..."):
        ok, _ = run_adb("shell", "screencap", "-p", remote, device=dev)
        if ok:
            ok, out = run_adb("pull", remote, local, device=dev)
            run_adb("shell", "rm", "-f", remote, device=dev)
    console.print(f"[{'green' if ok else 'red'}]"
                  f"{'✅ Guardado: ' + local if ok else out}[/]")
    pause()


def cmd_multi_screenshot():
    dev = require_device()
    if not dev: pause(); return
    n        = int(Prompt.ask("Número de capturas", default="5"))
    interval = float(Prompt.ask("Intervalo (segundos)", default="2"))
    prefix   = Prompt.ask("Prefijo", default="shot")
    for i in range(n):
        remote = f"/sdcard/_ph_{i:03d}.png"
        local  = f"{prefix}_{i:03d}.png"
        run_adb("shell", "screencap", "-p", remote, device=dev)
        run_adb("pull", remote, local, device=dev)
        run_adb("shell", "rm", "-f", remote, device=dev)
        console.print(f"[green]✅ {i+1}/{n} → {local}[/]")
        if i < n - 1:
            time.sleep(interval)
    pause()


def cmd_check_scrcpy():
    if _scrcpy_ok():
        result  = subprocess.run([_scrcpy_path(), "--version"],
                                 capture_output=True, text=True, timeout=5)
        ver_line = (result.stdout or "").splitlines()[0] if result.stdout else "instalado"
        console.print(f"[bold green]✅ {ver_line}[/]")
    else:
        _scrcpy_hint()
    pause()


def cmd_sync_folder():
    dev = require_device()
    if not dev: pause(); return
    remote = Prompt.ask("Carpeta en el dispositivo", default="/sdcard/DCIM/")
    local  = Prompt.ask("Destino local",             default="./sync_android/")
    os.makedirs(local, exist_ok=True)
    with console.status("[bold cyan]Sincronizando..."):
        ok, out = run_adb("pull", remote, local, device=dev, timeout=300)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


# ══════════════════════════════════════════════════════════════════════════
#  OPERACIONES DE ARCHIVO  (19-27)
# ══════════════════════════════════════════════════════════════════════════

def cmd_record_screen_adb():
    dev      = require_device()
    if not dev: pause(); return
    duration = Prompt.ask("Duración (segundos)", default="30")
    local    = Prompt.ask("Guardar como",        default="grabacion.mp4")
    remote   = "/sdcard/_phantom_rec.mp4"
    console.print(f"[bold cyan]Grabando {duration}s... (Ctrl+C para parar antes)[/]")
    try:
        run_adb("shell", "screenrecord", "--time-limit", duration,
                remote, device=dev, timeout=int(duration) + 10)
    except KeyboardInterrupt:
        pass
    with console.status("[bold cyan]Descargando grabación..."):
        ok, out = run_adb("pull", remote, local, device=dev, timeout=60)
        run_adb("shell", "rm", "-f", remote, device=dev)
    console.print(f"[{'green' if ok else 'red'}]"
                  f"{'✅ Guardado: ' + local if ok else out}[/]")
    pause()


def cmd_upload():
    dev = require_device()
    if not dev: pause(); return
    src  = Prompt.ask("Archivo local").strip('"').strip("'")
    dest = Prompt.ask("Destino en el dispositivo", default="/sdcard/")
    with console.status("[bold cyan]Subiendo archivo..."):
        ok, out = run_adb("push", src, dest, device=dev, timeout=120)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


def cmd_download():
    dev = require_device()
    if not dev: pause(); return
    src  = Prompt.ask("Ruta en el dispositivo")
    dest = Prompt.ask("Destino local", default="./")
    with console.status("[bold cyan]Descargando archivo..."):
        ok, out = run_adb("pull", src, dest, device=dev, timeout=120)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


def cmd_list_files():
    dev = require_device()
    if not dev: pause(); return
    path = Prompt.ask("Ruta en el dispositivo", default="/sdcard/")
    _, out = run_adb("shell", "ls", "-la", path, device=dev)
    console.print(Panel(out or "", title=f"Archivos: {path}", border_style="cyan"))
    pause()


def cmd_create_folder():
    dev = require_device()
    if not dev: pause(); return
    path = Prompt.ask("Ruta de la nueva carpeta")
    ok, out = run_adb("shell", "mkdir", "-p", path, device=dev)
    console.print(f"[{'green' if ok else 'red'}]"
                  f"{'Carpeta creada' if ok else out}[/]")
    pause()


def cmd_delete():
    dev = require_device()
    if not dev: pause(); return
    path = Prompt.ask("Ruta a eliminar")
    if not Confirm.ask(f"[bold red]¿Eliminar permanentemente {path}? Esta acción es irreversible.[/]"):
        return
    ok, out = run_adb("shell", "rm", "-rf", path, device=dev)
    console.print(f"[{'green' if ok else 'red'}]{'Eliminado' if ok else out}[/]")
    pause()


def cmd_backup_folder():
    dev = require_device()
    if not dev: pause(); return
    src  = Prompt.ask("Carpeta en el dispositivo", default="/sdcard/")
    dest = Prompt.ask("Destino local",             default="./backup_android/")
    os.makedirs(dest, exist_ok=True)
    with console.status("[bold cyan]Haciendo backup..."):
        ok, out = run_adb("pull", src, dest, device=dev, timeout=300)
    console.print(f"[{'green' if ok else 'red'}]{out}[/]")
    pause()


# ══════════════════════════════════════════════════════════════════════════
#  GESTIÓN WiFi-ADB  (46-54)
# ══════════════════════════════════════════════════════════════════════════

def cmd_quick_wifi_setup():
    global current_device, wireless_connected
    console.print(Panel(
        "[bold]Setup Rápido ADB WiFi[/]\n\n"
        "Requisitos:\n"
        "  1. Celular conectado por USB\n"
        "  2. Depuración USB activada (Opciones de desarrollador)\n"
        "  3. Celular conectado a la misma red WiFi que esta PC",
        border_style="cyan"))

    # Filtra solo los USB autorizados: descarta WiFi (tiene ":") y no autorizados
    usb = [d for d in get_devices() if not d["wireless"] and d["status"] == "device"]
    if not usb:
        console.print("[red]No hay dispositivo USB. Conéctalo primero.[/]")
        pause(); return

    ip = get_device_ip(usb[0]["serial"])
    if not ip:
        console.print("[red]No se pudo obtener IP del dispositivo.[/]")
        pause(); return

    console.print(f"[green]IP detectada: {ip}[/]")
    with console.status("[bold cyan]Configurando..."):
        ok, result = setup_wireless_adb(usb[0]["serial"])

    if ok:
        current_device     = result
        wireless_connected = True
        console.print(f"\n[bold green]✅ ¡Listo! Conectado a {result}[/]")
        console.print("[bold yellow]💡 Puedes desconectar el cable USB.[/]")
    else:
        console.print(f"[bold red]❌ {result}[/]")
    pause()


def cmd_wifi_status():
    dev = require_device()
    if not dev: pause(); return
    _, out = run_adb("shell", "dumpsys", "wifi", device=dev)
    lines = [l for l in (out or "").splitlines()
             if any(k in l for k in
                    ("SSID", "freq", "rssi", "ip_address", "macAddress", "mWifiInfo"))]
    console.print(Panel("\n".join(lines[:25]), title="Estado WiFi", border_style="cyan"))
    pause()


def cmd_disconnect_wifi():
    global current_device, wireless_connected
    _, out = run_adb("disconnect")
    console.print(f"[cyan]{out}[/]")
    current_device     = None
    wireless_connected = False
    pause()


def cmd_auto_reconnect():
    """Intenta reconectar al último dispositivo WiFi conocido."""
    global current_device, wireless_connected
    devs = get_devices()
    wifi = [d for d in devs if d["wireless"] and d["status"] == "device"]
    if wifi:
        current_device     = wifi[0]["serial"]
        wireless_connected = True
        console.print(f"[bold green]✅ Ya conectado:[/] {current_device}")
    else:
        usb = [d for d in devs if not d["wireless"] and d["status"] == "device"]
        if usb:
            cmd_connect_wifi()
            return
        console.print("[yellow]No hay dispositivos disponibles.[/]")
    pause()


def cmd_logcat():
    dev = require_device()
    if not dev: pause(); return
    tag = Prompt.ask("Filtrar por tag (vacío = todo)", default="")
    console.print("[dim]Logcat en tiempo real. Ctrl+C para salir.[/]\n")
    cmd = ["adb"]
    if dev:
        cmd += ["-s", dev]
    cmd.append("logcat")
    if tag:
        cmd += ["-s", f"{tag}:V"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            if " E " in line or " E/" in line:
                console.print(f"[red]{line.rstrip()}[/]")
            elif " W " in line or " W/" in line:
                console.print(f"[yellow]{line.rstrip()}[/]")
            else:
                console.print(f"[dim]{line.rstrip()}[/]")
    except KeyboardInterrupt:
        proc.terminate()
    pause()


def cmd_service_status():
    dev = require_device()
    if not dev: pause(); return
    _, out = run_adb("shell", "dumpsys", "activity", "services", device=dev)
    console.print(Panel((out or "")[:3500], title="Servicios Activos", border_style="magenta"))
    pause()


def cmd_settings():
    console.print(Panel(
        f"Puerto ADB    : {ADB_PORT}\n"
        f"Intervalo     : {POLLING_INTERVAL}s\n"
        f"Dispositivo   : {current_device or 'ninguno'}\n"
        f"Modo WiFi     : {'sí' if wireless_connected else 'no'}",
        title="Configuración actual", border_style="cyan"))
    pause()


# ══════════════════════════════════════════════════════════════════════════
#  MAPA DE COMANDOS
# ══════════════════════════════════════════════════════════════════════════

COMMANDS = {
    # Gestión de dispositivo
    "1":  cmd_list_devices,
    "2":  cmd_connect_wifi,
    "3":  cmd_disconnect,
    "4":  cmd_device_info,
    "5":  cmd_restart_adb,
    "6":  cmd_check_connection,
    "7":  cmd_shell,
    "8":  cmd_logs,
    "9":  cmd_reboot,
    # Gestión de apps
    "10": cmd_install_apk,
    "11": cmd_uninstall,
    "12": cmd_list_packages,
    "13": cmd_package_info,
    "14": cmd_clear_data,
    "15": cmd_force_stop,
    "16": cmd_start_app,
    "17": cmd_backup_app,
    "18": cmd_batch_install,
    # Archivos
    "19": cmd_screenshot,
    "20": cmd_multi_screenshot,
    "21": cmd_record_screen_adb,
    "22": cmd_upload,
    "23": cmd_download,
    "24": cmd_list_files,
    "25": cmd_create_folder,
    "26": cmd_delete,
    "27": cmd_backup_folder,
    # Monitoreo
    "28": cmd_battery,
    "29": cmd_memory,
    "30": cmd_cpu,
    "31": cmd_storage,
    "32": cmd_processes,
    "33": cmd_network_info,
    "34": cmd_sys_props,
    "35": cmd_apps_by_size,
    "36": cmd_performance,
    # Pantalla / scrcpy
    "37": cmd_screen_mirror,
    "38": cmd_screen_mirror_custom,
    "39": cmd_stop_scrcpy,
    "40": cmd_record_scrcpy,
    "41": cmd_screenshot,
    "42": cmd_multi_screenshot,
    "43": cmd_check_scrcpy,
    "44": cmd_list_devices,
    "45": cmd_sync_folder,
    # WiFi-ADB
    "46": cmd_quick_wifi_setup,
    "47": cmd_connect_wifi,
    "48": cmd_quick_wifi_setup,
    "49": cmd_wifi_status,
    "50": cmd_disconnect_wifi,
    "51": cmd_auto_reconnect,
    "52": cmd_logcat,
    "53": cmd_service_status,
    "54": cmd_settings,
}


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    # Verificar ADB disponible — solo avisa, nunca cierra
    ok, out = run_adb("version")
    if ok:
        console.print(f"[dim green]{out.splitlines()[0]}[/]")
    else:
        console.print(Panel(
            "[bold yellow]⚠ ADB no detectado en el PATH actual.[/]\n\n"
            "El programa seguirá abierto. Si instalaste Platform Tools,\n"
            "abre una nueva terminal y vuelve a ejecutar el script.\n\n"
            "  [cyan]winget install Google.PlatformTools[/]   ← instalar ADB",
            title="⚠ ADB no encontrado", border_style="yellow"))
        console.print("[dim]Esperando... (presiona Ctrl+C para salir)[/]\n")

    # Iniciar hilos de fondo
    threading.Thread(target=_device_watcher, daemon=True, name="DeviceWatcher").start()
    threading.Thread(target=_stdin_reader,   daemon=True, name="StdinReader").start()

def _print_waiting_screen():
    """Pantalla de espera mientras no hay dispositivo."""
    os.system("cls" if os.name == "nt" else "clear")
    console.print(Panel(
        "[bold red] ____  _           _                  ____            _     _ \n"
        "|  _ \\| |__   __ _| |_ ___  _ __ ___|  _ \\_ __ ___ (_) __| |\n"
        "| |_) | '_ \\ / _` | __/ _ \\| '_ ` _ \\ | | | '__/ _ \\| |/ _` |\n"
        "|  __/| | | | (_| | || (_) | | | | | | |_| | | | (_) | | (_| |\n"
        "|_|   |_| |_|\\__,_|\\__\\___/|_| |_| |_|____/|_|  \\___/|_|\\__,_|[/]\n\n"
        "[bold cyan]  v1.0  •  Controlador Autónomo Android  •  ADB + scrcpy[/]",
        border_style="red", padding=(1, 2)))

    console.print(Panel(
        "\n"
        "  [bold yellow]⏳ Esperando celular...[/]\n\n"
        "  [white]1.[/] [cyan]Conecta el celular por USB[/]\n"
        "  [white]2.[/] [cyan]Acepta el popup 'Permitir depuración USB'[/]\n"
        "  [white]3.[/] [cyan]Asegúrate que el celular esté en la misma WiFi que esta PC[/]\n\n"
        "  [dim]El programa configura ADB WiFi automáticamente.[/]\n"
        "  [dim]Luego podrás desconectar el cable.[/]\n",
        border_style="yellow", padding=(0, 2)))


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    # Verificar ADB disponible
    ok, out = run_adb("version")
    if not ok:
        console.print(Panel(
            "[bold yellow]⚠ ADB no detectado en el PATH actual.[/]\n\n"
            "  [cyan]winget install Google.PlatformTools[/]   ← instalar ADB\n\n"
            "Luego cierra y abre la terminal de nuevo.",
            title="⚠ ADB no encontrado", border_style="yellow"))
        input("Presiona Enter para salir...")
        return

    # Iniciar hilos de fondo
    threading.Thread(target=_device_watcher, daemon=True, name="DeviceWatcher").start()
    threading.Thread(target=_stdin_reader,   daemon=True, name="StdinReader").start()

    try:
        in_menu     = False   # True cuando el menú de 54 opciones ya está dibujado
        needs_draw  = True    # True cuando hay que redibujar la pantalla en el próximo ciclo

        while True:

            # ── FASE 1: Sin dispositivo → pantalla de espera ─────────────
            # current_device es None hasta que el watcher complete el setup WiFi
            if not current_device:
                # Solo redibujamos si cambiamos de fase (veníamos del menú) o es la primera vez
                if needs_draw or in_menu:
                    _print_waiting_screen()
                    in_menu    = False
                    needs_draw = False

                # Esperamos un evento del watcher (señal vacía "") o simplemente un timeout
                # timeout=2 evita quedarse bloqueado para siempre si no hay eventos
                try:
                    _input_q.get(timeout=2)
                except queue.Empty:
                    pass   # sin novedades, seguimos esperando
                continue   # volvemos al inicio del while para chequear current_device

            # ── FASE 2: Con dispositivo → menú completo ──────────────────
            # Solo redibujamos cuando needs_draw=True (evita parpadeo constante)
            if needs_draw or not in_menu:
                os.system("cls" if os.name == "nt" else "clear")
                print_banner()   # muestra ASCII art + estado de conexión
                print_menu()     # muestra las 54 opciones en 3 columnas
                console.print("\n[bold white]Opción ()[/]: ", end="")
                in_menu    = True
                needs_draw = False

            # Bloqueamos hasta que el usuario escriba algo o pasen 4 segundos
            try:
                choice = _input_q.get(timeout=4)
            except queue.Empty:
                # Timeout sin input: aprovechamos para detectar si el celular se desconectó
                if not current_device:
                    needs_draw = True   # volvemos a fase 1 en el próximo ciclo
                continue

            choice = choice.strip()   # elimina espacios y saltos de línea sobrantes

            if choice == "99":
                _stop_event.set()   # le dice a los hilos de fondo que paren
                console.print("\n[bold cyan]Hasta luego 👋[/]")
                break

            if not choice:   # string vacío = señal del watcher (no input real del usuario)
                time.sleep(2)   # pausa para leer los mensajes del watcher antes de redibujar
                needs_draw = True
                continue

            fn = COMMANDS.get(choice)
            if fn:
                fn()
            else:
                console.print("[yellow]Opción inválida.[/]")
                time.sleep(0.8)

            needs_draw = True

    except KeyboardInterrupt:
        _stop_event.set()
        console.print("\n[bold cyan]Saliendo...[/]")


if __name__ == "__main__":
    main()
