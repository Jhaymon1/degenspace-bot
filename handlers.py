from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    get_telegram_user, get_portfolio, get_holdings,
    get_trades, get_session, set_session,
    execute_buy, execute_sell, get_leaderboard, supabase
)
from dexscreener import (
    get_trending_tokens, search_token, 
    get_token_price, format_price, format_large
)
from config import PAPERDEX_URL, CHAIN_DISPLAY
import logging

logger = logging.getLogger(__name__)


# ─── /start ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    db_user = get_telegram_user(tg_user.id)
    
    if db_user and db_user.get("user_id"):
        portfolio = get_portfolio(db_user["user_id"])
        name = db_user.get("profiles", {})
        if isinstance(name, dict):
            name = name.get("display_name", tg_user.first_name)
        else:
            name = tg_user.first_name
            
        text = (
            f"👋 Welcome back, *{name}*!\n\n"
            f"Your portfolio is live and synced 🔄\n\n"
            f"💰 Balance: *${portfolio['virtual_balance_usd']:,.2f}*\n\n"
            f"What do you want to do?"
        )
        keyboard = main_menu_keyboard()
    else:
        text = (
            f"🚀 *Welcome to PaperDex Bot!*\n\n"
            f"Trade meme coins with virtual funds.\n"
            f"Real markets. Zero risk.\n\n"
            f"To get started, link your PaperDex account:\n\n"
            f"1️⃣ Open the app: {PAPERDEX_URL}\n"
            f"2️⃣ Sign up or log in\n"
            f"3️⃣ Come back and use /link to connect\n\n"
            f"Or use /link email password to connect now."
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🌐 Open PaperDex", url=PAPERDEX_URL)
        ]])
    
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=keyboard
    )


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Market", callback_data="menu_market"),
            InlineKeyboardButton("👛 Portfolio", callback_data="menu_portfolio"),
        ],
        [
            InlineKeyboardButton("💼 Holdings", callback_data="menu_holdings"),
            InlineKeyboardButton("🕐 History", callback_data="menu_history"),
        ],
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_leaderboard"),
            InlineKeyboardButton("🔔 Alerts", callback_data="menu_alerts"),
        ],
        [
            InlineKeyboardButton("🌐 Open App", url=PAPERDEX_URL),
        ]
    ])


# ─── /link ────────────────────────────────────────────────
async def link_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "📧 *Link your PaperDex account*\n\n"
            "Usage: `/link email@example.com yourpassword`\n\n"
            "Your credentials are used only to verify your account "
            "and are never stored by the bot.",
            parse_mode="Markdown"
        )
        return
    
    email = args[0]
    password = args[1]
    
    await update.message.reply_text("🔄 Linking your account...")
    
    try:
        auth_resp = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not auth_resp.user:
            await update.message.reply_text(
                "❌ Invalid email or password. Please try again."
            )
            return
        
        user_id = auth_resp.user.id
        tg_user = update.effective_user
        
        # Save telegram link
        supabase.table("telegram_users").upsert({
            "telegram_id": tg_user.id,
            "telegram_username": tg_user.username or "",
            "user_id": user_id,
        }).execute()
        
        # Get display name
        profile = supabase.table("profiles")\
            .select("display_name")\
            .eq("id", user_id)\
            .execute()
        
        name = profile.data[0]["display_name"] if profile.data else email.split("@")[0]
        portfolio = get_portfolio(user_id)
        
        await update.message.reply_text(
            f"✅ *Account linked successfully!*\n\n"
            f"👤 Trader: *{name}*\n"
            f"💰 Balance: *${portfolio['virtual_balance_usd']:,.2f}*\n"
            f"🚀 Starting balance: *${portfolio['starting_balance']:,.2f}*\n\n"
            f"Your web app and Telegram bot are now fully synced!",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        
        try:
            supabase.auth.sign_out()
        except Exception as e:
            logger.warning("sign_out failed (non-critical): %s", e)
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Link failed. Check your credentials and try again.\n"
            f"Error: {str(e)[:100]}"
        )


