import os
import time
import sqlite3
import logging
from datetime import datetime, timedelta
import telebot
from yt_dlp import YoutubeDL
from telebot import types
from flask import Flask
from threading import Thread

# ================= CONFIGURATION =================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8551871189:AAH6Dbp-PBtQtiScv58WraS3CCL_uCad7zM")
bot = telebot.TeleBot(TOKEN)
ADMIN_ID = 5573149859  # ⚠️ CHANGE TO YOUR TELEGRAM ID

# ⚠️ CHANGE THESE TO YOUR ACTUAL CHANNEL
YOUR_CHANNEL = "@wbrand_shop"  # Your channel username
CHANNEL_LINK = "https://t.me/wbrand_shop"  # Your channel link
TELEBIRR_NUMBER = "0940213338"  # Your Telebirr number

DOWNLOAD_FOLDER = "downloads"
FREE_DAILY_LIMIT = 2
FREE_WEEKLY_LIMIT = 7
PREMIUM_PRICE = 30

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT,
                  joined INTEGER DEFAULT 0,
                  daily_count INTEGER DEFAULT 0,
                  weekly_count INTEGER DEFAULT 0,
                  last_reset_date TEXT,
                  premium INTEGER DEFAULT 0,
                  premium_expiry TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(user_id, username):
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def update_user(user_id, **kwargs):
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    c = conn.cursor()
    for key, value in kwargs.items():
        c.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

# ================= FORCE JOIN CHECK =================
def check_membership(user_id):
    """Check if user has joined the channel"""
    try:
        channel_clean = YOUR_CHANNEL.replace("@", "")
        member = bot.get_chat_member(f"@{channel_clean}", user_id)
        is_member = member.status in ["member", "administrator", "creator"]
        return is_member
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return False

# ================= START COMMAND =================
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"User_{user_id}"
    
    create_user(user_id, username)
    
    # CHECK IF USER JOINED CHANNEL
    if not check_membership(user_id):
        # User NOT joined - SHOW JOIN MESSAGE
        join_text = f"""🚫 ACCESS REQUIRED

Hello {username}!

You must join our channel to use this MP3 downloader bot.

Channel: {YOUR_CHANNEL}

Instructions:
1. Click JOIN CHANNEL button below
2. Join the channel
3. Come back and click ✅ I JOINED
4. Start downloading MP3s!"""
        
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("🔔 JOIN CHANNEL", url=CHANNEL_LINK),
            types.InlineKeyboardButton("✅ I JOINED", callback_data="check_join")
        )
        
        bot.send_message(message.chat.id, join_text, reply_markup=keyboard)
        return
    
    # User HAS joined
    update_user(user_id, joined=1)
    show_mode_menu(message)

def show_mode_menu(message):
    user_id = message.from_user.id
    username = message.from_user.username or f"User_{user_id}"
    
    user = get_user(user_id)
    
    if user and user[6] == 1:  # Premium user
        expiry = user[7] or "Not set"
        text = f"""💎 PREMIUM USER

Welcome {username}!

Your premium is active until: {expiry}

Enjoy unlimited MP3 downloads!

Send me any YouTube link! 🎵"""
        bot.send_message(message.chat.id, text)
    else:
        # Show Free/Premium choice
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("🆓 FREE MODE", callback_data="free_mode"),
            types.InlineKeyboardButton("💎 PREMIUM", callback_data="premium_mode")
        )
        
        text = f"""🎵 YOUTUBE MP3 DOWNLOADER

Hello {username}!

Choose your access mode:

🆓 FREE MODE
• {FREE_DAILY_LIMIT} downloads per day
• {FREE_WEEKLY_LIMIT} downloads per week
• Max 15 minute audio
• 192kbps MP3 quality

💎 PREMIUM MODE ({PREMIUM_PRICE} Birr/month)
• Unlimited downloads
• No time limits
• Best audio quality
• Priority processing"""
        
        bot.send_message(message.chat.id, text, reply_markup=keyboard)

# ================= JOIN VERIFICATION =================
@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def verify_join(call):
    user_id = call.from_user.id
    
    if check_membership(user_id):
        update_user(user_id, joined=1)
        bot.edit_message_text(
            "✅ VERIFIED! You have joined the channel.",
            call.message.chat.id,
            call.message.message_id
        )
        show_mode_menu(call.message)
    else:
        bot.answer_callback_query(
            call.id,
            "❌ You haven't joined the channel yet! Please join first.",
            show_alert=True
        )

