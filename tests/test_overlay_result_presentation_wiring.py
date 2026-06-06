from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OVERLAY_WINDOW = PROJECT_ROOT / "src" / "ludiglot" / "ui" / "overlay_window.py"


def test_result_presentation_adapter_wiring_uses_existing_overlay_methods():
    tree = ast.parse(OVERLAY_WINDOW.read_text(encoding="utf-8"))
    overlay_class = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OverlayWindow"
    )
    defined_methods = {
        node.name for node in overlay_class.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    adapter_call = None
    for node in ast.walk(overlay_class):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "QtResultPresentationAdapter":
            adapter_call = node
            break

    assert adapter_call is not None

    wired_method_names = []
    for keyword in adapter_call.keywords:
        if keyword.arg not in {"show_single_result", "show_multi_result"}:
            continue
        value = keyword.value
        assert isinstance(value, ast.Attribute)
        assert isinstance(value.value, ast.Name)
        assert value.value.id == "self"
        wired_method_names.append(value.attr)

    assert set(wired_method_names) == {"show_and_activate"}
    assert all(method_name in defined_methods for method_name in wired_method_names)
