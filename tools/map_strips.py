"""Lossless fixed-size map-strip dictionary; no runtime unpack buffer."""
STRIP_WORDS = 32

def pack_map(values):
    values = list(map(int, values))
    assert values and len(values) % STRIP_WORDS == 0
    unique, strips, indices = {}, [], []
    for at in range(0, len(values), STRIP_WORDS):
        strip = tuple(values[at:at + STRIP_WORDS])
        assert all(0 <= word <= 65535 for word in strip)
        if strip not in unique:
            unique[strip] = len(strips)
            strips.append(strip)
        indices.append(unique[strip])
    return strips, indices

def pointer_table(name, indices, storage=''):
    return storage + 'const u16 *const ' + name + '[]={\n' + ','.join(
        name + '_strips+' + str(index * STRIP_WORDS) for index in indices) + '};\n'

def c_map(name, values, storage='static '):
    strips, indices = pack_map(values)
    return (storage + 'const u16 ' + name + '_strips[]={\n' +
            ','.join(str(word) for strip in strips for word in strip) + '};\n' +
            pointer_table(name, indices, storage))
