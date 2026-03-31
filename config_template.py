# ==============================================================================
# ATTENZIONE!!!!!!!
# Questo file è un template. Rinominalo in "config.py" e inserisci le tue chiavi API.
# NON COMMETTERE QUESTO FILE SU VERSION CONTROL!
# ==============================================================================

"""
Configuration file for API keys and secrets.
DO NOT COMMIT THIS FILE TO VERSION CONTROL!
This file is listed in .gitignore for security.
"""

# MapTiler API Key - Get yours at https://cloud.maptiler.com/
# Sign up for a free account and create an API key
MAPTILER_API_KEY = "INSERT YOUR API KEY HERE"

def get_maptiler_key() -> str:
    """Returns the MapTiler API key for 3D map visualization."""
    return MAPTILER_API_KEY
