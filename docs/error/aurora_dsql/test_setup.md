# Aurora DSQL テストセットアップガイド

## 前提条件

- Aurora DSQLクラスターが作成済み
- AWS CLIが設定済み
- Python 3.9以上
- PostgreSQLクライアント（psql）がインストール済み
- IAMユーザーまたはロールに適切な権限が付与済み

## 環境情報

- **エンドポイント**: `4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws`
- **データベース名**: `jr_champions_activities`
- **リージョン**: `us-east-1`
- **クラスターID**: `4qabuloasdxs36dl2zc6pablbm`

## Aurora DSQL認証体系について

Aurora DSQLでは2種類のロールを使い分けます：

1. **adminロール**: データベース管理用（テーブル作成、ロール管理）
   - `dsql:DbConnectAdmin`権限が必要
   - テーブル作成やスキーマ変更時に使用

2. **カスタムロール（app_user）**: アプリケーション接続用（データ操作）
   - `dsql:DbConnect`権限が必要
   - 通常のデータ操作時に使用

詳細は [`aurora_dsql_custom_role_setup.md`](./aurora_dsql_custom_role_setup.md) を参照してください。

## セットアップ手順

### 1. 依存関係のインストール

```bash
# agent/ディレクトリで実行
cd agent/
pip install -r requirements.txt
```

### 2. IAMロールの作成（初回のみ）

#### 2.1 AWS IAMコンソールでロールを作成

1. IAMコンソールにアクセス
2. 「ロール」→「ロールの作成」を選択
3. 信頼されたエンティティタイプを選択（EC2、Lambda、またはAWSアカウント）
4. ロール名を設定（例：`aurora-dsql-app-role`）

#### 2.2 カスタムポリシーを作成してアタッチ

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "dsql:DbConnect",
      "Resource": "arn:aws:dsql:us-east-1:*:cluster/4qabuloasdxs36dl2zc6pablbm"
    }
  ]
}
```

### 3. カスタムデータベースロールの作成（初回のみ）

#### 3.1 adminユーザーとして接続

```bash
# 環境変数の設定
export DSQL_ENDPOINT="4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws"
export DB_NAME="jr_champions_activities"
export AWS_REGION="us-east-1"
export PGSSLMODE=require

# adminユーザー用のトークン生成
export PGPASSWORD=$(aws dsql generate-db-connect-admin-auth-token \
  --expires-in 3600 \
  --region $AWS_REGION \
  --hostname $DSQL_ENDPOINT)

# psqlでの接続
psql --dbname $DB_NAME \
     --username admin \
     --host $DSQL_ENDPOINT
```

#### 3.2 カスタムロールの作成とマッピング

psqlセッション内で以下のSQLを実行：

```sql
-- ログイン可能なロールを作成
CREATE ROLE app_user WITH LOGIN;

-- IAMロールにマッピング（YOUR_ACCOUNT_IDとYOUR_IAM_ROLE_NAMEを置き換え）
-- 例: AWS IAM GRANT app_user TO 'arn:aws:iam::123456789012:role/aurora-dsql-app-role';
AWS IAM GRANT app_user TO 'arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_IAM_ROLE_NAME';

-- 必要な権限を付与
GRANT CONNECT ON DATABASE jr_champions_activities TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT CREATE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- デフォルト権限も設定（今後作成されるテーブルに対して）
ALTER DEFAULT PRIVILEGES IN SCHEMA public 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public 
  GRANT USAGE, SELECT ON SEQUENCES TO app_user;

-- マッピングの確認
SELECT * FROM sys.iam_pg_role_mappings;
```

### 4. テーブルの作成（adminユーザーで実行）

#### 4.1 既存テーブルの削除（必要な場合）

```bash
# adminトークンが有効期限切れの場合は再生成
export PGPASSWORD=$(aws dsql generate-db-connect-admin-auth-token \
  --expires-in 3600 \
  --region $AWS_REGION \
  --hostname $DSQL_ENDPOINT)

# テーブル削除
psql -h $DSQL_ENDPOINT \
     -U admin \
     -d $DB_NAME \
     -f ../../terraform/sql/drop_all_tables.sql
```

#### 4.2 テーブルの作成

```bash
# v2版（Aurora DSQL対応版）のSQLファイルを使用
psql -h $DSQL_ENDPOINT \
     -U admin \
     -d $DB_NAME \
     -f ../../terraform/sql/create_tables_dsql_v2.sql
```

#### 4.3 テーブル作成の確認

```bash
# テーブル一覧を確認
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\dt"

