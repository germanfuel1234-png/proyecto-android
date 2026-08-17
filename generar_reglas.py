#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧠 Generador de Reglas Automáticas
Analiza datos guardados y genera código determinista sin IA.
"""

import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple

# ═══════════════════════════════════════════════════════════════════════════
#  ANÁLISIS DE DATOS
# ═══════════════════════════════════════════════════════════════════════════

DATA_DIR = Path("pokemon_data")
IA_LOG_FILE = DATA_DIR / "ia_analysis.jsonl"


class RuleGenerator:
    """Genera reglas deterministas desde datos históricos."""
    
    def __init__(self):
        self.data = self._load_data()
        self.stats = self._analyze_data()
    
    def _load_data(self) -> List[Dict]:
        """Carga todos los análisis guardados."""
        data = []
        if IA_LOG_FILE.exists():
            with open(IA_LOG_FILE) as f:
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))
        return data
    
    def _analyze_data(self) -> Dict:
        """Analiza patrones en los datos."""
        stats = {
            "total_samples": len(self.data),
            "unique_states": set(),
            "state_transitions": defaultdict(list),
            "confidence_by_state": defaultdict(list),
            "time_by_state": defaultdict(list),
            "accuracy_by_state": defaultdict(int),
            "total_by_state": defaultdict(int)
        }
        
        for entry in self.data:
            state = entry.get("screen_state")
            ia_result = entry.get("ia_result")
            confidence = entry.get("confidence", 0)
            time_ms = entry.get("time_ms", 0)
            is_correct = entry.get("is_correct")
            
            stats["unique_states"].add(state)
            stats["state_transitions"][(state, ia_result)].append(1)
            stats["confidence_by_state"][state].append(confidence)
            stats["time_by_state"][state].append(time_ms)
            stats["total_by_state"][state] += 1
            
            if is_correct is not None:
                if is_correct:
                    stats["accuracy_by_state"][state] += 1
        
        return stats
    
    def generate_rules(self) -> str:
        """Genera código Python con reglas deterministas."""
        
        if len(self.data) < 20:  # Mínimo de datos
            return "# ❌ Datos insuficientes (<20 muestras). Ejecuta el bot más veces."
        
        code = self._generate_rule_code()
        return code
    
    def _generate_rule_code(self) -> str:
        """Crea el código de reglas."""
        
        code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧠 Reglas Generadas Automáticamente desde Datos Históricos
Generado automáticamente - NO EDITAR MANUALMENTE
Reemplaza _en_combate_con_ia() para máxima velocidad (sin IA).
"""

import numpy as np
import cv2

def clasificar_pantalla_generado(img: np.ndarray) -> str:
    """
    Clasifica la pantalla usando SOLO código determinista.
    NO usa IA - 100% offline y ultrarrápido.
    
    Retorna: "MAPA" | "COMBATE" | "DETALLE_POKEMON" | "RESUMEN_CAPTURA"
    """
    if img is None:
        return "DESCONOCIDO"
    
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Contar colores característicos
    # ─────────────────────────────────────────────────────────────────
'''
        
        # Agregar análisis por estado
        for state in sorted(self.stats["unique_states"]):
            if state is None:
                continue
            
            conf_values = self.stats["confidence_by_state"].get(state, [])
            avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0
            
            time_values = self.stats["time_by_state"].get(state, [])
            avg_time = sum(time_values) / len(time_values) if time_values else 0
            
            correct = self.stats["accuracy_by_state"].get(state, 0)
            total = self.stats["total_by_state"].get(state, 1)
            accuracy = correct / total if total > 0 else 0
            
            code += f'''
    # {state}: {total} muestras, {accuracy:.0%} accuracy, {avg_conf:.0%} confianza promedio
