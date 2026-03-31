# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""
Configuration file TEMPLATE for API keys and secrets.
This is a template - il file reale (config.py) viene generato da setup_project.py

DO NOT COMMIT THE ACTUAL config.py FILE TO VERSION CONTROL!
The actual config.py file is listed in .gitignore for security reasons.

Questo file template mostra la struttura di come config.py sarà generato.
"""

# MapTiler API Key - Get yours at https://cloud.maptiler.com/
# Sign up for a free account and create an API key
# Obtain it at: https://cloud.maptiler.com/
# SARÀ INSERITA DURANTE LO SETUP
MAPTILER_API_KEY = "YOUR_API_KEY_HERE"

# Mapbox Access Token (optional, for alternative map provider)
# Get yours at https://account.mapbox.com/
MAPBOX_ACCESS_TOKEN = "YOUR_MAPBOX_TOKEN_HERE"


def get_maptiler_key() -> str:
    """Returns the MapTiler API key for 3D map visualization."""
    return MAPTILER_API_KEY


def get_mapbox_token() -> str:
    """Returns the Mapbox access token (optional)."""
    return MAPBOX_ACCESS_TOKEN


# ==============================================================================
# NOTA PER GLI SVILUPPATORI:
# ==============================================================================
# Se stai eseguendo il setup per la prima volta:
# 1. Esegui: python setup_project.py (Windows: doppio clic su SETUP.bat)
# 2. Inserisci la tua API key MapTiler quando richiesto
# 3. Il file config.py sarà auto-generato con la tua chiave
#
# Se hai già un config.py ma vuoi aggiornare l'API key:
# 1. Edita il file config.py
# 2. Cambia MAPTILER_API_KEY = "nuova_chiave_qui"
# 3. Salva e riavvia il server
# ==============================================================================
