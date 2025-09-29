# Aurora DSQL セットアップ手順書

## 概要

このドキュメントでは、Jr.Champions活動記録システムのAurora DSQLデータベースを初期化し、必要なロール、スキーマ、テーブルを作成してテストを実行するまでの完全な手順を説明します。

## 前提条件

### 1. AWS CLIの設定
```bash
# AWS CLIがインストールされていることを確認
aws --version

# AWS認証情報が設定されていることを確認
aws sts get-caller-identity
```

### 2. 必要なパッケージのインストール
```bash
# Pythonパッケージのインストール
pip install psycopg2-binary boto3
```

### 3. Aurora DSQLクラスターの存在確認
```bash
# DSQLクラスターのエンドポイントを確認
aws dsql describe-clusters --region us-east-1

# エンドポイントをメモしておく
```

## セットアップ手順

### ステップ1: 環境変数の設定

```bash
# Aurora DSQL接続情報の設定
export DSQL_ENDPOINT='YOUR_DSQL_ENDPOINT.dsql.us-east-1.on.aws'
export DB_NAME='postgres'  # Aurora DSQLでは固定値（postgresデータベースのみサポート）
export AWS_REGION='us-east-1'

# 環境変数の確認
echo "DSQL_ENDPOINT: $DSQL_ENDPOINT"
echo "DB_NAME: $DB_NAME"
echo "AWS_REGION: $AWS_REGION"
```

> **重要**: Aurora DSQLは単一の`postgres`データベースのみをサポートします。新しいデータベースの作成はできません。すべてのデータはスキーマで論理的に分離して管理します。

### ステップ2: IAMトークンの生成（adminロール用）

```bash
# adminロール用のトークンを生成（DDL操作用）
TOKEN=$(aws dsql generate-db-connect-admin-auth-token \
  --hostname $DSQL_ENDPOINT \
  --region $AWS_REGION \
  --expires-in 900)

echo "Admin token generated successfully"
```

### ステップ3: データベースの初期化

#### 3.1 既存のスキーマとテーブルの削除（必要な場合）

```bash
# 既存のオブジェクトを削除する場合（注意：全データが削除されます）
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -f terraform/sql/drop_all_tables_output_history.sql

echo "Existing objects dropped (if any)"
```

#### 3.2 スキーマ、ロール、テーブルの作成

```bash
# output_historyスキーマとagent_graphロール、テーブルを作成
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -f terraform/sql/create_tables_output_history.sql

echo "Schema, role, and tables created successfully"
```

### ステップ4: 作成結果の確認

#### 4.1 スキーマの確認

```bash
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -c "\dn"
```

期待される出力：
```
       List of schemas
      Name       |  Owner  
-----------------+---------
 output_history  | admin
 public          | admin
```

#### 4.2 ロールの確認

```bash
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -c "\du"
```

期待される出力：
```
                List of roles
 Role name    |  Attributes  |     Member of
--------------+--------------+------------------
 admin        | Superuser    | {}
 agent_graph  |              | {}
```

#### 4.3 テーブルの確認

```bash
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -c "\dt output_history.*"
```

期待される出力：
```
                   List of relations
     Schema      |       Name        | Type  |  Owner
-----------------+-------------------+-------+---------
 output_history  | activities        | table | admin
 output_history  | members           | table | admin
 output_history  | monthly_reports   | table | admin
 output_history  | processing_history| table | admin
```

#### 4.4 権限の確認

```bash
# activitiesテーブルの権限を確認
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -c "\dp output_history.activities"
```

期待される出力：
```
                                     Access privileges
     Schema      |    Name     | Type  |       Access privileges
-----------------+-------------+-------+--------------------------------
 output_history  | activities  | table | admin=arwdDxt/admin
                 |             |       | agent_graph=arw/admin
```

### ステップ5: agent_graphロールでの接続テスト

```bash
# agent_graphロール用のトークンを生成
TOKEN_AGENT=$(aws dsql generate-db-connect-auth-token \
  --hostname $DSQL_ENDPOINT \
  --region $AWS_REGION \
  --expires-in 900)

# agent_graphロールで接続テスト
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=agent_graph port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN_AGENT" \
  -c "SELECT current_user, current_schema();"
```

期待される出力：
```
 current_user | current_schema
--------------+----------------
 agent_graph  | public
```

### ステップ6: Pythonテストスクリプトの実行

#### 6.1 テスト環境の準備

```bash
# プロジェクトディレクトリに移動
cd /path/to/jc-activity

# Python仮想環境を有効化（既に作成済みの場合）
source .venv/bin/activate

# 必要なパッケージを確認
pip list | grep -E "boto3|psycopg2"
```

  Aurora DSQL データアクセス層テスト
  Jr.Champions Activity Tracker

  1. データベース接続テスト
接続情報:
  エンドポイント: YOUR_DSQL_ENDPOINT.dsql.us-east-1.on.aws
  データベース: jr_champions_activities
  リージョン: us-east-1
✅ 接続成功（テストメンバーID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx）
#### 6.2 テストスクリプトの実行

