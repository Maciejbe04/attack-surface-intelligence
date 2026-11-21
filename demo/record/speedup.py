#!/usr/bin/env python3
"""Encode the raw recording to MP4, playing scan-wait segments (from ff.json) at SPEED x."""
import json, subprocess, sys

raw, marks_file, out = sys.argv[1:4]
SPEED = 4
marks = json.load(open(marks_file))
assert len(marks) % 2 == 0, "ff marks must come in start/end pairs"
pairs = list(zip(marks[::2], marks[1::2]))

parts, t = [], 0.0
for a, b in pairs:
    parts.append((t, a, 1)); parts.append((a, b, SPEED)); t = b
parts.append((t, None, 1))

chains = []
for i, (a, b, sp) in enumerate(parts):
    trim = f"trim=start={a}" + (f":end={b}" if b is not None else "")
    chains.append(f"[0:v]{trim},setpts=(PTS-STARTPTS)/{sp}[v{i}]")
graph = ";".join(chains) + ";" + "".join(f"[v{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[out]"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-filter_complex", graph, "-map", "[out]",
                "-r", "25", "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", out], check=True)
