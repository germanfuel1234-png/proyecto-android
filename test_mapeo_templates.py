#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 TEST: Mapeo Template → Estado

Valida que los templates se mapeen correctamente a estados.
"""

def test_mapeo_templates():
    """Prueba la lógica de mapeo de templates a estados."""
    
    # Simular detección de templates
    templates = [
        ("pokemon_enelmapa.jpg", 0.73),
        ("confirmacion.jpg", 0.89),
        ("camara.jpg", 0.75),
        ("pokeball_template.jpg", 0.65),  # Bajo threshold, no debería mapear
    ]
    
    expected = {
        "pokemon_enelmapa.jpg": ("✅ MAPA", "pokemon detectado"),
        "confirmacion.jpg": ("🎁 POST-CAPTURA", "confirmación"),
        "camara.jpg": ("⚔️  COMBATE", "cámara"),
        "pokeball_template.jpg": (None, None),  # Threshold bajo
    }
    
    print("🧪 TEST: Mapeo Template → Estado")
    print("=" * 60)
    
    all_pass = True
    for template_name, confianza in templates:
        # Aplicar lógica de mapeo (>0.70 threshold)
        if confianza > 0.70:
            if "pokemon" in template_name.lower() and "mapa" in template_name.lower():
                estado = "✅ MAPA"
                desc = f"pokemon detectado {confianza:.0%}"
            elif "confirmacion" in template_name.lower():
                estado = "🎁 POST-CAPTURA"
                desc = f"confirmación {confianza:.0%}"
            elif "camara" in template_name.lower():
                estado = "⚔️  COMBATE"
                desc = f"cámara {confianza:.0%}"
            else:
                estado = None
                desc = None
        else:
            estado = None
            desc = None
        
        # Validar
        expected_state, expected_desc_prefix = expected[template_name]
        
        if estado == expected_state:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
            all_pass = False
        
        print(f"\n{status} | {template_name} ({confianza:.0%})")
        print(f"   Esperado: {expected_state}")
        print(f"   Obtuvo:   {estado}")
        if desc:
            print(f"   Detalles: {desc}")
    
    print("\n" + "=" * 60)
    if all_pass:
        print("✅ TODOS LOS TESTS PASARON")
        return 0
    else:
        print("❌ ALGUNOS TESTS FALLARON")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(test_mapeo_templates())
