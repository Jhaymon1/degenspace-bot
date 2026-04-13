import httpx
from config import DEXSCREENER_BASE


async def get_trending_tokens(limit: int = 10):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DEXSCREENER_BASE}/token-boosts/top/v1",
            timeout=10
        )
        if resp.status_code != 200:
            return []
        
        boosts = resp.json()
        if not isinstance(boosts, list):
            return []
        
        results = []
        for boost in boosts[:limit]:
            token_addr = boost.get("tokenAddress", "")
            chain = boost.get("chainId", "")
            if not token_addr:
                continue
            
            pair_resp = await client.get(
                f"{DEXSCREENER_BASE}/latest/dex/tokens/{token_addr}",
                timeout=10
            )
            if pair_resp.status_code == 200:
                data = pair_resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    results.append(pairs[0])
            
            if len(results) >= limit:
                break
        
        return results


async def search_token(query: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DEXSCREENER_BASE}/latest/dex/search?q={query}",
            timeout=10
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("pairs", [])[:5]


async def get_token_price(token_address: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DEXSCREENER_BASE}/latest/dex/tokens/{token_address}",
            timeout=10
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        pairs = data.get("pairs", [])
        return pairs[0] if pairs else None


def format_price(price_str: str) -> str:
    try:
        price = float(price_str)
        if price >= 1:
            return f"${price:,.4f}"
        elif price >= 0.001:
            return f"${price:.6f}"
        else:
            # Count leading zeros
            s = f"{price:.20f}".split(".")[1]
            zeros = len(s) - len(s.lstrip("0"))
            sig = s.lstrip("0")[:4]
            return f"$0.0{zeros}{sig}"
    except:
        return f"${price_str}"


def format_large(val) -> str:
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"${v/1_000_000:.1f}M"
        elif v >= 1_000:
            return f"${v/1_000:.1f}K"
        else:
            return f"${v:.2f}"
    except:
        return "$—"
