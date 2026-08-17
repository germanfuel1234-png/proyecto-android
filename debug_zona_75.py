#!/usr/bin/env python3
"""
Debug: Ver qué contornos se detectan en la zona Y>75%
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
print(f"📱 Pantalla: {w}x{h}")

# Búsqueda en zona Y>75%, X>85%
x_start = int(w * 0.85)
y_start = int(h * 0.75)
zone = img[y_start:, x_start:]

print(f"🔍 Zona [{x_start}:{w}, {y_start}:{h}]\n")

hsv = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
mask_white = cv2.inRange(hsv, np.array([0, 0, 210]), np.array([180, 40, 255]))

print(f"Píxeles blancos en zona: {cv2.countNonZero(mask_white)}")

kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE, kernel)

contours, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

print(f"Contornos encontrados: {len(contours)}\n")

candidates = []
for i, cnt in enumerate(contours):
    area = cv2.contourArea(cnt)
    if area < 100:
        continue
    
    x, y, bw, bh = cv2.boundingRect(cnt)
    aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
    
    M = cv2.moments(cnt)
    if M["m00"] > 0:
        cx_local = int(M["m10"] / M["m00"])
        cy_local = int(M["m01"] / M["m00"])
        cx_global = cx_local + x_start
        cy_global = cy_local + y_start
        
        marker = ""
        if 200 <= area <= 3000:
            marker += " ✓ÁREA_OK"
        else:
            marker += f" ✗ÁREA({area:.0f})"
        
        if 0.8 <= aspect <= 1.2:
            marker += " ✓AR_OK"
        else:
            marker += f" ✗AR({aspect:.2f})"
        
        print(f"[{i}] Área={area:6.0f} AR={aspect:.2f} → ({cx_global:4d}, {cy_global:4d}){marker}")
        
        if 200 <= area <= 3000 and 0.8 <= aspect <= 1.2:
            candidates.append((area, cx_global, cy_global))

print(f"\n✨ CANDIDATOS VÁLIDOS: {len(candidates)}")
for area, cx, cy in sorted(candidates, reverse=True):
    print(f"   Área={area:.0f} → ({cx}, {cy})")
