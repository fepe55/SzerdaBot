import os
import re
import pytz
import json
import locale
import logging
from datetime import datetime, timedelta
from collections import OrderedDict

from dotenv import load_dotenv

from telegram import Sticker, Update
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext,
)
from telegram.parsemode import ParseMode

'''
Resultados format:
[
  {'dia': '10/10/2018', 'posiciones': {'juancito': 8, 'pedrito': 19}}
  {'dia': '17/10/2018', 'posiciones': {'juancito': 18, 'pedrito': 0}}
  {'dia': '24/10/2018', 'posiciones': {'juancito': 8, 'pedrito': 0}}
]
'''

load_dotenv()
locale.setlocale(locale.LC_ALL, 'es_AR.UTF-8')
DATE_FORMAT = '%d/%m/%Y'
DATETIME_FORMAT = '%A %d/%m/%Y %H:%M:%S'
# Example: 'Wordle (ES) #22 3/6'
# Example: 'Wordle (ES)  #82 5/6'
# WORDLE_PATTERN = r'Wordle \(ES\) #(\d+) (\d)\/6'
# Added a bunch of (?: )+ in case the author adds more spaces
WORDLE_PATTERN = r'Wordle(?: )+\(ES\)(?: )+#(\d+)(?: )+(\d)\/6'
WORDLE_REGEX = re.compile(WORDLE_PATTERN)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

API_TOKEN = os.getenv('API_TOKEN')
DEBUG = os.getenv('SZERDA_DEBUG', False)

ALLOWED_STICKER_SETS = [
    'Piggy2019',
    'vinki',
    'NickWallowPig',
    'waddles_pig',
    'svincent_vk',
]
# FILE_PATH = 'resultados.json'


def _get_now():
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    now = datetime.now(tz)
    return now


def _es_miercoles(dt: datetime = None):
    if not dt:
        dt = _get_now()
    return DEBUG or dt.weekday() == 2


def _es_lunes(dt: datetime = None):
    if not dt:
        dt = _get_now()
    return DEBUG or dt.weekday() == 0


class Game:
    def __init__(self, prefix, validity_function_check):
        self._prefix = prefix
        self._validity_function_check = validity_function_check

    @property
    def prefix(self):
        return self._prefix

    @property
    def validity_function_check(self):
        return self._validity_function_check


SZERDA_GAME = Game('szerda', _es_miercoles)
DAILY_GAME = Game('daily', _es_lunes)
WORDLE_GAME = Game('wordle', lambda _=None: True)


def _easter_egg(update, context):
    # PUG_RECEIVED_FILE_ID = 'CAACAgIAAxkBAAICQF8SWXrp9vpWQiv4HjjuzwdOv51CAAJ5AwAC7sShChuQueMKcwYNGgQ'  # noqa
    PUG_RECEIVED_UNIQUE_ID = 'AgADeQMAAu7EoQo'

    # PUG_TO_SEND
    file_id = 'CAACAgIAAxkBAAICP18SWNY-NLC_96rFAemzZ0s2nLCVAAIEAQAC9HsZAAGAEeRAK8ac-xoE'  # noqa
    file_unique_id = 'AgADBAEAAvR7GQAB'
    width = 440
    height = 512
    STICKER_TO_SEND = Sticker(
        file_id=file_id, file_unique_id=file_unique_id,
        width=width, height=height, is_animated=False,
    )

    if update.message.sticker.file_unique_id == PUG_RECEIVED_UNIQUE_ID:
        context.bot.send_sticker(update.message.chat_id, STICKER_TO_SEND)


def _get_stickers_de_hoy(chat_id):
    now = _get_now()
    now_filename_str = now.strftime('%Y%m%d')
    file_path = '{}-stickers-{}.json'.format(now_filename_str, chat_id)
    if not os.path.isfile(file_path):
        with open(file_path, 'w') as f:
            f.write(json.dumps([]))
    with open(file_path, 'r') as f:
        stickers = json.load(f)
    return stickers
    # return [sticker['file_unique_id'] for sticker in stickers]


