"""
Formateador de mensajes para Telegram — Multi-mercado.
Genera mensajes bonitos con emojis y estructura clara.
"""
from datetime import datetime
from predictor.engine import Prediction, get_accuracy_stats, get_current_weights


def _confidence_bar(confidence: float) -> str:
    """Genera barra visual de confianza."""
    filled = int(confidence / 10)
    return "█" * filled + "░" * (10 - filled)


def _confidence_emoji(confidence: float) -> str:
    """Emoji según nivel de confianza."""
    if confidence >= 75:
        return "🔥"
    elif confidence >= 65:
        return "✅"
    elif confidence >= 58:
        return "🟡"
    else:
        return "⚪"


def format_football_match(match_data: dict) -> str:
    """
    Formatea un partido de fútbol con todos sus mercados.
    
    Args:
        match_data: Dict con 'prediction' y 'markets'
    """
    pred = match_data["prediction"]
    markets = match_data["markets"]

    # Header del partido
    winner_emoji = "👈" if pred.predicted_winner == pred.home_team else "👉"
    lines = [
        f"  ⚽ *{pred.home_team}* vs *{pred.away_team}*",
        "",
    ]

    # 1X2 - Ganador
    lines.append(f"  🏆 *Ganador:* {pred.predicted_winner} {winner_emoji}")
    lines.append(f"     {_confidence_emoji(pred.confidence)} Confianza: {pred.confidence}% [{_confidence_bar(pred.confidence)}]")

    # Factores del ganador
    for key, desc in pred.factors.items():
        lines.append(f"     {desc}")

    # Over/Under
    ou = markets.get("over_under", {})
    if ou:
        lines.append("")
        lines.append(f"  📊 *Goles:* {ou['recommendation']}")
        lines.append(f"     {_confidence_emoji(ou['confidence'])} {ou['confidence']}% | {ou['detail']}")

    # BTTS
    btts = markets.get("btts", {})
    if btts:
        lines.append(f"  🎯 *Ambos Anotan:* {btts['recommendation']}")
        lines.append(f"     {_confidence_emoji(btts['confidence'])} {btts['confidence']}% | {btts['detail']}")

    # Córners
    corners = markets.get("corners", {})
    if corners:
        lines.append(f"  🚩 *Córners:* {corners['recommendation']}")
        lines.append(f"     {_confidence_emoji(corners['confidence'])} {corners['confidence']}% | {corners['detail']}")

    # Resultado exacto
    exact = markets.get("exact_score", {})
    if exact and exact.get("top_scores"):
        scores_text = " | ".join([f"{s[0]} ({s[1]}%)" for s in exact["top_scores"]])
        lines.append(f"  🎲 *Marcador:* {scores_text}")
        lines.append(f"     xG: {exact['home_xg']}-{exact['away_xg']}")

    return "\n".join(lines)


def format_nba_match(match_data: dict) -> str:
    """
    Formatea un partido de NBA con todos sus mercados.
    """
    pred = match_data["prediction"]
    markets = match_data["markets"]

    winner_emoji = "👈" if pred.predicted_winner == pred.home_team else "👉"
    lines = [
        f"  🏀 *{pred.home_team}* vs *{pred.away_team}*",
        "",
    ]

    # Ganador
    lines.append(f"  🏆 *Ganador:* {pred.predicted_winner} {winner_emoji}")
    lines.append(f"     {_confidence_emoji(pred.confidence)} Confianza: {pred.confidence}% [{_confidence_bar(pred.confidence)}]")
    for key, desc in pred.factors.items():
        lines.append(f"     {desc}")

    # Over/Under puntos
    ou = markets.get("over_under", {})
    if ou:
        lines.append("")
        lines.append(f"  📊 *Puntos:* {ou['recommendation']}")
        lines.append(f"     {_confidence_emoji(ou['confidence'])} {ou['confidence']}% | Proy: {ou['projected_total']} pts")
        lines.append(f"     {ou['detail']}")

    # Handicap
    hc = markets.get("handicap", {})
    if hc:
        lines.append(f"  📐 *Spread:* {hc['recommendation']}")
        lines.append(f"     {_confidence_emoji(hc['confidence'])} {hc['confidence']}% | {hc['detail']}")

    # Primer cuarto
    q1 = markets.get("first_quarter", {})
    if q1:
        lines.append(f"  ⏱️ *1er Cuarto:* {q1['recommendation']}")
        lines.append(f"     {_confidence_emoji(q1['confidence'])} {q1['confidence']}% | {q1['detail']}")

    # Puntos por equipo
    tp = markets.get("team_points", {})
    if tp:
        lines.append(f"  📈 *Líneas:* {tp['home_team']} O/U {tp['home_line']} (prom {tp['home_avg']})")
        lines.append(f"     {tp['away_team']} O/U {tp['away_line']} (prom {tp['away_avg']})")

    return "\n".join(lines)


