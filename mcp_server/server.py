"""product-mcp: официальный MCP SDK, Streamable HTTP на loopback."""
import os
from functools import wraps
from mcp.server.mcpserver.exceptions import ToolError
import sys
from pathlib import Path
from typing import Annotated
from pydantic import BaseModel, Field, ConfigDict
from mcp.server import MCPServer
from dotenv import load_dotenv

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_server.db import Catalog
from mcp_server.tools import calculate as safe_calculate

ROOT = Path(__file__).resolve().parents[1]


class OrderItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: Annotated[int, Field(strict=True, gt=0)]
    quantity: Annotated[int, Field(strict=True, ge=1, le=10000)]


def expected_errors(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
    return wrapped


def create_server(db_path):
    catalog = Catalog(db_path)
    app = MCPServer('product-mcp', instructions='Учебный каталог спецодежды и СИЗ. Все цены и товары демонстрационные.')

    @app.tool()
    @expected_errors
    def list_products(limit: Annotated[int, Field(ge=1, le=100)] = 20, offset: Annotated[int, Field(ge=0)] = 0) -> dict:
        """Список товаров с ID, ценами в рублях и пагинацией; для всех товаров limit=100."""
        return catalog.search(limit=limit, offset=offset)

    @app.tool()
    @expected_errors
    def find_product(name: str) -> dict:
        """Найти товары по части названия, без учёта регистра, включая кириллицу."""
        return catalog.search(name=name, limit=100)

    @app.tool()
    @expected_errors
    def add_product(name: str, category: str, price: Annotated[float, Field(gt=0, le=10000000)]) -> dict:
        """Добавить товар в учебный каталог. Только по явному запросу пользователя с названием, категорией и ценой в RUB."""
        return catalog.add(name, category, price)

    @app.tool()
    @expected_errors
    def calculate(expression: str) -> dict:
        """Безопасный калькулятор: числа, скобки и операции + - * / // %. Без eval."""
        return safe_calculate(expression)

    @app.tool()
    @expected_errors
    def list_categories() -> dict:
        """Показать фактические категории каталога и число товаров в каждой."""
        return catalog.categories()

    @app.tool()
    @expected_errors
    def find_products_by_category(category: str, min_price: float | None = None, max_price: float | None = None) -> dict:
        """Поиск по части категории и необязательному диапазону цен в RUB (границы включены)."""
        return catalog.search(category=category, min_price=min_price, max_price=max_price, limit=100)

    @app.tool()
    @expected_errors
    def quote_order(items: list[OrderItem], discount_percent: Annotated[float, Field(ge=0, le=30)] = 0) -> dict:
        """Учебная стоимость заказа по реальным ID из каталога: количества, скидка 0–30%, итог в RUB. Не оформляет заказ."""
        return catalog.quote([item.model_dump() for item in items], discount_percent)

    return app


def main():
    load_dotenv(ROOT / '.env')
    path = Path(os.getenv('PRODUCTS_DB', 'data/products.db'))
    if not path.is_absolute():
        path = ROOT / path
    app = create_server(path)
    app.run(transport='streamable-http', host='127.0.0.1', port=int(os.getenv('MCP_PORT', '8008')),
            json_response=True, stateless_http=True)


if __name__ == '__main__':
    main()
