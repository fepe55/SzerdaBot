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

ALLOWED_STICKER_SETS = ['Piggy2019', 'vinki', ]
# FILE_PATH = 'resultados.json'


def _easter_egg(bot, update):
    PUG_RECEIVED = 'CAADAgADeQMAAu7EoQobkLnjCnMGDQI'

    # PUG_TO_SEND
    file_id = 'CAADAgADBAEAAvR7GQABgBHkQCvGnPsC'
    width = 440
    height = 512
    STICKER_TO_SEND = Sticker(file_id=file_id, height=height, width=width)

    if update.message.sticker.file_id == PUG_RECEIVED:
        bot.send_sticker(update.message.chat_id, STICKER_TO_SEND)


def _get_now():
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    now = datetime.now(tz)
    return now


def _es_miercoles():
    now = _get_now()
    return DEBUG or now.weekday() == 2


def get_resultados(chat_id, LIMIT=None):
    file_path = 'resultados-{}.json'.format(chat_id)
    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            resultados = json.load(f)
    else:
        resultados = []

    resultados = _update_resultados(resultados)
    if LIMIT:
        resultados = resultados[:LIMIT]
    return resultados


def save_resultados(resultados, chat_id):
    file_path = 'resultados-{}.json'.format(chat_id)
    with open(file_path, 'w') as f:
        f.write(json.dumps(resultados))


def _update_resultados(resultados):
    """
    Update the resultados for every wednesday already passed since the last one
    """
    now = _get_now()
    hoy_str = now.date().strftime(DATE_FORMAT)
    if not resultados:
        if _es_miercoles():
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


def get_time(bot, update):
    now = _get_now()
    message = now.strftime(DATETIME_FORMAT)
    bot.send_message(update.message.chat_id, message)


def get_posiciones_generales(bot, update):
    '''
    Get posiciones generales. Days won. Total stickers sent
    users format: {
      'juancito': {'stickers_sent': 99, 'days_lost': 2},
      'pedrito': {'stickers_sent': 9, 'days_lost': 4},
    }
    '''
    resultados = get_resultados(update.effective_chat.id)
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
        # Only one user sent the wrong stickers
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
    bot.send_message(
        update.message.chat_id, message, parse_mode=ParseMode.MARKDOWN
    )


def get_posiciones(bot, update):
    ''' Get posiciones by day '''
    resultados = get_resultados(update.effective_chat.id, LIMIT=5)
    message = ''
    for resultado in resultados:
        # update.message.reply_text(resultado['dia'])
        message += '*{}*\n'.format(resultado['dia'])
        posiciones = resultado['posiciones']
        posiciones = OrderedDict(
            sorted(posiciones.items(), key=lambda x: x[1], reverse=True)
        )
        for user, puntos in posiciones.items():
            message += '{} - {}\n'.format(user, puntos)
        if not posiciones.items():
            message += 'Nadie mandó no-szerdos\n'
        message += '\n'

    # Message as a reply
    # update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    # Message as a standalone message
    if not message:
        message = 'Aún no hay posiciones'
    bot.send_message(
        update.message.chat_id, message, parse_mode=ParseMode.MARKDOWN
    )


def check_sticker_set(bot, update):
    user = update.message.from_user
    if user.is_bot:
        return

    _easter_egg(bot, update)
    if not _es_miercoles():
        return

    now = _get_now()
    hoy_str = now.date().strftime(DATE_FORMAT)
    resultados = get_resultados(update.effective_chat.id)

    if resultados and hoy_str in [x['dia'] for x in resultados]:
        index_to_pop = None
        for index, r in enumerate(resultados):
            if r['dia'] == hoy_str:
                index_to_pop = index
                break
        resultados_de_hoy = resultados.pop(index_to_pop)
    else:
        resultados_de_hoy = {'dia': hoy_str, 'posiciones': {}}

    sticker_set = update.message.sticker.set_name

    if sticker_set not in ALLOWED_STICKER_SETS:
        resultados_de_hoy = _sumar_punto(resultados_de_hoy, user.username)
        resultados.insert(0, resultados_de_hoy)
        save_resultados(resultados, update.effective_chat.id)
        if DEBUG:
            get_posiciones(bot, update)
    else:
        if DEBUG:
            update.message.reply_text('You are safe... for now')


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(API_TOKEN)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.sticker, check_sticker_set))
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
