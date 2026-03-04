import logging
import random
import sqlite3
from datetime import datetime
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ================== НАСТРОЙКИ ==================
TOKEN = "8705816654:AAHsYNSRPA5otJG5xqsVlfVc8GJ-oyMVZT0"
ADMIN_IDS = [1553865459]  # Ваш ID
DB_PATH = "homework_bot.db"

# ================== ЛОГИРОВАНИЕ ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== БАЗА ДАННЫХ ==================
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица с домашним заданием
    c.execute('''CREATE TABLE IF NOT EXISTS homework
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  subject TEXT NOT NULL,
                  task TEXT NOT NULL,
                  date TEXT NOT NULL)''')
    
    # Таблица с фотографиями
    c.execute('''CREATE TABLE IF NOT EXISTS photos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_id TEXT NOT NULL,
                  user_id INTEGER,
                  username TEXT,
                  date TEXT NOT NULL)''')
    
    # Таблица с администраторами
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  added_by INTEGER,
                  date TEXT NOT NULL)''')
    
    conn.commit()
    conn.close()

# ================== ФУНКЦИИ ДЛЯ РАБОТЫ С БД ==================
def is_admin(user_id):
    """Проверка, является ли пользователь администратором"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None or user_id in ADMIN_IDS

def add_admin(user_id, username, added_by):
    """Добавление нового администратора"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO admins (user_id, username, added_by, date) VALUES (?, ?, ?, ?)",
              (user_id, username, added_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_homework():
    """Получение текущего домашнего задания"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subject, task FROM homework ORDER BY id DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result

def set_homework(subject, task):
    """Установка нового домашнего задания"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO homework (subject, task, date) VALUES (?, ?, ?)",
              (subject, task, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def add_photo(file_id, user_id, username):
    """Добавление фотографии в базу"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO photos (file_id, user_id, username, date) VALUES (?, ?, ?, ?)",
              (file_id, user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_random_photo():
    """Получение случайной фотографии"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_id FROM photos")
    photos = c.fetchall()
    conn.close()
    
    if photos:
        return random.choice(photos)[0]
    return None

def get_photos_count():
    """Получение количества фотографий в базе"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM photos")
    count = c.fetchone()[0]
    conn.close()
    return count

# ================== ДЕКОРАТОР ДЛЯ ПРОВЕРКИ АДМИНА ==================
def admin_required(func):
    """Декоратор для проверки прав администратора"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ================== ОБРАБОТЧИКИ КОМАНД ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот-помощник 9Г класса. Вот что я умею:\n\n"
        "📚 /hw - узнать домашнее задание\n"
        "📸 Отправь мне фото, и оно сохранится в общую галерею\n"
        "🎲 /random - получить случайное фото из галереи\n"
        "ℹ️ /help - показать это сообщение\n\n"
    )
    
    # Добавляем информацию об админ-панели, если пользователь администратор
    if is_admin(user.id):
        welcome_text += (
            "👑 **Панель администратора:**\n"
            "/admin - показать панель администратора\n"
        )
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await start(update, context)

async def homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /hw - показать домашнее задание"""
    hw = get_homework()
    if hw:
        subject, task = hw
        await update.message.reply_text(
            f"📚 **Текущее домашнее задание:**\n\n"
            f"**Предмет:** {subject}\n"
            f"**Задание:** {task}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("📚 Домашнее задание пока не добавлено.")

async def random_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /random - показать случайное фото"""
    photo_id = get_random_photo()
    if photo_id:
        count = get_photos_count()
        await update.message.reply_photo(
            photo=photo_id,
            caption=f"🎲 Случайное фото из галереи\n"
                   f"Всего фотографий: {count}"
        )
    else:
        await update.message.reply_text("📸 В галерее пока нет фотографий. Отправь своё фото!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик получения фотографий"""
    user = update.effective_user
    photo = update.message.photo[-1]  # Берем самое качественное фото
    
    # Сохраняем фото в базу
    add_photo(photo.file_id, user.id, user.username or user.first_name)
    
    count = get_photos_count()
    await update.message.reply_text(
        f"✅ Фото добавлено в галерею!\n"
        f"Всего фотографий: {count}\n\n"
        f"Чтобы посмотреть случайное фото, используй /random"
    )

# ================== АДМИН-ПАНЕЛЬ ==================
@admin_required
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель администратора"""
    keyboard = [
        [InlineKeyboardButton("📝 Изменить домашнее задание", callback_data="admin_edit_hw")],
        [InlineKeyboardButton("➕ Добавить администратора", callback_data="admin_add_admin")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👑 **Панель администратора**\n\nВыберите действие:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

@admin_required
async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback-запросов от админ-панели"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_edit_hw":
        await query.edit_message_text(
            "📝 Введите новое домашнее задание в формате:\n"
            "`Предмет: Задание`\n\n"
            "Пример: `Математика: Учебник стр. 45, № 123-125`\n\n"
            "Или отправьте /cancel для отмены"
        )
        context.user_data["awaiting_hw"] = True
        
    elif query.data == "admin_add_admin":
        await query.edit_message_text(
            "➕ Чтобы добавить нового администратора, перешлите мне сообщение от того пользователя или отправьте его ID.\n\n"
            "ID можно узнать с помощью бота @userinfobot\n\n"
            "Или отправьте /cancel для отмены"
        )
        context.user_data["awaiting_admin_id"] = True
        
    elif query.data == "admin_stats":
        # Получаем статистику
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM photos")
        photos_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM admins")
        admins_count = c.fetchone()[0] + len(ADMIN_IDS)
        
        c.execute("SELECT COUNT(*) FROM homework")
        hw_count = c.fetchone()[0]
        
        conn.close()
        
        await query.edit_message_text(
            "📊 **Статистика бота:**\n\n"
            f"📸 Фотографий в галерее: {photos_count}\n"
            f"👑 Администраторов: {admins_count}\n"
            f"📚 Записей о ДЗ: {hw_count}",
            parse_mode="Markdown"
        )

@admin_required
async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода от администратора"""
    user_id = update.effective_user.id
    
    # Обработка добавления домашнего задания
    if context.user_data.get("awaiting_hw"):
        text = update.message.text
        
        if ":" in text:
            subject, task = text.split(":", 1)
            set_homework(subject.strip(), task.strip())
            
            await update.message.reply_text(
                "✅ Домашнее задание успешно обновлено!"
            )
            context.user_data["awaiting_hw"] = False
        else:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: `Предмет: Задание`\n"
                "Попробуйте снова или отправьте /cancel",
                parse_mode="Markdown"
            )
    
    # Обработка добавления администратора
    elif context.user_data.get("awaiting_admin_id"):
        try:
            new_admin_id = int(update.message.text.strip())
            
            # Получаем информацию о пользователе
            try:
                chat = await context.bot.get_chat(new_admin_id)
                username = chat.username or chat.first_name
            except:
                username = "Unknown"
            
            add_admin(new_admin_id, username, user_id)
            
            await update.message.reply_text(
                f"✅ Пользователь {username} (ID: {new_admin_id}) "
                f"теперь администратор!"
            )
            context.user_data["awaiting_admin_id"] = False
            
            # Уведомляем нового администратора
            try:
                await context.bot.send_message(
                    chat_id=new_admin_id,
                    text="🎉 Вас назначили администратором бота 'Помощник 9Г'!\n"
                         "Используйте /admin для доступа к панели управления."
                )
            except:
                pass
                
        except ValueError:
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте числовой ID пользователя\n"
                "Попробуйте снова или отправьте /cancel"
            )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущего действия"""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено.")

# ================== ЗАПУСК БОТА ==================
def main():
    """Главная функция запуска бота"""
    # Инициализация БД
    init_db()
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("hw", homework))
    application.add_handler(CommandHandler("random", random_photo))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("cancel", cancel))
    
    # Обработчик фотографий
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Обработчик callback-запросов (для кнопок)
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    
    # Обработчик текстовых сообщений для админ-режима
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_admin_input
    ))
    
    # Запускаем бота
    print("🚀 Бот 'Помощник 9Г' запущен...")
    print(f"👑 Главный администратор ID: {ADMIN_IDS[0]}")
    print("📸 Бот готов к работе!")
    application.run_polling()

if __name__ == "__main__":
    main()
