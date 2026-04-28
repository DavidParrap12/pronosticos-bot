"""
Predictor de NBA — Multi-mercado.
Analiza partidos de baloncesto usando TheSportsDB y genera predicciones para:
  - Ganador directo
  - Over/Under puntos totales
  - Handicap / Spread
  - Cuarto más anotador
"""
import logging
from api import thesportsdb
from predictor.engine import calculate_prediction, Prediction
from config import NBA_SEASON

logger = logging.getLogger(__name__)

NBA_LEAGUE_ID = 4387


def _get_team_record(team_name: str) -> dict:
    """Obtiene el récord de la temporada de un equipo NBA."""
    table = thesportsdb.get_table(NBA_LEAGUE_ID, NBA_SEASON)

    if not table:
        return {"wins": 0, "losses": 0, "win_pct": 0.5, "position": 0, "total_teams": 0}

    total_teams = len(table)

    for entry in table:
        name = (entry.get("strTeam") or "").lower()
        if team_name.lower() in name or name in team_name.lower():
            try:
                wins = int(entry.get("intWin") or 0)
                losses = int(entry.get("intLoss") or 0)
                position = int(entry.get("intRank") or total_teams)
            except (ValueError, TypeError):
                wins = losses = 0
                position = total_teams

            total = wins + losses
            win_pct = wins / total if total > 0 else 0.5

            return {
                "wins": wins,
                "losses": losses,
                "win_pct": win_pct,
                "position": position,
                "total_teams": total_teams,
            }

    return {"wins": 0, "losses": 0, "win_pct": 0.5, "position": 0, "total_teams": 0}


def _get_recent_form(team_name: str, past_events: list) -> dict:
    """
    Calcula la forma reciente de un equipo NBA (últimos 10 partidos).
    Incluye datos extendidos para mercados múltiples.
    """
    wins = losses = 0
    points_for = points_against = 0
    form_chars = []
    match_totals = []       # Puntos totales por partido
    margins = []            # Margen de victoria/derrota
    games_found = 0

    for event in past_events:
        home = (event.get("strHomeTeam") or "").lower()
        away = (event.get("strAwayTeam") or "").lower()
        name = team_name.lower()

        if name not in home and name not in away:
            continue

        try:
            home_score = int(event.get("intHomeScore") or 0)
            away_score = int(event.get("intAwayScore") or 0)
        except (ValueError, TypeError):
            continue

        total = home_score + away_score
        match_totals.append(total)
        is_home = name in home

        if is_home:
            points_for += home_score
            points_against += away_score
            margin = home_score - away_score
            margins.append(margin)
            if home_score > away_score:
                wins += 1
                form_chars.append("W")
            else:
                losses += 1
                form_chars.append("L")
        else:
            points_for += away_score
            points_against += home_score
            margin = away_score - home_score
            margins.append(margin)
            if away_score > home_score:
                wins += 1
                form_chars.append("W")
            else:
                losses += 1
                form_chars.append("L")

        games_found += 1
        if games_found >= 10:
            break

    total_games = wins + losses
    avg_total = sum(match_totals) / len(match_totals) if match_totals else 215.0
    avg_margin = sum(margins) / len(margins) if margins else 0.0

    return {
        "wins": wins,
        "losses": losses,
        "total": total_games,
        "form_string": "".join(form_chars[:10]),
        "form_score": wins / total_games if total_games > 0 else 0.5,
        "avg_pf": points_for / total_games if total_games > 0 else 105,
        "avg_pa": points_against / total_games if total_games > 0 else 105,
        # Datos extendidos
        "avg_total": avg_total,
        "avg_margin": avg_margin,
        "match_totals": match_totals,
        "over215_rate": sum(1 for t in match_totals if t > 215) / len(match_totals) if match_totals else 0.5,
        "over225_rate": sum(1 for t in match_totals if t > 225) / len(match_totals) if match_totals else 0.4,
    }


def _get_league_avg_total(past_events: list) -> float:
    """Calcula el promedio de puntos totales en la liga."""
    totals = []
    for event in past_events:
        try:
            hs = int(event.get("intHomeScore") or 0)
            aws = int(event.get("intAwayScore") or 0)
            totals.append(hs + aws)
        except (ValueError, TypeError):
            continue
    return sum(totals) / len(totals) if totals else 215.0


