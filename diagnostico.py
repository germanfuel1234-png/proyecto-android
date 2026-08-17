#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 Diagnóstico de Pantalla v2 — MEJORADO CON TEMPLATES + OCR
================================================================

Uso: python diagnostico.py

Detecta:
  - ✅ MAPA (vista normal)
  - ⚔️  COMBATE (con Pokémon)
  - 🎁 POST-CAPTURA (con checkmark)
  - ⚠️  MODAL (inventario, opciones, etc)
  - 🔵 POKÉSTOP
  - 🏋️  GIMNASIO
  - 📱 PANTALLA CARGA
  - Y más...
"""

import subprocess
import sys
import os
import time
import glob

# Importar las funciones necesarias desde pokemon_catcher
sys.path.insert(0, os.path.dirname(__file__))

import cv2
import numpy as np
from rich.console import Console
from rich.panel import Panel

# Intenta usar pytesseract para OCR, pero no falla si no está
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

console = Console()

# =============== TEMPLATES PRECARGADOS ===============
_TEMPLATES_CACHE = {}

def _cargar_templates():
    """Precarga todos los templates disponibles."""
    global _TEMPLATES_CACHE
    
    templates_dir = os.path.join(os.path.dirname(__file__), "pokmoengobot")
    
    templates_a_buscar = [
        "camara.jpg", "camara_1080.jpg",
        "confirmacion.jpg", "confirmacion_1080.jpg",
        "pokemon_enelmapa.jpg", "pokemon_enelmapa2.jpg",
        "pokeball_template.jpg",
        "sniper_panel.jpg",
        "bola_region.jpg",
    ]
    
    for template_name in templates_a_buscar:
        ruta = os.path.join(templates_dir, template_name)
        if os.path.exists(ruta):
            try:
                img = cv2.imread(ruta, cv2.IMREAD_COLOR)
                if img is not None:
                    # Redimensionar a múltiples escalas para robustez
                    _TEMPLATES_CACHE[template_name] = {
                        'original': img,
                        'escalas': [
                            cv2.resize(img, (int(img.shape[1] * 0.8), int(img.shape[0] * 0.8))),
                            cv2.resize(img, (int(img.shape[1] * 1.2), int(img.shape[0] * 1.2))),
                        ]
                    }
            except Exception as e:
                pass

_cargar_templates()

# ─── Templates de combate y post-captura en raíz del proyecto ───────────────
_TMPL_COMBATE_BAYA:    np.ndarray | None = None
_TMPL_COMBATE_CAMARA:  np.ndarray | None = None
_TMPL_POST_DEACUERDO:  np.ndarray | None = None
_TMPL_POST_TOTAL:      np.ndarray | None = None

def _cargar_templates_combate():
    """Carga templates de combate y post-captura desde la raíz del proyecto."""
    global _TMPL_COMBATE_BAYA, _TMPL_COMBATE_CAMARA, _TMPL_POST_DEACUERDO, _TMPL_POST_TOTAL
    base = os.path.dirname(__file__)
    pares = [
        ("baya_poke.png",         "_TMPL_COMBATE_BAYA"),
        ("camara_fotos_poke.png", "_TMPL_COMBATE_CAMARA"),
        ("De_acuerdo_poke.png",   "_TMPL_POST_DEACUERDO"),
        ("Total_poke.png",        "_TMPL_POST_TOTAL"),
    ]
    for nombre, var in pares:
        ruta = os.path.join(base, nombre)
        if os.path.exists(ruta):
            img = cv2.imread(ruta, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                globals()[var] = img

_cargar_templates_combate()


def _detectar_combate_por_templates(img: np.ndarray) -> bool:
    """
    Devuelve True si se detectan la baya o la cámara de la pantalla de combate.
    Threshold bajo (0.55) para tolerar diferencias de escala/iluminación.
    """
    if img is None:
        return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    for tmpl in (_TMPL_COMBATE_BAYA, _TMPL_COMBATE_CAMARA):
        if tmpl is None:
            continue
        if tmpl.shape[0] > h or tmpl.shape[1] > w:
            continue
        try:
            res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= 0.55:
                return True
        except Exception:
            pass
    return False


def _detectar_postcaptura_por_templates(img: np.ndarray) -> tuple[bool, int, int]:
    """
    Devuelve (encontrado, cx, cy) si se detectan De_acuerdo_poke o Total_poke.
    cx, cy = centro del botón DE ACUERDO para hacer tap directo.
    Solo busca en la mitad inferior de la pantalla (Y > 50%) para evitar
    falsos positivos con botones del menú principal.
    """
    if img is None:
        return False, None, None
    h, w = img.shape[:2]

    # Recortar a la mitad inferior — el botón DE ACUERDO/TOTAL está siempre
    # por debajo del 50% de la pantalla (~Y>1200 en 2400px)
    mitad_inferior = img[h // 2:, :]
    gray = cv2.cvtColor(mitad_inferior, cv2.COLOR_BGR2GRAY)
    roi_h, roi_w = gray.shape[:2]

    # Primero buscar DE ACUERDO (tiene coordenadas de click directas)
    if _TMPL_POST_DEACUERDO is not None:
        th, tw = _TMPL_POST_DEACUERDO.shape[:2]
        if th <= roi_h and tw <= roi_w:
            try:
                res = cv2.matchTemplate(gray, _TMPL_POST_DEACUERDO, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= 0.55:
                    cx = max_loc[0] + tw // 2
                    cy = max_loc[1] + th // 2 + h // 2  # offset por recorte
                    return True, cx, cy
            except Exception:
                pass

    # Luego buscar TOTAL (indica card XP → botón DE ACUERDO está debajo)
    if _TMPL_POST_TOTAL is not None:
        th, tw = _TMPL_POST_TOTAL.shape[:2]
        if th <= roi_h and tw <= roi_w:
            try:
                res = cv2.matchTemplate(gray, _TMPL_POST_TOTAL, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= 0.55:
                    cx = max_loc[0] + tw // 2
                    cy = max_loc[1] + th + 180 + h // 2  # offset por recorte
                    cy = min(cy, h - 50)
                    return True, cx, cy
            except Exception:
                pass

    return False, None, None

# =============== FUNCIONES AUXILIARES ===============

def _find_adb():
    import shutil
    adb = shutil.which("adb")
    if adb:
        return adb
    for path in [
        "/tmp/platform-tools/adb",
        os.path.expanduser("~/Android/platform-tools/adb"),
        "/opt/android-sdk/platform-tools/adb",
    ]:
        if os.path.exists(path):
            return path
    return "adb"

def _adb(*args, timeout: int = 15):
    """Ejecuta ADB."""
    cmd = [_find_adb(), "-s", "ZY22FVZQQF"] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except:
        return False, "ADB error"

def screenshot_adb() -> np.ndarray | None:
    """Captura pantalla vía ADB."""
    adb_cmd = _find_adb()
    cmd = [adb_cmd, "-s", "ZY22FVZQQF", "exec-out", "screencap", "-p"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        if r.returncode != 0 or not r.stdout:
            return None
        arr = np.frombuffer(r.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img if img is not None and img.size > 0 else None
    except Exception as e:
        return None

# =============== TEMPLATE MATCHING ===============

def _hacer_template_matching(img: np.ndarray) -> tuple[str, float]:
    """
    Intenta encontrar templates en la imagen.
    Retorna: (nombre_template, confianza 0-1)
    """
    if img is None or not _TEMPLATES_CACHE:
        return "", 0.0
    
    h, w = img.shape[:2]
    mejor_match = ("", 0.0)
    
    for template_name, template_data in _TEMPLATES_CACHE.items():
        # Intenta original + escalas
        for scale_idx, template in enumerate([template_data['original']] + template_data['escalas']):
            if template.shape[0] > h or template.shape[1] > w:
                continue
            
            try:
                result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                if max_val > mejor_match[1]:
                    mejor_match = (template_name, max_val)
                    
                    # Si encontramos match > 0.70, retornamos inmediatamente
                    if max_val > 0.70:
                        return mejor_match
            except Exception as e:
                pass
    
    # Solo retornar si confianza > 0.50
    if mejor_match[1] > 0.50:
        return mejor_match
    
    return "", 0.0

# =============== OCR / DETECCIÓN DE TEXTO ===============

def _detectar_texto_en_zona(img: np.ndarray, zona: tuple = None) -> list[str]:
    """
    Detecta texto en la imagen usando Tesseract.
    Retorna lista de palabras detectadas.
    """
    if not PYTESSERACT_AVAILABLE or img is None:
        return []
    
    try:
        # Extraer zona si se especifica
        if zona:
            x1, y1, x2, y2 = zona
            roi = img[y1:y2, x1:x2]
        else:
            roi = img
        
        # Preprocesamiento para mejor OCR
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 150, 255, cv2.MORPH_CLOSE)
        
        # OCR con configuración para UI
        custom_config = r'--psm 6'  # Sparse text
        text = pytesseract.image_to_string(binary, config=custom_config, lang='eng')
        
        # Extraer palabras clave
        palabras = text.lower().split()
        return palabras
    except Exception as e:
        return []

def _detectar_texto_pantalla(img: np.ndarray) -> list[str]:
    """
    Detecta texto importante en zonas estratégicas de la pantalla.
    """
    if img is None:
        return []
    
    h, w = img.shape[:2]
    todas_palabras = []
    
    # Zona superior (nombres de lugares, títulos)
    palabras_top = _detectar_texto_en_zona(img, (0, 0, w, int(h * 0.15)))
    todas_palabras.extend(palabras_top)
    
    # Zona inferior (botones)
    palabras_bottom = _detectar_texto_en_zona(img, (0, int(h * 0.85), w, h))
    todas_palabras.extend(palabras_bottom)
    
    # Zona centro
    palabras_center = _detectar_texto_en_zona(img, (0, int(h * 0.3), w, int(h * 0.7)))
    todas_palabras.extend(palabras_center)
    
    return todas_palabras

# =============== DETECCIÓN MEJORADA DE PANTALLAS ===============

def detectar_boton_x(img: np.ndarray) -> tuple[bool, int, int]:
    """
    Detecta el botón X para cerrar menús/modales.
    SOLO en zona inferior derecha (X > 85%, Y > 75%).
    MUY RESTRICTIVO para evitar falsos positivos.
    Devuelve: (encontrado, x, y)
    """
    if img is None:
        return False, 0, 0
    
    h, w = img.shape[:2]
    
    try:
        # BÚSQUEDA LOCALIZADA: zona inferior derecha
        # Pero MÁS RESTRICTIVA: X > 90%, Y > 80% (esquina real)
        x_start = int(w * 0.90)  # 10% derecha solamente
        y_start = int(h * 0.80)  # 20% inferior solamente
        zone = img[y_start:, x_start:]
        
        if zone.size == 0:
            return False, 0, 0
        
        hsv = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
        
        # BLANCO PURO (muy restrictivo)
        mask_white = cv2.inRange(hsv, np.array([0, 0, 220]), np.array([180, 30, 255]))
        
        # Debe haber suficiente blanco
        blanco_count = cv2.countNonZero(mask_white)
        if blanco_count < 200:  # Aumentado de 50 a 200 (mucho más restrictivo)
            return False, 0, 0
        
        # Limpiar ruido
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))  # Kernel más grande
        mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE, kernel)
        mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_OPEN, kernel)
        
        # Encontrar contornos
        contours, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return False, 0, 0
        
        # Filtrar candidatos AGRESIVAMENTE
        candidates = []
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            
            # Área ESTRICTA: X debe ser ~40x40 a ~80x80 píxeles
            # (800-6400 píxeles cuadrados)
            if area < 800 or area > 6400:
                continue
            
            x, y, bw, bh = cv2.boundingRect(cnt)
            
            # Debe ser CUADRADO (0.85-1.15, muy estricto)
            aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
            if aspect < 0.85 or aspect > 1.15:
                continue
            
            # Debe estar en esquina (coordenadas muy restrictivas)
            cx = x + bw // 2
            cy = y + bh // 2
            
            # Solo en esquina REAL (último 10% derecha, último 20% abajo)
            if cx < zone.shape[1] * 0.5 or cy < zone.shape[0] * 0.3:
                continue
            
            # Calcular centro global
            cx_global = cx + x_start
            cy_global = cy + y_start
            
            candidates.append((area, cx_global, cy_global))
        
        if not candidates:
            return False, 0, 0
        
        # Tomar el MEJOR CANDIDATO
        candidates.sort(reverse=True)
        _, cx, cy = candidates[0]
        
        return True, cx, cy
        
    except Exception as e:
        return False, 0, 0

def detectar_modal_abierto(img: np.ndarray) -> bool:
    """Detecta si hay un modal abierto (por presencia de botón X)."""
    if img is None:
        return False
    try:
        hay_x, _, _ = detectar_boton_x(img)
        return hay_x
    except Exception as e:
        return False

def _detectar_pokebola_region_central(img: np.ndarray) -> tuple[bool, int, int]:
    """
    🟴 Detecta POKÉBOLA ROJA en REGIÓN CENTRAL (20%-70% altura)
    Si hay pokébola en el medio de la pantalla (NO en zona de throw abajo)
    → DEFINITIVAMENTE es MAPA

    ⚠️ No se ejecuta si hay modal blanco abierto (pantalla de detalle/XP)
    porque el ícono de pokébola en la tarjeta "Atrapado" da falsos positivos.

    Retorna: (encontrada: bool, coord_x, coord_y)
    """
    if img is None:
        return False, None, None
    
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, w = img.shape[:2]

        # Salir inmediatamente si hay modal blanco (>25%) — pantalla detalle/XP abierta
        mask_blanco_chk = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
        pct_blanco_chk = cv2.countNonZero(mask_blanco_chk) / (w * h)
        if pct_blanco_chk > 0.25:
            return False, None, None
        
        # Región central: excluir zona de throw (últimos 30% abajo)
        region_inicio = int(h * 0.20)  # 20% desde arriba
        region_fin = int(h * 0.70)     # 70% = excluye zona de throw
        
        # Máscaras de rojo PURO (pokébola)
        # H: 0-10 o 160-180, S: 150+ (intenso), V: 80-255
        mask_r1 = cv2.inRange(hsv[region_inicio:region_fin, :], 
                              np.array([0, 150, 80]), np.array([10, 255, 255]))
        mask_r2 = cv2.inRange(hsv[region_inicio:region_fin, :], 
                              np.array([170, 150, 80]), np.array([180, 255, 255]))
        mask_rojo = cv2.bitwise_or(mask_r1, mask_r2)
        
        # Encontrar contornos
        contours, _ = cv2.findContours(mask_rojo, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # Buscar contorno más grande
            contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(contour)
            
            # Pokébola debe ser visible pero no demasiado grande
            if 500 < area < 50000:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"]) + region_inicio  # Offset de región
                    return True, cx, cy
    except Exception as e:
        pass
    
    return False, None, None

def _detectar_avatar(img: np.ndarray) -> tuple[bool, int, int]:
    """
    👤 Detecta AVATAR del usuario en esquina superior izquierda
    Si existe `pokmoengobot/exclusion_templates/avatar.png`
    → DEFINITIVAMENTE es MAPA
    
    Retorna: (encontrado: bool, coord_x, coord_y)
    """
    if img is None:
        return False, None, None
    
    # Intentar cargar avatar template
    avatar_path = os.path.join(os.path.dirname(__file__), 
                               "pokmoengobot", "exclusion_templates", "avatar.png")
    
    if not os.path.exists(avatar_path):
        return False, None, None
    
    try:
        avatar_template = cv2.imread(avatar_path, cv2.IMREAD_COLOR)
        if avatar_template is None:
            return False, None, None
        
        h, w = img.shape[:2]
        th, tw = avatar_template.shape[:2]
        
        # Limitar búsqueda a esquina superior izquierda (primeros 15% ancho, primeros 20% alto)
        region = img[:int(h * 0.20), :int(w * 0.15)]
        
        # Template matching en la región
        result = cv2.matchTemplate(region, avatar_template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        # Si confianza > 0.75 (bastante seguro)
        if max_val > 0.75:
            # Coordenadas globales del avatar
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return True, cx, cy
    except Exception as e:
        pass
    
    return False, None, None

def mostrar_diagnostico():
    """
    🎯 DIAGNÓSTICO PROFESIONAL v4 - RETORNA COORDENADAS DE CLICK
    ═════════════════════════════════════════════════════════════
    
    Retorna: (estado, detalles, coord_x, coord_y)
    - estado: ✅ MAPA | ⚔️ COMBATE | 🎁 POST-CAPTURA | etc
    - detalles: Información adicional
    - coord_x, coord_y: Coordenadas donde hacer click
    
    PRIORIDAD:
    1. COLORES (definitivos)
    2. TEMPLATES (fallback)
    3. FALLBACK SUAVE
    """
    img = screenshot_adb()
    if img is None:
        return None, "❌ Error: No se pudo capturar pantalla", None, None
    
    h, w = img.shape[:2]
    total_pixeles = w * h
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # ═══════════════════════════════════════════════════════════
    # ANÁLISIS DE COLORES (PRIORITARIO)
    # ═══════════════════════════════════════════════════════════
    # Máscaras más restrictivas: solo rojo PURO (S >= 150)
    # Evita capturar sombras o colores intermedios en POST-CAPTURA
    mask_r1 = cv2.inRange(hsv, np.array([0,   150, 80]),   np.array([10,  255, 255]))
    mask_r2 = cv2.inRange(hsv, np.array([170, 150, 80]),   np.array([180, 255, 255]))
    rojo_total = cv2.countNonZero(mask_r1 | mask_r2)
    pct_rojo = rojo_total / total_pixeles
    
    mask_verde = cv2.inRange(hsv, np.array([35, 40, 50]), np.array([95, 255, 255]))
    verde_total = cv2.countNonZero(mask_verde)
    pct_verde = verde_total / total_pixeles
    
    mask_blanco = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
    blanco_total = cv2.countNonZero(mask_blanco)
    pct_blanco = blanco_total / total_pixeles
    
    # ═══════════════════════════════════════════════════════════
    # 🎯 PRIORIDAD 0: ¿HAY MODAL ABIERTO? (DETECTAR X)
    # ═══════════════════════════════════════════════════════════
    # Si detectamos X en esquina superior derecha → hay modal abierto
    # → NO es MAPA, es modal (POST-CAPTURA, inventario, etc)
    hay_modal, modal_x, modal_y = detectar_boton_x(img)
    
    # Si hay modal + mucho blanco → POST-CAPTURA
    if hay_modal and pct_blanco > 0.30:
        coord_x, coord_y = _detectar_checkmark_coords(img)
        if coord_x is None:
            coord_x, coord_y = 547, 2142
        return "🎁 POST-CAPTURA", f"modal abierto {pct_blanco:.1%}", coord_x, coord_y
    
    # Si hay modal pero no mucho blanco → otro modal (inventario, opciones, etc)
    # En ese caso, mejor fallback a DESCONOCIDO que confundir con MAPA
    if hay_modal:
        return "❓ MODAL DESCONOCIDO", f"modal detectado", None, None
    
    # ═══════════════════════════════════════════════════════════
    # 🎯 PRIORIDAD 1: POKÉBOLA EN REGIÓN CENTRAL = MAPA
    # ═══════════════════════════════════════════════════════════
    # Si NO hay modal Y hay pokébola ROJA en el medio
    # → DEFINITIVAMENTE es MAPA (usuario ve la bola)
    pokebola_encontrada, pb_x, pb_y = _detectar_pokebola_region_central(img)
    if pokebola_encontrada:
        return "✅ MAPA", f"pokébola región central", pb_x, pb_y
    
    # ═══════════════════════════════════════════════════════════
    # 🎯 PRIORIDAD 2: AVATAR DEL USUARIO = MAPA
    # ═══════════════════════════════════════════════════════════
    # Si NO hay modal Y se detecta el avatar en esquina superior
    # → DEFINITIVAMENTE es MAPA
    avatar_encontrado, av_x, av_y = _detectar_avatar(img)
    if avatar_encontrado:
        return "✅ MAPA", f"avatar detectado", av_x, av_y
    
    # ═══════════════════════════════════════════════════════════
    # 1️⃣ POST-CAPTURA (BLANCO > 30%, sin modal detectado)
    # ═══════════════════════════════════════════════════════════
    # Fallback si hay blanco pero X no detectó modal
    if pct_blanco > 0.30 and pct_rojo < 0.010:
        coord_x, coord_y = _detectar_checkmark_coords(img)
        if coord_x is None:
            coord_x, coord_y = 547, 2142
        return "🎁 POST-CAPTURA", f"modal {pct_blanco:.1%}", coord_x, coord_y
    
    # ═══════════════════════════════════════════════════════════    # 🎯 PRIORIDAD ALTA: TEMPLATES DE POST-CAPTURA (DE ACUERDO + TOTAL)
    # ═══════════════════════════════════════════════════════════════════════════════
    # Si se detecta el botón DE ACUERDO o el texto TOTAL → definitivamente POST-CAPTURA
    post_tmpl, pt_x, pt_y = _detectar_postcaptura_por_templates(img)
    if post_tmpl:
        return "🎁 POST-CAPTURA", "template DE ACUERDO/TOTAL", pt_x, pt_y
    # 🎯 PRIORIDAD ALTA: TEMPLATES DE COMBATE (baya + cámara)
    # ═══════════════════════════════════════════════════════════
    # Si se detecta la baya frambuesa O la cámara → definitivamente COMBATE
    # Esto evita que el verde del fondo del juego confunda con MAPA
    if _detectar_combate_por_templates(img):
        return "⚔️  COMBATE", "template baya/cámara", 546, 1420

    # ═══════════════════════════════════════════════════════════
    # 2️⃣ MAPA (VERDE > 15%) - PRIORIDAD SOBRE ROJO BAJO
    # ═══════════════════════════════════════════════════════════
    # Si hay mucho verde, es MAPA incluso si hay pokémon rojo visible
    if pct_verde > 0.15:
        # Buscar pokémon (rojo/naranja oscuro en la pantalla)
        coord_x, coord_y = _detectar_pokemon_coords(img)
        if coord_x is None:
            # Fallback: centro de la pantalla superior
            coord_x, coord_y = w // 2, h // 3
        return "✅ MAPA", f"verde={pct_verde:.1%}", coord_x, coord_y
    
    # ═══════════════════════════════════════════════════════════
    # 3️⃣ COMBATE (ROJO > 2.5% Y NO ES MAPA)
    # ═══════════════════════════════════════════════════════════
    # Threshold aumentado a 0.025 (2.5%) = pokébola centrada en COMBATE real
    # Con S >= 150, solo rojo PURO es detectado (evita falsos positivos)
    if pct_rojo > 0.025 and pct_blanco < 0.30 and pct_verde < 0.15:
        # Pokébola está en el centro inferior - confirmado rojo puro
        coord_x, coord_y = 546, 1420  # Centro de pokébola
        return "⚔️  COMBATE", f"rojo={pct_rojo:.1%}", coord_x, coord_y
    
    # ═══════════════════════════════════════════════════════════
    # TEMPLATE MATCHING (FALLBACK)
    # ═══════════════════════════════════════════════════════════
    template_match, confianza_template = _hacer_template_matching(img)
    if confianza_template > 0.70:
        if "pokemon" in template_match.lower() and "mapa" in template_match.lower():
            coord_x, coord_y = _detectar_pokemon_coords(img)
            if coord_x is None:
                coord_x, coord_y = w // 2, h // 3
            return "✅ MAPA", f"pokemon {confianza_template:.0%}", coord_x, coord_y
        
        elif "confirmacion" in template_match.lower():
            coord_x, coord_y = _detectar_checkmark_coords(img)
            if coord_x is None:
                coord_x, coord_y = 547, 2142
            return "🎁 POST-CAPTURA", f"confirmación {confianza_template:.0%}", coord_x, coord_y
        
        elif "camara" in template_match.lower():
            coord_x, coord_y = 546, 1420
            return "⚔️  COMBATE", f"cámara {confianza_template:.0%}", coord_x, coord_y
    
    # ═══════════════════════════════════════════════════════════
    # FALLBACK SUAVE
    # ═══════════════════════════════════════════════════════════
    if pct_verde > 0.10:
        coord_x, coord_y = _detectar_pokemon_coords(img)
        if coord_x is None:
            coord_x, coord_y = w // 2, h // 3
        return "✅ MAPA", f"verde={pct_verde:.1%} (probable)", coord_x, coord_y
    
    # ═══════════════════════════════════════════════════════════
    # DESCONOCIDO
    # ═══════════════════════════════════════════════════════════
    return "❓ DESCONOCIDO", f"R={pct_rojo:.2%} V={pct_verde:.2%} B={pct_blanco:.2%}", None, None


def _detectar_pokemon_coords(img: np.ndarray) -> tuple[int, int]:
    """
    Detecta pokémon en pantalla MAPA y retorna sus coordenadas.
    Busca puntos rojos/naranjas que típicamente son pokémon.
    """
    if img is None:
        return None, None
    
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Buscar rojo/naranja (pokémon)
        # H: 0-10 o 160-180 (rojo), S: 50-255, V: 100-255
        mask1 = cv2.inRange(hsv, np.array([0, 50, 100]), np.array([10, 255, 255]))
        mask2 = cv2.inRange(hsv, np.array([160, 50, 100]), np.array([180, 255, 255]))
        mask = cv2.bitwise_or(mask1, mask2)
        
        # Encontrar contornos
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # Buscar el contorno más grande (pokémon principal)
            contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(contour)
            
            # Verificar que sea un tamaño razonable (100-10000 px²)
            if 100 < area < 10000:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    return cx, cy
    except:
        pass
    
    return None, None


def _detectar_checkmark_coords(img: np.ndarray) -> tuple[int, int]:
    """
    Detecta el botón checkmark teal (✓) en la barra inferior de la pantalla de detalle.
    Busca círculos teal en el último 15% de pantalla (donde están los botones ✓ y ≡).
    """
    if img is None:
        return None, None

    try:
        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Buscar teal SOLO en la barra inferior (último 15%)
        # El checkmark ✓ y el botón ≡ son los dos círculos teal de abajo
        zona_baja = hsv[int(h * 0.85):, :]
        mask_teal = cv2.inRange(zona_baja,
                                np.array([82, 80, 100]),
                                np.array([105, 255, 255]))

        contours, _ = cv2.findContours(mask_teal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            # El checkmark (✓) está a la izquierda del ≡ → el de X menor
            centros = []
            for c in contours:
                area = cv2.contourArea(c)
                if area < 500:
                    continue
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"]) + int(h * 0.85)
                    centros.append((cx, cy))

            if centros:
                # Ordenar por X: el checkmark es el de menor X (izquierda)
                centros.sort(key=lambda p: p[0])
                return centros[0]  # checkmark ✓

    except:
        pass

    return None, None

def monitor_continuo():
    """Monitor en tiempo real que se actualiza cada 1 segundo y muestra coordenadas."""
    console.print(Panel(
        "[bold cyan]🔍 MONITOR DE DIAGNÓSTICO EN VIVO (CON COORDENADAS)[/]\n"
        "[dim]Se actualiza cada 1 segundo (Ctrl+C para salir)[/]",
        border_style="cyan"))
    console.print()
    
    try:
        ciclo = 0
        while True:
            ciclo += 1
            estado, detalles, coord_x, coord_y = mostrar_diagnostico()
            
            if estado is None:
                console.print(f"[dim][{ciclo:04d}] {detalles}[/]")
            else:
                coords_str = f"({coord_x},{coord_y})" if coord_x is not None else "sin coords"
                console.print(f"[dim][{ciclo:04d}][/] {estado}  {detalles} {coords_str}")
            
            time.sleep(1.0)
    except KeyboardInterrupt:
        console.print("\n[dim]Monitor detenido.[/]")

if __name__ == "__main__":
    monitor_continuo()
