import asyncio
import logging
import random
import string
import os
import json
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = "@generateuse"
CHANNEL_USERNAME = "generateuse"
CHANNEL_CHAT_ID = -1003983302844
ACTIVITY_GROUP_ID = -1002277786445

os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

USERS_FILE = "users.json"
POSTS_FILE = "posts.json"
TOTAL_GEN_FILE = "total_gen.json"
TEXTS_FILE = "texts.json"
session = None

CONSONANTS = 'bcdfghjklmnpqrstvwxyz'
VOWELS = 'aeiou'

user_last_message = {}
admin_edit_state = {}

# Тексты по умолчанию
DEFAULT_TEXTS = {
    "welcome": (
        "🎯 Генератор username\n\n"
        "🤖 Всего сгенерировано — {total_generated} username\n\n"
        "Этот бот поможет тебе сделать ценный username, для продажи или для профиля.\n"
        "Мы генерируем уникальные username — 5 значные, такого нет ни-у-кого.\n\n"
        "💰 Баланс: {balance} юзернеймов"
    ),
    "subscription_warning": (
        "⚠️ Для использования бота необходимо подписаться на канал @generateuse\n\n"
        "Подпишитесь и нажмите кнопку проверки!"
    ),
    "not_subscribed": "❌ Вы еще не подписались! Подпишитесь на @generateuse",
    "no_generations": "❌ Недостаточно генераций!",
    "choose_length": "📏 Выберите длину username:\n💰 Баланс: {balance} генераций",
    "choose_type": "🎯 Выберите тип username ({length} знаков):",
    "found_username": (
        "✅ Найден username!\n\n"
        "Username: @{username}\n"
        "Длина: {length} знаков\n"
        "Тип: {type_name}\n"
        "💰 Баланс: {balance} юзернеймов"
    ),
    "not_found": "😔 Не найден свободный username.\nГенерация возвращена.",
    "award_comment": "🎁 Вы получили 1 генерацию на баланс бота за активность в комментариях!",
    "award_group": "🎁 Вы получили 1 генерацию на баланс бота за активность в группе! Общайся дальше что бы получить еще!",
    "award_admin": "🎁 Вы получили {amount} генерацию(й) на баланс бота!",
    "referral_text": (
        "👥 Реферальная система\n\n"
        "🎁 +2 генерации вам и другу\n"
        "⚠️ Бонус начисляется после подписки на @generateuse\n\n"
        "📊 Друзей: {referrals}\n"
        "🔗 Ваша ссылка:\n{link}"
    ),
    "buy_generations": (
        "🛒 Покупка генераций\n\n"
        "💎 1 генерация = 1 ⭐ XTR\n"
        "Минимум: 1, Максимум: 100\n\n"
        "✏️ Введите количество:"
    ),
    "ref_joined": "🎉 Вы присоединились по реферальной ссылке!\n💰 Вам начислено +2 генерации на баланс!",
    "ref_bonus": "🎉 По вашей реферальной ссылке присоединился новый пользователь!\n💰 Вам начислено +2 генерации на баланс!",
}

def load_json(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def load_users():
    return load_json(USERS_FILE)

def save_users(users):
    save_json(USERS_FILE, users)

def load_posts():
    return load_json(POSTS_FILE)

def save_posts(posts):
    save_json(POSTS_FILE, posts)

def get_total_generated():
    try:
        with open(TOTAL_GEN_FILE, 'r') as f:
            data = json.load(f)
            return data.get('total', 0)
    except:
        return 0

def increment_total_generated():
    total = get_total_generated() + 1
    with open(TOTAL_GEN_FILE, 'w') as f:
        json.dump({'total': total}, f)
    return total

def load_texts():
    texts = load_json(TEXTS_FILE)
    if not texts:
        texts = DEFAULT_TEXTS.copy()
        save_json(TEXTS_FILE, texts)
    return texts

def save_texts(texts):
    save_json(TEXTS_FILE, texts)

def get_text(key, **kwargs):
    texts = load_texts()
    text = texts.get(key, DEFAULT_TEXTS.get(key, ""))
    if kwargs:
        text = text.format(**kwargs)
    return text

def get_user_data(user_id):
    users = load_users()
    user_id = str(user_id)
    
    if user_id == "8406627355":
        if user_id not in users:
            users[user_id] = {
                'balance': 999,
                'total_generated': 0,
                'referrals': 0,
                'referral_code': 'ADMIN999',
                'referred_by': None,
                'referral_bonus_claimed': False,
                'pending_referral': None
            }
        else:
            users[user_id]['balance'] = 999
        save_users(users)
        return users[user_id]
    
    if user_id not in users:
        users[user_id] = {
            'balance': 3,
            'total_generated': 0,
            'referrals': 0,
            'referral_code': generate_referral_code(),
            'referred_by': None,
            'referral_bonus_claimed': False,
            'pending_referral': None
        }
        save_users(users)
    
    return users[user_id]

def update_user_balance(user_id, amount):
    users = load_users()
    user_id = str(user_id)
    
    if user_id == "8406627355":
        users[user_id]['balance'] = 999
        save_users(users)
        return 999
    
    if user_id in users:
        users[user_id]['balance'] += amount
        if users[user_id]['balance'] < 0:
            users[user_id]['balance'] = 0
        save_users(users)
        return users[user_id]['balance']
    return 0

def generate_referral_code():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(8))

