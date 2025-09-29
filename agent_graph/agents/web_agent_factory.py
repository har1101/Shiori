from strands import Agent, tool
from strands.tools.mcp import MCPClient
import logging
from boto3.session import Session
import os
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from agents.config.gateway_identity_config import _get_tool_name
from agents.config.mcp_config import MCPConfig
from ..data_access import dsql_client

logger = logging.getLogger("web_search_agent")
logger.setLevel(logging.INFO)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

boto_session = Session()
region = boto_session.region_name

# システムプロンプトを定義
ACTIVITY_SEARCH_SYSTEM_PROMPT = """
あなたは活動内容分析アシスタントです。
提供されたURLから以下の情報を抽出してください：

1. 活動の種類判定:
    - event_presentation: 登壇・発表
    - article: ブログ記事・技術記事
    - study_group: 勉強会開催
    - other: その他

2. connpassのURLの場合、connpass_search_toolまたはextract_connpass_from_urlを使用し以下の内容を抽出
    - イベント名
    - 開催日時
    - 参加者数

3. その他のURLの場合、Firecrawlツールで以下の内容を抽出
    - タイトル
    - 投稿日
    - いいね数/参加者数
    - 本文の内容

4. 取得した技術ブログ・登壇資料の内容がAWSに関するものであった場合、以下4つのレベルのいずれかに判定してください。
    - Level 100: AWSサービスの概要を解説するレベル
      基本的な概念や用語の説明、サービスの紹介など
    - Level 200: 入門知識を前提に、ベストプラクティスやサービス機能を解説するレベル
      基本的な実装方法、標準的な使用パターンなど
    - Level 300: 対象トピックの詳細を解説するレベル
      高度な機能、パフォーマンス最適化、複雑な設定など
    - Level 400: 複数サービス・アーキテクチャによる実装を解説するレベル
      大規模システム設計、複雑な統合パターン、エンタープライズレベルの実装など

    判定時は以下の観点を考慮してください：
    - 使用されているAWSサービスの数と複雑さ
    - 技術的な深さと詳細度
    - 前提知識のレベル
    - 実装の規模と複雑さ
"""


# ToolUseを確認せず実行できるようにする
# https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/community-tools-package/
# os.environ["BYPASS_TOOL_CONSENT"] = "true"

# ==== Firecrawl Agent Factory ======================================================
class FirecrawlAgentFactory(MCPConfig):
    """
    Firecrawl（web検索/クロール/抽出）用の Agent を、“今開いている” Firecrawl MCPセッションから構築。
    呼び出し側で必ず `with firecrawl_mcp:` の中で build() を呼ぶこと。
    """
    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.system_prompt = ACTIVITY_SEARCH_SYSTEM_PROMPT

        if not self.system_prompt:
            raise ValueError("Web検索エージェント用システムプロンプトが必要です")

    def build(self, mcp_client: MCPClient) -> Agent:
        # ★ with mcp_client: の内側で呼ぶこと
        firecrawl_tools = list(mcp_client.list_tools_sync())

        # EN: Expose Aurora DSQL persistence tool to the web agent alongside MCP-provided tools.
        # JA: MCP提供ツールに加え、Aurora DSQL保存ツールをWebエージェントへ提供する。
        combined_tools = [*firecrawl_tools, aurora_dsql_activity_tool]

        # 以下は複数MCPを登録した中からfirecrawlだけを抽出する処理
        # all_tools = mcp_client.list_tools_sync()
        # firecrawl / extract / crawl / search などを優先
        # firecrawl_tools = [t for t in all_tools if any(k in getattr(t, "tool_name", getattr(t, "name", "")).lower()
        #                                           for k in ("firecrawl", "extract", "crawl", "search"))] or all_tools

        agent = Agent(
            name="FirecrawlAgent",
            tools=combined_tools,
            model=self.model_id,
            system_prompt=self.system_prompt,
        )

        # ログ（任意）
        try:
            base_tool_names = [_get_tool_name(t) for t in firecrawl_tools]
        except Exception:
            base_tool_names = [str(t) for t in firecrawl_tools]

        try:
            dsql_tool_name = _get_tool_name(aurora_dsql_activity_tool)
        except Exception:
            dsql_tool_name = str(aurora_dsql_activity_tool)

        tool_names = [*base_tool_names, dsql_tool_name]
        logger.info(f"FirecrawlAgent 構築: ツール数={len(firecrawl_tools)} -> {tool_names}")

        return agent

    async def stream(self, agent: Agent, prompt: str):
        # ★ with mcp_client: の内側で呼ぶこと
        async for ev in agent.stream_async(prompt):
            if ev is not None:
                yield ev
# EN: Normalize supported date formats for Aurora DSQL operations.
# JA: Aurora DSQL操作で利用する日付文字列を正規化する。
def _normalize_activity_date(raw_date: Any) -> date:
    """EN: Convert various date inputs into a timezone-agnostic date.

    JA: さまざまな形式の日付入力をタイムゾーン非依存の日付型へ変換します。
    """
    if isinstance(raw_date, date):
        return raw_date

    if isinstance(raw_date, datetime):
        return raw_date.date()

    if isinstance(raw_date, str):
        candidates = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
        stripped = raw_date.strip()
        for fmt in candidates:
            try:
                return datetime.strptime(stripped, fmt).date()
            except ValueError:
                continue

        try:
            iso_candidate = stripped[:-1] + "+00:00" if stripped.endswith("Z") else stripped
            cleaned_iso = iso_candidate.replace("/", "-")
            return datetime.fromisoformat(cleaned_iso).date()
        except ValueError as exc:
            raise ValueError(
                "Unsupported date string format; use ISO-8601 (YYYY-MM-DD). / ISO-8601形式(YYYY-MM-DD)で日付を指定してください"
            ) from exc

    raise ValueError(
        "Unsupported date value; provide a date, datetime, or ISO string. / date, datetime, または ISO形式文字列を指定してください"
    )


