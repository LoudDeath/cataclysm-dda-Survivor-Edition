"""Compile the pinned upstream PO, preserving upstream msgfmt -f behavior."""

import argparse
import gettext
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools/python-packages"))
try:
    import polib
except ImportError as exc:
    raise SystemExit("Missing polib 1.2.0; restore edition/polib.lock.json into .tools/python-packages") from exc


def validate_structure(catalog):
    match = re.search(r'nplurals\s*=\s*(\d+)', catalog.metadata.get('Plural-Forms', ''))
    expected = set(range(int(match.group(1)))) if match else None
    for entry in catalog:
        if entry.obsolete:
            continue
        if entry.msgid_plural:
            active = bool(entry.msgstr or any(entry.msgstr_plural.values()))
            if active and (entry.msgstr or expected is None or set(entry.msgstr_plural) != expected or
                           not all(entry.msgstr_plural.values())):
                raise ValueError(f'Incomplete or singular-only plural translation: {(entry.msgctxt, entry.msgid)!r}')
        elif entry.msgstr_plural:
            raise ValueError(f'Unexpected plural slots on singular entry: {entry.msgid!r}')


def write_mo(catalog, output):
    """Serialize GNU MO in linear memory without repeated large bytes copies."""
    validate_structure(catalog)
    messages = [(b"", catalog.metadata_as_entry().msgstr.encode(catalog.encoding))]
    for entry in catalog.translated_entries():
        key = (entry.msgctxt + "\x04") if entry.msgctxt else ""
        key += entry.msgid
        if entry.msgid_plural:
            key += "\x00" + entry.msgid_plural
            value = "\x00".join(entry.msgstr_plural[i] for i in sorted(entry.msgstr_plural))
        else:
            value = entry.msgstr
        messages.append((key.encode(catalog.encoding), value.encode(catalog.encoding)))
    messages.sort(key=lambda pair: pair[0])
    count = len(messages)
    key_offset = 28 + 16 * count
    value_offset = key_offset + sum(len(key) + 1 for key, _ in messages)
    keys, values, key_table, value_table = [], [], [], []
    for key, value in messages:
        key_table.append(struct.pack("<2I", len(key), key_offset))
        value_table.append(struct.pack("<2I", len(value), value_offset))
        keys.append(key + b"\x00")
        values.append(value + b"\x00")
        key_offset += len(key) + 1
        value_offset += len(value) + 1
    header = struct.pack("<7I", 0x950412DE, 0, count, 28, 28 + 8 * count, 0, 0)
    output.write_bytes(b"".join([header, *key_table, *value_table, *keys, *values]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", choices=["ru"], default="ru")
    parser.add_argument("--source", type=Path, help="Optional merged edition PO; upstream PO remains unchanged")
    parser.add_argument("--output", type=Path, help="Optional MO path for isolated verification")
    args = parser.parse_args()
    if polib.__version__ != "1.2.0":
        raise SystemExit("This build expects polib 1.2.0")
    source = (args.source or ROOT / "lang/po" / (args.locale + ".po")).resolve()
    output = (args.output or ROOT / "lang/mo" / args.locale / "LC_MESSAGES/cataclysm-dda.mo").resolve()
    # polib's incremental duplicate check is quadratic for the large CDDA PO.
    # Validate the complete catalog in linear time instead.
    catalog = polib.pofile(str(source))
    keys = set()
    for entry in catalog:
        if entry.obsolete:
            continue
        key = (entry.msgctxt, entry.msgid)
        if key in keys:
            raise SystemExit(f"Duplicate gettext entry: {key!r}")
        keys.add(key)
    fuzzy_count = len(catalog.fuzzy_entries())
    translated_count = len(catalog.translated_entries())
    for entry in catalog:
        entry.flags = [flag for flag in entry.flags if flag != "fuzzy"]
    output.parent.mkdir(parents=True, exist_ok=True)
    write_mo(catalog, output)
    with output.open("rb") as stream:
        validated = gettext.GNUTranslations(stream)
    result = {
        "locale": args.locale,
        "source": source.as_posix(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": output.as_posix(),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "non_fuzzy_translated_entries": translated_count,
        "fuzzy_entries_included_like_upstream": fuzzy_count,
        "mo_parse_status": "PASS",
        "runtime_localization_status": "UNKNOWN",
        "compiler": "polib " + polib.__version__,
        "sample_new_game": validated.pgettext("Main Menu", "<N|n>ew Game"),
    }
    report = ROOT / "audits/localization"
    report.mkdir(parents=True, exist_ok=True)
    (report / "ru-compile.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
