"""
🏆 Bot de Pronósticos Deportivos — Telegram
Envía pronósticos diarios de Fútbol, NBA y LoL con auto-aprendizaje.

Uso: python pronosticos_bot.py
"""
import logging
import asyncio
from datetime import datetime, time, timedelta

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from config import (
    TELEGRAM_TOKEN,
    CHAT_ID,
    FOOTBALL_LEAGUES,
    NBA_LEAGUE,
    SCHEDULE_HOUR,
    SCHEDULE_MINUTE,
    TIMEZONE,
)

from api import thesportsdb, pandascore, conmebol
from predictor import futbol, nba, lol
from predictor.engine import (
    get_accuracy_stats,
    get_unverified_predictions,
    verify_prediction,
    get_current_weights,
)
from formatters.telegram import (
    format_daily_predictions,
    format_stats_message,
    format_welcome_message,
)

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============================================================
# Utilidades de zona horaria
# ============================================================

def _get_event_dates() -> list:
    """
    Retorna las fechas UTC a consultar para encontrar partidos de hoy.
    TheSportsDB usa fechas UTC. Un partido a las 7pm Colombia (UTC-5)
    se registra como el día siguiente en UTC (00:00 UTC).
    Por eso consultamos hoy Y mañana en UTC.
    """
    import pytz
    tz = pytz.timezone(TIMEZONE)
    now_local = datetime.now(tz)
    today_local = now_local.strftime("%Y-%m-%d")
    
    # En UTC, "hoy" puede ser hoy o mañana
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    today_utc = now_utc.strftime("%Y-%m-%d")
    tomorrow_utc = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Siempre consultar ambas fechas para no perder partidos
    dates = [today_utc]
    if tomorrow_utc != today_utc:
        dates.append(tomorrow_utc)
    
    return dates


def _is_upcoming_event(event: dict) -> bool:
    """
    Verifica si un evento aún no ha terminado.
    Filtra los que ya tienen resultado final (FT).
    """
    status = (event.get("strStatus") or "").upper()
    # FT = Full Time, AET = After Extra Time, PEN = Penalties, AOT = After OT
    finished_statuses = {"FT", "AET", "PEN", "AOT", "ABD", "CANC", "PST", "AWD", "WO"}
    
    if status in finished_statuses:
        return False
    
    # Si tiene score final, está terminado
    home_score = event.get("intHomeScore")
    away_score = event.get("intAwayScore")
    if home_score is not None and away_score is not None:
        try:
            int(home_score)
            int(away_score)
            if status == "FT" or status == "":
                # Tiene score pero sin status claro — verificar por hora
                return False
        except (ValueError, TypeError):
            pass
    
    return True


# ============================================================
# Generadores de Pronósticos
# ============================================================

def generate_football_predictions() -> list:
    """
    Genera pronósticos multi-mercado para todos los partidos de fútbol del día.
    Incluye ligas de TheSportsDB + torneos CONMEBOL de API-Football.
    Consulta hoy + mañana UTC para cubrir zona horaria Colombia.
    
    Returns:
        Lista de (match_data_dict, league_name) tuples
        match_data_dict = {"prediction": Prediction, "markets": {...}}
    """
    predictions = []
    dates = _get_event_dates()
    seen_events = set()  # Evitar duplicados

    # ---- Ligas de TheSportsDB ----
    for league_name, league_id in FOOTBALL_LEAGUES.items():
        try:
            all_events = []
            for date in dates:
                evts = thesportsdb.get_events_by_league_date(league_id, date)
                all_events.extend(evts)

            # Filtrar solo partidos que NO han terminado
            events = [e for e in all_events if _is_upcoming_event(e)]

            if not events:
                logger.info(f"Sin partidos hoy en {league_name}")
                continue

            for event in events:
                home_team = event.get("strHomeTeam", "")
                away_team = event.get("strAwayTeam", "")
                event_id = str(event.get("idEvent", ""))

                if not home_team or not away_team:
                    continue

                try:
                    match_data = futbol.predict_match(
                        home_team=home_team,
                        away_team=away_team,
                        league_name=league_name,
                        league_id=league_id,
                        event_id=event_id,
                    )
                    predictions.append((match_data, league_name))
                except Exception as e:
                    logger.error(f"Error prediciendo {home_team} vs {away_team}: {e}")

        except Exception as e:
            logger.error(f"Error obteniendo partidos de {league_name}: {e}")

    # ---- Torneos CONMEBOL (Libertadores + Sudamericana) ----
    try:
        conmebol_matches = conmebol.get_conmebol_matches_today(today)
        if conmebol_matches:
            logger.info(f"⚽ CONMEBOL: {len(conmebol_matches)} partidos encontrados")

        for match in conmebol_matches:
            home_team = match.get("home_team", "")
            away_team = match.get("away_team", "")
            league_name = match.get("league_name", "CONMEBOL")
            event_id = match.get("event_id", "")

            if not home_team or not away_team:
                continue

            # Obtener datos pasados de CONMEBOL para el predictor
            past_results = conmebol.get_conmebol_past_results()

            try:
                match_data = futbol.predict_match(
                    home_team=home_team,
                    away_team=away_team,
                    league_name=league_name,
                    league_id=0,  # Sin ID de TheSportsDB
                    event_id=event_id,
                )
                predictions.append((match_data, league_name))
            except Exception as e:
                logger.error(f"Error prediciendo CONMEBOL {home_team} vs {away_team}: {e}")

    except Exception as e:
        logger.error(f"Error obteniendo partidos CONMEBOL: {e}")

    return predictions


