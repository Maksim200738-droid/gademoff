import requests
from bs4 import BeautifulSoup as bs
import re
import json
import os
import time
from datetime import datetime


# Лог-файл для попыток публикации
LOG_PATH = "funpay_post_debug.log"


def append_post_log(event: str, data: dict):
    try:
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": event,
            **data
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Ошибка записи лога: {e}")


# --- Telegram ---
def send_file_to_telegram(bot_token: str, chat_id: str, file_path: str, caption: str | None = None) -> bool:
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        with open(file_path, 'rb') as f:
            files = {"document": (os.path.basename(file_path), f)}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            resp = requests.post(url, data=data, files=files, timeout=30)
        if resp.status_code == 200 and resp.json().get("ok"):
            print("Файл отправлен в Telegram.")
            return True
        else:
            print(f"Не удалось отправить файл в Telegram: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")
        return False


def send_text_to_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
        return resp.status_code == 200 and resp.json().get("ok")
    except Exception:
        return False


def run_telegram_polling(bot_token: str, chat_id: str, file_path: str):
    print("Запускаю Telegram-поллинг. Команды: /status, /gk <key>, /create_url <url>, /parse_url <url>, /markup <percent>, /range <min> <max>, /post, /file, /stop")
    last_update_id = None
    # Загружаем и держим настройки в памяти
    state = load_config()
    # Значения по умолчанию
    state.setdefault("golden_key", "")
    state.setdefault("create_lot_url", "")
    state.setdefault("parse_lot_url", "")
    state.setdefault("markup_percent", 0.0)
    state.setdefault("price_min", 0.0)
    state.setdefault("price_max", 0.0)  # 0 = без верхней границы
    # Зафиксируем чат: если chat_id пуст, привяжем к первому сообщению
    bound_chat_id = str(chat_id) if chat_id else ""
    save_config(state)

    def keyboard_json() -> str:
        kb = {
            "keyboard": [
                ["📋 Статус", "▶️ Запустить"],
                ["🔑 Указать Golden Key", "🧭 Ссылка создания лота"],
                ["🔎 Ссылка для парсинга", "📈 Наценка"],
                ["💰 Диапазон цен", "📄 Файл"],
                ["ℹ️ Помощь", "⛔ Стоп"]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }
        try:
            return json.dumps(kb, ensure_ascii=False)
        except Exception:
            return ""

    def send_with_kb(chat: str, text: str):
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat, "text": text, "reply_markup": keyboard_json()}
            requests.post(url, data=payload, timeout=15)
        except Exception:
            pass

    def send_help(chat: str):
        txt = (
            "Кнопки:\n\n"
            "🔑 Указать Golden Key — сохранит ваш ключ доступа.\n"
            "🧭 Ссылка создания лота — URL вида https://funpay.com/lots/offerEdit?node=700.\n"
            "🔎 Ссылка для парсинга — раздел лотов, например https://funpay.com/lots/700/.\n"
            "📈 Наценка — процент наценки (например 15).\n"
            "💰 Диапазон цен — min max (0 вместо max — без верхней границы).\n"
            "📋 Статус — показать текущие настройки.\n"
            "▶️ Запустить — выполнить парсинг и публикацию.\n"
            "📄 Файл — прислать файл funpay_items.txt.\n"
            "⛔ Стоп — остановить бота (только из привязанного чата).\n\n"
            "Также доступны команды: /status, /gk, /create_url, /parse_url, /markup, /range, /post, /file, /stop"
        )
        send_with_kb(chat, txt)

    # Сразу очистим старые непрочитанные апдейты, чтобы не схватить древний /stop
    try:
        purge_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        purge = requests.get(purge_url, params={"timeout": 0}, timeout=10)
        if purge.status_code == 200 and purge.json().get("ok"):
            res = purge.json().get("result", [])
            if res:
                last_update_id = res[-1]["update_id"]
    except Exception:
        pass

    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            params = {"timeout": 50}
            if last_update_id is not None:
                params["offset"] = last_update_id + 1
            r = requests.get(url, params=params, timeout=60)
            if r.status_code != 200:
                time.sleep(2)
                continue
            data = r.json()
            if not data.get("ok"):
                time.sleep(2)
                continue
            for upd in data.get("result", []):
                last_update_id = upd["update_id"]
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                from_chat = str(msg.get("chat", {}).get("id"))
                # Привязка чата если не задан
                if not bound_chat_id:
                    bound_chat_id = from_chat
                    state_cfg = load_config()
                    state_cfg["tg_chat_id"] = bound_chat_id
                    save_config(state_cfg)
                    send_with_kb(from_chat, "Чат привязан. Нажмите ℹ️ Помощь для инструкции.")
                if bound_chat_id and from_chat != bound_chat_id:
                    continue
                text = (msg.get("text", "") or "").strip()
                # Кнопки → подсказки к командам
                if text == "📋 Статус":
                    text = "/status"
                elif text == "▶️ Запустить":
                    text = "/post"
                elif text == "🔑 Указать Golden Key":
                    send_with_kb(from_chat, "Отправьте: /gk ВАШ_КЛЮЧ")
                    continue
                elif text == "🧭 Ссылка создания лота":
                    send_with_kb(from_chat, "Отправьте: /create_url https://funpay.com/lots/offerEdit?node=700")
                    continue
                elif text == "🔎 Ссылка для парсинга":
                    send_with_kb(from_chat, "Отправьте: /parse_url https://funpay.com/lots/700/")
                    continue
                elif text == "📈 Наценка":
                    send_with_kb(from_chat, "Отправьте: /markup 15")
                    continue
                elif text == "💰 Диапазон цен":
                    send_with_kb(from_chat, "Отправьте: /range 20000 150000 (0 вместо max — без границы)")
                    continue
                elif text == "📄 Файл":
                    text = "/file"
                elif text == "ℹ️ Помощь":
                    send_help(from_chat)
                    continue
                elif text == "⛔ Стоп":
                    text = "/stop"

                if text.startswith("/status"):
                    st = [
                        f"golden_key: {'set' if bool(state.get('golden_key')) else 'not set'}",
                        f"create_url: {state.get('create_lot_url') or '-'}",
                        f"parse_url: {state.get('parse_lot_url') or '-'}",
                        f"markup: {state.get('markup_percent', 0)}%",
                        f"range: {state.get('price_min', 0)} - {state.get('price_max', 0) or '∞'}"
                    ]
                    send_with_kb(from_chat, "\n".join(st))
                elif text.startswith("/gk "):
                    key = text.split(" ", 1)[1].strip()
                    state["golden_key"] = key
                    save_config(state)
                    send_with_kb(from_chat, "Golden key сохранён.")
                elif text.startswith("/create_url "):
                    urlv = text.split(" ", 1)[1].strip()
                    state["create_lot_url"] = urlv
                    save_config(state)
                    send_with_kb(from_chat, "Ссылка создания лота сохранена.")
                elif text.startswith("/parse_url "):
                    urlv = text.split(" ", 1)[1].strip()
                    state["parse_lot_url"] = urlv
                    save_config(state)
                    send_with_kb(from_chat, "Ссылка для парсинга сохранена.")
                elif text.startswith("/markup "):
                    try:
                        pct = float(text.split(" ", 1)[1].strip())
                    except Exception:
                        pct = 0.0
                    state["markup_percent"] = pct
                    save_config(state)
                    send_with_kb(from_chat, f"Наценка установлена: {pct}%")
                elif text.startswith("/range "):
                    try:
                        parts = text.split()
                        pmin = float(parts[1])
                        pmax = float(parts[2]) if len(parts) > 2 else 0.0
                    except Exception:
                        send_with_kb(from_chat, "Формат: /range <min> <max>. 0 для <max> = без ограничений.")
                        continue
                    state["price_min"] = max(0.0, pmin)
                    state["price_max"] = max(0.0, pmax)
                    save_config(state)
                    send_with_kb(from_chat, f"Диапазон установлен: {state['price_min']} - {state['price_max'] or '∞'}")
                elif text == "/post":
                    ok, summary = run_parse_and_post_via_state(state)
                    send_with_kb(from_chat, summary)
                elif text == "/file":
                    if os.path.exists(file_path):
                        send_file_to_telegram(bot_token, from_chat, file_path, caption="Актуальный список товаров")
                    else:
                        send_with_kb(from_chat, "Файл не найден.")
                elif text == "/stop":
                    # Разрешаем /stop только из привязанного чата
                    if bound_chat_id and from_chat == bound_chat_id:
                        send_with_kb(from_chat, "Останавливаю бота по команде /stop")
                        return
                    else:
                        # Игнорируем /stop из других чатов/до привязки
                        continue
                elif text:
                    send_with_kb(from_chat, "Команды: /status, /gk, /create_url, /parse_url, /markup, /range, /post, /file, /stop")
        except KeyboardInterrupt:
            print("Остановка Telegram-поллинга (Ctrl+C)")
            break
        except Exception:
            time.sleep(3)
            continue


