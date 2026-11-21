"""Indexed shader trace writer. Run as a script to index a copy of an archived trace."""
import json
import os
import struct
import tempfile
import zlib


def _json_bytes(value):
    return json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def write_trace(stream, payload):
    """Single JSON document, with fixed-width ASCII seek records in an extra field."""
    header = {key: payload[key] for key in ("stage", "complete", "errors")}
    stream.write(_json_bytes(header)[:-1] + b",\n")
    for key, value in payload.items():
        if key not in header and key not in ("states", "_rd_seek", "_rd_page_v1"):
            stream.write(_json_bytes(key) + b":" + _json_bytes(value) + b",")
    stream.write(b'"states":[')
    index = bytearray()
    for ordinal, state in enumerate(payload["states"]):
        if ordinal:
            stream.write(b",")
        start = stream.tell()
        raw = _json_bytes(state)
        checksum = zlib.crc32(raw, zlib.crc32(struct.pack("<Q", ordinal)))
        index.extend(("%016x%016x%08x" % (start, len(raw), checksum)).encode("ascii"))
        stream.write(raw)
    stream.write(b'],"_rd_seek":"')
    stream.write(index)
    stream.write(('","_rd_page_v1":"%016x"}\n' % len(payload["states"])).encode("ascii"))


def publish_trace(path, payload, overwrite):
    # Index and payload reach readers in the same publication, including on overwrite.
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            write_trace(stream, payload)
        if overwrite:
            os.replace(temporary, path)
        elif os.name == "nt":
            os.rename(temporary, path)  # Windows rename fails when the destination exists.
        else:
            os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Existing shader debugger JSON")
    parser.add_argument("destination", help="New indexed JSON file")
    args = parser.parse_args()
    with open(args.source, "r", encoding="utf-8") as source:
        trace = json.load(source)
    if not isinstance(trace.get("states"), list) or not all(key in trace for key in ("stage", "complete", "errors")):
        parser.error("Expected a shader debug trace with states, stage, complete and errors")
    publish_trace(os.path.abspath(args.destination), trace, False)
