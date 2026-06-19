import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import threading
import time
import datetime
import csv
import os
import random

# ==========================================
# CONFIGURATION
# ==========================================
BOT_TOKEN = "8908371597:AAEf9isbps5VyzeG3vKVnBPGZ3fSCrhH2lM"
CHANNEL_USERNAME = "@thealgorithamdestroyer" # For force subscribe
CHANNEL_URL = "https://t.me/thealgorithamdestroyer"
GAME_LINK = "https://www.rajaparty2.com/#/register?invitationCode=674176097525"
ADMIN_IDS = ["@Youknowmebitch"] # REPLACE WITH YOUR ACTUAL TELEGRAM USER ID

# Reward settings
INVITES_NEEDED_FOR_REWARD = 5
DAILY_BONUS_COINS = 10

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# ==========================================
# DATABASE SETUP (SQLite)
# ==========================================
db_lock = threading.Lock()

def get_db_connection():
    conn = sqlite3.connect("bot_database.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Create Users Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                referred_by INTEGER,
                balance INTEGER DEFAULT 0,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_bonus_date DATE,
                is_banned BOOLEAN DEFAULT 0,
                share_count INTEGER DEFAULT 0
            )
        ''')
        # Try to add column if it doesn't exist for older databases
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN share_count INTEGER DEFAULT 0")
        except:
            pass
        # Create Prediction Results Table (for self-learning)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prediction_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                mode TEXT,
                predicted_color TEXT,
                actual_color TEXT,
                color_correct INTEGER DEFAULT 0,
                predicted_size TEXT,
                actual_size TEXT,
                size_correct INTEGER DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

init_db()

# ==========================================
# DATABASE HELPER FUNCTIONS
# ==========================================
def add_user(user_id, username, first_name, referred_by=None):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone() is None:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, referred_by)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, referred_by))
            conn.commit()
            conn.close()
            return True # New user added
        conn.close()
        return False # User already exists

def get_user(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user

def get_referral_count(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

def get_share_count(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT share_count FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        count = row['share_count'] if row else 0
        conn.close()
        return count

def increment_share_count(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET share_count = share_count + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

def update_balance(user_id, amount):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()

def claim_daily_bonus(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        today = datetime.date.today().isoformat()
        cursor.execute("SELECT last_bonus_date FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result and result['last_bonus_date'] == today:
            conn.close()
            return False # Already claimed today
        
        cursor.execute("UPDATE users SET last_bonus_date = ?, balance = balance + ? WHERE user_id = ?", 
                       (today, DAILY_BONUS_COINS, user_id))
        conn.commit()
        conn.close()
        return True

# ==========================================
# SECURITY & MIDDLEWARES
# ==========================================
# Rate limiting dictionary
user_last_action = {}

def check_rate_limit(user_id):
    now = time.time()
    if user_id in user_last_action and now - user_last_action[user_id] < 1.0:
        return False # Too fast, ignore
    user_last_action[user_id] = now
    return True

def is_subscribed(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False # Default to False if error (e.g., bot not admin in channel)

def subscription_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_URL))
    markup.add(InlineKeyboardButton("✅ I have joined", callback_data="check_sub"))
    return markup

# ==========================================
# USER KEYBOARDS
# ==========================================
def main_menu_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("🔗 My Referral Link"), KeyboardButton("📊 My Stats"))
    markup.add(KeyboardButton("🎁 Daily Bonus"), KeyboardButton("🏆 Leaderboard"))
    markup.add(KeyboardButton("🎮 Play & Earn"), KeyboardButton("🔮 Raja Club Prediction"))
    return markup

# ==========================================
# BOT HANDLERS
# ==========================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    if not check_rate_limit(user_id): return
    
    # Check if user is banned
    user = get_user(user_id)
    if user and user['is_banned']:
        return
        
    args = message.text.split()
    referred_by = None
    
    # Parse referral ID
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id: # Prevent self-referral
            referred_by = ref_id

    # Add user to DB
    is_new = add_user(user_id, message.from_user.username, message.from_user.first_name, referred_by)
    
    # Send notification to referrer if it's a new successful referral
    if is_new and referred_by:
        try:
            bot.send_message(referred_by, f"🎉 <b>New Referral!</b>\n<a href='tg://user?id={user_id}'>{message.from_user.first_name}</a> joined using your link!")
        except:
            pass # Referrer might have blocked the bot

    # Force Subscribe Check
    if not is_subscribed(user_id):
        bot.send_message(
            user_id, 
            "🛑 <b>Access Denied!</b>\n\nYou must join our official channel to use this bot and start earning.",
            reply_markup=subscription_keyboard()
        )
        return

    welcome_text = (
        f"👋 Welcome <b>{message.from_user.first_name}</b>!\n\n"
        "Earn rewards by inviting friends and playing games. "
        "Use the menu below to navigate."
    )
    bot.send_message(user_id, welcome_text, reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
    if is_subscribed(call.message.chat.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(
            call.message.chat.id, 
            "✅ <b>Verification Successful!</b>\nWelcome to the bot.",
            reply_markup=main_menu_keyboard()
        )
    else:
        bot.answer_callback_query(call.id, "❌ You haven't joined the channel yet!", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "🔗 My Referral Link")
def referral_link(message):
    user_id = message.chat.id
    if not is_subscribed(user_id): return
    if not check_rate_limit(user_id): return
    
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    text = (
        "🚀 <b>Your Unique Referral Link:</b>\n\n"
        f"<code>{ref_link}</code>\n\n"
        "<i>Share this link with your friends to earn rewards!</i>"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Share Link ↗️", url=f"https://t.me/share/url?url={ref_link}&text=Join%20and%20earn%20rewards!"))
    
    bot.send_message(user_id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📊 My Stats")
def my_stats(message):
    user_id = message.chat.id
    if not is_subscribed(user_id): return
    if not check_rate_limit(user_id): return
    
    user = get_user(user_id)
    if not user: return
    
    share_count = get_share_count(user_id)
    progress = min(share_count, INVITES_NEEDED_FOR_REWARD)
    
    text = (
        "📊 <b>Your Statistics</b>\n\n"
        f"👤 ID: <code>{user_id}</code>\n"
        f"💰 Balance: <b>{user['balance']} Coins</b>\n"
        f"📤 Bot Shares: <b>{share_count}</b>\n"
        f"👥 Total Referrals: <b>{get_referral_count(user_id)}</b>\n"
        f"🎯 VIP Unlock Progress: <b>{progress}/{INVITES_NEEDED_FOR_REWARD} shares</b>"
    )
    
    if progress >= INVITES_NEEDED_FOR_REWARD:
        text += "\n\n🎉 <i>You have unlocked the VIP Raja Club Prediction feature! Use the menu to get your predictions.</i>"
        
    bot.send_message(user_id, text)

@bot.message_handler(func=lambda message: message.text == "🎁 Daily Bonus")
def daily_bonus(message):
    user_id = message.chat.id
    if not is_subscribed(user_id): return
    if not check_rate_limit(user_id): return
    
    if claim_daily_bonus(user_id):
        bot.send_message(user_id, f"🎁 <b>Success!</b>\nYou claimed your daily bonus of {DAILY_BONUS_COINS} coins!")
    else:
        bot.send_message(user_id, "❌ <b>Already Claimed!</b>\nYou have already claimed your daily bonus today. Come back tomorrow.")

@bot.message_handler(func=lambda message: message.text == "🏆 Leaderboard")
def leaderboard(message):
    user_id = message.chat.id
    if not is_subscribed(user_id): return
    if not check_rate_limit(user_id): return
    
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.first_name, u.user_id, COUNT(r.user_id) as refs
            FROM users u
            LEFT JOIN users r ON u.user_id = r.referred_by
            GROUP BY u.user_id
            ORDER BY refs DESC
            LIMIT 10
        ''')
        top_users = cursor.fetchall()
        conn.close()
        
    text = "🏆 <b>Top 10 Referrers</b> 🏆\n\n"
    for i, user in enumerate(top_users, 1):
        name = user['first_name'] if user['first_name'] else "User"
        text += f"{i}. {name} - <b>{user['refs']}</b> invites\n"
        
    bot.send_message(user_id, text)

