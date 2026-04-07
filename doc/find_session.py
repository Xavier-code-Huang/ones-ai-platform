# -*- coding: utf-8 -*-
import os
import time

brain = r'C:\Users\HuangYixiang\.gemini\antigravity\brain'
results = []

for d in os.listdir(brain):
    dp = os.path.join(brain, d)
    if not os.path.isdir(dp):
        continue
    task_md = os.path.join(dp, 'task.md')
    if os.path.exists(task_md):
        mtime = os.path.getmtime(task_md)
        # Read first few lines of task.md
        with open(task_md, 'r', encoding='utf-8', errors='ignore') as f:
            first_lines = f.read(200)
        results.append((mtime, d, first_lines.replace('\n', ' | ')))

results.sort(key=lambda x: x[0], reverse=True)
for mtime, cid, preview in results[:30]:
    t = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))
    print(f"{t} | {cid} | {preview[:120]}")
