# -*- coding: utf-8 -*-
# @Time    : 2023/11/18 上午12:51
# @Author  : sudoskys
# @File    : utils.py
# @Software: PyCharm

import aiohttp


def parse_command(command):
    if not command:
        return None, None
    parts = command.split(" ", 1)
    if len(parts) > 1:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], None
    else:
        return None, None


def generate_uuid():
    import shortuuid

    return str(shortuuid.uuid())


class WdTaggerSDK:
    def __init__(self, base_url):
        self.base_url = base_url

    async def upload(
        self, file, token, general_threshold=0.35, character_threshold=0.85
    ):
        if not self.base_url.endswith("/"):
            self.base_url += "/"
        url = self.base_url
        if not self.base_url.endswith("upload/"):
            url = f"{self.base_url}/upload/"
        data = {
            "token": token,
            "file": file,
            "general_threshold": str(general_threshold),
            "character_threshold": str(character_threshold),
        }
        # print(data)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                # response.raise_for_status()
                return await response.json()
