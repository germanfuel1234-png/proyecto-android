#!/usr/bin/env python3
"""
Debug: Analizar colores en POST-CAPTURA modal
"""
import cv2
import numpy as np
import subprocess

def screenshot_adb():
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
print(f"📱 Pantalla: {w}x{h}\n")

hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Analizar zona inferior (donde está el botón DE ACUERDO)
zone_inferior = img[int(h * 0.5):, :]
hsv_inferior = cv2.cvtColor(zone_inferior, cv2.COLOR_BGR2HSV)

print("🔍 Buscando contornos VERDES en zona inferior (Y > 50%)\n")

# Probar diferentes rangos
rangos = [
    ("Verde puro", [60, 50, 80], [90, 255, 255]),
    ("Verde-Turquesa", [60, 50, 80], [160, 255, 255]),
    ("Turquesa", [85, 50, 80], [105, 255, 255]),
    ("Verde saturado", [70, 100, 100], [95, 255, 255]),
]

for nombre, lower, upper in rangos:
    mask = cv2.inRange(hsv_inferior, np.array(lower), np.array(upper))
    count = cv2.countNonZero(mask)
    print(f"{nombre:20s} [{lower[0]:3d}-{upper[0]:3d}H, {lower[1]:3d}-{upper[1]:3d}S, {lower[2]:3d}-{upper[2]:3d}V]: {count:6d} píxeles")
    
    if count > 100:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for i, cnt in enumerate(contours[:3]):  # Primeros 3
            area = cv2.contourArea(cnt)
            if area > 500:
                x, y, bw, bh = cv2.boundingRect(cnt)
                print(f"   Contorno {i}: Area={area:.0f} {bw}x{bh} @ Y={int(h*0.5)+y}")

print("\n" + "="*80)
print("MUESTREO DE PÍXELES EN ZONA DEL BOTÓN DE ACUERDO (aprox Y=60%)")
print("="*80)

# Muestrear área donde típicamente está el botón
sample_y = int(h * 0.60)
sample_x_start = int(w * 0.35)
sample_x_end = int(w * 0.65)

print(f"Zona de muestreo: X[{sample_x_start}:{sample_x_end}] Y={sample_y}\n")

for x in range(sample_x_start, sample_x_end, 50):
    bgr = img[sample_y, x]
    hsv_val = hsv[sample_y, x]
    print(f"X={x:4d}: BGR={bgr} → HSV=[{hsv_val[0]:3d}, {hsv_val[1]:3d}, {hsv_val[2]:3d}]")
