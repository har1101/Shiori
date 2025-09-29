# Jr.Champions活動記録システム 設計書

## 1. システム概要

### 1.1 目的

Jr.Championsの活動を自動的に収集・分析・可視化し、コミュニティへの貢献度を定量的に評価することで、活動の意義を明確にし、今後の活動継続を支援する。

### 1.2 主要機能

- Slackからの活動情報自動収集
- 活動内容の分析と分類
- AWSレベル判定による技術レベル評価
- 月次レポート自動生成
- カレンダー形式での活動表示

### 1.3 ステークホルダー

- Jr.Championsメンバー（活動登録・参照）
- AWS担当者（活動集計・報告）
- コミュニティ（活動成果の確認）

## 2. システムアーキテクチャ

### 2.1 全体構成

```text
┌─────────────────┐
│   Slack         │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│           Bedrock AgentCore Runtime             │
│                                                 │
│  ┌───────────────────────────────────────┐     │
│  │      Strands Agents Graph             │     │
│  │                                       │     │
│  │  1. Slack検索エージェント             │     │
│  │     └─> Slack MCP (via Gateway)      │     │
│  │                                       │     │
│  │  2. 活動内容検索エージェント          │     │
│  │     ├─> Firecrawl MCP (via Gateway)     │     │
│  │     └─> connpass APIツール           │     │
│  │                                       │     │
│  │  3. AWSレベル判定エージェント         │     │
│  │     ├─> AWS Knowledge MCP            │     │
│  │     └─> AWS API MCP                  │     │
│  │                                       │     │
│  │  4. データ格納ツール                  │     │
│  │  5. 通知送信ツール                    │     │
│  └───────────────────────────────────────┘     │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Aurora DSQL    │     │   React App     │
│  (データ保存)    │◀────│  (可視化UI)      │
└─────────────────┘     └─────────────────┘
```

### 2.2 技術スタック

- **バックエンド**: Amazon Bedrock AgentCore + Strands Agents SDK
- **データベース**: Amazon Aurora DSQL (PostgreSQL互換)
- **フロントエンド**: React + Vite
- **認証**: Amazon Cognito
- **インフラ**: Terraform
- **CI/CD**: GitHub Actions

## 3. エージェント設計

### 3.1 Agent Graph構成

#### 3.1.1 Slack検索エージェント

**役割**: Slackメッセージから活動情報を検索・抽出

**システムプロンプト**:

```text
あなたはSlack統合アシスタントです。
Jr.Championsの活動チャンネルから、メンバーのアウトプット（ブログ、登壇、勉強会など）に関する投稿を抽出します。
URLが含まれるメッセージを重点的に取得し、活動の種類を判定してください。
```

**使用ツール**:

- Slack MCP (AgentCore Gateway経由)
  - 認証: AgentCore Identityで管理されたSlack Token

**処理内容**:

1. 指定チャンネル（環境変数: `SLACK_CHANNEL_ID`）から投稿取得
2. URLを含むメッセージの抽出
3. 投稿者情報とタイムスタンプの記録

#### 3.1.2 活動内容検索エージェント

**役割**: URLから詳細情報を取得・分析

**システムプロンプト**:

```text
あなたは活動内容分析アシスタントです。
提供されたURLから以下の情報を抽出してください：
1. 活動の種類（ブログ記事、登壇資料、勉強会開催など）
2. タイトルと概要
3. 技術キーワード
4. 参加者数やいいね数（取得可能な場合）
```

**使用ツール**:

- Firecrawl MCP (URL内容抽出)
- connpass APIツール（カスタム実装）

**connpass APIツール実装**:

```python
@tool
def connpass_search_tool(event_name: str, ymd: str = None) -> dict:
    """
    connpass APIを使用してイベント情報を取得
    
    Args:
        event_name: イベント名（部分一致検索）
        ymd: イベント開催日（YYYYMMDD形式、オプション）
    
    Returns:
        イベント詳細情報（title, started_at, accepted, place等）
    """
    base_url = "https://connpass.com/api/v2/events/"
    headers = {"X-API-Key": os.environ["CONNPASS_API_KEY"]}
    params = {"keyword": event_name, "count": 10}
    if ymd:
        params["ymd"] = ymd
    
    response = requests.get(base_url, headers=headers, params=params)
    # 結果の解析と返却
    return parse_connpass_response(response.json())
```

