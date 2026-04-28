import os

# ============================================================
# Configuración Bot Original (Goles en Vivo)
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8573366278:AAG1yg_Dh9qbVB8rgg0lSi0vnw4-qzKI7dw")
CHAT_ID = os.getenv("CHAT_ID", "1485084567")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "1f4004ebf3msh9220152d426f303p17386fjsn25cdfcef0730")
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
STADIUM_DELAY = 55
TEAM_ID = 1141  # Deportes Tolima

# ============================================================
# Configuración Bot de Pronósticos
# ============================================================

# TheSportsDB — API gratuita (key de prueba)
THESPORTSDB_KEY = "3"
THESPORTSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{THESPORTSDB_KEY}"

# PandaScore — API gratuita para esports
PANDASCORE_TOKEN = os.getenv("PANDASCORE_TOKEN", "bDkJQyPMExD3AttJV2hdpiYaPK0mXevDCUKevEo8qIx1kGo1E8A")
PANDASCORE_BASE = "https://api.pandascore.co"

# ============================================================
# Ligas a monitorear
# ============================================================
FOOTBALL_LEAGUES = {
    "Premier League": 4328,
    "La Liga": 4335,
    "Champions League": 4480,
    "Serie A": 4332,
    "Liga BetPlay": 4346,
}
# Copa Libertadores y Sudamericana se obtienen de API-Football (api/conmebol.py)

NBA_LEAGUE = {
    "NBA": 4387,
}

# ============================================================
# Temporadas actuales
# ============================================================
FOOTBALL_SEASONS = {
    4328: "2025-2026",   # Premier League
    4335: "2025-2026",   # La Liga
    4480: "2025-2026",   # Champions League
    4332: "2025-2026",   # Serie A
    4346: "2026",        # Liga BetPlay
}

NBA_SEASON = "2025-2026"

# ============================================================
# Horario de envío automático
# ============================================================
SCHEDULE_HOUR = 8       # 8:00 AM
SCHEDULE_MINUTE = 0
TIMEZONE = "America/Bogota"

# ============================================================
# Caché TTL (en segundos)
# ============================================================
CACHE_TTL_EVENTS = 1800       # 30 minutos
CACHE_TTL_RESULTS = 3600      # 1 hora
CACHE_TTL_TABLE = 21600       # 6 horas

# ============================================================
# Predictor — Pesos iniciales (se auto-ajustan)
# ============================================================
INITIAL_WEIGHTS_FOOTBALL = {
    "table_position": 0.25,
    "recent_form": 0.25,
    "home_advantage": 0.15,
    "head_to_head": 0.20,
    "goals_form": 0.15,
}

INITIAL_WEIGHTS_NBA = {
    "record": 0.25,
    "recent_form": 0.30,
    "head_to_head": 0.20,
    "points_avg": 0.25,
}

INITIAL_WEIGHTS_LOL = {
    "win_rate": 0.30,
    "tournament_position": 0.25,
    "head_to_head": 0.25,
    "side_preference": 0.20,
}