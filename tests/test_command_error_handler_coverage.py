"""Integration checks for the shared command/view/modal error handling in loaded cogs."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COG_ROOTS = (ROOT / "cogs", ROOT / "cogs_test")
HELPERS_ROOT = ROOT / "helpers"
EXCLUDED_MODULES = {
    "cogs.social.anilist_site_embed",
    "cogs.social.feedback",
}
ALLOWED_LOCAL_ERROR_CLASSES = {
    "cogs.customization.custom_roles": {"LoggedView"},
    "helpers.command_error_handler": {"FeedbackAwareView", "FeedbackAwareModal"},
}


def _python_modules(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != "__init__.py")


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _shared_handler_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "helpers.command_error_handler":
            imports.update(alias.asname or alias.name for alias in node.names)
    return imports


def _shared_handler_references(path: Path) -> set[str]:
    symbols = {
        "FeedbackAwareView", "FeedbackAwareModal", "application_error_message",
        "prefix_error_message", "FEEDBACK_ERROR_GUIDANCE", "handle_application_command_error",
        "handle_prefix_command_error", "handle_component_error", "handle_modal_error",
        "is_excluded_command",
    }
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in symbols}


def _component_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "discord.ui":
            for alias in node.names:
                if alias.name in {"View", "Modal"}:
                    aliases[alias.asname or alias.name] = f"discord.ui.{alias.name}"
        elif node.module == "discord":
            for alias in node.names:
                if alias.name == "ui":
                    prefix = alias.asname or alias.name
                    aliases[f"{prefix}.View"] = "discord.ui.View"
                    aliases[f"{prefix}.Modal"] = "discord.ui.Modal"
    return aliases


def _error_hooks(path: Path) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "cog_app_command_error"
    ]


def _component_classes(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _component_aliases(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = _dotted_name(base)
            name = aliases.get(name, name)
            if name in {"discord.ui.View", "discord.ui.Modal", "FeedbackAwareView", "FeedbackAwareModal"}:
                found.append((node.name, name))
    return found


def _bare_component_constructors(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _component_aliases(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            name = aliases.get(name, name)
            if name in {"discord.ui.View", "discord.ui.Modal"}:
                found.append(name)
    return found


class CommandErrorHandlerCoverageTests(unittest.TestCase):
    def test_bot_registers_global_slash_and_prefix_error_callbacks(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("@bot.tree.error", source)
        self.assertIn("await handle_application_command_error(interaction, error)", source)
        self.assertIn("async def on_command_error(ctx, error)", source)
        self.assertIn("await handle_prefix_command_error(ctx, error)", source)

    def test_loaded_cogs_and_helpers_use_shared_view_and_modal_errors(self):
        paths = [path for root in (*COG_ROOTS, HELPERS_ROOT) for path in _python_modules(root)]
        self.assertTrue(paths, "No loaded cog/helper modules were discovered")
        helper_source = (ROOT / "helpers" / "command_error_handler.py").read_text(encoding="utf-8")
        self.assertIn("EXCLUDED_COG_MODULES", helper_source)
        self.assertIn("class FeedbackAwareView", helper_source)
        self.assertIn("class FeedbackAwareModal", helper_source)

        for path in paths:
            module = _module_name(path)
            with self.subTest(module=module):
                hooks = _error_hooks(path)
                if hooks and module not in EXCLUDED_MODULES:
                    self.assertIn("helpers.command_error_handler", path.read_text(encoding="utf-8"))

                if module != "helpers.command_error_handler":
                    references = _shared_handler_references(path)
                    imports = _shared_handler_imports(path)
                    self.assertEqual(
                        references - imports, set(),
                        f"{module} references shared handler names without importing them",
                    )

                if module in EXCLUDED_MODULES:
                    continue
                for class_name, base in _component_classes(path):
                    if base in {"discord.ui.View", "discord.ui.Modal"}:
                        self.assertIn(class_name, ALLOWED_LOCAL_ERROR_CLASSES.get(module, set()))
                    else:
                        self.assertIn(base, {"FeedbackAwareView", "FeedbackAwareModal"})
                        self.assertIn(base, _shared_handler_imports(path))
                self.assertEqual(
                    _bare_component_constructors(path), [],
                    f"{module} instantiates a bare View/Modal and bypasses shared component handling",
                )

    def test_only_anilist_site_embed_and_feedback_are_excluded(self):
        helper_source = (ROOT / "helpers" / "command_error_handler.py").read_text(encoding="utf-8")
        for module in EXCLUDED_MODULES:
            with self.subTest(module=module):
                self.assertTrue((ROOT / Path(*module.split("."))).with_suffix(".py").is_file())
                self.assertIn(f'"{module}"', helper_source)

    def test_loaded_cog_and_helper_sources_parse(self):
        for path in [path for root in (*COG_ROOTS, HELPERS_ROOT) for path in _python_modules(root)]:
            with self.subTest(path=str(path.relative_to(ROOT))):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

