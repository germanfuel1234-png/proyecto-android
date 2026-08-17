#!/usr/bin/env python3
"""Debug: probar detectar_boton_x()"""
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

def detectar_boton_x_debug(img: np.ndarray) -> tuple[bool, int, int]:
    """Versión debug con logs"""
    if img is None:
        print("❌ Imagen None")
        return False, 0, 0
    
    h, w = img.shape[:2]
    print(f"📱 Pantalla: {w}x{h}")
    
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Detectar píxeles blancos puros en TODA la pantalla
        mask_white = cv2.inRange(hsv, np.array([0, 0, 210]), np.array([180, 40, 255]))
        white_pixels = cv2.countNonZero(mask_white)
        print(f"\n⚪ Píxeles blancos encontrados: {white_pixels}")
        
        if white_pixels < 50:
            print("❌ Muy pocos píxeles blancos")
            return False, 0, 0
        
        # Limpiar ruido
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE, kernel)
        mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_OPEN, kernel)
        
        # Encontrar todos los contornos blancos
        contours, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        print(f"📦 Contornos encontrados: {len(contours)}")
        
        # Buscar candidatos EN ZONA INFERIOR primero
        candidates_inferior = []
        for i, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
            
            M = cv2.moments(cnt)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                
                # Debug de los candidatos
                if 200 <= area <= 1500 and 0.8 <= aspect <= 1.2:
                    if cy > h * 0.60:  # ZONA INFERIOR
                        print(f"  ✓ Contorno {i}: ({cx}, {cy}) área={area:.0f}, AR={aspect:.2f} - EN ZONA INFERIOR")
                        candidates_inferior.append((-area, aspect, cx, cy))
                    else:
                        print(f"  ✗ Contorno {i}: ({cx}, {cy}) área={area:.0f}, AR={aspect:.2f} - NO en zona inferior (Y={cy}, límite={int(h*0.60)})")
        
        if not candidates_inferior:
            print("❌ No hay candidatos en zona inferior")
            return False, 0, 0
        
        candidates_inferior.sort()
        _, _, cx, cy = candidates_inferior[0]
        print(f"\n✅ X SELECCIONADA en ({cx}, {cy})")
        
        return True, cx, cy
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0, 0

img = screenshot_adb()
print("="*60)
encontrado, x, y = detectar_boton_x_debug(img)
print("="*60)
