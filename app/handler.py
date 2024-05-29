
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
# from decimal import Decimal
from pytonconnect import TonConnect
from replenishment.connector import get_connector
import app.keyboards as kb
from pytoniq_core import Address
import logging
import asyncio
import aiohttp
import sqlite3
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
#from aiogram.utils.exceptions import MessageToEditNotFound, MessageToDeleteNotFound
import sys
import logging
import asyncio
import time
from io import BytesIO
import qrcode
# from main import bot
import pytonconnect.exceptions
from pytoniq_core import Address
from pytonconnect import TonConnect

import config
from replenishment.message import get_comment_message
from replenishment.connector import get_connector

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
# Initialize bot and dispatcher

router = Router()
bot = Bot(config.TOKEN)
logger = logging.getLogger(__file__)

db_path = 'database.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# таблицы
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        ton_balance REAL DEFAULT 0,
        not_balance REAL DEFAULT 0,
        ton_address TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY,
        buyer_id INTEGER,
        seller_id INTEGER,
        ton_amount REAL,
        not_amount REAL,
        status TEXT,
        comments TEXT,
        deal_name TEXT
    )
''')

conn.commit()

# States
class Form(StatesGroup):
    deal_type = State()
    deal_amount = State()
    deal_name = State()
    confirm_deal = State()
    send_goods = State()
    confirm_receive = State()
    send_tokens = State()
    dispute = State()

# Start command handler
@router.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    print("new_user")
    await message.answer('Добро пожаловать!')
    # connector = get_connector(chat_id)

    # connected = await connector.restore_connection()
    # print(connected)
    if user is None:
        cursor.execute("INSERT INTO users (telegram_id) VALUES (?)", (user_id,))
        conn.commit()
    # if connected:
    await show_main_menu(message)
    # else:
    #     await message.answer('Подключите или переподключите пожалуйста свой TON кошелек', reply_markup=kb.wallets)

# Main menu

async def show_main_menu(message: Message):
    await message.answer('Что вы хотите сделать?', reply_markup=kb.main)

# Wallet connect function

async def connect_wallet(message: Message, wallet_name: str):
    connector = get_connector(message.chat.id)
    print(wallet_name)
    wallets_list = connector.get_wallets()
    wallet = None

    for w in wallets_list:
        if w['name'] == wallet_name:
            wallet = w

    if wallet is None:
        raise Exception(f'Unknown wallet: {wallet_name}')
    print(wallet)
    generated_url = await connector.connect(wallet)
    print(generated_url)
    mk_b = InlineKeyboardBuilder()
    mk_b.button(text='Connect', url=generated_url)

    img = qrcode.make(generated_url)
    stream = BytesIO()
    img.save(stream)
    file = BufferedInputFile(file=stream.getvalue(), filename='qrcode')
    print("woooooork")
    await message.answer_photo(photo=file, caption='Connect wallet within 3 minutes', reply_markup=mk_b.as_markup())

    mk_b = InlineKeyboardBuilder()
    mk_b.button(text='Start', callback_data='start')

    for i in range(1, 180):
        await asyncio.sleep(1)
        if connector.connected:
            if connector.account.address:
                wallet_address = connector.account.address
                wallet_address = Address(wallet_address).to_str(is_bounceable=False)
                cursor.execute("UPDATE users SET ton_address = ? WHERE telegram_id = ?", (wallet_address, message.from_user.id))
                conn.commit()
                await message.answer(f'You are connected with address <code>{wallet_address}</code>', reply_markup=mk_b.as_markup())
                logger.info(f'Connected with address: {wallet_address}')
            return
    await message.answer(f'Timeout error!', reply_markup=mk_b.as_markup())

# Callback query handler
@router.callback_query(lambda c: True)
async def callback_query_handler(call: CallbackQuery, state: FSMContext):
    await call.answer()
    message = call.message
    data = call.data
    user_id = call.from_user.id
    connector = get_connector(call.message.chat.id)
    # Обработка кнопок подключения кошелька
    if data.startswith('connect:'):
        wallet_name = data.split(':')[1]
        await connect_wallet(message, wallet_name)
    elif data == 'start':
        await start(message)
    # Обработка создания сделки
    elif data == 'create_deal':
        await message.answer("Создать сделку:\n\n"
                             "1. Купить или продать?\n"
                             "2. Сколько TON?\n"
                             "3. Название сделки?", reply_markup=kb.create_deal_type)
        await Form.deal_type.set()
    # Сохранение типа сделки (купить/продать)
    elif data.startswith('deal_type:'):
        deal_type = data.split(':')[1]
        await state.update_data(deal_type=deal_type)
        await message.answer("Введите количество TON:", reply_markup=kb.back_to_main)
        await Form.deal_amount.set()
    # Сохранение количества TON
    elif data.startswith('deal_amount:'):
        try:
            ton_amount = int(data.split(':')[1])
        except ValueError:
            await message.answer("Некорректное значение. Введите число.")
            return
        await state.update_data(ton_amount=ton_amount)
        await message.answer("Введите название сделки:", reply_markup=kb.back_to_main)
        await Form.deal_name.set()
    # Сохранение названия сделки
    elif data.startswith('deal_name:'):
        deal_name = data.split(':')[1]
        await state.update_data(deal_name=deal_name)
        data = await state.get_data()
        deal_type = data.get('deal_type')
        ton_amount = data.get('ton_amount')
        if deal_type == 'buy':
            await message.answer(f"Вы хотите купить {ton_amount} TON. Подтвердите сделку:", reply_markup=kb.confirm_deal_buy(ton_amount, deal_name))
        else:
            await message.answer(f"Вы хотите продать {ton_amount} TON. Подтвердите сделку:", reply_markup=kb.confirm_deal_sell(ton_amount, deal_name))
        await Form.confirm_deal.set()
    # Подтверждение сделки
    elif data.startswith('confirm_deal:'):
        try:
            ton_amount = int(data.split(':')[1])
        except ValueError:
            await message.answer("Некорректное значение. Введите число.")
            return
        deal_name = data.split(':')[2]
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
        user = cursor.fetchone()
        if user:
            ton_balance = user[1]
            if ton_balance >= ton_amount:
                cursor.execute("INSERT INTO deals (buyer_id, seller_id, ton_amount, status, deal_name) VALUES (?, ?, ?, ?, ?)", (user_id, user_id, ton_amount, "Pending", deal_name))
                conn.commit()
                await message.answer(f"Сделка на {ton_amount} TON создана. Ожидаем подтверждения от другого пользователя.", reply_markup=kb.back_to_main)
                await handle_match(message, ton_amount, deal_name)
                await state.finish()
            else:
                await message.answer("Недостаточно средств на балансе!")
                await state.finish()
        else:
            await message.answer("Ошибка: Пользователь не найден")
            await state.finish()
    # Отправка товара
    elif data.startswith('send_goods:'):
        deal_id = int(data.split(':')[1])
        cursor.execute("UPDATE deals SET status = 'GoodsSent' WHERE id = ?", (deal_id,))
        conn.commit()
        await message.answer("Товар отправлен. Ожидайте подтверждения покупателя.", reply_markup=kb.back_to_main)
        await handle_goods_sent(deal_id)
    # Подтверждение получения товара
    elif data.startswith('confirm_receive:'):
        deal_id = int(data.split(':')[1])
        cursor.execute("UPDATE deals SET status = 'PaymentPending' WHERE id = ?", (deal_id,))
        conn.commit()
        await message.answer("Товар получен. Отправьте токены для завершения сделки.", reply_markup=kb.send_tokens(deal_id))
        await handle_receive_confirmed(deal_id)
    # Отправка токенов
    elif data.startswith('send_tokens:'):
        try:
            deal_id = int(data.split(':')[1])
        except ValueError:
            await message.answer("Некорректное значение. Введите число.")
            return
        await state.update_data(deal_id=deal_id)
        await message.answer("Введите количество TON для отправки:", reply_markup=kb.back_to_main)
        await Form.send_tokens.set()
    # Отправка токенов после ввода суммы
    elif data.startswith('send_tokens_amount:'):
        try:
            deal_id = int(data.split(':')[1])
        except ValueError:
            await message.answer("Некорректное значение. Введите число.")
            return
        try:
            ton_amount = int(data.split(':')[2])
        except ValueError:
            await message.answer("Некорректное значение. Введите число.")
            return
        cursor.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
        deal = cursor.fetchone()
        if deal:
            buyer_id, seller_id, ton_amount_deal, status, comments, deal_name = deal
            if seller_id == user_id:
                cursor.execute("UPDATE deals SET status = 'Completed' WHERE id = ?", (deal_id,))
                conn.commit()
                await message.answer("Токены отправлены. Сделка завершена.", reply_markup=kb.back_to_main)
                await handle_tokens_sent(deal_id, ton_amount)
                await state.finish()
            elif buyer_id == user_id:
                cursor.execute("UPDATE deals SET status = 'Completed' WHERE id = ?", (deal_id,))
                conn.commit()
                await message.answer("Токены отправлены. Сделка завершена.", reply_markup=kb.back_to_main)
                await handle_tokens_sent(deal_id, ton_amount)
                await state.finish()
        else:
            await message.answer("Ошибка: Сделка не найдена")
            await state.finish()
    # Начать спор
    elif data.startswith('start_dispute:'):
        deal_id = int(data.split(':')[1])
        await handle_dispute(deal_id)
        await state.finish()
    # Начать спор после ввода комментария
    elif data.startswith('confirm_dispute:'):
        deal_id = int(data.split(':')[1])
        cursor.execute("UPDATE deals SET status = 'Dispute' WHERE id = ?", (deal_id,))
        conn.commit()
        await message.answer("Сделка передана в спор. Ожидайте решения администратора.", reply_markup=kb.back_to_main)
        await handle_dispute_confirmed(deal_id)
        await state.finish()
    # Назад к главному меню
    elif data == 'back_to_main':
        await state.finish()
        await show_main_menu(message)

# Обработка поиска совпадений по сделкам
async def handle_match(message: Message, ton_amount, deal_name):
    user_id = message.from_user.id
    cursor.execute("SELECT * FROM deals WHERE status = 'Pending' AND ton_amount = ? AND deal_name = ? AND buyer_id != ? AND seller_id != ?", (ton_amount, deal_name, user_id, user_id))
    deals = cursor.fetchall()
    if deals:
        for deal in deals:
            deal_id, buyer_id, seller_id, ton_amount, status, comments, deal_name = deal
            if buyer_id == user_id:
                await message.answer(f"Найдена подходящая сделка. Ожидайте подтверждения от продавца.", reply_markup=kb.back_to_main)
                await bot.send_message(chat_id=seller_id, text=f"Поступила заявка на покупку {ton_amount} TON. Подтвердите сделку:", reply_markup=kb.confirm_deal(deal_id))
            else:
                await message.answer(f"Найдена подходящая сделка. Ожидайте подтверждения от покупателя.", reply_markup=kb.back_to_main)
                await bot.send_message(chat_id=buyer_id, text=f"Поступила заявка на продажу {ton_amount} TON. Подтвердите сделку:", reply_markup=kb.confirm_deal(deal_id))
            break
    else:
        await message.answer(f"Нет подходящих сделок на {ton_amount} TON. Попробуйте позже.", reply_markup=kb.back_to_main)

# Обработка отправки товара
async def handle_goods_sent(deal_id):
    cursor.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    deal = cursor.fetchone()
    if deal:
        buyer_id, seller_id, ton_amount, status, comments, deal_name = deal
        await bot.send_message(chat_id=buyer_id, text=f"Продавец отправил товар. Подтвердите получение и нажмите кнопку \"Подтвердить получение\".", reply_markup=kb.confirm_receive(deal_id))

# Обработка подтверждения получения товара
async def handle_receive_confirmed(deal_id):
    cursor.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    deal = cursor.fetchone()
    if deal:
        buyer_id, seller_id, ton_amount, status, comments, deal_name = deal
        await bot.send_message(chat_id=seller_id, text=f"Покупатель подтвердил получение товара. Ожидайте отправки токенов.", reply_markup=kb.back_to_main)

# Обработка отправки токенов
async def handle_tokens_sent(message:Message,deal_id, ton_amount):
    cursor.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    deal = cursor.fetchone()
    if deal:
        buyer_id, seller_id, ton_amount_deal, status, comments, deal_name = deal
        # Отправка токенов продавцу
        if seller_id == message.from_user.id:
            await bot.send_message(chat_id=buyer_id, text=f"Токены получены. Сделка завершена.", reply_markup=kb.back_to_main)
        # Отправка токенов покупателю
        elif buyer_id == message.from_user.id:
            await bot.send_message(chat_id=seller_id, text=f"Токены получены. Сделка завершена.", reply_markup=kb.back_to_main)

# Обработка начала спора
async def handle_dispute(deal_id):
    cursor.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    deal = cursor.fetchone()
    if deal:
        buyer_id, seller_id, ton_amount, status, comments, deal_name = deal
        await bot.send_message(chat_id=buyer_id, text=f"Администратор подключен к спору. Ожидайте решения.", reply_markup=kb.back_to_main)
        await bot.send_message(chat_id=seller_id, text=f"Администратор подключен к спору. Ожидайте решения.", reply_markup=kb.back_to_main)

# Обработка подтверждения начала спора
async def handle_dispute_confirmed(deal_id):
    cursor.execute("SELECT * FROM deals WHERE id = ?", (deal_id,))
    deal = cursor.fetchone()
    if deal:
        buyer_id, seller_id, ton_amount, status, comments, deal_name = deal
        await bot.send_message(chat_id=buyer_id, text=f"Администратор подключен к спору. Ожидайте решения.", reply_markup=kb.back_to_main)
        await bot.send_message(chat_id=seller_id, text=f"Администратор подключен к спору. Ожидайте решения.", reply_markup=kb.back_to_main)

# Обработка текстовых сообщений
@router.message()
async def text_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text
    # Обработка ввода количества TON для отправки токенов
    if state:
        current_state = await state.get_state()
        if current_state == Form.send_tokens.state:
            try:
                ton_amount = int(text)
            except ValueError:
                await message.answer("Некорректное значение. Введите число.")
                return
            data = await state.get_data()
            deal_id = data.get('deal_id')
            await message.answer(f"Вы хотите отправить {ton_amount} TON. Подтвердите отправку:", reply_markup=kb.confirm_send_tokens(deal_id, ton_amount))
            await Form.send_tokens_amount.set()
        elif current_state == Form.dispute.state:
            data = await state.get_data()
            deal_id = data.get('deal_id')
            cursor.execute("UPDATE deals SET comments = ? WHERE id = ?", (text, deal_id))
            conn.commit()
            await message.answer("Комментарий добавлен. Подтвердите начало спора:", reply_markup=kb.confirm_dispute(deal_id))
    # Обработка ввода комментария для спора
    elif text.startswith('/dispute'):
        try:
            deal_id = int(text.split(' ')[1])
        except ValueError:
            await message.answer("Некорректное значение. Введите число.")
            return
        await state.update_data(deal_id=deal_id)
        await message.answer("Введите комментарий к спору:", reply_markup=kb.back_to_main)
        await Form.dispute.set()