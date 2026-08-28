#!/usr/bin/env python3
"""OTAP para sinks Wirepas: sube un fichero .otap/.spb por UART (WPC/SLIP).

Uso:
    python wirepas_otap.py COM5 --vecinos                    # descubrir vecinos del sink
    python wirepas_otap.py COM5 fichero.otap --seq 5         # OTAP red completa
    python wirepas_otap.py COM5 fichero.otap --seq 5 --todos # descubrir, esperar y procesar todos
    python wirepas_otap.py COM5 fichero.otap --seq 5 --nodos 11,12   # esperar llegada y procesar esos nodos
    python wirepas_otap.py COM5 --seq 5 --nodos 11           # nodo concreto reutilizando scratchpad ya cargado
    python wirepas_otap.py COM5 --status-only
Requiere: pip install pyserial
"""
import argparse
import struct
import sys
import time

import builtins

import serial


def log(*args, **kwargs):
    builtins.print(time.strftime("%H:%M:%S"), *args, **kwargs)


def _comprobar_cancelacion(cancelar):
    if cancelar and cancelar():
        raise InterruptedError("operacion cancelada")


def _reintentar(paso, funcion, cancelar=None, intentos=3):
    for intento in range(1, intentos + 1):
        _comprobar_cancelacion(cancelar)
        try:
            return funcion()
        except InterruptedError:
            raise
        except (TimeoutError, IOError, serial.SerialException) as e:
            if intento == intentos:
                raise
            log(f"[REINTENTO] {paso} fallo ({e}); intento {intento + 1}/{intentos}")
            for _ in range(2):
                time.sleep(1)
                _comprobar_cancelacion(cancelar)


def _esperar(segundos, cancelar=None):
    for _ in range(segundos):
        time.sleep(1)
        _comprobar_cancelacion(cancelar)

END, ESC = 0xC0, 0xDB
END_SUB, ESC_SUB = 0xDC, 0xDD
BLOCK = 112

SCRATCH_START = 0x17
SCRATCH_BLOCK = 0x18
SCRATCH_STATUS = 0x19
SCRATCH_UPDATE = 0x1A
SCRATCH_CLEAR = 0x1B
TARGET_WRITE = 0x26
SINK_COST_READ = 0x39
STACK_START = 0x05
STACK_STOP = 0x06

DSAP_DATA_TX_REQUEST = 0x01
DSAP_DATA_TX_TT_REQUEST = 0x1F  # variante usada por el lib oficial (con buffering_delay)
DSAP_DATA_RX_INDICATION = 0x03
EP_GATEWAY = 255
EP_REMOTA = 240
ESPERA_RESP_S = 20

MSAP_INDICATION_POLL_REQUEST = 0x04
MSAP_GET_NBORS_REQUEST = 0x20
MSAP_SCAN_NBORS_REQUEST = 0x21
MSAP_SCAN_NBORS_INDICATION = 0x22

ERRORES_REM = {
    0xF8: "acceso denegado",
    0xF9: "atributo solo escritura",
    0xFA: "peticion broadcast invalida",
    0xFB: "begin invalido",
    0xFC: "sin espacio para respuesta",
    0xFD: "valor invalido",
    0xFE: "longitud invalida",
    0xFF: "peticion desconocida",
}


def _lut():
    t = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        t.append(c)
    return t


_LUT = _lut()


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc = _LUT[b ^ (crc >> 8)] ^ ((crc << 8) & 0xFFFF)
    return crc


def slip_send(port: serial.Serial, core: bytes):
    buf = bytearray([END] * 3)
    for b in core + crc16(core).to_bytes(2, "little"):
        if b == END:
            buf += bytes([ESC, END_SUB])
        elif b == ESC:
            buf += bytes([ESC, ESC_SUB])
        else:
            buf.append(b)
    buf.append(END)
    port.write(buf)


