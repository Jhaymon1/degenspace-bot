from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY, CHAIN_FEES

_supabase_client = None


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "Supabase env vars missing. "
                "Set SUPABASE_URL and SUPABASE_KEY in Render Environment."
            )
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


class _SupabaseProxy:
    """Forwards all attribute access to the lazily-initialised Supabase client."""

    def __getattr__(self, name):
        return getattr(_get_supabase(), name)


supabase = _SupabaseProxy()


def get_telegram_user(telegram_id: int):
    result = supabase.table("telegram_users")\
        .select("*, profiles(display_name)")\
        .eq("telegram_id", telegram_id)\
        .single()\
        .execute()
    return result.data if result.data else None


def get_portfolio(user_id: str):
    result = supabase.table("portfolios")\
        .select("*")\
        .eq("user_id", user_id)\
        .single()\
        .execute()
    return result.data if result.data else None


def get_holdings(user_id: str):
    result = supabase.table("holdings")\
        .select("*")\
        .eq("user_id", user_id)\
        .execute()
    return result.data if result.data else []


def get_trades(user_id: str, limit: int = 10):
    result = supabase.table("trades")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("timestamp", desc=True)\
        .limit(limit)\
        .execute()
    return result.data if result.data else []


def get_session(telegram_id: int):
    result = supabase.table("bot_sessions")\
        .select("*")\
        .eq("telegram_id", telegram_id)\
        .execute()
    if result.data:
        return result.data[0]
    # Create new session
    supabase.table("bot_sessions").insert({
        "telegram_id": telegram_id,
        "state": "idle",
        "temp_data": {}
    }).execute()
    return {"telegram_id": telegram_id, "state": "idle", "temp_data": {}}


def set_session(telegram_id: int, state: str, temp_data: dict | None = None):
    if temp_data is None:
        temp_data = {}
    supabase.table("bot_sessions").upsert({
        "telegram_id": telegram_id,
        "state": state,
        "temp_data": temp_data,
        "updated_at": "now()"
    }).execute()


def execute_buy(user_id: str, token_data: dict, amount_usd: float):
    import random
    
    slippage = round(random.uniform(0.005, 0.025), 4)
    chain = token_data.get("chainId", "solana")
    fee = CHAIN_FEES.get(chain, 0.10)
    
    price = float(token_data.get("priceUsd", 0))
    if price <= 0:
        return None, "Invalid token price"
    
    effective_price = price * (1 + slippage)
    total_cost = amount_usd + fee
    tokens_received = amount_usd / effective_price
    
    # Get current portfolio
    portfolio = get_portfolio(user_id)
    if not portfolio:
        return None, "Portfolio not found"
    
    if portfolio["virtual_balance_usd"] < total_cost:
        return None, "Insufficient balance"
    
    token_address = token_data.get("baseToken", {}).get("address", "")
    token_symbol = token_data.get("baseToken", {}).get("symbol", "")
    token_name = token_data.get("baseToken", {}).get("name", "")
    
    # Deduct from portfolio
    new_balance = portfolio["virtual_balance_usd"] - total_cost
    supabase.table("portfolios")\
        .update({"virtual_balance_usd": new_balance})\
        .eq("user_id", user_id)\
        .execute()
    
    # Check existing holding
    existing = supabase.table("holdings")\
        .select("*")\
        .eq("user_id", user_id)\
        .eq("token_address", token_address)\
        .eq("chain_id", chain)\
        .execute()
    
    if existing.data:
        h = existing.data[0]
        new_amount = h["amount_held"] + tokens_received
        new_avg = ((h["amount_held"] * h["avg_buy_price_usd"]) + 
                   (tokens_received * effective_price)) / new_amount
        supabase.table("holdings")\
            .update({
                "amount_held": new_amount,
                "avg_buy_price_usd": new_avg,
                "last_updated": "now()"
            })\
            .eq("id", h["id"])\
            .execute()
    else:
        supabase.table("holdings").insert({
            "user_id": user_id,
            "token_address": token_address,
            "chain_id": chain,
            "token_symbol": token_symbol,
            "token_name": token_name,
            "amount_held": tokens_received,
            "avg_buy_price_usd": effective_price,
        }).execute()
    
    # Log trade
    supabase.table("trades").insert({
        "user_id": user_id,
        "token_address": token_address,
        "chain_id": chain,
        "token_symbol": token_symbol,
        "token_name": token_name,
        "trade_type": "BUY",
        "amount_usd": amount_usd,
        "token_amount": tokens_received,
        "price_at_trade": effective_price,
        "slippage_applied": slippage,
        "fee_applied": fee,
        "entry_price": price,
    }).execute()
    
    # Price snapshot
    supabase.table("price_snapshots").insert({
        "token_address": token_address,
        "chain_id": chain,
        "token_symbol": token_symbol,
        "price_usd": price,
        "volume_24h": token_data.get("volume", {}).get("h24", 0),
        "price_change_24h": token_data.get("priceChange", {}).get("h24", 0),
        "liquidity_usd": token_data.get("liquidity", {}).get("usd", 0),
    }).execute()
    
    return {
        "tokens_received": tokens_received,
        "effective_price": effective_price,
        "slippage": slippage * 100,
        "fee": fee,
        "total_cost": total_cost,
        "new_balance": new_balance,
        "token_symbol": token_symbol,
    }, None


