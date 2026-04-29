"""
pronosticos_bot.py — VERSIÓN CON IA COMPLETA

Bot de Telegram con:
  ✅ Groq Llama 3.1 70B (gratis)
  ✅ Fútbol multi-mercado
  ✅ NBA multi-mercado
  ✅ LoL, CS2, Valorant, Dota 2
  ✅ Libertadores + Sudamericana con altitud
  ✅ Auto-aprendizaje adaptativo
  ✅ Nuevos comandos /cs2 /valorant
"""
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    TELEGRAM_TOKEN, CHAT_ID,
    FOOTBALL_LEAGUES, NBA_LEAGUE,
    SCHEDULE_HOUR, SCHEDULE_MINUTE, TIMEZONE,
)
from api import thesportsdb, pandascore, conmebol
from predictor import futbol_con_ai as futbol    # ← usa la versión con IA
from predictor import nba_con_ai as nba          # ← usa la versión con IA
from predictor import esports_con_ai as esports  # ← nuevo módulo unificado

from predictor.engine import (
    get_accuracy_stats, get_unverified_predictions,
    verify_prediction, get_current_weights,
)
from formatters.telegram import (
    format_daily_predictions, format_stats_message,
    format_welcome_message,
)

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ALTITUDES CONMEBOL (factor clave para el análisis IA)
# ──────────────────────────────────────────────────────────────

ALTITUDES = {
    # Colombia
    "Deportes Tolima": 1285,
    "Millonarios": 2640,
    "Santa Fe": 2640,
    "América de Cali": 995,
    "Atlético Nacional": 1495,
    "Independiente Medellín": 1495,
    "Junior": 18,
    "Deportivo Cali": 995,
    "Peñarol": 43,   # Montevideo
    # Bolivia — Extremo
    "Bolívar": 3637,
    "The Strongest": 3637,
    "Always Ready": 3637,
    # Ecuador
    "Liga de Quito": 2850,
    "Independiente del Valle": 2400,
    "Barcelona SC": 4,
    "Emelec": 4,
    # Perú
    "Universitario": 154,
    "Sporting Cristal": 154,
    "Cienciano": 3399,
    "Alianza Lima": 154,
    # Argentina/Brasil/Uruguay — nivel del mar aprox
    "Boca Juniors": 25,
    "River Plate": 25,
    "Flamengo": 10,
    "Fluminense": 10,
    "Palmeiras": 760,
    "Atlético Mineiro": 858,
    "Cruzeiro": 858,
    "Santos": 3,
    "São Paulo": 760,
    # Chile
    "Colo-Colo": 520,
    "Universidad de Chile": 520,
    "O'Higgins": 172,
    "Coquimbo Unido": 28,
}


# ──────────────────────────────────────────────────────────────
#  UTILIDADES DE FECHA/HORA
# ──────────────────────────────────────────────────────────────

def _get_dates() -> list:
    """Fechas UTC a consultar (hoy + mañana) para cubrir COL GMT-5."""
    now  = datetime.now(timezone.utc)
    return [
        now.strftime("%Y-%m-%d"),
        (now + timedelta(days=1)).strftime("%Y-%m-%d"),
    ]


def _is_upcoming(event: dict) -> bool:
    """Filtra partidos ya terminados."""
    status = (event.get("strStatus") or "").upper()
    finished = {"FT", "AET", "PEN", "AOT", "ABD", "CANC", "PST", "AWD", "WO"}
    return status not in finished


# ──────────────────────────────────────────────────────────────
#  GENERADORES DE PRONÓSTICOS
# ──────────────────────────────────────────────────────────────

def generate_football() -> list:
    """Genera pronósticos de fútbol para todas las ligas + CONMEBOL."""
    predictions = []
    dates = _get_dates()

    # Ligas de TheSportsDB
    for league_name, league_id in FOOTBALL_LEAGUES.items():
        try:
            events = []
            for date in dates:
                events.extend(thesportsdb.get_events_by_league_date(league_id, date))
            events = [e for e in events if _is_upcoming(e)]

            for event in events:
                home = event.get("strHomeTeam", "")
                away = event.get("strAwayTeam", "")
                eid  = str(event.get("idEvent", ""))
                if not home or not away:
                    continue
                try:
                    md = futbol.predict_match(
                        home_team=home, away_team=away,
                        league_name=league_name, league_id=league_id,
                        event_id=eid,
                        altitude_m=ALTITUDES.get(home),
                    )
                    predictions.append((md, league_name))
                except Exception as e:
                    logger.error(f"Error {home} vs {away}: {e}")
        except Exception as e:
            logger.error(f"Error liga {league_name}: {e}")

    # CONMEBOL (Libertadores + Sudamericana)
    try:
        for match in conmebol.get_conmebol_matches_today():
            home  = match.get("home_team", "")
            away  = match.get("away_team", "")
            lname = match.get("league_name", "CONMEBOL")
            eid   = match.get("event_id", "")
            if not home or not away:
                continue
            try:
                md = futbol.predict_match(
                    home_team=home, away_team=away,
                    league_name=lname, league_id=0,
                    event_id=eid,
                    altitude_m=ALTITUDES.get(home),
                )
                predictions.append((md, lname))
            except Exception as e:
                logger.error(f"Error CONMEBOL {home} vs {away}: {e}")
    except Exception as e:
        logger.error(f"Error CONMEBOL: {e}")

    return predictions