def slip_recv(port: serial.Serial, timeout_s: float) -> bytes:
    fin = time.time() + timeout_s
    while time.time() < fin:
        raw = bytearray()
        started = False
        while time.time() < fin:
            b = port.read(1)
            if not b:
                break
            x = b[0]
            if x == END:
                if started and len(raw) >= 4:
                    out = bytearray()
                    it = iter(raw)
                    for c in it:
                        if c == ESC:
                            n = next(it, None)
                            out.append(END if n == END_SUB else ESC)
                        else:
                            out.append(c)
                    if crc16(out[:-2]) != int.from_bytes(out[-2:], "little"):
                        continue
                    return bytes(out[:-2])
                raw.clear()
                started = True
            elif started:
                raw.append(x)
    raise TimeoutError("sin respuesta del sink (revisa puerto/baudios o si otro programa lo usa)")


class Sink:
    def __init__(self, puerto: str, baudios: int = 115200):
        self.puerto = puerto
        self.baudios = baudios
        self.s = serial.Serial(puerto, baudios, timeout=0.05)
        self.fid = 0
        self.pdu = 0
        self.indicaciones = []

    def _ack(self, prim: int, fid: int, siguiente: int = 0):
        slip_send(self.s, bytes([prim | 0x80, fid, 1, siguiente]))

    def req(self, prim: int, payload: bytes = b"", timeout_s: float = 0.5) -> bytes:
        self.fid = (self.fid + 1) & 0xFF
        slip_send(self.s, bytes([prim, self.fid, len(payload)]) + payload)
        fin = time.time() + timeout_s
        while True:
            f = slip_recv(self.s, max(0.05, fin - time.time()))
            if f[0] == (prim | 0x80) and f[1] == self.fid:
                return f[3 : 3 + f[2]]
            if not f[0] & 0x80:
                siguiente = f[3] if len(f) > 3 else 0
                self._ack(f[0], f[1], siguiente)
                self.indicaciones.append(f)

    def close(self):
        self.s.close()

    def parar_pila(self) -> bool:
        """Para la pila y reabre UART tras el reinicio del nodo."""
        r = self.req(STACK_STOP, b"", 10)
        if r[0] == 1:
            return False
        if r[0] != 0:
            raise IOError(f"STOP rechazado (result=0x{r[0]:02x})")
        self.s.close()
        limite = time.time() + 15
        ultimo = None
        while time.time() < limite:
            try:
                self.s = serial.Serial(self.puerto, self.baudios, timeout=0.05)
                if probar(self):
                    return True
                self.s.close()
            except serial.SerialException as e:
                ultimo = e
                try:
                    self.s.close()
                except serial.SerialException:
                    pass
            time.sleep(0.5)
        raise TimeoutError(f"UART no vuelve tras STOP: {ultimo or self.puerto}")

    def arrancar_pila(self):
        r = self.req(STACK_START, b"\x00", 10)
        if r[0] not in (0, 1):
            raise IOError(f"START rechazado (result=0x{r[0]:02x})")
        if not probar(self):
            raise TimeoutError("la pila no responde tras START")

    def send_data(self, dest: int, apdu: bytes):
        """DSAP_DATA_TX_TT: envia un APDU a un nodo (Remote API: ep 255 -> ep 240)."""
        self.pdu = (self.pdu + 1) & 0xFFFF
        pl = struct.pack(
            "<HBIBBBIB", self.pdu, EP_GATEWAY, dest, EP_REMOTA, 0, 0, 0, len(apdu)
        ) + apdu
        c = self.req(DSAP_DATA_TX_TT_REQUEST, pl, 2)
        pdu, result, _ = struct.unpack("<HBB", c[:4])
        if result:
            raise IOError(f"TX a {dest} rechazada (result=0x{result:02x})")

    def recv_data(self, src: int, timeout_s: float, tipos: set = None) -> bytes:
        """Espera la respuesta DSAP de un nodo (ep 240 -> ep 255), via polls."""
        fin = time.time() + timeout_s
        while time.time() < fin:
            for f in _ciclo_poll(self):
                if f[0] != DSAP_DATA_RX_INDICATION:
                    continue
                src_add = int.from_bytes(f[4:8], "little")
                src_ep = f[8]
                ln = f[19]
                if src_add == src and src_ep == EP_REMOTA:
                    apdu = f[20 : 20 + ln]
                    if tipos is None or tipos.intersection(_tlv(apdu)):
                        return apdu
            time.sleep(0.05)
        raise TimeoutError(f"nodo {src} no responde")


