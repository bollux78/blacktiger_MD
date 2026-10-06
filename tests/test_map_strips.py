#!/usr/bin/env python3
"""Decode every map with production C and from the linked cartridge; compare all cells."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from map_strips import STRIP_WORDS, pack_map

def words(raw):
    return struct.unpack('>'+str(len(raw)//2)+'H',raw)

rom=(ROOT/'out/release/rom.bin').read_bytes()
symbols={}
for line in (ROOT/'out/release/symbol.txt').read_text().splitlines():
    v=line.split()
    if len(v)>=3:
        symbols[v[2].split('.lto_priv.')[0]]=int(v[0],16)
source=(ROOT/'src/data.c').read_text()
arena=(ROOT/'src/arena_parallax_data.inc').read_text()
cases=[]
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp)
    for name,original in [(f'map{i}',f'map{i}') for i in range(8)]+[('arena_walls','palace_map')]:
        raw=(ROOT/f'res/generated/{original}.bin').read_bytes()
        expected=words(raw)
        strips,indices=pack_map(expected)
        assert [w for i in indices for w in strips[i]]==list(expected)
        declarations=re.search(r'(?:static )?const u16 \*const '+name+r'\[\]=\{.*?\};',arena if name=='arena_walls' else source,re.S)[0]
        if name=='arena_walls':
            declarations=re.search(r'static const u16 arena_walls_strips\[\]=\{.*?\};',arena,re.S)[0]+'\n'+declarations
        else:
            packed=words((ROOT/f'res/generated/{name}_strips.bin').read_bytes())
            declarations='const u16 '+name+'_strips[]={'+','.join(map(str,packed))+'};\n'+declarations
        (tmp/'map.c').write_text('#include "map_strips.h"\n'+declarations+'\nvoid decode(u16 *out){for(u16 i=0;i<32768;i++)out[i]=map_word('+name+',i);}\n')
        binary=tmp/(name+'.dylib')
        subprocess.run(['cc','-shared','-fPIC','-O2','-DHOST_TEST','-I'+str(ROOT/'inc'),str(tmp/'map.c'),'-o',str(binary)],check=True)
        lib=C.CDLL(str(binary));out=(C.c_uint16*32768)();lib.decode(out)
        assert tuple(out)==expected,(name,'production host decoder')
        # Read the actual ROM pointer table, not reconstructed packer indices.
        pointers=struct.unpack_from('>1024I',rom,symbols[name])
        linked=[]
        for pointer in pointers:
            assert pointer%2==0 and pointer+STRIP_WORDS*2<=len(rom),(name,pointer)
            linked.extend(struct.unpack_from('>32H',rom,pointer))
        assert tuple(linked)==expected,(name,'linked ROM decoder')
        original_bytes=len(raw);packed_bytes=len(strips)*STRIP_WORDS*2+len(indices)*4
        cases.append(dict(name=name,cells=len(expected),original_bytes=original_bytes,packed_bytes=packed_bytes,saved_bytes=original_bytes-packed_bytes,original_sha256=hashlib.sha256(raw).hexdigest()))
report=dict(passed=True,rom_sha256=hashlib.sha256(rom).hexdigest(),cells=sum(c['cells'] for c in cases),saved_data_bytes=sum(c['saved_bytes'] for c in cases),cases=cases,scope=__doc__)
(ROOT/'reports/map-strip-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
