"""
Predictor de fútbol — Multi-mercado.
Analiza partidos usando TheSportsDB y genera predicciones para:
  - Ganador (1X2)
  - Over/Under goles (línea 2.5)
  - Ambos Anotan (BTTS)
  - Córners estimados
  - Resultado exacto más probable
"""
import logging
from api import thesportsdb
from predictor.engine import calculate_prediction, Prediction
from config import FOOTBALL_SEASONS

logger = logging.getLogger(__name__)


# ================================================================
# Análisis de datos
# ================================================================

def _get_team_form(team_name: str, past_events: list) -> dict:
    """
    Calcula la forma reciente de un equipo (últimos 5 partidos).
    Incluye datos extendidos para mercados múltiples.
    """
    wins = draws = losses = gf = ga = 0
    form_chars = []
    match_goals = []        # Total de goles por partido
    both_scored = 0         # Partidos donde ambos anotaron
    clean_sheets = 0        # Partidos sin recibir gol
    failed_to_score = 0     # Partidos sin anotar
    high_scoring = 0        # Partidos con 3+ goles totales

    for event in past_events[:15]:  # Revisar más para encontrar 5 del equipo
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

        total_goals = home_score + away_score
        match_goals.append(total_goals)
        is_home = name in home

        if is_home:
            gf += home_score
            ga += away_score
            if home_score > 0 and away_score > 0:
                both_scored += 1
            if away_score == 0:
                clean_sheets += 1
            if home_score == 0:
                failed_to_score += 1
            if home_score > away_score:
                wins += 1
                form_chars.append("W")
            elif home_score < away_score:
                losses += 1
                form_chars.append("L")
            else:
                draws += 1
                form_chars.append("D")
        else:
            gf += away_score
            ga += home_score
            if home_score > 0 and away_score > 0:
                both_scored += 1
            if home_score == 0:
                clean_sheets += 1
            if away_score == 0:
                failed_to_score += 1
            if away_score > home_score:
                wins += 1
                form_chars.append("W")
            elif away_score < home_score:
                losses += 1
                form_chars.append("L")
            else:
                draws += 1
                form_chars.append("D")

        if total_goals >= 3:
            high_scoring += 1

        if len(form_chars) >= 5:
            break

    total = wins + draws + losses
    avg_goals_total = sum(match_goals) / len(match_goals) if match_goals else 2.5

    return {
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": gf,
        "goals_against": ga,
        "total": total,
        "form_string": "".join(form_chars[:5]),
        "form_score": (wins * 3 + draws) / max(total * 3, 1),
        # Datos extendidos para mercados
        "avg_goals_for": gf / total if total > 0 else 1.2,
        "avg_goals_against": ga / total if total > 0 else 1.0,
        "avg_goals_total": avg_goals_total,
        "btts_rate": both_scored / total if total > 0 else 0.5,
        "clean_sheet_rate": clean_sheets / total if total > 0 else 0.2,
        "failed_to_score_rate": failed_to_score / total if total > 0 else 0.2,
        "over25_rate": high_scoring / total if total > 0 else 0.5,
    }


def _get_league_avg_goals(past_events: list) -> float:
    """Calcula el promedio de goles por partido en la liga."""
    total_goals = 0
    count = 0
    for event in past_events:
        try:
            hs = int(event.get("intHomeScore") or 0)
            aws = int(event.get("intAwayScore") or 0)
            total_goals += hs + aws
            count += 1
        except (ValueError, TypeError):
            continue
    return total_goals / count if count > 0 else 2.5


def _get_table_position(team_name: str, league_id: int) -> dict:
    """Obtiene la posición en la tabla de un equipo."""
    season = FOOTBALL_SEASONS.get(league_id, "2025-2026")
    table = thesportsdb.get_table(league_id, season)

    if not table:
        return {"position": 0, "total_teams": 0, "relative_position": 0.5}

    total = len(table)
    position = total

    for entry in table:
        name_in_table = (entry.get("strTeam") or "").lower()
        if team_name.lower() in name_in_table or name_in_table in team_name.lower():
            try:
                position = int(entry.get("intRank") or total)
            except (ValueError, TypeError):
                position = total
            break

    relative = 1.0 - (position - 1) / max(total - 1, 1) if total > 1 else 0.5

    return {
        "position": position,
        "total_teams": total,
        "relative_position": relative,
    }


