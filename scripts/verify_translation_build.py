"""Check a merged Russian catalog with GNU gettext and compare MO semantics."""
import argparse
import gettext
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools/python-packages"))
import polib


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Merged edition PO")
    parser.add_argument("mo", type=Path, help="MO from compile_translations.py")
    args = parser.parse_args()
    source, mo = args.source.resolve(), args.mo.resolve()
    msgfmt = ROOT / ".tools/gettext-1.0/bin/msgfmt.exe"
    pot = ROOT / "audits/localization/current-source.pot"
    if not msgfmt.is_file() or not pot.is_file():
        raise SystemExit("Restore gettext tools and run scripts/extract_translations.ps1 first")
    report_dir = ROOT / "audits/localization"
    work = ROOT / ".build/localization"
    work.mkdir(parents=True, exist_ok=True)
    gnu_mo = work / "gnu-verified-ru.mo"
    checked = subprocess.run([str(msgfmt), "--check", "--check-format", "--statistics",
                              "--output-file", str(gnu_mo), str(source)],
                             capture_output=True, encoding="utf-8", errors="replace")
    (report_dir / "edition-msgfmt.log").write_text(checked.stdout + checked.stderr, encoding="utf-8")
    report = {"source": str(source), "source_sha256": digest(source), "mo": str(mo),
              "mo_sha256": digest(mo), "msgfmt_exit": checked.returncode,
              "format_check": "PASS" if checked.returncode == 0 else "FAIL",
              "runtime_layout": "UNKNOWN", "human_review": False}
    if checked.returncode == 0:
        with gnu_mo.open("rb") as stream:
            gnu = gettext.GNUTranslations(stream)
        with mo.open("rb") as stream:
            custom = gettext.GNUTranslations(stream)
        # Header order, generated dates and charset case may differ between
        # writers. Compare every message/context/plural key and separately check
        # the metadata that controls how translations are interpreted.
        gnu_messages = {key: value for key, value in gnu._catalog.items() if key != ""}
        custom_messages = {key: value for key, value in custom._catalog.items() if key != ""}
        message_match = gnu_messages == custom_messages
        language_match = gnu.info().get("language") == custom.info().get("language") == "ru"
        charset_match = gnu.charset().lower().replace("-", "") == custom.charset().lower().replace("-", "") == "utf8"
        plural_match = all(gnu.plural(n) == custom.plural(n) for n in range(1001))
        report["mo_message_entries"] = len(custom_messages)
        report["mo_metadata_checks"] = {"language": language_match, "charset": charset_match,
                                         "plural_evaluation_0_to_1000": plural_match}
        report["mo_semantic_equivalence"] = "PASS" if all((message_match, language_match,
                                                           charset_match, plural_match)) else "FAIL"
        po = polib.pofile(str(source))
        index = {(e.msgctxt or "", e.msgid): e for e in po if not e.obsolete}
        template = polib.pofile(str(pot))
        active = [e for e in template if not e.obsolete and e.msgid]
        missing = [e for e in active if (e.msgctxt or "", e.msgid) not in index]
        blank = [e for e in active if (e.msgctxt or "", e.msgid) in index and
                 not index[(e.msgctxt or "", e.msgid)].translated()]
        report.update(current_source_keys=len(active), missing_keys=len(missing),
                      untranslated_current_keys=len(blank),
                      translated_current_keys=len(active) - len(missing) - len(blank),
                      menu_new_game=custom.pgettext("Main Menu", "<N|n>ew Game"))
    (report_dir / "edition-translation-validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if checked.returncode or report.get("mo_semantic_equivalence") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
