# Private boot logos and lossless map storage

## Scope and tracked boundary

The VERSION/private-hook patch is its own commit, `f1fc657`. `VERSION=1.7`
produces exactly the previous `src/ui_data.inc`; switching to `1.8` changes the
stamp and records `v1.8`, and restoring `1.7` restores the exact original bytes.
The source-only boot, held Start isolation, importer and staged-source audit
passed before that commit.

The remaining source changes deduplicate map strips, adapt map readers, and add
exhaustive host/linked-ROM and boot-variant tests. No artwork, music, ROM-derived
tables, binaries or kit files belong in either source commit. The private kit
remains `.local/private-boot-kit/`, copied to ignored `src/private_boot/`; the
hook remains `boot_logos_private()`.

## Space measurement and choice

Measured with the current local SGDK, GCC 16.1.0 and a fresh build after moving
the checkout. `nm -S --size-sort` and `size -A` snapshots are local under
`.local/logo-map-work/space-audit.json`.

Largest original ROM symbols:

| Data | Bytes |
| --- | ---: |
| `object_patterns` | 1,958,400 |
| Eight level maps | 524,288 |
| `arena_walls` | 65,536 |
| `music_27` | 68,154 |
| `bg2` | 51,264 |

Before repacking, the source-hook build has 4,150,592 bytes of `.text` and 116
bytes of initialized `.data`. The unmodified private kit adds 46,776 ROM bytes
in this toolchain; its chant alone is 27,136 bytes. Its linked ROM data ends at
`0x400C6C` (exclusive), 3,180 bytes above the cartridge window. This reproduces
the overflow, but not the pasted `0x40D104` result; measurements here use the
actual rebuilt ELF, not that earlier estimate.

Candidates measured:

- Whole-row deduplication saves nothing on the eight level maps: every row is
  distinct. The arena alone saves just 2,560 bytes after row pointers.
- Fixed strip dictionaries retain arbitrary random access. 32-word strips save
  **116,864 bytes** across all nine maps, including 32-bit ROM pointer tables.
  Eight-word strips save 275,680 bytes; 16-word strips save 205,024 bytes;
  64-word strips save 48,512 bytes. Smaller strips require more pointer changes
  while streaming rows. All chunk sizes measured are in local
  `map-candidates.json`.
- The sprite packer already saves 130,560 bytes. Uniform 512-byte deduplication
  of its current output has a further theoretical 45,086-byte saving after a
  16-bit index, insufficient alone and requiring changes to contiguous sprite
  DMA. 32-byte tile deduplication has a theoretical 651,008-byte saving but
  would require substantially more indirection/transfers. Neither was needed.
- Removing the 68,154-byte music track would change behavior. No music or
  samples were removed. Four-byte resource alignment has at most 192 bytes of
  padding across 64 resources, far below the target. Final cartridge padding
  is retained according to the existing 128 KiB size alignment.

The chosen format stores each unique 32-word horizontal strip once. Maps hold
1,024 ROM pointers each; a cell takes a strip lookup and an unchanged word read.
The renderer reuses the pointer within a row strip. No decompression buffer or
additional persistent RAM is needed. Collision byte maps, pots, hidden walls,
bonus patches and boss closure data are unchanged. Wraparound remains in the
existing callers. Dynamic terrain reads use the same packed-map accessor.

## ROM extent

Ends below are exclusive (`.text` plus initialized `.data` load image), before
cartridge padding; the last used address is one less.

| Build | Data end | Space below 4 MiB |
| --- | --- | ---: |
| Hook, original maps, no kit | `0x3F55B4` | 43,596 bytes |
| Original maps, unmodified kit | `0x400C6C` | -3,180 bytes |
| Packed maps, no kit | `0x3D8E38` | 160,200 bytes |
| Packed maps, corrected private kit | `0x3E4584` | 113,276 bytes |

