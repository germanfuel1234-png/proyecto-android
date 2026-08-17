#!/usr/bin/env python3
"""Verificar píxeles blancos alrededor de (957, 2070)"""
import subprocess, sys, os, cv2, numpy as np

def _find_adb():
    import shutil
    adb = shutil.which("adb")
    if adb:
        return adb
    for path in ["/tmp/platform-tools/adb", os.path.expanduser("~/Android/platform-tools/adb"), "/opt/android-sdk/platform-tools/adb"]:
        if os.path.exists(path):
            return path
    return "adb"

def screenshot_adb():
    adb_cmd = _find_adb()
    cmd = [adb_cmd, "-s", "ZY22FVZQQF", "exec-out", "screencap", "-p"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        if r.returncode != 0 or not r.stdout:
            return None
        arr = np.frombuffer(r.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img if img is not None and img.size > 0 else None
    except:
        return None

img = screenshot_adb()
if img is None:
    print("❌ No se pudo capturar")
    sys.exit(1)

h, w = img.shape[:2]
print(f"📱 Pantalla: {w}x{h}")
print(f"   Verificando píxeles en (957, 2070)\n")

# Zoom 50px alrededor
margin = 50
zone = img[2070-margin:2070+margin, 957-margin:957+margin]
print(f"📍 Zona: [{2070-margin}:{2070+margin}, {957-margin}:{957+margin}] = {zone.shape}\n")

# Colores en el centro (957, 2070)
pixel = img[2070, 957]
print(f"Pixel en (957, 2070): BGR={pixel}")

# Convertir a HSV
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
pixel_hsv = hsv[2070, 957]
print(f"                    HSV={pixel_hsv}")

# Detectar blancos en esa zona
hsv_zone = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
mask_white = cv2.inRange(hsv_zone, np.array([0, 0, 210]), np.array([180, 40, 255]))

white_count = cv2.countNonZero(mask_white)
print(f"\n⚪ Píxeles blancos en zona 100x100: {white_count}")

if white_count > 0:
    print(f"✅ SÍ hay píxeles blancos")
    # Mostrar distribución
    print(f"   Distribución:")
    for y in range(0, 100, 20):
        count = cv2.countNonZero(mask_white[y:y+20, :])
        print(f"   Y[{2070-50+y}:{2070-50+y+20}]: {count} píxeles blancos")
else:
    print(f"❌ NO hay píxeles blancos")
    print(f"   Esto significa que (957, 2070) NO es una X blanca real")
    
    # Analizar qué color hay
    gray_zone = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
    print(f"\n   Valores de gris en zona:")
    print(f"   Rango: {gray_zone.min()}-{gray_zone.max()}")
    print(f"   Media: {gray_zone.mean():.0f}")
    
    # Detectar colores cian/turquesa (para X de Pokémon)
    mask_cyan = cv2.inRange(hsv_zone, np.array([80, 50, 100]), np.array([100, 255, 255]))
    cyan_count = cv2.countNonZero(mask_cyan)
    print(f"\n   Píxeles cian/turquesa: {cyan_count}")
    if cyan_count > 50:
        print(f"   ⚠️  Hay píxeles CIAN - podría ser X de detalle de Pokémon")