# --- Конфиг ---
CONFIG_PATH = "funpay_config.json"


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Не удалось сохранить конфиг: {e}")


def run_parse_and_post_via_state(state: dict) -> tuple[bool, str]:
    """Выполняет полный цикл парсинга и постинга согласно state (конфигу).
    Возвращает (ok, summary)."""
    # Авторизация
    golden_key = (state.get("golden_key") or "").strip()
    session = None
    acc = None
    csrf_from_acc = None
    try:
        if golden_key:
            from FunPayAPI.account import Account
            acc = Account(golden_key=golden_key)
            acc.get()
            session = get_session_with_golden_key(golden_key, acc.phpsessid)
            csrf_from_acc = acc.csrf_token
        else:
            return False, "Golden key не задан. Установите через /gk <key>."
    except Exception as e:
        return False, f"Не удалось авторизоваться: {e}"

    create_lot_url = (state.get("create_lot_url") or "").strip()
    parse_lot_url = (state.get("parse_lot_url") or "").strip()
    if not create_lot_url or not parse_lot_url:
        return False, "create_url или parse_url не задан. Используйте /create_url и /parse_url."

    # category/csrf
    csrf_token = acc.csrf_token if acc else csrf_from_acc
    category_id = robust_extract_category_id_from_url(create_lot_url)
    if not category_id:
        _, category_id = get_csrf_and_category(session, create_lot_url)
    if not category_id:
        return False, "Не удалось определить category_id (node). Проверьте /create_url."

    # Парсинг
    items = parse_funpay_lot(parse_lot_url)
    if not items:
        return False, "Не удалось найти товары по ссылке parse_url."
    items_sorted = sort_items(items, 'subscribers')
    markup = float(state.get("markup_percent", 0) or 0)
    items_with_markup = apply_markup(items_sorted, markup_percent=markup)

    # Диапазон цен
    price_min = float(state.get("price_min", 0) or 0)
    price_max = float(state.get("price_max", 0) or 0)
    if price_min or price_max:
        def within_range(item):
            val = extract_price_value(item.get('new_price') or item['price'])
            if price_min and val < price_min:
                return False
            if price_max and price_max > 0 and val > price_max:
                return False
            return True

        items_with_markup = [it for it in items_with_markup if within_range(it)]

    # Сохранить файл
    save_to_file(items_with_markup, filename='funpay_items.txt')

    # Постинг
    posted = 0
    for item in items_with_markup:
        src = {}
        if not item.get('short_description') or not item.get('full_description'):
            src = scrape_offer_page_details(session, item.get('link', '')) if item.get('link') else {}
        src_subject = src.get("subject")
        src_subs = src.get("subscribers") or item.get('subscribers') or 0
        src_summary_ru = (src.get("summary_ru") or item.get('short_description') or item['title'])
        src_desc_ru = (src.get("desc_ru") or item.get('full_description') or "")
        ok = create_lot_via_account(
            acc,
            item['title'],
            extract_price_value(item.get('new_price', item['price'])),
            category_id,
            description=src_desc_ru if src_desc_ru else f"Перепродажа: {item['title']} (оригинал: {item['link']})",
            session=session,
            create_lot_url=create_lot_url,
            subscribers_value=src_subs,
            summary_ru=src_summary_ru[:120],
            summary_en=None,
            preferred_subject=src_subject
        )
        if ok:
            posted += 1

    return True, f"Готово. Найдено: {len(items)}; к публикации после фильтров: {len(items_with_markup)}; успешно опубликовано: {posted}."


