# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 准确度评测引擎
@Version: 1.0.0
@Date: 2026-03-30

五维度评分体系（v2 优化版）：
  1. 文件定位准确度 (0-20)
  2. 根因定位 (0-20)
  3. 修复方案相似度 (0-25) — 含 LLM 语义对比
  4. 可操作性 (0-15)
  5. 整体一致性 (0-20)

总分 100 分，≥ 40 分视为"有效"（对开发有实质帮助）

评分等级映射:
  ≥ 75 分 → 完全一致 (10分/1分)
  40-74 分 → 思路相近 (7分/0.7分)
  < 40 分 → 无效 (0分)
"""

import asyncio
import json
import logging
import re
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from config import settings
from gerrit_client import GerritClient, GerritChange, GerritConfig, GERRIT_INSTANCES

logger = logging.getLogger("ones-ai.accuracy")


@dataclass
class EvalResult:
    """评测结果"""
    ticket_id: str = ""
    task_ticket_id: int = 0

    # Gerrit 数据
    gerrit_change_id: str = ""
    gerrit_change_url: str = ""
    gerrit_files: list = field(default_factory=list)
    gerrit_diff_summary: str = ""
    gerrit_commit_msg: str = ""

    # 五维度评分
    score_file_match: int = 0       # 文件定位 (0-20)
    score_root_cause: int = 0       # 根因定位 (0-20)
    score_fix_similar: int = 0      # 方案相似度 (0-25)
    score_actionable: int = 0       # 可操作性 (0-15)
    score_consistency: int = 0      # 整体一致性 (0-20)
    total_score: int = 0
    is_effective: bool = False      # ≥ 40 分

    # 评审理由
    reasoning: str = ""

    # 无法评测原因
    skip_reason: str = ""


# ======================================================
#  辅助函数：从文本中提取信息
# ======================================================

def extract_file_paths(text: str) -> set:
    """从报告文本中提取文件路径"""
    if not text:
        return set()

    patterns = [
        # 完整路径: /path/to/file.java
        r'(?:^|[\s`"\'])(/[\w/.-]+\.(?:java|c|cpp|h|xml|mk|py|kt|gradle|go|rs|sh|json|yaml|yml|properties))',
        # 相对路径: path/to/file.java
        r'(?:^|[\s`"\'])([\w][\w/.-]*\.(?:java|c|cpp|h|xml|mk|py|kt|gradle|go|rs|sh|json|yaml|yml|properties))',
        # markdown 代码引用中的文件
        r'`([^`]+\.(?:java|c|cpp|h|xml|mk|py|kt|gradle))`',
    ]

    files = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            path = match.group(1)
            # 只取文件名（去掉路径前缀以提高匹配率）
            basename = path.split("/")[-1]
            if basename and len(basename) > 2:
                files.add(basename)
    return files


def extract_diff_function_names(diff_text: str) -> set:
    """从 Gerrit diff 的 @@ 行提取函数名（更精准）"""
    if not diff_text:
        return set()
    # @@ -a,b +c,d @@ functionName  或  @@ -a,b +c,d @@ ReturnType functionName(
    funcs = set()
    for match in re.finditer(r'@@\s*-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@\s*(.+)', diff_text):
        ctx = match.group(1).strip()
        # 尝试提取最后一个 word( 形式
        fn_match = re.search(r'\b([a-zA-Z_]\w{2,})\s*\(', ctx)
        if fn_match:
            funcs.add(fn_match.group(1))
        elif ctx and not ctx.startswith('#') and not ctx.startswith('//'):
            # 可能是类名或宏
            words = re.findall(r'\b([a-zA-Z_]\w{3,})\b', ctx)
            funcs.update(words)
    return funcs


def extract_function_names(text: str) -> set:
    """从文本中提取函数/方法名"""
    if not text:
        return set()

    patterns = [
        # Java/Kotlin: methodName(
        r'\b([a-zA-Z_]\w{2,})\s*\(',
        # C/C++: function_name(
        r'\b([a-z_]\w{2,})\s*\(',
    ]

    funcs = set()
    # 排除常见关键词（扩充 Android/Java/C++ SDK 常见API）
    keywords = {
        # 语言关键字
        'if', 'else', 'for', 'while', 'switch', 'case', 'return', 'void',
        'int', 'string', 'boolean', 'class', 'public', 'private', 'static',
        'import', 'package', 'new', 'try', 'catch', 'throw', 'null', 'true',
        'false', 'this', 'super', 'final', 'abstract', 'extends', 'implements',
        'sizeof', 'typedef', 'struct', 'enum', 'const', 'include', 'define',
        'virtual', 'override', 'inline', 'extern', 'volatile', 'register',
        'namespace', 'template', 'typename', 'using', 'auto', 'break',
        'continue', 'default', 'goto', 'signed', 'unsigned', 'long', 'short',
        'float', 'double', 'char', 'bool', 'interface', 'protected',
        # 常见 API / 框架方法 — 不具备定位价值
        'Log', 'println', 'print', 'printf', 'fprintf', 'sprintf', 'snprintf',
        'System', 'String', 'Integer', 'Object', 'Arrays', 'Collections',
        'List', 'Map', 'Set', 'HashMap', 'ArrayList', 'HashSet',
        'IOException', 'Exception', 'RuntimeException', 'NullPointerException',
        'assertEquals', 'assertTrue', 'assertFalse', 'assertNotNull',
        'Intent', 'Bundle', 'Context', 'Activity', 'Fragment', 'View',
        'TextView', 'ImageView', 'Button', 'LinearLayout', 'RelativeLayout',
        'Toast', 'Dialog', 'AlertDialog', 'SharedPreferences', 'Handler',
        'Looper', 'Thread', 'Runnable', 'AsyncTask', 'LayoutInflater',
        'RecyclerView', 'Adapter', 'ViewHolder', 'ViewModel', 'LiveData',
        'Application', 'Service', 'BroadcastReceiver', 'ContentProvider',
        'Cursor', 'ContentValues', 'SQLiteDatabase', 'ContentResolver',
        'MotionEvent', 'KeyEvent', 'GestureDetector', 'Drawable', 'Canvas',
        'Paint', 'Bitmap', 'Matrix', 'Rect', 'Point', 'Color',
        'malloc', 'calloc', 'realloc', 'free', 'memset', 'memcpy', 'memmove',
        'strlen', 'strcmp', 'strcpy', 'strncpy', 'strcat', 'strncat',
        'fopen', 'fclose', 'fread', 'fwrite', 'fseek', 'ftell',
        'assert', 'exit', 'abort', 'signal', 'raise',
    }
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = match.group(1)
            if name not in keywords and not name.isupper() and len(name) > 2:
                funcs.add(name)
    return funcs


def extract_code_blocks(text: str) -> list:
    """从 markdown 报告中提取代码块"""
    if not text:
        return []
    blocks = re.findall(r'```[\w]*\n(.*?)```', text, re.DOTALL)
    return [b.strip() for b in blocks if len(b.strip()) > 20]


def count_actionable_keywords(text: str) -> int:
    """统计可操作性关键词"""
    if not text:
        return 0
    keywords = [
        '修改', '替换', '新增', '删除', '添加', '移除', '调整',
        '修复', '更改', '设置', '配置', '注释', '反注释',
        'modify', 'replace', 'add', 'remove', 'fix', 'change', 'update',
        '步骤', '方案', '建议', '实现',
    ]
    count = 0
    for kw in keywords:
        count += text.lower().count(kw.lower())
    return count


# ======================================================
#  维度评分函数
# ======================================================

def score_file_match(ai_files: set, gerrit_files: set) -> int:
    """维度一：文件定位准确度 (0-20)"""
    if not gerrit_files:
        return 0
    if not ai_files:
        return 0

    # 用文件名（不含路径）做匹配
    ai_basenames = {f.split("/")[-1] for f in ai_files}
    gerrit_basenames = {f.split("/")[-1] for f in gerrit_files}

    intersection = ai_basenames & gerrit_basenames
    if not intersection:
        # 尝试模糊匹配（文件名包含关系）
        fuzzy = 0
        for af in ai_basenames:
            for gf in gerrit_basenames:
                if af in gf or gf in af:
                    fuzzy += 1
        if fuzzy > 0:
            return 5  # 模糊命中
        return 0

    rate = len(intersection) / len(gerrit_basenames)
    if rate >= 0.8:
        return 20
    elif rate >= 0.5:
        return 15
    elif rate >= 0.3:
        return 10
    else:
        return 5


def score_root_cause(ai_funcs: set, gerrit_funcs: set, ai_files: set = None, gerrit_files: set = None) -> int:
    """维度二：根因定位 (0-20)
    优化：当 Gerrit diff 无函数名时，用文件覆盖率做降级评分
    """
    # 主评分：函数名匹配
    if gerrit_funcs and ai_funcs:
        intersection = ai_funcs & gerrit_funcs
        if intersection:
            rate = len(intersection) / len(gerrit_funcs)
            if rate >= 0.5:
                return 20
            elif rate >= 0.3:
                return 15
            elif rate >= 0.1:
                return 10
            else:
                return 5

    # 降级评分：Gerrit diff 无函数名（commit message 纯标题），用文件覆盖替代
    if not gerrit_funcs:
        if ai_files and gerrit_files:
            ai_basenames = {f.split('/')[-1] for f in ai_files}
            gerrit_basenames = {f.split('/')[-1] for f in gerrit_files}
            overlap = ai_basenames & gerrit_basenames
            if overlap:
                rate = len(overlap) / len(gerrit_basenames)
                if rate >= 0.6:
                    return 10  # 文件高覆盖 → 根因基本正确
                elif rate >= 0.3:
                    return 7
                else:
                    return 3
        # AI 有分析但 Gerrit 无函数信息，给最低基础分
        if ai_funcs:
            return 3
        return 0

    return 0


def score_actionable(report: str, conclusion: str, analysis: str) -> int:
    """维度四：可操作性 (0-15)"""
    full_text = f"{report}\n{conclusion}\n{analysis}"

    code_blocks = extract_code_blocks(full_text)
    action_count = count_actionable_keywords(full_text)
    text_len = len(full_text)

    score = 0

    # 有代码块 -> 有具体方案
    if len(code_blocks) >= 3:
        score += 8
    elif len(code_blocks) >= 1:
        score += 5
    elif code_blocks:
        score += 3

    # 可操作关键词
    if action_count >= 10:
        score += 4
    elif action_count >= 5:
        score += 3
    elif action_count >= 2:
        score += 2

    # 报告有一定长度（不是水内容）
    if text_len >= 2000:
        score += 3
    elif text_len >= 500:
        score += 2
    elif text_len >= 100:
        score += 1

    return min(score, 15)


# ======================================================
#  评测引擎主类
# ======================================================

class AccuracyEngine:
    """准确度评测引擎"""

    def __init__(self, pool, ai_api_key: str = "", ai_base_url: str = ""):
        self.pool = pool
        self.ai_api_key = ai_api_key
        self.ai_base_url = ai_base_url

    async def evaluate_ticket(self, task_ticket_id: int) -> EvalResult:
        """评测单个工单"""

        result = EvalResult(task_ticket_id=task_ticket_id)

        # 1. 从数据库获取 AI 报告
        async with self.pool.acquire() as conn:
            ticket = await conn.fetchrow("""
                SELECT id, ticket_id, result_report, result_conclusion,
                       result_analysis, result_summary, ticket_title, status
                FROM task_tickets WHERE id = $1
            """, task_ticket_id)

        if not ticket:
            result.skip_reason = "工单不存在"
            return result

        if ticket["status"] != "completed":
            result.skip_reason = f"工单状态: {ticket['status']}"
            return result

        result.ticket_id = ticket["ticket_id"]
        report = ticket["result_report"] or ""
        conclusion = ticket["result_conclusion"] or ""
        analysis = ticket["result_analysis"] or ""
        summary = ticket["result_summary"] or ""
        title = ticket["ticket_title"] or ""

        full_ai_text = f"{report}\n{conclusion}\n{analysis}\n{summary}"

        if len(full_ai_text.strip()) < 50:
            result.skip_reason = "AI 报告内容为空"
            return result

        # 2. 从 Gerrit 搜索关联提交
        gerrit_changes = await self._search_gerrit(ticket["ticket_id"])

        if not gerrit_changes:
            result.skip_reason = "Gerrit 中未找到关联提交"
            return result

        # 取第一条最相关的 change（subject 包含工单号的优先）
        best_change = self._pick_best_change(gerrit_changes, ticket["ticket_id"])
        result.gerrit_change_id = best_change.change_id
        result.gerrit_change_url = f"{GERRIT_INSTANCES[0].base_url}/#/c/{best_change.number}/"
        result.gerrit_files = list(best_change.files.keys())
        result.gerrit_commit_msg = best_change.commit_message or best_change.subject
        result.gerrit_diff_summary = f"+{best_change.insertions}/-{best_change.deletions}"

        # 3. 五维度打分

        # 维度一：文件定位
        ai_files = extract_file_paths(full_ai_text)
        gerrit_files_set = set(best_change.files.keys())
        result.score_file_match = score_file_match(ai_files, gerrit_files_set)

        # 维度二：根因定位（优化：先从 diff @@ 行提取精准函数名）
        ai_funcs = extract_function_names(full_ai_text)
        gerrit_funcs = set()
        if best_change.diff_content:
            # 优先从 @@ 行提取（最精准）
            gerrit_funcs = extract_diff_function_names(best_change.diff_content)
            # 补充从 diff 全文提取
            gerrit_funcs |= extract_function_names(best_change.diff_content)
        if not gerrit_funcs and best_change.commit_message:
            gerrit_funcs = extract_function_names(best_change.commit_message)
        result.score_root_cause = score_root_cause(
            ai_funcs, gerrit_funcs,
            ai_files=ai_files, gerrit_files=gerrit_files_set
        )

        # 维度三：方案相似度 — 先用基于规则的方法
        result.score_fix_similar = await self._score_fix_similarity(
            full_ai_text, best_change, title
        )

        # 维度四：可操作性
        result.score_actionable = score_actionable(report, conclusion, analysis)

        # 维度五：整体一致性 — 工单标题 vs AI 结论 vs Gerrit subject
        result.score_consistency = self._score_consistency(
            title, conclusion or summary, best_change.subject, full_ai_text
        )

        # 汇总
        result.total_score = (
            result.score_file_match +
            result.score_root_cause +
            result.score_fix_similar +
            result.score_actionable +
            result.score_consistency
        )
        result.is_effective = result.total_score >= 40

        result.reasoning = (
            f"文件定位={result.score_file_match}/20, "
            f"根因={result.score_root_cause}/20, "
            f"方案相似={result.score_fix_similar}/25, "
            f"可操作={result.score_actionable}/15, "
            f"一致性={result.score_consistency}/20 → "
            f"总分={result.total_score}/100 ({'有效' if result.is_effective else '无效'})"
        )

        return result

    async def _search_gerrit(self, ticket_id: str) -> list[GerritChange]:
        """在所有 Gerrit 实例中搜索"""
        all_changes = []
        for config in GERRIT_INSTANCES:
            client = GerritClient(config)
            try:
                changes = await client.search_by_ticket(ticket_id)
                all_changes.extend(changes)
            except Exception as e:
                logger.warning(f"{config.name} 搜索 {ticket_id} 失败: {e}")
            finally:
                await client.close()
        return all_changes

    def _pick_best_change(self, changes: list[GerritChange], ticket_id: str) -> GerritChange:
        """选择最相关的 Change"""
        num = re.sub(r"^ONES-", "", ticket_id)

        # 优先选 subject 直接包含工单号的
        for c in changes:
            if num in c.subject:
                return c

        # 优先选 MERGED 状态
        for c in changes:
            if c.status == "MERGED":
                return c

        return changes[0]

    async def _score_fix_similarity(self, ai_text: str, change: GerritChange, title: str) -> int:
        """维度三：修复方案相似度 (0-25) — 规则 + LLM 语义"""
        ai_code_blocks = extract_code_blocks(ai_text)
        gerrit_files = list(change.files.keys())

        # ---- 规则部分 (最高 10 分) ----
        rule_score = 0

        if ai_code_blocks:
            rule_score += 3  # 有代码建议基础分

            code_text = "\n".join(ai_code_blocks)
            # 代码提及 Gerrit 修改文件
            for gf in gerrit_files:
                basename = gf.split("/")[-1]
                if basename in code_text or basename in ai_text:
                    rule_score += 3
                    break

            # 函数名重叠
            ai_code_funcs = extract_function_names(code_text)
            gerrit_msg_funcs = extract_function_names(change.commit_message or change.subject)
            if ai_code_funcs & gerrit_msg_funcs:
                rule_score += 2

            # 增删方向一致
            if change.insertions > change.deletions:
                if any(kw in ai_text for kw in ["新增", "添加", "增加", "add", "insert"]):
                    rule_score += 2
            elif change.deletions > change.insertions:
                if any(kw in ai_text for kw in ["删除", "移除", "remove", "delete"]):
                    rule_score += 2
        else:
            if len(ai_text) > 500:
                rule_score += 2

        rule_score = min(rule_score, 10)

        # ---- LLM 语义对比部分 (最高 15 分) ----
        llm_score = await self._llm_compare_fix(ai_text, change, title)

        return min(rule_score + llm_score, 25)

    def _score_consistency(self, title: str, ai_conclusion: str, gerrit_subject: str, full_ai_text: str = "") -> int:
        """维度五：整体一致性 (0-20) — 优化版
        改进：无标题时用 AI 全文 vs Gerrit subject 对比
        改进：关键词提取更精准，排除更多停用词
        """
        if not ai_conclusion and not full_ai_text:
            return 0

        # 停用词
        stopwords_cn = {'一个', '这个', '那个', '进行', '通过', '可以', '需要', '已经',
                        '目前', '其中', '以及', '但是', '因为', '所以', '如果', '没有',
                        '问题', '文件', '代码', '修改', '分析', '建议', '修复', '方案',
                        '功能', '实现', '支持', '使用', '处理', '相关'}
        stopwords_en = {'the', 'and', 'for', 'with', 'from', 'this', 'that', 'have',
                        'has', 'not', 'but', 'are', 'was', 'were', 'been', 'will',
                        'can', 'should', 'would', 'could', 'also', 'may', 'into',
                        'when', 'where', 'which', 'there', 'their', 'about', 'each',
                        'make', 'like', 'than', 'then', 'more', 'some', 'other',
                        'file', 'code', 'change', 'add', 'fix', 'update', 'bug',
                        'new', 'set', 'get', 'use', 'null', 'void', 'int', 'return',
                        'string', 'class', 'public', 'private', 'static', 'import'}

        def extract_keywords(text: str) -> set:
            if not text:
                return set()
            # 中文词（3字以上更精准）
            cn_words = set(w for w in re.findall(r'[\u4e00-\u9fa5]{3,6}', text) if w not in stopwords_cn)
            # 补充2字关键词（技术术语）
            cn_words |= set(w for w in re.findall(r'[\u4e00-\u9fa5]{2}', text)
                          if w not in stopwords_cn and any(c in w for c in '异常崩溃死机重启闪退卡顿泄漏溢出越界空指黑屏花屏'))
            # 英文词
            en_words = set(w.lower() for w in re.findall(r'[a-zA-Z]{3,}', text)
                          if w.lower() not in stopwords_en)
            # 技术缩写（NPE, OOM, ANR 等）
            abbrevs = set(w for w in re.findall(r'\b[A-Z]{2,5}\b', text)
                        if w not in {'NULL', 'TRUE', 'FALSE', 'VOID', 'INT', 'TODO', 'NOTE', 'ONES', 'STORY', 'BUG'})
            return cn_words | en_words | abbrevs

        # 有标题时用标题，无标题时用 AI 报告全文（取前500字）
        ai_text_for_match = ai_conclusion
        if not title and full_ai_text:
            ai_text_for_match = full_ai_text[:500]

        title_kw = extract_keywords(title)
        gerrit_kw = extract_keywords(gerrit_subject)
        ai_kw = extract_keywords(ai_text_for_match)

        # AI 结论与工单标题的重叠
        overlap_title = 0
        if title_kw and ai_kw:
            overlap_title = len(title_kw & ai_kw) / max(len(title_kw), 1)

        # AI 结论/全文与 Gerrit subject 的重叠（核心改进）
        overlap_gerrit = 0
        if gerrit_kw and ai_kw:
            overlap_gerrit = len(gerrit_kw & ai_kw) / max(len(gerrit_kw), 1)

        best_overlap = max(overlap_title, overlap_gerrit)

        if best_overlap >= 0.4:
            return 20
        elif best_overlap >= 0.25:
            return 15
        elif best_overlap >= 0.12:
            return 10
        elif best_overlap > 0:
            return 5
        return 0

    async def _llm_compare_fix(self, ai_text: str, change: GerritChange, title: str) -> int:
        """用 LLM 对比 AI 报告与 Gerrit 实际修复的语义相似度 (0-15)"""
        # Qwen3-235B 配置
        LLM_BASE_URL = "http://115.190.54.79:8000/v1"
        LLM_API_KEY = "qingtianjia"
        LLM_MODEL = "Qwen3-235B-FP8"

        # 截断避免 token 爆掉
        ai_summary = ai_text[:2000]
        gerrit_info = f"""Gerrit Change: {change.subject}
