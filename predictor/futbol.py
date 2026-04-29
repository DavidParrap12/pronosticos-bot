"""
Predictor de fútbol — ESPN datos reales + Groq IA.
Combina datos estadísticos reales de ESPN con análisis de IA de Groq.
"""
import logging
from api import espn
from api.groq_analyzer import analyze_match
from predictor.engine import calculate_prediction, Prediction

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Altitudes CONMEBOL (factor real)
# ──────────────────────────────────────────────────────────────
ALTITUDES = {
    "Deportes Tolima": 1285, "Millonarios": 2640, "Santa Fe": 2640,
    "América de Cali": 995, "Atlético Nacional": 1495,
    "Independiente Medellín": 1495, "Junior": 18,
    "Bolívar": 3637, "The Strongest": 3637,
    "Liga de Quito": 2850, "Independiente del Valle": 2400,
    "Barcelona SC": 4, "Universitario": 154, "Sporting Cristal": 154,
    "Cienciano": 3400,
}


def predict_match(
    home_team: str,
    away_team: str,
    league_name: str,
    league_id: int = 0,
    event_id: str = None,
    altitude_m: int = None,
) -> dict:
    """
    Genera predicciones multi-mercado: ESPN (datos) + Groq (IA).
    
    Flujo:
      1. Obtiene datos REALES de ESPN (récord, forma, goles, H2H)
      2. Empaqueta todo y lo manda a Groq (Llama 3.3 70B)
      3. La IA analiza y devuelve predicción con confianza real
      4. Se guarda en historial para auto-aprendizaje
    """
    logger.info(f"[IA] Analizando: {home_team} vs {away_team} ({league_name})")

    # ── 1. Datos REALES de ESPN ──────────────────────────────
    home_record = espn.get_team_record(home_team, league_name)
    away_record = espn.get_team_record(away_team, league_name)
    home_form = espn.get_team_form(home_team, league_name, last_n=5)
    away_form = espn.get_team_form(away_team, league_name, last_n=5)
    h2h = espn.get_head_to_head(home_team, away_team, league_name)

    has_data = bool(home_record or home_form)
    
    # Preparar resúmenes legibles para la IA
    home_rec_str = home_record.get("record_summary", "Sin datos") if home_record else "Sin datos"
    away_rec_str = away_record.get("record_summary", "Sin datos") if away_record else "Sin datos"
    home_form_str = home_form.get("form_string", "Sin datos") if home_form else "Sin datos"
    away_form_str = away_form.get("form_string", "Sin datos") if away_form else "Sin datos"
    
    # Goles promedio
    home_gf = home_form.get("avg_goals_scored", 1.2) if home_form else 1.2
    home_ga = home_form.get("avg_goals_conceded", 1.0) if home_form else 1.0
    away_gf = away_form.get("avg_goals_scored", 1.2) if away_form else 1.2
    away_ga = away_form.get("avg_goals_conceded", 1.0) if away_form else 1.0
    home_wr = home_form.get("home_win_rate", 0.5) if home_form else 0.5
    
    # H2H texto
    h2h_total = h2h.get("total", 0)
    if h2h_total > 0:
        h2h_text = f"{h2h['team1_wins']} victorias {home_team}, {h2h['team2_wins']} victorias {away_team}, {h2h['draws']} empates ({h2h_total} partidos)"
    else:
        h2h_text = "Sin enfrentamientos recientes"

    if has_data:
        logger.info(f"  ✅ ESPN: {home_team} ({home_rec_str}) vs {away_team} ({away_rec_str})")

    # ── 2. Contexto para Groq ────────────────────────────────
    # Autobuscar altitud
    if not altitude_m:
        altitude_m = ALTITUDES.get(home_team)

    context = {
        "home_form": home_form_str or "Sin partidos recientes",
        "away_form": away_form_str or "Sin partidos recientes",
        "home_position": f"Récord: {home_rec_str}",
        "away_position": f"Récord: {away_rec_str}",
        "home_goals_avg": home_gf,
        "away_goals_avg": away_gf,
        "home_conceded_avg": home_ga,
        "away_conceded_avg": away_ga,
        "h2h": h2h_text,
        "injuries": "Sin información disponible",
        "venue": f"Estadio de {home_team}",
    }
    if altitude_m:
        context["altitude_m"] = altitude_m

    # ── 3. Llamada a Groq ────────────────────────────────────
    ai = analyze_match(home_team, away_team, league_name, "football", context)

    # ── 4. Convertir confianza IA → factor_scores ────────────
    conf = ai["confidence"] / 100.0
    predicted_is_home = ai["predicted_winner"].lower() in home_team.lower() or \
                        home_team.lower() in ai["predicted_winner"].lower()

    base_score = 0.5 + (conf - 0.5) if predicted_is_home else 0.5 - (conf - 0.5)
    base_score = max(0.1, min(0.9, base_score))

    factor_scores = {
        "table_position": base_score,
        "recent_form": base_score,
        "home_advantage": 0.58 if predicted_is_home else 0.42,
        "head_to_head": base_score,
        "goals_form": base_score,
    }

    # Factores con razones reales de la IA
    factors_desc = {}
    for i, factor in enumerate(ai.get("key_factors", [])[:3]):
        factors_desc[f"ia_factor_{i+1}"] = f"🤖 {factor}"
    
    # Agregar datos ESPN visibles
    if has_data:
        factors_desc["record"] = f"📋 {home_team} ({home_rec_str}) vs {away_team} ({away_rec_str})"
    if home_form_str and away_form_str:
        factors_desc["form"] = f"📈 Forma: {home_team} ({home_form_str}) vs {away_team} ({away_form_str})"

    # ── 5. Guardar en historial ───────────────────────────────
    prediction = calculate_prediction(
        sport="football",
        league=league_name,
        home_team=home_team,
        away_team=away_team,
        factor_scores=factor_scores,
        factors_description=factors_desc,
        event_id=event_id,
    )

    # Sobreescribir con confianza real de la IA
    prediction.confidence = ai["confidence"]
    prediction.factors = factors_desc

    # ── 6. Mercados ──────────────────────────────────────────
    ou_confidence = ai.get("ou_confidence", 58)
    btts_confidence = ai.get("btts_confidence", 55)

    avg_total = home_gf + away_gf
    markets = {
        "over_under": {
            "recommendation": ai.get("over_under", "Under 2.5"),
            "confidence": ou_confidence,
            "detail": f"Prom goles: {home_gf:.1f}+{away_gf:.1f} = {avg_total:.1f}/partido",
        },
        "btts": {
            "recommendation": ai.get("btts", "No"),
            "confidence": btts_confidence,
            "detail": f"Reciben: {home_ga:.1f} (local) {away_ga:.1f} (visita)",
        },
    }

    return {
        "prediction": prediction,
        "markets": markets,
        "ai_analysis": ai["analysis"],
        "ai_pick": ai["pick"],
        "ai_odds": ai["pick_odds"],
    }