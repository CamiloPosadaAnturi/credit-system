"""Compile the .po files into .mo without needing the gettext binaries.

    python scripts/compile_messages.py

Run it after editing locale/<language>/LC_MESSAGES/django.po so the
application picks up the new translations.
"""
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    import polib

    for po_path in (BASE_DIR / "locale").rglob("*.po"):
        catalog = polib.pofile(str(po_path))
        mo_path = po_path.with_suffix(".mo")
        catalog.save_as_mofile(str(mo_path))
        translated = len([entry for entry in catalog if entry.msgstr])
        print(f"{mo_path.relative_to(BASE_DIR)}: {translated}/{len(catalog)} translated")


if __name__ == "__main__":
    main()
