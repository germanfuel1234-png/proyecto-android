#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧹 Limpiador de Logs Inteligente
Elimina redundancias manteniendo:
- Todas las entradas INCORRECTAS (para entrenar IA)
- Todas con baja confianza (< 50%)
- Solo 5 ejemplos de cada patrón repetitivo
"""

import json
from collections import defaultdict
from pathlib import Path
import shutil

DATA_DIR = Path("pokemon_data")
IA_LOG_FILE = DATA_DIR / "ia_analysis.jsonl"
BACKUP_FILE = DATA_DIR / "ia_analysis.jsonl.backup"

def limpiar_logs():
    """Limpia logs redundantes de forma inteligente."""
    
    if not IA_LOG_FILE.exists():
        print("❌ No hay archivo de logs")
        return
    
    # Hacer backup
    shutil.copy(IA_LOG_FILE, BACKUP_FILE)
    print(f"✅ Backup creado: ia_analysis.jsonl.backup")
    
    logs = []
    with open(IA_LOG_FILE, 'r') as f:
        for line in f:
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    
    print(f"\n📊 Procesando {len(logs)} entradas...\n")
    
    # Categorizar logs
    incorrectas = [log for log in logs if log.get('is_correct') is False]
    baja_confianza = [log for log in logs if log.get('confidence', 1.0) < 0.5]
    
    print(f"🛡️  Protegidas:")
    print(f"   • Incorrectas (críticas): {len(incorrectas)}")
    print(f"   • Baja confianza: {len(baja_confianza)}\n")
    
    # Marcar logs a mantener
    mantener_indices = set()
    
    # 1. Mantener todas las incorrectas
    for i, log in enumerate(logs):
        if log.get('is_correct') is False:
            mantener_indices.add(i)
    
    # 2. Mantener todas con baja confianza
    for i, log in enumerate(logs):
        if log.get('confidence', 1.0) < 0.5:
            mantener_indices.add(i)
    
    # 3. Para patrones repetitivos: mantener solo 5 ejemplos
    patrones = defaultdict(list)
    for i, log in enumerate(logs):
        pattern = (log.get('screen_state'), log.get('ia_result'))
        patrones[pattern].append(i)
    
    print(f"📋 Patrones de estado:")
    eliminados_por_patron = 0
    
    for (state, result), indices in patrones.items():
        mantener = min(5, len(indices))
        
        if len(indices) > 5:
            # Mantener los primeros 5
            for j in range(mantener):
                mantener_indices.add(indices[j])
            
            eliminated = len(indices) - mantener
            eliminados_por_patron += eliminated
            print(f"   • {state:20} → {result:15}: {len(indices)} → {mantener} (+{eliminated} eliminadas)")
        else:
            # Mantener todos
            for idx in indices:
                mantener_indices.add(idx)
            print(f"   • {state:20} → {result:15}: {len(indices)} ✅")
    
    # Escribir logs filtrados
    logs_filtrados = [logs[i] for i in sorted(mantener_indices)]
    
    with open(IA_LOG_FILE, 'w') as f:
        for log in logs_filtrados:
            f.write(json.dumps(log) + '\n')
    
    print(f"\n{'='*60}")
    print(f"✨ LIMPIEZA COMPLETADA")
    print(f"{'='*60}")
    print(f"Antes: {len(logs)} entradas")
    print(f"Después: {len(logs_filtrados)} entradas")
    print(f"Eliminadas: {len(logs) - len(logs_filtrados)} ({(len(logs)-len(logs_filtrados))/len(logs)*100:.1f}%)")
    print(f"\n💾 Nuevo tamaño del archivo: ~{len(logs_filtrados)*200//1024}KB (aproximado)")
    print(f"📦 Backup disponible: ia_analysis.jsonl.backup")
    print(f"\n✅ Los logs están OPTIMIZADOS para máxima precisión")

if __name__ == "__main__":
    limpiar_logs()
