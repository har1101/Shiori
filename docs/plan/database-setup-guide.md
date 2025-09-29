# データベースセットアップガイド

## Aurora DSQLのセットアップ手順

### 1. Aurora DSQLクラスターの作成

#### AWSコンソールから作成する場合

1. AWSコンソールにログイン
2. RDSサービスに移動
3. 「データベースの作成」をクリック
4. エンジンタイプで「Aurora DSQL」を選択
5. 必要な設定を入力（クラスター名、認証情報など）

#### Terraformで作成する場合（推奨）

後述のシステムアーキテクチャ設計で、Terraformでの構築方法を含めます。

### 2. データベースへの接続方法

#### 方法1: psqlコマンドを使用

```bash
# Aurora DSQLのエンドポイントに接続
psql -h your-cluster-endpoint.dsql.us-east-1.on.aws -U admin -d postgres

# データベースを作成
CREATE DATABASE jr_champions_activities;

# 作成したデータベースに接続
\c jr_champions_activities

# SQLファイルを実行
\i /path/to/sql-definitions.sql
```

#### 方法2: AWS Systems Manager Session Managerを使用

セキュアな接続方法として推奨されます。

#### 方法3: Lambda関数で初期化（自動化）

```python
import psycopg2
import os

def initialize_database():
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        database='jr_champions_activities',
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD']
    )
    
    with conn.cursor() as cur:
        # SQLファイルを読み込んで実行
        with open('sql-definitions.sql', 'r') as f:
            cur.execute(f.read())
    
    conn.commit()
    conn.close()
```

### 3. 実行するSQLファイルの準備

`sql-definitions.sql`として、以下の順序でSQLをまとめます：

1. データベース作成（必要な場合）
2. テーブル作成（Members → Activities → MonthlyReports → ProcessingHistory）
3. インデックス作成
4. トリガー作成
5. 初期データ投入（開発環境のみ）

### 4. 環境別の管理

#### 開発環境

- ローカルのPostgreSQLでも動作確認可能
- Dockerでの環境構築も可能

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: jr_champions_activities
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - ./sql-definitions.sql:/docker-entrypoint-initdb.d/init.sql
```

#### 本番環境

- AWS Secrets Managerで認証情報を管理
- Terraformでインフラをコード化
- CI/CDパイプラインでのマイグレーション実行

### 5. 推奨される実装方法

プロジェクトの性質を考慮すると、以下のアプローチがおすすめです：

1. **初回セットアップ**
   - TerraformでAurora DSQLクラスターを作成
   - Lambda関数でテーブル初期化を自動実行

2. **継続的な運用**
   - マイグレーションツール（例：Flyway、migrate）の導入
   - バージョン管理されたSQLファイルで変更を管理

3. **開発時**
   - ローカルPostgreSQLで開発
   - 本番相当の環境でテスト

このアプローチにより、手動作業を最小限に抑え、再現性のある環境構築が可能になります。