def generate_nba() -> list:
    """Genera pronósticos NBA."""
    predictions = []
    dates = _get_dates()

    for league_name, league_id in NBA_LEAGUE.items():
        try:
            events = []
            for date in dates:
                events.extend(thesportsdb.get_events_by_league_date(league_id, date))
            events = [e for e in events if _is_upcoming(e)]

            for event in events:
                home = event.get("strHomeTeam", "")
                away = event.get("strAwayTeam", "")
                eid  = str(event.get("idEvent", ""))
                if not home or not away:
                    continue
                try:
                    md = nba.predict_match(home, away, event_id=eid)
                    predictions.append(md)
                except Exception as e:
                    logger.error(f"Error NBA {home} vs {away}: {e}")
        except Exception as e:
            logger.error(f"Error NBA: {e}")

    return predictions


def generate_esports(sport: str = "lol", limit: int = 5) -> list:
    """Genera pronósticos para el esport indicado."""
    return esports.get_all_upcoming(sport=sport, limit=limit)


# ──────────────────────────────────────────────────────────────
#  AUTO-APRENDIZAJE
# ──────────────────────────────────────────────────────────────

def verify_results() -> int:
    """Verifica resultados y ajusta pesos automáticamente."""
    unverified = get_unverified_predictions()
    count = 0

    for pred_data in unverified:
        sport    = pred_data.get("sport")
        event_id = pred_data.get("event_id")
        if not event_id:
            continue

        try:
            if sport == "football":
                for _, lid in FOOTBALL_LEAGUES.items():
                    for ev in thesportsdb.get_past_events(lid):
                        if str(ev.get("idEvent")) != event_id:
                            continue
                        hs, aws = int(ev.get("intHomeScore") or -1), int(ev.get("intAwayScore") or -1)
                        if hs < 0: break
                        winner = ev.get("strHomeTeam") if hs > aws else (
                            ev.get("strAwayTeam") if aws > hs else "Empate"
                        )
                        ok = verify_prediction(event_id, winner)
                        if ok is not None: count += 1
                        break

            elif sport == "nba":
                for ev in thesportsdb.get_past_events(4387):
                    if str(ev.get("idEvent")) != event_id: continue
                    hs, aws = int(ev.get("intHomeScore") or -1), int(ev.get("intAwayScore") or -1)
                    if hs < 0: break
                    winner = ev.get("strHomeTeam") if hs > aws else ev.get("strAwayTeam")
                    ok = verify_prediction(event_id, winner)
                    if ok is not None: count += 1
                    break

            elif sport == "lol":
                for match in pandascore.get_past_lol_matches(per_page=30):
                    if str(match.get("id")) != event_id: continue
                    winner = (match.get("winner") or {}).get("name", "")
                    if winner:
                        ok = verify_prediction(event_id, winner)
                        if ok is not None: count += 1
                    break

        except Exception as e:
            logger.error(f"Error verificando {event_id}: {e}")

    if count:
        logger.info(f"✅ {count} predicciones verificadas, pesos actualizados")
    return count


# ──────────────────────────────────────────────────────────────
#  COMANDOS TELEGRAM
# ──────────────────────────────────────────────────────────────

def _split(text: str, max_len: int = 3800) -> list:
    lines = text.split("\n")
    parts, cur, cur_len = [], [], 0
    for line in lines:
        if cur_len + len(line) + 1 > max_len:
            parts.append("\n".join(cur))
            cur, cur_len = [line], len(line)
        else:
            cur.append(line)
            cur_len += len(line) + 1
    if cur:
        parts.append("\n".join(cur))
    return parts


async def _send(update_or_ctx, text: str, is_ctx: bool = False):
    """Envía mensaje dividiéndolo si excede 4096 chars."""
    send_fn = (
        update_or_ctx.bot.send_message
        if is_ctx else
        update_or_ctx.message.reply_text
    )
    for part in _split(text):
        kwargs = {"text": part, "parse_mode": "Markdown"}
        if is_ctx:
            kwargs["chat_id"] = CHAT_ID
        await send_fn(**kwargs)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_welcome_message(), parse_mode="MarkdownV2")


async def cmd_pronosticos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Generando pronósticos con IA... ⏳")
    verify_results()
    football = generate_football()
    nba_p    = generate_nba()
    lol_p    = generate_esports("lol")
    msg = format_daily_predictions(football, nba_p, lol_p)
    await _send(update, msg)


async def cmd_futbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚽ Analizando fútbol con IA...")
    verify_results()
    msg = format_daily_predictions(generate_football(), [], [])
    await _send(update, msg)


async def cmd_nba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏀 Analizando NBA con IA...")
    verify_results()
    msg = format_daily_predictions([], generate_nba(), [])
    await _send(update, msg)


async def cmd_lol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎮 Analizando LoL con IA...")
    verify_results()
    lol_p = generate_esports("lol")
    msg = format_daily_predictions([], [], lol_p)
    await _send(update, msg)


