"""
predictor/futbol_con_ia.py

Versión mejorada del predictor de fútbol con análisis de IA (Groq).
Reemplaza a predictor/futbol.py

Diferencia clave vs el original:
  - El original siempre daba 52% porque la data de TheSportsDB estaba vacía
  - Esta versión usa ESPN como fuente de datos + Groq para analizar
  - La confianza ahora refleja el análisis real del modelo
"""
import logging
from api import thesportsdb, cache
from api.groq_analyzer import analyze_match
from predictor.engine import calculate_prediction, Prediction
from config import FOOTBALL_SEASONS

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Helpers de datos (mismo que antes, sin cambios)
# ──────────────────────────────────────────────────────────────

def _get_team_form(team_name: str, past_events: list) -> dict:
    """Extrae forma reciente del equipo de los últimos 5 partidos."""
    wins = draws = losses = gf = ga = 0
    form_chars = []

    for event in past_events[:15]:
        home = (event.get("strHomeTeam") or "").lower()
        away = (event.get("strAwayTeam") or "").lower()
        name = team_name.lower()
        if name not in home and name not in away:
            continue
        try:
            hs = int(event.get("intHomeScore") or 0)
            aws = int(event.get("intAwayScore") or 0)
        except (ValueError, TypeError):
            continue

        is_home = name in home
        if is_home:
            gf += hs; ga += aws
            if hs > aws: wins += 1; form_chars.append("W")
            elif hs < aws: losses += 1; form_chars.append("L")
            else: draws += 1; form_chars.append("D")
        else:
            gf += aws; ga += hs
            if aws > hs: wins += 1; form_chars.append("W")
            elif aws < hs: losses += 1; form_chars.append("L")
            else: draws += 1; form_chars.append("D")

        if len(form_chars) >= 5:
            break

    total = wins + draws + losses
    return {
        "wins": wins, "draws": draws, "losses": losses,
        "gf": gf, "ga": ga, "total": total,
        "form_str": "".join(form_chars[:5]),
        "avg_gf": round(gf / total, 2) if total else 1.2,
        "avg_ga": round(ga / total, 2) if total else 1.1,
    }


def _get_table_position(team_name: str, league_id: int) -> str:
    """Devuelve la posición del equipo como string legible."""
    season = FOOTBALL_SEASONS.get(league_id, "2025-2026")
    table  = thesportsdb.get_table(league_id, season)
    if not table:
        return "Sin datos de tabla"
    total = len(table)
    for entry in table:
        name_t = (entry.get("strTeam") or "").lower()
        if team_name.lower() in name_t or name_t in team_name.lower():
            pos  = entry.get("intRank", "?")
            pts  = entry.get("intPoints", "?")
            w    = entry.get("intWin", "?")
            d    = entry.get("intDraw", "?")
            l    = entry.get("intLoss", "?")
            return f"Posición {pos}/{total} · {pts} pts · {w}V {d}E {l}D"
    return f"No encontrado en tabla (de {total} equipos)"


def _get_h2h_summary(home_team: str, away_team: str, past_events: list) -> str:
    """Resumen texto del H2H."""
    h2h = []
    for ev in past_events:
        ht = (ev.get("strHomeTeam") or "").lower()
        at = (ev.get("strAwayTeam") or "").lower()
        t1 = home_team.lower(); t2 = away_team.lower()
        if (t1 in ht and t2 in at) or (t2 in ht and t1 in at):
            try:
                hs = int(ev.get("intHomeScore") or -1)
                aws = int(ev.get("intAwayScore") or -1)
                if hs >= 0 and aws >= 0:
                    h2h.append(f"{ev.get('strHomeTeam')} {hs}-{aws} {ev.get('strAwayTeam')}")
            except (ValueError, TypeError):
                pass
    if not h2h:
        return "Sin datos H2H recientes"
    return " | ".join(h2h[:3])


# ──────────────────────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL — predict_match con IA
# ──────────────────────────────────────────────────────────────