TAG_SCR1 = bytes.fromhex("534352319a933082d9eb0afc3121e337")


def load_otap(ruta: str, crudo: bool):
    """Devuelve (cuerpo_a_subir, crc_target, seq_en_fichero|None).

    - Contenedor SCR1 (NMS/SDK, magic 'SCR1'): se sube entero por bloques;
      el crc objetivo es el campo de su cabecera (lo que ve la red).
    - Binario crudo (--raw): crc = CRC16 calculado sobre el fichero.
    - Formato antiguo .spb: primeros 2 bytes = CRC del resto.
    """
    data = open(ruta, "rb").read()
    if not crudo and data[:16] == TAG_SCR1:
        if len(data) < 48 or int.from_bytes(data[16:20], "little") != len(data) - 32:
            raise ValueError("contenedor SCR1 con longitud inconsistente")
        crc = int.from_bytes(data[20:22], "little")
        if crc16(data[32:]) != crc:
            raise ValueError(f"CRC SCR1 incorrecto: cabecera=0x{crc:04X}")
        return data, crc, data[22]
    if crudo:
        return data, crc16(data), None
    if len(data) < 18 or crc16(data[2:]) != int.from_bytes(data[:2], "little"):
        raise ValueError("formato no reconocido (ni SCR1 ni spb); prueba --raw")
    return data[2:], int.from_bytes(data[:2], "little"), None


def status(sink: Sink):
    st = sink.req(SCRATCH_STATUS, b"", 2)
    return {
        "len": int.from_bytes(st[0:4], "little"),
        "crc": int.from_bytes(st[4:6], "little"),
        "seq": st[6],
        "tipo_scratchpad": st[7],
        "estado_scratchpad": st[8],
        "procesado_len": int.from_bytes(st[9:13], "little"),
        "procesado_crc": int.from_bytes(st[13:15], "little"),
        "procesado_seq": st[15],
    }


def probar(sink: Sink, intentos: int = 3) -> bool:
    """Handshake barato: poll hasta que el sink contesta."""
    for _ in range(intentos):
        try:
            sink.req(MSAP_INDICATION_POLL_REQUEST, b"", 0.7)
            return True
        except TimeoutError:
            pass
    return False


def _ciclo_poll(sink: Sink) -> list:
    """Un poll al sink; devuelve las indicaciones recibidas (ya acusadas).

    En dualmcu las indicaciones SOLO se entregan tras un poll: el confirm
    indica cuantas quedan y entonces llegan encadenadas.
    """
    inds, sink.indicaciones = sink.indicaciones, []
    try:
        r = sink.req(MSAP_INDICATION_POLL_REQUEST, b"", 1.0)
    except TimeoutError:
        return inds
    inds.extend(sink.indicaciones)
    sink.indicaciones = []
    if not r or r[0] == 0:
        return inds
    while True:
        f = slip_recv(sink.s, 3)
        if f[0] & 0x80:
            continue
        quedan = f[3] if len(f) > 3 else 0
        sink._ack(f[0], f[1], quedan)
        inds.append(f)
        if not quedan:
            break
    return inds


def es_sink(sink: Sink) -> bool:
    """True si el dispositivo conectado es un sink (el OTAP y el Remote API lo exigen)."""
    c = sink.req(SINK_COST_READ, b"", 2)
    return len(c) > 0 and c[0] == 0


def drenar(sink: Sink, max_polls: int = 10):
    """Vacia la cola de indicaciones pendientes del sink."""
    for _ in range(max_polls):
        if not _ciclo_poll(sink):
            return


def esperar_indicacion(sink: Sink, prim: int, timeout_s: float) -> bytes:
    fin = time.time() + timeout_s
    while time.time() < fin:
        for f in _ciclo_poll(sink):
            if f[0] == prim:
                return f[3 : 3 + f[2]]
        time.sleep(0.05)
    raise TimeoutError(f"timeout esperando indicacion 0x{prim:02X}")


