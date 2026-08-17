#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PokemonCatcher via ADB
======================
Automatiza la captura de Pokémon en Pokémon GO enviando inputs
directamente al celular vía ADB (sin mouse ni pyautogui).

Resolución del Moto G52: 1080x2400
Requiere: pip install opencv-python numpy rich

Uso:
  1. Asegúrate de estar conectado al celular (phantom_droid.py o adb devices)
  2. Ajusta las coordenadas SNIPER_X / SNIPER_Y si tu versión del juego las tiene distintas
  3. Ejecuta: python pokemon_catcher.py
  4. Presiona Ctrl+C para detener
"""

import subprocess
import sys
import os
import time
import random
import io
import shutil
import threading
import queue
import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Tuple

# ── Refrescar PATH desde el registro de Windows ───────────────────────────
# Permite encontrar ADB/platform-tools aunque la terminal no haya recargado
# las variables de entorno del sistema.
if sys.platform == "win32":
    import winreg
    def _refresh_path() -> None:
        paths = []
        for hive, sub in [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ]:
            try:
                with winreg.OpenKey(hive, sub) as k:
                    val, _ = winreg.QueryValueEx(k, "Path")
                    paths.append(val)
            except FileNotFoundError:
                pass
        if paths:
            os.environ["PATH"] = (os.pathsep.join(paths)
                                  + os.pathsep
                                  + os.environ.get("PATH", ""))
    _refresh_path()

import cv2
import numpy as np
from rich.console import Console
from rich.panel import Panel

# Importar diagnostico para obtener coordenadas automáticas
try:
    from diagnostico import mostrar_diagnostico
    DIAGNOSTICO_DISPONIBLE = True
    print("[INIT] ✓ diagnostico.py importado correctamente")
except ImportError as e:
    print(f"[INIT] ⚠ Error importando diagnostico: {e}")
    DIAGNOSTICO_DISPONIBLE = False
    mostrar_diagnostico = None
except Exception as e:
    print(f"[INIT] ⚠ Error inesperado importando diagnostico: {e}")
    DIAGNOSTICO_DISPONIBLE = False
    mostrar_diagnostico = None

# Importar detectores mejorados
try:
    from detector_modales import detectar_boton_x as detectar_boton_x_mejorado
    from detector_modales import detectar_checkmark as detectar_checkmark_mejorado
except ImportError:
    # Fallback si detector_modales no está disponible
    detectar_boton_x_mejorado = None
    detectar_checkmark_mejorado = None

# ══════════════════════════════════════════════════════════════════════════
#  GESTOR AUTOMÁTICO DE OLLAMA (IA)
# ══════════════════════════════════════════════════════════════════════════

class OllamaManager:
    """Gestiona el proceso de Ollama automáticamente."""
    
    def __init__(self):
        self.proceso = None
        self.iniciado_por_nosotros = False
    
    def verificar_ollama(self) -> bool:
        """Verifica si Ollama ya está corriendo."""
        try:
            import requests
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def iniciar_ollama(self) -> bool:
        """Inicia Ollama si no está corriendo. Retorna True si está disponible."""
        if self.verificar_ollama():
            console.print("[dim green]✓ Ollama ya está corriendo[/]")
            return True
        
        try:
            console.print("[cyan]Iniciando Ollama localmente...[/]")
            if sys.platform == "win32":
                # Windows: buscar ollama en PATH o carpeta predeterminada
                self.proceso = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                # Linux/Mac
                self.proceso = subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            self.iniciado_por_nosotros = True
            
            # Esperar a que Ollama esté listo (máximo 10s)
            for intento in range(20):
                time.sleep(0.5)
                if self.verificar_ollama():
                    console.print("[dim green]✓ Ollama iniciado correctamente[/]")
                    return True
            
            console.print("[yellow]⚠ Ollama inició pero tardó en responder[/]")
            return True
            
        except FileNotFoundError:
            console.print("[bold red]❌ Ollama no encontrado. Instálalo con: ollama install[/]")
            return False
        except Exception as e:
            console.print(f"[bold red]❌ Error al iniciar Ollama: {e}[/]")
            return False
    
    def detener_ollama(self, force: bool = False) -> bool:
        """
        Detiene Ollama.
        - Si force=False: solo detiene si lo iniciamos nosotros
        - Si force=True: intenta detenerlo incluso si estaba corriendo antes (RECOMENDADO para Ctrl+C)
        """
        if force:
            # Forzar detención: intentar matar proceso por nombre
            console.print("[dim yellow]Terminando Ollama (forzado)...[/]")
            try:
                if sys.platform == "win32":
                    os.system("taskkill /F /IM ollama.exe 2>nul")
                else:
                    # Linux/Mac: usar pkill
                    os.system("pkill -9 ollama 2>/dev/null")
                console.print("[dim green]✓ Ollama terminado[/]")
                return True
            except Exception as e:
                if DEBUG:
                    console.print(f"[dim yellow]⚠ No se pudo terminar Ollama (forzado): {e}[/]")
                return False
        else:
            # Solo detener si lo iniciamos nosotros
            if self.proceso and self.iniciado_por_nosotros:
                try:
                    console.print("[dim yellow]Cerrando Ollama...[/]")
                    self.proceso.terminate()
                    self.proceso.wait(timeout=5)
                    console.print("[dim green]✓ Ollama cerrado[/]")
                    return True
                except:
                    try:
                        self.proceso.kill()
                        console.print("[dim green]✓ Ollama terminado (kill)[/]")
                        return True
                    except:
                        return False
            return False

# Instancia global de Ollama
ollama_manager = OllamaManager()

# ── CONTROL DE IA ──────────────────────────────────────────────────────────
_usar_ia = False  # 🆕 DEFECTO: Deshabilitada (solo templates). Usar --enable-ia para activar

# ── OPTIONAL: IA AGENT (Ollama local) ──────────────────────────────────────
try:
    from ia_agent import analizar_pantalla as ia_analizar
    IA_DISPONIBLE = True
except ImportError:
    IA_DISPONIBLE = False
    ia_analizar = None

# ── DETECTORES MEJORADOS (basados en features, no colores) ────────────────────
try:
    from detectors_mejorados import DetectoresRobustos
    DETECTORES_MEJORADOS = True
except ImportError:
    DETECTORES_MEJORADOS = False

# ── LOGGING DE ANÁLISIS (para aprendizaje posterior) ─────────────────────────
try:
    from analysis_logger import AnalysisLogger
    logger = AnalysisLogger()
    LOGGING_DISPONIBLE = True
except ImportError:
    LOGGING_DISPONIBLE = False
    logger = None

console = Console()

# ══════════════════════════════════════════════════════════════════════════
#  SISTEMAS GLOBALES OPTIMIZADOS
# ══════════════════════════════════════════════════════════════════════════

# ── MEJORA 2: CACHE CIRCULAR DE SCREENSHOTS (50-100ms) ──────────────────
@dataclass
class CachedScreenshot:
    img: np.ndarray
    timestamp: float
    hash_val: str

_screenshot_cache: Optional[CachedScreenshot] = None
_lock_cache = threading.Lock()
SCREENSHOT_CACHE_DURATION_MS = 50  # Cachear durante 50ms

def screenshot_adb_cached(force_fresh: bool = False) -> Optional[np.ndarray]:
    """Devuelve screenshot con cache de 50ms para evitar captures innecesarias."""
    global _screenshot_cache
    
    if not force_fresh:
        with _lock_cache:  # Proteger lectura del cache (evita race condition entre hilos)
            if _screenshot_cache is not None:
                elapsed = (time.time() - _screenshot_cache.timestamp) * 1000
                if elapsed < SCREENSHOT_CACHE_DURATION_MS:
                    return _screenshot_cache.img  # Usar cache
    
    # Capturar fresco
    img = screenshot_adb()
    if img is not None:
        with _lock_cache:
            hash_val = hashlib.md5(cv2.imencode('.jpg', img)[1]).hexdigest()[:8]
            _screenshot_cache = CachedScreenshot(img=img, timestamp=time.time(), hash_val=hash_val)
    return img

# ── MEJORA 4: LOGGING ASINCRÓNICO EN COLA ────────────────────────────────
_log_queue = queue.Queue()
_logger_thread = None
_logger_active = False

def _logger_worker():
    """Hilo que procesa logs asincronamente sin bloquear el loop principal."""
    while _logger_active:
        try:
            msg = _log_queue.get(timeout=0.5)
            if msg is not None:
                console.print(msg)
        except queue.Empty:
            pass

def _iniciar_logger_asinc():
    """Inicia el hilo de logging asincrónico."""
    global _logger_active, _logger_thread
    _logger_active = True
    _logger_thread = threading.Thread(target=_logger_worker, daemon=True)
    _logger_thread.start()

def _detener_logger_asinc():
    """Detiene el logger asincrónico."""
    global _logger_active
    _logger_active = False

def log_async(msg: str, sync: bool = False):
    """Envía log a cola asincrónica. Si sync=True, log inmediato (bloqueante)."""
    if sync or not _logger_active:
        console.print(msg)
    else:
        try:
            _log_queue.put_nowait(msg)
        except queue.Full:
            console.print(msg)  # Fallback sincrónico

# ── MEJORA 5: PANEL DE ESTADÍSTICAS EN TIEMPO REAL ──────────────────────
@dataclass
class Estadisticas:
    pokemon_capturados: int = 0
    pokemon_fallidos: int = 0
    pokebolas_totales: int = 0
    tiempo_inicio: float = field(default_factory=time.time)
    pokebola_favorita_uso: dict = field(default_factory=lambda: {"NORMAL": 0, "ULTRA": 0, "LEJANO": 0, "SUPER_ULTRA": 0})
    aciertos_por_tipo: dict = field(default_factory=lambda: {"NORMAL": 0, "ULTRA": 0, "LEJANO": 0, "SUPER_ULTRA": 0})
    
    def tiempo_transcurrido_min(self) -> float:
        return (time.time() - self.tiempo_inicio) / 60
    
    def pokemon_por_hora(self) -> float:
        mins = self.tiempo_transcurrido_min()
        return (self.pokemon_capturados / mins * 60) if mins > 0 else 0
    
    def tasa_exito(self) -> float:
        total = self.pokemon_capturados + self.pokemon_fallidos
        return (self.pokemon_capturados / total * 100) if total > 0 else 0

_stats = Estadisticas()
_lock_stats = threading.Lock()

def registrar_captura_stats(tipo_pokebola: str):
    """Registra captura exitosa."""
    with _lock_stats:
        _stats.pokemon_capturados += 1
        _stats.pokebolas_totales += 1
        _stats.aciertos_por_tipo[tipo_pokebola] = _stats.aciertos_por_tipo.get(tipo_pokebola, 0) + 1

def registrar_fallo_stats(tipo_pokebola: str):
    """Registra intento fallido."""
    with _lock_stats:
        _stats.pokemon_fallidos += 1
        _stats.pokebolas_totales += 1

def mostrar_stats():
    """Muestra panel de estadísticas actuales."""
    with _lock_stats:
        pxh = _stats.pokemon_por_hora()
        log_async(f"[bold cyan]📊 STATS:[/] ✅ {_stats.pokemon_capturados} | ❌ {_stats.pokemon_fallidos} | "
                 f"Tasa: {_stats.tasa_exito():.1f}% | {pxh:.1f} Pokémon/h | Tiempo: {_stats.tiempo_transcurrido_min():.1f}min")

# ── MEJORA 1: SISTEMA DE EVENTOS PARA ESPERAS INTELIGENTES ───────────────
_event_diagnostico_cambio = threading.Event()
_event_captura_confirmada = threading.Event()

def notify_diagnostico_cambio():
    """Notifica que el diagnóstico cambió (despierta threads en espera)."""
    _event_diagnostico_cambio.set()
    time.sleep(0.05)
    _event_diagnostico_cambio.clear()

def wait_for_diagnostico_cambio(timeout_s: float = 0.5):
    """Espera inteligentemente hasta que el diagnóstico cambie o timeout."""
    _event_diagnostico_cambio.wait(timeout=timeout_s)

# ── MEJORA 7: BUFFER CIRCULAR PARA EVITAR OSCILACIONES ────────────────────
_estado_buffer = deque(maxlen=10)  # Últimos 10 estados
_lock_estado_buffer = threading.Lock()

def registrar_estado_detectado(estado: str):
    """Agrega estado al buffer circular."""
    with _lock_estado_buffer:
        _estado_buffer.append((estado, time.time()))

def es_estado_estable(estado: str, min_confirmaciones: int = 3) -> bool:
    """Verifica si un estado aparece N veces consecutivas (evita oscilaciones)."""
    with _lock_estado_buffer:
        if len(_estado_buffer) < min_confirmaciones:
            return False
        return all(s[0] == estado for s in list(_estado_buffer)[-min_confirmaciones:])

def detectar_oscilacion() -> bool:
    """Detecta si hay oscilación rápida entre estados."""
    with _lock_estado_buffer:
        if len(_estado_buffer) < 5:
            return False
        # Si los últimos 5 estados son alternancia rápida (~100ms cada uno)
        últimos_5 = list(_estado_buffer)[-5:]
        for i in range(1, len(últimos_5)):
            if últimos_5[i][1] - últimos_5[i-1][1] > 0.2:  # Cambio lento, no es oscilación
                return False
        # Todos dentro de 200ms = oscilación
        return últimos_5[-1][1] - últimos_5[0][1] < 0.2

# ══════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN — ajusta si es necesario
# ══════════════════════════════════════════════════════════════════════════

# Serial del dispositivo (vacío = usa el único conectado)
DEVICE_SERIAL: str = ""

# Resolución del celular (moto g52)
PHONE_W = 1080
PHONE_H = 2400

# --- Coordenadas del sniper (panel de Pokémon cercanos) ---
# ⚠ Los pokemones cercanos se muestran en el panel IZQUIERDO SUPERIOR
# Para recalibrar: en scrcpy hover sobre cada elemento y usa el X,Y que muestra
SNIPER_X        = 50    # X en la zona izquierda donde aparecen pokemones cercanos
SNIPER_SLOT_X   = 48    # X de los íconos en el panel izquierdo (borde IZQUIERDO)
# El botón ≡ (toggle del panel) está en SNIPER_Y_TOGGLE.
# Los iconos de Pokémon en el mapa empiezan en SNIPER_Y_FIRST
SNIPER_Y_TOGGLE      = 221   # botón ≡ que abre/cierra el panel  ← ajustar con scrcpy hover
SNIPER_Y_FIRST       = 231   # coordenada Y del PRIMER Pokémon en el panel ← verificado por usuario
SNIPER_SLOT_HEIGHT   = 80    # separación entre íconos del panel ← ajustar con scrcpy hover
SNIPER_MAX_SLOTS     = 12    # cuántos slots intentar como máximo (aumentado de 6)

# --- Lanzamiento de Pokébola (swipe hacia arriba desde la bola) ---
# Calibrado desde screenshot real 1080x2400 del Moto G52
# Centro real de la Pokébola detectado por color: (546, 1342)
THROW_START_X        = 546    # centro horizontal de la bola
THROW_START_Y        = 1420   # ligeramente más abajo para mayor arco
THROW_END_X          = 540    # ligeramente centrado
THROW_END_Y               = 700   # tiro NORMAL      (1420-700  = 720px)
THROW_END_Y_FAR           = 340   # tiro LEJANO      (1420-340  = 1080px, ~1.5×)
THROW_END_Y_ULTRA         =  50   # tiro ULTRA       (1420-50   = 1370px, ~1.9×)
THROW_END_Y_SUPER_ULTRA   = -80   # tiro SUPER ULTRA (1420+80   = 1500px, fuera de pantalla)
THROW_DURATION_MS             = 300  # swipe normal (ms)
THROW_DURATION_FAR_MS         = 260  # lejano: más rápido = más fuerza
THROW_DURATION_ULTRA_MS       = 215  # ultra
THROW_DURATION_SUPER_ULTRA_MS = 195  # super ultra: máxima fuerza

# --- Tap para cerrar diálogos post-captura ---
# Pantalla XP: botón OK verde centrado (aparece al capturar)
OK_XP_X    = 547   # Coordenada verificada del botón DE ACUERDO en tarjeta XP
OK_XP_Y    = 1570  # Coordenada verificada del botón DE ACUERDO en tarjeta XP
# Pantalla detalle pokémon: botón ✓ teal (checkmark confirmación)
CHECKMARK_X = 547  # Coordenada verificada del checkmark azul/celeste
CHECKMARK_Y = 2142  # Coordenada verificada del checkmark azul/celeste
# Diálogo "Do you want to exit Pokémon GO?" → botón CANCEL
CANCEL_EXIT_X = PHONE_W // 2
CANCEL_EXIT_Y = 1608  # Botón CANCELAR del diálogo ¿Salir de Pokémon GO? (verificado en foto)
# Fallback genérico (pokedex / otras pantallas desconocidas)
DISMISS_X = PHONE_W // 2
DISMISS_Y = 1800

# --- Thresholds de detección (0-1, más alto = más estricto) ---
THRESHOLD_CAMARA       = 0.70   # ícono cámara → pantalla de captura
THRESHOLD_CONFIRMACION = 0.75   # check verde → Pokémon capturado (aumentado de 0.70)
THRESHOLD_AURIOLA      = 0.65   # aro verde   → animación de lanzamiento en curso

# --- Mejoras de captura (NUEVO) ---
USAR_BAYAS_AUTOMATICO  = False  # ❌ DESACTIVADO: PGSharp ya maneja bayas automáticamente
WAIT_FOR_BETTER_ARO    = True   # ✅ Esperar a mejor momento del aro antes de lanzar
MIN_AURIOLA_PARA_TIRAR = 0.50   # Umbral mínimo de auriola para lanzar (reducido de 0.70 a 0.50)
MAX_ESPERA_ARO_MS      = 5000   # máx 5s esperando mejor aro (reducido de 8000)
BAYA_X = 150   # X aproximada del botón de baya (zona izq) - no usada
BAYA_Y = 1900  # Y aproximada del botón de baya (zona baja) - no usada

# --- Tiempos de espera ---
WAIT_AFTER_ENTER_BATTLE = 3.5   # segundos tras abrir la pantalla de captura
WAIT_AFTER_THROW        = 4.0   # segundos tras lanzar la Pokébola (aumentado a 4.0s para mejor detección)
WAIT_AFTER_CATCH        = 2.5   # segundos tras confirmar la captura (aumentado: más estable)
WAIT_BETWEEN_LOOPS      = 1.2   # segundos entre ciclos del loop principal (aumentado: menos prisa)
DELAY_ACCION            = 0.8   # delay global tras cada tap (aumentado: más tiempo para procesar)
WAIT_SNIPER_ENTRE_TAPS  = 0.10  # pausa entre los 2 taps del sniper (100ms - balance entre rapidez y confiabilidad)
WAIT_SNIPER_POST_TAP    = 0.05  # espera MÍNIMA DESPUÉS del doble tap antes de polling (50ms)
WAIT_SNIPER_AFTER_TAP   = 2.0   # espera tras tap sniper para abrir combate (2s, menos bloqueante)

# --- Detección de Pokémon en mapa (círculo/sombra blanca bajo el sprite) ---
# Área del contorno blanco en px² (filtro de tamaño)
MAP_POKEMON_AREA_MIN  = 300
MAP_POKEMON_AREA_MAX  = 9000
# Circularidad mínima (0=barra, 1=círculo perfecto) — sombra del sprite ≈ 0.45-0.85
MAP_POKEMON_CIRCULARITY = 0.40
# Zona del mapa a escanear como fracción de la pantalla (excluye UI inferior y sniper derecho)
MAP_ROI_TOP    = 0.15
MAP_ROI_BOTTOM = 0.82
MAP_ROI_LEFT   = 0.04
MAP_ROI_RIGHT  = 0.87
# Distancia mínima entre dos detecciones para no contar el mismo Pokémon 2x (px)
MAP_DEDUP_DIST = 50

# --- Barra izquierda (encuentro rápido con doble tap casi continuo) ---
# ⚠ DESACTIVADA: las coordenadas (55,350) abren el popup de CLIMA en lugar de un encuentro.
# Para activarla: pon BARRA_IZQ_ACTIVA = True y ajusta BARRA_IZQ_Y con el modo calibración.
BARRA_IZQ_ACTIVA        = False
BARRA_IZQ_X             = 55     # X borde izquierdo
BARRA_IZQ_Y             = 350    # ⚠ esta Y toca el ícono de CLIMA — ajustar antes de activar
BARRA_IZQ_TAP_GAP_MS    = 80     # ms entre los 2 taps (casi continuo = <100ms)

# ── Carga de calibración IA (calibrar_con_ia.py → calibracion_ia.json) ────
# Si existe el archivo, sobreescribe las coordenadas calibradas manualmente.
_CALIB_FILE = os.path.join(os.path.dirname(__file__), "calibracion_ia.json")
if os.path.exists(_CALIB_FILE):
    try:
        import json as _json
        with open(_CALIB_FILE) as _f:
            _calib = _json.load(_f)
        if "boton_de_acuerdo" in _calib:
            OK_XP_X = _calib["boton_de_acuerdo"]["x"]
            OK_XP_Y = _calib["boton_de_acuerdo"]["y"]
            # NO tocar CHECKMARK_X/Y — es un botón distinto (Y~2142 vs Y~1570)
            # CHECKMARK es el teal check que aparece después del "DE ACUERDO"
        if "sniper_primer_pokemon" in _calib:
            SNIPER_X = _calib["sniper_primer_pokemon"]["x"]
            _sniper_y = _calib["sniper_primer_pokemon"]["y"]
            # NO sobreescribir: el usuario verificó que Y=231 es correcto
            # La calibración OpenCV detecta falsos positivos en esta zona
            # SNIPER_Y_FIRST se mantiene hardcoded en 231
            print(f"[Calib] sniper_primer_pokemon ignorado (Y={_sniper_y}) — usando hardcoded {SNIPER_Y_FIRST}")
        if "umbral_contraste" in _calib:
            _CONTRASTE_UMBRAL_CALIBRADO = _calib["umbral_contraste"]
        else:
            _CONTRASTE_UMBRAL_CALIBRADO = None
        print(f"[Calib] ✅ calibracion_ia.json cargada — {list(_calib.keys())}")
        del _json, _f, _calib
    except Exception as _e:
        print(f"[Calib] ⚠ No se pudo leer calibracion_ia.json: {_e}")
        _CONTRASTE_UMBRAL_CALIBRADO = None
else:
    _CONTRASTE_UMBRAL_CALIBRADO = None

# ── Posiciones para cerrar pantallas no deseadas (Moto G52 1080×2400) ──────
# Se prueban en orden hasta que la pantalla cambie visiblemente.
# Ajusta o añade más coordenadas según los modales que aparezcan en tu cuenta.
_ESCAPE_TAPS: list[tuple[int, int]] = [
    (540,  175),   # X centrado-superior  (raid invite, huevo, investigación, evento)
    (540, 2200),   # botón inferior grande (¡GENIAL!, ACEPTAR, CONTINUAR, OK)
    (950,  190),   # X esquina derecha-sup (tienda, mochila, Pokédex)
    (130,  190),   # X esquina izquierda-sup (algunos modales de evento)
    (540, 1800),   # tap genérico de descarte (centro-bajo, para modales sin botón claro)
]

# ── Modo debug: muestra confianza numérica de cada template en cada ciclo ──
DEBUG = True

# ── Carpeta base del bot (donde están las imágenes de referencia) ──────────
BOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pokmoengobot")

# ── Sistema de vigilancia de confirmación en background ──────────────────
# Hilo que monitorea constantemente si aparece el botón de confirmación
_vigilancia_activa = False  # Flag para encender/apagar vigilancia
_vigilancia_thread = None   # Referencia al hilo
_lock_vigilancia = threading.Lock()  # Para acceso thread-safe a variables compartidas
_confirmacion_vista_recientemente = False  # Confirmación detectada en los últimos 0.5s

# ── Sistema de vigilancia de X (cierre de modales) ──────────────────────────
# Hilo independiente que detecta y clickea la X automáticamente
_vigilancia_x_activa = False  # Flag para encender/apagar vigilancia de X
_vigilancia_x_thread = None   # Referencia al hilo
_lock_vigilancia_x = threading.Lock()  # Para acceso thread-safe
_x_detectada_recientemente = False  # X detectada recientemente

# ── Sistema de diagnóstico centralizado (hilo independiente) ────────────────
# Mantiene el estado detectado actualizado sin capturar en cada ciclo principal
_estado_diagnostico = "DESCONOCIDO"  # "MAPA" | "COMBATE" | "CARGANDO" | "DESCONOCIDO"
_diagnostico_activo = False  # Flag para encender/apagar diagnóstico
_diagnostico_thread = None   # Referencia al hilo
_lock_diagnostico = threading.Lock()  # Para acceso thread-safe a estado diagnostico
_diagnostico_screenshot = None  # Última captura (compartida con hilo principal)
_diagnostico_congelado = False  # Flag: si True, NO actualizar _estado_diagnostico (durante impacto de bola)
_tiempo_diagnostico_descongelado = None  # Timestamp para cuando descongelar

# ── Sistema de pokébolas adaptativas (seleccionar tipo dinámicamente) ────────
# Empieza con ULTRA, si funciona repite, si falla pasa a siguiente
_pokebola_favorita = "SUPER_ULTRA"  # NORMAL | ULTRA | SUPER_ULTRA | LEJANO
_pokebola_intentos_fallidos = 0  # Contador de intentos fallidos con pokébola actual
_lock_pokebola = threading.Lock()  # Thread-safe access
_POKEBOLA_MAX_INTENTOS_ANTES_CAMBIO = 5  # Si falla 5 veces, cambiar a siguiente (aumentado de 3 a 5)

# ── MEJORA 8: GESTIÓN DINÁMICA DE INTENTOS (Adaptive Strategy) ────────────
# Aprende del historial qué tipo de pokébola funciona mejor con qué Pokémon
_pokebola_tasa_exito: dict[str, float] = {"ULTRA": 0.7, "SUPER_ULTRA": 0.8, "LEJANO": 0.6, "NORMAL": 0.4}
_pokebola_intentos_totales: dict[str, int] = {"ULTRA": 0, "SUPER_ULTRA": 0, "LEJANO": 0, "NORMAL": 0}
_lock_pokebola_stats = threading.Lock()

def actualizar_tasa_exito_pokebola(tipo: str, éxito: bool):
    """Actualiza las estadísticas de éxito para cada tipo de pokébola."""
    global _pokebola_tasa_exito, _pokebola_intentos_totales
    with _lock_pokebola_stats:
        _pokebola_intentos_totales[tipo] = _pokebola_intentos_totales.get(tipo, 0) + 1
        total = _pokebola_intentos_totales[tipo]
        # Promedio móvil: 70% peso anterior, 30% resultado actual
        anterior = _pokebola_tasa_exito.get(tipo, 0.5)
        _pokebola_tasa_exito[tipo] = anterior * 0.7 + (1.0 if éxito else 0.0) * 0.3

def obtener_pokebola_optima() -> str:
    """Selecciona tipo de pokébola basado en tasa de éxito histórica."""
    with _lock_pokebola_stats:
        # Excluir NORMAL del historial — solo ULTRA, SUPER_ULTRA, LEJANO
        # Nunca caer a pokébolas normales aunque el historial sugiera lo contrario
        tipos_validos = {k: v for k, v in _pokebola_tasa_exito.items() if k != "NORMAL"}
        return max(tipos_validos.items(), key=lambda x: x[1] + random.uniform(0, 0.05))[0]

# ── MEJORA 9: DETECCIÓN PREDICTIVA DE ESTADO ───────────────────────────────
# Predice cambios de estado antes de que ocurran basándose en histórico reciente
_prediccion_estado_ultimo: Optional[str] = None
_prediccion_confianza: float = 0.0
_tiempo_cambio_estado_anterior: float = 0.0

def predecir_proximo_estado(estado_actual: str) -> Tuple[Optional[str], float]:
    """
    Predice cuál será el próximo estado basándose en transiciones históricas.
    Devuelve (estado_predicho, confianza_0a1).
    """
    global _prediccion_estado_ultimo, _prediccion_confianza, _tiempo_cambio_estado_anterior
    
    # Transiciones conocidas y su probabilidad
    transiciones = {
        "MAPA": {"ESPERANDO_COMBATE": 0.9, "DESCONOCIDO": 0.1},
        "ESPERANDO_COMBATE": {"COMBATE": 0.85, "MAPA": 0.1, "DESCONOCIDO": 0.05},
        "COMBATE": {"POST-CAPTURA": 0.7, "COMBATE": 0.2, "MAPA": 0.1},
        "POST-CAPTURA": {"MAPA": 0.95, "COMBATE": 0.05},
    }
    
    probs = transiciones.get(estado_actual, {})
    if not probs:
        return None, 0.0
    
    # Seleccionar estado con mayor probabilidad
    estado_predicho = max(probs.items(), key=lambda x: x[1])
    return estado_predicho[0], estado_predicho[1]

# ── Nombres de templates (versiones escaladas a 1080px de ancho) ────────────
# Si no existe la versión _1080, usa la original como fallback
def _tmpl_name(base: str) -> str:
    scaled = base.replace(".jpg", "_1080.jpg")
    if os.path.exists(os.path.join(BOT_DIR, scaled)):
        return scaled
    return base


# ══════════════════════════════════════════════════════════════════════════
#  ADB HELPERS
# ══════════════════════════════════════════════════════════════════════════

# Buscar ADB en múltiples ubicaciones
_ADB_PATH = None
def _find_adb():
    """Busca ADB en múltiples ubicaciones."""
    global _ADB_PATH
    if _ADB_PATH:
        return _ADB_PATH
    
    # Buscar en PATH del sistema
    adb = shutil.which("adb")
    if adb:
        _ADB_PATH = adb
        return _ADB_PATH
    
    # Buscar en ubicaciones comunes
    for path in [
        "/tmp/platform-tools/adb",
        os.path.expanduser("~/Android/platform-tools/adb"),
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/opt/android-sdk/platform-tools/adb",
    ]:
        if os.path.exists(path):
            _ADB_PATH = path
            return _ADB_PATH
    
    return "adb"  # fallback: asumir que está en PATH

def _adb(*args, timeout: int = 15) -> tuple[bool, str]:
    """Ejecuta un comando ADB y devuelve (ok, stdout+stderr)."""
    adb_cmd = _find_adb()
    cmd = [adb_cmd]
    if DEVICE_SERIAL:
        cmd += ["-s", DEVICE_SERIAL]
    cmd += list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return False, "ADB no encontrado en PATH"


def screenshot_adb() -> np.ndarray | None:
    """
    Captura la pantalla del celular via ADB y devuelve un array numpy BGR.
    Usa 'adb exec-out screencap -p' que devuelve PNG por stdout (más rápido que pull).
    """
    adb_cmd = _find_adb()
    cmd = [adb_cmd]
    if DEVICE_SERIAL:
        cmd += ["-s", DEVICE_SERIAL]
    cmd += ["exec-out", "screencap", "-p"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        if r.returncode != 0 or not r.stdout:
            return None
        arr = np.frombuffer(r.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
#  MEJORA 10: POOL DE THREADS PARA ADB PARALELO
# ══════════════════════════════════════════════════════════════════════════

from concurrent.futures import ThreadPoolExecutor

_adb_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="adb_worker")
_adb_queue: queue.Queue[Tuple[list, dict, queue.Queue]] = queue.Queue()

def _adb_async(*args, timeout: int = 15) -> 'queue.Queue[Tuple[bool, str]]':
    """Ejecuta comando ADB de forma asincrónica. Devuelve una Queue para obtener resultado."""
    result_queue: queue.Queue[Tuple[bool, str]] = queue.Queue()
    _adb_pool.submit(_adb_worker_task, args, timeout, result_queue)
    return result_queue

def _adb_worker_task(args: tuple, timeout: int, result_queue: 'queue.Queue'):
    """Worker que ejecuta ADB en thread pool."""
    ok, out = _adb(*args, timeout=timeout)
    result_queue.put((ok, out))

def get_adb_result(result_queue: 'queue.Queue[Tuple[bool, str]]', timeout_s: float = 0.5) -> Optional[Tuple[bool, str]]:
    """Obtiene resultado de ADB asincrónico con timeout."""
    try:
        return result_queue.get(timeout=timeout_s)
    except queue.Empty:
        return None


def tap(x: int, y: int, delay: float = DELAY_ACCION):
    """Envía un tap al celular en las coordenadas dadas (coordenadas del teléfono)."""
    _adb("shell", "input", "tap", str(x), str(y))
    if delay > 0:
        time.sleep(delay)


def double_tap(x: int, y: int, delay: float = 0.12):
    """Envía un doble tap SIN delays globales (máxima velocidad)."""
    # Sin delay_accion en cada tap individual
    _adb("shell", "input", "tap", str(x), str(y))
    time.sleep(delay)
    _adb("shell", "input", "tap", str(x), str(y))


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 350):
    """Envía un swipe al celular."""
    _adb("shell", "input", "swipe",
         str(x1), str(y1), str(x2), str(y2), str(duration_ms))


# ══════════════════════════════════════════════════════════════════════════
#  MEJORA 3: FUNCIONES DE ROI (REGION OF INTEREST)
# ══════════════════════════════════════════════════════════════════════════

def extract_roi(img: np.ndarray, top_pct: float, bottom_pct: float, 
                left_pct: float = 0.0, right_pct: float = 1.0) -> Tuple[np.ndarray, Tuple[int, int]]:
    """
    Extrae una región de interés de la imagen. Devuelve (roi_img, offset=(top_px, left_px)).
    Útil para reducir cálculo de OpenCV en áreas específicas.
    """
    h, w = img.shape[:2]
    y_top = int(h * top_pct)
    y_bottom = int(h * bottom_pct)
    x_left = int(w * left_pct)
    x_right = int(w * right_pct)
    roi = img[y_top:y_bottom, x_left:x_right]
    return roi, (y_top, x_left)

def _confidence_roi(screenshot_gray: np.ndarray, template: np.ndarray, 
                   top_pct: float = 0.0, bottom_pct: float = 1.0,
                   left_pct: float = 0.0, right_pct: float = 1.0) -> float:
    """Busca template solo dentro de ROI especificado. 30-50% más rápido."""
    if template is None or screenshot_gray is None:
        return 0.0
    
    roi, _ = extract_roi(screenshot_gray, top_pct, bottom_pct, left_pct, right_pct)
    
    if (template.shape[0] > roi.shape[0] or
            template.shape[1] > roi.shape[1]):
        return 0.0
    
    res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(res)
    return float(max_val)

# ══════════════════════════════════════════════════════════════════════════
#  MEJORA 6: PRECARGA DE TEMPLATES CON CARACTERÍSTICAS
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class TemplateOptimizado:
    """Template precompilado con características para matching más rápido."""
    img: np.ndarray
    nombre: str
    tamaño: Tuple[int, int]
    hash_sift: Optional[str] = None
    histograma: Optional[np.ndarray] = None

_templates_cache: dict[str, TemplateOptimizado] = {}
_lock_templates = threading.Lock()

def _precargar_templates(template_names: list[str]):
    """Precarga templates en startup para matching más rápido durante ejecución."""
    global _templates_cache
    with _lock_templates:
        for name in template_names:
            path = os.path.join(BOT_DIR, name.replace(".jpg", "_1080.jpg") if name.endswith(".jpg") else name)
            if not os.path.exists(path):
                path = os.path.join(BOT_DIR, name)
            
            if os.path.exists(path):
                img = _imread_unicode(path, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    hist = cv2.calcHist([img], [0], None, [256], [0, 256])
                    tmpl_opt = TemplateOptimizado(
                        img=img, 
                        nombre=name,
                        tamaño=img.shape,
                        histograma=hist
                    )
                    _templates_cache[name] = tmpl_opt

def _get_cached_template(name: str) -> Optional[TemplateOptimizado]:
    """Obtiene template precompilado del cache."""
    with _lock_templates:
        return _templates_cache.get(name)


# ══════════════════════════════════════════════════════════════════════════
#  CARGA DE TEMPLATES
# ══════════════════════════════════════════════════════════════════════════

def _imread_unicode(path: str, flags: int = cv2.IMREAD_GRAYSCALE) -> np.ndarray | None:
    """
    cv2.imread no soporta rutas con caracteres non-ASCII en Windows.
    Esta función usa np.fromfile + cv2.imdecode como alternativa segura.
    """
    try:
        buf = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(buf, flags)
    except Exception:
        return None


def _load_template(filename: str) -> np.ndarray | None:
    """Carga una imagen de referencia en escala de grises desde la carpeta del bot."""
    path = os.path.join(BOT_DIR, filename)
    img = _imread_unicode(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        console.print(f"[bold red]❌ No se pudo cargar template: {path}[/]")
    return img


def _confidence(screenshot_gray: np.ndarray, template: np.ndarray) -> float:
    """Devuelve la confianza máxima del template matching (0.0 si falla)."""
    if template is None or screenshot_gray is None:
        return 0.0
    if (template.shape[0] > screenshot_gray.shape[0] or
            template.shape[1] > screenshot_gray.shape[1]):
        return 0.0
    res = cv2.matchTemplate(screenshot_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(res)
    return float(max_val)


def _safe_back(ciclo: int) -> None:
    """
    Cierra pantalla con seguridad usando SOLO TAPS (nunca BACK directo).
    Si detecta diálogo de salida 'Do you want to exit?', toca CANCEL.
    """
    # NUNCA usar BACK directo - puede cerrar el juego
    # En su lugar, usar taps en zona de botones
    console.print(f"[dim]   [{ciclo}] Cerrando pantalla con TAPs (no BACK)...")
    
    # Intentar taps en zona de botón "DE ACUERDO" o de cierre
    for tap_num in range(3):
        # Verificar PRIMERO con screenshot real si ya estamos en MAPA
        # (no confiar en diagnóstico que puede estar congelado)
        img_check = screenshot_adb()
        if img_check is not None:
            pantalla_actual, _ = _detectar_pantalla_postcombate(img_check)
            if pantalla_actual == 'mapa':
                console.print(f"[dim green]   [{ciclo}] ✓ Ya en MAPA — no se necesita tap extra[/]")
                return
        
        tap(PHONE_W // 2, 2100, delay=0.3)  # Botón típicamente en Y=2100
        time.sleep(0.5)
        img = screenshot_adb()
        if img is None:
            continue
        
        # Verificar estado con screenshot real
        pantalla_post, _ = _detectar_pantalla_postcombate(img)
        if pantalla_post == 'mapa':
            console.print(f"[dim green]   [{ciclo}] ✓ Pantalla cerrada con tap {tap_num+1}[/]")
            return
    
    # Si sigue en DETALLE después de taps, revisar si hay diálogo de salida
    img = screenshot_adb()
    if img is None:
        return
    
    h, w = img.shape[:2]
    band = img[int(h * 0.50): int(h * 0.75), int(w * 0.10): int(w * 0.90)]
    hsv_b = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    mask_w = cv2.inRange(hsv_b, np.array([0, 0, 200]), np.array([180, 40, 255]))
    white_pct = cv2.countNonZero(mask_w) / (band.shape[0] * band.shape[1])

    mask_g = cv2.inRange(hsv_b, np.array([45, 60, 100]), np.array([90, 255, 255]))
    green_px = cv2.countNonZero(mask_g)

    if white_pct > 0.15 and green_px > 200:
        console.print(f"[bold red]   [{ciclo}] ⚠ Diálogo 'salir' detectado → tap CANCEL ({CANCEL_EXIT_X},{CANCEL_EXIT_Y})[/]")
        tap(CANCEL_EXIT_X, CANCEL_EXIT_Y)
        time.sleep(0.8)
    else:
        console.print(f"[dim]   [{ciclo}] Back OK (white={white_pct:.1%} green={green_px}px)[/]")


def _en_pantalla_carga(img: np.ndarray) -> bool:
    """
    Detecta la pantalla de carga/tips de Pokémon GO.
    Se reconoce por la barra de progreso amarilla/naranja en el último 5%
    de la pantalla sobre fondo oscuro (sin modal blanco).
    """
    if img is None:
        return False
    h, w = img.shape[:2]

    # Franja inferior (último 5%): barra de progreso amarilla
    strip = img[int(h * 0.95):, :]
    hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
    mask_yellow = cv2.inRange(hsv,
                              np.array([15, 100, 100]),
                              np.array([45, 255, 255]))
    yellow_px = cv2.countNonZero(mask_yellow)

    # La barra ocupa al menos un 5% de esa franja
    total = strip.shape[0] * strip.shape[1]
    if yellow_px / total < 0.05:
        return False

    # Confirmar que el fondo general es oscuro (no un modal blanco)
    band_mid = img[int(h * 0.10): int(h * 0.90), int(w * 0.05): int(w * 0.95)]
    hsv_mid = cv2.cvtColor(band_mid, cv2.COLOR_BGR2HSV)
    mask_white = cv2.inRange(hsv_mid,
                             np.array([0,   0, 200]),
                             np.array([180, 40, 255]))
    white_pct = cv2.countNonZero(mask_white) / (band_mid.shape[0] * band_mid.shape[1])
    return white_pct < 0.15


def _vigilancia_confirmacion_worker(tmpl_confirmacion: np.ndarray) -> None:
    """
    Hilo daemon que monitorea constantemente si aparece el botón de confirmación
    (que significa "¡Pokémon capturado!"). Si lo detecta, hace clic automáticamente.
    
    Esto evita que el bot pierda sincronización si no detecta la captura en el flujo principal.
    """
    global _confirmacion_vista_recientemente
    tiempo_ultima_confirmacion = time.time()
    
    while True:
        try:
            with _lock_vigilancia:
                if not _vigilancia_activa:
                    _confirmacion_vista_recientemente = False
                    time.sleep(0.5)  # Aumentado de 0.2 a 0.5 para reducir CPU
                    continue
            
            # Capturar pantalla (usar cache para evitar captures redundantes)
            img = screenshot_adb_cached()
            if img is None:
                time.sleep(0.5)  # Aumentado de 0.3 a 0.5 para reducir CPU
                continue
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Detectar confirmación (botón verde de captura exitosa)
            conf_confirm = _confidence(gray, tmpl_confirmacion)
            
            # Si detecta confirmación con buena confianza → hacer clic
            if conf_confirm >= 0.70:  # Aumentado de 0.65 a 0.70 para evitar falsos positivos durante lanzamiento
                console.print(f"[bold green]🔔 [VIGILANCIA] ✅ Confirmación detectada (conf={conf_confirm:.2f}) → tap automático[/]")
                with _lock_vigilancia:
                    _confirmacion_vista_recientemente = True
                tiempo_ultima_confirmacion = time.time()
                tap(OK_XP_X, OK_XP_Y, delay=0.3)
                time.sleep(1.5)  # Aumentado de 1.0s a 1.5s para evitar interferencia con siguiente tiro
                continue
            
            # Limpiar flag si pasaron 0.5 segundos sin ver confirmación
            if time.time() - tiempo_ultima_confirmacion > 0.5:
                with _lock_vigilancia:
                    _confirmacion_vista_recientemente = False
            
            time.sleep(0.5)  # Polling cada 500ms - aumentado de 300ms para reducir CPU
        
        except Exception as e:
            if DEBUG:
                console.print(f"[dim red][VIGILANCIA] Error: {e}[/]")
            time.sleep(1.0)  # Aumentado de 0.5s a 1.0s en caso de error


def _iniciar_vigilancia(tmpl_confirmacion: np.ndarray) -> None:
    """Inicia el hilo de vigilancia en background."""
    global _vigilancia_activa, _vigilancia_thread
    
    with _lock_vigilancia:
        if _vigilancia_thread is not None and _vigilancia_thread.is_alive():
            return  # Ya está corriendo
        
        _vigilancia_activa = True
        _vigilancia_thread = threading.Thread(
            target=_vigilancia_confirmacion_worker,
            args=(tmpl_confirmacion,),
            daemon=True
        )
        _vigilancia_thread.start()
        if DEBUG:
            console.print("[dim green][VIGILANCIA] Hilo iniciado[/]")


def _detener_vigilancia() -> None:
    """Detiene la vigilancia."""
    global _vigilancia_activa, _confirmacion_vista_recientemente
    with _lock_vigilancia:
        _vigilancia_activa = False
        _confirmacion_vista_recientemente = False
    if DEBUG:
        console.print("[dim green][VIGILANCIA] Hilo detenido[/]")


def _hilo_vigilancia_x_worker() -> None:
    """
    Hilo independiente que monitorea la pantalla buscando la X.
    SOLO busca X cuando hay indicios de modal (blanco>20% o rojo>3%).
    Esto evita falsos positivos en MAPA puro.
    """
    global _vigilancia_x_activa, _x_detectada_recientemente
    
    if DEBUG:
        console.print("[dim green][VIGILANCIA-X] Hilo iniciado - monitoreando X en modales[/]")
    
    ciclo_x = 0
    while _vigilancia_x_activa:
        try:
            ciclo_x += 1

            # ── Respetar el estado del diagnóstico ─────────────────────────
            # Solo actuar en POST-CAPTURA o modal, NUNCA en MAPA o COMBATE.
            estado_diag = _obtener_estado_diagnostico()
            if estado_diag not in ("POST-CAPTURA", "MODAL", "DESCONOCIDO"):
                with _lock_vigilancia_x:
                    _x_detectada_recientemente = False
                time.sleep(1.0)
                continue

            # Capturar pantalla
            img = screenshot_adb()
            if img is None:
                time.sleep(1.0)
                continue

            h, w = img.shape[:2]
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            # Blanco (UI modal)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blanco = cv2.countNonZero(cv2.inRange(gray, 200, 255))
            pct_blanco = blanco / (w * h)

            # Solo buscar X si hay bastante blanco (modal real)
            hay_modal = pct_blanco > 0.20

            if not hay_modal:
                with _lock_vigilancia_x:
                    _x_detectada_recientemente = False
                time.sleep(1.0)
                continue
            
            # Hay indicios de modal: buscar X
            encontrado, x_pos, y_pos = _detectar_boton_x(img)
            
            if encontrado:
                # console.print(f"[bold yellow]⊗ [VIG-X-{ciclo_x}] X DETECTADA en ({x_pos}, {y_pos}) → clickeando[/]")
                tap(x_pos, y_pos, delay=0.3)
                time.sleep(0.8)
                
                with _lock_vigilancia_x:
                    _x_detectada_recientemente = True
            else:
                with _lock_vigilancia_x:
                    _x_detectada_recientemente = False
            
            # Monitorear cada 1 segundo (sincronizado con diagnóstico)
            time.sleep(1.0)
        
        except Exception as e:
            if DEBUG:
                console.print(f"[dim red][VIGILANCIA-X] Error: {e}[/]")
            time.sleep(1.0)


def _iniciar_vigilancia_x() -> None:
    """Inicia el hilo de vigilancia de X."""
    global _vigilancia_x_activa, _vigilancia_x_thread
    
    with _lock_vigilancia_x:
        if _vigilancia_x_thread is not None and _vigilancia_x_thread.is_alive():
            return  # Ya está corriendo
        
        _vigilancia_x_activa = True
        _vigilancia_x_thread = threading.Thread(
            target=_hilo_vigilancia_x_worker,
            daemon=True
        )
        _vigilancia_x_thread.start()
        if DEBUG:
            console.print("[dim green][VIGILANCIA-X] Hilo de X iniciado[/]")


def _detener_vigilancia_x() -> None:
    """Detiene la vigilancia de X."""
    global _vigilancia_x_activa, _x_detectada_recientemente
    with _lock_vigilancia_x:
        _vigilancia_x_activa = False
        _x_detectada_recientemente = False
    if DEBUG:
        console.print("[dim green][VIGILANCIA-X] Hilo de X detenido[/]")


def _hay_confirmacion_detectada() -> bool:
    """Retorna si la vigilancia ha detectado confirmación recientemente (thread-safe)."""
    with _lock_vigilancia:
        return _confirmacion_vista_recientemente


def _detectar_pokemon_en_mapa(img: np.ndarray) -> tuple[bool, int, int]:
    """
    Detecta pokemones en el PANEL IZQUIERDO (área de pokemones cercanos).
    Los pokemones tienen colores (naranja, rojo, azul oscuro, etc.) que contrastan con el mapa azul claro.
    Busca en zona izquierda/superior donde está el listado de pokemones cercanos.
    
    Devuelve: (encontrado, x, y) - coordenadas del centroide del pokémon más visible
    """
    if img is None:
        return False, 0, 0
    
    try:
        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Limitar búsqueda a ZONA IZQUIERDA SUPERIOR (panel de pokemones cercanos)
        # X: 0-250px (panel lateral izquierdo)
        # Y: 120-700px (área donde aparecen pokemones)
        zona_x_inicio = 0
        zona_x_fin = min(250, w)
        zona_y_inicio = int(h * 0.05)  # 5% desde arriba
        zona_y_fin = int(h * 0.35)      # 35% desde arriba (zona de pokemones cercanos)
        
        # Extraer región de interés
        hsv_zona = hsv[zona_y_inicio:zona_y_fin, zona_x_inicio:zona_x_fin]
        
        # Buscar colores de pokemones: 
        # - Rojos/naranjas (0-35, 165-180 hue)
        # - Otros (amarillos, purpuras, azules, etc.)
        
        # Máscara de rojo/naranja
        mask_red_l = cv2.inRange(hsv_zona, np.array([0, 50, 50]), np.array([15, 255, 255]))
        mask_red_h = cv2.inRange(hsv_zona, np.array([165, 50, 50]), np.array([180, 255, 255]))
        mask_red = cv2.bitwise_or(mask_red_l, mask_red_h)
        
        # Máscara de amarillo
        mask_yellow = cv2.inRange(hsv_zona, np.array([15, 50, 50]), np.array([35, 255, 255]))
        
        # Máscara de azul oscuro (diferentes pokemones)
        mask_blue = cv2.inRange(hsv_zona, np.array([100, 100, 100]), np.array([130, 255, 255]))
        
        # Máscara de magenta/púrpura
        mask_magenta = cv2.inRange(hsv_zona, np.array([130, 50, 50]), np.array([165, 255, 255]))
        
        # Combinar todas las máscaras
        mask_pokemon = cv2.bitwise_or(mask_red, mask_yellow)
        mask_pokemon = cv2.bitwise_or(mask_pokemon, mask_blue)
        mask_pokemon = cv2.bitwise_or(mask_pokemon, mask_magenta)
        
        # Limpiar ruido
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_pokemon = cv2.morphologyEx(mask_pokemon, cv2.MORPH_CLOSE, kernel)
        mask_pokemon = cv2.morphologyEx(mask_pokemon, cv2.MORPH_OPEN, kernel)
        
        contours, _ = cv2.findContours(mask_pokemon, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return False, 0, 0
        
        # Buscar el contorno más grande (el pokémon más prominente)
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        
        # Pokémon debe tener área razonable (300+ píxeles)
        if area < 300:
            return False, 0, 0
        
        # Obtener centroide del pokémon (en coordenadas locales de la zona)
        M = cv2.moments(largest_contour)
        if M["m00"] > 0:
            cx_local = int(M["m10"] / M["m00"])
            cy_local = int(M["m01"] / M["m00"])
            
            # Convertir a coordenadas globales
            cx = zona_x_inicio + cx_local
            cy = zona_y_inicio + cy_local
            
            return True, cx, cy
        
        return False, 0, 0
        
    except Exception as e:
        if DEBUG:
            console.print(f"[dim red][POKÉMON-DETECTOR] Error: {e}[/]")
        return False, 0, 0


# ══════════════════════════════════════════════════════════════════════════
#  DIAGNÓSTICO CENTRALIZADO (Hilo independiente)
# ══════════════════════════════════════════════════════════════════════════

def _detectar_checkmark_interno(img_check: np.ndarray) -> bool:
    """Detecta checkmark verde en POST-CAPTURA (fallback para diagnóstico)."""
    try:
        if img_check is None:
            return False
        h, w = img_check.shape[:2]
        hsv_check = cv2.cvtColor(img_check, cv2.COLOR_BGR2HSV)
        hsv_lower = cv2.inRange(hsv_check, np.array([60, 50, 80]), np.array([160, 255, 255]))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        hsv_lower = cv2.morphologyEx(hsv_lower, cv2.MORPH_CLOSE, kernel)
        contours_check, _ = cv2.findContours(hsv_lower, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours_check:
            area = cv2.contourArea(cnt)
            if 15000 <= area <= 35000:
                x, y, bw, bh = cv2.boundingRect(cnt)
                aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
                if 0.9 <= aspect <= 1.1:
                    cx = x + bw // 2
                    cy = y + bh // 2
                    if cx > w * 0.70 and cy > h * 0.80:
                        return True
        return False
    except:
        return False

def _hilo_diagnostico_worker() -> None:
    """
    Hilo independiente que continuamente diagnostica el estado de la pantalla.
    Funciona en background sin interferir con el bucle principal.
    """
    global _estado_diagnostico, _diagnostico_screenshot, _diagnostico_congelado
    
    if DEBUG:
        console.print("[dim cyan][DIAGNÓSTICO] Hilo iniciado[/]")
    
    estaba_congelado = False  # Para detectar transición de congelado a descongelado
    _ultimo_estado_bruto: Optional[str] = None  # Anti-oscilación: último estado candidato al cambio
    _confirmaciones_bruto: int = 0              # Anti-oscilación: confirmaciones consecutivas del candidato
    
    while _diagnostico_activo:
        try:
            # ─ Detectar si acaba de descongelarse ──────────────────────
            with _lock_diagnostico:
                esta_congelado_ahora = _diagnostico_congelado
            
            # Si pasó de congelado a descongelado, forzar screenshot fresca
            force_fresh = (estaba_congelado and not esta_congelado_ahora)
            estaba_congelado = esta_congelado_ahora
            
            # Capturar pantalla (usar cache excepto justo después de descongelar)
            img = screenshot_adb_cached(force_fresh=force_fresh)
            if img is None:
                time.sleep(0.1)
                continue
            
            # Guardar captura compartida
            with _lock_diagnostico:
                _diagnostico_screenshot = img
            
            # Analizar estado
            nuevo_estado = "DESCONOCIDO"
            h, w = img.shape[:2]
            
            # Calcular variables de detección comunes (EXACTAMENTE COMO EN diagnostico.py MEJORADO)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # ⚪ BLANCO (modal de post-captura) - HSV: V > 200, S < 50
            mask_blanco = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
            blanco = cv2.countNonZero(mask_blanco)
            pct_blanco = blanco / (w * h)
            
            # 🟢 VERDE (mapa: cielo y terreno)
            # Verde: H=35-95, S>40 (saturado)
            mask_verde = cv2.inRange(hsv, np.array([35, 40, 50]), np.array([95, 255, 255]))
            verde_count = cv2.countNonZero(mask_verde)
            pct_verde = verde_count / (w * h)
            
            # 🔴 ROJO (aro de combate)
            # S>=150: rojo PURO solamente (igual que diagnostico.py)
            # Evita que iconos del sidebar, baya, o pokémon del mapa disparen COMBATE
            mask_r1 = cv2.inRange(hsv, np.array([0,   150, 80]),   np.array([10,  255, 255]))
            mask_r2 = cv2.inRange(hsv, np.array([170, 150, 80]),   np.array([180, 255, 255]))
            rojo_total = cv2.countNonZero(mask_r1 | mask_r2)
            pct_rojo = rojo_total / (w * h)
            
            # ═══ MAPEO DE TEMPLATES A ESTADOS (PASO 1 - PRIORITARIO) ═══
            # Solo la cámara (ícono arriba al centro) es exclusiva del combate
            # La baya matchea el badge verde del avatar en el mapa → no usar aquí
            template_detectado = False
            if _tmpl_camara is not None:
                try:
                    # Usar _confidence_roi para procesar solo la ROI de interés (30-50% más rápido)
                    max_val = _confidence_roi(gray, _tmpl_camara,
                                             top_pct=0.05, bottom_pct=0.30,
                                             left_pct=0.30, right_pct=0.70)
                    if max_val > 0.65:
                        nuevo_estado = "COMBATE"
                        template_detectado = True
                        if DEBUG:
                            console.print(f"[dim yellow][DIAG] Template CAMARA detectado: {max_val:.0%}[/]")
                except:
                    pass

            # Si no detectó combate por template, chequear por colores
            if not template_detectado:
                # pct_verde < 0.35: la pantalla de combate real tiene cielo + poco verde.
                # El mapa tiene verde=40-50% (tiles de hierba + caminos). Los gimnasios
                # Team Valor/Mystic tienen rojo/azul intenso que puede superar el umbral
                # de rojo (2.5%) estando en el mapa → sin esta guarda se detecta COMBATE falso.
                if pct_rojo > 0.025 and pct_blanco < 0.30 and pct_verde < 0.35:
                    nuevo_estado = "COMBATE"
                elif pct_blanco > 0.30:
                    nuevo_estado = "POST-CAPTURA"
                elif pct_verde > 0.20:
                    nuevo_estado = "MAPA"
                # Descarte: sin modal, sin rojo de combate → MAPA (cubre noche con poco verde)
                elif pct_blanco < 0.15 and pct_rojo < 0.025:
                    nuevo_estado = "MAPA"
                else:
                    nuevo_estado = "DESCONOCIDO"
            
            # Registrar en buffer circular para detección de oscilaciones
            registrar_estado_detectado(nuevo_estado)
            
            # Anti-oscilación: requiere 2 detecciones consecutivas del mismo estado
            # antes de propagar un cambio. Evita "parpadeos" por frames inestables.
            if nuevo_estado != _estado_diagnostico:
                if nuevo_estado == _ultimo_estado_bruto:
                    _confirmaciones_bruto += 1
                else:
                    _ultimo_estado_bruto = nuevo_estado
                    _confirmaciones_bruto = 1
                estado_a_aplicar = nuevo_estado if _confirmaciones_bruto >= 2 else None
            else:
                # Estado igual al actual: estabilizar acumulador
                _confirmaciones_bruto = 0
                _ultimo_estado_bruto = None
                estado_a_aplicar = nuevo_estado
            
            # Debug: mostrar cambio solo cuando se confirma y aplica
            if DEBUG and estado_a_aplicar is not None and estado_a_aplicar != _estado_diagnostico:
                console.print(f"[dim cyan][DIAG] Cambio: {_estado_diagnostico} → {estado_a_aplicar} (blanco={pct_blanco:.1%}, verde={pct_verde:.1%}, rojo={pct_rojo:.1%})[/]")
            
            # Actualizar estado global con lock
            # SI EL DIAGNÓSTICO ESTÁ CONGELADO, NO actualizar (evita confusión durante impacto)
            with _lock_diagnostico:
                if not _diagnostico_congelado and estado_a_aplicar is not None:
                    _estado_diagnostico = estado_a_aplicar
            
            # Frecuencia fija de diagnóstico: 1 vez por segundo (solicitado)
            time.sleep(1.0)
        
        except Exception as e:
            if DEBUG:
                console.print(f"[dim red][DIAGNÓSTICO] Error: {e}[/]")
            time.sleep(1.0)


def _iniciar_diagnostico() -> None:
    """Inicia el hilo de diagnóstico centralizado."""
    global _diagnostico_activo, _diagnostico_thread
    
    with _lock_diagnostico:
        if _diagnostico_thread is not None and _diagnostico_thread.is_alive():
            return  # Ya está corriendo
        
        _diagnostico_activo = True
        _diagnostico_thread = threading.Thread(
            target=_hilo_diagnostico_worker,
            daemon=True
        )
        _diagnostico_thread.start()
        if DEBUG:
            console.print("[dim cyan][DIAGNÓSTICO] Hilo de diagnóstico iniciado[/]")


def _detener_diagnostico() -> None:
    """Detiene el diagnóstico centralizado."""
    global _diagnostico_activo
    with _lock_diagnostico:
        _diagnostico_activo = False
    if DEBUG:
        console.print("[dim cyan][DIAGNÓSTICO] Hilo detenido[/]")


def _congelar_diagnostico(duracion_ms: int = 3000) -> None:
    """Congela el diagnóstico por N milisegundos (evita confusión durante impacto de pokébola)."""
    global _diagnostico_congelado, _tiempo_diagnostico_descongelado
    with _lock_diagnostico:
        _diagnostico_congelado = True
        _tiempo_diagnostico_descongelado = time.time() + (duracion_ms / 1000.0)
    if DEBUG:
        console.print(f"[dim yellow][DIAGNÓSTICO] Congelado por {duracion_ms}ms[/]")


def _obtener_estado_diagnostico() -> str:
    """Retorna el estado actual del diagnóstico (thread-safe)."""
    global _diagnostico_congelado, _tiempo_diagnostico_descongelado
    with _lock_diagnostico:
        # Descongelar si pasó el tiempo
        if _diagnostico_congelado and _tiempo_diagnostico_descongelado is not None:
            if time.time() >= _tiempo_diagnostico_descongelado:
                _diagnostico_congelado = False
                _tiempo_diagnostico_descongelado = None
        return _estado_diagnostico


# ══════════════════════════════════════════════════════════════════════════
#  POKÉBOLAS ADAPTATIVAS
# ══════════════════════════════════════════════════════════════════════════

def _seleccionar_pokebola_siguiente() -> str:
    """
    Selecciona la siguiente pokébola usando historial adaptativo (_pokebola_tasa_exito).
    Si falló demasiadas veces, consulta obtener_pokebola_optima() en lugar de rotar ciegamente.
    PRIORIDAD: ULTRA → SUPER_ULTRA → LEJANO → NORMAL (tiros progresivamente más lejanos)
    """
    global _pokebola_favorita, _pokebola_intentos_fallidos
    
    with _lock_pokebola:
        # Si falló varias veces, usar historial adaptativo para elegir la mejor pokébola
        if _pokebola_intentos_fallidos >= _POKEBOLA_MAX_INTENTOS_ANTES_CAMBIO:
            optima = obtener_pokebola_optima()
            if optima != _pokebola_favorita:
                # El historial sugiere una pokébola diferente → usarla
                _pokebola_favorita = optima
            else:
                # La óptima histórica es la misma que falló → rotar secuencialmente
                secuencia = ["ULTRA", "SUPER_ULTRA", "LEJANO", "NORMAL"]
                idx_actual = secuencia.index(_pokebola_favorita)
                _pokebola_favorita = secuencia[(idx_actual + 1) % len(secuencia)]
            _pokebola_intentos_fallidos = 0
            console.print(f"[yellow]🎯 Cambiando pokébola a: {_pokebola_favorita} (adaptativo)[/]")
        
        return _pokebola_favorita


def _registrar_acierto_pokebola() -> None:
    """Registra que la pokébola actual funcionó (reset contador de fallos)."""
    global _pokebola_intentos_fallidos
    with _lock_pokebola:
        actualizar_tasa_exito_pokebola(_pokebola_favorita, True)
        registrar_captura_stats(_pokebola_favorita)
        _pokebola_intentos_fallidos = 0
        if DEBUG:
            console.print(f"[dim green][POKÉBOLA] ✓ Acierto con {_pokebola_favorita}[/]")


def _registrar_fallo_pokebola() -> None:
    """Registra un intento fallido de la pokébola actual."""
    global _pokebola_intentos_fallidos
    with _lock_pokebola:
        actualizar_tasa_exito_pokebola(_pokebola_favorita, False)
        registrar_fallo_stats(_pokebola_favorita)
        _pokebola_intentos_fallidos += 1
        if DEBUG:
            console.print(f"[dim yellow][POKÉBOLA] ✗ Fallo {_pokebola_intentos_fallidos}/{_POKEBOLA_MAX_INTENTOS_ANTES_CAMBIO} con {_pokebola_favorita}[/]")


# Templates de pantalla de captura (cámara, baya, pokébola) — globales para reusar
_tmpl_camara:  np.ndarray | None = None
_tmpl_baya:    np.ndarray | None = None
_tmpl_pokeball: np.ndarray | None = None
_tmpl_check:         np.ndarray | None = None  # Botón check verde para POST-CAPTURA
_tmpl_check_pokemon: np.ndarray | None = None  # Botón checkmark teal de pantalla detalle

# Template del compañero de mapa (cargado una vez al inicio para mayor velocidad)
_tmpl_companero: np.ndarray | None = None

def _cargar_companero() -> None:
    """Carga el template del compañero de mapa si existe."""
    global _tmpl_companero
    path = os.path.join(BOT_DIR, "compañero_mapa.jpg")
    if os.path.exists(path):
        _tmpl_companero = _imread_unicode(path, cv2.IMREAD_GRAYSCALE)
        if _tmpl_companero is not None:
            console.print(f"[green]  compañero_mapa : ✅ compañero_mapa.jpg ({_tmpl_companero.shape[1]}×{_tmpl_companero.shape[0]})[/]")
        else:
            console.print("[red]  compañero_mapa : ❌ no se pudo leer[/]")
    else:
        console.print("[dim]  compañero_mapa : (no encontrado — guarda pokmoengobot/compañero_mapa.jpg)[/]")


def _es_popup_clima(img: np.ndarray) -> bool:
    """
    Detecta el popup de 'Informar sobre el clima' de Pokémon GO.
    Tiene un fondo blanco modal en la zona media con botón verde (ENVIAR)
    y botón gris (CANCELAR). El indicador clave es el verde del botón ENVIAR
    en la franja 55-75% de altura + fondo blanco dominante.
    """
    if img is None:
        return False
    h, w = img.shape[:2]
    band = img[int(h * 0.55): int(h * 0.75), int(w * 0.10): int(w * 0.90)]
    hsv  = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    # Botón ENVIAR: verde saturado
    mask_g = cv2.inRange(hsv, np.array([45, 80, 100]), np.array([90, 255, 255]))
    green_px = cv2.countNonZero(mask_g)
    # Fondo blanco del modal
    mask_w = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 40, 255]))
    white_pct = cv2.countNonZero(mask_w) / (band.shape[0] * band.shape[1])
    # Íconos tipo (PLANTA/TIERRA/FUEGO) → naranja/rojo en franja 70-85%
    band2 = img[int(h * 0.70): int(h * 0.85), int(w * 0.05): int(w * 0.95)]
    hsv2  = cv2.cvtColor(band2, cv2.COLOR_BGR2HSV)
    mask_o = cv2.inRange(hsv2, np.array([5, 100, 100]), np.array([25, 255, 255]))
    orange_px = cv2.countNonZero(mask_o)
    return white_pct > 0.20 and (green_px > 300 or orange_px > 500)


def _cerrar_popup_clima_robusto(ciclo: int) -> None:
    """
    Cierra popup de clima de forma ROBUSTA: intenta múltiples veces
    con distintas posiciones hasta detectar que se cerró.
    """
    for intento in range(3):
        img = screenshot_adb()
        if img is None or not _es_popup_clima(img):
            if DEBUG and intento > 0:
                console.print(f"[dim green]   [{ciclo}] Popup clima cerrado tras {intento+1} intentos[/]")
            return
        
        # Intentar cerrar con posiciones alternativas
        tap_positions = [
            (PHONE_W // 2, int(img.shape[0] * 0.80)),  # Centro-bajo (botón cancelar)
            (PHONE_W // 2, int(img.shape[0] * 0.77)),  # Un poco más arriba
            (PHONE_W // 2, int(img.shape[0] * 0.83)),  # Un poco más abajo
        ]
        
        tap_x, tap_y = tap_positions[intento % len(tap_positions)]
        console.print(f"[yellow]   [{ciclo}] Cerrando popup clima intento {intento+1} → tap ({tap_x},{tap_y})[/]")
        tap(tap_x, tap_y, delay=0.5)
        time.sleep(0.8)


def _es_dialogo_evolucion(img: np.ndarray) -> bool:
    """
    Detecta si hay un diálogo de evolución mostrado.
    Características:
      - Modal blanco en el centro de la pantalla
      - Dos botones en la parte inferior (SÍ verde, NO gris)
      - Texto tipo "¿Quieres que [Pokémon] evolucione?"
    """
    if img is None:
        return False
    
    h, w = img.shape[:2]
    
    # Zona de botones: parte inferior de la pantalla
    band_botones = img[int(h * 0.75): int(h * 0.95), int(w * 0.05): int(w * 0.95)]
    hsv_botones = cv2.cvtColor(band_botones, cv2.COLOR_BGR2HSV)
    
    # Detectar botón SÍ (verde)
    mask_si = cv2.inRange(hsv_botones, np.array([45, 80, 100]), np.array([90, 255, 255]))
    si_px = cv2.countNonZero(mask_si)
    
    # Detectar botón NO (gris/blanco)
    mask_no = cv2.inRange(hsv_botones, np.array([0, 0, 150]), np.array([180, 50, 220]))
    no_px = cv2.countNonZero(mask_no)
    
    # Zona modal: centro con texto
    band_modal = img[int(h * 0.30): int(h * 0.75), int(w * 0.10): int(w * 0.90)]
    hsv_modal = cv2.cvtColor(band_modal, cv2.COLOR_BGR2HSV)
    mask_modal_blanco = cv2.inRange(hsv_modal, np.array([0, 0, 200]), np.array([180, 40, 255]))
    modal_blanco_pct = cv2.countNonZero(mask_modal_blanco) / (band_modal.shape[0] * band_modal.shape[1])
    
    # Si hay botones verde y gris/blanco, y fondo modal blanco → es diálogo de evolución
    return si_px > 200 and no_px > 200 and modal_blanco_pct > 0.15


def _cerrar_dialogo_evolucion(ciclo: int) -> bool:
    """
    Cierra el diálogo de evolución tappando el botón "NO".
    El botón NO está en la parte inferior derecha.
    """
    img = screenshot_adb()
    if img is None or not _es_dialogo_evolucion(img):
        return False
    
    console.print(f"[yellow]   [{ciclo}] ⚡ Diálogo de evolución → TAP en NO[/]")
    
    # El botón NO está aproximadamente en (830, 1125) en resolución 1080x2400
    # Pero vamos a calcularlo dinámicamente
    h, w = img.shape[:2]
    no_x = int(w * 0.77)   # ~830px en 1080 ancho
    no_y = int(h * 0.87)   # ~2088px en 2400 alto
    
    tap(no_x, no_y, delay=0.5)
    time.sleep(0.8)
    
    # Verificar que se cerró
    img_check = screenshot_adb()
    if img_check is not None and not _es_dialogo_evolucion(img_check):
        console.print(f"[green]   [{ciclo}] ✓ Diálogo de evolución cerrado[/]")
        return True
    
    return False


def _cerrar_pantalla_no_deseada(img: np.ndarray, ciclo: int) -> bool:
    """
    Intenta cerrar cualquier pantalla no esperada (popup, evento, tienda,
    Pokédex, gimnasio, raid, etc.).

    Estrategia en cascada:
      0. Botón check de POST-CAPTURA → click (máxima prioridad)
      1. Diálogo de evolución → tap NO
      2. Popup de clima → tap CANCELAR (posición específica conocida)
      3. Modal blanco detectado (>8% de la franja central) → prueba cada
         posición de _ESCAPE_TAPS en orden hasta que el % de blanco baje.
      4. Si ningún tap funcionó → tecla Back (con manejo automático del
         diálogo '¿Salir de Pokémon GO?' vía _safe_back).

    Devuelve True si realizó al menos una acción de cierre.
    """
    if img is None:
        return False

    # 0. Botón check de POST-CAPTURA (máxima prioridad - debe clickearse si se detecta)
    if _tmpl_check is not None:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Buscar el check en toda la pantalla usando template matching
        res = cv2.matchTemplate(gray, _tmpl_check, cv2.TM_CCOEFF_NORMED)
        _, max_conf, _, max_loc = cv2.minMaxLoc(res)
        
        if max_conf >= 0.70:
            # max_loc es la esquina superior-izquierda del template
            # Necesitamos el centro para hacer tap
            check_x = max_loc[0] + _tmpl_check.shape[1] // 2
            check_y = max_loc[1] + _tmpl_check.shape[0] // 2
            
            console.print(f"[bold green]✓ [{ciclo}] Botón check detectado en ({check_x},{check_y}) (conf={max_conf:.2f}) → tap[/]")
            tap(check_x, check_y, delay=0.5)
            time.sleep(1.0)
            return True

    # 1. Diálogo de evolución
    if _es_dialogo_evolucion(img):
        return _cerrar_dialogo_evolucion(ciclo)

    # 2. Popup de clima (manejo específico: botón CANCELAR en ~80% de altura)
    if _es_popup_clima(img):
        console.print(f"[yellow]   [{ciclo}] 🌦 Popup clima → CANCELAR[/]")
        tap(PHONE_W // 2, int(img.shape[0] * 0.80))
        time.sleep(1.0)
        return True


    h, w = img.shape[:2]

    def _medir_blanco(screenshot: np.ndarray) -> float:
        """% de píxeles blancos en la franja central (señal de modal abierto)."""
        band = screenshot[int(h * 0.20): int(h * 0.90),
                          int(w * 0.05): int(w * 0.95)]
        hsv_b = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
        mask_w = cv2.inRange(hsv_b,
                             np.array([0,   0, 200]),
                             np.array([180, 40, 255]))
        return cv2.countNonZero(mask_w) / (band.shape[0] * band.shape[1])

    white_ini = _medir_blanco(img)

    # 2. Buscar la X de cierre en la esquina superior derecha
    # ROI: 820-1080 x 60-260 (X=~950,Y=~190)
    roi_x = img[60:260, 820:1080]
    roi_gray = cv2.cvtColor(roi_x, cv2.COLOR_BGR2GRAY)
    # Buscar círculo blanco grande
    circles = cv2.HoughCircles(roi_gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=40,
                               param1=60, param2=30, minRadius=30, maxRadius=60)
    found_x = False
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for i in circles[0, :]:
            cx, cy, r = i
            # Buscar una X negra dentro del círculo
            # ROI pequeña centrada en el círculo
            x0 = max(cx-18, 0)
            y0 = max(cy-18, 0)
            x1 = min(cx+18, roi_gray.shape[1])
            y1 = min(cy+18, roi_gray.shape[0])
            roi_c = roi_gray[y0:y1, x0:x1]
            # La X suele ser dos líneas oscuras cruzadas
            edges = cv2.Canny(roi_c, 60, 120)
            lines = cv2.HoughLines(edges, 1, np.pi/180, 10)
            if lines is not None and len(lines) >= 2:
                # Consideramos que hay una X
                abs_x = 820 + cx
                abs_y = 60 + cy
                console.print(f"[yellow]   [{ciclo}] ❌ X de cierre detectada en ({abs_x},{abs_y}) → tap[/]")
                tap(abs_x, abs_y, delay=1.2)
                img_chk = screenshot_adb()
                if img_chk is not None:
                    white_now = _medir_blanco(img_chk)
                    if white_now < white_ini - 0.05:
                        console.print(f"[green]   [{ciclo}] ✓ Pantalla cerrada con X ({white_ini:.0%} → {white_now:.0%})[/]")
                        return True
                found_x = True
                break

    # 3. Modal blanco → probar taps de cierre en orden (si no se detectó la X o no funcionó)
    if white_ini > 0.08 and not found_x:
        console.print(
            f"[yellow]   [{ciclo}] ⚠ Pantalla no deseada "
            f"(blanco={white_ini:.0%}) → probando {len(_ESCAPE_TAPS)} posiciones[/]"
        )
        for tap_x, tap_y in _ESCAPE_TAPS:
            console.print(f"[dim yellow]   [{ciclo}]   Escape tap → ({tap_x},{tap_y})[/]")
            tap(tap_x, tap_y, delay=1.5)
            img_chk = screenshot_adb()
            if img_chk is None:
                continue
            # ¿Desapareció el modal?
            white_now = _medir_blanco(img_chk)
            if white_now < white_ini - 0.05:
                console.print(
                    f"[green]   [{ciclo}] ✓ Pantalla cerrada "
                    f"({white_ini:.0%} → {white_now:.0%})[/]"
                )
                return True
            # ¿Abrió popup de clima al cerrar?
            if _es_popup_clima(img_chk):
                console.print(f"[yellow]   [{ciclo}]   Popup clima secundario → CANCELAR[/]")
                tap(PHONE_W // 2, int(img_chk.shape[0] * 0.80))
                time.sleep(1.0)
                return True

    # 3. Back como último recurso (_safe_back cancela el diálogo de salida)
    console.print(f"[dim yellow]   [{ciclo}] ⬅ Back (último recurso)[/]")
    _safe_back(ciclo)
    time.sleep(1.5)
    return True


def _confirmar_en_mapa(img: np.ndarray) -> tuple[bool, dict]:
    """
    Confirma que estamos en la pantalla del MAPA.
    Orden de prioridad:
      0. Template del compañero de mapa (compañero_mapa.jpg) — más fiable
      1. Dot verde del avatar del entrenador
      2. Fondo oscuro de los tiles del mapa
      3. Template avatar_mapa.jpg (legacy, opcional)

    Devuelve (en_mapa, debug_dict).
    """
    dbg = {}
    if img is None:
        return False, dbg
    
    try:
        h, w = img.shape[:2]
        if h < 100 or w < 100:
            return False, dbg
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error shape/gray en _confirmar_en_mapa: {e}[/]")
        return False, dbg

    # ─ 0. Template del compañero de mapa (PRIORITARIO) ────────────────────
    # El compañero camina junto al avatar en la zona inferior-izquierda del mapa.
    # Si el template matchea aquí con buena confianza → estamos definitivamente en el mapa.
    try:
        if _tmpl_companero is not None:
            th, tw = _tmpl_companero.shape[:2]
            # ROI: zona inferior-izquierda donde camina el compañero (25% inferior, 50% izquierdo)
            y0 = max(0, int(h * 0.60))
            x1 = int(w * 0.60)
            roi_comp = gray[y0:, :x1]
            if roi_comp.shape[0] >= th and roi_comp.shape[1] >= tw:
                res = cv2.matchTemplate(roi_comp, _tmpl_companero, cv2.TM_CCOEFF_NORMED)
                _, conf_comp, _, _ = cv2.minMaxLoc(res)
                dbg['companero_conf'] = round(conf_comp, 2)
                if conf_comp >= 0.60:
                    dbg['avatar_green_px'] = 999  # señal para código que usa este campo
                    return True, dbg
            else:
                dbg['companero_conf'] = -1.0
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error template companero: {e}[/]")
        dbg['companero_conf'] = -1.0

    # ─ 1. Dot verde del avatar (esquina inferior-izquierda) ───────────────
    # Buscar en zona más amplia: últimos 20% alto, primeros 15% ancho
    try:
        roi_avatar = img[int(h * 0.80): int(h),
                         int(w * 0.00): int(w * 0.15)]
        
        # En COMBATE: el avatar desaparece, la zona está casi vacía
        # En MAPA: el avatar está visible como un círculo concentrado en la esquina
        
        hsv_av = cv2.cvtColor(roi_avatar, cv2.COLOR_BGR2HSV)
        
        # Rango expandido para verde
        mask_av = cv2.inRange(hsv_av,
                              np.array([35, 40, 50]),    # H,S,V mínimos (más tolerante)
                              np.array([95, 255, 255])
        )
        av_px = cv2.countNonZero(mask_av)
        dbg['avatar_green_px'] = av_px

        # IMPORTANTE: Si av_px es EXTREMADAMENTE alto (>10000), probablemente no es
        # el avatar real sino verde disperso del mapa de fondo.
        # Un avatar real concentrado tendrá 500-3000px, no 18000+.
        # Esto evita falsos positivos donde el mapa verde atrás se cuenta como avatar.
        if av_px > 15 and av_px < 10000:
            return True, dbg
        
        # Si av_px > 10000, probablemente estamos en COMBATE (el "avatar" es verde del mapa atrás)
        # En combate real, la zona debería estar vacía. Si ve tanta verde, no es avatar real.
        if av_px > 10000:
            # Marker de "en combate, no hay avatar real"
            dbg['avatar_green_px'] = av_px
            # NO retornar True aquí; seguir con otros criterios
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error detectando avatar verde: {e}[/]")
        dbg['avatar_green_px'] = 0

    # ─ 2. Fondo oscuro del mapa (tiles azul/verde en zona central) ───────────
    try:
        band_center = img[int(h * 0.15): int(h * 0.80),
                          int(w * 0.05): int(w * 0.95)]
        hsv_c = cv2.cvtColor(band_center, cv2.COLOR_BGR2HSV)
        mask_dark = cv2.inRange(hsv_c,
                                np.array([0,  15,  20]),
                                np.array([180, 255, 130]))
        dark_pct = cv2.countNonZero(mask_dark) / (band_center.shape[0] * band_center.shape[1])
        mask_white_c = cv2.inRange(hsv_c,
                                   np.array([0,   0, 200]),
                                   np.array([180, 40, 255]))
        white_c_pct = cv2.countNonZero(mask_white_c) / (band_center.shape[0] * band_center.shape[1])
        dbg['map_dark_pct']     = round(dark_pct, 3)
        dbg['center_white_pct'] = round(white_c_pct, 3)

        if dark_pct > 0.25 and white_c_pct < 0.15:
            return True, dbg
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error detectando fondo oscuro: {e}[/]")
        dbg['map_dark_pct']     = 0.0
        dbg['center_white_pct'] = 0.0

    # ─ 3. Template avatar_mapa.jpg (legacy, opcional) ─────────────────────
    tmpl_path = os.path.join(BOT_DIR, "avatar_mapa.jpg")
    if os.path.exists(tmpl_path):
        tmpl_av = _load_template("avatar_mapa.jpg")
        if tmpl_av is not None:
            conf = _confidence(gray, tmpl_av)
            dbg['avatar_tmpl_conf'] = round(conf, 2)
            if conf >= 0.70:
                return True, dbg

    return False, dbg


def _en_mapa_robusto(img: np.ndarray) -> tuple[bool, dict]:
    """
    Detecta mapa usando características INVARIANTES a cambios de iluminación/hora.
    En lugar de contar píxeles de color específicos, detecta la ESTRUCTURA del mapa.
    
    Criterios analizados:
      1. Intensidad de bordes (mapa tiene tiles con bordes claros)
      2. Diversidad de colores en histograma (mapa >> combate)
      3. Nivel de textura (mapa tiene patrones, combate es liso)
      4. Entropía de brillo (mapa tiene amplitud tonal, combate concentrado)
    
    Necesita ≥3 criterios cumplidos para ser "en mapa".
    """
    dbg = {}
    if img is None:
        return False, dbg
    
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # ─ 1. PATRÓN: Intensidad de bordes (Laplaciano) ─────────────────────
    # Mapa: tiles con transiciones bruscas → bordes fuertes
    # Combate: cielo liso, Pokémon suave → bordes débiles
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    edges_intensity = np.abs(laplacian).mean()
    dbg['edges_intensity'] = round(edges_intensity, 2)
    criterio_bordes = edges_intensity > 12  # umbral empírico
    
    # ─ 2. PATRÓN: Diversidad de colores ──────────────────────────────────
    # Mapa: muchos colores distintos (múltiples tiles, sprites, elementos)
    # Combate: pocos colores (dominado por Pokémon + cielo)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist_h = cv2.calcHist([hsv], [0], None, [8], [0, 180])
    hist_s = cv2.calcHist([hsv], [1], None, [8], [0, 256])
    hist_v = cv2.calcHist([hsv], [2], None, [8], [0, 256])
    
    bins_activos_h = np.sum(hist_h > 100)
    bins_activos_s = np.sum(hist_s > 100)
    bins_activos_v = np.sum(hist_v > 100)
    
    color_diversity = int(bins_activos_h + bins_activos_s + bins_activos_v)
    dbg['color_diversity'] = color_diversity
    # Mapa: 15-24 bins activos; Combate: 5-12
    criterio_colores = color_diversity > 14
    
    # ─ 3. PATRÓN: Textura local ──────────────────────────────────────────
    # Mapa: textura visible (tiles, sprites)
    # Combate: superficie lisa (cielo)
    roi_texture = gray[int(h*0.3):int(h*0.7), int(w*0.2):int(w*0.8)]
    mean = cv2.blur(roi_texture.astype(np.float32), (16, 16))
    sqmean = cv2.blur((roi_texture.astype(np.float32))**2, (16, 16))
    variance = sqmean - mean**2
    texture_level = variance.mean()
    
    dbg['texture_level'] = round(texture_level, 2)
    # Mapa: >800; Combate: <500
    criterio_textura = texture_level > 700
    
    # ─ 4. PATRÓN: Entropía de brillo ─────────────────────────────────────
    # Mapa: distribución amplia (tiene luz y sombra)
    # Combate: concentrada en un rango (cielo)
    hist_gray = cv2.calcHist([gray], [0], None, [16], [0, 256])
    hist_norm = hist_gray / hist_gray.sum()
    # Evitar log(0)
    entropy_brillo = -np.sum(hist_norm[hist_norm > 0] * np.log2(hist_norm[hist_norm > 0]))
    
    dbg['brightness_entropy'] = round(entropy_brillo, 2)
    # Mapa: >3.2; Combate: <2.8
    criterio_brillo = entropy_brillo > 3.0
    
    # ─ DECISIÓN FINAL ────────────────────────────────────────────────────
    # En mapa nocturno, algunos criterios pueden fallar (azul dominante = poca diversidad).
    # Bajamos de 3 a 2 criterios para ser más tolerante.
    criterios_lista = [criterio_bordes, criterio_colores, criterio_textura, criterio_brillo]
    criterios_cumplidos = sum(criterios_lista)
    
    dbg['criterios'] = {
        'bordes': criterio_bordes,
        'colores': criterio_colores,
        'textura': criterio_textura,
        'brillo': criterio_brillo,
    }
    dbg['criterios_cumplidos'] = criterios_cumplidos
    
    en_mapa = criterios_cumplidos >= 2
    
    return en_mapa, dbg


def _detectar_pantalla_postcombate(img: np.ndarray) -> tuple[str, dict]:
    """
    Detecta en qué pantalla post-combate estamos.
    Devuelve (pantalla, debug_dict) donde pantalla es:
      'xp'      → pantalla de XP/recompensa (botón OK verde)
      'modal'   → pantalla modal blanca desconocida (pokédex, etc.)
      'detalle' → página de detalle del Pokémon (✓ teal)
      'mapa'    → de vuelta en el mapa
    """
    dbg = {}
    if img is None:
        return 'mapa', dbg
    
    try:
        h, w = img.shape[:2]
        if h < 100 or w < 100:
            return 'mapa', dbg
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error shape img: {e}[/]")
        return 'mapa', dbg

    # ─ PRIORIDAD 0: Detectar pokébola central del mapa ───────────────
    # Si la pokébola grande del mapa es visible → estamos en MAPA, parar todo.
    # La pokébola del mapa está centrada horizontalmente en el 75-92% de altura.
    # Tiene zona roja arriba y zona blanca abajo + punto negro central.
    try:
        zona_pb = img[int(h * 0.72): int(h * 0.92), int(w * 0.35): int(w * 0.65)]
        hsv_pb  = cv2.cvtColor(zona_pb, cv2.COLOR_BGR2HSV)
        # Rojo pokébola (dos rangos HSV porque rojo cruza 0°)
        m_rojo1 = cv2.inRange(hsv_pb, np.array([0,  120, 120]), np.array([10, 255, 255]))
        m_rojo2 = cv2.inRange(hsv_pb, np.array([170, 120, 120]), np.array([180, 255, 255]))
        rojo_px = cv2.countNonZero(m_rojo1 | m_rojo2)
        # Blanco pokébola
        m_blanc = cv2.inRange(hsv_pb, np.array([0, 0, 210]), np.array([180, 30, 255]))
        blanc_px = cv2.countNonZero(m_blanc)
        dbg['pokeball_mapa_rojo'] = rojo_px
        dbg['pokeball_mapa_blanc'] = blanc_px
        # La pokébola del mapa tiene ~2000-6000px de rojo y ~2000-6000px de blanco
        # en esa zona recortada. Si ambos están presentes → es el mapa.
        if rojo_px > 1500 and blanc_px > 1500:
            if DEBUG:
                console.print(f"[dim cyan]  🔍 _detectar_pantalla_postcombate() → MAPA (pokébola central rojo={rojo_px} blanc={blanc_px})[/]")
            return 'mapa', dbg
    except Exception:
        pass

    # ─ 0. TEMPLATE MATCHING: checkmark teal = pantalla detalle (máx prioridad) ─
    # check_pokemon.png es el botón ✓ teal de la pantalla de detalle del Pokémon.
    # SOLO buscar en el último 20% de pantalla (barra inferior con botones teal).
    # Threshold alto (0.80) para evitar falsos positivos con botones del menú.
    if _tmpl_check_pokemon is not None:
        try:
            strip_check = img[int(h * 0.80):, :]
            gray_strip  = cv2.cvtColor(strip_check, cv2.COLOR_BGR2GRAY)
            res  = cv2.matchTemplate(gray_strip, _tmpl_check_pokemon, cv2.TM_CCOEFF_NORMED)
            _, max_conf, _, max_loc = cv2.minMaxLoc(res)
            dbg['check_tmpl_conf'] = round(float(max_conf), 2)
            if max_conf >= 0.80:
                ck_x = max_loc[0] + _tmpl_check_pokemon.shape[1] // 2
                ck_y = max_loc[1] + _tmpl_check_pokemon.shape[0] // 2 + int(h * 0.80)
                dbg['teal_px'] = 0
                dbg['green_px'] = 0
                if DEBUG:
                    console.print(f"[dim cyan]  🔍 _detectar_pantalla_postcombate() → DETALLE por template (conf={max_conf:.2f}, pos=({ck_x},{ck_y}))[/]")
                return 'detalle', dbg
        except Exception:
            pass

    # ─ 1. ¿Hay un modal blanco en pantalla? ────────────────────────
    # El diálogo de XP / detalle / pokédex tiene fondo blanco en la franja media
    try:
        band_modal = img[int(h * 0.30): int(h * 0.90), int(w * 0.05): int(w * 0.95)]
        hsv_m = cv2.cvtColor(band_modal, cv2.COLOR_BGR2HSV)
        mask_white = cv2.inRange(hsv_m,
                                 np.array([0,   0, 200]),
                                 np.array([180, 40, 255]))
        white_pct = cv2.countNonZero(mask_white) / (band_modal.shape[0] * band_modal.shape[1])
        dbg['white_pct'] = round(white_pct, 3)
        on_modal = white_pct > 0.45   # >45% blanco = modal EXTREMADAMENTE grande (confusión/transición rara, no POST-CAPTURA normal)
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error detectando modal blanco: {e}[/]")
        dbg['white_pct'] = 0.0
        on_modal = False

    # ─ 2. Pre-calcular green_px (se usa en XP y detalle) ─────────────
    try:
        band_xp = img[int(h * 0.50): int(h * 0.90), int(w * 0.10): int(w * 0.90)]
        hsv_xp  = cv2.cvtColor(band_xp, cv2.COLOR_BGR2HSV)
        mask_green1 = cv2.inRange(hsv_xp, np.array([35, 40, 80]),   np.array([85, 255, 255]))
        mask_green2 = cv2.inRange(hsv_xp, np.array([20, 50, 100]),  np.array([40, 255, 255]))
        green_px = cv2.countNonZero(cv2.bitwise_or(mask_green1, mask_green2))
        dbg['green_px'] = green_px
    except Exception:
        green_px = 0
        dbg['green_px'] = 0

    # ─ 3. Pantalla XP: verde grande + blanco ─────────────────────────
    # Discriminador clave: XP card tiene ~663k green_px; detalle tiene ~99k (MÁS PODER+EVOLUCIONAR).
    # Threshold alto (300k) para no confundir con botones verdes del detalle.
    if white_pct > 0.15 and green_px > 300000:
        if DEBUG:
            console.print(f"[dim cyan]  🔍 _detectar_pantalla_postcombate() → XP (white={white_pct:.1%}, green_px={green_px})[/]")
        return 'xp', dbg

    # ─ 2. Pantalla DETALLE: teal del ✓ / ≡ en el último 15% ──────────
    # Solo si NO hay verde grande (que indicaría XP card).
    # Dos círculos teal ~80px de diámetro ≈ 10.000 px teal.
    try:
        strip_b = img[int(h * 0.85):, :]
        hsv_b   = cv2.cvtColor(strip_b, cv2.COLOR_BGR2HSV)
        mask_teal = cv2.inRange(hsv_b,
                                np.array([82, 80, 100]),
                                np.array([105, 255, 255]))
        teal_px = cv2.countNonZero(mask_teal)
        dbg['teal_px'] = teal_px
        # Detalle: teal > 4000 = botones ✓/≡ visibles → SIEMPRE es detalle
        # (green_px de 'MÁS PODER' no debe bloquear esta detección)
        if teal_px > 4000:
            if DEBUG:
                console.print(f"[dim cyan]  🔍 _detectar_pantalla_postcombate() → DETALLE (teal_px={teal_px}, white={white_pct:.1%})[/]")
            return 'detalle', dbg
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error detectando detalle teal: {e}[/]")
        dbg['teal_px'] = 0

    # ─ FALLBACK: mucho blanco sin teal → XP card ───────────────────
    # Solo aplica si NO hay teal (si hubiera teal ya habría retornado 'detalle')
    if white_pct > 0.70:
        if DEBUG:
            console.print(f"[dim cyan]  🔍 _detectar_pantalla_postcombate() → XP fallback blanco (white={white_pct:.1%})[/]")
        return 'xp', dbg

    # ─ 4. Modal sin botón identificado ───────────────────────────────
    if on_modal:
        if DEBUG:
            console.print(f"[dim cyan]  🔍 _detectar_pantalla_postcombate() → MODAL (white={white_pct:.1%})[/]")
        return 'modal', dbg

    if DEBUG and white_pct > 0.30:
        console.print(f"[dim cyan]  🔍 _detectar_pantalla_postcombate() → MAPA (white={white_pct:.1%}, on_modal={on_modal}, green_px={dbg.get('green_px', '?')}, teal_px={dbg.get('teal_px', '?')})[/]")
    return 'mapa', dbg


def _detectar_boton_acuerdo(img: np.ndarray) -> tuple[bool, int, int]:
    """
    Detecta específicamente el botón verde/teal 'DE ACUERDO' de la pantalla de Pokémon atrapado.
    
    ⚠️ RESTRICCIONES PARA EVITAR FALSOS POSITIVOS:
    - Solo en zona BAJA (85-95% de altura) ← excluye botones en zone media
    - Debe estar CENTRADO horizontalmente (X entre 40% y 60% del ancho)
    - Debe ser GRANDE (>300k px²) ← los botones de la UI media son más pequeños
    
    Devuelve: (encontrado, x, y) donde (x, y) es el centro del botón.
    """
    if img is None:
        return False, 0, 0
    
    h, w = img.shape[:2]
    
    try:
        # ZONA: 50-90% de altura — cubre el botón DE ACUERDO que aparece ~65% de altura (Y≈1570)
        band_boton = img[int(h * 0.50):int(h * 0.90), :]
        hsv_band = cv2.cvtColor(band_boton, cv2.COLOR_BGR2HSV)
        
        # Detectar TEAL/CIAN (el botón DE ACUERDO es teal brillante)
        mask_teal1 = cv2.inRange(hsv_band, np.array([70, 60, 80]),    np.array([120, 255, 255]))   # Teal/cian
        mask_teal2 = cv2.inRange(hsv_band, np.array([30, 50, 80]),    np.array([90, 255, 255]))    # Verde claro
        mask_teal3 = cv2.inRange(hsv_band, np.array([80, 80, 100]),   np.array([105, 255, 255]))   # Cian puro
        mask_teal = cv2.bitwise_or(cv2.bitwise_or(mask_teal1, mask_teal2), mask_teal3)
        
        # Aplicar operaciones morfológicas para limpiar ruido
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_teal = cv2.morphologyEx(mask_teal, cv2.MORPH_CLOSE, kernel)
        mask_teal = cv2.morphologyEx(mask_teal, cv2.MORPH_OPEN, kernel)
        
        # Encontrar contornos
        contours, _ = cv2.findContours(mask_teal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            if DEBUG:
                console.print(f"[dim]   🔍 _detectar_boton_acuerdo: Sin contornos detectados[/]")
            return False, 0, 0
        
        # Encontrar el contorno más grande (el botón)
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        
        if DEBUG:
            console.print(f"[dim]   🔍 _detectar_boton_acuerdo: area={area:.0f}px²[/]")
        
        # Umbral de área: botón DE ACUERDO ocupa al menos 20k px² en su zona
        if area < 20000:
            if DEBUG:
                console.print(f"[dim]   🔍 _detectar_boton_acuerdo: área rechazada ({area:.0f} < 20k)[/]")
            return False, 0, 0
        
        x, y, bw, bh = cv2.boundingRect(largest)
        
        # El botón debe ser más ancho que alto (forma de píldora redondeada)
        if bw < bh:
            if DEBUG:
                console.print(f"[dim]   🔍 _detectar_boton_acuerdo: rechazado por forma (w={bw} < h={bh})[/]")
            return False, 0, 0
        
        # ⚠️ VALIDACIÓN DE POSICIÓN: El botón DE ACUERDO debe estar CENTRADO (X entre 40-60% del ancho)
        M = cv2.moments(largest)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"]) + int(h * 0.50)  # Sumar offset porque es en band_boton
            
            # Validar que está centrado
            x_min = int(w * 0.40)
            x_max = int(w * 0.60)
            if cx < x_min or cx > x_max:
                if DEBUG:
                    console.print(f"[dim]   🔍 _detectar_boton_acuerdo: rechazado por posición X={cx} (fuera de {x_min}-{x_max})[/]")
                return False, 0, 0
            
            if DEBUG:
                console.print(f"[dim green]   🔍 _detectar_boton_acuerdo: ✓ encontrado en ({cx}, {cy})[/]")
            return True, cx, cy
        
        return False, 0, 0
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error detectando botón acuerdo: {e}[/]")
        return False, 0, 0


def _cerrar_pantalla_acuerdo(img: np.ndarray, ciclo: int) -> bool:
    """
    Detecta y cierra la pantalla de 'Pokémon Atrapado' haciendo clic en 'DE ACUERDO'.
    Devuelve True si logró clickear, False si no encontró la pantalla.
    """
    if img is None:
        return False
    
    # Detectar el botón
    encontrado, btn_x, btn_y = _detectar_boton_acuerdo(img)
    
    if encontrado:
        console.print(f"[bold green]✅ [{ciclo}] Botón DE ACUERDO detectado en ({btn_x}, {btn_y}) → tap[/]")
        tap(btn_x, btn_y, delay=0.5)
        time.sleep(1.0)
        return True
    
    # FALLBACK: Si no se detectó por color, intentar tap en coordenadas típicas del botón
    # El botón está aproximadamente en Y=2100 (85% de 2400), centrado en X
    h, w = img.shape[:2]
    fallback_y = int(h * 0.85)  # 85% de altura
    fallback_x = w // 2  # Centrado
    
    # Verificar que hay blanco/modal en esa zona (validar que estamos en POST-CAPTURA)
    try:
        band_check = img[int(h * 0.75): int(h * 0.95), int(w * 0.1): int(w * 0.9)]
        hsv_check = cv2.cvtColor(band_check, cv2.COLOR_BGR2HSV)
        mask_white = cv2.inRange(hsv_check, np.array([0, 0, 200]), np.array([180, 40, 255]))
        white_pct = cv2.countNonZero(mask_white) / (band_check.shape[0] * band_check.shape[1])
        
        if white_pct > 0.20:  # Hay suficiente blanco → probablemente es POST-CAPTURA
            console.print(f"[bold green]✅ [{ciclo}] Pantalla POST-CAPTURA detectada (white={white_pct:.1%}) → tap fallback en ({fallback_x}, {fallback_y})[/]")
            tap(fallback_x, fallback_y, delay=0.5)
            time.sleep(1.0)
            return True
    except Exception as e:
        if DEBUG:
            console.print(f"[dim]   ⚠ Error en fallback: {e}[/]")
    
    return False


def _detectar_boton_x(img: np.ndarray) -> tuple[bool, int, int]:
    """
    Detecta el botón X para cerrar menús/modales.
    Usa la versión mejorada de detector_modales.py si está disponible,
    sino usa la versión anterior.
    Devuelve: (encontrado, x, y)
    """
    if img is None:
        return False, 0, 0
    
    # Intentar usar la versión mejorada
    if detectar_boton_x_mejorado is not None:
        return detectar_boton_x_mejorado(img)
    
    # FALLBACK a versión anterior (Hough Lines)
    h, w = img.shape[:2]
    
    try:
        # Buscar X SOLO en zona media-baja (60-90%, donde suelen estar modales)
        band_x = img[int(h * 0.60):int(h * 0.90), :]
        hsv_band = cv2.cvtColor(band_x, cv2.COLOR_BGR2HSV)
        
        mask_white = cv2.inRange(hsv_band, np.array([0, 0, 200]), np.array([180, 40, 255]))
        mask_gray = cv2.inRange(hsv_band, np.array([0, 0, 120]), np.array([180, 70, 200]))
        mask_x = cv2.bitwise_or(mask_white, mask_gray)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_x = cv2.morphologyEx(mask_x, cv2.MORPH_CLOSE, kernel)
        mask_x = cv2.morphologyEx(mask_x, cv2.MORPH_OPEN, kernel)
        
        edges = cv2.Canny(mask_x, 80, 200)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 50)
        
        if lines is None or len(lines) < 4:
            return False, 0, 0
        
        diagonal_lines = []
        for line in lines:
            rho, theta = line[0]
            theta_deg = np.degrees(theta)
            if (40 < theta_deg < 50) or (130 < theta_deg < 140):
                diagonal_lines.append((rho, theta))
        
        if len(diagonal_lines) < 3:
            return False, 0, 0
        
        contours, _ = cv2.findContours(mask_x, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False, 0, 0
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 3000 or area > 25000:
                continue
            
            x, y, bw, bh = cv2.boundingRect(contour)
            aspect = max(bw, bh) / (min(bw, bh) + 1)
            
            if aspect > 1.3 or aspect < 0.8:
                continue
            
            M = cv2.moments(contour)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"]) + int(h * 0.60)
                
                if cy > int(h * 0.95):
                    continue
                
                return True, cx, cy
        
        return False, 0, 0
        
    except Exception as e:
        if DEBUG:
            console.print(f"[dim]   ⚠ Error detectando X: {e}[/]")
        return False, 0, 0


def _detectar_boton_cancelar(img: np.ndarray) -> tuple[bool, int, int]:
    """
    Detecta el botón CANCELAR (generalmente verde/turquesa) en modales.
    Busca en zona 60-90% de altura.
    Devuelve: (encontrado, x, y) - coordenadas del centro del botón CANCELAR
    """
    if img is None:
        return False, 0, 0
    
    h, w = img.shape[:2]
    
    try:
        # Buscar CANCELAR en zona media-baja (60-90%)
        band = img[int(h * 0.60):int(h * 0.90), :]
        hsv_band = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
        
        # CANCELAR típicamente es verde/turquesa (botón secundario)
        # Rango HSV para verde claro/turquesa
        mask_green = cv2.inRange(hsv_band, np.array([80, 80, 100]), np.array([130, 255, 255]))
        
        # Limpiar ruido
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_green = cv2.morphologyEx(mask_green, cv2.MORPH_CLOSE, kernel)
        mask_green = cv2.morphologyEx(mask_green, cv2.MORPH_OPEN, kernel)
        
        contours, _ = cv2.findContours(mask_green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return False, 0, 0
        
        # Buscar el contorno más grande (es el botón)
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        
        # Botón debe tener área razonable (4000-50000 píxeles)
        if area < 4000 or area > 50000:
            return False, 0, 0
        
        # Obtener centro del botón
        M = cv2.moments(largest_contour)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"]) + int(h * 0.60)
            return True, cx, cy
        
        return False, 0, 0
        
    except Exception as e:
        if DEBUG:
            console.print(f"[dim]   ⚠ Error detectando CANCELAR: {e}[/]")
        return False, 0, 0


def _cerrar_pantalla_x(img: np.ndarray, ciclo: int) -> bool:
    """
    Detecta y cierra menús/modales haciendo clic en la X.
    Devuelve True si logró clickear, False si no encontró X.
    """
    if img is None:
        return False
    
    encontrado, btn_x, btn_y = _detectar_boton_x(img)
    
    if encontrado:
        console.print(f"[bold yellow]⊗ [{ciclo}] Botón X detectado en ({btn_x}, {btn_y}) → tap[/]")
        tap(btn_x, btn_y, delay=0.5)
        time.sleep(1.0)
        return True
    
    # FALLBACK: Tap en coordenadas típicas de X (usualmente centro bajo-izquierda)
    h, w = img.shape[:2]
    fallback_coords = [
        (220, int(h * 0.87)),  # Típica posición de X en menús (izquierda-centro)
        (int(w * 0.2), int(h * 0.87)),
        (int(w * 0.2), int(h * 0.85)),
    ]
    
    for fx, fy in fallback_coords:
        if 0 < fx < w and 0 < fy < h:
            console.print(f"[bold yellow]⊗ [{ciclo}] Intentando tap en X (fallback) en ({fx}, {fy})[/]")
            tap(fx, fy, delay=0.5)
            time.sleep(0.5)
            return True
    
    return False


def _cerrar_por_cancelar(img: np.ndarray, ciclo: int) -> bool:
    """
    Detecta y cierra modales clickeando el botón CANCELAR (verde).
    Devuelve True si logró clickear, False si no encontró botón.
    """
    if img is None:
        return False
    
    encontrado, btn_x, btn_y = _detectar_boton_cancelar(img)
    
    if encontrado:
        console.print(f"[bold green]✓ [{ciclo}] Botón CANCELAR detectado en ({btn_x}, {btn_y}) → tap[/]")
        tap(btn_x, btn_y, delay=0.5)
        time.sleep(1.0)
        return True
    
    return False


def _cerrar_post_captura_checkmark(img: np.ndarray, ciclo: int) -> bool:
    """
    Cierra POST-CAPTURA clickeando el CHECKMARK azul/celeste.
    Usa coordenadas HARDCODEADAS verificadas (547, 2142).
    La detección automática fue deshabilitada porque confundía botones.
    Devuelve True (asumir que el tap funcionó).
    """
    if img is None:
        return False
    
    # ⚠️ NOTA: Detección automática deshabilitada (confundía con botón verde de derecha)
    # Solo usar coordenadas hardcodeadas verificadas
    console.print(f"[bold cyan]   [{ciclo}] ✓ CHECKMARK → tap en ({CHECKMARK_X}, {CHECKMARK_Y})[/]")
    tap(CHECKMARK_X, CHECKMARK_Y, delay=0.5)
    time.sleep(1.0)
    return True  # Asumir que funcionó


def _cerrar_postcombate(ciclo: int) -> bool:
    """
    Loop post-captura: cierra DOS pantallas en secuencia (TAPs ONLY, CERO BACKs).
    Retorna True si se logró cerrar (volvió a MAPA), False si falló.

    FLUJO DE DOS PASOS:
      1. XP Card  → click botón DE ACUERDO (verde, coord detectada ~547,1570)
      2. Detalle  → click checkmark azul/teal (547,2142)
      → MAPA ✓
    """
    global _diagnostico_congelado, _tiempo_diagnostico_descongelado
    console.print(f"[bold green]✅ [{ciclo}] Captura terminada. Cerrando pantalla (TAPs ONLY)...[/]")

    # Congelar el diagnóstico: evita que el hilo de diagnóstico
    # reporte cambios de estado mientras cerramos los modales.
    # Se descongela automáticamente en 15s como máximo.
    _diagnostico_congelado = True
    _tiempo_diagnostico_descongelado = time.time() + 15.0

    for intento in range(2):
        img = screenshot_adb()
        if img is None:
            time.sleep(0.5)
            continue

        # ── PRIORIDAD 0: Diálogo ¿Quieres salir de Pokémon GO? → CANCELAR ────
        if _detectar_dialogo_salida_juego(img):
            console.print(f"[bold red]   [{ciclo}] ⚠ Diálogo salida detectado → tap CANCELAR ({CANCEL_EXIT_X},{CANCEL_EXIT_Y})[/]")
            tap(CANCEL_EXIT_X, CANCEL_EXIT_Y, delay=0.5)
            time.sleep(1.5)
            continue

        pantalla, dbg = _detectar_pantalla_postcombate(img)
        white_pct = dbg.get('white_pct', 0)
        green_px  = dbg.get('green_px', 0)
        teal_px   = dbg.get('teal_px', 0)
        console.print(
            f"[dim]   [{ciclo}] intento={intento+1} pantalla='{pantalla}' "
            f"white={white_pct:.1%} green={green_px}px teal={teal_px}px[/]"
        )

        # ── Ya estamos en MAPA ────────────────────────────────────────────
        if pantalla == 'mapa':
            console.print(f"[dim green]   [{ciclo}] ✓ De vuelta en MAPA[/]")
            _diagnostico_congelado = False  # descongelar al confirmar MAPA
            return True

        # ── PASO 1: Pantalla de XP/recompensas → click botón DE ACUERDO ──
        if pantalla == 'xp':
            # Usar coordenada verificada directamente (diagnostico devuelve coords erróneas)
            console.print(f"[bold green]✅ [{ciclo}] Pantalla XP → click DE ACUERDO en ({OK_XP_X}, {OK_XP_Y})[/]")
            tap(OK_XP_X, OK_XP_Y, delay=0.5)
            time.sleep(2.0)
            continue

        # ── PASO 2: Pantalla de detalle Pokémon → click checkmark ─────────
        if pantalla in ('detalle', 'modal'):
            console.print(f"[bold cyan]   [{ciclo}] Pantalla DETALLE → click checkmark ({CHECKMARK_X}, {CHECKMARK_Y})[/]")
            tap(CHECKMARK_X, CHECKMARK_Y, delay=0.5)
            time.sleep(2.5)  # más tiempo para que cierre la animación del detalle
            continue

        # ── Pantalla desconocida con blanco → tap en zona típica de botón ─
        if white_pct > 0.15:
            tap_y = int(PHONE_H * 0.75)
            console.print(f"[yellow]   [{ciclo}] Modal desconocido (white={white_pct:.1%}) → tap ({PHONE_W//2},{tap_y})[/]")
            tap(PHONE_W // 2, tap_y, delay=0.5)
            time.sleep(1.5)
            continue

        # ── Sin modal visible: esperar 1 ciclo ───────────────────────────
        time.sleep(1.0)

    console.print(f"[yellow]   [{ciclo}] ⚠ Modal no se cerró después de 12 intentos → usando Back[/]")
    _safe_back(ciclo)
    time.sleep(1.5)
    # Verificar si _safe_back logró llegar al MAPA
    img_final = screenshot_adb()
    if img_final is not None:
        pantalla_final, _ = _detectar_pantalla_postcombate(img_final)
        if pantalla_final == 'mapa':
            console.print(f"[dim green]   [{ciclo}] ✓ _safe_back llegó a MAPA → cierre exitoso[/]")
            _diagnostico_congelado = False
            return True
    _diagnostico_congelado = False
    return False


def _usar_baya(ciclo: int) -> None:
    """Tapa el botón de baya para mejorar probabilidad de captura (+10-15%)."""
    if not USAR_BAYAS_AUTOMATICO:
        return
    console.print(f"[dim cyan]   [{ciclo}] 🫐 Usando baya frambuesa (+10-15% captura)...[/]")
    tap(BAYA_X, BAYA_Y)
    time.sleep(0.8)  # esperar a que se active


def _detectar_aro_activo(img: np.ndarray) -> tuple[bool, float]:
    """
    Detecta si el aro de lanzamiento está presente Y activo (no en espera).
    Más preciso que _en_combate para determinar "tiempo de lanzar".
    
    Retorna (aro_activo, confianza).
    """
    if img is None:
        return False, 0.0
    
    en_combate, pct = _en_combate(img)
    
    # El aro está activo si:
    # 1. _en_combate() dice que estamos en la pantalla de captura
    # 2. El % de bola es lo suficientemente alto (>0.40 = visible y listo)
    aro_visible = en_combate and pct >= 0.40
    
    return aro_visible, pct


def _esperar_aro_activo_rapido(ciclo: int, timeout_ms: int = 3000) -> bool:
    """
    Espera RÁPIDAMENTE a que el aro esté activo y visible.
    Es más eficiente que _esperar_mejor_aro para el primer lanzamiento.
    
    Retorna True si el aro se activó, False si timeout.
    """
    deadline = time.time() + timeout_ms / 1000.0
    intent = 0
    
    while time.time() < deadline:
        intent += 1
        img = screenshot_adb()
        if img is None:
            time.sleep(0.1)
            continue
        
        aro_activo, conf = _detectar_aro_activo(img)
        
        if aro_activo:
            if DEBUG and intent > 1:
                console.print(f"[dim]   [{ciclo}] Aro activo detectado (conf={conf:.1%}) tras {intent} intentos[/]")
            return True
        
        if DEBUG and intent % 10 == 1:
            console.print(f"[dim]   [{ciclo}] Esperando aro activo... (conf={conf:.1%})[/]")
        
        time.sleep(0.1)
    
    if DEBUG:
        console.print(f"[dim]   [{ciclo}] Timeout esperando aro → lanzar de todas formas[/]")
    return False


def diagnosticar_pantalla_actual() -> None:
    """Asistente para saber dónde estás en Pokémon GO en este momento."""
    console.print("\n[bold cyan]🔍 DIAGNOSTICANDO PANTALLA ACTUAL...[/]\n")
    
    img = screenshot_adb()
    if img is None:
        console.print("[red]❌ No se pudo capturar pantalla[/]")
        return
    
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Detectar combate
    en_combate, pct_rojo = _en_combate(img)
    console.print(f"[bold]1. Estado de Combate:[/]")
    console.print(f"   {'✅' if en_combate else '❌'} HSV de bola: {pct_rojo:.1%} (umbral: 0.005)")
    
    # 2. Detectar mapa (NUEVO)
    console.print(f"\n[bold]2. Análisis de Mapa (Algoritmo Robusto):[/]")
    en_mapa_robusto, dbg_robusto = _en_mapa_robusto(img)
    en_mapa_legacy, dbg_legacy = _confirmar_en_mapa(img)
    
    console.print(f"   [bold cyan]Método Robusto (características invariantes):[/]")
    console.print(f"      • Intensidad bordes: {dbg_robusto.get('edges_intensity', 0):.2f} (umbral: 12)")
    console.print(f"      • Diversidad colores: {dbg_robusto.get('color_diversity', 0)} bins (umbral: 14)")
    console.print(f"      • Nivel textura: {dbg_robusto.get('texture_level', 0):.2f} (umbral: 700)")
    console.print(f"      • Entropía brillo: {dbg_robusto.get('brightness_entropy', 0):.2f} (umbral: 3.0)")
    criterios_dict = dbg_robusto.get('criterios', {})
    console.print(f"      • Criterios: {sum(criterios_dict.values())}/4 cumplidos")
    for nombre, cumple in criterios_dict.items():
        console.print(f"        - {nombre}: {'✅' if cumple else '❌'}")
    console.print(f"      → Resultado: {'[bold green]EN MAPA[/]' if en_mapa_robusto else '[bold red]NO EN MAPA[/]'}")
    
    console.print(f"\n   [bold cyan]Método Legacy (píxeles):[/]")
    console.print(f"      • Avatar verde: {dbg_legacy.get('avatar_green_px', 0)}px")
    console.print(f"      • Compañero template: {dbg_legacy.get('companero_conf', 0):.2f}")
    console.print(f"      • Fondo oscuro: {dbg_legacy.get('map_dark_pct', 0):.1%}")
    console.print(f"      → Resultado: {'[bold green]EN MAPA[/]' if en_mapa_legacy else '[bold red]NO EN MAPA[/]'}")
    
    final_en_mapa = en_mapa_robusto or en_mapa_legacy
    console.print(f"\n   [bold]Decisión Final: {'[bold green]✅ EN MAPA[/]' if final_en_mapa else '[bold red]❌ NO EN MAPA[/]'}[/]")
    
    # 3. Detectar pantalla postcombate
    pantalla, dbg_p = _detectar_pantalla_postcombate(img)
    console.print(f"\n[bold]3. Pantalla Post-combate:[/]")
    console.print(f"   Tipo detectado: [bold]{pantalla.upper()}[/]")
    console.print(f"      • Píxeles blancos (modal): {dbg_p.get('white_pct', 0):.1%}")
    console.print(f"      • Píxeles verdes (botón): {dbg_p.get('green_px', 0)}px")
    console.print(f"      • Píxeles cyan (barra): {dbg_p.get('teal_px', 0)}px")
    
    # 4. Resumen
    console.print(f"\n[bold yellow]📍 UBICACIÓN PROBABLE:[/]")
    if final_en_mapa and not en_combate:
        console.print("[bold green]✅ ESTÁS EN EL MAPA (campo abierto)[/]")
        console.print("   El bot puede buscar Pokémon aquí")
    elif en_combate:
        console.print("[bold magenta]⚔ ESTÁS EN COMBATE[/]")
        console.print("   El bot está intentando capturar")
    elif pantalla == 'xp':
        console.print("[bold green]📊 PANTALLA DE XP[/]")
        console.print("   Pokémon capturado, ganando experiencia")
    elif pantalla in ('detalle', 'modal'):
        console.print(f"[bold yellow]❓ MODAL DESCONOCIDO ({pantalla})[/]")
        console.print("   El bot intentará cerrar esta pantalla")
    else:
        console.print("[bold red]❌ UBICACIÓN DESCONOCIDA[/]")
        console.print("   Revisa manualmente la pantalla del celular")
    
    console.print("\n" + "="*80 + "\n")


def _usar_baya(ciclo: int) -> None:
    """Tapa el botón de baya para mejorar probabilidad de captura (+10-15%)."""
    if not USAR_BAYAS_AUTOMATICO:
        return
    console.print(f"[dim cyan]   [{ciclo}] 🫐 Usando baya frambuesa (+10-15% captura)...[/]")
    tap(BAYA_X, BAYA_Y)
    time.sleep(0.8)  # esperar a que se active


def _esperar_mejor_aro(ciclo: int, start_time: float) -> bool:
    """Espera a que el aro de lanzamiento sea más visible antes de tirar.
    Retorna True si se debe esperar más, False si lanzar ya."""
    if not WAIT_FOR_BETTER_ARO:
        return False
    
    elapsed_ms = (time.time() - start_time) * 1000
    if elapsed_ms > MAX_ESPERA_ARO_MS:
        if DEBUG:
            console.print(f"[dim]   [{ciclo}] Timeout esperando mejor aro ({elapsed_ms:.0f}ms) → lanzando[/]")
        return False  # timeout: lanzar de todas formas
    
    # Capturar pantalla actual
    img = screenshot_adb()
    if img is None:
        return False
    
    en_combate, pct_rojo = _en_combate(img)
    if not en_combate:
        return False  # No estamos en combate
    
    # Si el aro es lo bastante visible, lanzar AHORA
    # Umbral reducido de 0.70 a 0.55 para no esperar tanto
    if pct_rojo >= min(MIN_AURIOLA_PARA_TIRAR, 0.55):
        return False
    
    # Aro todavía débil → esperar un poco más pero con delay MÁS CORTO
    if DEBUG and elapsed_ms % 400 < 50:  # log cada ~400ms en lugar de 500ms
        console.print(f"[dim]   [{ciclo}] Esperando aro visible ({pct_rojo:.1%} < {min(MIN_AURIOLA_PARA_TIRAR, 0.55):.1%})...[/]")
    time.sleep(0.1)  # Aumentado de 0.05s a 0.1s para mejor sincronización
    return True


def _esperar_resultado_tiro(ciclo: int, tiro_n: int) -> str:
    """
    Observa qué pasó después de lanzar la Pokébola (3 FASES DISTINTAS).
    Devuelve:
      'capturado' → apareció pantalla de XP/modal (¡CAPTURADO!)
      'acertó'    → acertó pero no capturó → reintentar MISMA pokébola (3 sacudidas + se escapa)
      'falló'     → falló el tiro (bola rebota) → cambiar pokébola (no agarra)
      'huyó'      → el Pokémon huyó completamente (se va durante combate)

    Estrategia (3 FASES):
    FASE 1 (0-3s): IMPACTO - bola alcanza y rebota o agarra
    FASE 2 (3-6s): BALANCEO - si agarra, ve si se escapa (0-3 sacudidas)  
    FASE 3 (6-9s): RESULTADO - aparece XP o vuelve a COMBATE/MAPA
    
    ⚠️ NO CONGELAMOS DIAGNÓSTICO - el diagnóstico sigue corriendo para que el 
    estado máquina NO se quede esperando forever.
    """
    # ⚠️ Esperar 5.0s para que bola alcance e impacte completamente
    time.sleep(5.0)

    # 🔓 DESCONGELAR diagnóstico: la bola ya impactó, ahora necesitamos VER el resultado
    # (el congelado era solo para proteger la animación de vuelo)
    with _lock_diagnostico:
        _diagnostico_congelado = False
        _tiempo_diagnostico_descongelado = None

    # ═══════════════════════════════════════════════════════════════════
    # FASE 2 (4.0-7.0s): BALANCEO - polling para detectar captura o fallo temprano
    # ═══════════════════════════════════════════════════════════════════
    deadline_balanceo = time.time() + 3.0  # 3 segundos para fase de balanceo
    check_n = 0
    fase_actual = "BALANCEO"
    
    while time.time() < deadline_balanceo:
        check_n += 1
        img = screenshot_adb()
        if img is None:
            time.sleep(0.15)
            continue

        en_combate_hsv, pct_pokeball = _en_combate(img)
        pantalla, dbg = _detectar_pantalla_postcombate(img)
        en_mapa_chk, dbg_mapa = _confirmar_en_mapa(img)
        # También verificar el hilo de diagnóstico (ya descongelado)
        estado_diag_live = _obtener_estado_diagnostico()

        if DEBUG:
            console.print(
                f"[dim]   [{ciclo}] tiro#{tiro_n} {fase_actual} check{check_n}: "
                f"pantalla={pantalla} pokeball={pct_pokeball:.1%} "
                f"white={dbg.get('white_pct',0):.1%} diag={estado_diag_live}[/]"
            )

        # ✅ CAPTURADO: pantalla de recompensa detectada por _detectar_pantalla_postcombate
        if pantalla in ('xp', 'detalle', 'modal'):
            console.print(f"[bold green]   [{ciclo}] ✅ POST-CAPTURA detectada (pantalla={pantalla}) - cerrando...[/]")
            cerrado_correctamente = _cerrar_postcombate(ciclo)
            if cerrado_correctamente:
                console.print(f"[bold green]   [{ciclo}] ✅ CAPTURADO Y CERRADO CORRECTAMENTE[/]")
                return 'capturado'
            else:
                console.print(f"[bold red]   [{ciclo}] ❌ No se logró cerrar el modal - reintentando[/]")
                return 'acertó'

        # ✅ CAPTURADO: el hilo de diagnóstico detectó POST-CAPTURA (más sensible, S≤50)
        if estado_diag_live == "POST-CAPTURA":
            console.print(f"[bold green]   [{ciclo}] ✅ POST-CAPTURA por hilo diagnóstico - cerrando...[/]")
            cerrado_correctamente = _cerrar_postcombate(ciclo)
            if cerrado_correctamente:
                return 'capturado'
            return 'acertó'

        # ❌ FALLÓ: volvimos al mapa (bola rebota, no agarra)
        # Requiere TAMBIÉN que el hilo confirme MAPA para evitar falsos positivos
        # durante animaciones de combate donde la pantalla parece oscura
        if not en_combate_hsv and en_mapa_chk and pantalla == 'mapa' and check_n >= 4:
            if estado_diag_live == "MAPA":
                console.print(f"[bold red]   [{ciclo}] ❌ FALLÓ (rebota - mapa confirmado por hilo en {check_n*0.15:.1f}s)[/]")
                return 'falló'

        time.sleep(0.15)

    # ═══════════════════════════════════════════════════════════════════
    # FASE 3 (7.0-10.0s): RESULTADO - verificar si capturó o se escapó
    # ═══════════════════════════════════════════════════════════════════
    fase_actual = "RESULTADO"
    deadline_resultado = time.time() + 3.0  # 3 segundos más
    resultado_check_n = 0
    
    while time.time() < deadline_resultado:
        check_n += 1
        resultado_check_n += 1
        img = screenshot_adb()
        if img is None:
            time.sleep(0.15)
            continue

        en_combate_hsv, pct_pokeball = _en_combate(img)
        pantalla, dbg = _detectar_pantalla_postcombate(img)
        en_mapa_chk, dbg_mapa = _confirmar_en_mapa(img)
        estado_diag_live = _obtener_estado_diagnostico()

        if DEBUG:
            console.print(
                f"[dim]   [{ciclo}] tiro#{tiro_n} {fase_actual} check{check_n}: "
                f"pantalla={pantalla} pokeball={pct_pokeball:.1%} "
                f"white={dbg.get('white_pct',0):.1%} diag={estado_diag_live}[/]"
            )

        # ✅ CAPTURADO: aparece XP/detalle después del balanceo
        if pantalla in ('xp', 'detalle', 'modal'):
            console.print(f"[bold green]   [{ciclo}] ✅ POST-CAPTURA detectada (pantalla={pantalla} en resultado) - cerrando...[/]")
            cerrado_correctamente = _cerrar_postcombate(ciclo)
            if cerrado_correctamente:
                console.print(f"[bold green]   [{ciclo}] ✅ CAPTURADO Y CERRADO CORRECTAMENTE[/]")
                return 'capturado'
            else:
                console.print(f"[bold red]   [{ciclo}] ❌ No se logró cerrar el modal - reintentando[/]")
                return 'acertó'

        # ✅ CAPTURADO: hilo de diagnóstico confirma POST-CAPTURA
        if estado_diag_live == "POST-CAPTURA":
            console.print(f"[bold green]   [{ciclo}] ✅ POST-CAPTURA por hilo diagnóstico (resultado) - cerrando...[/]")
            cerrado_correctamente = _cerrar_postcombate(ciclo)
            if cerrado_correctamente:
                return 'capturado'
            return 'acertó'

        resultado_check_n += 1
        # 🏹 HUYÓ: Pokémon se escapó — requiere hilo Y local confirmando MAPA
        # Mínimo 2 checks en RESULTADO para evitar falsos durante transición de animación
        if not en_combate_hsv and not pantalla.startswith(('xp', 'detalle')):
            if en_mapa_chk and pantalla == 'mapa' and estado_diag_live == "MAPA" and resultado_check_n >= 2:
                console.print(f"[bold red]   [{ciclo}] 🏹 HUYÓ (confirmado por hilo+local en resultado)[/]")
                return 'huyó'

        time.sleep(0.15)

    # Timeout: sigue en combate sin cambios → ACERTÓ pero no capturó
    # (la pokébola lo agarró pero está en balanceo aún)
    console.print(f"[bold yellow]   [{ciclo}] 🎯 ACERTÓ (agarra pero no captura - reintentar misma pokébola)[/]")
    return 'acertó'


def _detectar_template(screenshot_gray: np.ndarray, template: np.ndarray,
                       threshold: float) -> bool:
    """Devuelve True si el template se encuentra en la imagen con confianza >= threshold."""
    return _confidence(screenshot_gray, template) >= threshold


def _en_mapa(img: np.ndarray) -> tuple[bool, float]:
    """
    Detecta si estamos en el MAPA (modo por defecto).
    
    ESTRATEGIA: Si NO hay evidencia clara de COMBATE, es MAPA.
    - No hay template de cámara (muy específico de COMBATE)
    - Bajo contraste en centro (no hay Pokémon grande visible)
    
    Devuelve (en_mapa, confianza: 0.0-1.0).
    """
    if img is None:
        return False, 0.0
    
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Test 1: NO hay template de cámara (muy específico de COMBATE)
    if _tmpl_camara is not None:
        roi_cam = gray[:int(h * 0.20), :]
        th, tw = _tmpl_camara.shape[:2]
        if roi_cam.shape[0] >= th and roi_cam.shape[1] >= tw:
            res = cv2.matchTemplate(roi_cam, _tmpl_camara, cv2.TM_CCOEFF_NORMED)
            _, conf_cam, _, _ = cv2.minMaxLoc(res)
            if conf_cam >= 0.45:  # Bajo threshold para detectar template
                return False, 0.0  # ← Hay template = definitivamente NO MAPA
    
    # Test 2: Contraste local bajo en centro (sin Pokémon grande lanzando)
    centro_x, centro_y = w // 2, h // 2
    zona_radio = 200
    zona_central = gray[
        max(0, centro_y-zona_radio):min(h, centro_y+zona_radio),
        max(0, centro_x-zona_radio):min(w, centro_x+zona_radio)
    ]
    
    contraste = zona_central.std() if zona_central.size > 0 else 0
    
    # En MAPA puro: contraste bajo (<17)
    # En COMBATE: contraste alto (>18)
    if contraste > 18:  # Contraste claramente ALTO = COMBATE
        return False, 0.0
    
    # Si pasó tests, probablemente es MAPA
    # Confianza depende de contraste
    if contraste < 15:
        confianza = 0.95  # Muy seguro
    elif contraste < 17:
        confianza = 0.80  # Bastante seguro
    else:
        confianza = 0.50  # Zona gris, pero por defecto MAPA
    
    return True, confianza


def _en_combate(img: np.ndarray) -> tuple[bool, float]:
    """
    Detecta si estamos en la pantalla de captura/combate.
    
    Usa detección por COLORES HSV específicos del combate:
    - Rojo intenso (pokébola): H=0-10 o 170-180, S>80, V>100
    - Aro blanco/gris: bajo S, alto V
    - Alto contraste por animación
    
    Devuelve (en_combate, confianza: 0.0-1.0).
    """
    if img is None:
        return False, 0.0
    
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # FILTRO PREVENTIVO: Si hay MUCHO cyan (>45%), probablemente es MAPA
    mask_cyan = cv2.inRange(hsv, np.array([85, 30, 50]), np.array([100, 255, 255]))
    pct_cyan = 100.0 * mask_cyan.sum() / (h * w * 255)
    if pct_cyan > 45:
        return False, 0.0
    
    # ESTRATEGIA 1: Buscar ROJO intenso (pokébola)
    # En COMBATE siempre hay una pokébola roja prominente
    mask_rojo1 = cv2.inRange(hsv, np.array([0, 80, 100]), np.array([10, 255, 255]))
    mask_rojo2 = cv2.inRange(hsv, np.array([170, 80, 100]), np.array([180, 255, 255]))
    mask_rojo = cv2.bitwise_or(mask_rojo1, mask_rojo2)
    pct_rojo = 100.0 * mask_rojo.sum() / (h * w * 255)
    
    if pct_rojo > 1.2:
        # Detectamos rojo prominente → COMBATE con alta confianza
        return True, min(pct_rojo / 3.0, 1.0)
    
    # ESTRATEGIA 2: Buscar ARO blanco/gris (indicador de combate)
    # El aro es círculo blanco/gris con alto valor
    mask_blanco = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([180, 50, 255]))
    pct_blanco = 100.0 * mask_blanco.sum() / (h * w * 255)
    
    # En COMBATE: mucho blanco (aro) + bajo cyan = combate
    if pct_blanco > 8.0 and pct_cyan < 20:
        return True, 0.7
    
    # ESTRATEGIA 3: Template de cámara (definitoria)
    if _tmpl_camara is not None:
        roi_cam = gray[:int(h * 0.20), :]
        th, tw = _tmpl_camara.shape[:2]
        if roi_cam.shape[0] >= th and roi_cam.shape[1] >= tw:
            res = cv2.matchTemplate(roi_cam, _tmpl_camara, cv2.TM_CCOEFF_NORMED)
            _, conf_cam, _, _ = cv2.minMaxLoc(res)
            if conf_cam >= 0.50:
                return True, min(conf_cam, 1.0)
    
    # ESTRATEGIA 4: Alto contraste en zona central (últimi recurso)
    centro_x, centro_y = w // 2, h // 2
    zona_radio = 200
    zona_central = gray[
        max(0, centro_y-zona_radio):min(h, centro_y+zona_radio),
        max(0, centro_x-zona_radio):min(w, centro_x+zona_radio)
    ]
    contraste = zona_central.std() if zona_central.size > 0 else 0
    
    if contraste > 20 and pct_cyan < 20:
        return True, min(contraste / 30.0, 1.0)
    
    # Nada más → NO COMBATE
    return False, 0.0
    if contraste > 19:
        return True, min(contraste / 23.0, 1.0)
    
    # Nada más → NO COMBATE
    return False, 0.0


def _estamos_en_pantalla_pokemon_capturado(img: np.ndarray) -> bool:
    """
    Detecta si estamos en la pantalla de ESTADÍSTICAS del Pokémon capturado.
    Esta pantalla tiene:
    - Título con nombre del Pokémon (ej: "Pidgeot", "Slowpoke")
    - Botones verdes/teal (MÁS PODER, EVOLUCIONAR)
    - Datos del Pokémon (peso, altura, etc.)
    - Barra teal en la parte inferior
    
    Devuelve True si detecta esta pantalla, False si no.
    """
    if img is None:
        return False
    
    h, w = img.shape[:2]
    
    try:
        # Detectar barra teal inferior (típica de pantalla de Pokémon capturado)
        strip_bottom = img[int(h * 0.90):, :]
        hsv_bottom = cv2.cvtColor(strip_bottom, cv2.COLOR_BGR2HSV)
        
        # Buscar teal/cian (botones EVOLUCIONAR, etc)
        mask_teal = cv2.inRange(hsv_bottom, np.array([70, 60, 80]), np.array([120, 255, 255]))
        teal_px = cv2.countNonZero(mask_teal)
        
        # Pantalla de Pokémon capturado tiene MUCHO teal en la barra inferior (>80000px)
        if teal_px > 80000:
            if DEBUG:
                console.print(f"[dim yellow]   ⚠ Detectada pantalla de Pokémon capturado (teal_px={teal_px})[/]")
            return True
        
        # Validación adicional: detectar si hay mucho blanco (típico de info Pokémon)
        # pero SIN rojo (si hubiera combate, tendría rojo de la bola)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Blanco: UI general
        mask_white = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 40, 255]))
        white_px = cv2.countNonZero(mask_white)
        white_pct = white_px / (h * w)
        
        # Rojo: pokébola de combate
        mask_red1 = cv2.inRange(hsv, np.array([0, 80, 80]), np.array([20, 255, 255]))
        mask_red2 = cv2.inRange(hsv, np.array([160, 80, 80]), np.array([180, 255, 255]))
        red_pct = cv2.countNonZero(mask_red1 | mask_red2) / (h * w)
        
        # Pantalla de Pokémon: mucho blanco (>30%) pero muy poco rojo (<1%)
        if white_pct > 0.30 and red_pct < 0.01:
            if DEBUG:
                console.print(f"[dim yellow]   ⚠ Detectada pantalla Pokémon por colores (white={white_pct:.1%}, red={red_pct:.1%})[/]")
            return True
    
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error en _estamos_en_pantalla_pokemon_capturado: {e}[/]")
    
    return False


def _detectar_dialogo_salida_juego(img: np.ndarray) -> bool:
    """
    Detecta el diálogo modal "¿Quieres salir de Pokémon GO?"
    con botones "DE ACUERDO" (verde) y "CANCELAR" (cian).
    
    Este diálogo aparece cuando presionas BACK demasiadas veces desde la pantalla de detalles.
    
    Devuelve True si detecta el diálogo, False si no.
    """
    if img is None:
        return False
    
    h, w = img.shape[:2]
    
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # El diálogo tiene dos botones característicos:
        # 1. "DE ACUERDO" en VERDE CLARO (brillo alto)
        # 2. "CANCELAR" en CIAN/TEAL
        
        # Buscar verde claro (botón DE ACUERDO)
        mask_green = cv2.inRange(hsv, np.array([40, 50, 100]), np.array([85, 255, 255]))
        green_px = cv2.countNonZero(mask_green)
        
        # Buscar cian (botón CANCELAR)
        mask_cyan = cv2.inRange(hsv, np.array([85, 80, 100]), np.array([100, 255, 255]))
        cyan_px = cv2.countNonZero(mask_cyan)
        
        # El diálogo tiene mucho verde + mucho cian (los dos botones)
        # Y predominantemente blanco en la zona central
        strip_dialog = img[int(h * 0.35):int(h * 0.75), int(w * 0.1):int(w * 0.9)]
        hsv_dialog = cv2.cvtColor(strip_dialog, cv2.COLOR_BGR2HSV)
        mask_white_dialog = cv2.inRange(hsv_dialog, np.array([0, 0, 200]), np.array([180, 30, 255]))
        white_px_dialog = cv2.countNonZero(mask_white_dialog)
        white_pct_dialog = white_px_dialog / strip_dialog.size
        
        # Validar que es el diálogo: tiene botones + mucho blanco
        # IMPORTANTE: excluir XP card (tiene green+cyan pero NO tiene rojo)
        # El diálogo de salida tiene fondo blanco puro sin verde dominante en zona media-alta.
        # La XP card tiene green_px muy alto (>300k) — el diálogo tiene mucho menos.
        if green_px > 15000 and cyan_px > 5000 and white_pct_dialog > 0.20:
            # Anti-falso-positivo: si hay demasiado verde es la XP card, no el diálogo
            if green_px > 200000:
                if DEBUG:
                    console.print(f"[dim]   ⚠ Falso positivo diálogo descartado (green={green_px} > 200k = XP card)[/]")
                return False
            # Anti-falso-positivo: si no hay blanco suficiente en zona superior es post-captura normal
            strip_top = img[int(h * 0.10):int(h * 0.30), int(w * 0.1):int(w * 0.9)]
            hsv_top = cv2.cvtColor(strip_top, cv2.COLOR_BGR2HSV)
            white_top = cv2.countNonZero(cv2.inRange(hsv_top, np.array([0,0,200]), np.array([180,30,255])))
            white_top_pct = white_top / strip_top.size
            if white_top_pct < 0.30:
                if DEBUG:
                    console.print(f"[dim]   ⚠ Falso positivo diálogo descartado (zona superior no blanca={white_top_pct:.1%})[/]")
                return False
            if DEBUG:
                console.print(f"[bold red]   ⚠⚠ DIÁLOGO DE SALIDA DETECTADO (green={green_px}, cyan={cyan_px})[/]")
            return True
    
    except Exception as e:
        if DEBUG:
            console.print(f"[red]   ⚠ Error en _detectar_dialogo_salida_juego: {e}[/]")
    
    return False


def _en_combate_con_ia(img: np.ndarray) -> tuple[bool, float]:
    """
    Versión mejorada de _en_combate() que usa IA como FALLBACK.
    
    1. Intenta detección por templates/colores (rápido)
    2. Si resultado no es concluyente, usa IA local (lento pero inteligente)
    3. Loguea automáticamente para aprendizaje posterior
    4. Retorna: (es_combate: bool, confianza: 0-1)
    
    NOTA: Si --no-ia está activado, solo usa detección tradicional.
    """
    if img is None:
        return False, 0.0
    
    # ──────────────────────────────────────────────────────────────────────
    # Si IA está deshabilitada, solo usar detección tradicional
    # ──────────────────────────────────────────────────────────────────────
    if not _usar_ia:
        return _en_combate(img)
    
    # ──────────────────────────────────────────────────────────────────────
    # PASO 1: INTENTAR DETECCIÓN TRADICIONAL
    # ──────────────────────────────────────────────────────────────────────
    es_combate_tradicional, confianza_trad = _en_combate(img)
    
    # Si está seguro (>80%), confiar en el resultado tradicional
    if confianza_trad > 0.80:
        return es_combate_tradicional, confianza_trad
    
    # Si está entre 0.30-0.80 (dudoso), consultar IA
    if confianza_trad > 0.30 and IA_DISPONIBLE and ia_analizar is not None:
        if DEBUG:
            console.print(f"[dim cyan]   [IA] Confianza baja ({confianza_trad:.0%}) → consultando IA...[/]")
        
        # Crear hash de screenshot para logging
        try:
            img_hash = hashlib.md5(cv2.imencode('.jpg', img)[1]).hexdigest()[:8]
        except:
            img_hash = "unknown"
        
        # Captura tiempo inicial
        time_inicio = time.time()
        resultado_ia = ia_analizar(img)
        tiempo_ms = int((time.time() - time_inicio) * 1000)
        
        # Mapear resultado IA a estado
        estado_real = "COMBATE" if es_combate_tradicional else "MAPA"  # Asunción
        
        # LOGUEAR ANÁLISIS (para aprendizaje posterior)
        if LOGGING_DISPONIBLE and logger is not None:
            logger.log_ia_analysis(
                screenshot_hash=img_hash,
                screen_state=estado_real,  # Lo que creemos que es
                ia_result=resultado_ia,     # Lo que IA dice
                time_ms=tiempo_ms,
                confidence=confianza_trad,
                is_correct=None  # Sin confirmación del usuario por ahora
            )
        
        # resultado_ia es ahora una cadena: "MAPA" | "COMBATE" | etc.
        if resultado_ia == "COMBATE":
            confianza_ia = 0.85  # Alta confianza si IA dice COMBATE
            if DEBUG:
                console.print(f"[dim cyan]   [IA] ✓ COMBATE detectado (confianza=0.85, tiempo={tiempo_ms}ms)[/]")
            return True, confianza_ia
        elif resultado_ia == "MAPA":
            confianza_ia = 0.85  # Alta confianza si IA dice MAPA
            if DEBUG:
                console.print(f"[dim cyan]   [IA] ✓ MAPA detectado (confianza=0.85, tiempo={tiempo_ms}ms)[/]")
            return False, confianza_ia
        elif resultado_ia in ["DETALLE_POKEMON", "RESUMEN_CAPTURA"]:
            # Post-captura, definitivamente no es combate
            if DEBUG:
                console.print(f"[dim cyan]   [IA] ✓ {resultado_ia} detectado (no es combate, tiempo={tiempo_ms}ms)[/]")
            return False, 0.85
    
    # Si no hay IA o ambas tienen baja confianza, confiar en la tradicional
    return es_combate_tradicional, confianza_trad


def detectar_pokemon_en_mapa(img: np.ndarray) -> list[tuple[int, int]]:
    """
    Detecta Pokémon en el mapa buscando círculos CIAN/AZUL (el color del sprite en mapa).
    
    Estrategia:
      1. Recorta la zona del mapa.
      2. Filtra píxeles CIAN (color de los pokémon en mapa: H~95, S>50, V>50).
      3. Usa Hough Circles para detectar círculos.
      4. Filtra por radio y distancia.
      
    Devuelve lista de (x, y) ordenados por tamaño (más grande/cercano primero).
    """
    if img is None:
        return []
    h, w = img.shape[:2]

    y0, y1 = int(h * MAP_ROI_TOP), int(h * MAP_ROI_BOTTOM)
    x0, x1 = int(w * MAP_ROI_LEFT), int(w * MAP_ROI_RIGHT)
    roi = img[y0:y1, x0:x1]
    
    # ESTRATEGIA 1: Detectar círculos CIAN usando Hough
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # Máscara CIAN: H en rango 85-105 (cyan), saturación y valor altos
    mask_cyan = cv2.inRange(hsv, np.array([85, 50, 50]), np.array([105, 255, 255]))
    
    # Aplicar Hough Circles en la máscara cyan
    circles = cv2.HoughCircles(
        mask_cyan,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=50,           # Distancia mínima entre círculos
        param1=50,            # Canny threshold alto
        param2=30,            # Acumulador threshold (más bajo = más sensible)
        minRadius=15,         # Radio mínimo (px)
        maxRadius=60          # Radio máximo (px)
    )
    
    candidatos: list[tuple[int, int, int]] = []
    
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for circle in circles[0, :]:
            x, y, radius = circle
            # Convertir a coordenadas globales
            cx = x + x0
            cy = y + y0
            candidatos.append((cx, cy, radius))
    
    # Si Hough no encuentra suficientes, usar estrategia antigua (blancos)
    if len(candidatos) < 2:
        # Blanco brillante: saturación muy baja + valor muy alto
        mask = cv2.inRange(hsv, np.array([0, 0, 220]), np.array([180, 35, 255]))
        
        # Morfología
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for c in contours:
            area = cv2.contourArea(c)
            if not (MAP_POKEMON_AREA_MIN < area < MAP_POKEMON_AREA_MAX):
                continue
            perimeter = cv2.arcLength(c, True)
            if perimeter == 0:
                continue
            circularity = 4 * np.pi * area / (perimeter ** 2)
            if circularity < MAP_POKEMON_CIRCULARITY:
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"]) + x0
            cy = int(M["m01"] / M["m00"]) + y0
            candidatos.append((cx, cy, int(np.sqrt(area / np.pi))))
    
    # Ordenar por radio descendente (más grande/cercano primero)
    candidatos.sort(key=lambda t: t[2], reverse=True)
    
    # Deduplicar: ignorar puntos cercanos
    resultado: list[tuple[int, int]] = []
    for cx, cy, _ in candidatos:
        if all(abs(cx - px) > MAP_DEDUP_DIST or abs(cy - py) > MAP_DEDUP_DIST
               for px, py in resultado):
            resultado.append((cx, cy))
    
    if DEBUG and len(resultado) > 0:
        console.print(f"[dim green]   [Pokémon] Detectados {len(resultado)} pokémon en mapa[/]")

    return resultado


def double_tap_rapido(x: int, y: int, gap_ms: int = BARRA_IZQ_TAP_GAP_MS):
    """Doble tap casi continuo: dos taps ADB separados por gap_ms milisegundos."""
    _adb("shell", "input", "tap", str(x), str(y))
    time.sleep(gap_ms / 1000.0)
    _adb("shell", "input", "tap", str(x), str(y))


# ══════════════════════════════════════════════════════════════════════════
#  LOOP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

def mostrar_ayuda():
    """Muestra información de uso del bot."""
    print("""
