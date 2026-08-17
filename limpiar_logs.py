#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧹 Analizador de Logs Redundantes
Detecta qué logs son innecesarios y los elimina para mayor precisión
"""

import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("pokemon_data")
IA_LOG_FILE = DATA_DIR / "ia_analysis.jsonl"

def analizar_logs():
    """Analiza los logs y detecta redundancias."""
    
    if not IA_LOG_FILE.exists():
        print("❌ No hay archivo de logs aún")
        return
    
    logs = []
    duplicados = defaultdict(int)
    patrones_redundantes = defaultdict(list)
    
    # Leer todos los logs
    with open(IA_LOG_FILE, 'r') as f:
        for i, line in enumerate(f, 1):
            try:
                log = json.loads(line)
                logs.append(log)
            except json.JSONDecodeError:
                print(f"⚠️  Línea {i} corrupta, saltando...")
    
    print(f"\n📊 ANÁLISIS DE LOGS")
    print(f"{'='*60}")
    print(f"Total de entradas: {len(logs)}\n")
    
    # 1. Detectar entradas duplicadas (mismo screenshot_hash)
    print("🔍 BÚSQUEDA 1: Entradas duplicadas (mismo screenshot)")
    print(f"{'-'*60}")
    
    hash_counts = defaultdict(list)
    for idx, log in enumerate(logs):
        hash_key = log.get('screenshot_hash', 'unknown')
        hash_counts[hash_key].append(idx)
    
    duplicados_encontrados = {k: v for k, v in hash_counts.items() if len(v) > 1}
    
    if duplicados_encontrados:
        total_duplicados = sum(len(v) - 1 for v in duplicados_encontrados.values())
        print(f"⚠️  {len(duplicados_encontrados)} screenshots aparecen múltiples veces")
        print(f"   → Total de ENTRADAS DUPLICADAS: {total_duplicados}")
        print(f"   → Puedes eliminarlas sin perder información\n")
    else:
        print("✅ No hay duplicados de screenshot\n")
    
    # 2. Detectar patrones repetitivos (mismo estado → mismo resultado)
    print("🔍 BÚSQUEDA 2: Patrones repetitivos (estado → resultado)")
    print(f"{'-'*60}")
    
    pattern_groups = defaultdict(list)
    for idx, log in enumerate(logs):
        pattern = (log.get('screen_state'), log.get('ia_result'))
        pattern_groups[pattern].append(idx)
    
    print(f"Patrones únicos encontrados: {len(pattern_groups)}\n")
    
    repetidos = {k: v for k, v in pattern_groups.items() if len(v) > 10}
    if repetidos:
        print(f"⚠️  Patrones que se repiten más de 10 veces:")
        for (state, result), indices in sorted(repetidos.items(), key=lambda x: -len(x[1])):
            print(f"   • {state:20} → {result:15} (aparece {len(indices)} veces)")
            if len(indices) > 20:
                print(f"     → Podrías guardar solo 3-5 ejemplos, eliminar {len(indices)-5} entradas")
        print()
    else:
        print("✅ No hay patrones excesivamente repetidos\n")
    
    # 3. Detectar baja confianza
    print("🔍 BÚSQUEDA 3: Análisis de baja confianza")
    print(f"{'-'*60}")
    
    low_confidence = [log for log in logs if log.get('confidence', 1.0) < 0.5]
    if low_confidence:
        print(f"⚠️  {len(low_confidence)} entradas con confianza < 50%")
        print(f"   → Estas son especialmente útiles para mejorar IA")
        print(f"   → Mantén TODAS estas\n")
    else:
        print("✅ Todas las entradas tienen buena confianza\n")
    
    # 4. Detectar entradas sin feedback (is_correct = None)
    print("🔍 BÚSQUEDA 4: Entradas sin validación")
    print(f"{'-'*60}")
    
    sin_validacion = [log for log in logs if log.get('is_correct') is None]
    correctas = [log for log in logs if log.get('is_correct') is True]
    incorrectas = [log for log in logs if log.get('is_correct') is False]
    
    print(f"📈 Validación de IA:")
    print(f"   • Sin validar: {len(sin_validacion)}")
    print(f"   • Correctas:   {len(correctas)} ✅")
    print(f"   • Incorrectas: {len(incorrectas)} ❌")
    
    if len(incorrectas) > 0:
        print(f"\n   ⚠️  Hay {len(incorrectas)} entradas INCORRECTAS")
        print(f"      Estas son CRÍTICAS para entrenar IA")
        print(f"      Mantén TODAS estas para que IA aprenda\n")
    
    # 5. Estadísticas de tiempo
    print("🔍 BÚSQUEDA 5: Estadísticas de tiempo")
    print(f"{'-'*60}")
    
    tiempos = [log.get('time_ms', 0) for log in logs]
    if tiempos:
        promedio = sum(tiempos) / len(tiempos)
        minimo = min(tiempos)
        maximo = max(tiempos)
        print(f"   • Tiempo promedio: {promedio:.1f}ms")
        print(f"   • Tiempo mínimo:   {minimo}ms")
        print(f"   • Tiempo máximo:   {maximo}ms")
        
        lentos = [log for log in logs if log.get('time_ms', 0) > 500]
        if lentos:
            print(f"\n   ⚠️  {len(lentos)} análisis tardaron > 500ms")
            print(f"      Estos son buenos para optimización\n")
    
    # RECOMENDACIÓN
    print("\n" + "="*60)
    print("💡 RECOMENDACIÓN DE LIMPIEZA")
    print("="*60)
    
    total_a_limpiar = 0
    
    if duplicados_encontrados:
        duplicados_count = sum(len(v) - 1 for v in duplicados_encontrados.values())
        total_a_limpiar += duplicados_count
        print(f"1. Eliminar {duplicados_count} duplicados")
    
    for (state, result), indices in sorted(repetidos.items(), key=lambda x: -len(x[1])):
        if len(indices) > 20:
            a_eliminar = len(indices) - 5
            total_a_limpiar += a_eliminar
            print(f"2. Del patrón '{state}→{result}': mantén 5, elimina {a_eliminar}")
    
    print(f"\n✨ TOTAL A ELIMINAR: ~{total_a_limpiar} entradas")
    print(f"   Reducción: {(total_a_limpiar/len(logs)*100):.1f}%")
    print(f"   Tamaño actual: ~23KB → ~{int(23 * (1 - total_a_limpiar/len(logs)))}KB")

if __name__ == "__main__":
    analizar_logs()
