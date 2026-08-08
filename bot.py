import os
import sqlite3
import random
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --- Configuration & Paths ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "couple_bot.db")

flask_app = Flask(__name__)

# Put both of your numerical Telegram User IDs here:
ALLOWED_USERS = []  # e.g., [123456789, 987654321]

def is_authorized(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    return update.effective_user and update.effective_user.id in ALLOWED_USERS

# --- Database Initialization ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            title TEXT NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            location TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bucket_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            idea TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS special_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            target_date DATE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gratitude_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at DATETIME NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# --- Helper Keyboards ---
def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🗓️ This Week", callback_data="view_week"),
            InlineKeyboardButton("📆 This Month", callback_data="view_month"),
        ],
        [
            InlineKeyboardButton("🔍 Free Slots", callback_data="find_freetime"),
            InlineKeyboardButton("💡 Date Ideas", callback_data="view_bucket"),
        ],
        [
            InlineKeyboardButton("🎲 Pick For Us", callback_data="pick_date"),
            InlineKeyboardButton("🎯 Help Us Decide", callback_data="help_spin"),
        ],
        [
            InlineKeyboardButton("⏳ Countdowns", callback_data="view_countdowns"),
            InlineKeyboardButton("💌 Love Notes", callback_data="view_thanks"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Start Screen & Auto-Pinning ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    welcome_text = (
        "💕 *Wei Wei & Kay Kay's Agenda*\n\n"
        "What are we up to today?\n\n"
        "📌 *Quick Add Cheat Sheet:*\n"
        "• `/add Title | YYYY-MM-DD HH:MM - HH:MM | [Loc] | [Notes]`— insert schedule\n"
        "• `/addidea <idea>` — save date idea\n"
        "• `/adddate <event> | YYYY-MM-DD` — set a countdown\n"
        "• `/thankyou <note>` — leave love note\n"
        "• `/freetime` | — see when we're both free\n"
        "• `/spin opt1 | opt2`\n — tiebreaker spinner\n"
        "✏️ *Edit / Delete (use ID from lists):*\n"
        "• `/delevent <id>` | `/editevent <id> | Title | ...`\n"
        "• `/delidea <id>` | `/editidea <id> | <new idea>`\n"
        "• `/deldate <id>` | `/editdate <id> | Title | YYYY-MM-DD`\n"
        "• `/delnote <id>` | `/editnote <id> | <new note>`\n\n"
        "_Tap a button below to check schedule & notes!_"
    )
    
    if update.message:
        sent_msg = await update.message.reply_text(
            welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard()
        )
        try:
            await sent_msg.pin(disable_notification=True)
        except Exception:
            pass
    elif update.callback_query:
        await update.callback_query.message.edit_text(
            welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard()
        )

# ==================== SCHEDULE / EVENTS ====================

async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    user_name = update.effective_user.first_name
    raw_args = " ".join(context.args)

    parts = [p.strip() for p in raw_args.split("|")]
    if len(parts) < 2:
        await update.message.reply_text(
            "⚠️ *Format:* `/add Title | YYYY-MM-DD HH:MM - HH:MM | [Location] | [Notes]`\n"
            "Example: `/add Work | 2026-08-06 09:00 - 18:00`",
            parse_mode="Markdown"
        )
        return

    title = parts[0]
    time_part = parts[1]
    location = parts[2] if len(parts) > 2 else ""
    notes = parts[3] if len(parts) > 3 else ""

    try:
        if "-" in time_part:
            start_str, end_time_str = time_part.rsplit("-", 1)
            start_str = start_str.strip()
            end_time_str = end_time_str.strip()

            start_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
            end_time_dt = datetime.strptime(end_time_str, "%H:%M").time()
            end_time = datetime.combine(start_time.date(), end_time_dt)
        else:
            start_time = datetime.strptime(time_part.strip(), "%Y-%m-%d %H:%M")
            end_time = start_time + timedelta(hours=1)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO events (user_name, title, start_time, end_time, location, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (user_name, title, start_time.strftime("%Y-%m-%d %H:%M:%S"), end_time.strftime("%Y-%m-%d %H:%M:%S"), location, notes)
        )
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()

        formatted_time = f"{start_time.strftime('%a, %b %d @ %I:%M %p')} - {end_time.strftime('%I:%M %p')}"
        msg = f"✅ *Added (ID: {event_id}) by {user_name}!*\n📌 *{title}*\n📅 {formatted_time}"
        if location:
            msg += f"\n📍 Location: {location}"
        if notes:
            msg += f"\n📝 Notes: {notes}"

        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())
    except Exception:
        await update.message.reply_text(
            "⚠️ Invalid time format! Example:\n`/add Work | 2026-08-06 09:00 - 18:00`",
            parse_mode="Markdown"
        )

async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ *Format:* `/delevent <ID>`\nExample: `/delevent 3`", parse_mode="Markdown")
        return

    event_id = int(context.args[0])
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        await update.message.reply_text(f"🗑️ Schedule `[ID: {event_id}]` deleted!", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(f"⚠️ Schedule ID `{event_id}` not found.", parse_mode="Markdown")

async def edit_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    raw_args = " ".join(context.args)
    parts = [p.strip() for p in raw_args.split("|")]
    if len(parts) < 3 or not parts[0].isdigit():
        await update.message.reply_text(
            "⚠️ *Format:* `/editevent <ID> | Title | YYYY-MM-DD HH:MM - HH:MM | [Location] | [Notes]`\n"
            "Example: `/editevent 3 | Dinner | 2026-08-08 19:00 - 21:00 | VivoCity`",
            parse_mode="Markdown"
        )
        return

    event_id = int(parts[0])
    title = parts[1]
    time_part = parts[2]
    location = parts[3] if len(parts) > 3 else ""
    notes = parts[4] if len(parts) > 4 else ""

    try:
        if "-" in time_part:
            start_str, end_time_str = time_part.rsplit("-", 1)
            start_time = datetime.strptime(start_str.strip(), "%Y-%m-%d %H:%M")
            end_time_dt = datetime.strptime(end_time_str.strip(), "%H:%M").time()
            end_time = datetime.combine(start_time.date(), end_time_dt)
        else:
            start_time = datetime.strptime(time_part.strip(), "%Y-%m-%d %H:%M")
            end_time = start_time + timedelta(hours=1)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE events SET title=?, start_time=?, end_time=?, location=?, notes=? WHERE id=?",
            (title, start_time.strftime("%Y-%m-%d %H:%M:%S"), end_time.strftime("%Y-%m-%d %H:%M:%S"), location, notes, event_id)
        )
        updated = cursor.rowcount
        conn.commit()
        conn.close()

        if updated > 0:
            await update.message.reply_text(f"✏️ Schedule `[ID: {event_id}]` updated to *{title}*!", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text(f"⚠️ Schedule ID `{event_id}` not found.", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("⚠️ Invalid format/time. Example:\n`/editevent 3 | Dinner | 2026-08-08 19:00 - 21:00`", parse_mode="Markdown")

def get_week_text():
    now = datetime.now()
    week_end = now + timedelta(days=7)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_name, title, start_time, end_time, location, notes FROM events WHERE start_time >= ? AND start_time <= ? ORDER BY start_time ASC",
        (now.strftime("%Y-%m-%d 00:00:00"), week_end.strftime("%Y-%m-%d 23:59:59"))
    )
    rows = cursor.fetchall()

    response = "🗓️ *Weekly Preview (Next 7 Days)*\n"
    if not rows:
        response += "\n✨ No scheduled activities! Perfect time to plan a date.\n"
    else:
        current_day = ""
        for eid, user_name, title, stime_str, etime_str, loc, notes in rows:
            s_dt = datetime.strptime(stime_str, "%Y-%m-%d %H:%M:%S")
            e_dt = datetime.strptime(etime_str, "%Y-%m-%d %H:%M:%S")
            day_header = s_dt.strftime("%A, %b %d")
            
            if day_header != current_day:
                current_day = day_header
                response += f"\n📅 *{current_day}*\n"
            
            time_slot = f"{s_dt.strftime('%I:%M %p')} - {e_dt.strftime('%I:%M %p')}"
            entry = f"  • `[ID:{eid}]` `{time_slot}` - {title} _({user_name})_"
            if loc:
                entry += f" 📍_{loc}_"
            if notes:
                entry += f" 📝_{notes}_"
            response += entry + "\n"

    week_ago = now - timedelta(days=7)
    cursor.execute(
        "SELECT id, user_name, note FROM gratitude_notes WHERE created_at >= ? ORDER BY created_at DESC",
        (week_ago.strftime("%Y-%m-%d %H:%M:%S"),)
    )
    thanks_rows = cursor.fetchall()
    conn.close()

    if thanks_rows:
        response += "\n\n💌 *Love Notes This Week:*\n"
        for nid, sender, note_text in thanks_rows:
            response += f"• `[ID:{nid}]` _{sender}_: \"{note_text}\"\n"

    return response

def get_month_text():
    now = datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_name, title, start_time, end_time, location FROM events WHERE start_time >= ? AND start_time <= ? ORDER BY start_time ASC",
        (start_of_month.strftime("%Y-%m-%d %H:%M:%S"), end_of_month.strftime("%Y-%m-%d %H:%M:%S"))
    )
    rows = cursor.fetchall()
    conn.close()

    month_name = now.strftime("%B %Y")
    if not rows:
        return f"✨ No activities scheduled for *{month_name}* yet."

    response = f"📆 *Month at a Glance ({month_name})*\n\n"
    for eid, user_name, title, stime_str, etime_str, loc in rows:
        s_dt = datetime.strptime(stime_str, "%Y-%m-%d %H:%M:%S")
        e_dt = datetime.strptime(etime_str, "%Y-%m-%d %H:%M:%S")
        loc_str = f" [📍 {loc}]" if loc else ""
        response += f"• `[ID:{eid}]` *{s_dt.strftime('%b %d (%a)')}* (`{s_dt.strftime('%I:%M %p')}-{e_dt.strftime('%I:%M %p')}`): {title} _({user_name})_{loc_str}\n"
    return response

# ==================== DATE IDEAS / WISHLIST ====================

async def add_idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    user_name = update.effective_user.first_name
    idea = " ".join(context.args).strip()
    if not idea:
        await update.message.reply_text("⚠️ *Format:* `/addidea Try new cafe`", parse_mode="Markdown")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO bucket_list (user_name, idea) VALUES (?, ?)", (user_name, idea))
    idea_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await update.message.reply_text(f"💡 Added to Wishlist `[ID: {idea_id}]`: *{idea}*", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def delete_idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ *Format:* `/delidea <ID>`\nExample: `/delidea 2`", parse_mode="Markdown")
        return

    idea_id = int(context.args[0])
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bucket_list WHERE id = ?", (idea_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        await update.message.reply_text(f"🗑️ Date idea `[ID: {idea_id}]` removed!", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(f"⚠️ Idea ID `{idea_id}` not found.", parse_mode="Markdown")

async def edit_idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    raw_args = " ".join(context.args)
    if "|" not in raw_args:
        await update.message.reply_text("⚠️ *Format:* `/editidea <ID> | <new idea>`\nExample: `/editidea 2 | Go ice skating`", parse_mode="Markdown")
        return

    parts = raw_args.split("|", 1)
    if not parts[0].strip().isdigit():
        await update.message.reply_text("⚠️ Invalid ID number.", parse_mode="Markdown")
        return

    idea_id = int(parts[0].strip())
    new_idea = parts[1].strip()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE bucket_list SET idea = ? WHERE id = ?", (new_idea, idea_id))
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    if updated > 0:
        await update.message.reply_text(f"✏️ Date idea `[ID: {idea_id}]` updated to: *{new_idea}*", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(f"⚠️ Idea ID `{idea_id}` not found.", parse_mode="Markdown")

def get_bucket_text():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_name, idea FROM bucket_list")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "💡 Your Date Wishlist is empty! Use `/addidea <idea>` to add items."

    res = "💡 *Date Night Wishlist*\n\n"
    for item_id, user_name, idea in rows:
        res += f"• `[ID:{item_id}]` {idea} _(added by {user_name})_\n"
    return res

def pick_random_idea():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, idea, user_name FROM bucket_list")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "🎲 Your wishlist is empty! Add ideas first using `/addidea`."
    
    item_id, selected_idea, user_name = random.choice(rows)
    return f"🎲 *Random Date Pick:*\n\n👉 `[ID:{item_id}]` *{selected_idea}*\n_(Added by {user_name})_"

# ==================== SPECIAL DATES / COUNTDOWNS ====================

async def add_special_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    raw_args = " ".join(context.args)
    if "|" not in raw_args:
        await update.message.reply_text("⚠️ Format: `/adddate Anniversary | YYYY-MM-DD`", parse_mode="Markdown")
        return

    title, date_str = raw_args.split("|")
    title = title.strip()
    
    try:
        tdate = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO special_dates (title, target_date) VALUES (?, ?)", (title, tdate.strftime("%Y-%m-%d")))
        date_id = cursor.lastrowid
        conn.commit()
        conn.close()

        await update.message.reply_text(f"⏳ Countdown added `[ID: {date_id}]` for *{title}* on {tdate}!", parse_mode="Markdown", reply_markup=get_main_keyboard())
    except ValueError:
        await update.message.reply_text("⚠️ Invalid date format. Use `YYYY-MM-DD`.")

async def delete_special_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ *Format:* `/deldate <ID>`\nExample: `/deldate 1`", parse_mode="Markdown")
        return

    date_id = int(context.args[0])
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM special_dates WHERE id = ?", (date_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        await update.message.reply_text(f"🗑️ Countdown `[ID: {date_id}]` deleted!", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(f"⚠️ Countdown ID `{date_id}` not found.", parse_mode="Markdown")

async def edit_special_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    raw_args = " ".join(context.args)
    if "|" not in raw_args:
        await update.message.reply_text("⚠️ *Format:* `/editdate <ID> | Title | YYYY-MM-DD`\nExample: `/editdate 1 | Trip to Japan | 2026-12-15`", parse_mode="Markdown")
        return

    parts = [p.strip() for p in raw_args.split("|")]
    if not parts[0].isdigit() or len(parts) < 3:
        await update.message.reply_text("⚠️ Invalid format. Example: `/editdate 1 | Trip to Japan | 2026-12-15`", parse_mode="Markdown")
        return

    date_id = int(parts[0])
    title = parts[1]
    
    try:
        tdate = datetime.strptime(parts[2], "%Y-%m-%d").date()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE special_dates SET title = ?, target_date = ? WHERE id = ?", (title, tdate.strftime("%Y-%m-%d"), date_id))
        updated = cursor.rowcount
        conn.commit()
        conn.close()

        if updated > 0:
            await update.message.reply_text(f"✏️ Countdown `[ID: {date_id}]` updated to *{title}* on {tdate}!", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text(f"⚠️ Countdown ID `{date_id}` not found.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("⚠️ Invalid date format. Use `YYYY-MM-DD`.")

def get_countdowns_text():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, target_date FROM special_dates ORDER BY target_date ASC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "⏳ No countdowns saved. Add one using `/adddate Title | YYYY-MM-DD`."

    today = datetime.now().date()
    res = "⏳ *Special Date Countdowns*\n\n"
    for did, title, tdate_str in rows:
        tdate = datetime.strptime(tdate_str, "%Y-%m-%d").date()
        days_left = (tdate - today).days
        if days_left > 0:
            res += f"• `[ID:{did}]` *{title}*: {days_left} days left _({tdate.strftime('%b %d, %Y')})_\n"
        elif days_left == 0:
            res += f"🎉 `[ID:{did}]` *{title}* is TODAY!\n"
        else:
            res += f"• `[ID:{did}]` *{title}*: Passed {abs(days_left)} days ago\n"
    return res

# ==================== GRATITUDE / LOVE NOTES ====================

async def add_thankyou(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    user_name = update.effective_user.first_name
    note = " ".join(context.args).strip()

    if not note:
        await update.message.reply_text("⚠️ *Format:* `/thankyou Thanks for coffee today!`", parse_mode="Markdown")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO gratitude_notes (user_name, note, created_at) VALUES (?, ?, ?)",
        (user_name, note, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await update.message.reply_text(f"💌 Note `[ID: {note_id}]` saved, {user_name}!", parse_mode="Markdown", reply_markup=get_main_keyboard())

async def delete_thankyou(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ *Format:* `/delnote <ID>`\nExample: `/delnote 4`", parse_mode="Markdown")
        return

    note_id = int(context.args[0])
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gratitude_notes WHERE id = ?", (note_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        await update.message.reply_text(f"🗑️ Love note `[ID: {note_id}]` deleted!", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(f"⚠️ Note ID `{note_id}` not found.", parse_mode="Markdown")

async def edit_thankyou(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    raw_args = " ".join(context.args)
    if "|" not in raw_args:
        await update.message.reply_text("⚠️ *Format:* `/editnote <ID> | <new note>`\nExample: `/editnote 4 | Thanks for picking up groceries!`", parse_mode="Markdown")
        return

    parts = raw_args.split("|", 1)
    if not parts[0].strip().isdigit():
        await update.message.reply_text("⚠️ Invalid ID number.", parse_mode="Markdown")
        return

    note_id = int(parts[0].strip())
    new_note = parts[1].strip()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE gratitude_notes SET note = ? WHERE id = ?", (new_note, note_id))
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    if updated > 0:
        await update.message.reply_text(f"✏️ Love note `[ID: {note_id}]` updated to: \"{new_note}\"", parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(f"⚠️ Note ID `{note_id}` not found.", parse_mode="Markdown")

def get_gratitude_text():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_name, note, created_at FROM gratitude_notes ORDER BY created_at DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "💌 No love notes saved yet! Send one using `/thankyou <your note>`."

    res = "💌 *Recent Love & Gratitude Notes*\n\n"
    for nid, sender, note_text, created_at in rows:
        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        res += f"• `[ID:{nid}]` *{sender}* _({dt.strftime('%b %d')})_: \"{note_text}\"\n"
    return res

# ==================== UTILITY FUNCTIONS ====================

def calculate_free_time():
    now = datetime.now()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    results = "🔍 *Joint Free Time (Next 7 Days)*\n\n"
    for day_offset in range(7):
        target_day = now + timedelta(days=day_offset)
        day_start = target_day.replace(hour=9, minute=0, second=0)
        day_end = target_day.replace(hour=22, minute=0, second=0)
        
        cursor.execute(
            "SELECT start_time, end_time FROM events WHERE start_time >= ? AND start_time <= ? ORDER BY start_time ASC",
            (day_start.strftime("%Y-%m-%d %H:%M:%S"), day_end.strftime("%Y-%m-%d %H:%M:%S"))
        )
        busy_slots = cursor.fetchall()
        
        if not busy_slots:
            results += f"🟢 *{target_day.strftime('%a, %b %d')}*: Fully Free (9:00 AM - 10:00 PM)\n"
        else:
            results += f"🟡 *{target_day.strftime('%a, %b %d')}*: Free outside these times:\n"
            for (s_str, e_str) in busy_slots:
                s_dt = datetime.strptime(s_str, "%Y-%m-%d %H:%M:%S")
                e_dt = datetime.strptime(e_str, "%Y-%m-%d %H:%M:%S")
                results += f"   • Busy `{s_dt.strftime('%I:%M %p')} - {e_dt.strftime('%I:%M %p')}`\n"
                
    conn.close()
    return results

async def spin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    raw_args = " ".join(context.args)
    if not raw_args or "|" not in raw_args:
        await update.message.reply_text(
            "🎰 *How to use /spin:*\n`/spin Italian | Sushi | Burgers`",
            parse_mode="Markdown"
        )
        return

    options = [opt.strip() for opt in raw_args.split("|") if opt.strip()]
    if len(options) < 2:
        await update.message.reply_text("⚠️ Please provide at least 2 choices separated by `|`.")
        return

    chosen = random.choice(options)
    await update.message.reply_text(
        f"🎰 *Decision Spinner*\n\nOptions: {', '.join(options)}\n\n✨ *The Spinner Chose:* 👉 *{chosen}*",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# --- Callback Handler ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "view_week":
        text = get_week_text()
    elif data == "view_month":
        text = get_month_text()
    elif data == "find_freetime":
        text = calculate_free_time()
    elif data == "view_bucket":
        text = get_bucket_text()
    elif data == "pick_date":
        text = pick_random_idea()
    elif data == "help_spin":
        text = "🎯 *Decision Spinner*\n\nType `/spin Option 1 | Option 2 | Option 3` in the chat to let the bot decide!"
    elif data == "view_countdowns":
        text = get_countdowns_text()
    elif data == "view_thanks":
        text = get_gratitude_text()
    else:
        text = "Option not recognized."

    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# --- Build Telegram Application & Handlers ---
ptb_app = ApplicationBuilder().token(TOKEN).build()

# Start & Help
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("help", start))

# Events / Schedule
ptb_app.add_handler(CommandHandler("add", add_event))
ptb_app.add_handler(CommandHandler("delevent", delete_event))
ptb_app.add_handler(CommandHandler("editevent", edit_event))

# Wishlist / Date Ideas
ptb_app.add_handler(CommandHandler("addidea", add_idea))
ptb_app.add_handler(CommandHandler("delidea", delete_idea))
ptb_app.add_handler(CommandHandler("editidea", edit_idea))

# Special Dates / Countdowns
ptb_app.add_handler(CommandHandler("adddate", add_special_date))
ptb_app.add_handler(CommandHandler("deldate", delete_special_date))
ptb_app.add_handler(CommandHandler("editdate", edit_special_date))

# Gratitude / Love Notes
ptb_app.add_handler(CommandHandler("thankyou", add_thankyou))
ptb_app.add_handler(CommandHandler("delnote", delete_thankyou))
ptb_app.add_handler(CommandHandler("editnote", edit_thankyou))

# Utilities
ptb_app.add_handler(CommandHandler("spin", spin_decision))
ptb_app.add_handler(CommandHandler("freetime", lambda u, c: u.message.reply_text(calculate_free_time(), parse_mode="Markdown")))

# Callbacks
ptb_app.add_handler(CallbackQueryHandler(button_callback))

# --- Single Persistent Event Loop for Instant Webhook Responses ---
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(ptb_app.initialize())

# --- Flask Routes for Webhook Server ---
@flask_app.route("/", methods=["GET"])
def index():
    return "Bot Web App is live 24/7!", 200

@flask_app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(force=True), ptb_app.bot)
            loop.run_until_complete(ptb_app.process_update(update))
            return "ok", 200
        except Exception as e:
            return str(e), 500
    return "error", 400
