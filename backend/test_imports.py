# -*- coding: utf-8 -*-
"""后端集成测试脚本"""
import sys
sys.path.insert(0, '.')

# 1. Config
from config import settings
print(f"✅ config.py OK - APP_NAME={settings.APP_NAME}")

# 2. Crypto
from crypto import encrypt_password, decrypt_password
encrypted = encrypt_password("test123")
decrypted = decrypt_password(encrypted)
assert decrypted == "test123", f"Crypto failed: {decrypted}"
print(f"✅ crypto.py OK - encrypt/decrypt verified")

# 3. Database DDL
from database import INIT_SQL
table_count = INIT_SQL.count("CREATE TABLE")
print(f"✅ database.py OK - {table_count} tables defined")

# 4. Import all modules
import ones_client
print("✅ ones_client.py OK")
import auth
print(f"✅ auth.py OK - {len(auth.router.routes)} routes")
import ssh_pool
print("✅ ssh_pool.py OK")
import servers
print(f"✅ servers.py OK - {len(servers.router.routes)} routes")
import tasks
print(f"✅ tasks.py OK - {len(tasks.router.routes)} routes")
import task_executor
print("✅ task_executor.py OK")
import log_streamer
print("✅ log_streamer.py OK")
import evaluations
print(f"✅ evaluations.py OK - {len(evaluations.router.routes)} routes")
import notifications
print("✅ notifications.py OK")
import admin
print(f"✅ admin.py OK - {len(admin.router.routes)} routes")

# 5. Main app import
import main
print(f"✅ main.py OK - routes registered")

print("\n🎉 ALL 14 backend modules import successfully!")