def format_lol_match(prediction: Prediction) -> str:
    """
    Formatea un partido de LoL (solo ganador directo).
    """
    winner_emoji = "👈" if prediction.predicted_winner == prediction.home_team else "👉"
    lines = [
        f"  🎮 *{prediction.home_team}* vs *{prediction.away_team}*",
        f"  🏆 *Ganador:* {prediction.predicted_winner} {winner_emoji}",
        f"     {_confidence_emoji(prediction.confidence)} Confianza: {prediction.confidence}% [{_confidence_bar(prediction.confidence)}]",
    ]
    for key, desc in prediction.factors.items():
        lines.append(f"     {desc}")

    return "\n".join(lines)


def _get_best_bets(
    football_predictions: list,
    nba_predictions: list,
    lol_predictions: list,
) -> list:
    """
    Analiza TODOS los mercados de todos los deportes y selecciona
    las 1-2 apuestas con mayor confianza del día.
    
    Returns:
        Lista de dicts: [{sport, match, market, recommendation, confidence, detail}]
    """
    candidates = []

    # ---- Fútbol: analizar todos los mercados ----
    for match_data, league in football_predictions:
        pred = match_data["prediction"]
        markets = match_data["markets"]
        match_label = f"{pred.home_team} vs {pred.away_team}"

        # Ganador 1X2
        candidates.append({
            "sport": "⚽",
            "league": league,
            "match": match_label,
            "market": "Ganador",
            "recommendation": pred.predicted_winner,
            "confidence": pred.confidence,
            "detail": f"Confianza {pred.confidence}%",
        })

        # Over/Under
        ou = markets.get("over_under", {})
        if ou and ou.get("confidence", 0) >= 55:
            candidates.append({
                "sport": "⚽",
                "league": league,
                "match": match_label,
                "market": "Goles",
                "recommendation": ou["recommendation"],
                "confidence": ou["confidence"],
                "detail": ou.get("detail", ""),
            })

        # BTTS
        btts = markets.get("btts", {})
        if btts and btts.get("confidence", 0) >= 60:
            candidates.append({
                "sport": "⚽",
                "league": league,
                "match": match_label,
                "market": "Ambos Anotan",
                "recommendation": btts["recommendation"],
                "confidence": btts["confidence"],
                "detail": btts.get("detail", ""),
            })

        # Córners
        corners = markets.get("corners", {})
        if corners and corners.get("confidence", 0) >= 60:
            candidates.append({
                "sport": "⚽",
                "league": league,
                "match": match_label,
                "market": "Córners",
                "recommendation": corners["recommendation"],
                "confidence": corners["confidence"],
                "detail": corners.get("detail", ""),
            })

    # ---- NBA: analizar mercados ----
    for match_data in nba_predictions:
        pred = match_data["prediction"]
        markets = match_data["markets"]
        match_label = f"{pred.home_team} vs {pred.away_team}"

        # Ganador
        candidates.append({
            "sport": "🏀",
            "league": "NBA",
            "match": match_label,
            "market": "Ganador",
            "recommendation": pred.predicted_winner,
            "confidence": pred.confidence,
            "detail": f"Confianza {pred.confidence}%",
        })

        # Over/Under
        ou = markets.get("over_under", {})
        if ou and ou.get("confidence", 0) >= 55:
            candidates.append({
                "sport": "🏀",
                "league": "NBA",
                "match": match_label,
                "market": "Puntos",
                "recommendation": ou["recommendation"],
                "confidence": ou["confidence"],
                "detail": f"Proy: {ou.get('projected_total', '?')} pts",
            })

        # Handicap/Spread
        hc = markets.get("handicap", {})
        if hc and hc.get("confidence", 0) >= 60:
            candidates.append({
                "sport": "🏀",
                "league": "NBA",
                "match": match_label,
                "market": "Spread",
                "recommendation": hc["recommendation"],
                "confidence": hc["confidence"],
                "detail": hc.get("detail", ""),
            })

    # ---- LoL: solo ganador ----
    for pred, league in lol_predictions:
        match_label = f"{pred.home_team} vs {pred.away_team}"
        candidates.append({
            "sport": "🎮",
            "league": league,
            "match": match_label,
            "market": "Ganador",
            "recommendation": pred.predicted_winner,
            "confidence": pred.confidence,
            "detail": f"Confianza {pred.confidence}%",
        })

    # Ordenar por confianza descendente
    candidates.sort(key=lambda x: x["confidence"], reverse=True)

    # Seleccionar máximo 2, pero solo si tienen >= 60% confianza
    best = [c for c in candidates if c["confidence"] >= 60][:2]

    # Si no hay ninguno con 60%+, tomar el mejor que haya
    if not best and candidates:
        best = [candidates[0]]

    return best


