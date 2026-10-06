#ifndef MAP_STRIPS_H
#define MAP_STRIPS_H
#include "game.h"
/* Each pointer addresses 32 unchanged row-major tile words in ROM. No RAM cache
   or decoder state: wrap and dynamic patches remain the caller's responsibility. */
#define MAP_STRIP_SHIFT 5
#define MAP_STRIP_MASK 31
static inline u16 map_word(const u16 *const *map, u16 cell) {
    return map[cell >> MAP_STRIP_SHIFT][cell & MAP_STRIP_MASK];
}
#endif
