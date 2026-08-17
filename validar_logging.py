#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
✅ SCRIPT DE VALIDACIÓN DEL SISTEMA DE LOGGING
Verifica que todo está configurado correctamente
"""

import json
import sys
from pathlib import Path

# Colores para terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def check(condition, message):
    """Verifica una condición y imprime resultado."""
    if condition:
        print(f"{GREEN}✓{RESET} {message}")
        return True
    else:
        print(f"{RED}✗{RESET} {message}")
        return False

def main():
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}✅ VALIDACIÓN DEL SISTEMA DE LOGGING{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")
    
    all_ok = True
    
    # ─────────────────────────────────────────────────────────────────────
    # 1. VERIFICAR MÓDULOS
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{YELLOW}[1] VERIFICANDO MÓDULOS...{RESET}")
    
    try:
        from analysis_logger import AnalysisLogger
        check(True, "analysis_logger.py importable")
    except Exception as e:
        check(False, f"analysis_logger.py: {e}")
        all_ok = False
    
    try:
        import numpy as np
        check(True, "NumPy disponible")
    except:
        check(False, "NumPy no disponible")
        all_ok = False
    
    try:
        import cv2
        check(True, "OpenCV disponible")
    except:
        check(False, "OpenCV no disponible")
        all_ok = False
    
    # ─────────────────────────────────────────────────────────────────────
    # 2. VERIFICAR DIRECTORIOS
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{YELLOW}[2] VERIFICANDO DIRECTORIOS...{RESET}")
    
    data_dir = Path("pokemon_data")
    if check(data_dir.exists() or data_dir.mkdir(exist_ok=True), "Directorio pokemon_data/ existe"):
        pass
    else:
        all_ok = False
    
    # ─────────────────────────────────────────────────────────────────────
    # 3. VERIFICAR LOGGER
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{YELLOW}[3] PROBANDO LOGGER...{RESET}")
    
    try:
        from analysis_logger import AnalysisLogger
        
        # Crear instancia
        logger = AnalysisLogger()
        check(True, "AnalysisLogger instanciable")
        
        # Probar logging
        logger.log_ia_analysis(
            screenshot_hash="test123",
            screen_state="MAPA",
            ia_result="MAPA",
            time_ms=2500,
            confidence=0.95,
            is_correct=True
        )
        check(True, "log_ia_analysis() funciona")
        
        # Verificar que se guardó
        ia_log = data_dir / "ia_analysis.jsonl"
        if ia_log.exists():
            with open(ia_log) as f:
                lines = f.readlines()
            check(len(lines) > 0, f"Datos guardados en ia_analysis.jsonl ({len(lines)} líneas)")
        else:
            check(False, "ia_analysis.jsonl no se creó")
            all_ok = False
        
        # Probar error logging
        logger.log_error(
            error_type="test_error",
            screen_state="MAPA",
            error_message="Este es un error de prueba",
            user_fix="Presionó BACK"
        )
        check(True, "log_error() funciona")
        
        # Probar stats
        stats = logger.get_stats()
        check(
            stats['total_ia_analyses'] > 0,
            f"get_stats() funciona (total_ia_analyses={stats['total_ia_analyses']})"
        )
        
    except Exception as e:
        check(False, f"Error en logger: {e}")
        all_ok = False
    
    # ─────────────────────────────────────────────────────────────────────
    # 4. VERIFICAR ARCHIVOS DE DATOS
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{YELLOW}[4] VERIFICANDO ARCHIVOS DE DATOS...{RESET}")
    
    ia_log = data_dir / "ia_analysis.jsonl"
    errors_log = data_dir / "errors.jsonl"
    
    if ia_log.exists():
        with open(ia_log) as f:
            lines = f.readlines()
        size_kb = ia_log.stat().st_size / 1024
        check(True, f"ia_analysis.jsonl ({len(lines)} líneas, {size_kb:.1f}KB)")
        
        # Mostrar última entrada
        if lines:
            try:
                last = json.loads(lines[-1])
                print(f"   Última entrada: {last.get('screen_state')} → {last.get('ia_result')}")
            except:
                pass
    else:
        print(f"{YELLOW}ℹ{RESET} ia_analysis.jsonl vacío (se creará después del primer análisis)")
    
    if errors_log.exists():
        with open(errors_log) as f:
            lines = f.readlines()
        size_kb = errors_log.stat().st_size / 1024
        check(True, f"errors.jsonl ({len(lines)} líneas, {size_kb:.1f}KB)")
    else:
        print(f"{YELLOW}ℹ{RESET} errors.jsonl vacío (se crea solo si hay errores)")
    
    # ─────────────────────────────────────────────────────────────────────
    # 5. VERIFICAR pokemon_catcher.py
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{YELLOW}[5] VERIFICANDO INTEGRACIÓN EN pokemon_catcher.py...{RESET}")
    
    try:
        with open("pokemon_catcher.py") as f:
            content = f.read()
        
        check("from analysis_logger import AnalysisLogger" in content,
              "Import de AnalysisLogger presente")
        
        check("LOGGING_DISPONIBLE" in content,
              "Flag LOGGING_DISPONIBLE presente")
        
        check("logger.log_ia_analysis" in content,
              "Llamadas a log_ia_analysis() presentes")
        
    except Exception as e:
        check(False, f"No se pudo leer pokemon_catcher.py: {e}")
        all_ok = False
    
    # ─────────────────────────────────────────────────────────────────────
    # 6. VERIFICAR SCRIPTS
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{YELLOW}[6] VERIFICANDO SCRIPTS...{RESET}")
    
    check(Path("generar_reglas.py").exists(), "generar_reglas.py existe")
    check(Path("LEARNING_SYSTEM.md").exists(), "LEARNING_SYSTEM.md existe")
    
    # ─────────────────────────────────────────────────────────────────────
    # RESUMEN
    # ─────────────────────────────────────────────────────────────────────
    print(f"\n{BLUE}{'='*70}{RESET}")
    
    if all_ok:
        print(f"{GREEN}✅ VALIDACIÓN EXITOSA - TODO ESTÁ LISTO{RESET}")
        print(f"\n{YELLOW}Próximos pasos:{RESET}")
        print(f"  1. Ejecuta: python pokemon_catcher.py")
        print(f"  2. Deja que se acumulen ~50 capturas")
        print(f"  3. Ejecuta: python generar_reglas.py")
        print(f"  4. Verás estadísticas y reglas generadas")
        return 0
    else:
        print(f"{RED}❌ ALGUNAS VERIFICACIONES FALLARON{RESET}")
        print(f"\n{YELLOW}Lee los errores arriba y corrígelos.{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
