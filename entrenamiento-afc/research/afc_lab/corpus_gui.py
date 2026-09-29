"""Local desktop interface for corpus inspection and pilot selection."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime

from .corpus import select_pilot, sha256
from .audio_preview import AudioPreview

ROOT = Path(__file__).resolve().parents[2]


def selection_manifest(source, paths, seconds):
    """Preserve audited partitions/exclusions; selection never moves identities."""
    rows = [r for r in source['inventory'] if r['path'] in paths and r['eligible']]
    summary = {f'{split}/{kind}': sum(r['seconds'] for r in rows
               if r['split'] == split and r['kind'] == kind)
               for split in ('train', 'validation', 'test') for kind in ('speech', 'singing')}
    return {**source, 'records': rows, 'seconds': summary,
            'requested_seconds_per_kind': seconds,
            'coverage_complete': all(v > 0 for v in summary.values()),
            'duration_target_met': all(sum(r['seconds'] for r in rows if r['kind'] == kind)
                                       >= seconds for kind in ('speech', 'singing')),
            'listening_review': 'pending', 'complete': False,
            'selection_method': 'local_gui_from_audited_inventory'}


class CorpusApp:
    def __init__(self, window):
        self.window = window
        window.title('AFC · Preparar voces')
        window.geometry('1180x760')
        window.minsize(900, 580)
        self.events = queue.Queue()
        self.busy = False
        self.source = None
        self.chosen = set()
        self.player = AudioPreview()
        self.playing_path = None
        self.player_label = tk.StringVar(value='Selecciona una grabación y pulsa Reproducir.')
        self.player_time = tk.StringVar(value='0:00 / 0:00')
        self.root = tk.StringVar(value=str(ROOT / 'data' / 'raw'))
        self.minutes = tk.StringVar(value='60')
        self.kind = tk.StringVar(value='Todos')
        self.split = tk.StringVar(value='Todos')
        self.status = tk.StringVar(value='Abre un inventario existente o analiza los originales locales.')
        self.summary = tk.StringVar(value='Objetivo inicial: 60 minutos de habla y 60 minutos de canto.')
        outer = ttk.Frame(window, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Preparar voces para AFC', font=('Segoe UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='48 kHz · Personas separadas entre entrenamiento, validación y prueba').pack(anchor='w', pady=(0, 12))
        folder = ttk.Frame(outer)
        folder.pack(fill='x')
        ttk.Label(folder, text='Originales:').pack(side='left')
        ttk.Entry(folder, textvariable=self.root).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(folder, text='Elegir carpeta', command=self.choose_folder).pack(side='left')
        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=10)
        for label, action in [('Abrir inventario', self.open_manifest), ('Analizar originales', self.audit),
                              ('Obtener/verificar 12 clips de prueba', self.download)]:
            ttk.Button(actions, text=label, command=action).pack(side='left', padx=(0, 8))
        ttk.Label(outer, text='Las descargas disponibles son muestras técnicas. El catálogo del corpus ampliado está pendiente.').pack(anchor='w')
        filters = ttk.Frame(outer)
        filters.pack(fill='x', pady=10)
        for label, var, values in [('Tipo', self.kind, ['Todos', 'speech', 'singing']),
                                    ('Grupo', self.split, ['Todos', 'train', 'validation', 'test'])]:
            ttk.Label(filters, text=label).pack(side='left', padx=(0, 5))
            box = ttk.Combobox(filters, textvariable=var, values=values, state='readonly', width=13)
            box.pack(side='left', padx=(0, 12))
            box.bind('<<ComboboxSelected>>', lambda _: self.refresh())
        ttk.Label(filters, text='Minutos por tipo:').pack(side='left')
        ttk.Entry(filters, textvariable=self.minutes, width=7).pack(side='left', padx=6)
        ttk.Button(filters, text='Selección automática', command=self.auto_select).pack(side='left')
        table = ttk.Frame(outer)
        table.pack(fill='both', expand=True)
        columns = ['selected', 'person', 'kind', 'split', 'seconds', 'status', 'file']
        self.tree = ttk.Treeview(table, columns=columns, show='headings', selectmode='extended')
        for col, label, width in zip(columns, ['Incluir', 'Persona', 'Tipo', 'Grupo', 'Segundos', 'Revisión técnica', 'Archivo'], [55, 160, 70, 85, 65, 160, 360]):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, minwidth=45)
        scrollbar = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        self.tree.bind('<Double-1>', lambda _: self.toggle())
        buttons = ttk.Frame(outer)
        buttons.pack(fill='x', pady=8)
        for label, action in [('Incluir / excluir filas marcadas', self.toggle),
                              ('Guardar selección…', self.save)]:
            ttk.Button(buttons, text=label, command=action).pack(side='left', padx=(0, 8))
        player = ttk.LabelFrame(outer, text='Escucha del original', padding=8)
        player.pack(fill='x', pady=(0, 8))
        ttk.Label(player, textvariable=self.player_label, wraplength=1050).pack(anchor='w')
        controls = ttk.Frame(player)
        controls.pack(fill='x', pady=(5, 0))
        ttk.Button(controls, text='Reproducir', command=self.listen).pack(side='left')
        ttk.Button(controls, text='Pausa / continuar', command=self.player.pause).pack(side='left', padx=6)
        ttk.Button(controls, text='Detener', command=self.player.stop).pack(side='left')
        self.audio_progress = ttk.Progressbar(controls, maximum=1)
        self.audio_progress.pack(side='left', fill='x', expand=True, padx=10)
        ttk.Label(controls, textvariable=self.player_time).pack(side='left')
        ttk.Label(controls, text='Volumen').pack(side='left', padx=(12, 4))
        volume = ttk.Scale(controls, from_=0, to=1, length=100,
                           command=lambda value: setattr(self.player, 'volume', float(value)))
        volume.set(self.player.volume)
        volume.pack(side='left')
        ttk.Label(outer, textvariable=self.summary, wraplength=1100).pack(anchor='w')
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(8, 3))
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(anchor='w')
        self.log = tk.Text(outer, height=5, state='disabled', wrap='word')
        self.log.pack(fill='x', pady=(5, 0))
        window.protocol('WM_DELETE_WINDOW', self.close)
        window.after(100, self.poll)

    def available(self):
        if self.busy:
            messagebox.showinfo('Proceso activo', 'Espera a que termine la operación actual.')
        return not self.busy

    def choose_folder(self):
        if not self.available(): return
        value = filedialog.askdirectory(initialdir=self.root.get())
        if value:
            self.player.stop()
            self.playing_path = None
            self.root.set(value)
            self.source = None
            self.chosen.clear()
            self.refresh()

    def target_seconds(self):
        value = float(self.minutes.get().replace(',', '.')) * 60
        if not 0 < value <= 86400: raise ValueError('Indica entre 0 y 1440 minutos por tipo.')
        return value

    def run(self, commands, done=None):
        if not self.available(): return
        self.busy = True
        self.progress.start()
        self.status.set('Trabajando; puedes consultar el registro de progreso.')
        def worker():
            try:
                for command in commands:
                    with subprocess.Popen([sys.executable, '-u', '-m', *command], cwd=ROOT,
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          text=True, encoding='utf-8', errors='replace',
                                          env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) as process:
                        for line in process.stdout:
                            self.events.put(('log', line))
                        if process.wait(): raise RuntimeError('La operación no terminó correctamente. Consulta el registro.')
                self.events.put(('done', done))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        position = self.player.position / self.player.rate
        duration = self.player.duration
        self.audio_progress['value'] = position / duration if duration else 0
        def stamp(seconds):
            return f'{int(seconds) // 60}:{int(seconds) % 60:02d}'
        state = ' · Pausa' if self.player.paused else ''
        self.player_time.set(f'{stamp(position)} / {stamp(duration)}{state}')
        for _ in range(200):
            try: event, value = self.events.get_nowait()
            except queue.Empty: break
            if event == 'log':
                self.log.configure(state='normal')
                self.log.insert('end', value)
                self.log.see('end')
                self.log.configure(state='disabled')
            else:
                self.busy = False
                self.progress.stop()
                self.status.set('Operación terminada.' if event == 'done' else value)
                if event == 'done' and value:
                    try: value()
                    except Exception as exc: messagebox.showerror('Inventario', str(exc))
                elif event == 'error': messagebox.showerror('Operación', value)
        self.window.after(100, self.poll)

    def download(self):
        self.run([['afc_lab.fetch_samples', '--data-root', self.root.get()],
                  ['afc_lab.fetch_vctk_samples', '--data-root', self.root.get()]], self.audit)

    def audit(self):
        if not self.available(): return
        try: seconds = self.target_seconds()
        except ValueError as exc:
            messagebox.showerror('Duración', str(exc)); return
        output = ROOT / 'outputs' / 'training' / 'gui' / datetime.now().strftime('%Y%m%d-%H%M%S-%f') / 'inventory.json'
        self.run([['afc_lab.corpus', '--data-root', self.root.get(), '--output', str(output),
                   '--seconds-per-kind', str(seconds)]], lambda: self.load(output))

    def open_manifest(self):
        if not self.available(): return
        path = filedialog.askopenfilename(initialdir=ROOT / 'outputs' / 'training', filetypes=[('Inventario JSON', '*.json')])
        if path:
            try: self.load(Path(path))
            except Exception as exc: messagebox.showerror('Inventario', str(exc))

    def load(self, path):
        source = json.loads(path.read_text(encoding='utf-8'))
        if source.get('schema_version') != 2 or source.get('sample_rate') != 48000 or 'inventory' not in source:
            raise ValueError('Se requiere un inventario AFC a 48 kHz de versión 2.')
        self.source = source
        self.player.stop()
        self.playing_path = None
        original_root = Path(source['data_root_hint'])
        actual_root = original_root if original_root.is_dir() else ROOT / 'data' / 'raw'
        self.root.set(str(actual_root))
        # Historical JSON/checkpoint hashes remain intact after relocation.
        # Only a newly exported selection receives the current local root hint.
        self.source = {**source, 'data_root_hint': str(actual_root)}
        self.chosen = {r['path'] for r in source['records'] if r['eligible']}
        self.status.set(f'Inventario abierto: {path}')
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if not self.source:
            self.summary.set('Sin inventario cargado.'); return
        for index, row in enumerate(self.source['inventory']):
            if self.kind.get() not in ('Todos', row['kind']) or self.split.get() not in ('Todos', row['split']): continue
            self.tree.insert('', 'end', iid=str(index), values=(
                'Sí' if row['path'] in self.chosen else '', row['identity'], row['kind'], row['split'],
                f"{row['seconds']:.1f}", 'Apta; escucha pendiente' if row['eligible'] else ', '.join(row['reasons']), row['path']))
        selected = selection_manifest(self.source, self.chosen, 3600)
        amounts = ' · '.join(f'{key}: {value / 60:.1f} min' for key, value in selected['seconds'].items())
        self.summary.set(f"{len(selected['records'])} archivos incluidos. {amounts}\nEscucha pendiente; las exclusiones técnicas y los grupos se conservan.")

    def auto_select(self):
        if not self.available() or not self.source: return
        try:
            self.chosen = {r['path'] for r in select_pilot(self.source['inventory'], self.target_seconds())}
            self.refresh()
        except ValueError as exc: messagebox.showerror('Duración', str(exc))

    def toggle(self):
        if not self.available() or not self.source: return
        for index in self.tree.selection():
            row = self.source['inventory'][int(index)]
            if not row['eligible']: continue
            if row['path'] in self.chosen: self.chosen.remove(row['path'])
            else: self.chosen.add(row['path'])
        self.refresh()

    def listen(self):
        if not self.source or not self.tree.selection(): return
        try:
            row = self.source['inventory'][int(self.tree.selection()[0])]
            root = Path(self.root.get()).resolve()
            path = (root / row['path']).resolve()
            if not path.is_relative_to(root) or path.suffix.lower() not in ('.wav', '.flac'):
                raise ValueError('Ruta de audio inválida.')
            if sha256(path) != row['sha256']: raise ValueError('El original cambió desde el inventario; vuelve a analizarlo.')
            if path != self.playing_path:
                self.playing_path = None
                self.player.load(path)
                self.playing_path = path
            self.player_label.set(f"{row['identity']} · {row['kind']} · {row['path']}")
            self.player.play()
        except Exception as exc: messagebox.showerror('Audio', str(exc))

    def save(self):
        if not self.available() or not self.source: return
        try: payload = selection_manifest(self.source, self.chosen, self.target_seconds())
        except ValueError as exc:
            messagebox.showerror('Duración', str(exc)); return
        if not payload['records']:
            messagebox.showinfo('Selección vacía', 'Incluye grabaciones antes de guardar.'); return
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='pilot-selection.json', filetypes=[('Inventario JSON', '*.json')])
        if path:
            try:
                Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
                self.status.set(f'Selección guardada: {path}. Revisión auditiva pendiente.')
            except OSError as exc: messagebox.showerror('Guardar', str(exc))

    def close(self):
        if self.available():
            self.player.stop()
            self.window.destroy()


def main():
    window = tk.Tk()
    app = CorpusApp(window)
    if len(sys.argv) == 2:
        app.load(Path(sys.argv[1]))
    window.mainloop()


if __name__ == '__main__':
    main()
