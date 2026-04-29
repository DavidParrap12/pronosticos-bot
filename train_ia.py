"""
Entrenador: Analiza partidos YA JUGADOS para calibrar la IA.
Compara predicción vs resultado real y guarda estadísticas.
"""
import os, json, logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from api import espn
from api.groq_analyzer import analyze_match

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

RESULTS_FILE = Path("data/training_results.json")


def load_results():
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"matches": [], "stats": {"total": 0, "correct": 0, "accuracy": 0}}


def save_results(data):
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_finished_matches():
    """Obtiene partidos terminados de hoy de ESPN."""
    import requests
    
    finished = []
    
    # Ligas ESPN a revisar
    leagues = {
        "Copa Libertadores": {"sport": "soccer", "league": "conmebol.libertadores"},
        "Copa Sudamericana": {"sport": "soccer", "league": "conmebol.sudamericana"},
        "Champions League": {"sport": "soccer", "league": "uefa.champions"},
        "Premier League": {"sport": "soccer", "league": "eng.1"},
        "La Liga": {"sport": "soccer", "league": "esp.1"},
        "Serie A": {"sport": "soccer", "league": "ita.1"},
        "Liga BetPlay": {"sport": "soccer", "league": "col.1"},
        "NBA": {"sport": "basketball", "league": "nba"},
    }
    
    # Cubrir últimos 5 días
    today = datetime.now()
    dates = [(today - timedelta(days=d)).strftime("%Y%m%d") for d in range(5)]
    
    for league_name, info in leagues.items():
        sport = info["sport"]
        league_slug = info["league"]
        
        for date_str in dates:
            try:
                if sport == "soccer":
                    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={date_str}"
                else:
                    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league_slug}/scoreboard?dates={date_str}"
                
                r = requests.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                    
                data = r.json()
                events = data.get("events", [])
                
                for ev in events:
                    status = ev.get("status", {}).get("type", {}).get("name", "")
                    if status != "STATUS_FINAL":
                        continue
                    
                    comps = ev.get("competitions", [{}])[0]
                    teams = comps.get("competitors", [])
                    if len(teams) < 2:
                        continue
                    
                    home_team = away_team = None
                    home_score = away_score = 0
                    
                    for t in teams:
                        name = t.get("team", {}).get("displayName", "")
                        score = int(t.get("score", "0"))
                        if t.get("homeAway") == "home":
                            home_team = name
                            home_score = score
                        else:
                            away_team = name
                            away_score = score
                    
                    if home_team and away_team:
                        finished.append({
                            "home_team": home_team,
                            "away_team": away_team,
                            "home_score": home_score,
                            "away_score": away_score,
                            "league": league_name,
                            "sport": sport,
                            "date": date_str,
                            "event_name": ev.get("name", ""),
                        })
            except Exception as e:
                logger.error(f"  Error {league_name}: {e}")
    
    return finished


def analyze_finished_match(match):
    """Analiza un partido terminado con Groq y compara."""
    home = match["home_team"]
    away = match["away_team"]
    league = match["league"]
    sport = match["sport"]
    hs = match["home_score"]
    aws = match["away_score"]
    
    # Resultado real
    if hs > aws:
        actual_winner = home
    elif aws > hs:
        actual_winner = away
    else:
        actual_winner = "Empate"
    
    total_goals = hs + aws
    btts_actual = "Sí" if hs > 0 and aws > 0 else "No"
    ou_actual = "Over 2.5" if total_goals > 2.5 else "Under 2.5"
    
    # Datos ESPN para contexto
    home_rec = espn.get_team_record(home, league)
    away_rec = espn.get_team_record(away, league)
    home_form = espn.get_team_form(home, league, last_n=5)
    away_form = espn.get_team_form(away, league, last_n=5)
    
    context = {
        "home_form": home_form.get("form_string", "Sin datos") if home_form else "Sin datos",
        "away_form": away_form.get("form_string", "Sin datos") if away_form else "Sin datos",
        "home_position": f"Récord: {home_rec.get('record_summary', 'N/A')}" if home_rec else "Sin datos",
        "away_position": f"Récord: {away_rec.get('record_summary', 'N/A')}" if away_rec else "Sin datos",
        "home_goals_avg": home_form.get("avg_goals_scored", 1.2) if home_form else 1.2,
        "away_goals_avg": away_form.get("avg_goals_scored", 1.2) if away_form else 1.2,
        "home_conceded_avg": home_form.get("avg_goals_conceded", 1.0) if home_form else 1.0,
        "away_conceded_avg": away_form.get("avg_goals_conceded", 1.0) if away_form else 1.0,
        "h2h": "Sin datos H2H",
        "injuries": "Sin información",
        "venue": f"Estadio de {home}",
    }
    
    sport_type = "football" if sport == "soccer" else "basketball"
    ai = analyze_match(home, away, league, sport_type, context)
    
    # Comparar
    predicted = ai["predicted_winner"]
    predicted_correct = (
        predicted.lower() in actual_winner.lower() or 
        actual_winner.lower() in predicted.lower()
    )
    
    ou_predicted = ai.get("over_under", "")
    btts_predicted = ai.get("btts", "")
    
    ou_correct = ou_predicted.lower().replace(" ", "") == ou_actual.lower().replace(" ", "") if ou_predicted else None
    btts_correct = btts_predicted.lower() == btts_actual.lower() if btts_predicted and btts_predicted != "No definido" else None
    
    return {
        "match": f"{home} {hs}-{aws} {away}",
        "league": league,
        "date": match["date"],
        "actual_winner": actual_winner,
        "predicted_winner": predicted,
        "confidence": ai["confidence"],
        "winner_correct": predicted_correct,
        "ou_actual": ou_actual,
        "ou_predicted": ou_predicted,
        "ou_correct": ou_correct,
        "btts_actual": btts_actual,
        "btts_predicted": btts_predicted,
        "btts_correct": btts_correct,
        "analysis": ai["analysis"],
        "pick": ai["pick"],
        "key_factors": ai.get("key_factors", []),
    }