Commit Message: {(change.commit_message or '')[:500]}
Modified Files: {', '.join(list(change.files.keys())[:10])}
Changes: +{change.insertions}/-{change.deletions}"""

        prompt = f"""你是代码审查专家。请对比以下两份内容，判断 AI 分析报告与开发者实际修复的相似程度。

## 工单标题
{title}

## AI 分析报告（摘要）
{ai_summary}

## 开发者实际修复（Gerrit 提交）
{gerrit_info}

请只回答一个 JSON，格式如下（不要其他内容）：
{{"score": 0-15, "level": "完全一致|思路相近|部分相关|无关", "reason": "一句话理由"}}

评分标准：
- 13-15: AI 建议的修复方案与实际提交语义高度一致（核心逻辑相同）
- 9-12: 修复方向正确，思路相同但细节不同
- 5-8: 有部分参考价值，分析了正确的问题域
- 1-4: 给出了分析但方向有偏差
- 0: 完全无关或无实质内容"""

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": LLM_MODEL,
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                }
                async with session.post(
                    f"{LLM_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning(f"LLM 评分请求失败: {resp.status} {body[:200]}")
                        return 0
                    data = await resp.json()

                # 解析返回
                content = ""
                if "content" in data and data["content"]:
                    content = data["content"][0].get("text", "")
                elif "choices" in data and data["choices"]:
                    content = data["choices"][0].get("message", {}).get("content", "")

                # 从返回中提取 JSON
                json_match = re.search(r'\{[^}]+\}', content)
                if json_match:
                    result = json.loads(json_match.group())
                    score = min(max(int(result.get("score", 0)), 0), 15)
                    reason = result.get("reason", "")
                    level = result.get("level", "")
                    logger.info(f"LLM 评分: {score}/15 [{level}] {reason}")
                    return score
                else:
                    logger.warning(f"LLM 返回格式异常: {content[:200]}")
                    return 0

        except asyncio.TimeoutError:
            logger.warning("LLM 评分超时")
            return 0
        except Exception as e:
            logger.warning(f"LLM 评分异常: {e}")
            return 0

    async def save_result(self, result: EvalResult):
        """保存评测结果到数据库（内部工单）"""
        async with self.pool.acquire() as conn:
            # 检查是否已存在（task_ticket_id 不再 UNIQUE，改用手动 upsert）
            existing = await conn.fetchval(
                "SELECT id FROM accuracy_evaluations WHERE task_ticket_id=$1 AND source='internal'",
                result.task_ticket_id
            )
            if existing:
                await conn.execute("""
                    UPDATE accuracy_evaluations SET
                        ticket_id=$1, gerrit_change_id=$2, gerrit_change_url=$3,
                        gerrit_files=$4, gerrit_diff_summary=$5, gerrit_commit_msg=$6,
                        score_file_match=$7, score_root_cause=$8, score_fix_similar=$9,
                        score_actionable=$10, score_consistency=$11, total_score=$12,
                        is_effective=$13, llm_reasoning=$14, skip_reason=$15, evaluated_at=NOW()
                    WHERE id=$16
                """,
                    result.ticket_id, result.gerrit_change_id, result.gerrit_change_url,
                    json.dumps(result.gerrit_files, ensure_ascii=False),
                    result.gerrit_diff_summary, result.gerrit_commit_msg,
                    result.score_file_match, result.score_root_cause,
                    result.score_fix_similar, result.score_actionable,
                    result.score_consistency, result.total_score,
                    result.is_effective, result.reasoning, result.skip_reason,
                    existing,
                )
            else:
                await conn.execute("""
                    INSERT INTO accuracy_evaluations (
                        task_ticket_id, ticket_id, source,
                        gerrit_change_id, gerrit_change_url, gerrit_files,
                        gerrit_diff_summary, gerrit_commit_msg,
                        score_file_match, score_root_cause, score_fix_similar,
                        score_actionable, score_consistency, total_score,
                        is_effective, llm_reasoning, skip_reason
                    ) VALUES ($1,$2,'internal',$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                """,
                    result.task_ticket_id, result.ticket_id,
                    result.gerrit_change_id, result.gerrit_change_url,
                    json.dumps(result.gerrit_files, ensure_ascii=False),
                    result.gerrit_diff_summary, result.gerrit_commit_msg,
                    result.score_file_match, result.score_root_cause,
                    result.score_fix_similar, result.score_actionable,
                    result.score_consistency, result.total_score,
                    result.is_effective, result.reasoning, result.skip_reason,
                )

    async def batch_evaluate(self, limit: int = 50) -> dict:
        """批量评测已完成但未评测的工单（内部 + 外部）[FR-302]"""
        async with self.pool.acquire() as conn:
            # 内部待评测
            rows = await conn.fetch("""
                SELECT tt.id FROM task_tickets tt
                LEFT JOIN accuracy_evaluations ae ON ae.task_ticket_id = tt.id AND ae.source = 'internal'
                WHERE tt.status = 'completed'
                  AND ae.id IS NULL
                  AND tt.result_report IS NOT NULL
                  AND tt.result_report != ''
                ORDER BY tt.id DESC
                LIMIT $1
            """, limit)

        total = len(rows)
        evaluated = 0
        effective = 0
        skipped = 0
        errors = 0

        for row in rows:
            try:
                result = await self.evaluate_ticket(row["id"])
                if result.skip_reason:
                    skipped += 1
                    logger.info(f"跳过 {result.ticket_id}: {result.skip_reason}")
                else:
                    evaluated += 1
                    if result.is_effective:
                        effective += 1
                    logger.info(f"评测 {result.ticket_id}: {result.total_score}分 ({'有效' if result.is_effective else '无效'})")
                await self.save_result(result)
            except Exception as e:
                errors += 1
                logger.error(f"评测 task_ticket#{row['id']} 异常: {e}")

        # [FR-302] 外部数据评测
        remaining = max(limit - total, 0)  # 外部名额 = 总配额 - 内部已用
        ext_evaluated, ext_effective, ext_skipped, ext_errors = await self._batch_evaluate_external(remaining)
        total += (ext_evaluated + ext_skipped + ext_errors)
        evaluated += ext_evaluated
        effective += ext_effective
        skipped += ext_skipped
        errors += ext_errors

        return {
            "total": total,
            "evaluated": evaluated,
            "effective": effective,
            "skipped": skipped,
            "errors": errors,
            "accuracy_rate": f"{effective / evaluated * 100:.1f}%" if evaluated > 0 else "N/A",
        }

    # ---- 外部数据评测 [FR-302] ----

    async def evaluate_external_log(self, log_id: int) -> EvalResult:
        """评测外部团队上报的日志（逻辑与 evaluate_ticket 一致）"""
        result = EvalResult()

        async with self.pool.acquire() as conn:
            log = await conn.fetchrow("SELECT * FROM external_logs WHERE id=$1", log_id)

        if not log:
            result.skip_reason = "外部日志不存在"
            return result

        ticket_id = log["ticket_id"] or ""
        if not ticket_id:
            result.skip_reason = "无工单号"
            return result

        ai_report = log["ai_report"] or ""
        summary = log["summary"] or ""
        full_ai_text = f"{ai_report}\n{summary}"

        if len(full_ai_text.strip()) < 50:
            result.skip_reason = "AI 报告内容为空"
            return result

        result.ticket_id = ticket_id

        # 从 Gerrit 搜索关联提交
        gerrit_changes = await self._search_gerrit(ticket_id)
        if not gerrit_changes:
            result.skip_reason = "Gerrit 中未找到关联提交"
            return result

        best_change = self._pick_best_change(gerrit_changes, ticket_id)
        result.gerrit_change_id = best_change.change_id
        result.gerrit_change_url = f"{GERRIT_INSTANCES[0].base_url}/#/c/{best_change.number}/"
        result.gerrit_files = list(best_change.files.keys())
        result.gerrit_commit_msg = best_change.commit_message or best_change.subject
        result.gerrit_diff_summary = f"+{best_change.insertions}/-{best_change.deletions}"

        # 五维度打分
        ai_files = extract_file_paths(full_ai_text)
        gerrit_files_set = set(best_change.files.keys())
        result.score_file_match = score_file_match(ai_files, gerrit_files_set)

        ai_funcs = extract_function_names(full_ai_text)
        gerrit_funcs = set()
        if best_change.diff_content:
            gerrit_funcs = extract_diff_function_names(best_change.diff_content)
            gerrit_funcs |= extract_function_names(best_change.diff_content)
        if not gerrit_funcs and best_change.commit_message:
            gerrit_funcs = extract_function_names(best_change.commit_message)
        result.score_root_cause = score_root_cause(
            ai_funcs, gerrit_funcs, ai_files=ai_files, gerrit_files=gerrit_files_set
        )

        result.score_fix_similar = await self._score_fix_similarity(
            full_ai_text, best_change, ticket_id
        )
        result.score_actionable = score_actionable(ai_report, "", "")
        result.score_consistency = self._score_consistency(
            ticket_id, summary, best_change.subject, full_ai_text
        )

        result.total_score = (
            result.score_file_match + result.score_root_cause +
            result.score_fix_similar + result.score_actionable +
            result.score_consistency
        )
        result.is_effective = result.total_score >= 40
        result.reasoning = (
            f"[外部] 文件={result.score_file_match}/20, "
            f"根因={result.score_root_cause}/20, "
            f"方案={result.score_fix_similar}/25, "
            f"可操作={result.score_actionable}/15, "
            f"一致性={result.score_consistency}/20 → "
            f"总分={result.total_score}/100 ({'有效' if result.is_effective else '无效'})"
        )
        return result

    async def save_external_result(self, result: EvalResult, log_id: int):
        """保存外部评测结果"""
        async with self.pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM accuracy_evaluations WHERE external_log_id=$1 AND source='external'",
                log_id
            )
            if existing:
                await conn.execute("""
                    UPDATE accuracy_evaluations SET
                        ticket_id=$1, gerrit_change_id=$2, gerrit_change_url=$3,
                        gerrit_files=$4, gerrit_diff_summary=$5, gerrit_commit_msg=$6,
                        score_file_match=$7, score_root_cause=$8, score_fix_similar=$9,
                        score_actionable=$10, score_consistency=$11, total_score=$12,
                        is_effective=$13, llm_reasoning=$14, skip_reason=$15, evaluated_at=NOW()
                    WHERE id=$16
                """,
                    result.ticket_id, result.gerrit_change_id, result.gerrit_change_url,
                    json.dumps(result.gerrit_files, ensure_ascii=False),
                    result.gerrit_diff_summary, result.gerrit_commit_msg,
                    result.score_file_match, result.score_root_cause,
                    result.score_fix_similar, result.score_actionable,
                    result.score_consistency, result.total_score,
                    result.is_effective, result.reasoning, result.skip_reason,
                    existing,
                )
            else:
                await conn.execute("""
                    INSERT INTO accuracy_evaluations (
                        task_ticket_id, ticket_id, source, external_log_id,
                        gerrit_change_id, gerrit_change_url, gerrit_files,
                        gerrit_diff_summary, gerrit_commit_msg,
                        score_file_match, score_root_cause, score_fix_similar,
                        score_actionable, score_consistency, total_score,
                        is_effective, llm_reasoning, skip_reason
                    ) VALUES (NULL,$1,'external',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                """,
                    result.ticket_id, log_id,
                    result.gerrit_change_id, result.gerrit_change_url,
                    json.dumps(result.gerrit_files, ensure_ascii=False),
                    result.gerrit_diff_summary, result.gerrit_commit_msg,
                    result.score_file_match, result.score_root_cause,
                    result.score_fix_similar, result.score_actionable,
                    result.score_consistency, result.total_score,
                    result.is_effective, result.reasoning, result.skip_reason,
                )

    async def _batch_evaluate_external(self, limit: int) -> tuple:
        """批量评测外部日志"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT el.id FROM external_logs el
                LEFT JOIN accuracy_evaluations ae ON ae.external_log_id = el.id AND ae.source = 'external'
                WHERE ae.id IS NULL
                  AND el.ai_report IS NOT NULL AND el.ai_report != ''
                  AND el.ticket_id IS NOT NULL AND el.ticket_id != ''
                ORDER BY el.reported_at DESC
                LIMIT $1
            """, limit)

        evaluated = 0
        effective = 0
        skipped = 0
        errors = 0

        for row in rows:
            try:
                result = await self.evaluate_external_log(row["id"])
                if result.skip_reason:
                    skipped += 1
                    logger.info(f"[外部] 跳过 log#{row['id']}: {result.skip_reason}")
                else:
                    evaluated += 1
                    if result.is_effective:
                        effective += 1
                    logger.info(f"[外部] 评测 {result.ticket_id}: {result.total_score}分")
                await self.save_external_result(result, row["id"])
            except Exception as e:
                errors += 1
                logger.error(f"[外部] 评测 log#{row['id']} 异常: {e}")

        return evaluated, effective, skipped, errors
