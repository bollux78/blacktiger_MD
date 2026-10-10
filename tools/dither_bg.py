"""Experimental ordered dithering for Genesis background tiles.

The pattern is local to the source tile to preserve deduplication.
"""
import numpy as np

BAYER4 = np.array([
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
], dtype=np.float64)


def convert(indices, source_palette, target_palette, strength=1.0):
    """Convert source pen indices to target indices 1..15.

    Source and target colors are RGB333 triples. This does not handle
    transparency: the caller must restore transparent pixels explicitly.
    """
    indices = np.asarray(indices, dtype=np.uint8)
    source = np.asarray(source_palette, dtype=np.float64)
    target = np.asarray(target_palette, dtype=np.float64)
    if indices.ndim != 2 or indices.shape[0] % 4 or indices.shape[1] % 4:
        raise ValueError('indices must be a 2D array with dimensions divisible by 4')
    if target.shape != (15, 3) or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError('expected source Nx3 and target 15x3 RGB333 palettes')
    if not 0 <= strength <= 1:
        raise ValueError('strength must be between 0 and 1')
    if int(indices.max()) >= len(source):
        raise ValueError('source pen index outside source palette')

    result = np.empty(indices.shape, dtype=np.uint8)
    threshold = np.tile((BAYER4 + 0.5) / 16.0,
                        (indices.shape[0] // 4, indices.shape[1] // 4))
    for pen in np.unique(indices):
        color = source[int(pen)]
        distances = np.sum((target - color) ** 2, axis=1)
        nearest = int(np.argmin(distances))
        best_error = float(distances[nearest])
        best_second = nearest
        best_fraction = 0.0
        for second in range(len(target)):
            if second == nearest:
                continue
            direction = target[second] - target[nearest]
            denom = float(np.dot(direction, direction))
            if denom == 0:
                continue
            fraction = float(np.clip(np.dot(color - target[nearest], direction) / denom, 0, 1))
            mixture = target[nearest] + fraction * direction
            error = float(np.sum((color - mixture) ** 2))
            if error < best_error - 1e-9:
                best_error = error
                best_second = second
                best_fraction = fraction
        pattern = np.where(threshold < best_fraction * strength,
                           best_second + 1, nearest + 1)
        result[indices == pen] = pattern[indices == pen]
    return result


def convert_soft(indices, source_palette, target_palette, original_mapping):
    """Selective Bayer: keep flat colors and reject high-contrast substitutions."""
    indices = np.asarray(indices, dtype=np.uint8)
    target = np.asarray(target_palette, dtype=np.float64)
    source = np.asarray(source_palette, dtype=np.float64)
    mapping = np.asarray(original_mapping, dtype=np.uint8)
    base = mapping[indices].copy()
    proposed = convert(indices, source_palette, target_palette)
    if proposed.shape != base.shape:
        proposed = proposed.reshape(base.shape)
    # Bayer proposals are retained only on selected sites (~31% maximum).
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                      [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.uint8)
    yy, xx = np.indices(base.shape[-2:])
    sparse = bayer[yy % 4, xx % 4] < 9
    # Skip colors already well represented by the palette.
    dist = np.sum((source[:, None, :] - target[None, :, :]) ** 2, axis=2)
    error = np.min(dist, axis=1)[indices] >= 1.0
    # Ignore bright/dark jumps. Index zero is reserved for transparency.
    safe = (base > 0) & (proposed > 0) & (proposed <= len(target))
    base_idx = np.clip(base.astype(int) - 1, 0, len(target) - 1)
    prop_idx = np.clip(proposed.astype(int) - 1, 0, len(target) - 1)
    weights = np.array([0.2126, 0.7152, 0.0722])
    delta = np.abs((target[base_idx] - target[prop_idx]) @ weights)
    chroma_jump = np.linalg.norm(target[base_idx] - target[prop_idx], axis=-1)
    keep = (proposed != base) & sparse & error & safe & (delta <= 2.0) & (chroma_jump <= 3.5)
    base[keep] = proposed[keep]
    return base


def convert_adaptive(indices, source_palette, target_palette, original_mapping):
    """Conservative error-guided ordered dithering, tile-local and deterministic.

    Only mix when a second color materially improves squared RGB error.
    Reject large chromatic or luminance jumps to preserve pixel-art outlines.
    """
    indices = np.asarray(indices, dtype=np.uint8)
    source = np.asarray(source_palette, dtype=np.float64)
    target = np.asarray(target_palette, dtype=np.float64)
    mapping = np.asarray(original_mapping, dtype=np.uint8)
    base = mapping[indices].copy()
    if indices.ndim != 2 or target.shape != (15, 3):
        raise ValueError('Expected 2D pens and 15 RGB target colors')
    threshold = np.tile((BAYER4 + 0.5) / 16.0,
                        (indices.shape[0] // 4, indices.shape[1] // 4))
    if threshold.shape != indices.shape:
        raise ValueError('Tile dimensions must be multiples of four')
    weights = np.array([0.2126, 0.7152, 0.0722])
    for pen in np.unique(indices):
        mask = indices == pen
        primary = int(mapping[int(pen)]) - 1
        if primary < 0 or primary >= len(target):
            continue
        color = source[int(pen)]
        first = target[primary]
        original_error = float(np.sum((color - first) ** 2))
        if original_error < 0.5:
            continue
        best_score = 0.0
        best_index = -1
        best_fraction = 0.0
        for second in range(len(target)):
            if second == primary:
                continue
            other = target[second]
            direction = other - first
            norm2 = float(np.dot(direction, direction))
            if norm2 < 1e-8 or norm2 > 20.0:
                continue
            if abs(float(np.dot(direction, weights))) > 2.3:
                continue
            fraction = float(np.clip(np.dot(color - first, direction) / norm2, 0.0, 0.48))
            if fraction < 0.10:
                continue
            mixed = first + fraction * direction
            gain = original_error - float(np.sum((color - mixed) ** 2))
            # Penalize chromatic separation, preventing noisy outlines.
            score = gain - 0.04 * norm2
            if score > best_score:
                best_score, best_index, best_fraction = score, second, fraction
        if best_index >= 0 and best_score >= 0.25:
            # At most 48% secondary pixels; local Bayer pattern stays tile stable.
            base[mask & (threshold < best_fraction)] = best_index + 1
    return base
