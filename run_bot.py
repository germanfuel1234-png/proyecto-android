#!/usr/bin/env python3
"""
run_bot.py
==========
Punto de entrada para la nueva arquitectura limpia del bot.

Uso:
    .venv/bin/python3 run_bot.py                      # Iniciar bot (auto-detecta dispositivo)
    .venv/bin/python3 run_bot.py --serial ZY22FVZ      # Serial específico
    .venv/bin/python3 run_bot.py --calibrate           # Guardar overlay de calibración
    .venv/bin/python3 run_bot.py --stats               # Ver estadísticas SQLite
    .venv/bin/python3 run_bot.py --no-debug            # Menos logs
    .venv/bin/python3 run_bot.py --interval 1000       # Loop cada 1s (más lento/seguro)
"""

import sys
import os

# Añadir directorio del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.bot import main

if __name__ == "__main__":
    main()