# --- Авторизация через cookies ---
def get_funpay_session(cookie_str):
    """
    Возвращает requests.Session с авторизацией на FunPay по cookies (cookie_str — строка из браузера)
    """
    session = requests.Session()
    cookies = {}
    for part in cookie_str.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            cookies[k] = v
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    return session


def get_session_with_golden_key(golden_key: str, phpsessid: str | None = None, user_agent: str | None = None):
    """
    Создаёт requests.Session, авторизованный через golden_key (+ PHPSESSID при наличии).
    """
    session = requests.Session()
    cookie = f"golden_key={golden_key}; cookie_prefs=1"
    if phpsessid:
        cookie += f"; PHPSESSID={phpsessid}"
    session.headers.update({
        "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookie
    })
    return session


def get_balance(session):
    """
    Получает баланс пользователя с FunPay (в рублях)
    """
    url = "https://funpay.com/account/balance"
    resp = session.get(url)
    if resp.status_code != 200:
        print("Не удалось получить баланс. Проверьте cookies.")
        return 0
    soup = bs(resp.text, "html.parser")
    # Пример: <div class="balance-block__value">1 234.56 ₽</div>
    balance_tag = soup.find("div", class_="balance-block__value")
    if not balance_tag:
        print("Не удалось найти баланс на странице.")
        return 0
    balance_str = balance_tag.get_text(strip=True)
    balance_val = re.sub(r'[^\d.,]', '', balance_str).replace(',', '.')
    try:
        return float(balance_val)
    except Exception:
        return 0


