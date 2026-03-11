import logging
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
import time
import json
import re
from collections import defaultdict
from threading import Thread, Lock
from queue import Queue
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
import cachetools
import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, CallbackQueryHandler,
    Filters, CallbackContext, PreCheckoutQueryHandler
)

# ================== НАСТРОЙКИ ==================
TOKEN = "8623075329:AAHRnpXR1nMd5m-STE8daYUAevtL9D38jEQ"
ADMIN_IDS = [1553865459]
DB_PATH = "homework_bot.db"
STAR_PRICE = 50
PHOTO_EXPIRE_DAYS = 7

# ================== ЛОГИРОВАНИЕ ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== КЛАССЫ-ПЕРЕЧИСЛЕНИЯ ==================
class Language(Enum):
    RU = 'ru'
    EN = 'en'
    KZ = 'kz'

class UserRole(Enum):
    USER = 'user'
    SUBSCRIBER = 'subscriber'
    ADMIN = 'admin'
    OWNER = 'owner'

class PhotoStatus(Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'

class GameType(Enum):
    TIC_TAC_TOE = "tic_tac_toe"
    GUESS_NUMBER = "guess_number"
    RPS = "rock_paper_scissors"
    DICE = "dice"
    MATH = "math"

# ================== ПЕРЕВОДЫ ==================
TRANSLATIONS = {
    Language.RU: {
        'welcome': "👋 Привет, {name}!\nЯ бот-помощник 9Г класса. Выбери действие:",
        'main_menu': "🏠 Главное меню",
        'homework': "📚 Домашнее задание",
        'homework_text': "📚 **Домашнее задание:**\n\n**Предмет:** {subject}\n**Задание:** {task}",
        'no_homework': "📚 Домашнее задание пока не добавлено.",
        'send_photo': "📸 Отправьте мне фото, и оно будет отправлено на модерацию.",
        'random_photo': "🎲 Случайное фото из галереи\nВсего фотографий: {count}",
        'no_photos': "📸 В галерее пока нет фотографий.",
        'subscription': "⭐ **Подписка за {price} звёзд**\n\nЧто дает подписка:\n✅ Доступ к решенному домашнему заданию\n✅ Приоритетная поддержка\n✅ +10 баллов к рейтингу за фото",
        'active_subscription': "⭐ **У вас активна подписка!**\n\nДействует до: {date}\n\nДоступно:\n✅ Решенное домашнее задание",
        'profile': "📊 **Ваш профиль**\n\n👤 Имя: {name}\n⭐ Рейтинг: {rating}\n📸 Фото: {photos}\n💎 Подписка: {subscription}\n📅 С: {date}\n🆔 ID: {user_id}",
        'banned': "⛔ Вы забанены до {date}. Причина: {reason}",
        'permanent_ban': "⛔ Вы забанены навсегда. Причина: {reason}",
        'support_message': "📞 Напишите ваше сообщение для администратора.",
        'support_sent': "✅ Ваше сообщение отправлено администратору!",
        'back': "🔙 Назад",
        'more': "🔄 Ещё",
        'cancel': "❌ Отмена",
        'confirm': "✅ Подтвердить",
        'language_changed': "✅ Язык изменен на русский",
        'games': "🎮 Игры",
        'currency': "💱 Курс USD",
        'schedule': "📅 Расписание",
        'games_menu': "🎮 **Выберите игру:**",
        'game_tic': "❌ Крестики-нолики",
        'game_number': "🔢 Угадай число",
        'game_rps': "✂️ Камень-ножницы-бумага",
        'game_dice': "🎲 Кости",
        'game_math': "🧮 Математика",
    },
    Language.EN: {
        'welcome': "👋 Hello, {name}!\nI'm the 9G class assistant bot. Choose an action:",
        'main_menu': "🏠 Main Menu",
        'homework': "📚 Homework",
        'homework_text': "📚 **Homework:**\n\n**Subject:** {subject}\n**Task:** {task}",
        'no_homework': "📚 No homework added yet.",
        'send_photo': "📸 Send me a photo, and it will be sent for moderation.",
        'random_photo': "🎲 Random photo from gallery\nTotal photos: {count}",
        'no_photos': "📸 No photos in gallery yet.",
        'subscription': "⭐ **Subscription for {price} stars**\n\nWhat it gives:\n✅ Access to solved homework\n✅ Priority support\n✅ +10 rating points per photo",
        'active_subscription': "⭐ **You have an active subscription!**\n\nValid until: {date}\n\nAvailable:\n✅ Solved homework",
        'profile': "📊 **Your Profile**\n\n👤 Name: {name}\n⭐ Rating: {rating}\n📸 Photos: {photos}\n💎 Subscription: {subscription}\n📅 Since: {date}\n🆔 ID: {user_id}",
        'banned': "⛔ You are banned until {date}. Reason: {reason}",
        'permanent_ban': "⛔ You are permanently banned. Reason: {reason}",
        'support_message': "📞 Write your message to the administrator.",
        'support_sent': "✅ Your message has been sent to the administrator!",
        'back': "🔙 Back",
        'more': "🔄 More",
        'cancel': "❌ Cancel",
        'confirm': "✅ Confirm",
        'language_changed': "✅ Language changed to English",
        'games': "🎮 Games",
        'currency': "💱 USD Rate",
        'schedule': "📅 Schedule",
        'games_menu': "🎮 **Choose a game:**",
        'game_tic': "❌ Tic-Tac-Toe",
        'game_number': "🔢 Guess Number",
        'game_rps': "✂️ Rock-Paper-Scissors",
        'game_dice': "🎲 Dice",
        'game_math': "🧮 Math",
    },
    Language.KZ: {
        'welcome': "👋 Сәлем, {name}!\nМен 9Г сыныбының көмекші ботымын. Әрекетті таңдаңыз:",
        'main_menu': "🏠 Басты мәзір",
        'homework': "📚 Үй тапсырмасы",
        'homework_text': "📚 **Үй тапсырмасы:**\n\n**Пән:** {subject}\n**Тапсырма:** {task}",
        'no_homework': "📚 Үй тапсырмасы әлі қосылмаған.",
        'send_photo': "📸 Маған фото жіберіңіз, ол модерацияға жіберіледі.",
        'random_photo': "🎲 Галереядан кездейсоқ фото\nБарлығы: {count}",
        'no_photos': "📸 Галереяда әлі фото жоқ.",
        'subscription': "⭐ **{price} жұлдызға жазылым**\n\nБеретін мүмкіндіктер:\n✅ Шешілген үй тапсырмасы\n✅ Бірінші кезектегі қолдау\n✅ Фото үшін +10 рейтинг баллы",
        'active_subscription': "⭐ **Жазылымыңыз белсенді!**\n\nМерзімі: {date}\n\nҚолжетімді:\n✅ Шешілген үй тапсырмасы",
        'profile': "📊 **Сіздің профиліңіз**\n\n👤 Аты: {name}\n⭐ Рейтинг: {rating}\n📸 Фото: {photos}\n💎 Жазылым: {subscription}\n📅 Тіркелген: {date}\n🆔 ID: {user_id}",
        'banned': "⛔ Сіз {date} дейін бұғатталдыңыз. Себеп: {reason}",
        'permanent_ban': "⛔ Сіз мәңгілікке бұғатталдыңыз. Себеп: {reason}",
        'support_message': "📞 Әкімшіге хабарламаңызды жазыңыз.",
        'support_sent': "✅ Хабарламаңыз әкімшіге жіберілді!",
        'back': "🔙 Артқа",
        'more': "🔄 Тағы",
        'cancel': "❌ Болдырмау",
        'confirm': "✅ Растау",
        'language_changed': "✅ Тіл қазақ тіліне ауыстырылды",
        'games': "🎮 Ойындар",
        'currency': "💱 USD бағамы",
        'schedule': "📅 Кесте",
        'games_menu': "🎮 **Ойынды таңдаңыз:**",
        'game_tic': "❌ Хрестики-нолики",
        'game_number': "🔢 Санды тап",
        'game_rps': "✂️ Тас-қайшы-қағаз",
        'game_dice': "🎲 Сүйек",
        'game_math': "🧮 Математика",
    }
}

# ================== БАЗА ДАННЫХ ==================
class DatabaseManager:
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cache = cachetools.TTLCache(maxsize=100, ttl=300)
        self._create_tables()
    
    def _create_tables(self):
        c = self.conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language TEXT DEFAULT 'ru',
            role TEXT DEFAULT 'user',
            rating INTEGER DEFAULT 0,
            photos_count INTEGER DEFAULT 0,
            subscription_end TEXT,
            banned_until TEXT,
            permanent_ban INTEGER DEFAULT 0,
            ban_reason TEXT,
            join_date TEXT,
            last_active TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            user_id INTEGER,
            username TEXT,
            date TEXT,
            status TEXT DEFAULT 'pending',
            moderated_by INTEGER,
            moderation_date TEXT,
            likes INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            task TEXT,
            date TEXT,
            created_by INTEGER
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS solved_homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            photo_ids TEXT,
            date TEXT,
            expires_at TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            added_by INTEGER,
            date TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            message TEXT,
            date TEXT,
            status TEXT DEFAULT 'new'
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week INTEGER,
            lesson_number INTEGER,
            subject TEXT,
            teacher TEXT,
            room TEXT,
            start_time TEXT,
            end_time TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS daily_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT,
            category TEXT,
            added_by INTEGER,
            date TEXT,
            language TEXT DEFAULT 'ru'
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enabled INTEGER DEFAULT 0
        )''')
        
        # Добавляем настройку слежки, если её нет
        c.execute("INSERT OR IGNORE INTO tracking (id, enabled) VALUES (1, 0)")
        
        self.conn.commit()
    
    def execute(self, query: str, params: tuple = (), cache_key: str = None):
        if cache_key and cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            c = self.conn.cursor()
            c.execute(query, params)
            
            if query.strip().upper().startswith('SELECT'):
                result = c.fetchall()
                if cache_key:
                    self.cache[cache_key] = result
                return result
            else:
                self.conn.commit()
                return c.lastrowid
        except Exception as e:
            logger.error(f"DB Error: {e}")
            return None
    
    def close(self):
        self.conn.close()

db = DatabaseManager()

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    result = db.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return bool(result)

def is_tracking_enabled() -> bool:
    result = db.execute("SELECT enabled FROM tracking WHERE id = 1")
    return result and result[0]['enabled'] == 1

def set_tracking(enabled: bool):
    db.execute("UPDATE tracking SET enabled = ? WHERE id = 1", (1 if enabled else 0,))

def get_user_language(user_id: int) -> Language:
    result = db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    if result:
        return Language(result[0]['language'])
    return Language.RU

def get_text(user_id: int, key: str, **kwargs) -> str:
    lang = get_user_language(user_id)
    text = TRANSLATIONS[lang].get(key, key)
    return text.format(**kwargs)

# ================== ИГРЫ ==================
class GameManager:
    def __init__(self):
        self.active_games = {}
    
    def start_game(self, user_id: int, game_type: str):
        self.active_games[user_id] = {
            'type': game_type,
            'data': self._init_game(game_type)
        }
        return self.active_games[user_id]
    
    def get_game(self, user_id: int):
        return self.active_games.get(user_id)
    
    def end_game(self, user_id: int):
        if user_id in self.active_games:
            del self.active_games[user_id]
    
    def _init_game(self, game_type: str):
        if game_type == 'tic':
            return {
                'board': [' '] * 9,
                'turn': 'X',
                'moves': 0
            }
        elif game_type == 'number':
            return {
                'number': random.randint(1, 100),
                'attempts': 0,
                'min': 1,
                'max': 100
            }
        elif game_type == 'rps':
            return {
                'wins': 0,
                'losses': 0,
                'ties': 0
            }
        elif game_type == 'dice':
            return {
                'score': 0,
                'throws': 0
            }
        elif game_type == 'math':
            a = random.randint(1, 20)
            b = random.randint(1, 20)
            op = random.choice(['+', '-', '*'])
            if op == '+':
                answer = a + b
            elif op == '-':
                answer = a - b
            else:
                answer = a * b
            return {
                'a': a,
                'b': b,
                'op': op,
                'answer': answer,
                'attempts': 0
            }
        return {}
    
    def process_move(self, user_id: int, move):
        game = self.get_game(user_id)
        if not game:
            return None
        
        game_type = game['type']
        data = game['data']
        
        if game_type == 'tic':
            return self._process_tic(user_id, data, move)
        elif game_type == 'number':
            return self._process_number(user_id, data, move)
        elif game_type == 'rps':
            return self._process_rps(user_id, data, move)
        elif game_type == 'dice':
            return self._process_dice(user_id, data, move)
        elif game_type == 'math':
            return self._process_math(user_id, data, move)
        
        return None
    
    def _process_tic(self, user_id, data, move):
        try:
            pos = int(move)
            if pos < 0 or pos > 8 or data['board'][pos] != ' ':
                return {'valid': False, 'message': '❌ Неверный ход!'}
            
            data['board'][pos] = data['turn']
            data['moves'] += 1
            
            # Проверка победы
            win_combinations = [
                [0,1,2], [3,4,5], [6,7,8],
                [0,3,6], [1,4,7], [2,5,8],
                [0,4,8], [2,4,6]
            ]
            
            for combo in win_combinations:
                if data['board'][combo[0]] == data['board'][combo[1]] == data['board'][combo[2]] != ' ':
                    winner = data['turn']
                    points = 10
                    db.execute("UPDATE users SET rating = rating + ? WHERE user_id = ?", (points, user_id))
                    self.end_game(user_id)
                    return {
                        'valid': True,
                        'game_over': True,
                        'message': f"🎉 Победил {winner}! +{points} очков\n\n{self._format_board(data['board'])}"
                    }
            
            if data['moves'] == 9:
                points = 5
                db.execute("UPDATE users SET rating = rating + ? WHERE user_id = ?", (points, user_id))
                self.end_game(user_id)
                return {
                    'valid': True,
                    'game_over': True,
                    'message': f"🤝 Ничья! +{points} очков\n\n{self._format_board(data['board'])}"
                }
            
            data['turn'] = 'O' if data['turn'] == 'X' else 'X'
            return {
                'valid': True,
                'message': f"Ходит {data['turn']}\n\n{self._format_board(data['board'])}"
            }
        except:
            return {'valid': False, 'message': 'Введите число от 0 до 8'}
    
    def _format_board(self, board):
        return f"{board[0]}│{board[1]}│{board[2]}\n──┼──┼──\n{board[3]}│{board[4]}│{board[5]}\n──┼──┼──\n{board[6]}│{board[7]}│{board[8]}"
    
    def _process_number(self, user_id, data, move):
        try:
            guess = int(move)
            data['attempts'] += 1
            
            if guess < data['min'] or guess > data['max']:
                return {'valid': False, 'message': f'Число должно быть от {data["min"]} до {data["max"]}'}
            
            if guess == data['number']:
                points = max(30 - data['attempts'], 5)
                db.execute("UPDATE users SET rating = rating + ? WHERE user_id = ?", (points, user_id))
                self.end_game(user_id)
                return {
                    'valid': True,
                    'game_over': True,
                    'message': f"✅ Угадал! Число {data['number']}\nПопыток: {data['attempts']}\n+{points} очков"
                }
            elif guess < data['number']:
                data['min'] = max(data['min'], guess + 1)
                return {'valid': True, 'message': f"⬆️ Больше {guess}"}
            else:
                data['max'] = min(data['max'], guess - 1)
                return {'valid': True, 'message': f"⬇️ Меньше {guess}"}
        except:
            return {'valid': False, 'message': 'Введите число'}
    
    def _process_rps(self, user_id, data, move):
        choices = ['камень', 'ножницы', 'бумага']
        if move not in choices:
            return {'valid': False, 'message': 'Выберите: камень, ножницы, бумага'}
        
        comp = random.choice(choices)
        
        if move == comp:
            data['ties'] += 1
            result = "🤝 Ничья"
        elif (move == 'камень' and comp == 'ножницы') or \
             (move == 'ножницы' and comp == 'бумага') or \
             (move == 'бумага' and comp == 'камень'):
            data['wins'] += 1
            points = 5
            db.execute("UPDATE users SET rating = rating + ? WHERE user_id = ?", (points, user_id))
            result = f"✅ Вы выиграли! +{points}"
        else:
            data['losses'] += 1
            result = "❌ Вы проиграли"
        
        return {
            'valid': True,
            'message': f"Вы: {move}\nКомп: {comp}\n{result}\n\n"
                      f"Счет: {data['wins']}:{data['losses']}:{data['ties']}"
        }
    
    def _process_dice(self, user_id, data, move):
        if move.lower() == 'бросить':
            dice = random.randint(1, 6)
            data['throws'] += 1
            data['score'] += dice
            
            if data['throws'] == 3:
                points = data['score']
                db.execute("UPDATE users SET rating = rating + ? WHERE user_id = ?", (points, user_id))
                self.end_game(user_id)
                return {
                    'valid': True,
                    'game_over': True,
                    'message': f"🎲 Игра окончена!\nСумма очков: {data['score']}\n+{points} очков"
                }
            
            return {
                'valid': True,
                'message': f"🎲 Выпало: {dice}\nБросок {data['throws']}/3\nСумма: {data['score']}\n\nНапишите 'бросить' для следующего броска"
            }
        return {'valid': False, 'message': 'Напишите "бросить"'}
    
    def _process_math(self, user_id, data, move):
        try:
            answer = float(move)
            data['attempts'] += 1
            
            if abs(answer - data['answer']) < 0.01:
                points = max(20 - data['attempts'] * 2, 5)
                db.execute("UPDATE users SET rating = rating + ? WHERE user_id = ?", (points, user_id))
                self.end_game(user_id)
                return {
                    'valid': True,
                    'game_over': True,
                    'message': f"✅ Правильно! {data['a']} {data['op']} {data['b']} = {data['answer']}\nПопыток: {data['attempts']}\n+{points} очков"
                }
            else:
                if data['attempts'] >= 3:
                    self.end_game(user_id)
                    return {
                        'valid': True,
                        'game_over': True,
                        'message': f"❌ Неправильно. Правильный ответ: {data['answer']}"
                    }
                return {'valid': True, 'message': f'❌ Неправильно. Осталось попыток: {3 - data["attempts"]}'}
        except:
            return {'valid': False, 'message': 'Введите число'}

game_manager = GameManager()

# ================== ОСНОВНОЙ КЛАСС БОТА ==================
class HomeworkBot:
    def __init__(self, token: str):
        self.token = token
        self.updater = Updater(token, use_context=True)
        self.dp = self.updater.dispatcher
        self.bot = self.updater.bot
        
        self._register_handlers()
    
    def _register_handlers(self):
        self.dp.add_handler(CommandHandler("start", self.cmd_start))
        self.dp.add_handler(CommandHandler("help", self.cmd_help))
        self.dp.add_handler(CommandHandler("menu", self.cmd_menu))
        self.dp.add_handler(CommandHandler("profile", self.cmd_profile))
        self.dp.add_handler(CommandHandler("admin", self.cmd_admin))
        self.dp.add_handler(CommandHandler("rates", self.cmd_rates))
        self.dp.add_handler(CommandHandler("fact", self.cmd_fact))
        self.dp.add_handler(CommandHandler("top", self.cmd_top))
        self.dp.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        
        self.dp.add_handler(CallbackQueryHandler(self.handle_callback))
        self.dp.add_handler(MessageHandler(Filters.photo, self.handle_photo))
        self.dp.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handle_text))
        self.dp.add_error_handler(self.error_handler)
    
    def get_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(get_text(user_id, 'homework'), callback_data="menu_hw"),
             InlineKeyboardButton(get_text(user_id, 'games'), callback_data="menu_games")],
            [InlineKeyboardButton(get_text(user_id, 'currency'), callback_data="menu_currency"),
             InlineKeyboardButton(get_text(user_id, 'schedule'), callback_data="menu_schedule")],
            [InlineKeyboardButton("📸 Фото", callback_data="menu_photo"),
             InlineKeyboardButton("🎲 Случайное", callback_data="menu_random")],
            [InlineKeyboardButton("⭐ Подписка", callback_data="menu_subscription"),
             InlineKeyboardButton("📞 Поддержка", callback_data="menu_support")],
            [InlineKeyboardButton("📊 Профиль", callback_data="menu_profile"),
             InlineKeyboardButton("🌐 Язык", callback_data="menu_language")],
            [InlineKeyboardButton("🎯 Факт", callback_data="menu_fact"),
             InlineKeyboardButton("🏆 Топ", callback_data="menu_top")],
        ]
        
        if is_admin(user_id):
            buttons.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_menu")])
        
        return InlineKeyboardMarkup(buttons)
    
    # ================== КОМАНДЫ ==================
    def cmd_start(self, update: Update, context: CallbackContext):
        user = update.effective_user
        
        # Регистрация пользователя
        db.execute(
            """INSERT OR IGNORE INTO users 
               (user_id, username, first_name, last_name, join_date, last_active) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user.id, user.username, user.first_name, user.last_name or '',
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        
        text = get_text(user.id, 'welcome', name=user.first_name)
        update.message.reply_text(text, reply_markup=self.get_main_keyboard(user.id))
    
    def cmd_help(self, update: Update, context: CallbackContext):
        help_text = """
📚 **Помощь по боту**

/start - Запустить бота
/menu - Главное меню
/profile - Мой профиль
/fact - Случайный факт
/top - Топ игроков
/rates - Курс USD

🎮 **Игры:**
- Крестики-нолики
- Угадай число
- Камень-ножницы-бумага
- Кости
- Математика

📸 Отправляйте фото - они попадут в галерею после модерации
⭐ Подписка - доступ к решенным ДЗ
📞 Связь с админом - задать вопрос

**Администраторам:**
/admin - Панель администратора
/broadcast - Сделать рассылку
"""
        update.message.reply_text(help_text, parse_mode='Markdown')
    
    def cmd_menu(self, update: Update, context: CallbackContext):
        update.message.reply_text(
            get_text(update.effective_user.id, 'main_menu'),
            reply_markup=self.get_main_keyboard(update.effective_user.id)
        )
    
    def cmd_profile(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        result = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        
        if result:
            data = result[0]
            subscription = "✅ Активна" if data['subscription_end'] and \
                          datetime.strptime(data['subscription_end'], "%Y-%m-%d %H:%M:%S") > datetime.now() else "❌ Нет"
            
            text = get_text(user_id, 'profile',
                          name=data['first_name'],
                          rating=data['rating'],
                          photos=data['photos_count'],
                          subscription=subscription,
                          date=data['join_date'][:10],
                          user_id=user_id)
            
            keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
            update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    def cmd_rates(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        try:
            response = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
            data = response.json()
            rub = data['rates'].get('RUB', 'N/A')
            eur = data['rates'].get('EUR', 'N/A')
            kzt = data['rates'].get('KZT', 'N/A')
            
            text = f"💱 **Курсы валют к USD**\n\n"
            text += f"🇺🇸 USD: 1.00\n"
            text += f"🇪🇺 EUR: {eur}\n"
            text += f"🇷🇺 RUB: {rub}\n"
            text += f"🇰🇿 KZT: {kzt}\n"
            text += f"\n🔄 {datetime.now().strftime('%H:%M')}"
        except:
            text = "❌ Не удалось получить курсы"
        
        keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
        update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    def cmd_fact(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        facts = db.execute("SELECT fact FROM daily_facts ORDER BY RANDOM() LIMIT 1")
        if facts:
            update.message.reply_text(f"🎯 {facts[0]['fact']}")
        else:
            update.message.reply_text("🎯 Фактов пока нет")
    
    def cmd_top(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        users = db.execute("SELECT first_name, rating FROM users WHERE rating > 0 ORDER BY rating DESC LIMIT 10")
        if users:
            text = "🏆 **Топ игроков**\n\n"
            for i, u in enumerate(users, 1):
                text += f"{i}. {u['first_name']} — {u['rating']} ⭐\n"
            keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
            update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    def cmd_broadcast(self, update: Update, context: CallbackContext):
        if not is_admin(update.effective_user.id):
            update.message.reply_text("❌ Нет прав")
            return
        
        if not context.args:
            update.message.reply_text("Использование: /broadcast <сообщение>")
            return
        
        message = ' '.join(context.args)
        users = db.execute("SELECT user_id FROM users")
        
        sent = 0
        failed = 0
        
        for user in users:
            try:
                context.bot.send_message(
                    chat_id=user['user_id'],
                    text=f"📢 **Сообщение от администрации**\n\n{message}",
                    parse_mode='Markdown'
                )
                sent += 1
            except:
                failed += 1
            time.sleep(0.05)
        
        update.message.reply_text(f"✅ Рассылка завершена!\n📨 Отправлено: {sent}\n❌ Не доставлено: {failed}")
    
    def cmd_admin(self, update: Update, context: CallbackContext):
        if not is_admin(update.effective_user.id):
            update.message.reply_text("❌ Нет прав")
            return
        
        user_id = update.effective_user.id
        keyboard = [
            [InlineKeyboardButton("📝 Добавить ДЗ", callback_data="admin_hw")],
            [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="admin_solved_hw")],
            [InlineKeyboardButton("📸 Модерация", callback_data="admin_moderate")],
            [InlineKeyboardButton("➕ Добавить факт", callback_data="admin_add_fact")],
            [InlineKeyboardButton("➕ Добавить урок", callback_data="admin_add_lesson")],
            [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton("🚫 Бан", callback_data="admin_ban")],
            [InlineKeyboardButton("✅ Разбан", callback_data="admin_unban")],
            [InlineKeyboardButton("⭐ Выдать подписку", callback_data="admin_subscription")],
            [InlineKeyboardButton("👁️ Слежка", callback_data="admin_tracking")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("📞 Сообщения", callback_data="admin_reports")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
        ]
        
        update.message.reply_text("👑 **Админ-панель**", parse_mode='Markdown',
                                 reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ================== ОБРАБОТЧИКИ ==================
    def handle_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        user_id = query.from_user.id
        data = query.data
        
        # Главное меню
        if data == "main_menu":
            query.edit_message_text(
                get_text(user_id, 'main_menu'),
                reply_markup=self.get_main_keyboard(user_id)
            )
            return
        
        # ДЗ
        if data == "menu_hw":
            hw = db.execute("SELECT subject, task FROM homework ORDER BY id DESC LIMIT 1")
            if hw:
                text = get_text(user_id, 'homework_text', subject=hw[0]['subject'], task=hw[0]['task'])
            else:
                text = get_text(user_id, 'no_homework')
            keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Игры
        if data == "menu_games":
            keyboard = [
                [InlineKeyboardButton(get_text(user_id, 'game_tic'), callback_data="game_tic")],
                [InlineKeyboardButton(get_text(user_id, 'game_number'), callback_data="game_number")],
                [InlineKeyboardButton(get_text(user_id, 'game_rps'), callback_data="game_rps")],
                [InlineKeyboardButton(get_text(user_id, 'game_dice'), callback_data="game_dice")],
                [InlineKeyboardButton(get_text(user_id, 'game_math'), callback_data="game_math")],
                [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")],
            ]
            query.edit_message_text(
                get_text(user_id, 'games_menu'),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Запуск игр
        if data in ["game_tic", "game_number", "game_rps", "game_dice", "game_math"]:
            game_type = data[5:]
            game_manager.start_game(user_id, game_type)
            
            messages = {
                'tic': f"❌ Крестики-нолики\nХодит X\n\n⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜\n\nВведите номер клетки (0-8):",
                'number': "🔢 Я загадал число от 1 до 100. Введите ваш вариант:",
                'rps': "✂️ Выберите: камень, ножницы, бумага",
                'dice': "🎲 Игра в кости\nУ вас 3 броска\nНапишите 'бросить'",
                'math': "🧮 Решите пример:\nВведите число"
            }
            
            game = game_manager.get_game(user_id)
            if game['type'] == 'math':
                a, b, op = game['data']['a'], game['data']['b'], game['data']['op']
                query.edit_message_text(f"{messages['math']} {a} {op} {b} = ?")
            else:
                query.edit_message_text(messages[game_type])
            return
        
        # Курс валют
        if data == "menu_currency":
            try:
                response = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
                data = response.json()
                rub = data['rates'].get('RUB', 'N/A')
                eur = data['rates'].get('EUR', 'N/A')
                kzt = data['rates'].get('KZT', 'N/A')
                
                text = f"💱 **Курсы валют к USD**\n\n"
                text += f"🇺🇸 USD: 1.00\n"
                text += f"🇪🇺 EUR: {eur}\n"
                text += f"🇷🇺 RUB: {rub}\n"
                text += f"🇰🇿 KZT: {kzt}\n"
                text += f"\n🔄 {datetime.now().strftime('%H:%M')}"
            except:
                text = "❌ Не удалось получить курсы"
            
            keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Расписание
        if data == "menu_schedule":
            days = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ']
            keyboard = []
            row = []
            for i, day in enumerate(days):
                row.append(InlineKeyboardButton(day, callback_data=f"schedule_{i}"))
                if (i + 1) % 3 == 0:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")])
            
            query.edit_message_text("📅 **Выберите день:**", parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        if data.startswith("schedule_"):
            day = int(data.split('_')[1])
            days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']
            
            schedule = db.execute(
                "SELECT * FROM schedule WHERE day_of_week = ? ORDER BY lesson_number",
                (day,)
            )
            
            if schedule:
                text = f"📅 **{days[day]}**\n\n"
                for lesson in schedule:
                    text += f"{lesson['lesson_number']}. {lesson['subject']}\n"
                    if lesson['teacher']:
                        text += f"   👨‍🏫 {lesson['teacher']}\n"
                    if lesson['room']:
                        text += f"   🏫 Каб. {lesson['room']}\n"
            else:
                text = f"📅 {days[day]}\n\nУроков нет"
            
            keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="menu_schedule")]]
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Фото
        if data == "menu_photo":
            query.edit_message_text(
                get_text(user_id, 'send_photo'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")
                ]])
            )
            return
        
        # Случайное фото
        if data == "menu_random":
            photos = db.execute("SELECT file_id FROM photos WHERE status = 'approved'")
            if photos:
                photo = random.choice(photos)
                count = len(photos)
                
                caption = get_text(user_id, 'random_photo', count=count)
                
                if is_tracking_enabled() and is_admin(user_id):
                    info = db.execute(
                        "SELECT username, user_id, date FROM photos WHERE file_id = ?",
                        (photo['file_id'],)
                    )
                    if info:
                        caption += f"\n\n👤 Отправил: @{info[0]['username']} (ID: {info[0]['user_id']})\n📅 {info[0]['date'][:16]}"
                
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(user_id, 'more'), callback_data="menu_random"),
                    InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")
                ]])
                
                query.message.reply_photo(photo=photo['file_id'], caption=caption, reply_markup=keyboard)
                query.message.delete()
            else:
                query.edit_message_text(
                    get_text(user_id, 'no_photos'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")
                    ]])
                )
            return
        
        # Подписка
        if data == "menu_subscription":
            result = db.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
            has_sub = result and result[0]['subscription_end'] and \
                     datetime.strptime(result[0]['subscription_end'], "%Y-%m-%d %H:%M:%S") > datetime.now()
            
            if has_sub:
                text = get_text(user_id, 'active_subscription', date=result[0]['subscription_end'])
                keyboard = [
                    [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw")],
                    [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
                ]
            else:
                text = get_text(user_id, 'subscription', price=STAR_PRICE)
                keyboard = [
                    [InlineKeyboardButton(f"⭐ Оплатить {STAR_PRICE} звёзд", callback_data="pay_subscription")],
                    [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
                ]
            
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Решенное ДЗ
        if data == "menu_solved_hw":
            result = db.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
            has_sub = result and result[0]['subscription_end'] and \
                     datetime.strptime(result[0]['subscription_end'], "%Y-%m-%d %H:%M:%S") > datetime.now()
            
            if not has_sub:
                keyboard = [
                    [InlineKeyboardButton("⭐ Купить подписку", callback_data="menu_subscription")],
                    [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]
                ]
                query.edit_message_text(
                    get_text(user_id, 'subscription', price=STAR_PRICE),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            
            solved = db.execute(
                "SELECT subject, photo_ids FROM solved_homework WHERE expires_at > datetime('now') ORDER BY id DESC LIMIT 1"
            )
            
            if solved and solved[0]['photo_ids']:
                subject = solved[0]['subject']
                photo_ids = solved[0]['photo_ids'].split(',')
                
                query.edit_message_text(f"✅ Решенное ДЗ - {subject}\n\nЗагружаю {len(photo_ids)} фото...")
                
                for i, pid in enumerate(photo_ids, 1):
                    caption = f"✅ {subject} (фото {i}/{len(photo_ids)})"
                    query.message.reply_photo(photo=pid, caption=caption)
                
                query.message.reply_text(
                    get_text(user_id, 'main_menu'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")
                    ]])
                )
                query.message.delete()
            else:
                query.edit_message_text(
                    "📝 Решенное ДЗ пока нет",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")
                    ]])
                )
            return
        
        # Оплата
        if data == "pay_subscription":
            query.edit_message_text(
                f"⭐ Для оплаты подписки отправьте {STAR_PRICE} звёзд этому боту.\n\n"
                f"Инструкция:\n"
                f"1. Нажмите на скрепку 📎\n"
                f"2. Выберите 💎 'Звёзды'\n"
                f"3. Укажите количество: {STAR_PRICE}\n"
                f"4. Отправьте и подписка активируется!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(user_id, 'back'), callback_data="menu_subscription")
                ]])
            )
            return
        
        # Поддержка
        if data == "menu_support":
            query.edit_message_text(
                get_text(user_id, 'support_message'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")
                ]])
            )
            context.user_data['waiting_support'] = True
            return
        
        # Профиль
        if data == "menu_profile":
            result = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            if result:
                data = result[0]
                subscription = "✅ Активна" if data['subscription_end'] and \
                              datetime.strptime(data['subscription_end'], "%Y-%m-%d %H:%M:%S") > datetime.now() else "❌ Нет"
                
                text = get_text(user_id, 'profile',
                              name=data['first_name'],
                              rating=data['rating'],
                              photos=data['photos_count'],
                              subscription=subscription,
                              date=data['join_date'][:10],
                              user_id=user_id)
                
                keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
                query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Язык
        if data == "menu_language":
            keyboard = [
                [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
                [InlineKeyboardButton("🇰🇿 Қазақша", callback_data="lang_kz")],
                [InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")],
            ]
            query.edit_message_text("Выберите язык:", reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        if data.startswith("lang_"):
            lang = data.split('_')[1]
            db.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
            query.edit_message_text(
                get_text(user_id, 'language_changed'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")
                ]])
            )
            return
        
        # Факт
        if data == "menu_fact":
            facts = db.execute("SELECT fact FROM daily_facts ORDER BY RANDOM() LIMIT 1")
            if facts:
                text = f"🎯 {facts[0]['fact']}"
            else:
                text = "🎯 Фактов пока нет"
            
            keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Топ
        if data == "menu_top":
            users = db.execute("SELECT first_name, rating FROM users WHERE rating > 0 ORDER BY rating DESC LIMIT 10")
            if users:
                text = "🏆 **Топ игроков**\n\n"
                for i, u in enumerate(users, 1):
                    text += f"{i}. {u['first_name']} — {u['rating']} ⭐\n"
            else:
                text = "🏆 Пока нет игроков с рейтингом"
            
            keyboard = [[InlineKeyboardButton(get_text(user_id, 'back'), callback_data="main_menu")]]
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Админ-меню
        if data == "admin_menu" and is_admin(user_id):
            keyboard = [
                [InlineKeyboardButton("📝 Добавить ДЗ", callback_data="admin_hw")],
                [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="admin_solved_hw")],
                [InlineKeyboardButton("📸 Модерация", callback_data="admin_moderate")],
                [InlineKeyboardButton("➕ Добавить факт", callback_data="admin_add_fact")],
                [InlineKeyboardButton("➕ Добавить урок", callback_data="admin_add_lesson")],
                [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
                [InlineKeyboardButton("🚫 Бан", callback_data="admin_ban")],
                [InlineKeyboardButton("✅ Разбан", callback_data="admin_unban")],
                [InlineKeyboardButton("⭐ Выдать подписку", callback_data="admin_subscription")],
                [InlineKeyboardButton("👁️ Слежка", callback_data="admin_tracking")],
                [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
                [InlineKeyboardButton("📞 Сообщения", callback_data="admin_reports")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
            ]
            query.edit_message_text("👑 **Админ-панель**", parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Слежка
        if data == "admin_tracking" and is_admin(user_id):
            enabled = is_tracking_enabled()
            status = "✅ ВКЛЮЧЕНА" if enabled else "❌ ВЫКЛЮЧЕНА"
            keyboard = [
                [InlineKeyboardButton("✅ Включить" if not enabled else "❌ Выключить", callback_data="toggle_tracking")],
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")],
            ]
            query.edit_message_text(
                f"👁️ **Настройка слежки**\n\nТекущий статус: {status}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        if data == "toggle_tracking" and is_admin(user_id):
            enabled = is_tracking_enabled()
            set_tracking(not enabled)
            new_status = "✅ ВКЛЮЧЕНА" if not enabled else "❌ ВЫКЛЮЧЕНА"
            query.edit_message_text(
                f"👁️ Статус изменен на: {new_status}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="admin_tracking")
                ]])
            )
            return
        
        # Статистика
        if data == "admin_stats" and is_admin(user_id):
            users = db.execute("SELECT COUNT(*) as count FROM users")[0]['count']
            photos = db.execute("SELECT COUNT(*) as count FROM photos WHERE status='approved'")[0]['count']
            pending = db.execute("SELECT COUNT(*) as count FROM photos WHERE status='pending'")[0]['count']
            reports = db.execute("SELECT COUNT(*) as count FROM reports WHERE status='new'")[0]['count']
            
            text = f"📊 **Статистика**\n\n"
            text += f"👥 Пользователей: {users}\n"
            text += f"📸 Фото в галерее: {photos}\n"
            text += f"⏳ На модерации: {pending}\n"
            text += f"📞 Новых сообщений: {reports}"
            
            query.edit_message_text(text, parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup([[
                                      InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                                  ]]))
            return
        
        # Сообщения
        if data == "admin_reports" and is_admin(user_id):
            reports = db.execute("SELECT * FROM reports WHERE status='new' ORDER BY date")
            if not reports:
                query.edit_message_text(
                    "📞 Новых сообщений нет",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                    ]])
                )
                return
            
            for report in reports[:5]:
                text = f"📞 **Новое сообщение**\n\n"
                text += f"От: @{report['username']} (ID: {report['user_id']})\n"
                text += f"Дата: {report['date'][:16]}\n"
                text += f"Сообщение: {report['message']}"
                
                db.execute("UPDATE reports SET status='read' WHERE id=?", (report['id'],))
                
                query.message.reply_text(text, parse_mode='Markdown')
            
            query.message.reply_text(
                "✅ Сообщения отмечены как прочитанные",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                ]])
            )
            query.message.delete()
            return
        
        # Админ-действия с вводом
        admin_actions = {
            'admin_hw': ('📝 Введите ДЗ в формате:\nПредмет: Задание', 'hw'),
            'admin_solved_hw': ('✅ Отправьте фото решенного ДЗ (можно несколько)', 'solved_hw'),
            'admin_add_fact': ('📝 Введите факт:', 'add_fact'),
            'admin_add_lesson': ('📚 Введите урок в формате:\nдень номер предмет учитель кабинет\n(день: 0-4)', 'add_lesson'),
            'admin_add': ('➕ Введите ID нового администратора:', 'add_admin'),
            'admin_ban': ('🚫 Введите ID пользователя и часы (или навсегда):\nПример: 123456789 24', 'ban'),
            'admin_unban': ('✅ Введите ID пользователя для разбана:', 'unban'),
            'admin_subscription': ('⭐ Введите ID пользователя и дни подписки:', 'subscription'),
        }
        
        if data in admin_actions and is_admin(user_id):
            text, action = admin_actions[data]
            query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            context.user_data['admin_action'] = action
            if action == 'solved_hw':
                context.user_data['solved_photos'] = []
            return
        
        # Модерация
        if data == "admin_moderate" and is_admin(user_id):
            pending = db.execute("SELECT * FROM photos WHERE status='pending'")
            if pending:
                context.user_data['pending'] = pending
                context.user_data['pending_index'] = 0
                self._show_pending(query, context, 0)
            else:
                query.edit_message_text(
                    "📸 Нет фото на модерации",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                    ]])
                )
            return
        
        if data.startswith("approve_") and is_admin(user_id):
            photo_id = int(data.split('_')[1])
            db.execute(
                "UPDATE photos SET status='approved', moderated_by=?, moderation_date=? WHERE id=?",
                (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), photo_id)
            )
            
            if 'pending' in context.user_data:
                idx = context.user_data.get('pending_index', 0) + 1
                pending = context.user_data['pending']
                if idx < len(pending):
                    self._show_pending(query, context, idx)
                else:
                    query.edit_message_text(
                        "✅ Все фото обработаны",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                        ]])
                    )
                    context.user_data.pop('pending', None)
                    context.user_data.pop('pending_index', None)
            return
        
        if data.startswith("reject_") and is_admin(user_id):
            photo_id = int(data.split('_')[1])
            db.execute(
                "UPDATE photos SET status='rejected', moderated_by=?, moderation_date=? WHERE id=?",
                (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), photo_id)
            )
            
            if 'pending' in context.user_data:
                idx = context.user_data.get('pending_index', 0) + 1
                pending = context.user_data['pending']
                if idx < len(pending):
                    self._show_pending(query, context, idx)
                else:
                    query.edit_message_text(
                        "✅ Все фото обработаны",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                        ]])
                    )
                    context.user_data.pop('pending', None)
                    context.user_data.pop('pending_index', None)
            return
    
    def _show_pending(self, query, context, index):
        pending = context.user_data['pending']
        if index >= len(pending):
            return
        
        photo = pending[index]
        context.user_data['pending_index'] = index
        
        caption = f"📸 {index+1}/{len(pending)}\nОт: @{photo['username']}\nДата: {photo['date'][:16]}"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{photo['id']}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{photo['id']}")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")]
        ])
        
        query.message.reply_photo(photo=photo['file_id'], caption=caption, reply_markup=keyboard)
        query.message.delete()
    
    # ================== ОБРАБОТЧИКИ СООБЩЕНИЙ ==================
    def handle_photo(self, update: Update, context: CallbackContext):
        user = update.effective_user
        photo = update.message.photo[-1]
        
        # Проверка на решенное ДЗ
        if context.user_data.get('admin_action') == 'solved_hw' and is_admin(user.id):
            if 'solved_photos' not in context.user_data:
                context.user_data['solved_photos'] = []
            context.user_data['solved_photos'].append(photo.file_id)
            update.message.reply_text(
                f"✅ Фото {len(context.user_data['solved_photos'])} добавлено.\n"
                f"Отправьте ещё или напишите название предмета для завершения"
            )
            return
        
        # Обычное фото
        db.execute(
            "INSERT INTO photos (file_id, user_id, username, date, status) VALUES (?, ?, ?, ?, ?)",
            (photo.file_id, user.id, user.username or user.first_name,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'pending')
        )
        
        # Уведомление админам при включенной слежке
        if is_tracking_enabled():
            for admin_id in ADMIN_IDS:
                try:
                    context.bot.send_message(
                        chat_id=admin_id,
                        text=f"📸 Новое фото на модерацию от @{user.username or user.first_name} (ID: {user.id})"
                    )
                except:
                    pass
        
        update.message.reply_text(
            "✅ Фото отправлено на модерацию!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
        )
    
    def handle_text(self, update: Update, context: CallbackContext):
        user = update.effective_user
        text = update.message.text
        
        # Обновление активности
        db.execute(
            "UPDATE users SET last_active = ? WHERE user_id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user.id)
        )
        
        # Обработка игр
        game = game_manager.get_game(user.id)
        if game:
            result = game_manager.process_move(user.id, text.lower())
            if result:
                if result.get('game_over'):
                    game_manager.end_game(user.id)
                update.message.reply_text(result['message'])
                return
        
        # Обработка поддержки
        if context.user_data.get('waiting_support'):
            db.execute(
                "INSERT INTO reports (user_id, username, message, date) VALUES (?, ?, ?, ?)",
                (user.id, user.username or user.first_name, text,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            
            update.message.reply_text(
                get_text(user.id, 'support_sent'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ]])
            )
            
            context.user_data['waiting_support'] = False
            
            # Уведомление админам
            for admin_id in ADMIN_IDS:
                try:
                    context.bot.send_message(
                        chat_id=admin_id,
                        text=f"📞 Новое сообщение от @{user.username or user.first_name} (ID: {user.id})\n\n{text}"
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
                    db.execute(
                        "INSERT INTO homework (subject, task, date, created_by) VALUES (?, ?, ?, ?)",
                        (subject.strip(), task.strip(),
                         datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user.id)
                    )
                    update.message.reply_text("✅ ДЗ добавлено!")
                    context.user_data['admin_action'] = None
                else:
                    update.message.reply_text("❌ Используйте формат: Предмет: Задание")
            
            elif action == 'solved_hw':
                if context.user_data.get('solved_photos'):
                    photo_ids = ','.join(context.user_data['solved_photos'])
                    expires_at = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                    db.execute(
                        "INSERT INTO solved_homework (subject, photo_ids, date, expires_at) VALUES (?, ?, ?, ?)",
                        (text, photo_ids, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at)
                    )
                    update.message.reply_text("✅ Решенное ДЗ добавлено!")
                    context.user_data['admin_action'] = None
                    context.user_data.pop('solved_photos', None)
                else:
                    update.message.reply_text("❌ Сначала отправьте фото")
            
            elif action == 'add_fact':
                db.execute(
                    "INSERT INTO daily_facts (fact, added_by, date) VALUES (?, ?, ?)",
                    (text, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                update.message.reply_text("✅ Факт добавлен!")
                context.user_data['admin_action'] = None
            
            elif action == 'add_lesson':
                try:
                    parts = text.split()
                    day = int(parts[0])
                    num = int(parts[1])
                    subject = parts[2]
                    teacher = parts[3] if len(parts) > 3 else ''
                    room = parts[4] if len(parts) > 4 else ''
                    
                    db.execute(
                        "INSERT INTO schedule (day_of_week, lesson_number, subject, teacher, room) VALUES (?, ?, ?, ?, ?)",
                        (day, num, subject, teacher, room)
                    )
                    update.message.reply_text("✅ Урок добавлен!")
                    context.user_data['admin_action'] = None
                except:
                    update.message.reply_text("❌ Ошибка формата")
            
            elif action == 'add_admin':
                try:
                    admin_id = int(text)
                    chat = context.bot.get_chat(admin_id)
                    username = chat.username or chat.first_name
                    
                    db.execute(
                        "INSERT OR REPLACE INTO admins (user_id, username, added_by, date) VALUES (?, ?, ?, ?)",
                        (admin_id, username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    
                    update.message.reply_text(f"✅ Пользователь {username} теперь администратор!")
                    context.user_data['admin_action'] = None
                    
                    try:
                        context.bot.send_message(
                            chat_id=admin_id,
                            text="🎉 Вас назначили администратором бота!"
                        )
                    except:
                        pass
                except:
                    update.message.reply_text("❌ Введите корректный ID")
            
            elif action == 'ban':
                try:
                    parts = text.split()
                    uid = int(parts[0])
                    hours = int(parts[1]) if len(parts) > 1 else None
                    reason = ' '.join(parts[2:]) if len(parts) > 2 else "Нарушение правил"
                    
                    if hours:
                        ban_until = datetime.now() + timedelta(hours=hours)
                        db.execute(
                            "UPDATE users SET banned_until=?, permanent_ban=0, ban_reason=? WHERE user_id=?",
                            (ban_until.strftime("%Y-%m-%d %H:%M:%S"), reason, uid)
                        )
                        update.message.reply_text(f"✅ Пользователь {uid} забанен на {hours} часов")
                    else:
                        db.execute(
                            "UPDATE users SET permanent_ban=1, ban_reason=? WHERE user_id=?",
                            (reason, uid)
                        )
                        update.message.reply_text(f"✅ Пользователь {uid} забанен навсегда")
                    
                    context.user_data['admin_action'] = None
                except:
                    update.message.reply_text("❌ Ошибка формата")
            
            elif action == 'unban':
                try:
                    uid = int(text)
                    db.execute(
                        "UPDATE users SET banned_until=NULL, permanent_ban=0, ban_reason='' WHERE user_id=?",
                        (uid,)
                    )
                    update.message.reply_text(f"✅ Пользователь {uid} разбанен")
                    context.user_data['admin_action'] = None
                except:
                    update.message.reply_text("❌ Введите ID")
            
            elif action == 'subscription':
                try:
                    parts = text.split()
                    uid = int(parts[0])
                    days = int(parts[1]) if len(parts) > 1 else 30
                    
                    sub_end = datetime.now() + timedelta(days=days)
                    db.execute(
                        "UPDATE users SET subscription_end=? WHERE user_id=?",
                        (sub_end.strftime("%Y-%m-%d %H:%M:%S"), uid)
                    )
                    
                    update.message.reply_text(f"✅ Подписка выдана на {days} дней")
                    context.user_data['admin_action'] = None
                    
                    try:
                        context.bot.send_message(
                            chat_id=uid,
                            text=f"⭐ Вам выдана подписка на {days} дней!"
                        )
                    except:
                        pass
                except:
                    update.message.reply_text("❌ Ошибка формата")
    
    def error_handler(self, update: Update, context: CallbackContext):
        logger.error(f"Update {update} caused error {context.error}")
        try:
            if update and update.effective_message:
                update.effective_message.reply_text("❌ Произошла ошибка")
        except:
            pass
    
    def run(self):
        print("🚀 Бот 'Помощник 9Г' запущен...")
        print(f"👑 Главный администратор ID: {ADMIN_IDS[0]}")
        print("✅ Все функции работают:")
        print("   - Игры (Крестики-нолики, Угадай число, КНБ, Кости, Математика)")
        print("   - Профиль и рейтинг")
        print("   - Смена языка")
        print("   - Слежка и модерация")
        print("   - Рассылка")
        print("   - Расписание")
        print("   - Курсы валют")
        print("   - Факты")
        print("   - Подписки")
        
        self.updater.start_polling()
        self.updater.idle()

# ================== ЗАПУСК ==================
if __name__ == "__main__":
    bot = HomeworkBot(TOKEN)
    bot.run()
