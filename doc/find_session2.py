# -*- coding: utf-8 -*-
import os
import time

brain = r'C:\Users\HuangYixiang\.gemini\antigravity\brain'
results = []

# List all session directories without task.md (might be the lost session)
for d in os.listdir(brain):
    dp = os.path.join(brain, d)
    if not os.path.isdir(dp):
        continue
    task_md = os.path.join(dp, 'task.md')
    if not os.path.exists(task_md):
        # Check any files at all
        files = os.listdir(dp)
        if files:
            # Get modification time of the directory
            mtime = max(os.path.getmtime(os.path.join(dp, f)) for f in files if os.path.isfile(os.path.join(dp, f))) if any(os.path.isfile(os.path.join(dp, f)) for f in files) else os.path.getmtime(dp)
            results.append((mtime, d, ', '.join(files[:5])))

results.sort(key=lambda x: x[0], reverse=True)
print("=== Sessions WITHOUT task.md (possible lost sessions) ===")
for mtime, cid, files_preview in results[:20]:
    t = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))
    print(f"{t} | {cid} | files: {files_preview}")
