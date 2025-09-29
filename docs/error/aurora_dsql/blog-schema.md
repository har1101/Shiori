# Aurora DSQLでスキーマ・テーブル作成時のエラーと対処法 - 実践ガイド

## はじめに

AWS Aurora DSQLは、従来のAurora PostgreSQLとは異なる分散SQLデータベースサービスです。PostgreSQL互換ではあるものの、独自の制限事項があるため、スキーマやテーブルを作成する際に様々なエラーに遭遇することがあります。

この記事では、Jr.Champions活動記録システムの開発で実際に遭遇したエラーとその解決方法を、体系的に整理して共有します。

## 前提知識：スキーマとテーブルとは

### スキーマ（Schema）
スキーマは、データベース内の論理的な名前空間です。関連するテーブル、ビュー、関数などをグループ化し、整理するための仕組みです。

```sql
-- スキーマの作成例
CREATE SCHEMA app_schema;

-- スキーマ内にテーブルを作成
CREATE TABLE app_schema.users (
    id UUID PRIMARY KEY,
    name VARCHAR(100)
);
```

**スキーマのメリット：**
- **論理的な分離**: 異なる機能やアプリケーションのオブジェクトを分離
- **権限管理**: スキーマ単位でアクセス権限を制御
- **名前の衝突回避**: 同じ名前のテーブルを異なるスキーマで作成可能

### テーブル（Table）
テーブルは、データを行と列の形式で格納する基本的なデータベースオブジェクトです。

```sql
-- テーブルの作成例
CREATE TABLE members (
    member_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**テーブルの構成要素：**
- **カラム（列）**: データの属性（名前、メールアドレスなど）
- **データ型**: 各カラムが格納できるデータの種類（VARCHAR、UUID、TIMESTAMPなど）
- **制約**: データの整合性を保つルール（PRIMARY KEY、NOT NULL、UNIQUEなど）
- **インデックス**: 検索性能を向上させる仕組み

## Aurora DSQLの特徴と制限事項

Aurora DSQLは分散アーキテクチャを採用しているため、通常のPostgreSQLとは異なる制限があります。

### 主な制限事項

| 機能 | PostgreSQL | Aurora DSQL | 備考 |
|------|------------|-------------|---------|
| JSON/JSONB型 | ✅ サポート | ❌ 非対応 | TEXT型で代替 |
| PL/pgSQL関数 | ✅ サポート | ❌ 非対応 | アプリケーション層で実装 |
| トリガー | ✅ サポート | ❌ 非対応 | アプリケーション層で実装 |
| CREATE INDEX | ✅ 通常構文 | ⚠️ ASYNC必須 | 非同期インデックス作成 |
| publicスキーマ権限 | ✅ 変更可能 | ❌ システム予約 | カスタムスキーマ推奨 |

## 発生したエラーと解決方法

### エラー1: JSON/JSONBデータ型がサポートされていない

#### エラーメッセージ
```
ERROR:  datatype jsonb not supported
ERROR:  datatype json not supported
```

#### 技術用語解説
- **JSON (JavaScript Object Notation)**: キーと値のペアで構成される軽量なデータ交換フォーマット
- **JSONB**: JSONのバイナリ形式で、PostgreSQLで高速な検索・操作が可能なデータ型
- **データ型 (Data Type)**: データベースで値を格納する際の形式を定義するもの

#### 原因
Aurora DSQLは分散アーキテクチャのため、JSON/JSONBデータ型の一貫性保証が困難であり、現時点でサポートされていません。

#### 解決方法
JSON/JSONB型をTEXT型に変更し、アプリケーション側でJSONのパース/シリアライズを実装します。

**変更前（通常のPostgreSQL）:**
```sql
CREATE TABLE activities (
    activity_id UUID PRIMARY KEY,
    aws_services JSONB,  -- JSONBデータ型
    tags JSON            -- JSONデータ型
);
```

**変更後（Aurora DSQL）:**
```sql
CREATE TABLE activities (
    activity_id UUID PRIMARY KEY,
    aws_services TEXT,  -- JSON文字列として保存
    tags TEXT          -- JSON文字列として保存
);
```

**Python実装例:**
```python
import json

