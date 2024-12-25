# -*- coding: utf-8 -*-
# @Time    : 2023/11/18 上午12:18
# @File    : controller.py
# @Software: PyCharm
import json
from io import BytesIO

import json_repair
import telegramify_markdown
from PIL import Image
from loguru import logger
from novelai_python.tool.image_metadata import ImageMetadata, ImageVerifier
from novelai_python.tool.random_prompt import RandomPromptGenerator
from telebot import formatting
from telebot import types
from telebot import util
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_helper import ApiTelegramException
from telebot.asyncio_storage import StateMemoryStorage
from telegramify_markdown import ContentTypes

from app.event import pipeline_tag
from app_conf import settings
from setting.telegrambot import BotSetting

StepCache = StateMemoryStorage()

prompt_generator = RandomPromptGenerator(nsfw_enabled=False)


def cite(
    content: str,
):
    return f">{content}\n"


def code(
    content: str,
    language: str,
):
    return f"```{language}\n{content}\n```"


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
            message = f"{negative_prompt}\n{info}"
            while "\n\n" in message:
                message = message.replace("\n\n", "\n")
            while "\n\n" in prompt:
                prompt = prompt.replace("\n\n", "\n")
    except Exception as e:
        logger.debug(f"Error {e}")
        return []
    else:
        return [
            formatting.mbold("📦 Prompt", escape=False),
            code(content=prompt, language="txt"),
            formatting.mbold("📦 Negative Prompt", escape=False),
            cite(content=negative_prompt),
        ]


async def read_comfyui(file: BytesIO):
    try:
        file.seek(0)
        with Image.open(file) as img:
            parameter = img.info.get("prompt")
            if not parameter:
                raise Exception("Empty Parameter")
            decoded_object = json_repair.loads(parameter)
            return [
                formatting.mbold("📦 Comfyui", escape=False),
                code(content=json.dumps(decoded_object, indent=2), language="txt"),
            ]
    except Exception as e:
        logger.debug(f"Error {e}")
    return []


