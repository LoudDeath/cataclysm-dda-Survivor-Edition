"""Run isolated CLI checks on the specified distribution, preserving all player data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import ctypes
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=ROOT)
    parser.add_argument('--all-mods', action='store_true')
    parser.add_argument('--locale', choices=['en', 'ru'], default='en', help='Locale of the isolated verification profile')
    parser.add_argument('--mods', nargs='+', help='Check only these mods, each with dependencies')
    args = parser.parse_args()
    if os.name == 'nt':
        # Fail unattended checks through their exit status instead of a blocking OS crash dialog.
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    game = args.game.resolve()
    executable = game / 'cataclysm-tiles.exe'
    if not executable.is_file():
        raise SystemExit(f'Missing game executable: {executable}')
    run = ROOT / '.build/qa-edition' / ('runtime-' + uuid.uuid4().hex[:10])
    foreign = run / 'foreign working directory'
    profile = run / 'профиль с пробелами'
    foreign.mkdir(parents=True)
    profile.mkdir()
    (profile / 'config').mkdir()
    (profile / 'config/options.json').write_text(json.dumps([{'name': 'USE_LANG', 'value': args.locale}]), encoding='utf-8')
    report_dir = ROOT / 'audits/edition'
    report_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = report_dir / run.name
    evidence_dir.mkdir()
    print('Evidence: ' + str(evidence_dir), flush=True)
    tests = [('help', ['--help']), ('jsonverify', ['--jsonverify'])]
    if args.mods:
        tests.append(('specified-mods', ['--check-mods', *args.mods]))
    elif args.all_mods:
        mods = []
        for source in sorted((game / 'data/mods').glob('*/modinfo.json')):
            for entry in json.loads(source.read_text(encoding='utf-8-sig')):
                if entry.get('type') == 'MOD_INFO' and not entry.get('obsolete') and entry.get('id') != 'test_data':
                    mods.append(entry['id'])
        if not mods:
            raise SystemExit('No production mod definitions found')
        # The parser requires at least one ID; the game checks each separately with dependencies.
        tests.append(('all-mods', ['--check-mods', *mods]))
    else:
        tests.append(('default-mods', ['--check-mods', 'dda', 'no_npc_food', 'personal_portal_storms']))
    result = {'game': str(game), 'locale': args.locale, 'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
              'profile': str(profile), 'foreign_cwd': str(foreign), 'checks': [],
              'gameplay_and_save_load': 'UNKNOWN', 'audible_sound': 'UNKNOWN',
              'clean_windows_10_11': 'UNKNOWN'}
    for name, flags in tests:
        command = [str(executable), '--userdir', str(profile), *flags]
        out = evidence_dir / (name + '-stdout.log')
        err = evidence_dir / (name + '-stderr.log')
        with out.open('wb') as stdout, err.open('wb') as stderr:
            process = subprocess.run(command, cwd=foreign, stdout=stdout, stderr=stderr,
                                     env={**os.environ, 'SDLAUDIODRIVER': 'dummy'}, timeout=7200,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        diagnostic = err.read_text(encoding='utf-8', errors='replace')
        data_failure = any(marker in diagnostic for marker in ['Error loading data:', 'Error loading data from json:', 'Missing dependencies:', 'Unknown mod:', 'Json error:'])
        check = {'name': name, 'command': command, 'exit_code': process.returncode,
                 'status': 'PASS' if process.returncode == 0 and not data_failure else 'FAIL',
                 'data_exception_reported': data_failure,
                 'stdout': str(out.relative_to(ROOT)), 'stderr': str(err.relative_to(ROOT))}
        result['checks'].append(check)
        (report_dir / 'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        (evidence_dir / 'runtime.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'{name}: {check["status"]}', flush=True)
    raise SystemExit(0 if all(t['status'] == 'PASS' for t in result['checks']) else 1)


if __name__ == '__main__':
    main()
