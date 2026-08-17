#!/usr/bin/env python3
"""Test script para verificar que ADB se detecta correctamente."""

import os
import sys
import subprocess
import shutil

# Buscar ADB en múltiples ubicaciones
_ADB_PATH = None
def _find_adb():
    """Busca ADB en múltiples ubicaciones."""
    global _ADB_PATH
    if _ADB_PATH:
        return _ADB_PATH
    
    # Buscar en PATH del sistema
    adb = shutil.which("adb")
    if adb:
        _ADB_PATH = adb
        return _ADB_PATH
    
    # Buscar en ubicaciones comunes
    for path in [
        "/tmp/platform-tools/adb",
        os.path.expanduser("~/Android/platform-tools/adb"),
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/opt/android-sdk/platform-tools/adb",
    ]:
        if os.path.exists(path):
            _ADB_PATH = path
            return _ADB_PATH
    
    return "adb"  # fallback

# Verificar
adb_path = _find_adb()
print(f"✓ ADB encontrado en: {adb_path}")

# Verificar que funciona
try:
    result = subprocess.run([adb_path, "version"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print(f"✓ ADB funciona correctamente")
        print(f"\n{result.stdout}")
    else:
        print(f"✗ ADB reportó error: {result.stderr}")
except Exception as e:
    print(f"✗ Error al ejecutar ADB: {e}")