async def read_novelai(file: BytesIO):
    message = []
    try:
        file.seek(0)
        with Image.open(file) as img:
            meta_data = ImageMetadata.load_image(img)
        rq_type = meta_data.Comment.request_type
        mode = ""
        if rq_type == "PromptGenerateRequest":
            mode += "Text2Image"
        elif rq_type == "Img2ImgRequest":
            mode += "Img2Img"
        if meta_data.Comment.reference_strength:
            mode += "+VibeTransfer"
        if not meta_data.Comment.prompt:
            return []
    except Exception as e:
        logger.debug(f"Empty metadata {e}")
        return []

    message.append(formatting.mbold("📦 NovelAI", escape=False))
    message.append(f"📦 Mode: {mode}")
    if meta_data.Comment.prompt:
        message.append(code(content=meta_data.Comment.prompt, language="txt"))
    if meta_data.Comment.negative_prompt:
        message.append(
            code(
                content=meta_data.Comment.negative_prompt,
                language="txt",
            )
        )
    if meta_data.used_model:
        model_tag = str(meta_data.used_model.value).replace("-", "_")
        message.append(
            formatting.mbold(f"📦 Model #{model_tag}", escape=False),
        )
    if meta_data.Source:
        source_tag = meta_data.Source.lower().replace(" ", "_")
        message.append(
            formatting.mbold(f"📦 Source #{source_tag}", escape=False),
        )
    try:
        file.seek(0)
        with Image.open(file) as img:
            is_novelai, has_latent = ImageVerifier().verify(img)
    except Exception:
        logger.debug("Not NovelAI")
    else:
        if is_novelai:
            message.append(formatting.mbold("🧊 Signed by NovelAI", escape=False))
        if has_latent:
            message.append(formatting.mbold("🧊 Find Latent Space", escape=False))
    message.append(
        code(
            content=meta_data.Comment.model_dump_json(indent=2),
            language="json",
        )
    )
    return message


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
        raw_file_data = await self.download(file=file)
        if raw_file_data is None:
            return "🥛 Not An image"
        if isinstance(raw_file_data, bytes):
            file_data = BytesIO(raw_file_data)
        else:
            file_data = raw_file_data
        # Infer Tags
        infer = await pipeline_tag(trace_id="test", content=file_data)
        infer_message = [
            formatting.mbold("🥛 Tags", escape=False),
        ]
        novelai_message = await read_novelai(file=file_data)
        comfyui_message = await read_comfyui(file=file_data)
        a111_message = await read_a111(file=file_data)
        # 只能选一个有内容的
        read_message = next(
            filter(lambda msg: msg, [novelai_message, comfyui_message, a111_message]),
            None,
        )
        if read_message:
            infer_message.append(cite(content=infer.anime_tags))
        else:
            infer_message.append(code(content=infer.anime_tags, language="txt"))
        if infer.characters:
            infer_message.append(formatting.mbold("🥛 Characters", escape=False))
            infer_message.append(
                code(content=",".join(infer.characters), language="txt")
            )
        if not read_message:
            infer_message.append(formatting.mbold("🥛 No Metadata", escape=False))
        else:
            infer_message.extend(read_message)
        file_data.close()
        return "\n".join(infer_message)

    async def run(self):
        logger.info("Bot Start")
        bot = self.bot
        if BotSetting.proxy_address:
            from telebot import asyncio_helper

            asyncio_helper.proxy = BotSetting.proxy_address
            logger.info("Proxy tunnels are being used!")

        async def reply_markdown(
            chat_id: int,
            text: str,
            reply_to_message_id: int = None,
        ):
            blocks = await telegramify_markdown.telegramify(
                text,
                max_word_count=1000,
            )
            for item in blocks:
                try:
                    if item.content_type == ContentTypes.TEXT:
                        await bot.send_message(
                            chat_id=chat_id,
                            reply_to_message_id=reply_to_message_id,
                            text=item.content,
                            parse_mode="MarkdownV2",
                        )
                    elif item.content_type == ContentTypes.PHOTO:
                        await bot.send_photo(
                            chat_id,
                            (item.file_name, item.file_data),
                            caption=item.caption,
                            reply_to_message_id=reply_to_message_id,
                            parse_mode="MarkdownV2",
                        )
                    elif item.content_type == ContentTypes.FILE:
                        await bot.send_document(
                            chat_id,
                            (item.file_name, item.file_data),
                            caption=item.caption,
                            reply_to_message_id=reply_to_message_id,
                            parse_mode="MarkdownV2",
                        )
                except Exception as e:
                    logger.exception(e)

        @bot.message_handler(
            content_types=["photo", "document"], chat_types=["private"]
        )
        async def listen_pm(message: types.Message):
            if settings.mode.only_white:
                if message.chat.id not in settings.mode.white_group:
                    return logger.info(f"White List Out {message.chat.id}")
            logger.info(f"Report in {message.chat.id} {message.from_user.id}")
            if message.photo:
                prompt = await self.tagger(file=message.photo[-1])
                await reply_markdown(
                    chat_id=message.chat.id, reply_to_message_id=message.id, text=prompt
                )
            if message.document:
                prompt = await self.tagger(file=message.document)
                await reply_markdown(
                    chat_id=message.chat.id, reply_to_message_id=message.id, text=prompt
                )

        @bot.message_handler(
            commands="scene_composition", chat_types=["supergroup", "group", "private"]
        )
        async def scene_composition(message: types.Message):
            if settings.mode.only_white:
                if message.chat.id not in settings.mode.white_group:
                    return logger.info(f"White List Out {message.chat.id}")
            contents = prompt_generator.generate_scene_composition()
            prompt = [formatting.mbold("🥛 Scene Composition Prompt", escape=False)]
            for content in contents:
                prompt.append(f"- `{content}`")
            return await reply_markdown(
                chat_id=message.chat.id,
                reply_to_message_id=message.id,
                text="\n".join(prompt),
            )

        @bot.message_handler(
            commands="scene", chat_types=["supergroup", "group", "private"]
        )
        async def scene(message: types.Message):
            if settings.mode.only_white:
                if message.chat.id not in settings.mode.white_group:
                    return logger.info(f"White List Out {message.chat.id}")
            contents = prompt_generator.generate_scene_tags()
            prompt = [formatting.mbold("🥛 Scene Prompt", escape=False)]
            for content in contents:
                prompt.append(f"- `{content}`")
            return await reply_markdown(
                chat_id=message.chat.id,
                reply_to_message_id=message.id,
                text="\n".join(prompt),
            )

        @bot.message_handler(
            commands="nsfw", chat_types=["supergroup", "group", "private"]
        )
        async def nsfw(message: types.Message):
            if settings.mode.only_white:
                if message.chat.id not in settings.mode.white_group:
                    return logger.info(f"White List Out {message.chat.id}")
            contents = prompt_generator.generate_common_tags(nsfw=True)
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
            contents = prompt_generator.generate_common_tags(nsfw=False)
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
                    text=f"🍡 Please reply a photo with this command, chat id:({message.chat.id})",
                )
            logger.info(f"Report in {message.chat.id} {message.from_user.id}")
            reply_message = message.reply_to_message
            reply_message_ph = reply_message.photo
            reply_message_doc = reply_message.document
            if reply_message_ph:
                prompt = await self.tagger(file=reply_message_ph[-1])
                return await reply_markdown(
                    chat_id=message.chat.id, reply_to_message_id=message.id, text=prompt
                )
            if reply_message_doc:
                prompt = await self.tagger(file=reply_message_doc)
                return await reply_markdown(
                    chat_id=message.chat.id, reply_to_message_id=message.id, text=prompt
                )
            return await bot.reply_to(message, text="🥛 Not image")

        await bot.set_my_commands(
            commands=[
                types.BotCommand("tag", "Tag Image"),
                types.BotCommand("scene", "Generate Scene Prompt"),
                types.BotCommand(
                    "scene_composition", "Generate Scene Composition Prompt"
                ),
                types.BotCommand("nsfw", "Generate NSFW Prompt"),
                types.BotCommand("sfw", "Generate SFW Prompt"),
            ],
        )
        try:
            await bot.polling(
                non_stop=True, allowed_updates=util.update_types, skip_pending=True
            )
        except ApiTelegramException as e:
            logger.opt(exception=e).exception("ApiTelegramException")
        except Exception as e:
            logger.exception(e)
