"""
predictor/esports_con_ia.py

Predictor de Esports mejorado con análisis de IA (Groq).
Reemplaza y EXTIENDE a predictor/lol.py

Deportes soportados:
  - League of Legends  (PandaScore API)
  - CS2 / Counter-Strike (PandaScore API — gratis igual)
  - Valorant           (PandaScore API — gratis igual)
  - Dota 2             (PandaScore API — gratis igual)

PandaScore cubre todos con la misma key gratuita.
Solo cambia el endpoint: /lol/ → /csgo/ → /valorant/ → /dota2/
"""
import logging
from api import pandascore
from api.groq_analyzer import analyze_match
from predictor.engine import calculate_prediction, Prediction

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ENDPOINTS POR DEPORTE
# ──────────────────────────────────────────────────────────────

SPORT_ENDPOINTS = {
    "lol":      "/lol",
    "cs2":      "/csgo",
    "valorant": "/valorant",
    "dota2":    "/dota2",
    "rl":       "/rl",      # Rocket League
}

SPORT_LABELS = {
    "lol":      "League of Legends",
    "cs2":      "Counter-Strike 2",
    "valorant": "Valorant",
    "dota2":    "Dota 2",
    "rl":       "Rocket League",
}


# ──────────────────────────────────────────────────────────────
#  HELPERS DE DATOS
# ──────────────────────────────────────────────────────────────

def _get_upcoming_matches(sport: str = "lol", per_page: int = 10) -> list:
    """
    Obtiene próximos partidos del esport indicado.
    Todos usan PandaScore con el mismo token gratuito.
    """
    if not pandascore._is_configured():
        return []

    endpoint_base = SPORT_ENDPOINTS.get(sport, "/lol")
    matches = pandascore._get(f"{endpoint_base}/matches/upcoming", {
        "sort": "begin_at",
        "per_page": per_page,
        "filter[status]": "not_started",
    })

    result = []
    for match in (matches or []):
        opponents = match.get("opponents") or []
        if len(opponents) < 2:
            continue
        t1 = opponents[0].get("opponent", {})
        t2 = opponents[1].get("opponent", {})
        league     = match.get("league", {})
        tournament = match.get("tournament", {})

        result.append({
            "match_id":       match.get("id"),
            "team1_name":     t1.get("name", "TBD"),
            "team1_id":       t1.get("id"),
            "team1_acronym":  t1.get("acronym", ""),
            "team2_name":     t2.get("name", "TBD"),
            "team2_id":       t2.get("id"),
            "team2_acronym":  t2.get("acronym", ""),
            "league_name":    league.get("name", "Unknown"),
            "tournament":     tournament.get("name", ""),
            "begin_at":       match.get("begin_at", ""),
            "best_of":        match.get("number_of_games", 1),
            "sport":          sport,
        })
    return result


def _get_past_matches(sport: str = "lol", per_page: int = 50) -> list:
    """Resultados recientes del esport indicado."""
    endpoint_base = SPORT_ENDPOINTS.get(sport, "/lol")
    return pandascore._get(f"{endpoint_base}/matches/past", {
        "sort": "-begin_at",
        "per_page": per_page,
    }) or []


def _calculate_team_stats(team_name: str, past_matches: list) -> dict:
    """Calcula WR, racha y H2H de un equipo."""
    wins = losses = 0
    recent_results = []

    for match in past_matches:
        opponents = match.get("opponents") or []
        if len(opponents) < 2:
            continue
        names = [(o.get("opponent") or {}).get("name", "").lower() for o in opponents]
        t = team_name.lower()
        if not any(t in n or n in t for n in names):
            continue

        winner = (match.get("winner") or {}).get("name", "").lower()
        won    = t in winner or winner in t

        if won:
            wins += 1; recent_results.append("W")
        else:
            losses += 1; recent_results.append("L")

        if len(recent_results) >= 10:
            break

    total   = wins + losses
    win_pct = round(wins / total * 100, 1) if total else 50.0
    streak  = ""
    if recent_results:
        last  = recent_results[0]
        count = 1
        for r in recent_results[1:]:
            if r == last: count += 1
            else: break
        streak = f"{count} {'victorias' if last=='W' else 'derrotas'} seguidas"

    return {
        "wins": wins, "losses": losses, "total": total,
        "win_pct": win_pct,
        "form_str": "".join(recent_results[:5]),
        "streak": streak,
        "summary": (
            f"WR: {win_pct}% ({wins}W-{losses}L) | "
            f"Forma: {''.join(recent_results[:5])} | {streak}"
        )
    }