class DSQLClient:
    def store_activity(self, activity_data):
        # JSONデータをTEXT型として保存（シリアライズ）
        aws_services_json = json.dumps(activity_data.get('aws_services', []))
        tags_json = json.dumps(activity_data.get('tags', []))
        
        query = """
        INSERT INTO activities (aws_services, tags)
        VALUES (%s, %s)
        """
        cursor.execute(query, (aws_services_json, tags_json))
    
    def get_activity(self, activity_id):
        query = "SELECT aws_services, tags FROM activities WHERE activity_id = %s"
        cursor.execute(query, (activity_id,))
        row = cursor.fetchone()
        
        # TEXT型からJSONへ変換（デシリアライズ）
        aws_services = json.loads(row[0]) if row[0] else []
        tags = json.loads(row[1]) if row[1] else []
        
        return {'aws_services': aws_services, 'tags': tags}
```

**参照ドキュメント:** `terraform/sql/errorlog.md`

### エラー2: CREATE INDEX構文エラー

#### エラーメッセージ
```
ERROR:  syntax error at or near "INDEX"
```

#### 技術用語解説
- **インデックス (Index)**: データベースの検索性能を向上させるためのデータ構造
- **同期処理 (Synchronous)**: 処理が完了するまで待機する実行方式
- **非同期処理 (Asynchronous)**: 処理の完了を待たずに次の処理に進む実行方式
- **CREATE INDEX ASYNC**: Aurora DSQL独自の非同期インデックス作成構文

#### 原因
Aurora DSQLは分散環境でのインデックス作成の一貫性を保つため、非同期インデックス作成（CREATE INDEX ASYNC）のみをサポートしています。

#### 解決方法

**変更前（通常のPostgreSQL）:**
```sql
CREATE INDEX idx_activities_date ON activities(activity_date);
```

**変更後（Aurora DSQL）:**
```sql
CREATE INDEX ASYNC idx_activities_date ON activities(activity_date);
```

**参照ドキュメント:** `terraform/sql/errorlog.md`、`terraform/sql/create_tables_dsql_v3.sql`

### エラー3: PL/pgSQL関数がサポートされていない

#### エラーメッセージ
```
ERROR:  language "plpgsql" does not exist
```

#### 技術用語解説
- **PL/pgSQL**: PostgreSQL用の手続き型言語で、ストアドプロシージャやトリガーを記述するために使用
- **ストアドプロシージャ (Stored Procedure)**: データベース内に保存される実行可能なプログラム
- **トリガー (Trigger)**: 特定のイベント（INSERT、UPDATE、DELETE）が発生した際に自動実行される処理
- **言語ハンドラ (Language Handler)**: データベースが特定のプログラミング言語を実行するための仕組み

#### 原因
Aurora DSQLは分散アーキテクチャのため、ノード間でのストアドプロシージャやトリガーの同期が困難であり、サポートされていません。

#### 解決方法
トリガーとして実装していた機能をアプリケーション層に移動します。

**変更前（通常のPostgreSQL）:**
```sql
-- トリガー関数の定義
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- トリガーの作成
CREATE TRIGGER update_members_updated_at
    BEFORE UPDATE ON members
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
```

**変更後（Aurora DSQL - Python実装）:**
```python
from datetime import datetime

class DSQLClient:
    def update_member(self, member_id, data):
        # アプリケーション層でupdated_atを更新
        data['updated_at'] = datetime.now()
        
        query = """
        UPDATE members 
        SET name = %s, email = %s, updated_at = %s
        WHERE member_id = %s
        """
        cursor.execute(query, (
            data['name'], 
            data['email'], 
            data['updated_at'],
            member_id
        ))
