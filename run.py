"""Тот же агент через CLI: python run.py --ask 'Найди каски'."""
import argparse
import asyncio
from openai import AsyncOpenAI
from telegram_bot.agent import Agent
from telegram_bot.config import settings, setup_logging


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ask', required=True)
    args = parser.parse_args()
    config = settings()
    async with AsyncOpenAI(api_key=config.api_key, base_url=config.base_url, timeout=60, max_retries=1) as api:
        print(await Agent(api, config.mcp_url, config.model).answer('cli', args.ask))


if __name__ == '__main__':
    setup_logging()
    asyncio.run(main())
