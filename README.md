# Prime Support Bot

A PrimeXSupport Telegram support bot for your channel/community —
welcome message, feedback/support inbox, broadcast, stats, ban/unban,
optional force-join, all backed by SQLite so data survives crashes and
restarts.

## Features

- `/start` — welcome message with buttons (earning link, chat group link, contact support)
- Support inbox: user taps **Contact Support**, types their issue, it's
  forwarded to all admins with a **Reply** button — admin's reply goes
  straight back to the user
- `/broadcast <text>` — message every user who has started the bot
- `/stats` — active / banned users, admin count
- `/ban <id>` / `/unban <id>`
- `/addadmin <id>` — owner-only
- `/setwelcome <text>` — edit the welcome message without touching code
- Optional force-join: require users to join your channel before using the bot
- Support messages (both from users and admin replies) are relayed with
  `copy_message`, so premium/custom emoji, stickers, formatting, and
  photos come through exactly as sent instead of being flattened to plain text
- All data in SQLite (`bot_data.db`) with an auto-refreshed `backup.json`
  restored automatically on boot if the database is ever missing

## 1. Get a bot token

Message **@BotFather** on Telegram → `/newbot` → copy the token.

## 2. Push this code to GitHub

\```bash
cd prime-support-bot
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/prime-support-bot.git
git push -u origin main
\```

`.env` and `bot_data.db` are already excluded via `.gitignore` — never
commit your real token.

## 3. Deploy on Render

1. Go to render.com → **New** → **Web Service**
2. Connect your GitHub repo
3. Render should auto-detect `render.yaml`. If not, set manually:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python bot.py`
4. Under **Environment**, add these (see `.env.example`):
   - `BOT_TOKEN`, `OWNER_IDS`, `SUPPORT_USERNAME`, `DAILY_EARNING_URL`,
     `CHAT_GROUP_URL`, `FORCE_JOIN_CHANNEL`
   - `WEBHOOK_URL` — set this to your Render URL **after** the first deploy
5. Deploy. Once live, message your bot `/start`.

## About data persistence

- `bot_data.db` survives the bot **crashing or restarting** — same container, disk intact.
- It does **not** survive a fresh **redeploy** on Render's free plan (clean disk each time).
- For redeploy-proof persistence, upgrade to a free external DB later — only `database.py` changes.

## Local testing

\```bash
cp .env.example .env
pip install -r requirements.txt
python bot.py
\```
