"""
Prime Support Bot - Pro Version (Ultimate)
-------------------------------------------
Features: Categories, Auto-FAQ, Working Hours, Export DB, User Profiles, 
Mention Alerts, Broadcasts, Ban/Unban, and Custom Emojis.
"""

import html
import logging
import os
import csv
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database as db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- config from environment ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_IDS = [int(x) for x in os.environ.get("OWNER_IDS", "").replace(" ", "").split(",") if x]
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "")
DAILY_EARNING_URL = os.environ.get("DAILY_EARNING_URL", "")
CHAT_GROUP_URL = os.environ.get("CHAT_GROUP_URL", "")
FORCE_JOIN_CHANNEL = os.environ.get("FORCE_JOIN_CHANNEL", "")

# ---------- premium animated custom emoji ----------
def _parse_custom_emojis(raw: str) -> dict:
    result = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        name, _, emoji_id = pair.partition(":")
        if name and emoji_id:
            result[name.strip()] = emoji_id.strip()
    return result

CUSTOM_EMOJIS = _parse_custom_emojis(os.environ.get("CUSTOM_EMOJIS", ""))

def ce(name: str, fallback: str) -> str:
    emoji_id = CUSTOM_EMOJIS.get(name)
    if not emoji_id:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def esc(value) -> str:
    return html.escape(str(value))

def default_welcome_text() -> str:
    return (
        f"{ce('wave', '👋')} <b>Welcome to Prime X Support</b>\n\n"
        "We're glad to have you here. This is your official channel for "
        "the latest updates, earnings information, and direct support.\n\n"
        f"{ce('clock', '🕐')} <b>24/7 Assistance</b> — our team is available around the clock\n"
        f"{ce('rocket', '🚀')} <b>Fast Updates</b> — announcements and new features, as soon as they land\n"
        f"{ce('support', '🤝')} <b>Dedicated Support</b> — tap below any time you need help\n\n"
        "Use the menu below to get started."
    )

def is_owner_or_admin(user_id: int) -> bool:
    return user_id in OWNER_IDS or db.is_admin(user_id)

# ---------- time checking (IST) ----------
def is_working_hours() -> bool:
    """Check if current time in IST is between 9 AM and 10 PM"""
    ist = timezone(timedelta(hours=5, minutes=30))
    current_hour = datetime.now(ist).hour
    return 9 <= current_hour < 22

# ---------- keyboards ----------
def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    if DAILY_EARNING_URL or CHAT_GROUP_URL:
        top_row = []
        if DAILY_EARNING_URL:
            top_row.append(InlineKeyboardButton("🔥 Daily Earning", url=DAILY_EARNING_URL, api_kwargs={"style": "success"}))
        if CHAT_GROUP_URL:
            top_row.append(InlineKeyboardButton("💬 Chat Group", url=CHAT_GROUP_URL, api_kwargs={"style": "primary"}))
        rows.append(top_row)

    rows.append([
        InlineKeyboardButton("🛠 Support", callback_data="support_menu", api_kwargs={"style": "primary"}),
        InlineKeyboardButton("🎫 My Tickets", callback_data="my_tickets", api_kwargs={"style": "primary"}),
    ])

    if SUPPORT_USERNAME:
        rows.append([
            InlineKeyboardButton("👤 Message Admin Directly", url=f"https://t.me/{SUPPORT_USERNAME}", api_kwargs={"style": "danger"})
        ])

    return InlineKeyboardMarkup(rows)

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats", api_kwargs={"style": "primary"}),
            InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast_help", api_kwargs={"style": "danger"}),
        ],
        [InlineKeyboardButton("✏️ Edit Welcome Message", callback_data="admin_edit_welcome_help", api_kwargs={"style": "success"})],
        [InlineKeyboardButton("📄 Export DB to CSV", callback_data="admin_export_db", api_kwargs={"style": "primary"})]
    ])

def category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Payment Issue", callback_data="cat_Payment", api_kwargs={"style": "primary"})],
        [InlineKeyboardButton("🐛 Bug/Error", callback_data="cat_Bug", api_kwargs={"style": "danger"})],
        [InlineKeyboardButton("❓ Other Inquiry", callback_data="cat_Other", api_kwargs={"style": "success"})]
    ])