# テーブル構造を確認
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ members"
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ activities"
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ monthly_reports"
psql -h $DSQL_ENDPOINT -U admin -d $DB_NAME -c "\d+ processing_history"
```

### 5. アプリケーション接続の設定

#### 5.1 IAMロールの引き受け（ローカル開発の場合）

```bash
# 方法1: AWS CLIプロファイルを使用
export AWS_PROFILE=your-profile-name

# 方法2: STSでロールを引き受け
aws sts assume-role \
  --role-arn arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_IAM_ROLE_NAME \
  --role-session-name test-session > assume-role-output.json

# 取得した認証情報を環境変数に設定
export AWS_ACCESS_KEY_ID=$(jq -r '.Credentials.AccessKeyId' assume-role-output.json)
export AWS_SECRET_ACCESS_KEY=$(jq -r '.Credentials.SecretAccessKey' assume-role-output.json)
export AWS_SESSION_TOKEN=$(jq -r '.Credentials.SessionToken' assume-role-output.json)
```

#### 5.2 カスタムロールでの接続テスト

```bash
# app_user用のトークン生成（注: admin用ではない）
export APP_TOKEN=$(aws dsql generate-db-connect-auth-token \
  --expires-in 3600 \
  --region $AWS_REGION \
  --hostname $DSQL_ENDPOINT)

# psqlでの接続テスト
PGPASSWORD=$APP_TOKEN psql \
  --dbname $DB_NAME \
  --username app_user \
  --host $DSQL_ENDPOINT \
  -c "SELECT current_user, current_database();"
```

### 6. Pythonテストスクリプトの実行

```bash
# agent/data_access/ディレクトリで実行
cd data_access/
python test_dsql.py
```

## トラブルシューティング

### 接続エラーの対処

#### DbConnect権限エラー
```
FATAL: unable to accept connection, access denied
HINT: Wrong user to action mapping. user: admin, action: DbConnect
```
**解決策**: 
- adminユーザーではなくカスタムロール（app_user）を使用する
- adminには`generate-db-connect-admin-auth-token`を使用
- app_userには`generate-db-connect-auth-token`を使用

#### IAM認証エラー
- IAMポリシーが正しくアタッチされているか確認
- トークン生成コマンドが正しいか確認
- トークンの有効期限（デフォルト15分）が切れていないか確認

#### SSL接続エラー
- `PGSSLMODE=require`環境変数が設定されているか確認

### よくある問題と解決策

| 問題 | 原因 | 解決策 |
|------|------|--------|
| adminで接続できるがデータ操作でエラー | adminはDbConnectAdmin権限のみ | カスタムロールを作成して使用 |
| app_userで接続できない | IAMロールマッピングが未設定 | AWS IAM GRANTコマンドでマッピング |
| トークンが無効 | 有効期限切れまたは誤ったコマンド使用 | 新しいトークンを正しいコマンドで生成 |
| テーブルが見えない | スキーマ権限不足 | GRANT USAGE ON SCHEMAを実行 |
| データ挿入できない | テーブル権限不足 | GRANT INSERT ON TABLEを実行 |

### IAM権限の確認

```bash
# 現在のIAMユーザー/ロールの確認
aws sts get-caller-identity

# DSQLクラスター一覧の確認
aws dsql list-clusters --region us-east-1

# クラスター詳細の確認
aws dsql describe-cluster \
  --identifier 4qabuloasdxs36dl2zc6pablbm \
  --region us-east-1
```

## Aurora DSQL特有の注意事項

- **外部キー制約なし**: アプリケーション側で整合性管理が必要
- **JSON/JSONB型非対応**: TEXT型で代替、アプリケーション側でJSON処理
- **CREATE INDEX ASYNC必須**: 通常のCREATE INDEXは使用不可
- **PL/pgSQL関数非対応**: トリガーや関数はアプリケーション層で実装
- **IAM認証のみ**: パスワード認証は使用不可
- **トークン有効期限**: 
  - CLI/SDK: デフォルト15分
  - コンソール: デフォルト1時間
  - 最大: 604,800秒（1週間）

## 期待されるテスト結果

テストスクリプト実行時の期待結果：

1. **接続テスト**: ✅ 成功（app_userとして接続）
2. **メンバー作成**: ✅ 成功（または既存の場合スキップ）
3. **活動記録作成**: ✅ 成功（重複の場合スキップ）
4. **月次レポート生成**: ✅ 成功（既存の場合スキップ）
5. **処理履歴記録**: ✅ 成功

詳細なエラー情報は [`errorlog.md`](../../terraform/sql/errorlog.md) を参照してください。