# ─── /market ──────────────────────────────────────────────
async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    await msg.reply_text("🔄 Fetching live markets...")
    
    tokens = await get_trending_tokens(10)
    
    if not tokens:
        await msg.reply_text("❌ Could not fetch market data. Try again.")
        return
    
    text = "🔥 *Trending Meme Coins*\n\n"
    
    for i, pair in enumerate(tokens[:10], 1):
        symbol = pair.get("baseToken", {}).get("symbol", "?")
        name = pair.get("baseToken", {}).get("name", "?")
        price = format_price(str(pair.get("priceUsd", "0")))
        change_24h = pair.get("priceChange", {}).get("h24", 0)
        volume = format_large(pair.get("volume", {}).get("h24", 0))
        liq = format_large(pair.get("liquidity", {}).get("usd", 0))
        chain = CHAIN_DISPLAY.get(pair.get("chainId", ""), pair.get("chainId", ""))
        
        arrow = "🟢" if float(change_24h or 0) >= 0 else "🔴"
        change_str = f"+{change_24h}%" if float(change_24h or 0) >= 0 else f"{change_24h}%"
        
        text += (
            f"{i}. *{symbol}* — {name}\n"
            f"   {chain} | {price} {arrow} {change_str}\n"
            f"   VOL {volume} | LIQ {liq}\n\n"
        )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Search Token", callback_data="action_search"),
            InlineKeyboardButton("🔄 Refresh", callback_data="menu_market"),
        ],
        [InlineKeyboardButton("« Back", callback_data="menu_main")]
    ])
    
    await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ─── /portfolio ───────────────────────────────────────────
async def portfolio_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    tg_user = update.effective_user
    db_user = get_telegram_user(tg_user.id)
    
    if not db_user or not db_user.get("user_id"):
        await msg.reply_text(
            "❌ Account not linked.\nUse /link email password to connect."
        )
        return
    
    user_id = db_user["user_id"]
    portfolio = get_portfolio(user_id)
    holdings = get_holdings(user_id)
    
    if not portfolio:
        await msg.reply_text("❌ Portfolio not found.")
        return
    
    # Calculate holdings value
    holdings_value = 0
    for h in holdings:
        token_data = await get_token_price(h["token_address"])
        if token_data:
            current_price = float(token_data.get("priceUsd", 0))
            holdings_value += h["amount_held"] * current_price
    
    total_value = portfolio["virtual_balance_usd"] + holdings_value
    pnl = total_value - portfolio["starting_balance"]
    pnl_pct = (pnl / portfolio["starting_balance"]) * 100
    
    pnl_emoji = "🚀" if pnl > 0 else "💀" if pnl < 0 else "🤝"
    pnl_sign = "+" if pnl >= 0 else ""
    
    profile = supabase.table("profiles")\
        .select("display_name")\
        .eq("id", user_id)\
        .execute()
    name = profile.data[0]["display_name"] if profile.data else "Trader"
    
    text = (
        f"👛 *{name}'s Portfolio*\n\n"
        f"💵 Cash Balance: *${portfolio['virtual_balance_usd']:,.2f}*\n"
        f"📦 Holdings Value: *${holdings_value:,.2f}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💼 Total Value: *${total_value:,.2f}*\n"
        f"📈 PnL: *{pnl_sign}${pnl:,.2f} ({pnl_sign}{pnl_pct:.1f}%)* {pnl_emoji}\n"
        f"🏦 Started: *${portfolio['starting_balance']:,.2f}*\n"
        f"🔄 Resets: *{portfolio.get('reset_count', 0)}*\n\n"
        f"_Synced with PaperDex web app_ 🔄"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💼 Holdings", callback_data="menu_holdings"),
            InlineKeyboardButton("📊 Market", callback_data="menu_market"),
        ],
        [InlineKeyboardButton("« Main Menu", callback_data="menu_main")]
    ])
    
    await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ─── /holdings ────────────────────────────────────────────
