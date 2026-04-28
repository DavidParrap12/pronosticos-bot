"""
Sistema de caché en JSON local.
Evita exceder rate limits guardando respuestas en archivos.
"""
import json
import os
import time
import hashlib
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"


def _ensure_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(namespace: str, params: dict) -> str:
    """Genera una clave de caché única basada en namespace + params."""
    raw = f"{namespace}:{json.dumps(params, sort_keys=True)}"
    return hashlib.md5(raw.encode()).hexdigest()


def get(namespace: str, params: dict, ttl: int = 3600):
    """
    Obtiene datos del caché si existen y no han expirado.
    
    Args:
        namespace: Categoría (ej: 'events_today', 'table')
        params: Parámetros de la consulta
        ttl: Tiempo de vida en segundos
    
    Returns:
        Datos cacheados o None si expirados/no existen
    """
    _ensure_dir()
    key = _cache_key(namespace, params)
    filepath = CACHE_DIR / f"{key}.json"

    if not filepath.exists():
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            cached = json.load(f)

        if time.time() - cached.get("timestamp", 0) > ttl:
            return None  # Expirado

        return cached.get("data")
    except (json.JSONDecodeError, KeyError):
        return None


def set(namespace: str, params: dict, data):
    """
    Guarda datos en el caché.
    
    Args:
        namespace: Categoría
        params: Parámetros de la consulta
        data: Datos a guardar
    """
    _ensure_dir()
    key = _cache_key(namespace, params)
    filepath = CACHE_DIR / f"{key}.json"

    cached = {
        "timestamp": time.time(),
        "namespace": namespace,
        "params": params,
        "data": data,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(cached, f, ensure_ascii=False, indent=2)


def clear(namespace: str = None):
    """Limpia el caché (todo o por namespace)."""
    _ensure_dir()
    for filepath in CACHE_DIR.glob("*.json"):
        if namespace is None:
            filepath.unlink()
        else:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("namespace") == namespace:
                    filepath.unlink()
            except (json.JSONDecodeError, KeyError):
                filepath.unlink()
