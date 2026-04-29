"""
Predictor de NBA — Multi-mercado con datos REALES de ESPN.
Analiza partidos de baloncesto y genera predicciones para:
  - Ganador directo
  - Over/Under puntos totales
  - Handicap / Spread
  - Primer cuarto
  - Líneas por equipo
"""
import logging
from api import espn
from predictor.engine import calculate_prediction, Prediction

logger = logging.getLogger(__name__)


def _get_nba_data(team_name: str) -> dict:
    """Obtiene datos completos de un equipo NBA desde ESPN."""
    record = espn.get_team_record(team_name, "NBA")
    form = espn.get_team_form(team_name, "NBA", last_n=10)
    schedule = espn.get_team_schedule(team_name, "NBA")
    
    if not record and not form:
        return {"has_data": False}
    
    recent = schedule[-10:] if schedule else []
    match_totals = [r["team_score"] + r["opp_score"] for r in recent]
    margins = [r["team_score"] - r["opp_score"] for r in recent]
    
    wins = record.get("wins", 0)
    losses = record.get("losses", 0)
    total = wins + losses
    
    avg_pf = record.get("avg_points_for", 0) or (sum(r["team_score"] for r in recent) / max(len(recent), 1))
    avg_pa = record.get("avg_points_against", 0) or (sum(r["opp_score"] for r in recent) / max(len(recent), 1))
    
    return {
        "has_data": True,
        "wins": wins,
        "losses": losses,
        "total": total,
        "win_pct": wins / total if total > 0 else 0.5,
        "record_summary": record.get("record_summary", f"{wins}-{losses}"),
        "avg_pf": round(avg_pf, 1),
        "avg_pa": round(avg_pa, 1),
        "differential": record.get("differential", round(avg_pf - avg_pa, 1)),
        "form_score": form.get("win_rate", 0.5) if form else 0.5,
        "form_string": form.get("form_string", "") if form else "",
        "avg_total": sum(match_totals) / max(len(match_totals), 1) if match_totals else 215,
        "avg_margin": sum(margins) / max(len(margins), 1) if margins else 0,
        "match_totals": match_totals,
        "over215_rate": sum(1 for t in match_totals if t > 215) / max(len(match_totals), 1) if match_totals else 0.5,
    }


def predict_match(
    home_team: str,
    away_team: str,
    event_id: str = None,
) -> dict:
    """
    Genera predicciones multi-mercado para un partido de NBA.
    Usa datos REALES de ESPN API.
    """
    logger.info(f"Analizando NBA: {home_team} vs {away_team}")

    home = _get_nba_data(home_team)
    away = _get_nba_data(away_team)
    
    has_data = home.get("has_data", False) and away.get("has_data", False)
    
    if has_data:
        logger.info(f"  ✅ NBA real: {home_team} ({home['record_summary']}) vs {away_team} ({away['record_summary']})")
    else:
        logger.warning(f"  ⚠️ Sin datos ESPN para {home_team} o {away_team}")

    # ---- Factor 1: Récord de temporada ----
    if has_data and (home["total"] > 0 and away["total"] > 0):
        record_score = home["win_pct"] / max(home["win_pct"] + away["win_pct"], 0.01)
    else:
        record_score = 0.5

    # ---- Factor 2: Racha reciente ----
    if has_data:
        form_score = (home["form_score"] + (1 - away["form_score"])) / 2
    else:
        form_score = 0.5

    # ---- Factor 3: H2H ----
    h2h = espn.get_head_to_head(home_team, away_team, "NBA")
    h2h_total = h2h.get("total", 0)
    h2h_score = (h2h["team1_wins"] / h2h_total) if h2h_total > 0 else 0.5

    # ---- Factor 4: Net rating ----
    if has_data:
        home_net = home["avg_pf"] - home["avg_pa"]
        away_net = away["avg_pf"] - away["avg_pa"]
        diff = home_net - away_net
        points_score = 0.5 + min(max(diff / 30, -0.4), 0.4)
    else:
        points_score = 0.5
        home_net = away_net = 0

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
    if has_data:
        factors_desc["record"] = f"📊 {home_team} ({home['record_summary']}) vs {away_team} ({away['record_summary']})"
        
        if form_score > 0.55:
            factors_desc["recent_form"] = f"🔥 {home_team} en racha ({home['form_string'][:5]})"
        elif form_score < 0.45:
            factors_desc["recent_form"] = f"🔥 {away_team} en racha ({away['form_string'][:5]})"
        else:
            factors_desc["recent_form"] = f"📈 Forma: {home['form_string'][:5]} vs {away['form_string'][:5]}"
        
        if points_score > 0.55:
            factors_desc["points_avg"] = f"🏀 {home_team} {home['avg_pf']:.0f}pts/g (dif: {home['differential']:+.1f})"
        elif points_score < 0.45:
            factors_desc["points_avg"] = f"🏀 {away_team} {away['avg_pf']:.0f}pts/g (dif: {away['differential']:+.1f})"
    
    if h2h_total > 0:
        factors_desc["head_to_head"] = f"⚔️ H2H: {h2h['team1_wins']}-{h2h['team2_wins']}"

    winner = calculate_prediction(
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
    if has_data:
        combined_avg = (home["avg_total"] + away["avg_total"]) / 2
        projected_total = 0.40 * combined_avg + 0.35 * (home["avg_pf"] + away["avg_pf"]) + 0.25 * 215
    else:
        combined_avg = 215
        projected_total = 215

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
        "detail": f"Prom: {combined_avg:.0f}pts | {home_team}: {home.get('avg_pf',105):.0f}pts/g | {away_team}: {away.get('avg_pf',105):.0f}pts/g",
    }

    # ============================================================
    # MERCADO 3: Handicap / Spread
    # ============================================================
    home_court = 3.5
    projected_margin = (home_net - away_net) / 2 + home_court

    if has_data and home["total"] > 0 and away["total"] > 0:
        record_diff = (home["win_pct"] - away["win_pct"]) * 10
        projected_margin = projected_margin * 0.7 + record_diff * 0.3

    spread = round(projected_margin * 2) / 2
    spread_team = home_team if spread > 0 else away_team
    spread_value = -abs(spread)
    spread_confidence = max(52, min(78, 50 + abs(projected_margin) * 1.5))

    handicap = {
        "favorite": spread_team,
        "spread": spread_value,
        "projected_margin": round(projected_margin, 1),
        "confidence": round(spread_confidence, 1),
        "recommendation": f"{spread_team} {spread_value}",
        "detail": f"Net: {home_team} {home_net:+.1f} | {away_team} {away_net:+.1f} | Cancha +3.5",
    }

    # ============================================================
    # MERCADO 4: Primer cuarto
    # ============================================================
    q1_projected = projected_total * 0.25
    q1_line = round(q1_projected * 2) / 2
    
    if has_data:
        home_pace = home["avg_pf"] / 107.5
        away_pace = away["avg_pf"] / 107.5
    else:
        home_pace = away_pace = 1.0
    
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
    # MERCADO 5: Líneas por equipo
    # ============================================================
    home_line = round(home.get("avg_pf", 105) * 2) / 2
    away_line = round(away.get("avg_pf", 105) * 2) / 2

    team_points = {
        "home_team": home_team,
        "home_line": home_line,
        "home_avg": round(home.get("avg_pf", 105), 1),
        "away_team": away_team,
        "away_line": away_line,
        "away_avg": round(away.get("avg_pf", 105), 1),
    }

    return {
        "prediction": winner,
        "markets": {
            "over_under": over_under,
            "handicap": handicap,
            "first_quarter": first_quarter,
            "team_points": team_points,
        },
    }