def _update_stickers_de_hoy(chat_id, sticker):
    now = _get_now()
    now_filename_str = now.strftime('%Y%m%d')
    file_path = '{}-stickers-{}.json'.format(now_filename_str, chat_id)
    stickers_de_hoy = _get_stickers_de_hoy(chat_id)
    stickers_de_hoy.append({
        'file_id': sticker.file_id,
        'file_unique_id': sticker.file_unique_id,
        'width': sticker.width,
        'height': sticker.height,
        'is_animated': sticker.is_animated,
    })
    with open(file_path, 'w') as f:
        f.write(json.dumps(stickers_de_hoy))


def _get_resultados_de_hoy(resultados):
    " Get today's results if they already exist, else we return a new dict "
    now = _get_now()
    hoy_str = now.date().strftime(DATE_FORMAT)

    if resultados and hoy_str in [x['dia'] for x in resultados]:
        index_to_pop = None
        for index, r in enumerate(resultados):
            if r['dia'] == hoy_str:
                index_to_pop = index
                break
        resultados_de_hoy = resultados.pop(index_to_pop)
    else:
        resultados_de_hoy = {'dia': hoy_str, 'posiciones': {}}

    return resultados_de_hoy


def get_resultados(chat_id, game, limit=None):
    file_path = '{}-resultados-{}.json'.format(game.prefix, chat_id)
    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            resultados = json.load(f)
    else:
        resultados = []

    resultados = _update_resultados(resultados, game)
    if limit:
        resultados = resultados[:limit]
    return resultados


def save_resultados(resultados, chat_id, game):
    file_path = '{}-resultados-{}.json'.format(game.prefix, chat_id)
    with open(file_path, 'w') as f:
        f.write(json.dumps(resultados))


def _update_resultados(resultados, game):
    """
    Update the resultados for every day already passed since the last one
    """
    now = _get_now()
    hoy_str = now.date().strftime(DATE_FORMAT)
    if not resultados:
        # if _es_miercoles():
        if game.validity_function_check():
            resultados_de_hoy = {'dia': hoy_str, 'posiciones': {}}
            resultados.insert(0, resultados_de_hoy)
    else:
        ultimo_resultados = resultados[0]
        ultimo_dia_str = ultimo_resultados['dia']
        ultimo_dia = datetime.strptime(ultimo_dia_str, DATE_FORMAT)
        dia = ultimo_dia + timedelta(days=1)
        while dia.date() <= now.date():
            if game.validity_function_check(dia):
                dia_str = dia.date().strftime(DATE_FORMAT)
                resultados_del_dia = {'dia': dia_str, 'posiciones': {}}
                resultados.insert(0, resultados_del_dia)
            dia += timedelta(days=1)
    return resultados


def _sumar_puntos(resultado, username, puntos):
    puntos = int(puntos)
    if username in resultado['posiciones'].keys():
        resultado['posiciones'][username] += puntos
    else:
        resultado['posiciones'][username] = puntos
    return resultado


def get_time(update, context):
    now = _get_now()
    message = now.strftime(DATETIME_FORMAT)
    context.bot.send_message(update.message.chat_id, message)


def get_posiciones_generales(update, context):
    chat_id = update.effective_chat.id

    _update_file(chat_id, SZERDA_GAME)
    message = '*Posiciones Szerda*:\n'
    message += _get_posiciones_generales_msg(chat_id, context, SZERDA_GAME)

    _update_file(chat_id, DAILY_GAME)
    message += '\n*Posiciones Daily*:\n'
    message += _get_posiciones_generales_msg(chat_id, context, DAILY_GAME)

    context.bot.send_message(
        update.message.chat_id, message, parse_mode=ParseMode.MARKDOWN
    )


