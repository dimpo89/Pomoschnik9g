import logging
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
import time
import asyncio
from collections import deque
from threading import Thread
from queue import Queue

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters, CallbackContext

# ================== НАСТРОЙКИ ==================
TOKEN = "8623075329:AAHRnpXR1nMd5m-STE8daYUAevtL9D38jEQ"
ADMIN_IDS = [1553865459]  # Ваш ID
DB_PATH = "homework_bot.db"
STAR_PRICE = 50  # Цена подписки в звёздах
PHOTO_EXPIRE_DAYS = 7  # Фото удаляются через 7 дней

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
                  photo_ids TEXT,
                  date TEXT,
                  expires_at TEXT)''')
    
    # Таблица с фотографиями (с модерацией)
    c.execute('''CREATE TABLE IF NOT EXISTS photos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_id TEXT,
                  user_id INTEGER,
                  username TEXT,
                  date TEXT,
                  status TEXT DEFAULT 'pending',  # pending, approved, rejected
                  moderated_by INTEGER,
                  moderation_date TEXT)''')
    
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
                  join_date TEXT,
                  rating INTEGER DEFAULT 0,
                  photos_count INTEGER DEFAULT 0,
                  last_active TEXT)''')
    
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
    
    # Таблица для рассылок
    c.execute('''CREATE TABLE IF NOT EXISTS broadcasts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  admin_id INTEGER,
                  message TEXT,
                  date TEXT,
                  status TEXT DEFAULT 'pending')''')
    
    # Таблица для ежедневных фактов
    c.execute('''CREATE TABLE IF NOT EXISTS daily_facts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  fact TEXT,
                  category TEXT,
                  added_by INTEGER,
                  date TEXT)''')
    
    # Таблица для опросов
    c.execute('''CREATE TABLE IF NOT EXISTS polls
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  question TEXT,
                  options TEXT,
                  created_by INTEGER,
                  date TEXT,
                  expires_at TEXT,
                  is_active INTEGER DEFAULT 1)''')
    
    # Таблица для голосов в опросах
    c.execute('''CREATE TABLE IF NOT EXISTS poll_votes
                 (poll_id INTEGER,
                  user_id INTEGER,
                  option_index INTEGER,
                  date TEXT,
                  PRIMARY KEY (poll_id, user_id))''')
    
    conn.commit()
    conn.close()

# ================== ФУНКЦИИ ДЛЯ УСКОРЕНИЯ РАБОТЫ ==================
# Кэш для частых запросов
cache = {
    'stats': {'data': None, 'timestamp': 0},
    'homework': {'data': None, 'timestamp': 0},
    'solved_hw': {'data': None, 'timestamp': 0},
    'photo_count': {'data': 0, 'timestamp': 0}
}
CACHE_TTL = 60  # Кэш живет 60 секунд

def get_cached_or_query(key, query_func, ttl=CACHE_TTL):
    """Получить данные из кэша или выполнить запрос"""
    now = time.time()
    if key in cache and now - cache[key]['timestamp'] < ttl:
        return cache[key]['data']
    
    data = query_func()
    cache[key] = {'data': data, 'timestamp': now}
    return data

def invalidate_cache(keys=None):
    """Очистить кэш"""
    if keys:
        for key in keys:
            if key in cache:
                cache[key]['timestamp'] = 0
    else:
        for key in cache:
            cache[key]['timestamp'] = 0

# Очередь для асинхронных задач
task_queue = Queue()

def worker():
    """Фоновый рабочий процесс"""
    while True:
        task = task_queue.get()
        if task is None:
            break
        try:
            task['func'](*task['args'], **task['kwargs'])
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче: {e}")
        task_queue.task_done()

# Запускаем фоновый рабочий процесс
Thread(target=worker, daemon=True).start()

def add_background_task(func, *args, **kwargs):
    """Добавить задачу в фоновую очередь"""
    task_queue.put({'func': func, 'args': args, 'kwargs': kwargs})

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
    invalidate_cache(['stats'])

