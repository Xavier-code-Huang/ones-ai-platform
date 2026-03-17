# -*- coding: utf-8 -*-
import urllib.request, json, sys

BASE = "http://localhost:9610"

login_data = json.dumps({"email": "admin@ones-ai.local", "password": "admin"}).encode()
req = urllib.request.Request(f"{BASE}/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
try:
    resp = urllib.request.urlopen(req, timeout=10)
    result = json.loads(resp.read())
    token = result["token"]
    print(f"Login OK: {result['user']['ones_email']} role={result['user']['role']}")
except Exception as e:
    print(f"Login failed: {e}")
    if hasattr(e, 'read'): print(e.read().decode())
    sys.exit(1)

server_data = json.dumps({"name": "35服务器", "host": "172.60.1.35", "ssh_port": 22, "description": "ones-AI 主部署服务器"}).encode()
req2 = urllib.request.Request(f"{BASE}/api/servers", data=server_data, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
try:
    resp2 = urllib.request.urlopen(req2, timeout=10)
    print(f"Server added: {json.loads(resp2.read())}")
except Exception as e:
    print(f"Add server result: {e}")
    if hasattr(e, 'read'): print(e.read().decode())

req3 = urllib.request.Request(f"{BASE}/api/servers", headers={"Authorization": f"Bearer {token}"})
resp3 = urllib.request.urlopen(req3, timeout=10)
servers = json.loads(resp3.read())
print(f"\nServers ({len(servers)}):")
for s in servers:
    print(f"  - {s.get('name','?')} ({s.get('host','?')})")
