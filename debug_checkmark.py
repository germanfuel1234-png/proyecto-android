#!/usr/bin/env python3
"""
Debug: Analizar CHECKMARK en POST-CAPTURA
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

# Zona inferior derecha: X>70%, Y>80%
x_start = int(w * 0.70)
y_start = int(h * 0.80)
zone = img[y_start:, x_start:]

print(f"🔍 Zona esquina inferior derecha: [{x_start}:{w}, {y_start}:{h}]")
print(f"   Tamaño zona: {zone.shape}\n")

hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
hsv_zone = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)

# Buscar verdes
mask = cv2.inRange(hsv_zone, np.array([60, 50, 80]), np.array([160, 255, 255]))
green_count = cv2.countNonZero(mask)
print(f"Píxeles verdes/turquesa en zona: {green_count}")

if green_count > 100:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    print(f"\n🔍 Contornos verdes encontrados: {len(contours)}\n")
    
    candidates = []
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
        
        M = cv2.moments(cnt)
        if M["m00"] > 0:
            cx_local = int(M["m10"] / M["m00"])
            cy_local = int(M["m01"] / M["m00"])
            cx_global = cx_local + x_start
            cy_global = cy_local + y_start
            
            candidates.append({
                'i': i,
                'area': area,
                'aspect': aspect,
                'cx': cx_global,
                'cy': cy_global,
                'w': bw,
                'h': bh
            })
    
    candidates.sort(key=lambda x: x['area'], reverse=True)
    
    for c in candidates[:10]:
        marker = ""
        if 800 <= c['area'] <= 2500:
            marker += " ✓ÁREA_OK"
        else:
            marker += f" ✗ÁREA({c['area']:.0f})"
        
        print(f"[{c['i']}] Área={c['area']:6.0f} AR={c['aspect']:.2f} "
              f"→ ({c['cx']:4d}, {c['cy']:4d}) {c['w']}x{c['h']}{marker}")
else:
    print("❌ No hay verdes en la zona esquina derecha")
    print("\nBuscando verdes en TODA la pantalla inferior (Y>80%)...")
    
    zone_full = img[y_start:, :]
    mask_full = cv2.inRange(cv2.cvtColor(zone_full, cv2.COLOR_BGR2HSV), 
                            np.array([60, 50, 80]), 
                            np.array([160, 255, 255]))
    green_full = cv2.countNonZero(mask_full)
    print(f"Píxeles verdes totales en Y>80%: {green_full}")
    
    if green_full > 100:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_full = cv2.morphologyEx(mask_full, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask_full, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        print(f"Contornos: {len(contours)}\n")
        
        for i, cnt in enumerate(contours[:5]):
            area = cv2.contourArea(cnt)
            x, y, bw, bh = cv2.boundingRect(cnt)
            
            M = cv2.moments(cnt)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"]) + y_start
                
                print(f"[{i}] Área={area:6.0f} → ({cx}, {cy})")
