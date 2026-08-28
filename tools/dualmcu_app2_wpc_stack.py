#!/usr/bin/env python3
"""Actualizador local del sink dual-MCU con scratchpad combinado app + stack.

No usa Remote API ni TARGET_WRITE: escribe el scratchpad directamente en el
sink con MSAP-SCRATCHPAD, lo marca y provoca el reboot que ejecuta el bootloader.
"""
from dataclasses import dataclass
import struct
import time

import wirepas_otap as w


STACK_AREA_ID = 0x00000106
APPLICATION_AREA_ID = 0x8CEC7B06
NRF52840_MAGIC = 0x06
SCRATCHPAD_TAG = w.TAG_SCR1
SCRATCHPAD_HEADER = 32
SECURITY_HEADER = 32
FILE_HEADER = 16


@dataclass(frozen=True)
class Image:
    area_id: int
    length: int
    version: tuple


@dataclass(frozen=True)
class Scratchpad:
    data: bytes
    crc: int
    stack: Image
    application: Image


def cargar(ruta: str) -> Scratchpad:
    data = open(ruta, "rb").read()
    if len(data) < SCRATCHPAD_HEADER + SECURITY_HEADER + FILE_HEADER:
        raise ValueError("scratchpad demasiado pequeno")
    if data[:16] != SCRATCHPAD_TAG:
        raise ValueError("no es un scratchpad SCR1")

    longitud, crc, _seq, _pad, _tipo, _estado = struct.unpack(
        "<LH2B2L", data[16:32]
    )
    if longitud != len(data) - SCRATCHPAD_HEADER:
        raise ValueError(f"longitud SCR1 incorrecta: cabecera={longitud}, real={len(data) - 32}")
    if w.crc16(data[32:]) != crc:
        raise ValueError(f"CRC SCR1 incorrecto: cabecera=0x{crc:04X}")

    pos = SCRATCHPAD_HEADER + SECURITY_HEADER
    imagenes = []
    while pos < len(data):
        if len(data) - pos < FILE_HEADER:
            raise ValueError("cabecera de imagen incompleta")
        area, longitud_imagen, *version, _pad = struct.unpack(
            "<2L4BL", data[pos : pos + FILE_HEADER]
        )
        pos += FILE_HEADER
        if pos + longitud_imagen > len(data):
            raise ValueError("datos de imagen incompletos")
        imagenes.append(Image(area, longitud_imagen, tuple(version)))
        pos += longitud_imagen
    if pos != len(data):
        raise ValueError("datos sobrantes tras las imagenes")

    stacks = [i for i in imagenes if i.area_id == STACK_AREA_ID]
    aplicaciones = [
        i for i in imagenes
        if i.area_id & 0xFF == NRF52840_MAGIC and i.area_id & 0x80000000
    ]
    if len(stacks) != 1:
        raise ValueError(f"se esperaba un stack 0x{STACK_AREA_ID:08X}, hay {len(stacks)}")
    if len(aplicaciones) != 1:
        raise ValueError(f"se esperaba una aplicacion nRF52840, hay {len(aplicaciones)}")
    if len(imagenes) != 2:
        raise ValueError(f"scratchpad no dual app+stack: contiene {len(imagenes)} imagenes")
    if aplicaciones[0].area_id != APPLICATION_AREA_ID:
        raise ValueError(
            f"area de aplicacion incompatible: 0x{aplicaciones[0].area_id:08X}; "
            f"se esperaba 0x{APPLICATION_AREA_ID:08X}"
        )
    return Scratchpad(data, crc, stacks[0], aplicaciones[0])


def estado(sink: w.Sink) -> dict:
    payload = sink.req(w.SCRATCH_STATUS, b"", 2)
    if len(payload) < 24:
        raise IOError(f"SCRATCHPAD_STATUS incompleto: {len(payload)} bytes")
    return {
        "len": int.from_bytes(payload[0:4], "little"),
        "crc": int.from_bytes(payload[4:6], "little"),
        "seq": payload[6],
        "tipo": payload[7],
        "estado": payload[8],
        "procesado_len": int.from_bytes(payload[9:13], "little"),
        "procesado_crc": int.from_bytes(payload[13:15], "little"),
        "procesado_seq": payload[15],
        "area_firmware": int.from_bytes(payload[16:20], "little"),
        "version": tuple(payload[20:24]),
    }


def siguiente_seq(st: dict) -> int:
    actual = st["seq"] if st["len"] else st["procesado_seq"]
    return 1 if actual in (0, 254, 255) else actual + 1


def _comprobar(cancelar):
    w._comprobar_cancelacion(cancelar)


def _reconectar(sink: w.Sink, timeout_s: int, cancelar=None):
    try:
        sink.s.close()
    except Exception:
        pass
    fin = time.time() + timeout_s
    ultimo = None
    while time.time() < fin:
        _comprobar(cancelar)
        try:
            sink.s = w.serial.Serial(sink.puerto, sink.baudios, timeout=0.05)
            if w.probar(sink):
                w.drenar(sink)
                return
            sink.s.close()
        except w.serial.SerialException as e:
            ultimo = e
            try:
                sink.s.close()
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"UART no vuelve tras reboot: {ultimo or sink.puerto}")


def _detener(sink: w.Sink, timeout_s: int, cancelar=None, debe_reiniciar=False):
    _comprobar(cancelar)
    respuesta = sink.req(w.STACK_STOP, b"", 10)
    if not respuesta:
        raise IOError("STACK_STOP sin resultado")
    resultado = respuesta[0]
    if resultado == 1 and not debe_reiniciar:
        return
    if resultado != 0:
        raise IOError(f"STACK_STOP rechazado (result=0x{resultado:02X})")
    _reconectar(sink, timeout_s, cancelar)


