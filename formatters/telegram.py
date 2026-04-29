"""
formatters/telegram.py — VERSIÓN CON IA

Formateador de mensajes para Telegram.
Ahora incluye el análisis de IA en todos los deportes.
"""
from datetime import datetime
from predictor.engine import get_accuracy_stats, get_current_weights


def _bar(confidence: float) -> str:
    filled = int(confidence / 10)
    return "█" * filled + "░" * (10 - filled)

def _emoji(confidence: float) -> str:
    if confidence >= 75: return "🔥"
    if confidence >= 65: return "✅"
    if confidence >= 58: return "🟡"
    return "⚪"

def _upset_emoji(risk: str) -> str:
    return {"Alto": "⚠️", "Medio": "🟡", "Bajo": "✅"}.get(risk, "🟡")


# ──────────────────────────────────────────────────────────────
#  FÚTBOL
# ──────────────────────────────────────────────────────────────

def format_football_match(match_data: dict) -> str:
    pred    = match_data["prediction"]
    markets = match_data["markets"]
    ai_txt  = match_data.get("ai_analysis", "")
    ai_pick = match_data.get("ai_pick", "")
    ai_odds = match_data.get("ai_odds", "")

    winner_arrow = "👈" if pred.predicted_winner == pred.home_team else "👉"
    lines = [
        f"  ⚽ *{pred.home_team}* vs *{pred.away_team}*",
        "",
        f"  🏆 *Ganador:* {pred.predicted_winner} {winner_arrow}",
        f"     {_emoji(pred.confidence)} {pred.confidence}% [{_bar(pred.confidence)}]",
    ]

    # Análisis IA (el gran cambio vs antes)
    if ai_txt:
        lines.append(f"  🤖 _{ai_txt}_")

    # Pick recomendado por la IA
    if ai_pick:
        lines.append(f"  💡 *Pick:* {ai_pick}  |  Cuota ~{ai_odds}")

    # Over/Under
    ou = markets.get("over_under", {})
    if ou:
        lines.append("")
        lines.append(f"  📊 *Goles:* {ou['recommendation']}")
        lines.append(f"     {_emoji(ou['confidence'])} {ou['confidence']}% | {ou.get('detail','')}")

    # BTTS
    btts = markets.get("btts", {})
    if btts:
        lines.append(f"  🎯 *Ambos Anotan:* {btts['recommendation']}")
        lines.append(f"     {_emoji(btts['confidence'])} {btts['confidence']}%")

    # Córners (si existe)
    corners = markets.get("corners", {})
    if corners:
        lines.append(f"  🚩 *Córners:* {corners['recommendation']}")
        lines.append(f"     {_emoji(corners['confidence'])} {corners['confidence']}% | {corners.get('detail','')}")

    # Marcador exacto (si existe)
    exact = markets.get("exact_score", {})
    if exact and exact.get("top_scores"):
        scores = " | ".join([f"{s[0]} ({s[1]}%)" for s in exact["top_scores"]])
        lines.append(f"  🎲 *Marcador probable:* {scores}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
#  NBA
# ──────────────────────────────────────────────────────────────

def format_nba_match(match_data: dict) -> str:
    pred    = match_data["prediction"]
    markets = match_data["markets"]
    ai_txt  = match_data.get("ai_analysis", "")
    ai_pick = match_data.get("ai_pick", "")
    ai_odds = match_data.get("ai_odds", "")

    winner_arrow = "👈" if pred.predicted_winner == pred.home_team else "👉"
    lines = [
        f"  🏀 *{pred.home_team}* vs *{pred.away_team}*",
        "",
        f"  🏆 *Ganador:* {pred.predicted_winner} {winner_arrow}",
        f"     {_emoji(pred.confidence)} {pred.confidence}% [{_bar(pred.confidence)}]",
    ]

    if ai_txt:
        lines.append(f"  🤖 _{ai_txt}_")
    if ai_pick:
        lines.append(f"  💡 *Pick:* {ai_pick}  |  Cuota ~{ai_odds}")

    # Over/Under puntos
    ou = markets.get("over_under", {})
    if ou:
        lines.append("")
        lines.append(f"  📊 *Puntos:* {ou['recommendation']}")
        lines.append(
            f"     {_emoji(ou['confidence'])} {ou['confidence']}% | "
            f"Total proy: {ou.get('projected_total','?')} pts"
        )
        lines.append(f"     {ou.get('detail','')}")

    # Spread
    hc = markets.get("handicap", {})
    if hc:
        lines.append(f"  📐 *Spread:* {hc['recommendation']}")
        lines.append(
            f"     {_emoji(hc['confidence'])} {hc['confidence']}% | "
            f"{hc.get('detail','')}"
        )

    # Primer cuarto
    q1 = markets.get("first_quarter", {})
    if q1:
        lines.append(f"  ⏱️ *1er Cuarto:* {q1['recommendation']}")
        lines.append(f"     {_emoji(q1['confidence'])} {q1['confidence']}%")

    # Líneas por equipo
    tp = markets.get("team_points", {})
    if tp:
        lines.append(
            f"  📈 *Líneas:* {tp['home_team']} O/U {tp['home_line']} "
            f"(prom {tp['home_avg']}) | "
            f"{tp['away_team']} O/U {tp['away_line']} (prom {tp['away_avg']})"
        )

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
#  ESPORTS (LoL, CS2, Valorant, Dota 2)
# ──────────────────────────────────────────────────────────────

def format_esport_match(prediction, sport_label: str = "🎮 Esports") -> str:
    """
    Formatea un partido de esports con análisis IA.
    prediction puede ser un Prediction object o un dict.
    """
    # Compatibilidad con ambos formatos
    if hasattr(prediction, "predicted_winner"):
        pred       = prediction
        ai_txt     = getattr(pred, "ai_analysis", "")
        ai_pick    = getattr(pred, "ai_pick", "")
        ai_odds    = getattr(pred, "ai_odds", "")
        upset_risk = getattr(pred, "upset_risk", "Medio")
        map_pick   = getattr(pred, "map_pick", "")
    else:
        pred       = prediction
        ai_txt     = pred.get("ai_analysis", "")
        ai_pick    = pred.get("ai_pick", "")
        ai_odds    = pred.get("ai_odds", "")
        upset_risk = pred.get("upset_risk", "Medio")
        map_pick   = pred.get("map_pick", "")

    winner_arrow = "👈" if pred.predicted_winner == pred.home_team else "👉"

    lines = [
        f"  🎮 *{pred.home_team}* vs *{pred.away_team}*",
        "",
        f"  🏆 *Ganador:* {pred.predicted_winner} {winner_arrow}",
        f"     {_emoji(pred.confidence)} {pred.confidence}% [{_bar(pred.confidence)}]",
    ]

    if ai_txt:
        lines.append(f"  🤖 _{ai_txt}_")
    if ai_pick:
        lines.append(f"  💡 *Pick:* {ai_pick}  |  Cuota ~{ai_odds}")
    if map_pick:
        lines.append(f"  🗺️ *Mapa/Side:* {map_pick}")

    lines.append(
        f"  {_upset_emoji(upset_risk)} *Riesgo sorpresa:* {upset_risk}"
    )

    for key, desc in pred.factors.items():
        lines.append(f"     {desc}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
#  MENSAJE DIARIO COMPLETO
# ──────────────────────────────────────────────────────────────

def format_daily_predictions(
    football_predictions: list,
    nba_predictions: list,
    lol_predictions: list,
    esport_predictions: dict = None,  # {"cs2": [...], "valorant": [...]}
    is_tomorrow: bool = False,
) -> str:
    today     = datetime.now()
    date_str  = today.strftime("%d/%m/%Y")
    day_label = "MAÑANA" if is_tomorrow else "HOY"

    lines = [
        f"📊 *PRONÓSTICOS CON IA — {date_str}*",
        f"🗓️ Partidos de {day_label}  🤖 _Análisis: Groq Llama 3.1_",
        "",
    ]

    # ── Fútbol ────────────────────────────────────────────────
    if football_predictions:
        lines.append("⚽ *FÚTBOL*")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        by_league = {}
        for match_data, league in football_predictions:
            by_league.setdefault(league, []).append(match_data)
        for league, matches in by_league.items():
            lines.append(f"\n🏆 *{league}*")
            for md in matches:
                lines.append(format_football_match(md))
                lines.append("  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─")

    # ── NBA ───────────────────────────────────────────────────
    if nba_predictions:
        lines.extend(["", "🏀 *NBA*", "━━━━━━━━━━━━━━━━━━━━"])
        for md in nba_predictions:
            lines.append(format_nba_match(md))
            lines.append("  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─")

    # ── LoL (formato heredado) ────────────────────────────────
    if lol_predictions:
        lines.extend(["", "🎮 *LEAGUE OF LEGENDS*", "━━━━━━━━━━━━━━━━━━━━"])
        by_league = {}
        for pred, league in lol_predictions:
            by_league.setdefault(league, []).append(pred)
        for league, preds in by_league.items():
            lines.append(f"\n🏆 *{league}*")
            for pred in preds:
                lines.append(format_esport_match(pred, "🎮 LoL"))
                lines.append("")

    # ── Otros esports (CS2, Valorant, Dota2) ─────────────────
    if esport_predictions:
        icons = {"cs2": "🔫 *CS2*", "valorant": "🌀 *VALORANT*",
                 "dota2": "🏹 *DOTA 2*", "rl": "🚗 *ROCKET LEAGUE*"}
        for sport_key, matches in esport_predictions.items():
            if not matches:
                continue
            lines.extend([
                "", icons.get(sport_key, f"🎮 *{sport_key.upper()}*"),
                "━━━━━━━━━━━━━━━━━━━━",
            ])
            by_league = {}
            for pred, league, label in matches:
                by_league.setdefault(league, []).append(pred)
            for league, preds in by_league.items():
                lines.append(f"\n🏆 *{league}*")
                for pred in preds:
                    lines.append(format_esport_match(pred))
                    lines.append("")

    # ── Sin partidos ──────────────────────────────────────────
    if not any([football_predictions, nba_predictions,
                lol_predictions, esport_predictions]):
        lines.append("😴 No se encontraron partidos para hoy.")
        lines.append("Usa /futbol /nba /lol /cs2 /valorant")

    # ── Footer stats ──────────────────────────────────────────
    stats = get_accuracy_stats()
    total_ok  = sum(s["monthly"]["correct"] for s in stats.values())
    total_all = sum(s["monthly"]["total"]   for s in stats.values())

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _Pronósticos orientativos — no garantía_",
    ])

    if total_all > 0:
        acc = round(total_ok / total_all * 100, 1)
        lines.append(
            f"📊 _Aciertos ganador este mes: {acc}% ({total_ok}/{total_all})_"
        )
    else:
        lines.append("📊 _Sin datos de aciertos aún_")

    lines.append("🤖 _Powered by Groq Llama 3.1 70B · Auto-aprendizaje activo_")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