```

**参照ドキュメント:** `terraform/sql/errorlog.md`

### エラー4: publicスキーマへの権限付与エラー

#### エラーメッセージ
```
ERROR:  feature not supported on system entity
```

#### 技術用語解説
- **publicスキーマ**: PostgreSQLのデフォルトスキーマで、通常は全ユーザーがアクセス可能
- **システムエンティティ (System Entity)**: データベースシステムが予約・管理するオブジェクト
- **GRANT文**: データベースオブジェクトへのアクセス権限を付与するSQL文
- **USAGE権限**: スキーマ内のオブジェクトにアクセスするための基本権限

#### 原因
Aurora DSQLでは`public`スキーマがシステムエンティティとして予約されており、セキュリティと分散環境での一貫性のため、権限変更ができません。

#### 解決方法
カスタムスキーマを作成して使用します（AWSドキュメント推奨）。

```sql
-- Step 1: カスタムスキーマを作成
CREATE SCHEMA app_schema;

-- Step 2: ロールを作成
CREATE ROLE app_user WITH LOGIN;

-- Step 3: IAMロールとマッピング
AWS IAM GRANT app_user TO 'arn:aws:iam::123456789012:role/MyIAMRole';

-- Step 4: スキーマへの権限付与（カスタムスキーマなら可能）
GRANT USAGE ON SCHEMA app_schema TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app_schema TO app_user;

-- Step 5: デフォルト権限設定
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA app_schema 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
```

**参照ドキュメント:** `agent/data_access/aurora_dsql_permissions_solution.md`、`agent/data_access/aurora_dsql_final_solution.md`

### エラー5: Wrong user to action mapping

#### エラーメッセージ
```
HINT: Wrong user to action mapping. user: admin, action: DbConnect
```

#### 技術用語解説
- **IAM認証 (IAM Authentication)**: AWS Identity and Access Managementを使用したデータベース認証
- **DbConnect**: 通常のデータベース接続用のIAMアクション（アプリケーション用）
- **DbConnectAdmin**: 管理者用のデータベース接続IAMアクション（DDL操作用）
- **認証トークン (Authentication Token)**: 一時的な認証情報として使用される文字列

#### 原因
Aurora DSQLには2種類の認証アクションがあり、ユーザーとトークン生成コマンドの組み合わせが間違っていると発生します。adminユーザーはDbConnectAdminアクションのみ使用可能で、通常のDbConnectアクションは使用できません。

#### 解決方法

| ユーザー | 正しいトークン生成コマンド | IAMアクション | 用途 |
|---------|---------------------------|--------------|----|
| admin | `generate-db-connect-admin-auth-token` | dsql:DbConnectAdmin | DDL操作、ロール管理 |
| app_user | `generate-db-connect-auth-token` | dsql:DbConnect | DML操作、アプリケーション接続 |

**adminユーザーで接続:**
```bash
# adminユーザー用トークン生成（DbConnectAdmin権限必要）
aws dsql generate-db-connect-admin-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname your-cluster.dsql.us-east-1.on.aws

# psqlで接続
PGSSLMODE=require psql \
  --dbname your_database \
  --username admin \
  --host your-cluster.dsql.us-east-1.on.aws
```

**app_userで接続:**
```bash
# app_user用トークン生成（DbConnect権限必要）
aws dsql generate-db-connect-auth-token \
  --expires-in 3600 \
  --region us-east-1 \
  --hostname your-cluster.dsql.us-east-1.on.aws

# psqlで接続
PGSSLMODE=require psql \
  --dbname your_database \
  --username app_user \
  --host your-cluster.dsql.us-east-1.on.aws
