"""
predictor/nba_con_ia.py

Predictor NBA mejorado con análisis de IA (Groq).
Reemplaza a predictor/nba.py

Mercados:
  - Ganador directo
  - Over/Under puntos totales (línea dinámica)
  - Handicap / Spread
  - Primer cuarto
  - Puntos por equipo
"""
import logging
from api import thesportsdb
from api.groq_analyzer import analyze_match
from predictor.engine import calculate_prediction
from config import NBA_SEASON

logger = logging.getLogger(__name__)
NBA_LEAGUE_ID = 4387


# ──────────────────────────────────────────────────────────────
#  HELPERS DE DATOS
# ──────────────────────────────────────────────────────────────

def _get_team_record(team_name: str) -> dict:
    table = thesportsdb.get_table(NBA_LEAGUE_ID, NBA_SEASON)
    if not table:
        return {"wins": 0, "losses": 0, "win_pct": 0.5, "position": 0,
                "total_teams": 0, "summary": "Sin datos de tabla"}

    total = len(table)
    for entry in table:
        name = (entry.get("strTeam") or "").lower()
        if team_name.lower() in name or name in team_name.lower():
            try:
                w   = int(entry.get("intWin")  or 0)
                l   = int(entry.get("intLoss") or 0)
                pos = int(entry.get("intRank") or total)
                pts = entry.get("intPoints", "?")
            except (ValueError, TypeError):
                w = l = 0; pos = total; pts = "?"
            pct = w / (w + l) if (w + l) > 0 else 0.5
            return {
                "wins": w, "losses": l, "win_pct": pct,
                "position": pos, "total_teams": total,
                "summary": f"Posición {pos}/{total} · {w}W-{l}L · {round(pct*100,1)}% WR"
            }
    return {"wins": 0, "losses": 0, "win_pct": 0.5, "position": 0,
            "total_teams": total, "summary": "No encontrado en tabla"}


def _get_recent_form(team_name: str, past_events: list) -> dict:
    wins = losses = pf = pa = 0
    form_chars = []
    totals = []
    margins = []

    for event in past_events:
        home = (event.get("strHomeTeam") or "").lower()
        away = (event.get("strAwayTeam") or "").lower()
        name = team_name.lower()
        if name not in home and name not in away:
            continue
        try:
            hs  = int(event.get("intHomeScore") or 0)
            aws = int(event.get("intAwayScore") or 0)
        except (ValueError, TypeError):
            continue

        total = hs + aws
        totals.append(total)
        is_home = name in home

        if is_home:
            pf += hs; pa += aws; margins.append(hs - aws)
            if hs > aws: wins += 1; form_chars.append("W")
            else:        losses += 1; form_chars.append("L")
        else:
            pf += aws; pa += hs; margins.append(aws - hs)
            if aws > hs: wins += 1; form_chars.append("W")
            else:        losses += 1; form_chars.append("L")

        if len(form_chars) >= 10:
            break

    total_g = wins + losses
    avg_tot = sum(totals) / len(totals) if totals else 215.0
    avg_pf  = pf / total_g if total_g else 110.0
    avg_pa  = pa / total_g if total_g else 110.0
    avg_mar = sum(margins) / len(margins) if margins else 0.0

    return {
        "wins": wins, "losses": losses, "total": total_g,
        "form_str": "".join(form_chars[:10]),
        "avg_pf": round(avg_pf, 1),
        "avg_pa": round(avg_pa, 1),
        "avg_total": round(avg_tot, 1),
        "avg_margin": round(avg_mar, 1),
        "summary": (
            f"Forma: {''.join(form_chars[:5])} | "
            f"Prom pts: {round(avg_pf,1)} (recibe {round(avg_pa,1)}) | "
            f"Total prom: {round(avg_tot,1)} pts/partido"
        )
    }


def _get_h2h_summary(home: str, away: str, past_events: list) -> str:
    results = []
    for ev in past_events:
        ht = (ev.get("strHomeTeam") or "").lower()
        at = (ev.get("strAwayTeam") or "").lower()
        t1 = home.lower(); t2 = away.lower()
        if (t1 in ht and t2 in at) or (t2 in ht and t1 in at):
            try:
                hs  = int(ev.get("intHomeScore") or -1)
                aws = int(ev.get("intAwayScore") or -1)
                if hs >= 0 and aws >= 0:
                    results.append(
                        f"{ev.get('strHomeTeam')} {hs}-{aws} {ev.get('strAwayTeam')}"
                        f" (total {hs+aws} pts)"
                    )
            except (ValueError, TypeError):
                pass
    return " | ".join(results[:3]) if results else "Sin H2H reciente"


# ──────────────────────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────────────────────

