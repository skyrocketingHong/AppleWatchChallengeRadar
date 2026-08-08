"""Predicate DSL parser (AST-lite).

Supported syntax: comparison operators >= > <= < == !=, boolean AND/OR/&&/||,
and parentheses. This is intentionally NOT a full NSExpression/NSPredicate
compiler; unknown tokens produce a parse error so callers can fall back to
recording the raw predicate as unparsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Union

NUMBER_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*")

OPS = (">=", "<=", "==", "!=", ">", "<")
AND_WORDS = {"AND", "&&", "and"}
OR_WORDS = {"OR", "||", "or"}
END_WORDS = AND_WORDS | OR_WORDS


@dataclass
class Comparison:
    metric: str
    op: str
    value: float


@dataclass
class Logical:
    op: str  # AND | OR
    children: list["Expr"] = field(default_factory=list)


Expr = Union[Comparison, Logical]


class ParseError(ValueError):
    pass


@dataclass
class ParseResult:
    ok: bool
    ast: Expr | None = None
    error: str | None = None
    raw: str = ""


class _Tokenizer:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def peek(self) -> str | None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1
        if self.pos >= len(self.text):
            return None
        rest = self.text[self.pos:]
        for op in OPS:
            if rest.startswith(op):
                return op
        if rest.startswith("&&"):
            return "&&"
        if rest.startswith("||"):
            return "||"
        if rest[0] in "()":
            return rest[0]
        if IDENT_RE.match(rest):
            return IDENT_RE.match(rest).group(0)  # type: ignore[union-attr]
        if NUMBER_RE.match(rest):
            return NUMBER_RE.match(rest).group(0)  # type: ignore[union-attr]
        raise ParseError(f"unexpected token at offset {self.pos}: {rest[:20]!r}")

    def next(self) -> str | None:
        token = self.peek()
        if token is None:
            return None
        self.pos += len(token)
        return token


class _Parser:
    """Recursive-descent parser for the predicate grammar."""

    def __init__(self, text: str):
        self.tokens = _Tokenizer(text)

    def _expect(self, wanted: str) -> str:
        token = self.tokens.next()
        if token is None:
            raise ParseError(f"expected {wanted!r}, reached end of input")
        if token.upper() != wanted.upper():
            raise ParseError(f"expected {wanted!r}, got {token!r}")
        return token

    def parse(self) -> Expr:
        expr = self._parse_or()
        extra = self.tokens.next()
        if extra is not None:
            raise ParseError(f"unexpected trailing token {extra!r}")
        return expr

    def _parse_or(self) -> Expr:
        children = [self._parse_and()]
        while True:
            token = self.tokens.peek()
            if token is not None and token.upper() in OR_WORDS:
                self.tokens.next()
                children.append(self._parse_and())
            else:
                break
        if len(children) == 1:
            return children[0]
        return Logical(op="OR", children=children)

    def _parse_and(self) -> Expr:
        children = [self._parse_primary()]
        while True:
            token = self.tokens.peek()
            if token is not None and token.upper() in AND_WORDS:
                self.tokens.next()
                children.append(self._parse_primary())
            else:
                break
        if len(children) == 1:
            return children[0]
        return Logical(op="AND", children=children)

    def _parse_primary(self) -> Expr:
        token = self.tokens.next()
        if token is None:
            raise ParseError("expected expression, reached end of input")
        if token == "(":
            expr = self._parse_or()
            self._expect(")")
            return expr
        if token in OPS or token in ("&&", "||", ")"):
            raise ParseError(f"unexpected token {token!r}")
        # token is an identifier (metric name)
        op = self.tokens.next()
        if op not in OPS:
            raise ParseError(f"expected comparison operator after {token!r}, got {op!r}")
        value_token = self.tokens.next()
        if value_token is None or value_token in END_WORDS or value_token in OPS:
            raise ParseError(f"expected numeric value after {token!r}{op!r}, got {value_token!r}")
        try:
            value = float(value_token)
        except ValueError as exc:
            raise ParseError(f"invalid numeric value {value_token!r}") from exc
        return Comparison(metric=token, op=op, value=value)


def parse_predicate(raw: str) -> ParseResult:
    """Parse a predicate string into an AST; never raises."""
    if not raw or not raw.strip():
        return ParseResult(ok=False, error="empty predicate", ast=None, raw=raw)
    try:
        ast = _Parser(raw).parse()
        return ParseResult(ok=True, ast=ast, raw=raw)
    except ParseError as exc:
        return ParseResult(ok=False, error=str(exc), ast=None, raw=raw)


# ---- AST helpers ----

def flatten_comparisons(expr: Expr) -> list[Comparison]:
    """Return all Comparison leaves in order (no logical semantics)."""
    if isinstance(expr, Comparison):
        return [expr]
    result: list[Comparison] = []
    for child in expr.children:
        result.extend(flatten_comparisons(child))
    return result


def type_or_group(expr: Expr) -> tuple[list[int], bool]:
    """If expr is OR-workout.type==N (or a single such comparison), return
    (type_ids, True); otherwise ([], False)."""
    if isinstance(expr, Comparison):
        if expr.metric == "workout.type" and expr.op == "==":
            return [int(expr.value)], True
        return [], False
    if expr.op == "OR":
        ids: list[int] = []
        for child in expr.children:
            if isinstance(child, Comparison) and child.metric == "workout.type" and child.op == "==":
                ids.append(int(child.value))
            else:
                return [], False
        return ids, True
    return [], False