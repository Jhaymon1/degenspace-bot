import os
from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Set it in Render Dashboard → Environment."
        )
    return val


BOT_TOKEN = _require_env("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = _require_env("WEBHOOK_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PAPERDEX_URL = os.getenv("PAPERDEX_URL", "")

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
