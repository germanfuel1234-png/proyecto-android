#!/usr/bin/env python3
"""
Detector de Modales y Estados
==============================
Libería reutilizable para detectar: MAPA, COMBATE, POST-CAPTURA, MODALES
Usada por: diagnostico.py y pokemon_catcher.py

Exporta:
  - detectar_boton_x(img) → (bool, int, int) : Detecta X blanca para cerrar modales
  - detectar_checkmark(img) → (bool, int, int) : Detecta CHECKMARK verde POST-CAPTURA
  - detectar_estado(img) → (str, str) : Diagnostico completo: MAPA/COMBATE/POST-CAPTURA
"""

import cv2
import numpy as np
import subprocess
from typing import Tuple


def screenshot_adb() -> np.ndarray:
    """Captura pantalla del dispositivo via ADB."""
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


def detectar_boton_x(img: np.ndarray) -> Tuple[bool, int, int]:
    """
    Detecta el botón X blanca para cerrar menús/modales.
    SOLO en zona inferior derecha (X > 85%, Y > 75%).
    Filtro: contornos cuadrados (AR 0.8-1.2), área 500-3000.
    
    Retorna: (encontrado, x, y) - coordenadas del centro de la X
    """
    if img is None:
        return False, 0, 0
    
    h, w = img.shape[:2]
    
    try:
        # BÚSQUEDA LOCALIZADA: zona inferior derecha
        x_start = int(w * 0.85)  # 15% derecha
        y_start = int(h * 0.75)  # 25% inferior
        zone = img[y_start:, x_start:]
        
        if zone.size == 0:
            return False, 0, 0
        
        hsv = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
        
        # Detectar píxeles blancos puros
        mask_white = cv2.inRange(hsv, np.array([0, 0, 210]), np.array([180, 40, 255]))
        
        if cv2.countNonZero(mask_white) < 50:
            return False, 0, 0
        
        # Limpiar ruido
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE, kernel)
        
        # Encontrar contornos
        contours, _ = cv2.findContours(mask_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return False, 0, 0
        
        # Filtrar candidatos
        candidates = []
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            
            # Filtro de área: 500-3000 (evitar ruido, la X típica es ~900px)
            if area < 500 or area > 3000:
                continue
            
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
            
            # Debe ser cuadrado (0.8-1.2)
            if aspect < 0.8 or aspect > 1.2:
                continue
            
            # Calcular centro
            M = cv2.moments(cnt)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"]) + x_start
                cy = int(M["m01"] / M["m00"]) + y_start
                
                candidates.append((area, cx, cy))
        
        if not candidates:
            return False, 0, 0
        
        # Tomar el MAYOR (más probable que sea la X real, no ruido)
        candidates.sort(reverse=True)
        _, cx, cy = candidates[0]
        
        return True, cx, cy
        
    except Exception as e:
        return False, 0, 0


def detectar_checkmark(img: np.ndarray) -> Tuple[bool, int, int]:
    """
    Detecta el CHECKMARK verde en esquina inferior derecha (POST-CAPTURA).
    Es un cuadrado ~180x180px, área típicamente 20000-30000px.
    
    Retorna: (encontrado, x, y) - coordenadas del centro del CHECKMARK
    """
    if img is None:
        return False, 0, 0
    
    h, w = img.shape[:2]
    
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Detectar verde/turquesa
        hsv_lower = cv2.inRange(hsv, np.array([60, 50, 80]), np.array([160, 255, 255]))
        kernel_verde = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        hsv_lower = cv2.morphologyEx(hsv_lower, cv2.MORPH_CLOSE, kernel_verde)
        
        # Buscar contornos verdes
        contours_verde, _ = cv2.findContours(hsv_lower, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours_verde:
            area = cv2.contourArea(cnt)
            # CHECKMARK: área 15000-35000
            if 15000 <= area <= 35000:
                x, y, bw, bh = cv2.boundingRect(cnt)
                aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
                
                # Debe ser cuadrado (0.9-1.1)
                if aspect < 0.9 or aspect > 1.1:
                    continue
                
                # En esquina inferior DERECHA (X>70%, Y>80%)
                cx = x + bw // 2
                cy = y + bh // 2
                if cx > w * 0.70 and cy > h * 0.80:
                    return True, cx, cy
        
        return False, 0, 0
        
    except Exception as e:
        return False, 0, 0


def detectar_estado(img: np.ndarray) -> Tuple[str, str]:
    """
    Diagnóstico completo: retorna (estado, detalles)
    Estados posibles:
      - "MAPA": Pantalla de mapa limpia
      - "COMBATE": En combate con Pokémon
      - "POST-CAPTURA": Modal de POST-CAPTURA
      - "MODAL": Modal/menú abierto (inventario, opciones)
    """
    if img is None:
        return "ERROR", "No se pudo capturar pantalla"
    
    h, w = img.shape[:2]
    
    try:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # 1. Detectar rojo (Pokébola de combate)
        mask_r = cv2.inRange(hsv, np.array([0, 80, 100]), np.array([10, 255, 255]))
        mask_r += cv2.inRange(hsv, np.array([170, 80, 100]), np.array([180, 255, 255]))
        rojo_total = cv2.countNonZero(mask_r)
        pct_rojo = rojo_total / (w * h)
        
        # 2. Detectar verde (avatar)
        mask_g = cv2.inRange(hsv, np.array([35, 40, 50]), np.array([95, 255, 255]))
        verde_total = cv2.countNonZero(mask_g)
        pct_verde = verde_total / (w * h)
        
        # 3. Detectar blanco (UI)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blanco = cv2.countNonZero(cv2.inRange(gray, 200, 255))
        pct_blanco = blanco / (w * h)
        
        # 4. Detectar X (criterio principal para modal)
        hay_x, x_cx, x_cy = detectar_boton_x(img)
        
        # 5. Detectar CHECKMARK
        hay_checkmark, chk_x, chk_y = detectar_checkmark(img)
        
        # --- Determinar estado ---
        if hay_x:
            return "MODAL", f"X en ({x_cx}, {x_cy})"
        elif hay_checkmark:
            return "POST-CAPTURA", f"Checkmark en ({chk_x}, {chk_y})"
        elif pct_rojo > 0.03:
            return "COMBATE", f"rojo={pct_rojo:.1%}"
        else:
            return "MAPA", f"verde={pct_verde:.1%}"
        
    except Exception as e:
        return "ERROR", str(e)


if __name__ == "__main__":
    # Test
    img = screenshot_adb()
    if img is not None:
        estado, detalles = detectar_estado(img)
        print(f"Estado: {estado}")
        print(f"Detalles: {detalles}")
    else:
        print("No se pudo capturar pantalla")
