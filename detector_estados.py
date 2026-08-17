#!/usr/bin/env python3
"""
Detector Unificado de Estados — fusión ponderada de múltiples estrategias.

Reemplaza los detectores inline dispersos por un pipeline centralizado con:
  - 5 estrategias de detección independientes
  - Fusión ponderada con pesos adaptativos
  - Sub-estados POST-CAPTURA (xp/detalle/mapa)
  - Coordenadas de acción recomendadas
  - Pipeline de visión cacheado (HSV + gray 1 sola vez)

Uso:
    detector = DetectorEstados(tmpl_camara, tmpl_check_pokemon)
    estado = detector.analizar(screenshot)
    print(estado.estado, estado.sub_estado, estado.confianza)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np


# ─── Tipos de estado ────────────────────────────────────────────────────────

ESTADOS = ("MAPA", "COMBATE", "POST_CAPTURA", "MODAL", "CARGANDO", "DESCONOCIDO")
SUB_ESTADOS_POST = ("xp", "detalle", "modal", "mapa")


@dataclass
class ResultadoEstrategia:
    """Resultado de una estrategia individual."""
    scores: dict[str, float]  # estado -> confianza 0.0-1.0
    info: dict = field(default_factory=dict)


@dataclass
class ScreenState:
    """Estado completo de la pantalla detectado."""
    estado: str                        # MAPA | COMBATE | POST_CAPTURA | MODAL | CARGANDO | DESCONOCIDO
    sub_estado: Optional[str]          # None | xp | detalle | modal | mapa
    confianza: float                   # 0.0-1.0 general
    scores: dict[str, float]           # score por estrategia
    debug: dict                        # info de depuración (pcts, etc.)
    coord_accion: Optional[tuple[int, int]] = None  # (x, y) para tap si aplica


# ─── Pipeline de visión cacheado ────────────────────────────────────────────

class PipelineVision:
    """Preprocesa la imagen una sola vez y cachea resultados."""
    
    __slots__ = ('img', 'hsv', 'gray', 'h', 'w', 'total')
    
    def __init__(self, img: np.ndarray):
        self.img = img
        self.h, self.w = img.shape[:2]
        self.total = self.h * self.w
        self.hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        self.gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ─── Detector Unificado ─────────────────────────────────────────────────────

class DetectorEstados:
    """
    Pipeline de detección con fusión ponderada de 5 estrategias.
    
    Pesos por defecto (ajustables por brief):
      hsv:         0.25  — rápido, frágil a iluminación
      estructural: 0.25  — bordes/textura/entropía, robusto
      combate:     0.20  — Hough/contraste/líneas, específico
      post:        0.20  — paneles/checkmark teal/XP card
      template:    0.10  — matching de plantillas
    """
    
    PESOS = {
        'hsv': 0.25,
        'estructural': 0.25,
        'combate': 0.20,
        'post': 0.20,
        'template': 0.10,
    }
    
    def __init__(self, tmpl_camara: Optional[np.ndarray] = None,
                 tmpl_check_pokemon: Optional[np.ndarray] = None,
                 pesos: Optional[dict[str, float]] = None):
        self.tmpl_camara = tmpl_camara
        self.tmpl_check_pokemon = tmpl_check_pokemon
        if pesos:
            self.PESOS = {**self.PESOS, **pesos}
    
    # ── API pública ─────────────────────────────────────────────────────────
    
    def analizar(self, img: np.ndarray) -> ScreenState:
        """Punto de entrada único: procesa una imagen y devuelve ScreenState."""
        if img is None or img.size == 0:
            return ScreenState("DESCONOCIDO", None, 0.0, {}, {"error": "img nula"}, None)
        
        pipe = PipelineVision(img)
        
        # Ejecutar estrategias
        r_hsv = self._hsv(pipe)
        r_estructural = self._estructural(pipe)
        r_combate = self._combate_preciso(pipe)
        r_post = self._post_captura(pipe)
        r_template = self._template(pipe)
        
        estrategias = {
            'hsv': r_hsv,
            'estructural': r_estructural,
            'combate': r_combate,
            'post': r_post,
            'template': r_template,
        }
        
        return self._fusionar(estrategias, pipe)
    
    # ── Estrategia HSV ──────────────────────────────────────────────────────
    
    def _hsv(self, p: PipelineVision) -> ResultadoEstrategia:
        """Detección por color: rojo (combate), blanco (post-captura), verde (mapa)."""
        # Blanco
        mask_b = cv2.inRange(p.hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
        pct_b = cv2.countNonZero(mask_b) / p.total
        # Verde
        mask_v = cv2.inRange(p.hsv, np.array([35, 40, 50]), np.array([95, 255, 255]))
        pct_v = cv2.countNonZero(mask_v) / p.total
        # Rojo puro (S>=150)
        m_r1 = cv2.inRange(p.hsv, np.array([0, 150, 80]), np.array([10, 255, 255]))
        m_r2 = cv2.inRange(p.hsv, np.array([170, 150, 80]), np.array([180, 255, 255]))
        pct_r = cv2.countNonZero(m_r1 | m_r2) / p.total
        
        scores = {}
        # COMBATE: rojo > 2.5% es señal fuerte
        if pct_r > 0.025:
            scores['COMBATE'] = min(pct_r / 0.06, 1.0)
        elif pct_r > 0.01:
            scores['COMBATE'] = 0.3
        else:
            scores['COMBATE'] = 0.0
        
        # POST_CAPTURA: blanco > 30% con poco rojo
        if pct_b > 0.30 and pct_r < 0.03:
            scores['POST_CAPTURA'] = min(pct_b / 0.60, 1.0)
        elif pct_b > 0.15:
            scores['POST_CAPTURA'] = 0.3
        else:
            scores['POST_CAPTURA'] = 0.0
        
        # MAPA: verde > 20% o poco blanco + poco rojo
        if pct_v > 0.20:
            scores['MAPA'] = min(pct_v / 0.40, 1.0)
        elif pct_b < 0.15 and pct_r < 0.015:
            scores['MAPA'] = 0.6  # mapa por descarte
        else:
            scores['MAPA'] = max(pct_v / 0.35, 0.0)
        
        return ResultadoEstrategia(scores, {
            'pct_rojo': round(pct_r, 4), 'pct_verde': round(pct_v, 4),
            'pct_blanco': round(pct_b, 4),
        })
    
    # ── Estrategia Estructural (invariante a iluminación) ────────────────────
    
    def _estructural(self, p: PipelineVision) -> ResultadoEstrategia:
        """
        Detecta MAPA vs COMBATE usando bordes/textura/entropía.
        Inspirado en _en_mapa_robusto de pokemon_catcher.py.
        """
        laplacian = cv2.Laplacian(p.gray, cv2.CV_64F)
        edges_intensity = float(np.abs(laplacian).mean())
        
        # Diversidad de color (histograma HSV)
        hist_h = cv2.calcHist([p.hsv], [0], None, [8], [0, 180])
        hist_s = cv2.calcHist([p.hsv], [1], None, [8], [0, 256])
        bins = np.sum(hist_h > 100) + np.sum(hist_s > 100)
        
        # Textura
        roi = p.gray[int(p.h*0.3):int(p.h*0.7), int(p.w*0.2):int(p.w*0.8)]
        mean_blur = cv2.blur(roi.astype(np.float32), (16, 16))
        sqmean = cv2.blur(roi.astype(np.float32)**2, (16, 16))
        texture = float((sqmean - mean_blur**2).mean())
        
        # Entropía de brillo
        hist_g = cv2.calcHist([p.gray], [0], None, [16], [0, 256])
        hist_n = hist_g / hist_g.sum()
        entropy = -float(np.sum(hist_n[hist_n > 0] * np.log2(hist_n[hist_n > 0])))
        
        # Criterios de MAPA (terreno con textura)
        crit_bordes = edges_intensity > 12
        crit_diversidad = bins > 14
        crit_textura = texture > 700
        crit_entropia = entropy > 3.0
        mapa_criterios = sum([crit_bordes, crit_diversidad, crit_textura, crit_entropia])
        
        conf_mapa = min(mapa_criterios / 4.0, 1.0)
        conf_combate = 1.0 - conf_mapa if mapa_criterios < 3 else 0.0
        
        # POST_CAPTURA: white panel suprime señal estructural de mapa
        mask_b = cv2.inRange(p.hsv, np.array([0, 0, 200]), np.array([180, 50, 255]))
        pct_b = cv2.countNonZero(mask_b) / p.total
        if pct_b > 0.30:
            conf_mapa *= 0.3
        
        return ResultadoEstrategia(
            {'MAPA': conf_mapa, 'COMBATE': conf_combate},
            {'edges': round(edges_intensity, 1), 'diversidad': int(bins),
             'texture': round(texture, 0), 'entropy': round(entropy, 2),
             'criteria': mapa_criterios}
        )
    
    # ── Estrategia Combate Preciso ──────────────────────────────────────────
    
    def _combate_preciso(self, p: PipelineVision) -> ResultadoEstrategia:
        """
        Detecta COMBATE con 4 criterios: contraste, líneas Hough, brillo extremo,
        picos de histograma. Inspirado en detector_preciso_combate.py.
        """
        # Contraste central
        cx, cy = p.w // 2, p.h // 2
        zona = p.gray[max(0, cy-200):min(p.h, cy+200), max(0, cx-200):min(p.w, cx+200)]
        contraste = float(zona.std()) if zona.size > 0 else 0
        
        # Líneas Hough (UI count)
        edges = cv2.Canny(p.gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=50, maxLineGap=10)
        n_lineas = len(lines) if lines is not None else 0
        
        # Brillo extremo (V>200)
        mask_brillo = cv2.inRange(p.hsv, np.array([0, 0, 200]), np.array([180, 255, 255]))
        pct_brillo = cv2.countNonZero(mask_brillo) / p.total
        
        # Picos de histograma (bimodal = combate)
        hist = cv2.calcHist([p.gray], [0], None, [32], [0, 256]).flatten()
        hist_smooth = cv2.GaussianBlur(hist, (3, 3), 0).flatten()
        picos = 0
        for i in range(1, len(hist_smooth)-1):
            if hist_smooth[i] > hist_smooth[i-1] and hist_smooth[i] > hist_smooth[i+1]:
                picos += 1
        
        # Puntuación
        pts = 0
        if contraste > 15.5: pts += 1
        if n_lineas < 540: pts += 1
        if pct_brillo > 0.007: pts += 1
        if picos >= 2: pts += 1
        
        conf = min(pts / 4.0, 1.0)
        
        return ResultadoEstrategia(
            {'COMBATE': conf if pts >= 2 else conf * 0.3,
             'MAPA': 1.0 - conf if pts < 2 else 0.0},
            {'contraste': round(contraste, 1), 'lineas': n_lineas,
             'brillo': round(pct_brillo, 4), 'picos_hist': int(picos)}
        )
    
    # ── Estrategia Post-Captura ─────────────────────────────────────────────
    
    def _post_captura(self, p: PipelineVision) -> ResultadoEstrategia:
        """
        Detecta POST_CAPTURA y sub-estados (xp/detalle/modal/mapa).
        Inspirado en _detectar_pantalla_postcombate de pokemon_catcher.py.
        """
        h, w = p.h, p.w
        scores = {'POST_CAPTURA': 0.0, 'MAPA': 0.0, 'COMBATE': 0.0}
        info: dict = {}
        
        # ─ Prioridad 0: Pokébola central = MAPA
        try:
            zona_pb = p.img[int(h*0.72):int(h*0.92), int(w*0.35):int(w*0.65)]
            hsv_pb = cv2.cvtColor(zona_pb, cv2.COLOR_BGR2HSV)
            mr1 = cv2.inRange(hsv_pb, np.array([0, 120, 120]), np.array([10, 255, 255]))
            mr2 = cv2.inRange(hsv_pb, np.array([170, 120, 120]), np.array([180, 255, 255]))
            rojo_pb = cv2.countNonZero(mr1 | mr2)
            mb = cv2.inRange(hsv_pb, np.array([0, 0, 210]), np.array([180, 30, 255]))
            blanc_pb = cv2.countNonZero(mb)
            info['pb_rojo'] = rojo_pb
            info['pb_blanco'] = blanc_pb
            if rojo_pb > 1500 and blanc_pb > 1500:
                scores['POST_CAPTURA'] = 0.0
                scores['MAPA'] = 1.0
                info['sub_estado'] = 'mapa'
                return ResultadoEstrategia(scores, info)
        except:
            pass
        
        # ─ Proporción de blanco en banda modal
        try:
            band = p.img[int(h*0.30):int(h*0.90), int(w*0.05):int(w*0.95)]
            hsv_m = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
            mw = cv2.inRange(hsv_m, np.array([0, 0, 200]), np.array([180, 40, 255]))
            white_pct = cv2.countNonZero(mw) / (band.shape[0] * band.shape[1])
        except:
            white_pct = 0.0
        info['white_pct'] = round(white_pct, 3)
        
        # ─ Verde XP card (H=35-85)
        try:
            xp_band = p.img[int(h*0.50):int(h*0.90), int(w*0.10):int(w*0.90)]
            hsv_xp = cv2.cvtColor(xp_band, cv2.COLOR_BGR2HSV)
            mg1 = cv2.inRange(hsv_xp, np.array([35, 40, 80]), np.array([85, 255, 255]))
            mg2 = cv2.inRange(hsv_xp, np.array([20, 50, 100]), np.array([40, 255, 255]))
            green_px = cv2.countNonZero(mg1 | mg2)
        except:
            green_px = 0
        info['green_px'] = green_px
        
        # ─ Teal checkmark en borde inferior
        try:
            strip = p.img[int(h*0.85):, :]
            hsv_b = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
            mask_t = cv2.inRange(hsv_b, np.array([82, 80, 100]), np.array([105, 255, 255]))
            teal_px = cv2.countNonZero(mask_t)
        except:
            teal_px = 0
        info['teal_px'] = teal_px
        
        # ─ Decisión POST_CAPTURA con sub-estado
        if white_pct > 0.15 and green_px > 300000:
            scores['POST_CAPTURA'] = 0.95
            info['sub_estado'] = 'xp'
            info['coord_accion'] = (547, 1570)  # DE ACUERDO button
        elif teal_px > 4000:
            scores['POST_CAPTURA'] = 0.90
            info['sub_estado'] = 'detalle'
            info['coord_accion'] = (547, 2142)  # checkmark
        elif white_pct > 0.70:
            scores['POST_CAPTURA'] = 0.80
            info['sub_estado'] = 'xp'
            info['coord_accion'] = (547, 1570)
        elif white_pct > 0.45:
            scores['POST_CAPTURA'] = 0.60
            info['sub_estado'] = 'modal'
        else:
            scores['POST_CAPTURA'] = max(white_pct / 0.60, 0.0)
        
        return ResultadoEstrategia(scores, info)
    
    # ── Estrategia Template ─────────────────────────────────────────────────
    
    def _template(self, p: PipelineVision) -> ResultadoEstrategia:
        """Template matching para confirmar estados específicos."""
        scores = {'COMBATE': 0.0, 'POST_CAPTURA': 0.0, 'MAPA': 0.0}
        
        # Cámara → COMBATE (más específico)
        if self.tmpl_camara is not None:
            try:
                roi = p.gray[int(p.h*0.05):int(p.h*0.30), int(p.w*0.30):int(p.w*0.70)]
                res = cv2.matchTemplate(roi, self.tmpl_camara, cv2.TM_CCOEFF_NORMED)
                _, conf, _, _ = cv2.minMaxLoc(res)
                if conf > 0.50:
                    scores['COMBATE'] = min(conf, 1.0)
                    return ResultadoEstrategia(scores, {'camara': round(conf, 3)})
            except:
                pass
        
        # Checkmark teal → POST_CAPTURA (alta especificidad)
        if self.tmpl_check_pokemon is not None:
            try:
                strip = p.gray[int(p.h*0.80):, :]
                th, tw = self.tmpl_check_pokemon.shape[:2]
                if strip.shape[0] >= th and strip.shape[1] >= tw:
                    res = cv2.matchTemplate(strip, self.tmpl_check_pokemon, cv2.TM_CCOEFF_NORMED)
                    _, conf, _, max_loc = cv2.minMaxLoc(res)
                    if conf > 0.70:
                        cx = max_loc[0] + tw // 2
                        cy = max_loc[1] + th // 2 + int(p.h * 0.80)
                        scores['POST_CAPTURA'] = min(conf, 1.0)
                        return ResultadoEstrategia(scores, {
                            'check_tmpl': round(conf, 3),
                            'coord_accion': (cx, cy),
                        })
            except:
                pass
        
        return ResultadoEstrategia(scores)
    
    # ── Fusión ponderada ────────────────────────────────────────────────────
    
    def _fusionar(self, estrategias: dict[str, ResultadoEstrategia],
                  pipe: PipelineVision) -> ScreenState:
        """
        Combina todas las estrategias con pesos.
        
        Para cada estado candidato (MAPA, COMBATE, POST_CAPTURA):
          score_total = Σ peso_i * score_i(estado)
        
        Gana el estado con score total más alto, si supera 0.3.
        """
        estados_candidatos = ['MAPA', 'COMBATE', 'POST_CAPTURA']
        scores_totales: dict[str, float] = {}
        debug: dict = {}
        sub_estado: Optional[str] = None
        coord: Optional[tuple[int, int]] = None
        
        for estado in estados_candidatos:
            total = 0.0
            for nombre_estr, resultado in estrategias.items():
                peso = self.PESOS.get(nombre_estr, 0.15)
                score = resultado.scores.get(estado, 0.0)
                total += peso * score
            scores_totales[estado] = round(total, 3)
        
        debug['scores_brutos'] = {
            name: {k: round(v, 3) for k, v in r.scores.items()}
            for name, r in estrategias.items()
        }
        debug['info_estrategias'] = {
            name: r.info
            for name, r in estrategias.items()
        }
        debug['fusion'] = scores_totales
        
        # Extraer info adicional
        for resultado in estrategias.values():
            if 'sub_estado' in resultado.info and resultado.info['sub_estado']:
                sub_estado = resultado.info['sub_estado']
            if 'coord_accion' in resultado.info:
                coord = resultado.info['coord_accion']
        
        # Decisión final
        mejor_estado = max(scores_totales, key=scores_totales.get)
        mejor_score = scores_totales[mejor_estado]
        
        # Detectar MODAL (X button visible)
        hay_x, x_cx, x_cy = self._detectar_x_button(pipe)
        if hay_x and mejor_score < 0.7:
            return ScreenState("MODAL", None, 0.8, scores_totales,
                             {**debug, 'x_coord': (x_cx, x_cy)}, (x_cx, x_cy))
        
        # Detectar CARGANDO (barra amarilla)
        if self._es_cargando(pipe):
            return ScreenState("CARGANDO", None, 0.7, scores_totales,
                             {**debug, 'yellow_bar': True}, None)
        
        if mejor_score < 0.3:
            return ScreenState("DESCONOCIDO", None, mejor_score, scores_totales, debug, None)
        
        return ScreenState(
            estado=mejor_estado,
            sub_estado=sub_estado if mejor_estado == 'POST_CAPTURA' else None,
            confianza=mejor_score,
            scores=scores_totales,
            debug=debug,
            coord_accion=coord,
        )
    
    # ── Auxiliares ──────────────────────────────────────────────────────────
    
    def _detectar_x_button(self, p: PipelineVision) -> tuple[bool, int, int]:
        """Detecta X blanca para cerrar modales."""
        try:
            x_start = int(p.w * 0.85)
            y_start = int(p.h * 0.75)
            zone = p.img[y_start:, x_start:]
            if zone.size == 0:
                return False, 0, 0
            hsv_z = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
            mask_w = cv2.inRange(hsv_z, np.array([0, 0, 210]), np.array([180, 40, 255]))
            if cv2.countNonZero(mask_w) < 50:
                return False, 0, 0
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask_w = cv2.morphologyEx(mask_w, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask_w, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 500 or area > 3000:
                    continue
                x, y, bw, bh = cv2.boundingRect(cnt)
                aspect = max(bw, bh) / (min(bw, bh) + 1) if min(bw, bh) > 0 else 0
                if aspect < 0.8 or aspect > 1.2:
                    continue
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"]) + x_start
                    cy = int(M["m01"] / M["m00"]) + y_start
                    return True, cx, cy
            return False, 0, 0
        except:
            return False, 0, 0
    
    def _es_cargando(self, p: PipelineVision) -> bool:
        """Detecta pantalla de carga (barra amarilla)."""
        try:
            strip = p.gray[int(p.h * 0.95):, :]
            bright = cv2.inRange(p.hsv[int(p.h*0.95):, :],
                                 np.array([20, 100, 150]), np.array([40, 255, 255]))
            pct_yellow = cv2.countNonZero(bright) / (strip.size + 1)
            return pct_yellow > 0.05
        except:
            return False


# ─── Entry point para pruebas rápidas ───────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python3 detector_estados.py <ruta_imagen>")
        sys.exit(1)
    img = cv2.imread(sys.argv[1])
    if img is None:
        print(f"No se pudo leer: {sys.argv[1]}")
        sys.exit(1)
    det = DetectorEstados()
    res = det.analizar(img)
    print(f"Estado: {res.estado}")
    print(f"Sub-estado: {res.sub_estado}")
    print(f"Confianza: {res.confianza:.1%}")
    print(f"Scores: {res.scores}")
    if res.coord_accion:
        print(f"Acción: tap en {res.coord_accion}")
    print(f"Debug: {res.debug}")
