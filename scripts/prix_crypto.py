# Cours de cryptomonnaies via l'API publique de CoinGecko.
# ARGS : identifiants CoinGecko (bitcoin, ethereum, solana, ...)
from pyodide.http import pyfetch

ids = [a.lower() for a in ARGS] or ["bitcoin", "ethereum", "solana"]
url = (
    "https://api.coingecko.com/api/v3/simple/price"
    f"?ids={','.join(ids)}&vs_currencies=chf,usd&include_24hr_change=true"
)
r = await pyfetch(url)
data = await r.json()

if not data:
    print("Aucun résultat. Vérifie les identifiants (ex. bitcoin, ethereum, solana).")
for coin in ids:
    d = data.get(coin)
    if not d:
        print(f"{coin} : introuvable")
        continue
    change = d.get("chf_24h_change") or 0
    arrow = "▲" if change >= 0 else "▼"
    print(f"{coin} : {d['chf']:,.2f} CHF | {d['usd']:,.2f} USD | {arrow} {change:+.2f} % sur 24 h".replace(",", "'"))