#### 3.1.3 AWSレベル判定エージェント

**役割**: AWS技術コンテンツのレベル判定

**システムプロンプト**:

```text
あなたはAWS技術レベル判定アシスタントです。
提供されたコンテンツを分析し、以下の4つのレベルのいずれかに判定してください：

- Level 100: AWSサービスの概要を解説するレベル
  基本的な概念や用語の説明、サービスの紹介など

- Level 200: 入門知識を前提に、ベストプラクティスやサービス機能を解説するレベル
  基本的な実装方法、標準的な使用パターンなど

- Level 300: 対象トピックの詳細を解説するレベル
  高度な機能、パフォーマンス最適化、複雑な設定など

- Level 400: 複数サービス・アーキテクチャによる実装を解説するレベル
  大規模システム設計、複雑な統合パターン、エンタープライズレベルの実装など

判定時は以下の観点を考慮してください：
1. 使用されているAWSサービスの数と複雑さ
2. 技術的な深さと詳細度
3. 前提知識のレベル
4. 実装の規模と複雑さ

出力形式：
レベル: [100/200/300/400]
判定理由: [詳細な判定理由]
```

**使用ツール**:

- AWS Knowledge MCP (AWSドキュメント参照)
- AWS API MCP (サービス情報取得)

### 3.2 ツールノード

#### 3.2.1 データ格納ツール (PutDataTool)

**役割**: Aurora DSQLへのデータ保存

**処理内容**:

1. 活動情報の整形
2. 重複チェック（slack_message_id）
3. データベースへの保存
4. ProcessingHistoryの更新

#### 3.2.2 通知送信ツール (SendResultTool)

**役割**: 処理完了通知

**処理内容**:

1. 処理結果のサマリー生成
2. Amazon SNS経由での通知送信
3. エラー発生時のアラート

### 3.3 Agent Graph実行フロー

```python
# 実行順序（オーケストレーション）
1. Slack検索エージェント
   ↓
2. 活動内容検索エージェント
   ↓
3. AWSレベル判定エージェント
   ↓
4. データ格納ツール
   ↓
5. 通知送信ツール
```

## 4. データモデル設計

### 4.1 テーブル構成

#### 4.1.1 members（メンバー）

```sql
CREATE TABLE members (
    member_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    slack_user_id VARCHAR(50) UNIQUE,
    github_username VARCHAR(100),  -- 将来の拡張用
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

#### 4.1.2 activities（活動）

```sql
CREATE TABLE activities (
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id UUID NOT NULL,
    activity_type VARCHAR(20) NOT NULL CHECK (
        activity_type IN ('event_presentation', 'article', 'study_group', 'other')
    ),
    title VARCHAR(255) NOT NULL,
    description TEXT,  -- 100-200文字の要約
    summary_by_ai TEXT,  -- AI生成の詳細要約
    activity_date DATE NOT NULL,
    event_name VARCHAR(255),
    participant_count INTEGER,
    like_count INTEGER,
    resource_url TEXT,
    aws_level VARCHAR(10) CHECK (aws_level IN ('100', '200', '300', '400')),
    tags JSONB,  -- 技術タグ（例: {"tags": ["EC2", "Lambda", "DynamoDB"]}）
    slack_message_id VARCHAR(100) UNIQUE,
    slack_channel_id VARCHAR(50),
    slack_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_activities_member 
        FOREIGN KEY (member_id) 
        REFERENCES members(member_id) 
        ON DELETE CASCADE
);
```

#### 4.1.3 monthly_reports（月次レポート）

```sql
CREATE TABLE monthly_reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    total_activities INTEGER NOT NULL DEFAULT 0,
    activities_by_type JSONB NOT NULL DEFAULT '{}',
    total_participants INTEGER DEFAULT 0,
    total_likes INTEGER DEFAULT 0,
    feedback_content TEXT,  -- Markdown形式
    community_contribution TEXT,  -- Markdown形式
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_year_month UNIQUE (year, month)
);
```

#### 4.1.4 processing_history（処理履歴）

```sql
CREATE TABLE processing_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_type VARCHAR(20) NOT NULL CHECK (
        process_type IN ('slack_fetch', 'report_generation')
    ),
    last_processed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_slack_timestamp TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'failed')),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 インデックス設計

