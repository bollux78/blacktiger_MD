"""Perfis JSON do Black Tiger Dithering Lab 2.0.

Sem alterações automáticas nos assets, ROM, extrator ou JSONs ativos.
Suporta perfil completo e importação dos JSONs anteriores.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from tkinter import ttk, filedialog, messagebox

from dither_tile_policy import MODES, normalize_rules, validate_params

FORMAT = 'blacktiger-dithering-lab-profile'
FORMAT_VERSION = 1


def normalize_legacy(data):
    """Retorna no_dither_tiles.json sem itens duplicados e com 8 fases."""
    if not isinstance(data, dict):
        raise ValueError('As seleções sem dithering devem ser um objeto JSON.')
    invalid = sorted(set(data) - {str(i) for i in range(8)})
    if invalid:
        raise ValueError('Chaves de fase inválidas em no_dither_tiles.json: ' + ', '.join(invalid))
    result = {}
    for i in range(8):
        values = data.get(str(i), [])
        if not isinstance(values, list):
            raise ValueError(f'Fase {i + 1}: era esperada uma lista de códigos.')
        if any(type(n) is not int or n < 0 or n >= 2048 for n in values):
            raise ValueError(f'Fase {i + 1}: os códigos devem ser inteiros entre 0 e 2047.')
        result[str(i)] = sorted(set(values))
    return result


def validate_global(data):
    if not isinstance(data, dict):
        raise ValueError('Configuração geral precisa ser um objeto JSON.')
    mode = data.get('mode')
    if mode not in MODES:
        raise ValueError('Algoritmo geral desconhecido: ' + str(mode))
    params = validate_params(data.get('parameters'))
    return {'mode': mode, 'parameters': params}


def classify_import(data):
    """Classifica sem efeitos colaterais; devolve alterações já validadas."""
    if not isinstance(data, dict):
        raise ValueError('A raiz do JSON deve ser um objeto.')
    if 'format' in data:
        if data.get('format') != FORMAT or data.get('version') != FORMAT_VERSION:
            raise ValueError('Formato de perfil desconhecido ou versão incompatível.')
        required = {'format', 'version', 'global', 'tile_rules', 'no_dither_tiles'}
        if set(data) != required:
            raise ValueError('Perfil incompleto ou com campos desconhecidos: ' + ', '.join(sorted(set(data) ^ required)))
        return {
            'kind': 'complete',
            'global': validate_global(data['global']),
            'rules': normalize_rules(data['tile_rules']),
            'legacy': normalize_legacy(data['no_dither_tiles']),
        }
    if 'version' in data and 'stages' in data:
        return {'kind': 'rules', 'rules': normalize_rules(data)}
    if 'mode' in data and 'parameters' in data:
        return {'kind': 'global', 'global': validate_global(data)}
    if set(data) <= {str(i) for i in range(8)}:
        return {'kind': 'legacy', 'legacy': normalize_legacy(data)}
    raise ValueError('JSON não reconhecido. Use perfil completo, tile_dither_rules.json, '
                     'no_dither_tiles.json ou preset de algoritmo geral.')


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Campo repetido no JSON: {key}')
        result[key] = value
    return result


def write_json_atomic(path, data):
    """Salva em arquivo temporário no mesmo diretório e renomeia ao concluir."""
    path = Path(path)
    payload = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    staging = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=path.parent,
            prefix='.' + path.stem + '.', suffix='.tmp',
            delete=False
        ) as handle:
            staging = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


class SessionIOMixin:
    """Adiciona Importar JSON / Salvar como sem mexer nas ações existentes."""

    def create_editor(self):
        super().create_editor()
        children = self.editor_tab.winfo_children()
        if len(children) < 2:
            raise RuntimeError('A estrutura da aba visual foi alterada; barra de perfis indisponível.')
        toolbar = ttk.Frame(self.editor_tab, padding=(8, 1))
        toolbar.pack(fill='x', before=children[1])
        ttk.Button(toolbar, text='Salvar como…', command=self.export_profile).pack(side='left', padx=(0, 8))
        ttk.Button(toolbar, text='Importar JSON…', command=self.import_profile).pack(side='left')
        ttk.Label(
            toolbar,
            text='Perfis completos incluem algoritmo, sliders, cores manuais e exclusões.',
            foreground='#777'
        ).pack(side='left', padx=12)

    def _current_global_profile(self):
        return validate_global({
            'mode': self.mode.get(),
            'parameters': {key: float(variable.get()) for key, variable in self.values.items()},
        })

    def export_profile(self):
        """Cria uma cópia externa; não altera o JSON ativo do projeto."""
        if getattr(self, 'busy', False):
            messagebox.showwarning('Compilação em andamento', 'Aguarde terminar a compilação.', parent=self)
            return
        try:
            data = {
                'format': FORMAT,
                'version': FORMAT_VERSION,
                'global': self._current_global_profile(),
                'tile_rules': normalize_rules(self.rules),
                'no_dither_tiles': normalize_legacy(self.legacy),
            }
        except Exception as exc:
            messagebox.showerror('Erro nas regras', str(exc), parent=self)
            return
        filename = 'blacktiger_perfil_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json'
        selection = filedialog.asksaveasfilename(
            parent=self,
            title='Salvar perfil completo do Dithering Lab como…',
            initialdir=str(self.project),
            initialfile=filename,
            defaultextension='.json',
            filetypes=[('Arquivos JSON', '*.json')],
        )
        if not selection:
            return
        path = Path(selection).expanduser()
        if path.resolve() in {self.rules_path.resolve(), self.legacy_path.resolve()}:
            messagebox.showerror('Arquivo protegido',
                'Use “Salvar regras em JSON” para atualizar os arquivos ativos do projeto.', parent=self)
            return
        try:
            write_json_atomic(path, data)
        except Exception as exc:
            messagebox.showerror('Erro ao exportar', str(exc), parent=self)
            return
        self.info.set(f'Perfil completo exportado: {path}. Os arquivos ativos não foram alterados.')

    def import_profile(self):
        """Importa para a memória; usuário salva os JSONs ativos separadamente."""
        if getattr(self, 'busy', False):
            messagebox.showwarning('Compilação em andamento', 'Aguarde terminar a compilação.', parent=self)
            return
        selection = filedialog.askopenfilename(
            parent=self,
            title='Importar perfil ou regras JSON',
            initialdir=str(self.project),
            filetypes=[('Arquivos JSON', '*.json'), ('Todos os arquivos', '*.*')],
        )
        if not selection:
            return
        path = Path(selection)
        try:
            if path.stat().st_size > 4_000_000:
                raise ValueError('JSON muito grande (limite: 4 MB).')
            data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=reject_duplicate_keys)
            changes = classify_import(data)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            messagebox.showerror('JSON inválido', f'{path.name}\n\n{exc}\n\nNada foi alterado.', parent=self)
            return
        sections = {
            'complete': 'algoritmo geral, sliders, regras individuais e exclusões',
            'rules': 'somente regras individuais dos blocos',
            'legacy': 'somente códigos sem dithering',
            'global': 'somente algoritmo e sliders gerais',
        }
        if not messagebox.askyesno(
            'Confirmar importação',
            f'Importar “{path.name}”?\n\nSerão substituídos em memória: '
            f'{sections[changes["kind"]]}.\n\n'
            'O arquivo ativo do projeto NÃO será sobrescrito até você clicar '
            'em “Salvar regras em JSON”.',
            parent=self,
        ):
            return
        try:
            # Aplicar somente depois de todas as validações e da confirmação.
            if 'rules' in changes:
                self.rules = changes['rules']
            if 'legacy' in changes:
                self.legacy = changes['legacy']
            if 'global' in changes:
                self.mode.set(changes['global']['mode'])
                for key, value in changes['global']['parameters'].items():
                    self.values[key].set(value)
                self.toggle()
            if 'rules' in changes or 'legacy' in changes:
                if hasattr(self, '_cancel_live'):
                    self._cancel_live()
                if hasattr(self, '_live_touched'):
                    self._live_touched = {str(i): set() for i in range(8)}
                self.current = None
                self.load_stage()
            if 'rules' in changes or 'legacy' in changes:
                # BLACKTIGER_PURE_UNTIL_JSON_V1: só importar ativa regras na ROM.
                self.profile_rules_active = True
                self.profile_source_name = path.name
                self.unsaved = True
                self.info.set(
                    f'Perfil ativo: {path.name}. A próxima ROM usará as regras importadas. '
                    'Não é necessário sobrescrever os JSONs do projeto para compilar.'
                )
            else:
                self.info.set(
                    f'Preset geral importado: {path.name}. Para preservá-lo entre sessões, '
                    'use “Salvar como…” ou “Salvar preset geral”.'
                )
        except Exception as exc:
            messagebox.showerror('Erro ao atualizar editor', str(exc), parent=self)
            return
