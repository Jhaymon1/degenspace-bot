import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PAPERDEX_URL = os.getenv("PAPERDEX_URL")

DEXSCREENER_BASE = "https://api.dexscreener.com"
ALERT_CHECK_INTERVAL = 60  # seconds between price alert checks
SLIPPAGE_MIN = 0.005
SLIPPAGE_MAX = 0.025

CHAIN_FEES = {
    "solana": 0.001,
    "ethereum": 0.50,
    "bsc": 0.10,
    "base": 0.10,
    "arbitrum": 0.10,
    "avalanche": 0.10,
}

CHAIN_DISPLAY = {
    "solana": "◎ Solana",
    "ethereum": "⟠ Ethereum", 
    "bsc": "🟡 BSC",
    "base": "🔵 Base",
    "arbitrum": "🔷 Arbitrum",
    "avalanche": "🔺 Avalanche",
}