#  STATS + WELCOME (sin cambios relevantes, solo actualizados)
# ──────────────────────────────────────────────────────────────

def format_stats_message() -> str:
    stats    = get_accuracy_stats()
    weights  = get_current_weights()
    month    = datetime.now().strftime("%B %Y")
    lines    = [
        "📈 *ESTADÍSTICAS DEL BOT*",
        f"📅 {month}  🤖 _Groq Llama 3.1_",
        "━━━━━━━━━━━━━━━━━━━━", "",
    ]
    sport_names = {
        "football": "⚽ Fútbol",
        "nba":      "🏀 NBA",
        "lol":      "🎮 Esports",
    }
    total_ok = total_all = 0
    for sport, name in sport_names.items():
        s = stats[sport]
        lines.append(f"*{name}*")
        if s["monthly"]["total"] > 0:
            lines.append(
                f"  Mes: {s['monthly']['accuracy']}% "
                f"({s['monthly']['correct']}/{s['monthly']['total']})"
            )
        else:
            lines.append("  Mes: Sin datos")
        if s["all_time"]["total"] > 0:
            lines.append(
                f"  Histórico: {s['all_time']['accuracy']}% "
                f"({s['all_time']['correct']}/{s['all_time']['total']})"
            )
        total_ok  += s["all_time"]["correct"]
        total_all += s["all_time"]["total"]
        lines.append("")

    if total_all > 0:
        overall = round(total_ok / total_all * 100, 1)
        lines.append(f"🎯 *Precisión general: {overall}%*")
    else:
        lines.append("🎯 _Precisión: pendiente de primeros resultados_")

    return "\n".join(lines)


