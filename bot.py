import logging
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters, CallbackContext

# ================== НАСТРОЙКИ ==================
TOKEN = "8623075329:AAHRnpXR1nMd5m-STE8daYUAevtL9D38jEQ"
ADMIN_IDS = [1553865459]  # Ваш ID
DB_PATH = "homework_bot.db"
STAR_PRICE = 50  # Цена подписки в звёздах

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
    
    # Таблица с домашним заданием
    c.execute('''CREATE TABLE IF NOT EXISTS homework
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  subject TEXT,
                  task TEXT,
                  type TEXT DEFAULT 'regular',
                  date TEXT)''')
    
    # Таблица с решенным домашним заданием (для подписчиков)
    c.execute('''CREATE TABLE IF NOT EXISTS solved_homework
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  subject TEXT,
                  photo_id TEXT,
                  date TEXT)''')
    
    # Таблица с фотографиями
    c.execute('''CREATE TABLE IF NOT EXISTS photos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_id TEXT,
                  user_id INTEGER,
                  username TEXT,
                  date TEXT)''')
    
    # Таблица с администраторами
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  added_by INTEGER,
                  date TEXT)''')
    
    # Таблица с пользователями и подписками
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  subscription_end TEXT,
                  banned_until TEXT,
                  is_permanently_banned INTEGER DEFAULT 0,
                  warnings INTEGER DEFAULT 0,
                  join_date TEXT)''')
    
    # Таблица с настройками слежки
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    
    # Таблица с жалобами/связью с администратором
    c.execute('''CREATE TABLE IF NOT EXISTS reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  message TEXT,
                  date TEXT,
                  status TEXT DEFAULT 'new')''')
    
    conn.commit()
    conn.close()

# ================== ФУНКЦИИ ДЛЯ РАБОТЫ С БД ==================

# Проверка администратора
def is_admin(user_id):
    if user_id in ADMIN_IDS:
        return True
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

# Добавление администратора
def add_admin(user_id, username, added_by):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO admins VALUES (?, ?, ?, ?)",
              (user_id, username, added_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# Удаление администратора
def remove_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# Проверка слежки
def is_tracking_enabled():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'tracking'")
    result = c.fetchone()
    conn.close()
    return result is not None and result[0] == 'enabled'

# Включение/выключение слежки
def set_tracking(enabled):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
              ('tracking', 'enabled' if enabled else 'disabled'))
    conn.commit()
    conn.close()

