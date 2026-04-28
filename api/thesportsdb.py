"""
Cliente para TheSportsDB API v1 (100% gratis).
Proporciona datos de fútbol y NBA: partidos, resultados, tablas.
"""
import requests
import time
import logging
from datetime import datetime, timedelta

from api import cache
from config import THESPORTSDB_BASE, CACHE_TTL_EVENTS, CACHE_TTL_RESULTS, CACHE_TTL_TABLE

logger = logging.getLogger(__name__)

# Rate limiting: máximo 30 req/min
_last_request_time = 0
_MIN_INTERVAL = 2.1  # ~28 req/min para estar seguros


def _rate_limit():
    """Respeta el rate limit de 30 req/min."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _get(endpoint: str, params: dict = None) -> dict:
    """
    Realiza una petición GET a TheSportsDB con rate limiting.
    
    Args:
        endpoint: Nombre del endpoint (ej: 'eventsday.php')
        params: Parámetros de la query string
    
    Returns:
        Respuesta JSON como dict
    """
    _rate_limit()
    url = f"{THESPORTSDB_BASE}/{endpoint}"
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        # Algunas respuestas vienen vacías (ej: lookuptable para copas)
        if not response.text or response.text.strip() == "":
            return {}
        return response.json()
    except ValueError:
        # JSON inválido o vacío — normal para ligas sin tabla
        logger.debug(f"Respuesta no-JSON de TheSportsDB {endpoint} (normal para copas)")
        return {}
    except requests.RequestException as e:
        logger.error(f"Error en TheSportsDB {endpoint}: {e}")
        return {}


def get_events_by_date(date_str: str = None) -> list:
    """
    Obtiene todos los eventos deportivos de una fecha.
    
    Args:
        date_str: Fecha en formato YYYY-MM-DD (default: hoy)
    
    Returns:
        Lista de eventos
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    cache_params = {"date": date_str}
    cached = cache.get("events_day", cache_params, ttl=CACHE_TTL_EVENTS)
    if cached is not None:
        return cached

    data = _get("eventsday.php", {"d": date_str})
    events = data.get("events") or []

    cache.set("events_day", cache_params, events)
    return events


