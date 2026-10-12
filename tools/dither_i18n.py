"""UI-only PT/EN localization for Black Tiger MD Dithering Lab 2.0.

This module does not modify the asset pipeline, dither rules or JSON schema.
It observes Tk widgets and translates their displayed text, plus help tooltips
and the Tk dialogs used by the editor. Internal algorithm identifiers stay intact.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Portuguese source strings -> English interface strings. Exact strings first;
# partial phrases below cover dynamic status text with numeric identifiers.
TEXT = {
    'Prévia por bloco + compilação': 'Per-tile preview + ROM build',
    ' Editor visual dos tiles ': ' Visual tile editor ',
    ' Configuração geral e gerar ROM ': ' Global settings and ROM build ',
    'Fase:': 'Stage:',
    'Zoom do mapa:': 'Map zoom:',
    'Mostrar ajustes no mapa': 'Show edits on map',
    'Salvar regras em JSON': 'Save rules to JSON',
    'Descartar alterações': 'Discard changes',
    'Salvar como…': 'Save as…',
    'Importar JSON…': 'Import JSON…',
    'Perfis completos incluem algoritmo, sliders, cores manuais e exclusões.':
        'Full profiles include the algorithm, sliders, manual colors, and exclusions.',
    'Fonte da extração  ·  Sem dither  ·  Nova conversão':
        'Source artwork  ·  No dithering  ·  New conversion',
    'Fonte RGB333': 'RGB333 source',
    'Sem dithering': 'No dithering',
    'Prévia escolhida': 'Selected preview',
    'Selecione\num bloco': 'Select\na tile',
    'Contexto: somente o bloco central é atualizado na prévia':
        'Context: only the center tile is updated in the preview',
    'Contexto com as regras aplicadas e a prévia atual':
        'Context with applied rules and current preview',
    'Clique em um bloco para ver o contexto.': 'Click a tile to see its surroundings.',
    'Tratamento:': 'Treatment:',
    'Cores do Bayer...': 'Bayer colors…',
    'Parâmetros do algoritmo selecionado (prévia em tempo real)':
        'Selected algorithm parameters (live preview)',
    'Aplicar ao código': 'Apply to tile code',
    'Herdar da fase': 'Inherit from stage',
    'As regras valem para todas as ocorrências do código nesta fase.\n'
    'A compilação lê o JSON; nenhum gráfico é regravado enquanto você edita.':
        'Rules apply to every occurrence of this tile code in the stage.\n'
        'The build reads the JSON; graphics are not rewritten while you edit.',
    'Cada ajuste aplicado aparece em TODAS as ocorrências do código no mapa.\n'
    'O mapa é uma prévia: os arquivos gráficos só mudam ao gerar assets/ROM.':
        'Each applied edit appears at EVERY occurrence of that tile code on the map.\n'
        'The map is a preview: graphics files change only when assets/ROM are built.',
    'Algoritmo geral:': 'Global algorithm:',
    'Salvar preset geral': 'Save global preset',
    'Carregar preset geral': 'Load global preset',
    'Sliders gerais do modo adaptativo': 'Global adaptive sliders',
    'Gerar ROM com estas regras': 'Build ROM with these rules',
    'Abrir pasta de ROMs': 'Open ROM folder',
    'Saída da compilação': 'Build output',
    'O módulo dither_bg.py é restaurado ao fim da compilação. Evite builds paralelos.':
        'The dither_bg.py module is restored after the build. Avoid parallel builds.',
    'Original: conversão direta sem parâmetros de dithering.':
        'Original: direct color conversion, no dithering parameters.',
    'Herdar utiliza o modo geral. Um ajuste local cria uma regra deste MESMO algoritmo.':
        'Inherit uses the global mode. A local change creates a rule for the SAME algorithm.',
    'Sem dithering: preserva o mapeamento original do código selecionado.':
        'No dithering: preserves the selected tile code’s original color mapping.',
    'Herdar algoritmo geral': 'Inherit global algorithm',
    'Original — sem dithering': 'Original — no dithering',
    'Bayer4 completo': 'Full Bayer4',
    'Bayer4 balanced': 'Bayer4 balanced',
    'Bayer4 adaptativo': 'Adaptive Bayer4',
    'Intensidade Bayer (%)': 'Bayer strength (%)',
    'Limite da matriz Bayer': 'Bayer matrix threshold',
    'Erro minimo RGB²': 'Minimum RGB² error',
    'Erro mínimo RGB²': 'Minimum RGB² error',
    'Distância máxima RGB²': 'Maximum RGB² distance',
    'Diferença máxima de luminância': 'Maximum luminance difference',
    'Diferença máx. luminância': 'Maximum luminance difference',
    'Diferenca max. luminancia': 'Maximum luminance difference',
    'Diferenca max. de cor': 'Maximum color difference',
    'Penalização de contraste': 'Contrast penalty',
    'Ganho mínimo': 'Minimum gain',
    'Mistura máxima (%)': 'Maximum mix (%)',
    'Escolha QUAL cor original do bloco será ajustada':
        'Choose WHICH original tile color to adjust',
    'Clique em um pixel na prévia principal ou selecione o pen abaixo. '
    'As alterações valem apenas para este pen, nesta paleta e neste código.':
        'Click a pixel in the main preview or select a source pen below. '
        'Changes apply only to this pen, palette, and tile code.',
    'Pen original:': 'Source pen:',
    'Automático': 'Automatic',
    'Secundária manual': 'Manual secondary',
    'Par manual': 'Manual pair',
    'Cor primária (clicar ativa Par manual)': 'Primary color (click to enable Manual pair)',
    'Cor secundária (clicar ativa Secundária manual)':
        'Secondary color (click to enable Manual secondary)',
    'Clique nas amostras de cores do Mega Drive. Índice 0 é reservado para transparência.':
        'Click the Mega Drive color swatches. Index 0 is reserved for transparency.',
    'Pixels da cor secundária (%)': 'Secondary-color pixels (%)',
    'Aplicar ao código no editor': 'Apply to tile code in editor',
    'Fechar (manter prévia)': 'Close (keep preview)',
    'Copiar par': 'Copy pair',
    'Colar par': 'Paste pair',
    'Par copiado. Selecione outro pen ou tile para colar.':
        'Pair copied. Select another pen or tile to paste.',
    'Par colado na prévia. Aplique ao código para confirmar.':
        'Pair pasted into preview. Apply to tile code to confirm.',
    'Selecione Par manual antes de copiar as duas cores.':
        'Select Manual pair before copying both colors.',
    'Paleta diferente': 'Different palette',
    'A paleta de destino é diferente da paleta copiada. '
    'Os índices de cor podem representar outras cores. Colar mesmo assim?':
        'The target palette differs from the copied palette. '
        'Color indices may represent different colors. Paste anyway?',
    'Automático: o algoritmo escolhe o par para este pen.':
        'Automatic: the algorithm chooses the color pair for this pen.',
    'Black Tiger MD — Par de cores Bayer por pen': 'Black Tiger MD — Bayer color pair per pen',
    'Nenhum bloco selecionado': 'No tile selected',
    'Escolha uma fase e clique em um bloco do cenário.':
        'Choose a stage and click a tile on the map.',
    'Fase ainda não exportada': 'Stage not exported yet',
    'Clique num bloco de 16×16 pixels': 'Click a 16×16-pixel tile',
    'Pronto.': 'Ready.',
    'Índice inválido': 'Invalid index',
    'Seleção': 'Selection',
    'Selecione primeiro um bloco no mapa.': 'First select a tile on the map.',
    'Regra de cores': 'Color rule',
    'O modo Original não aceita pares manuais.':
        'Original mode does not support manual color pairs.',
    'Pixel transparente: escolha outro pixel da prévia.':
        'Transparent pixel: choose another preview pixel.',
    'Clique em um bloco do mapa antes de editar suas cores.':
        'Click a map tile before editing its colors.',
    'Modo Original': 'Original mode',
    'Selecione Bayer4, Balanced ou Adaptive antes de escolher pares manuais.':
        'Select Bayer4, Balanced, or Adaptive before choosing manual color pairs.',
    'Modo Original não aceita pares manuais. Escolha um Bayer.':
        'Original mode does not support manual color pairs. Choose a Bayer mode.',
    'Regras salvas em tools/tile_dither_rules.json e tools/no_dither_tiles.json.':
        'Rules saved to tools/tile_dither_rules.json and tools/no_dither_tiles.json.',
    'Erro salvando regras': 'Error saving rules',
    'Descartar': 'Discard',
    'Descartar todas as regras ainda não salvas?': 'Discard all unsaved rules?',
    'Alterações não salvas descartadas.': 'Unsaved changes discarded.',
    'Regras não salvas': 'Unsaved rules',
    'Salvar as regras antes de gerar a ROM?': 'Save rules before building the ROM?',
    'Existem regras não salvas. Sair mesmo assim?':
        'There are unsaved rules. Exit anyway?',
    'Compilação em andamento': 'Build in progress',
    'Aguarde a conclusão para restaurar dither_bg.py com segurança.':
        'Wait for the build to finish so dither_bg.py can be restored safely.',
    'Aguarde terminar a compilação.': 'Wait for the build to finish.',
    'Erro atualizando mapa: ': 'Error updating map: ',
    'Erro atualizando bloco no mapa: ': 'Error updating map tile: ',
    'Erro restaurando mapa: ': 'Error restoring map: ',
    'Erro aplicando regra ao mapa: ': 'Error applying rule to map: ',
    'Erro na prévia de contexto: ': 'Context preview error: ',
    'Salvar perfil completo do Dithering Lab como…': 'Save full Dithering Lab profile as…',
    'Importar perfil ou regras JSON': 'Import JSON profile or rules',
    'Confirmar importação': 'Confirm import',
    'Arquivo protegido': 'Protected file',
    'Use “Salvar regras em JSON” para atualizar os arquivos ativos do projeto.':
        'Use “Save rules to JSON” to update the project’s active files.',
    'Erro nas regras': 'Rule error',
    'Erro ao exportar': 'Export error',
    'JSON inválido': 'Invalid JSON',
    'JSON muito grande (limite: 4 MB).': 'JSON too large (limit: 4 MB).',
    'Erro ao atualizar editor': 'Error updating editor',
    'Arquivos JSON': 'JSON files',
    'Todos os arquivos': 'All files',
    'algoritmo geral, sliders, regras individuais e exclusões':
        'global algorithm, sliders, per-tile rules, and exclusions',
    'somente regras individuais dos blocos': 'per-tile rules only',
    'somente códigos sem dithering': 'no-dithering tile codes only',
    'somente algoritmo e sliders gerais': 'global algorithm and sliders only',
    'A raiz do JSON deve ser um objeto.': 'The JSON root must be an object.',
    'Configuração geral precisa ser um objeto JSON.':
        'Global configuration must be a JSON object.',
    'As seleções sem dithering devem ser um objeto JSON.':
        'No-dithering selections must be a JSON object.',
    'JSON não reconhecido. Use perfil completo, tile_dither_rules.json, '
    'no_dither_tiles.json ou preset de algoritmo geral.':
        'Unrecognized JSON. Use a full profile, tile_dither_rules.json, '
        'no_dither_tiles.json, or a global algorithm preset.',
    'Formato de perfil desconhecido ou versão incompatível.':
        'Unknown profile format or incompatible version.',
    'A estrutura da aba visual foi alterada; barra de perfis indisponível.':
        'The visual tab layout changed; the profile toolbar is unavailable.',
    'Projeto ou tools/dither_bg.py não encontrado.':
        'Project or tools/dither_bg.py not found.',
    'Falha na geração de assets. Consulte o log.':
        'Asset generation failed. Check the log.',
    'Falha na compilação da ROM. Consulte o log.':
        'ROM compilation failed. Check the log.',
    'Compilação terminou, mas out/release/rom.bin não existe.':
        'Build finished, but out/release/rom.bin does not exist.',
    'Preset inválido': 'Invalid preset',
    'Modo desconhecido': 'Unknown mode',
    'Falha na compilação': 'Build failed',
    'ROM criada': 'ROM built',
    'Gerar ROM': 'Build ROM',
    'Parâmetros do Bayer adaptativo': 'Adaptive Bayer parameters',
    'Algoritmo:': 'Algorithm:',
    'Carregar preset': 'Load preset',
    'Salvar preset': 'Save preset',
    'Durante a compilação, o módulo temporário é restaurado ao terminar. Não execute outra compilação em paralelo.':
        'The temporary module is restored after the build. Do not run parallel builds.',
}

# Translation of all documented slider help texts (including dynamic per-mode
# tooltips). Keys are stable internal names, never translated in JSON.
HELP_EN = {
 'min_error': 'Squared RGB error between the original color and the nearest palette color.\nBelow this threshold, dithering is not applied.\nLower = more eligible areas; higher = more smooth surfaces.',
 'max_distance': 'Squared RGB distance between the two palette colors used in a mix.\nLower = prevents widely separated color pairs; higher = allows more combinations,\nbut may produce more noticeable dots.',
 'max_luma': 'Maximum luminance difference between the mixed colors, on the RGB333 scale.\nLower = protects edges and contrast; higher = allows larger brightness changes.',
 'contrast_penalty': 'Penalty in the score: score = gain - penalty × RGB² distance.\nLower = favors more dithering; higher = discourages contrasting color pairs.',
 'min_score': 'Minimum score required to accept a color mix after the penalty.\nLower = more mixing; higher = only more significant improvements.',
 'max_mix': 'Maximum percentage of pixels that can use the secondary color in the 4×4 Bayer pattern.\nLower = subtler texture; higher = stronger texture.\nThe Bayer grid changes in discrete 6.25% steps, so small adjustments may not be visible.',
}
MODE_HELP_EN = {
 'bayer4': {
   'strength': 'Proportion of the second color in the 4×4 Bayer pattern. 100% reproduces the original Bayer4. Lower strength produces fewer secondary-color pixels; 0% keeps only the closest color (not necessarily the original mapping).',
 },
 'bayer4_soft': {
   'strength': 'Controls the strength of Bayer proposals before the Balanced filter.',
   'density': 'How many of the 16 Bayer-matrix positions may accept replacements. 9 reproduces the current Balanced behavior; 0 disables all replacements.',
   'min_error': 'Minimum quantization error required for mixing. Lower values allow more regions.',
   'max_luma': 'Allowed brightness difference between the mapped color and the proposal. Higher values allow stronger contrasts.',
   'max_chroma': 'Maximum RGB333 distance between two colors. Higher values allow more distant colors.',
 },
}

# Dynamic messages built from multiple string fragments or f-strings.
# These are deliberately limited to UI vocabulary, not JSON keys or paths.
PARTS = [
 ('Fase ', 'Stage '),
 (' | Código ', ' | Code '),
 (' | Paleta ', ' | Palette '),
 ('\nBloco (', '\nTile ('),
 (' ocorrências', ' occurrences'),
 ('Bloco (', 'Tile ('),
 (': faltam prévias. Execute make assets após instalar o Dithering Lab 2.0.',
  ': previews are missing. Run make assets after installing Dithering Lab 2.0.'),
 (': mapa de ', ': map of '),
 (' blocos.\nClique para selecionar um código original.',
  ' tiles.\nClick to select an original tile code.'),
 ('Zoom limitado a ', 'Zoom limited to '),
 ('× para economizar memória.', '× to save memory.'),
 ('Erro ao abrir dados da fase ', 'Error opening stage data '),
 (': ', ': '),
 ('Tile ', 'Tile '),
 (' indisponível nos dados exportados.', ' unavailable in exported data.'),
 ('Editando ', 'Editing '),
 (' somente neste código. Clique em Aplicar ao código para confirmar.',
  ' for this tile code only. Click Apply to tile code to confirm.'),
 ('Os sliders editam ', 'The sliders edit '),
 (' sem trocar de algoritmo. Aplique ao código para salvar.',
  ' without changing the algorithm. Apply to the tile code to save.'),
 ('Prévia: ', 'Preview: '),
 (' · código ', ' · code '),
 ('Não foi possível gerar prévia: ', 'Could not generate preview: '),
 ('Regra do código ', 'Rule for tile code '),
 (' aplicada na memória. Salve as regras em JSON.',
  ' applied in memory. Save rules to JSON.'),
 ('Cores do código ', 'Colors for tile code '),
 (' ajustadas na prévia. Clique em Aplicar ao código para confirmar.',
  ' adjusted in preview. Click Apply to tile code to confirm.'),
 ('  ·  paleta original ', '  ·  source palette '),
 (' → paleta MD ', ' → MD palette '),
 ('Cor Mega Drive ', 'Mega Drive color '),
 ('Pen ', 'Pen '),
 (': primária automática + secundária ', ': automatic primary + secondary '),
 (': primária ', ': primary '),
 (' + secundária ', ' + secondary '),
 ('  ·  Pressione “Aplicar ao código” e depois “Salvar regras em JSON”.',
  '  ·  Click “Apply to tile code” and then “Save rules to JSON”.'),
 ('Perfil completo exportado: ', 'Full profile exported: '),
 ('. Os arquivos ativos não foram alterados.', '. Active files were not changed.'),
 ('Preset geral importado: ', 'Global preset imported: '),
 ('. Para preservá-lo entre sessões, use “Salvar como…” ou “Salvar preset geral”.',
  '. To preserve it between sessions, use “Save as…” or “Save global preset”.'),
 ('Importado: ', 'Imported: '),
 ('. Regras carregadas em memória; clique em “Salvar regras em JSON” para gravar as regras no projeto. '
  'Para guardar também algoritmo e sliders gerais, use “Salvar como…”.',
  '. Rules loaded in memory; click “Save rules to JSON” to write them to the project. '
  'To save the global algorithm and sliders as well, use “Save as…”.'),
 ('Importar “', 'Import “'),
 ('” ?','” ?'),
 ('” ?\n','” ?\n'),
 ('” ?\n\n','” ?\n\n'),
 ('”?\n\nSerão substituídos em memória: ', '”?\n\nThe following will be replaced in memory: '),
 ('.\n\nO arquivo ativo do projeto NÃO será sobrescrito até você clicar em “Salvar regras em JSON”.',
  '.\n\nThe project’s active file will NOT be overwritten until you click “Save rules to JSON”.'),
 ('Nada foi alterado.', 'Nothing was changed.'),
 ('ROM salva em:\n', 'ROM saved to:\n'),
 ('Fase ainda não exportada', 'Stage not exported yet'),
 (': era esperada uma lista de códigos.', ': expected a list of codes.'),
 (': os códigos devem ser inteiros entre 0 e 2047.', ': codes must be integers from 0 to 2047.'),
 ('Arquivo protegido', 'Protected file'),
 ('Parâmetro fora do intervalo: ', 'Parameter out of range: '),
 ('Já existe um build em andamento ou lock antigo: ', 'A build is already running or an old lock exists: '),
 ('ATENÇÃO: não foi possível restaurar ', 'WARNING: could not restore '),
 ('Módulo original restaurado.', 'Original module restored.'),
 ('Módulo temporário aplicado; backup de recuperação criado.',
  'Temporary module applied; recovery backup created.'),
 ('Erro na prévia de contexto: ', 'Context preview error: '),
 ('Erro atualizando mapa: ', 'Error updating map: '),
 ('Erro atualizando bloco no mapa: ', 'Error updating map tile: '),
 ('Erro restaurando mapa: ', 'Error restoring map: '),
 ('Erro aplicando regra ao mapa: ', 'Error applying rule to map: '),
 ('Os parametros de dithering devem ser um objeto JSON.', 'Dithering parameters must be a JSON object.'),
 ('Modo de prévia inválido: ', 'Invalid preview mode: '),
 ('Algoritmo geral desconhecido: ', 'Unknown global algorithm: '),
 ('Campo repetido no JSON: ', 'Duplicate JSON field: '),
 ('Chaves de fase inválidas em no_dither_tiles.json: ', 'Invalid stage keys in no_dither_tiles.json: '),
 ('Formato de perfil desconhecido ou versão incompatível.', 'Unknown profile format or incompatible version.'),
 ('Perfil incompleto ou com campos desconhecidos: ', 'Incomplete profile or unknown fields: '),
 ('A estrutura da aba visual foi alterada; barra de perfis indisponível.',
  'The visual tab layout changed; the profile toolbar is unavailable.'),
 ('Erro nas regras', 'Rule error'),
 ('Erro ao exportar', 'Export error'),
 ('Erro ao atualizar editor', 'Error updating editor'),
 ('JSON inválido', 'Invalid JSON'),
 ('Confirmar importação', 'Confirm import'),
 ('Arquivo protegido', 'Protected file'),
 ('Configuração geral precisa ser um objeto JSON.', 'Global configuration must be a JSON object.'),
]
PARTS.sort(key=lambda item: len(item[0]), reverse=True)

# The active language only affects the UI process, never build subprocesses.
_ACTIVE = 'pt'
_PATCHED_DIALOGS = False
_PATCHED_TOOLTIPS = False

def set_active_language(lang):
    global _ACTIVE
    _ACTIVE = 'en' if lang == 'en' else 'pt'


def translate(s, lang=None):
    if not isinstance(s, str):
        return s
    if (lang or _ACTIVE) != 'en' or not s:
        return s
    if s in TEXT:
        return TEXT[s]
    # Help strings are matched exactly; avoid accidentally modifying prose in
    # the mathematical expressions or identifiers.
    if s in _TOOLTIP_EXACT:
        return _TOOLTIP_EXACT[s]
    out = s
    for pt, en in PARTS:
        if pt in out:
            out = out.replace(pt, en)
    return out

_TOOLTIP_EXACT = {}

def patch_tooltips(tooltip_type, help_pt, mode_help_pt):
    global _PATCHED_TOOLTIPS
    for key, value in help_pt.items():
        if key in HELP_EN:
            _TOOLTIP_EXACT[value] = HELP_EN[key]
    for mode, group in mode_help_pt.items():
        for key, value in group.items():
            if key in MODE_HELP_EN.get(mode, {}):
                _TOOLTIP_EXACT[value] = MODE_HELP_EN[mode][key]
    if _PATCHED_TOOLTIPS:
        return
    original_show = tooltip_type.show
    def show_localized(self):
        original = getattr(self, '_bt_original_tooltip', self.text)
        self._bt_original_tooltip = original
        self.text = translate(original)
        try:
            return original_show(self)
        finally:
            self.text = original
    tooltip_type.show = show_localized
    _PATCHED_TOOLTIPS = True


def patch_dialogs():
    global _PATCHED_DIALOGS
    if _PATCHED_DIALOGS:
        return
    for name in ('showinfo','showwarning','showerror','askyesno','askokcancel','askyesnocancel','askretrycancel','askquestion'):
        if not hasattr(messagebox, name):
            continue
        original = getattr(messagebox, name)
        def wrapped(title=None, message=None, _original=original, **kwargs):
            return _original(translate(title), translate(message), **kwargs)
        setattr(messagebox, name, wrapped)
    for name in ('askopenfilename','asksaveasfilename','askdirectory'):
        if not hasattr(filedialog, name):
            continue
        original = getattr(filedialog, name)
        def wrapped_dialog(_original=original, **kwargs):
            if 'title' in kwargs:
                kwargs['title'] = translate(kwargs['title'])
            if 'filetypes' in kwargs:
                kwargs['filetypes'] = [(translate(label), pattern) for label, pattern in kwargs['filetypes']]
            return _original(**kwargs)
        setattr(filedialog, name, wrapped_dialog)
    _PATCHED_DIALOGS = True


def load_language(project):
    path = Path(project)/'tools/dither_lab_language.json'
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
        return obj['language'] if obj.get('language') in ('pt','en') else 'pt'
    except (OSError, ValueError, TypeError, KeyError):
        return 'pt'


def save_language(project, lang):
    path = Path(project)/'tools/dither_lab_language.json'
    staging = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.dither_lab_language.', suffix='.tmp', delete=False) as handle:
            staging = Path(handle.name)
            json.dump({'language':lang},handle,indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging,path)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


class LanguageMixin:
    """Runtime language selection without changing algorithm/JSON semantics."""

    def build_widgets(self):
        self._bt_language = load_language(self.project)
        set_active_language(self._bt_language)
        patch_dialogs()
        from dither_lab import Tooltip, HELP
        from dither_tile_policy import MODE_HELP
        patch_tooltips(Tooltip, HELP, MODE_HELP)
        self._bt_language_choice = tk.StringVar(master=self, value=('English' if self._bt_language=='en' else 'Português'))
        super().build_widgets()
        self._bt_install_selector()
        self._bt_refresh_language()
        self.after(350, self._bt_language_tick)

    def _bt_install_selector(self):
        top = self.winfo_children()[0]
        if not isinstance(top, (ttk.Frame, tk.Frame)):
            raise RuntimeError('Dithering Lab toolbar structure changed; cannot add language selector.')
        # Place next to the title, while preserving all existing buttons.
        self._bt_lang_combo = ttk.Combobox(top, textvariable=self._bt_language_choice,
                                          values=('Português','English'), width=12, state='readonly')
        self._bt_lang_combo.pack(side='right', padx=(4, 6))
        ttk.Label(top, text='Idioma / Language:').pack(side='right', padx=(12, 2))
        self._bt_lang_combo.bind('<<ComboboxSelected>>', self._bt_on_language_selected)

    def _bt_on_language_selected(self, event=None):
        new = 'en' if self._bt_language_choice.get()=='English' else 'pt'
        if new == self._bt_language:
            return
        self._bt_language = new
        set_active_language(new)
        try:
            save_language(self.project, new)
        except OSError as exc:
            messagebox.showwarning('Language preference', f'Could not save language preference:\n{exc}', parent=self)
        self._bt_refresh_language()

    def _bt_language_tick(self):
        try:
            if not self.winfo_exists():
                return
            self._bt_refresh_language()
        except tk.TclError:
            return
        self.after(350, self._bt_language_tick)

    def _bt_refresh_language(self):
        lang = self._bt_language
        set_active_language(lang)
        # Preserve the stage number. Both Stage 8 and Fase 8 have the same
        # numeric suffix, which is what change_stage() parses.
        if hasattr(self,'stage_string'):
            current=self.stage_string.get()
            match=re.fullmatch(r'(?:Fase|Stage)\s+(\d+)',current)
            if match:
                expected=('Stage ' if lang=='en' else 'Fase ')+match.group(1)
                if current!=expected:
                    self.stage_string.set(expected)
        for variable_name in ('info','tile_info','edited_flag','state_value','color_clip_status'):
            var=getattr(self,variable_name,None)
            if var is None:
                continue
            value=var.get()
            previous=getattr(var,'_bt_rendered',None)
            if previous != value:
                var._bt_original=value
            original=getattr(var,'_bt_original',value)
            rendered=translate(original,lang)
            if rendered != value:
                var.set(rendered)
            var._bt_rendered=rendered
        self._bt_translate_tree(self)

    def _bt_translate_tree(self, widget):
        if isinstance(widget, (tk.Tk,tk.Toplevel)):
            self._bt_translate_title(widget)
        if isinstance(widget, ttk.Notebook):
            for tab in widget.tabs():
                original=widget.tab(tab,'text')
                # Notebook labels are fixed at creation time; we keep their PT
                # originals on the notebook, keyed by tab identity.
                originals=getattr(widget,'_bt_original_tabs',None)
                if originals is None:
                    originals={}
                    widget._bt_original_tabs=originals
                if tab not in originals:
                    originals[tab]=original
                expected=translate(originals[tab],self._bt_language)
                if original!=expected:
                    widget.tab(tab,text=expected)
        if isinstance(widget, ttk.Combobox) and widget is not getattr(self,'_bt_lang_combo',None):
            values=tuple(widget.cget('values'))
            if len(values)==8 and all(re.fullmatch(r'(?:Fase|Stage)\s+[1-8]',v) for v in values):
                expected=tuple(('Stage ' if self._bt_language=='en' else 'Fase ')+str(i) for i in range(1,9))
                if values!=expected:
                    widget.configure(values=expected)
        if isinstance(widget, (tk.Label,tk.Button,tk.Radiobutton,tk.Checkbutton,
                               tk.LabelFrame,ttk.Label,ttk.Button,ttk.Radiobutton,
                               ttk.Checkbutton,ttk.LabelFrame)):
            try:
                if 'textvariable' in widget.keys() and widget.cget('textvariable'):
                    pass
                else:
                    self._bt_translate_widget_text(widget)
            except tk.TclError:
                pass
        for child in widget.winfo_children():
            self._bt_translate_tree(child)

    def _bt_translate_title(self, widget):
        title=widget.title()
        rendered=getattr(widget,'_bt_rendered_title',None)
        if title!=rendered:
            widget._bt_original_title=title
        original=getattr(widget,'_bt_original_title',title)
        expected=translate(original,self._bt_language)
        if title!=expected:
            widget.title(expected)
        widget._bt_rendered_title=expected

    def _bt_translate_widget_text(self, widget):
        current=widget.cget('text')
        rendered=getattr(widget,'_bt_rendered_text',None)
        if current!=rendered:
            widget._bt_original_text=current
        original=getattr(widget,'_bt_original_text',current)
        expected=translate(original,self._bt_language)
        if current!=expected:
            widget.configure(text=expected)
        widget._bt_rendered_text=expected

    def open_color_editor(self):
        # Translate the dialog synchronously, before the user sees it.
        result=super().open_color_editor()
        self._bt_refresh_language()
        return result
