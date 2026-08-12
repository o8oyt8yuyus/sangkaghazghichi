# botvakhar.py - نسخه نهایی با رفع کامل باگ‌های بازی و نمایش صحیح نتایج
import telebot
from telebot import types
import sqlite3
import threading
import re
import json
import base64
import os
from collections import defaultdict
import itertools
from datetime import datetime, date, timedelta
import time  # <--- اضافه شده برای retry

TOKEN = '8385965292:AAF9YwGbGHRZ35FU4-4oN7-JXsR2mfDJT9A'
ADMIN_IDS = [8318255695]
ADMIN_USERNAMES = ['@RPSArena_Sup']
SECRET_ADMIN_COMMAND = '/AlirezaaghoztabestanholoalipraliPro'

DEFAULT_CHANNEL_LINK = 'https://t.me/RPSarenaOfficial1'
DEFAULT_CHANNEL_USERNAME = '@RPSarenaOfficial1'

CARD_NUMBER = '6219861851166826'
CARD_OWNER = 'سید محمد مهدی حسنی'

WITHDRAW_RATE = 1
DAILY_GAME_LIMIT = 10

bot = telebot.TeleBot(TOKEN)

# ---------- دیتابیس ----------
def add_column_if_not_exists(conn, table, column, column_type):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        conn.commit()