def execute_sell(user_id: str, holding: dict, sell_percent: float, current_price: float):
    import random
    
    slippage = round(random.uniform(0.005, 0.025), 4)
    chain = holding.get("chain_id", "solana")
    fee = CHAIN_FEES.get(chain, 0.10)
    
    tokens_to_sell = holding["amount_held"] * sell_percent
    gross_proceeds = tokens_to_sell * current_price
    net_proceeds = gross_proceeds * (1 - slippage) - fee
    
    if net_proceeds <= 0:
        return None, "Proceeds too small after fees"
    
    portfolio = get_portfolio(user_id)
    new_balance = portfolio["virtual_balance_usd"] + net_proceeds
    
    # Update portfolio balance
    supabase.table("portfolios")\
        .update({"virtual_balance_usd": new_balance})\
        .eq("user_id", user_id)\
        .execute()
    
    # Update or delete holding
    if sell_percent >= 1.0:
        supabase.table("holdings")\
            .delete()\
            .eq("id", holding["id"])\
            .execute()
    else:
        supabase.table("holdings")\
            .update({
                "amount_held": holding["amount_held"] - tokens_to_sell,
                "last_updated": "now()"
            })\
            .eq("id", holding["id"])\
            .execute()
    
    # PnL calculation
    pnl = (current_price - holding["avg_buy_price_usd"]) * tokens_to_sell
    
    # Log trade
    supabase.table("trades").insert({
        "user_id": user_id,
        "token_address": holding["token_address"],
        "chain_id": chain,
        "token_symbol": holding["token_symbol"],
        "token_name": holding["token_name"],
        "trade_type": "SELL",
        "amount_usd": net_proceeds,
        "token_amount": tokens_to_sell,
        "price_at_trade": current_price,
        "slippage_applied": slippage,
        "fee_applied": fee,
        "entry_price": holding["avg_buy_price_usd"],
    }).execute()
    
    return {
        "tokens_sold": tokens_to_sell,
        "net_proceeds": net_proceeds,
        "pnl": pnl,
        "slippage": slippage * 100,
        "fee": fee,
        "new_balance": new_balance,
        "token_symbol": holding["token_symbol"],
    }, None


def get_leaderboard(limit: int = 10):
    portfolios = supabase.table("portfolios")\
        .select("user_id, starting_balance, virtual_balance_usd")\
        .execute()
    
    if not portfolios.data:
        return []
    
    results = []
    for p in portfolios.data:
        profile = supabase.table("profiles")\
            .select("display_name")\
            .eq("id", p["user_id"])\
            .execute()
        
        name = "Trader"
        if profile.data and profile.data[0].get("display_name"):
            name = profile.data[0]["display_name"]
        
        gain_pct = ((p["virtual_balance_usd"] - p["starting_balance"]) 
                    / p["starting_balance"] * 100)
        
        results.append({
            "display_name": name,
            "starting_balance": p["starting_balance"],
            "current_value": p["virtual_balance_usd"],
            "gain_pct": gain_pct,
        })
    
    results.sort(key=lambda x: x["gain_pct"], reverse=True)
    return results[:limit]
