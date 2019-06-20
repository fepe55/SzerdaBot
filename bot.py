import os
import pytz
import json
import locale
import logging
from datetime import datetime
from collections import OrderedDict

from dotenv import load_dotenv

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.parsemode import ParseMode

load_dotenv()
locale.setlocale(locale.LC_ALL, 'es_AR.UTF-8')

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

API_TOKEN = os.getenv('API_TOKEN')

ALLOWED_STICKER_SETS = ['Piggy2019', 'vinki', ]
# FILE_PATH = 'resultados.json'


def _get_now():
    tz = pytz.timezone('America/Argentina/Buenos_Aires')
    now = datetime.now(tz)
    return now


def get_resultados(chat_id):
    file_path = 'resultados-{}.json'.format(chat_id)
    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            resultados = json.load(f)
    else:
        resultados = []

    return resultados


def save_resultados(resultados, chat_id):
    file_path = 'resultados-{}.json'.format(chat_id)
    with open(file_path, 'w') as f:
        f.write(json.dumps(resultados))


def _sumar_punto(resultado, username):
    if username in resultado['posiciones'].keys():
        resultado['posiciones'][username] += 1
    else:
        resultado['posiciones'][username] = 1
    return resultado


def get_time(bot, update):
    now = _get_now()
    message = now.strftime('%A %d/%m/%Y %H:%M:%S')
    bot.send_message(update.message.chat_id, message)


def print_resultados(bot, update):
    resultados = get_resultados(update.effective_chat.id)
    message = ''
    for resultado in resultados:
        # update.message.reply_text(resultado['dia'])
        message += '*{}*\n\n'.format(resultado['dia'])
        posiciones = resultado['posiciones']
        posiciones = OrderedDict(
            sorted(posiciones.items(), key=lambda x: x[1], reverse=True)
        )
        for user, puntos in posiciones.items():
            message += '{} - {}\n'.format(user, puntos)

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

    now = _get_now()
    es_miercoles = now.weekday() == 2
    hoy = now.date().strftime('%d/%m/%Y')
    if not es_miercoles:
        return

    resultados = get_resultados(update.effective_chat.id)
    if resultados and resultados[-1]['dia'] == hoy:
        resultados_de_hoy = resultados.pop()
    else:
        resultados_de_hoy = {'dia': hoy, 'posiciones': {}}

    sticker_set = update.message.sticker.set_name

    if sticker_set not in ALLOWED_STICKER_SETS:
        resultados_de_hoy = _sumar_punto(resultados_de_hoy, user.username)
        resultados.append(resultados_de_hoy)
        save_resultados(resultados, update.effective_chat.id)
        # print_resultados(bot, update)
    # else:
    #     update.message.reply_text('You are safe... for now')


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
    dp.add_handler(CommandHandler('posiciones', print_resultados))
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
