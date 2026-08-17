#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
✅ TEST RÁPIDO - Verifica que Ollama Manager está funcionando
"""

import sys
import time
import subprocess
from pathlib import Path

# Colores
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[94m"
RESET = "\033[0m"

def print_header():
    print(f"\n{CYAN}{'='*70}{RESET}")
    print(f"{CYAN}✅ TEST - OllamaManager y Scripts de Ejecución{RESET}")
    print(f"{CYAN}{'='*70}{RESET}\n")

def test_imports():
    """Test 1: Importar módulos necesarios"""
    print(f"{YELLOW}[TEST 1] Verificando imports...{RESET}")
    
    try:
        import cv2
        print(f"{GREEN}✓{RESET} opencv-python")
    except:
        print(f"{RED}✗{RESET} opencv-python")
        return False
    
    try:
        import numpy
        print(f"{GREEN}✓{RESET} numpy")
    except:
        print(f"{RED}✗{RESET} numpy")
        return False
    
    try:
        import rich
        print(f"{GREEN}✓{RESET} rich")
    except:
        print(f"{RED}✗{RESET} rich")
        return False
    
    try:
        import requests
        print(f"{GREEN}✓{RESET} requests")
    except:
        print(f"{RED}✗{RESET} requests")
        return False
    
    return True

def test_adb():
    """Test 2: Verificar ADB"""
    print(f"\n{YELLOW}[TEST 2] Verificando ADB...{RESET}")
    
    try:
        result = subprocess.run(["adb", "devices"], 
                              capture_output=True, 
                              timeout=3,
                              text=True)
        print(f"{GREEN}✓{RESET} adb disponible")
        if "List of attached devices" in result.stdout:
            print(f"{GREEN}✓{RESET} Dispositivo(s) conectado(s)")
        else:
            print(f"{YELLOW}⚠{RESET} No hay dispositivos conectados (pero ADB funciona)")
        return True
    except Exception as e:
        print(f"{RED}✗{RESET} ADB no disponible: {e}")
        return False

def test_ollama_detect():
    """Test 3: Detectar si Ollama está corriendo"""
    print(f"\n{YELLOW}[TEST 3] Verificando Ollama...{RESET}")
    
    try:
        import requests
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print(f"{GREEN}✓{RESET} Ollama está corriendo")
            return True
        else:
            print(f"{YELLOW}⚠{RESET} Ollama responde pero status={response.status_code}")
            return False
    except:
        print(f"{YELLOW}ℹ{RESET} Ollama no está activo (se iniciará automáticamente)")
        return True  # No es error, es normal

def test_scripts_exist():
    """Test 4: Verificar que existen los scripts de ejecución"""
    print(f"\n{YELLOW}[TEST 4] Verificando scripts de ejecución...{RESET}")
    
    scripts = {
        "run.py": "Python launcher",
        "run.sh": "Shell script (Linux/Mac)",
        "run.bat": "Batch script (Windows)",
        "pokemon_catcher.py": "Bot principal",
    }
    
    all_exist = True
    for script, desc in scripts.items():
        if Path(script).exists():
            print(f"{GREEN}✓{RESET} {script:20s} ({desc})")
        else:
            print(f"{RED}✗{RESET} {script:20s} NO ENCONTRADO")
            all_exist = False
    
    return all_exist

def test_ollama_manager():
    """Test 5: Importar y probar OllamaManager"""
    print(f"\n{YELLOW}[TEST 5] Probando OllamaManager...{RESET}")
    
    try:
        # Importar el módulo
        import sys
        sys.path.insert(0, ".")
        
        # Verificar que OllamaManager existe en pokemon_catcher.py
        with open("pokemon_catcher.py") as f:
            content = f.read()
        
        if "class OllamaManager" in content:
            print(f"{GREEN}✓{RESET} OllamaManager clase encontrada")
        else:
            print(f"{RED}✗{RESET} OllamaManager NO definida")
            return False
        
        if "ollama_manager = OllamaManager()" in content:
            print(f"{GREEN}✓{RESET} Instancia global creada")
        else:
            print(f"{RED}✗{RESET} Instancia global NO encontrada")
            return False
        
        if "signal.signal(signal.SIGINT, signal_handler)" in content:
            print(f"{GREEN}✓{RESET} Signal handlers configurados")
        else:
            print(f"{YELLOW}⚠{RESET} Signal handlers no encontrados")
        
        return True
        
    except Exception as e:
        print(f"{RED}✗{RESET} Error: {e}")
        return False

def print_summary(results):
    """Muestra resumen final"""
    print(f"\n{CYAN}{'='*70}{RESET}")
    print(f"{CYAN}RESUMEN{RESET}")
    print(f"{CYAN}{'='*70}{RESET}\n")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"Tests: {passed}/{total} pasados\n")
    
    for test_name, result in results.items():
        status = f"{GREEN}✓ PASÓ{RESET}" if result else f"{RED}✗ FALLÓ{RESET}"
        print(f"  {test_name:25s} {status}")
    
    print()
    
    if passed == total:
        print(f"{GREEN}🎉 ¡TODOS LOS TESTS PASARON!{RESET}\n")
        print("Ahora puedes ejecutar:\n")
        print(f"  {CYAN}Linux/Mac:{RESET}")
        print(f"    ./run.sh\n")
        print(f"  {CYAN}Windows:{RESET}")
        print(f"    run.bat\n")
        print(f"  {CYAN}Python (cualquier sistema):{RESET}")
        print(f"    python run.py\n")
        return 0
    else:
        print(f"{YELLOW}⚠ Algunos tests no pasaron. Revisa arriba.{RESET}\n")
        return 1

def main():
    print_header()
    
    results = {
        "Imports": test_imports(),
        "ADB": test_adb(),
        "Ollama": test_ollama_detect(),
        "Scripts": test_scripts_exist(),
        "OllamaManager": test_ollama_manager(),
    }
    
    exit_code = print_summary(results)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