def init_db():
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        total_invites INTEGER DEFAULT 0,
        card_number TEXT,
        registered_at TEXT,
        level INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0
    )''')
    try:
        c.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
    except:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player1_id INTEGER,
        player2_id INTEGER,
        bet_amount INTEGER,
        status TEXT,
        winner_id INTEGER,
        p1_choice TEXT,
        p2_choice TEXT,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount_toman INTEGER,
        card_number TEXT,
        status TEXT,
        created_at TEXT,
        reject_reason TEXT
    )''')
    add_column_if_not_exists(conn, 'withdraw_requests', 'reject_reason', 'TEXT')
    
    c.execute('''CREATE TABLE IF NOT EXISTS purchase_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount_toman INTEGER,
        coins INTEGER,
        status TEXT,
        receipt_text TEXT,
        receipt_photo_id TEXT,
        created_at TEXT,
        reject_reason TEXT
    )''')
    add_column_if_not_exists(conn, 'purchase_requests', 'reject_reason', 'TEXT')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_games (
        user_id INTEGER,
        game_date TEXT,
        count INTEGER,
        PRIMARY KEY (user_id, game_date)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_withdrawals (
        user_id INTEGER,
        withdraw_date TEXT,
        total_amount INTEGER,
        PRIMARY KEY (user_id, withdraw_date)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS required_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_link TEXT NOT NULL,
        channel_username TEXT NOT NULL,
        added_at TEXT,
        active INTEGER DEFAULT 1
    )''')
    
    # تنظیم کانال پیش‌فرض
    c.execute("SELECT id FROM required_channels")
    if not c.fetchone():
        now = datetime.now().isoformat()
        c.execute("INSERT INTO required_channels (channel_link, channel_username, added_at, active) VALUES (?, ?, ?, ?)",
                  (DEFAULT_CHANNEL_LINK, DEFAULT_CHANNEL_USERNAME, now, 1))
    else:
        # اگر کانال دیگری وجود دارد، آن را حذف و فقط پیش‌فرض را نگه دار
        c.execute("DELETE FROM required_channels")
        now = datetime.now().isoformat()
        c.execute("INSERT INTO required_channels (channel_link, channel_username, added_at, active) VALUES (?, ?, ?, ?)",
                  (DEFAULT_CHANNEL_LINK, DEFAULT_CHANNEL_USERNAME, now, 1))

    c.execute("SELECT value FROM settings WHERE key='card_number'")
    row = c.fetchone()
    if row and row[0] != CARD_NUMBER:
        c.execute("UPDATE settings SET value=? WHERE key='card_number'", (CARD_NUMBER,))
    elif not row:
        c.execute("INSERT INTO settings (key, value) VALUES ('card_number', ?)", (CARD_NUMBER,))

    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('card_owner', ?)", (CARD_OWNER,))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('min_withdraw', '10000')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('max_withdraw', '250000')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('daily_game_limit', ?)", (str(DAILY_GAME_LIMIT),))
    
    welcome = '''🌟 به ربات **پاداش و جوایز** خوش آمدید!
─ ─ ─ ─ ─ ─ ─ ─ ─ ─
در این ربات می‌توانید با انجام بازی **دوئل سنگ کاغذ قیچی** سکه جمع‌آوری کرده و از جوایز ویژه بهره‌مند شوید.

📢 کانال رسمی: {https://t.me/RPSarenaOfficial1}'''
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', ?)", (welcome,))
    
    help_txt = '''📖 **راهنما و پشتیبانی**

به بخش راهنما خوش آمدید. در اینجا پاسخ سوالات پرتکرار را گردآوری کرده‌ایم.

---
💰 **درآمد پلتفرم از کجاست؟**
• کارمزد ۱۰٪ از برد کاربران
• همکاری با اسپانسرها و شرکای تجاری
هیچ هزینه پنهانی وجود ندارد.
• پس از اطمینان کامل، می‌توانید حساب خود را شارژ کنید (اختیاری).

🛡️ **امنیت واریز و برداشت**
• تمام تراکنش‌ها خودکار و بدون دخالت انسانی انجام می‌شود.
• قابلیت پیگیری دقیق تراکنش‌ها.

🎮 **چگونه بازی کنیم؟**
۱. گزینه «شروع بازی» را انتخاب کنید.
۲. مبلغ دوئل را مشخص کنید.
۳. منتظر پیدا شدن رقیب بمانید.
۴. در زمان ۶۰ ثانیه‌ای، سنگ/کاغذ/قیچی خود را انتخاب کنید.

⏱️ **زمان واریز و برداشت**
• واریز (خرید سکه): پس از تأیید ادمین، معمولاً ظرف ۱ ساعت
• برداشت: پس از تأیید ادمین، معمولاً بین ۱ تا ۲۴ ساعت

📞 **پشتیبانی**
در صورت هرگونه مشکل، از طریق دکمه زیر با ما در ارتباط باشید.

🤝 **هدف ما**
ایجاد یک تجربه سالم، شفاف و منصفانه برای همه کاربران.'''
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('help_text', ?)", (help_txt,))
    conn.commit()
    conn.close()

init_db()

# ---------- وضعیت‌ها ----------
user_states = {}
waiting_queues = defaultdict(list)
game_sessions = {}

cross_bet_proposals = {}
user_wait_timers = {}
matching_lock = threading.Lock()
_proposal_id_seq = itertools.count(1)

STATE_MAIN = 'main'
STATE_SELECTING_BET = 'selecting_bet'
STATE_SELECTING_MODE = 'selecting_mode'
STATE_WAITING_OPPONENT = 'waiting_opponent'
STATE_PLAYING = 'playing'
STATE_WITHDRAW_AMOUNT = 'withdraw_amount'
STATE_WITHDRAW_CARD = 'withdraw_card'
STATE_PURCHASE_AMOUNT = 'purchase_amount'
STATE_PURCHASE_RECEIPT = 'purchase_receipt'
STATE_ADMIN_ADD_BALANCE = 'admin_add_balance'
STATE_ADMIN_SET_CARD = 'admin_set_card'
STATE_ADMIN_BROADCAST = 'admin_broadcast'
STATE_ADMIN_PRIVATE_MSG = 'admin_private_msg'
STATE_ADMIN_REJECT_REASON = 'admin_reject_reason'
STATE_ADMIN_EDIT_SETTING = 'admin_edit_setting'
STATE_REGISTER_CARD = 'register_card'
STATE_ADMIN_REPLY_USER = 'admin_reply_user'
STATE_ADMIN_BAN_USER = 'admin_ban_user'
STATE_ADMIN_VIEW_USER = 'admin_view_user'
STATE_ADMIN_QUICK_ADD_BALANCE = 'admin_quick_add_balance'
STATE_ADMIN_CHANGE_BALANCE = 'admin_change_balance'
STATE_ADMIN_CHANGE_BALANCE_AMOUNT = 'admin_change_balance_amount'
STATE_ADMIN_ADD_CHANNEL = 'admin_add_channel'
STATE_ADMIN_REMOVE_CHANNEL = 'admin_remove_channel'
STATE_ADMIN_USER_STATS_INPUT = 'admin_user_stats_input'
STATE_ADMIN_USER_STATS_VIEW = 'admin_user_stats_view'
STATE_ADMIN_STATS_ADD_BALANCE = 'admin_stats_add_balance'
STATE_ADMIN_STATS_CHANGE_BALANCE = 'admin_stats_change_balance'

# ---------- توابع کمکی ----------
def is_admin(user_id, username=None):
    if user_id in ADMIN_IDS:
        return True
    if username and username in ADMIN_USERNAMES:
        return True
    return False

def get_required_channels(active_only=True):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    if active_only:
        c.execute("SELECT id, channel_link, channel_username, added_at FROM required_channels WHERE active=1 ORDER BY id")
    else:
        c.execute("SELECT id, channel_link, channel_username, added_at, active FROM required_channels ORDER BY id")
    rows = c.fetchall()
    conn.close()
    channels = []
    for row in rows:
        if active_only:
            channels.append({
                'id': row[0],
                'link': row[1],
                'username': row[2],
                'added_at': row[3]
            })
        else:
            channels.append({
                'id': row[0],
                'link': row[1],
                'username': row[2],
                'added_at': row[3],
                'active': row[4]
            })
    return channels

def add_required_channel(link, username):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("INSERT INTO required_channels (channel_link, channel_username, added_at, active) VALUES (?, ?, ?, ?)",
              (link, username, now, 1))
    conn.commit()
    conn.close()

def remove_required_channel(channel_id):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("DELETE FROM required_channels WHERE id=?", (channel_id,))
    conn.commit()
    conn.close()

def toggle_channel_active(channel_id, active):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("UPDATE required_channels SET active=? WHERE id=?", (1 if active else 0, channel_id))
    conn.commit()
    conn.close()

def get_user(user_id, retries=3, delay=0.1):
    """
    دریافت اطلاعات کاربر با تلاش مجدد در صورت بروز خطای دیتابیس.
    """
    for attempt in range(retries):
        try:
            conn = sqlite3.connect('duel_bot.db')
            c = conn.cursor()
            c.execute("SELECT user_id, username, balance, total_invites, card_number, registered_at, level, banned FROM users WHERE user_id=?", (int(user_id),))
            row = c.fetchone()
            conn.close()
            if row:
                return {
                    'user_id': row[0],
                    'username': row[1],
                    'balance': row[2],
                    'total_invites': row[3],
                    'card_number': row[4],
                    'registered_at': row[5],
                    'level': row[6],
                    'banned': row[7]
                }
            else:
                return None
        except Exception as e:
            print(f"⚠️ خطا در get_user (تلاش {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                print(f"❌ خطای نهایی در get_user: {e}")
                return None
    return None

def create_user(user_id, username, ref=None):
    try:
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("INSERT OR IGNORE INTO users (user_id, username, balance, total_invites, card_number, registered_at, level, banned) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (int(user_id), username, 0, 0, None, now, 0, 0))
        conn.commit()
        conn.close()
        if ref:
            ref_user = get_user(int(ref))
            if ref_user and ref_user['user_id'] != user_id and not is_banned(int(ref)):
                conn = sqlite3.connect('duel_bot.db')
                c = conn.cursor()
                c.execute("UPDATE users SET total_invites = total_invites + 1, level = level + 1 WHERE user_id=?", (int(ref),))
                conn.commit()
                conn.close()
                bot.send_message(int(ref),
                    f"🎉 یک دوست جدید از طریق دعوت شما ثبت‌نام کرد!\n"
                    f"⭐ ۱ سطح به سطح شما اضافه شد.\n"
                    f"👥 تعداد دعوت‌های شما: {get_user(int(ref))['total_invites']}")
        welcome_text = get_setting('welcome_text') or f"🌟 به ربات **پاداش و جوایز** خوش آمدید!\n─ ─ ─ ─ ─ ─ ─ ─ ─ ─\nدر این ربات می‌توانید با انجام بازی **دوئل سنگ کاغذ قیچی** سکه جمع‌آوری کرده و از جوایز ویژه بهره‌مند شوید.\n\n📢 کانال رسمی: {DEFAULT_CHANNEL_LINK}"
        bot.send_message(user_id, welcome_text, parse_mode='Markdown')
    except Exception as e:
        print(f"❌ خطا در create_user برای کاربر {user_id}: {e}")

def ensure_user_exists(user_id, username=None):
    user = get_user(user_id)
    if not user:
        if username is None:
            username = str(user_id)
        create_user(user_id, username)
        user = get_user(user_id)
    return user

def get_non_member_channels(user_id):
    if user_id in ADMIN_IDS:
        return []
    ensure_user_exists(user_id, str(user_id))
    channels = get_required_channels(active_only=True)
    non_member = []
    for ch in channels:
        try:
            chat_member = bot.get_chat_member(ch['username'], user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                non_member.append(ch)
        except Exception:
            non_member.append(ch)
    return non_member

def is_member_all_channels(user_id):
    if user_id in ADMIN_IDS:
        return True
    ensure_user_exists(user_id, str(user_id))
    channels = get_required_channels(active_only=True)
    if not channels:
        return True
    for ch in channels:
        try:
            chat_member = bot.get_chat_member(ch['username'], user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

def is_banned(user_id):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

def update_balance(user_id, amount):
    try:
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (int(amount), int(user_id)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"خطا در update_balance: {e}")

def set_balance(user_id, new_balance):
    try:
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET balance = ? WHERE user_id=?", (int(new_balance), int(user_id)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"خطا در set_balance: {e}")

def get_balance(user_id):
    user = get_user(user_id)
    return user['balance'] if user else 0

def get_or_create_user(user_id, username):
    user = get_user(user_id)
    if not user:
        create_user(user_id, username)
        user = get_user(user_id)
    return user

def get_setting(key):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    try:
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM games WHERE (player1_id=? OR player2_id=?) AND status='finished'", (int(user_id), int(user_id)))
        total_games = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM games WHERE winner_id=? AND status='finished'", (int(user_id),))
        wins = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM games WHERE (player1_id=? OR player2_id=?) AND status='finished' AND winner_id IS NULL", (int(user_id), int(user_id)))
        draws = c.fetchone()[0]
        loses = total_games - wins - draws
        c.execute("SELECT level FROM users WHERE user_id=?", (int(user_id),))
        row = c.fetchone()
        invite_level = row[0] if row and row[0] else 0
        win_level = min(150, wins // 5)
        level = win_level + invite_level
        conn.close()
        return total_games, wins, loses, draws, level
    except Exception as e:
        print(f"خطا در get_user_stats: {e}")
        return 0, 0, 0, 0, 0

def get_daily_games_count(user_id):
    today = date.today().isoformat()
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("SELECT count FROM daily_games WHERE user_id=? AND game_date=?", (int(user_id), today))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def increment_daily_games(user_id):
    today = date.today().isoformat()
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO daily_games (user_id, game_date, count) VALUES (?, ?, 1) ON CONFLICT(user_id, game_date) DO UPDATE SET count = count + 1", (int(user_id), today))
    conn.commit()
    conn.close()

def get_daily_game_limit():
    val = get_setting('daily_game_limit')
    try:
        return int(val) if val is not None else DAILY_GAME_LIMIT
    except (TypeError, ValueError):
        return DAILY_GAME_LIMIT

def can_play_game(user_id):
    return get_daily_games_count(user_id) < get_daily_game_limit()

def get_daily_withdrawal_total(user_id):
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("SELECT COALESCE(SUM(amount_toman), 0) FROM withdraw_requests WHERE user_id=? AND status='approved' AND created_at > ?", (int(user_id), cutoff))
    total = c.fetchone()[0]
    conn.close()
    return total

def build_user_profile_text(target_uid):
    user_info = get_user(target_uid)
    if not user_info:
        return None
    total_games, wins, loses, draws, level = get_user_stats(target_uid)
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM purchase_requests WHERE user_id=? AND status='pending'", (int(target_uid),))
    pending_purchases = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdraw_requests WHERE user_id=? AND status='pending'", (int(target_uid),))
    pending_withdraws = c.fetchone()[0]
    conn.close()
    ban_status = "🚫 بله (مسدود)" if user_info['banned'] else "✅ خیر"
    card = user_info['card_number'] or "ثبت نشده"
    registered = user_info['registered_at'][:10] if user_info['registered_at'] else "نامشخص"
    username_line = f"@{user_info['username']}" if user_info['username'] else "ثبت نشده"
    text = (
        f"👤 **پروفایل کاربر**\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        f"🆔 شناسه: `{target_uid}`\n"
        f"📛 نام کاربری: {username_line}\n"
        f"📅 تاریخ عضویت: {registered}\n"
        f"⭐ سطح: {level}\n"
        f"🪙 موجودی: **{user_info['balance']:,} سکه**\n"
        f"👥 دعوت‌های موفق: {user_info['total_invites']}\n"
        f"🎮 تعداد دوئل‌ها: {total_games} (🏆 {wins} برد | 🤝 {draws} مساوی | 📉 {loses} باخت)\n"
        f"💳 شماره کارت: `{card}`\n"
        f"⛔ وضعیت مسدودیت: {ban_status}\n"
        f"📋 خریدهای در انتظار: {pending_purchases}\n"
        f"📋 برداشت‌های در انتظار: {pending_withdraws}"
    )
    return text

def get_user_detailed_stats(target_uid):
    user_info = get_user(target_uid)
    if not user_info:
        return None
    total_games, wins, loses, draws, level = get_user_stats(target_uid)
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    
    c.execute("SELECT id, amount_toman, coins, status, created_at, reject_reason, receipt_text FROM purchase_requests WHERE user_id=? ORDER BY created_at DESC", (int(target_uid),))
    purchases = c.fetchall()
    total_purchase_coins = sum(p[2] for p in purchases if p[3] == 'approved')
    total_purchase_amount = sum(p[1] for p in purchases if p[3] == 'approved')
    pending_purchases = [p for p in purchases if p[3] == 'pending']
    approved_purchases = [p for p in purchases if p[3] == 'approved']
    rejected_purchases = [p for p in purchases if p[3] == 'rejected']
    
    c.execute("SELECT id, amount_toman, card_number, status, created_at, reject_reason FROM withdraw_requests WHERE user_id=? ORDER BY created_at DESC", (int(target_uid),))
    withdraws = c.fetchall()
    total_withdraw_amount = sum(w[1] for w in withdraws if w[3] == 'approved')
    pending_withdraws = [w for w in withdraws if w[3] == 'pending']
    approved_withdraws = [w for w in withdraws if w[3] == 'approved']
    rejected_withdraws = [w for w in withdraws if w[3] == 'rejected']
    
    conn.close()
    
    stats = {
        'user': user_info,
        'total_games': total_games,
        'wins': wins,
        'draws': draws,
        'loses': loses,
        'level': level,
        'purchases': purchases,
        'total_purchase_coins': total_purchase_coins,
        'total_purchase_amount': total_purchase_amount,
        'pending_purchases': pending_purchases,
        'approved_purchases': approved_purchases,
        'rejected_purchases': rejected_purchases,
        'withdraws': withdraws,
        'total_withdraw_amount': total_withdraw_amount,
        'pending_withdraws': pending_withdraws,
        'approved_withdraws': approved_withdraws,
        'rejected_withdraws': rejected_withdraws
    }
    return stats

def format_detailed_stats(stats):
    if not stats:
        return "❌ کاربر یافت نشد."
    u = stats['user']
    ban_status = "🚫 مسدود" if u['banned'] else "✅ فعال"
    card = u['card_number'] or "ثبت نشده"
    registered = u['registered_at'][:10] if u['registered_at'] else "نامشخص"
    username_line = f"@{u['username']}" if u['username'] else "ثبت نشده"
    text = (
        f"📊 **آمار کامل کاربر**\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        f"🆔 شناسه: `{u['user_id']}`\n"
        f"📛 نام کاربری: {username_line}\n"
        f"📅 تاریخ عضویت: {registered}\n"
        f"⭐ سطح: {stats['level']}\n"
        f"🪙 موجودی: **{u['balance']:,} سکه**\n"
        f"👥 دعوت‌های موفق: {u['total_invites']}\n"
        f"💳 شماره کارت: `{card}`\n"
        f"⛔ وضعیت: {ban_status}\n\n"
        f"🎮 **آمار بازی‌ها**\n"
        f"   کل: {stats['total_games']} | 🏆 برد: {stats['wins']} | 🤝 مساوی: {stats['draws']} | 📉 باخت: {stats['loses']}\n\n"
        f"🪙 **خریدها**\n"
        f"   تعداد کل: {len(stats['purchases'])} (تأییدشده: {len(stats['approved_purchases'])} | در انتظار: {len(stats['pending_purchases'])} | ردشده: {len(stats['rejected_purchases'])})\n"
        f"   مجموع سکه خریداری‌شده: {stats['total_purchase_coins']:,} سکه\n"
        f"   مجموع مبلغ خرید: {stats['total_purchase_amount']:,} تومان\n\n"
        f"🏦 **برداشت‌ها**\n"
        f"   تعداد کل: {len(stats['withdraws'])} (تأییدشده: {len(stats['approved_withdraws'])} | در انتظار: {len(stats['pending_withdraws'])} | ردشده: {len(stats['rejected_withdraws'])})\n"
        f"   مجموع مبلغ برداشت: {stats['total_withdraw_amount']:,} سکه (معادل {stats['total_withdraw_amount']:,} تومان)\n"
    )
    if stats['purchases']:
        text += f"\n📋 **آخرین خریدها (حداکثر ۱۰):**\n"
        for p in stats['purchases'][:10]:
            status_map = {'pending': '⏳ در انتظار', 'approved': '✅ تأیید', 'rejected': '❌ رد'}
            status = status_map.get(p[3], p[3])
            date = p[4][:10] if p[4] else 'نامشخص'
            reason = f" (دلیل: {p[5]})" if p[5] else ""
            text += f"   🆔 {p[0]} | {p[1]:,} تومان → {p[2]:,} سکه | {status} | {date}{reason}\n"
    if stats['withdraws']:
        text += f"\n🏦 **آخرین برداشت‌ها (حداکثر ۱۰):**\n"
        for w in stats['withdraws'][:10]:
            status_map = {'pending': '⏳ در انتظار', 'approved': '✅ تأیید', 'rejected': '❌ رد'}
            status = status_map.get(w[3], w[3])
            date = w[4][:10] if w[4] else 'نامشخص'
            reason = f" (دلیل: {w[5]})" if w[5] else ""
            text += f"   🆔 {w[0]} | {w[1]:,} سکه | کارت: {w[2]} | {status} | {date}{reason}\n"
    return text

def admin_stats_keyboard(target_uid):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    user = get_user(target_uid)
    is_banned_status = user['banned'] == 1 if user else False
    ban_label = "✅ آن‌بن" if is_banned_status else "🚫 بن"
    keyboard.add(
        types.InlineKeyboardButton(ban_label, callback_data=f'admin_stats_ban_{target_uid}', style='danger' if not is_banned_status else 'success'),
        types.InlineKeyboardButton("➕ افزایش موجودی", callback_data=f'admin_stats_addbal_{target_uid}', style='success'),
        types.InlineKeyboardButton("🔄 تغییر موجودی", callback_data=f'admin_stats_changebal_{target_uid}', style='primary'),
        types.InlineKeyboardButton("📩 ارسال پیام", callback_data=f'admin_reply_user_{target_uid}', style='primary')
    )
    keyboard.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin_back', style='danger'))
    return keyboard

# ============================================================
#  تابع ارسال داده به مینی‌اپ
# ============================================================
def send_to_miniapp(user_id, data, query_id=None):
    try:
        if query_id:
            bot.answer_web_app_query(query_id, json.dumps(data))
            print(f"✅ پاسخ با answer_web_app_query به {user_id} ارسال شد")
            return True
    except Exception as e:
        print(f"⚠️ خطا در answer_web_app_query: {e}")
    
    try:
        msg = f"DATA:{json.dumps(data)}"
        sent = bot.send_message(user_id, msg, disable_notification=True)
        threading.Timer(2.0, lambda: bot.delete_message(user_id, sent.message_id)).start()
        print(f"✅ پاسخ با DATA: به {user_id} ارسال شد")
        return True
    except Exception as e:
        print(f"⚠️ خطا در ارسال به مینی‌اپ {user_id}: {e}")
        return False

# ============================================================
#  هندلر اصلی مینی‌اپ (بدون تغییر)
# ============================================================
@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.reply_to(message, "⛔ شما توسط ادمین مسدود شده‌اید. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.")
        return
    try:
        data = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        bot.reply_to(message, "❌ داده‌های ارسال شده نامعتبر است.")
        return

    action = data.get('action')
    query_id = message.web_app_data.query_id

    if action == 'get_user_data':
        user = get_user(user_id)
        stats = get_user_stats(user_id)
        today_games = get_daily_games_count(user_id)
        response = {
            'action': 'user_data',
            'user_id': user_id,
            'username': user['username'] if user else '',
            'first_name': message.from_user.first_name,
            'balance': user['balance'] if user else 0,
            'wins': stats[1],
            'draws': stats[3],
            'loses': stats[2],
            'today_games': today_games,
            'level': user['level'] if user else 0,
            'total_invites': user['total_invites'] if user else 0
        }
        send_to_miniapp(user_id, response, query_id)
        return

    if action == 'graphic_start_duel':
        bet_amount = data.get('bet_amount', 5000)
        rounds = data.get('rounds', 3)
        if rounds not in [3, 5, 7]:
            rounds = 3
        if not can_play_game(user_id):
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': f'⛔ شما امروز {get_daily_game_limit()} دوئل انجام داده‌اید!',
                'reset': True
            }, query_id)
            return
        balance = get_balance(user_id)
        if balance < bet_amount:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': f'❌ موجودی کافی نیست! ({balance:,} سکه)',
                'reset': True
            }, query_id)
            return
        update_balance(user_id, -bet_amount)
        increment_daily_games(user_id)
        waiting_queues[(rounds, bet_amount)].append(user_id)
        user_states[user_id] = {'state': STATE_WAITING_OPPONENT, 'bet_amount': bet_amount, 'mode': rounds, 'from_graphic': True}
        send_to_miniapp(user_id, {
            'action': 'graphic_waiting',
            'message': '⏳ در حال پیدا کردن حریف...'
        }, query_id)
        match_players()
        schedule_cross_bet_check(user_id, rounds, bet_amount)
        return

    if action == 'graphic_choice':
        choice = data.get('choice')
        game_id = data.get('game_id')
        if not game_id:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': '❌ شناسه بازی نامعتبر!'
            }, query_id)
            return
        game = game_sessions.get(game_id)
        if not game:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': '⏰ زمان بازی تمام شد!'
            }, query_id)
            return
        if game['status'] != 'active':
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': '⚠️ بازی به پایان رسیده!'
            }, query_id)
            return
        if game['player1_id'] == user_id:
            if game['p1_chosen']:
                send_to_miniapp(user_id, {
                    'action': 'graphic_error',
                    'message': '✅ قبلاً انتخاب کردید!'
                }, query_id)
                return
            game['p1_choice'] = choice
            game['p1_chosen'] = True
        elif game['player2_id'] == user_id:
            if game['p2_chosen']:
                send_to_miniapp(user_id, {
                    'action': 'graphic_error',
                    'message': '✅ قبلاً انتخاب کردید!'
                }, query_id)
                return
            game['p2_choice'] = choice
            game['p2_chosen'] = True
        else:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': '⚠️ شما در این بازی نیستید!'
            }, query_id)
            return
        send_to_miniapp(user_id, {
            'action': 'graphic_choice_received',
            'message': '✅ انتخاب ثبت شد. منتظر حریف...'
        }, query_id)
        if game.get('p1_chosen') and game.get('p2_chosen'):
            if game.get('round_timer'):
                game['round_timer'].cancel()
                game['round_timer'] = None
            resolve_round(game_id)
        return

    if action == 'graphic_cancel_duel':
        game_id = data.get('game_id')
        if game_id and game_id in game_sessions:
            game = game_sessions[game_id]
            bet = game['bet_amount']
            update_balance(user_id, bet)
            for key, queue in waiting_queues.items():
                if user_id in queue:
                    queue.remove(user_id)
                    break
            opponent = game['player2_id'] if game['player1_id'] == user_id else game['player1_id']
            if opponent:
                send_to_miniapp(opponent, {'action': 'graphic_error', 'message': '❌ حریف شما دوئل را لغو کرد. سکه‌ها به حساب شما بازگشت.'})
                update_balance(opponent, bet)
            del game_sessions[game_id]
            if user_id in user_states:
                user_states[user_id] = {'state': STATE_MAIN}
            if opponent and opponent in user_states:
                user_states[opponent] = {'state': STATE_MAIN}
            send_to_miniapp(user_id, {
                'action': 'graphic_cancel_success',
                'message': '❌ دوئل لغو شد.'
            }, query_id)
        else:
            removed = cancel_user_waiting(user_id)
            if removed:
                user_states[user_id] = {'state': STATE_MAIN}
                send_to_miniapp(user_id, {
                    'action': 'graphic_cancel_success',
                    'message': '❌ جستجوی حریف لغو شد.'
                }, query_id)
            else:
                send_to_miniapp(user_id, {
                    'action': 'graphic_error',
                    'message': '⏳ شما در صف نیستید!'
                }, query_id)
        return

    if action == 'get_card_number':
        card = get_setting('card_number') or CARD_NUMBER
        send_to_miniapp(user_id, {
            'action': 'card_number',
            'card_number': card
        }, query_id)
        return

    if action == 'get_withdraw_settings':
        user = get_user(user_id)
        min_w = int(get_setting('min_withdraw') or 10000)
        max_w = int(get_setting('max_withdraw') or 250000)
        send_to_miniapp(user_id, {
            'action': 'withdraw_settings',
            'min_withdraw': min_w,
            'max_withdraw': max_w,
            'card_number': user['card_number'] if user else ''
        }, query_id)
        return

    if action == 'purchase_request':
        amount = data.get('amount', 0)
        receipt_text = data.get('receipt_text', '')
        receipt_base64 = data.get('receipt_base64', '')
        has_photo = bool(receipt_base64)

        if amount < 5000:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': '❌ حداقل خرید ۵,۰۰۰ سکه است!'
            }, query_id)
            return

        receipt_path = None
        if receipt_base64:
            try:
                image_data = base64.b64decode(receipt_base64)
                os.makedirs('receipts', exist_ok=True)
                filename = f"receipts/{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                with open(filename, 'wb') as f:
                    f.write(image_data)
                receipt_path = filename
            except Exception as e:
                print(f"⚠️ خطا در ذخیره رسید: {e}")

        coins = amount
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("INSERT INTO purchase_requests (user_id, amount_toman, coins, status, receipt_text, receipt_photo_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (int(user_id), amount, coins, 'pending', receipt_text, receipt_path, now))
        request_id = c.lastrowid
        conn.commit()
        conn.close()

        user_info = get_user(user_id)
        username_line = f"@{user_info['username']}" if user_info['username'] else "ثبت نشده"
        admin_text = (
            f"📩 خرید جدید (از مینی‌اپ)\n"
            f"🆔 شماره درخواست: {request_id}\n"
            f"👤 نام کاربری: {username_line}\n"
            f"🆔 آیدی کاربر: {user_id}\n"
            f"💰 {amount:,} تومان\n"
            f"🪙 {coins:,} سکه\n"
            f"📝 {receipt_text or 'بدون متن'}"
        )
        if receipt_path:
            try:
                with open(receipt_path, 'rb') as f:
                    bot.send_photo(ADMIN_IDS[0], f, caption=admin_text, reply_markup=admin_purchase_keyboard(request_id))
            except:
                bot.send_message(ADMIN_IDS[0], admin_text, reply_markup=admin_purchase_keyboard(request_id))
        else:
            bot.send_message(ADMIN_IDS[0], admin_text, reply_markup=admin_purchase_keyboard(request_id))

        send_to_miniapp(user_id, {
            'action': 'purchase_request_sent',
            'request_id': request_id,
            'message': '✅ درخواست خرید ثبت شد. منتظر تأیید ادمین...'
        }, query_id)
        return

    if action == 'withdraw_request':
        card_number = data.get('card_number', '').replace(' ', '')
        amount = data.get('amount', 0)

        if len(card_number) != 16 or not card_number.isdigit():
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': '❌ شماره کارت ۱۶ رقم باید باشد!'
            }, query_id)
            return

        min_w = int(get_setting('min_withdraw') or 10000)
        max_w = int(get_setting('max_withdraw') or 250000)
        balance = get_balance(user_id)

        if amount < min_w:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': f'❌ حداقل {min_w:,} سکه!'
            }, query_id)
            return
        if amount > max_w:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': f'❌ حداکثر {max_w:,} سکه!'
            }, query_id)
            return
        if amount > balance:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': f'❌ موجودی شما {balance:,} سکه است!'
            }, query_id)
            return
        daily_used = get_daily_withdrawal_total(user_id)
        if daily_used + amount > max_w:
            remaining = max_w - daily_used
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': f'❌ امروز {daily_used:,} سکه برداشت کرده‌اید. فقط {remaining:,} سکه دیگر می‌توانید برداشت کنید.'
            }, query_id)
            return

        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("INSERT INTO withdraw_requests (user_id, amount_toman, card_number, status, created_at) VALUES (?, ?, ?, ?, ?)",
                  (int(user_id), amount, card_number, 'pending', now))
        request_id = c.lastrowid
        conn.commit()
        conn.close()

        user_info = get_user(user_id)
        username_line = f"@{user_info['username']}" if user_info['username'] else "ثبت نشده"
        admin_text = (
            f"📩 برداشت جدید (از مینی‌اپ)\n"
            f"🆔 شماره درخواست: {request_id}\n"
            f"👤 نام کاربری: {username_line}\n"
            f"🆔 آیدی کاربر: {user_id}\n"
            f"💰 {amount:,} سکه (معادل {amount:,} تومان)\n"
            f"💳 {card_number}"
        )
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, admin_text, reply_markup=admin_withdraw_keyboard(request_id))
            except:
                pass

        send_to_miniapp(user_id, {
            'action': 'withdraw_request_sent',
            'request_id': request_id,
            'amount': amount,
            'message': '✅ درخواست برداشت ثبت شد. منتظر تأیید ادمین...'
        }, query_id)
        return

    if action == 'get_invite_link':
        bot_name = bot.get_me().username
        invite_link = f"https://t.me/{bot_name}?start=ref_{user_id}"
        send_to_miniapp(user_id, {
            'action': 'invite_link',
            'link': invite_link
        }, query_id)
        return

    if action == 'register_card':
        card_number = data.get('card_number', '').replace(' ', '')
        if len(card_number) != 16 or not card_number.isdigit():
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': '❌ شماره کارت ۱۶ رقم باید باشد!'
            }, query_id)
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET card_number=? WHERE user_id=?", (card_number, int(user_id)))
        conn.commit()
        conn.close()
        send_to_miniapp(user_id, {
            'action': 'card_registered',
            'card_number': card_number,
            'message': '✅ شماره کارت با موفقیت ثبت شد.'
        }, query_id)
        return

    if action == 'support_message':
        text = data.get('text', '')
        if not text:
            send_to_miniapp(user_id, {
                'action': 'graphic_error',
                'message': '❌ پیام خالی است!'
            }, query_id)
            return
        user_info = get_user(user_id)
        admin_text = f"📩 **پیام پشتیبانی از مینی‌اپ**\n👤 {user_info['username'] or user_id}\n🆔 {user_id}\n📝 {text}"
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(admin_id, admin_text, reply_markup=admin_reply_user_keyboard(user_id), parse_mode='Markdown')
            except:
                pass
        send_to_miniapp(user_id, {
            'action': 'support_sent',
            'message': '✅ پیام شما به پشتیبانی ارسال شد.'
        }, query_id)
        return

    if action == 'game_result':
        earned = data.get('amount', 0)
        if earned > 0:
            update_balance(user_id, earned)
            bot.reply_to(message, f"🎮 نتیجه‌ی بازی شما ثبت شد!\n🪙 {earned} سکه به حساب شما اضافه شد.\n🪙 موجودی فعلی: {get_balance(user_id):,} سکه")
        else:
            bot.reply_to(message, "🎮 بازی انجام شد اما هیچ سکه‌ای کسب نکردید.")
        return

    if action == 'add_coins':
        amount = data.get('amount', 0)
        if amount > 0:
            update_balance(user_id, amount)
            bot.reply_to(message, f"✅ {amount} سکه به حساب شما اضافه شد.\n🪙 موجودی: {get_balance(user_id):,} سکه")
        return

    bot.reply_to(message, f"✅ داده دریافت شد: {data}")