async def holdings_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    tg_user = update.effective_user
    db_user = get_telegram_user(tg_user.id)
    
    if not db_user or not db_user.get("user_id"):
        await msg.reply_text("❌ Use /link to connect your account.")
        return
    
    holdings = get_holdings(db_user["user_id"])
    
    if not holdings:
        await msg.reply_text(
            "📭 *No holdings yet*\n\n"
            "Use /market to find tokens and start trading!",
            parse_mode="Markdown"
        )
        return
    
    text = "💼 *Your Holdings*\n\n"
    buttons = []
    
    for h in holdings:
        token_data = await get_token_price(h["token_address"])
        current_price = float(token_data.get("priceUsd", 0)) if token_data else 0
        current_value = h["amount_held"] * current_price
        pnl = (current_price - h["avg_buy_price_usd"]) * h["amount_held"]
        pnl_pct = ((current_price - h["avg_buy_price_usd"]) / h["avg_buy_price_usd"] * 100) if h["avg_buy_price_usd"] > 0 else 0
        
        pnl_sign = "+" if pnl >= 0 else ""
        arrow = "📈" if pnl >= 0 else "📉"
        
        text += (
            f"{arrow} *{h['token_symbol']}*\n"
            f"   Amount: {h['amount_held']:,.2f}\n"
            f"   Value: ${current_value:,.4f}\n"
            f"   PnL: {pnl_sign}${pnl:,.4f} ({pnl_sign}{pnl_pct:.1f}%)\n\n"
        )
        
        buttons.append([
            InlineKeyboardButton(
                f"Sell {h['token_symbol']}",
                callback_data=f"sell_{h['id']}"
            )
        ])
    
    buttons.append([InlineKeyboardButton("« Back", callback_data="menu_main")])
    
    await msg.reply_text(
        text, 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── /history ─────────────────────────────────────────────
async def history_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    tg_user = update.effective_user
    db_user = get_telegram_user(tg_user.id)
    
    if not db_user or not db_user.get("user_id"):
        await msg.reply_text("❌ Use /link to connect your account.")
        return
    
    trades = get_trades(db_user["user_id"], limit=10)
    
    if not trades:
        await msg.reply_text(
            "📭 *No trades yet*\n\nBuy your first token!",
            parse_mode="Markdown"
        )
        return
    
    text = "🕐 *Recent Trades* (last 10)\n\n"
    
    for t in trades:
        badge = "🟣 BUY" if t["trade_type"] == "BUY" else "🔵 SELL"
        price = format_price(str(t["price_at_trade"]))
        entry = format_price(str(t.get("entry_price") or t["price_at_trade"]))
        amount = f"${t['amount_usd']:,.2f}"
        date = str(t["timestamp"])[:10]
        
        pnl_line = ""
        if t["trade_type"] == "SELL" and t.get("entry_price"):
            pnl = (t["price_at_trade"] - t["entry_price"]) * t["token_amount"]
            sign = "+" if pnl >= 0 else ""
            pnl_line = f"   PnL: {sign}${pnl:,.4f}\n"
        
        text += (
            f"{badge} *{t['token_symbol']}*\n"
            f"   Amount: {amount} | {date}\n"
            f"   Entry: {entry} → Trade: {price}\n"
            f"{pnl_line}\n"
        )
    
    await msg.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Back", callback_data="menu_main")]
        ])
    )


# ─── /leaderboard ─────────────────────────────────────────
async def leaderboard_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    await msg.reply_text("🔄 Loading leaderboard...")
    
    board = get_leaderboard(10)
    
    if not board:
        await msg.reply_text("❌ No leaderboard data yet.")
        return
    
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 *PaperDex Leaderboard*\n_Top traders by portfolio gain_\n\n"
    
    for i, entry in enumerate(board, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        sign = "+" if entry["gain_pct"] >= 0 else ""
        text += (
            f"{medal} *{entry['display_name']}*\n"
            f"   {sign}{entry['gain_pct']:.1f}% | "
            f"${entry['current_value']:,.2f}\n\n"
        )
    
    text += "_Rankings update in real-time_ 🔄"
    
    await msg.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="menu_leaderboard"),
                InlineKeyboardButton("🌐 Full App", url=PAPERDEX_URL),
            ],
            [InlineKeyboardButton("« Back", callback_data="menu_main")]
        ])
    )


# ─── BUY FLOW ─────────────────────────────────────────────
async def buy_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    tg_user = update.effective_user
    db_user = get_telegram_user(tg_user.id)
    
    if not db_user or not db_user.get("user_id"):
        await msg.reply_text("❌ Use /link to connect your account.")
        return
    
    set_session(tg_user.id, "awaiting_buy_search")
    await msg.reply_text(
        "🔍 *Search for a token to buy*\n\n"
        "Send the token name or contract address:\n"
        "e.g. `PEPE` or `So11111...`",
        parse_mode="Markdown"
    )


