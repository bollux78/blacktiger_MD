#!/usr/bin/env python3
"""Black Tiger MD Dithering Lab - Tkinter, Python 3.10+."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

MODES = ('original', 'bayer4', 'bayer4_soft', 'bayer4_adaptive')
PARAMS = [
    ('min_error', 'Erro mínimo RGB²', 0.5, 0.0, 5.0, 0.05),
    ('max_distance', 'Distância máxima RGB²', 20.0, 2.0, 50.0, 0.5),
    ('max_luma', 'Diferença máx. luminância', 2.3, 0.0, 6.0, 0.1),
    ('contrast_penalty', 'Penalização de contraste', 0.04, 0.0, 0.25, 0.005),
    ('min_score', 'Ganho mínimo', 0.25, 0.0, 3.0, 0.05),
    ('max_mix', 'Mistura máxima (%)', 48.0, 0.0, 80.0, 1.0),
]
HELP = {
    'min_error': 'Erro quadrático RGB da cor original em relação à cor principal da paleta.\nAbaixo desse valor, não se aplica dithering.\nMenor = mais áreas elegíveis; maior = mais superfícies lisas.',
    'max_distance': 'Distância quadrática RGB entre as duas cores da paleta usadas na mistura.\nMenor = evita pares de cores muito diferentes; maior = permite mais misturas,\nmas pode produzir pontos mais visíveis.',
    'max_luma': 'Diferença máxima de luminância entre as cores misturadas, em escala RGB333.\nMenor = protege contrastes e contornos; maior = aceita variações de brilho maiores.',
    'contrast_penalty': 'Penalidade aplicada à pontuação: score = ganho - penalização × distância RGB².\nMenor = favorece mais dithering; maior = desestimula pares contrastantes.',
    'min_score': 'Pontuação mínima para aceitar uma mistura de cores após a penalização.\nMenor = mais misturas; maior = apenas melhorias mais expressivas.',
    'max_mix': 'Percentual máximo de pixels que podem usar a cor secundária no padrão Bayer 4×4.\nMenor = textura discreta; maior = textura mais intensa.\nA grade Bayer tem passos discretos de 6,25%, então pequenas mudanças podem não aparecer.',
}


class Tooltip:
    """Balão de ajuda ao passar o mouse; sem dependências adicionais."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.popup = None
        self.job = None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')

    def schedule(self, event=None):
        self.cancel()
        self.job = self.widget.after(500, self.show)

    def cancel(self):
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None

    def show(self):
        self.job = None
        if self.popup is not None:
            return
        x = self.widget.winfo_pointerx() + 16
        y = self.widget.winfo_pointery() + 18
        popup = tk.Toplevel(self.widget)
        popup.withdraw()
        popup.wm_overrideredirect(True)
        label = tk.Label(popup, text=self.text, justify='left', anchor='w',
                         background='#fff7d6', foreground='#202020',
                         relief='solid', borderwidth=1, padx=10, pady=8,
                         font=('Sans', 10))
        label.pack()
        popup.update_idletasks()
        x = min(x, max(0, popup.winfo_screenwidth() - popup.winfo_reqwidth() - 8))
        y = min(y, max(0, popup.winfo_screenheight() - popup.winfo_reqheight() - 8))
        popup.geometry(f'+{x}+{y}')
        popup.deiconify()
        self.popup = popup

    def hide(self, event=None):
        self.cancel()
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None


