# Aurora DSQLカスタムロール設定ガイド

## 問題の概要

現在、`admin`ユーザーで`DbConnect`アクションを実行しようとして以下のエラーが発生：
```
FATAL: unable to accept connection, access denied
HINT: Wrong user to action mapping. user: admin, action: DbConnect
```

**原因**: Aurora DSQLでは、`admin`ユーザーは`DbConnectAdmin`権限のみを持ち、アプリケーション接続には`DbConnect`権限を持つカスタムデータベースロールが必要。

## Aurora DSQL認証体系

### ロールの種類
1. **adminロール**
   - `dsql:DbConnectAdmin`権限のみ
   - データベース管理用（テーブル作成、ロール管理など）
   - アプリケーション接続には不適切

2. **カスタムデータベースロール**
   - `dsql:DbConnect`権限
   - アプリケーション接続用
   - IAMロールとマッピングして使用

## 解決手順

### Step 1: IAMロールの作成

1. AWS IAMコンソールで新しいロールを作成
2. 信頼ポリシーを設定（EC2、Lambda、またはユーザーアカウントからの引き受けを許可）
3. カスタムポリシーを作成してアタッチ：

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

### Step 2: カスタムデータベースロールの作成

1. **adminユーザーとして接続**（DbConnectAdmin権限を使用）：
```bash
# 認証トークン生成（admin用）
aws dsql generate-db-connect-admin-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws

# psqlで接続
PGSSLMODE=require psql \
  --dbname jr_champions_activities \
  --username admin \
  --host 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws
```

2. **カスタムデータベースロールを作成**：
```sql
-- ログイン可能なロールを作成
CREATE ROLE app_user WITH LOGIN;

-- IAMロールにマッピング（IAMロールのARNに置き換え）
AWS IAM GRANT app_user TO 'arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_IAM_ROLE_NAME';

-- 重要: Aurora DSQLの権限設定の制限
-- ❌ GRANT CONNECT ON DATABASE → エラー: unsupported object type in GRANT
-- ❌ GRANT USAGE ON SCHEMA public → エラー: feature not supported on system entity
-- ✅ 解決策: 個別テーブルに権限を付与

-- adminでテーブル作成後、個別に権限付与
GRANT SELECT, INSERT, UPDATE, DELETE ON members TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON activities TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON monthly_reports TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON processing_history TO app_user;

-- 今後adminが作成するテーブルへのデフォルト権限
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA public 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
```

3. **マッピングの確認**：
```sql
-- IAMロールとデータベースロールのマッピングを確認
SELECT * FROM sys.iam_pg_role_mappings;
```

### Step 3: アプリケーション接続の設定

#### カスタムロール用の認証トークン生成

```bash
# カスタムロール用（注: admin用ではなくDbConnect用）
aws dsql generate-db-connect-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname 4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws
```

#### Python接続コードの修正

`dsql_client.py`の接続部分を以下のように修正：

```python
import boto3
import psycopg
from typing import Optional

class DSQLClient:
    def __init__(self, 
                 endpoint: str,
                 database: str = "jr_champions_activities",
                 region: str = "us-east-1",
                 use_admin: bool = False):  # adminとカスタムロールの切り替え
        self.endpoint = endpoint
        self.database = database
        self.region = region
        self.use_admin = use_admin
        self.username = "admin" if use_admin else "app_user"
        self.connection = None
        
    def generate_auth_token(self) -> str:
        """IAM認証トークンを生成"""
        client = boto3.client("dsql", region_name=self.region)
        
        if self.use_admin:
            # admin用（テーブル作成時などに使用）
            token = client.generate_db_connect_admin_auth_token(
                Hostname=self.endpoint,
                Region=self.region
            )
        else:
            # カスタムロール用（通常のアプリケーション接続）
            token = client.generate_db_connect_auth_token(
                Hostname=self.endpoint,
                Region=self.region
            )
        
        return token
    
    def connect(self) -> psycopg.Connection:
        """Aurora DSQLに接続"""
        if self.connection and not self.connection.closed:
            return self.connection
        
        try:
            # 認証トークンを生成
            password = self.generate_auth_token()
            
            # 接続パラメータ
            conn_params = {
                'host': self.endpoint,
                'port': 5432,
                'dbname': self.database,
                'user': self.username,
                'password': password,
                'sslmode': 'require',
                'connect_timeout': 30
            }
            
            # 接続
            self.connection = psycopg.connect(**conn_params)
            print(f"Successfully connected as {self.username}")
            return self.connection
            
        except Exception as e:
            print(f"Connection failed: {e}")
            raise
```

## テスト手順

### Step 1: テーブルの再作成（admin権限で実行）

```python
# admin権限でテーブル作成
client = DSQLClient(
    endpoint="4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws",
    use_admin=True  # admin権限を使用
)

# drop_all_tables.sqlとcreate_tables_dsql_v2.sqlを実行
```

### Step 2: アプリケーション接続テスト

```python
# カスタムロールでアプリケーション接続
client = DSQLClient(
    endpoint="4qabuloasdxs36dl2zc6pablbm.dsql.us-east-1.on.aws",
    use_admin=False  # カスタムロールを使用
)

# データ操作のテスト
client.test_connection()
client.test_member_operations()
client.test_activity_storage()
```

## 重要な注意事項

1. **IAMロールの引き受け**
   - EC2インスタンス、Lambda関数、またはローカル開発環境でIAMロールを引き受ける必要がある
   - ローカル開発の場合は`aws configure`でプロファイルを設定するか、`aws sts assume-role`を使用

2. **トークンの有効期限**
   - デフォルト: CLI/SDK 15分、コンソール 1時間
   - 最大: 604,800秒（1週間）
   - 接続確立後はトークンの有効期限切れても接続は維持される

3. **権限の分離**
   - テーブル作成・スキーマ変更: `admin`ロール
   - データ操作（CRUD）: カスタムロール
   - 本番環境では最小権限の原則に従う

4. **接続のトラブルシューティング**
   - IAMポリシーが正しくアタッチされているか確認
   - データベースロールが正しく作成されているか確認
   - IAMロールとデータベースロールのマッピングを確認
   - リージョンとエンドポイントが正しいか確認

## 環境別の推奨設定

### 開発環境
- 開発者のIAMユーザーにDbConnect権限を付与
- 短めのトークン有効期限（1時間）

### 本番環境
- EC2/Lambda用のIAMロールを使用
- 長めのトークン有効期限（最大1週間）
- 最小権限の原則を徹底

## 次のステップ

1. 上記の手順に従ってIAMロールとカスタムデータベースロールを作成
2. `dsql_client.py`を修正して両方のロールに対応
3. `test_setup.md`を更新して新しい手順を反映
4. `test_dsql.py`を実行して接続をテスト
