# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""S-10 spike: engine overhead per step, fsync cost, and replay speed. Throwaway.

Method. A block calls N steps through ctx. The tool does no work (it returns a small dict at once), so the time of
`await ctx.tool(...)` is the engine's own cost plus the tool's own time. The tool times itself; the engine overhead
of a step is (time around ctx.tool) minus (the tool's own time). Clock: time.perf_counter_ns. The journal is a real
SQLite file in a temporary directory on the same disk the run would use. Percentiles use the nearest-rank method.

    uv run --script bench.py [--n 2000] [--dir PATH]
"""

import argparse
import asyncio
import math
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from engine import POLICIES, Ctx, Engine, ToolSpec


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def summarize(ms: list[float]) -> dict[str, float]:
    return {"n": len(ms), "p50": pct(ms, 50), "p95": pct(ms, 95), "p99": pct(ms, 99), "max": max(ms), "mean": sum(ms) / len(ms)}


async def _step_overhead(run_dir: Path, policy: str, effect: str, n: int, warm: int, payload: int) -> list[float]:
    inner: list[int] = []
    blob = "x" * payload

    async def noop(op_id: str, i: int) -> Any:
        t = time.perf_counter_ns()
        r = {"ok": True, "i": i, "echo": blob}
        inner.append(time.perf_counter_ns() - t)
        return r

    over: list[float] = []

    async def block(ctx: Ctx, inp: Any) -> Any:
        for i in range(n + warm):
            t0 = time.perf_counter_ns()
            await ctx.tool("noop", i=i)
            total = time.perf_counter_ns() - t0
            if i >= warm:
                over.append((total - inner[-1]) / 1e6)
        return {}

    eng = Engine(run_dir, "bench", {"noop": ToolSpec(noop, effect)}, policy)
    out = await eng.run(block, {}, "bench", "1")
    assert out.status == "COMPLETED", out
    return over


def step_overhead(base: Path, policy: str, effect: str, n: int, payload: int = 256) -> dict[str, float]:
    d = base / f"ov-{policy}-{effect}-{payload}"
    shutil.rmtree(d, ignore_errors=True)
    return summarize(asyncio.run(_step_overhead(d, policy, effect, n, max(50, n // 20), payload)))


def fsync_cost(base: Path, n: int = 500) -> dict[str, float]:
    """Raw cost of append + fsync of a small record on this disk, for comparison with the journal numbers."""
    p = base / "fsync.bin"
    ms: list[float] = []
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        for _ in range(n):
            t = time.perf_counter_ns()
            os.write(fd, b"x" * 200)
            os.fsync(fd)
            ms.append((time.perf_counter_ns() - t) / 1e6)
    finally:
        os.close(fd)
        p.unlink()
    return summarize(ms)


async def _replay(run_dir: Path, steps: int) -> tuple[float, float, int]:
    async def noop(op_id: str, i: int) -> Any:
        return {"ok": True, "i": i}

    async def block(ctx: Ctx, inp: Any) -> Any:
        for i in range(steps):
            await ctx.tool("noop", i=i)
        await ctx.approve("stop", {"n": steps})  # pauses, so the run is not terminal and can be resumed
        return {}

    tools = {"noop": ToolSpec(noop, "write")}
    t0 = time.perf_counter()
    out = await Engine(run_dir, "bench", tools, "normal").run(block, {}, "bench", "1")
    first = time.perf_counter() - t0
    assert out.status == "PAUSED"
    t0 = time.perf_counter()
    out = await Engine(run_dir, "bench", tools, "normal").run(block, {}, "bench", "1")
    second = time.perf_counter() - t0
    assert out.status == "PAUSED" and out.replayed == steps and out.live == 0, out
    size = sum(f.stat().st_size for f in run_dir.glob("journal.sqlite*"))
    return first, second, size


def replay_cost(base: Path, steps: int) -> dict[str, float]:
    d = base / f"replay-{steps}"
    shutil.rmtree(d, ignore_errors=True)
    first, second, size = asyncio.run(_replay(d, steps))
    return {"steps": steps, "resume_ms": second * 1e3, "us_per_recorded_step": second / steps * 1e6, "bytes_per_step": size / steps}


def fs_type(path: Path) -> str:
    try:
        best = ("", "?")
        for line in Path("/proc/mounts").read_text().splitlines():
            dev, mnt, fst = line.split()[:3]
            if str(path.resolve()).startswith(mnt) and len(mnt) >= len(best[0]):
                best = (mnt, fst)
        return best[1]
    except OSError:
        return "unknown" if os.name != "nt" else "NTFS or other (not read)"


def row(label: str, s: dict[str, float]) -> str:
    return f"| {label} | {s['n']} | {s['p50']:.3f} | {s['p95']:.3f} | {s['p99']:.3f} | {s['max']:.3f} |"


def report(base: Path, n: int, policies: list[str]) -> str:
    out = [
        f"python {platform.python_version()} · {platform.system()} {platform.release()} · sqlite {__import__('sqlite3').sqlite_version}"
        f" · cpu count {os.cpu_count()} · dir fs: {fs_type(base)}",
        "",
        "Engine overhead per step in ms (time around ctx.tool minus the tool's own time):",
        "",
        "| policy / step type | steps | p50 | p95 | p99 | max |",
        "|---|---|---|---|---|---|",
    ]
    for pol in policies:
        for eff in ("write", "read"):
            out.append(row(f"{pol} / {eff}", step_overhead(base, pol, eff, n)))
    out.append(row("mixed / write, 10 KB result", step_overhead(base, "mixed", "write", max(200, n // 4), 10_000)))
    out += ["", "Raw append + fsync of 200 bytes on the same disk (ms):", "", "| | n | p50 | p95 | p99 | max |", "|---|---|---|---|---|---|"]
    out.append(row("os.write + os.fsync", fsync_cost(base)))
    out += ["", "Replay speed (resume of a paused run, policy normal):", "", "| recorded steps | resume ms | us per recorded step | journal bytes per step |", "|---|---|---|---|"]
    for steps in (1000, 10000):
        r = replay_cost(base, steps)
        out.append(f"| {r['steps']} | {r['resume_ms']:.1f} | {r['us_per_recorded_step']:.1f} | {r['bytes_per_step']:.0f} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--dir", default="")
    ap.add_argument("--policies", default=",".join(POLICIES))
    a = ap.parse_args()
    base = Path(a.dir) if a.dir else Path(tempfile.mkdtemp(prefix="s10-bench-"))
    base.mkdir(parents=True, exist_ok=True)
    try:
        print(report(base, a.n, a.policies.split(",")))
    finally:
        if not a.dir:
            shutil.rmtree(base, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