# ---------- صفحه‌کلیدهای رنگی (با استایل) ----------
def main_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🎮 شروع دوئل", callback_data='start_game', style='primary'),
        types.InlineKeyboardButton("💰 موجودی من", callback_data='balance', style='primary'),
        types.InlineKeyboardButton("👥 دعوت دوستان", callback_data='invite', style='primary'),
        types.InlineKeyboardButton("🪙 خرید سکه", callback_data='purchase', style='success'),
        types.InlineKeyboardButton("🏦 برداشت وجه", callback_data='withdraw', style='danger'),
        types.InlineKeyboardButton("📞 پشتیبانی", url=f"https://t.me/{ADMIN_USERNAMES[0].replace('@','')}", style='primary')
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "🎮 دوئل گرافیکی",
            web_app=types.WebAppInfo(url="https://halydydyal7-lgtm.github.io/Hostbrmodedoel/"),
            style='primary'
        )
    )
    return keyboard

def numeric_menu_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        "🎮 شروع دوئل",
        "💰 موجودی",
        "👥 دعوت دوستان",
        "🪙 خرید سکه",
        "🏦 برداشت وجه",
        "📞 پشتیبانی",
        "🎮 دوئل گرافیکی"
    ]
    keyboard.add(*buttons)
    return keyboard

def get_main_menu_with_back():
    keyboard = main_menu_keyboard()
    keyboard.row(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='back_to_main', style='danger'))
    return keyboard

def bet_amount_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    amounts = [5000, 20000, 50000, 100000, 200000, 500000]
    for a in amounts:
        keyboard.add(types.InlineKeyboardButton(f"{a:,} سکه", callback_data=f'bet_{a}', style='primary'))
    keyboard.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main', style='danger'))
    return keyboard

def confirm_bet_keyboard(bet_amount):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ ثبت دوئل", callback_data=f'confirm_bet_{bet_amount}', style='success'),
        types.InlineKeyboardButton("❌ لغو", callback_data='cancel_bet', style='danger')
    )
    return keyboard

def mode_selection_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        types.InlineKeyboardButton("۳ راند", callback_data='mode_3', style='primary'),
        types.InlineKeyboardButton("۵ راند", callback_data='mode_5', style='primary'),
        types.InlineKeyboardButton("۷ راند", callback_data='mode_7', style='primary')
    )
    keyboard.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main', style='danger'))
    return keyboard

def game_choice_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        types.InlineKeyboardButton("🪨 سنگ", callback_data='choice_rock', style='primary'),
        types.InlineKeyboardButton("📄 کاغذ", callback_data='choice_paper', style='primary'),
        types.InlineKeyboardButton("✂️ قیچی", callback_data='choice_scissors', style='primary')
    )
    return keyboard

def purchase_amount_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    amounts = [5000, 20000, 50000, 100000, 500000]
    for a in amounts:
        keyboard.add(types.InlineKeyboardButton(f"{a:,} سکه ({a:,} تومان)", callback_data=f'purchase_{a}', style='success'))
    keyboard.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main', style='danger'))
    return keyboard

def purchase_cancel_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 انصراف", callback_data='cancel_purchase', style='danger'))
    return keyboard

def admin_panel_keyboard():
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM purchase_requests WHERE status='pending'")
    pending_purchases = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdraw_requests WHERE status='pending'")
    pending_withdraws = c.fetchone()[0]
    conn.close()
    purchases_label = f"📋 سفارشات در انتظار تایید ({pending_purchases})" if pending_purchases else "📋 سفارشات در انتظار تایید"
    withdraws_label = f"🏦 درخواست‌های برداشت ({pending_withdraws})" if pending_withdraws else "🏦 درخواست‌های برداشت"
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(purchases_label, callback_data='admin_purchases', style='primary'),
        types.InlineKeyboardButton(withdraws_label, callback_data='admin_withdraws', style='danger'),
        types.InlineKeyboardButton("➕ افزایش موجودی (سکه)", callback_data='admin_add_balance', style='success'),
        types.InlineKeyboardButton("💳 تنظیم شماره کارت", callback_data='admin_set_card', style='primary'),
        types.InlineKeyboardButton("⚙️ تنظیمات", callback_data='admin_settings', style='primary'),
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data='admin_broadcast', style='primary'),
        types.InlineKeyboardButton("📩 پیام تکی", callback_data='admin_private_msg', style='primary'),
        types.InlineKeyboardButton("👥 مدیریت کاربران", callback_data='admin_manage_users', style='primary'),
        types.InlineKeyboardButton("🔍 مشاهده پروفایل کاربر", callback_data='admin_view_user', style='primary'),
        types.InlineKeyboardButton("🕓 آخرین کاربران", callback_data='admin_recent_users', style='primary'),
        types.InlineKeyboardButton("✅ لیست برداشت‌های تأییدشده", callback_data='admin_approved_withdrawals', style='success'),
        types.InlineKeyboardButton("🚫 لیست کاربران مسدود", callback_data='admin_banned_users', style='danger'),
        types.InlineKeyboardButton("📊 آمار کامل ربات", callback_data='admin_stats', style='primary'),
        types.InlineKeyboardButton("🔄 تغییر موجودی کاربر", callback_data='admin_change_balance', style='primary'),
        types.InlineKeyboardButton("📢 مدیریت عضویت اجباری", callback_data='admin_manage_channels', style='primary'),
        types.InlineKeyboardButton("📊 آمار کاربران", callback_data='admin_user_stats', style='primary')
    )
    return keyboard

def admin_settings_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💳 شماره کارت", callback_data='admin_edit_card', style='primary'),
        types.InlineKeyboardButton("📉 حداقل برداشت (سکه)", callback_data='admin_edit_min_withdraw', style='danger'),
        types.InlineKeyboardButton("📈 حداکثر برداشت (سکه)", callback_data='admin_edit_max_withdraw', style='danger'),
        types.InlineKeyboardButton("🎮 سقف بازی روزانه", callback_data='admin_edit_daily_limit', style='primary'),
        types.InlineKeyboardButton("📝 پیام خوش‌آمدگویی", callback_data='admin_edit_welcome', style='primary'),
        types.InlineKeyboardButton("📖 پیام راهنما", callback_data='admin_edit_help', style='primary'),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data='admin_back', style='danger')
    )
    return keyboard

def admin_user_profile_keyboard(target_uid, is_banned_status):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    ban_label = "✅ آن‌بن کردن" if is_banned_status else "🚫 بن کردن"
    keyboard.add(
        types.InlineKeyboardButton(ban_label, callback_data=f'admin_toggle_ban_{target_uid}', style='danger' if not is_banned_status else 'success'),
        types.InlineKeyboardButton("📩 ارسال پیام", callback_data=f'admin_reply_user_{target_uid}', style='primary'),
        types.InlineKeyboardButton("➕ افزایش موجودی", callback_data=f'admin_quick_addbal_{target_uid}', style='success')
    )
    keyboard.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin_back', style='danger'))
    return keyboard

def admin_purchase_keyboard(request_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ تأیید", callback_data=f'approve_purchase_{request_id}', style='success'),
        types.InlineKeyboardButton("❌ رد با دلیل", callback_data=f'reject_purchase_{request_id}', style='danger')
    )
    return keyboard

def admin_withdraw_keyboard(request_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ تأیید و کسر سکه", callback_data=f'approve_withdraw_{request_id}', style='success'),
        types.InlineKeyboardButton("❌ رد با دلیل", callback_data=f'reject_withdraw_{request_id}', style='danger')
    )
    return keyboard

def cancel_withdraw_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 انصراف", callback_data='cancel_withdraw', style='danger'))
    return keyboard

def withdraw_info_keyboard(has_enough_balance, has_card):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    if has_enough_balance:
        keyboard.add(types.InlineKeyboardButton("📝 ادامه فرآیند برداشت", callback_data='withdraw_continue', style='success'))
    if not has_card:
        keyboard.add(types.InlineKeyboardButton("💳 ثبت شماره کارت", callback_data='register_card_from_withdraw', style='primary'))
    else:
        keyboard.add(types.InlineKeyboardButton("🔄 تغییر شماره کارت", callback_data='change_card_from_withdraw', style='primary'))
    keyboard.add(types.InlineKeyboardButton("🔙 بازگشت به منو", callback_data='back_to_main', style='danger'))
    return keyboard

def membership_check_keyboard():
    channels = get_required_channels(active_only=True)
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        keyboard.add(types.InlineKeyboardButton(f"📢 عضویت در {ch['username']}", url=ch['link'], style='primary'))
    keyboard.add(types.InlineKeyboardButton("✅ تأیید عضویت", callback_data='check_membership', style='success'))
    return keyboard

def help_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("📩 ارسال پیام به پشتیبانی", url=f"https://t.me/{ADMIN_USERNAMES[0].replace('@','')}", style='primary'),
        types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='back_to_main', style='danger')
    )
    return keyboard

def cancel_waiting_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("❌ لغو دوئل", callback_data='cancel_waiting', style='danger'))
    return keyboard

def register_card_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 انصراف", callback_data='cancel_register_card', style='danger'))
    return keyboard

def admin_reply_user_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("📩 پاسخ به کاربر", callback_data=f'admin_reply_user_{user_id}', style='primary'))
    return keyboard

def admin_channels_management_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("➕ افزودن کانال جدید", callback_data='admin_add_channel', style='success'),
        types.InlineKeyboardButton("📋 لیست کانال‌ها", callback_data='admin_list_channels', style='primary')
    )
    keyboard.add(types.InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin_back', style='danger'))
    return keyboard

def admin_channel_list_keyboard():
    channels = get_required_channels(active_only=False)
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        status = "✅ فعال" if ch['active'] else "❌ غیرفعال"
        label = f"{ch['username']} ({status})"
        keyboard.add(types.InlineKeyboardButton(label, callback_data=f'admin_toggle_channel_{ch["id"]}', style='primary'))
        keyboard.add(types.InlineKeyboardButton(f"🗑 حذف {ch['username']}", callback_data=f'admin_delete_channel_{ch["id"]}', style='danger'))
    keyboard.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data='admin_manage_channels', style='danger'))
    return keyboard

# ========== بخش بازی (بازنویسی کامل برای رفع باگ‌ها) ==========
def create_game(p1, p2, bet, mode):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("INSERT INTO games (player1_id, player2_id, bet_amount, status, created_at) VALUES (?, ?, ?, ?, ?)",
              (int(p1), int(p2), bet, 'active', now))
    game_id = c.lastrowid
    conn.commit()
    conn.close()
    
    game_sessions[game_id] = {
        'player1_id': p1,
        'player2_id': p2,
        'bet_amount': bet,
        'status': 'active',
        'total_rounds': mode,
        'current_round': 1,
        'scores': {p1: 0, p2: 0},
        'p1_choice': None,
        'p2_choice': None,
        'p1_chosen': False,
        'p2_chosen': False,
        'winner_id': None,
        'created_at': now,
        'round_timer': None,
        'is_graphic': False,
        'round_resolved': False,
        'resolve_lock': threading.Lock(),
        'last_p1_choice': None,
        'last_p2_choice': None
    }
    return game_id

def start_round(game_id):
    game = game_sessions.get(game_id)
    if not game:
        return
    p1, p2 = game['player1_id'], game['player2_id']
    current = game['current_round']
    total = game['total_rounds']
    
    game['p1_choice'] = None
    game['p2_choice'] = None
    game['p1_chosen'] = False
    game['p2_chosen'] = False
    game['round_resolved'] = False
    
    if game.get('is_graphic'):
        send_to_miniapp(p1, {
            'action': 'graphic_round_start',
            'round': current,
            'total_rounds': total,
            'message': f'🎯 راند {current} از {total} - انتخاب خود را بزنید'
        })
        send_to_miniapp(p2, {
            'action': 'graphic_round_start',
            'round': current,
            'total_rounds': total,
            'message': f'🎯 راند {current} از {total} - انتخاب خود را بزنید'
        })
    else:
        msg = f"🎯 **راند {current} از {total}**\nلطفاً انتخاب خود را انجام دهید (۶۰ ثانیه فرصت):"
        bot.send_message(p1, msg, reply_markup=game_choice_keyboard(), parse_mode='Markdown')
        bot.send_message(p2, msg, reply_markup=game_choice_keyboard(), parse_mode='Markdown')
    
    timer = threading.Timer(60.0, round_timeout, args=[game_id])
    timer.daemon = True
    timer.start()
    game['round_timer'] = timer

def round_timeout(game_id):
    game = game_sessions.get(game_id)
    if not game:
        return
    if game.get('p1_chosen') and game.get('p2_chosen'):
        return
    p1, p2 = game['player1_id'], game['player2_id']
    if not game['p1_chosen']:
        if game.get('is_graphic'):
            send_to_miniapp(p1, {'action': 'graphic_error', 'message': '⏰ زمان شما تمام شد! این راند را باختید.'})
        else:
            bot.send_message(p1, "⏰ زمان شما برای این راند تمام شد! این راند را باختید.", parse_mode='Markdown')
        game['p1_choice'] = None
    if not game['p2_chosen']:
        if game.get('is_graphic'):
            send_to_miniapp(p2, {'action': 'graphic_error', 'message': '⏰ زمان شما تمام شد! این راند را باختید.'})
        else:
            bot.send_message(p2, "⏰ زمان شما برای این راند تمام شد! این راند را باختید.", parse_mode='Markdown')
        game['p2_choice'] = None
    resolve_round(game_id)

def resolve_round(game_id):
    game = game_sessions.get(game_id)
    if not game:
        return
    lock = game.get('resolve_lock')
    if lock:
        if not lock.acquire(blocking=False):
            return
    if game.get('round_resolved'):
        if lock:
            lock.release()
        return
    game['round_resolved'] = True
    if lock:
        lock.release()
    
    if game.get('round_timer'):
        game['round_timer'].cancel()
        game['round_timer'] = None
    
    p1, p2 = game['player1_id'], game['player2_id']
    choice1 = game['p1_choice']
    choice2 = game['p2_choice']
    
    game['last_p1_choice'] = choice1
    game['last_p2_choice'] = choice2
    
    round_winner = None
    if choice1 is None and choice2 is None:
        round_winner = None
    elif choice1 is None:
        round_winner = p2
    elif choice2 is None:
        round_winner = p1
    else:
        if choice1 == choice2:
            round_winner = None
        elif (choice1 == 'rock' and choice2 == 'scissors') or \
             (choice1 == 'scissors' and choice2 == 'paper') or \
             (choice1 == 'paper' and choice2 == 'rock'):
            round_winner = p1
        else:
            round_winner = p2
    
    if round_winner == p1:
        game['scores'][p1] += 1
    elif round_winner == p2:
        game['scores'][p2] += 1
    
    choice_map = {'rock': 'سنگ 🪨', 'paper': 'کاغذ 📄', 'scissors': 'قیچی ✂️'}
    c1 = choice_map.get(choice1, 'انتخاب نشده')
    c2 = choice_map.get(choice2, 'انتخاب نشده')
    
    if game.get('is_graphic'):
        for uid in [p1, p2]:
            is_p1 = (uid == p1)
            my_choice = choice1 if is_p1 else choice2
            opp_choice = choice2 if is_p1 else choice1
            winner = 'me' if (round_winner == uid) else ('opponent' if round_winner and round_winner != uid else 'draw')
            send_to_miniapp(uid, {
                'action': 'graphic_round_result',
                'my_choice': my_choice,
                'opp_choice': opp_choice,
                'winner': winner,
                'my_score': game['scores'][uid],
                'opp_score': game['scores'][p2 if is_p1 else p1],
                'round': game['current_round'],
                'total_rounds': game['total_rounds'],
                'game_finished': False
            })
    else:
        if round_winner == p1:
            result_text_p1 = "🏆 شما این راند را بردید!"
            result_text_p2 = "😔 شما این راند را باختید."
        elif round_winner == p2:
            result_text_p1 = "😔 شما این راند را باختید."
            result_text_p2 = "🏆 شما این راند را بردید!"
        else:
            result_text_p1 = "⚖️ این راند مساوی شد."
            result_text_p2 = "⚖️ این راند مساوی شد."
        
        bot.send_message(p1, f"📊 **نتیجه راند {game['current_round']}**\nانتخاب شما: {c1}\nانتخاب حریف: {c2}\n{result_text_p1}\nامتیاز شما: {game['scores'][p1]} - {game['scores'][p2]} حریف", parse_mode='Markdown')
        bot.send_message(p2, f"📊 **نتیجه راند {game['current_round']}**\nانتخاب شما: {c2}\nانتخاب حریف: {c1}\n{result_text_p2}\nامتیاز شما: {game['scores'][p2]} - {game['scores'][p1]} حریف", parse_mode='Markdown')
    
    total = game['total_rounds']
    if game['current_round'] >= total:
        if game['scores'][p1] > game['scores'][p2]:
            game['winner_id'] = p1
        elif game['scores'][p2] > game['scores'][p1]:
            game['winner_id'] = p2
        else:
            game['winner_id'] = None
        finalize_game(game_id)
    else:
        game['current_round'] += 1
        start_round(game_id)

