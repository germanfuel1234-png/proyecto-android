#!/usr/bin/env python3
"""
Debug: Analizar qué hay en la esquina inferior derecha (donde debería estar la X)
"""
import cv2
import numpy as np
import subprocess

def screenshot_adb():
    """Captura pantalla via ADB"""
    try:
        result = subprocess.run(
            ['adb', 'exec-out', 'screencap', '-p'],
            capture_output=True,
            timeout=5
        )
        nparr = np.frombuffer(result.stdout, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except:
        return None

img = screenshot_adb()
if img is None:
    print("❌ No se pudo capturar pantalla")
    exit(1)

h, w = img.shape[:2]
print(f"📱 Pantalla: {w}x{h}")

# Analizar esquina inferior derecha (90%-100% X, 88%-100% Y)
x_start = int(w * 0.90)
y_start = int(h * 0.88)
zone = img[y_start:, x_start:]

print(f"\n📍 ESQUINA INFERIOR DERECHA ({x_start}:{w}, {y_start}:{h})")
print(f"   Zona: {zone.shape}")

hsv = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)

# Detectar píxeles blancos
mask_white = cv2.inRange(hsv, np.array([0, 0, 210]), np.array([180, 40, 255]))
white_count = cv2.countNonZero(mask_white)
print(f"\n⚪ Píxeles blancos: {white_count}")

if white_count > 0:
    # Mostrar distribución de blancos
    for y in range(0, mask_white.shape[0], 20):
        row_count = cv2.countNonZero(mask_white[y:y+20, :])
        print(f"   Y[{y_start+y}:{y_start+y+20}]: {row_count} píxeles")
    
    # Encontrar contornos
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    print(f"\n🔍 Contornos encontrados: {len(contours)}")
    
    valid_contours = []
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
        
        cx = x + bw // 2 + x_start
        cy = y + bh // 2 + y_start
        
        print(f"   [{i}] Área={area:.0f} AR={aspect:.2f} @({cx}, {cy}) Tamaño={bw}x{bh}")
        
        # Verificar si cumple criterios
        if area >= 200 and area <= 600:
            if aspect >= 0.9 and aspect <= 1.1:
                valid_contours.append((area, cx, cy))
                print(f"        ✅ VÁLIDO")
            else:
                print(f"        ❌ AR fuera de rango (0.9-1.1)")
        else:
            print(f"        ❌ Área fuera de rango (200-600)")
    
    if valid_contours:
        valid_contours.sort(reverse=True)
        area, cx, cy = valid_contours[0]
        print(f"\n✨ MEJOR CANDIDATO: ({cx}, {cy})")
    else:
        print(f"\n⚠️  No hay contornos válidos")
else:
    print("\n❌ NO hay píxeles blancos en esquina inferior derecha")
    print("\n   Buscando píxeles blancos en toda la pantalla...")
    mask_white_full = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV), 
                                  np.array([0, 0, 210]), 
                                  np.array([180, 40, 255]))
    full_count = cv2.countNonZero(mask_white_full)
    print(f"   Píxeles blancos totales: {full_count}")
    
    # Mostrar dónde están
    coords = np.where(mask_white_full > 0)
    if len(coords[0]) > 0:
        min_y, max_y = coords[0].min(), coords[0].max()
        min_x, max_x = coords[1].min(), coords[1].max()
        print(f"   Rango: X[{min_x}:{max_x}] Y[{min_y}:{max_y}]")
        print(f"   Centro aproximado: ({(min_x+max_x)//2}, {(min_y+max_y)//2})")