def format_welcome_message() -> str:
    return (
        "🏆 *¡Bienvenido al Bot de Pronósticos con IA\\!*\n"
        "\n"
        "Uso *Groq Llama 3\\.1 70B* para analizar cada partido con\n"
        "estadísticas reales y producir pronósticos fundamentados\\.\n"
        "\n"
        "📊 *Deportes y mercados:*\n"
        "\n"
        "⚽ *Fútbol* \\(Libertadores, Sudamericana, Premier,\n"
        "  La Liga, Champions, BetPlay\\)\n"
        "  • Ganador · Over/Under · BTTS · Córners · Marcador\n"
        "\n"
        "🏀 *NBA*\n"
        "  • Ganador · Over/Under pts · Spread · Q1 · Líneas\n"
        "\n"
        "🎮 *Esports* \\(LoL, CS2, Valorant, Dota 2\\)\n"
        "  • Ganador · Riesgo sorpresa · Ventaja de mapa/side\n"
        "\n"
        "📱 *Comandos:*\n"
        "  /pronosticos — Todos\n"
        "  /futbol — Solo fútbol\n"
        "  /nba — Solo NBA\n"
        "  /lol — League of Legends\n"
        "  /cs2 — Counter\\-Strike 2\n"
        "  /valorant — Valorant\n"
        "  /stats — Estadísticas de acierto\n"
        "  /verificar — Verificar resultados\n"
        "\n"
        "⏰ _Envío automático 8:00 AM \\(COL\\)_\n"
        "🤖 _Powered by Groq · 100% gratis_"
    )