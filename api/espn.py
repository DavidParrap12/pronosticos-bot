"""
Cliente ESPN API — Fuente principal de datos deportivos.
100% gratuito, sin key, datos reales de standings, equipos y resultados.
Reemplaza TheSportsDB como fuente de datos para el predictor.
"""
import requests
import logging
from datetime import datetime

from api import cache

logger = logging.getLogger(__name__)

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Mapeo de ligas a slugs ESPN
LEAGUE_SLUGS = {
    # Fútbol
    "Champions League": ("soccer", "uefa.champions"),
    "Premier League": ("soccer", "eng.1"),
    "La Liga": ("soccer", "esp.1"),
    "Serie A": ("soccer", "ita.1"),
    "Liga BetPlay": ("soccer", "col.1"),
    "Copa Libertadores": ("soccer", "conmebol.libertadores"),
    "Copa Sudamericana": ("soccer", "conmebol.sudamericana"),
    # NBA
    "NBA": ("basketball", "nba"),
}


def _get(url: str, timeout: int = 15) -> dict:
    """Petición genérica a ESPN."""
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return {}
    except Exception as e:
        logger.debug(f"ESPN request error: {e}")
        return {}


def _get_slug(league_name: str) -> tuple:
    """Obtiene (sport, slug) para una liga."""
    return LEAGUE_SLUGS.get(league_name, (None, None))


# ============================================================
# Equipos y Team IDs
# ============================================================

def get_teams(league_name: str) -> dict:
    """
    Obtiene todos los equipos de una liga.
    Returns: Dict {team_name: team_id}
    """
    sport, slug = _get_slug(league_name)
    if not slug:
        return {}

    cache_key = f"espn_teams_{slug}"
    cached = cache.get(cache_key, {}, ttl=86400)
    if cached:
        return cached

    data = _get(f"{ESPN_BASE}/{sport}/{slug}/teams")
    teams = {}
    
    sport_list = data.get("sports", [])
    if sport_list:
        league_list = sport_list[0].get("leagues", [])
        if league_list:
            for t in league_list[0].get("teams", []):
                team = t.get("team", {})
                name = team.get("displayName", "")
                tid = team.get("id", "")
                if name and tid:
                    teams[name] = tid
                    # También guardar con nombre corto
                    short = team.get("shortDisplayName", "")
                    if short and short != name:
                        teams[short] = tid
                    abbr = team.get("abbreviation", "")
                    if abbr:
                        teams[abbr] = tid

    cache.set(cache_key, {}, teams)
    return teams


def _find_team_id(team_name: str, league_name: str) -> str:
    """Busca el ESPN team ID por nombre (fuzzy match)."""
    teams = get_teams(league_name)
    
    # Exacto
    if team_name in teams:
        return teams[team_name]
    
    # Parcial
    team_lower = team_name.lower()
    for name, tid in teams.items():
        if team_lower in name.lower() or name.lower() in team_lower:
            return tid
    
    # Buscar palabras clave
    words = team_lower.split()
    for name, tid in teams.items():
        name_lower = name.lower()
        for word in words:
            if len(word) > 3 and word in name_lower:
                return tid
    
    return ""


# ============================================================
# Récord y Estadísticas del equipo
# ============================================================

def get_team_record(team_name: str, league_name: str) -> dict:
    """
    Obtiene el récord y stats de un equipo.
    
    Returns:
        {wins, losses, draws, points, goals_for, goals_against, 
         games_played, record_summary, stats_raw}
    """
    sport, slug = _get_slug(league_name)
    team_id = _find_team_id(team_name, league_name)
    
    if not slug or not team_id:
        return {}

    cache_key = f"espn_record_{slug}_{team_id}"
    cached = cache.get(cache_key, {}, ttl=3600)
    if cached:
        return cached

    data = _get(f"{ESPN_BASE}/{sport}/{slug}/teams/{team_id}")
    team_info = data.get("team", {})
    record_data = team_info.get("record", {})
    
    result = {
        "team_name": team_info.get("displayName", team_name),
        "team_id": team_id,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "points": 0,
        "goals_for": 0,
        "goals_against": 0,
        "games_played": 0,
        "record_summary": "",
    }
    
    items = record_data.get("items", [])
    if items:
        overall = items[0]
        result["record_summary"] = overall.get("summary", "")
        
        stats = {}
        for s in overall.get("stats", []):
            stats[s.get("name", "")] = s.get("value", 0)
        
        # Fútbol
        result["wins"] = int(stats.get("wins", stats.get("gamesWon", 0)))
        result["losses"] = int(stats.get("losses", stats.get("gamesLost", 0)))
        result["draws"] = int(stats.get("ties", stats.get("draws", 0)))
        result["points"] = int(stats.get("points", 0))
        result["goals_for"] = int(stats.get("pointsFor", 0))
        result["goals_against"] = int(stats.get("pointsAgainst", 0))
        result["games_played"] = int(stats.get("gamesPlayed", 0))
        
        # NBA específico
        if "avgPointsFor" in stats:
            result["avg_points_for"] = round(stats.get("avgPointsFor", 0), 1)
            result["avg_points_against"] = round(stats.get("avgPointsAgainst", 0), 1)
            result["differential"] = round(stats.get("differential", 0), 1)
            result["streak"] = int(stats.get("streak", 0))
    
    cache.set(cache_key, {}, result)
    return result


# ============================================================
# Resultados pasados (schedule del equipo)
# ============================================================

