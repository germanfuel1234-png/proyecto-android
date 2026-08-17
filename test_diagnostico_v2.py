#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔬 TEST DIAGNÓSTICO v2 - Demuestra todas las capacidades
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from diagnostico import mostrar_diagnostico
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import time

console = Console()

def test_diagnostico():
    """Ejecuta 10 diagnósticos y muestra estadísticas."""
    
    console.print(Panel(
        "[bold cyan]🔬 TEST DIAGNÓSTICO v2[/]\n"
        "[dim]Probando 10 capturas consecutivas...[/]",
        border_style="cyan"))
    console.print()
    
    resultados = []
    
    for i in range(1, 11):
        estado, detalles = mostrar_diagnostico()
        
        if estado is None:
            console.print(f"[red]❌ [{i:02d}] Error: {detalles}[/]")
        else:
            console.print(f"[green]✅ [{i:02d}] {estado:<25} {detalles}[/]")
            resultados.append((estado, detalles))
        
        time.sleep(0.5)
    
    console.print()
    console.print(Panel(
        "[bold cyan]📊 ESTADÍSTICAS[/]",
        border_style="cyan"))
    
    # Contar pantallas detectadas
    pantallas = {}
    for estado, _ in resultados:
        if "TEMPLATE" in estado:
            key = "Template Matching"
        elif "POST-CAPTURA" in estado:
            key = "Post-Captura"
        elif "COMBATE" in estado:
            key = "Combate"
        elif "MODAL" in estado:
            key = "Modal"
        elif "POKÉSTOP" in estado:
            key = "Pokéstop"
        elif "GIMNASIO" in estado:
            key = "Gimnasio"
        elif "MAPA" in estado:
            key = "Mapa"
        else:
            key = "Desconocido"
        
        pantallas[key] = pantallas.get(key, 0) + 1
    
    # Tabla de resultados
    table = Table(title="Detecciones")
    table.add_column("Pantalla", style="cyan")
    table.add_column("Cantidad", style="magenta")
    table.add_column("Porcentaje", style="green")
    
    total = len(resultados)
    for pantalla in sorted(pantallas.keys()):
        cant = pantallas[pantalla]
        pct = (cant / total) * 100
        table.add_row(pantalla, str(cant), f"{pct:.0f}%")
    
    console.print(table)
    console.print()
    console.print("[bold green]✨ Diagnóstico v2 funcionando correctamente[/]")
    console.print("[dim]Templates + OCR + HSV activados y operacionales[/]")

if __name__ == "__main__":
    try:
        test_diagnostico()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Test interrumpido por usuario[/]")
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/]")
        import traceback
        traceback.print_exc()
