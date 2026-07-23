"""
起動時の軽量マイグレーション。

rinaresu は Alembic を使わず、起動時に Base.metadata.create_all() でテーブルを
作成する方式（TV_MVP の alembic 方式とは異なる）。create_all() は「無いテーブル」は
作るが、「既存テーブルへの列追加」はしない。そこで、既存 DB に対して
users / idols への新規列を冪等な ALTER TABLE で追加するのがこのモジュールの役割。

- 実行は毎起動。inspector で現在の列を確認し、無い列だけを追加する（冪等）。
- SQLite / PostgreSQL 両対応（boolean のデフォルト表記だけ dialect で分岐）。
- 新規テーブル（user_rewards）は create_all() 側で作られるため、ここでは扱わない。
- 新規 DB では create_all() が全列付きで作るため、ここは全て「列あり」となり no-op。

呼び出し順（main.py）: create_all() → run_migrations() → seed_all()
（seed は idols.is_limited を参照するため、列追加を seed より前に済ませる）
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _existing_columns(inspector, table_name: str) -> set[str]:
    """テーブルが存在すればその列名集合を、無ければ空集合を返す。"""
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def run_migrations(engine: Engine) -> list[str]:
    """不足している列を冪等に追加する。実行した DDL の一覧を返す（ログ・テスト用）。"""
    inspector = inspect(engine)
    is_postgres = engine.dialect.name == "postgresql"
    # boolean のリテラル既定値は方言で異なる（SQLite は 0/1、PostgreSQL は FALSE/TRUE）
    bool_false = "FALSE" if is_postgres else "0"

    user_cols = _existing_columns(inspector, "users")
    idol_cols = _existing_columns(inspector, "idols")

    ddl: list[str] = []

    # users への追加列（pt特典プログラム）
    if user_cols:  # users テーブルが既存の場合のみ ALTER（新規DBは create_all 済み）
        if "monthly_points" not in user_cols:
            ddl.append("ALTER TABLE users ADD COLUMN monthly_points INTEGER NOT NULL DEFAULT 0")
        if "monthly_period" not in user_cols:
            ddl.append("ALTER TABLE users ADD COLUMN monthly_period VARCHAR(7)")
        if "active_visual" not in user_cols:
            ddl.append("ALTER TABLE users ADD COLUMN active_visual VARCHAR(10) NOT NULL DEFAULT 'main'")
        if "prev_idol_id" not in user_cols:
            ddl.append("ALTER TABLE users ADD COLUMN prev_idol_id VARCHAR(30)")

    # idols への追加列（期間限定推しフラグ）
    if idol_cols:
        if "is_limited" not in idol_cols:
            ddl.append(f"ALTER TABLE idols ADD COLUMN is_limited BOOLEAN NOT NULL DEFAULT {bool_false}")

    if ddl:
        with engine.begin() as conn:
            for stmt in ddl:
                conn.execute(text(stmt))

    return ddl
