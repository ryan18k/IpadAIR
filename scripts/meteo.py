# Météo actuelle et prévisions via Open-Meteo (gratuit, sans clé).
# ARGS : nom de la ville
from pyodide.http import pyfetch
from urllib.parse import quote

ville = " ".join(ARGS) or "Lausanne"
geo = await (await pyfetch(
    f"https://geocoding-api.open-meteo.com/v1/search?name={quote(ville)}&count=1&language=fr"
)).json()
if not geo.get("results"):
    raise SystemExit(f"Ville introuvable : {ville}")
lieu = geo["results"][0]

meteo = await (await pyfetch(
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={lieu['latitude']}&longitude={lieu['longitude']}"
    "&current=temperature_2m,apparent_temperature,precipitation,wind_speed_10m,weather_code"
    "&daily=temperature_2m_min,temperature_2m_max,precipitation_sum,weather_code"
    "&timezone=auto&forecast_days=3"
)).json()

CODES = {0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
         45: "brouillard", 48: "brouillard givrant", 51: "bruine légère", 53: "bruine", 55: "bruine forte",
         61: "pluie faible", 63: "pluie", 65: "forte pluie", 71: "neige faible", 73: "neige", 75: "forte neige",
         80: "averses", 81: "averses", 82: "fortes averses", 95: "orage", 96: "orage avec grêle", 99: "orage avec grêle"}

c = meteo["current"]
print(f"{lieu['name']} ({lieu.get('country', '')}) — maintenant : {c['temperature_2m']} °C "
      f"(ressenti {c['apparent_temperature']} °C), {CODES.get(c['weather_code'], 'temps variable')}, "
      f"vent {c['wind_speed_10m']} km/h")
d = meteo["daily"]
for i, jour in enumerate(d["time"]):
    print(f"{jour} : {d['temperature_2m_min'][i]} à {d['temperature_2m_max'][i]} °C, "
          f"{CODES.get(d['weather_code'][i], 'variable')}, pluie {d['precipitation_sum'][i]} mm")