```sql
-- 検索パフォーマンス最適化
CREATE INDEX idx_activities_member_id ON activities(member_id);
CREATE INDEX idx_activities_activity_date ON activities(activity_date DESC);
CREATE INDEX idx_activities_activity_type ON activities(activity_type);
CREATE INDEX idx_activities_date_type ON activities(activity_date, activity_type);
CREATE INDEX idx_activities_aws_level ON activities(aws_level);
CREATE INDEX idx_activities_tags ON activities USING gin(tags);
```

## 5. API仕様

### 5.1 内部API（エージェント間通信）

#### 5.1.1 Slack検索API

```python
def search_slack_messages(channel_id: str, since: datetime) -> List[Message]:
    """
    指定チャンネルからメッセージを取得
    
    Args:
        channel_id: SlackチャンネルID
        since: この日時以降のメッセージを取得
    
    Returns:
        メッセージリスト（URL含むもののみ）
    """
```

#### 5.1.2 活動情報抽出API

```python
def extract_activity_info(url: str) -> ActivityInfo:
    """
    URLから活動情報を抽出
    
    Args:
        url: 活動のURL
    
    Returns:
        ActivityInfo: タイトル、概要、参加者数等
    """
```

### 5.2 外部API（フロントエンド用）

#### 5.2.1 活動一覧取得

```sql
GET /api/v1/activities
Query Parameters:
  - member_id: メンバーID（オプション）
  - start_date: 開始日（YYYY-MM-DD）
  - end_date: 終了日（YYYY-MM-DD）
  - activity_type: 活動種別
  - aws_level: AWSレベル（100/200/300/400）
  - limit: 取得件数（デフォルト: 20）
  - offset: オフセット
```

#### 5.2.2 月次レポート取得

```sql
GET /api/v1/reports/{year}/{month}
Response:
  - report_id: レポートID
  - year: 年
  - month: 月
  - statistics: 統計情報
  - feedback: フィードバック内容
```

## 6. セキュリティ設計

### 6.1 認証・認可

- **ユーザー認証**: Amazon Cognito
- **API認証**: JWT トークン
- **エージェント認証**: AgentCore Identity

### 6.2 シークレット管理

```yaml
AgentCore Identity管理:
  - Slack Token
  - Firecrawl API Key
  - connpass API Key

AWS Secrets Manager管理:
  - DB接続情報
  - Cognito設定
```

### 6.3 アクセス制御

- Jr.Championsメンバーのメールアドレスホワイトリスト
- IAMロール最小権限原則
- VPCエンドポイント経由のアクセス（該当する場合）

## 7. 環境設定

### 7.1 環境変数

```bash
# Slack設定
SLACK_CHANNEL_ID=<対象チャンネルID>

# AgentCore設定
GATEWAY_URL=<AgentCore Gateway URL>
COGNITO_SCOPE=<OAuth2スコープ>
WORKLOAD_NAME=jr-champions-agent
USER_ID=jc-agent-001

# API Keys (AgentCore Identity管理)
Firecrawl_API_KEY=<Firecrawl APIキー>
CONNPASS_API_KEY=<connpass APIキー>

# Database設定
DB_HOST=<Aurora DSQLエンドポイント>
DB_NAME=jr_champions_activities
DB_USER=<データベースユーザー>
DB_PASSWORD=<データベースパスワード> # Secrets Manager経由

# AWS設定
AWS_REGION=us-east-1  # AgentCore対応まで
AWS_ACCOUNT_ID=<AWSアカウントID>

# 実行設定
INITIAL_FETCH_DATE=2025-07-01
DAILY_EXECUTION_TIME=07:00
MONTHLY_REPORT_TIME=06:00
```

### 7.2 リージョン設定

- **現在**: us-east-1（バージニア北部）- AgentCore対応リージョン
- **将来**: ap-northeast-1（東京）- AgentCore対応後に移行

## 8. 実装フェーズ

### Phase 1: 基盤構築（1週間）

- [◯] Aurora DSQLクラスター作成
- [◯] テーブル作成（追加カラム含む）
- [◯] Terraformテンプレート作成
- [◯] 基本的なデータアクセス層実装

### Phase 2: エージェント基本実装（2週間）
n

