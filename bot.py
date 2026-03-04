import logging
import random
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters, CallbackContext

# ================== НАСТРОЙКИ ==================
TOKEN = "8705816654:AAHsYNSRPA5otJG5xqsVlfVc8GJ-oyMVZT0"
ADMIN_IDS = [1553865459]
DB_PATH = "homework_bot.db"

# ================== ЛОГИРОВАНИЕ ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== БАЗА ДАННЫХ ==================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS homework
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  subject TEXT,
                  task TEXT,
                  date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS photos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_id TEXT,
                  user_id INTEGER,
                  username TEXT,
                  date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  added_by INTEGER,
                  date TEXT)''')
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id in ADMIN_IDS:
        return True
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_admin(user_id, username, added_by):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO admins VALUES (?, ?, ?, ?)",
              (user_id, username, added_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_homework():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subject, task FROM homework ORDER BY id DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result

def set_homework(subject, task):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO homework (subject, task, date) VALUES (?, ?, ?)",
              (subject, task, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def add_photo(file_id, user_id, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO photos (file_id, user_id, username, date) VALUES (?, ?, ?, ?)",
              (file_id, user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_random_photo():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_id FROM photos")
    photos = c.fetchall()
    conn.close()
    if photos:
        return random.choice(photos)[0]
    return None

def get_photos_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM photos")
    return c.fetchone()[0]

# ================== ОБРАБОТЧИКИ ==================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    text = f"👋 Привет, {user.first_name}!\n\nЯ бот-помощник 9Г класса.\n\n"
    text += "📚 /hw - узнать ДЗ\n📸 Отправь фото - оно сохранится\n🎲 /random - случайное фото\n"
    if is_admin(user.id):
        text += "\n👑 /admin - панель администратора"
    update.message.reply_text(text)

def homework(update: Update, context: CallbackContext):
    hw = get_homework()
    if hw:
        update.message.reply_text(f"📚 Домашнее задание:\n\nПредмет: {hw[0]}\nЗадание: {hw[1]}")
    else:
        update.message.reply_text("📚 Домашнее задание пока не добавлено.")

def random_photo(update: Update, context: CallbackContext):
    photo_id = get_random_photo()
    if photo_id:
        count = get_photos_count()
        update.message.reply_photo(photo=photo_id, caption=f"🎲 Случайное фото (всего: {count})")
    else:
        update.message.reply_text("📸 Фотографий пока нет.")

def handle_photo(update: Update, context: CallbackContext):
    user = update.effective_user
    photo = update.message.photo[-1]
    add_photo(photo.file_id, user.id, user.username or user.first_name)
    count = get_photos_count()
    update.message.reply_text(f"✅ Фото добавлено! Всего: {count}")

def admin_panel(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Нет прав.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📝 Изменить ДЗ", callback_data="hw")],
        [InlineKeyboardButton("➕ Добавить админа", callback_data="admin")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
    ]
    update.message.reply_text("👑 Панель администратора:", 
                            reply_markup=InlineKeyboardMarkup(keyboard))

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    if not is_admin(query.from_user.id):
        query.edit_message_text("❌ Нет прав.")
        return
    
    if query.data == "hw":
        query.edit_message_text("📝 Введите ДЗ в формате: Предмет: Задание")
        context.user_data['step'] = 'hw'
    elif query.data == "admin":
        query.edit_message_text("➕ Введите ID нового администратора:")
        context.user_data['step'] = 'admin'
    elif query.data == "stats":
        photos = get_photos_count()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM admins")
        admins = c.fetchone()[0] + 1
        c.execute("SELECT COUNT(*) FROM homework")
        hw_count = c.fetchone()[0]
        conn.close()
        query.edit_message_text(f"📊 Статистика:\n\n📸 Фото: {photos}\n👑 Админы: {admins}\n📚 Записей ДЗ: {hw_count}")

def handle_text(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    
    if context.user_data.get('step') == 'hw':
        text = update.message.text
        if ':' in text:
            subject, task = text.split(':', 1)
            set_homework(subject.strip(), task.strip())
            update.message.reply_text("✅ ДЗ обновлено!")
            context.user_data['step'] = None
        else:
            update.message.reply_text("❌ Используйте формат: Предмет: Задание")
    
    elif context.user_data.get('step') == 'admin':
        try:
            admin_id = int(update.message.text)
            add_admin(admin_id, "admin", update.effective_user.id)
            update.message.reply_text(f"✅ Админ {admin_id} добавлен!")
            context.user_data['step'] = None
        except:
            update.message.reply_text("❌ Введите числовой ID")

def main():
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("hw", homework))
    dp.add_handler(CommandHandler("random", random_photo))
    dp.add_handler(CommandHandler("admin", admin_panel))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    print("✅ Бот запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
