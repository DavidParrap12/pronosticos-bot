"""
Cliente para PandaScore API (tier gratuito).
Proporciona datos de esports: League of Legends matches y stats.
"""
import requests
import time
import logging

from api import cache
from config import PANDASCORE_TOKEN, PANDASCORE_BASE

logger = logging.getLogger(__name__)

# Rate limiting para free tier
_last_request_time = 0
_MIN_INTERVAL = 0.5  # Conservador para 1000 req/hr


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _is_configured() -> bool:
    """Verifica si PandaScore está configurado."""
    return bool(PANDASCORE_TOKEN)


def _get(endpoint: str, params: dict = None) -> list | dict:
    """
    Realiza una petición GET a PandaScore.
    
    Args:
        endpoint: Ruta del endpoint (ej: '/lol/matches/upcoming')
        params: Parámetros de query
    
    Returns:
        Respuesta JSON
    """
    if not _is_configured():
        logger.warning("PandaScore no configurado. Agrega PANDASCORE_TOKEN en config.py")
        return []

    _rate_limit()
    url = f"{PANDASCORE_BASE}{endpoint}"
    headers = {"Authorization": f"Bearer {PANDASCORE_TOKEN}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Error en PandaScore {endpoint}: {e}")
        return []


def get_upcoming_lol_matches(per_page: int = 10) -> list:
    """
    Obtiene los próximos partidos de League of Legends.
    
    Args:
        per_page: Número de resultados
    
    Returns:
        Lista de partidos próximos
    """
    cache_params = {"per_page": per_page}
    cached = cache.get("lol_upcoming", cache_params, ttl=1800)
    if cached is not None:
        return cached

    matches = _get("/lol/matches/upcoming", {
        "sort": "begin_at",
        "per_page": per_page,
        "filter[status]": "not_started",
    })

    cache.set("lol_upcoming", cache_params, matches)
    return matches


def get_running_lol_matches() -> list:
    """Obtiene partidos de LoL en curso."""
    cache_params = {}
    cached = cache.get("lol_running", cache_params, ttl=300)  # 5 min
    if cached is not None:
        return cached

    matches = _get("/lol/matches/running")

    cache.set("lol_running", cache_params, matches)
    return matches


def get_past_lol_matches(per_page: int = 20) -> list:
    """
    Obtiene los últimos resultados de partidos LoL.
    
    Args:
        per_page: Número de resultados
    
    Returns:
        Lista de partidos pasados con resultados
    """
    cache_params = {"per_page": per_page}
    cached = cache.get("lol_past", cache_params, ttl=3600)
    if cached is not None:
        return cached

    matches = _get("/lol/matches/past", {
        "sort": "-begin_at",
        "per_page": per_page,
    })

    cache.set("lol_past", cache_params, matches)
    return matches


def get_team_stats(team_slug: str) -> dict:
    """
    Obtiene estadísticas de un equipo de LoL.
    
    Args:
        team_slug: Slug del equipo (ej: 't1', 'gen-g')
    
    Returns:
        Datos del equipo
    """
    cache_params = {"slug": team_slug}
    cached = cache.get("lol_team", cache_params, ttl=3600)
    if cached is not None:
        return cached

    teams = _get("/lol/teams", {"filter[slug]": team_slug})
    result = teams[0] if teams else {}

    cache.set("lol_team", cache_params, result)
    return result


def get_team_matches(team_id: int, per_page: int = 10) -> list:
    """
    Obtiene partidos recientes de un equipo.
    
    Args:
        team_id: ID del equipo en PandaScore
        per_page: Número de resultados
    
    Returns:
        Lista de partidos
    """
    cache_params = {"team_id": team_id, "per_page": per_page}
    cached = cache.get("lol_team_matches", cache_params, ttl=3600)
    if cached is not None:
        return cached

    matches = _get(f"/lol/matches/past", {
        "sort": "-begin_at",
        "per_page": per_page,
        "filter[opponent_id]": team_id,
    })

    cache.set("lol_team_matches", cache_params, matches)
    return matches


def get_lol_tournaments_running() -> list:
    """Obtiene torneos de LoL en curso."""
    cache_params = {}
    cached = cache.get("lol_tournaments", cache_params, ttl=3600)
    if cached is not None:
        return cached

    tournaments = _get("/lol/tournaments/running")

    cache.set("lol_tournaments", cache_params, tournaments)
    return tournaments
