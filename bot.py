import os
import json
import base64
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from database import Database
import locale
import qrcode
from io import BytesIO
from subscription_service import SubscriptionService
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
db = Database()

class VPNManager:
    def __init__(self):
        self.api_url = os.getenv('MARZBAN_API_URL')
        self.api_username = os.getenv('MARZBAN_USERNAME')
        self.api_password = os.getenv('MARZBAN_PASSWORD')
        self.session = requests.Session()
        self.session.verify = False
        self.access_token = None
        
        logger.info(f"VPNManager initialized with API URL: {self.api_url}")
        
        # Получаем токен при инициализации
        self._authenticate()

    def _authenticate(self):
        """Аутентификация в Marzban API и получение access token"""
        try:
            if not self.api_username or not self.api_password:
                logger.error("MARZBAN_USERNAME or MARZBAN_PASSWORD not provided")
                return False
                
            auth_url = f"{self.api_url}/api/admin/token"
            auth_data = {
                "username": self.api_username,
                "password": self.api_password
            }
            
            logger.info(f"Authenticating with Marzban API at: {auth_url}")
            response = self.session.post(auth_url, data=auth_data)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                if self.access_token:
                    self.session.headers.update({'Authorization': f'Bearer {self.access_token}'})
                    logger.info("Successfully authenticated with Marzban API")
                    return True
                else:
                    logger.error("No access token in response")
                    return False
            else:
                logger.error(f"Authentication failed with status: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    def test_api_connection(self):
        """Test API connection and discover available endpoints"""
        try:
            logger.info("Testing Marzban API connection...")
            
            # Проверяем аутентификацию
            if not self.access_token:
                logger.error("No access token available")
                return False
            
            # Тестируем основные endpoints
            test_endpoints = [
                f"{self.api_url}/api/users",
                f"{self.api_url}/api/system",
                f"{self.api_url}/api/admin"
            ]
            
            for endpoint in test_endpoints:
                try:
                    logger.info(f"Testing endpoint: {endpoint}")
                    response = self.session.get(endpoint)
                    logger.info(f"Status: {response.status_code}")
                    
                    if response.status_code == 200:
                        logger.info(f"Endpoint {endpoint} is working")
                        return True
                    elif response.status_code == 401:
                        # Токен истек, пробуем переаутентификацию
                        logger.info("Token expired, re-authenticating...")
                        if self._authenticate():
                            response = self.session.get(endpoint)
                            if response.status_code == 200:
                                return True
                                
                except Exception as e:
                    logger.info(f"Endpoint {endpoint} failed: {e}")
                    continue
            
            return False
        except Exception as e:
            logger.error(f"API connection test failed: {e}")
            return False

    def get_users(self):
        """Получить список пользователей"""
        try:
            response = self.session.get(f"{self.api_url}/api/users")
            logger.info(f"Get users response status: {response.status_code}")
            
            if response.status_code == 401:
                # Токен истек, переаутентификация
                if self._authenticate():
                    response = self.session.get(f"{self.api_url}/api/users")
                else:
                    raise Exception("Failed to re-authenticate")
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            raise

    def create_user(self, username, email=None, password=None, expireAt=None, **kwargs):
        """Создать пользователя в Marzban"""
        try:
            # Marzban API структура для создания пользователя
            user_data = {
                "username": username,
                "proxies": kwargs.get('proxies', {
                    "vless": {},
                    "vmess": {},
                    "trojan": {},
                    "shadowsocks": {}
                }),
                "data_limit": kwargs.get('data_limit', 0),  # 0 = unlimited
                "expire": None,
                "status": kwargs.get('status', 'active')
            }
            
            # Устанавливаем дату истечения если передана
            if expireAt:
                if expireAt > 1000000000000:  # milliseconds
                    dt = datetime.fromtimestamp(expireAt / 1000)
                else:  # seconds
                    dt = datetime.fromtimestamp(expireAt)
                # Marzban ожидает timestamp в секундах
                user_data["expire"] = int(dt.timestamp())
            
            logger.info(f"Creating Marzban user with data: {user_data}")
            
            response = self.session.post(f"{self.api_url}/api/user", json=user_data)
            
            if response.status_code == 401:
                # Токен истек, переаутентификация
                if self._authenticate():
                    response = self.session.post(f"{self.api_url}/api/user", json=user_data)
                else:
                    raise Exception("Failed to re-authenticate")
            
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response body: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Marzban user creation response: {result}")
                
                # Marzban возвращает данные пользователя напрямую
                if 'username' in result:
                    # Добавляем id для совместимости с существующим кодом
                    result['id'] = result.get('username')
                    return result
                else:
                    logger.error(f"Invalid response from Marzban API: {result}")
                    raise Exception("Не удалось получить данные пользователя от Marzban")
            else:
                error_text = response.text
                logger.error(f"Error creating user. Status: {response.status_code}, Response: {error_text}")
                raise Exception(f"Ошибка создания пользователя в Marzban: {error_text}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error creating Marzban user: {e}")
            raise Exception(f"Ошибка подключения к Marzban API: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating Marzban user: {e}")
            raise

    def delete_user(self, user_id):
        """Удалить пользователя"""
        try:
            response = self.session.delete(f"{self.api_url}/api/user/{user_id}")
            
            if response.status_code == 401:
                # Токен истек, переаутентификация
                if self._authenticate():
                    response = self.session.delete(f"{self.api_url}/api/user/{user_id}")
                else:
                    raise Exception("Failed to re-authenticate")
            
            response.raise_for_status()
            return response.json() if response.content else {"success": True}
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            raise

    def get_user_config(self, user_id):
        """Получить конфигурацию пользователя"""
        try:
            # Marzban endpoints для получения конфигурации
            endpoints = [
                f"{self.api_url}/api/user/{user_id}",
                f"{self.api_url}/sub/{user_id}",
                f"{self.api_url}/sub/{user_id}/"
            ]
            
            for endpoint in endpoints:
                try:
                    logger.info(f"Trying config endpoint: {endpoint}")
                    response = self.session.get(endpoint)
                    
                    if response.status_code == 401:
                        # Токен истек, переаутентификация
                        if self._authenticate():
                            response = self.session.get(endpoint)
                        else:
                            continue
                    
                    logger.info(f"Config response status: {response.status_code}")
                    
                    if response.status_code == 200:
                        # Для subscription URL возвращаем текст напрямую
                        if '/sub/' in endpoint:
                            config_text = response.text
                            if config_text and not config_text.startswith('<!DOCTYPE'):
                                return {
                                    'id': user_id,
                                    'username': user_id,
                                    'config': config_text,
                                    'link': config_text,
                                    'subscription_url': endpoint
                                }
                        else:
                            # Для API endpoint возвращаем JSON
                            result = response.json()
                            logger.info(f"Marzban config response for user {user_id}: {result}")
                            
                            # Добавляем subscription URL
                            if 'subscription_url' not in result:
                                result['subscription_url'] = f"{self.api_url}/sub/{user_id}"
                            
                            # Добавляем config и link для совместимости
                            if 'config' not in result and 'subscription_url' in result:
                                result['config'] = result['subscription_url']
                                result['link'] = result['subscription_url']
                            
                            return result
                    
                except requests.exceptions.RequestException as e:
                    logger.info(f"Endpoint {endpoint} failed: {e}")
                    continue
            
            # Если все endpoints не сработали, возвращаем базовую конфигурацию
            return {
                'id': user_id,
                'username': user_id,
                'subscription_url': f"{self.api_url}/sub/{user_id}",
                'config': f"{self.api_url}/sub/{user_id}",
                'link': f"{self.api_url}/sub/{user_id}"
            }
            
        except Exception as e:
            logger.error(f"Error getting user config for {user_id}: {e}")
            raise

vpn_manager = VPNManager()
subscription_service = SubscriptionService(db, vpn_manager)

# Состояния для ConversationHandler
MAIN_MENU, PAYMENT_AMOUNT, PAYMENT_CONFIRMATION = range(3)
RENAME_SUB = 100

# Состояния для админ-панели
ADMIN_BROADCAST, ADMIN_BROADCAST_PREVIEW = range(10, 12)

# Словарь для хранения ожидающих подтверждения платежей
pending_payments = {}

# Состояния для меню покупки VPN
ADD_SUB, CREATE_SUB_PAYMENT, EXTEND_SUB_PAYMENT = range(101, 104)

# Состояния для оплаты
PAY_CRYPTOBOT, PAY_BINANCE, PAY_BYBIT = range(201, 204)

# Состояния для оплаты продления
PAY_CRYPTOBOT_EXTEND, PAY_BINANCE_EXTEND, PAY_BYBIT_EXTEND = range(301, 304)

# Состояния для подтверждения оплаты
BINANCE_PAID, BYBIT_PAID = range(401, 403)

# Состояния для подтверждения продления
BINANCE_PAID_EXTEND, BYBIT_PAID_EXTEND = range(501, 503)

# Состояния для подтверждения админа
ADMIN_CONFIRM_BINANCE, ADMIN_CONFIRM_BYBIT = range(601, 603)
ADMIN_CONFIRM_BINANCE_EXTEND, ADMIN_CONFIRM_BYBIT_EXTEND = range(701, 703)

# Словарь для хранения данных о платежах пользователей
user_payment_data = {}

def update_user_info(user):
    """Обновляет информацию о пользователе в базе данных"""
    if user:
        db.add_user(user.id, user.username or "Unknown", None)

# Главное меню
async def test_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test API connection - admin only"""
    user_id = update.effective_user.id
    admin_id = int(os.getenv('ADMIN_ID', 2122584931))
    
    if user_id != admin_id:
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    await update.message.reply_text("🔄 Тестирую подключение к API...")
    
    try:
        # Test API connection
        connection_ok = vpn_manager.test_api_connection()
        
        if connection_ok:
            await update.message.reply_text("✅ API доступен")
        else:
            await update.message.reply_text("❌ API недоступен")
        
        # Try to get users list
        try:
            users = vpn_manager.get_users()
            await update.message.reply_text(f"📊 Найдено пользователей: {len(users) if isinstance(users, list) else 'неизвестно'}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка получения списка пользователей: {str(e)}")
        
        # Test user creation with proper expireAt
        try:
            test_username = f"test_user_{int(datetime.now().timestamp())}"
            test_email = f"{test_username}@rockvpn.local"
            # Set expiration to 30 days from now (in milliseconds)
            expire_timestamp = int((datetime.now() + timedelta(days=30)).timestamp() * 1000)
            
            await update.message.reply_text(f"🧪 Тестирую создание пользователя: {test_username}")
            
            test_user = vpn_manager.create_user(
                username=test_username, 
                email=test_email,
                expireAt=expire_timestamp
            )
            
            await update.message.reply_text(f"✅ Тестовый пользователь создан: {test_user.get('id', 'ID не найден')}")
            
            # Try to get config
            if 'id' in test_user:
                try:
                    config = vpn_manager.get_user_config(test_user['id'])
                    config_preview = str(config)[:100] + "..." if len(str(config)) > 100 else str(config)
                    await update.message.reply_text(f"📋 Конфигурация получена: {config_preview}")
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Не удалось получить конфигурацию: {str(e)}")
                
                # Try to delete test user
                try:
                    vpn_manager.delete_user(test_user['id'])
                    await update.message.reply_text("🗑️ Тестовый пользователь удален")
                except:
                    await update.message.reply_text("⚠️ Не удалось удалить тестового пользователя")
                    
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка создания тестового пользователя: {str(e)}")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Общая ошибка тестирования: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_info(user)  # Обновляем информацию о пользователе
    
    photo_url = "https://i.imgur.com/your-image.png"
    
    # Получаем данные пользователя из БД
    user_data = db.get_user(user.id)
    balance = 0  # Пока что баланс не реализован
    subscriptions = db.get_user_subscriptions(user.id)
    sub_count = len(subscriptions) if subscriptions else 0
    
    profile_text = (
        f"<b>🧑‍💻 Профиль: {user.first_name or 'Пользователь'}</b>\n\n"
        f"<pre>── ID: {user.id}\n── Баланс: {balance} RUB\n── К-во подписок: {sub_count}</pre>\n\n"
        f"<b>👉 Наш канал 👈</b>\n"
        f"<i>Нажмите кнопку «Купить VPN» или «Продлить VPN», чтобы оформить или продлить подписку.</i>"
    )
    keyboard = [
        [InlineKeyboardButton("Купить VPN", callback_data="buy_vpn"), InlineKeyboardButton("Продлить VPN", callback_data="renew_vpn")],
        [InlineKeyboardButton("Мои подписки", callback_data="my_subs")],
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("👥 Пригласить", callback_data="invite"), InlineKeyboardButton("🎁 Подарить", callback_data="gift")],
        [InlineKeyboardButton("ℹ️ О сервисе", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_photo(photo=photo_url, caption=profile_text, reply_markup=reply_markup, parse_mode="HTML")
    elif update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.delete()
        except:
            pass
        await context.bot.send_photo(chat_id=update.effective_user.id, photo=photo_url, caption=profile_text, reply_markup=reply_markup, parse_mode="HTML")

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = db.get_user(user.id)
    balance = 0  # Пока что баланс не реализован
    subscriptions = db.get_user_subscriptions(user.id)
    sub_count = len(subscriptions) if subscriptions else 0
    
    profile_text = (
        f"<b>🧑‍💻 Профиль: {user.first_name or 'Пользователь'}</b>\n\n"
        f"<pre>── ID: {user.id}\n── Баланс: {balance} RUB\n── К-во подписок: {sub_count}</pre>\n\n"
        f"<b>👉 Наш канал 👈</b>\n"
        f"<i>Нажмите кнопку «Купить VPN» или «Продлить VPN», чтобы оформить или продлить подписку.</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("Купить VPN", callback_data="buy_vpn"), InlineKeyboardButton("Продлить VPN", callback_data="renew_vpn")],
        [InlineKeyboardButton("Мои подписки", callback_data="my_subs")],
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("👥 Пригласить", callback_data="invite"), InlineKeyboardButton("🎁 Подарить", callback_data="gift")],
        [InlineKeyboardButton("ℹ️ О сервисе", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    photo_url = "https://i.imgur.com/your-image.png"

    if hasattr(update, 'callback_query') and update.callback_query:
        cq = update.callback_query
        await cq.answer()
        try:
            await cq.message.delete()
        except:
            pass
        await context.bot.send_photo(
            chat_id=cq.from_user.id, 
            photo=photo_url, 
            caption=profile_text, 
            reply_markup=reply_markup, 
            parse_mode='HTML'
        )
    elif update.message:
        await update.message.reply_photo(
            photo=photo_url, 
            caption=profile_text, 
            reply_markup=reply_markup, 
            parse_mode='HTML'
        )
    return MAIN_MENU

# Обработчик выбора тарифа для создания новой подписки
async def create_sub_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # Определяем тариф и сохраняем в пользовательских данных
    tariff_info = {
        'create_sub_1': {'months': 1, 'name': '1 месяц — 179Р'},
        'create_sub_3': {'months': 3, 'name': '3 месяца — 474Р'},
        'create_sub_6': {'months': 6, 'name': '6 месяцев — 919Р'},
        'create_sub_12': {'months': 12, 'name': '12 месяцев — 1549Р'},
    }
    
    selected_tariff = tariff_info.get(data)
    if not selected_tariff:
        await query.answer("Неверный тариф", show_alert=True)
        return
    
    # Сохраняем информацию о тарифе
    user_payment_data[user_id] = {
        'action': 'create_subscription',
        'months': selected_tariff['months'],
        'tariff_name': selected_tariff['name']
    }
    
    text = f"Вы выбрали тариф: <b>{selected_tariff['name']}</b>\n\nВыберите способ оплаты:" 
    keyboard = [
        [InlineKeyboardButton("CryptoBot (автомат)", callback_data="pay_cryptobot")],
        [InlineKeyboardButton("Binance (ручное подтверждение)", callback_data="pay_binance")],
        [InlineKeyboardButton("Bybit (ручное подтверждение)", callback_data="pay_bybit")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="add_sub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            await query.answer("Ошибка отображения меню. Попробуйте ещё раз.", show_alert=True)
            logger.error(f"Error in create_sub_payment_callback: {e}")

# Обработчик выбора тарифа для продления
async def extend_sub_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # data: extend_{sub_id}_{months}
    parts = data.split('_')
    if len(parts) < 3:
        await query.answer("Неверный формат данных", show_alert=True)
        return
    
    sub_id = parts[1]
    months = int(parts[2])
    
    tariff_map = {
        1: '1 месяц — 179Р',
        3: '3 месяца — 474Р',
        6: '6 месяцев — 919Р',
        12: '12 месяцев — 1549Р',
    }
    tariff_name = tariff_map.get(months, 'Неизвестно')
    
    # Сохраняем информацию о продлении
    user_payment_data[user_id] = {
        'action': 'extend_subscription',
        'subscription_id': sub_id,
        'months': months,
        'tariff_name': tariff_name
    }
    
    text = f"Вы выбрали продление: <b>{tariff_name}</b>\n\nВыберите способ оплаты:"
    keyboard = [
        [InlineKeyboardButton("CryptoBot (автомат)", callback_data="pay_cryptobot_extend")],
        [InlineKeyboardButton("Binance (ручное подтверждение)", callback_data="pay_binance_extend")],
        [InlineKeyboardButton("Bybit (ручное подтверждение)", callback_data="pay_bybit_extend")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"renew_sub_{sub_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            await query.answer("Ошибка отображения меню. Попробуйте ещё раз.", show_alert=True)
            logger.error(f"Error in extend_sub_payment_callback: {e}")

# Пользователь сообщил об оплате Binance/Bybit (создание новой подписки)
async def binance_paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_id = 2122584931  # <-- ваш ID
    
    payment_info = user_payment_data.get(user_id, {})
    tariff_name = payment_info.get('tariff_name', 'Неизвестный тариф')
    
    # Уведомляем админа
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"Пользователь {user_id} сообщил об оплате через Binance.\nТариф: {tariff_name}\nПодтвердите выдачу ключа.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Подтвердить выдачу ключа", callback_data=f"admin_confirm_binance_{user_id}")]
            ])
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение админу: {e}")
    
    try:
        await query.message.edit_text("Ожидайте подтверждения оплаты администратором.")
    except Exception:
        try:
            await query.message.edit_caption(caption="Ожидайте подтверждения оплаты администратором.")
        except Exception:
            pass

async def bybit_paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_id = 2122584931  # <-- ваш ID
    
    payment_info = user_payment_data.get(user_id, {})
    tariff_name = payment_info.get('tariff_name', 'Неизвестный тариф')
    
    # Уведомляем админа
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"Пользователь {user_id} сообщил об оплате через Bybit.\nТариф: {tariff_name}\nПодтвердите выдачу ключа.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Подтвердить выдачу ключа", callback_data=f"admin_confirm_bybit_{user_id}")]
            ])
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение админу: {e}")
    
    try:
        await query.message.edit_text("Ожидайте подтверждения оплаты администратором.")
    except Exception:
        try:
            await query.message.edit_caption(caption="Ожидайте подтверждения оплаты администратором.")
        except Exception:
            pass

# Админ подтверждает выдачу ключа (создание новой подписки)
async def admin_confirm_binance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = int(data.replace("admin_confirm_binance_", ""))
    
    # Получаем информацию о платеже
    payment_info = user_payment_data.get(user_id, {})
    months = payment_info.get('months', 1)
    
    try:
        result = await subscription_service.issue_subscription(user_id, months)
        if result['success']:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Ваша оплата через Binance подтверждена! Вот ваш ключ:\n{result['vpn_key']}\n\nСсылка для подключения через miniapp:\n{result['miniapp_url']}"
            )
            await query.message.edit_text("Ключ выдан пользователю.")
            # Очищаем данные о платеже
            if user_id in user_payment_data:
                del user_payment_data[user_id]
        else:
            await context.bot.send_message(chat_id=user_id, text=f"Ошибка при создании ключа: {result['error']}")
            await query.message.edit_text("Ошибка при выдаче ключа.")
    except Exception as e:
        logger.error(f"Error in admin_confirm_binance_callback: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"Ошибка при создании ключа: {e}")
        await query.message.edit_text("Ошибка при выдаче ключа.")

async def admin_confirm_bybit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = int(data.replace("admin_confirm_bybit_", ""))
    
    # Получаем информацию о платеже
    payment_info = user_payment_data.get(user_id, {})
    months = payment_info.get('months', 1)
    
    try:
        result = await subscription_service.issue_subscription(user_id, months)
        if result['success']:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Ваша оплата через Bybit подтверждена! Вот ваш ключ:\n{result['vpn_key']}\n\nСсылка для подключения через miniapp:\n{result['miniapp_url']}"
            )
            await query.message.edit_text("Ключ выдан пользователю.")
            # Очищаем данные о платеже
            if user_id in user_payment_data:
                del user_payment_data[user_id]
        else:
            await context.bot.send_message(chat_id=user_id, text=f"Ошибка при создании ключа: {result['error']}")
            await query.message.edit_text("Ошибка при выдаче ключа.")
    except Exception as e:
        logger.error(f"Error in admin_confirm_bybit_callback: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"Ошибка при создании ключа: {e}")
        await query.message.edit_text("Ошибка при выдаче ключа.")

# Главное меню callback обработчик
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Всегда отвечаем на callback_query сразу
    
    data = query.data
    user_id = query.from_user.id
    update_user_info(query.from_user)  # Обновляем информацию о пользователе

    if data == "buy_vpn":
        text = "🛒 <b>Покупка VPN</b>\n\nВыберите действие:"
        keyboard = [
            [InlineKeyboardButton("➕ Купить новый ключ", callback_data="add_sub")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            try:
                await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
        return

    elif data == "renew_vpn":
        text = "🔄 <b>Продление VPN</b>\n\nВыберите действие:"
        keyboard = [
            [InlineKeyboardButton("🔄 Продлить текущий ключ", callback_data="my_subs")],
            [InlineKeyboardButton("➕ Купить новый ключ", callback_data="add_sub")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            try:
                await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
        return

    elif data == "my_subs":
        subscriptions = db.get_user_subscriptions(user_id)
        if not subscriptions:
            text = "📋 У вас нет активных подписок.\n\nНачните с покупки нового VPN ключа!"
            keyboard = [
                [InlineKeyboardButton("➕ Купить VPN", callback_data="add_sub")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                try:
                    await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
                except Exception:
                    await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
            return
                
        caption = "🔑 <b>Список ваших подписок:</b>\n\n"
        buttons = []
        for sub in subscriptions:
            name = sub.get('name') or sub.get('vpn_config') or f"user_{sub.get('client_id', '')[:8]}"
            import re
            key = sub.get('vpn_config', '')
            username = None
            if key:
                m = re.search(r'#([\w\-@.]+)$', key)
                if m:
                    username = m.group(1)
                else:
                    m = re.search(r'email=([\w\-@.]+)', key)
                    if m:
                        username = m.group(1)
            if username:
                name = username
            end_date = sub.get('end_date', '')
            caption += f"│ <code>{name}</code> (до {end_date})\n"
            buttons.append([
                InlineKeyboardButton(f"🔑 {name}", callback_data=f"sub_{sub['id']}"),
                InlineKeyboardButton("✏️", callback_data=f"rename_{sub['id']}")
            ])
        caption += "\n<i>Нажмите на ✏️ чтобы переименовать подписку.</i>"
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(buttons)
        
        try:
            await query.message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            try:
                await query.message.edit_text(text=caption, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=caption, reply_markup=reply_markup, parse_mode="HTML")
        return

    elif data == "balance":
        user = db.get_user(user_id)
        balance = user.get('balance', 0) if user else 0
        text = (
            "💰 <b>Управление балансом</b>\n\n"
            f"Ваш баланс: <b>{balance} RUB</b>"
        )
        keyboard = [
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="balance_topup")],
            [InlineKeyboardButton("📊 История пополнения", callback_data="balance_history")],
            [InlineKeyboardButton("🎫 Активировать купон", callback_data="balance_coupon")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            try:
                await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
        return

    elif data == "invite":
        username = query.from_user.username or ""
        referral_link = f"https://t.me/{context.bot.username}?start=ref{user_id}"
        total_invited = 0
        total_bonus = 0.0
        
        if hasattr(db, 'get_referral_stats'):
            stats = db.get_referral_stats(user_id)
            total_invited = stats.get('referral_count', 0)
            total_bonus = stats.get('total_earnings', 0.0)
            level_stats = stats.get('level_stats', {})
            if level_stats:
                details = "\n".join([f"{lvl}: {cnt} чел." for lvl, cnt in level_stats.items()])
            else:
                details = "—"
        else:
            details = "—"

        text = (
            "👥 <b>Ваша реферальная ссылка:</b>\n\n"
            f"<a href=\"{referral_link}\">{referral_link}</a>\n\n"
            "🤝 <b>Приглашайте друзей и получайте крутые бонусы на каждом уровне!</b> 💰\n\n"
            "🏆 <b>Бонусы за приглашения:</b>\n"
            "<pre>"
            "1 уровень: 🌟 25% бонуса\n"
            "2 уровень: 🌟 10% бонуса\n"
            "3 уровень: 🌟 6% бонуса\n"
            "4 уровень: 🌟 5% бонуса\n"
            "5 уровень: 🌟 4% бонуса\n"
            "</pre>\n"
            "📊 <b>Статистика приглашений:</b>\n"
            f"👥 Всего приглашено: {total_invited} человек\n"
            "📝 Детальная статистика по уровням:\n"
            f"<pre>{details}</pre>\n"
            f"💰 <b>Общий бонус от рефералов: {total_bonus} RUB</b>"
        )
        keyboard = [
            [InlineKeyboardButton("📨 Пригласить", switch_inline_query="")],
            [InlineKeyboardButton("📷 Показать QR-код", callback_data="show_qr")],
            [InlineKeyboardButton("🏆 Top-5", callback_data="top5")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            try:
                await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
        return

    elif data == "gift":
        text = "🎁 <b>Подарки</b>\n\nДарите подарки и следите, чтобы они дошли до адресата! 🎄"
        keyboard = [
            [InlineKeyboardButton("🎁 Подарить подписку", callback_data="gift_give")],
            [InlineKeyboardButton("🎁 Мои подарки", callback_data="gift_my")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            try:
                await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
        return

    elif data == "about":
        text = (
            "ℹ️ <b>О сервисе</b>\n\n"
            "📬 <b>Контакты:</b>\n\n"
            "<b>🔔 Подпишись на наш канал!</b>\n"
            "Следи за всеми новостями сервиса!\n"
            "Получай свежие обновления.\n"
            "Узнавай о новых тарифах.\n"
            "Участвуй в крутых акциях.\n"
            "Лови эксклюзивные подарки!\n\n"
            "<b>🛠 Техническая поддержка</b>\n"
            "Пиши нам без стеснения!\n"
            "Решаем любые вопросы по VPN.\n"
            "Помогаем с настройкой.\n"
            "Разбираемся с любыми сложностями!\n\n"
            "<i>Продолжая использование сервиса, вы соглашаетесь с правилами предоставления услуг:</i>\n"
            "<a href='https://t.me/your_channel'>Политика конфиденциальности</a>"
        )
        keyboard = [
            [InlineKeyboardButton("💬 Поддержка", url="https://t.me/your_support")],
            [InlineKeyboardButton("📢 Канал", url="https://t.me/your_channel")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            try:
                await query.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
        return

    else:
        # Неизвестная команда
        await query.answer("Неизвестная команда меню.", show_alert=True)

# Обработчик для неизвестных callback
async def handle_unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Функция временно недоступна", show_alert=True)
    logger.info(f"Unhandled callback: {query.data}")

# Детали подписки
async def subscription_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    sub_id = data.replace("sub_", "")
    sub = None
    
    # Получаем подписку по id
    if hasattr(db, 'get_subscription_by_id'):
        sub = db.get_subscription_by_id(sub_id)
    else:
        subs = db.get_user_subscriptions(user_id)
        for s in subs:
            if str(s.get('id')) == sub_id:
                sub = s
                break
    
    if not sub:
        await query.answer("Подписка не найдена", show_alert=True)
        return
    
    # Данные подписки
    key = sub.get('vpn_config', '')
    expires = sub.get('end_date', '')
    tariff = sub.get('subscription_type', '—')
    
    # Преобразуем дату в формат "18 Августа 2025 года"
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except:
        pass  # На Windows может не работать, fallback ниже
    
    try:
        dt = datetime.fromisoformat(expires)
        expires_str = dt.strftime('%d %B %Y года')
    except:
        expires_str = expires
    
    # Осталось времени
    try:
        now = datetime.now()
        left = dt - now
        days = left.days
        hours = left.seconds // 3600
        minutes = (left.seconds % 3600) // 60
        left_str = f"{days} дн, {hours} часов, {minutes} минут"
    except:
        left_str = "—"
    
    # Имя тарифа
    TARIFFS = {
        "trial": "Пробная подписка 5 дней",
        "1_99": "1 месяц",
        "2_179": "2 месяца",
        "6_499": "6 месяцев",
        "12_899": "1 год"
    }
    tariff_name = TARIFFS.get(tariff, tariff)
    
    # Лимит трафика (пример: 50 ГБ для trial, иначе ∞)
    traffic_limit = "50 ГБ" if tariff == "trial" else "∞"
    
    # miniapp url
    miniapp_url = f"https://maksim200738-droid.github.io/rockvpn/?key={key}&expires={expires}"
    
    # Оформление подписи
    caption = (
        "<b>🗝️ Ваша подписка:</b>\n\n"
        f"<a href=\"{miniapp_url}\">{miniapp_url}</a>\n\n"
        "<b>📦 Информация о тарифе:</b>\n"
        f"<pre>📅 Тариф: {tariff_name}\n📊 Трафик: {traffic_limit}</pre>\n\n"
        "<b>🔴 Статус подписки:</b>\n"
        f"<pre>⏳ Осталось: {left_str}\n📅 Истекает: {expires_str}</pre>\n\n"
        "<i>Подключите свое устройство по кнопкам ниже ⬇️</i>"
    )
    
    # Кнопки
    keyboard = [
        [InlineKeyboardButton("📲 Подключить устройство", web_app=WebAppInfo(url=miniapp_url))],
        [InlineKeyboardButton("📺 Андроид TV", callback_data=f"android_tv_{sub_id}")],
        [InlineKeyboardButton("🖼 Показать QR-код", callback_data=f"show_qr_{sub_id}")],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"delete_sub_{sub_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="my_subs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Фото
    photo_url = "https://i.imgur.com/your-image.png"
    
    # Отправка
    try:
        await query.message.delete()
    except:
        pass
    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=photo_url,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def show_qr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    sub_id = data.replace("show_qr_", "")
    
    # Получаем подписку
    sub = None
    if hasattr(db, 'get_subscription_by_id'):
        sub = db.get_subscription_by_id(sub_id)
    else:
        subs = db.get_user_subscriptions(user_id)
        for s in subs:
            if str(s.get('id')) == sub_id:
                sub = s
                break
    
    if not sub:
        await query.answer("Подписка не найдена", show_alert=True)
        return
    
    key = sub.get('vpn_config', '')
    
    # Генерируем QR-код
    img = qrcode.make(key)
    bio = BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    
    text = (
        "🖼 <b>QR-код для подключения</b>\n\n"
        "Отсканируйте этот код в приложении Hiddify или другом VPN-клиенте.\n\n"
        "<i>Для возврата нажмите кнопку ниже</i>"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"sub_{sub_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=bio,
        caption=text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def delete_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    sub_id = data.replace("delete_sub_", "")
    
    # Деактивируем подписку
    if hasattr(db, 'deactivate_subscription'):
        db.deactivate_subscription(sub_id)
    
    # Сообщение об удалении
    try:
        await query.message.edit_caption(
            caption="❌ Подписка удалена.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="my_subs")]]),
            parse_mode="HTML"
        )
    except Exception:
        await query.message.edit_text(
            text="❌ Подписка удалена.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="my_subs")]]),
            parse_mode="HTML"
        )
    await query.answer("Подписка удалена", show_alert=True)

async def android_tv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    sub_id = data.replace("android_tv_", "")
    
    # Получаем подписку
    sub = None
    if hasattr(db, 'get_subscription_by_id'):
        sub = db.get_subscription_by_id(sub_id)
    else:
        subs = db.get_user_subscriptions(user_id)
        for s in subs:
            if str(s.get('id')) == sub_id:
                sub = s
                break
    
    if not sub:
        await query.answer("Подписка не найдена", show_alert=True)
        return
    
    # Ссылка на Android TV клиент (пример)
    tv_link = "https://play.google.com/store/apps/details?id=app.hiddify.com.tv"
    text = (
        "📺 <b>Android TV</b>\n\n"
        f"<a href=\"{tv_link}\">Скачать Hiddify TV</a>\n\n"
        "1. Установите приложение на Android TV\n"
        "2. Откройте и импортируйте ключ через QR-код или ссылку из вашей подписки.\n\n"
        "<i>Для возврата нажмите кнопку ниже</i>"
    )
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"sub_{sub_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_caption(
            caption=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except Exception:
        await query.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

async def rename_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    sub_id = query.data.replace("rename_", "")
    context.user_data['rename_sub_id'] = sub_id
    
    try:
        await query.message.edit_caption(
            caption="✏️ Введите новое имя подписки (до 10 символов):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="my_subs")]])
        )
    except Exception:
        await query.message.edit_text(
            text="✏️ Введите новое имя подписки (до 10 символов):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="my_subs")]])
        )
    return RENAME_SUB

async def process_rename_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    if len(new_name) > 10:
        await update.message.reply_text("❌ Имя слишком длинное! Введите до 10 символов.")
        return RENAME_SUB
    
    sub_id = context.user_data.get('rename_sub_id')
    if not sub_id:
        await update.message.reply_text("❌ Ошибка. Попробуйте ещё раз.")
        return ConversationHandler.END
    
    # Сохраняем новое имя в базе
    if hasattr(db, 'rename_subscription'):
        db.rename_subscription(sub_id, new_name)
    elif hasattr(db, 'update_subscription_name'):
        db.update_subscription_name(sub_id, new_name)
    elif hasattr(db, 'update_subscription'):
        db.update_subscription(sub_id, {'name': new_name})
    
    await update.message.reply_text("✅ Имя подписки изменено!")
    
    # Показываем обновлённый список
    class DummyQuery:
        def __init__(self, user_id, message):
            self.data = "my_subs"
            self.from_user = type('User', (), {'id': user_id})
            self.message = message
        async def answer(self, *a, **kw):
            pass
    
    dummy_update = type('Update', (), {'callback_query': DummyQuery(update.effective_user.id, update.message)})
    await main_menu_callback(dummy_update, context)
    return ConversationHandler.END

# Обработчик для меню продления подписки
async def renew_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    sub_id = data.replace("renew_sub_", "")
    
    # Получаем подписку
    sub = None
    if hasattr(db, 'get_subscription_by_id'):
        sub = db.get_subscription_by_id(sub_id)
    else:
        subs = db.get_user_subscriptions(user_id)
        for s in subs:
            if str(s.get('id')) == sub_id:
                sub = s
                break
    
    if not sub:
        await query.answer("Подписка не найдена", show_alert=True)
        return

    # Пример меню продления
    balance = 0.0
    user = db.get_user(user_id)
    if user:
        balance = user.get('balance', 0.0)
    
    expires = sub.get('end_date', '')
    text = (
        "📋 Выберите план продления:\n\n"
        f"💰 Баланс: {balance} руб.\n\n"
        f"📅 Текущая дата истечения подписки: {expires} 🔑"
    )
    keyboard = [
        [InlineKeyboardButton("1 месяц — 179Р", callback_data=f"extend_{sub_id}_1")],
        [InlineKeyboardButton("3 месяца — 474Р", callback_data=f"extend_{sub_id}_3")],
        [InlineKeyboardButton("6 месяцев — 919Р", callback_data=f"extend_{sub_id}_6")],
        [InlineKeyboardButton("12 месяцев — 1549Р", callback_data=f"extend_{sub_id}_12")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_caption(
            caption=text,
            reply_markup=reply_markup
        )
    except Exception:
        await query.message.edit_text(
            text=text,
            reply_markup=reply_markup
        )

# Обработчик для добавления новой подписки
async def add_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Меню выбора тарифа для создания нового ключа
    text = "📋 Выберите тарифный план для создания нового ключа:"
    keyboard = [
        [InlineKeyboardButton("1 месяц — 179Р", callback_data="create_sub_1")],
        [InlineKeyboardButton("3 месяца — 474Р", callback_data="create_sub_3")],
        [InlineKeyboardButton("6 месяцев — 919Р", callback_data="create_sub_6")],
        [InlineKeyboardButton("12 месяцев — 1549Р", callback_data="create_sub_12")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_caption(caption=text, reply_markup=reply_markup)
    except Exception:
        await query.message.edit_text(text=text, reply_markup=reply_markup)

# Оплата через CryptoBot (автомат) для создания новой подписки
async def pay_cryptobot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    # Здесь должна быть интеграция с CryptoBot API для создания invoice
    # Для примера — просто отправим ссылку-заглушку
    invoice_url = "https://t.me/CryptoBot?start=shop-example"  # <-- замените на реальный invoice
    text = f"<b>Оплата через CryptoBot</b>\n\nПерейдите по ссылке для оплаты:\n<a href='{invoice_url}'>Оплатить через CryptoBot</a>\n\nПосле оплаты ключ будет выдан автоматически!"
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="add_sub")]]
    
    try:
        await query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except Exception:
        try:
            await query.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            pass

# Оплата через Binance (ручное подтверждение) для создания новой подписки
async def pay_binance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_id = 2122584931  # <-- ваш ID
    binance_wallet = "binance_test_wallet"  # <-- замените на свой кошелек
    
    text = (
        f"<b>Оплата через Binance</b>\n\n"
        f"Переведите сумму на кошелек: <code>{binance_wallet}</code>\n"
        "После оплаты нажмите кнопку ниже. Админ проверит поступление и выдаст ключ."
    )
    keyboard = [
        [InlineKeyboardButton("Я оплатил", callback_data="binance_paid")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="add_sub")]
    ]
    
    try:
        await query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except Exception:
        try:
            await query.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            pass

# Оплата через Bybit (ручное подтверждение) для создания новой подписки
async def pay_bybit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_id = 2122584931  # <-- ваш ID
    bybit_wallet = "bybit_test_wallet"  # <-- замените на свой кошелек
    
    text = (
        f"<b>Оплата через Bybit</b>\n\n"
        f"Переведите сумму на кошелек: <code>{bybit_wallet}</code>\n"
        "После оплаты нажмите кнопку ниже. Админ проверит поступление и выдаст ключ."
    )
    keyboard = [
        [InlineKeyboardButton("Я оплатил", callback_data="bybit_paid")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="add_sub")]
    ]
    
    try:
        await query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except Exception:
        try:
            await query.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            pass

# Аналогичные обработчики для продления подписки (extend)
async def pay_cryptobot_extend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    invoice_url = "https://t.me/CryptoBot?start=shop-example"  # <-- замените на реальный invoice
    text = f"<b>Оплата продления через CryptoBot</b>\n\nПерейдите по ссылке для оплаты:\n<a href='{invoice_url}'>Оплатить через CryptoBot</a>\n\nПосле оплаты подписка будет продлена автоматически!"
    
    payment_info = user_payment_data.get(user_id, {})
    sub_id = payment_info.get('subscription_id', '')
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"renew_sub_{sub_id}")]]
    
    try:
        await query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except Exception:
        try:
            await query.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            pass

async def pay_binance_extend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_id = 2122584931  # <-- ваш ID
    binance_wallet = "binance_test_wallet"  # <-- замените на свой кошелек
    
    payment_info = user_payment_data.get(user_id, {})
    sub_id = payment_info.get('subscription_id', '')
    
    text = (
        f"<b>Оплата продления через Binance</b>\n\n"
        f"Переведите сумму на кошелек: <code>{binance_wallet}</code>\n"
        "После оплаты нажмите кнопку ниже. Админ проверит поступление и продлит подписку."
    )
    keyboard = [
        [InlineKeyboardButton("Я оплатил", callback_data="binance_paid_extend")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"renew_sub_{sub_id}")]
    ]
    
    try:
        await query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except Exception:
        try:
            await query.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            pass

async def pay_bybit_extend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_id = 2122584931  # <-- ваш ID
    bybit_wallet = "bybit_test_wallet"  # <-- замените на свой кошелек
    
    payment_info = user_payment_data.get(user_id, {})
    sub_id = payment_info.get('subscription_id', '')
    
    text = (
        f"<b>Оплата продления через Bybit</b>\n\n"
        f"Переведите сумму на кошелек: <code>{bybit_wallet}</code>\n"
        "После оплаты нажмите кнопку ниже. Админ проверит поступление и продлит подписку."
    )
    keyboard = [
        [InlineKeyboardButton("Я оплатил", callback_data="bybit_paid_extend")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"renew_sub_{sub_id}")]
    ]
    
    try:
        await query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    except Exception:
        try:
            await query.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except Exception:
            pass

async def binance_paid_extend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_id = 2122584931  # <-- ваш ID
    
    payment_info = user_payment_data.get(user_id, {})
    sub_id = payment_info.get('subscription_id', '')
    tariff_name = payment_info.get('tariff_name', 'Неизвестный тариф')
    
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"Пользователь {user_id} сообщил об оплате продления через Binance (подписка {sub_id}).\nТариф: {tariff_name}\nПодтвердите продление.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Подтвердить продление", callback_data=f"admin_confirm_binance_extend_{user_id}_{sub_id}")]
            ])
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение админу: {e}")
    
    try:
        await query.message.edit_text("Ожидайте подтверждения оплаты администратором.")
    except Exception:
        try:
            await query.message.edit_caption(caption="Ожидайте подтверждения оплаты администратором.")
        except Exception:
            pass

async def bybit_paid_extend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    admin_id = 2122584931  # <-- ваш ID
    
    payment_info = user_payment_data.get(user_id, {})
    sub_id = payment_info.get('subscription_id', '')
    tariff_name = payment_info.get('tariff_name', 'Неизвестный тариф')
    
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=f"Пользователь {user_id} сообщил об оплате продления через Bybit (подписка {sub_id}).\nТариф: {tariff_name}\nПодтвердите продление.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Подтвердить продление", callback_data=f"admin_confirm_bybit_extend_{user_id}_{sub_id}")]
            ])
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение админу: {e}")
    
    try:
        await query.message.edit_text("Ожидайте подтверждения оплаты администратором.")
    except Exception:
        try:
            await query.message.edit_caption(caption="Ожидайте подтверждения оплаты администратором.")
        except Exception:
            pass

async def admin_confirm_binance_extend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.replace("admin_confirm_binance_extend_", "").split('_')
    user_id = int(parts[0])
    sub_id = parts[1]
    
    # Получаем информацию о продлении
    payment_info = user_payment_data.get(user_id, {})
    months = payment_info.get('months', 1)
    
    try:
        result = await subscription_service.extend_subscription(sub_id, months)
        if result['success']:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Ваша оплата через Binance подтверждена! Подписка продлена.\n\nОбновленный ключ:\n{result['vpn_key']}\n\nСсылка для подключения через miniapp:\n{result['miniapp_url']}"
            )
            await query.message.edit_text("Продление подтверждено и подписка продлена.")
            
            # Очищаем данные о платеже
            if user_id in user_payment_data:
                del user_payment_data[user_id]
        else:
            await context.bot.send_message(chat_id=user_id, text=f"Ошибка продления: {result['error']}")
            await query.message.edit_text("Ошибка при продлении подписки.")
    except Exception as e:
        logger.error(f"Error in admin_confirm_binance_extend_callback: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"Ошибка продления: {e}")
        await query.message.edit_text("Ошибка при продлении подписки.")

async def admin_confirm_bybit_extend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.replace("admin_confirm_bybit_extend_", "").split('_')
    user_id = int(parts[0])
    sub_id = parts[1]

    # Получаем информацию о продлении
    payment_info = user_payment_data.get(user_id, {})
    months = payment_info.get('months', 1)
    
    try:
        result = await subscription_service.extend_subscription(sub_id, months)
        if result['success']:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Ваша оплата через Bybit подтверждена! Подписка продлена.\n\nОбновленный ключ:\n{result['vpn_key']}\n\nСсылка для подключения через miniapp:\n{result['miniapp_url']}"
            )
            await query.message.edit_text("Продление подтверждено и подписка продлена.")
            
            # Очищаем данные о платеже
            if user_id in user_payment_data:
                del user_payment_data[user_id]
        else:
            await context.bot.send_message(chat_id=user_id, text=f"Ошибка продления: {result['error']}")
            await query.message.edit_text("Ошибка при продлении подписки.")
    except Exception as e:
        logger.error(f"Error in admin_confirm_bybit_extend_callback: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"Ошибка продления: {e}")
        await query.message.edit_text("Ошибка при продлении подписки.")

def main():
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()
    
    # ConversationHandler для переименования подписки (должен быть первым)
    rename_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(rename_sub_callback, pattern="^rename_")],
        states={
            RENAME_SUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_rename_sub)]
        },
        fallbacks=[CallbackQueryHandler(main_menu_callback, pattern="^my_subs$")],
        per_message=True
    )
    application.add_handler(rename_conv)

    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", back_to_menu))
    application.add_handler(CommandHandler("test_api", test_api))
    application.add_handler(MessageHandler(filters.Regex("^Главное меню$"), back_to_menu))
    
    # Специфичные callback handlers (должны быть перед общими)
    application.add_handler(CallbackQueryHandler(subscription_detail_callback, pattern="^sub_\\d+$"))
    application.add_handler(CallbackQueryHandler(show_qr_callback, pattern="^show_qr_\\d+$"))
    application.add_handler(CallbackQueryHandler(delete_sub_callback, pattern="^delete_sub_\\d+$"))
    application.add_handler(CallbackQueryHandler(android_tv_callback, pattern="^android_tv_\\d+$"))
    application.add_handler(CallbackQueryHandler(renew_sub_callback, pattern="^renew_sub_\\d+$"))
    application.add_handler(CallbackQueryHandler(extend_sub_payment_callback, pattern="^extend_\\d+_(1|3|6|12)$"))
    
    # Обработчики покупки и оплаты
    application.add_handler(CallbackQueryHandler(add_sub_callback, pattern="^add_sub$"))
    application.add_handler(CallbackQueryHandler(create_sub_payment_callback, pattern="^create_sub_(1|3|6|12)$"))
    
    # Обработчики оплаты для новых подписок
    application.add_handler(CallbackQueryHandler(pay_cryptobot_callback, pattern="^pay_cryptobot$"))
    application.add_handler(CallbackQueryHandler(pay_binance_callback, pattern="^pay_binance$"))
    application.add_handler(CallbackQueryHandler(pay_bybit_callback, pattern="^pay_bybit$"))
    application.add_handler(CallbackQueryHandler(binance_paid_callback, pattern="^binance_paid$"))
    application.add_handler(CallbackQueryHandler(bybit_paid_callback, pattern="^bybit_paid$"))
    
    # Обработчики оплаты для продления
    application.add_handler(CallbackQueryHandler(pay_cryptobot_extend_callback, pattern="^pay_cryptobot_extend$"))
    application.add_handler(CallbackQueryHandler(pay_binance_extend_callback, pattern="^pay_binance_extend$"))
    application.add_handler(CallbackQueryHandler(pay_bybit_extend_callback, pattern="^pay_bybit_extend$"))
    application.add_handler(CallbackQueryHandler(binance_paid_extend_callback, pattern="^binance_paid_extend$"))
    application.add_handler(CallbackQueryHandler(bybit_paid_extend_callback, pattern="^bybit_paid_extend$"))
    
    # Админские обработчики
    application.add_handler(CallbackQueryHandler(admin_confirm_binance_callback, pattern="^admin_confirm_binance_\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_confirm_bybit_callback, pattern="^admin_confirm_bybit_\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_confirm_binance_extend_callback, pattern="^admin_confirm_binance_extend_\\d+_\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_confirm_bybit_extend_callback, pattern="^admin_confirm_bybit_extend_\\d+_\\d+$"))
    
    # Общие обработчики (должны быть в конце)
    application.add_handler(CallbackQueryHandler(start, pattern="^profile$"))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^(buy_vpn|renew_vpn|my_subs|balance|invite|gift|about)$"))
    
    # Обработчик для всех остальных callback_query (fallback)
    application.add_handler(CallbackQueryHandler(handle_unknown_callback))
    
    logger.info("Bot started successfully!")
    application.run_polling()

if __name__ == "__main__":
    main()