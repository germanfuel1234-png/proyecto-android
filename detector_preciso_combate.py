#!/usr/bin/env python3
"""
Detector PRECISO de COMBATE vs MAPA basado en análisis de features
Usa contraste local y patrones de UI
"""
import cv2
import numpy as np

class DetectorCombatePreciso:
    """Detecta con alta precisión si estamos en COMBATE o MAPA"""
    
    @staticmethod
    def _analizar_zona_central(img):
        """Analiza la zona central donde aparece el Pokémon en combate"""
        h, w = img.shape[:2]
        
        # Zona central (donde está el sniper/pokémon)
        centro_x, centro_y = w // 2, h // 2
        zona_radio = 200
        
        zona_central = img[max(0, centro_y-zona_radio):min(h, centro_y+zona_radio),
                          max(0, centro_x-zona_radio):min(w, centro_x+zona_radio)]
        
        gray = cv2.cvtColor(zona_central, cv2.COLOR_BGR2GRAY)
        
        # Contraste local (desv. est. del brillo)
        # En COMBATE es alto (Pokémon con contraste), en MAPA es bajo
        contraste = gray.std()
        
        # Brillo medio
        brillo = gray.mean()
        
        return {
            'contraste': contraste,
            'brillo': brillo,
            'gray_zone': gray
        }
    
    @staticmethod
    def _contar_lineas_ui(img):
        """Cuenta líneas rectas (UI elements son líneas)"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # En MAPA hay más líneas por los menús y botones
        # En COMBATE la UI es mínima
        edges = cv2.Canny(gray, 50, 150)
        
        # Detectar líneas rectas
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, 
                               minLineLength=50, maxLineGap=10)
        
        return len(lines) if lines is not None else 0
    
    @staticmethod
    def _detectar_brillo_extremo(img):
        """Detecta píxeles MUY brillantes (característico de Pokémon/centelleo)"""
        h, w = img.shape[:2]
        
        # Zona central
        centro_x, centro_y = w // 2, h // 2
        radio = 250
        
        zona_central = img[max(0, centro_y-radio):min(h, centro_y+radio),
                          max(0, centro_x-radio):min(w, centro_x+radio)]
        
        gray = cv2.cvtColor(zona_central, cv2.COLOR_BGR2GRAY)
        
        # Píxeles muy brillantes (200+)
        brillo_extremo = cv2.countNonZero(cv2.inRange(gray, 200, 255))
        total_pixels = zona_central.shape[0] * zona_central.shape[1]
        pct_brillo = (brillo_extremo / total_pixels) * 100
        
        return pct_brillo
    
    @staticmethod
    def _analizar_histograma(img):
        """Analiza distribución de brillo: COMBATE tiene bimodal (oscuro+pokémon)"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        
        # Normalizar
        hist = hist.flatten() / hist.sum()
        
        # Buscar picos (en combate hay 2 picos: fondo + pokémon)
        # En mapa es más uniforme
        picos = 0
        for i in range(1, 255):
            if hist[i] > hist[i-1] and hist[i] > hist[i+1] and hist[i] > 0.005:
                picos += 1
        
        return picos
    
    @classmethod
    def es_combate(cls, img, verbose=False):
        """
        Determina si estamos en COMBATE con alta precisión
        
        Returns:
            (bool, float): (es_combate, confianza 0-1)
        """
        
        # Análisis central
        central = cls._analizar_zona_central(img)
        contraste = central['contraste']
        
        # Análisis UI
        lineas = cls._contar_lineas_ui(img)
        
        # Análisis de brillo extremo
        brillo_extremo_pct = cls._detectar_brillo_extremo(img)
        
        # Análisis de histograma
        picos_hist = cls._analizar_histograma(img)
        
        if verbose:
            print(f"  Contraste central: {contraste:.2f}")
            print(f"  Líneas UI: {lineas}")
            print(f"  Brillo extremo: {brillo_extremo_pct:.2f}%")
            print(f"  Picos histograma: {picos_hist}")
        
        # Lógica de decisión:
        # COMBATE: alto contraste + pocas líneas UI + brillo extremo + picos bimodales
        # MAPA: bajo contraste + muchas líneas UI + poco brillo extremo + picos uniformes
        
        puntos_combate = 0
        confianza_total = 0
        
        # Criterio 1: Contraste (COMBATE > 16, MAPA < 14.5)
        if contraste > 15.5:
            puntos_combate += 1
            confianza_total += 0.3
        elif contraste < 14:
            confianza_total += 0.3
        else:
            confianza_total += 0.15  # Zona gris
        
        # Criterio 2: Líneas UI (COMBATE < 550, MAPA > 560)
        if lineas < 540:
            puntos_combate += 1
            confianza_total += 0.3
        elif lineas > 560:
            confianza_total += 0.3
        else:
            confianza_total += 0.15  # Zona gris
        
        # Criterio 3: Brillo extremo (COMBATE > 0.8%, MAPA < 0.5%)
        if brillo_extremo_pct > 0.7:
            puntos_combate += 1
            confianza_total += 0.2
        elif brillo_extremo_pct < 0.5:
            confianza_total += 0.2
        else:
            confianza_total += 0.1
        
        # Criterio 4: Picos (COMBATE >= 2, MAPA = 1)
        if picos_hist >= 2:
            puntos_combate += 1
            confianza_total += 0.2
        elif picos_hist == 1:
            confianza_total += 0.2
        
        # Decisión
        es_combate = puntos_combate >= 2
        confianza = min(1.0, (puntos_combate / 4.0))
        
        return es_combate, confianza
    
    @classmethod
    def es_mapa(cls, img, verbose=False):
        """Determina si estamos en MAPA (opuesto a combate)"""
        es_combate, conf = cls.es_combate(img, verbose)
        return not es_combate, conf


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python3 detector_preciso_combate.py <imagen>")
        sys.exit(1)
    
    img = cv2.imread(sys.argv[1])
    if img is None:
        print(f"No se pudo leer: {sys.argv[1]}")
        sys.exit(1)
    
    print(f"Analizando: {sys.argv[1]}")
    print("-" * 50)
    
    es_combate, confianza = DetectorCombatePreciso.es_combate(img, verbose=True)
    
    print()
    print("="*50)
    if es_combate:
        print(f"✅ COMBATE (confianza: {confianza:.1%})")
    else:
        print(f"🗺️  MAPA (confianza: {confianza:.1%})")
    print("="*50)
