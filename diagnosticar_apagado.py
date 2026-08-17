#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 DIAGNÓSTICO DE APAGADO PC
============================

Detecta automáticamente POR QUÉ se apaga la PC después de primera captura.

Uso:
  python diagnosticar_apagado.py
"""

import subprocess
import sys
import os
import time
import psutil
import json
from datetime import datetime
from pathlib import Path

class DiagnosticsRunner:
    def __init__(self):
        self.resultados = {}
        self.inicio = datetime.now()
    
    def print_header(self, title):
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}\n")
    
    def test_memoria_disponible(self):
        """Prueba 1: ¿Hay suficiente RAM?"""
        self.print_header("TEST 1: Memoria Disponible")
        
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        disponible_gb = mem.available / (1024**3)
        usado_pct = mem.percent
        
        print(f"RAM Total:      {total_gb:.1f} GB")
        print(f"RAM Disponible: {disponible_gb:.1f} GB ({100-usado_pct:.0f}%)")
        print(f"RAM En Uso:     {mem.used / (1024**3):.1f} GB ({usado_pct:.0f}%)")
        
        if total_gb < 4:
            print("\n⚠️ PROBLEMA: Menos de 4GB total → LLaVA no cabe")
            self.resultados["memoria"] = "CRITICA"
            return False
        elif disponible_gb < 2:
            print("\n⚠️ PROBLEMA: Menos de 2GB disponible → OOM killer activará")
            self.resultados["memoria"] = "BAJA"
            return False
        else:
            print("\n✅ Memoria suficiente para IA + Bot")
            self.resultados["memoria"] = "OK"
            return True
    
    def test_ollama(self):
        """Prueba 2: ¿Ollama está disponible?"""
        self.print_header("TEST 2: Ollama (IA)")
        
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True,
                timeout=2,
                text=True
            )
            print(f"✅ Ollama instalado: {result.stdout.strip()}")
            self.resultados["ollama"] = "INSTALADO"
            
            # Intentar conectar
            import requests
            try:
                response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    modelos = [m["name"] for m in data.get("models", [])]
                    print(f"✅ Ollama corriendo. Modelos: {modelos}")
                    
                    # Verificar tamaño de modelo
                    if any("llava" in m for m in modelos):
                        for m in modelos:
                            if "llava" in m:
                                print(f"   → {m} (probable culpable de memoria)")
                    
                    self.resultados["ollama_server"] = "CORRIENDO"
                    return True
                else:
                    print("⚠️ Ollama no responde")
                    self.resultados["ollama_server"] = "NO_RESPONDE"
                    return False
            except:
                print("⚠️ Ollama no está actualmente corriendo (se iniciará automáticamente)")
                self.resultados["ollama_server"] = "NO_CORRIENDO"
                return True
                
        except Exception as e:
            print(f"❌ Ollama no encontrado: {e}")
            self.resultados["ollama"] = "NO_INSTALADO"
            return False
    
    def test_adb(self):
        """Prueba 3: ¿ADB conectado?"""
        self.print_header("TEST 3: ADB (Conexión Android)")
        
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                timeout=2,
                text=True
            )
            if "device" in result.stdout:
                print(f"✅ ADB conectado correctamente")
                self.resultados["adb"] = "OK"
                return True
            else:
                print(f"❌ ADB no detecta dispositivo")
                print(f"   Salida: {result.stdout}")
                self.resultados["adb"] = "SIN_DISPOSITIVO"
                return False
        except Exception as e:
            print(f"❌ ADB no encontrado: {e}")
            self.resultados["adb"] = "NO_INSTALADO"
            return False
    
    def test_dependencias(self):
        """Prueba 4: ¿Están las dependencias?"""
        self.print_header("TEST 4: Dependencias Python")
        
        reqs = {
            "cv2": "OpenCV",
            "numpy": "NumPy",
            "rich": "Rich (logging)",
            "requests": "Requests",
            "psutil": "PSUtil (memory monitoring)",
        }
        
        ok_count = 0
        for mod, desc in reqs.items():
            try:
                __import__(mod)
                print(f"✅ {desc} ({mod})")
                ok_count += 1
            except ImportError:
                print(f"❌ {desc} ({mod}) - Instala con: pip install {mod}")
        
        self.resultados["dependencias"] = f"{ok_count}/{len(reqs)}"
        return ok_count == len(reqs)
    
    def test_bot_startup(self):
        """Prueba 5: ¿El bot arranca sin errores?"""
        self.print_header("TEST 5: Arranque del Bot (sin --no-ia)")
        
        print("Intentando iniciar el bot con IA...\n")
        
        try:
            # Iniciar bot con timeout de 30s
            proc = subprocess.Popen(
                [sys.executable, "pokemon_catcher.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            # Esperar a que inicie (máx 30s)
            try:
                stdout, stderr = proc.communicate(timeout=30)
                
                if "Error" in stdout or "Error" in stderr or proc.returncode != 0:
                    print(f"❌ Bot arrancó pero tuvo error:")
                    print(f"STDOUT:\n{stdout[:500]}")
                    print(f"STDERR:\n{stderr[:500]}")
                    self.resultados["bot_startup"] = "ERROR"
                    return False
                else:
                    print(f"✅ Bot arrancó exitosamente (30s test)")
                    self.resultados["bot_startup"] = "OK"
                    return True
                    
            except subprocess.TimeoutExpired:
                # Timeout = buena señal (bot está corriendo)
                proc.kill()
                print(f"✅ Bot arrancó y está corriendo (timeout esperado)")
                self.resultados["bot_startup"] = "OK"
                return True
                
        except Exception as e:
            print(f"❌ Error al arrancar bot: {e}")
            self.resultados["bot_startup"] = "FALLO_ARRANQUE"
            return False
    
    def test_bot_no_ia(self):
        """Prueba 6: ¿El bot funciona sin IA?"""
        self.print_header("TEST 6: Arranque del Bot (con --no-ia)")
        
        print("Intentando iniciar el bot SIN IA...\n")
        
        try:
            # Iniciar bot con timeout de 30s
            proc = subprocess.Popen(
                [sys.executable, "pokemon_catcher.py", "--no-ia"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            # Esperar a que inicie (máx 30s)
            try:
                stdout, stderr = proc.communicate(timeout=30)
                
                if "Error" in stdout or "Error" in stderr or proc.returncode != 0:
                    print(f"❌ Bot --no-ia tuvo error:")
                    print(f"STDOUT:\n{stdout[:500]}")
                    print(f"STDERR:\n{stderr[:500]}")
                    self.resultados["bot_no_ia"] = "ERROR"
                    return False
                else:
                    print(f"✅ Bot --no-ia arrancó exitosamente")
                    self.resultados["bot_no_ia"] = "OK"
                    return True
                    
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"✅ Bot --no-ia arrancó y está corriendo")
                self.resultados["bot_no_ia"] = "OK"
                return True
                
        except Exception as e:
            print(f"❌ Error al arrancar bot --no-ia: {e}")
            self.resultados["bot_no_ia"] = "FALLO_ARRANQUE"
            return False
    
    def diagnosticar(self):
        """Ejecuta todos los tests"""
        self.print_header("🔍 DIAGNÓSTICO COMPLETO DE APAGADO PC")
        
        # Tests básicos
        tests = [
            ("Memoria", self.test_memoria_disponible),
            ("Ollama", self.test_ollama),
            ("ADB", self.test_adb),
            ("Dependencias", self.test_dependencias),
        ]
        
        resultados_basicos = []
        for nombre, test in tests:
            try:
                ok = test()
                resultados_basicos.append((nombre, ok))
            except Exception as e:
                print(f"❌ Error en test {nombre}: {e}")
                resultados_basicos.append((nombre, False))
        
        # Tests de arranque
        self.test_bot_no_ia()
        self.test_bot_startup()
        
        # Reporte final
        self.generar_reporte()
    
    def generar_reporte(self):
        """Genera reporte final con diagnóstico"""
        self.print_header("📊 REPORTE FINAL")
        
        print("Resultados:\n")
        for key, val in self.resultados.items():
            print(f"  {key:20} : {val}")
        
        print("\n" + "="*60)
        print("RECOMENDACIONES:")
        print("="*60 + "\n")
        
        memoria = self.resultados.get("memoria", "DESCONOCIDA")
        bot_startup = self.resultados.get("bot_startup", "DESCONOCIDA")
        bot_no_ia = self.resultados.get("bot_no_ia", "DESCONOCIDA")
        
        if memoria == "CRITICA":
            print("🔴 PROBLEMA CRÍTICO ENCONTRADO:")
            print("   → Menos de 4GB de RAM total")
            print("   → LLaVA (IA) requiere 4-6GB mínimo")
            print("\n   SOLUCIONES:")
            print("   1. Ejecutar con: python pokemon_catcher.py --no-ia")
            print("   2. Cerrar otras aplicaciones pesadas")
            print("   3. Aumentar RAM física o configurar swap")
            print("   4. Usar modelo IA más ligero (llava:7b en lugar de llava:latest)")
        
        elif memoria == "BAJA":
            print("🟠 ADVERTENCIA - MEMORIA BAJA:")
            print("   → Menos de 2GB disponibles")
            print("   → OOM killer probablemente activará al usar IA")
            print("\n   SOLUCIONES:")
            print("   1. Cerrar navegadores/aplicaciones pesadas")
            print("   2. Usar: python pokemon_catcher.py --no-ia")
            print("   3. Configurar swap en Linux (ver SAFE_MODE_FIX.md)")
        
        elif bot_startup == "ERROR":
            print("🔴 BOT ARRANCA CON ERROR (IA habilitada):")
            print("   → El error ocurre al iniciar IA")
            print("   → Confirma: python pokemon_catcher.py --no-ia")
        
        elif bot_startup == "OK" and bot_no_ia == "OK":
            print("🟡 PROBABLE CULPABLE: LLaVA (Modelo de IA)")
            print("   → Bot funciona perfectamente sin IA")
            print("   → Pero se apaga cuando IA intenta analizar")
            print("\n   SOLUCIONES:")
            print("   1. Usar: python pokemon_catcher.py --no-ia (temporal)")
            print("   2. O cambiar a modelo más ligero (llava:7b)")
            print("   3. O aumentar RAM disponible")
        
        elif bot_startup == "OK" and bot_no_ia != "OK":
            print("🔴 PROBLEMA: Bot falla incluso SIN IA")
            print("   → No es LLaVA")
            print("   → Revisar logs de error arriba")
            print("   → Posibles causas: ADB, conexión, dependencias")
        
        else:
            print("✅ TODOS LOS TESTS PASARON")
            print("   → Sin problemas detectados")
            print("   → Ejecuta: python pokemon_catcher.py")
        
        print("\n" + "="*60)
        print("PRÓXIMOS PASOS:")
        print("="*60)
        print("""
1. Ejecuta el bot con: python pokemon_catcher.py --no-ia

2. Monitorea en otra terminal:
   watch -n 1 'free -h && ps aux | grep python'

3. Si funciona 30+ minutos sin apagarse:
   → Culpable es LLaVA
   → Lee SAFE_MODE_FIX.md para soluciones permanentes

4. Si se sigue apagando:
   → Problema es otro
   → Envía los logs al soporte técnico
""")


if __name__ == "__main__":
    # Verificar psutil
    try:
        import psutil
    except ImportError:
        print("⚠️ Instalando psutil (necesario para diagnóstico)...")
        subprocess.run([sys.executable, "-m", "pip", "install", "psutil"], check=True)
        import psutil
    
    runner = DiagnosticsRunner()
    runner.diagnosticar()