# ---------- force-join check ----------
async def user_has_joined(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not FORCE_JOIN_CHANNEL:
        return True
    try:
        member = await context.bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        return member.status not in ("left", "kicked")
    except Exception as e:
        return True

# ---------- handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)

    if not await user_has_joined(context, user.id):
        join_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL.lstrip('@')}", api_kwargs={"style": "primary"})],
            [InlineKeyboardButton("✅ I've Joined", callback_data="check_join", api_kwargs={"style": "success"})],
        ])
        await update.message.reply_text("Please join our channel first to use this bot.", reply_markup=join_kb)
        return

    welcome = db.get_setting("welcome_message") or default_welcome_text()
    name = esc(user.first_name or "there")
    await update.message.reply_text(f"<b>{name}</b>, {welcome}", reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if await user_has_joined(context, user_id):
        await query.answer("Thanks for joining!")
        welcome = db.get_setting("welcome_message") or default_welcome_text()
        name = esc(query.from_user.first_name or "there")
        await query.message.edit_text(f"<b>{name}</b>, {welcome}", reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)
    else:
        await query.answer("You haven't joined yet — please join and try again.", show_alert=True)

async def support_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🗂 <b>Please select a category for your ticket:</b>", reply_markup=category_keyboard(), parse_mode=ParseMode.HTML)

async def category_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.split("_")[1]
    context.user_data["awaiting_feedback"] = True
    context.user_data["ticket_category"] = category
    await query.message.reply_text(f"{ce('pencil', '✍️')} You selected <b>{category}</b>.\n\nPlease describe your question or issue in one message below:", parse_mode=ParseMode.HTML)

STATUS_LABEL = {
    "open": "🟡 <b>Open</b> — awaiting a response",
    "replied": "✅ <b>Replied</b>",
    "closed": "⚪ <b>Closed</b>",
}

def format_tickets(tickets: list) -> str:
    if not tickets:
        return f"You haven't raised any support tickets yet. Tap {ce('tools', '🛠')} Support to open one."
    lines = [f"{ce('ticket', '🎫')} <b>Your Support Tickets</b>\n"]
    for t in tickets:
        lines.append(f"#{t['id']} — {STATUS_LABEL.get(t['status'], esc(t['status']))}")
        lines.append(f"You: {esc(t['message'])}")
        if t.get("admin_reply"):
            lines.append(f"Support: {esc(t['admin_reply'])}")
        lines.append("")
    return "\n".join(lines).strip()

async def myticket_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tickets = db.get_feedback_by_user(update.effective_user.id)
    await update.message.reply_text(format_tickets(tickets), parse_mode=ParseMode.HTML)

async def my_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tickets = db.get_feedback_by_user(query.from_user.id)
    await query.message.reply_text(format_tickets(tickets), parse_mode=ParseMode.HTML)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    reply_ctx = context.user_data.get("reply_ticket")
    if reply_ctx and is_owner_or_admin(user.id):
        target_user_id = reply_ctx["user_id"]
        fid = reply_ctx["fid"]
        try:
            await context.bot.send_message(target_user_id, f"{ce('chat', '💬')} <b>Support team reply (Ticket #{fid})</b>", parse_mode=ParseMode.HTML)
            await context.bot.copy_message(chat_id=target_user_id, from_chat_id=user.id, message_id=message.message_id)
            db.set_feedback_reply(fid, message.text or "[Media Reply]")
            await message.reply_text(f"{ce('check', '✅')} Reply sent.", parse_mode=ParseMode.HTML)
        except Exception as e:
            await message.reply_text(f"❌ Couldn't deliver reply: {esc(e)}")
        context.user_data["reply_ticket"] = None
        return

    if context.user_data.get("awaiting_feedback"):
        context.user_data["awaiting_feedback"] = False
        category = context.user_data.get("ticket_category", "Other")
        text_for_record = f"[{category}] {message.text or message.caption or '[Media]'}"
        
        msg_lower = (message.text or "").lower()
        if "withdraw" in msg_lower or "payment" in msg_lower:
            await message.reply_text("💡 <i>Auto-Reply: Withdrawals usually take 24-48 hours to process. If your payment is delayed longer than this, our admins will assist you shortly!</i>", parse_mode=ParseMode.HTML)
        
        fid = db.add_feedback(user.id, text_for_record)
        
        reply_msg = f"{ce('check', '✅')} Ticket #{fid} opened. Our team will reply here."
        if not is_working_hours():
            reply_msg += "\n\n🌙 <i>Note: Our support team is currently away. We will respond to your ticket as soon as we are back online (9 AM - 10 PM IST).</i>"
            
        await message.reply_text(reply_msg, parse_mode=ParseMode.HTML)
        await notify_admins_of_feedback(context, fid, user, message, category)
        return

    if message.text:
        await message.reply_text(f"Use /start to see the menu, or tap {ce('tools', '🛠')} Support to reach our team.", parse_mode=ParseMode.HTML)

async def notify_admins_of_feedback(context: ContextTypes.DEFAULT_TYPE, fid: int, user, message, category):
    msg_lower = (message.text or "").lower()
    urgent_tag = "🚨 <b>URGENT/SCAM ALERT</b>\n" if "scam" in msg_lower or "urgent" in msg_lower or "help" in msg_lower else ""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{fid}_{user.id}", api_kwargs={"style": "primary"}),
         InlineKeyboardButton("🗑 Close Ticket", callback_data=f"close_{fid}", api_kwargs={"style": "danger"})]
    ])
    admin_ids = set(OWNER_IDS) | set(db.list_admins())
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                admin_id,
                f"{urgent_tag}{ce('ticket', '📩')} <b>Ticket #{fid} | {category}</b>\n"
                f"From: {esc(user.first_name)} (@{esc(user.username or 'None')}, ID: <code>{user.id}</code>)",
                parse_mode=ParseMode.HTML,
            )
            await context.bot.copy_message(chat_id=admin_id, from_chat_id=user.id, message_id=message.message_id, reply_markup=kb)
        except Exception:
            pass