@bot.message_handler(func=lambda message: message.text == "🎮 Play & Earn")
def play_and_earn(message):
    user_id = message.chat.id
    if not is_subscribed(user_id): return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎮 Play Now", url=GAME_LINK))
    
    text = (
        "🚀 <b>Ready to multiply your earnings?</b>\n\n"
        "Play games and earn real rewards. Click the button below to register and start playing immediately!\n\n"
        "<i>Note: Make sure to register using the link to track your rewards.</i>"
    )
    bot.send_message(user_id, text, reply_markup=markup)

# ==========================================
# PREDICTION DB HELPERS
# ==========================================
def save_prediction_result(user_id, mode, pred_color, actual_color, pred_size, actual_size):
    """Save actual result and return (color_correct, size_correct)."""
    color_correct = 1 if pred_color == actual_color else 0
    size_correct  = 1 if pred_size  == actual_size  else 0
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO prediction_results
            (user_id, mode, predicted_color, actual_color, color_correct, predicted_size, actual_size, size_correct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, mode, pred_color, actual_color, color_correct, pred_size, actual_size, size_correct))
        conn.commit()
        conn.close()
    return color_correct, size_correct

def get_accuracy_stats(mode, limit=20):
    """Get recent prediction accuracy to adapt engine weights."""
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT color_correct, size_correct FROM prediction_results
            WHERE mode = ? ORDER BY timestamp DESC LIMIT ?
        ''', (mode, limit))
        rows = cursor.fetchall()
        conn.close()
    if not rows:
        return {'color_acc': 0.5, 'size_acc': 0.5, 'total': 0}
    total = len(rows)
    return {
        'color_acc': sum(r['color_correct'] for r in rows) / total,
        'size_acc':  sum(r['size_correct']  for r in rows) / total,
        'total': total
    }

# In-memory store: pending feedback per user
pending_feedback = {}

# ==========================================
# RAJA CLUB VIP PREDICTION SYSTEM (v2 - Advanced Engine)
# ==========================================
import requests
from collections import Counter

API_BASE = 'https://indialotteryapi.com/wp-json/wingo/v1'

def fetch_history(market, count=30):
    """Fetch last 'count' results for deep statistical analysis."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(
            f"{API_BASE}/predict?market={market}&n={count}",
            headers=headers, timeout=12
        )
        res.raise_for_status()
        return res.json().get('items', [])
    except Exception as e:
        print("Error fetching history:", e)
        return []

def deep_analyze(history):
    """
    Multi-layer statistical analysis engine.
    Analyzes: frequency, streaks, reversals, hot/cold numbers, weighted trend.
    Returns a dict of signals to be voted upon.
    """
    if not history:
        return {}

    colors   = [h.get('color', '') for h in history]
    sizes    = [h.get('bigSmall', '') for h in history]
    parities = [h.get('oddEven', '') for h in history]
    digits   = [int(h.get('digit', 0)) for h in history if str(h.get('digit', '')).isdigit()]

    # ── 1. FREQUENCY ANALYSIS (last 30 rounds) ──────────────────────────────
    color_freq   = Counter(colors)
    size_freq    = Counter(sizes)
    parity_freq  = Counter(parities)
    digit_freq   = Counter(digits)

    # ── 2. RECENT WEIGHTED TREND (last 10 rounds - 2x weight) ───────────────
    recent = history[-10:]
    r_colors  = [h.get('color', '') for h in recent]
    r_sizes   = [h.get('bigSmall', '') for h in recent]
    r_parities= [h.get('oddEven', '') for h in recent]

    # Weighted counter: recent counts double
    def weighted_top(global_ctr, recent_list):
        combined = dict(global_ctr)
        for item in recent_list:
            combined[item] = combined.get(item, 0) + 1  # +1 extra weight
        return max(combined, key=combined.get) if combined else None

    hot_color   = weighted_top(color_freq, r_colors)
    hot_size    = weighted_top(size_freq, r_sizes)
    hot_parity  = weighted_top(parity_freq, r_parities)

    # ── 3. STREAK ANALYSIS (current live streak from latest result) ──────────
    def get_streak(lst):
        if not lst: return 0, None
        val, count = lst[-1], 1
        for i in range(len(lst)-2, -1, -1):
            if lst[i] == val: count += 1
            else: break
        return count, val

    color_streak,  streak_color  = get_streak(colors)
    size_streak,   streak_size   = get_streak(sizes)
    parity_streak, streak_parity = get_streak(parities)

    # ── 4. REVERSAL LOGIC ────────────────────────────────────────────────────
    # If streak >= 4, statistically mean-reversion is likely → flip prediction
    REVERSAL_THRESHOLD = 4

    color_reversed = False
    if color_streak >= REVERSAL_THRESHOLD:
        color_reversed = True
        # Pick the color that appeared least recently among Red/Green
        candidates = {'Red': colors.count('Red'), 'Green': colors.count('Green')}
        hot_color = min(candidates, key=candidates.get)

    size_reversed = False
    if size_streak >= REVERSAL_THRESHOLD:
        size_reversed = True
        hot_size = 'Small' if streak_size == 'Big' else 'Big'

    parity_reversed = False
    if parity_streak >= REVERSAL_THRESHOLD:
        parity_reversed = True
        hot_parity = 'Even' if streak_parity == 'Odd' else 'Odd'

    # ── 5. HOT / COLD DIGIT ──────────────────────────────────────────────────
    if digit_freq:
        hot_digit  = digit_freq.most_common(1)[0][0]   # appeared most
        cold_digit = digit_freq.most_common()[-1][0]   # appeared least
    else:
        hot_digit, cold_digit = 5, 0

    # Best digit prediction: pick cold digit (due-to-appear logic)
    best_digit = cold_digit

    # ── 6. CONFIDENCE SCORING ────────────────────────────────────────────────
    # Base confidence
    confidence = 72

    # Boost if reversal signal is strong
    if color_reversed:  confidence += 8
    if size_reversed:   confidence += 5
    if parity_reversed: confidence += 5

    # Boost if majority of last 10 agrees with hot prediction
    if r_colors.count(hot_color) >= 7:  confidence += 5   # strong dominance
    elif r_colors.count(hot_color) <= 3: confidence -= 3  # weak signal

    # Boost if streak is moderate (2-3) → likely to continue
    if 2 <= color_streak <= 3 and not color_reversed:
        confidence += 4

    confidence = max(65, min(95, confidence))  # clamp 65–95

    return {
        'predicted_color':  hot_color,
        'predicted_size':   hot_size,
        'predicted_parity': hot_parity,
        'predicted_digit':  best_digit,
        'color_streak':     color_streak,
        'streak_color':     streak_color,
        'size_streak':      size_streak,
        'streak_size':      streak_size,
        'parity_streak':    parity_streak,
        'streak_parity':    streak_parity,
        'color_reversed':   color_reversed,
        'size_reversed':    size_reversed,
        'hot_digit':        hot_digit,
        'cold_digit':       cold_digit,
        'color_freq':       color_freq,
        'confidence':       confidence,
    }

def send_prediction_output(user_id, game_mode):
    bot.send_message(user_id, "⏳ <b>Deep analyzing live data (30 rounds)...</b>\n<i>Please wait a few seconds.</i>")

    modes_map  = {'Win Go 1 Min': 1, 'Win Go 3 Min': 3, 'Win Go 5 Min': 5, 'Win Go 10 Min': 10}
    modes_short= {1: 'wg1', 3: 'wg3', 5: 'wg5', 10: 'wg10'}
    market = modes_map.get(game_mode, 1)
    mode_key = modes_short.get(market, 'wg1')

    history = fetch_history(market, 30)
    if not history:
        bot.send_message(user_id, "❌ <b>Error:</b> Could not fetch live data. Please try again later.")
        return

    analysis = deep_analyze(history)
    if not analysis:
        bot.send_message(user_id, "❌ <b>Error:</b> Analysis failed.")
        return

    # ── Adaptive confidence from past feedback data ──────────────────────────
    stats = get_accuracy_stats(mode_key)
    if stats['total'] >= 5:
        avg_acc = (stats['color_acc'] + stats['size_acc']) / 2
        if avg_acc > 0.65:
            analysis['confidence'] = min(95, analysis['confidence'] + 5)
        elif avg_acc < 0.40:
            analysis['confidence'] = max(65, analysis['confidence'] - 4)

    # ── Store prediction for feedback later ──────────────────────────────────
    pending_feedback[user_id] = {
        'mode_key':        mode_key,
        'game_mode':       game_mode,
        'predicted_color': analysis['predicted_color'],
        'predicted_size':  analysis['predicted_size'],
    }

    # Next period estimate
    last_period = history[-1].get('period', '???')
    try:
        next_period = str(int(last_period) + 1)
    except:
        next_period = last_period

    # Color display
    c = analysis['predicted_color']
    color_emoji = "🔴" if c == 'Red' else "🟢" if c == 'Green' else "🟣"
    color_val   = f"{c} {color_emoji}"

    # Size display
    s = analysis['predicted_size']
    size_emoji = "🔺" if s == 'Big' else "🔻"
    size_val = f"{s} {size_emoji}"

    # Reversal tag
    rev_tag = " ↩️ <i>(Reversal Signal!)</i>" if analysis['color_reversed'] else ""

    # Recent 8 results visual strip
    history_strip = ""
    for h in history[-8:]:
        hc = h.get('color', '')
        history_strip += "🔴" if hc=='Red' else "🟢" if hc=='Green' else "🟣"

    # Color distribution in last 30
    cf = analysis['color_freq']
    total = sum(cf.values()) or 1
    red_pct   = round(cf.get('Red',0)   / total * 100)
    green_pct = round(cf.get('Green',0) / total * 100)
    vio_pct   = round(cf.get('Violet',0)/ total * 100)

    # Streak info
    cs = analysis['color_streak']
    sc = analysis['streak_color']
    streak_bar = "🟥" * cs if sc=='Red' else "🟩" * cs if sc=='Green' else "🟪" * cs

    conf = analysis['confidence']
    confidence_bar = "█" * (conf // 10) + "░" * (10 - conf // 10)

    # Inline buttons
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔄 Refresh Next Period", callback_data=f"next_{mode_key}"),
        InlineKeyboardButton("🎮 Change Mode", callback_data="change_mode")
    )

    # Accuracy footer (if we have feedback data)
    acc_footer = ""
    stats = get_accuracy_stats(mode_key)
    if stats['total'] > 0:
        cacc = round(stats['color_acc'] * 100)
        sacc = round(stats['size_acc']  * 100)
        acc_footer = (
            f"\n📈 <b>AI Self-Learning Stats ({stats['total']} rounds):</b>\n"
            f"  🎨 Color Accuracy: <b>{cacc}%</b>  |  📏 Size Accuracy: <b>{sacc}%</b>"
        )

    text = (
        "⚡️ <b>RAJA CLUB — VIP AI PREDICTION ENGINE v2</b> ⚡️\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Mode:</b> {game_mode}   |   🆔 <b>Next Period:</b> <code>{next_period}</code>\n\n"

        f"📊 <b>Last 8 Results (oldest→latest):</b>\n"
        f"{history_strip}\n\n"

        f"📈 <b>Color Distribution (30 rounds):</b>\n"
        f"  🔴 Red: {red_pct}%  |  🟢 Green: {green_pct}%  |  🟣 Violet: {vio_pct}%\n\n"

        f"🔥 <b>Current Streak:</b> {streak_bar} ({cs}x {sc})\n"
        f"🔄 <b>Reversal Active:</b> {'✅ YES' if analysis['color_reversed'] else '❌ NO'}\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>VIP PREDICTION FOR NEXT ROUND:</b>\n"
        f"🎨 <b>Color :</b> {color_val}{rev_tag}\n"
        f"📏 <b>Size  :</b> {size_val}\n"
        f"🔢 <b>Digit :</b> {analysis['predicted_digit']} (Cold/Due)\n"
        f"♻️ <b>Parity:</b> {analysis['predicted_parity']}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 <b>AI Confidence:</b> {conf}%\n"
        f"<code>[{confidence_bar}]</code>"
        f"{acc_footer}\n\n"

        "📊 <b>Martingale Guide:</b>\n"
        "• <b>Bet 1:</b> ₹10  → <b>Bet 2:</b> ₹30  → <b>Bet 3:</b> ₹90\n"
        "• <b>Bet 4:</b> ₹270 → <b>Bet 5:</b> ₹810 ✅ (Profit!)\n\n"
        "⚠️ <i>AI prediction only. Play responsibly!</i>"
    )

    bot.send_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def select_game_mode(call):
    mode_key = call.data.split("_")[1]
    modes = {
        'wg1': 'Win Go 1 Min',
        'wg3': 'Win Go 3 Min',
        'wg5': 'Win Go 5 Min',
        'wg10': 'Win Go 10 Min'
    }
    game_mode = modes.get(mode_key, 'Win Go 1 Min')
    
    # Acknowledge the callback immediately
    bot.answer_callback_query(call.id)
    send_prediction_output(call.message.chat.id, game_mode)

@bot.callback_query_handler(func=lambda call: call.data.startswith("next_") or call.data == "change_mode")
def handle_prediction_callbacks(call):
    user_id = call.message.chat.id
    if call.data == "change_mode":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🎮 Win Go 1 Min", callback_data="mode_wg1"),
            InlineKeyboardButton("🎮 Win Go 3 Min", callback_data="mode_wg3")
        )
        markup.add(
            InlineKeyboardButton("🎮 Win Go 5 Min", callback_data="mode_wg5"),
            InlineKeyboardButton("🎮 Win Go 10 Min", callback_data="mode_wg10")
        )
        bot.send_message(user_id, "🎮 <b>Select Game Mode for Prediction:</b>", reply_markup=markup)
        bot.answer_callback_query(call.id)
        return

    parts = call.data.split("_")
    mode_key = parts[1]
    modes = {'wg1': 'Win Go 1 Min', 'wg3': 'Win Go 3 Min', 'wg5': 'Win Go 5 Min', 'wg10': 'Win Go 10 Min'}
    game_mode = modes.get(mode_key, 'Win Go 1 Min')

    # ── If there is a pending prediction, ask for feedback first ────────────
    if user_id in pending_feedback:
        pf = pending_feedback[user_id]
        pc = pf['predicted_color']
        ps = pf['predicted_size']
        c_emoji = {"Red": "🔴", "Green": "🟢", "Violet": "🟣"}.get(pc, "")

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🔴 Red",    callback_data=f"fb_c_R_{mode_key}"),
            InlineKeyboardButton("🟢 Green",  callback_data=f"fb_c_G_{mode_key}"),
            InlineKeyboardButton("🟣 Violet", callback_data=f"fb_c_V_{mode_key}")
        )
        markup.add(InlineKeyboardButton("⏭ Skip & Get Next", callback_data=f"fb_skip_{mode_key}"))

        bot.answer_callback_query(call.id)
        bot.send_message(
            user_id,
            f"📋 <b>Quick Feedback — Previous Round</b>\n\n"
            f"🤖 AI predicted: <b>{pc} {c_emoji}</b>  |  <b>{ps}</b>\n\n"
            f"🎯 <b>What color ACTUALLY came?</b>\n"
            f"<i>(Your feedback trains the AI!)</i>",
        reply_markup=markup
        )
        return

    bot.answer_callback_query(call.id)
    send_prediction_output(user_id, game_mode)

# ── Feedback: Color selection ────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("fb_c_"))
def feedback_color(call):
    user_id = call.message.chat.id
    parts = call.data.split("_")   # fb_c_R_wg1
    color_code = parts[2]
    mode_key   = parts[3]
    color_map  = {"R": "Red", "G": "Green", "V": "Violet"}
    actual_color = color_map.get(color_code, "Red")

    if user_id in pending_feedback:
        pending_feedback[user_id]['actual_color'] = actual_color

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("📈 Big",   callback_data=f"fb_s_B_{mode_key}"),
        InlineKeyboardButton("📉 Small", callback_data=f"fb_s_S_{mode_key}")
    )
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        f"✅ Color noted: <b>{actual_color}</b>\n\n"
        f"📏 <b>What SIZE (Big/Small) actually came?</b>",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup
    )

# ── Feedback: Size selection ─────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("fb_s_"))
def feedback_size(call):
    user_id  = call.message.chat.id
    parts    = call.data.split("_")   # fb_s_B_wg1
    size_code= parts[2]
    mode_key = parts[3]
    size_map = {"B": "Big", "S": "Small"}
    actual_size = size_map.get(size_code, "Big")
    modes = {'wg1': 'Win Go 1 Min', 'wg3': 'Win Go 3 Min', 'wg5': 'Win Go 5 Min', 'wg10': 'Win Go 10 Min'}
    game_mode = modes.get(mode_key, 'Win Go 1 Min')

    if user_id in pending_feedback:
        pf = pending_feedback.pop(user_id)
        actual_color   = pf.get('actual_color', '')
        pred_color     = pf.get('predicted_color', '')
        pred_size      = pf.get('predicted_size', '')

        color_correct, size_correct = save_prediction_result(
            user_id, mode_key, pred_color, actual_color, pred_size, actual_size
        )

        c_emoji = {"Red": "🔴", "Green": "🟢", "Violet": "🟣"}
        c_win   = "✅ WIN" if color_correct else "❌ MISS"
        s_win   = "✅ WIN" if size_correct  else "❌ MISS"

        if color_correct and size_correct:
            verdict = "🎉 <b>Perfect call! AI confidence boosted.</b>"
        elif color_correct or size_correct:
            verdict = "👍 <b>Partial hit! AI recalibrating weights...</b>"
        else:
            verdict = "🔄 <b>Both missed. AI learning from mistake...</b>"

        result_text = (
            f"📊 <b>Round Result Recorded</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎨 Color → Predicted: <b>{pred_color}</b>  |  Actual: <b>{actual_color}</b>  {c_win}\n"
            f"📏 Size  → Predicted: <b>{pred_size}</b>   |  Actual: <b>{actual_size}</b>  {s_win}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{verdict}\n\n"
            f"<i>⏳ Fetching next prediction now...</i>"
        )
        bot.answer_callback_query(call.id)
        bot.edit_message_text(result_text, call.message.chat.id, call.message.message_id)
        # Slight delay then show next prediction
        threading.Timer(1.2, send_prediction_output, args=[user_id, game_mode]).start()
    else:
        bot.answer_callback_query(call.id)
        send_prediction_output(user_id, game_mode)

# ── Feedback: Skip ───────────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("fb_skip_"))
def feedback_skip(call):
    user_id  = call.message.chat.id
    mode_key = call.data.split("_")[2]
    modes    = {'wg1': 'Win Go 1 Min', 'wg3': 'Win Go 3 Min', 'wg5': 'Win Go 5 Min', 'wg10': 'Win Go 10 Min'}
    game_mode= modes.get(mode_key, 'Win Go 1 Min')
    pending_feedback.pop(user_id, None)
    bot.answer_callback_query(call.id)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    send_prediction_output(user_id, game_mode)

@bot.callback_query_handler(func=lambda call: call.data == "action_share")
def handle_share_click(call):
    user_id = call.message.chat.id
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    share_url = f"https://t.me/share/url?url={ref_link}&text=Join%20this%20awesome%20Raja%20Club%20Prediction%20Bot%20and%20start%20winning!"
    
    increment_share_count(user_id)
    share_count = get_share_count(user_id)
    
    try:
        bot.answer_callback_query(call.id, url=share_url)
    except Exception as e:
        print(f"Error opening share url: {e}")
        bot.answer_callback_query(call.id, "Redirecting to Share...")
        
    if share_count >= INVITES_NEEDED_FOR_REWARD:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🎮 Win Go 1 Min", callback_data="mode_wg1"),
            InlineKeyboardButton("🎮 Win Go 3 Min", callback_data="mode_wg3")
        )
        markup.add(
            InlineKeyboardButton("🎮 Win Go 5 Min", callback_data="mode_wg5"),
            InlineKeyboardButton("🎮 Win Go 10 Min", callback_data="mode_wg10")
        )
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text="🎉 <b>VIP Predictions Unlocked!</b>\n\nSelect your game mode below to start playing:",
            reply_markup=markup
        )
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"📤 Share Link ({share_count}/{INVITES_NEEDED_FOR_REWARD})", callback_data="action_share"))
        
        bot.edit_message_text(
            chat_id=user_id,
            message_id=call.message.message_id,
            text=(
                "🔒 <b>VIP Prediction is Locked!</b>\n\n"
                f"To unlock the VIP Raja Club Predictions, you must share the bot link {INVITES_NEEDED_FOR_REWARD} times using the button below.\n\n"
                f"📈 <b>Your progress:</b> {share_count}/{INVITES_NEEDED_FOR_REWARD} shares"
            ),
            reply_markup=markup
        )

@bot.message_handler(func=lambda message: message.text == "🔮 Raja Club Prediction")
def get_prediction(message):
    user_id = message.chat.id
    if not is_subscribed(user_id): return
    if not check_rate_limit(user_id): return
    
    # We bypassed the share check here to allow testing:
    # share_count = get_share_count(user_id)
    # if share_count < INVITES_NEEDED_FOR_REWARD:
    #     bot_info = bot.get_me()
    #     ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    #     
    #     markup = InlineKeyboardMarkup()
    #     markup.add(InlineKeyboardButton(f"📤 Share Link ({share_count}/{INVITES_NEEDED_FOR_REWARD})", callback_data="action_share"))
    #     
    #     text = (
    #         "🔒 <b>VIP Prediction is Locked!</b>\n\n"
    #         f"To unlock the VIP Raja Club Predictions, you must share the bot link {INVITES_NEEDED_FOR_REWARD} times using the button below.\n\n"
    #         f"📈 <b>Your progress:</b> {share_count}/{INVITES_NEEDED_FOR_REWARD} shares"
    #     )
    #     bot.send_message(user_id, text, reply_markup=markup)
    #     return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎮 Win Go 1 Min", callback_data="mode_wg1"),
        InlineKeyboardButton("🎮 Win Go 3 Min", callback_data="mode_wg3")
    )
    markup.add(
        InlineKeyboardButton("🎮 Win Go 5 Min", callback_data="mode_wg5"),
        InlineKeyboardButton("🎮 Win Go 10 Min", callback_data="mode_wg10")
    )
    bot.send_message(user_id, "🎮 <b>Select Game Mode for Prediction:</b>", reply_markup=markup)

# ==========================================
# ADMIN COMMANDS
# ==========================================
def is_admin(message):
    if message.chat.id in ADMIN_IDS: return True
    if message.from_user.username and f"@{message.from_user.username}" in ADMIN_IDS: return True
    return False

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if not is_admin(message): return
    
    text = (
        "🛠 <b>Admin Panel</b>\n\n"
        "/stats - View total users and stats\n"
        "/broadcast [message] - Send message to all users\n"
        "/export - Export users to CSV\n"
        "/ban [user_id] - Ban a user\n"
        "/unban [user_id] - Unban a user"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if not is_admin(message): return
    
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE join_date >= date('now')")
        today_users = cursor.fetchone()[0]
        conn.close()
        
    bot.send_message(message.chat.id, f"📊 <b>Bot Statistics</b>\n\nTotal Users: <b>{total_users}</b>\nNew Today: <b>{today_users}</b>")

@bot.message_handler(commands=['broadcast'])
def admin_broadcast(message):
    if not is_admin(message): return
    
    text_to_send = message.text.replace("/broadcast ", "", 1)
    if not text_to_send or text_to_send == "/broadcast":
        bot.send_message(message.chat.id, "⚠️ Usage: /broadcast [your message here]")
        return
        
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
        users = cursor.fetchall()
        conn.close()
        
    success = 0
    bot.send_message(message.chat.id, f"⏳ Broadcasting to {len(users)} users...")
    
    for user in users:
        try:
            bot.send_message(user['user_id'], text_to_send)
            success += 1
            time.sleep(0.05) # Prevent hitting Telegram API limits (30 msgs/sec max)
        except:
            pass # User might have blocked the bot
            
    bot.send_message(message.chat.id, f"✅ Broadcast completed! Sent to {success} users.")

@bot.message_handler(commands=['export'])
def admin_export(message):
    if not is_admin(message): return
    
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        conn.close()
        
    filename = "users_export.csv"
    with open(filename, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(["user_id", "username", "first_name", "referred_by", "balance", "join_date", "is_banned"])
        for user in users:
            writer.writerow([user['user_id'], user['username'], user['first_name'], user['referred_by'], user['balance'], user['join_date'], user['is_banned']])
            
    for attempt in range(3):
        try:
            with open(filename, 'rb') as file:
                bot.send_document(message.chat.id, file)
            break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    else:
        bot.send_message(message.chat.id, "Failed to send the export file after multiple retries.")
        
    os.remove(filename)

# ==========================================
# SCHEDULED AUTOMATION
# ==========================================
# Example: Sending a daily reminder or auto-message
def auto_message_job():
    print("Running scheduled auto-message...")
    # Add logic here to broadcast automated messages or engagement nudges
    # Example: Send a reminder to users who haven't claimed daily bonus
    pass

def scheduler_thread():
    import schedule
    schedule.every(60).minutes.do(auto_message_job) # Configure as needed
    while True:
        schedule.run_pending()
        time.sleep(1)

# Start scheduler thread
threading.Thread(target=scheduler_thread, daemon=True).start()

# ==========================================
# RUN BOT
# ==========================================
from keep_alive import keep_alive

if __name__ == "__main__":
    keep_alive()
    print("Advanced Telegram Referral Bot is running...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Error occurred: {e}")
            time.sleep(15)
