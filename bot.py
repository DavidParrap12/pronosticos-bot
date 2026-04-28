import requests
import time
from telegram import Bot
from apscheduler.schedulers.blocking import BlockingScheduler
from config import TELEGRAM_TOKEN, CHAT_ID, RAPIDAPI_KEY, STADIUM_DELAY, TEAM_ID

bot = Bot(token=TELEGRAM_TOKEN)
goles_notificados = set()

def obtener_partido_en_vivo():
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    params = {"live": "all", "team": TEAM_ID}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if data["results"] > 0:
        return data["response"][0]
    return None

def obtener_partido_en_vivo():
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    params = {"live": "all", "team": TEAM_ID}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    print(data)  # <- agrega esta línea
    
    if data.get("results", 0) > 0:
        return data["response"][0]
    return None

def revisar_goles():
    partido = obtener_partido_en_vivo()
    
    if not partido:
        return  # No hay partido en vivo
    
    fixture_id = partido["fixture"]["id"]
    goles = partido["goals"]
    eventos = partido["events"] if "events" in partido else []
    
    for evento in eventos:
        evento_id = f"{fixture_id}_{evento['time']['elapsed']}_{evento['type']}"
        
        if evento["type"] == "Goal" and evento_id not in goles_notificados:
            goles_notificados.add(evento_id)
            equipo = evento["team"]["name"]
            jugador = evento["player"]["name"]
            minuto = evento["time"]["elapsed"]
            
            # Primera alerta — inmediata
            bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    f"⚽ *GOL de {equipo}!*\n"
                    f"👤 {jugador} — min {minuto}'\n"
                    f"🔊 El estadio lo anunciará en ~{STADIUM_DELAY} segundos..."
                ),
                parse_mode="Markdown"
            )
            
            # Segunda alerta — cuando el estadio debería anunciar
            time.sleep(STADIUM_DELAY)
            bot.send_message(
                chat_id=CHAT_ID,
                text="🎶 ¡Ya debería sonar el jingle en el estadio!"
            )

scheduler = BlockingScheduler()
scheduler.add_job(revisar_goles, "interval", seconds=10)

print("Bot corriendo... esperando goles 🏟️")
scheduler.start()