def get_team_schedule(team_name: str, league_name: str) -> list:
    """
    Obtiene el calendario/resultados del equipo en la temporada.
    
    Returns:
        Lista de dicts con resultados pasados:
        [{opponent, home_score, away_score, is_home, won, date}]
    """
    sport, slug = _get_slug(league_name)
    team_id = _find_team_id(team_name, league_name)
    
    if not slug or not team_id:
        return []

    cache_key = f"espn_schedule_{slug}_{team_id}"
    cached = cache.get(cache_key, {}, ttl=3600)
    if cached:
        return cached

    data = _get(f"{ESPN_BASE}/{sport}/{slug}/teams/{team_id}/schedule")
    events = data.get("events", [])
    
    results = []
    for event in events:
        comps = event.get("competitions", [{}])
        comp = comps[0] if comps else {}
        
        status = comp.get("status", event.get("status", {}))
        status_type = status.get("type", {})
        
        if not status_type.get("completed", False):
            continue
        
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            continue
        
        # Determinar home/away
        team_comp = None
        opp_comp = None
        for c in competitors:
            if str(c.get("id", "")) == str(team_id):
                team_comp = c
            else:
                opp_comp = c
        
        if not team_comp or not opp_comp:
            team_comp = competitors[0]
            opp_comp = competitors[1]
        
        # Extraer score
        team_score_data = team_comp.get("score", {})
        opp_score_data = opp_comp.get("score", {})
        
        if isinstance(team_score_data, dict):
            team_score = int(team_score_data.get("value", team_score_data.get("displayValue", 0)))
        else:
            try:
                team_score = int(team_score_data)
            except:
                team_score = 0

        if isinstance(opp_score_data, dict):
            opp_score = int(opp_score_data.get("value", opp_score_data.get("displayValue", 0)))
        else:
            try:
                opp_score = int(opp_score_data)
            except:
                opp_score = 0
        
        is_home = team_comp.get("homeAway", "") == "home"
        won = team_comp.get("winner", False)
        
        results.append({
            "opponent": opp_comp.get("team", {}).get("displayName", "?"),
            "team_score": team_score,
            "opp_score": opp_score,
            "is_home": is_home,
            "won": won,
            "date": event.get("date", ""),
            "total_goals": team_score + opp_score,
        })
    
    cache.set(cache_key, {}, results)
    return results


# ============================================================
# Funciones de análisis para el predictor
# ============================================================

def get_team_form(team_name: str, league_name: str, last_n: int = 5) -> dict:
    """
    Calcula la forma reciente del equipo.
    
    Returns:
        {win_rate, avg_goals_scored, avg_goals_conceded, avg_total_goals,
         home_win_rate, away_win_rate, form_string (WDLWW)}
    """
    schedule = get_team_schedule(team_name, league_name)
    
    if not schedule:
        return {}
    
    # Tomar últimos N partidos
    recent = schedule[-last_n:]
    
    if not recent:
        return {}
    
    wins = sum(1 for r in recent if r["won"])
    draws = sum(1 for r in recent if not r["won"] and r["team_score"] == r["opp_score"])
    losses = len(recent) - wins - draws
    
    form_chars = []
    for r in recent:
        if r["won"]:
            form_chars.append("W")
        elif r["team_score"] == r["opp_score"]:
            form_chars.append("D")
        else:
            form_chars.append("L")
    
    home_games = [r for r in recent if r["is_home"]]
    away_games = [r for r in recent if not r["is_home"]]
    
    all_schedule = schedule
    home_all = [r for r in all_schedule if r["is_home"]]
    away_all = [r for r in all_schedule if not r["is_home"]]
    
    return {
        "win_rate": wins / len(recent) if recent else 0,
        "draw_rate": draws / len(recent) if recent else 0,
        "loss_rate": losses / len(recent) if recent else 0,
        "avg_goals_scored": sum(r["team_score"] for r in recent) / len(recent),
        "avg_goals_conceded": sum(r["opp_score"] for r in recent) / len(recent),
        "avg_total_goals": sum(r["total_goals"] for r in recent) / len(recent),
        "home_win_rate": sum(1 for r in home_all if r["won"]) / max(len(home_all), 1),
        "away_win_rate": sum(1 for r in away_all if r["won"]) / max(len(away_all), 1),
        "form_string": "".join(form_chars),
        "games_analyzed": len(recent),
        "total_wins_season": sum(1 for r in all_schedule if r["won"]),
        "total_games_season": len(all_schedule),
    }


def get_head_to_head(team1: str, team2: str, league_name: str) -> dict:
    """
    Busca enfrentamientos directos entre dos equipos.
    
    Returns:
        {team1_wins, team2_wins, draws, total, team1_goals, team2_goals}
    """
    schedule1 = get_team_schedule(team1, league_name)
    
    h2h = {
        "team1_wins": 0,
        "team2_wins": 0,
        "draws": 0,
        "total": 0,
        "team1_goals": 0,
        "team2_goals": 0,
    }
    
    team2_lower = team2.lower()
    
    for match in schedule1:
        opp = match.get("opponent", "").lower()
        # Fuzzy match del oponente
        if team2_lower in opp or opp in team2_lower or any(
            w in opp for w in team2_lower.split() if len(w) > 3
        ):
            h2h["total"] += 1
            h2h["team1_goals"] += match["team_score"]
            h2h["team2_goals"] += match["opp_score"]
            
            if match["won"]:
                h2h["team1_wins"] += 1
            elif match["team_score"] == match["opp_score"]:
                h2h["draws"] += 1
            else:
                h2h["team2_wins"] += 1
    
    return h2h
