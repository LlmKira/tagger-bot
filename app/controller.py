# -*- coding: utf-8 -*-
# @Time    : 2023/11/18 上午12:18
# @File    : controller.py
# @Software: PyCharm
from io import BytesIO

from asgiref.sync import sync_to_async
from loguru import logger
from telebot import formatting
from telebot import types
from telebot import util
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_helper import ApiTelegramException
from telebot.asyncio_storage import StateMemoryStorage

from app.event import pipeline_tag
from app_conf import settings
from setting.telegrambot import BotSetting

StepCache = StateMemoryStorage()


@sync_to_async
def sync_to_async_func():
    pass


class BotRunner(object):
    def __init__(self):
        self.bot = AsyncTeleBot(BotSetting.token, state_storage=StepCache)

    async def download(self, file):
        assert hasattr(file, "file_id"), "file_id not found"
        name = file.file_id
        _file_info = await self.bot.get_file(file.file_id)
        if isinstance(file, types.PhotoSize):
            name = f"{_file_info.file_unique_id}.jpg"
        if isinstance(file, types.Document):
            name = f"{file.file_unique_id} {file.file_name}"
        if not name.endswith(("jpg", "png", "webp")):
            return None
        downloaded_file = await self.bot.download_file(_file_info.file_path)
        return downloaded_file

    async def tagger(self, file) -> str:
        file_data = await self.download(file=file)
        if file_data is None:
            return "🥛 Not An image"
        if isinstance(file_data, bytes):
            file_data = BytesIO(file_data)
        result = await pipeline_tag(trace_id="test", content=file_data)
        content = [
            formatting.mbold(f"🥽 AnimeScore: {result.anime_score}"),
            formatting.mcode(result.anime_tags)
        ]
        if result.characters:
            content.append(formatting.mbold(f"🌟 Characters: {result.characters}"))
        prompt = formatting.format_text(
            *content
        )
        return prompt

    async def run(self):
        logger.info("Bot Start")
        bot = self.bot
        if BotSetting.proxy_address:
            from telebot import asyncio_helper

            asyncio_helper.proxy = BotSetting.proxy_address
            logger.info("Proxy tunnels are being used!")

        @bot.message_handler(content_types=["photo", "document"], chat_types=["private"])
        async def start(message: types.Message):
            if settings.mode.only_white:
                if message.chat.id not in settings.mode.white_group:
                    return logger.info(f"White List Out {message.chat.id}")
            logger.info(f"Report in {message.chat.id} {message.from_user.id}")
            if message.photo:
                prompt = await self.tagger(file=message.photo[-1])
                await bot.reply_to(message, text=prompt, parse_mode="MarkdownV2")
            if message.document:
                prompt = await self.tagger(file=message.document)
                await bot.reply_to(message, text=prompt, parse_mode="MarkdownV2")

        @bot.message_handler(commands="tag", chat_types=["supergroup", "group"])
        async def tag(message: types.Message):
            if settings.mode.only_white:
                if message.chat.id not in settings.mode.white_group:
                    return logger.info(f"White List Out {message.chat.id}")

            if not message.reply_to_message:
                return await bot.reply_to(
                    message,
                    text=f"🍡 please reply to message with this command ({message.chat.id})",
                )
            logger.info(f"Report in {message.chat.id} {message.from_user.id}")
            reply_message = message.reply_to_message
            reply_message_ph = reply_message.photo
            reply_message_doc = reply_message.document
            if reply_message_ph:
                prompt = await self.tagger(file=reply_message_ph[-1])
                return await bot.reply_to(message, text=prompt, parse_mode="MarkdownV2")
            if reply_message_doc:
                prompt = await self.tagger(file=reply_message_doc)
                return await bot.reply_to(message, text=prompt, parse_mode="MarkdownV2")
            return await bot.reply_to(message, text="🥛 Not image")

        try:
            await bot.polling(
                non_stop=True, allowed_updates=util.update_types, skip_pending=True
            )
        except ApiTelegramException as e:
            logger.opt(exception=e).exception("ApiTelegramException")
        except Exception as e:
            logger.exception(e)
