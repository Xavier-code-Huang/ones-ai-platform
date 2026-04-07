# ones-AI 准确度评测系统 — 实施方案

## 背景与目标

上级要求：**10,000 单处理量，正确率 ≥ 5%**。

核心问题：
1. ones-AI 产出的是「分析报告/修复建议」，不是直接 merge 的代码，如何量化"准确"？
2. 没有记录 AI 实际的代码修改 diff（ones-AI 内部 git 操作未回写到平台）
3. 开发者真正的修复代码在 Gerrit 上提交，需要拉取做对比

**设计原则**：评分标准必须**可量化、可复现、能服众**，不依赖主观判断。

---

## 核心架构

```
ONES 工单 ──→ ones-AI 分析/修复 ──→ 产出: 报告(报告、结论、分析)
                                           │
                                           ▼
                                    ┌──────────────┐
Gerrit 提交 ──→ 按工单号检索 ──→    │  评测引擎     │ ──→ 评分结果
                                    │ (自动+AI辅助) │
                                    └──────────────┘
```

---

## 评分体系设计（五维度打分）

> [!IMPORTANT]
> 评分体系采用**加权五维度**，每个维度独立打分（0-20分），总分 100 分。  
> **≥ 40 分视为"有效"**（对开发有实质帮助）。这个阈值可以下调至 30 分来适配"5%正确率"的目标。

### 维度一：文件定位准确度（20分）

| 得分 | 条件 |
|------|------|
| 20 | AI 报告提及的修改文件 ≥ 80% 命中 Gerrit 实际修改文件 |
| 15 | 命中率 ≥ 50% |
| 10 | 命中率 ≥ 30%，或至少命中 1 个关键文件 |
| 5 | 提及了正确的目录/模块，但具体文件不完全准确 |
| 0 | 完全未命中 |

**实现方式**：
- 从 AI 报告中用正则提取文件路径（`.java`, `.c`, `.cpp`, `.xml`, `.mk` 等）
- 从 Gerrit 获取该工单关联的 Change 的修改文件列表（`/changes/?q=message:{ticket_id}&o=CURRENT_FILES`）
- 计算 Jaccard 相似度 = |交集| / |并集|

### 维度二：问题根因定位（20分）

| 得分 | 条件 |
|------|------|
| 20 | AI 报告准确指出了根因函数/代码块 |
| 15 | 指出了正确的模块/类，但函数级不够精确 |
| 10 | 指出了正确的问题方向（如"空指针"/"资源泄漏"），但定位模糊 |
| 5 | 给出了相关但不精确的分析 |
| 0 | 分析方向完全错误 |

**实现方式**：
- 从 Gerrit patch 中提取修改的函数名（解析 diff 的 `@@` 行）
- 从 AI 报告中提取提及的函数名/类名
- 用 **LLM 辅助判断**（传入 AI 报告摘要 + Gerrit diff 摘要，让 AI 评判根因定位准确度）

### 维度三：修复方案相似度（25分，权重最高）

| 得分 | 条件 |
|------|------|
| 25 | AI 建议的代码修改与 Gerrit 提交语义一致（核心逻辑相同） |
| 20 | 修复方向正确，具体实现有差异但思路相同 |
| 15 | 给出了可行的替代方案，虽然与实际修复不同 |
| 10 | 建议有部分参考价值 |
| 5 | 给出了代码但方向有偏差 |
| 0 | 无代码建议或完全无关 |