# ---------- admin commands ----------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lines = [
        f"{ce('star', '⭐')} <b>Available Commands</b>\n",
        "/start — open the main menu",
        "/myticket — check the status of your support tickets",
    ]
    if is_owner_or_admin(user_id):
        lines += [
            "",
            "<b>Admin</b>",
            "/admin — open the admin panel",
            "/user <id> — view user profile info",
            "/stats — active / banned users, admin count",
            "/broadcast <text> — message every user",
            "/broadcast_admins <text> — message all admins",
            "/ban <user_id> · /unban <user_id>",
            "/clearbans — unban all users",
            "/setwelcome <text> — update the welcome message",
            "/export — download database to CSV",
        ]
    if user_id in OWNER_IDS:
        lines.append("/addadmin <user_id> — grant admin access (owner only)")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

async def user_info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /user <user_id>")
        return
    try:
        uid = int(context.args[0])
        tickets = db.get_feedback_by_user(uid)
        await update.message.reply_text(
            f"👤 <b>User Info for {uid}</b>\n"
            f"Total Tickets Created: <b>{len(tickets)}</b>\n"
            f"Ban Status: Check via /stats or attempt /ban.",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await update.message.reply_text("Invalid User ID.")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    s = db.get_stats()
    await update.message.reply_text(
        f"{ce('stats', '📊')} <b>Statistics</b>\n\n"
        f"Active users: {s['active_users']}\n"
        f"Banned users: {s['banned_users']}\n"
        f"Administrators: {s['administrators']}",
        parse_mode=ParseMode.HTML,
    )

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    text = update.message.text.partition(" ")[2]
    if not text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    user_ids = db.get_all_user_ids()
    sent, failed = 0, 0
    status_msg = await update.message.reply_text(f"Broadcasting to {len(user_ids)} users…")
    for uid in user_ids:
        try:
            await context.bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(f"{ce('check', '✅')} Broadcast complete — sent: {sent}, failed: {failed}.", parse_mode=ParseMode.HTML)

async def broadcast_admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    text = update.message.text.partition(" ")[2]
    if not text:
        await update.message.reply_text("Usage: /broadcast_admins <message>")
        return
    admin_ids = set(OWNER_IDS) | set(db.list_admins())
    sent = 0
    for aid in admin_ids:
        try:
            await context.bot.send_message(aid, f"⚠️ <b>Admin Broadcast:</b>\n\n{text}", parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"📢 Broadcast sent to {sent} admins.")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    db.ban_user(int(context.args[0]))
    await update.message.reply_text("🚫 User banned.")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    db.unban_user(int(context.args[0]))
    await update.message.reply_text(f"{ce('check', '✅')} User unbanned.", parse_mode=ParseMode.HTML)

async def clear_bans_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("Only the owner can wipe the ban list.")
        return
    try:
        user_ids = db.get_all_user_ids()
        for uid in user_ids:
            db.unban_user(uid)
        await update.message.reply_text(f"{ce('check', '✅')} All users have been unbanned.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: {e}")

async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    db.add_admin(int(context.args[0]))
    await update.message.reply_text(f"{ce('check', '✅')} Admin added.", parse_mode=ParseMode.HTML)

async def setwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    text = update.message.text.partition(" ")[2]
    if not text:
        await update.message.reply_text("Usage: /setwelcome <new welcome text>")
        return
    db.set_setting("welcome_message", text)
    await update.message.reply_text(f"{ce('check', '✅')} Welcome message updated.", parse_mode=ParseMode.HTML)

async def export_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = getattr(update, 'callback_query', None)
    user_id = query.from_user.id if query else update.effective_user.id
    if query:
        await query.answer()
    if not is_owner_or_admin(user_id):
        return
    try:
        user_ids = db.get_all_user_ids()
        filename = "users_export.csv"
        with open(filename, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["User ID"])
            for uid in user_ids:
                writer.writerow([uid])
        await context.bot.send_document(chat_id=user_id, document=open(filename, 'rb'), filename=filename, caption="📊 Database Export")
        os.remove(filename)
    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"Export failed: {e}")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    await update.message.reply_text(f"{ce('gear', '⚙️')} <b>Admin Panel</b>", reply_markup=admin_panel_keyboard(), parse_mode=ParseMode.HTML)

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner_or_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return
    if query.data == "admin_stats":
        await query.answer()
        s = db.get_stats()
        await query.message.reply_text(f"{ce('stats', '📊')} Active: {s['active_users']} | Banned: {s['banned_users']} | Admins: {s['administrators']}")
    elif query.data == "admin_export_db":
        await export_db_cmd(update, context)
    elif query.data == "admin_broadcast_help":
        await query.answer()
        await query.message.reply_text("Send: /broadcast <your message>")
    elif query.data == "admin_edit_welcome_help":
        await query.answer()
        await query.message.reply_text("Send: /setwelcome <new welcome text>")