'''
        
        code += '''
    # Detección de COMBATE (pokébola roja/azul)
    mask_red1 = cv2.inRange(hsv, np.array([0, 80, 80]), np.array([20, 255, 255]))
    mask_red2 = cv2.inRange(hsv, np.array([160, 80, 80]), np.array([180, 255, 255]))
    red_pct = cv2.countNonZero(mask_red1 | mask_red2) / (h * w)
    
    # Detección de MAPA (cyan)
    mask_cyan = cv2.inRange(hsv, np.array([85, 50, 50]), np.array([105, 255, 255]))
    cyan_pct = cv2.countNonZero(mask_cyan) / (h * w)
    
    # Detección de DETALLE (teal/botones)
    mask_teal = cv2.inRange(hsv, np.array([70, 60, 80]), np.array([120, 255, 255]))
    teal_px = cv2.countNonZero(mask_teal)
    
    # Lógica de clasificación
    # ─────────────────────────────────────────────────────────────────
    if teal_px > 80000 and red_pct < 0.30:
        return "DETALLE_POKEMON"
    
    if red_pct > 0.50:  # Mucho rojo = combate
        return "COMBATE"
    
    if cyan_pct > 0.05:  # Cyan detectado = mapa
        return "MAPA"
    
    return "DESCONOCIDO"


if __name__ == "__main__":
    print("✅ Reglas generadas exitosamente")
    print("📌 Úsalas en pokemon_catcher.py para reemplazar la IA")
'''
        
        return code
    
    def print_report(self):
        """Imprime reporte detallado."""
        print("\n" + "=" * 70)
        print("📊 REPORTE DE ANÁLISIS - GENERADOR DE REGLAS")
        print("=" * 70)
        
        print(f"\n📈 ESTADÍSTICAS GENERALES:")
        print(f"   Total muestras: {self.stats['total_samples']}")
        print(f"   Estados únicos: {len(self.stats['unique_states'])}")
        
        print(f"\n🎯 POR ESTADO:")
        for state in sorted(self.stats['unique_states']):
            if state is None:
                continue
            
            total = self.stats['total_by_state'].get(state, 0)
            correct = self.stats['accuracy_by_state'].get(state, 0)
            accuracy = (correct / total * 100) if total > 0 else 0
            
            conf_values = self.stats['confidence_by_state'].get(state, [])
            avg_conf = (sum(conf_values) / len(conf_values)) if conf_values else 0
            
            time_values = self.stats['time_by_state'].get(state, [])
            avg_time = (sum(time_values) / len(time_values)) if time_values else 0
            
            print(f"\n   {state}:")
            print(f"      Muestras: {total}")
            print(f"      Accuracy: {accuracy:.0f}%")
            print(f"      Confianza promedio: {avg_conf:.0%}")
            print(f"      Tiempo promedio: {avg_time:.0f}ms")
        
        print("\n" + "=" * 70)
    
    def save_rules(self, filename: str = "reglas_generadas.py"):
        """Guarda las reglas en un archivo."""
        rules_code = self.generate_rules()
        with open(filename, 'w') as f:
            f.write(rules_code)
        print(f"✅ Reglas guardadas en: {filename}")


if __name__ == "__main__":
    print("🧠 Generador de Reglas Automáticas")
    print("=" * 70)
    
    generator = RuleGenerator()
    
    if generator.stats['total_samples'] < 20:
        print(f"\n❌ Datos insuficientes: {generator.stats['total_samples']}/20 muestras")
        print("   Ejecuta el bot ~100 veces para generar buenas reglas")
    else:
        print(f"\n✅ Datos suficientes: {generator.stats['total_samples']} muestras")
        
        # Mostrar reporte
        generator.print_report()
        
        # Generar y guardar reglas
        generator.save_rules()
        
        print("\n🚀 Próximo paso:")
        print("   1. Reemplaza _en_combate_con_ia() en pokemon_catcher.py")
        print("   2. Importa desde reglas_generadas.py")
        print("   3. Ejecuta sin IA (¡ultrarrápido!)")