# Регистрация пользователя
def register_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id, username, first_name, join_date) VALUES (?, ?, ?, ?)",
                  (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# Проверка бана
def is_banned(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT banned_until, is_permanently_banned FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return False
    
    banned_until, permanently = result
    
    if permanently == 1:
        return True
    
    if banned_until:
        ban_end = datetime.strptime(banned_until, "%Y-%m-%d %H:%M:%S")
        if ban_end > datetime.now():
            return True
    
    return False

# Бан пользователя
def ban_user(user_id, duration_hours=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if duration_hours is None:
        # Навсегда
        c.execute("UPDATE users SET is_permanently_banned = 1, banned_until = NULL WHERE user_id = ?", (user_id,))
    else:
        # На время
        ban_end = datetime.now() + timedelta(hours=duration_hours)
        c.execute("UPDATE users SET banned_until = ?, is_permanently_banned = 0 WHERE user_id = ?",
                  (ban_end.strftime("%Y-%m-%d %H:%M:%S"), user_id))
    
    conn.commit()
    conn.close()

# Разбан пользователя
def unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET banned_until = NULL, is_permanently_banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# Выдать подписку
def give_subscription(user_id, days=30):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if result and result[0]:
        current_end = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
        new_end = current_end + timedelta(days=days)
    else:
        new_end = datetime.now() + timedelta(days=days)
    
    c.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?",
              (new_end.strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

# Проверка подписки
def has_subscription(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return False
    
    end_date = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
    return end_date > datetime.now()

# Добавить фото
def add_photo(file_id, user_id, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO photos (file_id, user_id, username, date) VALUES (?, ?, ?, ?)",
              (file_id, user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# Получить случайное фото
def get_random_photo():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_id FROM photos")
    photos = c.fetchall()
    conn.close()
    if photos:
        return random.choice(photos)[0]
    return None

# Получить статистику фото
def get_photos_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM photos")
    return c.fetchone()[0]

# Добавить домашнее задание
def set_homework(subject, task):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO homework (subject, task, type, date) VALUES (?, ?, ?, ?)",
              (subject, task, 'regular', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# Получить домашнее задание
def get_homework():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subject, task FROM homework WHERE type='regular' ORDER BY id DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result

# Добавить решенное ДЗ
def add_solved_homework(subject, photo_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO solved_homework (subject, photo_id, date) VALUES (?, ?, ?)",
              (subject, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# Получить решенное ДЗ
def get_solved_homework():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subject, photo_id FROM solved_homework ORDER BY id DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result

# Добавить сообщение в поддержку
def add_report(user_id, username, message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reports (user_id, username, message, date) VALUES (?, ?, ?, ?)",
              (user_id, username, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    return report_id

# Получить новые сообщения
def get_new_reports():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, message, date FROM reports WHERE status='new' ORDER BY date")
    results = c.fetchall()
    conn.close()
    return results

# Отметить сообщение как прочитанное
def mark_report_read(report_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reports SET status='read' WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()

# ================== ДЕКОРАТОРЫ ==================
def admin_required(func):
    @wraps(func)
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

def not_banned(func):
    @wraps(func)
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if is_banned(user_id):
            update.message.reply_text("⛔ Вы забанены и не можете использовать бота.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

# ================== ОСНОВНЫЕ ФУНКЦИИ ==================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)
    
    # Главное меню
    keyboard = [
        [InlineKeyboardButton("📚 Домашнее задание", callback_data="menu_hw")],
        [InlineKeyboardButton("📸 Отправить фото", callback_data="menu_photo")],
        [InlineKeyboardButton("🎲 Случайное фото", callback_data="menu_random")],
        [InlineKeyboardButton("⭐ Подписка", callback_data="menu_subscription")],
        [InlineKeyboardButton("📞 Связаться с админом", callback_data="menu_support")],
    ]
    
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот-помощник 9Г класса. Выбери действие:"
    )
    
    update.message.reply_text(welcome_text, reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    if is_banned(user_id):
        query.edit_message_text("⛔ Вы забанены и не можете использовать бота.")
        return
    
    # Главное меню
    if query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("📚 Домашнее задание", callback_data="menu_hw")],
            [InlineKeyboardButton("📸 Отправить фото", callback_data="menu_photo")],
            [InlineKeyboardButton("🎲 Случайное фото", callback_data="menu_random")],
            [InlineKeyboardButton("⭐ Подписка", callback_data="menu_subscription")],
            [InlineKeyboardButton("📞 Связаться с админом", callback_data="menu_support")],
        ]
        if is_admin(user_id):
            keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_menu")])
        
        query.edit_message_text("🏠 Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Домашнее задание
    elif query.data == "menu_hw":
        hw = get_homework()
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        
        if hw:
            text = f"📚 **Домашнее задание:**\n\n**Предмет:** {hw[0]}\n**Задание:** {hw[1]}"
        else:
            text = "📚 Домашнее задание пока не добавлено."
        
        # Если есть подписка, показываем кнопку с решенным ДЗ
        if has_subscription(user_id):
            keyboard.insert(0, [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw")])
        
        query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Решенное ДЗ (для подписчиков)
    elif query.data == "menu_solved_hw":
        if not has_subscription(user_id):
            query.edit_message_text(
                "❌ У вас нет подписки!\n\n"
                "Купите подписку за 50 ⭐ или попросите администратора выдать её.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⭐ Купить подписку", callback_data="menu_subscription"),
                    InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
                ]])
            )
            return
        
        solved = get_solved_homework()
        if solved and solved[1]:
            subject, photo_id = solved
            query.message.reply_photo(
                photo=photo_id,
                caption=f"✅ Решенное домашнее задание\nПредмет: {subject}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
                ]])
            )
            query.message.delete()
        else:
            query.edit_message_text(
                "📝 Решенное домашнее задание пока не добавлено.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
                ]])
            )
    
    # Отправить фото
    elif query.data == "menu_photo":
        query.edit_message_text(
            "📸 Отправьте мне фото, и оно сохранится в общую галерею!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]])
        )
    
    # Случайное фото
    elif query.data == "menu_random":
        photo_id = get_random_photo()
        if photo_id:
            count = get_photos_count()
            caption = f"🎲 Случайное фото из галереи\nВсего фотографий: {count}"
            
            # Показываем, кто отправил, если слежка включена и пользователь админ
            if is_tracking_enabled() and is_admin(user_id):
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT username, user_id, date FROM photos WHERE file_id = ?", (photo_id,))
                photo_info = c.fetchone()
                conn.close()
                
                if photo_info:
                    username, photo_user_id, date = photo_info
                    caption += f"\n\n👤 Отправил: @{username or 'Неизвестно'} (ID: {photo_user_id})\n📅 Дата: {date}"
            
            query.message.reply_photo(
                photo=photo_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Ещё", callback_data="menu_random"),
                    InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
                ]])
            )
            query.message.delete()
        else:
            query.edit_message_text(
                "📸 В галерее пока нет фотографий. Отправь своё фото!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
                ]])
            )
    
    # Подписка
    elif query.data == "menu_subscription":
        if has_subscription(user_id):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
            end_date = c.fetchone()[0]
            conn.close()
            
            text = (
                f"⭐ **У вас активна подписка!**\n\n"
                f"Действует до: {end_date}\n\n"
                f"Доступно:\n"
                f"✅ Решенное домашнее задание"
            )
            keyboard = [[InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw")]]
        else:
            text = (
                f"⭐ **Подписка за {STAR_PRICE} звёзд**\n\n"
                f"Что дает подписка:\n"
                f"✅ Доступ к решенному домашнему заданию\n"
                f"✅ Приоритетная поддержка\n\n"
                f"Как оплатить:\n"
                f"1. Нажмите кнопку 'Оплатить звёздами'\n"
                f"2. Подтвердите платеж\n"
                f"3. Получите доступ!"
            )
            keyboard = [[InlineKeyboardButton(f"⭐ Оплатить {STAR_PRICE} звёзд", callback_data="pay_subscription")]]
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
        query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Оплата подписки
    elif query.data == "pay_subscription":
        query.edit_message_text(
            f"⭐ Для оплаты подписки отправьте {STAR_PRICE} звёзд этому боту.\n\n"
            f"Инструкция:\n"
            f"1. Нажмите на скрепку 📎\n"
            f"2. Выберите 💎 'Звёзды'\n"
            f"3. Укажите количество: {STAR_PRICE}\n"
            f"4. Отправьте и подписка активируется!\n\n"
            f"Или попросите администратора выдать подписку.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="menu_subscription")
            ]])
        )
    
    # Связь с админом
    elif query.data == "menu_support":
        query.edit_message_text(
            "📞 Напишите ваше сообщение для администратора.\n\n"
            "Опишите проблему или задайте вопрос — мы ответим как можно скорее!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]])
        )
        context.user_data['waiting_for_support'] = True
    
    # Админ-меню
    elif query.data == "admin_menu" and is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("📝 Изменить ДЗ", callback_data="admin_hw")],
            [InlineKeyboardButton("✅ Добавить решенное ДЗ", callback_data="admin_solved_hw")],
            [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton("❌ Удалить админа", callback_data="admin_remove")],
            [InlineKeyboardButton("🚫 Бан пользователя", callback_data="admin_ban")],
                        [InlineKeyboardButton("✅ Разбан пользователя", callback_data="admin_unban")],
            [InlineKeyboardButton("⭐ Выдать подписку", callback_data="admin_subscription")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("📞 Сообщения в поддержку", callback_data="admin_reports")],
            [InlineKeyboardButton("👁️ Слежка", callback_data="admin_tracking")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
        ]
        query.edit_message_text("👑 **Админ-панель**", parse_mode="Markdown", 
                              reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Слежка
    elif query.data == "admin_tracking" and is_admin(user_id):
        enabled = is_tracking_enabled()
        status = "✅ ВКЛЮЧЕНА" if enabled else "❌ ВЫКЛЮЧЕНА"
        keyboard = [
            [InlineKeyboardButton("✅ Включить" if not enabled else "❌ Выключить", 
                                 callback_data="toggle_tracking")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")],
        ]
        query.edit_message_text(
            f"👁️ **Настройка слежки**\n\n"
            f"Текущий статус: {status}\n\n"
            f"Когда слежка включена, администраторы видят, кто отправил фото.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Переключение слежки
    elif query.data == "toggle_tracking" and is_admin(user_id):
        enabled = is_tracking_enabled()
        set_tracking(not enabled)
        new_status = "✅ ВКЛЮЧЕНА" if not enabled else "❌ ВЫКЛЮЧЕНА"
        query.edit_message_text(
            f"👁️ Статус слежки изменен на: {new_status}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="admin_tracking")
            ]])
        )
    
    # Статистика
    elif query.data == "admin_stats" and is_admin(user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM photos")
        photos = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')")
        subs = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM reports WHERE status='new'")
        reports = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM admins")
        admins = c.fetchone()[0] + len(ADMIN_IDS)
        
        conn.close()
        
        text = (
            f"📊 **Статистика бота:**\n\n"
            f"👥 Всего пользователей: {users}\n"
            f"⭐ Подписчиков: {subs}\n"
            f"📸 Фотографий: {photos}\n"
            f"👑 Администраторов: {admins}\n"
            f"📞 Новых сообщений: {reports}"
        )
        
        query.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup([[
                                  InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                              ]]))
    
    # Сообщения в поддержку
    elif query.data == "admin_reports" and is_admin(user_id):
        reports = get_new_reports()
        
        if not reports:
            query.edit_message_text(
                "📞 Новых сообщений нет.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                ]])
            )
            return
        
        text = "📞 **Новые сообщения:**\n\n"
        for report in reports[:5]:  # Показываем первые 5
            report_id, user_id, username, message, date = report
            text += f"ID: {report_id}\nОт: @{username or 'Неизвестно'} (ID: {user_id})\nДата: {date}\nСообщение: {message}\n\n"
            mark_report_read(report_id)
        
        text += "\n✅ Сообщения отмечены как прочитанные. Ответьте пользователю в личные сообщения."
        
        query.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup([[
                                  InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                              ]]))
    
    # Разделы админ-панели, требующие ввода
    elif query.data in ["admin_hw", "admin_solved_hw", "admin_add", "admin_remove", 
                       "admin_ban", "admin_unban", "admin_subscription"] and is_admin(user_id):
        
        if query.data == "admin_hw":
            query.edit_message_text(
                "📝 Введите новое домашнее задание в формате:\n"
                "`Предмет: Задание`\n\n"
                "Пример: `Математика: Учебник стр. 45, № 123-125`",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = 'hw'
        
        elif query.data == "admin_solved_hw":
            query.edit_message_text(
                "✅ Отправьте фото решенного домашнего задания и укажите предмет.\n\n"
                "Сначала отправьте фото, а затем в сообщении напишите название предмета.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = 'solved_hw_waiting_photo'
        
        elif query.data == "admin_add":
            query.edit_message_text(
                "➕ Отправьте ID нового администратора.\n\n"
                "ID можно узнать у @userinfobot",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = 'add_admin'
        
        elif query.data == "admin_remove":
            query.edit_message_text(
                "❌ Отправьте ID администратора, которого хотите удалить.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = 'remove_admin'
        
        elif query.data == "admin_ban":
            query.edit_message_text(
                "🚫 Отправьте ID пользователя и время бана в часах.\n\n"
                "Формат: `ID часы`\n"
                "Пример: `123456789 24` - бан на 24 часа\n"
                "Если часы не указать - бан навсегда\n"
                "Пример: `123456789` - бан навсегда",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = 'ban'
        
        elif query.data == "admin_unban":
            query.edit_message_text(
                "✅ Отправьте ID пользователя для разбана.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = 'unban'
        
        elif query.data == "admin_subscription":
            query.edit_message_text(
                "⭐ Отправьте ID пользователя и количество дней подписки.\n\n"
                "Формат: `ID дни`\n"
                "Пример: `123456789 30` - подписка на 30 дней\n"
                "Если дни не указать - подписка на 30 дней по умолчанию",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = 'subscription'

# ================== ОБРАБОТЧИКИ СООБЩЕНИЙ ==================
@not_banned
def handle_photo(update: Update, context: CallbackContext):
    user = update.effective_user
    photo = update.message.photo[-1]
    
    # Проверяем, не ждем ли мы фото для решенного ДЗ
    if context.user_data.get('admin_action') == 'solved_hw_waiting_photo' and is_admin(user.id):
        context.user_data['solved_hw_photo'] = photo.file_id
        context.user_data['admin_action'] = 'solved_hw_waiting_subject'
        update.message.reply_text(
            "✅ Фото получено! Теперь напишите название предмета.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
            ]])
        )
        return
    
    # Обычное добавление фото
    add_photo(photo.file_id, user.id, user.username or user.first_name)
    count = get_photos_count()
    
    # Если слежка включена, уведомляем админов
    if is_tracking_enabled():
        for admin_id in ADMIN_IDS:
            try:
                context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📸 Новое фото от @{user.username or user.first_name} (ID: {user.id})"
                )
            except:
                pass
    
    update.message.reply_text(
        f"✅ Фото добавлено в галерею!\nВсего фотографий: {count}\n\n"
        f"Чтобы посмотреть случайное фото, нажми /random",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        ]])
    )

