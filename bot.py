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

BOT_TOKEN = "8705607694:AAH11zwytS-MN0BfBxfb4a9wyPDrEuzKMbA"
CHANNEL_ID = "@generateuse"
CHANNEL_USERNAME = "generateuse"
CHANNEL_CHAT_ID = -3937553278  # ЗАМЕНИ НА ID ТВОЕГО КАНАЛА

os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

USERS_FILE = "users.json"
POSTS_FILE = "posts.json"
session = None

CONSONANTS = 'bcdfghjklmnpqrstvwxyz'
VOWELS = 'aeiou'

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

def get_total_generated():
    users = load_users()
    total = 0
    for user_data in users.values():
        total += user_data.get('total_generated', 0)
    return total

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
                    logger.info(f"Сохранён pending_referral: user={user_id}, referrer={uid}")
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
        logger.info(f"Бонус начислен: user={user_id}, referrer={pending}")
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

# ===== ОБРАБОТКА КОММЕНТАРИЕВ В КАНАЛЕ =====

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает новые посты в канале и сбрасывает счетчик комментариев"""
    message = update.channel_post
    if message and message.chat_id == CHANNEL_CHAT_ID:
        posts = load_posts()
        post_id = str(message.message_id)
        posts[post_id] = {
            'rewarded_users': [],
            'max_rewards': 3
        }
        save_posts(posts)
        logger.info(f"Новый пост в канале: {post_id}, сброшен счетчик наград")

async def channel_comment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдает награду первым 3 комментаторам под постом"""
    message = update.message
    
    # Проверяем что это комментарий под постом в канале
    if not message or not message.reply_to_message:
        return
    
    # Получаем ID поста (на который ответили)
    original_post_id = str(message.reply_to_message.message_id)
    user_id = message.from_user.id
    
    posts = load_posts()
    
    # Проверяем есть ли такой пост в базе
    if original_post_id not in posts:
        return
    
    post_data = posts[original_post_id]
    
    # Проверяем не получил ли уже этот пользователь награду
    if str(user_id) in post_data['rewarded_users']:
        return
    
    # Проверяем не достигнут ли лимит наград (3 человека)
    if len(post_data['rewarded_users']) >= post_data['max_rewards']:
        return
    
    # Выдаем награду
    post_data['rewarded_users'].append(str(user_id))
    save_posts(posts)
    
    # Начисляем 1 генерацию
    update_user_balance(user_id, 1)
    
    bot_username = context.bot.username
    
    # Отправляем сообщение в канале (ответ на комментарий)
    keyboard = [[InlineKeyboardButton("🎯 Перейти в бота", url=f"https://t.me/{bot_username}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "🎁 Вы получили 1 генерацию на баланс бота за активность в комментариях!",
        reply_markup=reply_markup
    )
    
    # Отправляем уведомление в бота
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="🎁 Вы получили 1 генерацию на баланс бота за активность в комментариях!",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
    
    logger.info(f"Награда выдана пользователю {user_id} за комментарий под постом {original_post_id}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"START: user={user_id}, args={context.args}")
    
    if context.args and len(context.args) > 0:
        ref_code = context.args[0]
        logger.info(f"Получен реферальный код: {ref_code}")
        save_pending_referral(user_id, ref_code)
    
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        keyboard = [
            [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ Для использования бота необходимо подписаться на канал @generateuse\n\n"
            "Подпишитесь и нажмите кнопку проверки!",
            reply_markup=reply_markup
        )
        return
    
    user_data = get_user_data(user_id)
    total_generated = get_total_generated()
    
    keyboard = [
        [InlineKeyboardButton("🎯 Сгенерировать username", callback_data="choose_length")],
        [InlineKeyboardButton("🛒 Купить генерации", callback_data="buy_generations")],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="referral")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "🎯 Генератор username\n\n"
        f"🤖 Бот сгенерировал — {total_generated} username\n\n"
        "Этот бот поможет тебе сделать ценный username, для продажи или для профиля.\n"
        "Мы генерируем уникальные username — 5 значные, такого нет ни-у-кого.\n\n"
        f"💰 Баланс: {user_data['balance']} юзернеймов"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id, context)
    
    if is_subscribed:
        ref_result = claim_referral_bonus(user_id)
        
        if ref_result:
            try:
                await context.bot.send_message(
                    chat_id=int(ref_result),
                    text="🎉 По вашей реферальной ссылке присоединился новый пользователь!\n"
                         "💰 Вам начислено +2 генерации на баланс!"
                )
                logger.info(f"Уведомление отправлено рефереру {ref_result}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 Вы присоединились по реферальной ссылке!\n"
                         "💰 Вам начислено +2 генерации на баланс!"
                )
            except:
                pass
        
        await query.message.delete()
        await show_main_menu(query.message, user_id)
    else:
        await query.message.reply_text("❌ Вы еще не подписались! Подпишитесь на @generateuse")

async def show_main_menu(message, user_id):
    user_data = get_user_data(user_id)
    total_generated = get_total_generated()
    
    keyboard = [
        [InlineKeyboardButton("🎯 Сгенерировать username", callback_data="choose_length")],
        [InlineKeyboardButton("🛒 Купить генерации", callback_data="buy_generations")],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="referral")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🎯 Генератор username\n\n"
        f"🤖 Бот сгенерировал — {total_generated} username\n\n"
        "Этот бот поможет тебе сделать ценный username, для продажи или для профиля.\n"
        "Мы генерируем уникальные username — 5 значные, такого нет ни-у-кого.\n\n"
        f"💰 Баланс: {user_data['balance']} юзернеймов"
    )
    
    await message.reply_text(text, reply_markup=reply_markup)

async def choose_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    
    if user_data['balance'] <= 0 and str(user_id) != "8406627355":
        keyboard = [[InlineKeyboardButton("🛒 Купить генерации", callback_data="buy_generations")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("❌ Недостаточно генераций!", reply_markup=reply_markup)
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
        f"📏 Выберите длину username:\n💰 Баланс: {user_data['balance']} генераций",
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
        f"🎯 Выберите тип username ({length} знаков):",
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
        await query.message.reply_text("❌ Недостаточно генераций!")
        return
    
    type_names = {
        "letters": "📝 Только буквы",
        "digits": "🔢 Буквы и цифры",
        "sounding": "🗣 Звучащие"
    }
    type_name = type_names.get(username_type, "")
    
    if str(user_id) != "8406627355":
        update_user_balance(user_id, -1)
    
    status_msg = await query.message.reply_text(f"🔍 Поиск...")
    
    try:
        username = await find_available_username_massive(username_type, length, 2500)
        await status_msg.delete()
        
        if username:
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
                f"✅ Найден username!\n\n"
                f"Username: @{username}\n"
                f"Длина: {length} знаков\n"
                f"Тип: {type_name}\n"
                f"💰 Баланс: {user_data['balance']} юзернеймов",
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
            
            await query.message.reply_text(
                "😔 Не найден свободный username.\nГенерация возвращена.",
                reply_markup=reply_markup
            )
    
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        if str(user_id) != "8406627355":
            update_user_balance(user_id, 1)
        await query.message.reply_text("❌ Ошибка. Генерация возвращена.")
        await status_msg.delete()

async def buy_generations_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "🛒 Покупка генераций\n\n"
        "💎 1 генерация = 1 ⭐ XTR\n"
        "Минимум: 1, Максимум: 100\n\n"
        "✏️ Введите количество:"
    )
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
            f"✅ Оплата успешна!\n"
            f"💰 +{amount} генераций\n"
            f"🎯 Баланс: {user_data['balance']} юзернеймов"
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
    
    text = (
        "👥 Реферальная система\n\n"
        "🎁 +2 генерации вам и другу\n"
        "⚠️ Бонус начисляется после подписки на @generateuse\n\n"
        f"📊 Друзей: {user_data['referrals']}\n"
        f"🔗 Ваша ссылка:\n{referral_link}"
    )
    
    await query.message.reply_text(text, reply_markup=reply_markup)

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
    
    loop = asyncio.get_event_loop()
    loop.create_task(run_web_server())
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Основные обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    
    # Обработчики канала
    application.add_handler(MessageHandler(filters.Chat(CHANNEL_CHAT_ID) & filters.UpdateType.CHANNEL_POST, channel_post_handler))
    application.add_handler(MessageHandler(filters.Chat(CHANNEL_CHAT_ID) & filters.REPLY, channel_comment_handler))
    
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
