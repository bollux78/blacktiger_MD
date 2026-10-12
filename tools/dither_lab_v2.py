#!/usr/bin/env python3
"""Black Tiger MD - Dithering Lab 2.0

Editor de cenarios com previa do algoritmo verdadeiro por tile original 16x16.
Preserva tools/dither_lab.py (v1). A compilacao utiliza a rotina testada da v1.
"""
from __future__ import annotations
import hashlib
import json
import copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
from PIL import Image, ImageTk
import dither_bg
from dither_lab import Lab, Tooltip, PARAMS, HELP
# BLACKTIGER_MULTIMODE_SLIDERS_V1
from dither_tile_policy import (MODES, POLICIES, DEFAULTS, load_all,
                                MODE_PARAMS, MODE_HELP, mode_defaults, validate_mode_params,
                                validate_params, adaptive_custom, bayer4_custom, soft_custom,
                                apply_palette_overrides)  # BLACKTIGER_PALETTE_EDITOR_V1

MODES_LABELS = {
    'inherit': 'Herdar algoritmo geral',
    'original': 'Original — sem dithering',
    'bayer4': 'Bayer4 completo',
    'bayer4_soft': 'Bayer4 balanced',
    'bayer4_adaptive': 'Bayer4 adaptativo',
}


# BLACKTIGER_BAYER_POPUP_AUTO_SIZE_V1
# BLACKTIGER_BAYER_POPUP_COMPACT_V1
def autosize_bayer_dialog(win, min_w=900, min_h=440, pad_w=25, pad_h=25):
    """Ajusta o popup ao conteúdo, sem exceder a área visível do monitor."""
    win.update_idletasks()
    sw = max(1, win.winfo_screenwidth())
    sh = max(1, win.winfo_screenheight())
    # Deixa espaço para bordas da janela, painel do sistema e dock.
    usable_w = max(320, sw - 80) if sw > 320 else sw
    usable_h = max(260, sh - 120) if sh > 260 else sh
    requested_w = win.winfo_reqwidth() + pad_w
    requested_h = win.winfo_reqheight() + pad_h
    width = min(max(requested_w, min_w), usable_w)
    height = min(max(requested_h, min_h), usable_h)
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    # minsize nao pode superar a geometria em monitores menores.
    win.minsize(min(650, width), min(380, height))
    win.geometry(f'{width}x{height}+{x}+{y}')