def descubrir_vecinos(sink: Sink, timeout_s: float = 30) -> list:
    """Escanear y devolver vecinos del sink (MSAP_SCAN_NBORS + GET_NBORS)."""
    drenar(sink)
    r = sink.req(MSAP_SCAN_NBORS_REQUEST, b"", 10)
    if r[0]:
        raise IOError(f"scan rechazado (result=0x{r[0]:02x})")
    ind = esperar_indicacion(sink, MSAP_SCAN_NBORS_INDICATION, timeout_s)
    if not ind or ind[1] != 1:
        raise TimeoutError("el scan de vecinos no termino")
    c = sink.req(MSAP_GET_NBORS_REQUEST, b"", 5)
    vecinos = []
    for i in range(c[0]):
        e = c[1 + 13 * i : 1 + 13 * i + 13]
        vecinos.append(
            {
                "add": int.from_bytes(e[0:4], "little"),
                "link": e[4],
                "rssi": e[5],
                "cost": e[6],
                "ch": e[7],
                "tipo": e[8],
                "tx_power": e[9],
                "rx_power": e[10],
                "edad": int.from_bytes(e[11:13], "little"),
            }
        )
    return vecinos


def _tlv(apdu: bytes) -> dict:
    items = {}
    i = 0
    while i + 2 <= len(apdu):
        t = apdu[i]
        l = apdu[i + 1]
        items[t] = apdu[i + 2 : i + 2 + l]
        i += 2 + l
    return items


def _parse_estado(p: bytes) -> dict:
    if len(p) < 24:
        raise IOError(f"estado remoto truncado ({len(p)} B)")
    st_len, st_crc, st_seq, st_tipo, st_sta, fw_len, fw_crc, fw_seq, fw_id = struct.unpack(
        "<IHBBBIHBI", p[:20]
    )
    out = {
        "len": st_len,
        "crc": st_crc,
        "seq": st_seq,
        "tipo": st_tipo,
        "sta": st_sta,
        "procesado_len": fw_len,
        "procesado_crc": fw_crc,
        "procesado_seq": fw_seq,
        "area_id": fw_id,
        "fw_ver": ".".join(map(str, p[20:24])),
    }
    if len(p) >= 39:
        app_len, app_crc, app_seq, app_id = struct.unpack("<IHBI", p[24:35])
        out.update(
            app_procesado_len=app_len,
            app_procesado_crc=app_crc,
            app_procesado_seq=app_seq,
            app_area_id=app_id,
            app_ver=".".join(map(str, p[35:39])),
        )
    return out


def estado_nodo(sink: Sink, add: int) -> dict:
    """Remote API 'MSAP Scratchpad Status' (19 00) -> respuesta 0x99."""
    sink.send_data(add, b"\x19\x00")
    it = _tlv(sink.recv_data(add, ESPERA_RESP_S, {0x99, *ERRORES_REM}))
    if 0x99 not in it:
        err = next((t for t in it if t in ERRORES_REM), None)
        raise IOError(f"respuesta invalida: {ERRORES_REM.get(err, 'desconocida')}")
    return _parse_estado(it[0x99])


def descubrir_nodos(sink: Sink, rondas: int = 3, ventana_s: int = 30, cancelar=None) -> dict:
    """Descubre toda la red con Remote API broadcast, no solo vecinos de un salto."""
    nodos = {}
    drenar(sink)
    for ronda in range(1, rondas + 1):
        _comprobar_cancelacion(cancelar)
        antes = len(nodos)
        sink.send_data(0xFFFFFFFF, b"\x19\x00")
        fin = time.time() + ventana_s
        while time.time() < fin:
            _comprobar_cancelacion(cancelar)
            for f in _ciclo_poll(sink):
                if f[0] != DSAP_DATA_RX_INDICATION or len(f) < 20 or f[8] != EP_REMOTA:
                    continue
                src = int.from_bytes(f[4:8], "little")
                p = _tlv(f[20 : 20 + f[19]]).get(0x99)
                if p:
                    nodos[src] = _parse_estado(p)
            time.sleep(0.05)
        log(f"[RED] ronda {ronda}: {len(nodos)} nodo(s), {len(nodos) - antes} nuevo(s)")
    return nodos