def save_pending_referral(user_id, ref_code):
    users = load_users()
    user_id = str(user_id)
    
    if user_id in users:
        for uid, data in users.items():
            if data.get('referral_code') == ref_code and uid != user_id:
                if users[user_id].get('referred_by') is None:
                    users[user_id]['pending_referral'] = uid
                    save_users(users)
                    return uid
    return None

def claim_referral_bonus(user_id):
    users = load_users()
    user_id = str(user_id)
    
    if user_id not in users:
        return False
    
    user_data = users[user_id]
    pending = user_data.get('pending_referral')
    
    if pending and not user_data.get('referral_bonus_claimed') and user_id != "8406627355":
        users[user_id]['referred_by'] = pending
        users[user_id]['balance'] = users[user_id].get('balance', 0) + 2
        users[user_id]['referral_bonus_claimed'] = True
        users[user_id]['pending_referral'] = None
        
        if pending in users:
            users[pending]['balance'] = users[pending].get('balance', 0) + 2
            users[pending]['referrals'] = users[pending].get('referrals', 0) + 1
        
        save_users(users)
        return pending
    
    return None

async def check_subscription(user_id, context):
    if str(user_id) == "8406627355":
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

async def get_session():
    global session
    if session is None or session.closed:
        connector = aiohttp.TCPConnector(limit=500, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=5, connect=3)
        session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return session

async def check_telegram_batch_fast(usernames: list) -> set:
    sess = await get_session()
    free_usernames = set()
    semaphore = asyncio.Semaphore(100)
    
    async def check_single(username):
        async with semaphore:
            try:
                url = f"https://t.me/{username}"
                async with sess.get(
                    url, proxy=None, allow_redirects=False,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as response:
                    if response.status == 200:
                        html = await response.text()
                        if len(html) < 1000 or ('tgme_page_title' not in html and 'tgme_page_extra' not in html):
                            free_usernames.add(username)
                    elif response.status == 404:
                        free_usernames.add(username)
            except:
                pass
    
    chunk_size = 200
    for i in range(0, len(usernames), chunk_size):
        chunk = usernames[i:i+chunk_size]
        tasks = [check_single(username) for username in chunk]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    return free_usernames

async def check_fragment_batch_fast(usernames: list) -> set:
    sess = await get_session()
    sold_usernames = set()
    semaphore = asyncio.Semaphore(50)
    
    async def check_single(username):
        async with semaphore:
            try:
                url = f"https://fragment.com/username/{username}"
                async with sess.get(
                    url, proxy=None,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as response:
                    if response.status == 200:
                        html = await response.text()
                        html_lower = html.lower()
                        if any(word in html_lower for word in ['buy', 'auction', 'bid', 'sale', 'owner', 'ton']):
                            sold_usernames.add(username)
            except:
                pass
    
    chunk_size = 100
    for i in range(0, len(usernames), chunk_size):
        chunk = usernames[i:i+chunk_size]
        tasks = [check_single(username) for username in chunk]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    return sold_usernames

async def find_available_username_massive(username_type: str, length: int, total_to_check: int = 2500) -> str:
    usernames = set()
    while len(usernames) < total_to_check:
        usernames.add(generate_username(username_type, length))
    
    usernames_list = list(usernames)
    batch_size = 500
    all_free_telegram = set()
    all_sold_fragment = set()
    
    for i in range(0, len(usernames_list), batch_size):
        batch = usernames_list[i:i+batch_size]
        telegram_task = check_telegram_batch_fast(batch)
        fragment_task = check_fragment_batch_fast(batch)
        telegram_free, fragment_sold = await asyncio.gather(telegram_task, fragment_task)
        all_free_telegram.update(telegram_free)
        all_sold_fragment.update(fragment_sold)
        
        if len(all_free_telegram) > 100:
            break
    
    truly_free = all_free_telegram - all_sold_fragment
    
    if truly_free:
        for username in usernames_list:
            if username in truly_free:
                return username
    
    return None

def generate_letters_username(length):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))

