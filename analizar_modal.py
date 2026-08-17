#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 Analizar píxeles en zona del modal para debugging
"""

import subprocess
import sys
import os
import cv2
import numpy as np

def _find_adb():
    import shutil
    adb = shutil.which("adb")
    if adb:
        return adb
    for path in ["/tmp/platform-tools/adb", os.path.expanduser("~/Android/platform-tools/adb"), "/opt/android-sdk/platform-tools/adb"]:
        if os.path.exists(path):
            return path
    return "adb"

def screenshot_adb() -> np.ndarray | None:
    """Captura pantalla vía ADB."""
    adb_cmd = _find_adb()
    cmd = [adb_cmd, "-s", "ZY22FVZQQF", "exec-out", "screencap", "-p"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        if r.returncode != 0 or not r.stdout:
            return None
        arr = np.frombuffer(r.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.COLOR_BGR2GRAY if False else cv2.IMREAD_COLOR)
        return img if img is not None and img.size > 0 else None
    except Exception as e:
        return None

img = screenshot_adb()
if img is None:
    print("❌ No se pudo capturar")
    sys.exit(1)

h, w = img.shape[:2]
print(f"📱 Pantalla: {w}x{h}")

# Analizar zona inferior-derecha (donde está la X)
x_start = int(w * 0.65)
y_start = int(h * 0.75)
zone = img[y_start:, x_start:]

print(f"\n📍 Analizando zona: X={x_start}-{w}, Y={y_start}-{h}")
print(f"   Tamaño zona: {zone.shape}")

# Convertir a HSV
hsv_zone = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)

# Contar píxeles blancos
mask_white = cv2.inRange(hsv_zone, np.array([0, 0, 210]), np.array([180, 40, 255]))
white_pixels = cv2.countNonZero(mask_white)
print(f"\n⚪ Píxeles blancos (S<40, V>210): {white_pixels}")

# Contar píxeles totales en la zona
total_pixels = zone.shape[0] * zone.shape[1]
print(f"   Total píxeles en zona: {total_pixels}")
print(f"   Porcentaje blanco: {white_pixels/total_pixels*100:.1f}%")

# Convertir a escala de grises para análisis adicional
gray_zone = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
blanco_alto = cv2.countNonZero(cv2.inRange(gray_zone, 200, 255))
print(f"\n🤍 Píxeles muy claros (>200): {blanco_alto} ({blanco_alto/total_pixels*100:.1f}%)")

# Analizar TODA la pantalla inferior
menu_zone_full = cv2.cvtColor(img[int(h * 0.30):, :], cv2.COLOR_BGR2GRAY)
blanco_menu_full = cv2.countNonZero(cv2.inRange(menu_zone_full, 200, 255))
print(f"\n📊 Blanco en zona menú (30-100%): {blanco_menu_full} ({blanco_menu_full/(menu_zone_full.size)*100:.1f}%)")

# Estadísticas de color en toda la pantalla
hsv_full = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Verde
mask_g = cv2.inRange(hsv_full, np.array([35, 40, 50]), np.array([95, 255, 255]))
verde = cv2.countNonZero(mask_g)
print(f"🟢 Verde total: {verde/img.size*100:.1f}%")

# Rojo
mask_r1 = cv2.inRange(hsv_full, np.array([0, 80, 80]), np.array([15, 255, 255]))
mask_r2 = cv2.inRange(hsv_full, np.array([165, 80, 80]), np.array([180, 255, 255]))
rojo = cv2.countNonZero(mask_r1 | mask_r2)
print(f"🔴 Rojo total: {rojo/img.size*100:.1f}%")

gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
blanco_full = cv2.countNonZero(cv2.inRange(gray_full, 200, 255))
print(f"⚪ Blanco total: {blanco_full/img.size*100:.1f}%")

print("\n✅ Análisis completo. Usa este info para ajustar thresholds en diagnostico.py")