def procesar_nodo(sink: Sink, add: int, seq: int, reinicio_s: int = 120) -> tuple:
    """Remote API 'MSAP Scratchpad Update' (1A 01 seq) -> respuesta 0x9A."""
    sink.send_data(add, _apdu_procesar(seq, reinicio_s))
    it = _tlv(sink.recv_data(add, ESPERA_RESP_S, {0x9A, *ERRORES_REM}))
    if 0x9A in it and 0x85 in it:
        return it[0x9A][0], int.from_bytes(it[0x85], "little")
    err = next((t for t in it if t in ERRORES_REM), None)
    raise IOError(f"process rechazado: {ERRORES_REM.get(err, 'respuesta invalida')}")


def _procesado_esperado(st: dict, esperado: tuple) -> bool:
    return st["sta"] == 0 and (
        (st["procesado_len"], st["procesado_crc"], st["procesado_seq"]) == esperado
        or (
            st.get("app_procesado_len"),
            st.get("app_procesado_crc"),
            st.get("app_procesado_seq"),
        ) == esperado
    )


def _esperar_procesado_nodo(
    sink: Sink, add: int, esperado: tuple, cancelar=None
) -> dict:
    fin = time.time() + 90
    while time.time() < fin:
        _comprobar_cancelacion(cancelar)
        try:
            st = estado_nodo(sink, add)
            if _procesado_esperado(st, esperado):
                return st
            log(
                f"[NODO {add}] esperando reinicio/procesado "
                f"(tipo={st['tipo']}, estado=0x{st['sta']:02X})"
            )
        except (TimeoutError, IOError, serial.SerialException) as e:
            log(f"[NODO {add}] esperando que vuelva: {e}")
        _esperar(20, cancelar)
    raise TimeoutError(f"nodo {add} no confirmo el firmware procesado")


def procesar_y_verificar_nodo(
    sink: Sink, add: int, esperado: tuple, reinicio_s: int = 120,
    cancelar=None,
):
    try:
        st = estado_nodo(sink, add)
        if _procesado_esperado(st, esperado):
            log(f"[NODO {add}] ya estaba procesado; no se relanza")
            return
    except (TimeoutError, IOError, serial.SerialException):
        pass

    espera = reinicio_s
    try:
        seq, espera = procesar_nodo(sink, add, esperado[2], reinicio_s)
        log(f"[NODO {add}] process enviado una vez (seq {seq}, reinicio {espera}s)")
    except (TimeoutError, IOError, serial.SerialException) as e:
        log(
            f"[NODO {add}] sin ACK de process ({e}); no se reenvia para evitar "
            f"reinicios dobles. Esperando {reinicio_s}s..."
        )
    _esperar(espera, cancelar)
    st = _esperar_procesado_nodo(sink, add, esperado, cancelar)
    log(
        f"[NODO {add}] actualizado y verificado "
        f"(app={st.get('app_ver', '?')}, fw={st['fw_ver']})"
    )


def _apdu_procesar(seq: int, cuenta_atras_s: int = 120) -> bytes:
    """Marca el scratchpad y programa el reinicio sin romper la malla durante el broadcast."""
    if not 10 <= cuenta_atras_s <= 32767:
        raise ValueError("reinicio debe estar entre 10 y 32767 segundos")
    return b"\x04\x00\x01\x00\x1A\x01" + bytes([seq]) + b"\x03\x00\x05\x02" + struct.pack(
        "<H", cuenta_atras_s
    )


