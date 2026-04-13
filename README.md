# degenspace-bot

A Telegram paper-trading bot for meme coins powered by PaperDex.

## Deploying on Render (Web Service)

This bot runs a Telegram polling loop **and** a small FastAPI health-check server
so it can be deployed as a Render **Web Service**.

### Render settings

| Setting | Value |
|---|---|
| Service type | **Web Service** |
| Start command | `python main.py` |
| Health check path | `/healthz` |
| Instances | **1** (prevents duplicate polling bots) |

### Required environment variables

Set these in **Render Dashboard → Environment**:

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your Telegram Bot token from @BotFather |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon/service key |
| `PAPERDEX_URL` | PaperDex frontend URL (optional) |

### Health check endpoints

| Endpoint | Response |
|---|---|
| `GET /` | `{"ok": true, "service": "degenspace-bot"}` |
| `GET /healthz` | `{"ok": true}` |