def finalize_game(game_id):
    game = game_sessions.get(game_id)
    if not game:
        return
    if game.get('round_timer'):
        game['round_timer'].cancel()
        game['round_timer'] = None
    
    p1, p2 = game['player1_id'], game['player2_id']
    bet = game['bet_amount']
    winner = game['winner_id']
    
    p1_last = game.get('last_p1_choice')
    p2_last = game.get('last_p2_choice')
    choice_map = {'rock': 'سنگ 🪨', 'paper': 'کاغذ 📄', 'scissors': 'قیچی ✂️'}
    p1_choice_str = choice_map.get(p1_last, 'نامشخص')
    p2_choice_str = choice_map.get(p2_last, 'نامشخص')
    
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    
    if winner is None:
        update_balance(p1, bet)
        update_balance(p2, bet)
        if game.get('is_graphic'):
            new_balance_p1 = get_balance(p1)
            new_balance_p2 = get_balance(p2)
            send_to_miniapp(p1, {
                'action': 'graphic_game_finished',
                'winner': 'draw',
                'my_score': game['scores'][p1],
                'opp_score': game['scores'][p2],
                'bet_amount': bet,
                'win_amount': 0,
                'new_balance': new_balance_p1
            })
            send_to_miniapp(p2, {
                'action': 'graphic_game_finished',
                'winner': 'draw',
                'my_score': game['scores'][p2],
                'opp_score': game['scores'][p1],
                'bet_amount': bet,
                'win_amount': 0,
                'new_balance': new_balance_p2
            })
        else:
            for uid in [p1, p2]:
                my_choice = p1_choice_str if uid == p1 else p2_choice_str
                opp_choice = p2_choice_str if uid == p1 else p1_choice_str
                new_bal = get_balance(uid)
                msg = (
                    f"🤝 مساوی! نبرد بی‌برنده تموم شد…\n\n"
                    f"🎯 انتخاب تو: {my_choice}\n"
                    f"🧠 انتخاب حریف: {opp_choice}\n\n"
                    f"💵 مبلغ شرط: {bet:,} سکه\n\n"
                    f"🔄 نفس راحت! مبلغ شرط بدون کم‌وکاست به حسابت برگشت\n\n"
                    f"💰 موجودی فعلی: {new_bal:,} سکه\n\n"
                    f"🔥 دست بعدی می‌تونه ورق بازی رو برگردونه…"
                )
                bot.send_message(uid, msg, parse_mode='Markdown')
        game['status'] = 'finished'
        c.execute("UPDATE games SET status='finished', winner_id=NULL WHERE id=?", (game_id,))
    else:
        win_coins = int(2 * bet * 0.9)
        update_balance(winner, win_coins)
        loser = p2 if winner == p1 else p1
        
        if game.get('is_graphic'):
            for uid in [p1, p2]:
                is_winner = (uid == winner)
                new_balance = get_balance(uid)
                send_to_miniapp(uid, {
                    'action': 'graphic_game_finished',
                    'winner': 'me' if is_winner else 'opponent',
                    'my_score': game['scores'][uid],
                    'opp_score': game['scores'][loser if is_winner else winner],
                    'bet_amount': bet,
                    'win_amount': win_coins if is_winner else 0,
                    'new_balance': new_balance
                })
        else:
            winner_choice = p1_choice_str if winner == p1 else p2_choice_str
            loser_choice = p2_choice_str if winner == p1 else p1_choice_str
            commission = int(2 * bet * 0.1)
            profit = win_coins - bet
            new_bal = get_balance(winner)
            msg_win = (
                f"🏆 پیروزی! ضربهٔ نهایی رو تو زدی!\n\n"
                f"🎯 انتخاب تو: {winner_choice}\n"
                f"🧠 انتخاب حریف: {loser_choice}\n\n"
                f"💵 مبلغ شرط: {bet:,} سکه\n"
                f"💰 سود این نبرد: {profit:,} سکه\n"
                f"⚠️ کارمزد ربات: {commission:,} سکه\n\n"
                f"💰 موجودی جدید: {new_bal:,} سکه\n\n"
                f"🔥 برد شیرینه… ادامه می‌دی یا حریف رو فراری می‌دی؟"
            )
            bot.send_message(winner, msg_win, parse_mode='Markdown')
            loser_bal = get_balance(loser)
            msg_loss = (
                f"💀 شکست… این بار شانس با تو یار نبود\n\n"
                f"🎯 انتخاب تو: {loser_choice}\n"
                f"🧠 انتخاب حریف: {winner_choice}\n\n"
                f"💵 مبلغ شرط: {bet:,} سکه\n\n"
                f"😬 این دست از دست رفت، ولی بازی هنوز تموم نشده\n\n"
                f"💰 موجودی باقی‌مانده: {loser_bal:,} سکه\n\n"
                f"🔥 قهرمان‌ها بعد از باخت برمی‌گردن… آماده‌ای جبران کنی؟"
            )
            bot.send_message(loser, msg_loss, parse_mode='Markdown')
        game['status'] = 'finished'
        c.execute("UPDATE games SET status='finished', winner_id=? WHERE id=?", (winner, game_id))
    
    conn.commit()
    conn.close()
    
    del game_sessions[game_id]
    for uid in [p1, p2]:
        if uid in user_states and user_states[uid].get('state') == STATE_PLAYING:
            user_states[uid] = {'state': STATE_MAIN}
            if not game.get('is_graphic'):
                bot.send_message(uid, "🔙 بازگشت به منوی اصلی", reply_markup=numeric_menu_keyboard())

def announce_opponent_found(p1, p2, bet_amount, mode, is_graphic, game_id):
    if is_graphic:
        send_to_miniapp(p1, {
            'action': 'graphic_opponent_found',
            'game_id': game_id,
            'total_rounds': mode,
            'bet_amount': bet_amount
        })
        send_to_miniapp(p2, {
            'action': 'graphic_opponent_found',
            'game_id': game_id,
            'total_rounds': mode,
            'bet_amount': bet_amount
        })
    else:
        msg = (
            f"🤝 **یک رقیب برای دوئل پیدا شد!**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"💰 مبلغ دوئل: {bet_amount:,} سکه\n"
            f"🎯 تعداد راندها: {mode}\n"
            f"⏳ شما **۶۰ ثانیه** برای هر راند فرصت دارید."
        )
        bot.send_message(p1, msg, parse_mode='Markdown')
        bot.send_message(p2, msg, parse_mode='Markdown')

def start_matched_game(p1, p2, bet_amount, mode):
    cancel_pending_timer(p1)
    cancel_pending_timer(p2)
    is_graphic = user_states.get(p1, {}).get('from_graphic', False) or user_states.get(p2, {}).get('from_graphic', False)
    game_id = create_game(p1, p2, bet_amount, mode)
    game_sessions[game_id]['is_graphic'] = is_graphic
    announce_opponent_found(p1, p2, bet_amount, mode, is_graphic, game_id)
    user_states[p1] = {'state': STATE_PLAYING, 'game_id': game_id, 'bet_amount': bet_amount}
    user_states[p2] = {'state': STATE_PLAYING, 'game_id': game_id, 'bet_amount': bet_amount}
    start_round(game_id)
    return game_id

def match_players():
    with matching_lock:
        for key, queue in list(waiting_queues.items()):
            mode, bet_amount = key
            while len(queue) >= 2:
                p1 = queue.pop(0)
                p2 = queue.pop(0)
                start_matched_game(p1, p2, bet_amount, mode)

# ============================================================
#  دوئل متقاطع (بدون تغییر)
# ============================================================
def cancel_pending_timer(user_id):
    t = user_wait_timers.pop(user_id, None)
    if t:
        try:
            t.cancel()
        except:
            pass

def schedule_cross_bet_check(user_id, mode, bet_amount, delay=30.0):
    cancel_pending_timer(user_id)
    timer = threading.Timer(delay, cross_bet_check, args=[user_id, mode, bet_amount])
    timer.daemon = True
    timer.start()
    user_wait_timers[user_id] = timer

def cross_bet_check(user_id, mode, bet_amount):
    with matching_lock:
        key = (mode, bet_amount)
        if user_id not in waiting_queues.get(key, []):
            return
        candidates = [k for k in waiting_queues.keys() if k[0] == mode and k[1] != bet_amount and waiting_queues[k]]
        if not candidates:
            schedule_cross_bet_check(user_id, mode, bet_amount, delay=20.0)
            return
        candidates.sort(key=lambda k: abs(k[1] - bet_amount))
        other_key = candidates[0]
        other_queue = waiting_queues[other_key]
        if not other_queue or user_id not in waiting_queues.get(key, []):
            schedule_cross_bet_check(user_id, mode, bet_amount, delay=20.0)
            return
        other_user = other_queue[0]
        waiting_queues[key].remove(user_id)
        other_queue.remove(other_user)
        _create_cross_bet_proposal(mode, user_id, bet_amount, other_user, other_key[1])

def _create_cross_bet_proposal(mode, user_a, bet_a, user_b, bet_b):
    if bet_a > bet_b:
        high_user, high_bet, low_user, low_bet = user_a, bet_a, user_b, bet_b
    else:
        high_user, high_bet, low_user, low_bet = user_b, bet_b, user_a, bet_a

    pid = next(_proposal_id_seq)
    cross_bet_proposals[pid] = {
        'high_user': high_user, 'high_bet': high_bet,
        'low_user': low_user, 'low_bet': low_bet,
        'mode': mode, 'timer': None
    }
    timer = threading.Timer(30.0, proposal_expired, args=[pid])
    timer.daemon = True
    timer.start()
    cross_bet_proposals[pid]['timer'] = timer

    bot.send_message(low_user,
        f"🔎 **پیشنهاد دوئل برای کاربران آنلاین ارسال شد.**\n"
        f"لطفاً منتظر بمانید...",
        reply_markup=cancel_waiting_keyboard(), parse_mode='Markdown')

    accept_kb = types.InlineKeyboardMarkup(row_width=1)
    accept_kb.add(
        types.InlineKeyboardButton(f"✅ قبول دوئل با {low_bet:,} سکه", callback_data=f'accept_cross_bet_{pid}', style='success'),
        types.InlineKeyboardButton(f"❌ رد و ادامه جستجو با {high_bet:,} سکه", callback_data=f'decline_cross_bet_{pid}', style='danger'),
        types.InlineKeyboardButton("🚫 لغو کامل دوئل", callback_data='cancel_waiting', style='danger')
    )
    bot.send_message(high_user,
        f"🎲 **پیشنهاد دوئل با مبلغ متفاوت**\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        f"حریفی با مبلغ شرط **{low_bet:,} سکه** پیدا شد (شرط شما: {high_bet:,} سکه).\n"
        f"در صورت قبول، دوئل با مبلغ **{low_bet:,} سکه** شروع می‌شود و مابه‌التفاوت "
        f"(**{high_bet - low_bet:,} سکه**) بلافاصله به موجودی شما بازگردانده می‌شود.",
        reply_markup=accept_kb, parse_mode='Markdown')

def proposal_expired(pid):
    with matching_lock:
        prop = cross_bet_proposals.pop(pid, None)
        if not prop:
            return
        _requeue_after_proposal_ends(prop, reason='expired')

def _requeue_after_proposal_ends(prop, reason):
    mode = prop['mode']
    low_user, low_bet = prop['low_user'], prop['low_bet']
    high_user, high_bet = prop['high_user'], prop['high_bet']
    waiting_queues[(mode, low_bet)].append(low_user)
    waiting_queues[(mode, high_bet)].append(high_user)
    schedule_cross_bet_check(low_user, mode, low_bet)
    schedule_cross_bet_check(high_user, mode, high_bet)
    if reason == 'expired':
        bot.send_message(low_user, "⏳ پاسخی از حریف پیشنهادی دریافت نشد. جستجوی حریف ادامه دارد...", reply_markup=cancel_waiting_keyboard(), parse_mode='Markdown')
        bot.send_message(high_user, "⏳ زمان پاسخ به پیشنهاد دوئل تمام شد. جستجو با مبلغ اولیه شما ادامه دارد.", reply_markup=cancel_waiting_keyboard(), parse_mode='Markdown')
    elif reason == 'declined':
        bot.send_message(low_user, "↩️ حریف با مبلغ دیگر، پیشنهاد را رد کرد. جستجوی حریف ادامه دارد...", reply_markup=cancel_waiting_keyboard(), parse_mode='Markdown')
        bot.send_message(high_user, "🔎 در حال جستجوی حریف جدید با مبلغ شما...", reply_markup=cancel_waiting_keyboard(), parse_mode='Markdown')

def cancel_user_waiting(user_id):
    with matching_lock:
        for key, queue in list(waiting_queues.items()):
            if user_id in queue:
                queue.remove(user_id)
                mode, bet_amount = key
                cancel_pending_timer(user_id)
                update_balance(user_id, bet_amount)
                return True
        for pid, prop in list(cross_bet_proposals.items()):
            if user_id in (prop['high_user'], prop['low_user']):
                if prop.get('timer'):
                    prop['timer'].cancel()
                del cross_bet_proposals[pid]
                mode = prop['mode']
                if user_id == prop['high_user']:
                    my_bet = prop['high_bet']
                    other_user, other_bet = prop['low_user'], prop['low_bet']
                else:
                    my_bet = prop['low_bet']
                    other_user, other_bet = prop['high_user'], prop['high_bet']
                cancel_pending_timer(user_id)
                update_balance(user_id, my_bet)
                waiting_queues[(mode, other_bet)].append(other_user)
                schedule_cross_bet_check(other_user, mode, other_bet)
                bot.send_message(other_user,
                    "↩️ حریف پیشنهادی دوئل، دوئل را کاملاً لغو کرد. جستجوی حریف با مبلغ شما ادامه دارد...",
                    reply_markup=cancel_waiting_keyboard(), parse_mode='Markdown')
                return True
        return False

# ---------- تابع ارسال منوی اصلی ----------
def send_main_menu(user_id, text=None, delete_prev=False, chat_id=None, message_id=None):
    if is_banned(user_id):
        bot.send_message(user_id, "⛔ شما توسط ادمین مسدود شده‌اید. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.")
        return
    
    ensure_user_exists(user_id, str(user_id))
    
    non_member_channels = get_non_member_channels(user_id)
    if non_member_channels:
        msg_text = "⚠️ **برای استفاده از ربات، لازم است ابتدا در کانال‌های زیر عضو شوید:**\n\n"
        for ch in non_member_channels:
            msg_text += f"• {ch['link']}\n"
        msg_text += "\n📢 پس از عضویت در همه کانال‌ها، دکمه **تأیید عضویت** را بزنید."
        bot.send_message(user_id, msg_text, reply_markup=membership_check_keyboard(), parse_mode='Markdown')
        if delete_prev and chat_id and message_id:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
        return
    
    if delete_prev and chat_id and message_id:
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
    if not text:
        balance = get_balance(user_id)
        _, wins, _, _, level = get_user_stats(user_id)
        text = f"🪙 موجودی شما: {balance:,} سکه (معادل {balance:,} تومان)\n⭐ سطح: {level}\n\n🎯 آماده‌اید با کاربران واقعی **دوئل سنگ‌کاغذ‌قیچی** بازی کنید و سکه به دست آورید؟"
    bot.send_message(user_id, text, reply_markup=numeric_menu_keyboard(), parse_mode='Markdown')

# ---------- تابع نمایش اطلاعات برداشت ----------
def show_withdraw_info(user_id, chat_id=None, message_id=None):
    if is_banned(user_id):
        bot.send_message(user_id, "⛔ شما توسط ادمین مسدود شده‌اید.")
        return
    if not is_member_all_channels(user_id):
        send_main_menu(user_id)
        return
    user = get_user(user_id)
    if not user:
        return
    if chat_id and message_id:
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
    bot_name = bot.get_me().username
    invite_link = f"https://t.me/{bot_name}?start=ref_{user_id}"
    balance = user['balance']
    min_withdraw = int(get_setting('min_withdraw') or 10000)
    max_withdraw = int(get_setting('max_withdraw') or 250000)
    has_enough_balance = balance >= min_withdraw
    has_card = bool(user['card_number'])
    
    daily_used = get_daily_withdrawal_total(user_id)
    daily_remaining = max(0, max_withdraw - daily_used)

    text = (
        f"🏦 **برداشت وجه**\n"
        f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        f"🪙 موجودی کیف پول: **{balance:,} سکه** (معادل {balance:,} تومان)\n\n"
        f"📋 **شرایط برداشت:**\n"
        f"✅ موجودی حداقل **{min_withdraw:,} سکه**\n"
        f"✅ حداکثر هر برداشت **{max_withdraw:,} سکه**\n"
        f"✅ حداکثر برداشت روزانه (۲۴ ساعت) **{max_withdraw:,} سکه**\n\n"
        f"🔗 **لینک دعوت شما (اختیاری):**\n"
        f"`{invite_link}`\n\n"
        f"📤 لینک را برای دوستان خود ارسال کنید و از هر دعوت **۱ سطح** پاداش بگیرید."
    )
    
    if has_enough_balance:
        text += f"\n\n✅ **تبریک! شما شرایط برداشت را دارید.**"
        text += f"\n💰 امروز {daily_used:,} سکه برداشت کرده‌اید."
        text += f"\n⏳ مبلغ قابل برداشت امروز: **{daily_remaining:,} سکه**"
    else:
        text += f"\n\n⏳ موجودی شما کمتر از {min_withdraw:,} سکه است. ({balance:,} سکه)"
    
    bot.send_message(user_id, text, reply_markup=withdraw_info_keyboard(has_enough_balance, has_card), parse_mode='Markdown')

