# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — 准确度评测引擎
@Version: 1.0.0
@Date: 2026-03-30

五维度评分体系：
  1. 文件定位准确度 (0-20)
  2. 根因定位 (0-20)
  3. 修复方案相似度 (0-25)
  4. 可操作性 (0-15)
  5. 整体一致性 (0-20)

总分 100 分，≥ 40 分视为"有效"（对开发有实质帮助）
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

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
    # 排除常见关键词
    keywords = {
        'if', 'else', 'for', 'while', 'switch', 'case', 'return', 'void',
        'int', 'string', 'boolean', 'class', 'public', 'private', 'static',
        'import', 'package', 'new', 'try', 'catch', 'throw', 'null', 'true',
        'false', 'this', 'super', 'final', 'abstract', 'extends', 'implements',
        'sizeof', 'typedef', 'struct', 'enum', 'const', 'include', 'define',
        'Log', 'println', 'print', 'printf', 'fprintf', 'sprintf',
    }
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            name = match.group(1)
            if name not in keywords and not name.isupper():
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


def score_root_cause(ai_funcs: set, gerrit_funcs: set) -> int:
    """维度二：根因定位 (0-20)"""
    if not gerrit_funcs:
        return 5  # Gerrit 无函数信息，给基础分
    if not ai_funcs:
        return 0

    intersection = ai_funcs & gerrit_funcs
    if intersection:
        rate = len(intersection) / len(gerrit_funcs)
        if rate >= 0.5:
            return 20
        elif rate >= 0.3:
            return 15
        else:
            return 10
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

        # 维度二：根因定位
        ai_funcs = extract_function_names(full_ai_text)
        # 从 Gerrit patch 获取函数名（如果有 diff）
        gerrit_funcs = set()
        if best_change.diff_content:
            gerrit_funcs = extract_function_names(best_change.diff_content)
        elif best_change.commit_message:
            gerrit_funcs = extract_function_names(best_change.commit_message)
        result.score_root_cause = score_root_cause(ai_funcs, gerrit_funcs)

        # 维度三：方案相似度 — 先用基于规则的方法
        result.score_fix_similar = await self._score_fix_similarity(
            full_ai_text, best_change, title
        )

        # 维度四：可操作性
        result.score_actionable = score_actionable(report, conclusion, analysis)

        # 维度五：整体一致性 — 工单标题 vs AI 结论 vs Gerrit subject
        result.score_consistency = self._score_consistency(
            title, conclusion or summary, best_change.subject
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
        """维度三：修复方案相似度 (0-25) — 基于规则"""
        ai_code_blocks = extract_code_blocks(ai_text)
        gerrit_files = list(change.files.keys())

        score = 0

        # 有代码建议
        if ai_code_blocks:
            score += 10

            # 代码中是否提及了 Gerrit 修改的文件
            code_text = "\n".join(ai_code_blocks)
            for gf in gerrit_files:
                basename = gf.split("/")[-1]
                if basename in code_text or basename in ai_text:
                    score += 5
                    break

            # 代码中是否提及了类似的函数/变量
            ai_code_funcs = extract_function_names(code_text)
            gerrit_msg_funcs = extract_function_names(change.commit_message or change.subject)
            if ai_code_funcs & gerrit_msg_funcs:
                score += 5

            # 修改方向一致性（增/删）
            if change.insertions > change.deletions:
                if any(kw in ai_text for kw in ["新增", "添加", "增加", "add", "insert"]):
                    score += 5
            elif change.deletions > change.insertions:
                if any(kw in ai_text for kw in ["删除", "移除", "remove", "delete"]):
                    score += 5
        else:
            # 没有代码块但有分析
            if len(ai_text) > 500:
                score += 5

        return min(score, 25)

    def _score_consistency(self, title: str, ai_conclusion: str, gerrit_subject: str) -> int:
        """维度五：整体一致性 (0-20) — 基于关键词重叠"""
        if not title and not gerrit_subject:
            return 5

        # 提取中文和英文关键词
        def extract_keywords(text: str) -> set:
            if not text:
                return set()
            # 中文词（2字以上）
            cn_words = set(re.findall(r'[\u4e00-\u9fa5]{2,4}', text))
            # 英文词（3字符以上）
            en_words = set(w.lower() for w in re.findall(r'[a-zA-Z]{3,}', text) 
                          if w.lower() not in {'the', 'and', 'for', 'with', 'from', 'this', 'that'})
            return cn_words | en_words

        title_kw = extract_keywords(title)
        gerrit_kw = extract_keywords(gerrit_subject)
        ai_kw = extract_keywords(ai_conclusion)

        # AI 结论与工单标题的重叠
        if title_kw and ai_kw:
            overlap_title = len(title_kw & ai_kw) / max(len(title_kw), 1)
        else:
            overlap_title = 0

        # AI 结论与 Gerrit subject 的重叠
        if gerrit_kw and ai_kw:
            overlap_gerrit = len(gerrit_kw & ai_kw) / max(len(gerrit_kw), 1)
        else:
            overlap_gerrit = 0

        best_overlap = max(overlap_title, overlap_gerrit)

        if best_overlap >= 0.5:
            return 20
        elif best_overlap >= 0.3:
            return 15
        elif best_overlap >= 0.15:
            return 10
        elif best_overlap > 0:
            return 5
        return 0

    async def save_result(self, result: EvalResult):
        """保存评测结果到数据库"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO accuracy_evaluations (
                    task_ticket_id, ticket_id,
                    gerrit_change_id, gerrit_change_url, gerrit_files,
                    gerrit_diff_summary, gerrit_commit_msg,
                    score_file_match, score_root_cause, score_fix_similar,
                    score_actionable, score_consistency, total_score,
                    is_effective, llm_reasoning, skip_reason
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                ON CONFLICT (task_ticket_id) DO UPDATE SET
                    gerrit_change_id=EXCLUDED.gerrit_change_id,
                    gerrit_change_url=EXCLUDED.gerrit_change_url,
                    gerrit_files=EXCLUDED.gerrit_files,
                    gerrit_diff_summary=EXCLUDED.gerrit_diff_summary,
                    gerrit_commit_msg=EXCLUDED.gerrit_commit_msg,
                    score_file_match=EXCLUDED.score_file_match,
                    score_root_cause=EXCLUDED.score_root_cause,
                    score_fix_similar=EXCLUDED.score_fix_similar,
                    score_actionable=EXCLUDED.score_actionable,
                    score_consistency=EXCLUDED.score_consistency,
                    total_score=EXCLUDED.total_score,
                    is_effective=EXCLUDED.is_effective,
                    llm_reasoning=EXCLUDED.llm_reasoning,
                    skip_reason=EXCLUDED.skip_reason,
                    evaluated_at=NOW()
            """,
                result.task_ticket_id, result.ticket_id,
                result.gerrit_change_id, result.gerrit_change_url,
                json.dumps(result.gerrit_files, ensure_ascii=False),
                result.gerrit_diff_summary, result.gerrit_commit_msg,
                result.score_file_match, result.score_root_cause,
                result.score_fix_similar, result.score_actionable,
                result.score_consistency, result.total_score,
                result.is_effective, result.reasoning,
                result.skip_reason,
            )

    async def batch_evaluate(self, limit: int = 50) -> dict:
        """批量评测已完成但未评测的工单"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tt.id FROM task_tickets tt
                LEFT JOIN accuracy_evaluations ae ON ae.task_ticket_id = tt.id
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

        return {
            "total": total,
            "evaluated": evaluated,
            "effective": effective,
            "skipped": skipped,
            "errors": errors,
            "accuracy_rate": f"{effective / evaluated * 100:.1f}%" if evaluated > 0 else "N/A",
        }
