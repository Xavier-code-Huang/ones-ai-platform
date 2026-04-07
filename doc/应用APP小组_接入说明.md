# 应用APP小组 — ones-AI 日志上报接入说明

> **接口由 ones-AI 平台组提供** | 创建日期：2026-03-27

---

## 你们的专属信息

```
团队名称：应用APP小组
API Key：d9cd4bce921309d37907bb7a8c3538605ba12469d444f4a070f38ebc23b99817
```

> ⚠️ **API Key 请妥善保管**，拥有此 Key 即可上报数据到你们的团队名下。

---

## 怎么用

向以下地址发送 POST 请求，把你们的工单处理日志上报过来就行：

```
POST http://172.60.1.35:9621/api/external/report
```

### 请求头

```
Content-Type: application/json
X-API-Key: d9cd4bce921309d37907bb7a8c3538605ba12469d444f4a070f38ebc23b99817
```

### 请求体

```json
{
  "logs": [
    {
      "member_name": "张三",
      "ticket_id": "ONES-123456",
      "action_type": "process",
      "status": "completed",
      "duration": 120.5,
      "summary": "修复了某个问题"
    }
  ]
}
```

可以一次上报多条（最多 100 条），`logs` 数组里放多个对象就行。

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `member_name` | ✅ 必填 | 谁处理的（姓名），首次上报自动注册为团队成员 |
| `ticket_id` | 选填 | 工单号，如 `ONES-123456` |
| `action_type` | 选填 | 操作类型：`process`（处理）/ `analysis`（分析）/ `fix`（修复），默认 `process` |
| `status` | 选填 | 结果：`completed`（成功）/ `failed`（失败），默认 `completed` |
| `duration` | 选填 | 耗时（秒），默认 0 |
| `summary` | 选填 | 备注说明 |

### 返回示例

成功：
```json
{"success": true, "inserted": 1, "team": "应用APP小组"}
```

失败：
```json
{"detail": "无效的 API Key 或团队已禁用"}
```

---

## 代码示例

### Python（最简单）

```python
import requests

API_URL = "http://172.60.1.35:9621/api/external/report"
API_KEY = "d9cd4bce921309d37907bb7a8c3538605ba12469d444f4a070f38ebc23b99817"

r = requests.post(API_URL, json={
    "logs": [
        {
            "member_name": "张三",
            "ticket_id": "ONES-123456",
            "action_type": "process",
            "status": "completed",
            "duration": 120.5,
            "summary": "修复了空指针问题"
        },
        {
            "member_name": "李四",
            "ticket_id": "ONES-789012",
            "action_type": "analysis",
            "status": "failed",
            "duration": 45.0,
            "summary": "无法复现"
        }
    ]
}, headers={"X-API-Key": API_KEY})

print(r.json())  # {'success': True, 'inserted': 2, 'team': '应用APP小组'}
```

### cURL（命令行测试）

```bash
curl -X POST http://172.60.1.35:9621/api/external/report \
  -H "Content-Type: application/json" \
  -H "X-API-Key: d9cd4bce921309d37907bb7a8c3538605ba12469d444f4a070f38ebc23b99817" \
  -d '{"logs":[{"member_name":"张三","ticket_id":"ONES-123456","status":"completed","duration":60}]}'
```

### Java（OkHttp）

```java
OkHttpClient client = new OkHttpClient();
String json = "{\"logs\":[{\"member_name\":\"张三\",\"ticket_id\":\"ONES-123456\",\"action_type\":\"process\",\"status\":\"completed\",\"duration\":120.5,\"summary\":\"修复问题\"}]}";
Request request = new Request.Builder()
    .url("http://172.60.1.35:9621/api/external/report")
    .addHeader("X-API-Key", "d9cd4bce921309d37907bb7a8c3538605ba12469d444f4a070f38ebc23b99817")
    .post(RequestBody.create(json, MediaType.parse("application/json")))
    .build();
Response response = client.newCall(request).execute();
System.out.println(response.body().string());
```

---

## 常见问题

| 问题 | 解答 |
|------|------|
| 一次最多上报多少条？ | 100 条 |
| member_name 需要提前注册吗？ | 不需要，首次上报自动注册 |
| 可以重复上报同一个工单吗？ | 可以，每次上报都会新增一条记录 |
| 网络不通怎么办？ | 确认能 ping 通 172.60.1.35，端口 9621 在公司内网开放 |
| API Key 泄露了怎么办？ | 联系黄易翔重新生成 |

---

## 联系方式

有问题找 **黄易翔**