# ---------- هندلرهای دستورات ----------
@bot.message_handler(commands=['start', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'game', 'balance', 'invite', 'purchase', 'withdraw', 'help'])
def handle_commands(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    user = get_or_create_user(user_id, username)

    if is_banned(user_id):
        bot.reply_to(message, "⛔ شما توسط ادمین مسدود شده‌اید. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.")
        return

    cmd = message.text.split()[0].replace('/', '')
    
    if cmd in ['help', 'c6']:
        help_text = get_setting('help_text') or "📖 راهنما و پشتیبانی"
        keyboard = help_keyboard()
        bot.send_message(user_id, help_text, reply_markup=keyboard, parse_mode='Markdown')
        return

    if not is_member_all_channels(user_id) and cmd != 'start':
        send_main_menu(user_id, delete_prev=True, chat_id=message.chat.id, message_id=message.message_id)
        return

    if cmd in ['c1', 'start']:
        send_main_menu(user_id, delete_prev=True, chat_id=message.chat.id, message_id=message.message_id)
        return
    elif cmd == 'c2':
        cmd = 'balance'
    elif cmd == 'c3':
        cmd = 'invite'
    elif cmd == 'c4':
        cmd = 'purchase'
    elif cmd == 'c5':
        cmd = 'withdraw'

    if cmd == 'start':
        ref = None
        if len(message.text.split()) > 1:
            part = message.text.split()[1]
            if part.startswith('ref_'):
                ref = part[4:]
        if ref:
            pass
        send_main_menu(user_id, delete_prev=True, chat_id=message.chat.id, message_id=message.message_id)
        return

    elif cmd == 'game':
        if not can_play_game(user_id):
            bot.reply_to(message, f"⛔ شما امروز {get_daily_game_limit()} دوئل انجام داده‌اید و به سقف مجاز روزانه رسیده‌اید. لطفاً فردا مجدداً تلاش کنید.")
            return
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        bot.send_message(user_id,
            f"🎯 **انتخاب مبلغ دوئل (به سکه)**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"🪙 موجودی فعلی: {get_balance(user_id):,} سکه\n"
            f"📊 بازی‌های امروز: {get_daily_games_count(user_id)}/{get_daily_game_limit()}",
            reply_markup=bet_amount_keyboard(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_SELECTING_BET}

    elif cmd == 'balance':
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        balance = get_balance(user_id)
        total_games, wins, loses, draws, level = get_user_stats(user_id)
        invites = user['total_invites']
        bot.send_message(user_id,
            f"💰 **موجودی شما**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"🆔 شناسه: `{user_id}`\n"
            f"⭐ سطح: {level}\n"
            f"🪙 موجودی: **{balance:,} سکه** (معادل {balance:,} تومان)\n"
            f"👥 دعوت‌های موفق: {invites}\n"
            f"🎮 تعداد دوئل‌ها: {total_games}\n"
            f"🏆 بردها: {wins}\n"
            f"🤝 مساوی‌ها: {draws}\n"
            f"📉 باخت‌ها: {loses}\n\n"
            f"⚙️ کارمزد ربات: ۱۰٪ از برد شما",
            reply_markup=get_main_menu_with_back(), parse_mode='Markdown')

    elif cmd == 'invite':
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        bot_name = bot.get_me().username
        invite_link = f"https://t.me/{bot_name}?start=ref_{user_id}"
        text = (
            f"👥 **سیستم دعوت دوستان**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"🔢 تعداد دعوت‌های موفق شما: **{user['total_invites']}**\n"
            f"🎁 به ازای هر دعوت، **۱ سطح** به سطح شما اضافه می‌شود.\n\n"
            f"📋 **لینک دعوت اختصاصی شما:**\n"
            f"`{invite_link}`"
        )
        bot.send_message(user_id, text, reply_markup=get_main_menu_with_back(), parse_mode='Markdown')

    elif cmd == 'purchase':
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        card_number = get_setting('card_number') or CARD_NUMBER
        card_owner = get_setting('card_owner') or CARD_OWNER
        text = (
            f"🪙 **خرید سکه (شارژ حساب)**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"💳 **نرخ تبدیل:** هر ۱ تومان = ۱ سکه\n"
            f"📋 **حداقل خرید:** ۵,۰۰۰ سکه | **حداکثر خرید:** ۵۰۰,۰۰۰ سکه\n"
            f"⚠️ **توجه:** هر ۵,۰۰۰ سکه معادل ۵,۰۰۰ تومان است.\n\n"
            f"🏦 **شماره کارت برای واریز:**\n"
            f"`{card_number}`\n"
            f"به نام: {card_owner}\n\n"
            f"⚠️ **توجه:**\n"
            f"• فقط **کارت به کارت** (از طریق برنامه‌های بانکی) پذیرفته می‌شود.\n"
            f"• **پرداخت از طریق پایا، ساتنا یا شبا** قابل قبول نیست.\n"
            f"• لطفاً **رسید واریز** خود را به‌صورت **عکس یا شماره پیگیری** ارسال کنید.\n"
            f"• **مسئولیت واریز اشتباه** به عهده خود کاربر می‌باشد.\n\n"
            f"🔽 مبلغ مورد نظر را انتخاب کنید:"
        )
        bot.send_message(user_id, text, reply_markup=purchase_amount_keyboard(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_PURCHASE_AMOUNT}

    elif cmd == 'withdraw':
        show_withdraw_info(user_id, chat_id=message.chat.id, message_id=message.message_id)

    elif cmd == 'support':
        support_text = (
            "📞 **پشتیبانی**\n\n"
            "برای ارتباط با پشتیبانی، روی دکمه زیر کلیک کنید.\n"
            "پاسخگوی سوالات و مشکلات شما هستیم."
        )
        keyboard = help_keyboard()
        bot.send_message(user_id, support_text, reply_markup=keyboard, parse_mode='Markdown')

# ---------- هندلر دکمه‌ها ----------
def safe_answer_callback(call_id, *args, **kwargs):
    try:
        bot.answer_callback_query(call_id, *args, **kwargs)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    user = get_or_create_user(user_id, call.from_user.username or call.from_user.first_name)

    if is_banned(user_id):
        safe_answer_callback(call.id, "⛔ شما توسط ادمین مسدود شده‌اید.", show_alert=True)
        return

    if data == 'check_membership':
        if is_member_all_channels(user_id):
            safe_answer_callback(call.id, "✅ عضویت شما در همه کانال‌ها تأیید شد! خوش آمدید.")
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            send_main_menu(user_id)
        else:
            non_member = get_non_member_channels(user_id)
            msg = "❌ شما هنوز در کانال‌های زیر عضو نشده‌اید:\n"
            for ch in non_member:
                msg += f"• {ch['link']}\n"
            safe_answer_callback(call.id, msg, show_alert=True)
        return

    if data == 'support':
        support_text = (
            "📞 **پشتیبانی**\n\n"
            "برای ارتباط با پشتیبانی، روی دکمه زیر کلیک کنید.\n"
            "پاسخگوی سوالات و مشکلات شما هستیم."
        )
        keyboard = help_keyboard()
        bot.send_message(user_id, support_text, reply_markup=keyboard, parse_mode='Markdown')
        safe_answer_callback(call.id)
        return

    if not is_member_all_channels(user_id):
        non_member = get_non_member_channels(user_id)
        msg = "⚠️ ابتدا در همه کانال‌های زیر عضو شوید:\n"
        for ch in non_member:
            msg += f"• {ch['link']}\n"
        safe_answer_callback(call.id, msg, show_alert=True)
        send_main_menu(user_id)
        return

    safe_answer_callback(call.id, cache_time=2)

    # ---------- ثبت/تغییر شماره کارت ----------
    if data in ['register_card_from_withdraw', 'change_card_from_withdraw']:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id,
            "💳 **لطفاً شماره کارت ۱۶ رقمی خود را وارد کنید:**\n(عدد بدون فاصله)",
            reply_markup=register_card_keyboard(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_REGISTER_CARD, 'from_withdraw': True}
        return

    if data == 'cancel_register_card':
        user_states[user_id] = {'state': STATE_MAIN}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        if user_states.get(user_id, {}).get('from_withdraw'):
            show_withdraw_info(user_id)
        else:
            bot.send_message(user_id, "🔙 ثبت شماره کارت لغو شد.", reply_markup=numeric_menu_keyboard())
        return

    # ---------- شروع بازی ----------
    if data == 'start_game':
        if not can_play_game(user_id):
            safe_answer_callback(call.id, f"⛔ شما امروز {get_daily_game_limit()} دوئل انجام داده‌اید. لطفاً فردا تلاش کنید.", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id,
            f"🎯 **انتخاب مبلغ دوئل (به سکه)**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"🪙 موجودی فعلی: {get_balance(user_id):,} سکه\n"
            f"📊 بازی‌های امروز: {get_daily_games_count(user_id)}/{get_daily_game_limit()}",
            reply_markup=bet_amount_keyboard(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_SELECTING_BET}

    elif data == 'balance':
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        balance = get_balance(user_id)
        total_games, wins, loses, draws, level = get_user_stats(user_id)
        invites = user['total_invites']
        bot.send_message(user_id,
            f"💰 **موجودی شما**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"🆔 شناسه: `{user_id}`\n"
            f"⭐ سطح: {level}\n"
            f"🪙 موجودی: **{balance:,} سکه** (معادل {balance:,} تومان)\n"
            f"👥 دعوت‌های موفق: {invites}\n"
            f"🎮 تعداد دوئل‌ها: {total_games}\n"
            f"🏆 بردها: {wins}\n"
            f"🤝 مساوی‌ها: {draws}\n"
            f"📉 باخت‌ها: {loses}",
            reply_markup=get_main_menu_with_back(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_MAIN}

    elif data == 'invite':
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot_name = bot.get_me().username
        invite_link = f"https://t.me/{bot_name}?start=ref_{user_id}"
        text = (
            f"👥 **سیستم دعوت دوستان**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"🔢 تعداد دعوت‌های موفق: **{user['total_invites']}**\n"
            f"🎁 پاداش هر دعوت: **۱ سطح**\n\n"
            f"📋 **لینک دعوت شما:**\n"
            f"`{invite_link}`"
        )
        bot.send_message(user_id, text, reply_markup=get_main_menu_with_back(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_MAIN}

    elif data == 'purchase':
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        card_number = get_setting('card_number') or CARD_NUMBER
        card_owner = get_setting('card_owner') or CARD_OWNER
        text = (
            f"🪙 **خرید سکه (شارژ حساب)**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"💳 هر ۱ تومان = ۱ سکه\n"
            f"📋 حداقل: ۵,۰۰۰ | حداکثر: ۵۰۰,۰۰۰\n\n"
            f"🏦 شماره کارت:\n`{card_number}`\nبه نام: {card_owner}\n\n"
            f"⚠️ **فقط کارت به کارت**\n"
            f"• رسید را ارسال کنید (عکس یا شماره پیگیری)\n"
            f"• مسئولیت واریز اشتباه با شماست"
        )
        bot.send_message(user_id, text, reply_markup=purchase_amount_keyboard(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_PURCHASE_AMOUNT}

    elif data == 'withdraw':
        show_withdraw_info(user_id, chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif data == 'withdraw_continue':
        balance = get_balance(user_id)
        min_withdraw = int(get_setting('min_withdraw') or 10000)
        max_withdraw = int(get_setting('max_withdraw') or 250000)
        if balance < min_withdraw:
            safe_answer_callback(call.id, f"⛔ موجودی شما کمتر از {min_withdraw:,} سکه است!", show_alert=True)
            return
        daily_used = get_daily_withdrawal_total(user_id)
        if daily_used >= max_withdraw:
            safe_answer_callback(call.id, f"⛔ شما امروز سقف برداشت روزانه ({max_withdraw:,} سکه) را پر کرده‌اید!", show_alert=True)
            return
        if not user['card_number']:
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            bot.send_message(user_id,
                f"🏦 **شماره کارت خود را وارد کنید**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"📝 ۱۶ رقم را ارسال کنید.",
                reply_markup=cancel_withdraw_keyboard(), parse_mode='Markdown')
            user_states[user_id] = {'state': STATE_WITHDRAW_CARD}
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        remaining = max_withdraw - daily_used
        bot.send_message(user_id,
            f"🏦 **درخواست برداشت**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"🪙 موجودی: {get_balance(user_id):,} سکه (معادل {get_balance(user_id):,} تومان)\n"
            f"📋 حداقل: {min_withdraw:,} سکه | حداکثر: {max_withdraw:,} سکه\n"
            f"💰 امروز {daily_used:,} سکه برداشت کرده‌اید. باقیمانده: {remaining:,} سکه\n"
            f"🔢 شماره کارت: `{user['card_number']}`\n\n"
            f"مبلغ به سکه را وارد کنید:",
            reply_markup=cancel_withdraw_keyboard(),
            parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_WITHDRAW_AMOUNT}

    # ---------- شرط بندی و انتخاب حالت ----------
    elif data.startswith('bet_'):
        amount = int(data.split('_')[1])
        balance = get_balance(user_id)
        if amount > balance:
            safe_answer_callback(call.id, "❌ موجودی کافی نیست!", show_alert=True)
            return
        user_states[user_id] = {'state': 'confirm_bet', 'bet_amount': amount}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id,
            f"✅ **تأیید دوئل**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"💰 مبلغ دوئل: {amount:,} سکه\n"
            f"🧾 کارمزد: ۱۰٪ از برد\n"
            f"ثبت شود؟",
            reply_markup=confirm_bet_keyboard(amount), parse_mode='Markdown')

    elif data.startswith('confirm_bet_'):
        amount = int(data.split('_')[2])
        balance = get_balance(user_id)
        if amount > balance:
            safe_answer_callback(call.id, "❌ موجودی کافی نیست!", show_alert=True)
            return
        if not can_play_game(user_id):
            safe_answer_callback(call.id, f"⛔ شما امروز {get_daily_game_limit()} دوئل انجام داده‌اید. لطفاً فردا تلاش کنید.", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id,
            f"🎯 **تعداد راندها را انتخاب کنید:**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"💰 مبلغ دوئل: {amount:,} سکه\n"
            f"برنده با اکثریت راندها مشخص می‌شود.",
            reply_markup=mode_selection_keyboard(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_SELECTING_MODE, 'bet_amount': amount}

    elif data == 'cancel_bet':
        user_states[user_id] = {'state': STATE_MAIN}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "❌ دوئل لغو شد.", reply_markup=numeric_menu_keyboard())

    elif data.startswith('mode_'):
        mode = int(data.split('_')[1])
        state = user_states.get(user_id)
        if not state or state.get('state') != STATE_SELECTING_MODE:
            safe_answer_callback(call.id, "❌ خطا!", show_alert=True)
            return
        bet_amount = state.get('bet_amount', 5000)
        update_balance(user_id, -bet_amount)
        increment_daily_games(user_id)
        waiting_queues[(mode, bet_amount)].append(user_id)
        user_states[user_id] = {'state': STATE_WAITING_OPPONENT, 'bet_amount': bet_amount, 'mode': mode}
        safe_answer_callback(call.id, f"⏳ در حال پیدا کردن رقیب برای دوئل {mode} راندی...")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id,
            f"⏳ **در حال جستجوی حریف برای دوئل {mode} راندی**\nلطفاً صبر کنید...",
            reply_markup=cancel_waiting_keyboard(), parse_mode='Markdown')
        match_players()
        schedule_cross_bet_check(user_id, mode, bet_amount)

    elif data == 'cancel_waiting':
        removed = cancel_user_waiting(user_id)
        if removed:
            user_states[user_id] = {'state': STATE_MAIN}
            safe_answer_callback(call.id, "❌ جستجوی حریف لغو شد.")
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            bot.send_message(user_id, "❌ دوئل لغو شد و سکه‌ها به حساب شما بازگشت.", reply_markup=numeric_menu_keyboard())
        else:
            safe_answer_callback(call.id, "⏳ شما در صف نیستید یا قبلاً هم‌تایی شده‌اید.", show_alert=True)

    # ---------- پیشنهاد دوئل متقاطع (مبلغ نزدیک) ----------
    elif data.startswith('accept_cross_bet_'):
        pid = int(data.split('_')[-1])
        with matching_lock:
            prop = cross_bet_proposals.get(pid)
            if not prop or prop['high_user'] != user_id:
                safe_answer_callback(call.id, "❌ این پیشنهاد دیگر معتبر نیست.", show_alert=True)
                return
            if prop.get('timer'):
                prop['timer'].cancel()
            del cross_bet_proposals[pid]
            high_user, high_bet = prop['high_user'], prop['high_bet']
            low_user, low_bet = prop['low_user'], prop['low_bet']
            mode = prop['mode']
            diff = high_bet - low_bet
            if diff > 0:
                update_balance(high_user, diff)
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        try:
            bot.send_message(low_user, f"✅ حریف با شرط {low_bet:,} سکه پیدا شد! دوئل شروع می‌شود...", parse_mode='Markdown')
        except:
            pass
        safe_answer_callback(call.id, "✅ دوئل با مبلغ جدید شروع شد.")
        start_matched_game(low_user, high_user, low_bet, mode)

    elif data.startswith('decline_cross_bet_'):
        pid = int(data.split('_')[-1])
        with matching_lock:
            prop = cross_bet_proposals.get(pid)
            if not prop or prop['high_user'] != user_id:
                safe_answer_callback(call.id, "❌ این پیشنهاد دیگر معتبر نیست.", show_alert=True)
                return
            if prop.get('timer'):
                prop['timer'].cancel()
            del cross_bet_proposals[pid]
            _requeue_after_proposal_ends(prop, reason='declined')
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        safe_answer_callback(call.id, "❌ پیشنهاد رد شد. جستجو با مبلغ اولیه‌تان ادامه دارد.")

    # ---------- انتخاب در راند ----------
    elif data.startswith('choice_'):
        choice = data.split('_')[1]
        state = user_states.get(user_id)
        if not state or state.get('state') != STATE_PLAYING:
            safe_answer_callback(call.id, "⚠️ در دوئل نیستید!", show_alert=True)
            return
        game_id = state.get('game_id')
        if not game_id:
            safe_answer_callback(call.id, "⚠️ خطا!", show_alert=True)
            return
        game = game_sessions.get(game_id)
        if not game:
            safe_answer_callback(call.id, "⏰ زمان دوئل تمام شد!", show_alert=True)
            return
        if game['status'] != 'active':
            safe_answer_callback(call.id, "⚠️ بازی به پایان رسیده!", show_alert=True)
            return
        if game['player1_id'] == user_id:
            if game['p1_chosen']:
                safe_answer_callback(call.id, "✅ قبلاً انتخاب کردید!", show_alert=True)
                return
            game['p1_choice'] = choice
            game['p1_chosen'] = True
        elif game['player2_id'] == user_id:
            if game['p2_chosen']:
                safe_answer_callback(call.id, "✅ قبلاً انتخاب کردید!", show_alert=True)
                return
            game['p2_choice'] = choice
            game['p2_chosen'] = True
        else:
            safe_answer_callback(call.id, "⚠️ شما در این دوئل نیستید!", show_alert=True)
            return
        choice_persian = {'rock': 'سنگ 🪨', 'paper': 'کاغذ 📄', 'scissors': 'قیچی ✂️'}[choice]
        safe_answer_callback(call.id, f"✅ {choice_persian} ثبت شد.")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id,
            f"✅ انتخاب: **{choice_persian}**\n⏳ منتظر حریف...", parse_mode='Markdown')
        if game.get('p1_chosen') and game.get('p2_chosen'):
            if game.get('round_timer'):
                game['round_timer'].cancel()
                game['round_timer'] = None
            resolve_round(game_id)

    # ---------- خرید ----------
    elif data.startswith('purchase_'):
        amount_toman = int(data.split('_')[1])
        allowed = [5000, 20000, 50000, 100000, 500000]
        if amount_toman not in allowed:
            safe_answer_callback(call.id, "❌ مبلغ نامعتبر!", show_alert=True)
            return
        coins = amount_toman
        card_number = get_setting('card_number') or CARD_NUMBER
        card_owner = get_setting('card_owner') or CARD_OWNER
        text = (
            f"🪙 **درخواست خرید**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"💰 مبلغ: {amount_toman:,} تومان\n"
            f"🪙 سکه: {coins:,} (معادل {coins:,} تومان)\n\n"
            f"🏦 شماره کارت:\n`{card_number}`\nبه نام: {card_owner}\n\n"
            f"⚠️ **فقط کارت به کارت**\n"
            f"• رسید را ارسال کنید (عکس یا متن)\n"
            f"• مسئولیت واریز اشتباه با شماست\n\n"
            f"📤 لطفاً رسید خود را ارسال کنید:"
        )
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, text, reply_markup=purchase_cancel_keyboard(), parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_PURCHASE_RECEIPT, 'purchase_amount': amount_toman, 'purchase_coins': coins}

    elif data == 'cancel_purchase':
        user_states[user_id] = {'state': STATE_MAIN}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "🔙 خرید لغو شد.", reply_markup=numeric_menu_keyboard())

    elif data == 'cancel_withdraw':
        user_states[user_id] = {'state': STATE_MAIN}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "🔙 برداشت لغو شد.", reply_markup=numeric_menu_keyboard())

    # ---------- پنل ادمین ----------
    elif data == 'admin_settings':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id,
            "⚙️ **تنظیمات ربات**\nلطفاً گزینه مورد نظر را انتخاب کنید:",
            reply_markup=admin_settings_keyboard(), parse_mode='Markdown')

    elif data == 'admin_edit_card':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "💳 **شماره کارت جدید را وارد کنید:**", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_SET_CARD}

    elif data == 'admin_edit_min_withdraw':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "📉 **حداقل مبلغ برداشت را به سکه وارد کنید:**\n(عدد بدون کاما)", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_EDIT_SETTING, 'setting_key': 'min_withdraw'}

    elif data == 'admin_edit_max_withdraw':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "📈 **حداکثر مبلغ برداشت را به سکه وارد کنید:**\n(عدد بدون کاما)", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_EDIT_SETTING, 'setting_key': 'max_withdraw'}

    elif data == 'admin_edit_daily_limit':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"🎮 **سقف تعداد دوئل روزانه هر کاربر را وارد کنید:**\n(عدد صحیح - مقدار فعلی: {get_daily_game_limit()})", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_EDIT_SETTING, 'setting_key': 'daily_game_limit'}

    elif data == 'admin_edit_welcome':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "📝 **پیام خوش‌آمدگویی جدید را وارد کنید:**\n(از Markdown استفاده کنید)", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_EDIT_SETTING, 'setting_key': 'welcome_text'}

    elif data == 'admin_edit_help':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "📖 **پیام راهنمای جدید را وارد کنید:**\n(از Markdown استفاده کنید)", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_EDIT_SETTING, 'setting_key': 'help_text'}

    elif data == 'admin_back':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "🔐 **پنل مدیریت**", reply_markup=admin_panel_keyboard())

    elif data == 'admin_purchases':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount_toman, coins, receipt_text, receipt_photo_id, created_at FROM purchase_requests WHERE status='pending'")
        rows = c.fetchall()
        conn.close()
        if not rows:
            safe_answer_callback(call.id, "📭 درخواستی نیست.")
            return
        for row in rows:
            req_id, uid, amount, coins, receipt_text, receipt_photo_id, created = row
            user_info = get_user(uid)
            username_line = f"@{user_info['username']}" if user_info['username'] else "ثبت نشده"
            text = (
                f"🆔 شماره درخواست: {req_id}\n"
                f"👤 نام کاربری: {username_line}\n"
                f"🆔 آیدی کاربر: {uid}\n"
                f"💰 {amount:,} تومان\n"
                f"🪙 {coins:,} سکه\n"
                f"📝 {receipt_text or 'عکس'}"
            )
            if receipt_photo_id:
                bot.send_photo(user_id, receipt_photo_id, caption=text, reply_markup=admin_purchase_keyboard(req_id))
            else:
                bot.send_message(user_id, text, reply_markup=admin_purchase_keyboard(req_id))
        safe_answer_callback(call.id, "✅ درخواست‌ها ارسال شد.")

    elif data == 'admin_withdraws':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount_toman, card_number, created_at FROM withdraw_requests WHERE status='pending'")
        rows = c.fetchall()
        conn.close()
        if not rows:
            safe_answer_callback(call.id, "📭 درخواستی نیست.")
            return
        for row in rows:
            req_id, uid, amount, card, created = row
            user_info = get_user(uid)
            username_line = f"@{user_info['username']}" if user_info['username'] else "ثبت نشده"
            text = (
                f"🆔 شماره درخواست: {req_id}\n"
                f"👤 نام کاربری: {username_line}\n"
                f"🆔 آیدی کاربر: {uid}\n"
                f"💰 {amount:,} سکه (معادل {amount:,} تومان)\n"
                f"💳 {card}"
            )
            bot.send_message(user_id, text, reply_markup=admin_withdraw_keyboard(req_id))
        safe_answer_callback(call.id, "✅ درخواست‌ها ارسال شد.")

    # ========== مدیریت کاربران (بن/آن‌بن) ==========
    elif data == 'admin_manage_users':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "👥 **مدیریت کاربران**\n\nلطفاً `user_id` کاربر مورد نظر را وارد کنید تا وضعیت بن او تغییر کند.", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_BAN_USER}
        return

    # ========== مشاهده پروفایل کامل یک کاربر ==========
    elif data == 'admin_view_user':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "🔍 **مشاهده پروفایل کاربر**\n\nلطفاً `user_id` کاربر مورد نظر را ارسال کنید.", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_VIEW_USER}
        return

    # ========== تغییر وضعیت بن از داخل پروفایل ==========
    elif data.startswith('admin_toggle_ban_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        target_uid = int(data.split('_')[3])
        target_user = get_user(target_uid)
        if not target_user:
            safe_answer_callback(call.id, "❌ کاربر یافت نشد!", show_alert=True)
            return
        new_ban_status = 0 if target_user['banned'] == 1 else 1
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET banned=? WHERE user_id=?", (new_ban_status, target_uid))
        conn.commit()
        conn.close()
        status_text = "مسدود شد ❌" if new_ban_status == 1 else "آزاد شد ✅"
        safe_answer_callback(call.id, f"✅ کاربر {status_text}.")
        try:
            if new_ban_status == 1:
                bot.send_message(target_uid, "⛔ شما توسط ادمین مسدود شدید. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.")
            else:
                bot.send_message(target_uid, "✅ محدودیت شما توسط ادمین برداشته شد. خوش آمدید!")
        except:
            pass
        profile_text = build_user_profile_text(target_uid)
        try:
            bot.edit_message_text(profile_text, call.message.chat.id, call.message.message_id,
                                   reply_markup=admin_user_profile_keyboard(target_uid, new_ban_status == 1),
                                   parse_mode='Markdown')
        except:
            bot.send_message(user_id, profile_text, reply_markup=admin_user_profile_keyboard(target_uid, new_ban_status == 1), parse_mode='Markdown')
        return

    # ========== افزایش سریع موجودی از داخل پروفایل ==========
    elif data.startswith('admin_quick_addbal_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        target_uid = int(data.split('_')[3])
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"➕ **افزایش موجودی کاربر {target_uid}**\nتعداد سکه‌ای که می‌خواهید اضافه کنید را وارد کنید (عدد منفی برای کسر):", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_QUICK_ADD_BALANCE, 'target_uid': target_uid}
        return

    # ========== تغییر موجودی کاربر (قابلیت جدید) ==========
    elif data == 'admin_change_balance':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "🔄 **تغییر موجودی کاربر**\n\nلطفاً **آیدی عددی** یا **نام کاربری** (با @) کاربر مورد نظر را ارسال کنید.", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_CHANGE_BALANCE}
        return

    # ========== مدیریت کانال‌های اجباری ==========
    elif data == 'admin_manage_channels':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "📢 **مدیریت عضویت اجباری**\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=admin_channels_management_keyboard(), parse_mode='Markdown')
        return

    elif data == 'admin_add_channel':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "➕ **افزودن کانال جدید**\n\nلطفاً لینک کانال را ارسال کنید (مثال: https://t.me/username)", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_ADD_CHANNEL}
        return

    elif data == 'admin_list_channels':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        channels = get_required_channels(active_only=False)
        if not channels:
            bot.send_message(user_id, "📭 هیچ کانالی تعریف نشده است.")
            return
        bot.send_message(user_id, "📋 **لیست کانال‌های عضویت اجباری**\n\nبرای تغییر وضعیت یا حذف، روی دکمه‌ها کلیک کنید.", reply_markup=admin_channel_list_keyboard(), parse_mode='Markdown')
        return

    elif data.startswith('admin_toggle_channel_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        channel_id = int(data.split('_')[3])
        channels = get_required_channels(active_only=False)
        ch = next((c for c in channels if c['id'] == channel_id), None)
        if not ch:
            safe_answer_callback(call.id, "❌ کانال یافت نشد!", show_alert=True)
            return
        new_active = 0 if ch['active'] else 1
        toggle_channel_active(channel_id, new_active)
        status_text = "فعال شد ✅" if new_active else "غیرفعال شد ❌"
        safe_answer_callback(call.id, f"✅ کانال {ch['username']} {status_text}.")
        channels = get_required_channels(active_only=False)
        if not channels:
            bot.edit_message_text("📭 هیچ کانالی تعریف نشده است.", call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text("📋 **لیست کانال‌های عضویت اجباری**\n\nبرای تغییر وضعیت یا حذف، روی دکمه‌ها کلیک کنید.",
                                  call.message.chat.id, call.message.message_id,
                                  reply_markup=admin_channel_list_keyboard(), parse_mode='Markdown')
        return

    elif data.startswith('admin_delete_channel_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        channel_id = int(data.split('_')[3])
        channels = get_required_channels(active_only=False)
        ch = next((c for c in channels if c['id'] == channel_id), None)
        if not ch:
            safe_answer_callback(call.id, "❌ کانال یافت نشد!", show_alert=True)
            return
        remove_required_channel(channel_id)
        safe_answer_callback(call.id, f"✅ کانال {ch['username']} حذف شد.")
        channels = get_required_channels(active_only=False)
        if not channels:
            bot.edit_message_text("📭 هیچ کانالی تعریف نشده است.", call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text("📋 **لیست کانال‌های عضویت اجباری**\n\nبرای تغییر وضعیت یا حذف، روی دکمه‌ها کلیک کنید.",
                                  call.message.chat.id, call.message.message_id,
                                  reply_markup=admin_channel_list_keyboard(), parse_mode='Markdown')
        return

    # ========== لیست آخرین کاربران عضو شده ==========
    elif data == 'admin_recent_users':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id, username, balance, registered_at FROM users ORDER BY registered_at DESC LIMIT 15")
        rows = c.fetchall()
        conn.close()
        if not rows:
            safe_answer_callback(call.id, "📭 هیچ کاربری ثبت نشده.")
            return
        text = "🕓 **۱۵ کاربر آخر**\n─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        for uid, uname, bal, reg in rows:
            reg_short = reg[:10] if reg else "-"
            text += f"🆔 `{uid}` | @{uname or '-'} | 🪙 {bal:,} | 📅 {reg_short}\n"
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, text, parse_mode='Markdown')
        safe_answer_callback(call.id)
        return

    # ========== لیست کاربران مسدود ==========
    elif data == 'admin_banned_users':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id, username FROM users WHERE banned=1")
        rows = c.fetchall()
        conn.close()
        if not rows:
            safe_answer_callback(call.id, "📭 هیچ کاربر مسدودی وجود ندارد.")
            return
        text = "🚫 **کاربران مسدود شده**\n─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
        for uid, uname in rows:
            text += f"🆔 `{uid}` | @{uname or '-'}\n"
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, text, parse_mode='Markdown')
        safe_answer_callback(call.id)
        return

    # ========== لیست برداشت‌های تأییدشده ==========
    elif data == 'admin_approved_withdrawals':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount_toman, card_number, created_at FROM withdraw_requests WHERE status='approved' ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.send_message(user_id, "📭 هیچ برداشت تأیید شده‌ای وجود ندارد.")
            safe_answer_callback(call.id, "خالی")
            return
        text = "✅ **لیست برداشت‌های تأییدشده**\n\n"
        for row in rows:
            req_id, uid, amount, card, created = row
            user_info = get_user(uid)
            username = user_info['username'] if user_info else str(uid)
            text += f"🆔 {req_id} | 👤 {username} | 💰 {amount:,} سکه | 💳 {card}\n"
        bot.send_message(user_id, text, parse_mode='Markdown')
        safe_answer_callback(call.id, "لیست ارسال شد.")

    elif data.startswith('approve_purchase_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        request_id = int(data.split('_')[2])
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id, coins FROM purchase_requests WHERE id=? AND status='pending'", (request_id,))
        row = c.fetchone()
        if not row:
            safe_answer_callback(call.id, "❌ یافت نشد!", show_alert=True)
            conn.close()
            return
        uid, coins = row
        update_balance(uid, coins)
        c.execute("UPDATE purchase_requests SET status='approved' WHERE id=?", (request_id,))
        conn.commit()
        conn.close()
        bot.send_message(uid, f"✅ خرید تأیید شد!\n🪙 {coins:,} سکه اضافه شد.\n🪙 موجودی: {get_balance(uid):,} سکه", parse_mode='Markdown')
        safe_answer_callback(call.id, "✅ خرید تأیید شد.")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"✅ خرید {request_id} تأیید شد.")
        send_to_miniapp(uid, {
            'action': 'purchase_approved',
            'coins': coins,
            'new_balance': get_balance(uid)
        })

    elif data.startswith('reject_purchase_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        request_id = int(data.split('_')[2])
        user_states[user_id] = {'state': STATE_ADMIN_REJECT_REASON, 'reject_request_id': request_id, 'reject_type': 'purchase'}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"❌ دلیل رد درخواست {request_id}:", parse_mode='Markdown')
        safe_answer_callback(call.id, "📝 دلیل را وارد کنید.")

    elif data.startswith('approve_withdraw_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        request_id = int(data.split('_')[2])
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT user_id, amount_toman FROM withdraw_requests WHERE id=? AND status='pending'", (request_id,))
        row = c.fetchone()
        if not row:
            safe_answer_callback(call.id, "❌ یافت نشد!", show_alert=True)
            conn.close()
            return
        uid, amount_toman = row
        if get_balance(uid) < amount_toman:
            safe_answer_callback(call.id, f"❌ موجودی سکه کافی نیست! ({get_balance(uid):,} سکه)", show_alert=True)
            conn.close()
            return
        update_balance(uid, -amount_toman)
        c.execute("UPDATE withdraw_requests SET status='approved' WHERE id=?", (request_id,))
        conn.commit()
        conn.close()
        bot.send_message(uid, f"✅ برداشت {amount_toman:,} سکه (معادل {amount_toman:,} تومان) تأیید شد.\n🪙 موجودی: {get_balance(uid):,} سکه", parse_mode='Markdown')
        safe_answer_callback(call.id, "✅ برداشت تأیید شد.")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"✅ برداشت {request_id} تأیید شد.")
        send_to_miniapp(uid, {
            'action': 'withdraw_approved',
            'amount': amount_toman,
            'new_balance': get_balance(uid)
        })

    elif data.startswith('reject_withdraw_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        request_id = int(data.split('_')[2])
        user_states[user_id] = {'state': STATE_ADMIN_REJECT_REASON, 'reject_request_id': request_id, 'reject_type': 'withdraw'}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"❌ دلیل رد درخواست {request_id}:", parse_mode='Markdown')
        safe_answer_callback(call.id, "📝 دلیل را وارد کنید.")

    elif data == 'admin_add_balance':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "➕ `user_id تعداد_سکه`\nمثال: `123456789 5000`", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_ADD_BALANCE}

    elif data == 'admin_set_card':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "💳 شماره کارت جدید را وارد کنید:", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_SET_CARD}

    elif data == 'admin_broadcast':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "📢 پیام همگانی را وارد کنید:", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_BROADCAST}

    elif data == 'admin_private_msg':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "📩 `user_id پیام`\nمثال: `123456789 سلام`", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_PRIVATE_MSG}

    elif data == 'admin_stats':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        today = date.today().isoformat()
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE registered_at LIKE ?", (f"{today}%",))
        new_users_today = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE banned=1")
        banned_count = c.fetchone()[0]
        c.execute("SELECT SUM(balance) FROM users")
        total_coins = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM games WHERE status='finished'")
        games = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM games WHERE status='finished' AND created_at LIKE ?", (f"{today}%",))
        games_today = c.fetchone()[0]
        c.execute("SELECT COUNT(*), COALESCE(SUM(amount_toman),0) FROM purchase_requests WHERE status='pending'")
        pending_purchase_count, pending_purchase_sum = c.fetchone()
        c.execute("SELECT COUNT(*), COALESCE(SUM(amount_toman),0) FROM withdraw_requests WHERE status='pending'")
        pending_withdraw_count, pending_withdraw_sum = c.fetchone()
        c.execute("SELECT COUNT(*), COALESCE(SUM(coins),0) FROM purchase_requests WHERE status='approved'")
        approved_purchase_count, approved_purchase_coins = c.fetchone()
        c.execute("SELECT COUNT(*), COALESCE(SUM(amount_toman),0) FROM withdraw_requests WHERE status='approved'")
        approved_withdraw_count, approved_withdraw_sum = c.fetchone()
        conn.close()
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        text = (
            f"📊 **آمار کامل ربات**\n"
            f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
            f"👥 کل کاربران: **{users}**\n"
            f"🆕 کاربران جدید امروز: **{new_users_today}**\n"
            f"🚫 کاربران مسدود: **{banned_count}**\n\n"
            f"🪙 مجموع موجودی کاربران: **{total_coins:,} سکه**\n\n"
            f"🎮 کل دوئل‌های انجام‌شده: **{games}**\n"
            f"🎮 دوئل‌های امروز: **{games_today}**\n\n"
            f"🪙 خریدهای در انتظار: **{pending_purchase_count}** ({pending_purchase_sum:,} تومان)\n"
            f"🏦 برداشت‌های در انتظار: **{pending_withdraw_count}** ({pending_withdraw_sum:,} سکه)\n\n"
            f"✅ خریدهای تأییدشده: **{approved_purchase_count}** ({approved_purchase_coins:,} سکه)\n"
            f"✅ برداشت‌های تأییدشده: **{approved_withdraw_count}** ({approved_withdraw_sum:,} سکه)\n"
            f"⚙️ سقف بازی روزانه فعلی: **{get_daily_game_limit()}**"
        )
        bot.send_message(user_id, text, parse_mode='Markdown')

    elif data == 'back_to_main':
        user_states[user_id] = {'state': STATE_MAIN}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        send_main_menu(user_id)

    elif data.startswith('admin_reply_user_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        target_user_id = int(data.split('_')[3])
        user_states[user_id] = {'state': STATE_ADMIN_REPLY_USER, 'reply_target': target_user_id}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"📩 پیام خود را برای کاربر {target_user_id} وارد کنید:", parse_mode='Markdown')
        safe_answer_callback(call.id, "پیام را بنویسید.")

    # ========== آمار کاربران (جدید) ==========
    elif data == 'admin_user_stats':
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, "📊 **آمار کاربر**\n\nلطفاً **آیدی عددی** یا **نام کاربری** (با @) کاربر مورد نظر را ارسال کنید.", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_USER_STATS_INPUT}
        return

    # ========== مدیریت بن از داخل آمار ==========
    elif data.startswith('admin_stats_ban_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        target_uid = int(data.split('_')[3])
        target_user = get_user(target_uid)
        if not target_user:
            safe_answer_callback(call.id, "❌ کاربر یافت نشد!", show_alert=True)
            return
        new_ban_status = 0 if target_user['banned'] == 1 else 1
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET banned=? WHERE user_id=?", (new_ban_status, target_uid))
        conn.commit()
        conn.close()
        status_text = "مسدود شد ❌" if new_ban_status == 1 else "آزاد شد ✅"
        safe_answer_callback(call.id, f"✅ کاربر {status_text}.")
        try:
            if new_ban_status == 1:
                bot.send_message(target_uid, "⛔ شما توسط ادمین مسدود شدید. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.")
            else:
                bot.send_message(target_uid, "✅ محدودیت شما توسط ادمین برداشته شد. خوش آمدید!")
        except:
            pass
        stats = get_user_detailed_stats(target_uid)
        if stats:
            text = format_detailed_stats(stats)
            try:
                bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                                      reply_markup=admin_stats_keyboard(target_uid),
                                      parse_mode='Markdown')
            except:
                bot.send_message(user_id, text, reply_markup=admin_stats_keyboard(target_uid), parse_mode='Markdown')
        return

    # ========== افزایش موجودی از داخل آمار ==========
    elif data.startswith('admin_stats_addbal_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        target_uid = int(data.split('_')[3])
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"➕ **افزایش موجودی کاربر {target_uid}**\nتعداد سکه‌ای که می‌خواهید اضافه کنید را وارد کنید (عدد منفی برای کسر):", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_STATS_ADD_BALANCE, 'target_uid': target_uid}
        return

    # ========== تغییر موجودی از داخل آمار ==========
    elif data.startswith('admin_stats_changebal_'):
        if not is_admin(user_id, call.from_user.username):
            safe_answer_callback(call.id, "⛔ دسترسی غیرمجاز", show_alert=True)
            return
        target_uid = int(data.split('_')[3])
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(user_id, f"🔄 **تغییر موجودی کاربر {target_uid}**\nموجودی جدید را به **سکه** وارد کنید (عدد صحیح):", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_STATS_CHANGE_BALANCE, 'target_uid': target_uid}
        return