def predict_match(home_team: str, away_team: str, event_id: str = None) -> dict:
    """
    Genera predicciones NBA multi-mercado con análisis de IA.

    Flujo:
      1. Obtiene record de temporada, forma reciente y H2H
      2. Manda los datos a Groq (Llama 3.3 70B)
      3. La IA devuelve: ganador, over/under, spread, análisis
      4. Se combina con el engine para guardar en historial
    """
    logger.info(f"[NBA-IA] {home_team} vs {away_team}")

    past_events = thesportsdb.get_past_events(NBA_LEAGUE_ID)

    home_record = _get_team_record(home_team)
    away_record = _get_team_record(away_team)
    home_form   = _get_recent_form(home_team, past_events)
    away_form   = _get_recent_form(away_team, past_events)
    h2h_text    = _get_h2h_summary(home_team, away_team, past_events)

    # Línea O/U proyectada para incluir en el contexto
    projected_total = (home_form["avg_total"] + away_form["avg_total"]) / 2
    home_net = home_form["avg_pf"] - home_form["avg_pa"]
    away_net = away_form["avg_pf"] - away_form["avg_pa"]
    spread_proj = round((home_net - away_net) / 2 + 3.5, 1)  # +3.5 home court

    context = {
        "home_form":         home_form["summary"],
        "away_form":         away_form["summary"],
        "home_position":     home_record["summary"],
        "away_position":     away_record["summary"],
        "home_goals_avg":    home_form["avg_pf"],   # pts/partido
        "away_goals_avg":    away_form["avg_pf"],
        "home_conceded_avg": home_form["avg_pa"],
        "away_conceded_avg": away_form["avg_pa"],
        "h2h":               h2h_text,
        "injuries":          "Sin información",
        "venue":             f"Cancha de {home_team} (ventaja local +3.5 pts promedio NBA)",
        # Datos NBA adicionales
        "projected_total":   projected_total,
        "spread_projection": spread_proj,
        "home_net_rating":   home_net,
        "away_net_rating":   away_net,
    }

    # ── Groq IA ────────────────────────────────────────────────
    ai = analyze_match(home_team, away_team, "NBA", "nba", context)

    # ── Convertir a factor_scores ──────────────────────────────
    conf = ai["confidence"] / 100.0
    predicted_is_home = (
        ai["predicted_winner"].lower() in home_team.lower() or
        home_team.lower() in ai["predicted_winner"].lower()
    )
    base = 0.5 + (conf - 0.5) if predicted_is_home else 0.5 - (conf - 0.5)
    base = max(0.1, min(0.9, base))

    factor_scores = {
        "record":      base,
        "recent_form": base,
        "head_to_head": base,
        "points_avg":  base,
    }
    factors_desc = {
        f"ia_{i+1}": f"🤖 {f}"
        for i, f in enumerate(ai.get("key_factors", [])[:3])
    }

    prediction = calculate_prediction(
        sport="nba", league="NBA",
        home_team=home_team, away_team=away_team,
        factor_scores=factor_scores,
        factors_description=factors_desc,
        event_id=event_id,
    )
    prediction.confidence = ai["confidence"]
    prediction.factors    = factors_desc

    # ── Mercados ───────────────────────────────────────────────
    ou_line = round(projected_total * 2) / 2
    spread_val = round(abs(spread_proj) * 2) / 2
    spread_team = home_team if spread_proj > 0 else away_team

    markets = {
        "over_under": {
            "recommendation": ai.get("over_under_pts", f"Over {ou_line}"),
            "confidence":     ai.get("ou_confidence", 58),
            "projected_total": round(projected_total, 1),
            "detail": (
                f"Prom combinado: {round(projected_total,0):.0f} pts | "
                f"{home_team}: {home_form['avg_pf']} | {away_team}: {away_form['avg_pf']}"
            ),
        },
        "handicap": {
            "favorite":    spread_team,
            "spread":      -spread_val,
            "recommendation": ai.get("spread_pick", f"{spread_team} -{spread_val}"),
            "confidence":  max(52, min(78, 50 + abs(spread_proj) * 1.5)),
            "detail": (
                f"Net rating: {home_team} {home_net:+.1f} | "
                f"{away_team} {away_net:+.1f} | Home court +3.5"
            ),
        },
        "first_quarter": {
            "q1_line":     round(projected_total * 0.25 * 2) / 2,
            "recommendation": f"O/U {round(projected_total * 0.25 * 2) / 2} Q1",
            "confidence":  55,
            "detail":      "~25% del total de puntos en Q1 histórico NBA",
        },
        "team_points": {
            "home_team":  home_team,
            "home_line":  round(home_form["avg_pf"] * 2) / 2,
            "home_avg":   home_form["avg_pf"],
            "away_team":  away_team,
            "away_line":  round(away_form["avg_pf"] * 2) / 2,
            "away_avg":   away_form["avg_pf"],
        },
    }

    return {
        "prediction":  prediction,
        "markets":     markets,
        "ai_analysis": ai["analysis"],
        "ai_pick":     ai["pick"],
        "ai_odds":     ai["pick_odds"],
    }