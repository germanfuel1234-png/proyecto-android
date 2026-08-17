#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Sistema de Logging Inteligente para Pokémon Catcher
Graba automáticamente cada análisis para aprendizaje posterior.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════
DATA_DIR = Path("pokemon_data")
DATA_DIR.mkdir(exist_ok=True)

IA_LOG_FILE = DATA_DIR / "ia_analysis.jsonl"
ERRORS_LOG_FILE = DATA_DIR / "errors.jsonl"
FEEDBACK_LOG_FILE = DATA_DIR / "feedback.jsonl"


class AnalysisLogger:
    """Logger de análisis de IA para aprendizaje posterior."""
    
    @staticmethod
    def log_ia_analysis(
        screenshot_hash: str,
        screen_state: str,  # "MAPA", "COMBATE", "DETALLE_POKEMON", etc.
        ia_result: str,
        time_ms: int,
        confidence: float,
        is_correct: Optional[bool] = None
    ) -> None:
        """
        Graba análisis de IA.
        
        Args:
            screenshot_hash: Hash de la screenshot para deduplicación
            screen_state: Estado real de la pantalla
            ia_result: Resultado de IA ("MAPA", "COMBATE", etc.)
            time_ms: Tiempo que tardó IA
            confidence: Confianza del análisis
            is_correct: True/False si el usuario confirma/corrige (opcional)
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "screenshot_hash": screenshot_hash,
            "screen_state": screen_state,
            "ia_result": ia_result,
            "time_ms": time_ms,
            "confidence": confidence,
            "is_correct": is_correct
        }
        
        with open(IA_LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    @staticmethod
    def log_error(
        error_type: str,
        screen_state: str,
        error_message: str,
        user_fix: Optional[str] = None
    ) -> None:
        """
        Graba errores para análisis posterior.
        
        Args:
            error_type: "ia_timeout", "false_positive", "detection_failed", etc.
            screen_state: Estado donde ocurrió el error
            error_message: Descripción del error
            user_fix: Cómo el usuario lo arregló (si aplica)
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "screen_state": screen_state,
            "error_message": error_message,
            "user_fix": user_fix
        }
        
        with open(ERRORS_LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    @staticmethod
    def log_feedback(
        action: str,  # "corrected", "confirmed"
        ia_result: str,
        user_correction: str,
        timestamp: Optional[str] = None
    ) -> None:
        """
        Graba feedback del usuario (cuando el bot se equivoca y tú lo corriges).
        
        Args:
            action: "corrected" o "confirmed"
            ia_result: Lo que IA dijo
            user_correction: Lo que el usuario corrigió
            timestamp: Cuándo pasó
        """
        entry = {
            "timestamp": timestamp or datetime.now().isoformat(),
            "action": action,
            "ia_result": ia_result,
            "user_correction": user_correction
        }
        
        with open(FEEDBACK_LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """Devuelve estadísticas de los datos guardados."""
        stats = {
            "total_ia_analyses": 0,
            "total_errors": 0,
            "total_feedback": 0,
            "ia_accuracy": 0.0,
            "screen_state_distribution": {}
        }
        
        # Contar análisis de IA
        if IA_LOG_FILE.exists():
            with open(IA_LOG_FILE) as f:
                analyses = [json.loads(line) for line in f if line.strip()]
                stats["total_ia_analyses"] = len(analyses)
                
                # Calcular accuracy (solo los que tienen is_correct)
                confirmed = [a for a in analyses if a.get("is_correct") is not None]
                if confirmed:
                    correct = sum(1 for a in confirmed if a["is_correct"])
                    stats["ia_accuracy"] = correct / len(confirmed)
                
                # Distribución de estados
                for a in analyses:
                    state = a.get("screen_state")
                    stats["screen_state_distribution"][state] = \
                        stats["screen_state_distribution"].get(state, 0) + 1
        
        # Contar errores
        if ERRORS_LOG_FILE.exists():
            with open(ERRORS_LOG_FILE) as f:
                stats["total_errors"] = sum(1 for _ in f if _.strip())
        
        # Contar feedback
        if FEEDBACK_LOG_FILE.exists():
            with open(FEEDBACK_LOG_FILE) as f:
                stats["total_feedback"] = sum(1 for _ in f if _.strip())
        
        return stats
    
    @staticmethod
    def export_for_training() -> list:
        """
        Exporta datos listos para generar reglas.
        Retorna lista de tuplas (features, screen_state).
        """
        training_data = []
        
        if not IA_LOG_FILE.exists():
            return training_data
        
        with open(IA_LOG_FILE) as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                
                # Solo usar si es "correcto" o confirmado
                if entry.get("is_correct") is None:
                    continue
                
                features = {
                    "ia_result": entry["ia_result"],
                    "time_ms": entry["time_ms"],
                    "confidence": entry["confidence"],
                }
                
                training_data.append((features, entry["screen_state"]))
        
        return training_data


if __name__ == "__main__":
    # Test
    print("📊 Analysis Logger - Test")
    print("=" * 60)
    
    # Simular algunos análisis
    logger = AnalysisLogger()
    
    logger.log_ia_analysis(
        screenshot_hash="abc123",
        screen_state="MAPA",
        ia_result="MAPA",
        time_ms=2500,
        confidence=0.92,
        is_correct=True
    )
    
    logger.log_ia_analysis(
        screenshot_hash="def456",
        screen_state="COMBATE",
        ia_result="COMBATE",
        time_ms=2800,
        confidence=0.88,
        is_correct=True
    )
    
    logger.log_error(
        error_type="false_positive",
        screen_state="MAPA",
        error_message="Bot detectó combate en mapa",
        user_fix="Presionó BACK"
    )
    
    # Mostrar estadísticas
    stats = logger.get_stats()
    print(f"\n✅ Datos guardados:")
    print(f"   Total análisis de IA: {stats['total_ia_analyses']}")
    print(f"   Total errores: {stats['total_errors']}")
    print(f"   Accuracy de IA: {stats['ia_accuracy']:.0%}")
    print(f"   Distribución: {stats['screen_state_distribution']}")
