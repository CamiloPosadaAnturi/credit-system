"""Extract translatable strings without needing the gettext binaries.

Scans the Python sources for ``_("...")`` and the templates for
``{% trans %}`` / ``{% blocktrans %}`` and writes (or updates) a .po file.

    python scripts/extract_messages.py es

Windows users normally do not have xgettext installed, so this script plus
``scripts/compile_messages.py`` replace ``makemessages``/``compilemessages``.
"""
import ast
import pathlib
import re
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {"venv", ".venv", "migrations", "__pycache__", "staticfiles",
             "node_modules", ".git", ".ruff_cache", "locale", "scripts"}

TRANS_RE = re.compile(r"{%\s*trans\s+(\"([^\"]*)\"|'([^']*)')", re.S)
INLINE_RE = re.compile(r"_\(\s*(\"([^\"]*)\"|'([^']*)')\s*\)")
BLOCK_RE = re.compile(
    r"{%\s*blocktrans(?:late)?[^%]*%}(.*?){%\s*endblocktrans(?:late)?\s*%}", re.S)
PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z_][\w.]*)\s*}}")


def walk(extension: str):
    for path in BASE_DIR.rglob(f"*{extension}"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def from_python(path: pathlib.Path) -> list[str]:
    """Collect every ``_("...")`` call using the AST (handles concatenation)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_" and node.args):
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.append(argument.value)
    return found


def normalize_block(body: str) -> str:
    text = PLACEHOLDER_RE.sub(lambda match: f"%({match.group(1)})s", body)
    return text.strip()


def from_template(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = []
    for match in TRANS_RE.finditer(text):
        found.append(match.group(2) if match.group(2) is not None else match.group(3))
    for match in INLINE_RE.finditer(text):
        found.append(match.group(2) if match.group(2) is not None else match.group(3))
    for match in BLOCK_RE.finditer(text):
        body = match.group(1)
        if "{% plural %}" in body:
            singular, plural = body.split("{% plural %}", 1)
            found.append(normalize_block(singular))
            found.append(normalize_block(plural))
        else:
            found.append(normalize_block(body))
    return found


def collect() -> list[str]:
    messages: dict[str, None] = {}
    for path in walk(".py"):
        for message in from_python(path):
            messages.setdefault(message, None)
    for path in walk(".html"):
        for message in from_template(path):
            messages.setdefault(message, None)
    return [message for message in messages if message.strip()]


def main() -> None:
    language = sys.argv[1] if len(sys.argv) > 1 else "es"
    target = BASE_DIR / "locale" / language / "LC_MESSAGES" / "django.po"
    target.parent.mkdir(parents=True, exist_ok=True)

    import polib

    catalog = polib.pofile(str(target)) if target.exists() else polib.POFile()
    catalog.metadata = {
        "Project-Id-Version": "credit-system 1.0",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Language": language,
    }
    existing = {entry.msgid: entry for entry in catalog}

    added = 0
    for message in collect():
        if message not in existing:
            catalog.append(polib.POEntry(msgid=message, msgstr=""))
            added += 1
    catalog.save(str(target))
    print(f"{len(catalog)} messages in {target} ({added} new)")


if __name__ == "__main__":
    main()
