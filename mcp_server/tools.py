"""Ограниченный арифметический AST: без eval, вызовов и доступа к объектам."""
import ast
import operator
from decimal import Decimal, DecimalException, localcontext

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}


def calculate(expression: str) -> dict:
    if not isinstance(expression, str) or not 1 <= len(expression) <= 200:
        raise ValueError('Выражение должно содержать от 1 до 200 символов')
    expression = expression.strip()
    try:
        tree = ast.parse(expression, mode='eval')
        if len(list(ast.walk(tree))) > 80:
            raise ValueError('Слишком сложное выражение')

        def visit(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                result = Decimal(ast.get_source_segment(expression, node).replace('_', ''))
            elif isinstance(node, ast.BinOp) and type(node.op) in OPS:
                result = OPS[type(node.op)](visit(node.left), visit(node.right))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            else:
                raise ValueError('Разрешены только числа, скобки и + - * / // %')
            if not result.is_finite() or abs(result) > Decimal('1e15'):
                raise ValueError('Результат выходит за пределы ±10^15')
            return result

        with localcontext() as ctx:
            ctx.prec = 28
            result = visit(tree.body)
        return {'expression': expression, 'result': format(result, 'f')}
    except (SyntaxError, DecimalException, OverflowError, RecursionError):
        raise ValueError('Некорректное выражение или деление на ноль') from None