def _get_posiciones_generales_msg(chat_id, context, game):
    '''
    Get posiciones generales. Days won. Total points (stickers sent)
    users format: {
      'juancito': {'points': 99, 'days_lost': 2},
      'pedrito': {'points': 9, 'days_lost': 4},
    }
    '''
    resultados = get_resultados(chat_id, game)
    users = {}
    for dia in resultados:
        posiciones = dia['posiciones']
        for user, points in posiciones.items():
            if user in users.keys():
                users[user]['points'] += points
            else:
                users[user] = {
                    'points': points,
                    'days_lost': 0
                }

        # Empty day
        if not posiciones:
            continue
        # Only one user "scored"
        if len(posiciones) == 1:
            user, points = list(posiciones.items())[0]
            users[user]['days_lost'] += 1
        # Two users
        else:
            posiciones_sorted = sorted(
                posiciones.items(), key=lambda x: x[1], reverse=True
            )
            first, f_points = posiciones_sorted[0]
            second, s_points = posiciones_sorted[1]
            # If the first and second one have the same number of stickers
            # sent, then it's a draw. No loser
            if f_points > s_points:
                users[first]['days_lost'] += 1

    message = ''
    users = OrderedDict(
        sorted(
            users.items(), reverse=True,
            key=lambda x: (x[1]['days_lost'], x[1]['points'])
        )
    )
    for user, data in users.items():
        message += '{} - {} ({})\n'.format(
            user, data['days_lost'], data['points']
        )

    if not message:
        message = 'Aún no hay posiciones'
    return message


def get_posiciones(update, context):
    ''' Get posiciones by day '''
    chat_id = update.effective_chat.id

    _update_file(chat_id, SZERDA_GAME)
    _update_file(chat_id, DAILY_GAME)
    _update_file(chat_id, WORDLE_GAME)

    resultados_szerda = get_resultados(chat_id, SZERDA_GAME, limit=3)
    resultados_daily = get_resultados(chat_id, DAILY_GAME, limit=3)
    resultados_wordle = get_resultados(chat_id, WORDLE_GAME, limit=3)

    message = '*Posiciones Szerda*:\n'
    if not resultados_szerda:
        message += 'Aún no hay posiciones'
    for resultado in resultados_szerda:
        # update.message.reply_text(resultado['dia'])
        message += '_{}_\n'.format(resultado['dia'])
        posiciones = resultado['posiciones']
        posiciones = OrderedDict(
            sorted(posiciones.items(), key=lambda x: x[1], reverse=True)
        )
        for user, puntos in posiciones.items():
            message += '{} - {}\n'.format(user, puntos)
        if not posiciones.items():
            message += 'Nadie mandó no-szerdos\n'
        message += '\n'

    message += '\n*Posiciones Daily*:\n'
    if not resultados_daily:
        message += 'Aún no hay posiciones'
    for resultado in resultados_daily:
        # update.message.reply_text(resultado['dia'])
        message += '_{}_\n'.format(resultado['dia'])
        posiciones = resultado['posiciones']
        posiciones = OrderedDict(
            sorted(posiciones.items(), key=lambda x: x[1], reverse=True)
        )
        for user, puntos in posiciones.items():
            message += '{} - {}\n'.format(user, puntos)
        if not posiciones.items():
            message += 'Nadie mandó stickers repetidos\n'
        message += '\n'

    message += '\n*Posiciones Wordle*:\n'
    if not resultados_wordle:
        message += 'Aún no hay posiciones'
    for resultado in resultados_wordle:
        # update.message.reply_text(resultado['dia'])
        message += '_{}_\n'.format(resultado['dia'])
        posiciones = resultado['posiciones']
        posiciones = OrderedDict(
            sorted(posiciones.items(), key=lambda x: x[1], reverse=True)
        )
        for user, puntos in posiciones.items():
            message += '{} - {}\n'.format(user, puntos)
        if not posiciones.items():
            message += 'Nadie jugó Wordle\n'
        message += '\n'

    # Message as a reply
    # update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    # Message as a standalone message
    context.bot.send_message(
        update.message.chat_id, message, parse_mode=ParseMode.MARKDOWN
    )


def show_stickers_de_hoy(update, context):
    stickers_de_hoy = _get_stickers_de_hoy(update.effective_chat.id)
    for sticker in stickers_de_hoy:
        # sticker_to_send = Sticker(
        #     file_id=sticker['file_id'],
        #     file_unique_id=sticker['file_unique_id'],
        #     width=sticker['width'], height=sticker['height'],
        #     is_animated=sticker['is_animated'],
        # )
        sticker_to_send = Sticker(**sticker)
        context.bot.send_sticker(update.message.chat_id, sticker_to_send)


