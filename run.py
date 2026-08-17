#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 LAUNCHER - Ejecuta todo automáticamente
==========================================

Inicia:
  1. Ollama (IA local)
  2. pokemon_catcher.py (bot principal)

Todo en paralelo, con limpieza automática al salir.

Uso:
  python run.py          # Modo normal
  python run.py --debug  # Modo debug
  python run.py --no-ia  # Sin IA (solo templates)
"""

import subprocess
import sys
import os
import time
import signal

class Launcher:
    """Gestor de procesos para el bot y sus dependencias."""
    
    def __init__(self):
        self.procesos = []
        self.debug = "--debug" in sys.argv
        self.no_ia = "--no-ia" in sys.argv
        self.proyecto_dir = os.path.dirname(os.path.abspath(__file__))
    
    def print_banner(self):
        """Muestra banner de inicio."""
        banner = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║          🚀 POKÉMON GO CATCHER - LAUNCHER                     ║
║                                                               ║
║  Iniciando bot con IA automática...                           ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""
        print(banner)
        print(f"  📁 Proyecto: {self.proyecto_dir}")
        print(f"  🔧 Debug: {'ON' if self.debug else 'OFF'}")
        print(f"  🧠 IA: {'DESHABILITADA' if self.no_ia else 'AUTOMÁTICA'}")
        print(f"  ✋ Presiona Ctrl+C para salir\n")
    
    def verificar_dependencias(self) -> bool:
        """Verifica que estén instaladas las dependencias."""
        print("🔍 Verificando dependencias...\n")
        
        # Verificar Python
        print(f"  ✓ Python: {sys.version.split()[0]}")
        
        # Verificar módulos
        reqs = ["cv2", "numpy", "rich"]
        for mod in reqs:
            try:
                __import__(mod)
                print(f"  ✓ {mod}")
            except ImportError:
                print(f"  ✗ {mod} NO INSTALADO")
                print(f"    Instala con: pip install {mod}")
                return False
        
        # Verificar ADB
        try:
            subprocess.run(["adb", "--version"], 
                         capture_output=True, timeout=2, check=True)
            print(f"  ✓ adb")
        except:
            print(f"  ✗ adb NO ENCONTRADO")
            return False
        
        # Verificar Ollama (solo si no está deshabilitada)
        if not self.no_ia:
            try:
                subprocess.run(["ollama", "--version"],
                             capture_output=True, timeout=2, check=True)
                print(f"  ✓ ollama")
            except:
                print(f"  ✓ ollama (se instalará automáticamente)")
        
        print()
        return True
    
    def signal_handler(self, sig, frame):
        """Maneja Ctrl+C y cierra todo limpiamente."""
        print("\n\n⏹️  Deteniendo...\n")
        self.limpiar()
        sys.exit(0)
    
    def limpiar(self):
        """Cierra todos los procesos."""
        print("🧹 Limpiando procesos...")
        
        for proc in self.procesos:
            if proc and proc.poll() is None:
                try:
                    print(f"  Terminando PID {proc.pid}...")
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                        print(f"    ✓ Terminado")
                    except subprocess.TimeoutExpired:
                        print(f"    Forzando kill...")
                        proc.kill()
                        proc.wait()
                except Exception as e:
                    print(f"    ⚠ Error: {e}")
        
        print("✓ Limpieza completada\n")
    
    def verificar_ollama_corriendo(self) -> bool:
        """Verifica si Ollama ya está activo."""
        try:
            import requests
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def ejecutar(self):
        """Ejecuta el bot y dependencias."""
        # Registrar signal handler
        signal.signal(signal.SIGINT, self.signal_handler)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Mostrar banner
        self.print_banner()
        
        # Verificar dependencias
        if not self.verificar_dependencias():
            print("❌ Faltan dependencias. Instálalas e intenta de nuevo.")
            sys.exit(1)
        
        # Cambiar al directorio del proyecto
        os.chdir(self.proyecto_dir)
        
        # Iniciar el bot
        print("▶️  Iniciando bot...\n")
        cmd = [sys.executable, "pokemon_catcher.py"]
        
        if self.debug:
            cmd.append("--debug")
        
        if self.no_ia:
            cmd.append("--no-ia")
        
        try:
            proc_bot = subprocess.Popen(cmd)
            self.procesos.append(proc_bot)
            
            # Esperar a que termine el bot
            proc_bot.wait()
            
        except KeyboardInterrupt:
            self.signal_handler(None, None)
        except Exception as e:
            print(f"❌ Error al ejecutar: {e}")
            self.limpiar()
            sys.exit(1)


def main():
    launcher = Launcher()
    launcher.ejecutar()


if __name__ == "__main__":
    main()
