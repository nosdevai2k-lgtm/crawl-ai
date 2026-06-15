from pathlib import Path

SIG = (b"\xff\xd8\xff", b"\x89PNG", b"GIF87a", b"GIF89a", b"BM", b"RIFF")
base = Path("data/images")
GROUPS = ["festival", "holidays", "events", "human", "architecture"]

grand = bad_total = low = 0
for g in GROUPS:
    gdir = base / g
    if not gdir.is_dir():
        print(f"[MISSING] {g}"); continue
    print(f"\n=== {g} ===")
    for d in sorted(p for p in gdir.iterdir() if p.is_dir()):
        files = [f for f in d.iterdir() if f.is_file()]
        valid = bad = 0
        for f in files:
            try:
                if any(f.read_bytes()[:16].startswith(s) for s in SIG): valid += 1
                else: bad += 1
            except Exception: bad += 1
        grand += valid; bad_total += bad
        flag = "  <BAD" if bad else ("  <LOW" if valid < 35 else "")
        if bad or valid < 35:
            low += 1
        print(f"  {d.name:30} {valid:3} valid {('bad='+str(bad)) if bad else ''}{flag}")
print(f"\nTOTAL valid: {grand} | bad files: {bad_total} | low/bad folders: {low}")
