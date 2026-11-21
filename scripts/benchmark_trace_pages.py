"""Compare archived RenderDoc debugger traces with indexed copies in a temporary directory."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_trace_paging import page_tool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge_extension/renderdoc_mcp_bridge/domains"))
from trace_writer import write_trace


def original(path, offset, limit=50, variable=None):
    data = json.loads(path.read_text(encoding="utf-8"))
    states = data["states"][offset:offset+limit]
    if variable:
        states = [dict(s, changes=[c for c in s.get("changes", []) if any(
            variable in str(c.get(key, {}).get("name", "")) for key in ("before", "after"))]) for s in states]
    end = offset + len(states)
    return dict(stage=data.get("stage"), complete=data.get("complete"), errors=data.get("errors"),
                total_steps=len(data["states"]), offset=offset, next_offset=end,
                has_more=end < len(data["states"]), states=states)


def summarize(samples):
    return dict(p50_ms=round(statistics.median(samples), 3),
                p95_ms=round(sorted(samples)[math.ceil(.95*len(samples))-1], 3))


def peak(call):
    tracemalloc.start()
    try:
        call()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def compare(path, directory, repeats):
    indexed = directory/"indexed.json"
    legacy = directory/"legacy.json"
    trace = json.loads(path.read_bytes())
    count = len(trace["states"])
    read = page_tool()
    def old_write():
        with legacy.open("w", encoding="utf8") as stream:
            json.dump(trace, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.write("\n")
    def new_write():
        with indexed.open("wb") as stream:
            write_trace(stream, trace)
    writes = [[], []]
    for i in range(repeats+1):
        for j in (i%2, 1-i%2):
            start = time.perf_counter()
            (old_write, new_write)[j]()
            if i:
                writes[j].append((time.perf_counter()-start)*1000)
    restored = json.loads(indexed.read_bytes())
    for extra in ("_rd_seek", "_rd_page_v1"):
        restored.pop(extra)
    assert restored == trace
    names = (str(v.get("name", "")) for state in trace["states"] for c in state.get("changes", [])
             for v in (c.get("before", {}), c.get("after", {})))
    name = next((name for name in names if name), "r")
    offsets = sorted({0, count//2, max(0, count-50), count, count+1, *range(0, count, 50)})
    for offset in offsets:
        for variable in (None, name, "__unmatched__"):
            expected = original(path, offset, variable=variable)
            assert read(str(indexed), offset, 50, variable) == read(str(path), offset, 50, variable) == expected
    offset = max(0, count-50)
    funcs = [lambda: original(path, offset), lambda: read(str(indexed), offset, 50)]
    reads = [[], []]
    for i in range(repeats+1):
        for j in (i%2, 1-i%2):
            start = time.perf_counter()
            funcs[j]()
            if i:
                reads[j].append((time.perf_counter()-start)*1000)
    return dict(source=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                eid=trace.get("eid"), stage=trace["stage"], steps=count, checks=len(offsets)*3,
                source_bytes=path.stat().st_size, old_writer_bytes=legacy.stat().st_size,
                new_writer_bytes=indexed.stat().st_size, old_write=summarize(writes[0]),
                new_write=summarize(writes[1]), old_read=summarize(reads[0]), new_read=summarize(reads[1]),
                old_peak=peak(funcs[0]), new_peak=peak(funcs[1]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps([compare(path, Path(tmp), args.repeats) for path in args.traces], indent=2))
