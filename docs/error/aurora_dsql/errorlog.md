# Aurora DSQL エラーログと解決策

## 発生したエラーと対処法

### 1. JSON/JSONBデータ型がサポートされていない

**エラーメッセージ:**
```
ERROR:  datatype jsonb not supported
ERROR:  datatype json not supported
```

**原因:**
Aurora DSQLは現時点でJSON/JSONBデータ型をサポートしていません。

**解決策:**
- JSON/JSONB型をTEXT型に変更
- アプリケーション側でJSONのパース/シリアライズを実装
- Python例：
  ```python
  import json
  # 保存時
  json_string = json.dumps(data)
  # 読み取り時
  data = json.loads(json_string) if json_string else {}
  ```

### 2. CREATE INDEX構文エラー

**エラーメッセージ:**
```
ERROR:  syntax error at or near "INDEX"
```

**原因:**
Aurora DSQLは通常のCREATE INDEXをサポートせず、非同期インデックス作成が必要。

**解決策:**
```sql
-- 通常のPostgreSQL
CREATE INDEX idx_name ON table_name(column_name);

-- Aurora DSQL
CREATE INDEX ASYNC idx_name ON table_name(column_name);
```

### 3. PL/pgSQL関数がサポートされていない

**エラーメッセージ:**
```
ERROR:  language "plpgsql" does not exist
```

**原因:**
Aurora DSQLはストアドプロシージャやトリガーをサポートしていません。

**解決策:**
- トリガーとして実装していた機能をアプリケーション層に移動
- 例：updated_atの自動更新をPython側で実装

### 4. ::json キャストエラー

**エラーメッセージ:**
```
ERROR:  cannot cast type text to json
```

**原因:**
JSON型が存在しないため、キャスト演算子も使用できません。

**解決策:**
- SQLでのキャストを削除
- Python側でjson.dumps()を使用してTEXT型として保存

## Aurora DSQLの主な制限事項

1. **サポートされていないデータ型:**
   - JSONB
   - JSON
   - 配列型
   - 複合型
   - 範囲型

2. **サポートされていない機能:**
   - PL/pgSQL関数とトリガー
   - マテリアライズドビュー
   - パーティショニング
   - 外部テーブル
   - 全文検索（tsvector/tsquery）

3. **インデックス制限:**
   - CREATE INDEX ASYNC必須
   - 部分インデックスサポート制限あり
   - GINインデックスなし（JSONBがないため）

## 移行時の推奨事項

1. **JSON処理:**
   - データベース側：TEXT型で保存
   - アプリケーション側：JSON処理を実装
   - インデックスが必要な場合：重要なフィールドを別カラムに展開

2. **自動更新フィールド:**
   - トリガーの代わりにORMまたはアプリケーション層で実装
   - 例：SQLAlchemyのbefore_updateイベント使用

3. **パフォーマンス最適化:**
   - JSON検索が必要な場合、検索用の正規化テーブルを検討
   - 頻繁にアクセスされるJSON属性は別カラムとして定義

## 参考リンク

- [Aurora DSQL Documentation](https://docs.aws.amazon.com/aurora-dsql/)
- [Aurora DSQL Known Limitations](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/known-limitations.html)