@tool(name="aurora_dsql_activity_tool", description=(
    "Store structured activity data in Aurora DSQL with IAM token auth. "
    "構造化された活動データをIAMトークン認証でAurora DSQLへ保存するツール"
))
def aurora_dsql_activity_tool(
    member: Dict[str, Any],
    activity: Dict[str, Any],
    track_processing: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """EN: Persist activity metadata to Aurora DSQL using application role credentials.

    JA: アプリケーションロール認証を利用して活動メタデータをAurora DSQLへ保存します。

    Parameters
    ----------
    member: Dict[str, Any]
        EN: Identity dictionary with at least ``email`` and ``name``.
        JA: ``email`` と ``name`` を含むメンバー情報の辞書。
    activity: Dict[str, Any]
        EN: Activity payload containing ``title`` and ``activity_date`` plus optional metadata (type, description, URLs, AWS info).
        JA: ``title`` と ``activity_date`` を必須とし、種別や説明、URL、AWS関連情報を含められる活動データ。
    track_processing: Optional[Dict[str, Any]]
        EN: Optional processing log payload with ``process_type`` / ``status`` / ``details`` to record to ``processing_history``.
        JA: ``process_type``・``status``・``details`` などを含め処理履歴へ記録する任意の情報。

    Returns
    -------
    Dict[str, Any]
        EN: Result map containing persistence status, identifiers, and optional processing log outcome.
        JA: 保存ステータスや識別子、処理履歴の結果を含む辞書を返します。
    """

    if not isinstance(member, dict):
        raise ValueError("member must be a dictionary / member引数は辞書で指定してください")

    if not isinstance(activity, dict):
        raise ValueError("activity must be a dictionary / activity引数は辞書で指定してください")

    email = (member.get("email") or "").strip()
    name = (member.get("name") or "").strip()

    if not email or not name:
        raise ValueError(
            "member.email and member.name are required / member.email と member.name は必須です"
        )

    github_username = member.get("github_username")

    logger.info("aurora_dsql_activity_tool: resolving member profile")
    member_id = dsql_client.get_or_create_member(
        email=email,
        name=name,
        github_username=github_username
    )

    raw_date = (
        activity.get("activity_date")
        or activity.get("date")
        or activity.get("activityDate")
    )
    if raw_date is None:
        raise ValueError(
            "activity.activity_date is required / activity.activity_date は必須です"
        )

    activity_date = _normalize_activity_date(raw_date)

    title = (activity.get("title") or "").strip()
    if not title:
        raise ValueError("activity.title is required / activity.title は必須です")

    activity_type = activity.get("activity_type") or activity.get("type") or "article"
    description = activity.get("description") or activity.get("summary")
    blog_url = activity.get("blog_url") or activity.get("article_url") or activity.get("url")
    github_repo_url = activity.get("github_repo_url") or activity.get("repository_url")

    aws_services: Optional[List[str]] = None
    if "aws_services" in activity:
        raw_services = activity.get("aws_services")
        if isinstance(raw_services, list):
            aws_services = [str(item).strip() for item in raw_services if str(item).strip()]
        elif isinstance(raw_services, str):
            aws_services = [part.strip() for part in raw_services.split(",") if part.strip()]

    aws_level = activity.get("aws_level") or activity.get("awsLevel")

    tags: Optional[List[str]] = None
    if "tags" in activity:
        raw_tags = activity.get("tags")
        if isinstance(raw_tags, list):
            tags = [str(item).strip() for item in raw_tags if str(item).strip()]
        elif isinstance(raw_tags, str):
            tags = [part.strip() for part in raw_tags.split(",") if part.strip()]

    summary_by_ai = activity.get("summary_by_ai") or activity.get("summaryByAi")

    logger.info("aurora_dsql_activity_tool: storing activity payload")
    storage_result = dsql_client.store_activity(
        member_id=member_id,
        activity_date=activity_date,
        activity_type=str(activity_type),
        title=title,
        description=description,
        blog_url=blog_url,
        github_repo_url=github_repo_url,
        aws_services=aws_services,
        aws_level=aws_level,
        tags=tags,
        summary_by_ai=summary_by_ai,
    )

    processing_result: Optional[Dict[str, Any]] = None
    if track_processing:
        process_type = track_processing.get("process_type") or track_processing.get("type")
        status = track_processing.get("status") or "success"
        details = track_processing.get("details")
        error_message = track_processing.get("error_message")

        if process_type:
            logger.info("aurora_dsql_activity_tool: recording processing history")
            processing_result = dsql_client.record_processing(
                process_type=str(process_type),
                status=str(status),
                details=details,
                error_message=error_message,
            )

    return {
        "status": storage_result.get("status"),
        "activity_id": storage_result.get("activity_id"),
        "member_id": member_id,
        "processing": processing_result,
    }
