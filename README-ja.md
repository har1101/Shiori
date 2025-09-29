# Shiori（栞）

**Shiori**は、Slackチャンネルから技術的なアウトプットを自動的に収集・分析・記録するインテリジェントなマルチエージェントシステムです。「栞」という名前は、本に栞を挟むように自身のアウトプットを簡単に記録できるという意図を込めており、英語のbookmark（URL収集）の象徴でもあります。

## 🔖 プロジェクト概要

ShioriはAmazon Bedrock AgentCoreとStrands Agents SDKを活用して、以下の機能を実現します。

- 指定されたSlackチャンネルから技術コンテンツのURLを収集
- AIエージェントを使用したコンテンツの抽出・要約
- Amazon Aurora DSQLでの構造化データ保存
- Streamlitベースの直感的なWebインターフェース

## 🏗️ システム構成

### マルチエージェントシステム

- **Slackエージェント**: 指定されたSlackチャンネルからメッセージとURLを取得
- **Web コンテンツエージェント**: Firecrawlを使用してコンテンツの抽出・分析
- **AWSレベル評価エージェント**: 技術的複雑度とAWSサービス使用状況の評価

### 主要コンポーネント

- **フロントエンド**: Streamlitベースのチャットインターフェース（`frontend_app.py`）
- **エージェントグラフ**: マルチエージェント オーケストレーション（`agent_graph/shiori_agent_graph.py`）
- **データアクセス層**: Aurora DSQL連携（`agent_graph/data_access/dsql_client.py`）
- **データベーススキーマ**: 構造化データ保存（`sql/create_tables_output_history.sql`）

## 🚀 セットアップ手順

### 前提条件

1. **uvパッケージマネージャーのインストール**

   ```bash
   # uvがインストールされていない場合
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Amazon Aurora DSQLの設定**
   - AWSアカウントでAurora DSQLクラスターとIAMロール（クラスターアクセス用）を作成
   - セットアップガイドを参照: https://qiita.com/har1101/items/7dd1a6d803e48e3e0525
   - `sql/create_tables_output_history.sql`からSQLスキーマを実行

3. **Bedrock AgentCore GatewayとIdentityの設定**
   - AgentCore Gateway（Slack MCP用）を作成
   - AgentCore Identity（AgentCore GatewayとLangfuse用）を作成
   - セットアップガイドを参照:
     - https://qiita.com/har1101/items/aae967fa157b01e414a9
     - https://qiita.com/har1101/items/73165084bc6ec5c64290

### インストール

1. **リポジトリのクローン**

   ```bash
   git clone https://github.com/har1101/Shiori.git
   cd Shiori
   ```

2. **Python仮想環境のセットアップ**

   ```bash
   uv venv
   cd agent_graph
   uv pip install -r requirements.txt
   ```

3. **追加依存関係のインストール**
   ```bash
   uv pip install bedrock-agentcore-starter-toolkit streamlit
   ```

4. **AgentCoreの設定**

   ```bash
   cd agent_graph
   agentcore configure
   ```

5. **環境変数を指定してAgentCoreを起動**

   ```bash
   agentcore launch \
     --env LANGFUSE_PUBLIC_KEY_SECRET_ID=langfuse-public-key
     --env LANGFUSE_SECRET_KEY_SECRET_ID=langfuse-secret-key \
     --env DISABLE_ADOT_OBSERVABILITY=true \
     --env LANGFUSE_HOST=https://us.cloud.langfuse.com \
     --env COGNITO_SCOPE=<scope> \
     --env GATEWAY_URL=https://<gateway-id>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp \
     --env PROVIDER_NAME=<AgentCore Identity Provider Name> \
     --env SLACK_CHANNEL=<Slack Channel ID>
     --env AURORA_DSQL_CLUSTER_ENDPOINT=<Cluster ID>.dsql.<region>.on.aws \
     --env AURORA_DSQL_DATABASE_USER=<DB User Name>
   ```

6. **フロントエンドアプリケーションの起動**

   ```bash
   # プロジェクトルートから
   streamlit run frontend_app.py
   ```

## 🔧 設定

### 環境変数

| 変数名 | 説明 | 例 |
|--------|------|-----|
| `SLACK_CHANNEL` | 対象のSlackチャンネルID | `C*********` |
| `DSQL_ENDPOINT` | Aurora DSQLクラスターエンドポイント | `your-cluster.dsql.region.on.aws` |
| `LANGFUSE_HOST` | Langfuse可観測性エンドポイント | `https://us.cloud.langfuse.com` |