def check_texts(update: Update, context: CallbackContext):
    # We ignore edited messages for now
    if not hasattr(update, 'message') or not update.message:
        return
    user = update.message.from_user
    if user.is_bot:
        return
    user = update.message.from_user
    message = update.message.text
    chat_id = update.effective_chat.id

    resultados = get_resultados(chat_id, WORDLE_GAME)
    resultados_de_hoy = _get_resultados_de_hoy(resultados)

    result = WORDLE_REGEX.match(message)
    if result and len(result.groups()) == 2:
        (wordle_id, score) = result.groups()
        msg = (
            f'Es un wordle correcto {user.username}, es el número {wordle_id}'
            f' y tu score fue de {score} sobre 6'
        )

        if user.username in resultados_de_hoy['posiciones'].keys():
            msg = 'Ya jugaste este día 🤔'
            update.message.reply_text(msg, quote=True)
        else:
            resultados_de_hoy = _sumar_puntos(
                resultados_de_hoy, user.username, score
            )
            resultados.insert(0, resultados_de_hoy)
            save_resultados(resultados, update.effective_chat.id, WORDLE_GAME)

            update.message.reply_text(msg, quote=True)
    else:
        if DEBUG:
            if not result:
                msg = 'No cumple el pattern de Wordle'
            else:
                groups = len(result.groups())
                msg = f'Cumple el pattern, pero hay {groups} groups. Raro'
            update.message.reply_text(msg)


def check_stickers(update, context):
    user = update.message.from_user
    if user.is_bot:
        return
    _easter_egg(update, context)

    if _es_miercoles():
        check_sticker_set(update, context)
    if _es_lunes():
        check_daily_stickers(update, context)
    if DEBUG:
        sticker_set = update.message.sticker.set_name
        msg = 'This sticker belongs to the sticker set {}'.format(sticker_set)
        update.message.reply_text(msg)
        get_posiciones(update, context)


def check_sticker_set(update, context):
    user = update.message.from_user

    chat_id = update.effective_chat.id
    resultados = get_resultados(chat_id, SZERDA_GAME)

    resultados_de_hoy = _get_resultados_de_hoy(resultados)

    sticker_set = update.message.sticker.set_name

    if sticker_set and sticker_set not in ALLOWED_STICKER_SETS:
        resultados_de_hoy = _sumar_puntos(resultados_de_hoy, user.username, 1)
        resultados.insert(0, resultados_de_hoy)
        save_resultados(resultados, update.effective_chat.id, SZERDA_GAME)
        if DEBUG:
            update.message.reply_text('NON-SZERDA, GOT YA!')
    elif DEBUG:
        update.message.reply_text('You are szerda safe... for now')


def check_daily_stickers(update, context):
    user = update.message.from_user

    resultados = get_resultados(update.effective_chat.id, DAILY_GAME)
    resultados_de_hoy = _get_resultados_de_hoy(resultados)
    stickers_de_hoy = _get_stickers_de_hoy(update.effective_chat.id)
    stickers_ids = [sticker['file_unique_id'] for sticker in stickers_de_hoy]

    sticker = update.message.sticker

    if sticker.set_name and sticker.file_unique_id in stickers_ids:
        resultados_de_hoy = _sumar_puntos(resultados_de_hoy, user.username, 1)
        resultados.insert(0, resultados_de_hoy)
        save_resultados(resultados, update.effective_chat.id, DAILY_GAME)
        if DEBUG:
            update.message.reply_text('REPEATED STICKER, GOT YA!')
    else:
        _update_stickers_de_hoy(update.effective_chat.id, sticker)
        if DEBUG:
            update.message.reply_text('You are daily safe... for now')


def _update_file(chat_id, game):
    resultados = get_resultados(chat_id, game)
    save_resultados(resultados, chat_id, game)


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(API_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('stickers_de_hoy', show_stickers_de_hoy))
    dp.add_handler(CommandHandler('posiciones', get_posiciones))
    dp.add_handler(CommandHandler(
        'posiciones_generales', get_posiciones_generales
    ))
    dp.add_handler(CommandHandler('time', get_time))
    dp.add_handler(MessageHandler(Filters.sticker, check_stickers))
    dp.add_handler(MessageHandler(Filters.text, check_texts))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
