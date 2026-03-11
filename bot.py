import logging
import random
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
import time
import json
import hashlib
import re
from collections import defaultdict
from threading import Thread, Lock
from queue import Queue
import asyncio
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import cachetools
import aiohttp
import requests
from bs4 import BeautifulSoup
import yfinance as yf
from forex_python.converter import CurrencyRates
import schedule
import csv
from io import StringIO
import matplotlib.pyplot as plt
import io
import numpy as np
from datetime import date, time
import calendar
import string

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, CallbackQueryHandler,
    Filters, CallbackContext, ConversationHandler, PreCheckoutQueryHandler
)
from telegram.error import TelegramError

# ================== НАСТРОЙКИ И КОНСТАНТЫ ==================
TOKEN = "8623075329:AAHRnpXR1nMd5m-STE8daYUAevtL9D38jEQ"
ADMIN_IDS = [1553865459]
DB_PATH = "homework_bot.db"
STAR_PRICE = 50
PHOTO_EXPIRE_DAYS = 7

class Language(Enum):
    RU = 'ru'
    EN = 'en'
    KZ = 'kz'

class UserRole(Enum):
    USER = 'user'
    SUBSCRIBER = 'subscriber'
    MODERATOR = 'moderator'
    ADMIN = 'admin'
    OWNER = 'owner'

class PhotoStatus(Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    DELETED = 'deleted'

class ReportStatus(Enum):
    NEW = 'new'
    IN_PROGRESS = 'in_progress'
    RESOLVED = 'resolved'
    REJECTED = 'rejected'

class GameType(Enum):
    TIC_TAC_TOE = "tic_tac_toe"
    GUESS_NUMBER = "guess_number"
    WORD_GAME = "word_game"
    MATH_QUIZ = "math_quiz"
    MEMORY = "memory"
    RPS = "rock_paper_scissors"
    HANGMAN = "hangman"
    TRIVIA = "trivia"
    CHESS = "chess"
    SNAKE = "snake"

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
        'subscription': "⭐ **Подписка за {price} звёзд**\n\nЧто дает подписка:\n✅ Доступ к решенному домашнему заданию\n✅ Приоритетная поддержка\n✅ +10 баллов к рейтингу за фото\n✅ Доступ к эксклюзивному контенту\n✅ Специальный значок в профиле",
        'active_subscription': "⭐ **У вас активна подписка!**\n\nДействует до: {date}\n\nДоступно:\n✅ Решенное домашнее задание\n✅ Эксклюзивный контент\n✅ Специальный значок",
        'profile': "📊 **Ваш профиль**\n\n⭐ Рейтинг: {rating}\n📸 Одобренных фото: {photos}\n💎 Подписка: {subscription}\n📅 Дата регистрации: {join_date}\n🆔 ID: {user_id}",
        'banned': "⛔ Вы забанены до {date}. Причина: {reason}",
        'permanent_ban': "⛔ Вы забанены навсегда. Причина: {reason}",
        'support_message': "📞 Напишите ваше сообщение для администратора.",
        'support_sent': "✅ Ваше сообщение отправлено администратору!",
        'back': "🔙 Назад",
        'more': "🔄 Ещё",
        'cancel': "❌ Отмена",
        'confirm': "✅ Подтвердить",
        'language_changed': "✅ Язык изменен на русский",
        'games': "🎮 Игры на перемене",
        'currency': "💱 Курсы валют",
        'schedule': "📅 Расписание уроков",
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
        'subscription': "⭐ **Subscription for {price} stars**\n\nWhat it gives:\n✅ Access to solved homework\n✅ Priority support\n✅ +10 rating points per photo\n✅ Exclusive content access\n✅ Special profile badge",
        'active_subscription': "⭐ **You have an active subscription!**\n\nValid until: {date}\n\nAvailable:\n✅ Solved homework\n✅ Exclusive content\n✅ Special badge",
        'profile': "📊 **Your Profile**\n\n⭐ Rating: {rating}\n📸 Approved photos: {photos}\n💎 Subscription: {subscription}\n📅 Registration date: {join_date}\n🆔 ID: {user_id}",
        'banned': "⛔ You are banned until {date}. Reason: {reason}",
        'permanent_ban': "⛔ You are permanently banned. Reason: {reason}",
        'support_message': "📞 Write your message to the administrator.",
        'support_sent': "✅ Your message has been sent to the administrator!",
        'back': "🔙 Back",
        'more': "🔄 More",
        'cancel': "❌ Cancel",
        'confirm': "✅ Confirm",
        'language_changed': "✅ Language changed to English",
        'games': "🎮 Break Games",
        'currency': "💱 Currency Rates",
        'schedule': "📅 Class Schedule",
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
        'subscription': "⭐ **{price} жұлдызға жазылым**\n\nБеретін мүмкіндіктер:\n✅ Шешілген үй тапсырмасы\n✅ Бірінші кезектегі қолдау\n✅ Фото үшін +10 рейтинг баллы\n✅ Эксклюзивті контент\n✅ Арнайы профиль белгісі",
        'active_subscription': "⭐ **Жазылымыңыз белсенді!**\n\nМерзімі: {date}\n\nҚолжетімді:\n✅ Шешілген үй тапсырмасы\n✅ Эксклюзивті контент\n✅ Арнайы белгі",
        'profile': "📊 **Сіздің профиліңіз**\n\n⭐ Рейтинг: {rating}\n📸 Мақұлданған фото: {photos}\n💎 Жазылым: {subscription}\n📅 Тіркелген күн: {join_date}\n🆔 ID: {user_id}",
        'banned': "⛔ Сіз {date} дейін бұғатталдыңыз. Себеп: {reason}",
        'permanent_ban': "⛔ Сіз мәңгілікке бұғатталдыңыз. Себеп: {reason}",
        'support_message': "📞 Әкімшіге хабарламаңызды жазыңыз.",
        'support_sent': "✅ Хабарламаңыз әкімшіге жіберілді!",
        'back': "🔙 Артқа",
        'more': "🔄 Тағы",
        'cancel': "❌ Болдырмау",
        'confirm': "✅ Растау",
        'language_changed': "✅ Тіл қазақ тіліне ауыстырылды",
        'games': "🎮 Үзіліс ойындары",
        'currency': "💱 Валюта бағамдары",
        'schedule': "📅 Сабақ кестесі",
    }
}

