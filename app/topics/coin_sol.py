"""/sol: SOL on its own page (see _coin_page.py; data from btc_cycles' background fill, script static/topics/coin.js)."""
from ._coin_page import page

TOPIC, ENDPOINTS, SOURCES, NOTES = page("SOL", order=13)
