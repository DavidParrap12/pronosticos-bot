"""
Test completo: ESPN + Groq IA — sin necesidad de Telegram.
Simula un análisis de partido real.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from api import espn
from api.groq_analyzer import analyze_match
import json

print("=" * 60)
print("TEST: ESPN + Groq IA")
print("=" * 60)

# Test 1: Datos ESPN
print("\n--- ESPN: Récord de equipos ---")
for team, league in [("Millonarios", "Copa Sudamericana"), ("São Paulo", "Copa Sudamericana"), ("New York Knicks", "NBA")]:
    rec = espn.get_team_record(team, league)
    if rec:
        print(f"  ✅ {team}: {rec.get('record_summary', 'N/A')}")
    else:
        print(f"  ❌ {team}: Sin datos")

# Test 2: Forma reciente
print("\n--- ESPN: Forma reciente ---")
form = espn.get_team_form("Millonarios", "Copa Sudamericana", last_n=5)
if form:
    print(f"  ✅ Millonarios forma: {form.get('form_string', 'N/A')} | GF: {form.get('avg_goals_scored', '?')}/p | GA: {form.get('avg_goals_conceded', '?')}/p")
else:
    print("  ❌ Sin datos de forma")

# Test 3: Groq IA
print("\n--- Groq IA: Análisis de partido ---")
context = {
    "home_form": "WDLWW",
    "away_form": "WWDLW",
    "home_position": "Récord: 1-0-1",
    "away_position": "Récord: 2-0-0",
    "home_goals_avg": 1.5,
    "away_goals_avg": 1.8,
    "home_conceded_avg": 0.8,
    "away_conceded_avg": 1.2,
    "h2h": "Millonarios 1-2 São Paulo | São Paulo 3-0 Millonarios",
    "injuries": "Sin información",
    "venue": "Estadio El Campín, Bogotá",
    "altitude_m": 2640,
}

ai = analyze_match("Millonarios", "São Paulo", "Copa Sudamericana", "football", context)

print(f"\n  🏆 Ganador predicho: {ai['predicted_winner']}")
print(f"  📊 Confianza: {ai['confidence']}%")
print(f"  📝 Análisis: {ai['analysis']}")
print(f"  💡 Pick: {ai['pick']} (cuota ~{ai['pick_odds']})")
print(f"  ⚽ Over/Under: {ai.get('over_under', 'N/A')}")
print(f"  🎯 BTTS: {ai.get('btts', 'N/A')}")
print(f"  🔑 Factores: {ai.get('key_factors', [])}")

print("\n" + "=" * 60)
if ai['confidence'] > 52 and ai['analysis'] != "Análisis IA no disponible (sin conexión a Groq).":
    print("🎉 ¡ÉXITO! Groq IA funciona correctamente")
else:
    print("❌ FALLO: La IA no respondió correctamente")
print("=" * 60)