Source-only net saving is **116,604 bytes**, allowing 260 bytes for reader/code
layout changes. The final private build is 116,456 bytes smaller than the
uncompressed private build. Its BIN remains padded to 4,194,304 bytes, with a
`SEGA MEGA DRIVE` header, SRAM beginning at `$200001`, and no added mapper or
bank switching.

## Private startup heap correction

The first fitting private build stopped in SGDK `VDP_resetScreen`, before the
boot hook: its default font allocation exhausted startup heap. The extra private
BSS crossed an already narrow allocation margin. This was not a PCM hang.

The two sequential logo screens now share their 32-byte palette array through
an alias in the local kit. Both public palette symbols remain available. This
saves 32 bytes of palette storage (30 bytes net after linked BSS alignment),
without altering palette values, logo timing or gameplay. The original kit is
preserved locally in `.local/logo-map-work/private-kit-original/`. The corrected
files exist in both the kit and `src/private_boot/`, so the nightly setup copy
retains the fix. None of those files are committed.

## Pacing

Same 600-refresh scenarios and unchanged gates, with zero discarded logic ticks,
VBlank overruns and cache faults in each passing sample:

| Build | L2 presentations | L2 worst second | L3 presentations | L3 worst second |
| --- | ---: | ---: | ---: | ---: |
| Before packing, source hook | 443 | 24 | 483 | 27 |
| Packed, source-only | 447 | 26 | 479 | 27 |
| Packed, corrected private kit | 440 | 24 | 479 | 27 |
| Required floor | 430 | 24 | 470 | 25 |

These samples pass the required performance gates; they are not a claim of
universal 60 FPS or identical presentation timing in every scene.

## Validation

- All nine uncompressed reference maps match the previously validated v1.7 BIN
  byte for byte.
- 294,912 map cells compared exhaustively through the production C accessor and
  separately through the actual linked ROM pointer tables.
- 20,000 strip-walker comparisons against the uncompressed scalar reference,
  including horizontal/vertical wrap, out-of-range Y, dynamic rows, backdrop
  remapping and pin/unpin counts; address/undefined-behavior sanitizers enabled.
- Source-only startup explicitly tested without the kit. Private startup
  explicitly tested with it, including natural SEGA/CAPCOM order, audible boot
  output, held Start isolation and the retained Black Tiger intro after
  controller-driven play selection.
- Local captures: `reports/boot-private-sega.png`,
  `reports/boot-private-capcom.png`, `reports/boot-private-black-tiger-intro.png`.
- Full original-ROM fixture preparation (`tools/prepare_source_data.py --all`)
  completed successfully. Moving the checkout had left stale absolute ROM
  symlinks under ignored `reports/`; those were repaired before the successful
  run, recorded in `.local/logo-map-work/source-oracles-retry.log`.
- Two fixture assumptions exposed by the new build were corrected: the SRAM
  test now waits for actual boot completion, and the Round 5 column test now
  chooses an existing skeleton within the real 88-entry spawn table rather
  than reading 160 entries looking for a type absent from that level. All
  original physics, SRAM corruption and interrupted-write assertions remain.
- All **184 commands** in the Makefile test/profile list passed in the final
  run against the private-logo ROM, after the complete source-observation step.
  Results and command logs are under
  `.local/logo-map-work/private-suite-final/summary.json`. The runner executes
  independent commands in three processes; none were excluded. ROM SHA-256:
  `2067014f7c7e3ad6741716ce80a1713e1c781aecafdaa88ee8a3acc422a5dcbf`.

The local packaging gate also passed (14 asset checks and 47 runtime checks).
The final private release is `dist/blacktiger_MD_v1.7.bin`; the earlier
pre-logo distribution is preserved in `.local/logo-map-work/prior-distribution/`.

## Risks and limits

The SGDK startup font allocation still has a narrow RAM margin; future static
RAM growth must rerun the cold-boot tests. ROM margin is separate and is now
113,276 bytes with the kit. Emulator coverage does not establish physical
EverDrive/NTSC cold-boot compatibility or a complete natural playthrough.
