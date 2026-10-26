"""HTTP MCP integration checks in a temporary DB; no API keys required."""
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from telegram_bot.mcp_client import connect

ROOT = Path(__file__).resolve().parent


async def wait_ready(url, proc):
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError('MCP server exited')
        try:
            async with connect(url) as client:
                return await client.tools()
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.1)
    raise RuntimeError(f'MCP server readiness timeout: {last_error!r}')


async def check(url):
    async with connect(url) as client:
        tools = await client.tools()
        assert len(tools) == 7
        assert all(t['parameters']['type'] == 'object' for t in tools)
        listing = await client.call('list_products', {'limit': 100})
        assert listing['total'] == 100 and len(listing['products']) == 100
        assert (await client.call('find_product', {'name': 'ПЕРЧАТ'}))['total'] == 10
        assert len((await client.call('list_categories', {}))['categories']) == 10
        filtered = await client.call('find_products_by_category', {'category': 'Защита рук', 'max_price': 120})
        assert filtered['total'] == 4
        added = await client.call('add_product', {'name': 'Перчатки проверка', 'category': 'Защита рук', 'price': 125.50})
        assert added['created'] and added['product']['id'] == 101
        assert (await client.call('find_product', {'name': 'Перчатки проверка'}))['total'] == 1
        assert (await client.call('calculate', {'expression': '0.1+0.2'}))['result'] == '0.3'
        quote = await client.call('quote_order', {'items': [{'product_id': 41, 'quantity': 10}, {'product_id': 51, 'quantity': 2}], 'discount_percent': 5})
        assert quote['total'] == '1710.00'
        invalid = [
            ('calculate', {'expression': '__import__("os")'}),
            ('add_product', {'name': 'X', 'category': 'Y', 'price': -1}),
            ('quote_order', {'items': [{'product_id': 1, 'quantity': 1.5}]}),
            ('quote_order', {'items': [{'product_id': 999, 'quantity': 1}]}),
            ('find_product', {}),
        ]
        for name, args in invalid:
            assert 'error' in await client.call(name, args), (name, args)
        print(json.dumps({'passed': True, 'tools': [t['name'] for t in tools], 'http_checks': 14,
                          'order_total': quote['total']}, ensure_ascii=False), flush=True)


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'PRODUCTS_DB': str(Path(tmp) / 'test.db'), 'MCP_PORT': str(port)}
        with (Path(tmp) / 'server.log').open('w') as log:
            proc = subprocess.Popen([sys.executable, '-m', 'mcp_server.server'], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                url = f'http://127.0.0.1:{port}/mcp'
                await wait_ready(url, proc)
                await check(url)
            finally:
                proc.terminate()
                proc.wait(timeout=10)
                if proc.returncode not in (0, -15):
                    print((Path(tmp) / 'server.log').read_text()[-2000:])


if __name__ == '__main__':
    asyncio.run(main())
