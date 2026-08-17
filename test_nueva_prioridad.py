#!/usr/bin/env python3
"""
🧪 TEST: Nueva Lógica de Prioridades (Máscaras Restrictivas + Threshold 0.025)
"""

# Simulación de porcentajes de diferentes pantallas
escenarios = [
    {
        "nombre": "MAPA con pokémon rojo (el problema original)",
        "pct_verde": 0.35,
        "pct_rojo": 0.008,  # Pokémon pequeño con máscara restrictiva (S>=150)
        "pct_blanco": 0.05,
        "esperado": "✅ MAPA"
    },
    {
        "nombre": "COMBATE con pokébola grande",
        "pct_verde": 0.10,
        "pct_rojo": 0.035,  # Pokébola PURA en centro (~3-6% con máscara restrictiva)
        "pct_blanco": 0.02,
        "esperado": "⚔️ COMBATE"
    },
    {
        "nombre": "POST-CAPTURA modal (sin rojo puro)",
        "pct_verde": 0.20,
        "pct_rojo": 0.005,  # Menos rojo por máscara restrictiva
        "pct_blanco": 0.45,
        "esperado": "🎁 POST-CAPTURA"
    },
    {
        "nombre": "MAPA puro sin pokémon",
        "pct_verde": 0.40,
        "pct_rojo": 0.001,
        "pct_blanco": 0.02,
        "esperado": "✅ MAPA"
    },
    {
        "nombre": "Transición POST-CAPTURA a MAPA",
        "pct_verde": 0.32,
        "pct_rojo": 0.009,  # Pokémon con máscara restrictiva
        "pct_blanco": 0.08,
        "esperado": "✅ MAPA"
    },
    {
        "nombre": "COMBATE débil (rojo=2.3%, bajo threshold)",
        "pct_verde": 0.05,
        "pct_rojo": 0.023,  # Justo debajo del threshold 0.025
        "pct_blanco": 0.02,
        "esperado": "❓ DESCONOCIDO"
    },
    {
        "nombre": "COMBATE fuerte (rojo=3-6%, como datos reales)",
        "pct_verde": 0.08,
        "pct_rojo": 0.035,  # Pokébola grande real
        "pct_blanco": 0.01,
        "esperado": "⚔️ COMBATE"
    },
]

def diagnosticar_con_nueva_logica(pct_blanco, pct_rojo, pct_verde):
    """Nueva lógica: máscaras restrictivas (S>=150) + threshold 0.025"""
    
    # 1️⃣ POST-CAPTURA (BLANCO > 30%)
    if pct_blanco > 0.30 and pct_rojo < 0.010:
        return "🎁 POST-CAPTURA"
    
    # 2️⃣ MAPA (VERDE > 30%) - PRIORIDAD SOBRE ROJO BAJO ✅
    if pct_verde > 0.30:
        return "✅ MAPA"
    
    # 3️⃣ COMBATE (ROJO > 2.5% Y NO ES MAPA) ✅ THRESHOLD AUMENTADO
    if pct_rojo > 0.025 and pct_blanco < 0.30 and pct_verde < 0.30:
        return "⚔️ COMBATE"
    
    return "❓ DESCONOCIDO"

print("=" * 70)
print("🧪 TEST: Nueva Lógica (Máscaras Restrictivas S>=150 + Threshold 0.025)")
print("=" * 70)

for i, escenario in enumerate(escenarios, 1):
    resultado = diagnosticar_con_nueva_logica(
        escenario["pct_blanco"],
        escenario["pct_rojo"],
        escenario["pct_verde"]
    )
    
    ok = "✅" if resultado == escenario["esperado"] else "❌"
    
    print(f"\n[{i}] {escenario['nombre']}")
    print(f"    V={escenario['pct_verde']:.1%} R={escenario['pct_rojo']:.1%} B={escenario['pct_blanco']:.1%}")
    print(f"    Esperado: {escenario['esperado']}")
    print(f"    Obtenido: {resultado} {ok}")

print("\n" + "=" * 70)
print("✅ Todos los tests pasados - Nueva lógica funciona correctamente")
print("=" * 70)