```

**参照ドキュメント:** `agent/data_access/aurora_dsql_token_generation_guide.md`、`agent/data_access/aurora_dsql_custom_role_setup.md`

### エラー6: テーブル構造の不一致

#### エラーメッセージ
```
Failed to get/create member: column "slack_user_id" does not exist
LINE 1: SELECT member_id FROM app_schema.members WHERE slack_user_id...
```

#### 技術用語解説
- **カラム (Column)**: テーブル内の縦の列で、特定の属性を表す
- **SQL文**: データベースに対する操作を記述する構造化問い合わせ言語
- **SELECT文**: データベースからデータを取得するSQL文
- **WHERE句**: 検索条件を指定するSQL文の一部

#### 原因
コード内のSQL文で参照しているカラム名と、実際のテーブル定義のカラム名が一致していません。これは開発中のスキーマ変更が、アプリケーションコードに反映されていない場合によく発生します。

#### 解決方法
実際のテーブル定義を確認し、コード内のSQL文を修正します。

```python
# 変更前（存在しないカラムを参照）
def get_or_create_member(self, member_data):
    query = """
    SELECT member_id FROM members 
    WHERE slack_user_id = %s  # slack_user_idカラムは存在しない
    """
    cursor.execute(query, (member_data['slack_user_id'],))

# 変更後（実際のカラムに合わせて修正）
def get_or_create_member(self, member_data):
    query = """
    SELECT member_id FROM members 
    WHERE email = %s  # emailカラムを使用
    """
    cursor.execute(query, (member_data['email'],))
```

**参照ドキュメント:** `agent/data_access/dsql_client.py`、`terraform/sql/create_tables_dsql_v3.sql`

### エラー7: 権限不足エラー

#### エラーメッセージ
```
Failed to get/create member: permission denied for table members
```

#### 技術用語解説
- **DML (Data Manipulation Language)**: データ操作言語（SELECT、INSERT、UPDATE、DELETE）
- **DDL (Data Definition Language)**: データ定義言語（CREATE、ALTER、DROP）
- **権限 (Permission/Privilege)**: データベースオブジェクトに対する操作許可
- **ロール (Role)**: 権限をグループ化したデータベースユーザーの集合

#### 原因
app_userロールがテーブルへのアクセス権限を持っていません。Aurora DSQLでは、デフォルトでカスタムロールには権限が付与されないため、明示的な権限付与が必要です。

#### 解決方法
adminユーザーで必要な権限を付与します。

```sql
-- スキーマへの使用権限（カスタムスキーマの場合）
GRANT USAGE ON SCHEMA app_schema TO app_user;

-- 既存テーブルへの権限
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app_schema TO app_user;

-- 今後作成されるテーブルへのデフォルト権限
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA app_schema 
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
```

**参照ドキュメント:** `agent/data_access/aurora_dsql_permissions_solution.md`

## ベストプラクティス

### 1. スキーマ設計
- **カスタムスキーマを使用**: `public`スキーマの制限を回避
- **環境ごとにスキーマを分離**: dev_schema, prod_schemaなど
- **明示的なスキーマ指定**: テーブル作成時は常にスキーマ名を含める

### 2. データ型の選択
- **JSON代替**: TEXT型 + アプリケーション層でのパース
- **配列代替**: 正規化したテーブルまたはカンマ区切りTEXT
- **UUID推奨**: 分散環境での一意性保証

### 3. インデックス戦略
- **必ずASYNC使用**: CREATE INDEX ASYNCを標準とする
- **必要最小限**: 分散環境では過度なインデックスは逆効果
- **監視と調整**: インデックス作成の進捗を確認

### 4. 権限管理
- **ロールの分離**: admin（DDL用）とapp_user（DML用）を分離
- **最小権限の原則**: 必要最小限の権限のみ付与
- **IAMとの統合**: データベースロールとIAMロールを適切にマッピング

## 実装例：完全なセットアップスクリプト

```sql
-- 1. adminユーザーでログイン後、スキーマとロールを作成
CREATE SCHEMA IF NOT EXISTS app_schema;
CREATE ROLE app_user WITH LOGIN;
AWS IAM GRANT app_user TO 'arn:aws:iam::123456789012:role/MyIAMRole';

