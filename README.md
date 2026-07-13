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
- `/myticket` — user checks the status of their own support tickets (open,
  replied, closed) along with what the admin said, via command or the
  **🎫 My Tickets** menu button
- `/stats` — active / banned users, admin count
- `/ban <id>` / `/unban <id>`
- `/addadmin <id>` — owner-only
- `/setwelcome <text>` — edit the welcome message without touching code
- Optional force-join: require users to join your channel before using the bot
- Support messages (both from users and admin replies) are relayed with
  `copy_message`, so premium/custom emoji, stickers, formatting, and
  photos come through exactly as sent instead of being flattened to plain text
- `/help` — lists available commands, tailored to whether you're an admin
- Buttons use Telegram's native color styling (Bot API 9.4, Feb 2026) —
  green for earning/positive actions, blue for neutral actions, red for
  direct-contact actions. Users on a Telegram app older than Feb 9, 2026
  will just see plain buttons — the feature gracefully falls back, nothing breaks.
- Optional support for Telegram Premium **animated custom emoji** in bot
  messages (welcome message, confirmations, admin panel). Requires the
  bot owner's account to have an active Telegram Premium subscription —
  without it, Telegram just shows the plain fallback emoji, so this is
  safe to leave unconfigured.
- All data in SQLite (`bot_data.db`) with an auto-refreshed `backup.json`
  restored automatically on boot if the database is ever missing

## Setting up premium animated emoji (optional)

1. Make sure the Telegram account you'll use as bot owner has an active
   Telegram Premium subscription.
2. Get the `custom_emoji_id` of any animated emoji from a pack you have
   access to. The simplest way: forward or send a message containing that
   custom emoji to an "emoji ID" utility bot (search Telegram for one, e.g.
   an emoji-id extractor bot) — it will reply with the numeric ID.
3. In Render's environment variables, set:
   ```
   CUSTOM_EMOJIS=fire:5359xxxxxxxxxxxxxx,check:5312xxxxxxxxxxxxxx,rocket:...
   ```
   The names on the left (`fire`, `check`, `rocket`, `wave`, `clock`,
   `support`, `pencil`, `ticket`, `tools`, `star`, `stats`, `gear`, `chat`)
   correspond to where each emoji is used across the bot's messages — see
   `bot.py`'s `ce(...)` calls if you want to add more.
4. Leave any name unset and the bot just uses the plain Unicode emoji
   instead — nothing breaks either way.

## 1. Get a bot token

Message **@BotFather** on Telegram → `/newbot` → copy the token.

## 2. Push this code to GitHub

```bash
cd prime-support-bot
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/prime-support-bot.git
git push -u origin main
```

`.env` and `bot_data.db` are already excluded via `.gitignore` — never
commit your real token.

## 3. Deploy on Render

1. Go to [render.com](https://render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Render should auto-detect `render.yaml`. If not, set manually:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python bot.py`
4. Under **Environment**, add these (see `.env.example` for the full list):
   - `BOT_TOKEN` — from BotFather
   - `OWNER_IDS` — your Telegram numeric user ID (get it from **@userinfobot**)
   - `SUPPORT_USERNAME`, `DAILY_EARNING_URL`, `CHAT_GROUP_URL` — optional, for buttons
   - `FORCE_JOIN_CHANNEL` — optional
   - `WEBHOOK_URL` — set this to your Render URL **after** the first deploy,
     e.g. `https://prime-support-bot.onrender.com`, then save (Render will redeploy)
   - `PYTHON_VERSION` = `3.12.4` — **important:** without this, Render may pick
     a very new Python (e.g. 3.14) that `python-telegram-bot` isn't compatible
     with yet, and the bot crashes on startup with
     `RuntimeError: There is no current event loop`. Add this manually in the
     dashboard if your service already exists — it'll trigger a redeploy.
5. Deploy. Once live, message your bot `/start`.

## About data persistence (important)

- `bot_data.db` lives on the container's disk. It survives the bot
  **crashing or restarting** — that's the scenario you asked about, and
  it's covered: Render restarts the same container, disk stays intact,
  `bot_data.db` is untouched.
- What it does **not** survive on Render's free plan is a **fresh
  redeploy** (new commit pushed, manual redeploy) — free-tier containers
  get a clean disk each time. The bot auto-restores from `backup.json`
  in that case if the file happens to still be on disk, but a totally
  new container won't have either file.
- If you need data to survive redeploys too, the cleanest upgrade path
  is a free external database (Render's free PostgreSQL, or MongoDB
  Atlas's free tier) — ping me if you want that wired in; the rest of
  the bot doesn't need to change, only `database.py`.

## Local testing

```bash
cp .env.example .env
# fill in BOT_TOKEN and OWNER_IDS in .env, leave WEBHOOK_URL blank
pip install -r requirements.txt
python bot.py
```

With `WEBHOOK_URL` blank, the bot runs in polling mode — good for testing
on your own machine before you deploy.