def predict_match(
    home_team: str,
    away_team: str,
    event_id: str = None,
) -> dict:
    """
    Genera predicciones multi-mercado para un partido de NBA.
    
    Returns:
        Dict con:
          - prediction: Prediction del ganador
          - markets: Dict con mercados adicionales
    """
    logger.info(f"Analizando NBA: {home_team} vs {away_team}")

    past_events = thesportsdb.get_past_events(NBA_LEAGUE_ID)
    league_avg_total = _get_league_avg_total(past_events)

    # ---- Análisis de equipos ----
    home_record = _get_team_record(home_team)
    away_record = _get_team_record(away_team)
    home_form = _get_recent_form(home_team, past_events)
    away_form = _get_recent_form(away_team, past_events)

    # ---- Factor 1: Record de temporada ----
    if home_record["wins"] + home_record["losses"] > 0:
        record_score = (
            home_record["win_pct"] /
            max(home_record["win_pct"] + away_record["win_pct"], 0.01)
        )
    else:
        record_score = 0.5

    # ---- Factor 2: Racha reciente ----
    if home_form["total"] > 0 and away_form["total"] > 0:
        form_score = (home_form["form_score"] + (1 - away_form["form_score"])) / 2
    else:
        form_score = 0.5

    # ---- Factor 3: H2H ----
    h2h = thesportsdb.get_head_to_head(home_team, away_team, NBA_LEAGUE_ID)
    h2h_home_wins = h2h_away_wins = 0
    h2h_totals = []

    for match in h2h:
        try:
            hs = int(match.get("intHomeScore") or 0)
            aws = int(match.get("intAwayScore") or 0)
        except (ValueError, TypeError):
            continue

        h2h_totals.append(hs + aws)
        match_home = (match.get("strHomeTeam") or "").lower()
        if home_team.lower() in match_home:
            if hs > aws:
                h2h_home_wins += 1
            else:
                h2h_away_wins += 1
        else:
            if aws > hs:
                h2h_home_wins += 1
            else:
                h2h_away_wins += 1

    h2h_total = h2h_home_wins + h2h_away_wins
    h2h_score = h2h_home_wins / h2h_total if h2h_total > 0 else 0.5

    # ---- Factor 4: Puntos promedio ----
    if home_form["total"] > 0 and away_form["total"] > 0:
        home_net = home_form["avg_pf"] - home_form["avg_pa"]
        away_net = away_form["avg_pf"] - away_form["avg_pa"]
        diff = home_net - away_net
        points_score = 0.5 + min(max(diff / 30, -0.4), 0.4)
    else:
        points_score = 0.5

    # ============================================================
    # MERCADO 1: Ganador directo
    # ============================================================
    factor_scores = {
        "record": round(record_score, 3),
        "recent_form": round(form_score, 3),
        "head_to_head": round(h2h_score, 3),
        "points_avg": round(points_score, 3),
    }

    factors_desc = {}
    if record_score > 0.55:
        factors_desc["record"] = f"📊 {home_team} mejor récord ({home_record['wins']}-{home_record['losses']})"
    elif record_score < 0.45:
        factors_desc["record"] = f"📊 {away_team} mejor récord ({away_record['wins']}-{away_record['losses']})"
    if form_score > 0.6:
        factors_desc["recent_form"] = f"🔥 {home_team} en racha ({home_form['form_string'][:5]})"
    elif form_score < 0.4:
        factors_desc["recent_form"] = f"🔥 {away_team} en racha ({away_form['form_string'][:5]})"
    if h2h_total > 0:
        factors_desc["head_to_head"] = f"⚔️ H2H: {h2h_home_wins}-{h2h_away_wins}"
    if points_score > 0.55:
        factors_desc["points_avg"] = f"🏀 {home_team} mejor promedio"
    elif points_score < 0.45:
        factors_desc["points_avg"] = f"🏀 {away_team} mejor promedio"

    winner_prediction = calculate_prediction(
        sport="nba",
        league="NBA",
        home_team=home_team,
        away_team=away_team,
        factor_scores=factor_scores,
        factors_description=factors_desc,
        event_id=event_id,
    )

    # ============================================================
    # MERCADO 2: Over/Under puntos totales
    # ============================================================
    combined_avg = (home_form["avg_total"] + away_form["avg_total"]) / 2
    h2h_avg_total = sum(h2h_totals) / len(h2h_totals) if h2h_totals else combined_avg

    # Línea dinámica basada en los promedios
    projected_total = (
        0.35 * combined_avg +
        0.30 * (home_form["avg_pf"] + away_form["avg_pf"]) +
        0.20 * league_avg_total +
        0.15 * h2h_avg_total
    )

    # Línea redondeada a 0.5
    line = round(projected_total * 2) / 2

    over_prob = 0.5 + (projected_total - line) * 0.04
    over_prob = max(0.35, min(0.72, over_prob))
    ou_confidence = max(52, min(82, 50 + abs(over_prob - 0.5) * 200))

    over_under = {
        "line": line,
        "recommendation": f"OVER {line}" if over_prob > 0.52 else f"UNDER {line}",
        "probability": round(over_prob * 100, 1) if over_prob > 0.52 else round((1 - over_prob) * 100, 1),
        "confidence": round(ou_confidence, 1),
        "projected_total": round(projected_total, 1),
        "detail": f"Prom combinado: {combined_avg:.0f} pts | {home_team}: {home_form['avg_pf']:.0f} pts/g | {away_team}: {away_form['avg_pf']:.0f} pts/g",
    }

    # ============================================================
    # MERCADO 3: Handicap / Spread
    # ============================================================
    home_net_rating = home_form["avg_pf"] - home_form["avg_pa"]
    away_net_rating = away_form["avg_pf"] - away_form["avg_pa"]

    # Ventaja de cancha local (~3.5 puntos en NBA)
    home_court = 3.5
    projected_margin = (home_net_rating - away_net_rating) / 2 + home_court

    # Ajustar con récord de temporada
    if home_record["wins"] + home_record["losses"] > 0 and away_record["wins"] + away_record["losses"] > 0:
        record_diff = (home_record["win_pct"] - away_record["win_pct"]) * 10
        projected_margin = projected_margin * 0.7 + record_diff * 0.3

    spread = round(projected_margin * 2) / 2  # Redondear a 0.5

    if spread > 0:
        spread_team = home_team
        spread_value = -abs(spread)
    else:
        spread_team = away_team
        spread_value = -abs(spread)
        spread = abs(spread)

    spread_confidence = max(52, min(78, 50 + abs(projected_margin) * 1.5))

    handicap = {
        "favorite": spread_team,
        "spread": spread_value,
        "projected_margin": round(projected_margin, 1),
        "confidence": round(spread_confidence, 1),
        "recommendation": f"{spread_team} {spread_value}",
        "detail": f"Net rating: {home_team} {home_net_rating:+.1f} | {away_team} {away_net_rating:+.1f} | Cancha +3.5",
    }

    # ============================================================
    # MERCADO 4: Primer cuarto / Ritmo del partido
    # ============================================================
    # En NBA, el primer cuarto suele tener ~25% del total de puntos
    q1_projected = projected_total * 0.25
    q1_line = round(q1_projected * 2) / 2

    # Equipos ofensivos tienden a empezar fuerte
    home_pace = home_form["avg_pf"] / max(league_avg_total / 2, 1)
    away_pace = away_form["avg_pf"] / max(league_avg_total / 2, 1)
    combined_pace = (home_pace + away_pace) / 2

    pace_label = "ALTO" if combined_pace > 1.05 else ("BAJO" if combined_pace < 0.95 else "MEDIO")

    first_quarter = {
        "q1_line": q1_line,
        "q1_projected": round(q1_projected, 1),
        "pace": pace_label,
        "combined_pace_factor": round(combined_pace, 2),
        "recommendation": f"OVER {q1_line} Q1" if combined_pace > 1.02 else f"UNDER {q1_line} Q1",
        "confidence": round(max(52, min(72, 50 + abs(combined_pace - 1.0) * 200)), 1),
        "detail": f"Ritmo: {pace_label} | Q1 est: {q1_projected:.0f} pts",
    }

    # ============================================================
    # MERCADO 5: Puntos del equipo
    # ============================================================
    home_points_line = round(home_form["avg_pf"] * 2) / 2
    away_points_line = round(away_form["avg_pf"] * 2) / 2

    team_points = {
        "home_team": home_team,
        "home_line": home_points_line,
        "home_avg": round(home_form["avg_pf"], 1),
        "away_team": away_team,
        "away_line": away_points_line,
        "away_avg": round(away_form["avg_pf"], 1),
    }

    # ============================================================
    # Retorno completo
    # ============================================================
    return {
        "prediction": winner_prediction,
        "markets": {
            "over_under": over_under,
            "handicap": handicap,
            "first_quarter": first_quarter,
            "team_points": team_points,
        },
    }