def _get_h2h(team1: str, team2: str, past_matches: list) -> dict:
    """Enfrentamientos directos entre dos equipos."""
    t1_wins = t2_wins = 0
    results = []

    for match in past_matches:
        opponents = match.get("opponents") or []
        if len(opponents) < 2:
            continue
        names = [(o.get("opponent") or {}).get("name", "") for o in opponents]
        n_low = [n.lower() for n in names]
        t1 = team1.lower(); t2 = team2.lower()

        if not (any(t1 in n or n in t1 for n in n_low) and
                any(t2 in n or n in t2 for n in n_low)):
            continue

        winner = (match.get("winner") or {}).get("name", "").lower()
        if t1 in winner or winner in t1:
            t1_wins += 1
            results.append(f"{names[0]} ganó")
        elif t2 in winner or winner in t2:
            t2_wins += 1
            results.append(f"{names[1]} ganó")

        if len(results) >= 4:
            break

    total = t1_wins + t2_wins
    return {
        "t1_wins": t1_wins, "t2_wins": t2_wins, "total": total,
        "summary": (
            f"{team1} {t1_wins} - {t2_wins} {team2} "
            f"(últimos {total} enfrentamientos: {', '.join(results)})"
            if total else "Sin H2H reciente en base de datos"
        )
    }


def _get_tournament_position(team_name: str, past_matches: list,
                              tournament: str) -> str:
    """Posición aproximada en torneo basada en winrate reciente."""
    stats = _calculate_team_stats(team_name, past_matches)
    return (
        f"{stats['win_pct']}% WR en {tournament} | "
        f"{stats['wins']}W-{stats['losses']}L récord reciente"
    )


# ──────────────────────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────────────────────

