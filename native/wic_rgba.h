#ifndef WEDGE_WIC_RGBA_H
#define WEDGE_WIC_RGBA_H
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
typedef struct {uint8_t *pixels;uint32_t width,height,stride;size_t size;} WicRgba;
/* Returned pixels are RGBA8, top row first; caller owns them via wic_rgba_free. */
int wic_rgba_decode(const void *png,size_t length,WicRgba *out);
/* Explicit in-place row reversal. Decode itself always remains top-first. */
int wic_rgba_flip_vertical(WicRgba *image);
void wic_rgba_free(WicRgba *image);
#endif