# ---------- دریافت پیام‌های متنی و عکس ----------
@bot.message_handler(content_types=['text', 'photo'])
def handle_text_and_photo(message):
    user_id = message.from_user.id
    username = message.from_user.username or ''

    if message.text and message.text.strip() == SECRET_ADMIN_COMMAND:
        if not is_admin(user_id, username):
            bot.reply_to(message, "⛔ شما دسترسی ادمین ندارید.")
            return
        if is_banned(user_id):
            bot.reply_to(message, "⛔ شما مسدود هستید.")
            return
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        bot.send_message(message.chat.id, "🔐 **پنل مدیریت**", reply_markup=admin_panel_keyboard(), parse_mode='Markdown')
        return

    state = user_states.get(user_id)
    user = get_or_create_user(user_id, message.from_user.username or message.from_user.first_name)

    if is_banned(user_id):
        bot.reply_to(message, "⛔ شما توسط ادمین مسدود شده‌اید. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.")
        return

    if not is_member_all_channels(user_id):
        send_main_menu(user_id)
        return

    # ---------- ثبت شماره کارت ----------
    if state and state.get('state') == STATE_REGISTER_CARD:
        card = message.text.strip().replace(' ', '')
        if not card.isdigit() or len(card) != 16:
            bot.reply_to(message, "❌ شماره کارت ۱۶ رقم باید باشد!")
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET card_number=? WHERE user_id=?", (card, int(user_id)))
        conn.commit()
        conn.close()
        user_states[user_id] = {'state': STATE_MAIN}
        bot.reply_to(message, "✅ شماره کارت با موفقیت ثبت شد.")
        admin_text = f"💳 **ثبت شماره کارت جدید**\n👤 {message.from_user.first_name} (@{message.from_user.username})\n🆔 {user_id}\n🔢 شماره کارت: {card}"
        bot.send_message(ADMIN_IDS[0], admin_text, reply_markup=admin_reply_user_keyboard(user_id), parse_mode='Markdown')
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if state.get('from_withdraw'):
            show_withdraw_info(user_id)
        else:
            send_main_menu(user_id)
        return

    # ---------- ادمین پاسخ به کاربر ----------
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_REPLY_USER:
        target = state.get('reply_target')
        if not target:
            bot.reply_to(message, "❌ خطا!")
            user_states[user_id] = None
            return
        reply_text = message.text
        try:
            bot.send_message(target, f"📩 **پاسخ ادمین:**\n\n{reply_text}", parse_mode='Markdown')
            bot.reply_to(message, f"✅ پیام به کاربر {target} ارسال شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")
        user_states[user_id] = None
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        return

    # ---------- رد درخواست با دلیل (ادمین) ----------
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_REJECT_REASON:
        reason = message.text
        request_id = state.get('reject_request_id')
        reject_type = state.get('reject_type')
        if not request_id or not reject_type:
            bot.reply_to(message, "❌ خطا در شناسایی درخواست!")
            user_states[user_id] = None
            return

        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()

        if reject_type == 'purchase':
            c.execute("SELECT user_id FROM purchase_requests WHERE id=? AND status='pending'", (request_id,))
            row = c.fetchone()
            if not row:
                bot.reply_to(message, "❌ درخواست یافت نشد یا قبلاً پردازش شده!")
                conn.close()
                user_states[user_id] = None
                return
            uid = row[0]
            c.execute("UPDATE purchase_requests SET status='rejected', reject_reason=? WHERE id=?", (reason, request_id))
            conn.commit()
            conn.close()
            admin_username = f"@{message.from_user.username}" if message.from_user.username else f"ادمین {message.from_user.first_name}"
            try:
                bot.send_message(
                    uid,
                    f"❌ درخواست خرید شما رد شد\n"
                    f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                    f"📝 دلیل: {reason}\n"
                    f"👤 رد شده توسط: {admin_username}\n\n"
                    f"📞 پشتیبانی: {ADMIN_USERNAMES[0]}", parse_mode='Markdown'
                )
                bot.reply_to(message, f"✅ درخواست خرید شماره {request_id} با موفقیت رد شد و دلیل «{reason}» به کاربر اطلاع داده شد.")
            except Exception as e:
                bot.reply_to(message, f"⚠️ درخواست رد شد، اما ارسال پیام به کاربر با خطا مواجه شد: {e}")
            try:
                send_to_miniapp(uid, {
                    'action': 'purchase_rejected',
                    'reason': reason,
                    'admin': admin_username
                })
            except Exception:
                pass

        elif reject_type == 'withdraw':
            c.execute("SELECT user_id FROM withdraw_requests WHERE id=? AND status='pending'", (request_id,))
            row = c.fetchone()
            if not row:
                bot.reply_to(message, "❌ درخواست یافت نشد یا قبلاً پردازش شده!")
                conn.close()
                user_states[user_id] = None
                return
            uid = row[0]
            c.execute("UPDATE withdraw_requests SET status='rejected', reject_reason=? WHERE id=?", (reason, request_id))
            conn.commit()
            conn.close()
            admin_username = f"@{message.from_user.username}" if message.from_user.username else f"ادمین {message.from_user.first_name}"
            try:
                bot.send_message(
                    uid,
                    f"❌ درخواست برداشت شما رد شد\n"
                    f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                    f"📝 دلیل: {reason}\n"
                    f"👤 رد شده توسط: {admin_username}\n\n"
                    f"📞 پشتیبانی: {ADMIN_USERNAMES[0]}", parse_mode='Markdown'
                )
                bot.reply_to(message, f"✅ درخواست برداشت شماره {request_id} با موفقیت رد شد و دلیل «{reason}» به کاربر اطلاع داده شد.")
            except Exception as e:
                bot.reply_to(message, f"⚠️ درخواست رد شد، اما ارسال پیام به کاربر با خطا مواجه شد: {e}")

        user_states[user_id] = None
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        return

    # ---------- خرید (رسید) ----------
    if state and state.get('state') == STATE_PURCHASE_RECEIPT:
        amount = state.get('purchase_amount')
        coins = state.get('purchase_coins')
        if not amount:
            bot.reply_to(message, "❌ خطا!")
            return
        receipt_text = message.text if message.text else "عکس"
        receipt_photo_id = None
        if message.photo:
            receipt_photo_id = message.photo[-1].file_id
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("INSERT INTO purchase_requests (user_id, amount_toman, coins, status, receipt_text, receipt_photo_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (int(user_id), amount, coins, 'pending', receipt_text, receipt_photo_id, now))
        request_id = c.lastrowid
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ رسید ثبت شد!\n🆔 {request_id}\n⏳ منتظر تأیید ادمین...")
        user_info = get_user(user_id)
        username_line = f"@{user_info['username']}" if user_info['username'] else "ثبت نشده"
        admin_text = (
            f"📩 خرید جدید\n"
            f"🆔 شماره درخواست: {request_id}\n"
            f"👤 نام کاربری: {username_line}\n"
            f"🆔 آیدی کاربر: {user_id}\n"
            f"💰 {amount:,} تومان\n"
            f"🪙 {coins:,} سکه\n"
            f"📝 {receipt_text}"
        )
        if receipt_photo_id:
            bot.send_photo(ADMIN_IDS[0], receipt_photo_id, caption=admin_text, reply_markup=admin_purchase_keyboard(request_id))
        else:
            bot.send_message(ADMIN_IDS[0], admin_text, reply_markup=admin_purchase_keyboard(request_id))
        user_states[user_id] = {'state': STATE_MAIN}
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        send_main_menu(user_id)
        return

    # ---------- ثبت شماره کارت در حین برداشت ----------
    if state and state.get('state') == STATE_WITHDRAW_CARD:
        card = message.text.strip().replace(' ', '')
        if not card.isdigit() or len(card) != 16:
            bot.reply_to(message, "❌ شماره کارت ۱۶ رقم باید باشد!")
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET card_number=? WHERE user_id=?", (card, int(user_id)))
        conn.commit()
        conn.close()
        user_states[user_id] = {'state': STATE_MAIN}
        bot.reply_to(message, "✅ شماره کارت ثبت شد!\nحالا می‌توانید برداشت کنید.")
        admin_text = f"💳 **ثبت شماره کارت جدید (هنگام برداشت)**\n👤 {message.from_user.first_name} (@{message.from_user.username})\n🆔 {user_id}\n🔢 شماره کارت: {card}"
        bot.send_message(ADMIN_IDS[0], admin_text, reply_markup=admin_reply_user_keyboard(user_id), parse_mode='Markdown')
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        send_main_menu(user_id)
        return

    # ---------- برداشت مبلغ ----------
    if state and state.get('state') == STATE_WITHDRAW_AMOUNT:
        try:
            amount_coins = int(message.text.strip())
        except ValueError:
            bot.reply_to(message, "❌ عدد معتبر وارد کنید!")
            return
        min_amount = int(get_setting('min_withdraw') or 10000)
        max_amount = int(get_setting('max_withdraw') or 250000)
        balance = get_balance(user_id)
        if amount_coins < min_amount:
            bot.reply_to(message, f"❌ حداقل {min_amount:,} سکه!")
            return
        if amount_coins > max_amount:
            bot.reply_to(message, f"❌ حداکثر {max_amount:,} سکه!")
            return
        if amount_coins > balance:
            bot.reply_to(message, f"❌ موجودی شما {balance:,} سکه است!")
            return
        daily_used = get_daily_withdrawal_total(user_id)
        if daily_used + amount_coins > max_amount:
            remaining = max_amount - daily_used
            bot.reply_to(message, f"❌ شما امروز {daily_used:,} سکه برداشت کرده‌اید. تنها {remaining:,} سکه دیگر می‌توانید برداشت کنید.")
            return
        user = get_user(user_id)
        if not user['card_number']:
            bot.reply_to(message, "❌ شماره کارت ثبت نشده!")
            return
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute("INSERT INTO withdraw_requests (user_id, amount_toman, card_number, status, created_at) VALUES (?, ?, ?, ?, ?)",
                  (int(user_id), amount_coins, user['card_number'], 'pending', now))
        request_id = c.lastrowid
        conn.commit()
        conn.close()
        user_states[user_id] = {'state': STATE_MAIN}
        bot.reply_to(message, f"✅ درخواست برداشت ثبت شد!\n🆔 {request_id}\n💰 {amount_coins:,} سکه (معادل {amount_coins:,} تومان)\n💳 {user['card_number']}\n⏳ منتظر تأیید ادمین...")
        admin_text = (
            f"📩 برداشت جدید\n"
            f"🆔 شماره درخواست: {request_id}\n"
            f"👤 نام: {message.from_user.first_name} (@{message.from_user.username})\n"
            f"🆔 آیدی کاربر: {user_id}\n"
            f"💰 {amount_coins:,} سکه (معادل {amount_coins:,} تومان)\n"
            f"💳 {user['card_number']}"
        )
        bot.send_message(ADMIN_IDS[0], admin_text, reply_markup=admin_withdraw_keyboard(request_id))
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        send_main_menu(user_id)
        return

    # ---------- مدیریت کاربران (بن/آن‌بن) ----------
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_BAN_USER:
        try:
            target_uid = int(message.text.strip())
        except ValueError:
            bot.reply_to(message, "❌ لطفاً یک عدد (user_id) معتبر وارد کنید.")
            return
        target_user = get_user(target_uid)
        if not target_user:
            bot.reply_to(message, "❌ کاربری با این شناسه یافت نشد.")
            user_states[user_id] = None
            return
        new_ban_status = 0 if target_user['banned'] == 1 else 1
        conn = sqlite3.connect('duel_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET banned=? WHERE user_id=?", (new_ban_status, target_uid))
        conn.commit()
        conn.close()
        status_text = "بن شد ❌" if new_ban_status == 1 else "آن‌بن شد ✅"
        bot.reply_to(message, f"✅ کاربر {target_uid} با موفقیت {status_text}.")
        user_states[user_id] = None
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        try:
            if new_ban_status == 1:
                bot.send_message(target_uid, "⛔ شما توسط ادمین مسدود شدید. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.")
            else:
                bot.send_message(target_uid, "✅ محدودیت شما توسط ادمین برداشته شد. خوش آمدید!")
        except:
            pass
        return

    # ---------- مشاهده پروفایل کامل یک کاربر ----------
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_VIEW_USER:
        try:
            target_uid = int(message.text.strip())
        except ValueError:
            bot.reply_to(message, "❌ لطفاً یک عدد (user_id) معتبر وارد کنید.")
            return
        profile_text = build_user_profile_text(target_uid)
        user_states[user_id] = None
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        if not profile_text:
            bot.send_message(user_id, "❌ کاربری با این شناسه یافت نشد.")
            return
        target_user = get_user(target_uid)
        bot.send_message(user_id, profile_text,
                          reply_markup=admin_user_profile_keyboard(target_uid, target_user['banned'] == 1),
                          parse_mode='Markdown')
        return

    # ---------- افزایش/کاهش سریع موجودی از داخل پروفایل ----------
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_QUICK_ADD_BALANCE:
        target_uid = state.get('target_uid')
        try:
            amount = int(message.text.strip())
        except ValueError:
            bot.reply_to(message, "❌ لطفاً یک عدد صحیح وارد کنید.")
            return
        if not get_user(target_uid):
            bot.reply_to(message, "❌ کاربر یافت نشد.")
            user_states[user_id] = None
            return
        update_balance(target_uid, amount)
        user_states[user_id] = None
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        bot.reply_to(message, f"✅ موجودی کاربر {target_uid} به‌روزرسانی شد.\n🪙 موجودی فعلی: {get_balance(target_uid):,} سکه")
        try:
            if amount > 0:
                bot.send_message(target_uid, f"🎁 مبلغ {amount:,} سکه توسط ادمین به حساب شما اضافه شد.\n🪙 موجودی فعلی: {get_balance(target_uid):,} سکه", parse_mode='Markdown')
            elif amount < 0:
                bot.send_message(target_uid, f"⚠️ مبلغ {abs(amount):,} سکه توسط ادمین از حساب شما کسر شد.\n🪙 موجودی فعلی: {get_balance(target_uid):,} سکه", parse_mode='Markdown')
        except:
            pass
        return

    # ========== تغییر موجودی کاربر (ادمین) - مرحله اول: دریافت آیدی ==========
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_CHANGE_BALANCE:
        identifier = message.text.strip()
        target_uid = None
        
        if identifier.isdigit():
            target_uid = int(identifier)
        elif identifier.startswith('@'):
            conn = sqlite3.connect('duel_bot.db')
            c = conn.cursor()
            c.execute("SELECT user_id FROM users WHERE username=?", (identifier[1:],))
            row = c.fetchone()
            conn.close()
            if row:
                target_uid = row[0]
        
        if target_uid is None:
            bot.reply_to(message, "❌ کاربری با این شناسه یافت نشد. لطفاً آیدی عددی یا نام کاربری معتبر (با @) ارسال کنید.")
            return
        
        target_user = get_user(target_uid)
        if not target_user:
            # کاربر وجود ندارد، ایجاد می‌کنیم
            create_user(target_uid, str(target_uid))
            target_user = get_user(target_uid)
            if not target_user:
                bot.reply_to(message, "❌ خطا در ایجاد کاربر!")
                user_states[user_id] = None
                return
        
        current_balance = target_user['balance']
        bot.send_message(user_id,
            f"🔍 **کاربر یافت شد:**\n"
            f"🆔 شناسه: `{target_uid}`\n"
            f"📛 نام کاربری: @{target_user['username'] or 'ندارد'}\n"
            f"🪙 موجودی فعلی: **{current_balance:,} سکه**\n\n"
            f"📝 موجودی جدید را به **سکه** وارد کنید (عدد صحیح):", parse_mode='Markdown')
        user_states[user_id] = {'state': STATE_ADMIN_CHANGE_BALANCE_AMOUNT, 'target_uid': target_uid, 'old_balance': current_balance}
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        return

    # ========== تغییر موجودی کاربر (ادمین) - مرحله دوم: دریافت مبلغ جدید ==========
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_CHANGE_BALANCE_AMOUNT:
        target_uid = state.get('target_uid')
        old_balance = state.get('old_balance')
        if not target_uid or old_balance is None:
            bot.reply_to(message, "❌ خطا در فرآیند!")
            user_states[user_id] = None
            return
        try:
            new_balance = int(message.text.strip())
            if new_balance < 0:
                raise ValueError("منفی")
        except ValueError:
            bot.reply_to(message, "❌ لطفاً یک عدد صحیح **نامنفی** وارد کنید.")
            return
        # اعمال تغییر
        set_balance(target_uid, new_balance)
        user_states[user_id] = None
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        bot.reply_to(message,
            f"✅ موجودی کاربر `{target_uid}` با موفقیت تغییر کرد.\n"
            f"🪙 موجودی قبلی: {old_balance:,} سکه\n"
            f"🪙 موجودی جدید: {new_balance:,} سکه", parse_mode='Markdown')
        
        # اطلاع‌رسانی به کاربر
        target_user = get_user(target_uid)
        if target_user:
            admin_link = f"https://t.me/{ADMIN_USERNAMES[0].replace('@','')}"
            now = datetime.now()
            date_str = now.strftime("%Y/%m/%d")
            time_str = now.strftime("%H:%M:%S")
            msg = (
                f"💰 **تغییر موجودی حساب شما**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"🆔 شناسه کاربری: `{target_uid}`\n"
                f"📛 نام کاربری: @{target_user['username'] or 'ندارد'}\n"
                f"📅 تاریخ: {date_str}\n"
                f"⏰ ساعت: {time_str}\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"🪙 موجودی قبلی: **{old_balance:,} سکه**\n"
                f"🪙 موجودی جدید: **{new_balance:,} سکه**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"👤 تغییر توسط ادمین انجام شده است.\n\n"
                f"📞 در صورت نیاز با پشتیبانی تماس بگیرید:\n"
                f"[تماس با ادمین]({admin_link})"
            )
            try:
                bot.send_message(target_uid, msg, parse_mode='Markdown')
            except Exception as e:
                bot.send_message(user_id, f"⚠️ ارسال پیام به کاربر با خطا مواجه شد: {e}")
        return

    # ========== افزودن کانال اجباری (ادمین) ==========
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_ADD_CHANNEL:
        link = message.text.strip()
        username = None
        if 't.me/' in link:
            if link.startswith('https://t.me/'):
                username = '@' + link.split('https://t.me/')[-1].split('?')[0].split('/')[0]
            elif link.startswith('http://t.me/'):
                username = '@' + link.split('http://t.me/')[-1].split('?')[0].split('/')[0]
            elif link.startswith('t.me/'):
                username = '@' + link.split('t.me/')[-1].split('?')[0].split('/')[0]
        elif link.startswith('@'):
            username = link
        
        if not username:
            bot.reply_to(message, "❌ لینک نامعتبر است. لطفاً لینک کانال را به‌صورت `https://t.me/username` ارسال کنید.")
            return
        
        channels = get_required_channels(active_only=False)
        for ch in channels:
            if ch['username'] == username:
                bot.reply_to(message, f"⚠️ کانال {username} قبلاً در لیست وجود دارد.")
                user_states[user_id] = None
                return
        
        # بررسی عضویت ربات در کانال (اختیاری)
        try:
            bot.get_chat_member(username, bot.get_me().id)
        except:
            bot.reply_to(message, f"⚠️ ربات در کانال {username} عضو نیست یا دسترسی ندارد. لطفاً ابتدا ربات را به عنوان ادمین به کانال اضافه کنید.")
            # با این حال اجازه افزودن داده می‌شود
        
        add_required_channel(link, username)
        user_states[user_id] = None
        bot.reply_to(message, f"✅ کانال {username} با موفقیت به لیست عضویت اجباری اضافه شد.\nهمه کاربران (قدیم و جدید) باید در این کانال عضو شوند.")
        
        threading.Thread(target=notify_all_users_about_new_channel, args=(link, username)).start()
        
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        return

    # ========== آمار کاربران (دریافت آیدی) ==========
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_USER_STATS_INPUT:
        identifier = message.text.strip()
        target_uid = None
        
        if identifier.isdigit():
            target_uid = int(identifier)
        elif identifier.startswith('@'):
            conn = sqlite3.connect('duel_bot.db')
            c = conn.cursor()
            c.execute("SELECT user_id FROM users WHERE username=?", (identifier[1:],))
            row = c.fetchone()
            conn.close()
            if row:
                target_uid = row[0]
        
        if target_uid is None:
            bot.reply_to(message, "❌ کاربری با این شناسه یافت نشد. لطفاً آیدی عددی یا نام کاربری معتبر (با @) ارسال کنید.")
            return
        
        stats = get_user_detailed_stats(target_uid)
        if not stats:
            bot.reply_to(message, "❌ کاربر یافت نشد.")
            user_states[user_id] = None
            return
        
        text = format_detailed_stats(stats)
        user_states[user_id] = {'state': STATE_ADMIN_USER_STATS_VIEW, 'target_uid': target_uid}
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        bot.send_message(user_id, text, reply_markup=admin_stats_keyboard(target_uid), parse_mode='Markdown')
        return

    # ========== افزایش موجودی از داخل آمار (دریافت مبلغ) ==========
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_STATS_ADD_BALANCE:
        target_uid = state.get('target_uid')
        try:
            amount = int(message.text.strip())
        except ValueError:
            bot.reply_to(message, "❌ لطفاً یک عدد صحیح وارد کنید.")
            return
        if not get_user(target_uid):
            bot.reply_to(message, "❌ کاربر یافت نشد.")
            user_states[user_id] = None
            return
        update_balance(target_uid, amount)
        user_states[user_id] = {'state': STATE_ADMIN_USER_STATS_VIEW, 'target_uid': target_uid}
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        bot.reply_to(message, f"✅ موجودی کاربر {target_uid} به‌روزرسانی شد.\n🪙 موجودی فعلی: {get_balance(target_uid):,} سکه")
        try:
            if amount > 0:
                bot.send_message(target_uid, f"🎁 مبلغ {amount:,} سکه توسط ادمین به حساب شما اضافه شد.\n🪙 موجودی فعلی: {get_balance(target_uid):,} سکه", parse_mode='Markdown')
            elif amount < 0:
                bot.send_message(target_uid, f"⚠️ مبلغ {abs(amount):,} سکه توسط ادمین از حساب شما کسر شد.\n🪙 موجودی فعلی: {get_balance(target_uid):,} سکه", parse_mode='Markdown')
        except:
            pass
        stats = get_user_detailed_stats(target_uid)
        if stats:
            text = format_detailed_stats(stats)
            bot.send_message(user_id, text, reply_markup=admin_stats_keyboard(target_uid), parse_mode='Markdown')
        return

    # ========== تغییر موجودی از داخل آمار (دریافت مبلغ جدید) ==========
    if user_id in ADMIN_IDS and state and state.get('state') == STATE_ADMIN_STATS_CHANGE_BALANCE:
        target_uid = state.get('target_uid')
        try:
            new_balance = int(message.text.strip())
            if new_balance < 0:
                raise ValueError("منفی")
        except ValueError:
            bot.reply_to(message, "❌ لطفاً یک عدد صحیح **نامنفی** وارد کنید.")
            return
        old_balance = get_balance(target_uid)
        set_balance(target_uid, new_balance)
        user_states[user_id] = {'state': STATE_ADMIN_USER_STATS_VIEW, 'target_uid': target_uid}
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        bot.reply_to(message,
            f"✅ موجودی کاربر `{target_uid}` با موفقیت تغییر کرد.\n"
            f"🪙 موجودی قبلی: {old_balance:,} سکه\n"
            f"🪙 موجودی جدید: {new_balance:,} سکه", parse_mode='Markdown')
        
        target_user = get_user(target_uid)
        if target_user:
            admin_link = f"https://t.me/{ADMIN_USERNAMES[0].replace('@','')}"
            now = datetime.now()
            date_str = now.strftime("%Y/%m/%d")
            time_str = now.strftime("%H:%M:%S")
            msg = (
                f"💰 **تغییر موجودی حساب شما**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"🆔 شناسه کاربری: `{target_uid}`\n"
                f"📛 نام کاربری: @{target_user['username'] or 'ندارد'}\n"
                f"📅 تاریخ: {date_str}\n"
                f"⏰ ساعت: {time_str}\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"🪙 موجودی قبلی: **{old_balance:,} سکه**\n"
                f"🪙 موجودی جدید: **{new_balance:,} سکه**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"👤 تغییر توسط ادمین انجام شده است.\n\n"
                f"📞 در صورت نیاز با پشتیبانی تماس بگیرید:\n"
                f"[تماس با ادمین]({admin_link})"
            )
            try:
                bot.send_message(target_uid, msg, parse_mode='Markdown')
            except Exception as e:
                bot.send_message(user_id, f"⚠️ ارسال پیام به کاربر با خطا مواجه شد: {e}")
        stats = get_user_detailed_stats(target_uid)
        if stats:
            text = format_detailed_stats(stats)
            bot.send_message(user_id, text, reply_markup=admin_stats_keyboard(target_uid), parse_mode='Markdown')
        return

    # ---------- منوی متنی ----------
    menu_options = {
        "🎮 شروع دوئل": "game",
        "💰 موجودی": "balance",
        "👥 دعوت دوستان": "invite",
        "🪙 خرید سکه": "purchase",
        "🏦 برداشت وجه": "withdraw",
        "📞 پشتیبانی": "support",
        "🎮 دوئل گرافیکی": "graphic_duel"
    }
    if message.text in menu_options:
        cmd = menu_options[message.text]
        if cmd == "game":
            if not can_play_game(user_id):
                bot.reply_to(message, f"⛔ شما امروز {get_daily_game_limit()} دوئل انجام داده‌اید. لطفاً فردا تلاش کنید.")
                return
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            bot.send_message(user_id,
                f"🎯 **انتخاب مبلغ دوئل (به سکه)**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"🪙 موجودی فعلی: {get_balance(user_id):,} سکه\n"
                f"📊 بازی‌های امروز: {get_daily_games_count(user_id)}/{get_daily_game_limit()}",
                reply_markup=bet_amount_keyboard(), parse_mode='Markdown')
            user_states[user_id] = {'state': STATE_SELECTING_BET}
        elif cmd == "balance":
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            balance = get_balance(user_id)
            total_games, wins, loses, draws, level = get_user_stats(user_id)
            invites = user['total_invites']
            bot.send_message(user_id,
                f"💰 **موجودی شما**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"🆔 شناسه: `{user_id}`\n"
                f"⭐ سطح: {level}\n"
                f"🪙 موجودی: **{balance:,} سکه** (معادل {balance:,} تومان)\n"
                f"👥 دعوت‌های موفق: {invites}\n"
                f"🎮 تعداد دوئل‌ها: {total_games}\n"
                f"🏆 بردها: {wins}\n"
                f"🤝 مساوی‌ها: {draws}\n"
                f"📉 باخت‌ها: {loses}",
                reply_markup=get_main_menu_with_back(), parse_mode='Markdown')
        elif cmd == "invite":
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            bot_name = bot.get_me().username
            invite_link = f"https://t.me/{bot_name}?start=ref_{user_id}"
            text = (
                f"👥 **سیستم دعوت دوستان**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"🔢 تعداد دعوت‌های موفق: **{user['total_invites']}**\n"
                f"🎁 پاداش هر دعوت: **۱ سطح**\n\n"
                f"📋 **لینک دعوت شما:**\n"
                f"`{invite_link}`"
            )
            bot.send_message(user_id, text, reply_markup=get_main_menu_with_back(), parse_mode='Markdown')
        elif cmd == "purchase":
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            card_number = get_setting('card_number') or CARD_NUMBER
            card_owner = get_setting('card_owner') or CARD_OWNER
            text = (
                f"🪙 **خرید سکه (شارژ حساب)**\n"
                f"─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n"
                f"💳 هر ۱ تومان = ۱ سکه\n"
                f"📋 حداقل: ۵,۰۰۰ | حداکثر: ۵۰۰,۰۰۰\n\n"
                f"🏦 شماره کارت:\n`{card_number}`\nبه نام: {card_owner}\n\n"
                f"⚠️ **فقط کارت به کارت**\n"
                f"• رسید را ارسال کنید (عکس یا شماره پیگیری)\n"
                f"• مسئولیت واریز اشتباه با شماست"
            )
            bot.send_message(user_id, text, reply_markup=purchase_amount_keyboard(), parse_mode='Markdown')
            user_states[user_id] = {'state': STATE_PURCHASE_AMOUNT}
        elif cmd == "withdraw":
            show_withdraw_info(user_id, chat_id=message.chat.id, message_id=message.message_id)
        elif cmd == "support":
            support_text = (
                "📞 **پشتیبانی**\n\n"
                "برای ارتباط با پشتیبانی، روی دکمه زیر کلیک کنید.\n"
                "پاسخگوی سوالات و مشکلات شما هستیم."
            )
            keyboard = help_keyboard()
            bot.send_message(user_id, support_text, reply_markup=keyboard, parse_mode='Markdown')
        elif cmd == "graphic_duel":
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton(
                "🎮 دوئل گرافیکی",
                web_app=types.WebAppInfo(url="https://halydydyal7-lgtm.github.io/Hostbrmodedoel/")
            ))
            bot.send_message(user_id, "برای بازی روی دکمه زیر کلیک کنید:", reply_markup=keyboard)
        return

    # ---------- دستورات ادمین ----------
    if user_id in ADMIN_IDS and state:
        if state.get('state') == STATE_ADMIN_ADD_BALANCE:
            parts = message.text.split()
            if len(parts) != 2:
                bot.reply_to(message, "❌ فرمت: `user_id تعداد_سکه`")
                return
            try:
                uid = int(parts[0])
                amount = int(parts[1])
            except:
                bot.reply_to(message, "❌ عدد وارد کنید!")
                return
            update_balance(uid, amount)
            bot.reply_to(message, f"✅ {amount:,} سکه به کاربر {uid} اضافه شد.")
            user_states[user_id] = None
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            return

        elif state.get('state') == STATE_ADMIN_SET_CARD:
            card = message.text.strip().replace(' ', '')
            if not card.isdigit() or len(card) != 16:
                bot.reply_to(message, "❌ ۱۶ رقم!")
                return
            set_setting('card_number', card)
            bot.reply_to(message, f"✅ شماره کارت تغییر کرد:\n{card}")
            user_states[user_id] = None
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            return

        elif state.get('state') == STATE_ADMIN_EDIT_SETTING:
            key = state.get('setting_key')
            value = message.text.strip()
            if key in ['min_withdraw', 'max_withdraw', 'daily_game_limit']:
                try:
                    int_value = int(value)
                    if int_value <= 0:
                        raise ValueError
                    set_setting(key, str(int_value))
                    bot.reply_to(message, f"✅ {key} با موفقیت به {int_value:,} تغییر یافت.")
                except ValueError:
                    bot.reply_to(message, "❌ عدد معتبر (بزرگ‌تر از صفر) وارد کنید!")
            else:
                set_setting(key, value)
                bot.reply_to(message, f"✅ {key} با موفقیت تغییر یافت.")
            user_states[user_id] = None
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            return

        elif state.get('state') == STATE_ADMIN_BROADCAST:
            text = message.text
            conn = sqlite3.connect('duel_bot.db')
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            rows = c.fetchall()
            conn.close()
            count = 0
            for row in rows:
                try:
                    bot.send_message(row[0], f"📢 **پیام همگانی:**\n\n{text}", parse_mode='Markdown')
                    count += 1
                except:
                    pass
            bot.reply_to(message, f"✅ به {count} کاربر ارسال شد.")
            user_states[user_id] = None
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            return

        elif state.get('state') == STATE_ADMIN_PRIVATE_MSG:
            parts = message.text.split(maxsplit=1)
            if len(parts) != 2:
                bot.reply_to(message, "❌ فرمت: `user_id پیام`")
                return
            try:
                uid = int(parts[0])
                msg = parts[1]
            except:
                bot.reply_to(message, "❌ شناسه عددی!")
                return
            try:
                bot.send_message(uid, f"📩 **پیام از ادمین:**\n\n{msg}", parse_mode='Markdown')
                bot.reply_to(message, f"✅ به {uid} ارسال شد.")
            except Exception as e:
                bot.reply_to(message, f"❌ خطا: {e}")
            user_states[user_id] = None
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except:
                pass
            return

# ---------- تابع اطلاع‌رسانی به کاربران در مورد کانال جدید ----------
def notify_all_users_about_new_channel(channel_link, channel_username):
    conn = sqlite3.connect('duel_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    for row in rows:
        try:
            bot.send_message(row[0], f"📢 **کانال جدید عضویت اجباری**\n\nلطفاً برای ادامه استفاده از ربات، در کانال زیر عضو شوید:\n{channel_link}\nپس از عضویت، دکمه تأیید را بزنید.", parse_mode='Markdown')
        except:
            pass

# ---------- دستور پنل ادمین ----------
@bot.message_handler(commands=['admin'])
def admin_panel_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or ''
    if not is_admin(user_id, username):
        bot.reply_to(message, "⛔ شما دسترسی ادمین ندارید.")
        return
    if is_banned(user_id):
        bot.reply_to(message, "⛔ شما مسدود هستید.")
        return
    if not is_member_all_channels(user_id):
        send_main_menu(user_id)
        return
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    bot.send_message(message.chat.id, "🔐 **پنل مدیریت**", reply_markup=admin_panel_keyboard(), parse_mode='Markdown')

# ---------- اجرای ربات ----------
if __name__ == '__main__':
    print("🤖 ربات با پشتیبانی از مینی‌اپ جدید (Hostbrmodedoel) راه‌اندازی شد!")
    bot.polling(none_stop=True)
