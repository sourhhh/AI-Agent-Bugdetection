import json
import collections
import sys

REPORT = "output/defects4j_defect_report.json"

with open(REPORT, "r", encoding="utf-8") as f:
    r = json.load(f)

files = r.get("files", [])
sev_counter = collections.Counter()
type_counter = collections.Counter()
tool_counter = collections.Counter()
msg_counter = collections.Counter()

for f in files:
    for d in f.get("defects", []):
        sev = d.get("severity", "UNKNOWN")
        t = d.get("type", "UNKNOWN")
        tool = d.get("tool", "UNKNOWN")
        msg = d.get("message", "")
        sev_counter[sev] += 1
        type_counter[t] += 1
        tool_counter[tool] += 1
        # normalize message a bit
        short = msg.split('\n')[0][:120]
        msg_counter[short] += 1

print("Severity counts:")
for k, v in sev_counter.most_common():
    print(f"  {k}: {v}")

print("\nTop defect types:")
for k, v in type_counter.most_common(20):
    print(f"  {k}: {v}")

print("\nTop tools:")
for k, v in tool_counter.most_common():
    print(f"  {k}: {v}")

print("\nTop messages (sample):")
for k, v in msg_counter.most_common(20):
    print(f"  {v}x: {k}")

# show sample files with CRITICAL/HIGH/MEDIUM counts
file_summary = []
for f in files:
    c = collections.Counter()
    for d in f.get("defects", []):
        c[d.get("severity", "UNKNOWN")] += 1
    if c["CRITICAL"] + c["HIGH"] + c["MEDIUM"] > 0:
        file_summary.append((f.get("file_path"), c["CRITICAL"], c["HIGH"], c["MEDIUM"], c["LOW"]))

file_summary.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)
print("\nTop files by MEDIUM+/HIGH/CRITICAL defects (top 20):")
for fpath, cr, hi, me, lo in file_summary[:20]:
    print(f"  {cr} CRITICAL, {hi} HIGH, {me} MEDIUM, {lo} LOW — {fpath}")

# quick heuristic suggestions
print("\nHeuristic suggestions:\n  - Consider downgrading repetitive checkstyle formatting issues (tabs/indent/line-length) from MEDIUM to LOW when confidence >= 0.8 and type == 'code_smell'.")
print("  - Consider downgrading PMD warnings about 'System.exit in library' to LOW for test/resources or generated_sources directories.")
print("  - Keep CRITICAL/HIGH syntax errors unchanged.")

# exit with counts for potential automation
print("\nDone.")
