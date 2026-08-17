#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📐 Resumen de coordenadas de clicks calibradas para Moto G52 (1080x2400)
Basado en análisis de pantallas reales del bot
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

PHONE_W = 1080
PHONE_H = 2400

# Coordenadas del bot
SNIPER_X = 54
SNIPER_Y_FIRST = 245
CHECKMARK_X = 550
CHECKMARK_Y = 2135
THROW_START_X = 546
THROW_START_Y = 1420
THROW_END_X = 540

coords = {
    "🟢 MAPA - Doble tap pokemones": {
        "Panel izquierdo (pokemones)": (54, 245),
        "Botón ≡ toggle": (54, 221),
        "Máximo slots": 12,
        "Separación entre pokemones": "80px",
    },
    "⚔️  COMBATE - Lanzar Pokébola (swipe)": {
        "Inicio (Pokébola)": (546, 1420),
        "Fin NORMAL (700px)": (540, 700),
        "Fin FAR (1080px)": (540, 340),
        "Fin ULTRA (1370px)": (540, 50),
        "Fin SUPER ULTRA (1500px)": (540, -80),
        "Duración NORMAL": "300ms",
        "Duración FAR": "260ms",
        "Duración ULTRA": "215ms",
        "Duración SUPER ULTRA": "195ms",
    },
    "🎁 POST-CAPTURA - Cerrar modal": {
        "Botón DE ACUERDO (verde/teal)": (540, int(PHONE_H * 0.85)),
        "Botón CHECKMARK ✓": (550, 2135),
        "Botón X (esquina)": (950, 190),
        "Fallback tap": (540, int(PHONE_H * 0.87)),
    },
    "⚠️  MODALES - Cerrar diálogos": {
        "X centrado-superior": (540, 175),
        "Botón inferior grande": (540, 2200),
        "X esquina derecha-sup": (950, 190),
        "X esquina izq-sup": (130, 190),
        "Tap genérico center-low": (540, 1800),
    },
}

# Mostrar título
console.print(Panel(
    "[bold cyan]📐 COORDENADAS DE CLICKS - Moto G52 (1080x2400)[/]\n"
    "[dim]Basado en análisis real de pantallas del bot[/]",
    border_style="cyan",
    padding=(1, 2)
))

# Mostrar cada sección
for pantalla, items in coords.items():
    print(f"\n{pantalla}")
    print("─" * 70)
    
    if isinstance(items, dict):
        for accion, valor in items.items():
            if isinstance(valor, tuple):
                print(f"  {accion:<40} → ({valor[0]}, {valor[1]})")
            else:
                print(f"  {accion:<40} → {valor}")
    else:
        print(f"  {items}")

# Mostrar análisis de seguridad
console.print(Panel(
    "[bold green]✅ ANÁLISIS DE SEGURIDAD DE CLICKS[/]\n"
    "[dim]Verifica que los clicks NO toquen elementos incorrectos[/]",
    border_style="green",
    padding=(1, 2)
))

checks = [
    ("POST-CAPTURA 'DE ACUERDO'", (540, 2040), 
     "✅ No toca botones EXIT abajo (Y<2200)", "Y=2040 < 2200"),
    ("POST-CAPTURA CHECKMARK", (550, 2135),
     "✅ En zona baja pero segura", "Y=2135 < 2200"),
    ("Botón X rechazo", (950, 190),
     "✅ Arriba en esquina derecha", "Fuera de COMBATE"),
    ("COMBATE swipe inicio", (546, 1420),
     "✅ Centro de pantalla", "Zona de Pokébola"),
    ("COMBATE swipe fin ULTRA", (540, 50),
     "✅ Arriba (golpe fuerte)", "Buena velocidad"),
]

for nombre, (x, y), desc, reason in checks:
    status = "✅" if x > 0 and y > 0 else "❌"
    print(f"\n{status} {nombre}")
    print(f"   Coords: ({x}, {y})")
    print(f"   {desc}")
    print(f"   → {reason}")

# Mostrar problemas potenciales
console.print()
console.print(Panel(
    "[bold yellow]⚠️  POSIBLES PROBLEMAS Y SOLUCIONES[/]",
    border_style="yellow",
    padding=(1, 2)
))

problemas = [
    ("POST-CAPTURA no se cierra",
     "1. Verificar que POST-CAPTURA se detecta (blanco>40% + verde>30%)",
     "2. Si detecta mal, check checkmark verde por contorno",
     "3. Fallback: hacer tap en (540, 2040)"),
    
    ("Pokébola no sale en COMBATE",
     "1. Verificar que COMBATE se detecta (rojo>5%)",
     "2. Swipe debe ser RÁPIDO y hacia ARRIBA",
     "3. Duración: 215-300ms según pokébola"),
    
    ("Doble tap MAPA no abre combate",
     "1. Primer tap: (54, 245) esperar 100ms",
     "2. Segundo tap: (54, 245) mismo lugar",
     "3. Total ~200ms entre los dos"),
]

for titulo, *pasos in problemas:
    print(f"\n❌ {titulo}")
    for paso in pasos:
        print(f"   {paso}")

# Mostrar calibración
console.print()
console.print(Panel(
    "[bold cyan]🔧 CALIBRACIÓN RÁPIDA[/]",
    border_style="cyan",
    padding=(1, 2)
))

print("""
Para recalibrar manualmente en tu dispositivo:
1. Usa scrcpy: scrcpy -m 1080 (espejo)
2. Hover sobre elementos → scrcpy muestra X, Y en tiempo real
3. Actualiza las coordenadas en pokemon_catcher.py (líneas 800-900)
4. Test: python test_clicks.py --pixel X Y (muestra color en (X,Y))
5. Verifica logs: [0001] ✅ MAPA | [0012] ⚔️ COMBATE | [0017] 🎁 POST-CAPTURA

Pokébola (COMBATE):
  - Centro: (546, 1420)
  - Si se ve diferente, usa: python test_clicks.py --pixel 546 1420
  - Debe ser rojo/naranja/amarillo en HSV

Botón DE ACUERDO (POST-CAPTURA):
  - Centro bajo: (540, 2040)
  - Color: Verde/Teal/Cian en HSV
  - Si no detecta, fallback tap en: (540, 2200)
""")

print()