async def handle_sell_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    holding_id = query.data.replace("sell_", "")
    tg_user = update.effective_user
    db_user = get_telegram_user(tg_user.id)
    
    if not db_user:
        return
    
    holding_result = supabase.table("holdings")\
        .select("*")\
        .eq("id", holding_id)\
        .eq("user_id", db_user["user_id"])\
        .execute()
    
    if not holding_result.data:
        await query.message.reply_text("❌ Holding not found.")
        return
    
    holding = holding_result.data[0]
    token_data = await get_token_price(holding["token_address"])
    current_price = float(token_data.get("priceUsd", 0)) if token_data else 0
    current_value = holding["amount_held"] * current_price
    
    set_session(tg_user.id, "awaiting_sell_percent", {
        "holding_id": holding_id,
        "current_price": current_price,
        "holding": holding
    })
    
    await query.message.reply_text(
        f"💸 *Sell {holding['token_symbol']}*\n\n"
        f"Amount held: {holding['amount_held']:,.4f}\n"
        f"Current price: {format_price(str(current_price))}\n"
        f"Current value: ${current_value:,.4f}\n\n"
        f"How much do you want to sell?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("25%", callback_data="sellpct_0.25"),
                InlineKeyboardButton("50%", callback_data="sellpct_0.50"),
                InlineKeyboardButton("75%", callback_data="sellpct_0.75"),
                InlineKeyboardButton("100%", callback_data="sellpct_1.0"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="menu_holdings")]
        ])
    )


async def handle_sell_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pct = float(query.data.replace("sellpct_", ""))
    tg_user = update.effective_user
    session = get_session(tg_user.id)
    
    if session["state"] != "awaiting_sell_percent":
        return
    
    temp = session["temp_data"]
    holding = temp["holding"]
    current_price = temp["current_price"]
    db_user = get_telegram_user(tg_user.id)
    
    result, error = execute_sell(
        db_user["user_id"], holding, pct, current_price
    )
    
    if error:
        await query.message.reply_text(f"❌ Sell failed: {error}")
        return
    
    sign = "+" if result["pnl"] >= 0 else ""
    emoji = "🟢" if result["pnl"] >= 0 else "🔴"
    
    await query.message.reply_text(
        f"✅ *Sell Confirmed!* {emoji}\n\n"
        f"🪙 Sold: {result['tokens_sold']:,.4f} {result['token_symbol']}\n"
        f"💵 Received: ${result['net_proceeds']:,.4f}\n"
        f"📊 PnL: {sign}${result['pnl']:,.4f}\n"
        f"💸 Slippage: {result['slippage']:.2f}%\n"
        f"⛽ Fee: ${result['fee']:.4f}\n"
        f"💰 New Balance: ${result['new_balance']:,.2f}\n\n"
        f"_Synced to PaperDex app_ ✅",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )
    set_session(tg_user.id, "idle")


