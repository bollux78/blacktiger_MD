#!/usr/bin/env python3
"""Interactive ROM builder for the Black Tiger Mega Drive SGDK project."""
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MODES = (
    ('original', 'Sem dithering experimental'),
    ('bayer4', 'Bayer 4x4 completo'),
    ('bayer4_soft', 'Bayer suave / balanced'),
    ('bayer4_adaptive', 'Bayer adaptativo (versao atual)'),
)


def project_root():
    script_dir = Path(__file__).resolve().parent
    candidates = [Path.cwd(), script_dir, script_dir.parent]
    for candidate in candidates:
        if (candidate / 'Makefile').is_file() and (candidate / 'tools' / 'build_assets.py').is_file():
            return candidate
    raise RuntimeError('Projeto nao encontrado. Execute a partir de ~/Projetos/blacktiger_MD.')


def version_label(root):
    version_file = root / 'VERSION'
    if not version_file.is_file():
        return 'sem_versao'
    value = version_file.read_text(encoding='utf-8').strip().splitlines()
    version = value[0].strip() if value else ''
    if not version:
        return 'sem_versao'
    version = re.sub(r'[^A-Za-z0-9._-]+', '_', version).strip('._-')
    return version or 'sem_versao'


def unique_output(path):
    if not path.exists():
        return path
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    candidate = path.with_name(f'{path.stem}_{stamp}{path.suffix}')
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f'{path.stem}_{stamp}_{counter}{path.suffix}')
        counter += 1
    return candidate


def run_command(args, root, env):
    print('\n$ ' + ' '.join(args), flush=True)
    result = subprocess.run(args, cwd=root, env=env, check=False)
    if result.returncode:
        raise RuntimeError(f'Comando falhou (codigo {result.returncode}): {" ".join(args)}')


def main():
    root = project_root()
    gdk = os.environ.get('GDK', str(Path.home() / 'mars' / 'm68k-elf'))
    print(f'Projeto: {root}')
    print(f'Versao: {version_label(root)}')
    print(f'GDK: {gdk}')
    while True:
        print('\n=== BLACK TIGER MD | GERADOR DE ROM ===')
        for index, (mode, label) in enumerate(MODES, 1):
            print(f' {index}. {mode:<18} - {label}')
        print(' 0. Sair')
        try:
            choice = input('\nEscolha: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nSaindo.')
            return 0
        if choice == '0':
            return 0
        if choice not in ('1', '2', '3', '4'):
            print('Opcao invalida.')
            continue
        mode = MODES[int(choice) - 1][0]
        env = os.environ.copy()
        env['BLACKTIGER_DITHER'] = mode
        env['GDK'] = gdk
        try:
            run_command(['make', 'assets'], root, env)
            run_command(['make', f'GDK={gdk}', '-j4'], root, env)
            built = root / 'out' / 'release' / 'rom.bin'
            if not built.is_file() or built.stat().st_size == 0:
                raise RuntimeError(f'ROM nao encontrada ou vazia: {built}')
            output_dir = root / 'roms'
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = f'BlackTiger_MD_{version_label(root)}_{mode}.bin'
            destination = unique_output(output_dir / filename)
            shutil.copy2(built, destination)
            print(f'\nROM criada: {destination}')
            print(f'Tamanho: {destination.stat().st_size:,} bytes')
        except (OSError, RuntimeError) as exc:
            print(f'\nERRO: {exc}', file=sys.stderr)
            print('Nenhuma ROM foi copiada nesta tentativa.', file=sys.stderr)
        try:
            input('\nPressione Enter para voltar ao menu...')
        except (EOFError, KeyboardInterrupt):
            print()
            return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        sys.exit(1)