# The replacement patterns correspond to the convert_adaptive() implementation
# supplied by the user. Every pattern must match exactly once or no build starts.
REPLACEMENTS = [
    (r'if original_error\s*<\s*[\d.]+\s*:', 'if original_error < {min_error}:'),
    (r'if norm2\s*<\s*1e-8\s+or\s+norm2\s*>\s*[\d.]+\s*:', 'if norm2 < 1e-8 or norm2 > {max_distance}:'),
    (r'if abs\(float\(np\.dot\(direction, weights\)\)\)\s*>\s*[\d.]+\s*:', 'if abs(float(np.dot(direction, weights))) > {max_luma}:'),
    (r'np\.clip\(np\.dot\(color - first, direction\) / norm2, 0\.0,\s*[\d.]+\)', 'np.clip(np.dot(color - first, direction) / norm2, 0.0, {max_mix_fraction})'),
    (r'score\s*=\s*gain\s*-\s*[\d.]+\s*\*\s*norm2', 'score = gain - {contrast_penalty} * norm2'),
    (r'if best_index\s*>=\s*0\s+and\s+best_score\s*>=\s*[\d.]+\s*:', 'if best_index >= 0 and best_score >= {min_score}:'),
]


def find_project():
    candidates = [Path.cwd(), Path.home() / 'Projetos/blacktiger_MD']
    for p in candidates:
        if (p / 'tools/dither_bg.py').is_file() and (p / 'Makefile').is_file():
            return p
    return candidates[-1]


def render_module(original, values):
    marker = re.search(r'^def convert_adaptive\(', original, re.M)
    if not marker:
        raise ValueError('Função convert_adaptive() não encontrada no dither_bg.py.')
    following = re.search(r'^def \w+\(', original[marker.end():], re.M)
    end = marker.end() + following.start() if following else len(original)
    head, body, tail = original[:marker.start()], original[marker.start():end], original[end:]
    formatted = dict(values)
    formatted['max_mix_fraction'] = round(values['max_mix'] / 100, 6)
    for pattern, template in REPLACEMENTS:
        body, count = re.subn(pattern, template.format(**formatted), body)
        if count != 1:
            raise ValueError(f'Estrutura do algoritmo incompatível ({count} ocorrências): {pattern}')
    result = head + body + tail
    compile(result, 'dither_bg.py', 'exec')
    return result


