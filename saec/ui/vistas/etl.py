"""Pantalla del proceso ETL (rol administrador)."""
from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ...config import SETTINGS, base_dir
from ...etl import demo_data
from ...etl.extract import DESCRIPCION_TIPO, detectar_tipo
from ...etl.pipeline import ETLPipeline
from ...repositories import ETLRepository
from ..widgets import Tabla, Tarea


class ETLView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.repo = ETLRepository()
        self.archivos: list[Path] = []
        self.tarea: Tarea | None = None
        ttk.Label(self, text="Proceso ETL — Carga de datasets oficiales", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self, text="Formatos: CSV / XLSX / GeoJSON. El tipo de cada archivo se detecta por sus columnas. "
                             "Cargar el mismo archivo otra vez reemplaza sus datos (no duplica).",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
        arriba = ttk.Frame(self)
        arriba.pack(fill="x")
        arriba.columnconfigure(0, weight=3); arriba.columnconfigure(1, weight=2)
        izq = ttk.Frame(arriba, style="Card.TFrame", padding=10)
        izq.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(izq, text="Archivos a procesar", style="H2.TLabel").pack(anchor="w")
        self.lista = ttk.Treeview(izq, columns=("archivo", "tipo", "tam"), show="headings", height=5)
        for c, t, w in (("archivo", "Archivo", 260), ("tipo", "Tipo detectado", 260), ("tam", "Tamaño", 80)):
            self.lista.heading(c, text=t); self.lista.column(c, width=w, anchor="w")
        self.lista.pack(fill="x", pady=6)
        b = ttk.Frame(izq, style="Card.TFrame")
        b.pack(fill="x")
        ttk.Button(b, text="Agregar archivos…", command=self.agregar).pack(side="left")
        ttk.Button(b, text="Quitar seleccionado", command=self.quitar).pack(side="left", padx=6)
        ttk.Button(b, text="Generar datos de demostración", command=self.demo).pack(side="left")
        der = ttk.Frame(arriba, style="Card.TFrame", padding=10)
        der.grid(row=0, column=1, sticky="nsew")
        ttk.Label(der, text="Población objetivo (settings.ini)", style="H2.TLabel").pack(anchor="w")
        p = SETTINGS.poblacion
        ttk.Label(der, style="Card.TLabel", justify="left", text=(
            f"Edad: {p.edad_min}–{p.edad_max} años\nAños: {p.anio_min}–{p.anio_max}\n"
            f"Estratos: {', '.join(map(str, p.estratos))}\nLocalidades: {', '.join(p.localidades)}\n"
            "Enfermedades: EPOC (J44), asma (J45), diabetes (E11)")).pack(anchor="w", pady=4)
        self.v_staging = tk.BooleanVar(value=True)
        ttk.Checkbutton(der, text="Guardar copia cruda en el esquema staging", variable=self.v_staging).pack(anchor="w")
        bb = ttk.Frame(der, style="Card.TFrame")
        bb.pack(anchor="w", pady=(8, 0))
        self.b_run = ttk.Button(bb, text="▶ Ejecutar ETL", style="Accent.TButton", command=self.ejecutar)
        self.b_run.pack(side="left")
        self.b_cancel = ttk.Button(bb, text="Cancelar", command=self.cancelar, state="disabled")
        self.b_cancel.pack(side="left", padx=6)

        prog = ttk.Frame(self, style="Card.TFrame", padding=10)
        prog.pack(fill="x", pady=8)
        self.lbl_prog = ttk.Label(prog, text="Listo.", style="Card.TLabel")
        self.lbl_prog.pack(anchor="w")
        self.barra = ttk.Progressbar(prog, maximum=100)
        self.barra.pack(fill="x", pady=4)

        abajo = ttk.Notebook(self)
        abajo.pack(fill="both", expand=True)
        fl = ttk.Frame(abajo, padding=4)
        self.log = tk.Text(fl, height=10, bg="#1E2329", fg="#D7DEE5", font=("DejaVu Sans Mono", 9), relief="flat",
                           padx=8, pady=6)
        self.log.pack(fill="both", expand=True)
        abajo.add(fl, text="Bitácora de ejecución")
        fh = ttk.Frame(abajo, padding=4)
        self.hist = Tabla(fh, alto=8)
        self.hist.pack(fill="both", expand=True)
        self.hist.tv.bind("<Double-1>", self.ver_rechazos)
        ttk.Label(fh, text="Doble clic en una ejecución para ver sus registros rechazados.", style="Sub.TLabel").pack(anchor="w")
        abajo.add(fh, text="Historial de cargas")
        self.abajo = abajo

    def al_mostrar(self):
        self.cargar_historial()

    def cargar_historial(self):
        Tarea(self, lambda t: self.repo.historial(), lambda df: self.hist.mostrar(
            df.rename(columns={"id": "ID", "inicio": "Inicio", "fuente": "Archivo", "leidos": "Leídos",
                               "cargados": "Cargados", "rechazados": "Rechazados", "estado": "Estado"}),
            {"Archivo": 260, "ID": 50})).iniciar()

    def _agregar_rutas(self, rutas):
        for r in rutas:
            r = Path(r)
            if r in self.archivos:
                continue
            try:
                tipo = detectar_tipo(r)
            except Exception as exc:  # noqa: BLE001
                tipo = None
                self._log(f"No se pudo leer {r.name}: {exc}")
            if tipo is None:
                messagebox.showwarning("ETL", f"{r.name}: formato no reconocido. Revise las columnas (ver manual).", parent=self)
                continue
            self.archivos.append(r)
            mb = r.stat().st_size / 1e6
            self.lista.insert("", "end", iid=str(r), values=(r.name, DESCRIPCION_TIPO[tipo], f"{mb:,.1f} MB"))

    def agregar(self):
        rutas = filedialog.askopenfilenames(parent=self, title="Seleccione los datasets",
                                            filetypes=[("Datos", "*.csv *.xlsx *.xls *.geojson *.json"), ("Todos", "*.*")])
        self._agregar_rutas(rutas)

    def quitar(self):
        for iid in self.lista.selection():
            self.archivos.remove(Path(iid))
            self.lista.delete(iid)

    def demo(self):
        carpeta = base_dir() / "datos_demo"
        self._log("Generando datos de demostración…")

        def fin(archivos):
            self._agregar_rutas([a for a in archivos if "rips_agregado" not in a.name])
            self._log(f"Datos de demostración generados en {carpeta} (sintéticos, solo para pruebas). "
                      "El archivo rips_agregado_demo.csv muestra el formato del RIPS público.")
        Tarea(self, lambda t: demo_data.generar(carpeta), fin).iniciar()

    def _log(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def ejecutar(self):
        if not self.archivos:
            return messagebox.showinfo("ETL", "Agregue al menos un archivo.", parent=self)
        self.b_run.config(state="disabled"); self.b_cancel.config(state="normal")
        self.abajo.select(0)
        inicio = time.time()
        archivos, uid, staging = list(self.archivos), self.app.usuario.id_usuario, self.v_staging.get()

        def trabajo(t: Tarea):
            return ETLPipeline(archivos, uid, notificar=t.notificar, cancelar=t.cancelar, guardar_staging=staging).run()

        def progreso(msg, pct):
            self._log(msg)
            if pct is not None:
                self.barra["value"] = pct
            self.lbl_prog.config(text=f"{msg.split('] ', 1)[-1][:110]}  ·  {time.time() - inicio:,.0f} s")

        def fin(res):
            self.b_run.config(state="normal"); self.b_cancel.config(state="disabled")
            cargados = sum(r.atenciones for r in res)
            self.lbl_prog.config(text=f"ETL finalizado en {time.time() - inicio:,.0f} s · {cargados:,} atenciones cargadas".replace(",", "."))
            self.cargar_historial()
            self.app.datos_actualizados()
            for iid in self.lista.get_children():
                self.lista.delete(iid)
            self.archivos.clear()
            if messagebox.askyesno("ETL", "Carga completada. ¿Desea ver el diagnóstico actualizado?", parent=self):
                self.app.mostrar("diagnostico")

        def error(exc):
            self.b_run.config(state="normal"); self.b_cancel.config(state="disabled")
            self.lbl_prog.config(text=f"Error: {exc}")
            self.cargar_historial()
            messagebox.showerror("ETL", f"{exc}\n\nSe hizo ROLLBACK: la base de datos no cambió.", parent=self)
        self.tarea = Tarea(self, trabajo, fin, error, progreso).iniciar()

    def cancelar(self):
        if self.tarea:
            self.tarea.cancelar.set()
            self._log("Cancelando… (se deshará la carga del archivo en curso)")

    def ver_rechazos(self, _e):
        sel = self.hist.tv.selection()
        if not sel:
            return
        id_e = int(self.hist.tv.item(sel[0], "values")[0])
        win = tk.Toplevel(self)
        win.title(f"Registros rechazados — ejecución #{id_e}")
        win.geometry("900x420")
        t = Tabla(win, alto=16)
        t.pack(fill="both", expand=True, padx=8, pady=8)
        Tarea(win, lambda _t: self.repo.rechazos(id_e),
              lambda df: t.mostrar(df.rename(columns={"motivo": "Motivo", "registro": "Registro original"}),
                                   {"Motivo": 200, "Registro original": 650})).iniciar()
