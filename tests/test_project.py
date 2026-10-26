import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from mcp_server.db import Catalog
from mcp_server.tools import calculate
from telegram_bot.agent import Agent


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'products.db'
        self.catalog = Catalog(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_once_and_categories(self):
        self.assertEqual(self.catalog.search()['total'], 100)
        Catalog(self.path)
        self.assertEqual(self.catalog.search()['total'], 100)
        self.assertEqual(len(self.catalog.categories()['categories']), 10)

    def test_unicode_search_and_no_sql_or_wildcard_injection(self):
        self.assertEqual(self.catalog.search(name='ПЕРЧАТ')['total'], 10)
        self.assertEqual(self.catalog.search(name="' OR 1=1 --")['total'], 0)
        self.assertEqual(self.catalog.search(name='%')['total'], 0)

    def test_pagination(self):
        one = self.catalog.search(limit=7)
        two = self.catalog.search(limit=7, offset=one['next_offset'])
        self.assertFalse({p['id'] for p in one['products']} & {p['id'] for p in two['products']})
        self.assertIsNone(self.catalog.search(limit=100)['next_offset'])

    def test_category_and_price_bounds(self):
        result = self.catalog.search(category='ЗАЩИТА РУК', min_price=100, max_price=120)
        self.assertEqual([p['price'] for p in result['products']], [100, 110, 120])

    def test_add_persists_and_duplicate_is_idempotent(self):
        first = self.catalog.add('Перчатки тест', 'Защита рук', 125.50)
        self.assertTrue(first['created'])
        self.assertFalse(self.catalog.add('ПЕРЧАТКИ ТЕСТ', 'ЗАЩИТА РУК', 125.50)['created'])
        self.assertEqual(Catalog(self.path).search()['total'], 101)
        self.assertEqual(Catalog(self.path).search(name='Перчатки тест')['products'][0]['price'], 125.50)
        with self.assertRaises(ValueError):
            self.catalog.add('Перчатки тест', 'Защита рук', 200)

    def test_bad_inputs(self):
        for value in [0, -1, float('nan'), float('inf'), 1.111, 10000001, True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.catalog.add('Товар', 'Категория', value)
        for name in ['', '  ', 'X' * 151, 'X\nY']:
            with self.assertRaises(ValueError):
                self.catalog.add(name, 'Категория', 100)
        with self.assertRaises(ValueError):
            self.catalog.search(limit=101)
        with self.assertRaises(ValueError):
            self.catalog.search(offset=-1)
        with self.assertRaises(ValueError):
            self.catalog.search(min_price=100, max_price=50)

    def test_quote_decimal_and_rounding(self):
        result = self.catalog.quote([{'product_id': 41, 'quantity': 10}, {'product_id': 51, 'quantity': 2}], 5)
        self.assertEqual(result['subtotal'], '1800.00')
        self.assertEqual(result['discount_amount'], '90.00')
        self.assertEqual(result['total'], '1710.00')
        p = self.catalog.add('Точность', 'Тест', 0.10)['product']
        self.assertEqual(self.catalog.quote([{'product_id': p['id'], 'quantity': 3}])['total'], '0.30')

    def test_quote_rejects_missing_ids_and_invalid_quantities(self):
        for items, discount in [([], 0), ([{'product_id': 99999, 'quantity': 1}], 0),
                                 ([{'product_id': 1, 'quantity': 0}], 0),
                                 ([{'product_id': 1, 'quantity': 1.5}], 0),
                                 ([{'product_id': 1, 'quantity': True}], 0),
                                 ([{'product_id': 1, 'quantity': 1}] * 2, 0),
                                 ([{'product_id': 1, 'quantity': 1}], 31),
                                 ([{'product_id': 1, 'quantity': 1}], float('nan'))]:
            with self.subTest(items=items, discount=discount), self.assertRaises(ValueError):
                self.catalog.quote(items, discount)


class CalculatorTests(unittest.TestCase):
    def test_decimal_arithmetic(self):
        self.assertEqual(calculate('(2400 * 5 + 90 * 20) * 0.95')['result'], '13110.00')
        self.assertEqual(calculate('0.1 + 0.2')['result'], '0.3')
        self.assertEqual(calculate('-5 + 2')['result'], '-3')

    def test_rejects_code_and_excessive_work(self):
        for expr in ['__import__("os").system("whoami")', '(1).__class__', '[1][0]',
                     '2**1000000000', 'True + 1', '1/0', '1e999', '9'*201, '1+'*45+'1']:
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                calculate(expr)


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_reset_is_scoped(self):
        agent = Agent(AsyncMock(), 'http://localhost/mcp', 'test')
        agent.history['a'] = [{'role': 'user', 'content': 'a'}]
        agent.history['b'] = [{'role': 'user', 'content': 'b'}]
        await agent.reset('a')
        self.assertNotIn('a', agent.history)
        self.assertIn('b', agent.history)

    async def test_reject_oversized_text_before_api(self):
        api = AsyncMock()
        agent = Agent(api, '', '')
        with self.assertRaises(ValueError):
            await agent.answer('u', 'X'*6001)
        api.responses.create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
