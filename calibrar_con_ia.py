#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CALIBRADOR DE COORDENADAS CON IA (una sola vez)
================================================
FLUJO CORRECTO (dos fases separadas):

  FASE 1 - Con el juego abierto, guardás los screenshots:
      python calibrar_con_ia.py capturar

  FASE 2 - Sin tocar el teléfono, LLaVA analiza las imágenes:
      python calibrar_con_ia.py analizar

El bot lee calibracion_ia.json al iniciar y NUNCA más consulta IA.
"""

import subprocess
import json
import base64
import time
import sys
import os
import re
import requests
import cv2
import numpy as np
from pathlib import Path

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llava"
OUTPUT_FILE  = "calibracion_ia.json"
PHONE_W      = 1080
PHONE_H      = 2400

SCREENSHOTS = {
    "mapa":         "calib_mapa.png",
    "combate":      "calib_combate.png",
    "post_captura": "calib_post_captura.png",
}

# ─── ADB ──────────────────────────────────────────────────────────────────

def tomar_screenshot(nombre_archivo: str) -> bool:
    try:
        result = subprocess.run(
            ["adb", "exec-out", "screencap", "-p"],
            capture_output=True, timeout=10
        )
        if result.returncode != 0 or len(result.stdout) < 1000:
            print(f"  [ADB] Error o imagen vacía")
            return False
        arr = np.frombuffer(result.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return False
        cv2.imwrite(nombre_archivo, img)
        h, w = img.shape[:2]
        print(f"  [OK] Guardado: {nombre_archivo} ({w}x{h})")
        return True
    except Exception as e:
        print(f"  [ADB] Error: {e}")
        return False

# ─── LLAVA ────────────────────────────────────────────────────────────────

def img_a_base64(ruta: str) -> str:
    # 270px ancho = imagen pequeña, mucho menos RAM que 540px
    img = cv2.imread(ruta)
    h, w = img.shape[:2]
    new_h = int(h * 270 / w)
    img_small = cv2.resize(img, (270, new_h))
    img_rgb = cv2.cvtColor(img_small, cv2.COLOR_BGR2RGB)
    _, buf = cv2.imencode(".jpg", img_rgb, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode()


def liberar_llava():
    """Descarga LLaVA de RAM/VRAM después de cada consulta."""
    try:
        requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": "",
            "keep_alive": 0
        }, timeout=10)
        print("  [LLaVA] Modelo descargado de RAM")
        time.sleep(3)  # pausa para que el SO libere memoria
    except Exception:
        pass


def preguntar_llava(ruta_img: str, pregunta: str, timeout: int = 60) -> str:
    print(f"  [LLaVA] Analizando {Path(ruta_img).name}...")
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": pregunta,
        "images": [img_a_base64(ruta_img)],
        "stream": False,
        "keep_alive": 0,   # libera RAM inmediatamente al terminar
        "options": {
            "temperature": 0.05,
            "num_ctx": 512,       # contexto mínimo (default=4096 usa ~6GB extra de RAM)
            "num_predict": 60,    # respuesta corta: solo necesitamos "(x, y)"
            "num_thread": 4,      # limitar hilos de CPU
        }
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        respuesta = resp.json().get("response", "").strip()
        print(f"  [LLaVA] -> {respuesta[:150]}")
        return respuesta
    except requests.Timeout:
        print(f"  [LLaVA] Timeout {timeout}s")
        return ""
    except Exception as e:
        print(f"  [LLaVA] Error: {e}")
        return ""


def extraer_coordenadas(texto: str) -> tuple | None:
    for patron in [r"\((\d+)[,\s]+(\d+)\)", r"x[=:\s]+(\d+)[,\s]+y[=:\s]+(\d+)", r"(\d{3,4})[,\s]+(\d{3,4})"]:
        for m in re.finditer(patron, texto, re.IGNORECASE):
            x, y = int(m.group(1)), int(m.group(2))
            if 0 < x < PHONE_W and 0 < y < PHONE_H:
                return x, y
    return None


def extraer_todas(texto: str) -> list:
    resultados = []
    for m in re.finditer(r"\((\d+)[,\s]+(\d+)\)", texto):
        x, y = int(m.group(1)), int(m.group(2))
        if 0 < x < PHONE_W and 0 < y < PHONE_H:
            resultados.append((x, y))
    return resultados

# ─── FASE 1 ───────────────────────────────────────────────────────────────

def fase_capturar():
    print("\n=== FASE 1: CAPTURAS (con el juego abierto) ===")
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    if "device" not in r.stdout:
        print("[ERROR] No hay dispositivo ADB conectado.")
        sys.exit(1)
    print("[ADB] Dispositivo detectado OK\n")

    ok = 0

    print("--- 1/3: MAPA PRINCIPAL ---")
    print("  Andá al mapa de Pokemon GO (panel izquierdo con Pokemon cercanos visible).")
    input("  ENTER cuando el mapa este en pantalla: ")
    if tomar_screenshot(SCREENSHOTS["mapa"]): ok += 1

    print("\n--- 2/3: PANTALLA DE COMBATE ---")
    print("  Toca un Pokemon en el mapa para entrar al combate.")
    print("  Espera que el Pokemon este en pantalla, listo para capturar.")
    input("  ENTER cuando el Pokemon este visible (antes de lanzar): ")
    if tomar_screenshot(SCREENSHOTS["combate"]): ok += 1

    print("\n--- 3/3: POST-CAPTURA ---")
    print("  Lanza la pokebola y captura el Pokemon.")
    print("  Espera la pantalla con el boton 'DE ACUERDO'.")
    input("  ENTER cuando el boton DE ACUERDO sea visible: ")
    if tomar_screenshot(SCREENSHOTS["post_captura"]): ok += 1

    print(f"\nCapturas guardadas: {ok}/3")
    if ok > 0:
        print("Ahora corra (sin necesitar el telefono):")
        print("  python calibrar_con_ia.py analizar")

# ─── FASE 2: OPENCV PURO (sin LLaVA, sin RAM extra) ──────────────────────

def _detectar_boton_verde(img: np.ndarray) -> tuple | None:
    """Detecta el botón DE ACUERDO buscando el rectángulo verde/teal en la zona baja."""
    h, w = img.shape[:2]
    # Buscar solo en el 40% inferior (donde siempre está el botón)
    zona = img[int(h * 0.6):, :]
    offset_y = int(h * 0.6)
    hsv = cv2.cvtColor(zona, cv2.COLOR_BGR2HSV)
    # Verde Pokémon GO: teal/verde (#4CAF50 aprox)
    mascaras = [
        cv2.inRange(hsv, np.array([35, 80, 80]),  np.array([85, 255, 255])),   # verde
        cv2.inRange(hsv, np.array([85, 80, 80]),  np.array([105, 255, 255])),  # teal/cyan
    ]
    mascara = mascaras[0] | mascaras[1]
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE,
                               np.ones((15, 15), np.uint8))
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    mejor = None
    mejor_area = 0
    for cnt in contornos:
        area = cv2.contourArea(cnt)
        if area < 5000:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        # El botón es horizontal (más ancho que alto)
        if bw < bh:
            continue
        if area > mejor_area:
            mejor_area = area
            mejor = (x + bw // 2, offset_y + y + bh // 2)
    return mejor


def _detectar_sniper(img: np.ndarray) -> tuple | None:
    """Detecta el primer ícono del panel izquierdo buscando círculos en la franja izquierda."""
    h, w = img.shape[:2]
    # Panel izquierdo: primer 12% del ancho, zona media-superior
    franja = img[int(h * 0.05):int(h * 0.55), :int(w * 0.12)]
    gris = cv2.cvtColor(franja, cv2.COLOR_BGR2GRAY)
    gris = cv2.GaussianBlur(gris, (5, 5), 0)
    circulos = cv2.HoughCircles(
        gris, cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=40, param1=50, param2=25,
        minRadius=18, maxRadius=50
    )
    if circulos is not None:
        circulos = np.round(circulos[0]).astype(int)
        # Ordenar por Y ascendente → el más arriba es el primero
        circulos = sorted(circulos, key=lambda c: c[1])
        cx, cy, _ = circulos[0]
        return (cx, int(h * 0.05) + cy)
    return None


def _calcular_contraste(img: np.ndarray) -> float:
    """Contraste de la zona central de la imagen."""
    h, w = img.shape[:2]
    zona = img[h//3:2*h//3, w//3:2*w//3]
    return float(cv2.cvtColor(zona, cv2.COLOR_BGR2GRAY).std())


def _detectar_pokeball(img: np.ndarray) -> tuple | None:
    """Detecta la pokébola roja en la zona inferior de la pantalla de combate."""
    h, w = img.shape[:2]
    zona = img[int(h * 0.5):int(h * 0.75), int(w * 0.3):int(w * 0.7)]
    offset_x, offset_y = int(w * 0.3), int(h * 0.5)
    hsv = cv2.cvtColor(zona, cv2.COLOR_BGR2HSV)
    # Rojo pokébola
    m1 = cv2.inRange(hsv, np.array([0, 100, 100]),  np.array([10, 255, 255]))
    m2 = cv2.inRange(hsv, np.array([170, 100, 100]), np.array([180, 255, 255]))
    mascara = cv2.morphologyEx(m1 | m2, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    circulos = cv2.HoughCircles(
        cv2.cvtColor(zona, cv2.COLOR_BGR2GRAY),
        cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=30, param1=50, param2=20,
        minRadius=25, maxRadius=80
    )
    if circulos is not None:
        c = np.round(circulos[0][0]).astype(int)
        return (offset_x + c[0], offset_y + c[1])
    # Fallback: contorno del rojo
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if contornos:
        cnt = max(contornos, key=cv2.contourArea)
        x, y, bw, bh = cv2.boundingRect(cnt)
        return (offset_x + x + bw // 2, offset_y + y + bh // 2)
    return None


def fase_analizar():
    print("\n=== FASE 2: ANALISIS CON OPENCV (sin IA, sin RAM extra) ===")
    print("  Solo usa OpenCV — no carga ningun modelo de IA.")

    calibracion = {}
    if Path(OUTPUT_FILE).exists():
        try:
            with open(OUTPUT_FILE) as f:
                calibracion = json.load(f)
            print(f"[Info] Calibracion existente: {list(calibracion.keys())}")
        except json.JSONDecodeError:
            print("[!] calibracion_ia.json estaba corrupto (apagado brusco). Se reinicia.")
            calibracion = {}

    calibracion["telefono"] = {"ancho": PHONE_W, "alto": PHONE_H}
    calibracion["fecha_calibracion"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # ── MAPA ──────────────────────────────────────────────────────────────
    if Path(SCREENSHOTS["mapa"]).exists():
        print(f"\n--- Analizando {SCREENSHOTS['mapa']} ---")
        img = cv2.imread(SCREENSHOTS["mapa"])
        if img is not None:
            # Contraste
            c = _calcular_contraste(img)
            calibracion["contraste_mapa"] = round(c, 2)
            print(f"  [OK] contraste_mapa = {c:.2f}")
            # Sniper
            coords = _detectar_sniper(img)
            if coords:
                calibracion["sniper_primer_pokemon"] = {"x": int(coords[0]), "y": int(coords[1])}
                print(f"  [OK] sniper_primer_pokemon = {coords}")
            else:
                print("  [!] No detecto circulo en panel izquierdo.")
                print("      Usando valor por defecto (50, 231).")
                calibracion["sniper_primer_pokemon"] = {"x": 50, "y": 231}
    else:
        print(f"  [!] No existe {SCREENSHOTS['mapa']} - salta")

    # ── COMBATE ───────────────────────────────────────────────────────────
    if Path(SCREENSHOTS["combate"]).exists():
        print(f"\n--- Analizando {SCREENSHOTS['combate']} ---")
        img = cv2.imread(SCREENSHOTS["combate"])
        if img is not None:
            c = _calcular_contraste(img)
            calibracion["contraste_combate"] = round(c, 2)
            print(f"  [OK] contraste_combate = {c:.2f}")
            if "contraste_mapa" in calibracion:
                umbral = (calibracion["contraste_mapa"] + c) / 2
                calibracion["umbral_contraste"] = round(umbral, 2)
                print(f"  [OK] umbral_contraste = {umbral:.2f}  "
                      f"(MAPA<{umbral:.1f}<COMBATE)")
            # Pokébola
            pb = _detectar_pokeball(img)
            if pb:
                calibracion["pokeball_inicio"] = {"x": int(pb[0]), "y": int(pb[1])}
                print(f"  [OK] pokeball_inicio = {pb}")
    else:
        print(f"  [!] No existe {SCREENSHOTS['combate']} - salta")

    # ── POST-CAPTURA ───────────────────────────────────────────────────────
    if Path(SCREENSHOTS["post_captura"]).exists():
        print(f"\n--- Analizando {SCREENSHOTS['post_captura']} ---")
        img = cv2.imread(SCREENSHOTS["post_captura"])
        if img is not None:
            btn = _detectar_boton_verde(img)
            if btn:
                calibracion["boton_de_acuerdo"] = {"x": int(btn[0]), "y": int(btn[1])}
                print(f"  [OK] boton_de_acuerdo = {btn}")
            else:
                print(f"  [!] No detecto boton verde.")
                print(f"      Abri {SCREENSHOTS['post_captura']} y anotá las coordenadas.")
                x_s = input("      X del boton (Enter para usar 540): ").strip()
                y_s = input("      Y del boton (Enter para usar 2130): ").strip()
                calibracion["boton_de_acuerdo"] = {
                    "x": int(x_s) if x_s else 540,
                    "y": int(y_s) if y_s else 2130
                }
    else:
        print(f"  [!] No existe {SCREENSHOTS['post_captura']} - salta")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(calibracion, f, indent=2, ensure_ascii=False)

    print(f"\n=== Guardado en {OUTPUT_FILE} ===")
    for k, v in calibracion.items():
        print(f"  {k}: {v}")
    print("\nEl bot usara estos valores automaticamente al iniciar.")

# ─── MAIN ──────────────────────────────────────────────────────────────────

def main():
    print("CALIBRADOR IA - POKEMON GO BOT")
    print("  Fase 1 (con juego abierto): python calibrar_con_ia.py capturar")
    print("  Fase 2 (analisis offline):  python calibrar_con_ia.py analizar")

    if len(sys.argv) < 2:
        print("\nElige:")
        print("  1. capturar")
        print("  2. analizar")
        eleccion = input("Opcion (1/2): ").strip()
        sys.argv.append("capturar" if eleccion == "1" else "analizar")

    cmd = sys.argv[1].lower()
    if cmd == "capturar":
        fase_capturar()
    elif cmd == "analizar":
        fase_analizar()
    else:
        print(f"Comando invalido: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
