from telegram.ext import Application
from database import supabase, get_telegram_user
from dexscreener import get_token_price, format_price
import logging

logger = logging.getLogger(__name__)


async def check_price_alerts(app: Application):
    """Runs every 60 seconds to check all active alerts"""
    try:
        alerts = supabase.table("price_alerts")\
            .select("*")\
            .eq("is_active", True)\
            .execute()
        
        if not alerts.data:
            return
        
        for alert in alerts.data:
            try:
                token_data = await get_token_price(alert["token_address"])
                if not token_data:
                    continue
                
                current_price = float(token_data.get("priceUsd", 0))
                last_price = float(alert.get("last_price") or current_price)
                
                if last_price == 0:
                    # Just update last price, no alert yet
                    supabase.table("price_alerts")\
                        .update({"last_price": current_price})\
                        .eq("id", alert["id"])\
                        .execute()
                    continue
                
                change_pct = ((current_price - last_price) / last_price) * 100
                threshold = float(alert.get("threshold_percent", 10))
                
                should_alert = False
                alert_msg = ""
                
                if alert["alert_type"] in ["PUMP", "BOTH"] and change_pct >= threshold:
                    should_alert = True
                    alert_msg = (
                        f"🚀 *PUMP ALERT!*\n\n"
                        f"*{alert['token_symbol']}* is up "
                        f"*+{change_pct:.1f}%*\n"
                        f"Price: {format_price(str(current_price))}\n"
                        f"From: {format_price(str(last_price))}"
                    )
                elif alert["alert_type"] in ["DUMP", "BOTH"] and change_pct <= -threshold:
                    should_alert = True
                    alert_msg = (
                        f"📉 *DUMP ALERT!*\n\n"
                        f"*{alert['token_symbol']}* is down "
                        f"*{change_pct:.1f}%*\n"
                        f"Price: {format_price(str(current_price))}\n"
                        f"From: {format_price(str(last_price))}"
                    )
                
                if should_alert:
                    await app.bot.send_message(
                        chat_id=alert["telegram_id"],
                        text=alert_msg,
                        parse_mode="Markdown"
                    )
                
                # Update last price
                supabase.table("price_alerts")\
                    .update({"last_price": current_price})\
                    .eq("id", alert["id"])\
                    .execute()
                    
            except Exception as e:
                logger.error(f"Alert check error for {alert.get('token_symbol')}: {e}")
                
    except Exception as e:
        logger.error(f"Alert job error: {e}")


async def add_alert(telegram_id: int, user_id: str, token_address: str, 
                    chain_id: str, token_symbol: str, threshold: float = 10.0) -> bool:
    try:
        token_data = await get_token_price(token_address)
        current_price = float(token_data.get("priceUsd", 0)) if token_data else 0
        
        supabase.table("price_alerts").upsert({
            "user_id": user_id,
            "telegram_id": telegram_id,
            "token_address": token_address,
            "chain_id": chain_id,
            "token_symbol": token_symbol,
            "alert_type": "BOTH",
            "threshold_percent": threshold,
            "last_price": current_price,
            "is_active": True,
        }).execute()
        return True
    except Exception as e:
        logger.error("add_alert error for %s: %s", token_symbol, e)
        return False
