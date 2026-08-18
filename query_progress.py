"""Show running pipeline processes and files in their output dirs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent

PS_SCRIPT = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$procs = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -match '^(python|pythonw|cmd)\.exe$'
}
$result = foreach ($p in $procs) {
  $gp = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
  [pscustomobject]@{
    pid = $p.ProcessId
    ppid = $p.ParentProcessId
    name = $p.Name
    cmd = $p.CommandLine
    start = if ($gp) { $gp.StartTime.ToString('o') } else { $null }
    cpu_s = if ($gp) { [math]::Round($gp.CPU, 1) } else { $null }
    ws_mb = if ($gp) { [math]::Round($gp.WorkingSet64 / 1MB, 1) } else { $null }
  }
}
$result | ConvertTo-Json -Compress -Depth 4
"""

ARG_RE = re.compile(
  r"""(?:--(?:output-dir|output-root|output|raw|src|stem))(?:[=\s]+)(?:"([^"]+)"|'([^']+)'|(\S+))""",
  re.IGNORECASE,
)


def configure_stdout() -> None:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def parse_start(value: str | None) -> datetime | None:
  if not value:
    return None
  try:
    return datetime.fromisoformat(value)
  except ValueError:
    return None


def fmt_elapsed(start: datetime | None) -> str:
  if start is None:
    return "-"
  now = datetime.now(start.tzinfo) if start.tzinfo else datetime.now()
  sec = max(0, int((now - start).total_seconds()))
  h, rem = divmod(sec, 3600)
  m, s = divmod(rem, 60)
  if h:
    return f"{h}h {m}m {s}s"
  if m:
    return f"{m}m {s}s"
  return f"{s}s"


def fmt_size(n: int) -> str:
  if n < 1024:
    return f"{n} B"
  if n < 1024 * 1024:
    return f"{n / 1024:.1f} KB"
  return f"{n / (1024 * 1024):.1f} MB"


def relevant(cmd: str | None) -> bool:
  if not cmd:
    return False
  markers = (
    str(CODE_ROOT),
    "run_full_drawing",
    "run_stats",
    "batch_export_test_input",
    "collect_pipeline_stats",
    "step2A",
    "step2B",
    "step3A",
    "step3B",
    "step4A",
    "step4B",
    "step1a",
    "step1b",
    "stage2",
  )
  return any(m in cmd for m in markers)


def parse_cmd_args(cmd: str) -> dict[str, str]:
  out: dict[str, str] = {}
  for m in ARG_RE.finditer(cmd):
    key = m.group(0).split()[0].lstrip("-").split("=")[0].lower()
    val = next(g for g in m.groups() if g)
    out[key] = val.strip('"')
  stem_eq = re.search(r"--stem=(\S+)", cmd, re.IGNORECASE)
  if stem_eq and "stem" not in out:
    out["stem"] = stem_eq.group(1).strip('"')
  return out


def infer_output_dir(cmd: str) -> Path | None:
  args = parse_cmd_args(cmd)
  for key in ("output", "output-dir", "raw"):
    if key in args:
      p = Path(args[key])
      if not p.is_absolute():
        p = CODE_ROOT / p
      return p
  stem = args.get("stem")
  if not stem and "src" in args:
    stem = Path(args["src"]).stem
  if stem:
    root = args.get("output-root")
    if root:
      base = Path(root)
      if not base.is_absolute():
        base = CODE_ROOT / base
      return base / f"{stem}_output"
    return CODE_ROOT / f"{stem}_output"
  return None


def list_artifacts(out_dir: Path, *, start: datetime | None, limit: int) -> list[tuple[Path, int, datetime]]:
  if not out_dir.is_dir():
    return []
  rows: list[tuple[Path, int, datetime]] = []
  for p in out_dir.rglob("*"):
    if not p.is_file():
      continue
    st = p.stat()
    rows.append((p, st.st_size, datetime.fromtimestamp(st.st_mtime)))
  rows.sort(key=lambda x: x[2], reverse=True)
  return rows[:limit]


def load_processes() -> list[dict]:
  completed = subprocess.run(
    ["powershell", "-NoProfile", "-Command", PS_SCRIPT],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
  )
  if completed.returncode != 0:
    print(completed.stderr.strip() or "failed to list processes", file=sys.stderr)
    sys.exit(1)
  raw = (completed.stdout or "").strip()
  if not raw or raw == "null":
    return []
  data = json.loads(raw)
  if isinstance(data, dict):
    return [data]
  return list(data)


def main() -> None:
  configure_stdout()
  parser = argparse.ArgumentParser(description="Show running processes and their output files")
  parser.add_argument("--all", action="store_true", help="list all python/cmd, not only this repo")
  parser.add_argument("--limit", type=int, default=20, help="max files to list per process")
  args = parser.parse_args()

  now = datetime.now().astimezone()
  rows = load_processes()
  if not args.all:
    rows = [r for r in rows if relevant(r.get("cmd"))]
  rows.sort(key=lambda r: r.get("start") or "")

  print(f"query time  {now:%Y-%m-%d %H:%M:%S}")
  if not rows:
    print("no related process running")
    return

  print(f"processes   {len(rows)}\n")
  for r in rows:
    start = parse_start(r.get("start"))
    cpu = r.get("cpu_s")
    ws = r.get("ws_mb")
    cpu_txt = f"{cpu}s" if cpu is not None else "-"
    ws_txt = f"{ws} MB" if ws is not None else "-"
    start_txt = start.strftime("%H:%M:%S") if start else "-"
    cmd = r.get("cmd") or "(no command line)"
    print(f"PID {r.get('pid')}  parent {r.get('ppid')}  {r.get('name')}")
    print(f"  start {start_txt}    elapsed {fmt_elapsed(start)}")
    print(f"  CPU {cpu_txt}    RSS {ws_txt}")
    print(f"  {cmd}")

    out_dir = infer_output_dir(cmd)
    if out_dir is None:
      print("  output: (not inferred)")
      print()
      continue
    print(f"  output: {out_dir}")
    if not out_dir.exists():
      print("    (dir not created yet)")
      print()
      continue
    files = list_artifacts(out_dir, start=start, limit=args.limit)
    if not files:
      print("    (no files yet)")
      print()
      continue
    print(f"    files {len(files)} (newest first)")
    for path, size, mtime in files:
      flag = ""
      if start is not None:
        mtime_naive = mtime.replace(tzinfo=None)
        start_naive = start.replace(tzinfo=None)
        if mtime_naive >= start_naive:
          flag = "  [this run]"
      rel = path
      try:
        rel = path.relative_to(out_dir)
      except ValueError:
        pass
      print(f"    {mtime:%H:%M:%S}  {fmt_size(size):>10}  {rel}{flag}")
    print()


if __name__ == "__main__":
  main()
