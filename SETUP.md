# 🚀 Быстрая настройка бота для Marzban Panel

## ⚠️ Исправлены ошибки из логов

1. **Ошибка `AttributeError: 'tuple' object has no attribute 'get'`** ✅ ИСПРАВЛЕНА
2. **Предупреждение PTB ConversationHandler** ✅ ИСПРАВЛЕНО
3. **Ошибка подключения к API** - нужно настроить .env файл

## 📝 Пошаговая настройка

### 1. Создайте .env файл

Скопируйте `.env.example` в `.env`:

**Windows:**
```cmd
copy .env.example .env
```

**Linux/Mac:**
```bash
cp .env.example .env
```

### 2. Отредактируйте .env файл

Откройте `.env` в любом текстовом редакторе и замените значения:

```env
# Telegram Bot Configuration
BOT_TOKEN=7722199455:AAGk1iE9vUuEEyGCyL8KtHjVaNEMCSeSyvI

# Marzban Panel Configuration
MARZBAN_API_URL=https://ваш-домен-marzban.com
MARZBAN_USERNAME=admin
MARZBAN_PASSWORD=ваш_пароль_админа

# Admin Configuration  
ADMIN_ID=ваш_telegram_id

# Database Configuration
DATABASE_URL=sqlite:///vpn_bot.db
```

### 3. Найдите ваш Telegram ID

Отправьте сообщение боту @userinfobot или @getidsbot, чтобы узнать ваш ID.

### 4. Проверьте настройки Marzban

1. Откройте вашу Marzban панель в браузере
2. Убедитесь, что можете войти с указанными username/password
3. Проверьте доступность API по адресу: `https://ваш-домен/docs`

### 5. Запустите бота

```cmd
python bot.py
```

### 6. Протестируйте

1. Найдите вашего бота в Telegram
2. Отправьте команду `/start`
3. Отправьте команду `/test_api` (только для админа)

## 🔧 Примеры правильных настроек

### Если Marzban на локальном сервере:
```env
MARZBAN_API_URL=http://localhost:8000
```

### Если Marzban с доменом:
```env
MARZBAN_API_URL=https://panel.example.com
```

### Если Marzban на IP с портом:
```env
MARZBAN_API_URL=http://192.168.1.100:8000
```

## ❗ Частые ошибки

### 1. "Failed to establish a new connection"
- Проверьте правильность MARZBAN_API_URL
- Убедитесь, что Marzban панель запущена и доступна

### 2. "Authentication failed" 
- Проверьте MARZBAN_USERNAME и MARZBAN_PASSWORD
- Убедитесь, что пользователь имеет права администратора

### 3. "getaddrinfo failed"
- Проверьте правильность домена в MARZBAN_API_URL
- Попробуйте заменить домен на IP адрес

## 🎯 После успешного запуска

1. Бот покажет "Bot started successfully!" в логах
2. Команда `/test_api` должна вернуть "✅ API доступен"
3. Можно создавать VPN подписки через меню бота

## 📞 Поддержка

Если проблемы остались, проверьте:
- Логи бота на наличие других ошибок
- Доступность Marzban панели через браузер
- Правильность всех параметров в .env файле