def procesar_broadcast(
    sink: Sink, seq: int, esperados: set, reinicio_s: int = 120,
    envios: int = 3, ventana_s: int = 10, cancelar=None,
):
    confirmados = set()
    reinicios = {}
    for envio in range(1, envios + 1):
        _comprobar_cancelacion(cancelar)
        sink.send_data(0xFFFFFFFF, _apdu_procesar(seq, reinicio_s))
        fin = time.time() + ventana_s
        while time.time() < fin:
            _comprobar_cancelacion(cancelar)
            for f in _ciclo_poll(sink):
                if f[0] != DSAP_DATA_RX_INDICATION or len(f) < 20 or f[8] != EP_REMOTA:
                    continue
                src = int.from_bytes(f[4:8], "little")
                it = _tlv(f[20 : 20 + f[19]])
                if 0x9A in it and 0x85 in it:
                    confirmados.add(src)
                    reinicios[src] = int.from_bytes(it[0x85], "little")
            time.sleep(0.05)
        log(f"[PROCESS] broadcast {envio}/{envios}: ACK {len(confirmados)}/{len(esperados)}")
    faltan = esperados - confirmados
    if faltan:
        log(f"[PROCESS] sin ACK (pueden haber recibido la orden): {sorted(faltan)}")
    return max(reinicios.values(), default=reinicio_s + 20)


def verificar_procesados_broadcast(
    sink: Sink, esperado: tuple, nodos: set, cancelar=None, espera_s: int = 180
):
    pendientes = set(nodos)
    fin = time.time() + espera_s
    while pendientes and time.time() < fin:
        ventana = min(30, max(1, int(fin - time.time())))
        estados = descubrir_nodos(sink, rondas=1, ventana_s=ventana, cancelar=cancelar)
        for add in list(pendientes):
            if add in estados and _procesado_esperado(estados[add], esperado):
                pendientes.remove(add)
                log(f"[NODO {add}] actualizado y verificado")
        if pendientes:
            log(f"[OTAP] esperando reincorporacion de {len(pendientes)} nodo(s)")
    if pendientes:
        raise TimeoutError(f"sin confirmar procesado en: {sorted(pendientes)}")


def verificar_y_procesar(
    sink: Sink, esperado: tuple, nodos: list, espera_s: int, broadcast: bool = False,
    intervalo_s: int = 20, cancelar=None, reinicio_s: int = 120,
):
    pendientes = set(nodos)
    ultima = {}
    fin = time.time() + espera_s
    log(f"[OTAP] esperando llegada del scratchpad en {len(nodos)} nodo(s) (max {espera_s}s)...")
    while pendientes and time.time() < fin:
        _comprobar_cancelacion(cancelar)
        for add in sorted(pendientes):
            _comprobar_cancelacion(cancelar)
            if time.time() - ultima.get(add, 0) < intervalo_s:
                continue
            try:
                st = estado_nodo(sink, add)
            except (TimeoutError, IOError) as e:
                log(f"[NODO {add}] {e}")
                continue
            finally:
                ultima[add] = time.time()
            if (st["len"], st["crc"], st["seq"]) == esperado:
                pendientes.discard(add)
                log(f"[NODO {add}] recibido (estado=0x{st['sta']:02X}, fw={st['fw_ver']})")
            else:
                log(
                    f"[NODO {add}] pendiente (len={st['len']}, crc=0x{st['crc']:04X}, seq={st['seq']})"
                )
        time.sleep(1)
    if pendientes:
        raise IOError(f"el scratchpad no llego a: {sorted(pendientes)}")
    _comprobar_cancelacion(cancelar)
    if broadcast:
        log("[OTAP] llegado a todos. Lanzando process broadcast 3 veces...")
        reinicio_real = procesar_broadcast(
            sink, esperado[2], set(nodos), reinicio_s, cancelar=cancelar
        )
        log(f"[OTAP] esperando {reinicio_real}s antes de verificar la red...")
        _esperar(reinicio_real, cancelar)
        verificar_procesados_broadcast(sink, esperado, set(nodos), cancelar)
        log(f"[OTAP] red completa actualizada y verificada: {len(nodos)} nodo(s)")
        return
    log("[OTAP] recibido por todos los nodos solicitados. Lanzando process unicast...")
    for add in nodos:
        procesar_y_verificar_nodo(sink, add, esperado, reinicio_s, cancelar)