def get_events_by_league_date(league_id: int, date_str: str = None) -> list:
    """
    Obtiene eventos de una liga específica en una fecha.
    
    Args:
        league_id: ID de la liga en TheSportsDB
        date_str: Fecha en formato YYYY-MM-DD (default: hoy)
    
    Returns:
        Lista de eventos filtrados por liga
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    cache_params = {"league_id": league_id, "date": date_str}
    cached = cache.get("events_league_day", cache_params, ttl=CACHE_TTL_EVENTS)
    if cached is not None:
        return cached

    data = _get("eventsday.php", {"d": date_str, "l": league_id})
    events = data.get("events") or []

    cache.set("events_league_day", cache_params, events)
    return events


def get_past_events(league_id: int) -> list:
    """
    Obtiene los últimos 15 resultados de una liga.
    
    Args:
        league_id: ID de la liga
    
    Returns:
        Lista de eventos pasados con resultados
    """
    cache_params = {"league_id": league_id}
    cached = cache.get("past_events", cache_params, ttl=CACHE_TTL_RESULTS)
    if cached is not None:
        return cached

    data = _get("eventspastleague.php", {"id": league_id})
    events = data.get("events") or []

    cache.set("past_events", cache_params, events)
    return events


def get_next_events_team(team_id: int) -> list:
    """
    Obtiene los próximos 5 eventos de un equipo.
    
    Args:
        team_id: ID del equipo
    
    Returns:
        Lista de próximos eventos
    """
    cache_params = {"team_id": team_id}
    cached = cache.get("next_events_team", cache_params, ttl=CACHE_TTL_EVENTS)
    if cached is not None:
        return cached

    data = _get("eventsnext.php", {"id": team_id})
    events = data.get("events") or []

    cache.set("next_events_team", cache_params, events)
    return events


def get_last_events_team(team_id: int) -> list:
    """
    Obtiene los últimos 5 resultados de un equipo.
    
    Args:
        team_id: ID del equipo
    
    Returns:
        Lista de últimos eventos con resultados
    """
    cache_params = {"team_id": team_id}
    cached = cache.get("last_events_team", cache_params, ttl=CACHE_TTL_RESULTS)
    if cached is not None:
        return cached

    data = _get("eventslast.php", {"id": team_id})
    events = data.get("results") or []

    cache.set("last_events_team", cache_params, events)
    return events


def get_table(league_id: int, season: str) -> list:
    """
    Obtiene la tabla de posiciones de una liga y temporada.
    
    Args:
        league_id: ID de la liga
        season: Temporada (ej: '2025-2026')
    
    Returns:
        Lista de equipos con sus posiciones y stats
    """
    cache_params = {"league_id": league_id, "season": season}
    cached = cache.get("table", cache_params, ttl=CACHE_TTL_TABLE)
    if cached is not None:
        return cached

    data = _get("lookuptable.php", {"l": league_id, "s": season})
    table = data.get("table") or []

    cache.set("table", cache_params, table)
    return table


def search_team(team_name: str) -> dict:
    """
    Busca un equipo por nombre.
    
    Args:
        team_name: Nombre del equipo
    
    Returns:
        Datos del equipo o dict vacío
    """
    cache_params = {"team": team_name}
    cached = cache.get("search_team", cache_params, ttl=86400)  # 24h
    if cached is not None:
        return cached

    data = _get("searchteams.php", {"t": team_name})
    teams = data.get("teams") or []
    result = teams[0] if teams else {}

    cache.set("search_team", cache_params, result)
    return result


def get_team_details(team_id: int) -> dict:
    """
    Obtiene detalles completos de un equipo por ID.
    
    Args:
        team_id: ID del equipo
    
    Returns:
        Datos del equipo
    """
    cache_params = {"team_id": team_id}
    cached = cache.get("team_details", cache_params, ttl=86400)
    if cached is not None:
        return cached

    data = _get("lookupteam.php", {"id": team_id})
    teams = data.get("teams") or []
    result = teams[0] if teams else {}

    cache.set("team_details", cache_params, result)
    return result


def get_head_to_head(home_team: str, away_team: str, league_id: int) -> list:
    """
    Busca enfrentamientos directos entre dos equipos en resultados pasados.
    Usa los últimos resultados de la liga para encontrar H2H.
    
    Args:
        home_team: Nombre del equipo local
        away_team: Nombre del equipo visitante
        league_id: ID de la liga
    
    Returns:
        Lista de enfrentamientos encontrados
    """
    past = get_past_events(league_id)
    h2h = []
    for event in past:
        home = (event.get("strHomeTeam") or "").lower()
        away = (event.get("strAwayTeam") or "").lower()
        t1 = home_team.lower()
        t2 = away_team.lower()

        if (t1 in home and t2 in away) or (t2 in home and t1 in away):
            h2h.append(event)

    return h2h


def get_upcoming_matches(league_ids: dict, date_str: str = None) -> list:
    """
    Obtiene todos los partidos próximos de múltiples ligas para una fecha.
    
    Args:
        league_ids: Dict {nombre_liga: id_liga}
        date_str: Fecha (default: hoy y mañana)
    
    Returns:
        Lista de dicts con info del partido + nombre de la liga
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    all_matches = []

    for league_name, league_id in league_ids.items():
        events = get_events_by_league_date(league_id, date_str)
        for event in events:
            all_matches.append({
                "league_name": league_name,
                "league_id": league_id,
                "event": event,
            })

    # Si no hay partidos hoy, buscar mañana
    if not all_matches:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        for league_name, league_id in league_ids.items():
            events = get_events_by_league_date(league_id, tomorrow)
            for event in events:
                all_matches.append({
                    "league_name": league_name,
                    "league_id": league_id,
                    "event": event,
                    "is_tomorrow": True,
                })

    return all_matches
