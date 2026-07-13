"""
Prime Support Bot
------------------
A PrimeXSupport Telegram support bot: welcome message with buttons,
a feedback/support inbox that relays messages to admins and lets them
reply back to the user, broadcast, stats, ban/unban and a small admin
panel — all backed by SQLite (see database.py) so data survives
crashes and restarts.

Run locally:
    python bot.py

Deploy on Render: see README.md
"""

import logging
import os
from datetime import datetime

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
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "")  # e.g. luvarxp (no @)
DAILY_EARNING_URL = os.environ.get("DAILY_EARNING_URL", "")
CHAT_GROUP_URL = os.environ.get("CHAT_GROUP_URL", "")
FORCE_JOIN_CHANNEL = os.environ.get("FORCE_JOIN_CHANNEL", "")  # e.g. @yourchannel, blank = disabled

DEFAULT_WELCOME = (
    "Welcome to Prime X Support! 🚩\n\n"
    "We are absolutely thrilled to have you join our community.\n\n"
    "• This is your official hub for all the latest updates, earnings "
    "information, and dedicated support.\n\n"
    "• Here is what you can expect from us:\n"
    "🕐 24 X 7 Assistance: We are always here to help you around the clock.\n\n"
    "🚀 Fast & Reliable Updates: Stay informed with the newest announcements "
    "and features.\n\n"
    "🤝 Dedicated Support: Have a question or need help? Our team is just "
    "a message away.\n\n"
    "Please feel free to explore, ask questions, and stay connected."
)


def is_owner_or_admin(user_id: int) -> bool:
    return user_id in OWNER_IDS or db.is_admin(user_id)


# ---------- keyboards ----------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    rows = []
    top_row = []
    if DAILY_EARNING_URL:
        top_row.append(InlineKeyboardButton("🔥 Daily Agent Free Earning", url=DAILY_EARNING_URL))
    if CHAT_GROUP_URL:
        top_row.append(InlineKeyboardButton("💬 Prime X Chat", url=CHAT_GROUP_URL))
    if top_row:
        rows.append(top_row)
    rows.append([InlineKeyboardButton("🛠 Contact Support", callback_data="support")])
    rows.append([InlineKeyboardButton("🎫 My Tickets", callback_data="my_tickets")])
    if SUPPORT_USERNAME:
        rows.append([InlineKeyboardButton("👤 Message Admin Directly", url=f"https://t.me/{SUPPORT_USERNAME}")])
    return InlineKeyboardMarkup(rows)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast_help")],
            [InlineKeyboardButton("✏️ Edit Welcome Message", callback_data="admin_edit_welcome_help")],
        ]
    )


# ---------- force-join check ----------

async def user_has_joined(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not FORCE_JOIN_CHANNEL:
        return True
    try:
        member = await context.bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        return member.status not in ("left", "kicked")
    except Exception as e:
        logger.warning("Force-join check failed: %s", e)
        return True  # fail open so a misconfigured channel doesn't lock everyone out


# ---------- handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name)

    if not await user_has_joined(context, user.id):
        join_kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL.lstrip('@')}")],
                [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")],
            ]
        )
        await update.message.reply_text(
            "Please join our channel first to use this bot 👇", reply_markup=join_kb
        )
        return

    welcome = db.get_setting("welcome_message", DEFAULT_WELCOME)
    name = user.first_name or "there"
    await update.message.reply_text(
        f"{name}, {welcome}", reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML
    )


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if await user_has_joined(context, user_id):
        await query.answer("Thanks for joining! ✅")
        welcome = db.get_setting("welcome_message", DEFAULT_WELCOME)
        name = query.from_user.first_name or "there"
        await query.message.edit_text(f"{name}, {welcome}", reply_markup=main_menu_keyboard())
    else:
        await query.answer("You haven't joined yet — please join and try again.", show_alert=True)


async def support_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_feedback"] = True
    await query.message.reply_text(
        "✍️ Please type your question or issue below and our team will get back to you."
    )


STATUS_LABEL = {"open": "🟡 Open — waiting for a reply", "replied": "✅ Replied", "closed": "⚪ Closed"}


def format_tickets(tickets: list[dict]) -> str:
    if not tickets:
        return "You haven't raised any support tickets yet. Tap 🛠 Contact Support to open one."
    lines = ["🎫 Your tickets:\n"]
    for t in tickets:
        lines.append(f"#{t['id']} — {STATUS_LABEL.get(t['status'], t['status'])}")
        lines.append(f"You: {t['message']}")
        if t.get("admin_reply"):
            lines.append(f"Support: {t['admin_reply']}")
        lines.append("")  # blank line between tickets
    return "\n".join(lines).strip()


async def myticket_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tickets = db.get_feedback_by_user(update.effective_user.id)
    await update.message.reply_text(format_tickets(tickets))


