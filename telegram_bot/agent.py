"""Responses function calling: схемы и исполнение приходят из MCP по HTTP."""
import asyncio
import json
import logging
from collections import defaultdict
from telegram_bot.mcp_client import connect
from telegram_bot.prompt import SYSTEM_PROMPT


class Agent:
    def __init__(self, api, mcp_url, model):
        self.api, self.mcp_url, self.model = api, mcp_url, model
        self.history = defaultdict(list)
        self.locks = defaultdict(asyncio.Lock)
        self.last_calls = {}

    async def reset(self, user):
        async with self.locks[user]:
            self.history.pop(user, None)
            self.last_calls.pop(user, None)

    async def answer(self, user, text):
        if not text.strip() or len(text) > 6000:
            raise ValueError('Отправьте вопрос длиной 1–6000 символов')
        async with self.locks[user]:
            messages = [*self.history[user], {'role': 'user', 'content': text}]
            calls = []
            self.last_calls[user] = calls
            async with connect(self.mcp_url) as mcp:
                tools = await mcp.tools()
                for step in range(8):
                    response = await self.api.responses.create(
                        model=self.model, instructions=SYSTEM_PROMPT, input=messages,
                        tools=tools, parallel_tool_calls=False, max_output_tokens=8000, store=False)
                    if response.status != 'completed':
                        raise ValueError('Модель не завершила ответ. Уточните запрос; уже выполненные добавления сохранены.')
                    messages.extend(response.output)
                    functions = [x for x in response.output if x.type == 'function_call']
                    if not functions:
                        answer = response.output_text.strip()
                        if not answer:
                            raise ValueError('Модель не завершила ответ. Повторите вопрос.')
                        self.history[user] = [*self.history[user],
                            {'role': 'user', 'content': text}, {'role': 'assistant', 'content': answer}][-16:]
                        return answer
                    for call in functions:
                        calls.append(call.name)
                        logging.info('tool=%s step=%s', call.name, step + 1)
                        try:
                            arguments = json.loads(call.arguments)
                            result = await mcp.call(call.name, arguments)
                        except json.JSONDecodeError:
                            result = {'error': 'Аргументы должны быть JSON-объектом'}
                        messages.append({'type': 'function_call_output', 'call_id': call.call_id,
                                         'output': json.dumps(result, ensure_ascii=False)})
                raise ValueError('Достигнут лимит шагов. Уточните запрос; уже выполненные добавления сохранены.')
