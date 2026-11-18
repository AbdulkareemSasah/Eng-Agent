"""Product profiles and product resolution (plan 0008 T1; spec 0008 AC2, section 4.1)."""

import ast
from pathlib import Path

import pytest

from eng_harness.adapters.csi import products

SRC = Path(__file__).resolve().parents[3] / "src" / "eng_harness"
_NAMES = frozenset({"ETABS", "SAFE"})  # the product names a shared module must not branch on
_EXTENSIONS = frozenset({".EDB", ".FDB"})  # the model extensions that identify a product


@pytest.mark.parametrize(
    ("model", "product"),
    [
        ("model.EDB", "ETABS"),
        ("model.edb", "ETABS"),
        ("C:\\Projects\\Tower\\tower.EDB", "ETABS"),
        ("footing.FDB", "SAFE"),
        ("/data/footing.fdb", "SAFE"),
        ("C:\\Projects\\Tower\\raft.Fdb", "SAFE"),
    ],
)
def test_product_by_extension(model: str, product: str) -> None:
    """AC2: `.FDB` is SAFE and `.EDB` is ETABS, whatever the case and the path separator."""
    found = products.product_of_model(model)
    assert found.name == product
    assert found is products.profile(product)
    assert found.model_extensions == ((".EDB",) if product == "ETABS" else (".FDB",))
    assert products.product_of_model(model, product) is found  # the server of the same product


def _product_literal(node: ast.expr | None) -> bool:
    """A product name, or a collection holding one."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value in _NAMES
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return any(_product_literal(item) for item in node.elts)
    return False


def _hard_wired(node: ast.AST) -> ast.expr | None:
    """The value given to a `product`: an assignment, a keyword argument."""
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "product" for t in node.targets):
        return node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "product":
        return node.value
    if isinstance(node, ast.keyword) and node.arg == "product":
        return node.value
    return None


def _default_of_product(node: ast.arguments) -> ast.expr | None:
    """The default of a parameter named `product`."""
    positional = [a.arg for a in (*node.posonlyargs, *node.args)]
    padded = [None] * (len(positional) - len(node.defaults)) + list(node.defaults)
    pairs = [
        *zip(positional, padded, strict=True),
        *zip((a.arg for a in node.kwonlyargs), node.kw_defaults, strict=True),
    ]
    return next((default for name, default in pairs if name == "product"), None)


def _selects(node: ast.AST) -> bool:
    """True when the node selects by a product name or a model extension."""
    if isinstance(node, ast.Compare):
        return any(_product_literal(n) for n in (node.left, *node.comparators))
    if isinstance(node, ast.MatchValue):
        return _product_literal(node.value)
    if isinstance(node, ast.Dict):
        return any(_product_literal(key) for key in node.keys)
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value.upper() in _EXTENSIONS
    return _product_literal(_hard_wired(node))


def branches(source: str) -> list[int]:
    """The line numbers where `source` selects by a product name or a model extension.

    A branch is a comparison or membership test with a product name, a `match` case on one, a mapping keyed by one, a
    model extension literal, or a hard-wired `product` (an assignment, a keyword or a default). `products=` on a tool
    descriptor lists who serves a tool: data, not a branch.
    """
    lines: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.arguments):
            default = _default_of_product(node)
            if default is not None and _product_literal(default):
                lines.add(default.lineno)
        elif hasattr(node, "lineno") and _selects(node):
            lines.add(node.lineno)
    return sorted(lines)


def _shared_modules() -> list[Path]:
    """Every module that is not a product's own: the adapters outside `products/`, and the server code."""
    adapters = [p for p in (SRC / "adapters").rglob("*.py") if "products" not in p.relative_to(SRC / "adapters").parts]
    return sorted([*adapters, *(SRC / "servers").rglob("*.py")])


def test_no_product_branches_in_shared() -> None:
    """AC2: a shared module never branches on a product name, it asks the profile (no exclusions)."""
    modules = _shared_modules()
    assert len(modules) > 20
    found = [
        f"{path.relative_to(SRC)}:{line}" for path in modules for line in branches(path.read_text(encoding="utf-8"))
    ]
    assert found == []