# ─── MESSAGE HANDLER (text input states) ──────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    session = get_session(tg_user.id)
    text = update.message.text.strip()
    
    if session["state"] == "awaiting_buy_search":
        await update.message.reply_text(f"🔍 Searching for *{text}*...", parse_mode="Markdown")
        pairs = await search_token(text)
        
        if not pairs:
            await update.message.reply_text("❌ No tokens found. Try a different name.")
            return
        
        result_text = f"🔍 *Results for '{text}'*\n\n"
        buttons = []
        
        for i, pair in enumerate(pairs[:5], 1):
            symbol = pair.get("baseToken", {}).get("symbol", "?")
            name = pair.get("baseToken", {}).get("name", "?")
            price = format_price(str(pair.get("priceUsd", "0")))
            chain = CHAIN_DISPLAY.get(pair.get("chainId", ""), "")
            liq = format_large(pair.get("liquidity", {}).get("usd", 0))
            
            result_text += f"{i}. *{symbol}* — {name}\n   {chain} | {price} | LIQ {liq}\n\n"
            buttons.append([
                InlineKeyboardButton(
                    f"Buy {symbol}",
                    callback_data=f"buytoken_{pair.get('baseToken', {}).get('address', '')}_{pair.get('chainId', '')}"
                )
            ])
        
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="menu_main")])
        set_session(tg_user.id, "idle")
        
        await update.message.reply_text(
            result_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif session["state"] == "awaiting_buy_amount":
        try:
            amount = float(text.replace("$", "").strip())
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Enter a valid amount like `50` or `100`", parse_mode="Markdown")
            return
        
        temp = session["temp_data"]
        db_user = get_telegram_user(tg_user.id)
        
        portfolio = get_portfolio(db_user["user_id"])
        if amount > portfolio["virtual_balance_usd"]:
            await update.message.reply_text(
                f"❌ Insufficient balance.\n"
                f"Available: ${portfolio['virtual_balance_usd']:,.2f}"
            )
            return
        
        await update.message.reply_text("⚡ Executing trade...")
        
        token_data = await get_token_price(temp["token_address"])
        if not token_data:
            await update.message.reply_text("❌ Could not fetch token price.")
            return
        
        result, error = execute_buy(db_user["user_id"], token_data, amount)
        
        if error:
            await update.message.reply_text(f"❌ Trade failed: {error}")
            return
        
        await update.message.reply_text(
            f"✅ *Buy Confirmed!* 🚀\n\n"
            f"🪙 Bought: {result['tokens_received']:,.4f} {result['token_symbol']}\n"
            f"💵 Spent: ${result['total_cost']:,.4f}\n"
            f"📊 Price: {format_price(str(result['effective_price']))}\n"
            f"💸 Slippage: {result['slippage']:.2f}%\n"
            f"⛽ Fee: ${result['fee']:.4f}\n"
            f"💰 New Balance: ${result['new_balance']:,.2f}\n\n"
            f"_Trade synced to PaperDex app_ ✅",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
        set_session(tg_user.id, "idle")


async def handle_buy_token_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.replace("buytoken_", "").split("_")
    token_address = parts[0]
    chain_id = parts[1] if len(parts) > 1 else ""
    
    tg_user = update.effective_user
    db_user = get_telegram_user(tg_user.id)
    
    if not db_user:
        await query.message.reply_text("❌ Use /link to connect.")
        return
    
    portfolio = get_portfolio(db_user["user_id"])
    token_data = await get_token_price(token_address)
    
    if not token_data:
        await query.message.reply_text("❌ Could not fetch token data.")
        return
    
    symbol = token_data.get("baseToken", {}).get("symbol", "?")
    price = format_price(str(token_data.get("priceUsd", "0")))
    
    set_session(tg_user.id, "awaiting_buy_amount", {
        "token_address": token_address,
        "chain_id": chain_id
    })
    
    await query.message.reply_text(
        f"💸 *Buy {symbol}*\n\n"
        f"Current price: {price}\n"
        f"Available balance: ${portfolio['virtual_balance_usd']:,.2f}\n\n"
        f"How much USD do you want to spend?\n"
        f"Reply with a number, e.g. `100`",
        parse_mode="Markdown"
    )


# ─── /alerts ──────────────────────────────────────────────
async def alerts_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    tg_user = update.effective_user
    db_user = get_telegram_user(tg_user.id)

    if not db_user or not db_user.get("user_id"):
        await msg.reply_text("❌ Use /link to connect your account.")
        return

    try:
        result = supabase.table("price_alerts")\
            .select("*")\
            .eq("telegram_id", tg_user.id)\
            .eq("is_active", True)\
            .execute()
        alerts = result.data or []
    except Exception as e:
        logger.error("alerts_view error: %s", e)
        await msg.reply_text("❌ Could not fetch alerts. Try again.")
        return

    if not alerts:
        await msg.reply_text(
            "🔔 *Price Alerts*\n\n"
            "You have no active alerts.\n\n"
            "Go to *Holdings* and tap a token to set an alert.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data="menu_main")]
            ])
        )
        return

    text = "🔔 *Your Active Alerts*\n\n"
    buttons = []
    for alert in alerts:
        symbol = alert.get("token_symbol", "?")
        threshold = alert.get("threshold_percent", 10)
        alert_type = alert.get("alert_type", "BOTH")
        text += f"• *{symbol}* — {alert_type} ±{threshold}%\n"
        buttons.append([
            InlineKeyboardButton(
                f"❌ Remove {symbol}",
                callback_data=f"delalert_{alert['id']}"
            )
        ])

    buttons.append([InlineKeyboardButton("« Back", callback_data="menu_main")])
    await msg.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── CALLBACK ROUTER ──────────────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "menu_main":
        await query.message.reply_text(
            "🏠 *Main Menu*", 
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard()
        )
    elif data == "menu_market":
        await market(update, context)
    elif data == "menu_portfolio":
        await portfolio_view(update, context)
    elif data == "menu_holdings":
        await holdings_view(update, context)
    elif data == "menu_history":
        await history_view(update, context)
    elif data == "menu_leaderboard":
        await leaderboard_view(update, context)
    elif data == "menu_alerts":
        await alerts_view(update, context)
    elif data == "action_search":
        await buy_search(update, context)
    elif data.startswith("sell_"):
        await handle_sell_callback(update, context)
    elif data.startswith("sellpct_"):
        await handle_sell_percent(update, context)
    elif data.startswith("buytoken_"):
        await handle_buy_token_callback(update, context)
