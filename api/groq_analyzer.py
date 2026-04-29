"""
api/groq_analyzer.py

Analizador de partidos con IA usando Groq (GRATIS).
Llama 3.1 70B — 14,400 requests/día en el tier gratuito.

Registro: https://console.groq.com (solo email, sin tarjeta)
"""
import json
import logging
import requests
from api import cache
from config import GROQ_API_KEY  # Agregar esta línea a config.py

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL    = "llama-3.3-70b-versatile"  # Mejor calidad gratis


# ──────────────────────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────────────────────

def analyze_match(
    home_team: str,
    away_team: str,
    league: str,
    sport: str,
    context: dict,        # Datos que ya tienes de ESPN/TheSportsDB
) -> dict:
    """
    Manda los datos del partido a Groq y devuelve un análisis completo.

    Args:
        home_team:  Equipo local
        away_team:  Equipo visitante
        league:     Nombre de la liga/copa
        sport:      'football' | 'basketball' | 'lol'
        context:    Dict con todos los datos disponibles del partido

    Returns:
        {
          'predicted_winner': str,
          'confidence': float,          # 50-90
          'pick': str,                  # Mercado recomendado
          'pick_odds': str,             # Cuota estimada
          'analysis': str,              # Razones legibles
          'btts': str,                  # 'Sí' | 'No' (fútbol)
          'over_under': str,            # 'Over 2.5' | 'Under 2.5' (fútbol)
          'raw': dict,                  # JSON completo del modelo
        }
    """
    # Caché 4h para no gastar requests repetidos del mismo partido
    cache_key = {"home": home_team, "away": away_team, "league": league}
    cached = cache.get("groq_analysis", cache_key, ttl=14400)
    if cached:
        logger.info(f"[Groq] Cache hit: {home_team} vs {away_team}")
        return cached

    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY no configurado. Agrega tu key en config.py")
        return _fallback_analysis(home_team, away_team)

    prompt = _build_prompt(home_team, away_team, league, sport, context)

    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Eres un analista deportivo experto en fútbol sudamericano, "
                            "NBA y esports. Analizas partidos con datos estadísticos reales "
                            "y produces pronósticos con fundamento. Respondes SOLO en JSON "
                            "válido, sin texto extra, sin markdown, sin explicaciones fuera "
                            "del JSON. Todos los valores numéricos deben ser números, no strings."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,     # Baja para respuestas más consistentes
                "max_tokens": 600,
                "response_format": {"type": "json_object"},
            },
            timeout=20,
        )

        response.raise_for_status()
        data = response.json()
        raw_text = data["choices"][0]["message"]["content"]
        result = json.loads(raw_text)

        # Normalizar y validar campos
        analysis = _normalize(result, home_team, away_team)
        cache.set("groq_analysis", cache_key, analysis)
        logger.info(
            f"[Groq ✓] {home_team} vs {away_team} → "
            f"{analysis['predicted_winner']} ({analysis['confidence']}%)"
        )
        return analysis

    except requests.exceptions.Timeout:
        logger.error("[Groq] Timeout — usando fallback")
        return _fallback_analysis(home_team, away_team)
    except Exception as e:
        logger.error(f"[Groq] Error: {e}")
        return _fallback_analysis(home_team, away_team)


# ──────────────────────────────────────────────────────────────
#  CONSTRUCCIÓN DEL PROMPT
# ──────────────────────────────────────────────────────────────