# ================= MODE SELECTION =================
@bot.callback_query_handler(func=lambda call: call.data in ["free_mode", "premium_mode"])
def handle_mode(call):
    user_id = call.from_user.id
    
    if not check_membership(user_id):
        bot.answer_callback_query(call.id, "Join channel first!")
        return
    
    if call.data == "free_mode":
        user = get_user(user_id)
        
        # Check limits
        today = datetime.now().date().isoformat()
        if user[5] != today:
            update_user(user_id, daily_count=0, last_reset_date=today)
            user = get_user(user_id)
        
        if user[3] >= FREE_DAILY_LIMIT:
            bot.edit_message_text(
                f"❌ DAILY LIMIT REACHED\n\nYou've used {FREE_DAILY_LIMIT}/{FREE_DAILY_LIMIT} downloads today.\nTry again tomorrow or upgrade.",
                call.message.chat.id,
                call.message.message_id
            )
            return
        
        if user[4] >= FREE_WEEKLY_LIMIT:
            bot.edit_message_text(
                f"❌ WEEKLY LIMIT REACHED\n\nYou've used {FREE_WEEKLY_LIMIT}/{FREE_WEEKLY_LIMIT} downloads this week.\nTry again next week or upgrade.",
                call.message.chat.id,
                call.message.message_id
            )
            return
        
        remaining_daily = FREE_DAILY_LIMIT - user[3]
        remaining_weekly = FREE_WEEKLY_LIMIT - user[4]
        
        text = f"""🆓 FREE MODE ACTIVATED

You can download:
• Today: {remaining_daily}/{FREE_DAILY_LIMIT} remaining
• This week: {remaining_weekly}/{FREE_WEEKLY_LIMIT} remaining

Limitations:
• Max 15 minute audio
• 192kbps MP3

Send me any YouTube link to download MP3! 🎵"""
        
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id
        )
    
    else:  # premium_mode
        user = get_user(user_id)
        
        if user and user[6] == 1:
            expiry = user[7] or "Not set"
            bot.edit_message_text(
                f"💎 PREMIUM ACTIVE\n\nYour premium is active until: {expiry}\n\nSend any YouTube link! 🎵",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            payment_text = f"""💎 PREMIUM SUBSCRIPTION

Price: {PREMIUM_PRICE} Birr / Month
Telebirr: {TELEBIRR_NUMBER}
Reference: {user_id}

Instructions:
1. Send {PREMIUM_PRICE} Birr to above number
2. Use {user_id} as reference
3. Send payment screenshot here

Admin will verify within 24 hours."""
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("📤 I PAID", callback_data="i_paid"))
            
            bot.edit_message_text(
                payment_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )

# ================= PAYMENT HANDLING =================
@bot.callback_query_handler(func=lambda call: call.data == "i_paid")
def handle_payment(call):
    bot.edit_message_text(
        "Please send payment screenshot...",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_payment)

