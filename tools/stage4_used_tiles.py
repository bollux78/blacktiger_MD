"""Exact tile/palette pairs reachable by round-4 background rendering.

Read *generated* level map and C tables, which contain the actual 8x8 logical
words after extraction. Abort if their format changes: never guess usage.
"""
import ast
from pathlib import Path
import re
import numpy as np


def _initializer(text, symbol):
    match = re.search(r'\b' + re.escape(symbol) + r'\s*\[\s*\]\s*=\s*\{(.*?)\}\s*;',
                      text, flags=re.S)
    if not match:
        raise RuntimeError('Cannot find generated initializer: ' + symbol)
    # The extractor writes decimal-only nested C initializer lists. This is
    # intentionally strict: unknown formats require explicit inspection.
    payload = match.group(1)
    if not re.fullmatch(r'[\s\d,{}+-]*', payload):
        raise RuntimeError('Unexpected initializer format: ' + symbol)
    return ast.literal_eval('[' + payload.replace('{', '[').replace('}', ']') + ']')


def stage4_required_pairs(root, count):
    root = Path(root)
    content = (root / 'src/data.c').read_text(encoding='utf-8')
    map_path = root / 'res/generated/map3.bin'
    words = np.fromfile(map_path, dtype='>u2')
    if words.size != 128 * 256:
        raise RuntimeError('Unexpected map3.bin size: ' + str(words.size))
    used = set()
    source_counts = {}

    def add(word, source):
        word = int(word)
        if not 0 <= word <= 65535:
            raise RuntimeError('Invalid tile attribute word in ' + source)
        logical = word & 2047
        if logical < 16:
            # Reserved blank/HUD patterns do not use generated masked tiles.
            return
        if logical >= count + 16:
            raise RuntimeError(f'{source} references tile {logical}, max {count+15}')
        used.add(((word >> 13) & 1, logical))
        source_counts[source] = source_counts.get(source, 0) + 1

    for word in words:
        add(word, 'map3.bin')

    opened = _initializer(content, 'open_tile3')
    if len(opened) != 4:
        raise RuntimeError('Expected exactly four open_tile3 words')
    for word in opened:
        add(word, 'open_tile3')

    bonus = _initializer(content, 'bonus_patches3')
    for patch in bonus:
        if patch == [0]:
            continue
        if not isinstance(patch, list) or len(patch) < 3:
            raise RuntimeError('Unexpected bonus_patches3 structure')
        variants = patch[1]
        if len(variants) != 4:
            raise RuntimeError('Expected four bonus states per patch')
        for variant in variants:
            if len(variant) != 4:
                raise RuntimeError('Expected four tile words per bonus state')
            for word in variant:
                add(word, 'bonus_patches3')

    boss = _initializer(content, 'boss_terrain_patches3')
    for patch in boss:
        if patch == [0]:
            continue
        if not isinstance(patch, list) or len(patch) < 2 or len(patch[1]) != 4:
            raise RuntimeError('Unexpected boss_terrain_patches3 structure')
        for word in patch[1]:
            add(word, 'boss_terrain_patches3')

    print('Fase 4: pares (paleta,tile) requeridos:', len(used), flush=True)
    print('Fontes verificadas:', ', '.join(f'{k}={v}' for k,v in source_counts.items()), flush=True)
    return used