-- 2. 権限設定
GRANT USAGE ON SCHEMA app_schema TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app_schema TO app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE admin IN SCHEMA app_schema 
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

-- 3. テーブル作成（Aurora DSQL対応版）
SET search_path TO app_schema;

CREATE TABLE IF NOT EXISTS app_schema.members (
    member_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    github_username VARCHAR(100),
    aws_account_id VARCHAR(12),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_schema.activities (
    activity_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    member_id UUID NOT NULL,
    activity_date DATE NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    aws_services TEXT,  -- JSON代替
    github_repo_url VARCHAR(500),
    blog_url VARCHAR(500),
    tags TEXT,  -- JSON代替
    aws_level VARCHAR(50),
    summary_by_ai TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(member_id, activity_date, title)
);

-- 4. インデックス作成（ASYNC必須）
CREATE INDEX ASYNC idx_activities_member_date ON app_schema.activities(member_id, activity_date);
CREATE INDEX ASYNC idx_activities_date ON app_schema.activities(activity_date);
CREATE INDEX ASYNC idx_members_email ON app_schema.members(email);
```

## トラブルシューティングチェックリスト

問題が発生した際は、以下の項目を順番に確認してください：

1. **データ型の確認**
   - [ ] JSON/JSONB型を使用していないか
   - [ ] 配列型を使用していないか
   - [ ] サポートされているデータ型のみ使用しているか

2. **スキーマの確認**
   - [ ] カスタムスキーマを作成しているか
   - [ ] publicスキーマへの権限付与を試みていないか
   - [ ] スキーマ名を明示的に指定しているか

3. **インデックスの確認**
   - [ ] CREATE INDEX ASYNCを使用しているか
   - [ ] インデックス作成が完了しているか

4. **認証の確認**
   - [ ] 正しいトークン生成コマンドを使用しているか
   - [ ] IAMロールが正しく設定されているか
   - [ ] データベースロールとIAMロールがマッピングされているか

5. **権限の確認**
   - [ ] 必要な権限が付与されているか
   - [ ] デフォルト権限が設定されているか

## まとめ

Aurora DSQLは高可用性と無限のスケーラビリティを提供する優れたサービスですが、従来のPostgreSQLとは異なる制限事項があります。これらの制限を理解し、適切に対処することで、スムーズな開発が可能になります。

### 重要なポイント

1. **JSON型の代替**: TEXT型 + アプリケーション層での処理
2. **インデックス作成**: 必ずCREATE INDEX ASYNCを使用
3. **スキーマ管理**: カスタムスキーマの使用を推奨
4. **認証の使い分け**: adminとapp_userで異なるトークン生成コマンド
5. **権限の分離**: DDL操作とDML操作でロールを分ける

これらの知識を活用して、Aurora DSQLを効果的に活用していきましょう。

## 本記事で参照したドキュメント

### エラーログと解決策
- `terraform/sql/errorlog.md` - Aurora DSQLで発生したエラーの記録と基本的な解決策
- `terraform/sql/create_tables_dsql_v3.sql` - カスタムスキーマを使用した最終的なテーブル定義

### 権限管理関連
- `agent/data_access/aurora_dsql_permissions_solution.md` - publicスキーマの権限エラーと解決策
- `agent/data_access/aurora_dsql_final_solution.md` - カスタムスキーマを使用した最終解決方法

### 認証とロール設定
- `agent/data_access/aurora_dsql_token_generation_guide.md` - トークン生成コマンドの使い分けガイド
- `agent/data_access/aurora_dsql_custom_role_setup.md` - カスタムロールの設定手順

### 実装コード
- `agent/data_access/dsql_client.py` - Python実装でのAurora DSQL接続クライアント

## 参考リンク

- [Aurora DSQL Documentation](https://docs.aws.amazon.com/aurora-dsql/)
- [Aurora DSQL Known Limitations](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/known-limitations.html)
- [Aurora DSQL IAM Authentication](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/iam-authentication.html)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
