# -*- coding: utf-8 -*-
# @Time    : 2023/11/18 上午12:18
# @File    : controller.py
# @Software: PyCharm
from io import BytesIO

import telegramify_markdown
from PIL import Image
from asgiref.sync import sync_to_async
from loguru import logger
from novelai_python.tool.image_metadata import ImageMetadata, ImageVerifier
from novelai_python.tool.random_prompt import RandomPromptGenerator
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


def extract_between_multiple_markers(input_list, start_markers, end_markers):
    extracting = False
    extracted_elements = []
    for item in input_list:
        # Check if the item contains any start marker
        if any(start_marker in item for start_marker in start_markers):
            extracting = True
            # continue  # Skip appending the marker itself
        if end_markers:
            if any(end_marker in item for end_marker in end_markers):
                break
        if extracting:
            extracted_elements.append(item)
    return extracted_elements


async def read_a111(file: BytesIO):
    try:
        file.seek(0)
        with Image.open(file) as img:
            parameter = img.info.get("parameters", None)
            if not parameter:
                raise Exception("Empty Parameter")
            if not isinstance(parameter, str):
                parameter = str(parameter)
            parameters = parameter.split(",")
            prompt = extract_between_multiple_markers(
                parameters, [""], ["Negative prompt:", "Steps:"]
            )
            negative_prompt = extract_between_multiple_markers(
                parameters, ["Negative prompt:"], ["Steps:"]
            )
            info = extract_between_multiple_markers(parameters, ["Steps:"], None)
            prompt = ",".join(prompt)
            negative_prompt = ",".join(negative_prompt)
            info = ",".join(info)
            message = f"{prompt}\n{negative_prompt}\n{info}"
            while "\n\n" in message:
                message = message.replace("\n\n", "\n")
    except Exception as e:
        logger.debug(f"Error {e}")
        return []
    else:
        return [f"**📦 Prompt**\n>{message}\n"]


async def read_comfyui(file: BytesIO):
    try:
        file.seek(0)
        with Image.open(file) as img:
            print(img.info)
            parameter = img.info.get("prompt", None)
            if not parameter:
                raise Exception("Empty Parameter")
    except Exception as e:
        logger.debug(f"Error {e}")
        return []
    else:
        return [f"**📦 Comfyui** \n```{parameter}```"]


async def read_novelai(file: BytesIO):
    message = []
    try:
        file.seek(0)
        meta_data = ImageMetadata.load_image(file)
        read_prompt = meta_data.Description
        read_model = meta_data.used_model
        rq_type = meta_data.Comment.request_type
        mode = ""
        if rq_type == "PromptGenerateRequest":
            mode += "Text2Image"
        elif rq_type == "Img2ImgRequest":
            mode += "Img2Img"
        if meta_data.Comment.reference_strength:
            mode += "+VibeTransfer"
    except Exception as e:
        logger.debug(f"Empty metadata {e}")
        return []
    else:
        message.extend(
            [
                f"**📦 Prompt:** `{read_prompt}`" if read_prompt else "",
                f"**📦 Model:** `{read_model.value}`" if read_model else "",
                f"**📦 Source:** `{meta_data.Source}`" if meta_data.Source else "",
            ]
        )
    try:
        file.seek(0)
        is_novelai, has_latent = ImageVerifier().verify(file)
    except Exception:
        logger.debug("Not NovelAI")
    else:
        if is_novelai:
            message.append("**🧊 Signed by NovelAI**")
        if has_latent:
            message.append("**🧊 Find Latent Space**")
    return message


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

    async def tagger(self, file, hidden_long_text=False) -> str:
        raw_file_data = await self.download(file=file)
        if raw_file_data is None:
            return "🥛 Not An image"
        if isinstance(raw_file_data, bytes):
            file_data = BytesIO(raw_file_data)
        else:
            file_data = raw_file_data
        result = await pipeline_tag(trace_id="test", content=file_data)
        infer_message = [
            f"**🥽 AnimeScore: {result.anime_score}**",
            "**🔍 Infer Tags**",
        ]
        novelai_message = await read_novelai(file=file_data)
        comfyui_message = await read_comfyui(file=file_data)
        a111_message = await read_a111(file=file_data)
        # 只能选一个有内容的
        read_message = next(
            filter(lambda msg: msg, [novelai_message, comfyui_message, a111_message]),
            None,
        )
        if read_message and hidden_long_text:
            infer_message.append(f"\n>{result.anime_tags}\n")
        else:
            infer_message.append(f"```{result.anime_tags}```")
        if result.characters:
            infer_message.append(f"**🌟 Characters:** `{','.join(result.characters)}`")
        read_message = read_message or ["🥛 No Metadata"]
        content = infer_message + read_message
        prompt = telegramify_markdown.convert("\n".join(content))
        file_data.close()
        return prompt

    async def run(self):
        logger.info("Bot Start")
        bot = self.bot
        if BotSetting.proxy_address:
            from telebot import asyncio_helper

            asyncio_helper.proxy = BotSetting.proxy_address
            logger.info("Proxy tunnels are being used!")

        @bot.message_handler(
            content_types=["photo", "document"], chat_types=["private"]
        )
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

        @bot.message_handler(
            commands="nsfw", chat_types=["supergroup", "group", "private"]
        )
        async def nsfw(message: types.Message):
            if settings.mode.only_white:
                if message.chat.id not in settings.mode.white_group:
                    return logger.info(f"White List Out {message.chat.id}")
            contents = RandomPromptGenerator(nsfw_enabled=True).generate()
            prompt = formatting.format_text(
                formatting.mbold("🥛 NSFW Prompt"), formatting.mcode(content=contents)
            )
            return await bot.reply_to(message, text=prompt, parse_mode="MarkdownV2")

        @bot.message_handler(
            commands="sfw", chat_types=["supergroup", "group", "private"]
        )
        async def sfw(message: types.Message):
            if settings.mode.only_white:
                if message.chat.id not in settings.mode.white_group:
                    return logger.info(f"White List Out {message.chat.id}")
            contents = RandomPromptGenerator(nsfw_enabled=False).generate()
            prompt = formatting.format_text(
                formatting.mbold("🥛 SFW Prompt"), formatting.mcode(content=contents)
            )
            return await bot.reply_to(message, text=prompt, parse_mode="MarkdownV2")

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
                prompt = await self.tagger(
                    file=reply_message_ph[-1], hidden_long_text=True
                )
                return await bot.reply_to(message, text=prompt, parse_mode="MarkdownV2")
            if reply_message_doc:
                prompt = await self.tagger(
                    file=reply_message_doc, hidden_long_text=True
                )
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
