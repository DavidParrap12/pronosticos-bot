import requests
from datetime import datetime, timedelta

leagues = {
    "Libertadores": "conmebol.libertadores",
    "Sudamericana": "conmebol.sudamericana",
    "Champions": "uefa.champions",
    "Premier": "eng.1",
    "La Liga": "esp.1",
    "Serie A": "ita.1",
    "Bundesliga": "ger.1",
    "Ligue 1": "fra.1",
    "Liga BetPlay": "col.1",
    "Liga MX": "mex.1",
    "MLS": "usa.1",
    "Liga Argentina": "arg.1",
    "Brasileirão": "bra.1",
}
today = datetime.now()
total = 0
for d in range(8):  # última semana
    dt = (today - timedelta(days=d)).strftime("%Y%m%d")
    for name, slug in leagues.items():
        try:
            r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={dt}", timeout=10)
            evts = r.json().get("events", [])
            finished = [e for e in evts if e.get("status",{}).get("type",{}).get("name","") == "STATUS_FINAL"]
            if finished:
                print(f"{dt} | {name}: {len(finished)} terminados")
                total += len(finished)
                for e in finished[:3]:
                    c = e["competitions"][0]["competitors"]
                    ht = [t for t in c if t["homeAway"]=="home"][0]
                    at = [t for t in c if t["homeAway"]=="away"][0]
                    hn = ht["team"]["displayName"]
                    an = at["team"]["displayName"]
                    hs = ht["score"]
                    asc = at["score"]
                    print(f"    {hn} {hs}-{asc} {an}")
        except:
            pass

# NBA
for d in range(5):
    dt = (today - timedelta(days=d)).strftime("%Y%m%d")
    try:
        r = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={dt}", timeout=10)
        evts = r.json().get("events", [])
        finished = [e for e in evts if e.get("status",{}).get("type",{}).get("name","") == "STATUS_FINAL"]
        if finished:
            print(f"{dt} | NBA: {len(finished)} terminados")
            total += len(finished)
            for e in finished[:3]:
                c = e["competitions"][0]["competitors"]
                ht = [t for t in c if t["homeAway"]=="home"][0]
                at = [t for t in c if t["homeAway"]=="away"][0]
                print(f"    {ht['team']['displayName']} {ht['score']}-{at['score']} {at['team']['displayName']}")
    except:
        pass

print(f"\nTotal partidos terminados: {total}")
