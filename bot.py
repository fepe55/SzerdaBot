import os
import pytz
import json
import locale
import logging
from datetime import datetime, timedelta
from collections import OrderedDict

from dotenv import load_dotenv

from telegram import Sticker
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
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

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

API_TOKEN = os.getenv('API_TOKEN')
DEBUG = os.getenv('SZERDA_DEBUG', False)

ALLOWED_STICKER_SETS = ['Piggy2019', 'vinki', 'NickWallowPig']
# FILE_PATH = 'resultados.json'


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


def _get_now():
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    now = datetime.now(tz)
    return now


def _es_miercoles():
    now = _get_now()
    return DEBUG or now.weekday() == 2


def _es_jueves():
    now = _get_now()
    return DEBUG or now.weekday() == 3


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


def get_resultados(chat_id, prefix, day_function_check, limit=None):
    file_path = '{}-resultados-{}.json'.format(prefix, chat_id)
    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            resultados = json.load(f)
    else:
        resultados = []

    resultados = _update_resultados(resultados, day_function_check)
    if limit:
        resultados = resultados[:limit]
    return resultados


def save_resultados(resultados, chat_id, prefix):
    file_path = '{}-resultados-{}.json'.format(prefix, chat_id)
    with open(file_path, 'w') as f:
        f.write(json.dumps(resultados))


def _update_resultados(resultados, day_function_check):
    """
    Update the resultados for every day already passed since the last one
    """
    now = _get_now()
    hoy_str = now.date().strftime(DATE_FORMAT)
    if not resultados:
        # if _es_miercoles():
        if day_function_check():
            resultados_de_hoy = {'dia': hoy_str, 'posiciones': {}}
            resultados.insert(0, resultados_de_hoy)
    else:
        ultimo_resultados = resultados[0]
        ultimo_dia_str = ultimo_resultados['dia']
        ultimo_dia = datetime.strptime(ultimo_dia_str, DATE_FORMAT).date()
        dia = ultimo_dia + timedelta(days=7)
        while dia <= now.date():
            dia_str = dia.strftime(DATE_FORMAT)
            resultados_del_dia = {'dia': dia_str, 'posiciones': {}}
            resultados.insert(0, resultados_del_dia)
            dia += timedelta(days=7)
    return resultados


def _sumar_punto(resultado, username):
    if username in resultado['posiciones'].keys():
        resultado['posiciones'][username] += 1
    else:
        resultado['posiciones'][username] = 1
    return resultado


def get_time(update, context):
    now = _get_now()
    message = now.strftime(DATETIME_FORMAT)
    context.bot.send_message(update.message.chat_id, message)


def get_posiciones_generales(update, context):
    message = '*Posiciones Szerda*:\n'
    message += _get_posiciones_generales_msg(
        update, context, 'szerda', _es_miercoles
    )

    message += '\n*Posiciones Daily*:\n'
    message += _get_posiciones_generales_msg(
        update, context, 'daily', _es_jueves
    )

    context.bot.send_message(
        update.message.chat_id, message, parse_mode=ParseMode.MARKDOWN
    )


def _get_posiciones_generales_msg(update, context, prefix, day_function_check):
    '''
    Get posiciones generales. Days won. Total stickers sent
    users format: {
      'juancito': {'stickers_sent': 99, 'days_lost': 2},
      'pedrito': {'stickers_sent': 9, 'days_lost': 4},
    }
    '''
    chat_id = update.effective_chat.id
    resultados = get_resultados(chat_id, prefix, day_function_check)
    users = {}
    for dia in resultados:
        posiciones = dia['posiciones']
        for user, stickers_sent in posiciones.items():
            if user in users.keys():
                users[user]['stickers_sent'] += stickers_sent
            else:
                users[user] = {
                    'stickers_sent': stickers_sent,
                    'days_lost': 0
                }

        # Empty day
        if not posiciones:
            continue
        # Only one user "scored"
        if len(posiciones) == 1:
            user, stickers_sent = list(posiciones.items())[0]
            users[user]['days_lost'] += 1
        # More than one user
        else:
            posiciones_sorted = sorted(
                posiciones.items(), key=lambda x: x[1], reverse=True
            )
            first, f_stickers_sent = posiciones_sorted[0]
            second, s_stickers_sent = posiciones_sorted[1]
            # If the first and second one have the same number of stickers
            # sent, then it's a draw. No loser
            if f_stickers_sent > s_stickers_sent:
                users[first]['days_lost'] += 1

    message = ''
    users = OrderedDict(
        sorted(
            users.items(), reverse=True,
            key=lambda x: (x[1]['days_lost'], x[1]['stickers_sent'])
        )
    )
    for user, data in users.items():
        message += '{} - {} ({})\n'.format(
            user, data['days_lost'], data['stickers_sent']
        )

    if not message:
        message = 'Aún no hay posiciones'
    return message


def get_posiciones(update, context):
    ''' Get posiciones by day '''
    chat_id = update.effective_chat.id
    resultados_szerda = get_resultados(chat_id, 'szerda', _es_miercoles, limit=5)  # noqa
    resultados_daily = get_resultados(chat_id, 'daily', _es_jueves, limit=5)

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

    # Message as a reply
    # update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    # Message as a standalone message
    context.bot.send_message(
        update.message.chat_id, message, parse_mode=ParseMode.MARKDOWN
    )


def check_stickers(update, context):
    user = update.message.from_user
    if user.is_bot:
        return
    _easter_egg(update, context)
    if _es_miercoles():
        check_sticker_set(update, context)
    if _es_jueves():
        check_daily_stickers(update, context)
    if DEBUG:
        get_posiciones(update, context)


def check_sticker_set(update, context):
    user = update.message.from_user

    chat_id = update.effective_chat.id
    resultados = get_resultados(chat_id, 'szerda', _es_miercoles)

    resultados_de_hoy = _get_resultados_de_hoy(resultados)

    sticker_set = update.message.sticker.set_name

    if sticker_set not in ALLOWED_STICKER_SETS:
        resultados_de_hoy = _sumar_punto(resultados_de_hoy, user.username)
        resultados.insert(0, resultados_de_hoy)
        save_resultados(resultados, update.effective_chat.id, 'szerda')
    elif DEBUG:
        update.message.reply_text('You are szerda safe... for now')


def check_daily_stickers(update, context):
    user = update.message.from_user

    resultados = get_resultados(update.effective_chat.id, 'daily', _es_jueves)
    resultados_de_hoy = _get_resultados_de_hoy(resultados)
    stickers_de_hoy = _get_stickers_de_hoy(update.effective_chat.id)
    stickers_ids = [sticker['file_unique_id'] for sticker in stickers_de_hoy]

    sticker = update.message.sticker
    if sticker.file_unique_id in stickers_ids:
        resultados_de_hoy = _sumar_punto(resultados_de_hoy, user.username)
        resultados.insert(0, resultados_de_hoy)
        save_resultados(resultados, update.effective_chat.id, 'daily')
    else:
        _update_stickers_de_hoy(update.effective_chat.id, sticker)
        if DEBUG:
            update.message.reply_text('You are daily safe... for now')


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

    dp.add_handler(MessageHandler(Filters.sticker, check_stickers))
    dp.add_handler(CommandHandler('posiciones', get_posiciones))
    dp.add_handler(CommandHandler(
        'posiciones_generales', get_posiciones_generales
    ))
    dp.add_handler(CommandHandler('time', get_time))

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
