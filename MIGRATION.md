# Миграция с RemnaWave на Marzban Panel

Этот документ описывает процесс миграции телеграм бота с RemnaWave API на Marzban Panel API.

## Что изменилось

### 1. API структура

**RemnaWave:**
- Использовал API ключ для аутентификации
- Endpoints: `/users`, `/users/{id}/config`
- Возвращал данные в поле `response`

**Marzban:**
- Использует username/password для получения JWT токена
- Endpoints: `/api/user`, `/api/user/{username}`, `/sub/{username}`
- Возвращает данные напрямую в JSON

### 2. Аутентификация

**Было (RemnaWave):**
```python
self.api_key = os.getenv('REMNA_API_KEY')
self.session.headers.update({'Authorization': f'Bearer {self.api_key}'})
```

**Стало (Marzban):**
```python
self.api_username = os.getenv('MARZBAN_USERNAME')
self.api_password = os.getenv('MARZBAN_PASSWORD')
# Получаем токен через POST /api/admin/token
self.session.headers.update({'Authorization': f'Bearer {access_token}'})
```

### 3. Создание пользователей

**Было (RemnaWave):**
```python
data = {
    "username": username,
    "email": email,
    "expireAt": dt.isoformat() + "Z"
}
response = self.session.post(f"{self.api_url}/users", json=data)
```

**Стало (Marzban):**
```python
user_data = {
    "username": username,
    "proxies": {"vless": {}, "vmess": {}, "trojan": {}, "shadowsocks": {}},
    "data_limit": 0,
    "expire": int(dt.timestamp()),
    "status": "active"
}
response = self.session.post(f"{self.api_url}/api/user", json=user_data)
```

### 4. Получение конфигурации

**Было (RemnaWave):**
- Несколько endpoints для поиска конфигурации
- Конфигурация в JSON поле

**Стало (Marzban):**
- `/api/user/{username}` - информация о пользователе
- `/sub/{username}` - subscription URL с конфигурацией

### 5. Переменные окружения

**Было:**
```env
REMNA_API_URL=https://your-remna-panel.com
REMNA_API_KEY=your_api_key
```

**Стало:**
```env
MARZBAN_API_URL=https://your-marzban-panel.com
MARZBAN_USERNAME=admin
MARZBAN_PASSWORD=your_admin_password
```

## Шаги миграции

### 1. Обновите переменные окружения

1. Скопируйте `.env.example` в `.env`
2. Заполните новые переменные:
   - `MARZBAN_API_URL` - URL вашей Marzban панели
   - `MARZBAN_USERNAME` - имя администратора
   - `MARZBAN_PASSWORD` - пароль администратора

### 2. Обновите зависимости

```bash
pip install -r requirements.txt
```

### 3. Протестируйте подключение

```bash
python3 bot.py
```

Отправьте боту команду `/test_api` (только для админа) для проверки подключения.

### 4. Миграция данных пользователей

**Важно:** Существующие пользователи в RemnaWave НЕ будут автоматически перенесены в Marzban. 

Варианты действий:
1. **Ручная миграция**: Создайте пользователей в Marzban вручную
2. **Уведомление пользователей**: Сообщите пользователям о необходимости создать новые подписки
3. **Скрипт миграции**: Напишите скрипт для автоматического переноса (требует доступа к обеим панелям)

### 5. Обновите документацию

Обновите инструкции для пользователей с учетом новой структуры конфигураций Marzban.

## Проверка миграции

### 1. Проверьте API подключение
```bash
# В боте отправьте команду админу
/test_api
```

### 2. Создайте тестового пользователя
- Используйте функцию создания подписки в боте
- Проверьте, что пользователь появился в Marzban панели

### 3. Проверьте получение конфигурации
- Получите конфигурацию через бота
- Убедитесь, что subscription URL работает

## Возможные проблемы

### 1. Ошибки аутентификации
**Проблема:** `Authentication failed`
**Решение:** 
- Проверьте правильность MARZBAN_USERNAME и MARZBAN_PASSWORD
- Убедитесь, что пользователь имеет административные права

### 2. Ошибки SSL/TLS
**Проблема:** SSL certificate verification failed
**Решение:**
- Проверьте SSL сертификат Marzban панели
- Для тестирования можно временно отключить проверку SSL (не рекомендуется для продакшн)

### 3. Ошибки создания пользователей
**Проблема:** User creation failed
**Решение:**
- Проверьте настройки протоколов в Marzban
- Убедитесь, что не достигнуты лимиты пользователей

### 4. Недоступность конфигурации
**Проблема:** Config not available
**Решение:**
- Проверьте, что subscription URL доступен
- Убедитесь, что пользователь активен в Marzban

## Откат изменений

Если нужно вернуться к RemnaWave:

1. Восстановите старые переменные окружения:
```env
REMNA_API_URL=https://your-remna-panel.com
REMNA_API_KEY=your_api_key
```

2. Откатите изменения в `bot.py` через git:
```bash
git checkout HEAD~1 bot.py
```

## Поддержка

При возникновении проблем:
1. Проверьте логи бота
2. Убедитесь в доступности Marzban панели
3. Проверьте настройки API в Marzban
4. Используйте команду `/test_api` для диагностики

## Преимущества Marzban

- **Более стабильный API**: Стандартная REST структура
- **Лучшая документация**: Swagger UI доступен по адресу `/docs`
- **Активная разработка**: Регулярные обновления и исправления
- **Больше функций**: Расширенные возможности управления пользователями
- **Лучшая производительность**: Оптимизированная работа с базой данных