def otap(
    sink: Sink, cuerpo: bytes, crc: int, seq: int, accion: int, param: int,
    procesar: bool = True, cancelar=None,
):
    pila_parada = False
    try:
        sink.parar_pila()
        pila_parada = True
        def declarar():
            r = sink.req(SCRATCH_START, len(cuerpo).to_bytes(4, "little") + bytes([seq]), 45)
            if r[0]:
                raise IOError(f"START rechazado (result=0x{r[0]:02x})")

        _reintentar("declarar scratchpad", declarar, cancelar)
        log(f"[OTAP] scratchpad declarado: {len(cuerpo)} B, seq={seq}")

        for off in range(0, len(cuerpo), BLOCK):
            _comprobar_cancelacion(cancelar)
            trozo = cuerpo[off : off + BLOCK]
            def enviar_bloque():
                r = sink.req(
                    SCRATCH_BLOCK,
                    off.to_bytes(4, "little") + bytes([len(trozo)]) + trozo,
                    5,
                )
                if r[0] not in (0, 1):
                    raise IOError(f"BLOCK en offset {off} rechazado (result=0x{r[0]:02x})")

            _reintentar(f"bloque {off}", enviar_bloque, cancelar)
            enviados = off + len(trozo)
            if enviados == len(cuerpo) or enviados // 4096 != off // 4096:
                log(f"[OTAP] subida {enviados}/{len(cuerpo)} B")

        st = _reintentar("verificar scratchpad en sink", lambda: status(sink), cancelar)
        if (st["len"], st["crc"], st["seq"]) != (len(cuerpo), crc, seq):
            raise IOError(f"verificación fallida en sink: {st}")
        log("[OTAP] verificado en sink: len/crc/seq correctos")

        _comprobar_cancelacion(cancelar)
        def fijar_target():
            r = sink.req(
                TARGET_WRITE,
                bytes([seq]) + crc.to_bytes(2, "little") + bytes([accion, param]),
            )
            if r[0]:
                raise IOError(f"TARGET_WRITE rechazado (result=0x{r[0]:02x})")

        _reintentar("fijar target", fijar_target, cancelar)
        if not procesar:
            log("[OTAP] target fijado (solo propagar). El sink empieza a distribuirlo.")
            return
        def marcar_update():
            r = sink.req(SCRATCH_UPDATE, b"", 10)
            if r[0]:
                raise IOError(f"UPDATE rechazado (result=0x{r[0]:02x})")

        _reintentar("marcar scratchpad", marcar_update, cancelar)
        log(f"[OTAP] scratchpad marcado (action={accion}, param={param}); se procesará al reiniciar.")
    finally:
        if pila_parada:
            sink.arrancar_pila()