def generate_nba_predictions() -> list:
    """
    Genera pronósticos multi-mercado para todos los partidos de NBA del día.
    Consulta hoy + mañana UTC para cubrir zona horaria Colombia.
    
    Returns:
        Lista de match_data_dicts
        match_data_dict = {"prediction": Prediction, "markets": {...}}
    """
    predictions = []
    dates = _get_event_dates()

    for league_name, league_id in NBA_LEAGUE.items():
        try:
            all_events = []
            for date in dates:
                evts = thesportsdb.get_events_by_league_date(league_id, date)
                all_events.extend(evts)

            # Filtrar solo partidos que NO han terminado
            events = [e for e in all_events if _is_upcoming_event(e)]

            if not events:
                logger.info("Sin partidos NBA hoy")
                continue

            for event in events:
                home_team = event.get("strHomeTeam", "")
                away_team = event.get("strAwayTeam", "")
                event_id = str(event.get("idEvent", ""))

                if not home_team or not away_team:
                    continue

                try:
                    match_data = nba.predict_match(
                        home_team=home_team,
                        away_team=away_team,
                        event_id=event_id,
                    )
                    predictions.append(match_data)
                except Exception as e:
                    logger.error(f"Error prediciendo NBA {home_team} vs {away_team}: {e}")

        except Exception as e:
            logger.error(f"Error obteniendo partidos NBA: {e}")

    return predictions


def generate_lol_predictions() -> list:
    """
    Genera pronósticos para partidos de LoL próximos.
    
    Returns:
        Lista de (Prediction, league_name) tuples
    """
    predictions = []

    try:
        matches = lol.get_upcoming_matches()

        if not matches:
            logger.info("Sin partidos LoL próximos")
            return predictions

        # Tomar máximo 5 partidos para no saturar
        for match in matches[:5]:
            try:
                prediction = lol.predict_match(
                    team1_name=match["team1_name"],
                    team2_name=match["team2_name"],
                    league_name=match["league_name"],
                    event_id=str(match["match_id"]),
                )
                predictions.append((prediction, match["league_name"]))
            except Exception as e:
                logger.error(f"Error prediciendo LoL {match['team1_name']} vs {match['team2_name']}: {e}")

    except Exception as e:
        logger.error(f"Error obteniendo partidos LoL: {e}")

    return predictions


# ============================================================
# Verificación de Resultados (Auto-aprendizaje)
# ============================================================

