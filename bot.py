import logging
import random
import sqlite3
from datetime import datetime
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext
)

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
                  subject TEXT NOT NULL,
                  task TEXT NOT NULL,
                  date TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS photos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_id TEXT NOT NULL,
                  user_id INTEGER,
                  username TEXT,
                  date TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  added_by INTEGER,
                  date TEXT NOT NULL)''')
    conn.commit()
    conn.close()

def is_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None or user_id in ADMIN_IDS

def add_admin(user_id, username, added_by):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO admins (user_id, username, added_by, date) VALUES (?, ?, ?, ?)",
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
    count = c.fetchone()[0]
    conn.close()
    return count

# ================== ОБРАБОТЧИКИ ==================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот-помощник 9Г класса. Вот что я умею:\n\n"
        "📚 /hw - узнать домашнее задание\n"
        "📸 Отправь мне фото, и оно сохранится в общую галерею\n"
        "🎲 /random - получить случайное фото из галереи\n"
        "ℹ️ /help - показать это сообщение\n\n"
    )
    if is_admin(user.id):
        welcome_text += "👑 **Панель администратора:**\n/admin - показать панель администратора\n"
    update.message.reply_text(welcome_text, parse_mode="Markdown")

def help_command(update: Update, context: CallbackContext):
    start(update, context)

def homework(update: Update, context: CallbackContext):
    hw = get_homework()
    if hw:
        subject, task = hw
        update.message.reply_text(
            f"📚 **Текущее домашнее задание:**\n\n"
            f"**Предмет:** {subject}\n"
            f"**Задание:** {task}",
            parse_mode="Markdown"
        )
    else:
        update.message.reply_text("📚 Домашнее задание пока не добавлено.")

def random_photo(update: Update, context: CallbackContext):
    photo_id = get_random_photo()
    if photo_id:
        count = get_photos_count()
        update.message.reply_photo(
            photo=photo_id,
            caption=f"🎲 Случайное фото из галереи\nВсего фотографий: {count}"
        )
    else:
        update.message.reply_text("📸 В галерее пока нет фотографий. Отправь своё фото!")

def handle_photo(update: Update, context: CallbackContext):
    user = update.effective_user
    photo = update.message.photo[-1]
    add_photo(photo.file_id, user.id, user.username or user.first_name)
    count = get_photos_count()
    update.message.reply_text(
        f"✅ Фото добавлено в галерею!\nВсего фотографий: {count}\n\n"
        f"Чтобы посмотреть случайное фото, используй /random"
    )

def admin_panel(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📝 Изменить домашнее задание", callback_data="admin_edit_hw")],
        [InlineKeyboardButton("➕ Добавить администратора", callback_data="admin_add_admin")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "👑 **Панель администратора**\n\nВыберите действие:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    if not is_admin(query.from_user.id):
        query.edit_message_text("❌ У вас нет прав для этого действия.")
        return
    
    if query.data == "admin_edit_hw":
        query.edit_message_text(
            "📝 Введите новое домашнее задание в формате:\n"
            "`Предмет: Задание`\n\n"
            "Пример: `Математика: Учебник стр. 45, № 123-125`\n\n"
            "Или отправьте /cancel для отмены"
        )
        context.user_data['awaiting_hw'] = True
        
    elif query.data == "admin_add_admin":
        query.edit_message_text(
            "➕ Отправьте ID нового администратора.\n\n"
            "ID можно узнать у @userinfobot\n\n"
            "Или отправьте /cancel для отмены"
        )
        context.user_data['awaiting_admin_id'] = True
        
    elif query.data == "admin_stats":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM photos")
        photos_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM admins")
        admins_count = c.fetchone()[0] + len(ADMIN_IDS)
        c.execute("SELECT COUNT(*) FROM homework")
        hw_count = c.fetchone()[0]
        conn.close()
        
        query.edit_message_text(
            "📊 **Статистика бота:**\n\n"
            f"📸 Фотографий: {photos_count}\n"
            f"👑 Администраторов: {admins_count}\n"
            f"📚 Записей о ДЗ: {hw_count}",
            parse_mode="Markdown"
        )

def handle_admin_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    if context.user_data.get('awaiting_hw'):
        text = update.message.text
        if ":" in text:
            subject, task = text.split(":", 1)
            set_homework(subject.strip(), task.strip())
            update.message.reply_text("✅ Домашнее задание обновлено!")
            context.user_data['awaiting_hw'] = False
        else:
            update.message.reply_text("❌ Неверный формат. Используйте: `Предмет: Задание`", parse_mode="Markdown")
    
    elif context.user_data.get('awaiting_admin_id'):
        try:
            new_admin_id = int(update.message.text.strip())
            try:
                chat = context.bot.get_chat(new_admin_id)
                username = chat.username or chat.first_name
            except:
                username = "Unknown"
            
            add_admin(new_admin_id, username, user_id)
            update.message.reply_text(f"✅ Пользователь {username} теперь администратор!")
            context.user_data['awaiting_admin_id'] = False
            
            try:
                context.bot.send_message(
                    chat_id=new_admin_id,
                    text="🎉 Вас назначили администратором бота 'Помощник 9Г'!\nИспользуйте /admin для доступа к панели."
                )
            except:
                pass
        except ValueError:
            update.message.reply_text("❌ Отправьте числовой ID пользователя")

def cancel(update: Update, context: CallbackContext):
    context.user_data.clear()
    update.message.reply_text("❌ Действие отменено.")

def main():
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("hw", homework))
    dp.add_handler(CommandHandler("random", random_photo))
    dp.add_handler(CommandHandler("admin", admin_panel))
    dp.add_handler(CommandHandler("cancel", cancel))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_admin_input))
    
    print("🚀 Бот 'Помощник 9Г' запущен...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
