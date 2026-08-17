#!/usr/bin/env python3
"""Debug detectar_boton_x con logs detallados"""
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

def screenshot_adb() -> np.ndarray | None:
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
print(f"📱 Pantalla: {w}x{h}\n")

try:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Detectar píxeles blancos puros en TODA la pantalla
    mask_white = cv2.inRange(hsv, np.array([0, 0, 210]), np.array([180, 40, 255]))
    
    white_count = cv2.countNonZero(mask_white)
    print(f"⚪ Píxeles blancos: {white_count}")
    
    if white_count < 50:
        print("❌ Muy pocos píxeles")
        sys.exit(1)
    
    # Limpiar ruido - kernel más grande para preservar contornos
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE, kernel)
    # NO hacer OPEN
    
    # Encontrar contornos
    contours, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"📦 Contornos: {len(contours)}\n")
    
    # Filtrar candidatos
    candidates = []
    rejected = []
    
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        
        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
        
        M = cv2.moments(cnt)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            
            # Verificar por qué se rechaza
            reason = ""
            if area < 200 or area > 1500:
                reason = f"área={area:.0f}"
            elif aspect < 0.8 or aspect > 1.2:
                reason = f"AR={aspect:.2f}"
            else:
                # Criterios de ubicación
                in_right = 0.7 <= cx / w <= 1.0
                in_lower = 0.60 <= cy / h <= 1.0
                
                if not (in_right and in_lower):
                    reason = f"ubicación: X/W={cx/w:.2f}, Y/H={cy/h:.2f}"
                else:
                    right_score = (cx / w) * 50
                    bottom_score = (cy / h) * 50
                    square_score = 100 * (1 - abs(aspect - 1.0) / 0.4)
                    score = right_score + bottom_score + square_score
                    candidates.append((score, cx, cy, area, aspect))
                    print(f"✅ Contorno {i}: ({cx:4}, {cy:4}) área={area:.0f} AR={aspect:.2f} R={right_score:.0f} B={bottom_score:.0f} S={square_score:.0f} => SCORE={score:.1f}")
            
            if reason:
                rejected.append((i, cx, cy, area, aspect, reason))

    print(f"\n❌ Rechazados ({len(rejected)}):")
    for i, cx, cy, area, aspect, reason in rejected[:5]:
        print(f"  {i}: ({cx}, {cy}) - {reason}")

    if not candidates:
        print(f"\n❌ No hay candidatos válidos")
        sys.exit(1)
    
    candidates.sort(reverse=True)
    score, cx, cy, area, aspect = candidates[0]
    
    print(f"\n✅ MEJOR: ({cx}, {cy}) - SCORE={score:.1f}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
