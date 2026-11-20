"""Cache serveur partagé (initialisé sur le serveur Flask dans app.py)."""

from flask_caching import Cache

cache = Cache()

CACHE_CONFIG = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 3600,
    "CACHE_THRESHOLD": 500,
}
