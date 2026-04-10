"""Static analysis tests for UI screen and widget Python files.

Catches NameError-class bugs — referencing a local variable that was never
assigned in the same function — without requiring Kivy or device hardware.

Background: a merge refactored the filter-bar layout in longitudinal_screen.py
from two BoxLayout rows (row1, row2) into a single horizontal BoxLayout, but
left behind stale references to the now-deleted row1 and row2 variables.
Because Kivy screens are constructed at app startup, these NameErrors caused
an instant crash on launch. This test detects that class of mistake statically.
"""

import ast
import builtins
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
UI_ROOT = ROOT / 'app' / 'ui'

# Names that are always available without a local assignment.
_BUILTIN_NAMES: frozenset[str] = frozenset(dir(builtins)) | {
    '__name__', '__file__', '__doc__', '__all__', '__spec__',
    '__annotations__', '__builtins__', '__package__',
}

# Scoping boundaries — do not recurse past these into inner scopes.
_INNER_SCOPE_TYPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _walk_shallow(node):
    """Yield all AST nodes in *node*, but do not descend into inner scopes.

    Inner scope nodes (FunctionDef, Lambda, comprehensions, etc.) are yielded
    once so their names can be recorded as assigned, but their bodies are not
    traversed — references inside a closure are closure captures, not locals.
    """
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _INNER_SCOPE_TYPES):
            yield child  # yield the node itself so its name is captured, but don't recurse
        else:
            yield from _walk_shallow(child)


def _module_level_names(tree: ast.Module) -> frozenset[str]:
    """Names defined at module level (imports, assignments, class/function defs)."""
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != '*':
                    names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
    return frozenset(names)


def _function_assigned_names(func: ast.FunctionDef) -> frozenset[str]:
    """Names that are definitely assigned within *func* (args + any Store/Del)."""
    assigned: set[str] = set()

    # Function parameters
    all_args = (
        func.args.posonlyargs
        + func.args.args
        + func.args.kwonlyargs
    )
    for arg in all_args:
        assigned.add(arg.arg)
    if func.args.vararg:
        assigned.add(func.args.vararg.arg)
    if func.args.kwarg:
        assigned.add(func.args.kwarg.arg)

    # Walk the body without crossing scope boundaries
    for node in _walk_shallow(func):
        if node is func:
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            assigned.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            assigned.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assigned.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != '*':
                    assigned.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                assigned.add(name)

    return frozenset(assigned)


def _function_loaded_names(func: ast.FunctionDef) -> frozenset[str]:
    """Names that are loaded (read) in *func*'s direct body (inner scopes excluded)."""
    loaded: set[str] = set()
    for node in _walk_shallow(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded.add(node.id)
    return frozenset(loaded)


def _top_level_functions(tree: ast.Module):
    """Yield (func_node, extra_known_names) for module-level functions and class methods.

    Nested functions (closures) are intentionally excluded: they reference names
    from the enclosing scope via closure, which are not locally assigned in the
    inner function.  Checking them here would produce false positives.
    """
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node, frozenset()
        elif isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield child, frozenset()


def _find_undefined_refs(filepath: Path) -> list[tuple[str, int, set[str]]]:
    """Return (func_name, line_no, {undef_names}) for every top-level function or
    class method in *filepath* that references a name which is neither locally
    assigned, module-level, nor a Python builtin.

    Nested functions (closures) are excluded from analysis to avoid false positives
    from closure variables captured from the enclosing scope.
    """
    src = filepath.read_text(encoding='utf-8')
    try:
        tree = ast.parse(src, filename=str(filepath))
    except SyntaxError as exc:
        return [(f'<SyntaxError: {exc}>', 0, set())]

    module_names = _module_level_names(tree)
    issues: list[tuple[str, int, set[str]]] = []

    for func, _ in _top_level_functions(tree):
        assigned = _function_assigned_names(func)
        loaded = _function_loaded_names(func)
        undefined = (
            loaded
            - assigned
            - module_names
            - _BUILTIN_NAMES
        )
        # Ignore dunder names — Python/framework internals accessed as globals.
        undefined = {n for n in undefined if not n.startswith('__')}
        if undefined:
            issues.append((func.name, func.lineno, undefined))

    return issues


class TestUIScreenStaticAnalysis(unittest.TestCase):
    """Verify that every function in app/ui/ only references locally-defined names.

    This catches NameError bugs introduced during refactors — e.g. renaming a
    layout variable in one branch while leaving stale references in another.
    """

    def _ui_files(self):
        return sorted(UI_ROOT.rglob('*.py'))

    def test_no_undefined_local_references(self):
        """No function in app/ui/ should load a name that is never assigned there."""
        all_issues: list[str] = []

        for filepath in self._ui_files():
            rel = filepath.relative_to(ROOT)
            issues = _find_undefined_refs(filepath)
            for func_name, lineno, undef in issues:
                names_str = ', '.join(sorted(undef))
                all_issues.append(
                    f'{rel}:{lineno} in {func_name}() — undefined: {names_str}'
                )

        if all_issues:
            self.fail(
                'Potential NameError(s) detected in UI files '
                '(name used before assignment in same function):\n'
                + '\n'.join(f'  {issue}' for issue in all_issues)
            )

    def test_ui_files_have_no_syntax_errors(self):
        """All app/ui/ Python files must parse without SyntaxError."""
        for filepath in self._ui_files():
            rel = filepath.relative_to(ROOT)
            src = filepath.read_text(encoding='utf-8')
            try:
                ast.parse(src, filename=str(filepath))
            except SyntaxError as exc:
                self.fail(f'SyntaxError in {rel}: {exc}')

    def test_checker_catches_undefined_variable(self):
        """Unit-test the checker itself: it must flag a known-bad snippet."""
        bad_src = '''
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button

class MyScreen:
    def build(self):
        row1 = BoxLayout()
        row2.add_widget(Button())  # row2 is never defined
'''
        tree = ast.parse(bad_src)
        module_names = _module_level_names(tree)
        issues = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            assigned = _function_assigned_names(node)
            loaded = _function_loaded_names(node)
            undefined = (loaded - assigned - module_names - _BUILTIN_NAMES)
            undefined = {n for n in undefined if not n.startswith('__')}
            if undefined:
                issues.append((node.name, undefined))
        self.assertTrue(
            any('row2' in undef for _, undef in issues),
            'Checker failed to detect the undefined row2 reference',
        )

    def test_checker_does_not_flag_valid_code(self):
        """The checker must not produce false positives on clean UI-style code."""
        good_src = '''
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.metrics import sp

class MyScreen:
    def build(self):
        root = BoxLayout(orientation="vertical")
        filt = BoxLayout(orientation="horizontal", size_hint=(1, 0.07))
        subjects = sorted({s.get("id", "") for s in []})
        btn = Button(text="Go", size_hint=(0.2, 1), font_size=sp(14))
        btn.bind(on_press=lambda inst: self._go())
        filt.add_widget(btn)
        root.add_widget(filt)
        return root
'''
        tree = ast.parse(good_src)
        module_names = _module_level_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            assigned = _function_assigned_names(node)
            loaded = _function_loaded_names(node)
            undefined = (loaded - assigned - module_names - _BUILTIN_NAMES)
            undefined = {n for n in undefined if not n.startswith('__')}
            self.assertFalse(
                undefined,
                f'False positive(s) in clean code: {undefined}',
            )


if __name__ == '__main__':
    unittest.main()
