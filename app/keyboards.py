from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from pytonconnect import TonConnect

main = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text='Мои сделки', callback_data='mydeals')],
    [KeyboardButton(text='Создать сделку', callback_data='newdeal')]],
    resize_keyboard=True
)

def getWallets():
    wallets_list = TonConnect.get_wallets()
    ans = []
    for wallet in wallets_list:
        ans.append([InlineKeyboardButton(text=wallet['name'], callback_data=f'connect:{wallet["name"]}')])
    return ans

wallets = InlineKeyboardMarkup(inline_keyboard=getWallets())

deals = ['1', '2', '3']
async def deals():
    keyboard = InlineKeyboardBuilder()
    for deal in deals:
        keyboard.add(InlineKeyboardButton(text=deal))
    return keyboard.adjust(2).as_markup()