### データベースセットアップ

Aurora DSQLでSQLスキーマを実行

```bash
psql -h your-dsql-endpoint -U admin -d postgres -f sql/create_tables_output_history.sql
```

## 📊 主な機能

### インテリジェントなコンテンツ収集

- 指定されたSlackチャンネルの自動監視
- 技術的コンテンツを含むメッセージからのURL抽出
- 関連する技術的アウトプットのフィルタリング（ブログ記事、プレゼンテーション、ドキュメントなど）

### AIによる分析

- 高度な言語モデルを使用したコンテンツ要約
- AWSサービス使用状況評価と技術レベル判定
- Webコンテンツからの構造化データ抽出

### Streamlit Webインターフェース

- エージェントシステムとのリアルタイムチャットインターフェース
- 視覚的な進捗追跡と実行統計
- 展開可能な詳細を含む構造化レスポンス形式

### データ管理

- Amazon Aurora DSQLでの永続的ストレージ
- 包括的な活動追跡と月次レポート
- 処理履歴とエラーログ

## 🛠️ 技術スタック

- **フレームワーク**: Amazon Bedrock AgentCore、Strands Agents SDK
- **データベース**: Amazon Aurora DSQL
- **フロントエンド**: Streamlit
- **言語**: Python 3.9+
- **可観測性**: Langfuse
- **プロトコル**: MCP (Model Context Protocol)

## 📁 プロジェクト構造

```text
Shiori/
├── agent_graph/                 # コアエージェントシステム
│   ├── agents/                  # エージェント実装
│   │   ├── slack_agent_factory.py
│   │   ├── web_agent_factory.py
│   │   └── nodes/               # カスタムノード実装
│   ├── data_access/             # データベースアクセス層
│   │   └── dsql_client.py
│   ├── requirements.txt         # Python依存関係
│   └── shiori_agent_graph.py    # メインエージェントグラフ
├── sql/                         # データベーススキーマ
│   └── create_tables_output_history.sql
├── docs/                        # ドキュメント
├── frontend_app.py              # Streamlitフロントエンド
├── README.md                    # 英語版README
└── README-ja.md                 # このファイル
```

## 🎯 使用例

### 基本的な使用フロー

1. **Streamlitアプリケーションの起動**

   ```bash
   streamlit run frontend_app.py
   ```

2. **チャットインターフェースでのやり取り**
   - 「Slackチャンネルから最新の投稿を要約して」
   - 「技術ブログのURLを分析して」

3. **結果の確認**
   - 構造化されたレスポンスでエージェント実行結果を確認
   - 詳細情報は展開可能セクションで確認

## 📚 参考資料

- [Bedrock AgentCoreセットアップガイド](https://qiita.com/har1101/items/aae967fa157b01e414a9)
- [Aurora DSQL設定方法](https://qiita.com/har1101/items/7dd1a6d803e48e3e0525)

## 🔍 トラブルシューティング

### よくある問題

1. **AWS認証エラー**
   - AWS認証情報が正しく設定されているか確認
   - IAMロールの権限を確認

2. **Aurora DSQL接続エラー**
   - エンドポイントが正しいか確認
   - VPC設定とセキュリティグループを確認

3. **MCP接続エラー**
   - MCPサーバーが稼働しているか確認
   - ネットワーク接続を確認

## 🆘 サポート

ご質問やサポートが必要な場合は、Issueを作成するか、プロジェクトのメンテナーまでお問い合わせください。
