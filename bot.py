import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

import database as db
from config import BOT_TOKEN, OWNER_ID
from utils import calc_fee, fmt, is_valid_amount

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ---------- Helpers ----------
def mention(uid, name):
    return f"[{name}](tg://user?id={uid})"


def deal_card(deal):
    status_emoji = {
        "active": "🟢",
        "closed": "✅",
        "cancelled": "❌",
        "held": "⏸️",
        "refunded": "↩️",
    }.get(deal["status"], "⚪")

    text = (
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 *ESCROW DEAL #{deal['id']}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Escrower: {mention(deal['escrower_id'], deal['escrower_name'])}\n"
        f"💰 Amount: *{fmt(deal['amount'])}*\n"
        f"🧮 Fee: {fmt(deal['fee'])}\n"
        f"💵 Total: *{fmt(deal['total'])}*\n"
    )
    if deal.get("reason"):
        text += f"📝 Reason: {deal['reason']}\n"
    if deal.get("trade_id"):
        text += f"🪪 Trade ID: `{deal['trade_id']}`\n"
    text += f"📌 Status: {status_emoji} *{deal['status'].upper()}*\n"
    text += "━━━━━━━━━━━━━━━━━━━"
    return text


def admin_required(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not db.is_admin(uid, OWNER_ID):
            await update.message.reply_text("⛔ Admin only.")
            return
        return await func(update, ctx)

    return wrapper


def owner_required(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid != OWNER_ID:
            await update.message.reply_text("⛔ Owner only.")
            return
        return await func(update, ctx)

    return wrapper


def owner_or_coowner_required(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not db.is_owner_or_coowner(uid, OWNER_ID):
            await update.message.reply_text("⛔ Owner / Co-Owner only.")
            return
        return await func(update, ctx)

    return wrapper


# =========================================================
#                    DEAL COMMANDS
# =========================================================
async def deal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/deal 500 [reason]"""
    chat = update.effective_chat
    user = update.effective_user
    if not ctx.args:
        await update.message.reply_text("Usage: `/deal 500 [reason]`", parse_mode=ParseMode.MARKDOWN)
        return

    ok, amount = is_valid_amount(ctx.args[0])
    if not ok:
        await update.message.reply_text("❌ Invalid amount.")
        return

    reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
    fee, total = calc_fee(amount)
    deal_id = db.create_deal(chat.id, user.id, user.full_name, amount, fee, total, reason)
    d = db.get_deal(deal_id)

    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🔒 Close", callback_data=f"close:{deal_id}"),
            InlineKeyboardButton("⏸️ Hold", callback_data=f"hold:{deal_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{deal_id}"),
        ]]
    )
    await update.message.reply_text(deal_card(d), parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def close_deal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    d = db.latest_deal(chat.id)
    if not d or d["escrower_id"] != user.id:
        await update.message.reply_text("❌ No active deal found owned by you.")
        return
    db.update_deal(d["id"], status="closed")
    await update.message.reply_text(
        f"✅ Deal #{d['id']} closed.\n" + deal_card(db.get_deal(d["id"])),
        parse_mode=ParseMode.MARKDOWN,
    )


async def hold_deal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    reason = " ".join(ctx.args) if ctx.args else "No reason provided"
    d = db.latest_deal(chat.id)
    if not d or d["escrower_id"] != user.id:
        await update.message.reply_text("❌ No deal to hold.")
        return
    db.update_deal(d["id"], status="held", reason=reason)
    await update.message.reply_text(f"⏸️ Deal #{d['id']} on hold.\n📝 {reason}")


async def unhold_deal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    d = db.latest_deal(chat.id)
    if not d or d["escrower_id"] != user.id or d["status"] != "held":
        await update.message.reply_text("❌ No held deal found.")
        return
    db.update_deal(d["id"], status="active")
    await update.message.reply_text(f"🔓 Deal #{d['id']} is active again.")


async def cancel_deal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    d = db.latest_deal(chat.id)
    if not d or d["escrower_id"] != user.id:
        await update.message.reply_text("❌ No deal to cancel.")
        return
    db.update_deal(d["id"], status="cancelled")
    await update.message.reply_text(f"❌ Deal #{d['id']} cancelled.")


async def refund_deal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    d = db.latest_deal(chat.id)
    if not d or d["escrower_id"] != user.id:
        await update.message.reply_text("❌ No deal to refund.")
        return
    db.update_deal(d["id"], status="refunded")
    await update.message.reply_text(f"↩️ Deal #{d['id']} refunded. Amount {fmt(d['amount'])}.")


async def calc_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/c 500`", parse_mode=ParseMode.MARKDOWN)
        return
    ok, amount = is_valid_amount(ctx.args[0])
    if not ok:
        await update.message.reply_text("❌ Invalid amount.")
        return
    fee, total = calc_fee(amount)
    await update.message.reply_text(
        f"💎 *Fee Calculator*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Amount: {fmt(amount)}\n"
        f"Fee: {fmt(fee)}\n"
        f"Total: *{fmt(total)}*",
        parse_mode=ParseMode.MARKDOWN,
    )


@owner_or_coowner_required
async def settradeid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/settradeid 198`", parse_mode=ParseMode.MARKDOWN)
        return
    chat = update.effective_chat
    d = db.latest_deal(chat.id)
    if not d:
        await update.message.reply_text("❌ No deal in this chat.")
        return
    db.update_deal(d["id"], trade_id=ctx.args[0])
    await update.message.reply_text(
        f"🪪 Trade ID `{ctx.args[0]}` set for deal #{d['id']}.",
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_required
async def minus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    did = db.delete_latest(chat.id)
    if did:
        await update.message.reply_text(f"🗑️ Removed deal #{did}.")
    else:
        await update.message.reply_text("❌ No deals to remove.")


async def stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    s = db.chat_stats(chat.id)
    text = (
        f"📊 *GC Deal Statistics*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Deals: *{s['total_deals']}*\n"
        f"Volume: *{fmt(s['total_volume'])}*\n"
        f"Fees: *{fmt(s['total_fees'])}*"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def earnings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    total = db.user_earnings(uid)
    await update.message.reply_text(
        f"💵 *Your Earnings*\nTotal fees collected: *{fmt(total)}*",
        parse_mode=ParseMode.MARKDOWN,
    )


async def report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    deals = db.user_deals(uid, 10)
    if not deals:
        await update.message.reply_text("📭 No deals yet.")
        return
    lines = ["📄 *Your Deal Report*", "━━━━━━━━━━━━━━━"]
    for d in deals:
        lines.append(f"#{d['id']} • {fmt(d['amount'])} • `{d['status']}`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# =========================================================
#                    ADMIN COMMANDS
# =========================================================
@admin_required
async def admins(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = db.list_admins()
    owners = db.list_coowners()
    text = "👑 *Owner:*\n"
    text += f"• `{OWNER_ID}`\n\n"
    if owners:
        text += "🧑‍💼 *Co-Owners:*\n"
        for c in owners:
            text += f"• `{c}`\n"
        text += "\n"
    text += "🛡️ *Admins:*\n"
    if rows:
        for r in rows:
            text += f"• `{r['user_id']}` {r.get('username') or ''}\n"
    else:
        text += "• (none)\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_required
async def addadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/addadmin 123 [456 789]`", parse_mode=ParseMode.MARKDOWN)
        return
    added = []
    for a in ctx.args:
        if not a.lstrip("-").isdigit():
            continue
        db.add_admin(int(a))
        added.append(a)
    await update.message.reply_text(f"✅ Added: {', '.join(added) or 'none'}")


@admin_required
async def removeadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].lstrip("-").isdigit():
        await update.message.reply_text("Usage: `/removeadmin 123`", parse_mode=ParseMode.MARKDOWN)
        return
    db.remove_admin(int(ctx.args[0]))
    await update.message.reply_text(f"🗑️ Removed admin {ctx.args[0]}")


@owner_required
async def coowneradd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].lstrip("-").isdigit():
        await update.message.reply_text("Usage: `/coowneradd 123`", parse_mode=ParseMode.MARKDOWN)
        return
    db.add_coowner(int(ctx.args[0]))
    await update.message.reply_text(f"👑 Co-owner added: {ctx.args[0]}")


@owner_required
async def coownerremove(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].lstrip("-").isdigit():
        await update.message.reply_text("Usage: `/coownerremove 123`", parse_mode=ParseMode.MARKDOWN)
        return
    db.remove_coowner(int(ctx.args[0]))
    await update.message.reply_text(f"🗑️ Co-owner removed: {ctx.args[0]}")


async def coowners(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = db.list_coowners()
    if not rows:
        await update.message.reply_text("👑 No co-owners.")
        return
    await update.message.reply_text(
        "👑 *Co-Owners:*\n" + "\n".join(f"• `{r}`" for r in rows),
        parse_mode=ParseMode.MARKDOWN,
    )


# =========================================================
#                    SETTINGS / MISC
# =========================================================
@owner_required
async def settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = db.all_settings()
    text = "⚙️ *Bot Settings*\n━━━━━━━━━━━━━━━\n"
    text += "\n".join(f"• `{k}` = `{v}`" for k, v in s.items()) or "(no settings)"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@owner_required
async def fee_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "💰 *Universal Fee System*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "₹1–₹100 → ₹10\n"
        "₹101–₹599 → ₹20\n"
        "₹600–₹2000 → 3.5%\n"
        "₹2001+ → 3%\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Use `/c 500` to calculate."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is online and running.")


async def emoji_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            "💎 Premium emoji test: <tg-emoji emoji-id='5368324170671202286'>💎</tg-emoji>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        await update.message.reply_text("💎 (fallback) Premium emoji not supported.")


async def chatid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Chat ID: `{update.effective_chat.id}`", parse_mode=ParseMode.MARKDOWN
    )


# =========================================================
#              INLINE BUTTON CALLBACK HANDLER
# =========================================================
async def button_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, deal_id = q.data.split(":")
    deal_id = int(deal_id)
    d = db.get_deal(deal_id)
    if not d:
        await q.edit_message_text("❌ Deal no longer exists.")
        return
    uid = q.from_user.id
    if d["escrower_id"] != uid:
        await q.answer("⛔ Only the original escrower can do this.", show_alert=True)
        return
    if action == "close":
        db.update_deal(deal_id, status="closed")
        await q.edit_message_text(deal_card(db.get_deal(deal_id)), parse_mode=ParseMode.MARKDOWN)
    elif action == "hold":
        db.update_deal(deal_id, status="held")
        await q.edit_message_text(deal_card(db.get_deal(deal_id)), parse_mode=ParseMode.MARKDOWN)
    elif action == "cancel":
        db.update_deal(deal_id, status="cancelled")
        await q.edit_message_text(deal_card(db.get_deal(deal_id)), parse_mode=ParseMode.MARKDOWN)


# =========================================================
#                    STARTUP
# =========================================================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🔐 *Escrow Bot*\n"
        "━━━━━━━━━━━━━━━\n"
        "Use `/deal 500` to open a deal.\n"
        "Use `/c 500` to calculate fees."
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)


def main():
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Deal commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deal", deal))
    app.add_handler(CommandHandler("close", close_deal))
    app.add_handler(CommandHandler("hold", hold_deal))
    app.add_handler(CommandHandler("unhold", unhold_deal))
    app.add_handler(CommandHandler("cancel", cancel_deal))
    app.add_handler(CommandHandler("refund", refund_deal))
    app.add_handler(CommandHandler("c", calc_cmd))
    app.add_handler(CommandHandler("settradeid", settradeid))
    app.add_handler(CommandHandler("minus", minus))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("earnings", earnings))
    app.add_handler(CommandHandler("report", report))

    # Admin commands
    app.add_handler(CommandHandler("admins", admins))
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("removeadmin", removeadmin))
    app.add_handler(CommandHandler("coowneradd", coowneradd))
    app.add_handler(CommandHandler("coownerremove", coownerremove))
    app.add_handler(CommandHandler("coowners", coowners))

    # Settings / misc
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("fee", fee_settings))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(CommandHandler("emoji_test", emoji_test))
    app.add_handler(CommandHandler("chatid", chatid))

    # Callback buttons
    app.add_handler(CallbackQueryHandler(button_cb))

    log.info("🤖 Escrow bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