async def cmd_cs2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔫 Analizando CS2 con IA...")
    cs2_p = generate_esports("cs2")
    msg = format_daily_predictions([], [], [], esport_predictions={"cs2": cs2_p})
    await _send(update, msg)


async def cmd_valorant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌀 Analizando Valorant con IA...")
    val_p = generate_esports("valorant")
    msg = format_daily_predictions([], [], [], esport_predictions={"valorant": val_p})
    await _send(update, msg)


async def cmd_esports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Todos los esports de una vez."""
    await update.message.reply_text("🎮 Analizando todos los esports con IA...")
    lol_p = generate_esports("lol")
    cs2_p = generate_esports("cs2")
    val_p = generate_esports("valorant")
    msg = format_daily_predictions(
        [], [], lol_p,
        esport_predictions={"cs2": cs2_p, "valorant": val_p},
    )
    await _send(update, msg)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_stats_message(), parse_mode="Markdown")


async def cmd_verificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Verificando resultados...")
    count = verify_results()
    if count:
        stats   = get_accuracy_stats()
        total_ok  = sum(s["monthly"]["correct"] for s in stats.values())
        total_all = sum(s["monthly"]["total"]   for s in stats.values())
        acc = round(total_ok / total_all * 100, 1) if total_all else 0
        await update.message.reply_text(
            f"✅ *{count}* predicciones verificadas\n"
            f"📊 Precisión del mes: *{acc}%* ({total_ok}/{total_all})\n"
            f"🧠 _Pesos del algoritmo actualizados_",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "ℹ️ Sin resultados nuevos para verificar.\n"
            "Los partidos aún no han terminado o ya fueron procesados."
        )


# ──────────────────────────────────────────────────────────────
#  SCHEDULER (envíos automáticos)
# ──────────────────────────────────────────────────────────────

async def scheduled_send(context: ContextTypes.DEFAULT_TYPE):
    logger.info("⏰ Envío automático")
    verify_results()
    football = generate_football()
    nba_p    = generate_nba()
    lol_p    = generate_esports("lol")
    cs2_p    = generate_esports("cs2")
    msg = format_daily_predictions(
        football, nba_p, lol_p,
        esport_predictions={"cs2": cs2_p},
    )
    await _send(context, msg, is_ctx=True)


async def scheduled_verify(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔍 Verificación nocturna")
    count = verify_results()
    if count:
        stats   = get_accuracy_stats()
        total_ok  = sum(s["monthly"]["correct"] for s in stats.values())
        total_all = sum(s["monthly"]["total"]   for s in stats.values())
        acc = round(total_ok / total_all * 100, 1) if total_all else 0
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"📊 *Verificación nocturna*\n\n"
                f"✅ {count} predicciones verificadas\n"
                f"🎯 Precisión del mes: *{acc}%*\n"
                f"🧠 _Pesos actualizados automáticamente_"
            ),
            parse_mode="Markdown",
        )


# ──────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("🏆 Bot de Pronósticos con IA — Groq Llama 3.1 70B")
    print("=" * 55)
    print(f"📱 Chat ID:  {CHAT_ID}")
    print(f"⏰ Envío:    {SCHEDULE_HOUR}:{SCHEDULE_MINUTE:02d} ({TIMEZONE})")
    print(f"⚽ Fútbol:   {', '.join(FOOTBALL_LEAGUES.keys())} + CONMEBOL")
    print(f"🏀 NBA:      Activo")
    print(f"🎮 Esports: LoL · CS2 · Valorant · Dota2")
    print(f"🤖 IA:      Groq Llama 3.1 70B (gratis)")
    print("=" * 55)
    print("Comandos disponibles:")
    print("  /pronosticos /futbol /nba /lol /cs2 /valorant /esports")
    print("  /stats /verificar")
    print("=" * 55)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Comandos
    handlers = [
        ("start",        cmd_start),
        ("pronosticos",  cmd_pronosticos),
        ("futbol",       cmd_futbol),
        ("nba",          cmd_nba),
        ("lol",          cmd_lol),
        ("cs2",          cmd_cs2),
        ("valorant",     cmd_valorant),
        ("esports",      cmd_esports),
        ("stats",        cmd_stats),
        ("verificar",    cmd_verificar),
    ]
    for name, fn in handlers:
        app.add_handler(CommandHandler(name, fn))

    # Scheduler
    jq = app.job_queue
    if jq:
        import pytz
        from datetime import time as dt_time
        tz = pytz.timezone(TIMEZONE)
        jq.run_daily(
            scheduled_send,
            time=dt_time(SCHEDULE_HOUR, SCHEDULE_MINUTE, tzinfo=tz),
        )
        jq.run_daily(
            scheduled_verify,
            time=dt_time(23, 0, tzinfo=tz),
        )
        print(f"✅ Scheduler: pronósticos {SCHEDULE_HOUR}:00 · verificación 23:00")
    else:
        print("⚠️ JobQueue no disponible — instala: pip install 'python-telegram-bot[job-queue]'")

    print("\n🚀 Bot corriendo...\n")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()