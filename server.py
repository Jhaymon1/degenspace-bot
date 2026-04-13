import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN, WEBHOOK_URL
from handlers import (
    start, link_account, market, portfolio_view,
    holdings_view, history_view, leaderboard_view,
    buy_search, handle_message, button_callback,
)
from alerts import check_price_alerts

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/telegram/webhook"

# Module-level references set during lifespan startup
_ptb_app: Application | None = None
_scheduler: AsyncIOScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ptb_app, _scheduler

    # Build PTB Application
    _ptb_app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers (same as main.py)
    _ptb_app.add_handler(CommandHandler("start", start))
    _ptb_app.add_handler(CommandHandler("link", link_account))
    _ptb_app.add_handler(CommandHandler("market", market))
    _ptb_app.add_handler(CommandHandler("portfolio", portfolio_view))
    _ptb_app.add_handler(CommandHandler("holdings", holdings_view))
    _ptb_app.add_handler(CommandHandler("history", history_view))
    _ptb_app.add_handler(CommandHandler("leaderboard", leaderboard_view))
    _ptb_app.add_handler(CommandHandler("buy", buy_search))
    _ptb_app.add_handler(CallbackQueryHandler(button_callback))
    _ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # PTB v21 lifecycle
    await _ptb_app.initialize()
    await _ptb_app.start()

    # Register webhook with Telegram
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
    await _ptb_app.bot.set_webhook(webhook_url)
    logger.info("Webhook registered: %s", webhook_url)

    # Price alert scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        check_price_alerts,
        "interval",
        seconds=60,
        args=[_ptb_app],
    )
    _scheduler.start()

    logger.info("🚀 PaperDex Bot started in webhook mode")

    yield  # Application is running

    # Graceful shutdown
    _scheduler.shutdown(wait=False)
    await _ptb_app.stop()
    await _ptb_app.shutdown()
    logger.info("Bot stopped")


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    """Render health-check endpoint."""
    return {"status": "ok"}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """Receive Telegram updates and forward them to the PTB Application."""
    data = await request.json()
    update = Update.de_json(data, _ptb_app.bot)
    await _ptb_app.process_update(update)
    return Response(status_code=200)
