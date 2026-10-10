"""Black Tiger Dithering Lab 2.0: live overlay for per-tile rules on the full map.

Maps are not regenerated on slider movement: one converted 16x16 block image
is shared among every map occurrence of a (source code, palette, flip) triple.
All conversion uses LabV2._preview_pixels(), the same backend as the tile preview.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import numpy as np
from PIL import Image, ImageTk

from dither_tile_policy import mode_defaults


class MapLiveMixin:
    """Add complete-scene previews while leaving the existing editor intact."""

    def build_widgets(self):
        # Initialized before LabV2's build_widgets calls create_editor/load_stage.
        self.map_live_enabled = tk.BooleanVar(master=self, value=True)
        self._live_photos = {}            # code -> {(palette, flip): PhotoImage}
        self._live_pending = None
        self._live_touched = {str(i): set() for i in range(8)}
        self._live_loading = False
        self._live_current_code = None
        super().build_widgets()

    def create_editor(self):
        super().create_editor()
        bar = self.editor_tab.winfo_children()[0]
        ttk.Checkbutton(
            bar, text='Mostrar ajustes no mapa', variable=self.map_live_enabled,
            command=self._toggle_live_map
        ).pack(side='left', padx=(13, 0))
        # Existing context description would be misleading after adding overlays.
        for widget in self._all_widgets(self.editor_tab):
            if isinstance(widget, ttk.Label):
                label = str(widget.cget('text'))
                if label.startswith('Contexto: somente o bloco central'):
                    widget.configure(text='Contexto com as regras aplicadas e a prévia atual')
                elif label.startswith('As regras valem para todas as ocorrências'):
                    widget.configure(text=(
                        'Cada ajuste aplicado aparece em TODAS as ocorrências do código no mapa.\n'
                        'O mapa é uma prévia: os arquivos gráficos só mudam ao gerar assets/ROM.'
                    ))

    @staticmethod
    def _all_widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from MapLiveMixin._all_widgets(child)

    def _cancel_live(self):
        if self._live_pending is not None:
            try:
                self.after_cancel(self._live_pending)
            except tk.TclError:
                pass
            self._live_pending = None

    def load_stage(self):
        self._cancel_live()
        self._live_loading = True
        self._live_photos.clear()
        self._live_current_code = None
        try:
            super().load_stage()
        finally:
            self._live_loading = False
        if getattr(self, 'data', None) is not None:
            self._redraw_all_live()

    def _stage_saved_codes(self):
        stage = str(self.stage)
        return ({int(v) for v in self.legacy.get(stage, [])}
                | {int(v) for v in self.rules['stages'][stage]}
                | set(self._live_touched[stage]))

    def _effective(self, code, live=False):
        """Return the per-code settings, preserving existing, unsaved edits."""
        if live and self.current is not None and int(self.current[2]) == code:
            chosen = self.tile_mode.get()
            mode = self.mode.get() if chosen == 'inherit' else chosen
            if mode == 'original':
                params = {}
            elif mode == 'bayer4_adaptive' and chosen == 'inherit':
                params = {key: float(var.get()) for key, var in self.values.items()}
            else:
                params = self._mode_values(mode)
            # Includes possible manual color changes not yet applied to the code.
            return mode, params, self.palette_overrides

        stage = str(self.stage)
        if code in self.legacy.get(stage, []):
            return 'original', {}, {}
        rule = self.rules['stages'][stage].get(str(code))
        if rule is not None:
            mode = rule['mode']
            if mode == 'original':
                return 'original', {}, {}
            params = rule.get('parameters', mode_defaults(mode))
            return mode, params, rule.get('palette_overrides', {})

        mode = self.mode.get()
        if mode == 'original':
            return 'original', {}, {}
        if mode == 'bayer4_adaptive':
            params = {key: float(var.get()) for key, var in self.values.items()}
        else:
            params = mode_defaults(mode)
        return mode, params, {}

    def _tile_rgb(self, code, palette, flip, live=False):
        mode, params, overrides = self._effective(code, live=live)
        _, rgb = self._preview_pixels(
            int(code), int(palette), bool(flip), mode, params,
            overrides.get(str(palette), {})
        )
        return Image.fromarray(rgb, mode='RGB')

    def _redraw_code(self, code, live=False):
        if self.data is None or self.codes is None:
            return
        code = int(code)
        tag = f'dither-live-code-{code}'
        self.map_canvas.delete(tag)
        self._live_photos.pop(code, None)
        if not self.map_live_enabled.get():
            return

        yy, xx = np.where(self.codes == code)
        if len(xx) == 0:
            return
        zoom = int(self.zoom.get())
        step = 16 * zoom
        palettes = self.data['palettes']
        flips = self.data['flips']
        photos = {}
        # Cache each image once per source-palette and flip, not per occurrence.
        for y, x in zip(yy, xx):
            p = int(palettes[y, x])
            f = bool(flips[y, x])
            key = (p, f)
            if key not in photos:
                im = self._tile_rgb(code, p, f, live=live)
                if zoom != 1:
                    im = im.resize((step, step), Image.Resampling.NEAREST)
                photos[key] = ImageTk.PhotoImage(im, master=self)
            self.map_canvas.create_image(
                int(x)*step, int(y)*step, anchor='nw', image=photos[key],
                tags=('dither-live-map', tag)
            )
        self._live_photos[code] = photos
        self.map_canvas.tag_raise('marker')

    def _redraw_all_live(self):
        self._cancel_live()
        self.map_canvas.delete('dither-live-map')
        self._live_photos.clear()
        if not self.map_live_enabled.get() or self.data is None:
            return
        try:
            for code in sorted(self._stage_saved_codes()):
                self._redraw_code(code, live=False)
            if self.current is not None:
                self._redraw_code(int(self.current[2]), live=True)
            self.map_canvas.tag_raise('marker')
        except Exception as exc:
            self.edited_flag.set('Erro atualizando mapa: ' + str(exc))

    def _toggle_live_map(self):
        if self.map_live_enabled.get():
            self._redraw_all_live()
        else:
            self._cancel_live()
            self.map_canvas.delete('dither-live-map')
            self._live_photos.clear()
        if self.current is not None:
            self._refresh_context_live()

    def _schedule_current_live(self):
        if self._live_loading or self.current is None or self.data is None:
            return
        self._cancel_live()
        # Dragging the sliders can issue dozens of events per second.
        self._live_pending = self.after(130, self._refresh_current_live)

    def _refresh_current_live(self):
        self._live_pending = None
        if self.data is None or self.current is None:
            return
        code = int(self.current[2])
        if self.map_live_enabled.get():
            try:
                self._redraw_code(code, live=True)
            except Exception as exc:
                self.edited_flag.set('Erro atualizando bloco no mapa: ' + str(exc))
        self._refresh_context_live()

    def refresh_preview(self):
        super().refresh_preview()
        self._schedule_current_live()

    def on_map_click(self, event):
        previous = self.current[2] if self.current else None
        self._cancel_live()
        super().on_map_click(event)
        now = self.current[2] if self.current else None
        if previous is not None and previous != now:
            # The previous block may have been previewed without Apply. Restore
            # its committed rule, or the current general conversion if inherited.
            if self.map_live_enabled.get():
                try:
                    self._redraw_code(previous, live=False)
                except Exception as exc:
                    self.edited_flag.set('Erro restaurando mapa: ' + str(exc))
        self._schedule_current_live()

    def apply_tile(self):
        code = int(self.current[2]) if self.current else None
        super().apply_tile()
        if code is not None:
            self._live_touched[str(self.stage)].add(code)
            if self.map_live_enabled.get():
                try:
                    self._redraw_code(code, live=False)
                except Exception as exc:
                    self.edited_flag.set('Erro aplicando regra ao mapa: ' + str(exc))
        self._schedule_current_live()

    def discard(self):
        super().discard()
        if not self.unsaved:
            self._redraw_all_live()
            self._refresh_context_live()

    def _refresh_context_live(self):
        """Preview neighbouring saved rules, not only the centre block."""
        if self.current is None or self.source_image is None or self.codes is None:
            return
        try:
            x, y, code, _, _ = self.current
            px, py = x*16, y*16
            box = (max(0, px-32), max(0, py-32),
                   min(self.source_image.width, px+48),
                   min(self.source_image.height, py+48))
            context = self.source_image.crop(box)
            if self.map_live_enabled.get():
                drawn = self._stage_saved_codes() | {int(code)}
                cache = {}
                first_row, last_row = box[1]//16, (box[3]-1)//16
                first_col, last_col = box[0]//16, (box[2]-1)//16
                for cy in range(first_row, last_row+1):
                    for cx in range(first_col, last_col+1):
                        tile_code = int(self.codes[cy, cx])
                        if tile_code not in drawn:
                            continue
                        pal = int(self.data['palettes'][cy, cx])
                        flip = bool(self.data['flips'][cy, cx])
                        live = tile_code == code
                        key = (tile_code, pal, flip, live)
                        if key not in cache:
                            cache[key] = self._tile_rgb(tile_code, pal, flip, live)
                        dstx = cx*16-box[0]
                        dsty = cy*16-box[1]
                        context.paste(cache[key], (dstx,dsty))
            else:
                # Preserve the existing immediate centre preview in comparison mode.
                mode, params, overrides = self._effective(code, live=True)
                _, result = self._preview_pixels(
                    code, int(self.current[3]), bool(self.current[4]),
                    mode, params, overrides.get(str(self.current[3]), {})
                )
                context.paste(Image.fromarray(result,mode='RGB'), (px-box[0],py-box[1]))
            factor = min(4, max(1, 320//max(context.size)))
            context = context.resize((context.width*factor, context.height*factor),
                                     Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(context, master=self)
            self.context_photo = photo
            self.context_label.configure(image=photo, text='')
        except Exception as exc:
            self.edited_flag.set('Erro na prévia de contexto: ' + str(exc))

    def close(self):
        self._cancel_live()
        super().close()