def parse_funpay_lot(lot_url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    session = requests.Session()
    session.headers.update(headers)

    response = session.get(lot_url, timeout=30)
    if response.status_code != 200:
        print(f"Не удалось получить страницу: {lot_url}")
        return []
    soup = bs(response.text, "html.parser")
    items = []
    offers = soup.find_all("a", class_="tc-item")
    for offer in offers:
        try:
            # Название товара
            title_tag = offer.find("div", class_="tc-desc-text")
            title = title_tag.get_text(strip=True) if title_tag else "Без названия"

            # Продавец
            seller_tag = offer.find("div", class_="media-user-name")
            seller = seller_tag.get_text(strip=True) if seller_tag else "Без продавца"

            # Цена
            price_tag = offer.find("div", class_="tc-price")
            price = price_tag.get_text(strip=True) if price_tag else "Без цены"

            # Ссылка на товар
            item_link = offer.get('href', '')
            if item_link and not item_link.startswith('http'):
                item_link = 'https://funpay.com' + item_link

            # Извлекаем количество подписчиков из названия
            subscribers = extract_subscribers(title)

            # Извлекаем числовое значение цены для сортировки
            price_value = extract_price_value(price)

            # Краткое/подробное описание со страницы оффера
            short_description = ""
            full_description = ""
            if item_link:
                try:
                    details = scrape_offer_page_details(session, item_link)
                    short_description = details.get("summary_ru") or ""
                    full_description = details.get("desc_ru") or ""
                except Exception:
                    pass

            items.append({
                "title": title,
                "price": price,
                "price_value": price_value,
                "seller": seller,
                "subscribers": subscribers,
                "link": item_link,
                "short_description": short_description,
                "full_description": full_description
            })
        except Exception as e:
            print(f"Ошибка при парсинге товара: {e}")
    return items


def extract_subscribers(title):
    """Извлекает количество подписчиков из названия товара"""
    # Ищем паттерны типа "254669 подписчиков", "1.2M подписчиков", "500K подписчиков"
    patterns = [
        r'(\d+(?:\.\d+)?)\s*[МM]\s*подписчиков',  # 1.2M подписчиков
        r'(\d+(?:\.\d+)?)\s*[КK]\s*подписчиков',  # 500K подписчиков
        r'(\d+)\s*подписчиков',  # 254669 подписчиков
    ]

    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if 'М' in pattern or 'M' in pattern:
                return int(value * 1000000)
            elif 'К' in pattern or 'K' in pattern:
                return int(value * 1000)
            else:
                return int(value)
    return 0


# Детальный парсинг страницы конкретного оффера (offer?id=XXXXX)
def scrape_offer_page_details(session: requests.Session, offer_url: str) -> dict:
    """Возвращает детали оффера: subject, subscribers, summary_ru, desc_ru.
    Если что-то не найдено, поля могут отсутствовать.
    """
    details: dict = {}
    try:
        resp = session.get(offer_url, timeout=20)
        if resp.status_code != 200:
            return details
        soup = bs(resp.text, "html.parser")

        def find_param_value(label_text: str) -> str | None:
            # Ищем блок <div class="param-item"><h5>label</h5><div>value</div></div>
            for pi in soup.find_all("div", class_="param-item"):
                h5 = pi.find("h5")
                if h5 and (h5.get_text(strip=True) or "").strip().lower() == label_text.strip().lower():
                    # Значение может быть в <div> или внутри pi (последующий div)
                    val_div = pi.find("div")
                    if val_div:
                        # Сохраняем переносы строк для <br/>
                        for br in val_div.find_all("br"):
                            br.replace_with("\n")
                        return val_div.get_text(" ", strip=True)
            return None

        subject = find_param_value("Тематика")
        subs_text = find_param_value("Количество подписчиков")
        short_desc = find_param_value("Краткое описание")
        full_desc = find_param_value("Подробное описание")

        if subject:
            details["subject"] = subject
        if subs_text:
            try:
                subs_num = int(re.sub(r"[^\d]", "", subs_text) or "0")
            except Exception:
                subs_num = 0
            if subs_num:
                details["subscribers"] = subs_num
        if short_desc:
            details["summary_ru"] = short_desc
        if full_desc:
            details["desc_ru"] = full_desc

        append_post_log("offer_source_scraped", {"url": offer_url, "details": details})
    except Exception as e:
        append_post_log("offer_source_scrape_error", {"url": offer_url, "error": str(e)})
    return details


def extract_price_value(price_str):
    """Извлекает числовое значение цены для сортировки"""
    # Убираем все символы кроме цифр и точки
    price_clean = re.sub(r'[^\d.]', '', price_str)
    try:
        return float(price_clean)
    except:
        return 0


def sort_items(items, sort_by='subscribers'):
    """Сортирует товары по подписчикам или цене"""
    if sort_by == 'subscribers':
        return sorted(items, key=lambda x: x['subscribers'], reverse=True)
    elif sort_by == 'price':
        return sorted(items, key=lambda x: x['price_value'], reverse=True)
    else:
        return items


def save_to_file(items, filename='funpay_items.txt'):
    """Сохраняет товары в текстовый файл"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("ТОВАРЫ С FUNPAY (отсортированы по подписчикам)\n")
        f.write("=" * 80 + "\n\n")

        for i, item in enumerate(items, 1):
            f.write(f"{i}. {item['title']}\n")
            f.write(f"   Продавец: {item['seller']}\n")
            f.write(f"   Цена: {item['price']}\n")
            f.write(f"   Подписчики: {item['subscribers']:,}\n")
            if item.get('short_description'):
                f.write(f"   Кратко: {item['short_description']}\n")
            if item.get('full_description'):
                f.write(f"   Описание: {item['full_description']}\n")
            f.write(f"   Ссылка: {item['link']}\n")
            f.write("-" * 60 + "\n\n")

    print(f"Результат сохранён в файл: {filename}")


def apply_markup(items, markup_percent=0, markup_fixed=0):
    """
    Применяет наценку к цене товаров.
    markup_percent: процент наценки (например, 10 для +10%)
    markup_fixed: фиксированная наценка (например, 50 для +50 рублей)
    Возвращает новый список товаров с обновлённой ценой.
    """
    result = []
    for item in items:
        price_str = ''.join(c for c in item['price'] if c.isdigit() or c == '.')
        try:
            price = float(price_str)
        except Exception:
            price = 0
        new_price = price * (1 + markup_percent / 100) + markup_fixed
        item_with_markup = item.copy()
        item_with_markup['new_price'] = f"{new_price:.2f} ₽"
        result.append(item_with_markup)
    return result


def print_items_with_markup(items):
    """
    Выводит список товаров с наценкой в консоль.
    """
    for item in items:
        print(f"Товар: {item['title']}")
        print(f"Продавец: {item['seller']}")
        print(f"Старая цена: {item['price']}")
        print(f"Новая цена: {item.get('new_price', '-')}")
        print(f"Подписчики: {item['subscribers']:,}")
        print("-" * 30)


def post_lot(session, csrf_token, title, price, category_id, description=""):
    """
    Выставляет новый лот на FunPay (через POST-запрос). Требует актуальный csrf_token.
    """
    url = "https://funpay.com/lots/create"
    data = {
        "csrf_token": csrf_token,
        "name": title,
        "price": price,
        "category": category_id,
        "description": description,
    }
    resp = session.post(url, data=data)
    if resp.status_code == 200 and "лот успешно создан" in resp.text.lower():
        print(f"Лот '{title}' успешно выставлен по цене {price}")
        return True
    else:
        print(f"Ошибка при выставлении лота '{title}': {resp.status_code} {resp.text[:200]}")
        return False


# ВАЖНО: category_id и csrf_token нужно получать динамически! (через парсинг страницы создания лота)
def get_csrf_and_category(session, lot_url):
    """
    Получает csrf_token и category_id для выставления лота.
    lot_url — ссылка на страницу создания/редактирования лота (например,
    https://funpay.com/lots/create, https://funpay.com/lots/offerEdit?node=700 или страница аналогичного лота)
    """
    # Попробуем извлечь category/node из URL (параметр node)
    category_id = None
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(lot_url)
        qs = parse_qs(parsed.query)
        if 'node' in qs and qs['node']:
            category_id = qs['node'][0]
    except Exception:
        pass

    resp = session.get(lot_url)
    if resp.status_code != 200:
        print("Не удалось получить страницу создания лота.")
        return None, category_id

    soup = bs(resp.text, "html.parser")

    # 1) csrf из input
    csrf_token = None
    csrf_tag = soup.find("input", {"name": "csrf_token"})
    if csrf_tag and csrf_tag.get("value"):
        csrf_token = csrf_tag["value"]

    # 2) csrf из data-app-data на <body>
    if not csrf_token:
        body = soup.find("body")
        if body and body.has_attr("data-app-data"):
            try:
                import json as _json
                app_data = _json.loads(body.get("data-app-data"))
                csrf_token = app_data.get("csrf-token") or csrf_token
            except Exception:
                pass

    # 3) category из select (если есть)
    if category_id is None:
        cat_tag = soup.find("select", {"name": "category"})
        if cat_tag:
            option = cat_tag.find("option", selected=True)
            if option:
                category_id = option.get("value")

    return csrf_token, category_id


def robust_extract_category_id_from_url(url: str) -> str | None:
    try:
        # Прямое извлечение ?node=XXX
        m = re.search(r"[?&]node=(\d+)", url)
        if m:
            return m.group(1)
    except Exception:
        pass
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if 'node' in qs and qs['node']:
            return qs['node'][0]
    except Exception:
        pass
    return None


def _shorten(text: str, limit: int = 80) -> str:
    return (text or "")[:limit]


def _make_en_summary(source_title: str) -> str:
    base = "YouTube channel for sale"
    extra = ""
    if source_title:
        # Добавим короткий хвост на англ., но обезопасим длину
        extra = " - Subscribers and views"
    s = f"{base}{extra}"
    return _shorten(s, 80)


def collect_offer_fields(session, create_lot_url: str, title: str, price: float, description: str | None, fallback_csrf: str | None,
                         preferred_subject: str | None = None,
                         subscribers_value: int | None = None,
                         summary_ru: str | None = None,
                         desc_ru: str | None = None,
                         amount_value: int | None = 1,
                         make_active: bool = True,
                         acc=None,
                         summary_en: str | None = None) -> tuple[dict, str | None, str | None]:
    try:
        if acc is not None:
            resp = acc.method("get", create_lot_url, {}, {}, raise_not_200=False)
            if resp.status_code in (301, 302) and 'Location' in resp.headers:
                resp = acc.method("get", resp.headers['Location'], {}, {}, raise_not_200=False)
        else:
            resp = session.get(create_lot_url, timeout=20)
    except Exception as e:
        append_post_log("offerEdit_open_exception", {"url": create_lot_url, "error": str(e)})
        print("Не удалось открыть страницу создания/редактирования лота для сбора полей.")
        return {}, fallback_csrf, robust_extract_category_id_from_url(create_lot_url)

    if resp.status_code != 200:
        print("Не удалось открыть страницу создания/редактирования лота для сбора полей.")
        append_post_log("offerEdit_open_failed", {"status": resp.status_code, "url": create_lot_url, "text": resp.text[:2000]})
        return {}, fallback_csrf, robust_extract_category_id_from_url(create_lot_url)
    soup = bs(resp.text, "html.parser")
    append_post_log("offerEdit_loaded", {"url": create_lot_url, "html": resp.text[:4000]})

    fields: dict = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if not name or name == "query":
            continue
        t = inp.get("type", "text")
        if t in ("checkbox", "radio"):
            if inp.has_attr("checked"):
                fields[name] = inp.get("value", "on") or "on"
            continue
        fields[name] = inp.get("value") or fields.get(name) or ""

    for ta in soup.find_all("textarea"):
        name = ta.get("name")
        if not name:
            continue
        fields[name] = (ta.text or "").strip()

    subjects_select_name = None
    subjects_options = []
    for sel in soup.find_all("select"):
        name = sel.get("name")
        if not name:
            continue
        if name == "fields[subject]":
            subjects_select_name = name
            subjects_options = [opt.get("value") or "" for opt in sel.find_all("option")]
        opt = sel.find("option", selected=True) or sel.find("option")
        if opt:
            fields[name] = opt.get("value") or fields.get(name) or ""

    csrf_tag = soup.find("input", {"name": "csrf_token"})
    csrf_token = csrf_tag.get("value") if csrf_tag else fallback_csrf
    node_id = fields.get("node_id") or robust_extract_category_id_from_url(create_lot_url)
    if csrf_token:
        fields["csrf_token"] = csrf_token
    if node_id:
        fields["node_id"] = str(node_id)
    fields["location"] = fields.get("location") or "trade"
    if title:
        fields["name"] = _shorten(title, 180)
    if price is not None:
        fields["price"] = str(int(round(price)))
    fields["amount"] = str(amount_value if amount_value is not None else 1)
    if make_active:
        fields["active"] = "on"

    if subjects_select_name:
        chosen = None
        if preferred_subject and preferred_subject in subjects_options:
            chosen = preferred_subject
        elif "Без тематики" in subjects_options:
            chosen = "Без тематики"
        else:
            for v in subjects_options:
                if v:
                    chosen = v
                    break
        if chosen:
            fields[subjects_select_name] = chosen

    if subscribers_value is not None:
        fields["fields[subscribers]"] = str(subscribers_value)

    if summary_ru is None:
        summary_ru = _shorten(title, 80)
    fields["fields[summary][ru]"] = _shorten(summary_ru, 80)

    if summary_en is None:
        summary_en = _make_en_summary(title)
    fields["fields[summary][en]"] = _shorten(summary_en, 80)

    if desc_ru is not None:
        fields["fields[desc][ru]"] = _shorten(desc_ru, 4000)

    append_post_log("form_fields_collected", {"fields": {k: (v if k not in ("csrf_token",) else "***") for k, v in fields.items()}})
    return fields, csrf_token, node_id


def create_lot_via_account(acc, title: str, price: float, category_id: str, description: str = "", session: requests.Session | None = None, create_lot_url: str | None = None,
                           subscribers_value: int | None = None,
                           summary_ru: str | None = None,
                           summary_en: str | None = None,
                           preferred_subject: str | None = None) -> bool:
    try:
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        int_price = int(round(price)) if price is not None else 1
        payload = {
            "csrf_token": acc.csrf_token,
            "name": _shorten(title, 180),
            "price": str(max(1, int_price)),
            "node_id": str(category_id),
            "location": "trade",
        }
        if description:
            payload["description"] = description

        if session and create_lot_url:
            form_fields, csrf_from_form, node_from_form = collect_offer_fields(
                session, create_lot_url, title, int_price, description, acc.csrf_token,
                preferred_subject=preferred_subject,
                subscribers_value=subscribers_value,
                summary_ru=summary_ru,
                summary_en=summary_en,
                acc=acc
            )
            if csrf_from_form:
                payload["csrf_token"] = csrf_from_form
            if node_from_form:
                payload["node_id"] = str(node_from_form)
            merged = form_fields
            merged.update(payload)
            payload = merged

        # Подготовим варианты падения цены, если сервер не принимает (без жёсткого 200000)
        base_price_int = int(payload.get("price") or 1)
        price_fallbacks = [
            str(max(1, base_price_int)),
            str(max(1, base_price_int - 1)),
            str(max(1, base_price_int - 10)),
            str(max(1, base_price_int - 100)),
            "1"
        ]

        # До 5 попыток, адаптивно сокращаем summary и меняем EN
        for attempt in range(5):
            # На первых попытках убеждаемся, что summary в лимите и EN валиден
            payload["fields[summary][ru]"] = _shorten(payload.get("fields[summary][ru]", _shorten(title, 80)), 80)
            payload["fields[summary][en]"] = _shorten(payload.get("fields[summary][en]", _make_en_summary(title)), 80)
            append_post_log("offerSave_attempt", {
                "attempt": attempt + 1,
                "headers": headers,
                "payload": {k: ("***" if k == "csrf_token" else v) for k, v in payload.items()}
            })
            resp = acc.method("post", "lots/offerSave", headers, payload, raise_not_200=False)
            append_post_log("offerSave_response", {"status": resp.status_code, "text": resp.text[:4000]})
            if resp.status_code == 429:
                delay = 2 * (attempt + 1)
                print(f"429 Too Many Requests. Повтор через {delay}s...")
                time.sleep(delay)
                continue
            try:
                j = resp.json()
                append_post_log("offerSave_json", j)
            except Exception:
                print(f"Неожиданный ответ: {resp.status_code} {resp.text[:200]}")
                return False
            if not j.get("error"):
                return True
            # Разбираем ошибки и адаптируемся
            errs = j.get("errors") or []
            need_retry = False
            for err in errs:
                field, msg = err
                if field in ("fields[summary][ru]", "fields[summary][en]") and "Слишком длинный" in msg:
                    # Усечь ещё сильнее
                    payload[field] = _shorten(payload.get(field, ""), 60)
                    need_retry = True
                if field == "fields[summary][en]" and "некорректного английского" in msg:
                    payload["fields[summary][en]"] = _make_en_summary(title)
                    need_retry = True
                if field == "price" and "Неверная цена" in msg:
                    # Берём следующий безопасный уровень цены
                    if price_fallbacks:
                        payload["price"] = price_fallbacks.pop(0)
                        need_retry = True
            if need_retry:
                continue
            if any(field == "price" for field, _ in errs):
                append_post_log("invalid_price", {"title": title, "wanted_price": payload.get("price"), "errors": errs})
            # Если нечего поправить — прекращаем
            print(f"Ошибка offerSave: {j.get('error')} {j.get('errors')}")
            return False
        return False
    except Exception as e:
        print(f"Исключение при создании лота через Account: {e}")
        return False


def main():
    print("=== FunPay Арбитраж Бот ===")
    print("ВНИМАНИЕ: Использование этого скрипта может нарушать правила FunPay. Вы используете его на свой страх и риск!")
    print("\nРежим Telegram: все настройки задаются командами в боте.\nКоманды: /status, /gk, /create_url, /parse_url, /markup, /range, /post, /file, /stop\n")

    cfg = load_config()
    # Telegram сначала: если задан токен — сразу запускаем бот-режим
    tg_token = cfg.get("tg_token", "").strip()
    tg_chat_id = cfg.get("tg_chat_id", "").strip()
    if tg_token:
        print("Запускаю бота. Настройте всё командами в Telegram и используйте /post")
        try:
            run_telegram_polling(tg_token, tg_chat_id or "", 'funpay_items.txt')
        except Exception as e:
            print(f"Telegram-поллинг завершился с ошибкой: {e}")
        # Не выходим автоматически: держим процесс живым до Ctrl+C
        print("Поллинг остановлен. Процесс остаётся запущенным. Нажмите Ctrl+C для выхода.")
        while True:
            time.sleep(3600)
        return
    else:
        # Если токен не задан — не выходим. Ждём, пока его добавят в funpay_config.json, и автозапускаем бота.
        print("Токен Telegram не задан. Добавьте 'tg_token' (и при желании 'tg_chat_id') в funpay_config.json. Я буду ждать и проверять каждые 5 секунд...")
        while True:
            time.sleep(5)
            cfg = load_config()
            tg_token = cfg.get("tg_token", "").strip()
            tg_chat_id = cfg.get("tg_chat_id", "").strip()
            if tg_token:
                print("Обнаружен tg_token в конфиге. Запускаю бота...")
                try:
                    run_telegram_polling(tg_token, tg_chat_id or "", 'funpay_items.txt')
                except Exception as e:
                    print(f"Telegram-поллинг завершился с ошибкой: {e}")
                print("Поллинг остановлен. Процесс остаётся запущенным. Нажмите Ctrl+C для выхода.")
                while True:
                    time.sleep(3600)


if __name__ == "__main__":
    main()

