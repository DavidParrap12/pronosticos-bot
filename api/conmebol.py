"""
Cliente para API-Football (RapidAPI) — Torneos CONMEBOL.
Cubre Copa Libertadores y Copa Sudamericana.
Tier gratuito: 100 requests/día.

Para activar:
1. Ve a https://rapidapi.com/api-sports/api/api-football/pricing
2. Suscríbete al plan BASIC (gratis)
3. Tu misma RapidAPI key funcionará automáticamente
"""
import requests
import logging
from datetime import datetime, timedelta

from api import cache
from config import RAPIDAPI_KEY

logger = logging.getLogger(__name__)

# API-Football en RapidAPI
APIFOOTBALL_HOST = "api-football-v1.p.rapidapi.com"
APIFOOTBALL_BASE = f"https://{APIFOOTBALL_HOST}/v3"

# IDs de ligas en API-Football
CONMEBOL_LEAGUES = {
    "Copa Libertadores": 13,
    "Copa Sudamericana": 11,
}

# Temporada actual
CONMEBOL_SEASON = 2026


def _is_configured() -> bool:
    """Verifica si API-Football está accesible."""
    return bool(RAPIDAPI_KEY)


def _get(endpoint: str, params: dict = None) -> dict:
    """Petición a API-Football vía RapidAPI."""
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": APIFOOTBALL_HOST,
    }
    url = f"{APIFOOTBALL_BASE}/{endpoint}"

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code == 403:
            logger.warning(
                "API-Football no suscrita. Suscríbete gratis en: "
                "https://rapidapi.com/api-sports/api/api-football/pricing"
            )
            return {}
        if r.status_code == 429:
            logger.warning("API-Football: límite de requests alcanzado (100/día)")
            return {}
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error(f"Error API-Football: {e}")
        return {}


def get_conmebol_matches_today(date_str: str = None) -> list:
    """
    Obtiene partidos de Libertadores y Sudamericana para hoy.

    Returns:
        Lista de dicts con info del partido
    """
    if not _is_configured():
        return []

    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    cache_params = {"date": date_str, "source": "conmebol_apifootball"}
    cached = cache.get("conmebol_matches", cache_params, ttl=1800)
    if cached is not None:
        return cached

    matches = []

    for league_name, league_id in CONMEBOL_LEAGUES.items():
        data = _get("fixtures", {
            "date": date_str,
            "league": league_id,
            "season": CONMEBOL_SEASON,
        })

        fixtures = data.get("response") or []

        # Si no encuentra con 2026, probar 2025
        if not fixtures:
            data = _get("fixtures", {
                "date": date_str,
                "league": league_id,
                "season": CONMEBOL_SEASON - 1,
            })
            fixtures = data.get("response") or []

        for fixture in fixtures:
            teams = fixture.get("teams", {})
            goals = fixture.get("goals", {})
            info = fixture.get("fixture", {})

            matches.append({
                "league_name": league_name,
                "league_id": f"apif_{league_id}",
                "home_team": teams.get("home", {}).get("name", "?"),
                "away_team": teams.get("away", {}).get("name", "?"),
                "home_team_id": teams.get("home", {}).get("id"),
                "away_team_id": teams.get("away", {}).get("id"),
                "event_id": f"apif_{info.get('id', '')}",
                "home_score": goals.get("home"),
                "away_score": goals.get("away"),
                "status": info.get("status", {}).get("long", "Not Started"),
                "start_time": info.get("date", ""),
                "venue": info.get("venue", {}).get("name", ""),
                "source": "api-football",
            })

        if fixtures:
            logger.info(f"⚽ {league_name}: {len(fixtures)} partidos encontrados")

    cache.set("conmebol_matches", cache_params, matches)
    return matches


def get_conmebol_past_results(league_id: int = None) -> list:
    """
    Obtiene resultados pasados de Libertadores/Sudamericana
    para alimentar al predictor.

    Returns:
        Lista en formato compatible con TheSportsDB (strHomeTeam, intHomeScore, etc.)
    """
    cache_params = {"source": "conmebol_past_apifootball", "league": league_id or "all"}
    cached = cache.get("conmebol_past", cache_params, ttl=3600)
    if cached is not None:
        return cached

    results = []
    leagues_to_check = {league_id: ""} if league_id else CONMEBOL_LEAGUES

    for name, lid in (CONMEBOL_LEAGUES.items() if not league_id else [(f"League {league_id}", league_id)]):
        real_id = lid if isinstance(lid, int) else CONMEBOL_LEAGUES.get(name, 13)

        # Últimos 15 partidos finalizados
        data = _get("fixtures", {
            "league": real_id,
            "season": CONMEBOL_SEASON,
            "status": "FT",
            "last": 15,
        })

        fixtures = data.get("response") or []

        # Fallback a temporada anterior
        if not fixtures:
            data = _get("fixtures", {
                "league": real_id,
                "season": CONMEBOL_SEASON - 1,
                "status": "FT",
                "last": 15,
            })
            fixtures = data.get("response") or []

        for fixture in fixtures:
            teams = fixture.get("teams", {})
            goals = fixture.get("goals", {})
            info = fixture.get("fixture", {})

            results.append({
                "strHomeTeam": teams.get("home", {}).get("name", "?"),
                "strAwayTeam": teams.get("away", {}).get("name", "?"),
                "intHomeScore": str(goals.get("home", 0)),
                "intAwayScore": str(goals.get("away", 0)),
                "strLeague": name,
                "idEvent": f"apif_{info.get('id', '')}",
                "dateEvent": info.get("date", ""),
            })

    cache.set("conmebol_past", cache_params, results)
    return results


def get_team_stats(team_id: int, league_id: int = 13) -> dict:
    """
    Obtiene estadísticas de un equipo en un torneo.

    Returns:
        Dict con stats del equipo
    """
    if not team_id:
        return {}

    cache_params = {"team": team_id, "league": league_id}
    cached = cache.get("conmebol_team_stats", cache_params, ttl=86400)
    if cached is not None:
        return cached

    data = _get("teams/statistics", {
        "team": team_id,
        "league": league_id,
        "season": CONMEBOL_SEASON,
    })

    stats = data.get("response") or {}
    cache.set("conmebol_team_stats", cache_params, stats)
    return stats
