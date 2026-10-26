"""Telegram-интерфейс. Из корня: .venv/bin/python -m telegram_bot.bot."""
import sys
from pathlib import Path
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from openai import AsyncOpenAI
from telegram_bot.agent import Agent
from telegram_bot.config import settings, setup_logging, instance_lock
from telegram_bot.mcp_client import connect

HELP = """VPf08 — учебный магазин спецодежды и СИЗ.
Умею искать и добавлять товары, показывать категории и считать стоимость заявки.
Все цены и товары демонстрационные.

Примеры:
• Покажи все товары
• Найди перчатки
• Покажи товары категории Защита рук до 150 рублей
• Добавь товар Перчатки Тест, категория Защита рук, цена 125 рублей
• Рассчитай 10 штук товара ID 41 и 2 штуки ID 51 со скидкой 5%
• Сколько будет (2400 * 5 + 90 * 20) * 0.95?

/help — справка
/reset — очистить контекст диалога (каталог сохраняется)
История хранится в памяти процесса до перезапуска."""


def create_router(agent, allowed_ids=frozenset()):
    router = Router()
    router.message.filter(F.chat.type == 'private')
    if allowed_ids:
        router.message.filter(F.from_user.id.in_(allowed_ids))

    @router.message(CommandStart())
    @router.message(Command('help'))
    async def start(message: Message):
        await message.answer(HELP)

    @router.message(Command('reset'))
    async def reset(message: Message):
        await agent.reset(str(message.from_user.id))
        await message.answer('Контекст очищен. Каталог сохранён.')

    @router.message(F.text)
    async def question(message: Message):
        if message.text.startswith('/'):
            await message.answer(HELP)
            return
        try:
            answer = await agent.answer(str(message.from_user.id), message.text)
        except Exception as exc:
            logging.warning('answer_error=%s', type(exc).__name__)
            await message.answer(str(exc) if isinstance(exc, ValueError) else
                                 'Не удалось завершить запрос. Проверьте MCP-сервер, сеть и доступ к API. Если добавляли товар, сначала проверьте каталог.')
            return
        for offset in range(0, len(answer), 4000):
            await message.answer(answer[offset:offset + 4000])

    @router.message()
    async def unsupported(message: Message):
        await message.answer('Отправьте текстовый запрос или /help.')

    return router


async def main():
    config = settings()
    with instance_lock(config.token):
        async with connect(config.mcp_url) as mcp:
            await mcp.tools()
        async with AsyncOpenAI(api_key=config.api_key, base_url=config.base_url,
                               timeout=60, max_retries=1) as api, Bot(
                config.token, default=DefaultBotProperties(link_preview_is_disabled=True)) as bot:
            if (await bot.get_webhook_info()).url:
                raise ValueError('У бота есть webhook. Для polling отключите его отдельно.')
            me = await bot.get_me()
            logging.info('VPf08 started @%s model=%s', me.username, config.model)
            dp = Dispatcher()
            dp.include_router(create_router(Agent(api, config.mcp_url, config.model), config.allowed_ids))
            await dp.start_polling(bot, allowed_updates=['message'])


if __name__ == '__main__':
    setup_logging()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as exc:
        print(str(exc) if isinstance(exc, ValueError) else f'Ошибка запуска: {type(exc).__name__}')
        raise SystemExit(1)
