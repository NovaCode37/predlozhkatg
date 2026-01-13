import logging
import time
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, \
    CallbackQueryHandler

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
MODERATION_GROUP_ID = int(os.getenv('MODERATION_GROUP_ID', '-1003481535857'))
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1003697286219'))

if not BOT_TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN в файле .env")
    exit(1)

TITLE, TEXT = range(2)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
news_storage = {}


async def debug_all_messages(update: Update, context: CallbackContext):
    logger.info(f"🔍 DEBUG: Получено сообщение: '{update.message.text}' от {update.effective_user.id}")
    logger.info(f"🔍 DEBUG: user_data = {context.user_data}")


async def start(update: Update, context: CallbackContext) -> None:
    logger.info(f"🟢 /start от {update.effective_user.id}")
    keyboard = [[InlineKeyboardButton("Предложить новость", callback_data='start_post')]]
    await update.message.reply_text('Бот для новостей. Нажмите кнопку.', reply_markup=InlineKeyboardMarkup(keyboard))


async def start_post(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    logger.info(f"🟡 start_post от {update.effective_user.id}")
    await query.edit_message_text("Напишите заголовок для вашей новости:")
    return TITLE


async def get_title(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text
    logger.info(f"🟡 get_title от {update.effective_user.id}: '{user_text}'")
    context.user_data['news_title'] = user_text
    await update.message.reply_text("Теперь отправьте полный текст новости:")
    return TEXT


async def get_text(update: Update, context: CallbackContext) -> int:
    news_text = update.message.text
    news_title = context.user_data.get('news_title', 'НЕТ ЗАГОЛОВКА')
    user = update.effective_user
    logger.info(f"🟡 get_text от {user.id}, заголовок: {news_title}")

    unique_key = f"{user.id}_{int(time.time())}"
    news_storage[unique_key] = {
        'title': news_title,
        'text': news_text,
        'user_id': user.id,
        'username': user.username or user.first_name
    }

    keyboard = [
        [
            InlineKeyboardButton("Опубликовать", callback_data=f'publish_{unique_key}'),
            InlineKeyboardButton("Отклонить", callback_data=f'reject_{unique_key}')
        ]
    ]

    await context.bot.send_message(
        chat_id=MODERATION_GROUP_ID,
        text=f"*Новая новость на модерацию*\n\n"
             f"*От:* {user.username or user.first_name} (ID: {user.id})\n"
             f" *Заголовок:* {news_title}\n"
             f"*Текст:* {news_text}\n\n"
             f"*ID:* `{unique_key}`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("Новость отправлена на модерацию.")
    context.user_data.clear()
    return ConversationHandler.END


async def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    action, unique_key = query.data.split('_', 1)

    if unique_key not in news_storage:
        await query.edit_message_text("Новость не найдена (возможно, уже обработана)")
        return

    news = news_storage[unique_key]

    if action == 'publish':
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"*{news['title']}*\n\n{news['text']}",
            parse_mode='Markdown'
        )

        try:
            await context.bot.send_message(
                chat_id=news['user_id'],
                text=f"Ваша новость опубликована!\n\n"
                     f"*{news['title']}*"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {news['user_id']}: {e}")

        await query.edit_message_text(
            text=f"ОПУБЛИКОВАНО\n\n"
                 f"Заголовок: {news['title']}\n"
                 f"Автор: {news['username']}\n"
                 f"ID: {unique_key}",
            reply_markup=None
        )

    elif action == 'reject':
        try:
            await context.bot.send_message(
                chat_id=news['user_id'],
                text=f"Ваша новость отклонена модератором.\n\n"
                     f"*{news['title']}*"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {news['user_id']}: {e}")

        await query.edit_message_text(
            text=f"ОТКЛОНЕНО\n\n"
                 f"Заголовок: {news['title']}\n"
                 f"Автор: {news['username']}\n"
                 f"ID:: {unique_key}",
            reply_markup=None
        )

    del news_storage[unique_key]


async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Отменено.')
    context.user_data.clear()
    return ConversationHandler.END


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_post, pattern='^start_post$')],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_text)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        name="news_conversation"
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))

    application.add_handler(CallbackQueryHandler(button_callback, pattern='^(publish|reject)_'))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, debug_all_messages))

    logger.info("Бот запускается...")
    application.run_polling()


if __name__ == '__main__':
    main()
