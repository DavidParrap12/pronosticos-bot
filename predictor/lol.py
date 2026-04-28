"""
Predictor de League of Legends (esports).
Usa PandaScore API para obtener datos de partidos profesionales.
"""
import logging
from api import pandascore
from predictor.engine import calculate_prediction, Prediction

logger = logging.getLogger(__name__)


def _calculate_team_winrate(team_name: str, past_matches: list) -> dict:
    """
    Calcula el win rate reciente de un equipo.
    
    Returns:
        Dict con wins, losses, win_rate, total
    """
    wins = losses = 0

    for match in past_matches:
        if not match.get("winner"):
            continue

        opponents = match.get("opponents") or []
        winner = match.get("winner") or {}
        winner_name = (winner.get("name") or "").lower()

        for opp in opponents:
            opp_data = opp.get("opponent") or {}
            opp_name = (opp_data.get("name") or "").lower()

            if team_name.lower() in opp_name or opp_name in team_name.lower():
                if team_name.lower() in winner_name or winner_name in team_name.lower():
                    wins += 1
                else:
                    losses += 1
                break

    total = wins + losses
    return {
        "wins": wins,
        "losses": losses,
        "total": total,
        "win_rate": wins / total if total > 0 else 0.5,
    }


def _get_h2h_from_past(team1: str, team2: str, past_matches: list) -> dict:
    """
    Busca enfrentamientos directos entre dos equipos.
    """
    t1_wins = t2_wins = 0

    for match in past_matches:
        opponents = match.get("opponents") or []
        if len(opponents) < 2:
            continue

        names = []
        for opp in opponents:
            opp_data = opp.get("opponent") or {}
            names.append((opp_data.get("name") or "").lower())

        t1_in = any(team1.lower() in n or n in team1.lower() for n in names)
        t2_in = any(team2.lower() in n or n in team2.lower() for n in names)

        if t1_in and t2_in:
            winner = match.get("winner") or {}
            winner_name = (winner.get("name") or "").lower()

            if team1.lower() in winner_name or winner_name in team1.lower():
                t1_wins += 1
            elif team2.lower() in winner_name or winner_name in team2.lower():
                t2_wins += 1

    return {
        "team1_wins": t1_wins,
        "team2_wins": t2_wins,
        "total": t1_wins + t2_wins,
    }


def get_upcoming_matches() -> list:
    """
    Obtiene los próximos partidos de LoL formateados para predicción.
    
    Returns:
        Lista de dicts con info del match
    """
    if not pandascore._is_configured():
        return []

    matches = pandascore.get_upcoming_lol_matches(per_page=10)
    result = []

    for match in matches:
        opponents = match.get("opponents") or []
        if len(opponents) < 2:
            continue

        team1 = opponents[0].get("opponent", {})
        team2 = opponents[1].get("opponent", {})

        league = match.get("league") or {}
        tournament = match.get("tournament") or {}

        result.append({
            "match_id": match.get("id"),
            "team1_name": team1.get("name", "TBD"),
            "team1_id": team1.get("id"),
            "team2_name": team2.get("name", "TBD"),
            "team2_id": team2.get("id"),
            "league_name": league.get("name", "Unknown"),
            "tournament_name": tournament.get("name", ""),
            "begin_at": match.get("begin_at", ""),
            "number_of_games": match.get("number_of_games", 1),
        })

    return result


def predict_match(
    team1_name: str,
    team2_name: str,
    league_name: str = "LoL",
    event_id: str = None,
) -> Prediction:
    """
    Genera una predicción para un partido de LoL.
    
    Args:
        team1_name: Equipo 1 (blue side / "local")
        team2_name: Equipo 2 (red side / "visitante")
        league_name: Nombre de la liga/torneo
        event_id: ID del partido
    
    Returns:
        Prediction object
    """
    logger.info(f"Analizando LoL: {team1_name} vs {team2_name} ({league_name})")

    past_matches = pandascore.get_past_lol_matches(per_page=50)

    # ---- Factor 1: Win Rate reciente ----
    t1_stats = _calculate_team_winrate(team1_name, past_matches)
    t2_stats = _calculate_team_winrate(team2_name, past_matches)

    if t1_stats["total"] > 0 and t2_stats["total"] > 0:
        wr_score = t1_stats["win_rate"] / max(t1_stats["win_rate"] + t2_stats["win_rate"], 0.01)
    else:
        wr_score = 0.5

    # ---- Factor 2: Posición en torneo (basada en win rate relativo) ----
    # Sin tabla formal, usamos el win rate como proxy
    tournament_score = wr_score  # Similar al win rate

    # ---- Factor 3: H2H ----
    h2h = _get_h2h_from_past(team1_name, team2_name, past_matches)
    if h2h["total"] > 0:
        h2h_score = h2h["team1_wins"] / h2h["total"]
    else:
        h2h_score = 0.5

    # ---- Factor 4: Side preference (blue side tiene ~52% win rate históricamente) ----
    side_score = 0.52  # Blue side advantage

    # ---- Construir predicción ----
    factor_scores = {
        "win_rate": round(wr_score, 3),
        "tournament_position": round(tournament_score, 3),
        "head_to_head": round(h2h_score, 3),
        "side_preference": round(side_score, 3),
    }

    factors_desc = {}

    if wr_score > 0.55:
        factors_desc["win_rate"] = f"📊 {team1_name} mejor WR ({t1_stats['wins']}-{t1_stats['losses']})"
    elif wr_score < 0.45:
        factors_desc["win_rate"] = f"📊 {team2_name} mejor WR ({t2_stats['wins']}-{t2_stats['losses']})"

    if h2h["total"] > 0:
        factors_desc["head_to_head"] = f"⚔️ H2H: {h2h['team1_wins']}-{h2h['team2_wins']}"

    factors_desc["side_preference"] = f"🔵 {team1_name} blue side (52% avg)"

    return calculate_prediction(
        sport="lol",
        league=league_name,
        home_team=team1_name,
        away_team=team2_name,
        factor_scores=factor_scores,
        factors_description=factors_desc,
        event_id=str(event_id) if event_id else None,
    )
