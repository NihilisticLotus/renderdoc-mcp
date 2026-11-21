"""Seek into a v1 indexed JSON trace, or read the original JSON representation."""
import json
import os
import struct
import zlib


_TRAILER_PREFIX = b'","_rd_page_v1":"'
_TRAILER_SIZE = len(_TRAILER_PREFIX) + 16 + len(b'"}\n')
_INDEX_PREFIX = b'],"_rd_seek":"'
_RECORD_SIZE = 40  # 16 hex chars each for position and length, 8 for CRC32


def _indexed(stream, offset, limit):
    size = stream.seek(0, os.SEEK_END)
    if size < _TRAILER_SIZE:
        return None
    stream.seek(size - _TRAILER_SIZE)
    trailer = stream.read(_TRAILER_SIZE)
    if not trailer.startswith(_TRAILER_PREFIX) or not trailer.endswith(b'"}\n'):
        return None
    count = int(trailer[len(_TRAILER_PREFIX):-3], 16)
    table = size - _TRAILER_SIZE - count * _RECORD_SIZE
    if table < len(_INDEX_PREFIX):
        raise ValueError("Invalid trace index length")
    stream.seek(table - len(_INDEX_PREFIX))
    if stream.read(len(_INDEX_PREFIX)) != _INDEX_PREFIX:
        raise ValueError("Invalid trace index boundary")
    stream.seek(0)
    header = stream.readline(65536)
    if not header.endswith(b",\n"):
        return None  # Large diagnostic or file reformatted by another producer.
    metadata = json.loads(header[:-2] + b"}")
    length = max(0, min(limit, count - offset))
    states = []
    if length:
        stream.seek(table + offset * _RECORD_SIZE)
        records = stream.read(length * _RECORD_SIZE)
        for i in range(length):
            record = records[i * _RECORD_SIZE:(i + 1) * _RECORD_SIZE]
            start, nbytes, checksum = int(record[:16], 16), int(record[16:32], 16), int(record[32:], 16)
            if start < len(header) or nbytes < 2 or start + nbytes > table - len(_INDEX_PREFIX):
                raise ValueError("Invalid state coordinates")
            stream.seek(start)
            raw = stream.read(nbytes)
            if zlib.crc32(raw, zlib.crc32(struct.pack("<Q", offset + i))) != checksum:
                raise ValueError("Invalid state checksum")
            states.append(json.loads(raw))
    return metadata, count, states


def read_trace_page(path, offset, limit):
    with open(path, "rb") as stream:
        try:
            page = _indexed(stream, offset, limit)
        except (ValueError, OverflowError):
            page = None
        if page is not None:
            return page
        # Use the same open file even if the writer publishes a replacement meanwhile.
        stream.seek(0)
        data = json.load(stream)
        states = data.get("states", [])
        return data, len(states), states[offset:offset + limit]