class Lab(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Black Tiger MD — Dithering Lab')
        self.geometry('900x760')
        self.minsize(720, 610)
        self.project = find_project()
        self.q = queue.Queue()
        self.busy = False
        self.mode = tk.StringVar(value='bayer4_adaptive')
        self.values = {key: tk.DoubleVar(value=default) for key, _, default, _, _, _ in PARAMS}
        self.build_widgets()
        self.after(100, self.drain)

    def build_widgets(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill='both', expand=True)
        ttk.Label(root, text='Black Tiger MD — Dithering Lab', font=('Sans', 17, 'bold')).pack(anchor='w')
        ttk.Label(root, text=f'Projeto: {self.project}', foreground='#666').pack(anchor='w', pady=(0, 8))
        top = ttk.Frame(root)
        top.pack(fill='x')
        ttk.Label(top, text='Algoritmo:').pack(side='left')
        self.combo = ttk.Combobox(top, values=MODES, textvariable=self.mode, state='readonly', width=22)
        self.combo.pack(side='left', padx=8)
        self.combo.bind('<<ComboboxSelected>>', lambda _: self.toggle())
        ttk.Button(top, text='Carregar preset', command=self.load_preset).pack(side='right', padx=4)
        ttk.Button(top, text='Salvar preset', command=self.save_preset).pack(side='right', padx=4)
        self.controls = ttk.LabelFrame(root, text='Parâmetros do Bayer adaptativo', padding=10)
        self.controls.pack(fill='x', pady=12)
        self.sliders = []
        for key, label, _, low, high, step in PARAMS:
            line = ttk.Frame(self.controls)
            line.pack(fill='x', pady=3)
            name_label = ttk.Label(line, text=label + '  ⓘ', width=31)
            name_label.pack(side='left')
            slider = tk.Scale(line, from_=low, to=high, resolution=step, orient='horizontal',
                              showvalue=True, variable=self.values[key], length=430)
            slider.pack(side='left', fill='x', expand=True)
            self.sliders.append(slider)
            Tooltip(name_label, HELP[key])
            Tooltip(slider, HELP[key])
        actions = ttk.Frame(root)
        actions.pack(fill='x', pady=(0, 8))
        self.build_button = ttk.Button(actions, text='Gerar ROM', command=self.start_build)
        self.build_button.pack(side='left')
        ttk.Button(actions, text='Abrir pasta de ROMs', command=self.open_roms).pack(side='left', padx=8)
        self.progress = ttk.Progressbar(actions, mode='indeterminate', length=190)
        self.progress.pack(side='right')
        self.state_label = ttk.Label(root, text='Pronto.')
        self.state_label.pack(anchor='w')
        logframe = ttk.LabelFrame(root, text='Saída da compilação', padding=6)
        logframe.pack(fill='both', expand=True, pady=(5, 0))
        self.log = tk.Text(logframe, height=12, wrap='word', state='disabled', font=('Monospace', 9))
        bar = ttk.Scrollbar(logframe, command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.log.pack(fill='both', expand=True)
        ttk.Label(root, text='Durante a compilação, o módulo temporário é restaurado ao terminar. Não execute outra compilação em paralelo.',
                  foreground='#777').pack(anchor='w', pady=(6, 0))
        self.toggle()

    def toggle(self):
        state = 'normal' if self.mode.get() == 'bayer4_adaptive' else 'disabled'
        for slider in self.sliders:
            slider.configure(state=state)

    def append(self, s):
        self.log.configure(state='normal')
        self.log.insert('end', s)
        self.log.see('end')
        self.log.configure(state='disabled')

    def drain(self):
        try:
            while True:
                kind, value = self.q.get_nowait()
                if kind == 'log':
                    self.append(value)
                elif kind == 'state':
                    self.state_label.configure(text=value)
                elif kind == 'done':
                    self.busy = False
                    self.progress.stop()
                    self.build_button.configure(state='normal')
                    if value[0]:
                        messagebox.showinfo('ROM criada', f'ROM salva em:\n{value[1]}')
                    else:
                        messagebox.showerror('Falha na compilação', value[1])
        except queue.Empty:
            pass
        self.after(100, self.drain)

    def configuration(self):
        return {'mode': self.mode.get(), 'parameters': {k: round(v.get(), 6) for k, v in self.values.items()}}

    def save_preset(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')],
                                            initialfile='blacktiger_preset.json')
        if path:
            Path(path).write_text(json.dumps(self.configuration(), indent=2, ensure_ascii=False), encoding='utf-8')

    def load_preset(self):
        path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            if data['mode'] not in MODES:
                raise ValueError('Modo desconhecido')
            for key, _, _, low, high, _ in PARAMS:
                v = float(data['parameters'][key])
                if not low <= v <= high:
                    raise ValueError(f'Parâmetro fora do intervalo: {key}')
                self.values[key].set(v)
            self.mode.set(data['mode'])
            self.toggle()
        except (ValueError, KeyError, TypeError) as exc:
            messagebox.showerror('Preset inválido', str(exc))

    def open_roms(self):
        folder = self.project / 'roms'
        folder.mkdir(exist_ok=True)
        try:
            subprocess.Popen(['xdg-open', str(folder)])
        except OSError as exc:
            messagebox.showerror('Erro', str(exc))

    def start_build(self):
        if self.busy:
            return
        config = self.configuration()
        self.busy = True
        self.build_button.configure(state='disabled')
        self.progress.start(12)
        self.append('\n' + '=' * 60 + '\n')
        threading.Thread(target=self.worker, args=(config,), daemon=True).start()

    def say(self, s):
        self.q.put(('log', s))

    def run(self, args, env):
        self.say('$ ' + ' '.join(args) + '\n')
        proc = subprocess.Popen(args, cwd=self.project, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors='replace', bufsize=1)
        for line in proc.stdout:
            self.say(line)
        return proc.wait()

    def worker(self, config):
        module = self.project / 'tools/dither_bg.py'
        lock_path = self.project / '.local/dither-lab.lock'
        original_bytes = None
        replaced = False
        acquired = False
        try:
            if not (self.project / 'Makefile').is_file() or not module.is_file():
                raise RuntimeError('Projeto ou tools/dither_bg.py não encontrado.')
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                raise RuntimeError(f'Já existe um build em andamento ou lock antigo: {lock_path}')
            acquired = True
            with os.fdopen(fd, 'w') as lock:
                lock.write(str(os.getpid()))
            original_bytes = module.read_bytes()
            if config['mode'] == 'bayer4_adaptive':
                rendered = render_module(original_bytes.decode('utf-8'), config['parameters'])
                if rendered.encode('utf-8') != original_bytes:
                    # Persist recovery copy in case of forced termination or power loss.
                    backup = self.project / '.local/dither_bg.lab-recovery.py'
                    backup.write_bytes(original_bytes)
                    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=module.parent,
                                                     prefix='.dither_lab_', suffix='.py', delete=False) as temp:
                        temp.write(rendered)
                        temp_name = temp.name
                    os.replace(temp_name, module)
                    replaced = True
                    self.say('Módulo temporário aplicado; backup de recuperação criado.\n')
            env = os.environ.copy()
            env['BLACKTIGER_DITHER'] = config['mode']
            self.q.put(('state', 'Gerando assets...'))
            if self.run(['make', 'assets'], env) != 0:
                raise RuntimeError('Falha na geração de assets. Consulte o log.')
            self.q.put(('state', 'Compilando ROM...'))
            env['GDK'] = str(Path.home() / 'mars/m68k-elf')
            if self.run(['make', '-j4'], env) != 0:
                raise RuntimeError('Falha na compilação da ROM. Consulte o log.')
            rom = self.project / 'out/release/rom.bin'
            if not rom.is_file() or rom.stat().st_size == 0:
                raise RuntimeError('Compilação terminou, mas out/release/rom.bin não existe.')
            version_file = self.project / 'VERSION'
            version = version_file.read_text(encoding='utf-8').strip() if version_file.exists() else 'unknown'
            version = re.sub(r'[^A-Za-z0-9._-]+', '_', version)[:40] or 'unknown'
            digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]
            folder = self.project / 'roms'
            folder.mkdir(exist_ok=True)
            # Nomeia cada ROM com versao, algoritmo efetivamente compilado e horario local.
            # O JSON acompanhante continua registrando as configuracoes e o SHA-256.
            completed_at = datetime.now()
            stem_base = f"BlackTiger_MD_{version}_{config['mode']}_{completed_at:%Y-%m-%d_%H-%M-%S}"
            stem = stem_base
            counter = 2
            while (folder / f'{stem}.bin').exists() or (folder / f'{stem}.json').exists():
                stem = f'{stem_base}_{counter}'
                counter += 1
            destination = folder / f'{stem}.bin'
            shutil.copy2(rom, destination)
            (folder / f'{stem}.json').write_text(json.dumps({**config, 'version': version,
                'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                'created_at': completed_at.isoformat(timespec='seconds')},
                indent=2, ensure_ascii=False), encoding='utf-8')
            self.say(f'\nROM pronta: {destination}\n')
            self.q.put(('done', (True, str(destination))))
        except Exception as exc:
            self.say(f'\nERRO: {exc}\n')
            self.q.put(('done', (False, str(exc))))
        finally:
            if replaced and original_bytes is not None:
                try:
                    module.write_bytes(original_bytes)
                    self.say('Módulo original restaurado.\n')
                except OSError as exc:
                    self.say(f'ATENÇÃO: não foi possível restaurar {module}: {exc}\n')
            if acquired:
                try:
                    lock_path.unlink()
                except OSError:
                    pass


if __name__ == '__main__':
    Lab().mainloop()