def _estimate_corners(home_form: dict, away_form: dict, league_avg_goals: float) -> dict:
    """
    Estima córners basado en estilo de juego.
    Equipos con más goles y más ataques tienden a tener más córners.
    Promedio en ligas top: ~10 córners/partido.
    
    Heurística:
    - Equipos ofensivos (muchos goles) → más córners
    - Equipos defensivos (pocos goles recibidos) → fuerzan más córners al rival
    - Liga con muchos goles → más córners en general
    """
    base_corners = 10.0  # Promedio estadístico global

    # Factor ofensivo: más goles = más córners
    home_offensive = home_form["avg_goals_for"] / max(league_avg_goals / 2, 0.5)
    away_offensive = away_form["avg_goals_for"] / max(league_avg_goals / 2, 0.5)

    # Factor de intensidad: suma de goles totales
    combined_goals = (home_form["avg_goals_total"] + away_form["avg_goals_total"]) / 2
    intensity = combined_goals / max(league_avg_goals, 1.0)

    estimated = base_corners * (0.4 + 0.3 * intensity + 0.15 * home_offensive + 0.15 * away_offensive)
    estimated = max(6.0, min(15.0, estimated))  # Rango realista: 6-15

    # Línea recomendada (redondeada a 0.5)
    line = round(estimated * 2) / 2

    # Probabilidad Over
    over_prob = 0.5 + (estimated - line) * 0.15
    over_prob = max(0.35, min(0.70, over_prob))

    return {
        "estimated": round(estimated, 1),
        "line": line,
        "over_probability": round(over_prob, 2),
        "home_corners_est": round(estimated * (home_offensive / (home_offensive + away_offensive + 0.01)), 1),
        "away_corners_est": round(estimated * (away_offensive / (home_offensive + away_offensive + 0.01)), 1),
    }


def _predict_exact_score(home_form: dict, away_form: dict, home_advantage: bool = True) -> dict:
    """
    Predice el resultado exacto más probable.
    Basado en promedios de goles con distribución de Poisson simplificada.
    """
    home_attack = home_form["avg_goals_for"]
    away_defense = away_form["avg_goals_against"]
    away_attack = away_form["avg_goals_for"]
    home_defense = home_form["avg_goals_against"]

    # Expected goals
    home_xg = (home_attack + away_defense) / 2
    away_xg = (away_attack + home_defense) / 2

    # Ventaja local
    if home_advantage:
        home_xg *= 1.15
        away_xg *= 0.90

    home_xg = max(0.3, min(3.5, home_xg))
    away_xg = max(0.2, min(3.0, away_xg))

    # Resultados más probables (simplificación sin Poisson completo)
    scores = {}
    for hg in range(5):
        for ag in range(5):
            # Probabilidad simplificada basada en distancia al xG
            h_prob = max(0.01, 1.0 - abs(hg - home_xg) * 0.35)
            a_prob = max(0.01, 1.0 - abs(ag - away_xg) * 0.40)
            scores[f"{hg}-{ag}"] = round(h_prob * a_prob, 4)

    # Normalizar
    total = sum(scores.values())
    scores = {k: round(v / total * 100, 1) for k, v in scores.items()}

    # Top 3 más probables
    top_scores = sorted(scores.items(), key=lambda x: -x[1])[:3]

    return {
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "top_scores": top_scores,
    }


# ================================================================
# Predicción principal multi-mercado
# ================================================================

