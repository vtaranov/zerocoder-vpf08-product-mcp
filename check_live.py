"""Paid OpenAI + real HTTP MCP. Temporary DB; Telegram getMe only, no messages sent."""
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from aiogram import Bot
from openai import AsyncOpenAI
from check_mcp import wait_ready
from telegram_bot.config import settings, setup_logging, ROOT
from telegram_bot.agent import Agent
from telegram_bot.mcp_client import connect


async def main():
    config = settings()
    out = {'checked_at': datetime.now(ZoneInfo('Europe/Moscow')).isoformat(),
           'model': config.model, 'checks': []}
    async with Bot(config.token) as bot:
        me = await bot.get_me()
        out['telegram'] = {'username': me.username, 'get_me': True,
                           'webhook_set': bool((await bot.get_webhook_info()).url)}
    with tempfile.TemporaryDirectory() as tmp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'PRODUCTS_DB': str(Path(tmp) / 'live.db'), 'MCP_PORT': str(port)}
        with (Path(tmp) / 'server.log').open('w') as log:
            proc = subprocess.Popen([sys.executable, '-m', 'mcp_server.server'], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                url = f'http://127.0.0.1:{port}/mcp'
                await wait_ready(url, proc)
                async with AsyncOpenAI(api_key=config.api_key, base_url=config.base_url, timeout=90, max_retries=1) as api:
                    agent = Agent(api, url, config.model)
                    scenarios = [
                        ('categories', 'Какие категории спецодежды и СИЗ есть в каталоге?', ['list_categories']),
                        ('search', 'Найди перчатки, покажи ID и цены.', ['find_product']),
                        ('filter', 'Покажи товары категории Защита рук от 100 до 120 рублей включительно.', ['find_products_by_category']),
                        ('calculate', 'Вычисли (2400 * 5 + 90 * 20) * 0.95.', ['calculate']),
                        ('add', 'Добавь товар Перчатки Нитрил Тест VPf08, категория Защита рук, цена 125.50 рублей.', ['add_product']),
                        ('followup', 'Найди этот добавленный товар и покажи его ID и цену.', ['find_product']),
                        ('quote', 'Рассчитай 10 штук товара ID 41 и 2 штуки товара ID 51 со скидкой 5%.', ['quote_order']),
                        ('clarify', 'Добавь товар каска.', []),
                    ]
                    for name, question, expected in scenarios:
                        print('Checking:', name, flush=True)
                        answer = await agent.answer('live', question)
                        calls = agent.last_calls['live']
                        passed = all(x in calls for x in expected)
                        if name == 'calculate':
                            passed &= '13110' in answer.replace(' ', '').replace('\u00a0', '').replace('\u202f', '')
                        if name == 'quote':
                            passed &= '1710' in answer.replace(' ', '').replace('\u00a0', '').replace('\u202f', '')
                        if name == 'clarify':
                            passed &= 'add_product' not in calls and 'категор' in answer.lower() and 'цен' in answer.lower()
                        out['checks'].append({'name': name, 'question': question, 'answer': answer, 'tools': calls, 'passed': passed})
                        print('Passed:', passed, 'tools:', ','.join(calls), flush=True)
                    async with connect(url) as mcp:
                        await mcp.tools()
                        row = await mcp.call('find_product', {'name': 'Нитрил Тест VPf08'})
                        out['added_verified'] = row['total'] == 1 and row['products'][0]['price'] == 125.5
                        out['final_count'] = (await mcp.call('list_products', {}))['total']
            finally:
                proc.terminate()
                proc.wait(timeout=10)
    dest = ROOT / 'local_checks/live_check.json'
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    assert all(c['passed'] for c in out['checks']) and out['added_verified'] and out['final_count'] == 101
    print('All live checks passed. Saved local_checks/live_check.json', flush=True)


if __name__ == '__main__':
    setup_logging()
    try:
        asyncio.run(main())
    except Exception as exc:
        print('Live check failed:', type(exc).__name__, flush=True)
        raise SystemExit(1)
