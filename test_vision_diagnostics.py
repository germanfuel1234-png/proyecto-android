#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_vision_diagnostics.py
=======================
Captura múltiples frames y diagnostica qué está detectando la visión.
Útil para debuggear si MAP se detecta correctamente.

Uso:
  python test_vision_diagnostics.py --frames 30 --hsv-only
"""

import sys
import time
import argparse
import cv2
import numpy as np
from pathlib import Path
from collections import Counter

# Agregar kimi al path
sys.path.insert(0, str(Path(__file__).parent / "kimi"))

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
except ImportError:
    print("❌ Instala: pip install rich")
    sys.exit(1)

from adb_driver import ADBDriver
from vision_engine import VisionEngine, ScreenState


def analyze_hsv_metrics(img_bgr: np.ndarray) -> dict:
    """Calcula todas las métricas HSV para entender qué detecta."""
    h, w = img_bgr.shape[:2]
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    total_px = w * h
    
    # Blanco (modales)
    mask_white = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
    pct_white = cv2.countNonZero(mask_white) / total_px
    
    # Rojo intenso (pokébola de combate)
    mask_r1 = cv2.inRange(hsv, np.array([0, 150, 80]), np.array([10, 255, 255]))
    mask_r2 = cv2.inRange(hsv, np.array([170, 150, 80]), np.array([180, 255, 255]))
    pct_red = cv2.countNonZero(mask_r1 | mask_r2) / total_px
    
    # Verde (mapa)
    mask_green = cv2.inRange(hsv, np.array([35, 40, 50]), np.array([95, 255, 255]))
    pct_green = cv2.countNonZero(mask_green) / total_px
    
    # Cian dominante (mapa con agua/cielo)
    mask_cyan = cv2.inRange(hsv, np.array([85, 30, 50]), np.array([100, 255, 255]))
    pct_cyan = cv2.countNonZero(mask_cyan) / total_px
    
    # Oscuridad (loading)
    dark_px = cv2.countNonZero(cv2.inRange(gray, 0, 30))
    pct_dark = dark_px / total_px
    
    # Entropía de bordes
    edges = cv2.Laplacian(gray, cv2.CV_64F)
    edge_intensity = float(np.abs(edges).mean())
    
    return {
        "white": pct_white,
        "red": pct_red,
        "green": pct_green,
        "cyan": pct_cyan,
        "dark": pct_dark,
        "edge_intensity": edge_intensity,
    }


def diagnose_multiple_frames(vision: VisionEngine, num_frames: int = 30):
    """Captura múltiples frames y analiza patrones."""
    console = Console()
    driver = ADBDriver()
    
    if not driver.auto_detect():
        console.print("[bold red]❌ No se detectó dispositivo ADB[/]")
        return
    
    w, h = driver.get_resolution()
    console.print(f"[green]✅ Dispositivo: {driver.device} @ {w}×{h}[/]")
    console.print(f"[cyan]📸 Capturando {num_frames} frames...[/]\n")
    
    results = []
    states_detected = Counter()
    metrics_by_state = {}
    
    for i in range(num_frames):
        img = driver.screenshot()
        if img is None:
            console.print(f"[red]❌ Frame {i+1} falló[/]")
            continue
        
        result = vision.classify(img)
        states_detected[result.state.name] += 1
        
        metrics = analyze_hsv_metrics(img)
        if result.state.name not in metrics_by_state:
            metrics_by_state[result.state.name] = []
        metrics_by_state[result.state.name].append(metrics)
        
        results.append({
            "frame": i + 1,
            "state": result.state.name,
            "confidence": result.confidence,
            "metrics": metrics,
        })
        
        # Mostrar progreso
        console.print(
            f"[dim][{i+1:2d}/{num_frames}] "
            f"{result.state.name:15s} ({result.confidence:5.1%}) | "
            f"verde={metrics['green']:.1%} cian={metrics['cyan']:.1%} "
            f"rojo={metrics['red']:.1%} blanco={metrics['white']:.1%} "
            f"oscuro={metrics['dark']:.1%} bordes={metrics['edge_intensity']:6.1f}[/dim]"
        )
        
        time.sleep(0.5)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Resumen
    # ═══════════════════════════════════════════════════════════════════════
    
    console.print("\n" + "="*80 + "\n")
    
    # Tabla 1: Distribución de estados
    table1 = Table(title="📊 Estados Detectados", box=box.ROUNDED)
    table1.add_column("Estado", style="cyan", width=15)
    table1.add_column("Conteo", justify="right", style="white")
    table1.add_column("Porcentaje", justify="right", style="yellow")
    
    total = sum(states_detected.values())
    for state, count in states_detected.most_common():
        pct = count / total * 100
        table1.add_row(state, str(count), f"{pct:.1f}%")
    
    console.print(table1)
    
    # Tabla 2: Métricas promedio por estado
    console.print("\n")
    table2 = Table(title="📈 Métricas Promedio por Estado", box=box.ROUNDED)
    table2.add_column("Estado", style="cyan", width=15)
    table2.add_column("Verde", justify="right")
    table2.add_column("Cian", justify="right")
    table2.add_column("Rojo", justify="right")
    table2.add_column("Blanco", justify="right")
    table2.add_column("Oscuro", justify="right")
    table2.add_column("Bordes", justify="right")
    
    for state_name, metrics_list in sorted(metrics_by_state.items()):
        if not metrics_list:
            continue
        
        avg_green = np.mean([m["green"] for m in metrics_list])
        avg_cyan = np.mean([m["cyan"] for m in metrics_list])
        avg_red = np.mean([m["red"] for m in metrics_list])
        avg_white = np.mean([m["white"] for m in metrics_list])
        avg_dark = np.mean([m["dark"] for m in metrics_list])
        avg_edge = np.mean([m["edge_intensity"] for m in metrics_list])
        
        table2.add_row(
            state_name,
            f"{avg_green:.1%}",
            f"{avg_cyan:.1%}",
            f"{avg_red:.1%}",
            f"{avg_white:.1%}",
            f"{avg_dark:.1%}",
            f"{avg_edge:.1f}",
        )
    
    console.print(table2)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Diagnóstico específico: ¿Detecta bien MAP?
    # ═══════════════════════════════════════════════════════════════════════
    
    console.print("\n" + "="*80 + "\n")
    console.print("[bold cyan]🔍 DIAGNÓSTICO DE DETECCIÓN MAP[/]\n")
    
    map_results = [r for r in results if r["state"] == "MAP"]
    if map_results:
        console.print(f"[green]✅ Detectó MAP {len(map_results)}/{num_frames} veces ({len(map_results)/num_frames*100:.1f}%)[/]")
        
        # Analizar condiciones que llevan a MAP
        avg_metrics = np.mean([r["metrics"] for r in map_results], axis=0)
        table3 = Table(title="MAP: Condiciones detectadas", box=box.ROUNDED)
        table3.add_column("Métrica", style="cyan")
        table3.add_column("Valor", style="white")
        table3.add_column("¿Cumple?", style="yellow")
        
        # Condiciones necesarias para MAP
        verde_ok = avg_metrics["green"] > 0.20
        cian_ok = avg_metrics["cyan"] > 0.25
        bordes_ok = avg_metrics["edge_intensity"] > 10
        
        table3.add_row("Verde > 20%", f"{avg_metrics['green']:.1%}", "✅" if verde_ok else "❌")
        table3.add_row("Cian > 25%", f"{avg_metrics['cyan']:.1%}", "✅" if cian_ok else "❌")
        table3.add_row("Bordes > 10", f"{avg_metrics['edge_intensity']:.1f}", "✅" if bordes_ok else "❌")
        table3.add_row("(Verde OR Cian) AND Bordes", "", "✅" if ((verde_ok or cian_ok) and bordes_ok) else "❌")
        
        console.print(table3)
    else:
        console.print(f"[red]❌ NUNCA detectó MAP (0/{num_frames})[/]")
        console.print("[yellow]⚠ El bot probablemente no entrará a un Pokémon.[/]")
        console.print("[yellow]Posibles causas:[/]")
        console.print("  1. El celular no está en la pantalla MAP")
        console.print("  2. El modelo HSV está fallando (verde/cian bajos)")
        console.print("  3. La entropía de bordes es muy baja")
        
        # Mostrar qué detecta en su lugar
        other_states = Counter([r["state"] for r in results])
        console.print(f"\n[cyan]En su lugar está detectando:[/]")
        for state, count in other_states.most_common():
            console.print(f"  • {state}: {count}/{num_frames}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # Recomendaciones
    # ═══════════════════════════════════════════════════════════════════════
    
    console.print("\n" + "="*80)
    console.print("[bold cyan]💡 RECOMENDACIONES[/]\n")
    
    if not map_results:
        console.print("[yellow]1. Verifica que Pokémon GO esté abierto en MAP[/]")
        console.print("[yellow]2. Ajusta los umbrales de HSV en vision_engine.py:[/]")
        console.print("   - GREEN: línea ~310, aumenta desde 0.20 → 0.15")
        console.print("   - CYAN: línea ~313, ajusta desde 0.25 → 0.15")
        console.print("   - EDGE: línea ~321, reduce desde 10 → 5")
        console.print("[yellow]3. O entrena un modelo ONNX: python kimi/dataset_generator.py[/]")
    else:
        console.print("[green]✅ MAP se detecta correctamente[/]")
        console.print("[green]✅ Si el bot no toca sniper, el problema está en coordinates[/]")
        console.print("   Revisa state_machine.py línea ~279 (self.coords.sniper())")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=30, help="Cantidad de frames a capturar")
    parser.add_argument("--no-onnx", action="store_true", help="Forzar HSV fallback")
    args = parser.parse_args()
    
    # Inicializar visión
    model_path = "model.onnx" if not args.no_onnx else None
    vision = VisionEngine(model_path=model_path)
    
    diagnose_multiple_frames(vision, args.frames)


if __name__ == "__main__":
    main()
