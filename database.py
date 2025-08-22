import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path="vpn_bot.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Таблица пользователей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        full_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Таблица подписок
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        vpn_username TEXT UNIQUE,
                        subscription_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Таблица платежей
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS payments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        amount REAL,
                        currency TEXT,
                        payment_method TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        confirmed_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def add_user(self, user_id, username=None, full_name=None):
        """Добавить или обновить пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO users (user_id, username, full_name, last_activity)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, full_name, datetime.now()))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            raise
    
    def get_user(self, user_id):
        """Получить информацию о пользователе"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
                return cursor.fetchone()
                
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    def add_subscription(self, user_id, vpn_username, subscription_name=None, expires_at=None):
        """Добавить подписку"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO subscriptions (user_id, vpn_username, subscription_name, expires_at)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, vpn_username, subscription_name, expires_at))
                conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            logger.error(f"Error adding subscription for user {user_id}: {e}")
            raise
    
    def get_user_subscriptions(self, user_id):
        """Получить подписки пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM subscriptions 
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY created_at DESC
                ''', (user_id,))
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Error getting subscriptions for user {user_id}: {e}")
            return []
    
    def get_subscription_by_vpn_username(self, vpn_username):
        """Получить подписку по VPN username"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM subscriptions 
                    WHERE vpn_username = ? AND is_active = 1
                ''', (vpn_username,))
                return cursor.fetchone()
                
        except Exception as e:
            logger.error(f"Error getting subscription for VPN user {vpn_username}: {e}")
            return None
    
    def update_subscription_name(self, vpn_username, new_name):
        """Обновить название подписки"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE subscriptions 
                    SET subscription_name = ?
                    WHERE vpn_username = ? AND is_active = 1
                ''', (new_name, vpn_username))
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Error updating subscription name for {vpn_username}: {e}")
            return False
    
    def deactivate_subscription(self, vpn_username):
        """Деактивировать подписку"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE subscriptions 
                    SET is_active = 0
                    WHERE vpn_username = ?
                ''', (vpn_username,))
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Error deactivating subscription {vpn_username}: {e}")
            return False
    
    def add_payment(self, user_id, amount, currency, payment_method):
        """Добавить платеж"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO payments (user_id, amount, currency, payment_method)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, amount, currency, payment_method))
                conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            logger.error(f"Error adding payment for user {user_id}: {e}")
            raise
    
    def confirm_payment(self, payment_id):
        """Подтвердить платеж"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE payments 
                    SET status = 'confirmed', confirmed_at = ?
                    WHERE id = ?
                ''', (datetime.now(), payment_id))
                conn.commit()
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Error confirming payment {payment_id}: {e}")
            return False
    
    def get_user_payments(self, user_id):
        """Получить платежи пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM payments 
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                ''', (user_id,))
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Error getting payments for user {user_id}: {e}")
            return []