```bash
# 環境変数が設定されていることを確認
export DSQL_ENDPOINT='YOUR_DSQL_ENDPOINT.dsql.us-east-1.on.aws'
export DB_NAME='postgres'  # Aurora DSQLでは固定値
export AWS_REGION='us-east-1'

# テストスクリプトを実行
python agent/data_access/test_dsql.py
```

期待される出力：
```
  Aurora DSQL データアクセス層テスト
  Jr.Champions Activity Tracker

  1. データベース接続テスト
接続情報:
  エンドポイント: YOUR_DSQL_ENDPOINT.dsql.us-east-1.on.aws
  データベース: postgres
  リージョン: us-east-1
✅ 接続成功（テストメンバーID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx）
============================================================
  Aurora DSQL データアクセス層テスト
  Jr.Champions Activity Tracker
============================================================

============================================================
  1. データベース接続テスト
============================================================
接続情報:
  エンドポイント: YOUR_DSQL_ENDPOINT.dsql.us-east-1.on.aws
  データベース: jr_champions_activities
  リージョン: us-east-1
✅ 接続成功（テストメンバーID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx）

============================================================
  2. メンバー作成/取得テスト
============================================================
✅ メンバー取得/作成成功: テストユーザー1 (ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
✅ メンバー取得/作成成功: テストユーザー2 (ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
✅ メンバー取得/作成成功: テストユーザー1（重複） (ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

============================================================
  3. 活動記録格納テスト
============================================================
✅ 活動記録作成成功: Aurora DSQLのテスト投稿です...
   活動ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
✅ 活動記録作成成功: AWS Summit Tokyo 2025参加...
   活動ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

重複チェックテスト:
✅ 重複チェック機能正常（スキップされました）

============================================================
  4. 月次レポート格納テスト
============================================================
✅ 月次レポート作成成功
   レポートID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

重複チェックテスト:
✅ 重複チェック機能正常（既存レポート検出）

============================================================
  5. 処理履歴記録テスト
============================================================
✅ 処理履歴記録成功: daily_collection/success
✅ 処理履歴記録成功: monthly_report/success
✅ 処理履歴記録成功: slack_fetch/success
✅ 処理履歴記録成功: daily_collection/failed

============================================================
  テスト完了
============================================================
✅ すべてのテストが完了しました
```

## トラブルシューティング

### 1. データベースエラー

#### エラー: `database "jr_champions_activities" does not exist`

**原因**: Aurora DSQLは`postgres`データベースのみをサポートします。

**解決方法**:
```bash
# 誤り
export DB_NAME="jr_champions_activities"

# 正しい
export DB_NAME="postgres"
```

> **注意**: Aurora DSQLでは新しいデータベースを作成することはできません。すべてのデータは`postgres`データベース内の`output_history`スキーマで管理します。

### 2. 接続エラー

#### エラー: `FATAL: password authentication failed for user "agent_graph"`

**原因**: IAMトークンの生成方法が間違っている

**解決方法**:
```bash
# agent_graphロール用は通常のトークン生成を使用
aws dsql generate-db-connect-auth-token \
  --hostname $DSQL_ENDPOINT \
  --region $AWS_REGION

# adminロール用はadmin専用コマンドを使用
aws dsql generate-db-connect-admin-auth-token \
  --hostname $DSQL_ENDPOINT \
  --region $AWS_REGION
```

### 2. 権限エラー

#### エラー: `permission denied for schema output_history`

**原因**: ロールに適切な権限が付与されていない

**解決方法**:
```bash
# adminロールで接続して権限を再付与
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -c "GRANT USAGE ON SCHEMA output_history TO agent_graph;"
  
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -c "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA output_history TO agent_graph;"
```

### 3. スキーマが見つからない

#### エラー: `relation "output_history.members" does not exist`

**原因**: スキーマまたはテーブルが作成されていない

**解決方法**:
```bash
# スキーマとテーブルを再作成
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -f terraform/sql/create_tables_output_history.sql
```

## クリーンアップ

テスト後にデータベースをクリーンアップする場合：

```bash
# adminトークンを生成
TOKEN=$(aws dsql generate-db-connect-admin-auth-token \
  --hostname $DSQL_ENDPOINT \
  --region $AWS_REGION \
  --expires-in 900)

# 全オブジェクトを削除
psql "host=$DSQL_ENDPOINT dbname=$DB_NAME user=admin port=5432 sslmode=require" \
  -v PGPASSWORD="$TOKEN" \
  -f terraform/sql/drop_all_tables_output_history.sql
```

## 次のステップ

1. **本番環境への適用**
   - 本番用のDSQLクラスターでも同様の手順を実行
   - 本番用の環境変数を適切に設定

2. **Agent Graphとの統合**
   - `agent/agent_graph.py`でDSQLクライアントを使用
   - Strands Agents SDKとの統合

3. **モニタリングの設定**
   - CloudWatchメトリクスの設定
   - アラートの設定

## 参考資料

- [Aurora DSQL公式ドキュメント](https://docs.aws.amazon.com/aurora-dsql/)
- [IAM認証ガイド](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/authentication.html)
- [psqlコマンドリファレンス](https://www.postgresql.org/docs/current/app-psql.html)
