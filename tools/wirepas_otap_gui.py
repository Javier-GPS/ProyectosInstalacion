#!/usr/bin/env python3
"""GUI sencilla para tools/wirepas_otap.py (tkinter, sin dependencias extra).

Fichero independiente: se puede borrar sin afectar al CLI.
    python wirepas_otap_gui.py
"""
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import dualmcu_app2_wpc_stack as d
import wirepas_otap as w


class EscritorCola:
    """Redirige print() del hilo de trabajo a la cola de la GUI."""

    def __init__(self, cola):
        self.cola = cola

    def write(self, txt):
        if txt:
            self.cola.put(("log", txt))

    def flush(self):
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.cola = queue.Queue()
        self.sink_actual = None
        self.trabajando = False
        self.cancelar = threading.Event()
        root.title("Wirepas OTAP")
        self._widgets()
        root.after(100, self._drenar)

    def _widgets(self):
        fila = ttk.Frame(self.root)
        fila.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(fila, text="Puerto:").grid(row=0, column=0, sticky="e")
        self.e_puerto = ttk.Entry(fila, width=10)
        self.e_puerto.insert(0, "COM5")
        self.e_puerto.grid(row=0, column=1, padx=4)
        ttk.Label(fila, text="Baudios:").grid(row=0, column=2, sticky="e")
        self.e_baudios = ttk.Entry(fila, width=8)
        self.e_baudios.insert(0, "115200")
        self.e_baudios.grid(row=0, column=3, padx=4)
        self.b_vecinos = ttk.Button(fila, text="Vecinos", command=self.acc_vecinos)
        self.b_vecinos.grid(row=0, column=4, padx=4)
        self.b_estado = ttk.Button(fila, text="Estado sink", command=self.acc_estado)
        self.b_estado.grid(row=0, column=5, padx=4)

        fila2 = ttk.Frame(self.root)
        fila2.pack(fill="x", padx=8, pady=2)
        ttk.Label(fila2, text="Fichero:").grid(row=0, column=0, sticky="e")
        self.e_fichero = ttk.Entry(fila2, width=42)
        self.e_fichero.grid(row=0, column=1, padx=4)
        ttk.Button(fila2, text="...", width=3, command=self.acc_explorar).grid(row=0, column=2)
        ttk.Label(fila2, text="Seq:").grid(row=0, column=3, sticky="e")
        self.e_seq = ttk.Spinbox(fila2, from_=1, to=254, width=5)
        self.e_seq.grid(row=0, column=4, padx=4)
        ttk.Label(fila2, text="Nodos:").grid(row=0, column=5, sticky="e")
        self.e_nodos = ttk.Entry(fila2, width=14)
        self.e_nodos.grid(row=0, column=6, padx=4)
        ttk.Label(fila2, text="Espera(s):").grid(row=0, column=7, sticky="e")
        self.e_espera = ttk.Entry(fila2, width=6)
        self.e_espera.insert(0, "600")
        self.e_espera.grid(row=0, column=8, padx=4)
        ttk.Label(fila2, text="Reinicio(s):").grid(row=0, column=9, sticky="e")
        self.e_reinicio = ttk.Entry(fila2, width=6)
        self.e_reinicio.insert(0, "120")
        self.e_reinicio.grid(row=0, column=10, padx=4)

        fila3 = ttk.Frame(self.root)
        fila3.pack(fill="x", padx=8, pady=2)
        self.b_otap = ttk.Button(fila3, text="Iniciar OTAP", command=self.acc_otap)
        self.b_otap.pack(side="left")
        self.b_parar = ttk.Button(fila3, text="Detener", command=self.acc_parar, state="disabled")
        self.b_parar.pack(side="left", padx=6)
        self.v_raw = tk.BooleanVar(value=False)
        ttk.Checkbutton(fila3, text="raw (sin cabecera CRC)", variable=self.v_raw).pack(
            side="left", padx=6
        )
        ttk.Label(
            fila3,
            text="Sin 'Nodos' = red completa. Con 'Nodos' = esperar llegada y procesar solo esos.",
        ).pack(side="left", padx=8)

        sink_box = ttk.LabelFrame(self.root, text="Actualizacion sink dual-MCU: app + WPC stack")
        sink_box.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(sink_box, text="Fichero:").grid(row=0, column=0, sticky="e")
        self.e_sink_fichero = ttk.Entry(sink_box, width=52)
        fichero_sink = Path(__file__).with_name("dualmcu_app2_wpc_stack.otap")
        if fichero_sink.exists():
            self.e_sink_fichero.insert(0, str(fichero_sink))
        self.e_sink_fichero.grid(row=0, column=1, padx=4)
        ttk.Button(sink_box, text="...", width=3, command=self.acc_explorar_sink).grid(
            row=0, column=2
        )
        ttk.Label(sink_box, text="Seq:").grid(row=0, column=3, sticky="e")
        self.e_sink_seq = ttk.Entry(sink_box, width=7)
        self.e_sink_seq.insert(0, "auto")
        self.e_sink_seq.grid(row=0, column=4, padx=4)
        ttk.Label(sink_box, text="Reconexion(s):").grid(row=0, column=5, sticky="e")
        self.e_sink_reconexion = ttk.Entry(sink_box, width=7)
        self.e_sink_reconexion.insert(0, "180")
        self.e_sink_reconexion.grid(row=0, column=6, padx=4)
        self.b_sink_estado = ttk.Button(sink_box, text="Estado dual-MCU", command=self.acc_sink_estado)
        self.b_sink_estado.grid(row=0, column=7, padx=4)
        self.b_sink_otap = ttk.Button(sink_box, text="Actualizar sink", command=self.acc_sink_otap)
        self.b_sink_otap.grid(row=0, column=8, padx=4)
        ttk.Label(
            sink_box,
            text="Proceso local: STOP -> carga directa -> UPDATE -> reboot -> verificacion.",
        ).grid(row=1, column=0, columnspan=9, sticky="w", padx=4, pady=(2, 3))

        self.txt = tk.Text(self.root, height=22, width=110, font=("Consolas", 9))
        self.txt.tag_config("error", foreground="#c00")
        sb = ttk.Scrollbar(self.root, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(6, 8))
        sb.pack(side="right", fill="y", pady=(6, 8))

    def log(self, txt):
        es_err = txt.startswith("ERROR") or "rechazado" in txt or "no llego" in txt
        self.txt.insert("end", txt, "error" if es_err else ())
        self.txt.see("end")

    def _drenar(self):
        while not self.cola.empty():
            tipo, dato = self.cola.get()
            if tipo == "log":
                self.log(dato)
            else:
                self._fin_tarea()
        self.root.after(100, self._drenar)

    def _fin_tarea(self):
        self.trabajando = False
        for b in (self.b_vecinos, self.b_estado, self.b_otap, self.b_sink_estado, self.b_sink_otap):
            b.config(state="normal")
        self.b_parar.config(state="disabled")
        if self.sink_actual:
            try:
                self.sink_actual.close()
            except Exception:
                pass
            self.sink_actual = None

    def _abrir_sink(self):
        puerto = self.e_puerto.get().strip()
        baudios = int(self.e_baudios.get())
        w.log(f"[CONEXION] abriendo {puerto} @ {baudios}...")
        s = w.Sink(puerto, baudios)
        self.sink_actual = s
        if not w.probar(s):
            self._cerrar()
            raise IOError(
                f"el sink no contesta en {puerto} @{baudios} "
                "(¿puerto y baudios correctos? ¿otro programa lo esta usando?)"
            )
        w.log("[CONEXION] sink responde")
        w.drenar(s)
        return s

    def _cerrar(self):
        if self.sink_actual:
            try:
                self.sink_actual.close()
            except Exception:
                pass
            self.sink_actual = None

    def _lanzar(self, tarea):
        if self.trabajando:
            return
        try:
            int(self.e_baudios.get())
        except ValueError:
            self.log("ERROR: baudios invalidos\n")
            return
        self.trabajando = True
        self.cancelar.clear()
        for b in (self.b_vecinos, self.b_estado, self.b_otap, self.b_sink_estado, self.b_sink_otap):
            b.config(state="disabled")
        self.b_parar.config(state="normal")

        def hilo():
            viejos = sys.stdout, sys.stderr
            escritor = EscritorCola(self.cola)
            sys.stdout = sys.stderr = escritor
            try:
                tarea()
                w.log("[OK] terminado\n")
            except InterruptedError:
                w.log("[CANCELADO] operacion detenida\n")
            except Exception as e:
                w.log(f"ERROR: {e}\n")
            finally:
                sys.stdout, sys.stderr = viejos
                self.cola.put(("fin", None))

        threading.Thread(target=hilo, daemon=True).start()

    def acc_explorar(self):
        ruta = filedialog.askopenfilename(filetypes=[("OTAP", "*.otap *.spb"), ("Todos", "*.*")])
        if ruta:
            self.e_fichero.delete(0, "end")
            self.e_fichero.insert(0, ruta)

    def acc_explorar_sink(self):
        ruta = filedialog.askopenfilename(filetypes=[("OTAP combinado", "*.otap"), ("Todos", "*.*")])
        if ruta:
            self.e_sink_fichero.delete(0, "end")
            self.e_sink_fichero.insert(0, ruta)

    def acc_vecinos(self):
        def tarea():
            self._abrir_sink()
            try:
                vs = w.descubrir_vecinos(self.sink_actual)
            finally:
                self._cerrar()
            w.log(f"{'DIRECCION':>10}  LINK%  RSSI  COST  CH  TIPO  TXP  RXP  HACE(s)")
            for v in vs:
                w.log(
                    f"{v['add']:>10}  {v['link']:>5}  {v['rssi']:>4}  {v['cost']:>4}  "
                    f"{v['ch']:>2}  0x{v['tipo']:02X}  {v['tx_power']:>3}  {v['rx_power']:>3}  {v['edad']:>6}"
                )

        self._lanzar(tarea)

    def acc_estado(self):
        def tarea():
            st = w.status(self.sink_actual)
            w.log(
                f"sink: len={st['len']} crc=0x{st['crc']:04X} seq={st['seq']} "
                f"tipo=0x{st['tipo_scratchpad']:02X} estado=0x{st['estado_scratchpad']:02X}"
            )

        def con_sink():
            self._abrir_sink()
            try:
                tarea()
            finally:
                self._cerrar()

        self._lanzar(con_sink)

    def acc_sink_estado(self):
        def tarea():
            st = d.estado(self.sink_actual)
            w.log(
                f"sink dual-MCU: scratchpad={st['len']}/0x{st['crc']:04X}/{st['seq']} "
                f"tipo=0x{st['tipo']:02X} estado=0x{st['estado']:02X}; "
                f"procesado={st['procesado_len']}/0x{st['procesado_crc']:04X}/{st['procesado_seq']} "
                f"area=0x{st['area_firmware']:08X} fw={'.'.join(map(str, st['version']))}\n"
            )

        def con_sink():
            self._abrir_sink()
            try:
                tarea()
            finally:
                self._cerrar()

        self._lanzar(con_sink)

    def acc_sink_otap(self):
        fichero = self.e_sink_fichero.get().strip()
        seq_txt = self.e_sink_seq.get().strip().lower()
        try:
            reconexion = int(self.e_sink_reconexion.get())
            seq = None if seq_txt in ("", "auto") else int(seq_txt)
        except ValueError:
            self.log("ERROR: secuencia o reconexion invalidas\n")
            return
        if not fichero:
            self.log("ERROR: hace falta el fichero OTAP combinado del sink\n")
            return
        if reconexion < 30:
            self.log("ERROR: reconexion debe ser de al menos 30 segundos\n")
            return

        def tarea():
            self._abrir_sink()
            try:
                if not w.es_sink(self.sink_actual):
                    raise IOError("este puerto no corresponde a un sink")
                d.actualizar(
                    self.sink_actual,
                    fichero,
                    seq=seq,
                    reconexion_s=reconexion,
                    cancelar=self.cancelar.is_set,
                )
            finally:
                self._cerrar()

        self._lanzar(tarea)

    def acc_otap(self):
        fichero = self.e_fichero.get().strip()
        nodos_txt = self.e_nodos.get().strip()
        try:
            seq = int(self.e_seq.get())
            espera = int(self.e_espera.get())
            reinicio = int(self.e_reinicio.get())
            nodos = [int(x) for x in nodos_txt.replace(";", ",").split(",") if x.strip()] if nodos_txt else []
        except ValueError:
            self.log(
                "ERROR: seq, espera, reinicio o nodos invalidos "
                "(nodos: numeros separados por comas)\n"
            )
            return
        if not 10 <= reinicio <= 32767:
            self.log("ERROR: reinicio debe estar entre 10 y 32767 segundos\n")
            return
        if not fichero and not nodos:
            self.log("ERROR: hace falta fichero o lista de nodos\n")
            return

        def tarea():
            self._abrir_sink()
            try:
                if not w.es_sink(self.sink_actual):
                    raise IOError(
                        "este puerto es un nodo regular, NO un sink: "
                        "el OTAP y el Remote API solo se pueden hacer desde el sink"
                    )
                todos = not nodos
                nodos_objetivo = nodos
                if todos:
                    w.log("[OTAP] descubriendo inventario completo antes de subir...")
                    estados = w.descubrir_nodos(
                        self.sink_actual, cancelar=self.cancelar.is_set
                    )
                    if not estados:
                        raise IOError("ningun nodo respondio al descubrimiento broadcast")
                    nodos_objetivo = sorted(estados)
                    w.log(f"[OTAP] inventario fijado: {len(nodos_objetivo)} nodo(s)")
                if fichero:
                    cuerpo, crc, _ = w.load_otap(fichero, self.v_raw.get())
                    w.log(f"[OTAP] {fichero}: {len(cuerpo)} B, crc=0x{crc:04X}, seq={seq}")
                    w.otap(
                        self.sink_actual, cuerpo, crc, seq, 1, 0,
                        procesar=False, cancelar=self.cancelar.is_set,
                    )
                    esperado = (len(cuerpo), crc, seq)
                else:
                    st = w.status(self.sink_actual)
                    esperado = (st["len"], st["crc"], seq)
                    if st["len"] == 0 or st["seq"] != seq:
                        raise IOError(f"el sink no tiene un scratchpad con seq={seq}")
                    w.log(f"[OTAP] reutilizando scratchpad del sink: {esperado}")
                w.verificar_y_procesar(
                    self.sink_actual, esperado, nodos_objetivo, espera, broadcast=todos,
                    intervalo_s=20, cancelar=self.cancelar.is_set, reinicio_s=reinicio,
                )
            finally:
                self._cerrar()

        self._lanzar(tarea)

    def acc_parar(self):
        self.cancelar.set()
        self.b_parar.config(state="disabled")
        w.log("[CANCELANDO] esperando que termine la operacion en curso...")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
