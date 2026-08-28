#!/usr/bin/env python3
"""Prueba directa de envio y recepcion Wirepas por UART/USB.

La recepcion real solo puede comprobarse si la aplicacion del nodo remoto
devuelve un eco o un ACK.

Uso:
    python wirepas_message_test_gui.py
"""
import queue
import re
import serial
import struct
import threading
import time
import tkinter as tk
from tkinter import ttk

import wirepas_otap as w


MSAP_ATTRIBUTE_READ_REQUEST = 0x0C
MSAP_STACK_STATUS = 1
MSAP_PDU_BUFFER_USAGE = 2
MSAP_PDU_BUFFER_CAPACITY = 3
DSAP_DATA_RX_INDICATION = 0x03
TX_OPTIONS = 0x00
TX_RESULTS = {
    0x09: "valor invalido (endpoint o parametro)",
    0x04: "sin memoria en el stack",
    0x05: "destino desconocido",
    0x0A: "acceso denegado",
}


class TxRejected(IOError):
    def __init__(self, result):
        detail = TX_RESULTS.get(result, "codigo no documentado")
        super().__init__(f"TX rechazada (result=0x{result:02X}, {detail})")
        self.result = result


def read_pdu_attribute(sink, attribute):
    response = sink.req(
        MSAP_ATTRIBUTE_READ_REQUEST,
        struct.pack("<H", attribute),
        2,
    )
    if len(response) < 5 or response[0] != 0:
        result = response[0] if response else 0xFF
        raise IOError(f"atributo {attribute} rechazado (result=0x{result:02X})")
    if int.from_bytes(response[1:3], "little") != attribute or response[3] != 1:
        raise IOError(f"respuesta invalida para atributo {attribute}: {response.hex()}")
    return response[4]


def read_pdu_buffers(sink):
    return {
        "used": read_pdu_attribute(sink, MSAP_PDU_BUFFER_USAGE),
        "free": read_pdu_attribute(sink, MSAP_PDU_BUFFER_CAPACITY),
    }


def parse_payload(text):
    tokens = [token for token in re.split(r"[\s,;]+", text.strip()) if token]
    if not tokens:
        raise ValueError("Payload bytes esta vacio")
    values = []
    for token in tokens:
        try:
            value = int(token, 0) if token.lower().startswith("0x") else int(token, 10)
        except ValueError as error:
            raise ValueError(f"byte invalido: {token}") from error
        if not 0 <= value <= 255:
            raise ValueError(f"cada byte debe estar entre 0 y 255: {token}")
        values.append(value)
    return bytes(values)


def send_data(sink, destination, destination_ep, apdu, pdu_id):
    payload = struct.pack(
        "<HBIBBBB",
        pdu_id,
        destination_ep,
        destination,
        destination_ep,
        0,
        TX_OPTIONS,
        len(apdu),
    ) + apdu
    response = sink.req(w.DSAP_DATA_TX_REQUEST, payload, 2)
    if len(response) < 4:
        raise IOError(f"confirmacion TX truncada: {response.hex()}")
    response_pdu, result, capacity = struct.unpack("<HBB", response[:4])
    if result:
        raise TxRejected(result)
    return response_pdu, capacity


def poll_rx_frames(sink):
    """Hace un poll y devuelve todas las indicaciones RX validas disponibles."""
    frames = []
    for frame in w._ciclo_poll(sink):
        if frame[0] != DSAP_DATA_RX_INDICATION or len(frame) < 20:
            continue
        length = frame[19]
        if len(frame) < 20 + length:
            continue
        frames.append({
            "source": int.from_bytes(frame[4:8], "little"),
            "source_ep": frame[8],
            "destination": int.from_bytes(frame[9:13], "little"),
            "destination_ep": frame[13],
            "payload": bytes(frame[20 : 20 + length]),
            "received_at": time.perf_counter(),
        })
    return frames


def ensure_stack_started(sink, log):
    status = read_pdu_attribute(sink, MSAP_STACK_STATUS)
    if status & 0x01:
        log(f"[STACK] detenido (status=0x{status:02X}); arrancando...")
        sink.arrancar_pila()
        status = read_pdu_attribute(sink, MSAP_STACK_STATUS)
    log(f"[STACK] activo (status=0x{status:02X})")