def generate_letters_digits_username(length):
    chars = string.ascii_lowercase + string.digits
    username = ''.join(random.choice(chars) for _ in range(length))
    letter_count = sum(1 for c in username if c.isalpha())
    if letter_count < 2:
        username = list(username)
        for i in range(2 - letter_count):
            pos = random.randint(0, length-1)
            username[pos] = random.choice(string.ascii_lowercase)
        username = ''.join(username)
    return username

def generate_sounding_username(length):
    username = ''
    for i in range(length):
        if i % 2 == 0:
            username += random.choice(CONSONANTS)
        else:
            username += random.choice(VOWELS)
    if random.random() > 0.5:
        username = list(username)
        random.shuffle(username)
        username = ''.join(username)
    return username

def generate_username(username_type, length):
    if username_type == "letters":
        return generate_letters_username(length)
    elif username_type == "digits":
        return generate_letters_digits_username(length)
    elif username_type == "sounding":
        return generate_sounding_username(length)
    else:
        return generate_letters_username(length)

async def health_check(request):
    return web.Response(text="OK")

async def run_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logger.info("Web сервер запущен на порту 10000")

# ===== АДМИН-ПАНЕЛЬ РЕДАКТИРОВАНИЯ ТЕКСТОВ =====

async def adminfrag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /adminfrag123 - вход в админ-панель редактирования текстов"""
    message = update.message
    
    if message.from_user.id != 8406627355:
        return
    
    keyboard = []
    text_keys = list(DEFAULT_TEXTS.keys())
    
    for i in range(0, len(text_keys), 2):
        row = []
        for j in range(2):
            if i + j < len(text_keys):
                key = text_keys[i + j]
                row.append(InlineKeyboardButton(f"✏️ {key}", callback_data=f"edit_{key}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("📋 Показать все тексты", callback_data="show_all_texts")])
    keyboard.append([InlineKeyboardButton("🔄 Сбросить на стандартные", callback_data="reset_texts")])
    keyboard.append([InlineKeyboardButton("❌ Закрыть", callback_data="close_admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "🛠 Админ-панель редактирования текстов\n\n"
        "Выберите текст для редактирования:",
        reply_markup=reply_markup
    )

async def admin_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок админ-панели"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    if user_id != 8406627355:
        return
    
    data = query.data
    
    if data == "close_admin":
        await query.message.delete()
        return
    
    if data == "show_all_texts":
        texts = load_texts()
        all_texts = ""
        for key, value in texts.items():
            preview = value[:100] + "..." if len(value) > 100 else value
            all_texts += f"📌 {key}:\n{preview}\n\n"
        
        if len(all_texts) > 4000:
            all_texts = all_texts[:4000] + "..."
        
        await query.message.reply_text(f"📋 Все тексты:\n\n{all_texts}")
        return
    
    if data == "reset_texts":
        save_texts(DEFAULT_TEXTS.copy())
        await query.message.reply_text("✅ Тексты сброшены на стандартные!")
        return
    
    if data.startswith("edit_"):
        key = data.replace("edit_", "")
        admin_edit_state[user_id] = key
        
        current_text = get_text(key)
        
        await query.message.reply_text(
            f"✏️ Редактирование: {key}\n\n"
            f"📝 Текущий текст:\n{current_text}\n\n"
            f"Отправьте новый текст (можно с Premium стикерами):\n"
            f"Или /cancel для отмены"
        )
        return

async def admin_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает новый текст от админа"""
    message = update.message
    user_id = message.from_user.id
    
    if user_id != 8406627355:
        return
    
    if user_id not in admin_edit_state:
        return
    
    if message.text and message.text == '/cancel':
        del admin_edit_state[user_id]
        await message.reply_text("❌ Редактирование отменено")
        return
    
    key = admin_edit_state[user_id]
    new_text = message.text or message.caption or ""
    
    # Сохраняем entities для Premium стикеров
    if message.entities:
        # Сохраняем как HTML с emoji
        texts = load_texts()
        texts[key] = message.text_html or new_text
        save_texts(texts)
    else:
        texts = load_texts()
        texts[key] = new_text
        save_texts(texts)
    
    del admin_edit_state[user_id]
    
    await message.reply_text(
        f"✅ Текст '{key}' обновлен!\n\n"
        f"Новый текст:\n{new_text}"
    )

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if not message:
        return
    
    posts = load_posts()
    post_id = str(message.message_id)
    posts[post_id] = {
        'rewarded_users': [],
        'max_rewards': 3
    }
    save_posts(posts)