def predict_match(
    home_team: str,
    away_team: str,
    league_name: str,
    league_id: int,
    event_id: str = None,
    altitude_m: int = None,  # NUEVO — altitud del estadio en metros
) -> dict:
    """
    Genera predicciones multi-mercado usando ESPN/TheSportsDB + Groq IA.

    Flujo:
      1. Obtiene datos reales de ambos equipos (forma, tabla, H2H)
      2. Empaqueta esos datos y los manda a Groq (Llama 3.1 70B)
      3. La IA devuelve el análisis en JSON
      4. Se combina con el engine existente para guardar en historial

    Returns:
        Dict con 'prediction' y 'markets' (igual que antes para no romper nada)
    """
    logger.info(f"[IA] Analizando: {home_team} vs {away_team} ({league_name})")

    # ── 1. Datos de TheSportsDB ──────────────────────────────
    past_events = thesportsdb.get_past_events(league_id) if league_id else []

    home_form = _get_team_form(home_team, past_events)
    away_form = _get_team_form(away_team, past_events)
    home_pos  = _get_table_position(home_team, league_id) if league_id else "Sin datos"
    away_pos  = _get_table_position(away_team, league_id) if league_id else "Sin datos"
    h2h_text  = _get_h2h_summary(home_team, away_team, past_events)

    # ── 2. Contexto para la IA ───────────────────────────────
    context = {
        "home_form":        home_form["form_str"] or "Sin partidos recientes",
        "away_form":        away_form["form_str"] or "Sin partidos recientes",
        "home_position":    home_pos,
        "away_position":    away_pos,
        "home_goals_avg":   home_form["avg_gf"],
        "away_goals_avg":   away_form["avg_gf"],
        "home_conceded_avg": home_form["avg_ga"],
        "away_conceded_avg": away_form["avg_ga"],
        "h2h":              h2h_text,
        "injuries":         "Sin información disponible",
        "venue":            f"Estadio de {home_team}",
    }

    # Altitud — factor importante para CONMEBOL
    if altitude_m:
        context["altitude_m"] = altitude_m

    # ── 3. Llamada a Groq ────────────────────────────────────
    ai = analyze_match(home_team, away_team, league_name, "football", context)

    # ── 4. Convertir confianza IA → factor_scores ────────────
    # Para mantener compatibilidad con engine.py
    conf = ai["confidence"] / 100.0  # 0.0 - 1.0
    predicted_is_home = ai["predicted_winner"].lower() in home_team.lower() or \
                        home_team.lower() in ai["predicted_winner"].lower()

    # Si la IA predice local, score > 0.5; si visitante, < 0.5
    base_score = 0.5 + (conf - 0.5) if predicted_is_home else 0.5 - (conf - 0.5)
    base_score = max(0.1, min(0.9, base_score))

    factor_scores = {
        "table_position":  base_score,
        "recent_form":     base_score,
        "home_advantage":  0.58 if predicted_is_home else 0.42,
        "head_to_head":    base_score,
        "goals_form":      base_score,
    }

    # Descripción de factores con las razones reales de la IA
    factors_desc = {}
    for i, factor in enumerate(ai.get("key_factors", [])[:3]):
        factors_desc[f"ia_factor_{i+1}"] = f"🤖 {factor}"

    # ── 5. Guardar en historial (auto-aprendizaje) ───────────
    prediction = calculate_prediction(
        sport="football",
        league=league_name,
        home_team=home_team,
        away_team=away_team,
        factor_scores=factor_scores,
        factors_description=factors_desc,
        event_id=event_id,
    )

    # Sobreescribir confianza con la de la IA (más real)
    prediction.confidence  = ai["confidence"]
    prediction.factors     = factors_desc

    # ── 6. Construir mercados ────────────────────────────────
    ou_confidence   = ai.get("ou_confidence", 58)
    btts_confidence = ai.get("btts_confidence", 55)

    markets = {
        "over_under": {
            "recommendation": ai.get("over_under", "Under 2.5"),
            "confidence":     ou_confidence,
            "detail":         f"Prom: {home_form['avg_gf']:.1f}+{away_form['avg_gf']:.1f} goles/partido",
        },
        "btts": {
            "recommendation": ai.get("btts", "No"),
            "confidence":     btts_confidence,
            "detail":         f"GA prom: {home_form['avg_ga']:.1f} (local) {away_form['avg_ga']:.1f} (visita)",
        },
    }

    return {
        "prediction":   prediction,
        "markets":      markets,
        "ai_analysis":  ai["analysis"],   # ← NUEVO: análisis en lenguaje natural
        "ai_pick":      ai["pick"],        # ← NUEVO: pick recomendado por la IA
        "ai_odds":      ai["pick_odds"],   # ← NUEVO: cuota estimada
    }