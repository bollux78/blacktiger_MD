#!/usr/bin/env python3
"""Source-only or private-logo startup, held Start isolation, and Black Tiger intro."""
import argparse,hashlib,json
import numpy as np
from test_runtime import ROOT,Runner,state
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--variant',choices=('auto','source','private'),default='auto')
args=parser.parse_args()
rom=ROOT/'out/release/rom.bin'
assets=('sega_chant_pcm','shinobi_logo_tiles','capcom_logo_tiles')
captures=[]
variant=None
for held in (False,True):
 r=Runner(rom,skip_boot=False)
 private='boot_logos_private' in r.symbols
 variant='private' if private else 'source'
 assert args.variant in ('auto',variant),(args.variant,variant)
 for name in assets:
  assert (name in r.symbols)==private,('Boot asset linkage mismatch',name,variant)
 for _ in range(120):
  r.run(1,8 if held else 0)
  if int.from_bytes(r.read('boot_tick'),'big')>=1 or (held and int.from_bytes(r.read('boot_stage'),'big')==1):break
 else:raise AssertionError('Startup did not begin')
 if held:
  r.run(10,8)
  assert r.read('boot_done',1)==b'\0','held Start leaked into menu'
 seen=[]
 r.audio_capture=[]
 for _ in range(800 if private else 100):
  r.run(1)
  stage=int.from_bytes(r.read('boot_stage'),'big');tick=int.from_bytes(r.read('boot_tick'),'big')
  if private and not held and stage in (1,2) and tick>=90 and stage not in seen:
   assert np.count_nonzero(r.frame)>100,'Blank boot logo'
   name='boot-private-'+('sega' if stage==1 else 'capcom')+'.png'
   r.capture(name);captures.append(name);seen.append(stage)
  if r.read('boot_done',1)==b'\1':break
 else:raise AssertionError('Startup did not finish')
 if private and not held:
  assert seen==[1,2],('Logo sequence',seen)
  assert np.any(np.frombuffer(b''.join(r.audio_capture),dtype=np.int16)),'Boot audio silent'
 r.audio_capture=None
 r.run(60)
 assert r.read('boot_done',1)==b'\1' and state(r).mode==0
 assert r.read('frontend',2)==b'\0\0','startup selected a menu item'
 r.run(4,2);r.run(4);r.run(4,8);r.run(4);r.run(4,2);r.run(20)
 assert state(r).mode==9,'Original Black Tiger game intro missing'
 if not held:
  r.run(90)
  name='boot-'+variant+'-black-tiger-intro.png';r.capture(name);captures.append(name)
 r.close()
report=dict(passed=True,rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),variant=variant,held_start_isolated=True,black_tiger_intro_retained=True,third_party_boot_assets_absent=variant=='source',private_logo_sequence=variant=='private',captures=captures,scope=__doc__)
(ROOT/('reports/boot-logos-'+variant+'-runtime-tests.json')).write_text(json.dumps(report,indent=2)+'\n')
(ROOT/'reports/boot-logos-runtime-tests.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