async def my_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tickets = db.get_feedback_by_user(query.from_user.id)
    await query.message.reply_text(format_tickets(tickets))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles any incoming message (text, premium/custom emoji, stickers,
    photos, etc.): either a support message from a user, or an admin's
    reply typed after tapping Reply on a forwarded ticket.

    We use copy_message (not send_message with plain text) so premium
    custom emoji, formatting, stickers and media come through exactly as
    the sender sent them — extracting .text would silently strip custom
    emoji entities."""
    user = update.effective_user
    message = update.message

    # Admin replying to a ticket
    reply_ctx = context.user_data.get("reply_ticket")
    if reply_ctx and is_owner_or_admin(user.id):
        target_user_id = reply_ctx["user_id"]
        fid = reply_ctx["fid"]
        try:
            await context.bot.send_message(target_user_id, "💬 Support team reply:")
            await context.bot.copy_message(
                chat_id=target_user_id, from_chat_id=user.id, message_id=message.message_id
            )
            reply_text = message.text or message.caption or "[non-text reply]"
            db.set_feedback_reply(fid, reply_text)
            await message.reply_text("✅ Reply sent.")
        except Exception as e:
            await message.reply_text(f"❌ Couldn't deliver reply: {e}")
        context.user_data["reply_ticket"] = None
        return

    # User sending a support/feedback message
    if context.user_data.get("awaiting_feedback"):
        context.user_data["awaiting_feedback"] = False
        text_for_record = message.text or message.caption or "[non-text message]"
        fid = db.add_feedback(user.id, text_for_record)
        await message.reply_text("✅ Got it! Our team will reply here soon.")
        await notify_admins_of_feedback(context, fid, user, message)
        return

    # Fallback: unrecognised free content, outside any flow
    if message.text:
        await message.reply_text(
            "Use /start to see the menu, or tap 🛠 Contact Support to reach our team."
        )


async def notify_admins_of_feedback(context: ContextTypes.DEFAULT_TYPE, fid: int, user, message):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{fid}_{user.id}")]])
    admin_ids = set(OWNER_IDS) | set(db.list_admins())
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                admin_id,
                f"📩 New support ticket #{fid}\n"
                f"From: {user.first_name} (@{user.username or 'no_username'}, id: {user.id})",
            )
            await context.bot.copy_message(
                chat_id=admin_id, from_chat_id=user.id, message_id=message.message_id, reply_markup=kb
            )
        except Exception as e:
            logger.warning("Couldn't notify admin %s: %s", admin_id, e)


async def reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner_or_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return
    _, fid, target_user_id = query.data.split("_")
    context.user_data["reply_ticket"] = {"fid": int(fid), "user_id": int(target_user_id)}
    await query.answer()
    await query.message.reply_text(f"Type your reply to ticket #{fid} now:")


# ---------- admin commands ----------

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    s = db.get_stats()
    await update.message.reply_text(
        "📊 Statistics\n\n"
        f"• Active users: {s['active_users']}\n"
        f"• Banned users: {s['banned_users']}\n"
        f"• Administrators: {s['administrators']}"
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
    status_msg = await update.message.reply_text(f"Broadcasting to {len(user_ids)} users...")
    for uid in user_ids:
        try:
            await context.bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(f"✅ Broadcast done. Sent: {sent}, Failed: {failed}")


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
    await update.message.reply_text("✅ User unbanned.")


async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in OWNER_IDS:
        await update.message.reply_text("Only the owner can add admins.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    db.add_admin(int(context.args[0]))
    await update.message.reply_text("✅ Admin added.")


async def setwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    text = update.message.text.partition(" ")[2]
    if not text:
        await update.message.reply_text("Usage: /setwelcome <new welcome text>")
        return
    db.set_setting("welcome_message", text)
    await update.message.reply_text("✅ Welcome message updated.")


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner_or_admin(update.effective_user.id):
        return
    await update.message.reply_text("⚙️ Admin Panel", reply_markup=admin_panel_keyboard())


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner_or_admin(query.from_user.id):
        await query.answer("Admins only.", show_alert=True)
        return
    await query.answer()
    if query.data == "admin_stats":
        s = db.get_stats()
        await query.message.reply_text(
            f"📊 Active: {s['active_users']} | Banned: {s['banned_users']} | Admins: {s['administrators']}"
        )
    elif query.data == "admin_broadcast_help":
        await query.message.reply_text("Send: /broadcast <your message>")
    elif query.data == "admin_edit_welcome_help":
        await query.message.reply_text("Send: /setwelcome <new welcome text>")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Update %s caused error %s", update, context.error)


def build_app() -> Application:
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("addadmin", addadmin_cmd))
    app.add_handler(CommandHandler("setwelcome", setwelcome_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("myticket", myticket_cmd))

    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(support_button, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(my_tickets_callback, pattern="^my_tickets$"))
    app.add_handler(CallbackQueryHandler(reply_button, pattern="^reply_"))
    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_"))

    app.add_handler(MessageHandler(~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)
    return app


def main():
    app = build_app()
    port = int(os.environ.get("PORT", 8080))
    webhook_url = os.environ.get("WEBHOOK_URL")  # e.g. https://your-app.onrender.com

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


if __name__ == "__main__":
    main()
