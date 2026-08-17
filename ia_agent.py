#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 IA AGENT LOCAL - Ollama + LLaVA (Versión Estricta)
Análisis de pantallas con prompt ESTRICTO para evitar alucinaciones.
100% LOCAL, GRATIS, sin API keys.
"""

import cv2
import numpy as np
import requests
import base64
import time
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llava"
DEBUG = True

# CACHÉ: evitar analizar screenshots idénticos
_cache = {"hash": None, "resultado": None, "timestamp": 0}
_cache_timeout = 3.0  # segundos


def _hash_imagen(img: np.ndarray) -> str:
    """Hash rápido de imagen para caché."""
    if img is None:
        return ""
    thumb = cv2.resize(img, (16, 16))
    return str(hash(thumb.tobytes()))


def analizar_pantalla(img_bgr: np.ndarray) -> str:
    """
    Clasifica el estado actual de Pokémon GO.
    
    Retorna: "MAPA" | "COMBATE" | "DETALLE_POKEMON" | "RESUMEN_CAPTURA" | "CARGANDO" | "DESCONOCIDO"
    """
    if img_bgr is None:
        return "DESCONOCIDO"

    # ── CACHÉ ──────────────────────────────────────────────────────────────
    hash_img = _hash_imagen(img_bgr)
    ahora = time.time()
    
    if (_cache["hash"] == hash_img and 
        (ahora - _cache["timestamp"]) < _cache_timeout):
        if DEBUG:
            print(f"[IA] 📌 Resultado desde CACHÉ")
        return _cache["resultado"]

    # ── PROCESAR ───────────────────────────────────────────────────────────
    try:
        # 1. Redimensionar imagen (360px = ultra rápido)
        h, w = img_bgr.shape[:2]
        new_w = 360
        new_h = int(h * (new_w / w))
        img_resized = cv2.resize(img_bgr, (new_w, new_h))

        # 2. Codificar a Base64
        _, buffer = cv2.imencode('.jpg', img_resized, [cv2.IMWRITE_JPEG_QUALITY, 80])
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        # 3. PROMPT ESTRICTO (evita alucinaciones)
        prompt = (
            "Analiza detalladamente esta captura de pantalla de Pokémon GO y responde UNICAMENTE "
            "con UNA sola palabra clave en mayúscula, sin puntos ni texto adicional:\n\n"
            "- 'MAPA': Estás viendo el mapa del mundo con caminos y Pokémon libres en el mapa.\n"
            "- 'COMBATE': Estás frente a un Pokémon salvaje con la pokébola roja/azul abajo, listo para capturar.\n"
            "- 'DETALLE_POKEMON': Capturaste el Pokémon y ves su ficha con PC, peso, altura, botones 'MÁS PODER' y 'EVOLUCIONAR', y una X para cerrar.\n"
            "- 'RESUMEN_CAPTURA': Ves el cartel '¡Atrapaste a X!' con +100 XP, caramelos, y el botón 'DE ACUERDO'.\n"
            "- 'CARGANDO': Pantalla negra, en carga, o aviso de conexión.\n"
            "- 'DESCONOCIDO': No identificas la pantalla.\n\n"
            "IMPORTANTE: Responde SOLO una palabra. Nada más."
        )

        # 4. Payload para Ollama
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "images": [img_base64],
            "stream": False,
            "options": {
                "temperature": 0.0,  # Cero creatividad
                "top_p": 0.1,
                "num_predict": 10    # Max 10 tokens (una palabra)
            }
        }

        if DEBUG:
            print(f"[IA] 🤖 Analizando pantalla con Ollama...")

        tiempo_inicio = time.time()
        response = requests.post(OLLAMA_URL, json=payload, timeout=15)  # Aumentado de 8s a 15s (Ollama puede ser lento)
        tiempo_ms = int((time.time() - tiempo_inicio) * 1000)

        if response.status_code == 200:
            resultado_raw = response.json().get("response", "").strip().upper()
            
            # Extraer palabra clave
            keywords = ["MAPA", "COMBATE", "DETALLE_POKEMON", "RESUMEN_CAPTURA", "CARGANDO"]
            resultado = "DESCONOCIDO"
            
            for keyword in keywords:
                if keyword in resultado_raw:
                    resultado = keyword
                    break
            
            # Guardar en caché
            _cache["hash"] = hash_img
            _cache["resultado"] = resultado
            _cache["timestamp"] = ahora
            
            if DEBUG:
                print(f"[IA] ✓ {resultado} (tiempo={tiempo_ms}ms)")
                if resultado_raw != resultado:
                    print(f"[IA]    Raw: {resultado_raw[:80]}")
            
            return resultado
        else:
            if DEBUG:
                print(f"[IA] ⚠ Error HTTP {response.status_code}")
            return "DESCONOCIDO"

    except requests.exceptions.Timeout:
        if DEBUG:
            print(f"[IA] ⚠ Timeout (>15s) - Fallback a DESCONOCIDO (Ollama muy lento)")
        return "DESCONOCIDO"
    
    except Exception as e:
        if DEBUG:
            print(f"[IA] ⚠ Error: {e}")
        return "DESCONOCIDO"


if __name__ == "__main__":
    print("🤖 IA Agent - Versión Estricta")
    print("=" * 60)
    
    # Test conexión
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        print("✅ Ollama está corriendo")
    except:
        print("❌ Ollama NO está corriendo (inicia con: ollama serve &)")
        exit(1)
    
    # Test con imagen dummy
    print("\n📸 Creando imagen de prueba...")
    img_test = np.ones((2400, 1080, 3), dtype=np.uint8) * 128
    
    resultado = analizar_pantalla(img_test)
    print(f"\n📊 Resultado: {resultado}")
    
    # Test caché
    print("\n🧪 Probando caché (segunda consulta)...")
    resultado2 = analizar_pantalla(img_test)
    print(f"📊 Resultado: {resultado2} (desde caché)")

