#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de clicks: Verifica que las coordenadas estén bien calibradas
para POST-CAPTURA, COMBATE y otras pantallas.
"""

import subprocess
import time
from diagnostico import mostrar_diagnostico
import cv2
import numpy as np
from pokemon_catcher import screenshot_adb

def get_screenshot():
    """Captura screenshot del dispositivo."""
    return screenshot_adb()

def test_post_captura_clicks():
    """Verifica coordenadas de POST-CAPTURA."""
    print("\n🎁 TEST POST-CAPTURA - Clicks en modal de recompensas")
    print("=" * 60)
    
    img = get_screenshot()
    if img is None:
        print("❌ No se pudo capturar pantalla")
        return
    
    estado, detalles = mostrar_diagnostico()
    print(f"Estado detectado: {estado} - {detalles}")
    
    if "POST-CAPTURA" in estado:
        h, w = img.shape[:2]
        
        # Mostrar coordenadas clave
        print(f"\n📐 Resolución: {w}x{h}")
        print(f"\n🔵 Coordenadas clave para POST-CAPTURA:")
        
        # Botón DE ACUERDO (verde/teal)
        ok_x = w // 2
        ok_y = int(h * 0.85)  # 85% de altura
        print(f"  • Botón 'DE ACUERDO': ({ok_x}, {ok_y})")
        
        # Checkmark
        checkmark_x = 550
        checkmark_y = int(h * 0.89)  # ~2135 para 2400
        print(f"  • Checkmark ✓: ({checkmark_x}, {checkmark_y})")
        
        # Tap fallback
        fallback_x = w // 2
        fallback_y = int(h * 0.87)
        print(f"  • Fallback tap: ({fallback_x}, {fallback_y})")
        
        print(f"\n✅ POST-CAPTURA correctamente detectado")
        print(f"   Blanco: {detalles.split('=')[1].split()[0]}")
        print(f"   Verde: {detalles.split('=')[2]}")
        
    else:
        print(f"⚠️  No es POST-CAPTURA. Actual: {estado}")

def test_combate_clicks():
    """Verifica coordenadas de COMBATE."""
    print("\n⚔️  TEST COMBATE - Clicks de lanzamiento")
    print("=" * 60)
    
    img = get_screenshot()
    if img is None:
        print("❌ No se pudo capturar pantalla")
        return
    
    estado, detalles = mostrar_diagnostico()
    print(f"Estado detectado: {estado} - {detalles}")
    
    if "COMBATE" in estado:
        h, w = img.shape[:2]
        
        print(f"\n📐 Resolución: {w}x{h}")
        print(f"\n🔴 Coordenadas clave para COMBATE (lanzamiento):")
        
        # Coordenadas de swipe
        throw_start_x = 546
        throw_start_y = 1420
        throw_end_x = 540
        
        print(f"  • INICIO del swipe: ({throw_start_x}, {throw_start_y})")
        print(f"  • FIN NORMAL (700px): ({throw_end_x}, 700)")
        print(f"  • FIN FAR (1080px): ({throw_end_x}, 340)")
        print(f"  • FIN ULTRA (1370px): ({throw_end_x}, 50)")
        print(f"  • FIN SUPER ULTRA (1500px): ({throw_end_x}, -80)")
        
        print(f"\n⏱️  Duraciones de swipe:")
        print(f"  • NORMAL: 300ms")
        print(f"  • FAR: 260ms")
        print(f"  • ULTRA: 215ms")
        print(f"  • SUPER ULTRA: 195ms")
        
        print(f"\n✅ COMBATE correctamente detectado")
        print(f"   Rojo: {detalles}")
        
    else:
        print(f"⚠️  No es COMBATE. Actual: {estado}")

def test_mapa_clicks():
    """Verifica coordenadas de doble tap en MAPA."""
    print("\n✅ TEST MAPA - Doble tap en pokemones")
    print("=" * 60)
    
    img = get_screenshot()
    if img is None:
        print("❌ No se pudo capturar pantalla")
        return
    
    estado, detalles = mostrar_diagnostico()
    print(f"Estado detectado: {estado} - {detalles}")
    
    if "MAPA" in estado:
        h, w = img.shape[:2]
        
        print(f"\n📐 Resolución: {w}x{h}")
        print(f"\n🟢 Coordenadas clave para MAPA (doble tap):")
        
        # Panel de pokemones cercanos
        sniper_x = 54
        sniper_y_first = 245
        sniper_y_toggle = 221
        
        print(f"  • Panel izquierdo X: {sniper_x}")
        print(f"  • Botón ≡ (toggle): Y={sniper_y_toggle}")
        print(f"  • Pokemones comienzan: Y={sniper_y_first}")
        print(f"  • Primer pokemon: ({sniper_x}, {sniper_y_first})")
        
        print(f"\n✅ MAPA correctamente detectado")
        print(f"   Verde: {detalles.split('=')[1].split()[0]}")
        
    else:
        print(f"⚠️  No es MAPA. Actual: {estado}")

def show_pixel_colors(x, y):
    """Muestra el color HSV de un pixel (para calibración)."""
    img = get_screenshot()
    if img is None:
        print("❌ No se pudo capturar")
        return
    
    if x < 0 or y < 0 or x >= img.shape[1] or y >= img.shape[0]:
        print(f"❌ Coordenadas fuera de rango: ({x}, {y})")
        return
    
    # Extraer región pequeña alrededor del pixel
    margin = 10
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(img.shape[1], x + margin + 1)
    y2 = min(img.shape[0], y + margin + 1)
    
    roi = img[y1:y2, x1:x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # Pixel central
    cy = min(margin, hsv.shape[0] - 1)
    cx = min(margin, hsv.shape[1] - 1)
    h, s, v = hsv[cy, cx]
    
    # BGR del pixel central
    bgr = roi[cy, cx]
    
    print(f"\n📍 Pixel ({x}, {y}):")
    print(f"   BGR: {bgr}")
    print(f"   HSV: H={h} S={s} V={v}")
    
    # Detectar color aproximado
    if s < 30:
        if v < 100:
            color = "NEGRO"
        elif v > 200:
            color = "BLANCO"
        else:
            color = "GRIS"
    else:
        if h < 10 or h > 160:
            color = "ROJO"
        elif h < 25:
            color = "NARANJA"
        elif h < 35:
            color = "AMARILLO"
        elif h < 85:
            color = "VERDE"
        elif h < 100:
            color = "CIAN"
        elif h < 130:
            color = "AZUL"
        elif h < 160:
            color = "MAGENTA"
        else:
            color = "DESCONOCIDO"
    
    print(f"   Color detectado: {color}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--pixel":
        # Modo: test_clicks.py --pixel X Y
        if len(sys.argv) >= 4:
            x, y = int(sys.argv[2]), int(sys.argv[3])
            show_pixel_colors(x, y)
        else:
            print("Uso: python test_clicks.py --pixel X Y")
    else:
        # Modo normal: mostrar todos los tests
        print("\n" + "="*60)
        print("🔍 TEST DE CLICKS - Verificación de coordenadas")
        print("="*60)
        
        test_mapa_clicks()
        test_combate_clicks()
        test_post_captura_clicks()
        
        print("\n" + "="*60)
        print("✅ Test completado")
        print("\nPara verificar colores en píxeles específicos:")
        print("  python test_clicks.py --pixel 540 2135")
        print("="*60)
