#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎨 ANALIZADOR DE COLORES - Detallar HSV para calibración
"""

import subprocess
import sys
import os
import cv2
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def _find_adb():
    import shutil
    adb = shutil.which("adb")
    if adb:
        return adb
    for path in [
        "/tmp/platform-tools/adb",
        os.path.expanduser("~/Android/platform-tools/adb"),
        "/opt/android-sdk/platform-tools/adb",
    ]:
        if os.path.exists(path):
            return path
    return "adb"

def screenshot_adb() -> np.ndarray | None:
    """Captura pantalla vía ADB."""
    adb_cmd = _find_adb()
    cmd = [adb_cmd, "-s", "ZY22FVZQQF", "exec-out", "screencap", "-p"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        if r.returncode != 0 or not r.stdout:
            return None
        arr = np.frombuffer(r.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img if img is not None and img.size > 0 else None
    except Exception as e:
        return None

def analizar_colores():
    """Analiza todos los colores en la pantalla actual."""
    img = screenshot_adb()
    if img is None:
        console.print("[red]❌ Error: No se pudo capturar pantalla[/]")
        return
    
    h, w = img.shape[:2]
    total_pixeles = w * h
    
    console.print(Panel(
        "[bold cyan]🎨 ANÁLISIS DE COLORES DETALLADO[/]\n"
        f"[dim]Resolución: {w}x{h} ({total_pixeles:,} píxeles)[/]",
        border_style="cyan"))
    console.print()
    
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Definir rangos de colores
    colores = {
        "🔴 ROJO PURO": ([0, 80, 80], [15, 255, 255]),
        "🔴 ROJO OSCURO": ([165, 80, 80], [180, 255, 255]),
        "🟠 NARANJA": ([10, 100, 100], [25, 255, 255]),
        "🟡 AMARILLO": ([20, 100, 100], [35, 255, 255]),
        "🟢 VERDE CLARO": ([35, 40, 50], [95, 255, 255]),
        "🟢 VERDE OSCURO": ([40, 80, 80], [90, 255, 255]),
        "🔵 AZUL CLARO": ([100, 30, 30], [130, 255, 255]),
        "🔵 AZUL OSCURO": ([100, 100, 80], [130, 255, 255]),
        "⚪ BLANCO": ([0, 0, 200], [180, 50, 255]),
        "⚫ NEGRO": ([0, 0, 0], [180, 255, 50]),
        "🩶 GRIS": ([0, 0, 50], [180, 50, 200]),
        "🔵 CIAN": ([85, 100, 100], [100, 255, 255]),
    }
    
    # Crear tabla
    table = Table(title="Distribución de Colores", show_header=True)
    table.add_column("Color", style="cyan")
    table.add_column("Píxeles", style="magenta")
    table.add_column("Porcentaje", style="green")
    table.add_column("Estado", style="yellow")
    
    resultados = []
    for color_name, (lower, upper) in colores.items():
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        count = cv2.countNonZero(mask)
        pct = (count / total_pixeles) * 100
        resultados.append((color_name, count, pct))
        
        # Estado visual
        if count > 100000:
            estado = "🔥 ABUNDANTE"
        elif count > 50000:
            estado = "✅ PRESENTE"
        elif count > 10000:
            estado = "📊 MODERADO"
        elif count > 1000:
            estado = "🔍 POCO"
        else:
            estado = "⚪ MÍNIMO"
        
        table.add_row(color_name, f"{count:,}", f"{pct:.1%}", estado)
    
    console.print(table)
    console.print()
    
    # Análisis detallado
    console.print(Panel("[bold cyan]📊 ANÁLISIS DETALLADO[/]", border_style="cyan"))
    
    # Top 5 colores
    resultados.sort(key=lambda x: x[1], reverse=True)
    console.print("\n[bold]🏆 Top 5 Colores:[/]")
    for i, (color_name, count, pct) in enumerate(resultados[:5], 1):
        barra = "█" * int(pct / 2)
        console.print(f"  {i}. {color_name:<20} {count:>8,} px ({pct:>5.1f}%) {barra}")
    
    # Análisis HSV específico
    console.print("\n[bold]🎯 Histogramas HSV:[/]")
    h_vals = hsv[:, :, 0].flatten()
    s_vals = hsv[:, :, 1].flatten()
    v_vals = hsv[:, :, 2].flatten()
    
    console.print(f"  Hue:   min={h_vals.min():>3} max={h_vals.max():>3} mean={h_vals.mean():.0f} std={h_vals.std():.0f}")
    console.print(f"  Sat:   min={s_vals.min():>3} max={s_vals.max():>3} mean={s_vals.mean():.0f} std={s_vals.std():.0f}")
    console.print(f"  Val:   min={v_vals.min():>3} max={v_vals.max():>3} mean={v_vals.mean():.0f} std={v_vals.std():.0f}")
    
    # Recomendaciones
    console.print("\n[bold]💡 RECOMENDACIONES:[/]")
    
    mask_azul = cv2.inRange(hsv, np.array([100, 30, 30]), np.array([130, 255, 255]))
    azul_count = cv2.countNonZero(mask_azul)
    azul_pct = (azul_count / total_pixeles) * 100
    
    mask_verde = cv2.inRange(hsv, np.array([35, 40, 50]), np.array([95, 255, 255]))
    verde_count = cv2.countNonZero(mask_verde)
    verde_pct = (verde_count / total_pixeles) * 100
    
    if azul_pct > 30 and verde_pct > 5:
        console.print(f"  ✅ [green]MAPA DETECTADO[/]")
        console.print(f"     Azul: {azul_count:,} px ({azul_pct:.1f}%)")
        console.print(f"     Verde: {verde_count:,} px ({verde_pct:.1f}%)")
    else:
        console.print(f"  ⚠️  [yellow]NO ES MAPA[/]")
        console.print(f"     Azul: {azul_count:,} px ({azul_pct:.1f}%) [threshold: >30%]")
        console.print(f"     Verde: {verde_count:,} px ({verde_pct:.1f}%) [threshold: >5%]")
    
    # Guardar captura con estadísticas
    output_file = "ultima_captura_analisis.png"
    cv2.imwrite(output_file, img)
    console.print(f"\n[dim]📷 Captura guardada: {output_file}[/]")

if __name__ == "__main__":
    analizar_colores()
