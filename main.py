import logging
import threading
import uvicorn
from telegram.ext import (
    Application, CommandHandler, 
    MessageHandler, CallbackQueryHandler,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers import (
    start, link_account, market, portfolio_view,
    holdings_view, history_view, leaderboard_view,
    buy_search, handle_message, button_callback
)
from alerts import check_price_alerts
from config import BOT_TOKEN
from web import app as web_app, port as web_port

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def _run_web():
    """Start the FastAPI/Uvicorn server for Render health checks."""
    uvicorn.run(web_app, host="0.0.0.0", port=web_port(), log_level="info")


def main():
    # Start HTTP server in a daemon thread so Render Web Service health checks pass
    web_thread = threading.Thread(target=_run_web, daemon=True)
    web_thread.start()
    logger.info("🌐 Web server started on port %d", web_port())

    scheduler = AsyncIOScheduler()

    async def post_init(application: Application) -> None:
        """Start the scheduler inside the bot's running event loop."""
        scheduler.add_job(
            check_price_alerts,
            "interval",
            seconds=60,
            args=[application],
        )
        try:
            scheduler.start()
            logger.info("⏰ Price alert scheduler started")
        except Exception as exc:
            logger.error("Failed to start scheduler: %s", exc)

    async def post_shutdown(application: Application) -> None:
        """Cleanly stop the scheduler when the bot shuts down."""
        if scheduler.running:
            scheduler.shutdown(wait=False)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link_account))
    app.add_handler(CommandHandler("market", market))
    app.add_handler(CommandHandler("portfolio", portfolio_view))
    app.add_handler(CommandHandler("holdings", holdings_view))
    app.add_handler(CommandHandler("history", history_view))
    app.add_handler(CommandHandler("leaderboard", leaderboard_view))
    app.add_handler(CommandHandler("buy", buy_search))
    
    # Callback query handler (buttons)
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Text message handler (for buy/sell flows)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 PaperDex Bot starting (web + polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("Fatal error during startup: %s", exc)
        raise