╔════════════════════════════════════════════════════════════════╗
║                   OPCIONES DE EJECUCIÓN                       ║
╚════════════════════════════════════════════════════════════════╝

Uso normal (SOLO TEMPLATES - Recomendado):
  python pokemon_catcher.py
  ./run.sh

Usar con IA (Ollama + LLaVA, MÁS LENTO, requiere recursos):
  python pokemon_catcher.py --enable-ia
  python pokemon_catcher.py --ia

Mantener Ollama activo después de salir:
  python pokemon_catcher.py --enable-ia --keep-ollama
  python pokemon_catcher.py --ia -k

Ollama seguirá corriendo en background y podrás detenerlo manualmente con:
  Linux/Mac:  pkill -9 ollama  
  Windows:    taskkill /F /IM ollama.exe

Presiona Ctrl+C para detener el bot.

═════════════════════════════════════════════════════════════════
ℹ  NUEVA ESTRATEGIA: Los templates son suficientes para la mayoría
    de casos. La IA es opcional y solo para debug.
    """)

def main():
    # ── PARSEAR ARGUMENTOS DE LÍNEA DE COMANDOS ──────────────────────────────
    global _usar_ia
    
    if "-h" in sys.argv or "--help" in sys.argv:
        mostrar_ayuda()
        sys.exit(0)
    
    # Procesar --enable-ia (NUEVO: IA deshabilitada por defecto)
    if "--enable-ia" in sys.argv or "--ia" in sys.argv:
        _usar_ia = True
        console.print("[bold yellow]⚠ MODO CON IA ACTIVADO (LLaVA via Ollama)[/]")
    else:
        _usar_ia = False  # Default: solo templates
    
    detener_ollama_al_salir = True  # Por defecto: SÍ detener Ollama
    if "--keep-ollama" in sys.argv or "-k" in sys.argv:
        detener_ollama_al_salir = False
        console.print("[dim yellow]ℹ Modo: Ollama seguirá corriendo después de salir (--keep-ollama)[/]")
    
    console.print(Panel(
        "[bold cyan]PokémonGO Catcher via ADB[/]\n\n"
        "  [white]Estado:[/] iniciando...\n"
        "  [white]Dispositivo:[/] " + (DEVICE_SERIAL or "auto-detect") + "\n"
        f"  [white]Debug:[/] {'[green]ON[/]' if DEBUG else '[dim]off[/]'}\n"
        f"  [white]IA:[/] {'[green]HABILITADA[/]' if _usar_ia else '[dim]DESHABILITADA (templates)[/]'}\n"
        f"  [white]Detener Ollama:[/] {'[green]SÍ[/]' if detener_ollama_al_salir else '[yellow]NO[/]'}\n\n"
        "  [dim]Ctrl+C para detener[/]",
        border_style="cyan"))

    # ── INICIALIZAR OLLAMA ───────────────────────────────────────────────────
    if _usar_ia:
        console.print("[dim]Verificando IA (Ollama)...[/]")
        if ollama_manager.iniciar_ollama():
            console.print("[bold green]✓ IA disponible[/]")
        else:
            console.print("[bold yellow]⚠ IA no disponible (sin LLaVA, solo templates)[/]")
            _usar_ia = False  # Fallback a templates si Ollama no anda
    else:
        console.print("[bold dim]ℹ Modo templates activado (sin IA). Usa --enable-ia para activar Ollama[/]")

    # ── SIGNAL HANDLERS PARA LIMPIAR AL SALIR ────────────────────────────────
    import signal
    def signal_handler(sig, frame):
        console.print("\n[bold yellow]⚠ Deteniendo bot...[/]")
        if detener_ollama_al_salir:
            ollama_manager.detener_ollama(force=True)  # Force=True para detener Ollama incluso si estaba ya corriendo
            console.print("[dim green]✓ Limpieza completada (Ollama detenido)[/]")
        else:
            console.print("[dim green]✓ Limpieza completada (Ollama sigue corriendo)[/]")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)

    # Verificar ADB
    ok, out = _adb("devices")
    if not ok:
        console.print(f"[bold red]❌ ADB no disponible: {out}[/]")
        if detener_ollama_al_salir:
            ollama_manager.detener_ollama(force=True)
        sys.exit(1)
    console.print(f"[dim green]ADB OK → {DEVICE_SERIAL}[/]")

    # Cargar templates
    console.print("[dim]Cargando templates...[/]")
    tmpl_confirmacion = _load_template(_tmpl_name("confirmacion.jpg"))
    tmpl_auriola      = _load_template(_tmpl_name("auriola_caza.jpg"))
    console.print(f"  confirmacion : {chr(9989) + ' ' + _tmpl_name('confirmacion.jpg') if tmpl_confirmacion is not None else chr(10060) + ' NO ENCONTRADA'}")
    console.print(f"  auriola      : {chr(9989) + ' ' + _tmpl_name('auriola_caza.jpg') if tmpl_auriola is not None else chr(10060) + ' NO ENCONTRADA'}")
    # Templates de pantalla de captura (cámara + baya + pokébola)
    global _tmpl_camara, _tmpl_baya, _tmpl_pokeball, _tmpl_check, _tmpl_check_pokemon
    _tmpl_camara  = _load_template(_tmpl_name("camara.jpg"))
    _tmpl_baya    = _load_template("bayabrambu.jpg")
    _tmpl_pokeball = _load_template("pokeball_template.jpg")
    # Cargar check.png desde la raíz del proyecto
    check_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check.png")
    _tmpl_check = _imread_unicode(check_path, cv2.IMREAD_GRAYSCALE) if os.path.exists(check_path) else None
    # Cargar check_pokemon.png (botón checkmark teal de pantalla detalle)
    check_poke_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_pokemon.png")
    _tmpl_check_pokemon = _imread_unicode(check_poke_path, cv2.IMREAD_GRAYSCALE) if os.path.exists(check_poke_path) else None
    console.print(f"  camara       : {chr(9989) + ' ' + _tmpl_name('camara.jpg') if _tmpl_camara is not None else chr(10060) + ' NO ENCONTRADA'}")
    console.print(f"  baya         : {chr(9989) + ' bayabrambu.jpg' if _tmpl_baya is not None else chr(10060) + ' NO ENCONTRADA'}")
    console.print(f"  pokeball_tmpl: {chr(9989) + ' pokeball_template.jpg' if _tmpl_pokeball is not None else chr(10060) + ' NO ENCONTRADA'}")
    console.print(f"  check_btn    : {chr(9989) + ' check.png' if _tmpl_check is not None else chr(10060) + ' NO ENCONTRADA'}")
    console.print(f"  check_pokemon: {chr(9989) + ' check_pokemon.png' if _tmpl_check_pokemon is not None else chr(10060) + ' NO ENCONTRADA'}")
    _cargar_companero()
    
    # ── INICIALIZAR SISTEMAS OPTIMIZADOS ───────────────────────────────────────
    console.print("[dim]Inicializando sistemas optimizados...[/]")
    
    # Mejora 4: Iniciar logger asincrónico
    _iniciar_logger_asinc()
    log_async("[dim green]✓ Logger asincrónico iniciado[/]")
    
    # Mejora 6: Precarga de templates
    template_names = [
        _tmpl_name("confirmacion.jpg"),
        _tmpl_name("auriola_caza.jpg"),
        _tmpl_name("camara.jpg"),
        "bayabrambu.jpg",
        "pokeball_template.jpg",
        "check.png",
    ]
    _precargar_templates(template_names)
    log_async("[dim green]✓ Templates precargados[/]")
    
    # Mejora 7: Inicializar buffer circular
    log_async("[dim green]✓ Buffer circular inicializado[/]")
    
    # Mostrar estadísticas iniciales
    console.print("[dim]Estado: listo para capturar[/]\n")
    
    # Iniciar diagnóstico centralizado
    _iniciar_diagnostico()
    
    # Iniciar vigilancia de X (cierre automático de modales)
    _iniciar_vigilancia_x()

    # ══════════════════════════════════════════════════════════════════════════
    #  FUNCIONES DE ACCIÓN - Ejecutadas según lo que diagnostico nos diga
    # ══════════════════════════════════════════════════════════════════════════
    
    max_throws = 4  # Máximo intentos por combate

    def _accion_mapa(ciclo):
        """
        ACCIÓN MAPA: Detecta pokemones visibles en el mapa y hace doble tap en el pokémon detectado.
        Usa diagnostico.py para obtener coordenadas automáticas.
        Si no puede detectar, usa coordenadas fijas como fallback.
        
        Devuelve: 'ESPERANDO_COMBATE' tras doble tap.
        """
        # Verificar que el hilo confirme MAPA antes de actuar
        # (puede haber pantalla de detalle abierta que diagnostico.py confunde con MAPA)
        estado_hilo = _obtener_estado_diagnostico()
        if estado_hilo == "POST-CAPTURA":
            console.print(f"[yellow]⚠ [{ciclo}] _accion_mapa: hilo ve POST-CAPTURA → cerrar pantalla primero[/]")
            _cerrar_postcombate(ciclo)
            return "MAPA"

        # Si el hilo de diagnóstico YA ve COMBATE, no tapear — transicionar directamente
        if estado_hilo == "COMBATE":
            console.print(f"[bold yellow]⚔ [{ciclo}] _accion_mapa: hilo ve COMBATE → entrando directamente sin tap[/]")
            return "COMBATE"

        # Siempre tocar el panel sniper izquierdo — diagnostico confirma estado pero
        # sus coordenadas apuntan al mapa-mundo (ej: 456,492), NO al panel sniper.
        coord_x, coord_y = SNIPER_X, SNIPER_Y_FIRST
        confirmado_mapa = False

        # Usar diagnostico solo para confirmar que estamos en MAPA
        if DIAGNOSTICO_DISPONIBLE and mostrar_diagnostico:
            try:
                estado, detalles, diag_x, diag_y = mostrar_diagnostico()
                if estado and "MAPA" in estado:
                    confirmado_mapa = True
                    console.print(f"[green]✓[/] [{ciclo}] DIAGNOSTICO confirmó MAPA (diag coords ignoradas: {diag_x},{diag_y})")
                elif estado and "COMBATE" in estado:
                    # diagnostico.py también ve COMBATE → transicionar sin tapear
                    console.print(f"[bold yellow]⚔ [{ciclo}] diagnostico.py ve COMBATE → entrando sin tap[/]")
                    return "COMBATE"
                else:
                    console.print(f"[yellow]⚠[/] [{ciclo}] Diagnostico no confirmó MAPA (estado={estado})")
            except Exception as e:
                console.print(f"[yellow]⚠[/] [{ciclo}] Error en diagnostico: {e}")
        else:
            if not DIAGNOSTICO_DISPONIBLE:
                console.print(f"[dim yellow]⚠ Diagnostico NO disponible (import falló)[/]")

        source_str = "[sniper panel]" if confirmado_mapa else "[sniper panel fallback]"

        # Probar slots del panel de arriba a abajo hasta que uno entre a combate.
        # Cada slot está separado por SNIPER_SLOT_HEIGHT px.
        # También probamos tap simple (algunos clientes no responden al doble).
        slots_y = [
            SNIPER_Y_FIRST,
            SNIPER_Y_FIRST + SNIPER_SLOT_HEIGHT,
            SNIPER_Y_FIRST + SNIPER_SLOT_HEIGHT * 2,
        ]
        nonlocal _tiempo_tap_sniper

        for slot_y in slots_y:
            console.print(f"[bold cyan]🎯 [{ciclo}] MAPA → TAP sniper ({coord_x}, {slot_y}) {source_str}[/]")
            # Primero tap simple, más compatible con PGSharp
            tap(coord_x, slot_y)
            time.sleep(0.5)
            # Verificar si ya entró a combate
            if _obtener_estado_diagnostico() == "COMBATE":
                console.print(f"[bold yellow]⚔ [{ciclo}] Combate detectado tras tap en slot Y={slot_y}[/]")
                _tiempo_tap_sniper = time.time() - _TIMEOUT_ESPERANDO_COMBATE  # ya entró, no esperar
                return "COMBATE"
            # También hacer doble tap como respaldo
            double_tap(coord_x, slot_y, delay=WAIT_SNIPER_ENTRE_TAPS)
            time.sleep(0.8)
            if _obtener_estado_diagnostico() == "COMBATE":
                console.print(f"[bold yellow]⚔ [{ciclo}] Combate detectado tras doble-tap en slot Y={slot_y}[/]")
                _tiempo_tap_sniper = time.time() - _TIMEOUT_ESPERANDO_COMBATE
                return "COMBATE"

        # Ningún slot respondió — esperar a que el diagnóstico lo detecte
        _tiempo_tap_sniper = time.time()
        console.print(f"[dim cyan]   [{ciclo}] Esperando COMBATE...[/]")
        return "ESPERANDO_COMBATE"

    def _accion_combate(ciclo, throws_en_combate, tmpl_confirmacion):
        """
        ACCIÓN COMBATE: Lanzar UNA pokébola si es posible.
        Devuelve: (nuevo_estado, nuevo_throws_count)
        
        Estados posibles:
          - 'COMBATE': Sigue en combate, próxima pokébola
          - 'POST-CAPTURA': Pokémon capturado
          - 'MAPA': Pokémon huyó o se alcanzó máximo
        """
        # Esperar 1 segundo antes de lanzar
        time.sleep(1.0)
        
        if throws_en_combate >= max_throws:
            # Demasiados intentos → presionar atrás
            console.print(f"[red]⚠ [{ciclo}] {max_throws} pokébolas sin capturar → saliendo[/]")
            _safe_back(ciclo)
            time.sleep(0.5)  # Esperar estabilización sin congelar diagnóstico
            _registrar_fallo_pokebola()
            return ("MAPA", 0)
        
        # Usar baya en primer tiro
        if throws_en_combate == 0 and USAR_BAYAS_AUTOMATICO:
            _usar_baya(ciclo)
        
        # Esperar aro
        if throws_en_combate == 0:
            _esperar_aro_activo_rapido(ciclo, timeout_ms=2500)
        
        # 🔒 CONGELAR DIAGNÓSTICO antes de lanzar pokébola
        # (la animación confundiría COMBATE con MAPA)
        global _diagnostico_congelado, _tiempo_diagnostico_descongelado
        with _lock_diagnostico:
            _diagnostico_congelado = True
            _tiempo_diagnostico_descongelado = None
        
        # Lanzar pokébola
        dx = random.randint(-8, 8)
        pokebola_actual = _seleccionar_pokebola_siguiente()
        pokebola_map = {
            "ULTRA": (THROW_END_Y_ULTRA, THROW_DURATION_ULTRA_MS, "[bold red]ULTRA[/]"),
            "SUPER_ULTRA": (THROW_END_Y_SUPER_ULTRA, THROW_DURATION_SUPER_ULTRA_MS, "[bold magenta]SUPER ULTRA[/]"),
            "LEJANO": (THROW_END_Y_FAR, THROW_DURATION_FAR_MS, "[bold]LEJANO[/]"),
            "NORMAL": (THROW_END_Y, THROW_DURATION_MS, "normal"),
        }
        end_y, dur_base, tipo_str = pokebola_map[pokebola_actual]
        dur = dur_base + random.randint(-15, 15) if pokebola_actual == "ULTRA" else dur_base + random.randint(-20, 20)
        
        console.print(f"[cyan]💫 [{ciclo}] Pokébola #{throws_en_combate + 1}/{max_throws}: {tipo_str}[/]")
        swipe(THROW_START_X + dx, THROW_START_Y, THROW_END_X + dx, end_y, dur)
        throws_en_combate_nuevo = throws_en_combate + 1
        
        # Verificar resultado (diagnóstico SIGUE CONGELADO durante esto)
        resultado = _esperar_resultado_tiro(ciclo, throws_en_combate_nuevo)
        
        # 🔓 DESCONGELAR DIAGNÓSTICO: Después de esperar resultado
        with _lock_diagnostico:
            _diagnostico_congelado = False
            _tiempo_diagnostico_descongelado = None
        
        # 🔍 VERIFICACIÓN INMEDIATA POST-TIRO: Leer diagnóstico para confirmar estado real
        # Si el Pokémon huyó o se capturó RÁPIDAMENTE, el diagnóstico lo detectará antes que _esperar_resultado_tiro()
        estado_diag_post = _obtener_estado_diagnostico()
        if estado_diag_post == "MAPA":
            console.print(f"[bold red]🏹 [{ciclo}] Verificación POST-TIRO: Pokémon huyó (MAPA detectado por diagnóstico)[/]")
            _registrar_fallo_pokebola()
            return ("MAPA", 0)
        elif estado_diag_post == "POST-CAPTURA":
            console.print(f"[bold green]✅ [{ciclo}] Verificación POST-TIRO: Capturado (POST-CAPTURA detectado por diagnóstico)[/]")
            _registrar_acierto_pokebola()
            return ("POST-CAPTURA", throws_en_combate_nuevo)
        
        # Si diagnóstico sigue en COMBATE, procesar resultado normal de _esperar_resultado_tiro()
        if resultado == 'capturado':
            console.print(f"[bold green]✅ [{ciclo}] ¡CAPTURADO![/]")
            _registrar_acierto_pokebola()
            return ("POST-CAPTURA", throws_en_combate_nuevo)
        elif resultado == 'acertó':
            _registrar_acierto_pokebola()
            console.print(f"[yellow]💫 [{ciclo}] Acertó pero sin captura → reintentar MISMA pokébola (balanceo)[/]")
            return ("COMBATE", throws_en_combate_nuevo)
        elif resultado == 'falló':
            _registrar_fallo_pokebola()
            console.print(f"[red]❌ [{ciclo}] Falló tiro (rebota) → cambiar pokébola[/]")
            return ("COMBATE", throws_en_combate_nuevo)
        elif resultado == 'huyó':
            console.print(f"[bold red]🏹 [{ciclo}] ¡Pokémon huyó![/]")
            _registrar_fallo_pokebola()
            return ("MAPA", 0)
        
        return ("COMBATE", throws_en_combate_nuevo)

    def _accion_postcaptura(ciclo):
        """
        ACCIÓN POST-CAPTURA: Usa el método existente _cerrar_postcombate()
        que ya tiene lógica comprobada para cerrar modales POST-CAPTURA.
        ⚠️ CONGELA el diagnóstico durante el cierre para evitar clickeos duplicados.
        """
        global _diagnostico_congelado, _tiempo_diagnostico_descongelado
        
        # Esperar 1 segundo antes de cerrar modal
        time.sleep(1.0)
        
        console.print(f"[bold green]🎁 [{ciclo}] POST-CAPTURA detectado - CONGELANDO DIAGNÓSTICO[/]")
        
        # 🔒 CONGELAR diagnóstico mientras cerramos POST-CAPTURA (evita clickeos duplicados)
        with _lock_diagnostico:
            _diagnostico_congelado = True
            _tiempo_diagnostico_descongelado = time.time() + 8.0  # Descongelar en 8 segundos (aumentado para estabilidad)
        
        _cerrar_postcombate(ciclo)
        
        # Esperar extra para asegurar transición completa
        time.sleep(2.0)
        
        # 🔓 DESCONGELAR diagnóstico después de cerrar
        with _lock_diagnostico:
            _diagnostico_congelado = False
            _tiempo_diagnostico_descongelado = None
        
        return "MAPA"




    console.print("\n[bold green]✅ Iniciando loop de captura...[/]")
    console.print("[dim]Arquitectura: diagnóstico cada 1s (paralelo) + acciones cada 3s (principal)[/]\n")

    estado_maquina = "MAPA"           
    throws_en_combate = 0              
    ciclo = 0                          
    tiempo_ultimo_ciclo = time.time()
    _tiempo_tap_sniper = 0.0           # Timestamp del último tap al sniper
    _TIMEOUT_ESPERANDO_COMBATE = 3.0   # Si en 3s no entra a combate, reintentar tap
    estado_diag_anterior = None  # Para detectar cambios
    
    while True:
        # Control de timing: máximo 1 acción cada ~3.0s (diagnostico lee cada 1.0s en paralelo)
        ahora = time.time()
        if ahora - tiempo_ultimo_ciclo < 3.0:
            time.sleep(0.5)
            continue
        
        tiempo_ultimo_ciclo = ahora
        ciclo += 1
        
        # Mostrar estadísticas cada 10 ciclos
        if ciclo % 10 == 0:
            mostrar_stats()
        
        # ═══ LEER DIAGNÓSTICO DIRECTAMENTE (SIN DOBLE CONFIRMACIÓN) ═════
        estado_diag = _obtener_estado_diagnostico()
        
        # Mostrar cambios de estado
        if estado_diag != estado_diag_anterior:
            console.print(f"[bold]█ [{ciclo:04d}] diagnóstico={estado_diag} │ máquina={estado_maquina}[/]")
            estado_diag_anterior = estado_diag
        
        # ═══ LÓGICA SIMPLE: Siempre actúa según el diagnóstico actual ═════════
        # Sin importar estado anterior, solo ejecuta la acción del estado actual.
        
        # CASO 1: Diagnóstico = MAPA → Ejecutar ACCIÓN MAPA
        if estado_diag == "MAPA":
            # Si ya hicimos tap y estamos esperando que cargue el combate,
            # NO hacer otro tap — el juego tarda 2-4s en transicionar
            if estado_maquina == "ESPERANDO_COMBATE":
                elapsed = time.time() - _tiempo_tap_sniper
                
                # Después de 3 segundos → lanzar pokébola (aunque diagnóstico diga MAPA)
                if elapsed >= _TIMEOUT_ESPERANDO_COMBATE:
                    console.print(f"[dim cyan]   [{ciclo}] ⏳ Lanzando Pokébola (timeout {_TIMEOUT_ESPERANDO_COMBATE}s)...[/]")
                    throws_en_combate = 0
                    _iniciar_vigilancia(tmpl_confirmacion)
                    nuevo_estado, nuevo_throws = _accion_combate(ciclo, throws_en_combate, tmpl_confirmacion)
                    estado_maquina = nuevo_estado
                    throws_en_combate = nuevo_throws
                    if nuevo_estado == "POST-CAPTURA":
                        _detener_vigilancia()
                    elif nuevo_estado == "MAPA":
                        # Si falla, reintentar tap
                        console.print(f"[yellow]   [{ciclo}] No fue combate real → reintentar tap[/]")
                    continue
                else:
                    continue  # Esperar los 3 segundos

            if estado_maquina != "MAPA":
                console.print(f"[bold green]🗺 [{ciclo}] Diagnóstico: MAPA[/]")
                estado_maquina = "MAPA"
                throws_en_combate = 0
                _detener_vigilancia()
            
            nuevo_estado = _accion_mapa(ciclo)
            estado_maquina = nuevo_estado
            # Si _accion_mapa detectó COMBATE directamente (sin tap), ejecutar combate YA
            # sin esperar al siguiente ciclo (el hilo de fondo puede tardar en actualizarse)
            if nuevo_estado == "COMBATE":
                throws_en_combate = 0
                _iniciar_vigilancia(tmpl_confirmacion)
                nuevo_estado2, nuevo_throws = _accion_combate(ciclo, throws_en_combate, tmpl_confirmacion)
                estado_maquina = nuevo_estado2
                throws_en_combate = nuevo_throws
                if nuevo_estado2 == "POST-CAPTURA":
                    _detener_vigilancia()
        
        # CASO 2: Diagnóstico = COMBATE → Ejecutar ACCIÓN COMBATE
        elif estado_diag == "COMBATE":
            if estado_maquina != "COMBATE":
                console.print(f"[bold yellow]⚔ [{ciclo}] Diagnóstico: COMBATE[/]")
                estado_maquina = "COMBATE"
                throws_en_combate = 0
                _iniciar_vigilancia(tmpl_confirmacion)
            
            nuevo_estado, nuevo_throws = _accion_combate(ciclo, throws_en_combate, tmpl_confirmacion)
            estado_maquina = nuevo_estado
            throws_en_combate = nuevo_throws
            
            if nuevo_estado == "POST-CAPTURA":
                _detener_vigilancia()
        
        # CASO 3: Diagnóstico = POST-CAPTURA → Ejecutar ACCIÓN POST-CAPTURA
        elif estado_diag == "POST-CAPTURA":
            if estado_maquina != "POST-CAPTURA":
                console.print(f"[bold green]🎁 [{ciclo}] Diagnóstico: POST-CAPTURA[/]")
                estado_maquina = "POST-CAPTURA"
                _detener_vigilancia()
            
            nuevo_estado = _accion_postcaptura(ciclo)
            estado_maquina = nuevo_estado

        # CASO 4: Estado no confiable (DESCONOCIDO/CARGANDO) → Solo esperar sin hacer nada
        elif estado_diag in ("DESCONOCIDO", "CARGANDO"):
            if estado_maquina != "DESCONOCIDO":
                console.print(f"[dim yellow]⏳ [{ciclo}] Diagnóstico: {estado_diag} (esperando estabilización)[/]")
                estado_maquina = "DESCONOCIDO"
                _detener_vigilancia()
            # No hacer nada - dejar que se estabilice el diagnóstico

    try:
        while True:
            # ── Control de timing: dinámico según el estado ──────
            # POST-CAPTURA: 1.0s (cierre cauteloso)
            # COMBATE/otros: 3.0s (esperar confirmación completa del diagnóstico)
            ahora = time.time()
            timing_target = 1.0 if estado_maquina == "POST-CAPTURA" else 3.0
            if ahora - tiempo_ultimo_ciclo < timing_target:
                time.sleep(0.1)
                continue
            
            tiempo_ultimo_ciclo = ahora
            ciclo += 1
            
            # ── Mostrar estadísticas cada 10 ciclos (Mejora 5) ───────────────────
            if ciclo % 10 == 0:
                mostrar_stats()
            
            # ── Leer estado del diagnóstico (actualizado constantemente por hilo paralelo) ──
            estado_diag = _obtener_estado_diagnostico()
            
            # ─ DOBLE CONFIRMACIÓN DE DIAGNÓSTICO ─────────────────────────────────
            # EXCEPCIÓN: Si estamos EN MAPA y el diagnóstico ve COMBATE, confirmamos INMEDIATAMENTE
            # (rojo>90% es evidencia muy fuerte de combate)
            if estado_maquina == "MAPA" and estado_diag == "COMBATE" and estado_diag_confirmado is None:
                estado_diag_confirmado = "COMBATE"
                estado_diag_pendiente = "COMBATE"
                tiempo_inicio_confirmacion = None
                if DEBUG:
                    console.print(f"[bold cyan]   [RÁPIDO] Confirmación inmediata: MAPA + COMBATE detectado[/]")
            # EXCEPCIÓN 2: Si estamos ESPERANDO_COMBATE y el diagnóstico ve COMBATE, confirmamos INMEDIATAMENTE
            # (no necesitamos esperar 1.0s de confirmación en este caso)
            # EXCEPCIÓN 3: Si estamos EN COMBATE y el diagnóstico sigue viendo COMBATE, confirmamos INMEDIATAMENTE
            # (esto acelera los reintentos después de acertar sin capturar)
            elif (estado_maquina == "ESPERANDO_COMBATE" or estado_maquina == "COMBATE") and estado_diag == "COMBATE" and estado_diag_confirmado is None:
                estado_diag_confirmado = "COMBATE"
                estado_diag_pendiente = "COMBATE"
                tiempo_inicio_confirmacion = None
                if DEBUG:
                    console.print(f"[bold cyan]   [RÁPIDO] Confirmación inmediata: {estado_maquina} + COMBATE detectado[/]")
            # EXCEPCIÓN 4: Si estamos EN POST-CAPTURA y el diagnóstico sigue viéndola, confirmamos INMEDIATAMENTE
            # (esto acelera el cierre de pantalla de XP/detalles)
            elif estado_maquina == "POST-CAPTURA" and estado_diag == "POST-CAPTURA" and estado_diag_confirmado is None:
                estado_diag_confirmado = "POST-CAPTURA"
                estado_diag_pendiente = "POST-CAPTURA"
                tiempo_inicio_confirmacion = None
                if DEBUG:
                    console.print(f"[bold cyan]   [RÁPIDO] Confirmación inmediata: POST-CAPTURA detectado[/]")
            # Si es un estado NUEVO (diferente al pendiente), iniciar confirmación
            elif estado_diag != estado_diag_pendiente:
                estado_diag_pendiente = estado_diag
                tiempo_inicio_confirmacion = ahora
                # SIN LOG HASTA SEGUNDA CONFIRMACIÓN
                # continue
            
            # Si es el MISMO estado pero aún no pasaron 1.0 segundos, seguir esperando
            if tiempo_inicio_confirmacion is not None and (ahora - tiempo_inicio_confirmacion) < 1.0:
                # Sigue esperando confirmación, sin log
                time.sleep(0.5)
                continue
            
            # ¡Pasaron 1.0 segundos! Reconfirmar leyendo diagnóstico nuevamente
            if tiempo_inicio_confirmacion is not None and (ahora - tiempo_inicio_confirmacion) >= 1.0:
                estado_diag_reconfirma = _obtener_estado_diagnostico()
                if estado_diag_reconfirma != estado_diag_pendiente:
                    # El estado cambió durante los 0.5 segundos → reiniciar confirmación
                    estado_diag_pendiente = estado_diag_reconfirma
                    tiempo_inicio_confirmacion = ahora
                    # SIN LOG, volver a esperar
                    continue
                else:
                    # ✅ CONFIRMADO 2 VECES → puede proceder
                    estado_diag_confirmado = estado_diag_pendiente
                    tiempo_inicio_confirmacion = None
            
            # Si aún no hay confirmación, esperar
            if estado_diag_confirmado is None:
                continue
            
            # ═══ AQUÍ LLEGA CON ESTADO CONFIRMADO 2 VECES ═══════════════════════
            if DEBUG:
                console.print(f"[dim]█ [{ciclo:04d}] diagnóstico=[bold cyan]{estado_diag_confirmado}[/] │ máquina=[bold yellow]{estado_maquina}[/] │ vigilancia={_hay_confirmacion_detectada()}[/dim]")
            
            # ══════════════════════════════════════════════════════════════════════════
            #  ⚠⚠ VALIDACIÓN CRÍTICA: ¿Diálogo de salida "¿Quieres salir de Pokémon GO?"?
            # ══════════════════════════════════════════════════════════════════════════
            img_dialogo = screenshot_adb()
            if img_dialogo is not None and _detectar_dialogo_salida_juego(img_dialogo):
                console.print(f"[bold red]🚨 [{ciclo}] ¡¡DIÁLOGO DE SALIDA DETECTADO!! → PRESIONANDO CANCELAR[/]")
                # Coordenadas aproximadas del botón CANCELAR (parte inferior derecha del diálogo)
                # En pantalla 1080x2400, el botón está alrededor de (750, 560)
                _adb("shell", "input", "tap", "750", "560")
                time.sleep(0.5)
                estado_diag_confirmado = None
                continue
            
            # ══════════════════════════════════════════════════════════════════════════
            #  VALIDACIÓN ESPECIAL: ¿Estamos en estado POST-CAPTURA-DETALLE (atrapado)?
            # ══════════════════════════════════════════════════════════════════════════
            img_check = screenshot_adb()
            if img_check is not None and estado_maquina == "POST-CAPTURA":
                # Solo revisar si ya sabemos que estamos POST-CAPTURA
                tipo_pantalla_post = _detectar_pantalla_postcombate(img_check)
                if tipo_pantalla_post == "detalle":
                    # Estamos ESPECÍFICAMENTE en la pantalla de detalles del Pokémon capturado
                    console.print(f"[bold yellow]⚠ [{ciclo}] Atrapado en DETALLE → Intentando cerrar con TAPs[/]")
                    
                    # Estrategia: SOLO TAPS, NUNCA BACK (que cierra el juego)
                    for tap_intento in range(4):
                        # TAP en zona de botones de cierre (arriba izquierda, abajo centro, etc.)
                        tap_coords = [
                            (50, 100),      # Botón atrás esquina superior izquierda
                            (PHONE_W // 2, 2100),  # Centro bajo (zona botón)
                            (50, 50),       # Esquina superior
                            (PHONE_W - 50, 100),  # Esquina superior derecha
                        ]
                        tap_x, tap_y = tap_coords[tap_intento % 4]
                        _adb("shell", "input", "tap", str(tap_x), str(tap_y))
                        time.sleep(0.4)
                        
                        # Verificar si se cerró
                        img_check2 = screenshot_adb()
                        if img_check2 is not None and _detectar_pantalla_postcombate(img_check2) != "detalle":
                            console.print(f"[dim green]   [{ciclo}] ✓ DETALLE cerrado tras tap {tap_intento+1}[/]")
                            estado_diag_confirmado = None
                            break
                    else:
                        console.print(f"[dim yellow]   [{ciclo}] ⚠ DETALLE no cerró con taps - esperando diagnóstico[/]")
                    
                    estado_diag_confirmado = None
                    continue
            
            # ══════════════════════════════════════════════════════════════════════════
            #  DETECCIÓN URGENTE: Si vigilancia ve confirmación, DEBEMOS estar en COMBATE
            # ══════════════════════════════════════════════════════════════════════════
            if _hay_confirmacion_detectada() and estado_maquina != "COMBATE":
                console.print(f"[bold yellow]⚠ [{ciclo}] ¡ALERTA! Vigilancia ve confirmación pero máquina no está en COMBATE[/]")
                console.print(f"[bold yellow]         Forzando COMBATE... (diagnóstico falló: {estado_diag_confirmado})[/]")
                estado_maquina = "COMBATE"
                throws_en_combate = 0
                _detener_vigilancia()
                _iniciar_vigilancia(tmpl_confirmacion)
                estado_diag_confirmado = None
                continue
            
            # ══════════════════════════════════════════════════════════════════════════
            #  MÁQUINA DE ESTADOS DINÁMICO - Reacciona a diagnóstico en tiempo real
            # ══════════════════════════════════════════════════════════════════════════
            
            # DIAGNÓSTICO: MAPA
            if estado_diag_confirmado == "MAPA":
                # EXCEPCIÓN: Si estamos en COMBATE y la vigilancia AÚN ve confirmación,
                # ignorar el cambio a MAPA (la vigilancia es más confiable que el diagnóstico)
                if estado_maquina == "COMBATE" and _hay_confirmacion_detectada():
                    if DEBUG:
                        console.print(f"[dim yellow]   [{ciclo}] ⓘ Ignorando cambio a MAPA: vigilancia aún ve confirmación en combate[/]")
                    estado_diag_confirmado = None  # Reset para no procesar
                    continue

                # EXCEPCIÓN: Si ya hicimos el tap y estamos esperando que cargue el combate,
                # NO hacer otro tap — el juego puede tardar 2-4s en transicionar a COMBATE
                if estado_maquina == "ESPERANDO_COMBATE":
                    elapsed = time.time() - _tiempo_tap_sniper
                    if elapsed < _TIMEOUT_ESPERANDO_COMBATE:
                        if DEBUG:
                            console.print(f"[dim cyan]   [{ciclo}] ⏳ Esperando que cargue COMBATE ({elapsed:.1f}s/{_TIMEOUT_ESPERANDO_COMBATE}s)...[/]")
                        estado_diag_confirmado = None
                        time.sleep(1.0)
                        continue
                    else:
                        # Timeout: el tap no funcionó, volver a MAPA para reintentar
                        console.print(f"[yellow]   [{ciclo}] ⚠ Timeout {_TIMEOUT_ESPERANDO_COMBATE}s sin COMBATE → reintentar tap[/]")
                        estado_maquina = "MAPA"
                        # Cae al bloque siguiente que ejecuta _accion_mapa
                
                if estado_maquina != "MAPA":
                    console.print(f"[bold green]🗺 [{ciclo}] Diagnóstico: MAPA[/]")
                    estado_maquina = "MAPA"
                    throws_en_combate = 0
                    _detener_vigilancia()
                
                # EJECUTAR: TAP en primer Pokémon
                nuevo_estado = _accion_mapa(ciclo)
                estado_maquina = nuevo_estado
                if DEBUG and nuevo_estado == "ESPERANDO_COMBATE":
                    console.print(f"[bold cyan]⏳ [{ciclo}] Máquina → ESPERANDO_COMBATE (esperando diagnóstico)[/]")
                estado_diag_confirmado = None  # Reset para nueva confirmación
            
            # DIAGNÓSTICO: COMBATE
            elif estado_diag_confirmado == "COMBATE":
                # Transición: Detectamos COMBATE
                if estado_maquina == "ESPERANDO_COMBATE":
                    console.print(f"[bold yellow]⚔ [{ciclo}] ¡COMBATE DETECTADO![/]")
                    estado_maquina = "COMBATE"
                    throws_en_combate = 0
                    _iniciar_vigilancia(tmpl_confirmacion)
                
                elif estado_maquina == "MAPA":
                    # En MAPA: ignorar combate sorpresa, priorizar _accion_mapa (doble tap en sniper)
                    if DEBUG:
                        console.print(f"[dim yellow]   [{ciclo}] ⓘ Ignorando COMBATE sorpresa, ejecutar doble tap en sniper primero[/]")
                    nuevo_estado = _accion_mapa(ciclo)
                    estado_maquina = nuevo_estado
                    estado_diag_confirmado = None  # Reset para nueva confirmación
                
                elif estado_maquina == "POST-CAPTURA":
                    # POST-CAPTURA → COMBATE (combate automático después de captura)
                    console.print(f"[bold yellow]⚔ [{ciclo}] COMBATE automático post-captura[/]")
                    estado_maquina = "COMBATE"
                    throws_en_combate = 0
                    _detener_vigilancia()  # Detener vigilancia anterior
                    _iniciar_vigilancia(tmpl_confirmacion)
                
                # EJECUTAR: Lanzar pokébola si estamos en COMBATE
                if estado_maquina == "COMBATE":
                    nuevo_estado, nuevo_throws = _accion_combate(ciclo, throws_en_combate, tmpl_confirmacion)
                    estado_maquina = nuevo_estado
                    throws_en_combate = nuevo_throws
                    
                    # Si capturamos, detener vigilancia
                    if nuevo_estado == "POST-CAPTURA":
                        _detener_vigilancia()
                
                estado_diag_confirmado = None  # Reset para nueva confirmación
            
            # DIAGNÓSTICO: POST-CAPTURA
            elif estado_diag_confirmado == "POST-CAPTURA":
                if estado_maquina != "POST-CAPTURA":
                    console.print(f"[bold cyan]🎁 [{ciclo}] POST-CAPTURA detectado[/]")
                    estado_maquina = "POST-CAPTURA"
                    if throws_en_combate > 0:
                        _registrar_acierto_pokebola()
                    _detener_vigilancia()
                
                # EJECUTAR: Cerrar pantalla
                nuevo_estado = _accion_postcaptura(ciclo)
                estado_maquina = nuevo_estado
                throws_en_combate = 0
                estado_diag_confirmado = None  # Reset para nueva confirmación
            
            # DIAGNÓSTICO: CARGANDO
            elif estado_diag_confirmado == "CARGANDO":
                if DEBUG:
                    console.print(f"[dim]   [{ciclo}] Cargando...[/]")
                estado_diag_confirmado = None
            
            # DIAGNÓSTICO: DESCONOCIDO
            elif estado_diag_confirmado == "DESCONOCIDO":
                # Estado desconocido → intentar cerrar pantalla no deseada
                img_check = screenshot_adb()
                if img_check is not None:
                    console.print(f"[bold yellow]⚠ [{ciclo}] Pantalla desconocida detectada → intentando cerrar[/]")
                    _cerrar_pantalla_no_deseada(img_check, ciclo)
                    time.sleep(1.0)
                # Después de cerrar modal, resetear a MAPA
                estado_maquina = "MAPA"
                throws_en_combate = 0
                _detener_vigilancia()
                estado_diag_confirmado = None

    except KeyboardInterrupt:
        console.print(f"\n[bold cyan]👋 Detenido por usuario. Ciclos: {ciclo}[/]")
        
        # Mostrar estadísticas finales (Mejora 5)
        console.print("\n[bold cyan]═══════════════════════════════════════════════════════════[/]")
        console.print("[bold cyan]📊 ESTADÍSTICAS FINALES[/]")
        with _lock_stats:
            console.print(f"  ✅ Pokémon capturados: {_stats.pokemon_capturados}")
            console.print(f"  ❌ Pokémon fallidos: {_stats.pokemon_fallidos}")
            console.print(f"  📈 Tasa de éxito: {_stats.tasa_exito():.1f}%")
            console.print(f"  ⏱️  Tiempo: {_stats.tiempo_transcurrido_min():.1f} minutos")
            console.print(f"  🎯 Pokémon/hora: {_stats.pokemon_por_hora():.1f}")
            console.print(f"  📊 Pokébolas totales: {_stats.pokebolas_totales}")
        console.print(f"[bold cyan]═══════════════════════════════════════════════════════════[/]\n")
        
        # Detener sistemas
        _detener_vigilancia()
        _detener_vigilancia_x()
        _detener_diagnostico()
        _detener_logger_asinc()
        console.print("[dim green]Sistemas detenidos correctamente.[/]")


def calibrar():
    """
    Modo calibración: toma un screenshot del celular, dibuja una cuadrícula
    con coordenadas y guarda 'calibracion_overlay.png' para que puedas
    identificar las posiciones exactas del sniper y la Pokébola.
    También prueba si las templates se detectan correctamente.
    """
    console.print("[bold cyan]--- MODO CALIBRACIÓN ---[/]")
    console.print("Tomando screenshot del celular...")

    img = screenshot_adb()
    if img is None:
        console.print("[red]No se pudo capturar. Verifica la conexión ADB.[/]")
        return

    h, w = img.shape[:2]
    console.print(f"Resolución detectada: [green]{w}x{h}[/]")

    overlay = img.copy()

    # Dibujar cuadrícula cada 100px
    for x in range(0, w, 100):
        cv2.line(overlay, (x, 0), (x, h), (50, 50, 50), 1)
        cv2.putText(overlay, str(x), (x + 2, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    for y in range(0, h, 100):
        cv2.line(overlay, (0, y), (w, y), (50, 50, 50), 1)
        cv2.putText(overlay, str(y), (2, y + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

    # Marcar coordenadas actuales de sniper y bola
    cv2.circle(overlay, (SNIPER_X, SNIPER_Y_TOGGLE), 20, (0, 255, 0), 3)
    cv2.putText(overlay, f"SNIPER toggle ({SNIPER_X},{SNIPER_Y_TOGGLE})",
                (SNIPER_X - 160, SNIPER_Y_TOGGLE - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.circle(overlay, (SNIPER_X, SNIPER_Y_FIRST), 20, (0, 200, 0), 3)
    cv2.putText(overlay, f"SNIPER slot1 toggle-x ({SNIPER_X},{SNIPER_Y_FIRST})",
                (max(0, SNIPER_X - 280), SNIPER_Y_FIRST - 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)
    # Tap real de los slots (SNIPER_SLOT_X)
    cv2.circle(overlay, (SNIPER_SLOT_X, SNIPER_Y_FIRST), 25, (0, 255, 255), 3)
    cv2.putText(overlay, f"TAP slot1 ({SNIPER_SLOT_X},{SNIPER_Y_FIRST})",
                (SNIPER_SLOT_X + 30, SNIPER_Y_FIRST),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    cv2.circle(overlay, (THROW_START_X, THROW_START_Y), 20, (0, 0, 255), 3)
    cv2.putText(overlay, f"BOLA ({THROW_START_X},{THROW_START_Y})",
                (THROW_START_X + 25, THROW_START_Y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.circle(overlay, (THROW_END_X, THROW_END_Y), 15, (255, 0, 0), 3)
    cv2.putText(overlay, f"DESTINO ({THROW_END_X},{THROW_END_Y})",
                (THROW_END_X + 25, THROW_END_Y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "calibracion_overlay.png")
    cv2.imwrite(out_path, overlay)
    console.print(f"[green]✅ Guardado: {out_path}[/]")

    # Probar detección de templates (mismas que usa el loop principal)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    console.print("\n[bold]Prueba de detección de templates:[/]")
    templates_a_probar = [
        ("pokeball_template.jpg",        "En combate (Pokébola)"),
        (_tmpl_name("confirmacion.jpg"), "Captura confirmada"),
        (_tmpl_name("auriola_caza.jpg"), "Auriola de lanzamiento"),
    ]
    for nombre, descripcion in templates_a_probar:
        t = _load_template(_tmpl_name(nombre))
        if t is None:
            continue
        if t.shape[0] > gray.shape[0] or t.shape[1] > gray.shape[1]:
            console.print(f"  [yellow]⚠ {descripcion}: template más grande que la pantalla[/]")
            continue
        res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        color = "green" if max_val >= 0.65 else "yellow" if max_val >= 0.50 else "red"
        console.print(f"  [{color}]{descripcion}: confianza = {max_val:.2f} en {max_loc}[/]")

    console.print("\n[dim]Abre calibracion_overlay.png para verificar las coordenadas.[/]")


def calibrar_mapa():
    """
    Toma un screenshot del MAPA y guarda:
      - calibracion_mapa_full.png   : pantalla completa con cuadrícula cada 50px
      - calibracion_mapa_BJ.png     : zoom ×2 esquina inferior-derecha (radar de pokémon)
      - calibracion_mapa_BS.png     : zoom ×2 esquina inferior-izquierda (avatar/botones)
      - calibracion_mapa_AJ.png     : zoom ×2 esquina superior-derecha
    Abre las imágenes para identificar las coordenadas exactas del radar.
    """
    console.print(Panel(
        "[bold cyan]Calibración del MAPA[/]\n\n"
        "Asegúrate de estar en la pantalla del MAPA\n"
        "(no en combate). El bot tomará un screenshot\n"
        "en 3 segundos...",
        border_style="cyan"))
    time.sleep(3)

    img = screenshot_adb()
    if img is None:
        console.print("[red]No se pudo capturar. Verifica ADB.[/]")
        return

    h, w = img.shape[:2]
    console.print(f"Resolución: [green]{w}x{h}[/]")

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # ── 1. Imagen completa con cuadrícula cada 50px ──────────────────────
    full = img.copy()
    for x in range(0, w, 50):
        color = (80, 80, 80) if x % 200 != 0 else (200, 200, 0)
        cv2.line(full, (x, 0), (x, h), color, 1)
        if x % 100 == 0:
            cv2.putText(full, str(x), (x + 2, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    for y in range(0, h, 50):
        color = (80, 80, 80) if y % 200 != 0 else (200, 200, 0)
        cv2.line(full, (0, y), (w, y), color, 1)
        if y % 100 == 0:
            cv2.putText(full, str(y), (2, y + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    # Marcar SNIPER actual
    cv2.circle(full, (SNIPER_X, SNIPER_Y_TOGGLE), 25, (0, 255, 0), 3)
    cv2.putText(full, f"SNIPER toggle ({SNIPER_X},{SNIPER_Y_TOGGLE})",
                (max(0, SNIPER_X - 160), max(30, SNIPER_Y_TOGGLE - 30)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.circle(full, (SNIPER_X, SNIPER_Y_FIRST), 25, (0, 200, 0), 3)
    cv2.putText(full, f"SNIPER slot1 ({SNIPER_X},{SNIPER_Y_FIRST})",
                (max(0, SNIPER_X - 160), max(30, SNIPER_Y_FIRST - 30)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2)

    path_full = os.path.join(base_dir, "calibracion_mapa_full.png")
    cv2.imwrite(path_full, full)

    # ── 2. Función para guardar un cuadrante ×2 con cuadrícula fina ──────
    def _guardar_cuadrante(nombre: str, x1: int, y1: int, x2: int, y2: int):
        crop = img[y1:y2, x1:x2].copy()
        zoom = cv2.resize(crop, (crop.shape[1] * 2, crop.shape[0] * 2),
                          interpolation=cv2.INTER_NEAREST)
        cw, ch = zoom.shape[1], zoom.shape[0]
        # cuadrícula en coordenadas ORIGINALES del teléfono (cada 50px reales → 100px en zoom)
        for dx in range(0, x2 - x1, 50):
            px = dx * 2
            cv2.line(zoom, (px, 0), (px, ch), (80, 80, 80), 1)
            real_x = x1 + dx
            cv2.putText(zoom, str(real_x), (px + 2, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        for dy in range(0, y2 - y1, 50):
            py = dy * 2
            cv2.line(zoom, (0, py), (cw, py), (80, 80, 80), 1)
            real_y = y1 + dy
            cv2.putText(zoom, str(real_y), (2, py + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        path = os.path.join(base_dir, nombre)
        cv2.imwrite(path, zoom)
        console.print(f"  [green]✅ {nombre}[/] → cubre ({x1},{y1}) a ({x2},{y2}) en el teléfono")

    # Esquina inferior-derecha: radar de pokémon cercanos
    _guardar_cuadrante("calibracion_mapa_BJ.png",
                       w // 2, h * 3 // 4,  w, h)
    # Esquina inferior-izquierda: botones/avatar
    _guardar_cuadrante("calibracion_mapa_BS.png",
                       0,      h * 3 // 4,  w // 2, h)
    # Esquina superior-derecha
    _guardar_cuadrante("calibracion_mapa_AJ.png",
                       w // 2, 0,            w, h // 4)

    console.print(f"""