def process_payment(message):
    user_id = message.from_user.id
    
    if message.photo:
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            os.makedirs("payments", exist_ok=True)
            path = f"payments/{user_id}_{int(time.time())}.jpg"
            
            with open(path, 'wb') as f:
                f.write(downloaded_file)
            
            bot.reply_to(message, "✅ Payment received! Admin will verify within 24 hours.")
            
            # Notify admin
            admin_text = f"""🤑 NEW PAYMENT REQUEST

User: @{message.from_user.username or 'No username'}
ID: {user_id}
Amount: {PREMIUM_PRICE} Birr
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_{user_id}"),
                types.InlineKeyboardButton("❌ REJECT", callback_data=f"reject_{user_id}")
            )
            
            bot.send_message(ADMIN_ID, admin_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Payment error: {e}")
            bot.reply_to(message, "❌ Error processing payment.")
    else:
        bot.reply_to(message, "❌ Please send a screenshot.")

@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve_", "reject_")))
def admin_action(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "You are not admin!")
        return
    
    action, user_id = call.data.split("_")
    user_id = int(user_id)
    
    if action == "approve":
        expiry = (datetime.now() + timedelta(days=30)).date().isoformat()
        update_user(user_id, premium=1, premium_expiry=expiry)
        
        try:
            bot.send_message(user_id, f"✅ PREMIUM ACTIVATED!\n\nYour premium is active for 30 days (until {expiry}).\n\nEnjoy unlimited downloads! 🎵")
        except Exception as e:
            logger.error(f"Error notifying user: {e}")
        
        bot.edit_message_text(
            f"✅ Premium activated for user {user_id}",
            call.message.chat.id,
            call.message.message_id
        )
    
    elif action == "reject":
        try:
            bot.send_message(user_id, "❌ Your payment was rejected. Please contact support.")
        except:
            pass
        
        bot.edit_message_text(
            f"❌ Payment rejected for user {user_id}",
            call.message.chat.id,
            call.message.message_id
        )

# ================= DOWNLOAD HANDLER =================
@bot.message_handler(func=lambda m: "youtu" in m.text.lower())
def handle_link(message):
    user_id = message.from_user.id
    
    if not check_membership(user_id):
        bot.reply_to(message, f"❌ Join {YOUR_CHANNEL} first using /start")
        return
    
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "Please use /start first")
        return
    
    url = message.text.strip()
    
    if user[6] == 1:  # Premium
        download_audio(message, url, True)
    else:
        # Check limits
        today = datetime.now().date().isoformat()
        if user[5] != today:
            update_user(user_id, daily_count=0, last_reset_date=today)
            user = get_user(user_id)
        
        if user[3] >= FREE_DAILY_LIMIT:
            bot.reply_to(message, f"❌ Daily limit reached ({FREE_DAILY_LIMIT}/{FREE_DAILY_LIMIT}). Try tomorrow or upgrade.")
            return
        
        if user[4] >= FREE_WEEKLY_LIMIT:
            bot.reply_to(message, f"❌ Weekly limit reached ({FREE_WEEKLY_LIMIT}/{FREE_WEEKLY_LIMIT}). Try next week or upgrade.")
            return
        
        download_audio(message, url, False)

def download_audio(message, url, is_premium):
    user_id = message.from_user.id
    
    try:
        status = bot.reply_to(message, "⏳ Processing your audio download...")
        bot.send_chat_action(message.chat.id, 'upload_audio')
        
        if not is_premium:
            with YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                duration = info.get('duration', 0)
                if duration > 900:  # 15 minutes
                    bot.edit_message_text(
                        "❌ Audio too long for free users (max 15 minutes).",
                        message.chat.id,
                        status.message_id
                    )
                    return
        
        # Download options
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        # Download audio
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            filename = filename.rsplit('.', 1)[0] + '.mp3'
        
        # Send audio file
        with open(filename, 'rb') as f:
            title = info.get('title', 'Audio')[:64]
            bot.send_audio(message.chat.id, f, title=title, performer="YouTube", timeout=100)
        
        # Update usage for free users
        if not is_premium:
            user = get_user(user_id)
            new_daily = user[3] + 1
            new_weekly = user[4] + 1
            update_user(user_id, daily_count=new_daily, weekly_count=new_weekly)
            
            remaining_daily = FREE_DAILY_LIMIT - new_daily
            remaining_weekly = FREE_WEEKLY_LIMIT - new_weekly
            
            bot.edit_message_text(
                f"✅ MP3 downloaded!\n\nToday: {remaining_daily}/{FREE_DAILY_LIMIT} remaining\nWeek: {remaining_weekly}/{FREE_WEEKLY_LIMIT} remaining",
                message.chat.id,
                status.message_id
            )
        else:
            bot.edit_message_text(
                "✅ Premium MP3 downloaded! 🎧",
                message.chat.id,
                status.message_id
            )
        
        # Cleanup file after 30 minutes
        def delete_file():
            time.sleep(1800)
            if os.path.exists(filename):
                os.remove(filename)
        
        Thread(target=delete_file, daemon=True).start()
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)[:100]}")

# ================= HELP COMMAND =================
@bot.message_handler(commands=['help'])
def help_command(message):
    text = f"""📚 HELP GUIDE

Commands:
/start - Start the bot
/help - Show this help
/status - Check your status

How to use:
1. Join {YOUR_CHANNEL} (required)
2. Choose Free or Premium mode
3. Send any YouTube link
4. Get MP3 audio file

Free Mode Limits:
• {FREE_DAILY_LIMIT} downloads per day
• {FREE_WEEKLY_LIMIT} downloads per week
• Max 15 minute audio

Premium ({PREMIUM_PRICE} Birr/month):
• Unlimited downloads
• No time limits
• Best quality

Need help? Contact admin."""
    
    bot.reply_to(message, text)

# ================= STATUS COMMAND =================
@bot.message_handler(commands=['status'])
def status_command(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        bot.reply_to(message, "Please use /start first")
        return
    
    premium_status = "✅ Active" if user[6] == 1 else "❌ Inactive"
    expiry = user[7] or "N/A"
    
    text = f"""📊 YOUR STATUS

Premium: {premium_status}
Expiry: {expiry}

Downloads today: {user[3]}/{FREE_DAILY_LIMIT}
Downloads this week: {user[4]}/{FREE_WEEKLY_LIMIT}"""
    
    bot.reply_to(message, text)

# ================= FLASK SERVER =================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ YouTube MP3 Downloader Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)

# ================= MAIN =================
if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("Starting YouTube MP3 Downloader Bot...")
    logger.info(f"Channel: {YOUR_CHANNEL}")
    logger.info(f"Admin ID: {ADMIN_ID}")
    logger.info(f"Telebirr: {TELEBIRR_NUMBER}")
    logger.info("=" * 50)
    
    # Start Flask server in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Start bot polling
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot error: {e}")
        time.sleep(5)
        bot.infinity_polling(timeout=60, long_polling_timeout=60)