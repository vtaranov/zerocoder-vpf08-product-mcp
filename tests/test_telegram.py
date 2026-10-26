import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.types import Update, Message, User, Chat
from telegram_bot.bot import create_router


class CaptureSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        return Message(message_id=999, date=datetime.now(timezone.utc),
                       chat=Chat(id=method.chat_id, type='private'), text=method.text)

    async def stream_content(self, *args, **kwargs):
        yield b''


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def feed(self, text, agent, allowed=frozenset(), uid=123, chat_type='private'):
        session = CaptureSession()
        bot = Bot('123456:TEST_TOKEN_NO_NETWORK', session=session)
        dp = Dispatcher()
        dp.include_router(create_router(agent, allowed))
        update = Update(update_id=1, message=Message(
            message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=uid, type=chat_type),
            from_user=User(id=uid, is_bot=False, first_name='Test'), text=text,
            entities=[{'type': 'bot_command', 'offset': 0, 'length': len(text)}] if text.startswith('/') else []))
        await dp.feed_update(bot, update)
        return session.sent

    async def test_start(self):
        agent = AsyncMock()
        sent = await self.feed('/start', agent)
        self.assertIn('VPf08', sent[0].text)
        agent.answer.assert_not_called()

    async def test_long_answer_is_split(self):
        agent = AsyncMock()
        agent.answer.return_value = 'X'*8500
        sent = await self.feed('Все товары', agent)
        self.assertEqual([len(x.text) for x in sent], [4000, 4000, 500])
        agent.answer.assert_awaited_once_with('123', 'Все товары')

    async def test_reset(self):
        agent = AsyncMock()
        sent = await self.feed('/reset', agent)
        agent.reset.assert_awaited_once_with('123')
        self.assertIn('Каталог сохранён', sent[0].text)

    async def test_access_and_groups_filtered(self):
        agent = AsyncMock()
        self.assertEqual(await self.feed('Найди каски', agent, allowed=frozenset({999})), [])
        self.assertEqual(await self.feed('Найди каски', agent, chat_type='group'), [])
        agent.answer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