def predict_match(
    home_team: str,
    away_team: str,
    league_name: str,
    league_id: int,
    event_id: str = None,
) -> dict:
    """
    Genera predicciones multi-mercado para un partido de fútbol.
    
    Returns:
        Dict con:
          - prediction: Prediction del ganador (1X2)
          - markets: Dict con todos los mercados adicionales
    """
    logger.info(f"Analizando: {home_team} vs {away_team} ({league_name})")

    past_events = thesportsdb.get_past_events(league_id)
    league_avg = _get_league_avg_goals(past_events)

    # ---- Análisis de equipos ----
    home_form = _get_team_form(home_team, past_events)
    away_form = _get_team_form(away_team, past_events)
    home_pos = _get_table_position(home_team, league_id)
    away_pos = _get_table_position(away_team, league_id)

    # ---- Factor 1: Posición en tabla ----
    if home_pos["total_teams"] > 0 and away_pos["total_teams"] > 0:
        table_score = (home_pos["relative_position"] + (1 - away_pos["relative_position"])) / 2
    else:
        table_score = 0.5

    # ---- Factor 2: Racha reciente ----
    if home_form["total"] > 0 and away_form["total"] > 0:
        form_score = (home_form["form_score"] + (1 - away_form["form_score"])) / 2
    else:
        form_score = 0.5

    # ---- Factor 3: Ventaja local ----
    home_advantage_score = 0.58

    # ---- Factor 4: H2H ----
    h2h = thesportsdb.get_head_to_head(home_team, away_team, league_id)
    h2h_home_wins = h2h_away_wins = h2h_draws = 0
    h2h_goals = []

    for match in h2h:
        try:
            hs = int(match.get("intHomeScore") or 0)
            aws = int(match.get("intAwayScore") or 0)
        except (ValueError, TypeError):
            continue

        h2h_goals.append(hs + aws)
        match_home = (match.get("strHomeTeam") or "").lower()
        if home_team.lower() in match_home:
            if hs > aws:
                h2h_home_wins += 1
            elif hs < aws:
                h2h_away_wins += 1
            else:
                h2h_draws += 1
        else:
            if aws > hs:
                h2h_home_wins += 1
            elif aws < hs:
                h2h_away_wins += 1
            else:
                h2h_draws += 1

    h2h_total = h2h_home_wins + h2h_away_wins + h2h_draws
    h2h_score = (h2h_home_wins + h2h_draws * 0.5) / h2h_total if h2h_total > 0 else 0.5

    # ---- Factor 5: Forma goleadora ----
    if home_form["total"] > 0 and away_form["total"] > 0:
        home_gpg = home_form["avg_goals_for"]
        away_gpg = away_form["avg_goals_for"]
        home_gca = home_form["avg_goals_against"]
        away_gca = away_form["avg_goals_against"]
        diff = (home_gpg - home_gca) - (away_gpg - away_gca)
        goals_score = 0.5 + min(max(diff / 4, -0.4), 0.4)
    else:
        goals_score = 0.5

    # ============================================================
    # MERCADO 1: Ganador (1X2)
    # ============================================================
    factor_scores = {
        "table_position": round(table_score, 3),
        "recent_form": round(form_score, 3),
        "home_advantage": round(home_advantage_score, 3),
        "head_to_head": round(h2h_score, 3),
        "goals_form": round(goals_score, 3),
    }

    factors_desc = {}
    if table_score > 0.6:
        factors_desc["table_position"] = f"📊 {home_team} mejor posición"
    elif table_score < 0.4:
        factors_desc["table_position"] = f"📊 {away_team} mejor posición"
    if form_score > 0.6:
        factors_desc["recent_form"] = f"🔥 {home_team} en racha ({home_form['form_string']})"
    elif form_score < 0.4:
        factors_desc["recent_form"] = f"🔥 {away_team} en racha ({away_form['form_string']})"
    factors_desc["home_advantage"] = f"🏠 Ventaja local: {home_team}"
    if h2h_total > 0:
        factors_desc["head_to_head"] = f"⚔️ H2H: {h2h_home_wins}W-{h2h_draws}D-{h2h_away_wins}L"
    if goals_score > 0.6:
        factors_desc["goals_form"] = f"⚽ {home_team} mejor ataque"
    elif goals_score < 0.4:
        factors_desc["goals_form"] = f"⚽ {away_team} mejor ataque"

    winner_prediction = calculate_prediction(
        sport="football",
        league=league_name,
        home_team=home_team,
        away_team=away_team,
        factor_scores=factor_scores,
        factors_description=factors_desc,
        event_id=event_id,
    )

    # ============================================================
    # MERCADO 2: Over/Under 2.5 goles
    # ============================================================
    combined_avg_goals = (home_form["avg_goals_total"] + away_form["avg_goals_total"]) / 2
    home_over25 = home_form["over25_rate"]
    away_over25 = away_form["over25_rate"]

    # H2H goals influence
    h2h_avg_goals = sum(h2h_goals) / len(h2h_goals) if h2h_goals else combined_avg_goals

    over25_prob = (
        0.30 * (1.0 if combined_avg_goals > 2.5 else combined_avg_goals / 2.5) +
        0.25 * home_over25 +
        0.25 * away_over25 +
        0.20 * (1.0 if h2h_avg_goals > 2.5 else h2h_avg_goals / 2.5)
    )
    over25_prob = max(0.25, min(0.80, over25_prob))
    over25_confidence = abs(over25_prob - 0.5) * 200  # 0-100 qué tan seguro
    over25_confidence = max(52, min(85, 50 + over25_confidence))

    over_under = {
        "line": 2.5,
        "recommendation": "OVER 2.5" if over25_prob > 0.52 else "UNDER 2.5",
        "probability": round(over25_prob * 100, 1) if over25_prob > 0.52 else round((1 - over25_prob) * 100, 1),
        "confidence": round(over25_confidence, 1),
        "avg_goals_combined": round(combined_avg_goals, 2),
        "h2h_avg_goals": round(h2h_avg_goals, 2),
        "detail": f"Prom: {combined_avg_goals:.1f} goles/partido | Over25 rate: {home_over25*100:.0f}%-{away_over25*100:.0f}%",
    }

    # ============================================================
    # MERCADO 3: Ambos Anotan (BTTS)
    # ============================================================
    home_btts = home_form["btts_rate"]
    away_btts = away_form["btts_rate"]
    home_fts = 1 - home_form["failed_to_score_rate"]  # Prob de anotar
    away_fts = 1 - away_form["failed_to_score_rate"]
    home_concede = 1 - home_form["clean_sheet_rate"]   # Prob de recibir
    away_concede = 1 - away_form["clean_sheet_rate"]

    btts_prob = (
        0.25 * home_btts +
        0.25 * away_btts +
        0.25 * (home_fts * away_concede) +
        0.25 * (away_fts * home_concede)
    )
    btts_prob = max(0.25, min(0.80, btts_prob))
    btts_confidence = abs(btts_prob - 0.5) * 200
    btts_confidence = max(52, min(82, 50 + btts_confidence))

    btts = {
        "recommendation": "SÍ" if btts_prob > 0.52 else "NO",
        "probability": round(btts_prob * 100, 1) if btts_prob > 0.52 else round((1 - btts_prob) * 100, 1),
        "confidence": round(btts_confidence, 1),
        "detail": f"BTTS rate: {home_btts*100:.0f}%-{away_btts*100:.0f}% | Anotan: {home_fts*100:.0f}%-{away_fts*100:.0f}%",
    }

    # ============================================================
    # MERCADO 4: Córners estimados
    # ============================================================
    corners = _estimate_corners(home_form, away_form, league_avg)

    corners_market = {
        "estimated_total": corners["estimated"],
        "line": corners["line"],
        "recommendation": f"OVER {corners['line']}" if corners["over_probability"] > 0.52 else f"UNDER {corners['line']}",
        "confidence": round(abs(corners["over_probability"] - 0.5) * 200 + 50, 1),
        "home_est": corners["home_corners_est"],
        "away_est": corners["away_corners_est"],
        "detail": f"Est: {corners['estimated']} total ({corners['home_corners_est']}-{corners['away_corners_est']})",
    }

    # ============================================================
    # MERCADO 5: Resultado exacto más probable
    # ============================================================
    exact = _predict_exact_score(home_form, away_form)

    exact_score = {
        "home_xg": exact["home_xg"],
        "away_xg": exact["away_xg"],
        "top_scores": exact["top_scores"],  # Lista de (score_str, prob_pct)
    }

    # ============================================================
    # Retorno completo
    # ============================================================
    return {
        "prediction": winner_prediction,
        "markets": {
            "over_under": over_under,
            "btts": btts,
            "corners": corners_market,
            "exact_score": exact_score,
        },
    }