def _build_prompt(
    home_team: str,
    away_team: str,
    league: str,
    sport: str,
    ctx: dict,
) -> str:
    """
    Construye el prompt con todos los datos disponibles.
    Cuantos más datos en ctx, mejor el análisis.
    """

    # Datos que pueden venir de ESPN / TheSportsDB
    home_form      = ctx.get("home_form", "Sin datos")
    away_form      = ctx.get("away_form", "Sin datos")
    home_position  = ctx.get("home_position", "Sin datos")
    away_position  = ctx.get("away_position", "Sin datos")
    h2h            = ctx.get("h2h", "Sin enfrentamientos recientes")
    home_goals_avg = ctx.get("home_goals_avg", "?")
    away_goals_avg = ctx.get("away_goals_avg", "?")
    home_conceded  = ctx.get("home_conceded_avg", "?")
    away_conceded  = ctx.get("away_conceded_avg", "?")
    injuries       = ctx.get("injuries", "Sin información")
    venue          = ctx.get("venue", "Estadio local")
    altitude       = ctx.get("altitude_m", None)

    altitude_note = f"Altitud del estadio: {altitude} msnm (factor importante)" if altitude else ""

    if sport == "football":
        markets_req = (
            '"predicted_winner": "nombre del equipo ganador",'
            '"confidence": número entre 52 y 88,'
            '"pick": "mercado más recomendado (ej: Victoria X, BTTS Sí, Over 2.5)",'
            '"pick_odds": "cuota estimada como string (ej: 1.75)",'
            '"btts": "Sí o No",'
            '"over_under": "Over 2.5 o Under 2.5",'
            '"btts_confidence": número,'
            '"ou_confidence": número,'
            '"analysis": "análisis en español de 2-3 oraciones con las razones clave",'
            '"key_factors": ["factor1", "factor2", "factor3"]'
        )
    elif sport == "nba":
        markets_req = (
            '"predicted_winner": "nombre del equipo",'
            '"confidence": número entre 52 y 85,'
            '"pick": "mercado recomendado (ej: Victoria X, Over 215.5)",'
            '"pick_odds": "cuota estimada",'
            '"over_under_pts": "Over o Under con la línea (ej: Over 218.5)",'
            '"spread_pick": "equipo con spread (ej: Lakers -4.5)",'
            '"analysis": "análisis en español de 2-3 oraciones",'
            '"key_factors": ["factor1", "factor2", "factor3"]'
        )
    else:
        markets_req = (
            '"predicted_winner": "nombre del equipo",'
            '"confidence": número entre 52 y 80,'
            '"pick": "Victoria directa de X",'
            '"pick_odds": "cuota estimada",'
            '"analysis": "análisis en español de 2 oraciones",'
            '"key_factors": ["factor1", "factor2"]'
        )

    return f"""Analiza este partido y responde SOLO con un JSON válido con exactamente estos campos:

PARTIDO: {home_team} vs {away_team}
COMPETICIÓN: {league}
DEPORTE: {sport}

DATOS DISPONIBLES:
- Forma reciente {home_team}: {home_form}
- Forma reciente {away_team}: {away_form}
- Posición en tabla {home_team}: {home_position}
- Posición en tabla {away_team}: {away_position}
- Promedio goles/partido {home_team}: {home_goals_avg} (recibe {home_conceded})
- Promedio goles/partido {away_team}: {away_goals_avg} (recibe {away_conceded})
- Enfrentamientos directos: {h2h}
- Bajas/lesiones: {injuries}
- Estadio: {venue}
{altitude_note}

RESPONDE EXACTAMENTE CON ESTE JSON (sin texto extra):
{{{markets_req}}}"""


# ──────────────────────────────────────────────────────────────
#  NORMALIZACIÓN Y FALLBACK
# ──────────────────────────────────────────────────────────────

def _normalize(raw: dict, home: str, away: str) -> dict:
    """Asegura que todos los campos necesarios existan y tengan tipos correctos."""
    return {
        "predicted_winner":  raw.get("predicted_winner", home),
        "confidence":        float(raw.get("confidence", 55)),
        "pick":              raw.get("pick", f"Victoria {home}"),
        "pick_odds":         str(raw.get("pick_odds", "1.75")),
        "btts":              raw.get("btts", "No definido"),
        "over_under":        raw.get("over_under", "Under 2.5"),
        "btts_confidence":   float(raw.get("btts_confidence", 55)),
        "ou_confidence":     float(raw.get("ou_confidence", 55)),
        "over_under_pts":    raw.get("over_under_pts", ""),
        "spread_pick":       raw.get("spread_pick", ""),
        "analysis":          raw.get("analysis", "Sin análisis disponible."),
        "key_factors":       raw.get("key_factors", []),
        "raw":               raw,
    }


def _fallback_analysis(home: str, away: str) -> dict:
    """Respuesta vacía cuando Groq no está disponible."""
    return {
        "predicted_winner": home,
        "confidence": 52.0,
        "pick": f"Victoria {home}",
        "pick_odds": "1.70",
        "btts": "No definido",
        "over_under": "Under 2.5",
        "btts_confidence": 52.0,
        "ou_confidence": 52.0,
        "analysis": "Análisis IA no disponible (sin conexión a Groq).",
        "key_factors": ["Ventaja local"],
        "raw": {},
    }