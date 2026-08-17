#!/usr/bin/env python3
"""
[DEPRECATED] Este módulo ha sido subsumido por detector_estados.py (5 estrategias + fusión ponderada).
Todas las funciones aquí definidas se mantienen por compatibilidad pero ya no se usan
en el pipeline principal. Será eliminado en una versión futura.

Detectores mejorados basados en FEATURES en lugar de colores generales
Esto reemplaza los detectores defectuosos del bot principal

Problema: Los rangos HSV originales NO distinguen entre estados
Solución: Feature-based detection (arcos, paneles, brillos, etc.)
"""
import cv2
import numpy as np

class DetectoresRobustos:
    """Suite de detectores basados en features visuales específicas"""
    
    @staticmethod
    def es_combate_mejorado(img: np.ndarray) -> tuple[bool, float]:
        """
        Detecta combate buscando features ESPECÍFICAS:
        - Presencia de aro circular (Hough circles)
        - Pokébola visible
        - UI de combate
        
        Mucho más robusto que análisis de color general
        """
        if img is None:
            return False, 0.0
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = img.shape[:2]
        
        # Estrategia 1: Detectar aro circular (marca más clara de combate)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=100,
            param1=50,
            param2=30,
            minRadius=80,
            maxRadius=300
        )
        
        if circles is not None and len(circles[0]) > 0:
            # Hay círculos detectados → probablemente combate
            return True, 0.95
        
        # Estrategia 2: Buscar contraste alto en zona central (aro de combate)
        zona_central = gray[h//3:2*h//3, w//4:3*w//4]
        
        # Calcular contraste local
        mean_val = np.mean(zona_central)
        std_val = np.std(zona_central)
        contraste = std_val / (mean_val + 1)
        
        # En combate hay más contraste por el aro
        if contraste > 0.5:
            # Verificar que haya pokébola visible
            pokebola_visible = DetectoresRobustos._detectar_pokebola(img)
            if pokebola_visible > 0:
                return True, 0.85
        
        # Estrategia 3: Buscar patrón de UI de combate
        # El sniper panel tiene estructura visual específica
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Buscar pixeles de UI (grises oscuros = botones/barras)
        mask_ui = cv2.inRange(hsv, np.array([0, 0, 50]), np.array([180, 30, 150]))
        
        # Zona inferior (donde está sniper)
        ui_count = np.sum(mask_ui[2*h//3:, :] > 0)
        ui_pct = ui_count / ((h//3) * w)
        
        if ui_pct > 0.15:
            return True, 0.80
        
        return False, 0.0
    
    @staticmethod
    def es_post_captura_mejorado(img: np.ndarray) -> tuple[bool, float]:
        """
        Detecta pantalla post-captura buscando:
        - Paneles blancos grandes (dialogs)
        - Botones de confirmación
        - Estructura de modal
        """
        if img is None:
            return False, 0.0
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Buscar píxeles VERY blancos (paneles típicamente >245)
        mask_blanco = cv2.inRange(gray, 240, 255)
        
        # Encontrar contornos
        contours, _ = cv2.findContours(mask_blanco, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Contar paneles grandes (>10000 píxeles)
        paneles_grandes = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 10000:
                paneles_grandes += 1
        
        if paneles_grandes >= 1:
            return True, 0.90
        
        # Fallback: buscar estructura modal (bordes definidos)
        edges = cv2.Canny(gray, 50, 150)
        edge_count = np.sum(edges > 0)
        edge_pct = edge_count / (gray.shape[0] * gray.shape[1])
        
        if edge_pct > 0.08:
            return True, 0.75
        
        return False, 0.0
    
    @staticmethod
    def hay_pokemon_visible_mejorado(img: np.ndarray) -> tuple[bool, int]:
        """
        Detecta si hay pokémon visible en el mapa
        Busca puntos de brillo característicos
        
        Retorna: (hay_pokemon, cantidad_detectados)
        """
        if img is None:
            return False, 0
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Pokémon tiene brillo específico (puntos >190)
        mask_brillo = cv2.inRange(gray, 180, 255)
        
        # Limpiar ruido
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask_brillo = cv2.morphologyEx(mask_brillo, cv2.MORPH_OPEN, kernel, iterations=1)
        mask_brillo = cv2.morphologyEx(mask_brillo, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        # Encontrar contornos
        contours, _ = cv2.findContours(mask_brillo, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Contar puntos brillantes de tamaño pokémon (50-3000 píxeles)
        pokemon_count = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 50 < area < 3000:
                pokemon_count += 1
        
        return (pokemon_count > 0), pokemon_count
    
    @staticmethod
    def _detectar_pokebola(img: np.ndarray) -> int:
        """
        Detecta pokébolas visibles
        Busca patrón rojo-blanco característico
        """
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Rojo de pokébola (saturation media-alta, value media-alta)
        mask_rojo = cv2.inRange(hsv, np.array([0, 80, 100]), np.array([30, 255, 255]))
        
        # Contar pixels
        return np.sum(mask_rojo > 0)
    
    @staticmethod
    def validar_estado_multiplex(img: np.ndarray) -> str:
        """
        Validación FINAL: Retorna estado DEFINITIVO
        Usa múltiples detectores para máxima confianza
        
        Retorna: "MAPA" | "COMBATE" | "POST-CAPTURA" | "DESCONOCIDO"
        """
        if img is None:
            return "DESCONOCIDO"
        
        # Ejecutar todos los detectores
        es_combate, conf_combate = DetectoresRobustos.es_combate_mejorado(img)
        es_post_cap, conf_post = DetectoresRobustos.es_post_captura_mejorado(img)
        hay_pokemon, pokemon_count = DetectoresRobustos.hay_pokemon_visible_mejorado(img)
        
        # Lógica de decisión (prioridad)
        # 1. POST-CAPTURA es prioritario (es un estado modal)
        if es_post_cap and conf_post > 0.70:
            return "POST-CAPTURA"
        
        # 2. COMBATE
        if es_combate and conf_combate > 0.70:
            return "COMBATE"
        
        # 3. MAPA con pokémon
        if hay_pokemon and pokemon_count > 0:
            return "POKEMON_EN_MAPA"
        
        # 4. Solo MAPA
        return "MAPA"


# Pruebas rápidas
if __name__ == "__main__":
    print("Detectores mejorados cargados correctamente ✅")
    print("\nFunciones disponibles:")
    print("  - es_combate_mejorado(img)")
    print("  - es_post_captura_mejorado(img)")
    print("  - hay_pokemon_visible_mejorado(img)")
    print("  - validar_estado_multiplex(img)")