# Удаление администратора
def remove_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    invalidate_cache(['stats'])

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
        c.execute("INSERT INTO users (user_id, username, first_name, join_date, last_active) VALUES (?, ?, ?, ?, ?)",
                  (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    else:
        c.execute("UPDATE users SET last_active = ?, username = ? WHERE user_id = ?",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, user_id))
    conn.commit()
    conn.close()
    invalidate_cache(['stats'])

# Получить всех пользователей
def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

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
        try:
            ban_end = datetime.strptime(banned_until, "%Y-%m-%d %H:%M:%S")
            if ban_end > datetime.now():
                return True
        except:
            pass
    
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
    invalidate_cache(['stats'])

# Разбан пользователя
def unban_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET banned_until = NULL, is_permanently_banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    invalidate_cache(['stats'])

# Выдать подписку
def give_subscription(user_id, days=30):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if result and result[0]:
        try:
            current_end = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
            new_end = current_end + timedelta(days=days)
        except:
            new_end = datetime.now() + timedelta(days=days)
    else:
        new_end = datetime.now() + timedelta(days=days)
    
    c.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?",
              (new_end.strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()
    invalidate_cache(['stats'])

# Проверка подписки
def has_subscription(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return False
    
    try:
        end_date = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
        return end_date > datetime.now()
    except:
        return False

# Добавить фото на модерацию
def add_photo_pending(file_id, user_id, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Удаляем старые фото (старше PHOTO_EXPIRE_DAYS дней)
    expire_date = (datetime.now() - timedelta(days=PHOTO_EXPIRE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("DELETE FROM photos WHERE date < ? AND status != 'pending'", (expire_date,))
    
    c.execute("INSERT INTO photos (file_id, user_id, username, date, status) VALUES (?, ?, ?, ?, ?)",
              (file_id, user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'pending'))
    photo_id = c.lastrowid
    conn.commit()
    conn.close()
    invalidate_cache(['stats', 'photo_count'])
    return photo_id

# Одобрить фото
def approve_photo(photo_id, admin_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE photos SET status = 'approved', moderated_by = ?, moderation_date = ? WHERE id = ?",
              (admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), photo_id))
    c.execute("UPDATE users SET photos_count = photos_count + 1 WHERE user_id = (SELECT user_id FROM photos WHERE id = ?)", (photo_id,))
    conn.commit()
    conn.close()
    invalidate_cache(['stats', 'photo_count'])

# Отклонить фото
def reject_photo(photo_id, admin_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE photos SET status = 'rejected', moderated_by = ?, moderation_date = ? WHERE id = ?",
              (admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), photo_id))
    conn.commit()
    conn.close()
    invalidate_cache(['stats', 'photo_count'])

# Получить фото на модерации
def get_pending_photos():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, file_id, user_id, username, date FROM photos WHERE status = 'pending' ORDER BY date")
    results = c.fetchall()
    conn.close()
    return results

# Получить случайное одобренное фото
def get_random_photo():
    def _query():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT file_id FROM photos WHERE status = 'approved'")
        photos = c.fetchall()
        conn.close()
        if photos:
            return random.choice(photos)[0]
        return None
    
    return get_cached_or_query('random_photo', _query, ttl=30)

# Получить статистику фото
def get_photos_count():
    def _query():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM photos WHERE status = 'approved'")
        return c.fetchone()[0]
    
    return get_cached_or_query('photo_count', _query)
# Добавить домашнее задание
def set_homework(subject, task):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO homework (subject, task, type, date) VALUES (?, ?, ?, ?)",
              (subject, task, 'regular', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    invalidate_cache(['homework'])

# Получить домашнее задание
def get_homework():
    def _query():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT subject, task FROM homework WHERE type='regular' ORDER BY id DESC LIMIT 1")
        return c.fetchone()
    
    return get_cached_or_query('homework', _query)

# Добавить решенное ДЗ (несколько фото)
def add_solved_homework(subject, photo_ids):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Удаляем старые записи
    c.execute("DELETE FROM solved_homework")
    
    # Сохраняем новые фото (как строку с ID через запятую)
    photo_ids_str = ','.join(photo_ids)
    expires_at = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("INSERT INTO solved_homework (subject, photo_ids, date, expires_at) VALUES (?, ?, ?, ?)",
              (subject, photo_ids_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at))
    conn.commit()
    conn.close()
    invalidate_cache(['solved_hw'])

# Получить решенное ДЗ
def get_solved_homework():
    def _query():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Удаляем просроченные
        c.execute("DELETE FROM solved_homework WHERE expires_at < datetime('now')")
        
        c.execute("SELECT subject, photo_ids FROM solved_homework ORDER BY id DESC LIMIT 1")
        result = c.fetchone()
        conn.close()
        
        if result:
            subject, photo_ids_str = result
            photo_ids = photo_ids_str.split(',') if photo_ids_str else []
            return subject, photo_ids
        return None, []
    
    return get_cached_or_query('solved_hw', _query, ttl=30)

# Добавить сообщение в поддержку
def add_report(user_id, username, message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reports (user_id, username, message, date) VALUES (?, ?, ?, ?)",
              (user_id, username, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    report_id = c.lastrowid
    conn.commit()
    conn.close()
    invalidate_cache(['reports'])
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

# Сохранить рассылку
def save_broadcast(admin_id, message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO broadcasts (admin_id, message, date) VALUES (?, ?, ?)",
              (admin_id, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    broadcast_id = c.lastrowid
    conn.commit()
    conn.close()
    return broadcast_id

# ================== НОВЫЕ ФУНКЦИИ ==================

# 1. Ежедневные факты
def add_daily_fact(fact, category, added_by):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO daily_facts (fact, category, added_by, date) VALUES (?, ?, ?, ?)",
              (fact, category, added_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    fact_id = c.lastrowid
    conn.commit()
    conn.close()
    invalidate_cache(['facts'])
    return fact_id

def get_random_fact():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT fact, category FROM daily_facts ORDER BY RANDOM() LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result

def get_facts_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM daily_facts")
    count = c.fetchone()[0]
    conn.close()
    return count

# 2. Опросы
def create_poll(question, options, created_by, hours_duration=24):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    options_str = '|'.join(options)
    expires_at = (datetime.now() + timedelta(hours=hours_duration)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO polls (question, options, created_by, date, expires_at) VALUES (?, ?, ?, ?, ?)",
              (question, options_str, created_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at))
    poll_id = c.lastrowid
    conn.commit()
    conn.close()
    invalidate_cache(['polls'])
    return poll_id

def get_active_polls():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, question, options, created_by, date, expires_at FROM polls WHERE is_active=1 AND expires_at > datetime('now') ORDER BY date DESC")
    results = c.fetchall()
    conn.close()
    return results

def vote_in_poll(poll_id, user_id, option_index):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO poll_votes (poll_id, user_id, option_index, date) VALUES (?, ?, ?, ?)",
                  (poll_id, user_id, option_index, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    invalidate_cache([f'poll_{poll_id}'])
    return success

def get_poll_results(poll_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT question, options FROM polls WHERE id=?", (poll_id,))
    poll = c.fetchone()
    if not poll:
        conn.close()
        return None
    
    question, options_str = poll
    options = options_str.split('|')
    
    c.execute("SELECT option_index, COUNT(*) FROM poll_votes WHERE poll_id=? GROUP BY option_index", (poll_id,))
    votes = dict(c.fetchall())
    
    total_votes = sum(votes.values())
    results = []
    for i, option in enumerate(options):
        count = votes.get(i, 0)
        percentage = (count / total_votes * 100) if total_votes > 0 else 0
        results.append((option, count, percentage))
    
    conn.close()
    return question, results, total_votes

def close_poll(poll_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE polls SET is_active=0 WHERE id=?", (poll_id,))
    conn.commit()
    conn.close()
    invalidate_cache(['polls'])

# 3. Рейтинг пользователей
def get_user_rating(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT rating, photos_count FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result or (0, 0)

def add_user_rating(user_id, points):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET rating = rating + ? WHERE user_id=?", (points, user_id))
    conn.commit()
    conn.close()
    invalidate_cache(['ratings'])

def get_top_users(limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, rating, photos_count FROM users WHERE rating > 0 ORDER BY rating DESC LIMIT ?", (limit,))
    results = c.fetchall()
    conn.close()
    return results

# 4. Автоочистка старых данных
def cleanup_old_data():
    """Автоматически удаляет старые данные"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Удаляем старые фото (одобренные, старше PHOTO_EXPIRE_DAYS)
    expire_date = (datetime.now() - timedelta(days=PHOTO_EXPIRE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("DELETE FROM photos WHERE date < ? AND status = 'approved'", (expire_date,))
    
    # Удаляем старые опросы (неактивные, старше 7 дней)
    old_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("DELETE FROM polls WHERE is_active=0 AND date < ?", (old_date,))
    c.execute("DELETE FROM poll_votes WHERE poll_id NOT IN (SELECT id FROM polls)")
    
    # Удаляем старые отчеты
    c.execute("DELETE FROM reports WHERE status='read' AND date < ?", (old_date,))
    
    conn.commit()
    conn.close()
    invalidate_cache()

# Запускаем автоочистку раз в день (будет выполняться при каждом запуске, но это ок)
add_background_task(cleanup_old_data)

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

# ================== ФУНКЦИЯ ДЛЯ ВОЗВРАТА В МЕНЮ ==================
def get_main_menu_keyboard(user_id):
    """Создает клавиатуру главного меню"""
    keyboard = [
        [InlineKeyboardButton("📚 Домашнее задание", callback_data="menu_hw")],
        [InlineKeyboardButton("📸 Отправить фото", callback_data="menu_photo")],
        [InlineKeyboardButton("🎲 Случайное фото", callback_data="menu_random")],
        [InlineKeyboardButton("⭐ Подписка", callback_data="menu_subscription")],
        [InlineKeyboardButton("📞 Связаться с админом", callback_data="menu_support")],
    ]
    
    # Новые функции для всех
    keyboard.append([InlineKeyboardButton("📊 Мой рейтинг", callback_data="menu_rating")])
    keyboard.append([InlineKeyboardButton("🎯 Интересный факт", callback_data="menu_fact")])
    
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_menu")])
    
    return InlineKeyboardMarkup(keyboard)

# ================== ОСНОВНЫЕ ФУНКЦИИ ==================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    register_user(user.id, user.username, user.first_name)
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот-помощник 9Г класса. Выбери действие:"
    )
    
    update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(user.id))

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    if is_banned(user_id):
        query.edit_message_text("⛔ Вы забанены и не можете использовать бота.")
        return
    
    # Главное меню
    if query.data == "main_menu":
        query.edit_message_text("🏠 Главное меню:", reply_markup=get_main_menu_keyboard(user_id))
        return
    
    # Домашнее задание
    elif query.data == "menu_hw":
        hw = get_homework()
        
        if hw:
            text = f"📚 **Домашнее задание:**\n\n**Предмет:** {hw[0]}\n**Задание:** {hw[1]}"
        else:
            text = "📚 Домашнее задание пока не добавлено."
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        
        # Если есть подписка, показываем кнопку с решенным ДЗ
        if has_subscription(user_id):
            keyboard.insert(0, [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw")])
        
        query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Решенное ДЗ (для подписчиков)
    elif query.data == "menu_solved_hw":
        if not has_subscription(user_id):
            keyboard = [
                [InlineKeyboardButton("⭐ Купить подписку", callback_data="menu_subscription")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ]
            query.edit_message_text(
                "❌ У вас нет подписки!\n\n"
                "Купите подписку за 50 ⭐ или попросите администратора выдать её.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        subject, photo_ids = get_solved_homework()
        if photo_ids:
            query.edit_message_text(f"✅ Решенное домашнее задание\nПредмет: {subject}\n\nЗагружаю фото...")
            
            # Отправляем все фото
            for i, photo_id in enumerate(photo_ids, 1):
                caption = f"✅ Решенное ДЗ - {subject} (фото {i}/{len(photo_ids)})" if len(photo_ids) > 1 else f"✅ Решенное ДЗ - {subject}"
                query.message.reply_photo(
                    photo=photo_id,
                    caption=caption
                )
            
            # Отправляем кнопку возврата
            query.message.reply_text(
                "Выберите действие:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
                ]])
            )
            query.message.delete()
        else:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
            query.edit_message_text(
                "📝 Решенное домашнее задание пока не добавлено.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
            
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    if is_banned(user_id):
        query.edit_message_text("⛔ Вы забанены и не можете использовать бота.")
        return
    
    # Главное меню
    if query.data == "main_menu":
        query.edit_message_text("🏠 Главное меню:", reply_markup=get_main_menu_keyboard(user_id))
        return
    
    # Домашнее задание
    elif query.data == "menu_hw":
        hw = get_homework()
        
        if hw:
            text = f"📚 **Домашнее задание:**\n\n**Предмет:** {hw[0]}\n**Задание:** {hw[1]}"
        else:
            text = "📚 Домашнее задание пока не добавлено."
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        
        # Если есть подписка, показываем кнопку с решенным ДЗ
        if has_subscription(user_id):
            keyboard.insert(0, [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw")])
        
        query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Решенное ДЗ (для подписчиков)
    elif query.data == "menu_solved_hw":
        if not has_subscription(user_id):
            keyboard = [
                [InlineKeyboardButton("⭐ Купить подписку", callback_data="menu_subscription")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ]
            query.edit_message_text(
                "❌ У вас нет подписки!\n\n"
                "Купите подписку за 50 ⭐ или попросите администратора выдать её.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        subject, photo_ids = get_solved_homework()
        if photo_ids:
            query.edit_message_text(f"✅ Решенное домашнее задание\nПредмет: {subject}\n\nЗагружаю фото...")
            
            # Отправляем все фото
            for i, photo_id in enumerate(photo_ids, 1):
                caption = f"✅ Решенное ДЗ - {subject} (фото {i}/{len(photo_ids)})" if len(photo_ids) > 1 else f"✅ Решенное ДЗ - {subject}"
                query.message.reply_photo(
                    photo=photo_id,
                    caption=caption
                )
            
            # Отправляем кнопку возврата
            query.message.reply_text(
                "Выберите действие:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
                ]])
            )
            query.message.delete()
        else:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
            query.edit_message_text(
                "📝 Решенное домашнее задание пока не добавлено.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
    # Отправить фото
    elif query.data == "menu_photo":
        query.edit_message_text(
            "📸 Отправьте мне фото, и оно будет отправлено на модерацию.\n\n"
            "После проверки администратором фото появится в галерее.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]])
        )
        return
    
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
            
            # Используем reply_photo с правильной клавиатурой
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Ещё", callback_data="menu_random"),
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]])
            
            query.message.reply_photo(
                photo=photo_id,
                caption=caption,
                reply_markup=keyboard
            )
            query.message.delete()
        else:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="main_menu")
            ]])
            query.edit_message_text(
                "📸 В галерее пока нет фотографий. Отправь своё фото!",
                reply_markup=keyboard
            )
        return
    
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
            keyboard = [
                [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ]
        else:
            text = (
                f"⭐ **Подписка за {STAR_PRICE} звёзд**\n\n"
                f"Что дает подписка:\n"
                f"✅ Доступ к решенному домашнему заданию\n"
                f"✅ Приоритетная поддержка\n"
                f"✅ +10% к рейтингу за фото\n\n"
                f"Как оплатить:\n"
                f"1. Нажмите кнопку 'Оплатить звёздами'\n"
                f"2. Подтвердите платеж\n"
                f"3. Получите доступ!"
            )
            keyboard = [
                [InlineKeyboardButton(f"⭐ Оплатить {STAR_PRICE} звёзд", callback_data="pay_subscription")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ]
        
        query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
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
        return
    
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
        return
    
    # НОВАЯ ФУНКЦИЯ: Рейтинг пользователя
    elif query.data == "menu_rating":
        rating, photos = get_user_rating(user_id)
        top_users = get_top_users(5)
        
        text = f"📊 **Ваш профиль**\n\n"
        text += f"⭐ Рейтинг: {rating}\n"
        text += f"📸 Одобренных фото: {photos}\n\n"
        
        if top_users:
            text += "🏆 **Топ пользователей:**\n"
            for i, (uid, uname, fname, rate, pcount) in enumerate(top_users, 1):
                name = uname or fname or f"ID{uid}"
                text += f"{i}. {name} — {rate} ⭐\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # НОВАЯ ФУНКЦИЯ: Интересный факт
    elif query.data == "menu_fact":
        fact_info = get_random_fact()
        if fact_info:
            fact, category = fact_info
            text = f"🎯 **Интересный факт**\n\n{fact}\n\n📚 Категория: {category}"
        else:
            text = "🎯 Факты пока не добавлены. Администраторы скоро добавят!"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Ещё факт", callback_data="menu_fact")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Админ-меню
    elif query.data == "admin_menu" and is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("📝 Изменить ДЗ", callback_data="admin_hw")],
            [InlineKeyboardButton("✅ Добавить решенное ДЗ", callback_data="admin_solved_hw")],
            [InlineKeyboardButton("📸 Модерация фото", callback_data="admin_moderate")],
            [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton("❌ Удалить админа", callback_data="admin_remove")],
            [InlineKeyboardButton("🚫 Бан пользователя", callback_data="admin_ban")],
            [InlineKeyboardButton("✅ Разбан пользователя", callback_data="admin_unban")],
            [InlineKeyboardButton("⭐ Выдать подписку", callback_data="admin_subscription")],
            [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("📞 Сообщения в поддержку", callback_data="admin_reports")],
            [InlineKeyboardButton("👁️ Слежка", callback_data="admin_tracking")],
            [InlineKeyboardButton("➕ Добавить факт", callback_data="admin_add_fact")],
            [InlineKeyboardButton("📊 Управление рейтингом", callback_data="admin_rating")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
        ]
        query.edit_message_text("👑 **Админ-панель**", parse_mode="Markdown", 
                              reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    # Модерация фото
    elif query.data == "admin_moderate" and is_admin(user_id):
        pending = get_pending_photos()
        if not pending:
            query.edit_message_text(
                "📸 Нет фото на модерации.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                ]])
            )
            return
        
        # Сохраняем список фото в контексте
        context.user_data['pending_photos'] = pending
        context.user_data['pending_index'] = 0
        show_pending_photo(query, context, 0)
        return
    
    # Одобрить фото
    elif query.data.startswith("approve_photo_"):
        photo_id = int(query.data.split("_")[2])
        approve_photo(photo_id, user_id)
        
        # Добавляем рейтинг пользователю
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM photos WHERE id=?", (photo_id,))
        photo_user = c.fetchone()
        conn.close()
        
        if photo_user:
            add_user_rating(photo_user[0], 10)  # +10 рейтинга за одобренное фото
        
        # Показываем следующее фото
        if 'pending_photos' in context.user_data:
            pending = context.user_data['pending_photos']
            index = context.user_data.get('pending_index', 0) + 1
            if index < len(pending):
                show_pending_photo(query, context, index)
            else:
                query.edit_message_text(
                    "✅ Все фото обработаны!",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                    ]])
                )
                context.user_data.pop('pending_photos', None)
                context.user_data.pop('pending_index', None)
        return
    
    # Отклонить фото
    elif query.data.startswith("reject_photo_"):
        photo_id = int(query.data.split("_")[2])
        reject_photo(photo_id, user_id)
        
        # Показываем следующее фото
        if 'pending_photos' in context.user_data:
            pending = context.user_data['pending_photos']
            index = context.user_data.get('pending_index', 0) + 1
            if index < len(pending):
                show_pending_photo(query, context, index)
            else:
                query.edit_message_text(
                    "✅ Все фото обработаны!",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                    ]])
                )
                context.user_data.pop('pending_photos', None)
                context.user_data.pop('pending_index', None)
        return
    
    # Добавить факт
    elif query.data == "admin_add_fact" and is_admin(user_id):
        query.edit_message_text(
            "📝 Введите факт в формате:\n"
            "`Категория: Факт`\n\n"
            "Пример: `Наука: Вода кипит при 100°C`\n"
            "Или: `История: Первый компьютер весил 30 тонн`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
            ]])
        )
        context.user_data['admin_action'] = 'add_fact'
        return
    
    # Управление рейтингом
    elif query.data == "admin_rating" and is_admin(user_id):
        query.edit_message_text(
            "📊 Введите ID пользователя и количество баллов рейтинга:\n\n"
            "Формат: `ID баллы`\n"
            "Пример: `123456789 50`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
            ]])
        )
        context.user_data['admin_action'] = 'add_rating'
        return
    
    # Слежка
    elif query.data == "admin_tracking" and is_admin(user_id):
        enabled = is_tracking_enabled()
        status = "✅ ВКЛЮЧЕНА" if enabled else "❌ ВЫКЛЮЧЕНА"
        keyboard = [
            [InlineKeyboardButton("✅ Включить" if not enabled else "❌ Выключить", callback_data="toggle_tracking")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")],
        ]
        query.edit_message_text(
            f"👁️ **Настройка слежки**\n\n"
            f"Текущий статус: {status}\n\n"
            f"Когда слежка включена, администраторы видят, кто отправил фото.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
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
        return
    
    # Статистика
    elif query.data == "admin_stats" and is_admin(user_id):
        def _get_stats():
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            c.execute("SELECT COUNT(*) FROM photos WHERE status='approved'")
            photos = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM photos WHERE status='pending'")
            pending = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')")
            subs = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM reports WHERE status='new'")
            reports = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM admins")
            admins = c.fetchone()[0] + len(ADMIN_IDS)
            
            c.execute("SELECT COUNT(*) FROM daily_facts")
            facts = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM polls WHERE is_active=1")
            polls = c.fetchone()[0]
            
            conn.close()
            
            return (photos, pending, users, subs, reports, admins, facts, polls)
        
        photos, pending, users, subs, reports, admins, facts, polls = _get_stats()
        
        text = (
            f"📊 **Статистика бота:**\n\n"
            f"👥 Всего пользователей: {users}\n"
            f"⭐ Подписчиков: {subs}\n"
            f"📸 Фото в галерее: {photos}\n"
            f"⏳ На модерации: {pending}\n"
            f"👑 Администраторов: {admins}\n"
            f"📞 Новых сообщений: {reports}\n"
            f"🎯 Интересных фактов: {facts}\n"
            f"📊 Активных опросов: {polls}"
        )
        
        query.edit_message_text(text, parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup([[
                                  InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                              ]]))
        return
    
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
        return
    
    # Рассылка
    elif query.data == "admin_broadcast" and is_admin(user_id):
        query.edit_message_text(
            "📢 Введите сообщение для рассылки всем пользователям.\n\n"
            "Поддерживается обычный текст, эмодзи и Markdown разметка.\n\n"
            "Пример: *Важное объявление* для всех!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
            ]])
        )
        context.user_data['admin_action'] = 'broadcast'
        return
    
    # Разделы админ-панели, требующие ввода
    elif query.data in ["admin_hw", "admin_solved_hw", "admin_add", "admin_remove", 
                       "admin_ban", "admin_unban", "admin_subscription"] and is_admin(user_id):
        
        if query.data == "admin_hw":
            query.edit_message_text(
     
    
    # Подписка
elif query.data == "menu_subscription":
        # ... остальной код ...
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
        keyboard = [
            [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
    else:
        text = (
            f"⭐ **Подписка за {STAR_PRICE} звёзд**\n\n"
            f"Что дает подписка:\n"
            f"✅ Доступ к решенному домашнему заданию\n"
            f"✅ Приоритетная поддержка\n"
            f"✅ +10% к рейтингу за фото\n\n"
            f"Как оплатить:\n"
            f"1. Нажмите кнопку 'Оплатить звёздами'\n"
            f"2. Подтвердите платеж\n"
            f"3. Получите доступ!"
        )
        keyboard = [
            [InlineKeyboardButton(f"⭐ Оплатить {STAR_PRICE} звёзд", callback_data="pay_subscription")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
    
    query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return

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
    return

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
    return

# НОВАЯ ФУНКЦИЯ: Рейтинг пользователя
elif query.data == "menu_rating":
    rating, photos = get_user_rating(user_id)
    top_users = get_top_users(5)
    
    text = f"📊 **Ваш профиль**\n\n"
    text += f"⭐ Рейтинг: {rating}\n"
    text += f"📸 Одобренных фото: {photos}\n\n"
    
    if top_users:
        text += "🏆 **Топ пользователей:**\n"
        for i, (uid, uname, fname, rate, pcount) in enumerate(top_users, 1):
            name = uname or fname or f"ID{uid}"
            text += f"{i}. {name} — {rate} ⭐\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
    query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return

# НОВАЯ ФУНКЦИЯ: Интересный факт
elif query.data == "menu_fact":
    fact_info = get_random_fact()
    if fact_info:
        fact, category = fact_info
        text = f"🎯 **Интересный факт**\n\n{fact}\n\n📚 Категория: {category}"
    else:
        text = "🎯 Факты пока не добавлены. Администраторы скоро добавят!"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Ещё факт", callback_data="menu_fact")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return

# Админ-меню
elif query.data == "admin_menu" and is_admin(user_id):
    keyboard = [
        [InlineKeyboardButton("📝 Изменить ДЗ", callback_data="admin_hw")],
        [InlineKeyboardButton("✅ Добавить решенное ДЗ", callback_data="admin_solved_hw")],
        [InlineKeyboardButton("📸 Модерация фото", callback_data="admin_moderate")],
        [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
        [InlineKeyboardButton("❌ Удалить админа", callback_data="admin_remove")],
        [InlineKeyboardButton("🚫 Бан пользователя", callback_data="admin_ban")],
        [InlineKeyboardButton("✅ Разбан пользователя", callback_data="admin_unban")],
        [InlineKeyboardButton("⭐ Выдать подписку", callback_data="admin_subscription")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📞 Сообщения в поддержку", callback_data="admin_reports")],
        [InlineKeyboardButton("👁️ Слежка", callback_data="admin_tracking")],
        [InlineKeyboardButton("➕ Добавить факт", callback_data="admin_add_fact")],
        [InlineKeyboardButton("📊 Управление рейтингом", callback_data="admin_rating")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
    ]
    query.edit_message_text("👑 **Админ-панель**", parse_mode="Markdown", 
                          reply_markup=InlineKeyboardMarkup(keyboard))
    return

# Модерация фото
elif query.data == "admin_moderate" and is_admin(user_id):
    pending = get_pending_photos()
    if not pending:
        query.edit_message_text(
            "📸 Нет фото на модерации.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
            ]])
        )
        return
    
    # Сохраняем список фото в контексте
    context.user_data['pending_photos'] = pending
    context.user_data['pending_index'] = 0
    show_pending_photo(query, context, 0)
    return

# Одобрить фото
elif query.data.startswith("approve_photo_"):
    photo_id = int(query.data.split("_")[2])
    approve_photo(photo_id, user_id)
    
    # Добавляем рейтинг пользователю
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM photos WHERE id=?", (photo_id,))
    photo_user = c.fetchone()
    conn.close()
    
    if photo_user:
        add_user_rating(photo_user[0], 10)  # +10 рейтинга за одобренное фото
    
    # Показываем следующее фото
    if 'pending_photos' in context.user_data:
        pending = context.user_data['pending_photos']
        index = context.user_data.get('pending_index', 0) + 1
        if index < len(pending):
            show_pending_photo(query, context, index)
        else:
            query.edit_message_text(
                "✅ Все фото обработаны!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                ]])
            )
            context.user_data.pop('pending_photos', None)
            context.user_data.pop('pending_index', None)
    return

# Отклонить фото
elif query.data.startswith("reject_photo_"):
    photo_id = int(query.data.split("_")[2])
    reject_photo(photo_id, user_id)
    
    # Показываем следующее фото
    if 'pending_photos' in context.user_data:
        pending = context.user_data['pending_photos']
        index = context.user_data.get('pending_index', 0) + 1
        if index < len(pending):
            show_pending_photo(query, context, index)
        else:
            query.edit_message_text(
                "✅ Все фото обработаны!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                ]])
            )
            context.user_data.pop('pending_photos', None)
            context.user_data.pop('pending_index', None)
    return

# Добавить факт
elif query.data == "admin_add_fact" and is_admin(user_id):
    query.edit_message_text(
        "📝 Введите факт в формате:\n"
        "`Категория: Факт`\n\n"
        "Пример: `Наука: Вода кипит при 100°C`\n"
        "Или: `История: Первый компьютер весил 30 тонн`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
        ]])
    )
    context.user_data['admin_action'] = 'add_fact'
    return

# Управление рейтингом
elif query.data == "admin_rating" and is_admin(user_id):
    query.edit_message_text(
        "📊 Введите ID пользователя и количество баллов рейтинга:\n\n"
        "Формат: `ID баллы`\n"
        "Пример: `123456789 50`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
        ]])
    )
    context.user_data['admin_action'] = 'add_rating'
    return

# Слежка
elif query.data == "admin_tracking" and is_admin(user_id):
    enabled = is_tracking_enabled()
    status = "✅ ВКЛЮЧЕНА" if enabled else "❌ ВЫКЛЮЧЕНА"
    keyboard = [
        [InlineKeyboardButton("✅ Включить" if not enabled else "❌ Выключить", callback_data="toggle_tracking")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")],
    ]
    query.edit_message_text(
        f"👁️ **Настройка слежки**\n\n"
        f"Текущий статус: {status}\n\n"
        f"Когда слежка включена, администраторы видят, кто отправил фото.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return

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
    return

# Статистика
elif query.data == "admin_stats" and is_admin(user_id):
    def _get_stats():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM photos WHERE status='approved'")
        photos = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM photos WHERE status='pending'")
        pending = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')")
        subs = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM reports WHERE status='new'")
        reports = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM admins")
        admins = c.fetchone()[0] + len(ADMIN_IDS)
        
        c.execute("SELECT COUNT(*) FROM daily_facts")
        facts = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM polls WHERE is_active=1")
        polls = c.fetchone()[0]
        
        conn.close()
        
        return (photos, pending, users, subs, reports, admins, facts, polls)
    
    photos, pending, users, subs, reports, admins, facts, polls = _get_stats()
    
    text = (
        f"📊 **Статистика бота:**\n\n"
        f"👥 Всего пользователей: {users}\n"
        f"⭐ Подписчиков: {subs}\n"
        f"📸 Фото в галерее: {photos}\n"
        f"⏳ На модерации: {pending}\n"
        f"👑 Администраторов: {admins}\n"
        f"📞 Новых сообщений: {reports}\n"
        f"🎯 Интересных фактов: {facts}\n"
        f"📊 Активных опросов: {polls}"
    )
    
    query.edit_message_text(text, parse_mode="Markdown",
                          reply_markup=InlineKeyboardMarkup([[
                              InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                          ]]))
    return
    
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
        return
    
    # Рассылка
    elif query.data == "admin_broadcast" and is_admin(user_id):
        query.edit_message_text(
            "📢 Введите сообщение для рассылки всем пользователям.\n\n"
            "Поддерживается обычный текст, эмодзи и Markdown разметка.\n\n"
            "Пример: *Важное объявление* для всех!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
            ]])
        )
        context.user_data['admin_action'] = 'broadcast'
        return
    
    # Разделы админ-панели, требующие ввода
    if query.data in ["admin_hw", "admin_solved_hw", "admin_add", "admin_remove", 
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
                "✅ Отправьте **несколько фото** решенного домашнего задания.\n\n"
                "После отправки всех фото нажмите кнопку 'Готово', чтобы указать предмет.\n\n"
                "📸 Отправляйте фото по одному.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Готово (закончить)", callback_data="solved_hw_done")],
                    [InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")]
                ])
            )
            context.user_data['admin_action'] = 'solved_hw_waiting_photos'
            context.user_data['solved_hw_photos'] = []
        
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
    
    # Завершение добавления фото для решенного ДЗ
    elif query.data == "solved_hw_done" and is_admin(user_id):
        if context.user_data.get('solved_hw_photos'):
            query.edit_message_text(
                "📝 Напишите название предмета для этих фото:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = 'solved_hw_waiting_subject'
        else:
            query.edit_message_text(
                "❌ Вы не отправили ни одного фото.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="admin_solved_hw")
                ]])
            )

def show_pending_photo(query, context, index):
    """Показать фото на модерации"""
    pending = context.user_data['pending_photos']
    if index >= len(pending):
        return
    
    photo_id, file_id, user_id, username, date = pending[index]
    context.user_data['pending_index'] = index
    
    caption = f"📸 Фото {index+1}/{len(pending)}\n"
    caption += f"От: @{username or 'Неизвестно'} (ID: {user_id})\n"
    caption += f"Дата: {date}"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_photo_{photo_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_photo_{photo_id}")
        ],
        [InlineKeyboardButton("🔙 В админ-панель", callback_data="admin_menu")]
    ])
    
    query.message.reply_photo(
        photo=file_id,
        caption=caption,
        reply_markup=keyboard
    )
    query.message.delete()

# ================== ОБРАБОТЧИКИ СООБЩЕНИЙ ==================
@not_banned
def handle_photo(update: Update, context: CallbackContext):
    user = update.effective_user
    photo = update.message.photo[-1]
    
    # Проверяем, не ждем ли мы фото для решенного ДЗ
    if context.user_data.get('admin_action') == 'solved_hw_waiting_photos' and is_admin(user.id):
        # Добавляем фото в список
        if 'solved_hw_photos' not in context.user_data:
            context.user_data['solved_hw_photos'] = []
        
        context.user_data['solved_hw_photos'].append(photo.file_id)
        
        count = len(context.user_data['solved_hw_photos'])
        update.message.reply_text(
            f"✅ Фото {count} добавлено для решенного ДЗ!\n"
            f"Отправьте еще фото или нажмите кнопку 'Готово'.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Готово (закончить)", callback_data="solved_hw_done")],
                [InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")]
            ])
        )
        return
    
    # Обычное добавление фото (на модерацию)
    photo_id = add_photo_pending(photo.file_id, user.id, user.username or user.first_name)
    
    # Уведомляем админов о новом фото на модерацию
    if is_tracking_enabled():
        for admin_id in ADMIN_IDS:
            try:
                context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📸 Новое фото на модерацию от @{user.username or user.first_name} (ID: {user.id})\n"
                         f"ID фото: {photo_id}"
                )
            except:
                pass
    
    update.message.reply_text(
        f"✅ Фото отправлено на модерацию!\n"
        f"Оно появится в галерее после проверки администратором.",
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
            if context.user_data.get('solved_hw_photos'):
                add_solved_homework(text.strip(), context.user_data['solved_hw_photos'])
                update.message.reply_text(
                    "✅ Решенное домашнее задание добавлено! Оно будет доступно подписчикам в течение 24 часов.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                context.user_data['admin_action'] = None
                context.user_data.pop('solved_hw_photos', None)
            else:
                update.message.reply_text("❌ Ошибка: фото не найдены")
        
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
                    update.message.reply_text(
                        f"✅ Пользователь {user_id} забанен на {hours} часов",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                        ]])
                    )
                else:
                    ban_user(user_id)
                    update.message.reply_text(
                        f"✅ Пользователь {user_id} забанен навсегда",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                        ]])
                    )
                
                context.user_data['admin_action'] = None
            except Exception as e:
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
            except Exception as e:
                update.message.reply_text("❌ Неверный формат. Используйте: `ID дни`")
        
        elif action == 'broadcast':
            # Сохраняем сообщение для рассылки
            context.user_data['broadcast_message'] = text
            users = get_all_users()
            
            update.message.reply_text(
                f"📢 Начинаю рассылку {len(users)} пользователям...\n"
                f"Это может занять некоторое время.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ]])
            )
            
            # Отправляем сообщение всем пользователям
            success = 0
            failed = 0
            
            for user_id in users:
                try:
                    context.bot.send_message(
                        chat_id=user_id,
                        text=f"📢 **Сообщение от администрации:**\n\n{text}",
                        parse_mode="Markdown"
                    )
                    success += 1
                except:
                    failed += 1
                
                # Небольшая задержка, чтобы не превысить лимиты Telegram
                time.sleep(0.05)
            
            save_broadcast(user.id, text)
            
            update.message.reply_text(
                f"✅ Рассылка завершена!\n"
                f"📨 Успешно: {success}\n"
                f"❌ Не удалось: {failed}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ]])
            )
            
            context.user_data['admin_action'] = None
        
        elif action == 'add_fact':
            if ':' in text:
                category, fact = text.split(':', 1)
                add_daily_fact(fact.strip(), category.strip(), user.id)
                fact_count = get_facts_count()
                update.message.reply_text(
                    f"✅ Факт добавлен! Всего фактов: {fact_count}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                context.user_data['admin_action'] = None
            else:
                update.message.reply_text("❌ Неверный формат. Используйте: `Категория: Факт`")
        
        elif action == 'add_rating':
            parts = text.strip().split()
            try:
                user_id = int(parts[0])
                points = int(parts[1])
                add_user_rating(user_id, points)
                update.message.reply_text(
                    f"✅ Пользователю {user_id} добавлено {points} баллов рейтинга",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                    ]])
                )
                context.user_data['admin_action'] = None
            except:
                update.message.reply_text("❌ Неверный формат. Используйте: `ID баллы`")

# ================== ОБРАБОТЧИК ЗВЁЗД ==================
def handle_stars(update: Update, context: CallbackContext):
    """Обработчик оплаты звёздами"""
    user = update.effective_user
    
    if update.message.successful_payment:
        # Подтверждение оплаты
        give_subscription(user.id, 30)  # 30 дней подписки
        add_user_rating(user.id, 100)  # +100 рейтинга за покупку
        update.message.reply_text(
            "⭐ Спасибо за покупку! Подписка активирована на 30 дней.\n"
            "Вам начислено 100 баллов рейтинга!\n"
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
    
    # Запускаем автоочистку при старте
    add_background_task(cleanup_old_data)
    
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
    print(f"📸 Фото удаляются через {PHOTO_EXPIRE_DAYS} дней")
    print(f"⚡ Кэш включен, TTL: {CACHE_TTL} сек")
    
    # Запускаем бота
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