@dataclass
class UserData:
    user_id: int
    username: str
    first_name: str
    last_name: str = ''
    language: Language = Language.RU
    role: UserRole = UserRole.USER
    rating: int = 0
    photos_count: int = 0
    subscription_end: Optional[datetime] = None
    banned_until: Optional[datetime] = None
    permanent_ban: bool = False
    ban_reason: str = ''
    join_date: datetime = None
    last_active: datetime = None
    warnings: int = 0
    achievements: List[str] = None
    # ================== ОПТИМИЗИРОВАННЫЙ МЕНЕДЖЕР БАЗЫ ДАННЫХ ==================
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
        self.connection_pool = Queue(maxsize=10)
        self.cache = cachetools.TTLCache(maxsize=100, ttl=300)
        self.stats = defaultdict(int)
        self._init_pool()
        self._create_tables()
    
    def _init_pool(self):
        for _ in range(5):
            conn = sqlite3.connect('homework_bot.db', check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self.connection_pool.put(conn)
    
    def _get_connection(self):
        return self.connection_pool.get()
    
    def _return_connection(self, conn):
        self.connection_pool.put(conn)
    
    def _create_tables(self):
        conn = self._get_connection()
        c = conn.cursor()
        
        # Users table
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
            last_active TEXT,
            warnings INTEGER DEFAULT 0,
            achievements TEXT,
            settings TEXT
        )''')
        
        # Photos table
        c.execute('''CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            user_id INTEGER,
            username TEXT,
            date TEXT,
            status TEXT DEFAULT 'pending',
            moderated_by INTEGER,
            moderation_date TEXT,
            moderation_comment TEXT,
            likes INTEGER DEFAULT 0,
            dislikes INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            tags TEXT,
            metadata TEXT
        )''')
        
        # Homework table
        c.execute('''CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            task TEXT,
            type TEXT DEFAULT 'regular',
            date TEXT,
            created_by INTEGER,
            attachments TEXT,
            due_date TEXT,
            priority INTEGER DEFAULT 0
        )''')
        
        # Solved homework table
        c.execute('''CREATE TABLE IF NOT EXISTS solved_homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            photo_ids TEXT,
            date TEXT,
            expires_at TEXT,
            created_by INTEGER,
            description TEXT,
            difficulty INTEGER DEFAULT 0
        )''')
        
        # Reports table
        c.execute('''CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            message TEXT,
            date TEXT,
            status TEXT DEFAULT 'new',
            assigned_to INTEGER,
            response TEXT,
            response_date TEXT,
            category TEXT
        )''')
        
        # Broadcasts table
        c.execute('''CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            message TEXT,
            date TEXT,
            status TEXT DEFAULT 'pending',
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            total_count INTEGER DEFAULT 0
        )''')
        
        # Facts table
        c.execute('''CREATE TABLE IF NOT EXISTS daily_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT,
            category TEXT,
            added_by INTEGER,
            date TEXT,
            language TEXT DEFAULT 'ru',
            likes INTEGER DEFAULT 0
        )''')
        
        # Polls table
        c.execute('''CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            options TEXT,
            created_by INTEGER,
            date TEXT,
            expires_at TEXT,
            is_active INTEGER DEFAULT 1,
            is_anonymous INTEGER DEFAULT 1,
            multiple_choice INTEGER DEFAULT 0,
            total_votes INTEGER DEFAULT 0
        )''')
        
        # Poll votes table
        c.execute('''CREATE TABLE IF NOT EXISTS poll_votes (
            poll_id INTEGER,
            user_id INTEGER,
            option_index INTEGER,
            date TEXT,
            PRIMARY KEY (poll_id, user_id)
        )''')
        
        # Achievements table
        c.execute('''CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            icon TEXT,
            condition TEXT,
            reward INTEGER DEFAULT 0
        )''')
        
        # User achievements table
        c.execute('''CREATE TABLE IF NOT EXISTS user_achievements (
            user_id INTEGER,
            achievement_id INTEGER,
            date TEXT,
            PRIMARY KEY (user_id, achievement_id)
        )''')
        
        # Chat history table
        c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            response TEXT,
            date TEXT,
            intent TEXT,
            sentiment REAL
        )''')
        
        # Notifications table
        c.execute('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            title TEXT,
            content TEXT,
            date TEXT,
            read INTEGER DEFAULT 0,
            data TEXT
        )''')
        
        # Moderation queue table
        c.execute('''CREATE TABLE IF NOT EXISTS moderation_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT,
            content_id INTEGER,
            priority INTEGER DEFAULT 0,
            date TEXT,
            assigned_to INTEGER,
            status TEXT DEFAULT 'pending'
        )''')
        
        # Game scores table
        c.execute('''CREATE TABLE IF NOT EXISTS game_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT,
            score INTEGER,
            level INTEGER,
            date TEXT,
            duration INTEGER
        )''')
        
        # Game stats table
        c.execute('''CREATE TABLE IF NOT EXISTS game_stats (
            user_id INTEGER,
            game_type TEXT,
            games_played INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            highest_score INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, game_type)
        )''')
        
        # Schedule table
        c.execute('''CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week INTEGER,
            lesson_number INTEGER,
            subject TEXT,
            teacher TEXT,
            room TEXT,
            start_time TEXT,
            end_time TEXT,
            is_active INTEGER DEFAULT 1
        )''')
        
        # Substitutions table
        c.execute('''CREATE TABLE IF NOT EXISTS substitutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            lesson_number INTEGER,
            original_subject TEXT,
            new_subject TEXT,
            reason TEXT
        )''')
        
        conn.commit()
        self._return_connection(conn)
    
    def execute_query(self, query: str, params: tuple = (), cache_key: str = None, cache_ttl: int = 300):
        if cache_key and cache_key in self.cache:
            self.stats['cache_hits'] += 1
            return self.cache[cache_key]
        
        conn = self._get_connection()
        c = conn.cursor()
        
        try:
            c.execute(query, params)
            if query.strip().upper().startswith('SELECT'):
                result = c.fetchall()
                if cache_key:
                    self.cache[cache_key] = result
                    self.stats['cache_misses'] += 1
                return result
            else:
                conn.commit()
                self.stats['write_operations'] += 1
                return c.lastrowid
        except Exception as e:
            self.stats['errors'] += 1
            raise e
        finally:
            self._return_connection(conn)
    
    def execute_transaction(self, queries: List[Tuple[str, tuple]]):
        conn = self._get_connection()
        c = conn.cursor()
        
        try:
            conn.execute("BEGIN TRANSACTION")
            results = []
            for query, params in queries:
                c.execute(query, params)
                results.append(c.lastrowid)
            conn.commit()
            self.stats['transactions'] += 1
            return results
        except Exception as e:
            conn.rollback()
            self.stats['errors'] += 1
            raise e
        finally:
            self._return_connection(conn)
    
    def get_stats(self):
        return dict(self.stats)
    
    def clear_cache(self):
        self.cache.clear()
        self.stats['cache_clears'] += 1

# ================== МЕНЕДЖЕР ПОЛЬЗОВАТЕЛЕЙ ==================
class UserManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.cache = cachetools.TTLCache(maxsize=500, ttl=600)
        self.active_users = set()
    
    def get_user(self, user_id: int) -> Optional[UserData]:
        cache_key = f'user_{user_id}'
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = self.db.execute_query(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
            cache_key=f'user_db_{user_id}'
        )
        
        if not result:
            return None
        
        row = result[0]
        user = UserData(
            user_id=row['user_id'],
            username=row['username'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            language=Language(row['language']),
            role=UserRole(row['role']),
            rating=row['rating'],
            photos_count=row['photos_count'],
            subscription_end=datetime.strptime(row['subscription_end'], "%Y-%m-%d %H:%M:%S") if row['subscription_end'] else None,
            banned_until=datetime.strptime(row['banned_until'], "%Y-%m-%d %H:%M:%S") if row['banned_until'] else None,
            permanent_ban=bool(row['permanent_ban']),
            ban_reason=row['ban_reason'] or '',
            join_date=datetime.strptime(row['join_date'], "%Y-%m-%d %H:%M:%S") if row['join_date'] else None,
            last_active=datetime.strptime(row['last_active'], "%Y-%m-%d %H:%M:%S") if row['last_active'] else None,
            warnings=row['warnings'],
            achievements=json.loads(row['achievements']) if row['achievements'] else []
        )
        
        self.cache[cache_key] = user
        return user
    
    def create_user(self, update: Update) -> UserData:
        user = update.effective_user
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.db.execute_query(
            """INSERT INTO users 
               (user_id, username, first_name, last_name, join_date, last_active, settings) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user.id, user.username, user.first_name, user.last_name, now, now, '{}')
        )
        
        user_data = UserData(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name or '',
            join_date=datetime.now()
        )
        
        self.cache[f'user_{user.id}'] = user_data
        return user_data
    
    def update_user(self, user_id: int, **kwargs):
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        
        self.db.execute_query(
            f"UPDATE users SET {set_clause} WHERE user_id = ?",
            tuple(values)
        )
        
        cache_key = f'user_{user_id}'
        if cache_key in self.cache:
            del self.cache[cache_key]
    
    def is_banned(self, user_id: int) -> Tuple[bool, str]:
        user = self.get_user(user_id)
        if not user:
            return False, ""
        
        if user.permanent_ban:
            return True, user.ban_reason
        
        if user.banned_until and user.banned_until > datetime.now():
            return True, user.ban_reason
        
        return False, ""
    
    def ban_user(self, user_id: int, duration: int = None, reason: str = ""):
        now = datetime.now()
        
        if duration:
            ban_until = now + timedelta(hours=duration)
            self.update_user(
                user_id,
                banned_until=ban_until.strftime("%Y-%m-%d %H:%M:%S"),
                permanent_ban=0,
                ban_reason=reason
            )
        else:
            self.update_user(
                user_id,
                banned_until=None,
                permanent_ban=1,
                ban_reason=reason
            )
    
    def unban_user(self, user_id: int):
        self.update_user(
            user_id,
            banned_until=None,
            permanent_ban=0,
            ban_reason=""
        )
    
    def add_rating(self, user_id: int, points: int):
        self.db.execute_query(
            "UPDATE users SET rating = rating + ? WHERE user_id = ?",
            (points, user_id)
        )
        
        cache_key = f'user_{user_id}'
        if cache_key in self.cache:
            del self.cache[cache_key]
    
    def get_top_users(self, limit: int = 10) -> List[dict]:
        results = self.db.execute_query(
            """SELECT user_id, username, first_name, rating, photos_count 
               FROM users WHERE rating > 0 ORDER BY rating DESC LIMIT ?""",
            (limit,)
        )
        
        return [dict(row) for row in results]
    
    def get_stats(self) -> dict:
        results = self.db.execute_query(
            """SELECT 
                COUNT(*) as total_users,
                SUM(CASE WHEN subscription_end > datetime('now') THEN 1 ELSE 0 END) as subscribers,
                SUM(CASE WHEN permanent_ban = 1 OR banned_until > datetime('now') THEN 1 ELSE 0 END) as banned,
                AVG(rating) as avg_rating,
                SUM(photos_count) as total_photos
               FROM users"""
        )
        
        if results:
            return dict(results[0])
        return {}
# ================== МЕНЕДЖЕР ФОТОГРАФИЙ ==================
class PhotoManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.cache = cachetools.TTLCache(maxsize=200, ttl=300)
    
    def add_photo(self, file_id: str, user_id: int, username: str, tags: List[str] = None):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tags_json = json.dumps(tags) if tags else '[]'
        metadata = json.dumps({'source': 'user', 'upload_time': now})
        
        photo_id = self.db.execute_query(
            """INSERT INTO photos 
               (file_id, user_id, username, date, status, tags, metadata) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (file_id, user_id, username, now, PhotoStatus.PENDING.value, tags_json, metadata)
        )
        
        self.db.execute_query(
            """INSERT INTO moderation_queue 
               (content_type, content_id, priority, date, status) 
               VALUES (?, ?, ?, ?, ?)""",
            ('photo', photo_id, 0, now, 'pending')
        )
        
        return photo_id
    
    def approve_photo(self, photo_id: int, admin_id: int, comment: str = ""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.db.execute_query(
            """UPDATE photos 
               SET status = ?, moderated_by = ?, moderation_date = ?, moderation_comment = ? 
               WHERE id = ?""",
            (PhotoStatus.APPROVED.value, admin_id, now, comment, photo_id)
        )
        
        result = self.db.execute_query(
            "SELECT user_id FROM photos WHERE id = ?",
            (photo_id,)
        )
        if result:
            user_id = result[0]['user_id']
            self.db.execute_query(
                "UPDATE users SET photos_count = photos_count + 1 WHERE user_id = ?",
                (user_id,)
            )
        
        self.db.execute_query(
            "DELETE FROM moderation_queue WHERE content_type = 'photo' AND content_id = ?",
            (photo_id,)
        )
        
        cache_key = f'pending_photos'
        if cache_key in self.cache:
            del self.cache[cache_key]
    
    def reject_photo(self, photo_id: int, admin_id: int, reason: str = ""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.db.execute_query(
            """UPDATE photos 
               SET status = ?, moderated_by = ?, moderation_date = ?, moderation_comment = ? 
               WHERE id = ?""",
            (PhotoStatus.REJECTED.value, admin_id, now, reason, photo_id)
        )
        
        self.db.execute_query(
            "DELETE FROM moderation_queue WHERE content_type = 'photo' AND content_id = ?",
            (photo_id,)
        )
        
        cache_key = f'pending_photos'
        if cache_key in self.cache:
            del self.cache[cache_key]
    
    def get_pending_photos(self) -> List[dict]:
        cache_key = 'pending_photos'
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        results = self.db.execute_query(
            """SELECT id, file_id, user_id, username, date, tags, metadata 
               FROM photos WHERE status = ? ORDER BY date""",
            (PhotoStatus.PENDING.value,)
        )
        
        photos = [dict(row) for row in results]
        self.cache[cache_key] = photos
        return photos
    
    def get_random_photo(self) -> Optional[str]:
        cache_key = 'random_photo'
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        results = self.db.execute_query(
            "SELECT file_id FROM photos WHERE status = ? ORDER BY RANDOM() LIMIT 1",
            (PhotoStatus.APPROVED.value,)
        )
        
        if results:
            file_id = results[0]['file_id']
            self.cache[cache_key] = file_id
            
            self.db.execute_query(
                "UPDATE photos SET views = views + 1 WHERE file_id = ?",
                (file_id,)
            )
            
            return file_id
        return None
    
    def get_photo_count(self) -> int:
        cache_key = 'photo_count'
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = self.db.execute_query(
            "SELECT COUNT(*) as count FROM photos WHERE status = ?",
            (PhotoStatus.APPROVED.value,)
        )
        
        count = result[0]['count'] if result else 0
        self.cache[cache_key] = count
        return count
    
    def like_photo(self, photo_id: int, user_id: int):
        self.db.execute_query(
            "UPDATE photos SET likes = likes + 1 WHERE id = ?",
            (photo_id,)
        )
    
    def dislike_photo(self, photo_id: int, user_id: int):
        self.db.execute_query(
            "UPDATE photos SET dislikes = dislikes + 1 WHERE id = ?",
            (photo_id,)
        )
    
    def get_photo_stats(self) -> dict:
        results = self.db.execute_query(
            """SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                SUM(likes) as total_likes,
                SUM(dislikes) as total_dislikes,
                SUM(views) as total_views
               FROM photos"""
        )
        
        if results:
            return dict(results[0])
        return {}

# ================== МЕНЕДЖЕР ФАКТОВ ==================
class FactManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.cache = cachetools.TTLCache(maxsize=50, ttl=3600)
    
    def add_fact(self, fact: str, category: str, added_by: int, language: str = 'ru'):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        fact_id = self.db.execute_query(
            """INSERT INTO daily_facts (fact, category, added_by, date, language) 
               VALUES (?, ?, ?, ?, ?)""",
            (fact, category, added_by, now, language)
        )
        
        cache_key = f'random_fact_{language}'
        if cache_key in self.cache:
            del self.cache[cache_key]
        
        return fact_id
    
    def get_random_fact(self, language: str = 'ru') -> Optional[Tuple[str, str]]:
        cache_key = f'random_fact_{language}'
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = self.db.execute_query(
            "SELECT fact, category FROM daily_facts WHERE language = ? ORDER BY RANDOM() LIMIT 1",
            (language,)
        )
        
        if result:
            fact = (result[0]['fact'], result[0]['category'])
            self.cache[cache_key] = fact
            return fact
        return None
    
    def get_facts_count(self) -> int:
        cache_key = 'facts_count'
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = self.db.execute_query("SELECT COUNT(*) as count FROM daily_facts")
        count = result[0]['count'] if result else 0
        self.cache[cache_key] = count
        return count
    
    def like_fact(self, fact_id: int):
        self.db.execute_query(
            "UPDATE daily_facts SET likes = likes + 1 WHERE id = ?",
            (fact_id,)
        )

# ================== МЕНЕДЖЕР ОПРОСОВ ==================
class PollManager:
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def create_poll(self, question: str, options: List[str], created_by: int, 
                    hours_duration: int = 24, anonymous: bool = True, multiple: bool = False) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (datetime.now() + timedelta(hours=hours_duration)).strftime("%Y-%m-%d %H:%M:%S")
        options_str = '|'.join(options)
        
        poll_id = self.db.execute_query(
            """INSERT INTO polls 
               (question, options, created_by, date, expires_at, is_anonymous, multiple_choice) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (question, options_str, created_by, now, expires_at, int(anonymous), int(multiple))
        )
        
        return poll_id
    
    def get_active_polls(self) -> List[dict]:
        results = self.db.execute_query(
            """SELECT id, question, options, created_by, date, expires_at, 
                      is_anonymous, multiple_choice, total_votes 
               FROM polls 
               WHERE is_active = 1 AND expires_at > datetime('now') 
               ORDER BY date DESC"""
        )
        
        polls = []
        for row in results:
            poll = dict(row)
            poll['options'] = poll['options'].split('|')
            polls.append(poll)
        
        return polls
    
    def vote(self, poll_id: int, user_id: int, option_index: int) -> bool:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            poll_result = self.db.execute_query(
                "SELECT expires_at, multiple_choice FROM polls WHERE id = ? AND is_active = 1",
                (poll_id,)
            )
            
            if not poll_result:
                return False
            
            expires_at = datetime.strptime(poll_result[0]['expires_at'], "%Y-%m-%d %H:%M:%S")
            if expires_at < datetime.now():
                return False
            
            if not poll_result[0]['multiple_choice']:
                existing = self.db.execute_query(
                    "SELECT 1 FROM poll_votes WHERE poll_id = ? AND user_id = ?",
                    (poll_id, user_id)
                )
                if existing:
                    return False
            
            self.db.execute_query(
                "INSERT INTO poll_votes (poll_id, user_id, option_index, date) VALUES (?, ?, ?, ?)",
                (poll_id, user_id, option_index, now)
            )
            
            self.db.execute_query(
                "UPDATE polls SET total_votes = total_votes + 1 WHERE id = ?",
                (poll_id,)
            )
            
            return True
        except Exception:
            return False
    
    def get_results(self, poll_id: int) -> Optional[dict]:
        poll_result = self.db.execute_query(
            "SELECT question, options, total_votes FROM polls WHERE id = ?",
            (poll_id,)
        )
        
        if not poll_result:
            return None
        
        question = poll_result[0]['question']
        options = poll_result[0]['options'].split('|')
        total_votes = poll_result[0]['total_votes']
        
        votes_result = self.db.execute_query(
            "SELECT option_index, COUNT(*) as count FROM poll_votes WHERE poll_id = ? GROUP BY option_index",
            (poll_id,)
        )
        
        votes = {row['option_index']: row['count'] for row in votes_result}
        
        results = []
        for i, option in enumerate(options):
            count = votes.get(i, 0)
            percentage = (count / total_votes * 100) if total_votes > 0 else 0
            results.append({
                'option': option,
                'count': count,
                'percentage': percentage
            })
        
        return {
            'question': question,
            'results': results,
            'total_votes': total_votes
        }
    
    def close_poll(self, poll_id: int):
        self.db.execute_query(
            "UPDATE polls SET is_active = 0 WHERE id = ?",
            (poll_id,)
        )
# ================== ИГРЫ НА ПЕРЕМЕНЕ ==================
class GameSession:
    def __init__(self, game_type: GameType, user_id: int):
        self.game_type = game_type
        self.user_id = user_id
        self.score = 0
        self.level = 1
        self.lives = 3
        self.state = {}
        self.start_time = datetime.now()
        self.last_move = datetime.now()
        self.history = []
        self._init_game()
    
    def _init_game(self):
        if self.game_type == GameType.TIC_TAC_TOE:
            self.state = {
                'board': [' '] * 9,
                'current_player': 'X',
                'winner': None
            }
        elif self.game_type == GameType.GUESS_NUMBER:
            self.state = {
                'number': random.randint(1, 100),
                'attempts': 0,
                'min_range': 1,
                'max_range': 100
            }
        elif self.game_type == GameType.WORD_GAME:
            words = ['python', 'telegram', 'bot', 'developer', 'coding']
            self.state = {
                'word': random.choice(words),
                'guessed': [],
                'attempts_left': 6
            }
        elif self.game_type == GameType.MATH_QUIZ:
            self.state = self._generate_math_problem()
        elif self.game_type == GameType.MEMORY:
            numbers = list(range(1, 5)) * 2
            random.shuffle(numbers)
            self.state = {
                'cards': numbers,
                'revealed': [False] * 8,
                'pairs_found': 0,
                'first_card': None
            }
        elif self.game_type == GameType.RPS:
            self.state = {
                'wins': 0,
                'losses': 0,
                'ties': 0
            }
        elif self.game_type == GameType.HANGMAN:
            words = ['программирование', 'телеграм', 'разработка', 'искусство']
            self.state = {
                'word': random.choice(words),
                'guessed_letters': [],
                'wrong_guesses': 0,
                'max_wrong': 6
            }
        elif self.game_type == GameType.TRIVIA:
            self.state = {
                'questions': self._get_trivia_questions(),
                'current': 0,
                'correct': 0
            }
        elif self.game_type == GameType.SNAKE:
            self.state = {
                'snake': [(5, 5)],
                'food': (random.randint(0, 9), random.randint(0, 9)),
                'direction': 'RIGHT',
                'score': 0,
                'game_over': False
            }
    
    def _generate_math_problem(self):
        if self.level <= 3:
            a = random.randint(1, 10)
            b = random.randint(1, 10)
            op = random.choice(['+', '-'])
        elif self.level <= 6:
            a = random.randint(10, 50)
            b = random.randint(10, 50)
            op = random.choice(['+', '-', '*'])
        else:
            a = random.randint(50, 100)
            b = random.randint(50, 100)
            op = random.choice(['+', '-', '*', '/'])
        
        if op == '+':
            answer = a + b
        elif op == '-':
            answer = a - b
        elif op == '*':
            answer = a * b
        else:
            answer = round(a / b, 2)
        
        return {
            'a': a,
            'b': b,
            'op': op,
            'answer': answer,
            'attempts': 0
        }
    
    def _get_trivia_questions(self):
        return [
            {
                'question': 'Столица Франции?',
                'options': ['Париж', 'Лондон', 'Берлин', 'Мадрид'],
                'correct': 0
            },
            {
                'question': 'Сколько планет в Солнечной системе?',
                'options': ['7', '8', '9', '10'],
                'correct': 1
            },
            {
                'question': 'Кто написал "Война и мир"?',
                'options': ['Достоевский', 'Толстой', 'Пушкин', 'Чехов'],
                'correct': 1
            },
            {
                'question': 'Какой язык программирования используется для этого бота?',
                'options': ['Java', 'Python', 'C++', 'JavaScript'],
                'correct': 1
            }
        ]
    
    def make_move(self, move):
        self.last_move = datetime.now()
        
        if self.game_type == GameType.TIC_TAC_TOE:
            return self._process_tic_tac_toe(move)
        elif self.game_type == GameType.GUESS_NUMBER:
            return self._process_guess_number(move)
        elif self.game_type == GameType.WORD_GAME:
            return self._process_word_game(move)
        elif self.game_type == GameType.MATH_QUIZ:
            return self._process_math_quiz(move)
        elif self.game_type == GameType.MEMORY:
            return self._process_memory(move)
        elif self.game_type == GameType.RPS:
            return self._process_rps(move)
        elif self.game_type == GameType.HANGMAN:
            return self._process_hangman(move)
        elif self.game_type == GameType.TRIVIA:
            return self._process_trivia(move)
        elif self.game_type == GameType.SNAKE:
            return self._process_snake(move)
    
    def _process_tic_tac_toe(self, position):
        try:
            pos = int(position)
        except:
            return {'valid': False, 'message': 'Введите число от 0 до 8'}
        
        board = self.state['board']
        if pos < 0 or pos > 8 or board[pos] != ' ':
            return {'valid': False, 'message': 'Недопустимый ход'}
        
        board[pos] = self.state['current_player']
        
        winning_combinations = [
            [0,1,2], [3,4,5], [6,7,8],
            [0,3,6], [1,4,7], [2,5,8],
            [0,4,8], [2,4,6]
        ]
        
        for combo in winning_combinations:
            if board[combo[0]] == board[combo[1]] == board[combo[2]] != ' ':
                self.state['winner'] = board[combo[0]]
                self.score += 10
                return {
                    'valid': True,
                    'game_over': True,
                    'winner': self.state['winner'],
                    'board': self._format_tic_tac_toe_board()
                }
        
        if ' ' not in board:
            self.score += 5
            return {
                'valid': True,
                'game_over': True,
                'winner': 'tie',
                'board': self._format_tic_tac_toe_board()
            }
        
        self.state['current_player'] = 'O' if self.state['current_player'] == 'X' else 'X'
        
        return {
            'valid': True,
            'game_over': False,
            'board': self._format_tic_tac_toe_board(),
            'current_player': self.state['current_player']
        }
    
    def _format_tic_tac_toe_board(self):
        board = self.state['board']
        return f"""
{board[0]} | {board[1]} | {board[2]}
---------
{board[3]} | {board[4]} | {board[5]}
---------
{board[6]} | {board[7]} | {board[8]}
        """
    
    def _process_guess_number(self, guess):
        try:
            g = int(guess)
        except:
            return {'valid': False, 'message': 'Введите число'}
        
        self.state['attempts'] += 1
        number = self.state['number']
        
        if g == number:
            points = max(100 - self.state['attempts'] * 5, 10)
            self.score += points
            return {
                'valid': True,
                'game_over': True,
                'message': f'✅ Правильно! Число {number}\nПопыток: {self.state["attempts"]}\n+{points} очков',
                'number': number
            }
        elif g < number:
            self.state['min_range'] = max(self.state['min_range'], g + 1)
            return {
                'valid': True,
                'game_over': False,
                'message': f'⬆️ Загаданное число больше {g}',
                'range': f'{self.state["min_range"]}-{self.state["max_range"]}'
            }
        else:
            self.state['max_range'] = min(self.state['max_range'], g - 1)
            return {
                'valid': True,
                'game_over': False,
                'message': f'⬇️ Загаданное число меньше {g}',
                'range': f'{self.state["min_range"]}-{self.state["max_range"]}'
            }
    
    def _process_word_game(self, letter):
        if len(letter) != 1 or not letter.isalpha():
            return {'valid': False, 'message': 'Введите одну букву'}
        
        letter = letter.lower()
        word = self.state['word']
        
        if letter in self.state['guessed']:
            return {'valid': False, 'message': 'Эта буква уже была'}
        
        self.state['guessed'].append(letter)
        
        if letter in word:
            self.score += 2
            display = ''.join([l if l in self.state['guessed'] else '_' for l in word])
            if '_' not in display:
                self.score += 10
                return {
                    'valid': True,
                    'game_over': True,
                    'message': f'🎉 Победа! Слово: {word}\n+{self.score} очков'
                }
            return {
                'valid': True,
                'message': f'✅ Буква {letter} есть!\nСлово: {display}'
            }
        else:
            self.state['attempts_left'] -= 1
            if self.state['attempts_left'] <= 0:
                self.lives -= 1
                return {
                    'valid': True,
                    'game_over': self.lives <= 0,
                    'message': f'❌ Буквы {letter} нет. Слово: {word}'
                }
            return {
                'valid': True,
                'message': f'❌ Буквы {letter} нет. Осталось попыток: {self.state["attempts_left"]}'
            }
    
    def _process_math_quiz(self, answer):
        try:
            user_answer = float(answer)
            correct = self.state['answer']
            
            if abs(user_answer - correct) < 0.01:
                self.score += 10
                self.level += 0.5
                self.state = self._generate_math_problem()
                return {
                    'valid': True,
                    'correct': True,
                    'message': f'✅ Правильно! +10 очков\nНовый пример:\n{self.state["a"]} {self.state["op"]} {self.state["b"]} = ?'
                }
            else:
                self.state['attempts'] += 1
                if self.state['attempts'] >= 3:
                    self.lives -= 1
                    return {
                        'valid': True,
                        'correct': False,
                        'game_over': self.lives <= 0,
                        'message': f'❌ Неправильно. Правильный ответ: {correct}'
                    }
                return {
                    'valid': True,
                    'correct': False,
                    'message': f'❌ Неправильно. Осталось попыток: {3 - self.state["attempts"]}'
                }
        except ValueError:
            return {'valid': False, 'message': 'Введите число'}
    
    def _process_memory(self, card_index):
        try:
            idx = int(card_index) - 1
        except:
            return {'valid': False, 'message': 'Введите номер карты (1-8)'}
        
        cards = self.state['cards']
        revealed = self.state['revealed']
        
        if idx < 0 or idx >= len(cards) or revealed[idx]:
            return {'valid': False, 'message': 'Недопустимый ход'}
        
        revealed[idx] = True
        
        if self.state['first_card'] is None:
            self.state['first_card'] = idx
            return {
                'valid': True,
                'message': f'Карта {idx + 1}: {cards[idx]}',
                'waiting': True
            }
        else:
            first = self.state['first_card']
            self.state['first_card'] = None
            
            if cards[first] == cards[idx]:
                self.state['pairs_found'] += 1
                self.score += 10
                
                if self.state['pairs_found'] == len(cards) // 2:
                    return {
                        'valid': True,
                        'game_over': True,
                        'message': f'🎉 Победа! Найдено {self.state["pairs_found"]} пар\n+{self.score} очков'
                    }
                
                return {
                    'valid': True,
                    'message': f'✅ Пара найдена! Карта {first + 1} = {cards[first]}, Карта {idx + 1} = {cards[idx]}\nНайдено пар: {self.state["pairs_found"]}'
                }
            else:
                revealed[first] = False
                revealed[idx] = False
                return {
                    'valid': True,
                    'message': f'❌ Не пара. Карта {first + 1}: {cards[first]}, Карта {idx + 1}: {cards[idx]}'
                }
    
    def _process_rps(self, choice):
        choices = ['камень', 'ножницы', 'бумага']
        computer = random.choice(choices)
        
        if choice.lower() not in choices:
            return {'valid': False, 'message': 'Выберите: камень, ножницы или бумага'}
        
        result = ''
        if choice.lower() == computer:
            self.state['ties'] += 1
            result = 'Ничья'
        elif (
            (choice.lower() == 'камень' and computer == 'ножницы') or
            (choice.lower() == 'ножницы' and computer == 'бумага') or
            (choice.lower() == 'бумага' and computer == 'камень')
        ):
            self.state['wins'] += 1
            self.score += 5
            result = 'Вы выиграли!'
        else:
            self.state['losses'] += 1
            result = 'Вы проиграли'
        
        stats = f"Побед: {self.state['wins']}, Поражений: {self.state['losses']}, Ничьих: {self.state['ties']}"
        
        return {
            'valid': True,
            'message': f'Вы: {choice}\nКомпьютер: {computer}\n{result}\n\n{stats}'
        }
    
    def _process_hangman(self, letter):
        if len(letter) != 1 or not letter.isalpha():
            return {'valid': False, 'message': 'Введите одну букву'}
        
        letter = letter.lower()
        word = self.state['word']
        
        if letter in self.state['guessed_letters']:
            return {'valid': False, 'message': 'Эта буква уже была'}
        
        self.state['guessed_letters'].append(letter)
        
        if letter in word:
            self.score += 3
            display = ''.join([l if l in self.state['guessed_letters'] else '_' for l in word])
            
            if '_' not in display:
                self.score += 20
                return {
                    'valid': True,
                    'game_over': True,
                    'message': f'🎉 Победа! Слово: {word}\n+{self.score} очков'
                }
            
            return {
                'valid': True,
                'message': f'✅ Буква {letter} есть!\nСлово: {display}'
            }
        else:
            self.state['wrong_guesses'] += 1
            
            if self.state['wrong_guesses'] >= self.state['max_wrong']:
                self.lives -= 1
                return {
                    'valid': True,
                    'game_over': self.lives <= 0,
                    'message': f'❌ Игра окончена! Слово: {word}'
                }
            
            return {
                'valid': True,
                'message': f'❌ Буквы {letter} нет\nОсталось попыток: {self.state["max_wrong"] - self.state["wrong_guesses"]}'
            }
    
    def _process_trivia(self, answer_index):
        try:
            idx = int(answer_index)
        except:
            return {'valid': False, 'message': 'Введите номер ответа'}
        
        current = self.state['current']
        questions = self.state['questions']
        
        if idx < 0 or idx >= len(questions[current]['options']):
            return {'valid': False, 'message': 'Неверный номер ответа'}
        
        if idx == questions[current]['correct']:
            self.state['correct'] += 1
            self.score += 10
            result = '✅ Правильно!'
        else:
            correct_answer = questions[current]['options'][questions[current]['correct']]
            result = f'❌ Неправильно. Правильный ответ: {correct_answer}'
        
        self.state['current'] += 1
        
        if self.state['current'] >= len(questions):
            return {
                'valid': True,
                'game_over': True,
                'message': f'🎉 Игра окончена!\nПравильных ответов: {self.state["correct"]}/{len(questions)}\n+{self.score} очков'
            }
        
        next_q = questions[self.state['current']]
        options_text = '\n'.join([f"{i}. {opt}" for i, opt in enumerate(next_q['options'])])
        
        return {
            'valid': True,
            'message': f"{result}\n\nСледующий вопрос:\n{next_q['question']}\n\n{options_text}"
        }
    
    def _process_snake(self, direction):
        direction = direction.upper()
        if direction not in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
            return {'valid': False, 'message': 'Используйте: UP, DOWN, LEFT, RIGHT'}
        
        if self.state['game_over']:
            return {'valid': False, 'message': 'Игра окончена. Начните новую'}
        
        opposites = {'UP': 'DOWN', 'DOWN': 'UP', 'LEFT': 'RIGHT', 'RIGHT': 'LEFT'}
        if direction in opposites and direction != opposites[self.state['direction']]:
            self.state['direction'] = direction
        
        head = self.state['snake'][0]
        if self.state['direction'] == 'RIGHT':
            new_head = (head[0] + 1, head[1])
        elif self.state['direction'] == 'LEFT':
            new_head = (head[0] - 1, head[1])
        elif self.state['direction'] == 'UP':
            new_head = (head[0], head[1] - 1)
        else:
            new_head = (head[0], head[1] + 1)
        
        if new_head[0] < 0 or new_head[0] >= 10 or new_head[1] < 0 or new_head[1] >= 10:
            self.state['game_over'] = True
            return {
                'valid': True,
                'game_over': True,
                'message': f'💥 Столкновение со стеной!\nСчет: {self.state["score"]}'
            }
        
        if new_head in self.state['snake'][1:]:
            self.state['game_over'] = True
            return {
                'valid': True,
                'game_over': True,
                'message': f'💥 Столкновение с собой!\nСчет: {self.state["score"]}'
            }
        
        if new_head == self.state['food']:
            self.state['snake'].insert(0, new_head)
            self.state['score'] += 10
            self.score += 10
            
            while True:
                new_food = (random.randint(0, 9), random.randint(0, 9))
                if new_food not in self.state['snake']:
                    self.state['food'] = new_food
                    break
        else:
            self.state['snake'].insert(0, new_head)
            self.state['snake'].pop()
        
        board = self._draw_snake_board()
        
        return {
            'valid': True,
            'message': f"{board}\n\nСчет: {self.state['score']}",
            'game_over': False
        }
    
    def _draw_snake_board(self):
        board = [['⬛' for _ in range(10)] for _ in range(10)]
        
        for i, segment in enumerate(self.state['snake']):
            x, y = segment
            if i == 0:
                board[y][x] = '🐍'
            else:
                board[y][x] = '🟩'
        
        fx, fy = self.state['food']
        board[fy][fx] = '🍎'
        
        return '\n'.join([''.join(row) for row in board])

class GamesManager:
    def __init__(self, db):
        self.db = db
        self.active_games = {}
        self.high_scores = cachetools.TTLCache(maxsize=100, ttl=3600)
    
    def start_game(self, game_type: GameType, user_id: int) -> GameSession:
        session = GameSession(game_type, user_id)
        self.active_games[f"{user_id}_{game_type.value}"] = session
        return session
    
    def get_game(self, user_id: int, game_type: GameType) -> Optional[GameSession]:
        return self.active_games.get(f"{user_id}_{game_type.value}")
    
    def end_game(self, user_id: int, game_type: GameType, session: GameSession):
        key = f"{user_id}_{game_type.value}"
        if key in self.active_games:
            del self.active_games[key]
        
        duration = (datetime.now() - session.start_time).seconds
        self.db.execute_query(
            """INSERT INTO game_scores 
               (user_id, game_type, score, level, date, duration) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, game_type.value, session.score, session.level,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), duration)
        )
        
        stats = self.get_user_stats(user_id, game_type)
        self.db.execute_query(
            """INSERT OR REPLACE INTO game_stats 
               (user_id, game_type, games_played, total_score, highest_score, wins, losses) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, game_type.value,
             stats['games_played'] + 1,
             stats['total_score'] + session.score,
             max(stats['highest_score'], session.score),
             stats['wins'] + (1 if session.score > 0 else 0),
             stats['losses'] + (1 if session.score == 0 else 0))
        )
    
    def get_user_stats(self, user_id: int, game_type: GameType) -> dict:
        result = self.db.execute_query(
            "SELECT * FROM game_stats WHERE user_id = ? AND game_type = ?",
            (user_id, game_type.value)
        )
        
        if result:
            return dict(result[0])
        return {
            'games_played': 0,
            'total_score': 0,
            'highest_score': 0,
            'wins': 0,
            'losses': 0
        }
    
    def get_leaderboard(self, game_type: GameType, limit: int = 10) -> List[dict]:
        cache_key = f"leaderboard_{game_type.value}"
        if cache_key in self.high_scores:
            return self.high_scores[cache_key]
        
        result = self.db.execute_query(
            """SELECT user_id, score, date 
               FROM game_scores 
               WHERE game_type = ? 
               ORDER BY score DESC 
               LIMIT ?""",
            (game_type.value, limit)
        )
        
        leaderboard = [dict(row) for row in result]
        self.high_scores[cache_key] = leaderboard
        return leaderboard
# ================== КУРС ВАЛЮТ ==================
class CurrencyManager:
    def __init__(self):
        self.cache = cachetools.TTLCache(maxsize=10, ttl=3600)
        self.rates = CurrencyRates()
        self.supported_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'KZT']
    
    def get_exchange_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        cache_key = f"{from_currency}_{to_currency}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            rate = self.rates.get_rate(from_currency, to_currency)
            self.cache[cache_key] = rate
            return rate
        except:
            return None
    
    def convert_currency(self, amount: float, from_currency: str, to_currency: str) -> Optional[float]:
        rate = self.get_exchange_rate(from_currency, to_currency)
        if rate:
            return amount * rate
        return None
    
    def get_usd_rate(self) -> Optional[float]:
        return self.get_exchange_rate('USD', 'RUB')
    
    def get_eur_rate(self) -> Optional[float]:
        return self.get_exchange_rate('EUR', 'RUB')
    
    def get_crypto_price(self, crypto: str) -> Optional[float]:
        try:
            ticker = yf.Ticker(f"{crypto}-USD")
            data = ticker.history(period="1d")
            return float(data['Close'].iloc[-1]) if not data.empty else None
        except:
            return None
    
    def format_rate_message(self) -> str:
        usd = self.get_usd_rate()
        eur = self.get_eur_rate()
        
        message = "💱 **Курсы валют**\n\n"
        
        if usd:
            message += f"🇺🇸 USD: {usd:.2f} ₽\n"
        if eur:
            message += f"🇪🇺 EUR: {eur:.2f} ₽\n"
        
        btc = self.get_crypto_price('BTC')
        eth = self.get_crypto_price('ETH')
        
        if btc:
            message += f"₿ Bitcoin: ${btc:,.2f}\n"
        if eth:
            message += f"Ξ Ethereum: ${eth:,.2f}\n"
        
        return message

# ================== РАСПИСАНИЕ УРОКОВ ==================
class ScheduleManager:
    def __init__(self, db):
        self.db = db
        self.cache = cachetools.TTLCache(maxsize=10, ttl=3600)
    
    def add_lesson(self, day: int, number: int, subject: str, teacher: str = None,
                   room: str = None, start: str = None, end: str = None):
        self.db.execute_query(
            """INSERT INTO schedule 
               (day_of_week, lesson_number, subject, teacher, room, start_time, end_time) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (day, number, subject, teacher, room, start, end)
        )
        self.cache.clear()
    
    def get_schedule_for_day(self, day: int) -> List[dict]:
        cache_key = f"schedule_day_{day}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = self.db.execute_query(
            """SELECT * FROM schedule 
               WHERE day_of_week = ? AND is_active = 1 
               ORDER BY lesson_number""",
            (day,)
        )
        
        schedule = [dict(row) for row in result]
        self.cache[cache_key] = schedule
        return schedule
    
    def get_today_schedule(self) -> List[dict]:
        today = datetime.now().weekday()
        return self.get_schedule_for_day(today)
    
    def format_schedule(self, day: int) -> str:
        days = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        schedule = self.get_schedule_for_day(day)
        
        if not schedule:
            return f"📅 **{days[day]}**\n\nУроков нет"
        
        message = f"📅 **{days[day]}**\n\n"
        
        for lesson in schedule:
            time_info = ""
            if lesson['start_time'] and lesson['end_time']:
                time_info = f" ({lesson['start_time']}-{lesson['end_time']})"
            
            message += f"{lesson['lesson_number']}. {lesson['subject']}{time_info}\n"
            
            if lesson['teacher']:
                message += f"   👨‍🏫 {lesson['teacher']}\n"
            if lesson['room']:
                message += f"   🏫 Каб. {lesson['room']}\n"
            message += "\n"
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        subs = self.db.execute_query(
            "SELECT * FROM substitutions WHERE date = ? ORDER BY lesson_number",
            (today_str,)
        )
        
        if subs:
            message += "\n⚠️ **Замены:**\n"
            for sub in subs:
                message += f"{sub['lesson_number']}. {sub['original_subject']} → {sub['new_subject']}"
                if sub['reason']:
                    message += f" ({sub['reason']})"
                message += "\n"
        
        return message
    
    def add_substitution(self, date_str: str, lesson: int, original: str, new: str, reason: str = ""):
        self.db.execute_query(
            """INSERT INTO substitutions 
               (date, lesson_number, original_subject, new_subject, reason) 
               VALUES (?, ?, ?, ?, ?)""",
            (date_str, lesson, original, new, reason)
        )
        self.cache.clear()
    
    def add_homework(self, subject: str, description: str, due_date: str, 
                     attachments: str = None, created_by: int = None):
        self.db.execute_query(
            """INSERT INTO homework 
               (subject, description, due_date, attachments, created_by, date) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (subject, description, due_date, attachments, created_by,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
    
    def get_homework(self, days_ahead: int = 7) -> List[dict]:
        end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        result = self.db.execute_query(
            """SELECT * FROM homework 
               WHERE due_date <= ? 
               ORDER BY due_date""",
            (end_date,)
        )
        
        return [dict(row) for row in result]
    
    def format_homework(self) -> str:
        homework = self.get_homework()
        
        if not homework:
            return "📚 Домашнее задание на ближайшие дни отсутствует"
        
        message = "📚 **Домашнее задание**\n\n"
        
        for hw in homework:
            due = datetime.strptime(hw['due_date'], "%Y-%m-%d").strftime("%d.%m")
            message += f"📅 {due} - **{hw['subject']}**\n"
            message += f"{hw['description']}\n\n"
        
        return message

# ================== МЕНЕДЖЕР УВЕДОМЛЕНИЙ ==================
class NotificationManager:
    def __init__(self, db: DatabaseManager, bot):
        self.db = db
        self.bot = bot
        self.queue = Queue()
        self._start_worker()
    
    def _start_worker(self):
        def worker():
            while True:
                notification = self.queue.get()
                if notification is None:
                    break
                try:
                    self._send_notification(notification)
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
                self.queue.task_done()
        
        Thread(target=worker, daemon=True).start()
    
    def _send_notification(self, notification: dict):
        try:
            text = f"**{notification['title']}**\n\n{notification['content']}"
            
            if notification.get('data'):
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Перейти", callback_data=notification['data'].get('callback', 'main_menu'))]
                ])
            else:
                keyboard = None
            
            self.bot.send_message(
                chat_id=notification['user_id'],
                text=text,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            
            self.db.execute_query(
                "UPDATE notifications SET read = 1 WHERE id = ?",
                (notification['id'],)
            )
        except Exception as e:
            logger.error(f"Failed to send notification to {notification['user_id']}: {e}")
    
    def add_notification(self, user_id: int, title: str, content: str, 
                        notification_type: str = 'info', data: dict = None):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data_json = json.dumps(data) if data else '{}'
        
        notification_id = self.db.execute_query(
            """INSERT INTO notifications 
               (user_id, type, title, content, date, data) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, notification_type, title, content, now, data_json)
        )
        
        notification = {
            'id': notification_id,
            'user_id': user_id,
            'title': title,
            'content': content,
            'data': data
        }
        
        self.queue.put(notification)
    
    def broadcast(self, message: str, admin_id: int, parse_mode: str = 'Markdown'):
        users = self.db.execute_query("SELECT user_id FROM users")
        total = len(users)
        
        broadcast_id = self.db.execute_query(
            """INSERT INTO broadcasts 
               (admin_id, message, date, status, total_count) 
               VALUES (?, ?, ?, ?, ?)""",
            (admin_id, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'in_progress', total)
        )
        
        sent = 0
        failed = 0
        
        for user in users:
            try:
                self.bot.send_message(
                    chat_id=user['user_id'],
                    text=f"📢 **Сообщение от администрации**\n\n{message}",
                    parse_mode=parse_mode
                )
                sent += 1
            except:
                failed += 1
            
            time.sleep(0.03)
        
        self.db.execute_query(
            """UPDATE broadcasts 
               SET status = 'completed', sent_count = ?, failed_count = ? 
               WHERE id = ?""",
            (sent, failed, broadcast_id)
        )
        
        return sent, failed

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def admin_required(func):
    @wraps(func)
    def wrapper(self, update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if not self.is_admin(user_id):
            update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        return func(self, update, context, *args, **kwargs)
    return wrapper

def not_banned(func):
    @wraps(func)
    def wrapper(self, update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        banned, reason = self.users.is_banned(user_id)
        if banned:
            update.message.reply_text(self.get_text(user_id, 'banned', reason=reason))
            return
        return func(self, update, context, *args, **kwargs)
    return wrapper
# ================== ОСНОВНОЙ КЛАСС БОТА ==================
class HomeworkBot:
    def __init__(self, token: str, admin_ids: List[int]):
        self.token = token
        self.admin_ids = admin_ids
        
        # Initialize managers
        self.db = DatabaseManager()
        self.users = UserManager(self.db)
        self.photos = PhotoManager(self.db)
        self.facts = FactManager(self.db)
        self.polls = PollManager(self.db)
        self.games = GamesManager(self.db)
        self.currency = CurrencyManager()
        self.schedule = ScheduleManager(self.db)
        
        # Initialize bot
        self.updater = Updater(token, use_context=True)
        self.dp = self.updater.dispatcher
        self.bot = self.updater.bot
        
        # Initialize notification manager
        self.notifications = NotificationManager(self.db, self.bot)
        
        # Register handlers
        self._register_handlers()
        
        # Start background tasks
        self._start_background_tasks()
    
    def _register_handlers(self):
        # Command handlers
        self.dp.add_handler(CommandHandler("start", self.cmd_start))
        self.dp.add_handler(CommandHandler("help", self.cmd_help))
        self.dp.add_handler(CommandHandler("menu", self.cmd_menu))
        self.dp.add_handler(CommandHandler("profile", self.cmd_profile))
        self.dp.add_handler(CommandHandler("stats", self.cmd_stats))
        self.dp.add_handler(CommandHandler("top", self.cmd_top))
        self.dp.add_handler(CommandHandler("fact", self.cmd_fact))
        self.dp.add_handler(CommandHandler("language", self.cmd_language))
        
        # Game commands
        self.dp.add_handler(CommandHandler("games", self.cmd_games))
        self.dp.add_handler(CommandHandler("play", self.cmd_play))
        self.dp.add_handler(CommandHandler("leaderboard", self.cmd_leaderboard))
        
        # Currency commands
        self.dp.add_handler(CommandHandler("rates", self.cmd_rates))
        self.dp.add_handler(CommandHandler("convert", self.cmd_convert))
        self.dp.add_handler(CommandHandler("crypto", self.cmd_crypto))
        
        # Schedule commands
        self.dp.add_handler(CommandHandler("schedule", self.cmd_schedule))
        self.dp.add_handler(CommandHandler("today", self.cmd_today))
        self.dp.add_handler(CommandHandler("tomorrow", self.cmd_tomorrow))
        self.dp.add_handler(CommandHandler("homework", self.cmd_homework_list))
        
        # Admin commands
        self.dp.add_handler(CommandHandler("admin", self.cmd_admin))
        self.dp.add_handler(CommandHandler("ban", self.cmd_ban))
        self.dp.add_handler(CommandHandler("unban", self.cmd_unban))
        self.dp.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        self.dp.add_handler(CommandHandler("add_admin", self.cmd_add_admin))
        self.dp.add_handler(CommandHandler("add_lesson", self.cmd_add_lesson))
        self.dp.add_handler(CommandHandler("add_substitution", self.cmd_add_substitution))
        self.dp.add_handler(CommandHandler("add_homework", self.cmd_add_homework))
        
        # Callback query handler
        self.dp.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Message handlers
        self.dp.add_handler(MessageHandler(Filters.photo, self.handle_photo))
        self.dp.add_handler(MessageHandler(Filters.text & ~Filters.command, self.handle_text))
        
        # Payment handler
        self.dp.add_handler(PreCheckoutQueryHandler(self.pre_checkout))
        self.dp.add_handler(MessageHandler(Filters.successful_payment, self.successful_payment))
        
        # Error handler
        self.dp.add_error_handler(self.error_handler)
    
    def _start_background_tasks(self):
        def cleanup_worker():
            while True:
                time.sleep(3600)
                self._cleanup_old_data()
        
        Thread(target=cleanup_worker, daemon=True).start()
    
    def _cleanup_old_data(self):
        try:
            expire_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute_query(
                "DELETE FROM photos WHERE date < ? AND status = 'approved'",
                (expire_date,)
            )
            
            old_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute_query(
                "DELETE FROM reports WHERE date < ? AND status != 'new'",
                (old_date,)
            )
            
            self.db.execute_query(
                "UPDATE polls SET is_active = 0 WHERE expires_at < datetime('now')"
            )
            
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def get_text(self, user_id: int, key: str, **kwargs) -> str:
        user = self.users.get_user(user_id)
        lang = user.language if user else Language.RU
        text = TRANSLATIONS[lang].get(key, key)
        return text.format(**kwargs)
    
    def is_admin(self, user_id: int) -> bool:
        if user_id in self.admin_ids:
            return True
        user = self.users.get_user(user_id)
        return user and user.role in [UserRole.ADMIN, UserRole.OWNER]
    
    def get_main_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton(self.get_text(user_id, 'homework'), callback_data="menu_hw")],
            [InlineKeyboardButton(self.get_text(user_id, 'games'), callback_data="menu_games")],
            [InlineKeyboardButton(self.get_text(user_id, 'currency'), callback_data="menu_currency")],
            [InlineKeyboardButton(self.get_text(user_id, 'schedule'), callback_data="menu_schedule")],
            [InlineKeyboardButton("📸 Отправить фото", callback_data="menu_photo")],
            [InlineKeyboardButton("🎲 Случайное фото", callback_data="menu_random")],
            [InlineKeyboardButton("⭐ Подписка", callback_data="menu_subscription")],
            [InlineKeyboardButton("📞 Связаться с админом", callback_data="menu_support")],
            [InlineKeyboardButton("📊 Мой профиль", callback_data="menu_profile")],
            [InlineKeyboardButton("🎯 Интересный факт", callback_data="menu_fact")],
            [InlineKeyboardButton("🌐 Сменить язык", callback_data="menu_language")],
        ]
        
        if self.is_admin(user_id):
            keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_menu")])
        
        return InlineKeyboardMarkup(keyboard)
    
    # ================== ОСНОВНЫЕ КОМАНДЫ ==================
    def cmd_start(self, update: Update, context: CallbackContext):
        user = update.effective_user
        
        existing = self.users.get_user(user.id)
        if not existing:
            self.users.create_user(update)
        
        banned, reason = self.users.is_banned(user.id)
        if banned:
            text = self.get_text(user.id, 'banned', date=user.banned_until, reason=reason)
            update.message.reply_text(text)
            return
        
        text = self.get_text(user.id, 'welcome', name=user.first_name)
        update.message.reply_text(text, reply_markup=self.get_main_keyboard(user.id))
    
    def cmd_help(self, update: Update, context: CallbackContext):
        help_text = """
📚 **Помощь по боту**

**Основные команды:**
/start - Запустить бота
/menu - Главное меню
/profile - Мой профиль
/fact - Случайный факт
/top - Топ пользователей
/language - Сменить язык

**Игры:**
/games - Список игр
/play <игра> - Начать игру
/leaderboard <игра> - Таблица лидеров

**Валюты:**
/rates - Курсы валют
/convert <сумма> <из> <в> - Конвертер
/crypto - Криптовалюты

**Расписание:**
/schedule [день] - Расписание
/today - На сегодня
/tomorrow - На завтра
/homework - Домашнее задание

**Функции:**
📸 Отправляйте фото - в галерею после модерации
🎲 Случайное фото - из галереи
⭐ Подписка - доступ к решенным ДЗ
📞 Связь с админом - задать вопрос
"""
        update.message.reply_text(help_text, parse_mode='Markdown')
    
    def cmd_menu(self, update: Update, context: CallbackContext):
        user = update.effective_user
        update.message.reply_text(self.get_text(user.id, 'main_menu'), 
                                 reply_markup=self.get_main_keyboard(user.id))
    
    def cmd_profile(self, update: Update, context: CallbackContext):
        user = update.effective_user
        user_data = self.users.get_user(user.id)
        
        if not user_data:
            user_data = self.users.create_user(update)
        
        subscription = "✅ Активна" if user_data.subscription_end and user_data.subscription_end > datetime.now() else "❌ Нет"
        join_date = user_data.join_date.strftime("%d.%m.%Y") if user_data.join_date else "Неизвестно"
        
        text = self.get_text(
            user.id, 'profile',
            rating=user_data.rating,
            photos=user_data.photos_count,
            subscription=subscription,
            join_date=join_date,
            user_id=user.id
        )
        
        if user_data.achievements:
            text += "\n\n**Достижения:**\n"
            for ach in user_data.achievements[:5]:
                text += f"🏆 {ach}\n"
        
        keyboard = [[InlineKeyboardButton(self.get_text(user.id, 'back'), callback_data="main_menu")]]
        update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    def cmd_stats(self, update: Update, context: CallbackContext):
        if not self.is_admin(update.effective_user.id):
            update.message.reply_text("❌ У вас нет прав")
            return
        
        user_stats = self.users.get_stats()
        photo_stats = self.photos.get_photo_stats()
        db_stats = self.db.get_stats()
        
        text = f"""
📊 **Статистика бота**

**Пользователи:**
👥 Всего: {user_stats.get('total_users', 0)}
⭐ Подписчиков: {user_stats.get('subscribers', 0)}
🚫 Забанено: {user_stats.get('banned', 0)}
📸 Всего фото: {user_stats.get('total_photos', 0)}
⭐ Средний рейтинг: {user_stats.get('avg_rating', 0):.1f}

**Фотографии:**
📸 Всего: {photo_stats.get('total', 0)}
⏳ На модерации: {photo_stats.get('pending', 0)}
✅ Одобрено: {photo_stats.get('approved', 0)}
❌ Отклонено: {photo_stats.get('rejected', 0)}
❤️ Лайков: {photo_stats.get('total_likes', 0)}
👁️ Просмотров: {photo_stats.get('total_views', 0)}

**База данных:**
💾 Кэш попаданий: {db_stats.get('cache_hits', 0)}
💾 Кэш промахов: {db_stats.get('cache_misses', 0)}
📝 Записей: {db_stats.get('write_operations', 0)}
🔄 Транзакций: {db_stats.get('transactions', 0)}
❌ Ошибок: {db_stats.get('errors', 0)}
"""
        
        update.message.reply_text(text, parse_mode='Markdown')
    
    def cmd_top(self, update: Update, context: CallbackContext):
        user = update.effective_user
        top_users = self.users.get_top_users(10)
        
        text = "🏆 **Топ пользователей**\n\n"
        
        for i, u in enumerate(top_users, 1):
            name = u['username'] or u['first_name'] or f"ID{u['user_id']}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
            text += f"{medal} {i}. {name} — {u['rating']} ⭐ ({u['photos_count']} фото)\n"
        
        keyboard = [[InlineKeyboardButton(self.get_text(user.id, 'back'), callback_data="main_menu")]]
        update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    def cmd_fact(self, update: Update, context: CallbackContext):
        user = update.effective_user
        user_data = self.users.get_user(user.id)
        lang = user_data.language.value if user_data else 'ru'
        
        fact_info = self.facts.get_random_fact(lang)
        
        if fact_info:
            fact, category = fact_info
            text = f"🎯 **Интересный факт**\n\n{fact}\n\n📚 Категория: {category}"
        else:
            text = "🎯 Факты пока не добавлены. Администраторы скоро добавят!"
        
        keyboard = [
            [InlineKeyboardButton(self.get_text(user.id, 'more'), callback_data="menu_fact")],
            [InlineKeyboardButton(self.get_text(user.id, 'back'), callback_data="main_menu")]
        ]
        update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    def cmd_language(self, update: Update, context: CallbackContext):
        keyboard = [
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇰🇿 Қазақша", callback_data="lang_kz")],
        ]
        
        update.message.reply_text("Выберите язык / Choose language / Тілді таңдаңыз:", 
                                 reply_markup=InlineKeyboardMarkup(keyboard))
    
    # ================== ИГРОВЫЕ КОМАНДЫ ==================
    def cmd_games(self, update: Update, context: CallbackContext):
        keyboard = [
            [InlineKeyboardButton("❌ Крестики-нолики", callback_data="game_tic_tac_toe")],
            [InlineKeyboardButton("🔢 Угадай число", callback_data="game_guess_number")],
            [InlineKeyboardButton("📝 Угадай слово", callback_data="game_word_game")],
            [InlineKeyboardButton("🧮 Математика", callback_data="game_math_quiz")],
            [InlineKeyboardButton("🧠 Память", callback_data="game_memory")],
            [InlineKeyboardButton("✂️ Камень-ножницы-бумага", callback_data="game_rps")],
            [InlineKeyboardButton("🎭 Виселица", callback_data="game_hangman")],
            [InlineKeyboardButton("❓ Викторина", callback_data="game_trivia")],
            [InlineKeyboardButton("🐍 Змейка", callback_data="game_snake")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
        ]
        
        update.message.reply_text(
            "🎮 **Игры на перемене**\n\nВыберите игру:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    def cmd_play(self, update: Update, context: CallbackContext):
        if not context.args:
            update.message.reply_text("Использование: /play <игра>\nНапример: /play tic_tac_toe")
            return
        
        game_name = context.args[0].lower()
        game_map = {
            'tic_tac_toe': GameType.TIC_TAC_TOE,
            'guess_number': GameType.GUESS_NUMBER,
            'word_game': GameType.WORD_GAME,
            'math': GameType.MATH_QUIZ,
            'memory': GameType.MEMORY,
            'rps': GameType.RPS,
            'hangman': GameType.HANGMAN,
            'trivia': GameType.TRIVIA,
            'snake': GameType.SNAKE
        }
        
        if game_name not in game_map:
            update.message.reply_text("❌ Игра не найдена. Список игр: /games")
            return
        
        game_type = game_map[game_name]
        session = self.games.start_game(game_type, update.effective_user.id)
        
        messages = {
            GameType.TIC_TAC_TOE: "❌ **Крестики-нолики**\n\nВыберите клетку (0-8):\n" + session._format_tic_tac_toe_board(),
            GameType.GUESS_NUMBER: "🔢 **Угадай число**\n\nЯ загадал число от 1 до 100. Попробуй угадать!",
            GameType.WORD_GAME: "📝 **Угадай слово**\n\nСлово состоит из 6 букв. Угадывайте по одной букве.",
            GameType.MATH_QUIZ: f"🧮 **Математика**\n\nРешите: {session.state['a']} {session.state['op']} {session.state['b']} = ?",
            GameType.MEMORY: "🧠 **Игра на память**\n\nЗапоминайте пары чисел. Выбирайте карты (1-8).",
            GameType.RPS: "✂️ **Камень-ножницы-бумага**\n\nВыберите: камень, ножницы или бумага",
            GameType.HANGMAN: "🎭 **Виселица**\n\nУгадывайте слово по буквам.",
            GameType.TRIVIA: "❓ **Викторина**\n\nОтвечайте на вопросы. Введите номер ответа.",
            GameType.SNAKE: "🐍 **Змейка**\n\nУправляйте змейкой (UP/DOWN/LEFT/RIGHT). Ешьте 🍎!"
        }
        
        update.message.reply_text(messages[game_type])
    
    def cmd_leaderboard(self, update: Update, context: CallbackContext):
        if not context.args:
            update.message.reply_text("Использование: /leaderboard <игра>\nНапример: /leaderboard tic_tac_toe")
            return
        
        game_name = context.args[0].lower()
        game_map = {
            'tic_tac_toe': GameType.TIC_TAC_TOE,
            'guess_number': GameType.GUESS_NUMBER,
            'word_game': GameType.WORD_GAME,
            'math': GameType.MATH_QUIZ,
            'memory': GameType.MEMORY,
            'rps': GameType.RPS,
            'hangman': GameType.HANGMAN,
            'trivia': GameType.TRIVIA,
            'snake': GameType.SNAKE
        }
        
        if game_name not in game_map:
            update.message.reply_text("❌ Игра не найдена")
            return
        
        game_type = game_map[game_name]
        leaderboard = self.games.get_leaderboard(game_type)
        
        if not leaderboard:
            update.message.reply_text("📊 В этой игре пока нет результатов")
            return
        
        text = f"🏆 **Таблица лидеров - {game_name}**\n\n"
        for i, entry in enumerate(leaderboard, 1):
            user_info = self.users.get_user(entry['user_id'])
            name = user_info.first_name if user_info else f"User {entry['user_id']}"
            text += f"{i}. {name} — {entry['score']} очков\n"
        
        update.message.reply_text(text, parse_mode='Markdown')
    # ================== КОМАНДЫ ВАЛЮТ ==================
    def cmd_rates(self, update: Update, context: CallbackContext):
        message = self.currency.format_rate_message()
        update.message.reply_text(message, parse_mode='Markdown')
    
    def cmd_convert(self, update: Update, context: CallbackContext):
        try:
            if len(context.args) < 3:
                update.message.reply_text(
                    "Использование: /convert <сумма> <из> <в>\n"
                    "Пример: /convert 100 USD RUB"
                )
                return
            
            amount = float(context.args[0])
            from_curr = context.args[1].upper()
            to_curr = context.args[2].upper()
            
            result = self.currency.convert_currency(amount, from_curr, to_curr)
            
            if result:
                update.message.reply_text(
                    f"💱 **Конвертация**\n\n"
                    f"{amount:,.2f} {from_curr} = {result:,.2f} {to_curr}"
                )
            else:
                update.message.reply_text("❌ Не удалось получить курс")
        except ValueError:
            update.message.reply_text("❌ Неверная сумма")
    
    def cmd_crypto(self, update: Update, context: CallbackContext):
        cryptos = ['BTC', 'ETH', 'BNB', 'SOL', 'ADA', 'DOT']
        
        message = "₿ **Криптовалюты**\n\n"
        
        for crypto in cryptos:
            price = self.currency.get_crypto_price(crypto)
            if price:
                message += f"{crypto}: ${price:,.2f}\n"
        
        update.message.reply_text(message, parse_mode='Markdown')
    
    # ================== КОМАНДЫ РАСПИСАНИЯ ==================
    def cmd_schedule(self, update: Update, context: CallbackContext):
        days = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
        
        if context.args:
            try:
                day = days.index(context.args[0].lower()[:2])
            except ValueError:
                update.message.reply_text(
                    "Использование: /schedule [день]\n"
                    "Дни: пн, вт, ср, чт, пт, сб, вс"
                )
                return
        else:
            day = datetime.now().weekday()
        
        schedule_text = self.schedule.format_schedule(day)
        update.message.reply_text(schedule_text, parse_mode='Markdown')
    
    def cmd_today(self, update: Update, context: CallbackContext):
        schedule_text = self.schedule.format_schedule(datetime.now().weekday())
        update.message.reply_text(schedule_text, parse_mode='Markdown')
    
    def cmd_tomorrow(self, update: Update, context: CallbackContext):
        tomorrow = (datetime.now().weekday() + 1) % 7
        schedule_text = self.schedule.format_schedule(tomorrow)
        update.message.reply_text(schedule_text, parse_mode='Markdown')
    
    def cmd_homework_list(self, update: Update, context: CallbackContext):
        homework_text = self.schedule.format_homework()
        update.message.reply_text(homework_text, parse_mode='Markdown')
    
    # ================== АДМИН-КОМАНДЫ ==================
    @admin_required
    def cmd_admin(self, update: Update, context: CallbackContext):
        keyboard = [
            [InlineKeyboardButton("📝 Изменить ДЗ", callback_data="admin_hw")],
            [InlineKeyboardButton("✅ Добавить решенное ДЗ", callback_data="admin_solved_hw")],
            [InlineKeyboardButton("📸 Модерация фото", callback_data="admin_moderate")],
            [InlineKeyboardButton("➕ Добавить факт", callback_data="admin_add_fact")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("📞 Сообщения", callback_data="admin_reports")],
            [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton("👁️ Слежка", callback_data="admin_tracking")],
            [InlineKeyboardButton("🚫 Бан", callback_data="admin_ban")],
            [InlineKeyboardButton("✅ Разбан", callback_data="admin_unban")],
            [InlineKeyboardButton("⭐ Выдать подписку", callback_data="admin_subscription")],
            [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton("❌ Удалить админа", callback_data="admin_remove")],
            [InlineKeyboardButton("📊 Управление рейтингом", callback_data="admin_rating")],
            [InlineKeyboardButton("📚 Добавить урок", callback_data="admin_add_lesson")],
            [InlineKeyboardButton("📅 Добавить замену", callback_data="admin_add_substitution")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
        ]
        
        update.message.reply_text(
            "👑 **Панель администратора**",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @admin_required
    def cmd_ban(self, update: Update, context: CallbackContext):
        try:
            args = context.args
            if len(args) < 1:
                update.message.reply_text("Использование: /ban <user_id> [часы] [причина]")
                return
            
            user_id = int(args[0])
            hours = int(args[1]) if len(args) > 1 else None
            reason = ' '.join(args[2:]) if len(args) > 2 else "Нарушение правил"
            
            self.users.ban_user(user_id, hours, reason)
            
            if hours:
                update.message.reply_text(f"✅ Пользователь {user_id} забанен на {hours} часов\nПричина: {reason}")
            else:
                update.message.reply_text(f"✅ Пользователь {user_id} забанен навсегда\nПричина: {reason}")
            
            try:
                text = self.get_text(user_id, 'banned' if hours else 'permanent_ban', 
                                   date=hours, reason=reason)
                context.bot.send_message(chat_id=user_id, text=text)
            except:
                pass
        except Exception as e:
            update.message.reply_text(f"❌ Ошибка: {e}")
    
    @admin_required
    def cmd_unban(self, update: Update, context: CallbackContext):
        try:
            args = context.args
            if len(args) < 1:
                update.message.reply_text("Использование: /unban <user_id>")
                return
            
            user_id = int(args[0])
            self.users.unban_user(user_id)
            update.message.reply_text(f"✅ Пользователь {user_id} разбанен")
        except Exception as e:
            update.message.reply_text(f"❌ Ошибка: {e}")
    
    @admin_required
    def cmd_broadcast(self, update: Update, context: CallbackContext):
        if not context.args:
            update.message.reply_text("Использование: /broadcast <сообщение>")
            return
        
        message = ' '.join(context.args)
        sent, failed = self.notifications.broadcast(message, update.effective_user.id)
        
        update.message.reply_text(f"✅ Рассылка завершена!\n📨 Отправлено: {sent}\n❌ Не доставлено: {failed}")
    
    @admin_required
    def cmd_add_admin(self, update: Update, context: CallbackContext):
        if update.effective_user.id not in self.admin_ids:
            update.message.reply_text("❌ Только владелец может добавлять администраторов")
            return
        
        try:
            args = context.args
            if len(args) < 1:
                update.message.reply_text("Использование: /add_admin <user_id>")
                return
            
            user_id = int(args[0])
            
            try:
                chat = context.bot.get_chat(user_id)
                username = chat.username or chat.first_name
            except:
                username = "Unknown"
            
            self.db.execute_query(
                "INSERT OR REPLACE INTO admins (user_id, username, added_by, date) VALUES (?, ?, ?, ?)",
                (user_id, username, update.effective_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            
            update.message.reply_text(f"✅ Пользователь {username} (ID: {user_id}) теперь администратор!")
            
            try:
                context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 Вас назначили администратором бота 'Помощник 9Г'!"
                )
            except:
                pass
        except Exception as e:
            update.message.reply_text(f"❌ Ошибка: {e}")
    
    @admin_required
    def cmd_add_lesson(self, update: Update, context: CallbackContext):
        context.user_data['admin_action'] = 'add_lesson'
        update.message.reply_text(
            "📚 Добавление урока\n\n"
            "Введите данные в формате:\n"
            "`день номер предмет учитель кабинет начало конец`\n\n"
            "Пример: `0 3 Математика Иванова 301 09:00 09:45`\n"
            "День: 0-6 (пн-вс)"
        )
    
    @admin_required
    def cmd_add_substitution(self, update: Update, context: CallbackContext):
        context.user_data['admin_action'] = 'add_substitution'
        update.message.reply_text(
            "⚠️ Добавление замены\n\n"
            "Введите данные в формате:\n"
            "`дата урок предмет_было предмет_стало причина`\n\n"
            "Пример: `2024-01-15 3 Математика Физика Болеет учитель`"
        )
    
    @admin_required
    def cmd_add_homework(self, update: Update, context: CallbackContext):
        context.user_data['admin_action'] = 'add_homework'
        update.message.reply_text(
            "📚 Добавление домашнего задания\n\n"
            "Введите данные в формате:\n"
            "`предмет описание дата`\n\n"
            "Пример: `Математика Решить уравнения 2024-01-20`"
        )
    
    # ================== ОБРАБОТЧИКИ СООБЩЕНИЙ ==================
    @not_banned
    def handle_photo(self, update: Update, context: CallbackContext):
        user = update.effective_user
        photo = update.message.photo[-1]
        
        if context.user_data.get('admin_action') == 'solved_hw_waiting_photos' and self.is_admin(user.id):
            if 'solved_hw_photos' not in context.user_data:
                context.user_data['solved_hw_photos'] = []
            
            context.user_data['solved_hw_photos'].append(photo.file_id)
            count = len(context.user_data['solved_hw_photos'])
            
            update.message.reply_text(
                f"✅ Фото {count} добавлено для решенного ДЗ!\nОтправьте еще или нажмите 'Готово'",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Готово", callback_data="solved_hw_done")],
                    [InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")]
                ])
            )
            return
        
        tags = self._extract_tags(update.message.caption) if update.message.caption else []
        photo_id = self.photos.add_photo(photo.file_id, user.id, user.username or user.first_name, tags)
        
        if is_tracking_enabled():
            for admin_id in self.admin_ids:
                try:
                    context.bot.send_message(
                        chat_id=admin_id,
                        text=f"📸 Новое фото на модерацию от @{user.username or user.first_name} (ID: {user.id})"
                    )
                except:
                    pass
        
        self.users.update_user(user.id, last_active=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        update.message.reply_text(
            "✅ Фото отправлено на модерацию! Оно появится в галерее после проверки.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
        )
    
    def _extract_tags(self, caption: str) -> List[str]:
        return re.findall(r'#(\w+)', caption)
    
    @not_banned
    def handle_text(self, update: Update, context: CallbackContext):
        user = update.effective_user
        text = update.message.text
        
        self.users.update_user(user.id, last_active=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # Check if it's a game move
        for game_type in GameType:
            session = self.games.get_game(user.id, game_type)
            if session:
                result = session.make_move(text)
                if result['valid']:
                    if result.get('game_over'):
                        self.games.end_game(user.id, game_type, session)
                    update.message.reply_text(result['message'])
                else:
                    update.message.reply_text(result['message'])
                return
        
        # Support messages
        if context.user_data.get('waiting_for_support'):
            report_id = self.db.execute_query(
                "INSERT INTO reports (user_id, username, message, date) VALUES (?, ?, ?, ?)",
                (user.id, user.username or user.first_name, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            update.message.reply_text(
                self.get_text(user.id, 'support_sent'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ]])
            )
            context.user_data['waiting_for_support'] = False
            
            for admin_id in self.admin_ids:
                try:
                    context.bot.send_message(
                        chat_id=admin_id,
                        text=f"📞 Новое сообщение от @{user.username or user.first_name} (ID: {user.id})\n\n{text}"
                    )
                except:
                    pass
            return
        
        # Admin actions
        if self.is_admin(user.id):
            action = context.user_data.get('admin_action')
            
            if action == 'hw':
                if ':' in text:
                    subject, task = text.split(':', 1)
                    self.db.execute_query(
                        "INSERT INTO homework (subject, task, type, date) VALUES (?, ?, ?, ?)",
                        (subject.strip(), task.strip(), 'regular', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    update.message.reply_text("✅ ДЗ обновлено!")
                    context.user_data['admin_action'] = None
                else:
                    update.message.reply_text("❌ Используйте: `Предмет: Задание`", parse_mode='Markdown')
            
            elif action == 'solved_hw_waiting_subject':
                if context.user_data.get('solved_hw_photos'):
                    photo_ids_str = ','.join(context.user_data['solved_hw_photos'])
                    expires_at = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                    self.db.execute_query(
                        "INSERT INTO solved_homework (subject, photo_ids, date, expires_at) VALUES (?, ?, ?, ?)",
                        (text.strip(), photo_ids_str, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at)
                    )
                    update.message.reply_text("✅ Решенное ДЗ добавлено!")
                    context.user_data['admin_action'] = None
                    context.user_data.pop('solved_hw_photos', None)
                else:
                    update.message.reply_text("❌ Нет фото")
            
            elif action == 'add_fact':
                if ':' in text:
                    category, fact = text.split(':', 1)
                    user_data = self.users.get_user(user.id)
                    lang = user_data.language.value if user_data else 'ru'
                    self.facts.add_fact(fact.strip(), category.strip(), user.id, lang)
                    count = self.facts.get_facts_count()
                    update.message.reply_text(f"✅ Факт добавлен! Всего: {count}")
                    context.user_data['admin_action'] = None
                else:
                    update.message.reply_text("❌ Используйте: `Категория: Факт`")
            
            elif action == 'add_lesson':
                try:
                    parts = text.split()
                    day = int(parts[0])
                    number = int(parts[1])
                    subject = parts[2]
                    teacher = parts[3] if len(parts) > 3 else None
                    room = parts[4] if len(parts) > 4 else None
                    start = parts[5] if len(parts) > 5 else None
                    end = parts[6] if len(parts) > 6 else None
                    
                    self.schedule.add_lesson(day, number, subject, teacher, room, start, end)
                    update.message.reply_text("✅ Урок добавлен")
                    context.user_data['admin_action'] = None
                except Exception as e:
                    update.message.reply_text(f"❌ Ошибка: {e}")
            
            elif action == 'add_substitution':
                try:
                    parts = text.split()
                    date_str = parts[0]
                    lesson = int(parts[1])
                    original = parts[2]
                    new = parts[3]
                    reason = ' '.join(parts[4:]) if len(parts) > 4 else ''
                    
                    self.schedule.add_substitution(date_str, lesson, original, new, reason)
                    update.message.reply_text("✅ Замена добавлена")
                    context.user_data['admin_action'] = None
                except Exception as e:
                    update.message.reply_text(f"❌ Ошибка: {e}")
            
            elif action == 'add_homework':
                try:
                    parts = text.split()
                    subject = parts[0]
                    description = ' '.join(parts[1:-1])
                    due_date = parts[-1]
                    
                    self.schedule.add_homework(subject, description, due_date, None, user.id)
                    update.message.reply_text("✅ Домашнее задание добавлено")
                    context.user_data['admin_action'] = None
                except Exception as e:
                    update.message.reply_text(f"❌ Ошибка: {e}")
            
            elif action == 'add_admin':
                try:
                    admin_id = int(text.strip())
                    try:
                        chat = context.bot.get_chat(admin_id)
                        username = chat.username or chat.first_name
                    except:
                        username = "Unknown"
                    
                    self.db.execute_query(
                        "INSERT OR REPLACE INTO admins VALUES (?, ?, ?, ?)",
                        (admin_id, username, user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                    
                    update.message.reply_text(f"✅ Пользователь {username} теперь админ!")
                    context.user_data['admin_action'] = None
                    
                    try:
                        context.bot.send_message(
                            chat_id=admin_id,
                            text="🎉 Вас назначили администратором!"
                        )
                    except:
                        pass
                except ValueError:
                    update.message.reply_text("❌ Введите числовой ID")
            
            elif action == 'remove_admin':
                try:
                    admin_id = int(text.strip())
                    if admin_id in self.admin_ids:
                        update.message.reply_text("❌ Нельзя удалить владельца")
                    else:
                        self.db.execute_query("DELETE FROM admins WHERE user_id = ?", (admin_id,))
                        update.message.reply_text(f"✅ Админ {admin_id} удален")
                        context.user_data['admin_action'] = None
                except ValueError:
                    update.message.reply_text("❌ Введите числовой ID")
            
            elif action == 'ban':
                parts = text.strip().split()
                try:
                    uid = int(parts[0])
                    hours = int(parts[1]) if len(parts) > 1 else None
                    reason = ' '.join(parts[2:]) if len(parts) > 2 else "Нарушение правил"
                    
                    self.users.ban_user(uid, hours, reason)
                    update.message.reply_text(f"✅ Пользователь {uid} забанен")
                    context.user_data['admin_action'] = None
                    
                    try:
                        ban_text = self.get_text(uid, 'banned' if hours else 'permanent_ban', 
                                               date=hours, reason=reason)
                        context.bot.send_message(chat_id=uid, text=ban_text)
                    except:
                        pass
                except:
                    update.message.reply_text("❌ Неверный формат")
            
            elif action == 'unban':
                try:
                    uid = int(text.strip())
                    self.users.unban_user(uid)
                    update.message.reply_text(f"✅ Пользователь {uid} разбанен")
                    context.user_data['admin_action'] = None
                except ValueError:
                    update.message.reply_text("❌ Введите числовой ID")
            
            elif action == 'subscription':
                parts = text.strip().split()
                try:
                    uid = int(parts[0])
                    days = int(parts[1]) if len(parts) > 1 else 30
                    
                    self.db.execute_query(
                        "UPDATE users SET subscription_end = datetime('now', '+{} days') WHERE user_id = ?".format(days),
                        (uid,)
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
                    update.message.reply_text("❌ Неверный формат")
            
            elif action == 'add_rating':
                parts = text.strip().split()
                try:
                    uid = int(parts[0])
                    points = int(parts[1])
                    self.users.add_rating(uid, points)
                    update.message.reply_text(f"✅ Рейтинг обновлен")
                    context.user_data['admin_action'] = None
                except:
                    update.message.reply_text("❌ Неверный формат")
            
            elif action == 'broadcast':
                sent, failed = self.notifications.broadcast(text, user.id)
                update.message.reply_text(f"✅ Рассылка завершена!\n📨 Отправлено: {sent}\n❌ Не доставлено: {failed}")
                context.user_data['admin_action'] = None
    
    # ================== ОБРАБОТЧИК CALLBACK ==================
    def handle_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        user_id = query.from_user.id
        
        banned, reason = self.users.is_banned(user_id)
        if banned:
            query.edit_message_text(self.get_text(user_id, 'banned', reason=reason))
            return
        
        data = query.data
        
        # Language selection
        if data.startswith('lang_'):
            lang = data.split('_')[1]
            self.users.update_user(user_id, language=lang)
            query.edit_message_text(self.get_text(user_id, 'language_changed'))
            return
        
        # Main menu
        if data == "main_menu":
            query.edit_message_text(
                self.get_text(user_id, 'main_menu'),
                reply_markup=self.get_main_keyboard(user_id)
            )
            return
        
        # Profile
        if data == "menu_profile":
            user_data = self.users.get_user(user_id)
            subscription = "✅ Активна" if user_data.subscription_end and user_data.subscription_end > datetime.now() else "❌ Нет"
            join_date = user_data.join_date.strftime("%d.%m.%Y") if user_data.join_date else "Неизвестно"
            
            text = self.get_text(
                user_id, 'profile',
                rating=user_data.rating,
                photos=user_data.photos_count,
                subscription=subscription,
                join_date=join_date,
                user_id=user_id
            )
            
            keyboard = [[InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")]]
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Games menu
        if data == "menu_games":
            keyboard = [
                [InlineKeyboardButton("❌ Крестики-нолики", callback_data="game_tic_tac_toe")],
                [InlineKeyboardButton("🔢 Угадай число", callback_data="game_guess_number")],
                [InlineKeyboardButton("📝 Угадай слово", callback_data="game_word_game")],
                [InlineKeyboardButton("🧮 Математика", callback_data="game_math_quiz")],
                [InlineKeyboardButton("🧠 Память", callback_data="game_memory")],
                [InlineKeyboardButton("✂️ Камень-ножницы-бумага", callback_data="game_rps")],
                [InlineKeyboardButton("🎭 Виселица", callback_data="game_hangman")],
                [InlineKeyboardButton("❓ Викторина", callback_data="game_trivia")],
                [InlineKeyboardButton("🐍 Змейка", callback_data="game_snake")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
            ]
            query.edit_message_text("🎮 **Игры на перемене**", parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Currency menu
        if data == "menu_currency":
            message = self.currency.format_rate_message()
            keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="menu_currency"),
                         InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
            query.edit_message_text(message, parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Schedule menu
        if data == "menu_schedule":
            days = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']
            keyboard = []
            row = []
            for i, day in enumerate(days):
                row.append(InlineKeyboardButton(day, callback_data=f"schedule_day_{i}"))
                if (i + 1) % 3 == 0:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("📚 ДЗ на неделю", callback_data="schedule_homework")])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
            
            query.edit_message_text("📅 **Расписание уроков**", parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        if data.startswith("schedule_day_"):
            day = int(data.split('_')[2])
            schedule_text = self.schedule.format_schedule(day)
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu_schedule")]]
            query.edit_message_text(schedule_text, parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        if data == "schedule_homework":
            homework_text = self.schedule.format_homework()
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu_schedule")]]
            query.edit_message_text(homework_text, parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Games
        if data.startswith("game_"):
            game_name = data[5:]
            game_map = {
                'tic_tac_toe': GameType.TIC_TAC_TOE,
                'guess_number': GameType.GUESS_NUMBER,
                'word_game': GameType.WORD_GAME,
                'math_quiz': GameType.MATH_QUIZ,
                'memory': GameType.MEMORY,
                'rps': GameType.RPS,
                'hangman': GameType.HANGMAN,
                'trivia': GameType.TRIVIA,
                'snake': GameType.SNAKE
            }
            
            if game_name in game_map:
                game_type = game_map[game_name]
                session = self.games.start_game(game_type, user_id)
                
                messages = {
                    'tic_tac_toe': "❌ **Крестики-нолики**\n\nВыберите клетку (0-8):\n" + session._format_tic_tac_toe_board(),
                    'guess_number': "🔢 **Угадай число**\n\nЯ загадал число от 1 до 100",
                    'word_game': "📝 **Угадай слово**\n\nУгадывайте по буквам",
                    'math_quiz': f"🧮 Решите: {session.state['a']} {session.state['op']} {session.state['b']} = ?",
                    'memory': "🧠 **Игра на память**\n\nВыбирайте карты (1-8)",
                    'rps': "✂️ Выберите: камень, ножницы или бумага",
                    'hangman': "🎭 **Виселица**\n\nУгадывайте слово",
                    'trivia': "❓ **Викторина**\n\nВведите номер ответа",
                    'snake': "🐍 **Змейка**\n\nУправляйте змейкой (UP/DOWN/LEFT/RIGHT)"
                }
                
                query.edit_message_text(messages[game_name])
            return
        
        # Homework
        if data == "menu_hw":
            result = self.db.execute_query(
                "SELECT subject, task FROM homework WHERE type='regular' ORDER BY id DESC LIMIT 1"
            )
            if result:
                subject, task = result[0]['subject'], result[0]['task']
                text = self.get_text(user_id, 'homework_text', subject=subject, task=task)
            else:
                text = self.get_text(user_id, 'no_homework')
            
            keyboard = [[InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")]]
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Random photo
        if data == "menu_random":
            photo_id = self.photos.get_random_photo()
            if photo_id:
                count = self.photos.get_photo_count()
                caption = self.get_text(user_id, 'random_photo', count=count)
                
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(self.get_text(user_id, 'more'), callback_data="menu_random"),
                    InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")
                ]])
                
                query.message.reply_photo(photo=photo_id, caption=caption, reply_markup=keyboard)
                query.message.delete()
            else:
                query.edit_message_text(self.get_text(user_id, 'no_photos'),
                                      reply_markup=InlineKeyboardMarkup([[
                                          InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")
                                      ]]))
            return
        
        # Subscription
        if data == "menu_subscription":
            result = self.db.execute_query(
                "SELECT subscription_end FROM users WHERE user_id = ?",
                (user_id,)
            )
            has_sub = result and result[0]['subscription_end'] and \
                     datetime.strptime(result[0]['subscription_end'], "%Y-%m-%d %H:%M:%S") > datetime.now()
            
            if has_sub:
                text = self.get_text(user_id, 'active_subscription', date=result[0]['subscription_end'])
                keyboard = [
                    [InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw")],
                    [InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")]
                ]
            else:
                text = self.get_text(user_id, 'subscription', price=STAR_PRICE)
                keyboard = [
                    [InlineKeyboardButton(f"⭐ Оплатить {STAR_PRICE} звёзд", callback_data="pay_subscription")],
                    [InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")]
                ]
            
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Solved homework
        if data == "menu_solved_hw":
            result = self.db.execute_query(
                "SELECT subscription_end FROM users WHERE user_id = ?",
                (user_id,)
            )
            has_sub = result and result[0]['subscription_end'] and \
                     datetime.strptime(result[0]['subscription_end'], "%Y-%m-%d %H:%M:%S") > datetime.now()
            
            if not has_sub:
                keyboard = [
                    [InlineKeyboardButton("⭐ Купить подписку", callback_data="menu_subscription")],
                    [InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")]
                ]
                query.edit_message_text(self.get_text(user_id, 'subscription', price=STAR_PRICE),
                                      reply_markup=InlineKeyboardMarkup(keyboard))
                return
            
            result = self.db.execute_query(
                "SELECT subject, photo_ids FROM solved_homework ORDER BY id DESC LIMIT 1"
            )
            if result and result[0]['photo_ids']:
                subject = result[0]['subject']
                photo_ids = result[0]['photo_ids'].split(',')
                
                query.edit_message_text(f"✅ Решенное ДЗ - {subject}\n\nЗагружаю {len(photo_ids)} фото...")
                
                for i, photo_id in enumerate(photo_ids, 1):
                    caption = f"✅ {subject} (фото {i}/{len(photo_ids)})"
                    query.message.reply_photo(photo=photo_id, caption=caption)
                
                query.message.reply_text(
                    self.get_text(user_id, 'main_menu'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")
                    ]])
                )
                query.message.delete()
            else:
                query.edit_message_text("📝 Решенное ДЗ пока не добавлено")
            return
        
        # Payment
        if data == "pay_subscription":
            query.edit_message_text(
                f"⭐ Для оплаты подписки отправьте {STAR_PRICE} звёзд этому боту.\n\n"
                f"Инструкция:\n"
                f"1. Нажмите на скрепку 📎\n"
                f"2. Выберите 💎 'Звёзды'\n"
                f"3. Укажите количество: {STAR_PRICE}\n"
                f"4. Отправьте и подписка активируется!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="menu_subscription")
                ]])
            )
            return
        
        # Support
        if data == "menu_support":
            query.edit_message_text(
                self.get_text(user_id, 'support_message'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")
                ]])
            )
            context.user_data['waiting_for_support'] = True
            return
        
        # Fact
        if data == "menu_fact":
            user_data = self.users.get_user(user_id)
            lang = user_data.language.value if user_data else 'ru'
            fact_info = self.facts.get_random_fact(lang)
            
            if fact_info:
                fact, category = fact_info
                text = f"🎯 **Интересный факт**\n\n{fact}\n\n📚 Категория: {category}"
            else:
                text = "🎯 Факты пока не добавлены"
            
            keyboard = [
                [InlineKeyboardButton(self.get_text(user_id, 'more'), callback_data="menu_fact")],
                [InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")]
            ]
            query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Photo
        if data == "menu_photo":
            query.edit_message_text(
                self.get_text(user_id, 'send_photo'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(self.get_text(user_id, 'back'), callback_data="main_menu")
                ]])
            )
            return
        
        # Admin menu
        if data == "admin_menu" and self.is_admin(user_id):
            keyboard = [
                [InlineKeyboardButton("📝 Изменить ДЗ", callback_data="admin_hw")],
                [InlineKeyboardButton("✅ Добавить решенное ДЗ", callback_data="admin_solved_hw")],
                [InlineKeyboardButton("📸 Модерация фото", callback_data="admin_moderate")],
                [InlineKeyboardButton("➕ Добавить факт", callback_data="admin_add_fact")],
                [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
                [InlineKeyboardButton("📞 Сообщения", callback_data="admin_reports")],
                [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
                [InlineKeyboardButton("👁️ Слежка", callback_data="admin_tracking")],
                [InlineKeyboardButton("🚫 Бан", callback_data="admin_ban")],
                [InlineKeyboardButton("✅ Разбан", callback_data="admin_unban")],
                [InlineKeyboardButton("⭐ Выдать подписку", callback_data="admin_subscription")],
                [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
                [InlineKeyboardButton("❌ Удалить админа", callback_data="admin_remove")],
                [InlineKeyboardButton("📊 Управление рейтингом", callback_data="admin_rating")],
                [InlineKeyboardButton("📚 Добавить урок", callback_data="admin_add_lesson")],
                [InlineKeyboardButton("📅 Добавить замену", callback_data="admin_add_substitution")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
            ]
            query.edit_message_text("👑 **Админ-панель**", parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Moderation
        if data == "admin_moderate" and self.is_admin(user_id):
            pending = self.photos.get_pending_photos()
            if not pending:
                query.edit_message_text("📸 Нет фото на модерации",
                                      reply_markup=InlineKeyboardMarkup([[
                                          InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                                      ]]))
                return
            
            context.user_data['pending_photos'] = pending
            context.user_data['pending_index'] = 0
            self._show_pending_photo(query, context, 0)
            return
        
        if data.startswith('approve_photo_') and self.is_admin(user_id):
            photo_id = int(data.split('_')[2])
            self.photos.approve_photo(photo_id, user_id)
            
            result = self.db.execute_query(
                "SELECT user_id FROM photos WHERE id = ?",
                (photo_id,)
            )
            if result:
                self.users.add_rating(result[0]['user_id'], 10)
            
            if 'pending_photos' in context.user_data:
                pending = context.user_data['pending_photos']
                index = context.user_data.get('pending_index', 0) + 1
                if index < len(pending):
                    self._show_pending_photo(query, context, index)
                else:
                    query.edit_message_text("✅ Все фото обработаны!",
                                          reply_markup=InlineKeyboardMarkup([[
                                              InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                                          ]]))
                    context.user_data.pop('pending_photos', None)
                    context.user_data.pop('pending_index', None)
            return
        
        if data.startswith('reject_photo_') and self.is_admin(user_id):
            photo_id = int(data.split('_')[2])
            self.photos.reject_photo(photo_id, user_id)
            
            if 'pending_photos' in context.user_data:
                pending = context.user_data['pending_photos']
                index = context.user_data.get('pending_index', 0) + 1
                if index < len(pending):
                    self._show_pending_photo(query, context, index)
                else:
                    query.edit_message_text("✅ Все фото обработаны!",
                                          reply_markup=InlineKeyboardMarkup([[
                                              InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                                          ]]))
                    context.user_data.pop('pending_photos', None)
                    context.user_data.pop('pending_index', None)
            return
        
        # Admin input requests
        admin_input_actions = [
            'admin_hw', 'admin_solved_hw', 'admin_add_fact', 'admin_ban', 'admin_unban',
            'admin_subscription', 'admin_add', 'admin_remove', 'admin_rating',
            'admin_add_lesson', 'admin_add_substitution'
        ]
        if data in admin_input_actions and self.is_admin(user_id):
            messages = {
                'admin_hw': "📝 Введите новое ДЗ в формате:\n`Предмет: Задание`",
                'admin_solved_hw': "✅ Отправьте фото решенного ДЗ (можно несколько)",
                'admin_add_fact': "📝 Введите факт в формате:\n`Категория: Факт`",
                'admin_ban': "🚫 Введите ID пользователя и часы бана:\n`ID часы [причина]`",
                'admin_unban': "✅ Введите ID пользователя для разбана",
                'admin_subscription': "⭐ Введите ID пользователя и дни:\n`ID дни`",
                'admin_add': "➕ Введите ID нового администратора",
                'admin_remove': "❌ Введите ID администратора для удаления",
                'admin_rating': "📊 Введите ID и баллы рейтинга:\n`ID баллы`",
                'admin_add_lesson': "📚 Введите данные урока:\n`день номер предмет учитель кабинет начало конец`",
                'admin_add_substitution': "📅 Введите данные замены:\n`дата урок предмет_было предмет_стало причина`"
            }
            
            action_map = {
                'admin_hw': 'hw',
                'admin_solved_hw': 'solved_hw_waiting_photos',
                'admin_add_fact': 'add_fact',
                'admin_ban': 'ban',
                'admin_unban': 'unban',
                'admin_subscription': 'subscription',
                'admin_add': 'add_admin',
                'admin_remove': 'remove_admin',
                'admin_rating': 'add_rating',
                'admin_add_lesson': 'add_lesson',
                'admin_add_substitution': 'add_substitution'
            }
            
            query.edit_message_text(
                messages[data],
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                ]])
            )
            
            context.user_data['admin_action'] = action_map[data]
            if data == 'admin_solved_hw':
                context.user_data['solved_hw_photos'] = []
            return
        
        # Solved homework done
        if data == "solved_hw_done" and self.is_admin(user_id):
            if context.user_data.get('solved_hw_photos'):
                query.edit_message_text(
                    "📝 Напишите название предмета:",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Отмена", callback_data="admin_menu")
                    ]])
                )
                context.user_data['admin_action'] = 'solved_hw_waiting_subject'
            else:
                query.edit_message_text(
                    "❌ Нет фото",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Назад", callback_data="admin_solved_hw")
                    ]])
                )
            return
        
        # Stats
        if data == "admin_stats" and self.is_admin(user_id):
            user_stats = self.users.get_stats()
            photo_stats = self.photos.get_photo_stats()
            db_stats = self.db.get_stats()
            
            text = f"""
📊 **Статистика бота**

**Пользователи:**
👥 Всего: {user_stats.get('total_users', 0)}
⭐ Подписчиков: {user_stats.get('subscribers', 0)}
🚫 Забанено: {user_stats.get('banned', 0)}
📸 Всего фото: {user_stats.get('total_photos', 0)}
⭐ Средний рейтинг: {user_stats.get('avg_rating', 0):.1f}

**Фотографии:**
📸 Всего: {photo_stats.get('total', 0)}
⏳ На модерации: {photo_stats.get('pending', 0)}
✅ Одобрено: {photo_stats.get('approved', 0)}
❌ Отклонено: {photo_stats.get('rejected', 0)}
❤️ Лайков: {photo_stats.get('total_likes', 0)}
👁️ Просмотров: {photo_stats.get('total_views', 0)}

**База данных:**
💾 Кэш попаданий: {db_stats.get('cache_hits', 0)}
💾 Кэш промахов: {db_stats.get('cache_misses', 0)}
📝 Записей: {db_stats.get('write_operations', 0)}
🔄 Транзакций: {db_stats.get('transactions', 0)}
❌ Ошибок: {db_stats.get('errors', 0)}
"""
            
            query.edit_message_text(text, parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup([[
                                      InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")
                                  ]]))
            return
    
    def _show_pending_photo(self, query, context, index: int):
        pending = context.user_data['pending_photos']
        if index >= len(pending):
            return
        
        photo = pending[index]
        context.user_data['pending_index'] = index
        
        caption = f"📸 Фото {index+1}/{len(pending)}\n"
        caption += f"От: @{photo['username'] or 'Неизвестно'} (ID: {photo['user_id']})\n"
        caption += f"Дата: {photo['date']}\n"
        
        if photo.get('tags'):
            tags = json.loads(photo['tags'])
            if tags:
                caption += f"Теги: {', '.join(tags)}\n"
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_photo_{photo['id']}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_photo_{photo['id']}")
            ],
            [InlineKeyboardButton("🔙 В админ-панель", callback_data="admin_menu")]
        ])
        
        query.message.reply_photo(photo=photo['file_id'], caption=caption, reply_markup=keyboard)
        query.message.delete()
    
    # ================== ПЛАТЕЖИ ==================
    def pre_checkout(self, update: Update, context: CallbackContext):
        query = update.pre_checkout_query
        if query.invoice_payload == "subscription":
            query.answer(ok=True)
    
    def successful_payment(self, update: Update, context: CallbackContext):
        user = update.effective_user
        self.db.execute_query(
            "UPDATE users SET subscription_end = datetime('now', '+30 days') WHERE user_id = ?",
            (user.id,)
        )
        self.users.add_rating(user.id, 100)
        
        update.message.reply_text(
            "⭐ Спасибо за покупку! Подписка активирована на 30 дней.\nВам начислено 100 баллов рейтинга!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Решенное ДЗ", callback_data="menu_solved_hw"),
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
        )
    
    # ================== ОБРАБОТКА ОШИБОК ==================
    def error_handler(self, update: Update, context: CallbackContext):
        logger.error(f"Update {update} caused error {context.error}")
        
        try:
            if update and update.effective_message:
                update.effective_message.reply_text(
                    "❌ Произошла ошибка. Администраторы уже уведомлены."
                )
        except:
            pass
    
    # ================== ЗАПУСК ==================
    def run(self):
        print("🚀 Бот 'Помощник 9Г' запущен...")
        print(f"👑 Главный администратор ID: {self.admin_ids[0]}")
        print("📸 Модерация фото включена")
        print("🌐 Поддержка 3 языков")
        print("🎮 9 игр на перемене")
        print("💱 Курсы валют и криптовалют")
        print("📅 Расписание уроков")
        print("⚡ Кэширование активно")
        
        self.updater.start_polling()
        self.updater.idle()

# ================== ФУНКЦИИ ДЛЯ СОВМЕСТИМОСТИ ==================
def is_tracking_enabled():
    db = DatabaseManager()
    result = db.execute_query("SELECT value FROM settings WHERE key = 'tracking'")
    return result and result[0]['value'] == 'enabled'

def set_tracking(enabled):
    db = DatabaseManager()
    db.execute_query(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ('tracking', 'enabled' if enabled else 'disabled')
    )

# ================== ЗАПУСК ==================
if __name__ == "__main__":
    bot = HomeworkBot(TOKEN, ADMIN_IDS)
    bot.run()
