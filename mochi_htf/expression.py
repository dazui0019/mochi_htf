from __future__ import annotations

import ast
from typing import Any


class ExpressionError(ValueError):
    """Raised when a verify expression is unsafe or invalid."""


_ALLOWED_NODES = {
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
}

_ALLOWED_NAME = {"result"}


def _validate_ast(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            raise ExpressionError(f"Unsupported syntax: {type(node).__name__}")

        if isinstance(node, ast.Name) and node.id not in _ALLOWED_NAME:
            raise ExpressionError(f"Unsupported variable: {node.id}")

        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (str, int, float, bool, type(None))):
                raise ExpressionError("Unsupported constant type")


def evaluate_expression(expr: str, result: Any) -> bool:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Invalid expression: {exc.msg}") from exc

    _validate_ast(tree)

    try:
        value = eval(compile(tree, "<verify_expr>", "eval"), {"__builtins__": {}}, {"result": result})
    except Exception as exc:  # noqa: BLE001
        raise ExpressionError(f"Expression evaluation error: {exc}") from exc

    if not isinstance(value, bool):
        raise ExpressionError("Expression result must be bool")

    return value