@not_banned
def handle_text(update: Update, context: CallbackContext):
    user = update.effective_user
    text = update.message.text
    
    # Обработка сообщений в поддержку
    if context.user_data.get('waiting_for_support'):
        report_id = add_report(user.id, user.username or user.first_name, text)
        update.message.reply_text(
            "✅ Ваше сообщение отправлено администратору! Мы ответим как можно скорее.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
        )
        context.user_data['waiting_for_support'] = False
        
        # Уведомляем админов
        for admin_id in ADMIN_IDS:
            try:
                context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📞 Новое сообщение в поддержку от @{user.username or user.first_name} (ID: {user.id})\n\n{text}"
                )
            except:
                pass
        return
    
    # Админ-действия
    if is_admin(user.id):
        action = context.user_data.get('admin_action')
        
        if action == 'hw':
            if ':' in text:
                subject, task = text.split(':', 1)
                set_homework(subject.strip(), task.strip())
                update.message.reply_text(
                    "✅ Домашнее задание обновлено!",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                context.user_data['admin_action'] = None
            else:
                update.message.reply_text("❌ Неверный формат. Используйте: `Предмет: Задание`", parse_mode="Markdown")
        
        elif action == 'solved_hw_waiting_subject':
            if context.user_data.get('solved_hw_photo'):
                add_solved_homework(text.strip(), context.user_data['solved_hw_photo'])
                update.message.reply_text(
                    "✅ Решенное домашнее задание добавлено!",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                context.user_data['admin_action'] = None
                context.user_data.pop('solved_hw_photo', None)
            else:
                update.message.reply_text("❌ Ошибка: фото не найдено")
        
        elif action == 'add_admin':
            try:
                admin_id = int(text.strip())
                try:
                    chat = context.bot.get_chat(admin_id)
                    username = chat.username or chat.first_name
                except:
                    username = "Unknown"
                
                add_admin(admin_id, username, user.id)
                update.message.reply_text(
                    f"✅ Пользователь {username} (ID: {admin_id}) теперь администратор!",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                context.user_data['admin_action'] = None
                
                try:
                    context.bot.send_message(
                        chat_id=admin_id,
                        text="🎉 Вас назначили администратором бота 'Помощник 9Г'!"
                    )
                except:
                    pass
            except ValueError:
                update.message.reply_text("❌ Введите числовой ID")
        
        elif action == 'remove_admin':
            try:
                admin_id = int(text.strip())
                if admin_id in ADMIN_IDS:
                    update.message.reply_text("❌ Нельзя удалить главного администратора")
                else:
                    remove_admin(admin_id)
                    update.message.reply_text(
                        f"✅ Администратор {admin_id} удален",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                        ]])
                    )
                    context.user_data['admin_action'] = None
            except ValueError:
                update.message.reply_text("❌ Введите числовой ID")
        
        elif action == 'ban':
            parts = text.strip().split()
            try:
                user_id = int(parts[0])
                hours = int(parts[1]) if len(parts) > 1 else None
                
                if hours:
                    ban_user(user_id, hours)
                    update.message.reply_text(f"✅ Пользователь {user_id} забанен на {hours} часов")
                else:
                    ban_user(user_id)
                    update.message.reply_text(f"✅ Пользователь {user_id} забанен навсегда")
                
                context.user_data['admin_action'] = None
            except:
                update.message.reply_text("❌ Неверный формат. Используйте: `ID часы` или просто `ID`")
        
        elif action == 'unban':
            try:
                user_id = int(text.strip())
                unban_user(user_id)
                update.message.reply_text(
                    f"✅ Пользователь {user_id} разбанен",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                context.user_data['admin_action'] = None
            except ValueError:
                update.message.reply_text("❌ Введите числовой ID")
        
        elif action == 'subscription':
            parts = text.strip().split()
            try:
                user_id = int(parts[0])
                days = int(parts[1]) if len(parts) > 1 else 30
                
                give_subscription(user_id, days)
                update.message.reply_text(
                    f"✅ Пользователю {user_id} выдана подписка на {days} дней",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                context.user_data['admin_action'] = None
                
                try:
                    context.bot.send_message(
                        chat_id=user_id,
                        text=f"⭐ Вам выдана подписка на {days} дней! Используйте /start для доступа к функциям."
                    )
                except:
                    pass
            except:
                update.message.reply_text("❌ Неверный формат. Используйте: `ID дни`")

# ================== ОБРАБОТЧИК ЗВЁЗД ==================
def handle_stars(update: Update, context: CallbackContext):
    """Обработчик оплаты звёздами"""
    user = update.effective_user
    
    if update.message.successful_payment:
        # Подтверждение оплаты
        give_subscription(user.id, 30)  # 30 дней подписки
        update.message.reply_text(
            "⭐ Спасибо за покупку! Подписка активирована на 30 дней.\n"
            "Теперь вам доступно решенное домашнее задание!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw"),
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
        )

# ================== ЗАПУСК БОТА ==================
def main():
    # Инициализация БД
    init_db()
    
    # Создаем updater
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Регистрируем обработчики
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dp.add_handler(MessageHandler(Filters.successful_payment, handle_stars))
    
    print("🚀 Бот 'Помощник 9Г' запущен...")
    print(f"👑 Главный администратор ID: {ADMIN_IDS[0]}")
    
    # Запускаем бота
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
```