def _format_best_bets(best_bets: list) -> str:
    """Formatea la sección de mejores apuestas del día."""
    if not best_bets:
        return ""

    lines = [
        "🔥🔥🔥 *APUESTAS DEL DÍA* 🔥🔥🔥",
        "━━━━━━━━━━━━━━━━━━━━",
        "_Las apuestas con mayor probabilidad:_",
        "",
    ]

    for i, bet in enumerate(best_bets, 1):
        medal = "🥇" if i == 1 else "🥈"
        lines.append(f"{medal} *PICK #{i}*")
        lines.append(f"   {bet['sport']} {bet['match']}")
        lines.append(f"   📌 *{bet['market']}:* {bet['recommendation']}")
        lines.append(f"   🎯 Confianza: *{bet['confidence']}%* [{_confidence_bar(bet['confidence'])}]")
        lines.append(f"   📋 {bet['detail']}")
        lines.append(f"   🏆 _{bet['league']}_")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    return "\n".join(lines)


def format_daily_predictions(
    football_predictions: list,
    nba_predictions: list,
    lol_predictions: list,
    is_tomorrow: bool = False,
) -> str:
    """
    Formatea todos los pronósticos del día en un solo mensaje.
    Incluye sección de APUESTAS DEL DÍA al inicio.
    
    Args:
        football_predictions: Lista de (match_data_dict, league_name)
        nba_predictions: Lista de match_data_dicts
        lol_predictions: Lista de (prediction, league_name) tuples
        is_tomorrow: Si son pronósticos para mañana
    """
    today = datetime.now()
    date_str = today.strftime("%d/%m/%Y")
    day_label = "MAÑANA" if is_tomorrow else "HOY"

    lines = [
        f"📊 *PRONÓSTICOS DEPORTIVOS — {date_str}*",
        f"🗓️ Partidos de {day_label}",
        "",
    ]

    # ---- APUESTAS DEL DÍA (al inicio) ----
    has_any = football_predictions or nba_predictions or lol_predictions
    if has_any:
        best_bets = _get_best_bets(football_predictions, nba_predictions, lol_predictions)
        best_bets_text = _format_best_bets(best_bets)
        if best_bets_text:
            lines.append(best_bets_text)

    # ---- FÚTBOL ----
    if football_predictions:
        lines.append("⚽ *FÚTBOL*")
        lines.append("━━━━━━━━━━━━━━━━━━━━")

        # Agrupar por liga
        by_league = {}
        for match_data, league in football_predictions:
            if league not in by_league:
                by_league[league] = []
            by_league[league].append(match_data)

        for league, matches in by_league.items():
            lines.append(f"\n🏆 *{league}*")
            for match_data in matches:
                lines.append(format_football_match(match_data))
                lines.append("  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─")

    # ---- NBA ----
    if nba_predictions:
        lines.append("")
        lines.append("🏀 *NBA*")
        lines.append("━━━━━━━━━━━━━━━━━━━━")

        for match_data in nba_predictions:
            lines.append(format_nba_match(match_data))
            lines.append("  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─")

    # ---- LOL ----
    if lol_predictions:
        lines.append("")
        lines.append("🎮 *LEAGUE OF LEGENDS*")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("_(Solo ganador directo)_")

        by_league = {}
        for pred, league in lol_predictions:
            if league not in by_league:
                by_league[league] = []
            by_league[league].append(pred)

        for league, preds in by_league.items():
            lines.append(f"\n🏆 *{league}*")
            for pred in preds:
                lines.append(format_lol_match(pred))
                lines.append("")

    # ---- Sin partidos ----
    if not football_predictions and not nba_predictions and not lol_predictions:
        lines.append("😴 No se encontraron partidos para hoy.")
        lines.append("Intenta de nuevo mañana o usa /futbol /nba /lol")

    # ---- Footer con stats ----
    stats = get_accuracy_stats()
    total_correct = sum(s["monthly"]["correct"] for s in stats.values())
    total_predictions = sum(s["monthly"]["total"] for s in stats.values())

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ _Los pronósticos son orientativos_")
    lines.append("⚠️ _No son garantía de resultado_")

    if total_predictions > 0:
        accuracy = round(total_correct / total_predictions * 100, 1)
        lines.append(
            f"📊 _Aciertos ganador del mes: {accuracy}% ({total_correct}/{total_predictions})_"
        )
    else:
        lines.append("📊 _Sin datos de aciertos aún — se calculan automáticamente_")

    lines.append("🧠 _Auto-aprendizaje activo_")

    return "\n".join(lines)