async def add_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    if not message or not message.text or not message.text.startswith('/add'):
        return
    
    if message.from_user.id != 8406627355:
        return
    
    if not message.reply_to_message:
        await message.reply_text("❌ Нужно ответить на сообщение пользователя")
        return
    
    try:
        parts = message.text.split()
        amount = int(parts[1]) if len(parts) > 1 else 1
    except:
        amount = 1
    
    target_user = message.reply_to_message.from_user
    
    if not target_user or target_user.is_bot:
        await message.reply_text("❌ Нельзя выдать боту")
        return
    
    update_user_balance(target_user.id, amount)
    user_data = get_user_data(target_user.id)
    
    bot_username = context.bot.username
    keyboard = [[InlineKeyboardButton("🎯 Перейти в бота", url=f"https://t.me/{bot_username}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    award_text = get_text("award_admin", amount=amount)
    
    await message.reply_text(
        f"✅ @{target_user.username or target_user.id} получил {amount} генераций\n"
        f"💰 Баланс: {user_data['balance']} юзернеймов",
        reply_markup=reply_markup
    )
    
    try:
        await context.bot.send_message(chat_id=target_user.id, text=award_text, reply_markup=reply_markup)
    except:
        pass
    
    try:
        await context.bot.send_message(
            chat_id=8406627355,
            text=f"✅ Выдано {amount} генераций\n👤 @{target_user.username or target_user.id}\n💰 Баланс: {user_data['balance']} юзернеймов"
        )
    except:
        pass

async def comment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    if not message or not message.reply_to_message:
        return
    
    if str(message.chat_id) != str(CHANNEL_CHAT_ID):
        return
    
    if message.from_user.is_bot:
        return
    
    original_post_id = str(message.reply_to_message.message_id)
    user_id = message.from_user.id
    
    posts = load_posts()
    
    if original_post_id not in posts:
        return
    
    post_data = posts[original_post_id]
    
    if str(user_id) in post_data['rewarded_users']:
        return
    
    if len(post_data['rewarded_users']) >= post_data['max_rewards']:
        return
    
    post_data['rewarded_users'].append(str(user_id))
    save_posts(posts)
    
    update_user_balance(user_id, 1)
    
    bot_username = context.bot.username
    keyboard = [[InlineKeyboardButton("🎯 Перейти в бота", url=f"https://t.me/{bot_username}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(get_text("award_comment"), reply_markup=reply_markup)
    
    try:
        await context.bot.send_message(chat_id=user_id, text=get_text("award_comment"), reply_markup=reply_markup)
    except:
        pass

async def activity_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    if not message or not message.text:
        return
    
    if str(message.chat_id) != str(ACTIVITY_GROUP_ID):
        return
    
    user_id = message.from_user.id
    
    if message.from_user.is_bot:
        return
    
    now = asyncio.get_event_loop().time()
    if user_id in user_last_message:
        if now - user_last_message[user_id] < 30:
            return
    
    user_last_message[user_id] = now
    
    if random.random() > 0.05:
        return
    
    update_user_balance(user_id, 1)
    user_data = get_user_data(user_id)
    
    bot_username = context.bot.username
    keyboard = [[InlineKeyboardButton("🎯 Перейти в бота", url=f"https://t.me/{bot_username}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(get_text("award_group"), reply_markup=reply_markup)
    
    try:
        await context.bot.send_message(
            chat_id=8406627355,
            text=f"🎁 Активность в группе\n👤 @{message.from_user.username or user_id}\n💰 Баланс: {user_data['balance']} юзернеймов\n💬 {message.text[:50]}"
        )
    except:
        pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ['group', 'supergroup', 'channel']:
        return
    
    user_id = update.effective_user.id
    
    if context.args and len(context.args) > 0:
        ref_code = context.args[0]
        save_pending_referral(user_id, ref_code)
    
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(get_text("subscription_warning"), reply_markup=reply_markup)
        return
    
    user_data = get_user_data(user_id)
    total_generated = get_total_generated()
    
    keyboard = [
        [InlineKeyboardButton("🎯 Сгенерировать username", callback_data="choose_length")],
        [InlineKeyboardButton("🛒 Купить генерации", callback_data="buy_generations")],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="referral")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        get_text("welcome", total_generated=total_generated, balance=user_data['balance']),
        reply_markup=reply_markup
    )

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id, context)
    
    if is_subscribed:
        ref_result = claim_referral_bonus(user_id)
        
        if ref_result:
            try:
                await context.bot.send_message(chat_id=int(ref_result), text=get_text("ref_bonus"))
            except:
                pass
        
        await query.message.delete()
        await show_main_menu(query.message, user_id)
    else:
        await query.message.reply_text(get_text("not_subscribed"))

async def show_main_menu(message, user_id):
    user_data = get_user_data(user_id)
    total_generated = get_total_generated()
    
    keyboard = [
        [InlineKeyboardButton("🎯 Сгенерировать username", callback_data="choose_length")],
        [InlineKeyboardButton("🛒 Купить генерации", callback_data="buy_generations")],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="referral")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        get_text("welcome", total_generated=total_generated, balance=user_data['balance']),
        reply_markup=reply_markup
    )

async def choose_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if user_data['balance'] <= 0 and str(user_id) != "8406627355":
        keyboard = [[InlineKeyboardButton("🛒 Купить генерации", callback_data="buy_generations")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(get_text("no_generations"), reply_markup=reply_markup)
        return
    
    keyboard = [
        [InlineKeyboardButton("5 знаков", callback_data="len_5")],
        [InlineKeyboardButton("6 знаков", callback_data="len_6")],
        [InlineKeyboardButton("7 знаков", callback_data="len_7")],
        [InlineKeyboardButton("8 знаков", callback_data="len_8")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        get_text("choose_length", balance=user_data['balance']),
        reply_markup=reply_markup
    )

async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    length = query.data.split("_")[1]
    context.user_data['username_length'] = int(length)
    
    keyboard = [
        [InlineKeyboardButton("📝 Только буквы", callback_data="type_letters")],
        [InlineKeyboardButton("🔢 Буквы и цифры", callback_data="type_digits")],
        [InlineKeyboardButton("🗣 Звучащие", callback_data="type_sounding")],
        [InlineKeyboardButton("🔙 Назад к длине", callback_data="choose_length")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        get_text("choose_type", length=length),
        reply_markup=reply_markup
    )

async def generate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username_type = query.data.split("_")[1]
    length = context.user_data.get('username_length', 6)
    
    user_data = get_user_data(user_id)
    
    if user_data['balance'] <= 0 and str(user_id) != "8406627355":
        await query.message.reply_text(get_text("no_generations"))
        return
    
    type_names = {
        "letters": "📝 Только буквы",
        "digits": "🔢 Буквы и цифры",
        "sounding": "🗣 Звучащие"
    }
    type_name = type_names.get(username_type, "")
    
    if str(user_id) != "8406627355":
        update_user_balance(user_id, -1)
    
    status_msg = await query.message.reply_text("🔍 Поиск...")
    
    try:
        username = await find_available_username_massive(username_type, length, 2500)
        await status_msg.delete()
        
        if username:
            increment_total_generated()
            
            users = load_users()
            users[str(user_id)]['total_generated'] += 1
            save_users(users)
            
            user_data = get_user_data(user_id)
            
            keyboard = [[InlineKeyboardButton(
                text=f"🚀 Занять @{username}",
                url=f"https://t.me/{username}"
            )]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(
                get_text("found_username", username=username, length=length, type_name=type_name, balance=user_data['balance']),
                reply_markup=reply_markup
            )
        else:
            if str(user_id) != "8406627355":
                update_user_balance(user_id, 1)
            
            keyboard = [
                [InlineKeyboardButton("🔄 Другая длина", callback_data="choose_length")],
                [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.reply_text(get_text("not_found"), reply_markup=reply_markup)
    
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        if str(user_id) != "8406627355":
            update_user_balance(user_id, 1)
        await query.message.reply_text("❌ Ошибка. Генерация возвращена.")
        await status_msg.delete()

async def buy_generations_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(get_text("buy_generations"))
    context.user_data['awaiting_buy_amount'] = True

async def handle_buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_buy_amount'):
        return
    
    try:
        amount = int(update.message.text)
        if amount < 1 or amount > 100:
            await update.message.reply_text("❌ Введите число от 1 до 100")
            return
        
        context.user_data['awaiting_buy_amount'] = False
        
        await context.bot.send_invoice(
            chat_id=update.effective_user.id,
            title=f"Покупка {amount} генераций",
            description=f"Генерации username в Telegram",
            payload=f"buy_{amount}_{update.effective_user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(f"{amount} генераций", amount)]
        )
    except ValueError:
        await update.message.reply_text("❌ Введите целое число!")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "main_menu":
        await show_main_menu(query.message, update.effective_user.id)
    elif query.data == "choose_length":
        await choose_length(update, context)
    elif query.data == "buy_generations":
        await buy_generations_menu(update, context)
    elif query.data == "referral":
        await referral_system(update, context)
    elif query.data.startswith("len_"):
        await choose_type(update, context)
    elif query.data.startswith("type_"):
        await generate_handler(update, context)

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    
    if payload.startswith("buy_"):
        parts = payload.split("_")
        amount = int(parts[1])
        user_id = int(parts[2])
        
        update_user_balance(user_id, amount)
        user_data = get_user_data(user_id)
        
        await update.message.reply_text(
            f"✅ Оплата успешна!\n💰 +{amount} генераций\n🎯 Баланс: {user_data['balance']} юзернеймов"
        )

async def referral_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_data = get_user_data(update.effective_user.id)
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start={user_data['referral_code']}"
    
    keyboard = [
        [InlineKeyboardButton("📤 Поделиться ссылкой", switch_inline_query=referral_link)],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        get_text("referral_text", referrals=user_data['referrals'], link=referral_link),
        reply_markup=reply_markup
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check username")
        return
    
    username = context.args[0].replace("@", "").lower()
    status_msg = await update.message.reply_text(f"🔍 Проверяю @{username}...")
    
    try:
        free_set = await check_telegram_batch_fast([username])
        is_free = username in free_set
        
        if is_free:
            fragment_set = await check_fragment_batch_fast([username])
            is_free = username not in fragment_set
        
        await status_msg.delete()
        
        if is_free:
            keyboard = [[InlineKeyboardButton("🚀 Занять", url=f"https://t.me/{username}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"✅ @{username} свободен!", reply_markup=reply_markup)
        else:
            await update.message.reply_text(f"❌ @{username} занят")
    except:
        await update.message.reply_text("❌ Ошибка проверки")
        await status_msg.delete()

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ['group', 'supergroup', 'channel']:
        return
    
    try:
        if context.user_data.get('awaiting_buy_amount'):
            await handle_buy_amount(update, context)
            return
    except:
        pass
    await update.message.reply_text("Используйте /start")

async def cleanup():
    global session
    if session and not session.closed:
        await session.close()

def main():
    logger.info("Запуск бота...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(run_web_server())
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Админ-панель
    application.add_handler(CommandHandler("adminfrag123", adminfrag_command))
    application.add_handler(CallbackQueryHandler(admin_text_callback, pattern="^(edit_|show_all_texts|reset_texts|close_admin)$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(user_id=8406627355), admin_receive_text))
    
    # /add от админа
    application.add_handler(MessageHandler(filters.COMMAND & filters.REPLY, add_command_handler))
    
    # Канал и комментарии
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post_handler))
    application.add_handler(MessageHandler(filters.Chat(CHANNEL_CHAT_ID) & filters.REPLY & ~filters.COMMAND, comment_handler))
    
    # Активность в группе
    application.add_handler(MessageHandler(filters.Chat(ACTIVITY_GROUP_ID) & filters.TEXT & ~filters.COMMAND, activity_group_handler))
    
    # Основные
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен!")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
