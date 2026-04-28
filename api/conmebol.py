"""
Cliente para torneos CONMEBOL (Libertadores y Sudamericana).
Usa ESPN API — 100% gratuita, sin key, sin límites.
"""
import requests
import logging
from datetime import datetime, timedelta

from api import cache

logger = logging.getLogger(__name__)

# ESPN API endpoints (gratuitos, sin autenticación)
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

CONMEBOL_TOURNAMENTS = {
    "Copa Libertadores": "conmebol.libertadores",
    "Copa Sudamericana": "conmebol.sudamericana",
}


def _get_espn(slug: str, endpoint: str = "scoreboard") -> dict:
    """Petición a ESPN API (gratuita, sin key)."""
    url = f"{ESPN_BASE}/{slug}/{endpoint}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
        else:
            logger.debug(f"ESPN {r.status_code} para {slug}/{endpoint}")
            return {}
    except Exception as e:
        logger.error(f"Error ESPN: {e}")
        return {}


def get_conmebol_matches_today(date_str: str = None) -> list:
    """
    Obtiene partidos de Libertadores y Sudamericana para hoy.
    Usa ESPN API gratuita.

    Returns:
        Lista de dicts con info del partido
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    cache_params = {"date": date_str, "source": "conmebol_espn"}
    cached = cache.get("conmebol_matches", cache_params, ttl=1800)
    if cached is not None:
        return cached

    matches = []

    for tournament_name, slug in CONMEBOL_TOURNAMENTS.items():
        try:
            # ESPN scoreboard muestra los partidos del día actual
            data = _get_espn(slug, "scoreboard")
            events = data.get("events") or []

            for event in events:
                competitions = event.get("competitions") or [{}]
                comp = competitions[0] if competitions else {}
                competitors = comp.get("competitors") or []

                if len(competitors) < 2:
                    continue

                # En ESPN, el competitor con homeAway="home" es local
                home_data = None
                away_data = None
                for c in competitors:
                    if c.get("homeAway") == "home":
                        home_data = c
                    else:
                        away_data = c

                if not home_data or not away_data:
                    home_data = competitors[0]
                    away_data = competitors[1]

                home_team = home_data.get("team", {})
                away_team = away_data.get("team", {})

                status_info = event.get("status", {})
                status_type = status_info.get("type", {})

                match_info = {
                    "league_name": tournament_name,
                    "league_id": f"espn_{slug}",
                    "home_team": home_team.get("displayName", home_team.get("name", "?")),
                    "away_team": away_team.get("displayName", away_team.get("name", "?")),
                    "home_team_id": home_team.get("id", ""),
                    "away_team_id": away_team.get("id", ""),
                    "event_id": f"espn_{event.get('id', '')}",
                    "home_score": home_data.get("score", "0"),
                    "away_score": away_data.get("score", "0"),
                    "status": status_type.get("description", "Scheduled"),
                    "status_state": status_type.get("state", "pre"),
                    "start_time": event.get("date", ""),
                    "venue": comp.get("venue", {}).get("fullName", ""),
                    "source": "espn",
                }
                matches.append(match_info)

            if events:
                logger.info(f"⚽ {tournament_name}: {len(events)} partidos encontrados (ESPN)")

        except Exception as e:
            logger.error(f"Error obteniendo {tournament_name} de ESPN: {e}")

    cache.set("conmebol_matches", cache_params, matches)
    return matches


def get_conmebol_past_results(tournament: str = None) -> list:
    """
    Obtiene resultados pasados recientes de Libertadores/Sudamericana.
    Usa ESPN API para obtener resultados.

    Returns:
        Lista en formato compatible con TheSportsDB
    """
    cache_params = {"source": "conmebol_past_espn", "tournament": tournament or "all"}
    cached = cache.get("conmebol_past", cache_params, ttl=3600)
    if cached is not None:
        return cached

    results = []

    tournaments = (
        {tournament: CONMEBOL_TOURNAMENTS[tournament]}
        if tournament and tournament in CONMEBOL_TOURNAMENTS
        else CONMEBOL_TOURNAMENTS
    )

    for name, slug in tournaments.items():
        try:
            # Buscar resultados recientes
            data = _get_espn(slug, "scoreboard")
            events = data.get("events") or []

            for event in events:
                status_state = event.get("status", {}).get("type", {}).get("state", "")
                if status_state != "post":
                    continue  # Solo partidos terminados

                competitions = event.get("competitions") or [{}]
                comp = competitions[0] if competitions else {}
                competitors = comp.get("competitors") or []

                if len(competitors) < 2:
                    continue

                home = None
                away = None
                for c in competitors:
                    if c.get("homeAway") == "home":
                        home = c
                    else:
                        away = c

                if not home or not away:
                    home = competitors[0]
                    away = competitors[1]

                results.append({
                    "strHomeTeam": home.get("team", {}).get("displayName", "?"),
                    "strAwayTeam": away.get("team", {}).get("displayName", "?"),
                    "intHomeScore": str(home.get("score", 0)),
                    "intAwayScore": str(away.get("score", 0)),
                    "strLeague": name,
                    "idEvent": f"espn_{event.get('id', '')}",
                })

        except Exception as e:
            logger.error(f"Error obteniendo resultados {name}: {e}")

    cache.set("conmebol_past", cache_params, results)
    return results