def _subir(sink: w.Sink, paquete: Scratchpad, seq: int, cancelar=None):
    if len(paquete.data) % 16:
        raise ValueError("el tamano del scratchpad no es multiplo de 16")
    respuesta = sink.req(
        w.SCRATCH_START,
        len(paquete.data).to_bytes(4, "little") + bytes([seq]),
        45,
    )
    if not respuesta or respuesta[0] != 0:
        raise IOError(f"SCRATCHPAD_START rechazado (result=0x{respuesta[0] if respuesta else 0xFF:02X})")

    for offset in range(0, len(paquete.data), w.BLOCK):
        _comprobar(cancelar)
        bloque = paquete.data[offset : offset + w.BLOCK]
        respuesta = sink.req(
            w.SCRATCH_BLOCK,
            offset.to_bytes(4, "little") + bytes([len(bloque)]) + bloque,
            5,
        )
        resultado = respuesta[0] if respuesta else 0xFF
        ultimo = offset + len(bloque) == len(paquete.data)
        if resultado != 0 and not (ultimo and resultado == 1):
            raise IOError(
                f"SCRATCHPAD_BLOCK offset={offset} rechazado (result=0x{resultado:02X}); "
                "hay que reiniciar la carga completa"
            )
        escritos = offset + len(bloque)
        if escritos == len(paquete.data) or escritos // 4096 != offset // 4096:
            w.log(f"[SINK] subida {escritos}/{len(paquete.data)} B")


def _comprobar_cargado(st: dict, paquete: Scratchpad, seq: int):
    esperado = len(paquete.data), paquete.crc, seq
    actual = st["len"], st["crc"], st["seq"]
    if actual != esperado:
        raise IOError(f"scratchpad del sink incorrecto: esperado={esperado}, real={actual}")
    if st["tipo"] != 1 or st["estado"] != 0xFF:
        raise IOError(
            f"scratchpad no esta listo para marcar: tipo=0x{st['tipo']:02X}, "
            f"estado=0x{st['estado']:02X}"
        )


def _comprobar_procesado(st: dict, paquete: Scratchpad, seq: int):
    esperado = len(paquete.data), paquete.crc, seq
    actual = st["procesado_len"], st["procesado_crc"], st["procesado_seq"]
    if st["estado"] != 0:
        raise IOError(f"bootloader rechazo el scratchpad (estado=0x{st['estado']:02X})")
    if actual != esperado:
        raise IOError(f"scratchpad procesado incorrecto: esperado={esperado}, real={actual}")
    if st["area_firmware"] != paquete.stack.area_id or st["version"] != paquete.stack.version:
        raise IOError(
            "stack ejecutado incorrecto: "
            f"area=0x{st['area_firmware']:08X}, version={'.'.join(map(str, st['version']))}"
        )


def actualizar(
    sink: w.Sink,
    ruta: str,
    seq: int = None,
    reconexion_s: int = 180,
    cancelar=None,
):
    paquete = cargar(ruta)
    if seq is None:
        seq = siguiente_seq(estado(sink))
    if not 1 <= seq <= 254:
        raise ValueError("seq debe estar entre 1 y 254")

    st = estado(sink)
    if st["tipo"] == 2 and st["estado"] == 0xFF:
        raise IOError("el sink ya tiene un scratchpad pendiente de procesar")
    if seq == st["seq"]:
        raise ValueError(f"seq={seq} coincide con el scratchpad actual")

    w.log(
        f"[SINK] paquete: {len(paquete.data)} B, crc=0x{paquete.crc:04X}, seq={seq}"
    )
    w.log(
        f"[SINK] stack: 0x{paquete.stack.area_id:08X} "
        f"{'.'.join(map(str, paquete.stack.version))}; "
        f"app: 0x{paquete.application.area_id:08X} "
        f"{'.'.join(map(str, paquete.application.version))}"
    )

    _detener(sink, reconexion_s, cancelar)
    try:
        _subir(sink, paquete, seq, cancelar)
        st = estado(sink)
        _comprobar_cargado(st, paquete, seq)
        w.log("[SINK] scratchpad verificado en sink")

        respuesta = sink.req(w.SCRATCH_UPDATE, b"", 10)
        if not respuesta or respuesta[0] != 0:
            raise IOError(f"SCRATCHPAD_UPDATE rechazado (result=0x{respuesta[0] if respuesta else 0xFF:02X})")
        st = estado(sink)
        if st["tipo"] != 2 or st["estado"] != 0xFF:
            raise IOError("el scratchpad no quedo marcado para procesar")
        w.log("[SINK] scratchpad marcado; provocando reboot para procesarlo")
    except Exception:
        w.log("[SINK] carga no completada; no se reintenta ningun bloque individual")
        raise

    _detener(sink, reconexion_s, cancelar, debe_reiniciar=True)
    st = estado(sink)
    _comprobar_procesado(st, paquete, seq)
    w.log("[SINK] stack procesado y verificado")

    respuesta = sink.req(w.STACK_START, b"\x00", 10)
    if not respuesta or respuesta[0] != 0:
        raise IOError(f"STACK_START rechazado (result=0x{respuesta[0] if respuesta else 0xFF:02X})")
    if not w.probar(sink):
        raise TimeoutError("el stack no responde tras STACK_START")
    w.log("[SINK] stack arrancado; la aplicacion va incluida en el scratchpad")
