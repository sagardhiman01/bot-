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
# RAJA CLUB VIP PREDICTION SYSTEM
# ==========================================
import requests

API_BASE = 'https://indialotteryapi.com/wp-json/wingo/v1'

def fetch_predictions(market, count=10):
    try:
        # UserAgent might help with connection dropped
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(f"{API_BASE}/predict?market={market}&n={count}", headers=headers, timeout=10)
        return res.json().get('items', [])
    except Exception as e:
        print("Error fetching predictions:", e)
        return []

def analyze_patterns(predictions):
    patterns = {
        'colorStreak': 0,
        'lastColor': None,
        'bigSmallStreak': 0,
        'lastSize': None,
        'oddEvenStreak': 0,
        'lastOddEven': None
    }
    
    last5 = predictions[-5:] if len(predictions) >= 5 else predictions
    for p in last5:
        if p.get('color') == patterns['lastColor']: patterns['colorStreak'] += 1
        else: patterns['colorStreak'] = 1; patterns['lastColor'] = p.get('color')
        
        if p.get('bigSmall') == patterns['lastSize']: patterns['bigSmallStreak'] += 1
        else: patterns['bigSmallStreak'] = 1; patterns['lastSize'] = p.get('bigSmall')
        
        if p.get('oddEven') == patterns['lastOddEven']: patterns['oddEvenStreak'] += 1
        else: patterns['oddEvenStreak'] = 1; patterns['lastOddEven'] = p.get('oddEven')
        
    return patterns

def smart_predict(predictions, patterns):
    if not predictions:
        return None
    api_result = predictions[-1]
    confidence_boost = 0
    if patterns['colorStreak'] >= 3:
        confidence_boost += 5
    
    conf = api_result.get('conf', 80)
    api_result['confidence'] = min(98, conf + confidence_boost)
    return api_result

def send_prediction_output(user_id, game_mode):
    bot.send_message(user_id, "⏳ <b>Analyzing live game data...</b>\n<i>Please wait a few seconds.</i>")
    
    modes_map = {
        'Win Go 1 Min': 1,
        'Win Go 3 Min': 3,
        'Win Go 5 Min': 5,
        'Win Go 10 Min': 10
    }
    market = modes_map.get(game_mode, 1)
    
    predictions = fetch_predictions(market, 10)
    if not predictions:
        bot.send_message(user_id, "❌ <b>Error:</b> Could not fetch live data. Please try again later.")
        return
        
    patterns = analyze_patterns(predictions)
    prediction = smart_predict(predictions, patterns)
    
    if not prediction:
        bot.send_message(user_id, "❌ <b>Error:</b> Analysis failed.")
        return
        
    color_val = "Red 🔴" if prediction.get('color') == "Red" else "Green 🟢" if prediction.get('color') == "Green" else "Violet 🟣"
    size_val = prediction.get('bigSmall', 'Unknown')
    digit = prediction.get('digit', '?')
    conf = prediction.get('confidence', 85)
    period = prediction.get('period', 'Unknown')
    
    # Show user's predicted history
    history_lines = []
    for p in predictions[-5:]:
        p_c = p.get('color')
        c_emoji = "🔴" if p_c == "Red" else "🟢" if p_c == "Green" else "🟣"
        history_lines.append(f"• Period {p.get('period')[-4:]}: {p_c} {c_emoji}")
    history_text = "\n".join(history_lines)
    
    # Inline buttons
    modes_short = {1: 'wg1', 3: 'wg3', 5: 'wg5', 10: 'wg10'}
    mode_short = modes_short.get(market, 'wg1')
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔄 Refresh Next Period", callback_data=f"next_{mode_short}"),
        InlineKeyboardButton("🎮 Change Mode", callback_data="change_mode")
    )
    
    # Construct message text
    text = (
        "⚡️ <b>RAJA CLUB VIP PREDICTION ENGINE</b> ⚡️\n\n"
        f"📝 <b>Game Mode:</b> {game_mode}\n"
        f"🆔 <b>Target Period:</b> {period}\n\n"
        f"📈 <b>Recent Live Trend:</b>\n{history_text}\n\n"
        f"🔍 <b>Pattern Analysis:</b>\n"
        f"  Color Streak: {patterns['colorStreak']}x {patterns['lastColor']}\n"
        f"  Size Streak: {patterns['bigSmallStreak']}x {patterns['lastSize']}\n"
        f"  O/E Streak: {patterns['oddEvenStreak']}x {patterns['lastOddEven']}\n\n"
        f"🎯 <b>VIP Recommendation for Next Round:</b>\n"
        f"🎨 <b>Color:</b> {color_val}\n"
        f"📏 <b>Size:</b> {size_val}\n"
        f"🔢 <b>Recommended Digit:</b> {digit}\n"
        f"🚀 <b>Confidence Score:</b> {conf}%\n\n"
        "📊 <b>3x Investment Plan Guide:</b>\n"
        "• <b>Bet 1:</b> ₹10 (If Lose ➡️ Bet 2)\n"
        "• <b>Bet 2:</b> ₹30 (If Lose ➡️ Bet 3)\n"
        "• <b>Bet 3:</b> ₹90 (If Lose ➡️ Bet 4)\n"
        "• <b>Bet 4:</b> ₹270 (If Lose ➡️ Bet 5)\n"
        "• <b>Bet 5:</b> ₹810 (Win covers all losses + profit!)\n\n"
        "⚠️ <i>Play responsibly. Never greed!</i>"
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
    
    modes = {
        'wg1': 'Win Go 1 Min',
        'wg3': 'Win Go 3 Min',
        'wg5': 'Win Go 5 Min',
        'wg10': 'Win Go 10 Min'
    }
    game_mode = modes.get(mode_key, 'Win Go 1 Min')
    
    bot.answer_callback_query(call.id)
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
