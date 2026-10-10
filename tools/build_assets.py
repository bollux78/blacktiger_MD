#!/usr/bin/env python3
"""Generate all build assets locally from a validated original ROM set."""
import hashlib
import os
import json
from pathlib import Path
import subprocess
import sys
from arcade_source import ROOT, Source

GENERATORS = ('extract.py', 'build_ui.py', 'build_intro.py', 'build_hud.py',
              'build_shop.py', 'build_attract.py', 'build_arena_parallax.py', 'build_backdrops.py',
              'pack_sprite_atlas.py', 'build_cave_geometry.py')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source = Source()
    subprocess.run([sys.executable, str(ROOT/'tools/prepare_source_data.py')], cwd=ROOT, check=True)
    inputs = sorted(set((ROOT/'tools').glob('*.py')) | set((ROOT/'tools').glob('*.lua')))
    inputs += [ROOT/'assets/board.json', ROOT/'assets/rom_manifest.json',
               ROOT/'art/black_tiger_md_logo_concept.png', ROOT/'art/yashichi.png',
               ROOT/'reference/.source-data.json', ROOT/'VERSION']
    # SHOP_PALETTE_LAB_V1: cache depende da paleta editada da loja
    inputs.append(ROOT/'tools/shop_palette_override.json')
    dither_mode = os.environ.get('BLACKTIGER_DITHER', 'original').lower()
    if dither_mode not in ('original', 'bayer4', 'bayer4_soft', 'bayer4_adaptive'):
        raise ValueError('BLACKTIGER_DITHER must be original, bayer4, bayer4_soft or bayer4_adaptive')
    inputs.append(ROOT/'tools/no_dither_tiles.json')
    inputs.append(ROOT/'tools/tile_dither_rules.json')
    # BLACKTIGER_PURE_UNTIL_JSON_V1: incluir perfil e regras temporárias no cache.
    tile_profile = os.environ.get('BLACKTIGER_TILE_PROFILE', 'pure')
    if tile_profile not in ('legacy', 'pure', 'loaded'):
        raise ValueError('BLACKTIGER_TILE_PROFILE inválido: ' + tile_profile)
    if tile_profile == 'loaded':
        inputs.extend((Path(os.environ['BLACKTIGER_TILE_RULES_FILE']),
                       Path(os.environ['BLACKTIGER_NO_DITHER_FILE'])))
    signature = hashlib.sha256(
        (''.join(digest(p) for p in inputs) + '|dither=' + dither_mode
         + '|tile_profile=' + tile_profile).encode()
    ).hexdigest()
    stamp = ROOT/'.local/assets-build.json'
    old = json.loads(stamp.read_text()) if stamp.exists() else {}
    if old.get('signature') == signature and old.get('outputs') and all((ROOT/p).is_file() and digest(ROOT/p)==h for p,h in old['outputs'].items()):
        print('Local generated assets are current; original ROM verified.')
        return
    for generator in GENERATORS:
        print(f'Generating: {generator}', flush=True)
        subprocess.run([sys.executable, str(ROOT/'tools'/generator)], cwd=ROOT, check=True)
    outputs = list((ROOT/'src').glob('*.inc')) + list((ROOT/'res/generated').glob('*'))
    outputs += [ROOT/'src/data.c', ROOT/'src/actor_dispatch.c', ROOT/'inc/assets.h', ROOT/'res/assets.res']
    stamp.parent.mkdir(exist_ok=True)
    stamp.write_text(json.dumps(dict(signature=signature, source_set=source.lock['aggregate_sha256'], outputs={str(p.relative_to(ROOT)):digest(p) for p in outputs if p.is_file()}),indent=2)+'\n')

if __name__ == '__main__':
    try:
        main()
    except (ValueError,OSError,RuntimeError) as error:
        sys.exit(str(error))