def verify_results():
    """
    Verifica resultados de predicciones anteriores.
    Busca en las APIs si los partidos ya terminaron y compara.
    """
    unverified = get_unverified_predictions()
    verified_count = 0

    for pred_data in unverified:
        sport = pred_data.get("sport")
        event_id = pred_data.get("event_id")

        if not event_id:
            continue

        try:
            if sport == "football":
                # Buscar en resultados recientes de la liga
                for league_name, league_id in FOOTBALL_LEAGUES.items():
                    past = thesportsdb.get_past_events(league_id)
                    for event in past:
                        if str(event.get("idEvent")) == event_id:
                            home_score = int(event.get("intHomeScore") or -1)
                            away_score = int(event.get("intAwayScore") or -1)

                            if home_score < 0 or away_score < 0:
                                continue

                            if home_score > away_score:
                                actual_winner = event.get("strHomeTeam", "")
                            elif away_score > home_score:
                                actual_winner = event.get("strAwayTeam", "")
                            else:
                                actual_winner = "Empate"

                            result = verify_prediction(event_id, actual_winner)
                            if result is not None:
                                verified_count += 1
                                status = "✅" if result else "❌"
                                logger.info(
                                    f"{status} Verificado: {pred_data['home_team']} vs "
                                    f"{pred_data['away_team']} → {actual_winner}"
                                )
                            break

            elif sport == "nba":
                past = thesportsdb.get_past_events(4387)
                for event in past:
                    if str(event.get("idEvent")) == event_id:
                        home_score = int(event.get("intHomeScore") or -1)
                        away_score = int(event.get("intAwayScore") or -1)

                        if home_score < 0 or away_score < 0:
                            continue

                        if home_score > away_score:
                            actual_winner = event.get("strHomeTeam", "")
                        else:
                            actual_winner = event.get("strAwayTeam", "")

                        result = verify_prediction(event_id, actual_winner)
                        if result is not None:
                            verified_count += 1
                            status = "✅" if result else "❌"
                            logger.info(
                                f"{status} NBA Verificado: {pred_data['home_team']} vs "
                                f"{pred_data['away_team']} → {actual_winner}"
                            )
                        break

            elif sport == "lol":
                past = pandascore.get_past_lol_matches(per_page=30)
                for match in past:
                    if str(match.get("id")) == event_id:
                        winner = match.get("winner") or {}
                        actual_winner = winner.get("name", "")

                        if actual_winner:
                            result = verify_prediction(event_id, actual_winner)
                            if result is not None:
                                verified_count += 1
                                status = "✅" if result else "❌"
                                logger.info(
                                    f"{status} LoL Verificado: {pred_data['home_team']} vs "
                                    f"{pred_data['away_team']} → {actual_winner}"
                                )
                        break

        except Exception as e:
            logger.error(f"Error verificando {event_id}: {e}")

    if verified_count > 0:
        logger.info(f"📊 Se verificaron {verified_count} predicciones y se ajustaron los pesos")

    return verified_count


# ============================================================
# Comandos de Telegram
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start — Bienvenida."""
    await update.message.reply_text(
        format_welcome_message(),
        parse_mode="MarkdownV2",
    )


async def cmd_pronosticos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /pronosticos — Todos los pronósticos del día."""
    await update.message.reply_text("🔄 Generando pronósticos... dame unos segundos ⏳")

    # Primero verificar resultados pendientes (auto-aprendizaje)
    verify_results()

    # Generar pronósticos
    football_preds = generate_football_predictions()
    nba_preds = generate_nba_predictions()
    lol_preds = generate_lol_predictions()

    message = format_daily_predictions(football_preds, nba_preds, lol_preds)

    # Telegram tiene límite de 4096 caracteres
    if len(message) > 3800:
        parts = _split_message(message, 3800)
        for part in parts:
            await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_futbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /futbol — Solo pronósticos de fútbol."""
    await update.message.reply_text("⚽ Analizando partidos de fútbol...")

    verify_results()
    football_preds = generate_football_predictions()

    message = format_daily_predictions(football_preds, [], [])
    if len(message) > 3800:
        parts = _split_message(message, 3800)
        for part in parts:
            await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_nba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /nba — Solo pronósticos de NBA."""
    await update.message.reply_text("🏀 Analizando partidos de NBA...")

    verify_results()
    nba_preds = generate_nba_predictions()

    message = format_daily_predictions([], nba_preds, [])
    if len(message) > 3800:
        parts = _split_message(message, 3800)
        for part in parts:
            await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_lol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /lol — Solo pronósticos de LoL."""
    await update.message.reply_text("🎮 Analizando partidos de League of Legends...")

    verify_results()
    lol_preds = generate_lol_predictions()

    message = format_daily_predictions([], [], lol_preds)
    if len(message) > 3800:
        parts = _split_message(message, 3800)
        for part in parts:
            await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats — Estadísticas de acierto."""
    message = format_stats_message()
    await update.message.reply_text(message, parse_mode="Markdown")


async def cmd_pesos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /pesos — Ver pesos actuales del algoritmo."""
    weights = get_current_weights()

    lines = ["🧠 *PESOS ACTUALES DEL ALGORITMO*", ""]

    weight_labels = {
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

    sport_names = {"football": "⚽ Fútbol", "nba": "🏀 NBA", "lol": "🎮 LoL"}

    for sport, name in sport_names.items():
        lines.append(f"*{name}:*")
        w = weights.get(sport, {})
        for factor, value in sorted(w.items(), key=lambda x: -x[1]):
            label = weight_labels.get(factor, factor)
            pct = round(value * 100)
            bar = "▓" * (pct // 5) + "░" * (20 - pct // 5)
            lines.append(f"  {label}: {bar} {pct}%")
        lines.append("")

    lines.append("_Los pesos se ajustan automáticamente_")
    lines.append("_tras verificar cada resultado real_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_verificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /verificar — Fuerza verificación de resultados."""
    await update.message.reply_text("🔍 Verificando resultados pendientes...")

    count = verify_results()

    if count > 0:
        await update.message.reply_text(
            f"✅ Se verificaron *{count}* predicciones.\n"
            f"Los pesos se han ajustado automáticamente.\n\n"
            f"Usa /stats para ver tu precisión actualizada.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "ℹ️ No hay resultados nuevos para verificar.\n"
            "Los partidos aún no han terminado o ya fueron verificados."
        )