async def reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner_or_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return
    _, fid, target_user_id = query.data.split("_")
    context.user_data["reply_ticket"] = {"fid": int(fid), "user_id": int(target_user_id)}
    await query.answer()
    await query.message.reply_text(f"Type your reply to ticket #{fid} now:")

async def close_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner_or_admin(query.from_user.id):
        return
    _, fid = query.data.split("_")
    try:
        db.set_feedback_reply(int(fid), "[Closed by Admin]")
        await query.answer("Ticket closed successfully.")
        await query.message.edit_text(f"🗑 <b>Ticket #{fid} has been marked as closed.</b>", parse_mode=ParseMode.HTML)
    except Exception:
        pass

def build_app() -> Application:
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("myticket", myticket_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("user", user_info_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("broadcast_admins", broadcast_admins_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("clearbans", clear_bans_cmd))
    app.add_handler(CommandHandler("addadmin", addadmin_cmd))
    app.add_handler(CommandHandler("setwelcome", setwelcome_cmd))
    app.add_handler(CommandHandler("export", export_db_cmd))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(my_tickets_callback, pattern="^my_tickets$"))
    app.add_handler(CallbackQueryHandler(support_menu_button, pattern="^support_menu$"))
    app.add_handler(CallbackQueryHandler(category_selection_callback, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(reply_button, pattern="^reply_"))
    app.add_handler(CallbackQueryHandler(close_ticket_callback, pattern="^close_"))
    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_"))

    # Messages
    app.add_handler(MessageHandler(~filters.COMMAND, handle_message))
    return app

if __name__ == "__main__":
    app = build_app()
    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.environ.get("WEBHOOK_URL")

    if webhook_url:
        logger.info("Starting in webhook mode on port %s", port)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=f"{webhook_url.rstrip('/')}/webhook",
        )
    else:
        logger.info("WEBHOOK_URL not set — starting in polling mode (fine for local dev)")
        app.run_polling()
