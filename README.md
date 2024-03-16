# Tagger Bot

![Ruff](https://github.com/LlmKira/tagger-bot/actions/workflows/ruff.yml/badge.svg)

> [!IMPORTANT]
> Deploy With [wd14-tagger-server](https://github.com/LlmKira/wd14-tagger-server)

## Project Description

Tag Picture In Telegram Group.

## Usage

```shell
git clone https://github.com/LlmKira/tagger-bot
cd tagger-bot
cp .env.exp .env
nano .env

```

### Run In Terminal

```shell
pip install pdm
pdm install
pdm run main.py
```

### Run In BackGround

```shell
pm2 start pm2.json
pm2 status
pm2 stop pm2.json

```