# ============================================================
# Envío automático programado
# ============================================================

async def scheduled_predictions(context: ContextTypes.DEFAULT_TYPE):
    """Envía pronósticos automáticamente cada mañana."""
    logger.info("⏰ Envío automático de pronósticos")

    # Verificar resultados de ayer
    verify_results()

    # Generar pronósticos del día
    football_preds = generate_football_predictions()
    nba_preds = generate_nba_predictions()
    lol_preds = generate_lol_predictions()

    message = format_daily_predictions(football_preds, nba_preds, lol_preds)

    if len(message) > 3800:
        parts = _split_message(message, 3800)
        for part in parts:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=part,
                parse_mode="Markdown",
            )
    else:
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="Markdown",
        )


async def scheduled_verify(context: ContextTypes.DEFAULT_TYPE):
    """Verifica resultados automáticamente por la noche."""
    logger.info("🔍 Verificación automática de resultados")
    count = verify_results()

    if count > 0:
        stats = get_accuracy_stats()
        total_correct = sum(s["monthly"]["correct"] for s in stats.values())
        total_preds = sum(s["monthly"]["total"] for s in stats.values())
        accuracy = round(total_correct / total_preds * 100, 1) if total_preds > 0 else 0

        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"📊 *Resultados verificados*\n\n"
                f"Se verificaron *{count}* predicciones\n"
                f"Precisión del mes: *{accuracy}%* ({total_correct}/{total_preds})\n\n"
                f"🧠 _Pesos del algoritmo actualizados_"
            ),
            parse_mode="Markdown",
        )


# ============================================================
# Utilidades
# ============================================================

def _split_message(text: str, max_length: int) -> list:
    """Divide un mensaje largo en partes."""
    lines = text.split("\n")
    parts = []
    current = []
    current_len = 0

    for line in lines:
        if current_len + len(line) + 1 > max_length:
            parts.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line) + 1

    if current:
        parts.append("\n".join(current))

    return parts


# ============================================================
# Main
# ============================================================

def main():
    """Arranca el bot."""
    print("=" * 50)
    print("🏆 Bot de Pronósticos Deportivos")
    print("=" * 50)
    print(f"📱 Chat ID: {CHAT_ID}")
    print(f"⏰ Envío automático: {SCHEDULE_HOUR}:{SCHEDULE_MINUTE:02d} ({TIMEZONE})")
    print(f"⚽ Ligas fútbol: {', '.join(FOOTBALL_LEAGUES.keys())}")
    print(f"🏀 NBA: Activo")
    print(f"🎮 LoL: {'Activo' if pandascore._is_configured() else 'Desactivado (falta PANDASCORE_TOKEN)'}")
    print("=" * 50)
    print("Comandos: /pronosticos /futbol /nba /lol /stats /pesos /verificar")
    print("=" * 50)

    # Crear aplicación
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Registrar comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pronosticos", cmd_pronosticos))
    app.add_handler(CommandHandler("futbol", cmd_futbol))
    app.add_handler(CommandHandler("nba", cmd_nba))
    app.add_handler(CommandHandler("lol", cmd_lol))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("pesos", cmd_pesos))
    app.add_handler(CommandHandler("verificar", cmd_verificar))

    # Programar envío automático diario a las 8:00 AM
    job_queue = app.job_queue
    if job_queue is not None:
        from datetime import time as dt_time
        import pytz

        tz = pytz.timezone(TIMEZONE)

        # Pronósticos cada mañana
        job_queue.run_daily(
            scheduled_predictions,
            time=dt_time(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, tzinfo=tz),
            name="daily_predictions",
        )

        # Verificación de resultados cada noche a las 11 PM
        job_queue.run_daily(
            scheduled_verify,
            time=dt_time(hour=23, minute=0, tzinfo=tz),
            name="nightly_verify",
        )

        print(f"✅ Scheduler configurado: pronósticos a las {SCHEDULE_HOUR}:{SCHEDULE_MINUTE:02d}, verificación a las 23:00")
    else:
        print("⚠️ JobQueue no disponible — instala 'python-telegram-bot[job-queue]'")

    # Iniciar bot
    print("\n🚀 Bot corriendo... esperando comandos")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