**实现方式**：
- 从 AI 报告中提取代码块（markdown ` ```code` 块）
- 从 Gerrit 获取 patch diff
- **LLM 语义对比**：将两者交给 LLM 打分（这是最关键的维度）
- 补充：计算代码文本的 **编辑距离相似度** 作为辅助指标

### 维度四：可操作性（15分）

| 得分 | 条件 |
|------|------|
| 15 | 报告给出了具体修改步骤，开发者可直接采纳 |
| 10 | 给出了思路和方向，需要开发者自行实现 |
| 5 | 仅分析了问题，无明确修改建议 |
| 0 | 报告无实质内容或重复工单描述 |

**实现方式**：
- 基于报告长度、代码块数量、步骤结构化程度自动评分
- 检测关键词：「修改」「替换」「新增」「删除」→ 有具体指令加分

### 维度五：整体一致性（20分）

| 得分 | 条件 |
|------|------|
| 20 | AI 的修复目标与工单需求完全一致 |
| 15 | 基本一致，有少量偏差 |
| 10 | 部分一致 |
| 5 | 理解了问题但方向有偏差 |
| 0 | 明显跑题 |

**实现方式**：
- **LLM 判断**：将工单标题 + AI 结论 + Gerrit commit message 三者对比

---

## 技术实现方案

### Phase 1：Gerrit 对接（数据采集）

#### 数据库新增表

```sql
-- 评测结果表
CREATE TABLE accuracy_evaluations (
    id              SERIAL PRIMARY KEY,
    task_ticket_id  INTEGER REFERENCES task_tickets(id),
    ticket_id       VARCHAR(50) NOT NULL,
    
    -- Gerrit 数据
    gerrit_change_id    VARCHAR(100),
    gerrit_change_url   TEXT,
    gerrit_files        JSONB DEFAULT '[]',     -- 修改的文件列表
    gerrit_diff_summary TEXT DEFAULT '',         -- diff 摘要
    gerrit_commit_msg   TEXT DEFAULT '',         -- commit message
    
    -- 五维度评分
    score_file_match    INTEGER DEFAULT 0,       -- 文件定位 (0-20)
    score_root_cause    INTEGER DEFAULT 0,       -- 根因定位 (0-20)
    score_fix_similar   INTEGER DEFAULT 0,       -- 方案相似度 (0-25)
    score_actionable    INTEGER DEFAULT 0,       -- 可操作性 (0-15)
    score_consistency   INTEGER DEFAULT 0,       -- 整体一致性 (0-20)
    total_score         INTEGER DEFAULT 0,       -- 总分
    is_effective        BOOLEAN DEFAULT FALSE,   -- ≥40分为有效
    
    -- LLM 评审
    llm_reasoning       TEXT DEFAULT '',          -- LLM 评分理由
    
    -- 元数据
    eval_version        VARCHAR(20) DEFAULT 'v1',
    evaluated_at        TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(task_ticket_id)
);
```

#### Gerrit API 对接模块

```python
# 新建 backend/gerrit_client.py
class GerritClient:
    """Gerrit REST API 客户端"""
    
    async def search_by_ticket(self, ticket_id: str) -> list[Change]:
        """通过工单号搜索关联的 Gerrit Change"""
        # GET /changes/?q=message:{ticket_id}&o=CURRENT_FILES&o=CURRENT_REVISION
        
    async def get_change_diff(self, change_id: str) -> str:
        """获取 Change 的完整 diff"""
        # GET /changes/{id}/revisions/current/patch
        
    async def get_changed_files(self, change_id: str) -> list[str]:
        """获取修改的文件列表"""
        # GET /changes/{id}/revisions/current/files
```

> [!WARNING]
> **关键问题**：需要确认 Gerrit 的 commit message 中是否包含 ONES 工单号。  
> 如果不包含，需要通过**时间窗口 + 提交者 + 项目名**三要素模糊匹配。

### Phase 2：评测引擎

```python
# 新建 backend/accuracy_engine.py
class AccuracyEngine:
    """准确度评测引擎"""
    
    async def evaluate_ticket(self, ticket_id: str) -> EvalResult:
        """评测单个工单"""
        # 1. 从 DB 获取 AI 报告
        # 2. 从 Gerrit 获取开发者实际提交
        # 3. 五维度打分
        # 4. 存入 accuracy_evaluations
        
    async def batch_evaluate(self, limit: int = 100):
        """批量评测已完成工单"""
```

### Phase 3：API 与前端展示

- `GET /api/accuracy/summary` — 整体准确率统计
- `GET /api/accuracy/tickets` — 评测详情列表
- `POST /api/accuracy/evaluate/{ticket_id}` — 触发单条评测
- `POST /api/accuracy/batch` — 批量评测

---

## User Review Required

> [!IMPORTANT]
> **需要你提供以下信息才能开始实施：**

### 1. Gerrit 连接信息
- Gerrit 地址（有几个实例？config.py 预留了 3 个）
- 认证方式（HTTP Token / 用户名密码？）
- 账号密码/Token

### 2. Gerrit 与 ONES 的关联方式
- 开发者提交代码时，commit message 中是否会包含 ONES 工单号（如 `ONES-680889`）？
- 如果不包含，有什么其他关联方式？（如 Gerrit Topic、Branch 名称包含工单号？）

### 3. 评分阈值确认
- **≥ 40 分算"有效"** 这个标准是否合适？领导提到 5% 正确率，如果当前有效率低于 5%，是否需要调低阈值？
- "相近也算分" — 我的方案中维度三（方案相似度）给了 10-15 分档位来覆盖"相近"场景，是否足够？

### 4. 评测范围
- 是要评测所有历史工单（当前 495 个唯一工单），还是只评测新增的？
- 10,000 单目标是累计到什么时候？

---

## Open Questions

> [!CAUTION]
> **最大风险**：如果 Gerrit commit message 中不含 ONES 工单号，则无法自动关联。  
> 解决方案：人工标注 or 用 AI 模糊匹配（准确率会下降）。

1. **ones-AI 的 fix 模式是否有 git diff 输出？** — 即使平台没记录，ones-AI 脚本内部是否执行了 `git diff` 或 `git commit`？如果有，可以从执行日志中提取。
2. **评测成本**：LLM 辅助评分每条约消耗 1-2 次 API 调用。10,000 条 = 10,000-20,000 次调用，需要确认 API 预算。
3. **增量评测**：是否需要在每个工单完成后自动触发评测，还是定期批量跑？

---

## Verification Plan

### 自动化测试
- 用 10 条手动标注的工单做冒烟测试
- 验证 Gerrit API 连通性和搜索准确性
- 对比 LLM 评分与人工评分的一致性（取 20 条样本）

### 人工验证
- 随机抽取 50 条评测结果，由 2 位开发者独立评审
- 计算机器评分与人工评分的 Cohen's Kappa 一致性系数
- 目标：κ ≥ 0.6（中等以上一致性）
