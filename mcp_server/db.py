"""SQLite-каталог: демонстрационные товары, параметризованные запросы."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from decimal import Decimal, InvalidOperation

GROUPS = [
    ("Спецодежда", "Костюм рабочий летний", 2400, "размер"),
    ("Зимняя спецодежда", "Куртка рабочая утеплённая", 4600, "размер"),
    ("Сигнальная одежда", "Жилет сигнальный", 350, "размер"),
    ("Защитная обувь", "Ботинки защитные с подноском", 2900, "размер"),
    ("Защита рук", "Перчатки рабочие с покрытием", 90, "модель"),
    ("Защита головы", "Каска защитная", 450, "модель"),
    ("Защита глаз", "Очки защитные прозрачные", 180, "модель"),
    ("Защита дыхания", "Респиратор учебный FFP2", 120, "модель"),
    ("Защита слуха", "Наушники противошумные", 800, "модель"),
    ("Защита от падения", "Привязь страховочная учебная", 3900, "модель"),
]


def money(value):
    if isinstance(value, bool):
        raise ValueError("Цена должна быть числом")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not Decimal('0') < amount <= Decimal('10000000'):
            raise ValueError("Цена должна быть больше 0 и не больше 10 000 000 рублей")
        if amount != amount.quantize(Decimal('0.01')):
            raise ValueError("Укажите цену с точностью до копеек")
        return amount.quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError):
        raise ValueError("Некорректная цена") from None


def clean(value, label):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 150:
        raise ValueError(f"{label}: требуется строка длиной 1–150 символов")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{label}: управляющие символы запрещены")
    return value.strip()


class Catalog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL CHECK(price > 0 AND price <= 10000000))")
            con.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
            if not con.execute("SELECT 1 FROM metadata WHERE key='seed_v1'").fetchone():
                if con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
                    rows = []
                    for category, name, price, variant in GROUPS:
                        for i in range(10):
                            number = (38 + i if category == 'Защитная обувь' else 44 + i * 2) if variant == 'размер' else i + 1
                            rows.append((f"{name}, {variant} {number}", category, price + i * (50 if price >= 1000 else 10)))
                    con.executemany("INSERT INTO products(name, category, price) VALUES (?, ?, ?)", rows)
                con.execute("INSERT INTO metadata VALUES ('seed_v1', 'done')")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.create_function("casefold", 1, lambda x: x.casefold())
        try:
            with con:
                yield con
        finally:
            con.close()

    def search(self, name=None, category=None, min_price=None, max_price=None, limit=20, offset=0):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit: целое число от 1 до 100")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset: неотрицательное целое число")
        clauses, args = [], []
        for column, value in [('name', name), ('category', category)]:
            if value is not None:
                clauses.append(f"instr(casefold({column}), ?) > 0")
                args.append(clean(value, column).casefold())
        if min_price is not None:
            clauses.append("price >= ?")
            args.append(float(money(min_price)))
        if max_price is not None:
            clauses.append("price <= ?")
            args.append(float(money(max_price)))
        if min_price is not None and max_price is not None and min_price > max_price:
            raise ValueError("Минимальная цена больше максимальной")
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.connect() as con:
            total = con.execute('SELECT COUNT(*) FROM products' + where, args).fetchone()[0]
            rows = con.execute('SELECT * FROM products' + where + ' ORDER BY id LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
        return {'products': [dict(r) for r in rows], 'total': total, 'offset': offset,
                'next_offset': offset + len(rows) if offset + len(rows) < total else None,
                'currency': 'RUB', 'demo': True}

    def add(self, name, category, price):
        name, category, price = clean(name, 'Название'), clean(category, 'Категория'), money(price)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            existing = con.execute('SELECT * FROM products WHERE casefold(name)=? AND casefold(category)=?', (name.casefold(), category.casefold())).fetchone()
            if existing:
                if Decimal(str(existing['price'])) != price:
                    raise ValueError("Товар уже существует с другой ценой; изменение цен не поддерживается")
                return {'product': dict(existing), 'created': False, 'demo': True}
            cur = con.execute('INSERT INTO products(name, category, price) VALUES (?, ?, ?)', (name, category, float(price)))
            return {'product': {'id': cur.lastrowid, 'name': name, 'category': category, 'price': float(price)}, 'created': True, 'demo': True}

    def categories(self):
        with self.connect() as con:
            rows = con.execute('SELECT category, COUNT(*) AS count FROM products GROUP BY category ORDER BY category').fetchall()
        return {'categories': [dict(r) for r in rows], 'demo': True}

    def quote(self, items, discount_percent=0):
        if not items or len(items) > 50:
            raise ValueError("Нужно от 1 до 50 позиций")
        discount = Decimal(str(discount_percent))
        if not discount.is_finite() or not 0 <= discount <= 30:
            raise ValueError("Скидка должна быть от 0 до 30 процентов")
        lines, seen = [], set()
        with self.connect() as con:
            for item in items:
                pid, qty = item['product_id'], item['quantity']
                if type(pid) is not int or pid <= 0 or type(qty) is not int or not 1 <= qty <= 10000:
                    raise ValueError("ID должен быть положительным целым; количество — целым от 1 до 10000")
                if pid in seen:
                    raise ValueError("Объедините повторяющиеся ID в одну позицию")
                seen.add(pid)
                row = con.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
                if not row:
                    raise ValueError(f"Товар с ID {pid} не найден")
                line = Decimal(str(row['price'])) * qty
                lines.append({'product_id': pid, 'name': row['name'], 'quantity': qty,
                              'unit_price': f"{row['price']:.2f}", 'line_total': f"{line:.2f}"})
        subtotal = sum((Decimal(x['line_total']) for x in lines), Decimal('0'))
        from decimal import ROUND_HALF_UP
        saving = (subtotal * discount / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return {'items': lines, 'subtotal': f"{subtotal:.2f}", 'discount_percent': str(discount),
                'discount_amount': f"{saving:.2f}", 'total': f"{subtotal - saving:.2f}",
                'currency': 'RUB', 'demo': True, 'note': 'Учебный расчёт, без резервирования, доставки и отдельного расчёта налогов'}