def main():
    print("=" * 65)
    print("🧠 ENTRENADOR DE IA — Analizando partidos jugados")
    print("=" * 65)
    
    # 1. Obtener partidos terminados
    print("\n📡 Buscando partidos terminados en ESPN...")
    matches = get_finished_matches()
    print(f"   Encontrados: {len(matches)} partidos terminados\n")
    
    if not matches:
        print("❌ No hay partidos terminados para analizar")
        return
    
    # 2. Cargar resultados anteriores
    results = load_results()
    
    # 3. Analizar cada partido
    already_analyzed = {m["match"] for m in results["matches"]}
    new_analyses = 0
    correct_count = 0
    total_analyzed = 0
    
    for i, match in enumerate(matches):
        match_key = f"{match['home_team']} vs {match['away_team']} ({match['date']})"
        
        # Saltar si ya fue analizado
        result_str = f"{match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']}"
        if result_str in already_analyzed:
            print(f"  ⏭️  Ya analizado: {result_str}")
            continue
        
        print(f"\n{'─' * 55}")
        print(f"  [{i+1}/{len(matches)}] {match['league']}")
        print(f"  ⚽ {match['home_team']} {match['home_score']}-{match['away_score']} {match['away_team']}")
        
        try:
            analysis = analyze_finished_match(match)
            total_analyzed += 1
            new_analyses += 1
            
            # Mostrar resultado
            emoji = "✅" if analysis["winner_correct"] else "❌"
            print(f"  {emoji} Predicción: {analysis['predicted_winner']} ({analysis['confidence']}%)")
            print(f"     Real: {analysis['actual_winner']}")
            print(f"     🤖 {analysis['analysis'][:100]}...")
            
            if analysis.get("ou_correct") is not None:
                ou_emoji = "✅" if analysis["ou_correct"] else "❌"
                print(f"  {ou_emoji} O/U: Pred={analysis['ou_predicted']} | Real={analysis['ou_actual']}")
            
            if analysis.get("btts_correct") is not None:
                btts_emoji = "✅" if analysis["btts_correct"] else "❌"
                print(f"  {btts_emoji} BTTS: Pred={analysis['btts_predicted']} | Real={analysis['btts_actual']}")
            
            if analysis["winner_correct"]:
                correct_count += 1
            
            results["matches"].append(analysis)
            
        except Exception as e:
            print(f"  ⚠️ Error: {e}")
    
    # 4. Actualizar stats globales
    all_matches = results["matches"]
    total = len(all_matches)
    correct = sum(1 for m in all_matches if m.get("winner_correct"))
    
    ou_total = sum(1 for m in all_matches if m.get("ou_correct") is not None)
    ou_correct = sum(1 for m in all_matches if m.get("ou_correct") == True)
    
    btts_total = sum(1 for m in all_matches if m.get("btts_correct") is not None)
    btts_correct = sum(1 for m in all_matches if m.get("btts_correct") == True)
    
    results["stats"] = {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
        "ou_total": ou_total,
        "ou_correct": ou_correct,
        "ou_accuracy": round(ou_correct / ou_total * 100, 1) if ou_total > 0 else 0,
        "btts_total": btts_total,
        "btts_correct": btts_correct,
        "btts_accuracy": round(btts_correct / btts_total * 100, 1) if btts_total > 0 else 0,
        "last_updated": datetime.now().isoformat(),
    }
    
    save_results(results)
    
    # 5. Resumen
    print(f"\n{'=' * 65}")
    print(f"📊 RESUMEN DE ENTRENAMIENTO")
    print(f"{'=' * 65}")
    print(f"  Nuevos analizados hoy: {new_analyses}")
    print(f"  Sesión: {correct_count}/{total_analyzed} acertados ({correct_count/max(total_analyzed,1)*100:.0f}%)")
    print(f"\n  📈 STATS ACUMULADAS:")
    print(f"     Ganador:  {correct}/{total} = {results['stats']['accuracy']}%")
    if ou_total > 0:
        print(f"     Over/Under: {ou_correct}/{ou_total} = {results['stats']['ou_accuracy']}%")
    if btts_total > 0:
        print(f"     BTTS: {btts_correct}/{btts_total} = {results['stats']['btts_accuracy']}%")
    print(f"\n  💾 Datos guardados en: {RESULTS_FILE}")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