[bold]Archivos generados:[/]
  [cyan]calibracion_mapa_full.png[/]  — pantalla completa con cuadrícula
  [cyan]calibracion_mapa_BJ.png[/]   — [bold]esquina inferior-DERECHA[/] (aquí está el radar ×2)
  [cyan]calibracion_mapa_BS.png[/]   — esquina inferior-izquierda
  [cyan]calibracion_mapa_AJ.png[/]   — esquina superior-derecha

[bold yellow]Paso siguiente:[/]
  1. Abre [cyan]calibracion_mapa_BJ.png[/] — ahí debería estar el radar de pokémon
  2. Identifica el primer ícono de pokémon y lee sus coordenadas en los ejes
  3. Cambia en el código:
       [green]SNIPER_X = <x que viste>[/]
       [green]SNIPER_Y = <y que viste>[/]
  4. Vuelve a correr [cyan]python pokemon_catcher.py calibrar_mapa[/] para verificar
     que el círculo verde SNIPER queda sobre el ícono correcto
""")


if __name__ == "__main__":
    import sys as _sys
    # Auto-detectar el primer dispositivo conectado si no se especificó serial
    if not DEVICE_SERIAL:
        r = subprocess.run(["adb", "devices"], capture_output=True,
                           text=True, encoding="utf-8")
        for line in r.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                DEVICE_SERIAL = parts[0]
                console.print(f"[dim green]Dispositivo detectado: {DEVICE_SERIAL}[/]")
                break

    if len(_sys.argv) > 1 and _sys.argv[1] == "calibrar":
        calibrar()
    elif len(_sys.argv) > 1 and _sys.argv[1] == "calibrar_mapa":
        calibrar_mapa()
    else:
        main()