def predict_match(
    team1_name: str,
    team2_name: str,
    league_name: str   = "LoL",
    tournament_name: str = "",
    event_id: str      = None,
    sport: str         = "lol",
    best_of: int       = 1,
) -> Prediction:
    """
    Genera una predicción para un partido de esports con análisis IA.

    Soporta: LoL, CS2, Valorant, Dota 2, Rocket League

    Args:
        team1_name:      Equipo 1 (blue side en LoL / CT en CS2 / etc)
        team2_name:      Equipo 2
        league_name:     Liga/torneo
        tournament_name: Nombre del torneo específico
        event_id:        ID PandaScore
        sport:           'lol' | 'cs2' | 'valorant' | 'dota2' | 'rl'
        best_of:         Formato (Bo1, Bo3, Bo5)

    Returns:
        Prediction object (mismo formato que antes)
    """
    sport_label = SPORT_LABELS.get(sport, "Esports")
    logger.info(f"[{sport_label}-IA] {team1_name} vs {team2_name} ({league_name})")

    past = _get_past_matches(sport, per_page=100)

    t1_stats = _calculate_team_stats(team1_name, past)
    t2_stats = _calculate_team_stats(team2_name, past)
    h2h      = _get_h2h(team1_name, team2_name, past)
    t1_pos   = _get_tournament_position(team1_name, past, league_name)
    t2_pos   = _get_tournament_position(team2_name, past, league_name)

    # Factores específicos por deporte
    sport_extra = ""
    if sport == "lol":
        sport_extra = (
            f"Blue side ({team1_name}) tiene ~52% de WR histórico global en LoL. "
            f"Formato: Best of {best_of}."
        )
    elif sport == "cs2":
        sport_extra = (
            f"En CS2 el equipo que eligió mapa tiene ventaja. "
            f"Formato: Best of {best_of}. "
            f"Considera mapa favorito de cada equipo."
        )
    elif sport == "valorant":
        sport_extra = (
            f"En Valorant la composición de agentes importa más que el mapa. "
            f"Formato: Best of {best_of}."
        )
    elif sport == "dota2":
        sport_extra = (
            f"En Dota 2 el draft y el meta actual son factores clave. "
            f"Formato: Best of {best_of}."
        )

    context = {
        "home_form":         t1_stats["summary"],
        "away_form":         t2_stats["summary"],
        "home_position":     t1_pos,
        "away_position":     t2_pos,
        "home_goals_avg":    f"{t1_stats['win_pct']}% WR",
        "away_goals_avg":    f"{t2_stats['win_pct']}% WR",
        "home_conceded_avg": f"{100 - t1_stats['win_pct']}% LR",
        "away_conceded_avg": f"{100 - t2_stats['win_pct']}% LR",
        "h2h":               h2h["summary"],
        "injuries":          "Sin información de roster disponible",
        "venue":             f"{league_name} — {tournament_name or 'Torneo'}",
        "sport_notes":       sport_extra,
    }

    # ── Groq IA ────────────────────────────────────────────────
    ai = analyze_match(team1_name, team2_name, league_name, "lol", context)

    # ── Factor scores ──────────────────────────────────────────
    conf = ai["confidence"] / 100.0
    predicted_is_t1 = (
        ai["predicted_winner"].lower() in team1_name.lower() or
        team1_name.lower() in ai["predicted_winner"].lower()
    )
    base = 0.5 + (conf - 0.5) if predicted_is_t1 else 0.5 - (conf - 0.5)
    base = max(0.1, min(0.9, base))

    # WR score real
    if t1_stats["total"] > 0 and t2_stats["total"] > 0:
        total_wr = t1_stats["win_pct"] + t2_stats["win_pct"]
        wr_score = t1_stats["win_pct"] / max(total_wr, 0.01)
    else:
        wr_score = base

    h2h_score = h2h["t1_wins"] / h2h["total"] if h2h["total"] > 0 else 0.5
    side_score = 0.52 if sport == "lol" else 0.5  # Blue side advantage en LoL

    factor_scores = {
        "win_rate":            wr_score,
        "tournament_position": base,
        "head_to_head":        h2h_score,
        "side_preference":     side_score,
    }
    factors_desc = {
        f"ia_{i+1}": f"🤖 {f}"
        for i, f in enumerate(ai.get("key_factors", [])[:3])
    }

    prediction = calculate_prediction(
        sport="lol",
        league=league_name,
        home_team=team1_name,
        away_team=team2_name,
        factor_scores=factor_scores,
        factors_description=factors_desc,
        event_id=str(event_id) if event_id else None,
    )
    prediction.confidence = ai["confidence"]
    prediction.factors    = factors_desc

    # Adjuntar análisis IA al objeto para el formatter
    prediction.ai_analysis = ai["analysis"]
    prediction.ai_pick     = ai["pick"]
    prediction.ai_odds     = ai["pick_odds"]

    return prediction


# ──────────────────────────────────────────────────────────────
#  WRAPPER: obtener todos los partidos del día
# ──────────────────────────────────────────────────────────────

def get_all_upcoming(sport: str = "lol", limit: int = 5) -> list:
    """
    Obtiene y predice todos los partidos próximos de un esport.

    Returns:
        Lista de (Prediction, league_name, sport_label) tuples
    """
    matches  = _get_upcoming_matches(sport, per_page=limit + 3)
    results  = []

    for m in matches[:limit]:
        try:
            pred = predict_match(
                team1_name     = m["team1_name"],
                team2_name     = m["team2_name"],
                league_name    = m["league_name"],
                tournament_name= m["tournament"],
                event_id       = str(m["match_id"]),
                sport          = sport,
                best_of        = m["best_of"],
            )
            results.append((pred, m["league_name"], SPORT_LABELS.get(sport, sport)))
        except Exception as e:
            logger.error(
                f"Error prediciendo {m['team1_name']} vs {m['team2_name']}: {e}"
            )

    return results