# -*- coding: utf-8 -*-
# @Time    : 2023/12/10 下午10:33
# @Author  : sudoskys
# @File    : event.py
# @Software: PyCharm
from io import TextIOBase
from typing import Union, IO, Optional

from loguru import logger
from pydantic import BaseModel

from app.utils import WdTaggerSDK
from setting.wdtagger import TaggerSetting


class TaggerResult(BaseModel):
    anime_tags: Optional[str] = ""
    characters: Optional[list] = []


async def pipeline_tag(trace_id, content: Union[IO, TextIOBase]) -> TaggerResult:
    content.seek(0)
    raw_output_wd = await WdTaggerSDK(base_url=TaggerSetting.wd_api_endpoint).upload(
        file=content.read(),
        token="tag",
        general_threshold=0.35,
        character_threshold=0.75,
    )
    tag_result: str = raw_output_wd["sorted_general_strings"]
    character_res: dict = raw_output_wd["character_res"]
    characters = list(character_res.keys())
    logger.info(f"Processed {trace_id},result {tag_result}")
    return TaggerResult(anime_tags=tag_result, characters=characters)