class LabV2(Lab):
    def build_widgets(self):
        self.title('Black Tiger MD — Dithering Lab 2.0')
        self.geometry('1280x860')
        self.minsize(950, 690)
        self.rules_path = self.project / 'tools/tile_dither_rules.json'
        self.legacy_path = self.project / 'tools/no_dither_tiles.json'
        self.rules = load_all(self.rules_path)
        self.legacy = self._load_legacy()
        self.unsaved = False
        self.stage = 0
        self.codes = None
        self.data = None
        self.source_image = None
        self.map_photo = None
        self.photo_preview = []
        self.current = None
        self.palette_overrides = {}
        self.color_window = None
        self.color_requested_pen = None
        self.color_pair_clipboard = None  # Copied pair survives tile, pen and stage changes.
        self.stage_string = tk.StringVar(value='Fase 1')
        self.zoom = tk.IntVar(value=1)
        self.tile_mode = tk.StringVar(value='inherit')
        self.tile_values = {key: tk.DoubleVar(value=default) for key, _, default, _, _, _ in PARAMS}
        self.info = tk.StringVar(value='Escolha uma fase e clique em um bloco do cenário.')
        self.tile_info = tk.StringVar(value='Nenhum bloco selecionado')
        self.edited_flag = tk.StringVar(value='')
        self.state_value = tk.StringVar(value='Pronto.')

        top = ttk.Frame(self, padding=(12, 9))
        top.pack(fill='x')
        ttk.Label(top, text='Black Tiger MD · Dithering Lab 2.0', font=('Sans', 17, 'bold')).pack(side='left')
        ttk.Label(top, text='Prévia por bloco + compilação', foreground='#777').pack(side='right')
        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        self.editor_tab = ttk.Frame(tabs)
        self.build_tab = ttk.Frame(tabs)
        tabs.add(self.editor_tab, text=' Editor visual dos tiles ')
        tabs.add(self.build_tab, text=' Configuração geral e gerar ROM ')
        self.create_editor()
        self.create_builder()
        ttk.Label(self, textvariable=self.info, padding=(9, 5)).pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.load_stage()

    def _load_legacy(self):
        if not self.legacy_path.exists():
            return {str(s): [] for s in range(8)}
        data = json.loads(self.legacy_path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('no_dither_tiles.json precisa ser um objeto')
        for s in range(8):
            key = str(s)
            values = data.setdefault(key, [])
            if not isinstance(values, list) or not all(isinstance(v,int) and 0 <= v < 2048 for v in values):
                raise ValueError(f'Lista original invalida: fase {s+1}')
        return data

    def create_editor(self):
        bar = ttk.Frame(self.editor_tab, padding=(8, 8))
        bar.pack(fill='x')
        ttk.Label(bar, text='Fase:').pack(side='left')
        combo = ttk.Combobox(bar, textvariable=self.stage_string,
                             values=[f'Fase {i}' for i in range(1, 9)], width=11, state='readonly')
        combo.pack(side='left', padx=6)
        combo.bind('<<ComboboxSelected>>', lambda e: self.change_stage())
        ttk.Label(bar, text='Zoom do mapa:').pack(side='left', padx=(12, 0))
        zoom = ttk.Combobox(bar, textvariable=self.zoom, width=4, state='readonly', values=[1, 2, 3])
        zoom.pack(side='left', padx=6)
        zoom.bind('<<ComboboxSelected>>', lambda e: self.load_stage())
        ttk.Button(bar, text='Salvar regras em JSON', command=self.save_rules).pack(side='right', padx=4)
        ttk.Button(bar, text='Descartar alterações', command=self.discard).pack(side='right', padx=4)

        pane = ttk.Panedwindow(self.editor_tab, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(pane)
        right = ttk.Frame(pane, padding=(9, 4))
        pane.add(left, weight=3)
        pane.add(right, weight=2)
        self.map_canvas = tk.Canvas(left, bg='#151515', highlightthickness=0, width=670)
        xbar = ttk.Scrollbar(left, orient='horizontal', command=self.map_canvas.xview)
        ybar = ttk.Scrollbar(left, orient='vertical', command=self.map_canvas.yview)
        self.map_canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.map_canvas.grid(row=0, column=0, sticky='nsew')
        ybar.grid(row=0, column=1, sticky='ns')
        xbar.grid(row=1, column=0, sticky='ew')
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.map_canvas.bind('<Button-1>', self.on_map_click)
        self.map_canvas.bind('<MouseWheel>', self.wheel)
        self.map_canvas.bind('<Button-4>', lambda e:self.map_canvas.yview_scroll(-3, 'units'))
        self.map_canvas.bind('<Button-5>', lambda e:self.map_canvas.yview_scroll(3, 'units'))

        ttk.Label(right, textvariable=self.tile_info, font=('Sans', 11, 'bold')).pack(anchor='w')
        ttk.Label(right, text='Fonte da extração  ·  Sem dither  ·  Nova conversão',
                  foreground='#666').pack(anchor='w', pady=(5, 2))
        images = ttk.Frame(right)
        images.pack(fill='x')
        self.preview_labels = []
        for name in ('Fonte RGB333', 'Sem dithering', 'Prévia escolhida'):
            frame = ttk.Frame(images)
            frame.pack(side='left', padx=4)
            img = ttk.Label(frame, text='Selecione\num bloco', anchor='center', justify='center', width=13)
            img.pack()
            ttk.Label(frame, text=name, foreground='#777', font=('Sans', 9)).pack(pady=(2, 0))
            self.preview_labels.append(img)
        # Clique em qualquer pixel das duas prévias para editar seu pen original.
        for preview in (self.preview_labels[0],self.preview_labels[2]):
            preview.bind('<Button-1>',self.on_source_pixel_click)
        ttk.Label(right, text='Contexto: somente o bloco central é atualizado na prévia',
                  foreground='#777', font=('Sans', 9)).pack(anchor='w', pady=(9, 2))
        self.context_label = ttk.Label(right, text='Clique em um bloco para ver o contexto.')
        self.context_label.pack(anchor='w')
        rule_row = ttk.Frame(right)
        rule_row.pack(fill='x', pady=(10, 6))
        ttk.Label(rule_row, text='Tratamento:').pack(side='left')
        self.tile_combo = ttk.Combobox(rule_row, state='readonly', textvariable=self.tile_mode,
                                       values=POLICIES, width=21)
        self.tile_combo.pack(side='left', padx=7)
        self.tile_combo.bind('<<ComboboxSelected>>', lambda e: self.tile_mode_changed())
        ttk.Button(rule_row,text='Cores do Bayer...',command=self.open_color_editor).pack(side='left',padx=3)
        self.tile_help = ttk.Label(right, text='', foreground='#777', wraplength=440)
        self.tile_help.pack(anchor='w')
        editor_sliders = ttk.LabelFrame(right, text='Parâmetros do algoritmo selecionado (prévia em tempo real)', padding=6)
        editor_sliders.pack(fill='x', pady=(7, 0))
        self.tile_slider_holder=ttk.Frame(editor_sliders)
        self.tile_slider_holder.pack(fill='x')
        self.tile_mode_vars={mode:{key:tk.DoubleVar(value=default)
                            for key,_,default,_,_,_ in defs}
                            for mode,defs in MODE_PARAMS.items()}
        # O modo adaptativo mantem as variaveis ja usadas no Lab 2.0.
        self.tile_mode_vars['bayer4_adaptive']=self.tile_values
        self.tile_sliders=[]
        buttons = ttk.Frame(right)
        buttons.pack(fill='x', pady=8)
        self.apply_button = ttk.Button(buttons, text='Aplicar ao código', command=self.apply_tile)
        self.apply_button.pack(side='left', padx=(0, 5))
        ttk.Button(buttons, text='Herdar da fase', command=self.restore_tile).pack(side='left')
        ttk.Label(right, textvariable=self.edited_flag, foreground='#666', wraplength=440).pack(anchor='w')
        ttk.Label(right,
                  text='As regras valem para todas as ocorrências do código nesta fase.\n'
                       'A compilação lê o JSON; nenhum gráfico é regravado enquanto você edita.',
                  foreground='#777', wraplength=440, justify='left').pack(anchor='w', pady=(8, 0))
        self.tile_mode_changed()

    def create_builder(self):
        area = ttk.Frame(self.build_tab, padding=12)
        area.pack(fill='both', expand=True)
        row = ttk.Frame(area)
        row.pack(fill='x')
        ttk.Label(row, text='Algoritmo geral:').pack(side='left')
        self.combo = ttk.Combobox(row, values=MODES, textvariable=self.mode, state='readonly', width=24)
        self.combo.pack(side='left', padx=7)
        self.combo.bind('<<ComboboxSelected>>', lambda e: self.on_global_mode_selected())
        ttk.Button(row, text='Salvar preset geral', command=self.save_preset).pack(side='right', padx=3)
        ttk.Button(row, text='Carregar preset geral', command=self.load_preset).pack(side='right', padx=3)
        self.controls = ttk.LabelFrame(area, text='Sliders gerais do modo adaptativo', padding=7)
        self.controls.pack(fill='x', pady=12)
        self.sliders = []
        for key, name, default, low, high, step in PARAMS:
            line = ttk.Frame(self.controls)
            line.pack(fill='x', pady=2)
            label = ttk.Label(line, text=name + ' ⓘ', width=32)
            label.pack(side='left')
            scale = tk.Scale(line, variable=self.values[key], from_=low, to=high,
                             resolution=step, orient='horizontal', length=400, command=lambda v: self.global_param_changed())
            scale.pack(side='left', expand=True, fill='x')
            Tooltip(label, HELP[key]); Tooltip(scale, HELP[key])
            self.sliders.append(scale)
        actions = ttk.Frame(area)
        actions.pack(fill='x', pady=(0, 9))
        self.build_button = ttk.Button(actions, text='Gerar ROM com estas regras', command=self.start_build)
        self.build_button.pack(side='left')
        ttk.Button(actions, text='Abrir pasta de ROMs', command=self.open_roms).pack(side='left', padx=8)
        self.progress = ttk.Progressbar(actions, mode='indeterminate', length=180)
        self.progress.pack(side='right')
        self.state_label = ttk.Label(area, text='Pronto.')
        self.state_label.pack(anchor='w')
        logs = ttk.LabelFrame(area, text='Saída da compilação', padding=6)
        logs.pack(fill='both', expand=True, pady=(6, 0))
        self.log = tk.Text(logs, height=10, wrap='word', state='disabled', font=('Monospace', 9))
        scroll = ttk.Scrollbar(logs, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.log.pack(fill='both', expand=True)
        ttk.Label(area, text='O módulo dither_bg.py é restaurado ao fim da compilação. Evite builds paralelos.',
                  foreground='#777').pack(anchor='w', pady=5)
        self.toggle()

    def on_global_mode_selected(self):
        # Uma escolha explicita do Adaptive usa os valores originais.
        # Carregar preset chama toggle() diretamente e preserva o JSON.
        if self.mode.get() == 'bayer4_adaptive':
            for key, _label, default, _low, _high, _step in PARAMS:
                self.values[key].set(default)
        self.toggle()

    def toggle(self):
        super().toggle()
        self.refresh_preview()

    def global_param_changed(self):
        if self.tile_mode.get() == 'inherit':
            self.refresh_preview()

    def change_stage(self):
        self.close_color_editor()
        self.stage = int(self.stage_string.get().split()[-1]) - 1
        self.current = None
        self.load_stage()

    def load_stage(self):
        self.data = None
        self.codes = None
        self.current = None
        self.map_canvas.delete('all')
        source_path = self.project / f'reports/dither_lab_source{self.stage}.npz'
        image_path = self.project / f'reports/tile_selector_stage{self.stage+1}.png'
        if not source_path.exists() or not image_path.exists():
            self.info.set(f'Fase {self.stage+1}: faltam prévias. Execute make assets após instalar o Dithering Lab 2.0.')
            self.tile_info.set('Fase ainda não exportada')
            return
        try:
            with np.load(source_path, allow_pickle=False) as dat:
                self.data = {key: dat[key].copy() for key in dat.files}
            self.codes = self.data['codes']
            self.source_image = Image.open(image_path).convert('RGB')
            expected_size = (self.codes.shape[1]*16, self.codes.shape[0]*16)
            if self.source_image.size != expected_size:
                raise ValueError(f'Imagem {self.source_image.size} diferente de {expected_size}')
            requested_zoom = int(self.zoom.get())
            z = requested_zoom
            while z > 1 and self.source_image.width * z * self.source_image.height * z > 42_000_000:
                z -= 1
            if z != requested_zoom:
                self.zoom.set(z)
                self.info.set(f'Zoom limitado a {z}× para economizar memória.')
            view = self.source_image if z == 1 else self.source_image.resize(
                (self.source_image.width*z, self.source_image.height*z), Image.Resampling.NEAREST)
            self.map_photo = ImageTk.PhotoImage(view)
            self.map_canvas.create_image(0, 0, anchor='nw', image=self.map_photo, tags='bg')
            self.map_canvas.configure(scrollregion=(0,0,view.width,view.height))
            self.tile_info.set('Clique num bloco de 16×16 pixels')
            self.info.set(f'Fase {self.stage+1}: mapa de {self.codes.shape[1]}×{self.codes.shape[0]} blocos.\n'
                          'Clique para selecionar um código original.')
        except Exception as exc:
            self.data = None
            self.info.set(f'Erro ao abrir dados da fase {self.stage+1}: {exc}')

    def wheel(self, event):
        units = -3 if event.delta > 0 else 3
        if event.state & 1:
            self.map_canvas.xview_scroll(units, 'units')
        else:
            self.map_canvas.yview_scroll(units, 'units')

    def on_map_click(self, event):
        self.close_color_editor()
        if self.data is None:
            return
        z = int(self.zoom.get())
        x = int(self.map_canvas.canvasx(event.x)) // (16*z)
        y = int(self.map_canvas.canvasy(event.y)) // (16*z)
        if not (0 <= y < self.codes.shape[0] and 0 <= x < self.codes.shape[1]):
            return
        code = int(self.codes[y,x])
        p = int(self.data['palettes'][y,x])
        flip = bool(self.data['flips'][y,x])
        if code >= len(self.data['tiles']):
            messagebox.showerror('Índice inválido', f'Tile {code} indisponível nos dados exportados.')
            return
        self.current = (x,y,code,p,flip)
        self.load_selected()
        self.mark_occurrences()

    def mark_occurrences(self):
        self.map_canvas.delete('marker')
        if self.current is None or self.codes is None:
            return
        x,y,code,_,_ = self.current
        zoom = int(self.zoom.get())
        step = 16*zoom
        yy, xx = np.where(self.codes == code)
        for row, col in zip(yy, xx):
            self.map_canvas.create_rectangle(int(col*step), int(row*step),
                                             int((col+1)*step-1), int((row+1)*step-1),
                                             outline='#30a6ed', width=1, tags='marker')
        self.map_canvas.create_rectangle(x*step, y*step, (x+1)*step-1, (y+1)*step-1,
                                         outline='#ffcb48', width=3, tags='marker')

    def load_selected(self):
        if self.current is None:
            return
        x,y,code,p,flip=self.current
        stage=str(self.stage)
        protected=code in self.legacy.get(stage,[])
        rule=self.rules['stages'][stage].get(str(code))
        self.palette_overrides=copy.deepcopy(rule.get('palette_overrides',{})) if rule else {}
        mode='original' if protected else (rule['mode'] if rule else 'inherit')
        self.tile_mode.set(mode)
        for m,defs in MODE_PARAMS.items():
            if m=='original':
                continue
            vals=mode_defaults(m)
            if m=='bayer4_adaptive':
                vals={key:float(var.get()) for key,var in self.values.items()}
            if rule and m==mode and 'parameters' in rule:
                vals=rule['parameters']
            for key,var in self.tile_mode_vars[m].items():
                var.set(vals[key])
        n=int(np.count_nonzero(self.codes==code))
        self.tile_info.set(f'Fase {self.stage+1} | Código {code} / 0x{code:03X} | Paleta {p}\n'
                           f'Bloco ({x},{y}) · {n} ocorrências')
        self.tile_mode_changed()

    def _mode_values(self, mode):
        return {key:float(var.get()) for key,var in self.tile_mode_vars[mode].items()}

    def _draw_tile_sliders(self):
        for child in self.tile_slider_holder.winfo_children():
            child.destroy()
        self.tile_sliders=[]
        selected=self.tile_mode.get()
        effective=self.mode.get() if selected=='inherit' else selected
        if effective=='original':
            ttk.Label(self.tile_slider_holder,
                      text='Original: conversão direta sem parâmetros de dithering.',
                      foreground='#777').pack(anchor='w',pady=8)
            return
        if effective not in MODE_PARAMS:
            return
        if selected=='inherit' and effective=='bayer4_adaptive':
            # O bloco com heranca usa os valores gerais do adaptativo na previa.
            for key,var in self.values.items():
                self.tile_mode_vars[effective][key].set(var.get())
        for key,name,default,low,high,step in MODE_PARAMS[effective]:
            line=ttk.Frame(self.tile_slider_holder)
            line.pack(fill='x',pady=1)
            label=ttk.Label(line,text=name+' ⓘ',width=28)
            label.pack(side='left')
            scale=tk.Scale(line,variable=self.tile_mode_vars[effective][key],
                           from_=low,to=high,resolution=step,
                           orient='horizontal',showvalue=True,length=150,
                           command=lambda v:self.on_tile_mode_slider())
            scale.pack(side='left',fill='x',expand=True)
            info=MODE_HELP.get(effective,{}).get(key,HELP.get(key,''))
            if info:
                Tooltip(label,info);Tooltip(scale,info)
            if selected=='inherit':
                # Promove para o proprio modo quando editado — nunca forca adaptive.
                scale.bind('<ButtonPress-1>',lambda e:self.promote_inherited_mode(),add='+')
                scale.bind('<KeyPress>',lambda e:self.promote_inherited_mode(),add='+')
                scale.bind('<MouseWheel>',lambda e:self.promote_inherited_mode(),add='+')
                scale.bind('<Button-4>',lambda e:self.promote_inherited_mode(),add='+')
                scale.bind('<Button-5>',lambda e:self.promote_inherited_mode(),add='+')
            self.tile_sliders.append(scale)

    def promote_inherited_mode(self):
        if self.current is not None and self.tile_mode.get()=='inherit':
            mode=self.mode.get()
            if mode!='original':
                self.tile_mode.set(mode)
                self.tile_help.configure(text='Editando '+mode+' somente neste código. Clique em Aplicar ao código para confirmar.')

    def on_tile_mode_slider(self):
        # Sliders de Bayer4 continuam Bayer4, do Balanced continuam Balanced.
        self.promote_inherited_mode()
        self.refresh_preview()

    def tile_mode_changed(self):
        mode=self.tile_mode.get()
        if mode=='inherit':
            help_text='Herdar utiliza o modo geral. Um ajuste local cria uma regra deste MESMO algoritmo.'
        elif mode=='original':
            help_text='Sem dithering: preserva o mapeamento original do código selecionado.'
        else:
            help_text='Os sliders editam '+mode+' sem trocar de algoritmo. Aplique ao código para salvar.'
        self.tile_help.configure(text=help_text)
        self._draw_tile_sliders()
        self.refresh_preview()

    def activate_tile_adaptive(self):
        self.promote_inherited_mode()

    def on_tile_slider_key(self, event):
        self.promote_inherited_mode()

    def _preview_pixels(self, code, p, flip, mode, params, palette_overrides=None):
        d=self.data
        pens=d['tiles'][code]
        source=d['source_palettes'][p]
        group=int(d['groups'][p])
        target=d['target_palettes'][group]
        mapping=d['mappings'][p]
        if mode=='original':
            out=mapping[pens].copy()
        elif mode=='bayer4':
            out=bayer4_custom(pens,source,target,params)
        elif mode=='bayer4_soft':
            out=soft_custom(pens,source,target,mapping,params)
        elif mode=='bayer4_adaptive':
            out=adaptive_custom(pens,source,target,mapping,params)
        else:
            raise ValueError('Modo de prévia inválido: '+str(mode))
        if palette_overrides and mode!='original':
            out=apply_palette_overrides(out,pens,mapping,palette_overrides)
        if self.stage in (4,6):
            out[pens==15]=0
        if self.stage==4 and 0x380<=code<=0x3df:
            out[:]=0
        if self.stage==6 and (0x580<=code<=0x59f or code==0x500):
            out[:]=0
        rgb_source=source[pens]
        palette=np.concatenate((np.zeros((1,3),dtype=np.uint8),target),axis=0)
        rgb_result=palette[out]
        if flip:
            rgb_source=rgb_source[:,::-1]
            rgb_result=rgb_result[:,::-1]
        return (np.uint8(rgb_source.astype(np.uint16)*255//7),
                np.uint8(rgb_result.astype(np.uint16)*255//7))

    def refresh_preview(self):
        if self.current is None or self.data is None:
            return
        try:
            x,y,code,p,flip=self.current
            selected=self.tile_mode.get()
            mode=self.mode.get() if selected=='inherit' else selected
            if mode=='bayer4_adaptive' and selected=='inherit':
                params={key:float(var.get()) for key,var in self.values.items()}
            elif mode=='original':
                params={}
            else:
                params=self._mode_values(mode)
            src,mapped=self._preview_pixels(code,p,flip,'original',{})
            _,converted=self._preview_pixels(code,p,flip,mode,params,
                               self.palette_overrides.get(str(p),{}))
            self.photo_preview=[]
            for label,im in zip(self.preview_labels,(src,mapped,converted)):
                img=Image.fromarray(im,mode='RGB').resize((128,128),Image.Resampling.NEAREST)
                photo=ImageTk.PhotoImage(img)
                self.photo_preview.append(photo)
                label.configure(image=photo,text='')
            px,py=x*16,y*16
            box=(max(0,px-32),max(0,py-32),min(self.source_image.width,px+48),min(self.source_image.height,py+48))
            context=self.source_image.crop(box)
            context.paste(Image.fromarray(converted,mode='RGB'),(px-box[0],py-box[1]))
            factor=min(4,max(1,320//max(context.size)))
            context=context.resize((context.width*factor,context.height*factor),Image.Resampling.NEAREST)
            photo=ImageTk.PhotoImage(context)
            self.context_photo=photo
            self.context_label.configure(image=photo,text='')
            self.edited_flag.set('Prévia: '+MODES_LABELS.get(mode,mode)+' · código '+str(code))
        except Exception as exc:
            self.edited_flag.set('Não foi possível gerar prévia: '+str(exc))

    def apply_tile(self):
        if self.current is None:
            messagebox.showinfo('Seleção','Selecione primeiro um bloco no mapa.')
            return
        _,_,code,_,_=self.current
        stage=str(self.stage)
        mode=self.tile_mode.get()
        if self.palette_overrides and mode=='inherit':
            mode=self.mode.get()
            self.tile_mode.set(mode)
        if self.palette_overrides and mode=='original':
            messagebox.showerror('Regra de cores','O modo Original não aceita pares manuais.')
            return
        protected=set(self.legacy[stage])
        protected.discard(code)
        self.rules['stages'][stage].pop(str(code),None)
        if mode=='original':
            protected.add(code)
        elif mode!='inherit':
            entry={'mode':mode}
            if MODE_PARAMS[mode]:
                entry['parameters']=validate_mode_params(mode,self._mode_values(mode))
            if self.palette_overrides:
                from dither_tile_policy import validate_palette_overrides
                entry['palette_overrides']=validate_palette_overrides(self.palette_overrides)
            self.rules['stages'][stage][str(code)]=entry
        self.legacy[stage]=sorted(protected)
        self.unsaved=True
        self.edited_flag.set(f'Regra do código {code} aplicada na memória. Salve as regras em JSON.')
        self.mark_occurrences()

    # ---- Seletor de cores por pen original --------------------------------
    def close_color_editor(self):
        win=getattr(self,'color_window',None)
        self.color_window=None
        if win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
            except tk.TclError:
                pass

    def _palette_target(self):
        _,_,_,p,_=self.current
        group=int(self.data['groups'][p])
        return self.data['target_palettes'][group]

    def _valid_source_pens(self):
        if self.current is None:
            return []
        _,_,code,_,_=self.current
        pens=sorted(int(x) for x in np.unique(self.data['tiles'][code]))
        if self.stage in (4,6):
            pens=[v for v in pens if v!=15]
        return pens

    def on_source_pixel_click(self,event):
        if self.current is None or self.data is None:
            return
        x,y,code,p,flip=self.current
        px=max(0,min(15,int(event.x)//8))
        py=max(0,min(15,int(event.y)//8))
        if flip:
            px=15-px
        pen=int(self.data['tiles'][code,py,px])
        if pen not in self._valid_source_pens():
            self.edited_flag.set('Pixel transparente: escolha outro pixel da prévia.')
            return
        self.color_requested_pen=pen
        if self.color_window is not None and self.color_window.winfo_exists():
            self.color_source_pen.set(str(pen))
            self._color_sync_dialog()
            self.color_window.lift()
        else:
            self.open_color_editor()

    def _suggest_secondary(self, source_pen):
        _,_,code,p,_=self.current
        palette=self._palette_target()
        mapping=self.data['mappings'][p]
        primary=int(mapping[source_pen])
        if primary<1 or primary>15:
            primary=1
        source=self.data['source_palettes'][p][source_pen].astype(float)
        first=palette[primary-1].astype(float)
        distances=np.sum((palette.astype(float)-source)**2,axis=1)
        candidates=sorted((float(d),i+1) for i,d in enumerate(distances) if i+1!=primary)
        return candidates[0][1] if candidates else primary

    def open_color_editor(self):
        if self.current is None:
            messagebox.showinfo('Seleção','Clique em um bloco do mapa antes de editar suas cores.')
            return
        if self.tile_mode.get()=='original' or (self.tile_mode.get()=='inherit' and self.mode.get()=='original'):
            messagebox.showinfo('Modo Original','Selecione Bayer4, Balanced ou Adaptive antes de escolher pares manuais.')
            return
        if self.color_window is not None and self.color_window.winfo_exists():
            self.color_window.lift()
            return
        self.color_window=tk.Toplevel(self)
        win=self.color_window
        win.title('Black Tiger MD — Par de cores Bayer por pen')
        win.resizable(True, True)
        win.transient(self)
        win.protocol('WM_DELETE_WINDOW',self.close_color_editor)
        self.color_kind=tk.StringVar(value='auto')
        self.color_source_pen=tk.StringVar(value='0')
        self.color_primary=tk.IntVar(value=1)
        self.color_secondary=tk.IntVar(value=2)
        self.color_mix=tk.DoubleVar(value=35)
        self._color_sync=True
        frame=ttk.Frame(win,padding=12)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Escolha QUAL cor original do bloco será ajustada',font=('Sans',11,'bold')).pack(anchor='w')
        ttk.Label(frame,text='Clique em um pixel na prévia principal ou selecione o pen abaixo. '
                  'As alterações valem apenas para este pen, nesta paleta e neste código.',wraplength=730).pack(anchor='w',pady=3)
        line=ttk.Frame(frame)
        line.pack(fill='x',pady=6)
        ttk.Label(line,text='Pen original:').pack(side='left')
        self.color_pen_combo=ttk.Combobox(line,textvariable=self.color_source_pen,width=5,
                state='readonly',values=[str(x) for x in self._valid_source_pens()])
        self.color_pen_combo.pack(side='left',padx=6)
        self.color_pen_combo.bind('<<ComboboxSelected>>',lambda e:self._color_sync_dialog())
        self.color_source_label=ttk.Label(line,text='')
        self.color_source_label.pack(side='left',padx=12)
        choices=ttk.Frame(frame)
        choices.pack(fill='x',pady=(4,4))
        for key,title in [('auto','Automático'),('secondary','Secundária manual'),('pair','Par manual')]:
            ttk.Radiobutton(choices,text=title,variable=self.color_kind,value=key,
                            command=self._color_rule_changed).pack(side='left',padx=9)
        ttk.Label(frame,text='Clique nas amostras de cores do Mega Drive. Índice 0 é reservado para transparência.').pack(anchor='w')
        self.color_grids={}
        for item,caption in [('primary','Cor primária (clicar ativa Par manual)'),
                             ('secondary','Cor secundária (clicar ativa Secundária manual)')]:
            row=ttk.Frame(frame)
            row.pack(fill='x',pady=3)
            ttk.Label(row,text=caption,width=39).pack(side='left')
            grid=ttk.Frame(row)
            grid.pack(side='left')
            self.color_grids[item]=[]
            for i in range(1,16):
                btn=tk.Button(grid,text=str(i),width=2,height=1,padx=0,pady=1,
                              command=lambda k=item,n=i:self._color_swatch_clicked(k,n))
                btn.grid(row=0,column=i-1,padx=1)
                self.color_grids[item].append(btn)
        mixrow=ttk.Frame(frame)
        mixrow.pack(fill='x',pady=(12,3))
        ttk.Label(mixrow,text='Pixels da cor secundária (%)',width=30).pack(side='left')
        self.color_mix_scale=tk.Scale(mixrow,variable=self.color_mix,from_=0,to=100,
                                     resolution=1,orient='horizontal',length=410,
                                     command=lambda _:self._color_rule_changed())
        self.color_mix_scale.pack(side='left',fill='x',expand=True)
        self.color_result_label=ttk.Label(frame,text='',foreground='#555',wraplength=720)
        self.color_result_label.pack(anchor='w',pady=(8,3))
        self.color_clip_status=tk.StringVar(value='')
        ttk.Label(frame,textvariable=self.color_clip_status,foreground='#555').pack(anchor='w',pady=(2,0))
        footer=ttk.Frame(frame)
        footer.pack(fill='x',pady=8)
        ttk.Button(footer,text='Aplicar ao código no editor',command=self._color_apply_and_close).pack(side='right',padx=6)
        ttk.Button(footer,text='Fechar (manter prévia)',command=self.close_color_editor).pack(side='right')
        ttk.Button(footer,text='Copiar par',command=self._color_copy_pair).pack(side='left',padx=(0,6))
        self.color_paste_button=ttk.Button(footer,text='Colar par',command=self._color_paste_pair,
                                           state='normal' if self.color_pair_clipboard else 'disabled')
        self.color_paste_button.pack(side='left')
        pens=self._valid_source_pens()
        pen=getattr(self,'color_requested_pen',None)
        if pen not in pens:
            pen=pens[0] if pens else 0
        self.color_source_pen.set(str(pen))
        self._color_sync=False
        self._color_sync_dialog()
        autosize_bayer_dialog(win, min_w=900, min_h=440, pad_w=25, pad_h=25)

    def _color_apply_and_close(self):
        self.apply_tile()
        self.close_color_editor()

    def _color_copy_pair(self):
        """Keep the selected manual pair in memory for reuse across tiles."""
        if self.color_kind.get() != 'pair':
            messagebox.showinfo('Copiar par',
                                'Selecione Par manual antes de copiar as duas cores.',
                                parent=self.color_window)
            return
        palette=tuple(tuple(map(int, rgb)) for rgb in self._palette_target())
        self.color_pair_clipboard={
            'primary':int(self.color_primary.get()),
            'secondary':int(self.color_secondary.get()),
            'mix':float(self.color_mix.get()),
            'palette':palette,
        }
        self.color_paste_button.configure(state='normal')
        self.color_clip_status.set('Par copiado. Selecione outro pen ou tile para colar.')

    def _color_paste_pair(self):
        """Paste a manual pair into the selected source pen, updating its live preview."""
        saved=self.color_pair_clipboard
        if not saved or self.current is None:
            return
        palette=tuple(tuple(map(int, rgb)) for rgb in self._palette_target())
        if palette != saved['palette']:
            if not messagebox.askyesno(
                'Paleta diferente',
                'A paleta de destino é diferente da paleta copiada. '
                'Os índices de cor podem representar outras cores. Colar mesmo assim?',
                parent=self.color_window
            ):
                return
        self._color_sync=True
        try:
            self.color_primary.set(saved['primary'])
            self.color_secondary.set(saved['secondary'])
            self.color_mix.set(saved['mix'])
            self.color_kind.set('pair')
        finally:
            self._color_sync=False
        self._color_rule_changed()
        self.color_clip_status.set('Par colado na prévia. Aplique ao código para confirmar.')

    def _color_sync_dialog(self):
        if self.current is None or self.color_window is None or not self.color_window.winfo_exists():
            return
        self._color_sync=True
        _,_,code,p,_=self.current
        pen=int(self.color_source_pen.get())
        override=self.palette_overrides.get(str(p),{}).get(str(pen))
        primary=int(self.data['mappings'][p,pen])
        primary=primary if 1<=primary<=15 else 1
        secondary=self._suggest_secondary(pen)
        if override:
            primary=int(override.get('primary',primary))
            secondary=int(override['secondary'])
            self.color_kind.set('pair' if 'primary' in override else 'secondary')
            self.color_mix.set(float(override['mix']))
        else:
            self.color_kind.set('auto')
            self.color_mix.set(35)
        self.color_primary.set(primary)
        self.color_secondary.set(secondary)
        src=self.data['source_palettes'][p,pen]
        group=int(self.data['groups'][p])
        self.color_source_label.configure(text=f'RGB333 {tuple(map(int,src))}  ·  paleta original {p} → paleta MD {group}')
        self._color_sync=False
        self._color_repaint()

    def _color_swatch_clicked(self,which,n):
        if which=='primary':
            self.color_primary.set(n)
            self.color_kind.set('pair')
        else:
            self.color_secondary.set(n)
            if self.color_kind.get()=='auto':
                self.color_kind.set('secondary')
        self._color_rule_changed()

    def _color_repaint(self):
        if self.color_window is None or not self.color_window.winfo_exists():
            return
        palette=self._palette_target()
        kind=self.color_kind.get()
        for which,buttons in self.color_grids.items():
            chosen=self.color_primary.get() if which=='primary' else self.color_secondary.get()
            for i,btn in enumerate(buttons,1):
                rgb=(palette[i-1].astype(np.uint16)*255//7).astype(np.uint8)
                hexa='#{:02x}{:02x}{:02x}'.format(*map(int,rgb))
                luminance=(int(rgb[0])*299+int(rgb[1])*587+int(rgb[2])*114)//1000
                active=(chosen==i and (which=='secondary' or kind=='pair'))
                btn.configure(bg=hexa,activebackground=hexa,fg='#101010' if luminance>130 else '#ffffff',
                              activeforeground='#101010' if luminance>130 else '#ffffff',
                              relief='sunken' if active else 'raised',bd=4 if active else 1)
                Tooltip(btn,f'Cor Mega Drive {i}: RGB333 {tuple(map(int,palette[i-1]))}') if not hasattr(btn,'_pal_tooltip') else None
                btn._pal_tooltip=True
        pen=int(self.color_source_pen.get())
        _,_,_,p,_=self.current
        label={'auto':'Automático: o algoritmo escolhe o par para este pen.',
               'secondary':f'Pen {pen}: primária automática + secundária {self.color_secondary.get()}, {self.color_mix.get():.0f}%.',
               'pair':f'Pen {pen}: primária {self.color_primary.get()} + secundária {self.color_secondary.get()}, {self.color_mix.get():.0f}%.'}[kind]
        self.color_result_label.configure(text=label+'  ·  Pressione “Aplicar ao código” e depois “Salvar regras em JSON”.')

    def _color_rule_changed(self):
        if getattr(self,'_color_sync',False) or self.current is None:
            return
        selected=self.tile_mode.get()
        if selected=='inherit':
            self.promote_inherited_mode()
        if self.tile_mode.get()=='original':
            self.edited_flag.set('Modo Original não aceita pares manuais. Escolha um Bayer.')
            return
        _,_,code,p,_=self.current
        pen=str(int(self.color_source_pen.get()))
        rule_bank=self.palette_overrides.setdefault(str(p),{})
        kind=self.color_kind.get()
        if kind=='auto':
            rule_bank.pop(pen,None)
            if not rule_bank:
                self.palette_overrides.pop(str(p),None)
        else:
            record={'secondary':self.color_secondary.get(),'mix':float(self.color_mix.get())}
            if kind=='pair':
                record['primary']=self.color_primary.get()
            rule_bank[pen]=record
        self._color_repaint()
        self.refresh_preview()
        self.edited_flag.set(f'Cores do código {code} ajustadas na prévia. Clique em Aplicar ao código para confirmar.')

    def restore_tile(self):
        if self.current is None:
            return
        self.tile_mode.set('inherit')
        self.palette_overrides={}
        self.apply_tile()
        self.tile_mode_changed()

    def save_rules(self):
        try:
            from dither_tile_policy import normalize_rules
            validated=normalize_rules(self.rules)
            # Sempre gerar backups antes da escrita, inclusive do JSON legado.
            for path in (self.rules_path, self.legacy_path):
                if path.exists():
                    path.with_name(path.name+'.lab2.bak').write_bytes(path.read_bytes())
            self.rules_path.write_text(json.dumps(validated, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
            self.legacy_path.write_text(json.dumps(self.legacy, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
            self.unsaved = False
            self.info.set('Regras salvas em tools/tile_dither_rules.json e tools/no_dither_tiles.json.')
        except Exception as exc:
            messagebox.showerror('Erro salvando regras', str(exc))
            raise

    def discard(self):
        if self.unsaved and not messagebox.askyesno('Descartar', 'Descartar todas as regras ainda não salvas?'):
            return
        self.rules = load_all(self.rules_path)
        self.legacy = self._load_legacy()
        self.unsaved = False
        if self.current is not None:
            self.load_selected()
        self.info.set('Alterações não salvas descartadas.')

    def configuration(self):
        config = super().configuration()
        # O digest da ROM inclui toda a selecao salva, nao apenas sliders globais.
        config['tile_rules_sha256'] = hashlib.sha256(self.rules_path.read_bytes()).hexdigest() if self.rules_path.exists() else 'none'
        config['no_dither_sha256'] = hashlib.sha256(self.legacy_path.read_bytes()).hexdigest() if self.legacy_path.exists() else 'none'
        config['rules_count'] = sum(len(items) for items in self.rules['stages'].values()) + sum(len(self.legacy[str(i)]) for i in range(8))
        return config

    def start_build(self):
        if self.unsaved:
            if messagebox.askyesno('Regras não salvas','Salvar as regras antes de gerar a ROM?'):
                try:
                    self.save_rules()
                except Exception:
                    return
            else:
                return
        super().start_build()

    def close(self):
        if self.busy:
            messagebox.showwarning('Compilação em andamento','Aguarde a conclusão para restaurar dither_bg.py com segurança.')
            return
        if self.unsaved and not messagebox.askyesno('Regras não salvas','Existem regras não salvas. Sair mesmo assim?'):
            return
        self.destroy()



# BLACKTIGER_DITHER_LIVE_MAP_V1
from dither_map_live import MapLiveMixin
_BaseLabV2 = LabV2
class LabV2(MapLiveMixin, _BaseLabV2):
    """Dithering Lab 2.0 com todas as regras visíveis no mapa."""
    pass



# BLACKTIGER_PROFILE_IO_V1
from dither_session_io import SessionIOMixin
_BlackTigerLabBeforeProfiles = LabV2
class LabV2(SessionIOMixin, _BlackTigerLabBeforeProfiles):
    """Editor visual com importar/exportar perfis JSON."""
    pass



# BLACKTIGER_BILINGUAL_MAP_EDITOR_V1
from dither_i18n import LanguageMixin
_BlackTigerLabBeforeLanguages = LabV2
class LabV2(LanguageMixin, _BlackTigerLabBeforeLanguages):
    # Map editor with runtime Portuguese/English interface selection.
    pass



# BLACKTIGER_PURE_UNTIL_JSON_V1
# O algoritmo escolhido na interface é puro até uma importação explícita de regras.
# Os JSONs existentes no projeto nunca são modificados por uma compilação.
import tempfile as _profile_tempfile
from dither_session_io import normalize_legacy as _normalize_profile_legacy
from dither_tile_policy import normalize_rules as _normalize_profile_rules

_BlackTigerLabBeforePureProfiles = LabV2
class LabV2(_BlackTigerLabBeforePureProfiles):
    def build_widgets(self):
        self.profile_rules_active = False
        self.profile_source_name = None
        self.profile_status = tk.StringVar(value='MODO PURO — regras por tile desativadas')
        self._build_profile_snapshot = None
        self._profile_build_env = {'BLACKTIGER_TILE_PROFILE': 'pure'}
        super().build_widgets()
        self._reset_to_pure_rules()
        self._previous_mode = self.mode.get()
        self.info.set('Modo puro: escolha um algoritmo. Para ativar regras individuais, use Importar JSON…')
        self._update_profile_status()

    def create_builder(self):
        super().create_builder()
        label = ttk.Label(self.build_tab, textvariable=self.profile_status, foreground='#3767a0')
        label.pack(fill='x', padx=12, pady=4, before=self.build_tab.winfo_children()[0])

    def _update_profile_status(self):
        if self.profile_rules_active:
            self.profile_status.set('PERFIL IMPORTADO ATIVO — ' + str(self.profile_source_name))
        else:
            self.profile_status.set('MODO PURO — regras por tile desativadas')

    def import_profile(self):
        super().import_profile()
        self._update_profile_status()

    def _reset_to_pure_rules(self):
        self.rules = {'version': 1, 'stages': {str(i): {} for i in range(8)}}
        self.legacy = {str(i): [] for i in range(8)}
        self.profile_rules_active = False
        self.profile_source_name = None
        self.unsaved = False
        self.current = None
        self.load_stage()
        self._update_profile_status()

    def toggle(self):
        super().toggle()
        self._previous_mode = self.mode.get()

    def on_global_mode_selected(self):
        if self.busy:
            self.mode.set(getattr(self, '_previous_mode', 'bayer4_adaptive'))
            self.toggle()
            return
        if self.unsaved and not messagebox.askyesno(
            'Voltar ao modo puro',
            'As alterações de regras em memória deixarão de estar ativas. '
            'Os arquivos JSON salvos não serão alterados. Continuar?', parent=self
        ):
            self.mode.set(getattr(self, '_previous_mode', 'bayer4_adaptive'))
            self.toggle()
            return
        self._reset_to_pure_rules()
        super().on_global_mode_selected()  # restaura os 6 valores originais do Adaptive
        self.info.set('Algoritmo puro selecionado. As regras pessoais só entram após Importar JSON…')

    def save_rules(self):
        if not self.profile_rules_active:
            messagebox.showwarning(
                'Modo puro',
                'Para editar e salvar regras personalizadas, importe primeiro seu JSON. '
                'As regras já salvas no projeto foram preservadas.', parent=self
            )
            return
        return super().save_rules()

    def discard(self):
        if not self.profile_rules_active:
            if self.unsaved and not messagebox.askyesno(
                'Descartar', 'Descartar alterações ainda não salvas?', parent=self
            ):
                return
            self._reset_to_pure_rules()
            return
        return super().discard()

    def configuration(self):
        config = super().configuration()
        if self.profile_rules_active:
            rules = _normalize_profile_rules(self.rules)
            legacy = _normalize_profile_legacy(self.legacy)
            encoded_rules = json.dumps(rules, sort_keys=True, ensure_ascii=False).encode('utf-8')
            encoded_legacy = json.dumps(legacy, sort_keys=True, ensure_ascii=False).encode('utf-8')
            config['tile_rules_sha256'] = hashlib.sha256(encoded_rules).hexdigest()
            config['no_dither_sha256'] = hashlib.sha256(encoded_legacy).hexdigest()
            config['rules_count'] = (sum(map(len, rules['stages'].values()))
                                     + sum(map(len, legacy.values())))
            config['tile_profile'] = 'imported'
            config['profile_source'] = self.profile_source_name
        else:
            config['tile_rules_sha256'] = 'disabled'
            config['no_dither_sha256'] = 'disabled'
            config['rules_count'] = 0
            config['tile_profile'] = 'pure'
        return config

    def start_build(self):
        if self.busy:
            return
        if not self.profile_rules_active and self.unsaved:
            if not messagebox.askyesno(
                'Compilar algoritmo puro',
                'Há alterações no editor que não foram importadas como perfil. '
                'Elas NÃO serão aplicadas. Gerar ROM pura mesmo assim?', parent=self
            ):
                return
        if self.profile_rules_active:
            try:
                self._build_profile_snapshot = (
                    _normalize_profile_rules(self.rules),
                    _normalize_profile_legacy(self.legacy)
                )
            except Exception as exc:
                messagebox.showerror('Regras inválidas', str(exc), parent=self)
                return
        else:
            self._build_profile_snapshot = None
        # Pula apenas a exigência antiga de gravar regras no disco antes do build.
        # O worker compila uma cópia temporária da configuração importada.
        Lab.start_build(self)

    def worker(self, config):
        snapshot = self._build_profile_snapshot
        self._profile_build_env = {'BLACKTIGER_TILE_PROFILE': 'pure'}
        if snapshot is None:
            try:
                return super().worker(config)
            finally:
                self._profile_build_env = {'BLACKTIGER_TILE_PROFILE': 'pure'}
        local = self.project / '.local'
        local.mkdir(parents=True, exist_ok=True)
        with _profile_tempfile.TemporaryDirectory(prefix='dither-imported-', dir=local) as td:
            rule_file = Path(td) / 'tile_dither_rules.json'
            legacy_file = Path(td) / 'no_dither_tiles.json'
            rule_file.write_text(json.dumps(snapshot[0], ensure_ascii=False), encoding='utf-8')
            legacy_file.write_text(json.dumps(snapshot[1], ensure_ascii=False), encoding='utf-8')
            self._profile_build_env = {
                'BLACKTIGER_TILE_PROFILE': 'loaded',
                'BLACKTIGER_TILE_RULES_FILE': str(rule_file),
                'BLACKTIGER_NO_DITHER_FILE': str(legacy_file),
            }
            try:
                return super().worker(config)
            finally:
                self._profile_build_env = {'BLACKTIGER_TILE_PROFILE': 'pure'}

    def run(self, args, env):
        isolated_env = dict(env)
        isolated_env.update(self._profile_build_env)
        return super().run(args, isolated_env)



# BLACKTIGER_SELECTED_ALGORITHM_MAP_PREVIEW_V1
# Reconstroi o mapa a partir dos dados originais, nao da ultima compilacao.
# Os overlays continuam disponiveis para edicoes interativas por tile.
_BlackTigerLabBeforeCorrectMap = LabV2
class LabV2(_BlackTigerLabBeforeCorrectMap):
    def build_widgets(self):
        # Evita renderizar duas vezes durante a inicializacao: primeiro a classe
        # anterior le os JSONs do projeto, depois ativa o modo puro.
        self._skip_selected_map_render = True
        self._selected_map_job = None
        try:
            super().build_widgets()
        finally:
            self._skip_selected_map_render = False
        self._cancel_selected_map_job()
        self._render_selected_map()

    def _cancel_selected_map_job(self):
        job = getattr(self, '_selected_map_job', None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._selected_map_job = None

    def _schedule_selected_map(self):
        if getattr(self, '_skip_selected_map_render', False):
            return
        self._cancel_selected_map_job()
        if getattr(self, 'data', None) is not None:
            # Um unico redesenho apos o usuario terminar de mover os sliders.
            self._selected_map_job = self.after(550, self._render_selected_map)

    def _clear_old_tile_preview(self):
        # Sem um tile selecionado, a coluna da direita nao pode exibir uma
        # imagem antiga, que parecia indicar que o perfil ainda estava ativo.
        if getattr(self, 'current', None) is not None:
            return
        for label in getattr(self, 'preview_labels', []):
            label.configure(image='', text='Selecione\num bloco')
        self.photo_preview = []
        if hasattr(self, 'context_label'):
            self.context_label.configure(image='', text='Clique em um bloco para ver o contexto.')
        self.context_photo = None
        if hasattr(self, 'edited_flag'):
            self.edited_flag.set('')

    def _reset_to_pure_rules(self):
        # O mapa ao vivo guarda os codigos ja tocados em memoria. Limpa-los
        # e indispensavel ao trocar do perfil importado para um algoritmo puro.
        if hasattr(self, '_live_touched'):
            self._live_touched = {str(i): set() for i in range(8)}
        if hasattr(self, 'tile_mode'):
            self.tile_mode.set('inherit')
        if hasattr(self, 'palette_overrides'):
            self.palette_overrides = {}
        result = super()._reset_to_pure_rules()
        self._clear_old_tile_preview()
        return result

    def load_stage(self):
        self._cancel_selected_map_job()
        super().load_stage()
        self._clear_old_tile_preview()
        if not getattr(self, '_skip_selected_map_render', False):
            self._render_selected_map()

    def on_global_mode_selected(self):
        # A rotina anterior reseta regras e os sliders do Adaptive. So depois
        # disso recalculamos o mapa, para evitar usar parametros antigos.
        self._cancel_selected_map_job()
        self._skip_selected_map_render = True
        try:
            super().on_global_mode_selected()
        finally:
            self._skip_selected_map_render = False
        self._cancel_selected_map_job()
        self._render_selected_map()

    def toggle(self):
        super().toggle()
        # Tambem cobre o carregamento de presets globais, que chama toggle().
        self._schedule_selected_map()

    def global_param_changed(self):
        super().global_param_changed()
        self._schedule_selected_map()

    def _effective(self, code, live=False):
        # O extrator sempre da prioridade ao modo geral Original.
        if self.mode.get() == 'original':
            return 'original', {}, {}
        return super()._effective(code, live=live)

    def _render_selected_map(self):
        self._selected_map_job = None
        if getattr(self, '_skip_selected_map_render', False):
            return
        if getattr(self, 'data', None) is None or getattr(self, 'codes', None) is None:
            return
        try:
            height, width = self.codes.shape
            # Fonte de verdade: tiles, paletas e flips originais no NPZ.
            # tile_selector_stage*.png pode ter sido criado por outra ROM.
            canvas_image = Image.new('RGB', (width * 16, height * 16))
            palettes = self.data['palettes']
            flips = self.data['flips']
            cache = {}
            for y in range(height):
                for x in range(width):
                    key = (int(self.codes[y, x]), int(palettes[y, x]), bool(flips[y, x]))
                    tile_image = cache.get(key)
                    if tile_image is None:
                        tile_image = self._tile_rgb(*key, live=False)
                        cache[key] = tile_image
                    canvas_image.paste(tile_image, (x * 16, y * 16))
            zoom = int(self.zoom.get())
            if zoom != 1:
                view = canvas_image.resize((width * 16 * zoom, height * 16 * zoom),
                                           Image.Resampling.NEAREST)
            else:
                view = canvas_image
            photo = ImageTk.PhotoImage(view, master=self)
            # Mantem as referencias usadas pelo editor e pela previa de contexto.
            self.source_image = canvas_image
            self.map_photo = photo
            background = self.map_canvas.find_withtag('bg')
            if background:
                self.map_canvas.itemconfigure(background[0], image=photo)
            else:
                self.map_canvas.create_image(0, 0, anchor='nw', image=photo, tags='bg')
            self.map_canvas.tag_lower('bg')
            self.map_canvas.configure(scrollregion=(0, 0, view.width, view.height))
            # Elimina overlays anteriores e redesenha somente os do perfil atual.
            if hasattr(self, '_redraw_all_live'):
                self._redraw_all_live()
            if getattr(self, 'current', None) is not None:
                self._refresh_context_live()
        except Exception as exc:
            self.edited_flag.set('Erro atualizando mapa para o algoritmo escolhido: ' + str(exc))

    def close(self):
        self._cancel_selected_map_job()
        return super().close()

if __name__ == '__main__':
    LabV2().mainloop()
