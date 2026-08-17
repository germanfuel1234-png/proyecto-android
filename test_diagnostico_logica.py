#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 TEST DE DIAGNÓSTICO - Validación de lógica SIN necesidad de dispositivo

Prueba la lógica de diagnóstico en casos extremos.
No requiere ADB ni dispositivo conectado.
"""

import sys
import os
import numpy as np
import cv2

# Importar funciones de diagnóstico
sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# ═══════════════════════════════════════════════════════════════════════════
# FUNCIONES DE TEST
# ═══════════════════════════════════════════════════════════════════════════

def crear_imagen_test(w: int, h: int, estado: str) -> np.ndarray:
    """
    Crea una imagen BGR simulada para un estado específico.
    
    Estados:
    - MAPA: verde dominante
    - COMBATE: rojo aro + verde
    - POST-CAPTURA: blanco modal
    - DESCONOCIDO: gris neutral
    """
    img = np.zeros((h, w, 3), dtype=np.uint8)
    
    if estado == "MAPA":
        # Verde claro (cielo y terreno)
        # BGR: (0, 200, 100) ≈ verde en HSV
        img[:, :] = (100, 200, 0)  # RGB: (0, 200, 100)
        
    elif estado == "COMBATE":
        # Verde de fondo + rojo aro (ROJO PURO, MUY SATURADO)
        img[:, :] = (100, 200, 0)  # Base verde (80% de la pantalla)
        # Agregar aro rojo en el centro con ÁREA GRANDE (2% de la pantalla)
        h_center, w_center = h // 2, w // 2
        # Usar líneas gruesas para crear suficiente rojo
        for i in range(-100, 101, 5):
            cv2.line(img, (w_center-100, h_center+i), (w_center+100, h_center+i), (0, 0, 255), 3)
        
    elif estado == "POST-CAPTURA":
        # Blanco modal (V>200, S<50 en HSV)
        img[:, :] = (240, 240, 240)  # Blanco puro
        
    elif estado == "DESCONOCIDO":
        # Gris neutral
        img[:, :] = (128, 128, 128)
    
    return img


def analizar_imagen_test(img: np.ndarray, nombre_test: str) -> dict:
    """Analiza una imagen de test y retorna porcentajes de colores."""
    h, w = img.shape[:2]
    total_pixeles = w * h
    
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Blanco
    mask_blanco = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
    pct_blanco = cv2.countNonZero(mask_blanco) / total_pixeles
    
    # Verde
    mask_verde = cv2.inRange(hsv, np.array([35, 40, 50]), np.array([95, 255, 255]))
    pct_verde = cv2.countNonZero(mask_verde) / total_pixeles
    
    # Rojo
    mask_r1 = cv2.inRange(hsv, np.array([0,   100, 80]),   np.array([10,  255, 255]))
    mask_r2 = cv2.inRange(hsv, np.array([170, 100, 80]),   np.array([180, 255, 255]))
    pct_rojo = cv2.countNonZero(mask_r1 | mask_r2) / total_pixeles
    
    return {
        "nombre": nombre_test,
        "rojo": pct_rojo,
        "verde": pct_verde,
        "blanco": pct_blanco,
    }


def diagnosticar_test(stats: dict) -> str:
    """
    Aplica la lógica de diagnóstico v3 a los valores de test.
    """
    rojo = stats["rojo"]
    verde = stats["verde"]
    blanco = stats["blanco"]
    
    # Lógica v3
    if rojo > 0.008 and blanco < 0.30:
        return "⚔️  COMBATE"
    elif blanco > 0.30:
        return "🎁 POST-CAPTURA"
    elif verde > 0.30:
        return "✅ MAPA"
    elif verde > 0.20:
        return "✅ MAPA (probable)"
    else:
        return "❓ DESCONOCIDO"


def main():
    console.print(Panel(
        "[bold cyan]🧪 TEST DE LÓGICA DE DIAGNÓSTICO[/]\n"
        "[dim]Valida que la detección de pantallas funcione correctamente[/]",
        border_style="cyan"
    ))
    console.print()
    
    # Crear imágenes de test
    w, h = 1080, 2400
    estados_test = ["MAPA", "COMBATE", "POST-CAPTURA", "DESCONOCIDO"]
    
    tabla = Table(title="Resultados de Detección")
    tabla.add_column("Estado Esperado", style="cyan")
    tabla.add_column("Rojo %", justify="right", style="red")
    tabla.add_column("Verde %", justify="right", style="green")
    tabla.add_column("Blanco %", justify="right", style="white")
    tabla.add_column("Detectado", style="yellow")
    tabla.add_column("Resultado", style="magenta")
    
    resultados = []
    
    for estado in estados_test:
        img = crear_imagen_test(w, h, estado)
        stats = analizar_imagen_test(img, estado)
        detectado = diagnosticar_test(stats)
        
        # Validar resultado
        esperado_map = {
            "MAPA": "✅ MAPA",
            "COMBATE": "⚔️  COMBATE",
            "POST-CAPTURA": "🎁 POST-CAPTURA",
            "DESCONOCIDO": "❓ DESCONOCIDO",
        }
        
        esperado = esperado_map.get(estado, "?")
        resultado = "✅ OK" if detectado.strip() == esperado.strip() else f"❌ FALLO (esperaba {esperado})"
        
        tabla.add_row(
            estado,
            f"{stats['rojo']:.2%}",
            f"{stats['verde']:.2%}",
            f"{stats['blanco']:.2%}",
            detectado,
            resultado
        )
        
        resultados.append(resultado == "✅ OK")
    
    console.print(tabla)
    console.print()
    
    # Resumen
    total = len(resultados)
    exitosos = sum(resultados)
    
    if exitosos == total:
        console.print(f"[bold green]✅ TODOS LOS TESTS PASARON ({exitosos}/{total})[/]")
        console.print()
        console.print("[green]La lógica de diagnóstico es precisa y está lista para uso.[/]")
        return 0
    else:
        console.print(f"[bold red]❌ {total - exitosos} TEST(S) FALLARON ({exitosos}/{total})[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