def main():
    p = argparse.ArgumentParser(description="OTAP Wirepas por UART")
    p.add_argument("puerto", help="p.ej. COM5 o /dev/ttyUSB0")
    p.add_argument("fichero", nargs="?", help="fichero .otap/.spb")
    p.add_argument("--baudios", type=int, default=115200)
    p.add_argument("--seq", type=int, required=False, help="secuencia nueva (obligatoria para OTAP)")
    p.add_argument("--accion", type=int, default=2, help="0 nada, 1 propagar, 2 propagar+procesar, 3 propagar+procesar con delay")
    p.add_argument("--param", type=int, default=0)
    p.add_argument("--raw", action="store_true", help="fichero sin cabecera CRC de 2 bytes")
    p.add_argument("--status-only", action="store_true", help="solo consultar estado del sink")
    p.add_argument("--vecinos", action="store_true", help="escanear y listar vecinos del sink")
    p.add_argument(
        "--nodos",
        help="lista de direcciones p.ej. 11,12,13: esperar llegada en todos y lanzar process",
    )
    p.add_argument(
        "--todos",
        action="store_true",
        help="descubrir toda la red por broadcast, esperar llegada y lanzar process",
    )
    p.add_argument("--espera", type=int, default=600, help="timeout global de espera a nodos (s)")
    p.add_argument(
        "--intervalo",
        type=int,
        default=20,
        help="segundos entre consultas a cada nodo (espacia el sondeo)",
    )
    p.add_argument(
        "--reinicio",
        type=int,
        default=120,
        help="cuenta atras de reinicio de nodos, 10..32767 s (Wirepas añade 0..20 s)",
    )
    args = p.parse_args()

    if not args.status_only and not args.vecinos:
        if args.seq is None:
            p.error("falta --seq")
        if not args.fichero and not (args.nodos or args.todos):
            p.error("sin FICHERO hace falta --nodos o --todos (reutilizar scratchpad ya cargado)")
    if args.nodos and args.todos:
        p.error("--nodos y --todos son excluyentes")
    if not 10 <= args.reinicio <= 32767:
        p.error("--reinicio debe estar entre 10 y 32767 segundos")

    sink = Sink(args.puerto, args.baudios)
    if not probar(sink):
        raise SystemExit(
            f"el sink no contesta en {args.puerto} @{args.baudios} "
            "(¿puerto correcto? ¿otro programa lo esta usando?)"
        )
    drenar(sink)
    try:
        if args.vecinos:
            vs = descubrir_vecinos(sink)
            log(f"{'DIRECCION':>10}  LINK%  RSSI  COST  CH  TIPO  TXP  RXP  HACE(s)")
            for v in vs:
                log(
                    f"{v['add']:>10}  {v['link']:>5}  {v['rssi']:>4}  {v['cost']:>4}  "
                    f"{v['ch']:>2}  0x{v['tipo']:02X}  {v['tx_power']:>3}  {v['rx_power']:>3}  {v['edad']:>6}"
                )
            return
        if args.status_only:
            log(status(sink))
            return
        if not es_sink(sink):
            raise SystemExit(
                f"{args.puerto} es un nodo regular, NO un sink: "
                "cargar OTAP y enviar Remote API solo se puede desde el sink"
            )
        todos = args.todos or bool(args.fichero and not args.nodos)
        estados = None
        if todos:
            log("[OTAP] descubriendo inventario completo antes de subir...")
            estados = descubrir_nodos(sink)
            if not estados:
                raise IOError("ningun nodo respondio al descubrimiento broadcast")
            log(f"[OTAP] inventario fijado: {len(estados)} nodo(s)")
        if args.fichero:
            cuerpo, crc, seq_fichero = load_otap(args.fichero, args.raw)
            log(
                f"[OTAP] {args.fichero}: {len(cuerpo)} B, crc=0x{crc:04X}, seq={args.seq}"
                + (f" (seq en fichero: {seq_fichero})" if seq_fichero is not None else "")
            )
            # Propagar sin auto-proceso; se verifica antes de lanzar process.
            otap(sink, cuerpo, crc, args.seq, 1, 0, procesar=False)
            esperado = (len(cuerpo), crc, args.seq)
        else:
            st = status(sink)
            esperado = (st["len"], st["crc"], args.seq)
            if st["len"] == 0 or st["seq"] != args.seq:
                raise IOError(f"el sink no tiene un scratchpad con seq={args.seq}: {st}")
            log(
                f"[OTAP] reutilizando scratchpad del sink: {st['len']} B, "
                f"crc=0x{st['crc']:04X}, seq={st['seq']}"
            )
            r = sink.req(TARGET_WRITE, bytes([args.seq]) + st["crc"].to_bytes(2, "little") + b"\x01\x00")
            if r[0]:
                raise IOError(f"TARGET_WRITE propagar rechazado (result=0x{r[0]:02x})")
        if todos:
            nodos = sorted(estados)
            for add in nodos:
                st = estados[add]
                log(
                    f"[NODO {add}] scratchpad={st['len']}/0x{st['crc']:04X}/{st['seq']} "
                    f"estado=0x{st['sta']:02X} app={st.get('app_ver', '?')}"
                )
        else:
            nodos = [int(x) for x in args.nodos.split(",")]
        verificar_y_procesar(
            sink, esperado, nodos, args.espera, todos, args.intervalo,
            reinicio_s=args.reinicio,
        )
    finally:
        sink.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
