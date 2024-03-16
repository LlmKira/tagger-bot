# -*- coding: utf-8 -*-
# @Time    : 2024/1/21 上午10:49
# @Author  : sudoskys
# @File    : wdtagger.py
# @Software: PyCharm

import requests
from dotenv import load_dotenv
from loguru import logger
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WdTagger(BaseSettings):
    """
    代理设置
    """

    wd_api_endpoint: str = "http://127.0.0.1:10011/upload"
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @model_validator(mode="after")
    def bot_validator(self):
        try:
            resp = requests.head(self.wd_api_endpoint)
            if resp.headers.get("server") != "uvicorn":
                logger.warning(
                    f"wd_api_endpoint {self.wd_api_endpoint} request success, but server is not uvicorn"
                )
            else:
                logger.success(f"wd_api_endpoint {self.wd_api_endpoint} is available")
        except Exception as e:
            logger.warning(
                f"wd_api_endpoint {self.wd_api_endpoint} is not available, please check the server is running {e}"
            )
            raise e


load_dotenv()
TaggerSetting = WdTagger()
