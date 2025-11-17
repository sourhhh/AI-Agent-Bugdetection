import json
import collections

REPORT = "output/defects4j_defect_report.json"

with open(REPORT, "r", encoding="utf-8") as f:
    r = json.load(f)

files = r.get("reports", {}).get("java", {}).get("files", [])
sev_counter = collections.Counter()
for f in files:
    for d in f.get("defects", []):
        sev_counter[d.get("severity", "UNKNOWN")] += 1

print("Severity counts:")
for k, v in sev_counter.most_common():
    print(f"  {k}: {v}")

medium_plus = sev_counter.get('CRITICAL', 0) + sev_counter.get('HIGH', 0) + sev_counter.get('MEDIUM', 0)
print(f"\nMEDIUM+ total: {medium_plus}")
print(f"Total defects: {sum(sev_counter.values())}")