def format_stats_message() -> str:
    """Formatea las estadísticas de acierto del bot."""
    stats = get_accuracy_stats()
    weights = get_current_weights()
    month_name = datetime.now().strftime("%B %Y")

    lines = [
        "📈 *ESTADÍSTICAS DEL BOT*",
        f"📅 {month_name}",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    sport_names = {"football": "⚽ Fútbol", "nba": "🏀 NBA", "lol": "🎮 LoL"}
    total_correct = 0
    total_predictions = 0

    for sport, name in sport_names.items():
        s = stats[sport]
        lines.append(f"*{name}*")
        if s["monthly"]["total"] > 0:
            lines.append(f"  Este mes: {s['monthly']['accuracy']}% ({s['monthly']['correct']}/{s['monthly']['total']})")
        else:
            lines.append("  Este mes: Sin datos")
        if s["all_time"]["total"] > 0:
            lines.append(f"  Histórico: {s['all_time']['accuracy']}% ({s['all_time']['correct']}/{s['all_time']['total']})")
        else:
            lines.append("  Histórico: Sin datos")
        total_correct += s["all_time"]["correct"]
        total_predictions += s["all_time"]["total"]
        lines.append("")

    # Pesos actuales
    lines.append("🧠 *PESOS DEL ALGORITMO (ganador)*")
    lines.append("_(se auto-ajustan con cada resultado)_")
    lines.append("")

    weight_names = {
        "table_position": "📊 Tabla",
        "recent_form": "🔥 Racha",
        "home_advantage": "🏠 Local",
        "head_to_head": "⚔️ H2H",
        "goals_form": "⚽ Goles",
        "record": "📊 Récord",
        "points_avg": "🏀 Puntos",
        "win_rate": "📊 WinRate",
        "tournament_position": "🏆 Torneo",
        "side_preference": "🔵 Side",
    }

    for sport, name in sport_names.items():
        lines.append(f"*{name}:*")
        w = weights.get(sport, {})
        for factor, value in sorted(w.items(), key=lambda x: -x[1]):
            label = weight_names.get(factor, factor)
            pct = round(value * 100)
            bar = "▓" * (pct // 5) + "░" * (20 - pct // 5)
            lines.append(f"  {label}: {bar} {pct}%")
        lines.append("")

    if total_predictions > 0:
        overall = round(total_correct / total_predictions * 100, 1)
        lines.append(f"🎯 *Precisión general: {overall}%*")
    else:
        lines.append("🎯 _Precisión: pendiente de resultados_")

    lines.append("")
    lines.append("_Nota: Los mercados adicionales (goles, córners,_")
    lines.append("_spread, etc.) no se rastrean por el auto-aprendizaje._")
    lines.append("_Solo el mercado 'ganador' se auto-ajusta._")

    return "\n".join(lines)


def format_welcome_message() -> str:
    """Mensaje de bienvenida cuando el usuario usa /start."""
    return (
        "🏆 *¡Bienvenido al Bot de Pronósticos Deportivos\\!*\n"
        "\n"
        "Soy un bot con *inteligencia artificial auto\\-adaptativa*\\. "
        "Analizo estadísticas reales para generar pronósticos diarios\\.\n"
        "\n"
        "📊 *Deportes y mercados:*\n"
        "\n"
        "⚽ *Fútbol* \\(Premier, La Liga, Champions, Serie A,\n"
        "  BetPlay, Libertadores, Sudamericana\\)\n"
        "  • Ganador 1X2\n"
        "  • Over/Under 2\\.5 goles\n"
        "  • Ambos Anotan \\(BTTS\\)\n"
        "  • Córners estimados\n"
        "  • Marcador exacto probable\n"
        "\n"
        "🏀 *NBA*\n"
        "  • Ganador directo\n"
        "  • Over/Under puntos totales\n"
        "  • Handicap / Spread\n"
        "  • 1er Cuarto\n"
        "  • Líneas por equipo\n"
        "\n"
        "🎮 *League of Legends* \\(esports pro\\)\n"
        "  • Ganador directo\n"
        "\n"
        "🧠 *¿Cómo funciono?*\n"
        "Analizo posición en tabla, rachas, enfrentamientos directos, "
        "ventaja local, promedios goleadores y más\\. Después de cada "
        "jornada, verifico resultados y *auto\\-ajusto mi algoritmo*\\.\n"
        "\n"
        "📱 *Comandos:*\n"
        "  /pronosticos — Todos los pronósticos\n"
        "  /futbol — Solo fútbol\n"
        "  /nba — Solo NBA\n"
        "  /lol — Solo LoL\n"
        "  /stats — Estadísticas de acierto\n"
        "  /pesos — Pesos del algoritmo\n"
        "  /verificar — Verificar resultados\n"
        "\n"
        "⏰ _Envío automático diario a las 8:00 AM \\(COL\\)_"
    )