def wait_for_free_buffer(sink, total_buffers, cancel, log):
    """Espera sin enviar hasta que haya al menos un buffer PDU libre."""
    waiting_log = False
    while not cancel.is_set():
        try:
            free = read_pdu_attribute(sink, MSAP_PDU_BUFFER_CAPACITY)
            if free >= 1:
                return free
            if not waiting_log:
                log(f"[PDU] sin hueco: libres={free}/{total_buffers}; esperando...")
                waiting_log = True
        except (TimeoutError, IOError, serial.SerialException) as error:
            if not waiting_log:
                log(f"[PDU] sin lectura de libres ({error}); reintentando...")
                waiting_log = True
        time.sleep(0.01)
    raise InterruptedError("operacion cancelada")


def send_when_available(
    sink, destination, destination_ep, payload, pdu_id,
    total_buffers, wait, cancel, log, wait_for_capacity=None,
):
    """Reintenta el PDU usando la misma politica de capacidad configurada."""
    while True:
        try:
            return send_data(sink, destination, destination_ep, payload, pdu_id)
        except TxRejected as error:
            if error.result != 0x04 or not wait:
                raise
            log("[PDU] sink sin memoria; esperando un buffer libre para reintentar...")
            if wait_for_capacity is None:
                wait_for_free_buffer(sink, total_buffers, cancel, log)
            elif not wait_for_capacity():
                raise


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.worker = None
        self.cancel = threading.Event()
        root.title("Wirepas - prueba de mensajes USB")
        self.build_widgets()
        root.after(100, self.process_events)

    def build_widgets(self):
        frame = ttk.Frame(self.root, padding=8)
        frame.pack(fill="x")
        fields = [
            ("Puerto", "COM3"),
            ("Baudios", "115200"),
            ("Nodo destino", "279"),
            ("Max. mensajes", "1"),
            ("Pausa ms", "0"),
            ("Timeout RX s", "30"),
            ("Buffers TX (ocupados max.)", "4"),
            ("Buffers RX (libres min.)", "12"),
            ("EP destino", "1"),
            ("EP respuesta", "1"),
            ("Payload bytes", "0 0 2"),
        ]
        self.entries = {}
        for row, (name, value) in enumerate(fields):
            ttk.Label(frame, text=f"{name}:").grid(row=row, column=0, sticky="e", pady=2)
            entry = ttk.Entry(frame, width=32 if name == "Payload bytes" else 14)
            entry.insert(0, value)
            entry.grid(row=row, column=1, sticky="w", padx=5, pady=2)
            self.entries[name] = entry
            if name == "Payload bytes":
                entry.bind("<KeyRelease>", self.update_payload_hex)

        mode_row = len(fields)
        ttk.Label(frame, text="Comprobacion:").grid(row=mode_row, column=0, sticky="e", pady=2)
        self.mode = tk.StringVar(value="any")
        modes = (
            ("Cualquier respuesta del nodo (recomendado)", "any"),
            ("Eco exacto", "echo"),
        )
        for column, (text, value) in enumerate(modes, 1):
            ttk.Radiobutton(frame, text=text, variable=self.mode, value=value).grid(
                row=mode_row, column=column, sticky="w", padx=3
            )
        ttk.Label(frame, text="Hex convertido:").grid(
            row=mode_row + 1, column=0, sticky="e", pady=2
        )
        self.payload_hex = ttk.Label(frame, text="")
        self.payload_hex.grid(row=mode_row + 1, column=1, sticky="w", padx=5, pady=2)
        self.update_payload_hex()

        neighbors = ttk.LabelFrame(self.root, text="Envio a vecinos", padding=(8, 4))
        neighbors.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(neighbors, text="Mensajes por vecino:").pack(side="left")
        self.neighbor_count = ttk.Entry(neighbors, width=8)
        self.neighbor_count.insert(0, "1")
        self.neighbor_count.pack(side="left", padx=5)
        self.neighbors_button = ttk.Button(
            neighbors, text="Enviar a vecinos", command=self.start_neighbors
        )
        self.neighbors_button.pack(side="left", padx=4)
        ttk.Label(
            neighbors,
            text="Escanea vecinos directos y usa el payload y endpoints superiores.",
        ).pack(side="left", padx=8)

        buttons = ttk.Frame(self.root, padding=(8, 0, 8, 4))
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Enviar prueba", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Detener", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        ttk.Label(
            buttons,
            text="Eco/ACK remoto necesario para confirmar recepcion en el nodo.",
        ).pack(side="left", padx=8)

        self.output = tk.Text(self.root, height=24, width=120, font=("Consolas", 9))
        self.output.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def log(self, text):
        self.events.put(("log", text + "\n"))

    def process_events(self):
        while True:
            try:
                event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "log":
                self.output.insert("end", value)
                self.output.see("end")
            elif event == "done":
                self.worker = None
                self.start_button.config(state="normal")
                self.neighbors_button.config(state="normal")
                self.stop_button.config(state="disabled")
        self.root.after(100, self.process_events)

    def value(self, name):
        return self.entries[name].get().strip()

    def update_payload_hex(self, _event=None):
        try:
            value = parse_payload(self.value("Payload bytes"))
            self.payload_hex.config(text=value.hex(" ").upper())
        except ValueError:
            self.payload_hex.config(text="invalido")

    def parse_config(self, neighbors=False):
        node = None if neighbors else int(self.value("Nodo destino"), 0)
        count = int(
            self.neighbor_count.get().strip()
            if neighbors else self.value("Max. mensajes"),
            0,
        )
        pause_ms = int(self.value("Pausa ms"), 0)
        timeout_s = float(self.value("Timeout RX s"))
        tx_buffers = int(self.value("Buffers TX (ocupados max.)"), 0)
        rx_buffers = int(self.value("Buffers RX (libres min.)"), 0)
        destination_ep = int(self.value("EP destino"), 0)
        response_ep = int(self.value("EP respuesta"), 0)
        payload = parse_payload(self.value("Payload bytes"))
        if not 1 <= count <= 1000000:
            name = "Mensajes por vecino" if neighbors else "Max. mensajes"
            raise ValueError(f"{name} debe estar entre 1 y 1000000")
        if pause_ms < 0 or timeout_s < 0:
            raise ValueError("Pausa y timeout RX no pueden ser negativos")
        if tx_buffers < 1 or rx_buffers < 0:
            raise ValueError("Buffers TX debe ser >=1 y Buffers RX >=0")
        if not 0 <= destination_ep <= 255 or not 0 <= response_ep <= 255:
            raise ValueError("Los endpoints deben estar entre 0 y 255")
        if len(payload) > 180:
            raise ValueError("El payload no puede superar 180 bytes")
        return {
            "port": self.value("Puerto"),
            "baud": int(self.value("Baudios"), 0),
            "node": node,
            "count": count,
            "pause": pause_ms / 1000,
            "timeout": timeout_s,
            "tx_buffers": tx_buffers,
            "rx_buffers": rx_buffers,
            "destination_ep": destination_ep,
            "response_ep": response_ep,
            "payload": payload,
            "mode": self.mode.get(),
            "neighbors": neighbors,
        }

    def start(self):
        self._start(False)

    def start_neighbors(self):
        self._start(True)

    def _start(self, neighbors):
        if self.worker is not None:
            return
        try:
            config = self.parse_config(neighbors)
        except (ValueError, TypeError) as error:
            self.log(f"ERROR: {error}")
            return
        self.cancel.clear()
        self.start_button.config(state="disabled")
        self.neighbors_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.worker = threading.Thread(target=self.run, args=(config,), daemon=True)
        self.worker.start()

    def stop(self):
        self.cancel.set()
        self.stop_button.config(state="disabled")
        self.log("[CANCELANDO] esperando al ciclo actual...")

    def handle_rx(self, frame, config, pending, received):
        if frame["source_ep"] != config["response_ep"]:
            return None
        payload = frame["payload"]
        if config["mode"] == "any":
            match = next(
                (index for index, (_, node, _, _, _) in enumerate(pending)
                 if node == frame["source"]),
                None,
            )
            if match is None:
                return None
            sequence, _, node_sequence, _, tx_started = pending.pop(match)
        else:
            match = next(
                (index for index, (_, node, _, expected_payload, _) in enumerate(pending)
                 if node == frame["source"] and expected_payload == payload),
                None,
            )
            if match is None:
                self.log(f"[RX] respuesta no asociada: {payload.hex(' ').upper()}")
                return None
            sequence, _, node_sequence, _, tx_started = pending.pop(match)
        received.add((frame["source"], node_sequence))
        received_at = frame["received_at"]
        self.log(
            f"[RX {sequence} nodo={frame['source']} #{node_sequence}] "
            f"recibido desde {frame['source']} "
            f"({len(payload)} B, latencia={(received_at - tx_started) * 1000:.1f} ms): "
            f"{payload.hex(' ').upper()}"
        )
        return received_at

    def wait_for_all_responses(self, sink, config, pending, received):
        """Drena RX hasta recibir todas las respuestas pendientes."""
        deadline = time.monotonic() + config["timeout"]
        last_rx_at = None
        while pending and time.monotonic() < deadline and not self.cancel.is_set():
            matched = False
            for frame in poll_rx_frames(sink):
                received_at = self.handle_rx(frame, config, pending, received)
                if received_at is not None:
                    last_rx_at = received_at
                    matched = True
                    deadline = time.monotonic() + config["timeout"]
            if pending and not matched:
                time.sleep(0.01)
        if pending and not self.cancel.is_set():
            self.log(
                f"[RX] TIMEOUT tras {config['timeout']:.1f} s sin recibir otra respuesta; "
                f"siguen pendientes {len(pending)} respuesta(s)"
            )
        return last_rx_at, not pending

    def wait_for_tx_capacity(self, sink, config, pending, received, total):
        """Espera ocupacion TX valida mientras sigue drenando respuestas."""
        deadline = time.monotonic() + config["timeout"]
        waiting_log = False
        last_rx_at = None
        while not self.cancel.is_set():
            for frame in poll_rx_frames(sink):
                received_at = self.handle_rx(frame, config, pending, received)
                if received_at is not None:
                    last_rx_at = received_at
                    deadline = time.monotonic() + config["timeout"]
            try:
                free = read_pdu_attribute(sink, MSAP_PDU_BUFFER_CAPACITY)
                if not 0 <= free <= total:
                    raise IOError(f"capacidad de buffers invalida: {free}/{total}")
                used = total - free
                if used <= config["tx_buffers"] and free >= config["rx_buffers"]:
                    return used, free, last_rx_at
                if not waiting_log:
                    self.log(
                        f"[PDU] ocupados={used}/{total} libres={free}/{total}; "
                        f"esperando ocupados<={config['tx_buffers']} y "
                        f"libres>={config['rx_buffers']}"
                    )
                    waiting_log = True
            except (TimeoutError, IOError, serial.SerialException) as error:
                if not waiting_log:
                    self.log(f"[PDU] sin lectura de libres ({error}); reintentando...")
                    waiting_log = True
            if time.monotonic() >= deadline:
                self.log(
                    f"[PDU] TIMEOUT tras {config['timeout']:.1f} s sin recibir otra respuesta; "
                    f"no hay capacidad TX con ocupados<={config['tx_buffers']} "
                    f"y libres>={config['rx_buffers']}"
                )
                return None, None, last_rx_at
            time.sleep(0.01)
        raise InterruptedError("operacion cancelada")

    def run(self, config):
        sink = None
        try:
            sink = w.Sink(config["port"], config["baud"])
            if not w.probar(sink):
                raise IOError("el sink no responde")
            self.log("[CONEXION] sink responde")
            if not w.es_sink(sink):
                raise IOError("el dispositivo no es un sink")
            ensure_stack_started(sink, self.log)
            if config["neighbors"]:
                self.log("[VECINOS] escaneando vecinos directos...")
                neighbors = w.descubrir_vecinos(sink)
                targets = sorted({neighbor["add"] for neighbor in neighbors})
                if not targets:
                    raise IOError("el escaneo no encontro vecinos")
                self.log(
                    f"[VECINOS] {len(targets)} encontrado(s): "
                    + ", ".join(map(str, targets))
                )
                self.log(
                    f"[PRUEBA] {config['count']} mensaje(s) por vecino; "
                    f"total={config['count'] * len(targets)}"
                )
            else:
                targets = [config["node"]]
                self.log(f"[PRUEBA] nodo={config['node']} mensajes={config['count']}")
            self.log(f"[PAYLOAD] {config['payload'].hex(' ').upper()}")

            before = read_pdu_buffers(sink)
            total_buffers = before["used"] + before["free"]
            if total_buffers == 0:
                raise IOError("el sink informa cero buffers PDU")
            self.log(
                f"[PDU] antes: usados={before['used']} libres={before['free']} "
                f"total={total_buffers}"
            )
            if config["tx_buffers"] + config["rx_buffers"] > total_buffers:
                raise ValueError(
                    f"Buffers TX ({config['tx_buffers']}) + RX ({config['rx_buffers']}) superan "
                    f"los {total_buffers} buffers del sink"
                )
            self.log(
                f"[FLUJO] ocupados<={config['tx_buffers']}, "
                f"libres>={config['rx_buffers']} de {total_buffers}"
            )

            stale = 0
            quiet_until = time.monotonic() + 0.1
            drain_until = time.monotonic() + 1.0
            while time.monotonic() < drain_until:
                frames = poll_rx_frames(sink)
                old_responses = sum(
                    frame["source"] in targets
                    and frame["source_ep"] == config["response_ep"]
                    for frame in frames
                )
                stale += old_responses
                if old_responses:
                    quiet_until = time.monotonic() + 0.1
                elif time.monotonic() >= quiet_until:
                    break
                time.sleep(0.01)
            if stale:
                self.log(f"[RX] descartadas {stale} respuesta(s) anteriores")

            pending = []
            sent = 0
            rejected = 0
            uncertain = 0
            tx_durations = []
            first_tx_at = None
            last_tx_at = None
            last_rx_at = None
            received = set()
            sent_by_node = {node: 0 for node in targets}
            sent_numbers_by_node = {node: set() for node in targets}
            response_timeout = False
            jobs = (
                (node, node_sequence)
                for node_sequence in range(1, config["count"] + 1)
                for node in targets
            )
            for sequence, (node, node_sequence) in enumerate(jobs, 1):
                if self.cancel.is_set():
                    return
                message = config["payload"]
                tx_label = (
                    f"{sequence} nodo={node} #{node_sequence}"
                    if config["neighbors"] else str(sequence)
                )
                try:
                    used_before, free_before, received_at = self.wait_for_tx_capacity(
                        sink, config, pending, received, total_buffers
                    )
                    if received_at is not None:
                        last_rx_at = received_at
                    if used_before is None:
                        response_timeout = True
                        break
                except InterruptedError:
                    return
                self.log(
                    f"[PDU TX {tx_label}] ocupados={used_before}/{total_buffers} "
                    f"libres={free_before}/{total_buffers}"
                )

                def wait_for_retry_capacity():
                    nonlocal last_rx_at, response_timeout
                    used, _, received_at = self.wait_for_tx_capacity(
                        sink, config, pending, received, total_buffers
                    )
                    if received_at is not None:
                        last_rx_at = received_at
                    if used is None:
                        response_timeout = True
                        return False
                    return True

                tx_started = time.perf_counter()
                tx_uncertain = False
                if first_tx_at is None:
                    first_tx_at = tx_started
                try:
                    pdu, _ = send_when_available(
                        sink,
                        node,
                        config["destination_ep"],
                        message,
                        sequence & 0xFFFF,
                        total_buffers,
                        True,
                        self.cancel,
                        self.log,
                        wait_for_capacity=wait_for_retry_capacity,
                    )
                    tx_finished = time.perf_counter()
                    tx_ms = (tx_finished - tx_started) * 1000
                    tx_durations.append(tx_ms)
                    last_tx_at = tx_finished
                    pending.append((sequence, node, node_sequence, message, tx_started))
                    sent += 1
                    sent_by_node[node] += 1
                    sent_numbers_by_node[node].add(node_sequence)
                    self.log(
                        f"[TX {tx_label}] aceptado pdu={pdu} tiempo={tx_ms:.1f} ms"
                    )
                except InterruptedError:
                    return
                except TxRejected as error:
                    tx_finished = time.perf_counter()
                    tx_ms = (tx_finished - tx_started) * 1000
                    tx_durations.append(tx_ms)
                    last_tx_at = tx_finished
                    rejected += 1
                    self.log(f"[TX {tx_label}] RECHAZADO ({tx_ms:.1f} ms): {error}")
                    if error.result == 0x04:
                        self.log("[PDU] sin libres; no se reintenta el envio")
                        break
                except (TimeoutError, serial.SerialException) as error:
                    tx_finished = time.perf_counter()
                    tx_ms = (tx_finished - tx_started) * 1000
                    tx_durations.append(tx_ms)
                    last_tx_at = tx_finished
                    uncertain += 1
                    tx_uncertain = True
                    self.log(f"[TX {tx_label}] SIN CONFIRMACION ({tx_ms:.1f} ms): {error}")
                for frame in poll_rx_frames(sink):
                    received_at = self.handle_rx(frame, config, pending, received)
                    if received_at is not None:
                        last_rx_at = received_at
                if tx_uncertain:
                    self.log("[TX] prueba detenida: el ultimo envio tiene estado incierto")
                    break
                if config["pause"]:
                    time.sleep(config["pause"])

            if pending and not response_timeout:
                self.log(f"[RX] esperando {len(pending)} respuesta(s) finales...")
                received_at, response_ok = self.wait_for_all_responses(
                    sink, config, pending, received
                )
                if received_at is not None:
                    last_rx_at = received_at
                if not response_ok:
                    response_timeout = True
            if not self.cancel.is_set():
                expected = config["count"] * len(targets)
                lost = expected - len(received)
                self.log(
                    f"[RESULTADO] enviados={sent} rechazados={rejected} "
                    f"inciertos={uncertain} recibidos={len(received)} perdidos={lost}"
                )
                if response_timeout:
                    self.log("[RESULTADO] terminado por timeout RX")
                for node in targets:
                    node_received_numbers = {
                        number for source, number in received if source == node
                    }
                    node_pending = sorted(
                        sent_numbers_by_node[node] - node_received_numbers
                    )
                    node_unsent = sorted(
                        set(range(1, config["count"] + 1)) - sent_numbers_by_node[node]
                    )
                    node_sent = sent_by_node[node]
                    node_received = len(node_received_numbers)
                    node_lost = len(node_pending) + len(node_unsent)
                    percentage = 100 * node_received / config["count"]
                    self.log(
                        f"[NODO {node}] enviados={node_sent} "
                        f"recibidos={node_received} perdidos={node_lost} "
                        f"entrega={percentage:.1f}%"
                    )
                    if node_pending:
                        self.log(
                            f"[PENDIENTES {node}] mensajes sin respuesta: "
                            + ", ".join(f"#{number}" for number in sorted(node_pending))
                        )
                    if node_unsent:
                        self.log(
                            f"[NO ENVIADOS {node}] mensajes: "
                            + ", ".join(f"#{number}" for number in node_unsent)
                        )

            if tx_durations:
                self.log(
                    f"[TIEMPOS TX] n={len(tx_durations)} "
                    f"min={min(tx_durations):.1f} ms "
                    f"max={max(tx_durations):.1f} ms "
                    f"media={sum(tx_durations) / len(tx_durations):.1f} ms"
                )
            if first_tx_at is not None:
                if last_rx_at is not None:
                    self.log(
                        f"[TIEMPO TOTAL] primer TX -> ultima RX: "
                        f"{(last_rx_at - first_tx_at) * 1000:.1f} ms"
                    )
                elif last_tx_at is not None:
                    self.log(
                        f"[TIEMPO TOTAL] primer TX -> ultimo TX: "
                        f"{(last_tx_at - first_tx_at) * 1000:.1f} ms; sin RX"
                    )
            try:
                after = read_pdu_buffers(sink)
                self.log(f"[PDU] despues: usados={after['used']} libres={after['free']}")
            except Exception as error:
                self.log(f"[PDU] no disponible despues: {error}")
            self.log("[OK] prueba terminada")
        except Exception as error:
            self.log(f"ERROR: {error}")
        finally:
            if sink is not None:
                sink.close()
            self.events.put(("done", None))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