- [◯] Slack検索エージェント実装
- [◯] Firecrawl検索エージェント実装
- [ ] AgentCore Gateway設定
- [ ] ProcessingHistoryによる重複制御
- [ ] Agent Graph基本構築

### Phase 3: 活動内容取得機能（1週間）

- [ ] Firecrawl MCP統合
- [ ] connpass APIツール実装
- [ ] URL情報抽出ロジック
- [ ] データ整形処理

### Phase 4: AWSレベル判定（1週間）

- [ ] AWSレベル判定エージェント実装
- [ ] AWS Knowledge/API MCP統合
- [ ] 判定ロジックの調整
- [ ] 判定結果のDB保存

### Phase 5: フロントエンド開発（2週間）

- [ ] React+Viteプロジェクト作成
- [ ] カレンダーコンポーネント実装
- [ ] 活動詳細表示機能
- [ ] 月次レポート表示
- [ ] レスポンシブデザイン対応

### Phase 6: 統合・テスト（1週間）

- [ ] エンドツーエンドテスト
- [ ] パフォーマンステスト
- [ ] セキュリティ監査
- [ ] ドキュメント整備

## 9. 運用・監視

### 9.1 監視項目

- **エージェント実行状況**: CloudWatch Logs
- **エラー率**: CloudWatch Metrics
- **処理時間**: X-Ray トレーシング
- **DB性能**: Aurora メトリクス

### 9.2 アラート設定

```yaml
アラート条件:
  - エージェント実行失敗: 2回連続失敗
  - API応答時間: 3秒以上
  - DB接続エラー: 発生時即座
  - 月次レポート生成失敗: 発生時即座

通知先:
  - Amazon SNS → メール通知
  - Slack通知（エラーチャンネル）
```

### 9.3 バックアップ

- **Aurora DSQL**: 自動バックアップ（日次）
- **設定ファイル**: Git管理
- **シークレット**: Secrets Managerバージョニング

## 10. 拡張性の考慮

### 10.1 将来の機能拡張

- GitHub連携によるコード貢献度分析
- AIによる活動サマリー自動生成
- 他コミュニティとの比較分析
- 個人ダッシュボード機能

### 10.2 スケーラビリティ

- Agent並列実行対応
- DB読み取りレプリカ
- CDNによる静的コンテンツ配信
- APIレート制限

## 11. 成功指標（KPI）

### 11.1 技術指標

- エージェント実行成功率: 99%以上
- API応答時間: 平均1秒以内
- システム稼働率: 99.9%以上

### 11.2 ビジネス指標

- 活動登録の自動化率: 90%以上
- 月次レポート生成の自動化: 100%
- メンバー利用率: 80%以上

## 12. リスクと対策

### 12.1 技術的リスク

| リスク | 影響度 | 対策 |
|--------|--------|------|
| Slack API制限 | 高 | レート制限の実装、キャッシュ活用 |
| connpass API障害 | 中 | リトライ処理、手動入力フォールバック |
| AWS レベル判定の精度 | 中 | 継続的なプロンプト改善、手動修正機能 |
| DB性能劣化 | 高 | インデックス最適化、定期メンテナンス |

### 12.2 運用リスク

| リスク | 影響度 | 対策 |
|--------|--------|------|
| シークレット漏洩 | 高 | Secrets Manager使用、定期ローテーション |
| データ消失 | 高 | 自動バックアップ、復元テスト |
| 不正アクセス | 高 | Cognito認証、監査ログ |

## 付録A: 用語集

- **Jr.Champions**: AWS若手コミュニティプログラム
- **AgentCore**: Amazon Bedrock のエージェント実行環境
- **Strands Agents SDK**: AWSのPythonエージェント開発SDK
- **MCP (Model Context Protocol)**: AIモデル向けコンテキスト共有プロトコル
- **Aurora DSQL**: AWSの分散SQLデータベース

## 付録B: 参考資料

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Strands Agents SDK Documentation](https://strandsagents.com/)
- [connpass API v2 Reference](https://connpass.com/about/api/v2/)
- [AWS MCP Servers](https://awslabs.github.io/mcp/)

---

作成日: 2025年1月2日
バージョン: 1.0.0
作成者: Jr.Champions活動記録システム開発チーム
