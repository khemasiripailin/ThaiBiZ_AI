from pathlib import Path
import re
from typing import Any

import duckdb
import pandas as pd
import streamlit as st

from data_loader import load_all_data


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "thaibiz.duckdb"


def _safe_table_name(name: Any) -> str:
    """แปลงชื่อ table/column ให้ปลอดภัยสำหรับ SQL"""
    name = str(name).strip().lower()
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = "col"
    if name[0].isdigit():
        name = f"t_{name}"
    return name


def _make_unique(names: list[str]) -> list[str]:
    """กันชื่อ column ซ้ำหลัง clean"""
    seen = {}
    out = []
    for n in names:
        base = _safe_table_name(n)
        if base not in seen:
            seen[base] = 0
            out.append(base)
        else:
            seen[base] += 1
            out.append(f"{base}_{seen[base]}")
    return out


def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
    """ทำความสะอาด DataFrame ก่อนโหลดเข้า DuckDB"""
    df = df.copy()
    df.columns = _make_unique(list(df.columns))

    # แปลง object ที่เป็นโครงสร้างซับซ้อนให้เป็น string กัน DuckDB cast error
    for c in df.columns:
        if df[c].dtype == "object":
            df[c] = df[c].apply(
                lambda x: str(x) if isinstance(x, (list, dict, tuple, set)) else x
            )

    return df


@st.cache_resource
def get_connection():
    """DuckDB connection แบบเก็บเป็นไฟล์ใน data/thaibiz.duckdb"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    return con


def table_exists(table_name: str) -> bool:
    con = get_connection()
    table_name = _safe_table_name(table_name)
    result = con.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = 'main'
          AND table_name = ?
        """,
        [table_name],
    ).fetchone()[0]
    return result > 0


def get_columns(table_name: str) -> list[str]:
    if not table_exists(table_name):
        return []
    con = get_connection()
    table_name = _safe_table_name(table_name)
    df = con.execute(f'DESCRIBE "{table_name}"').fetchdf()
    if df.empty or "column_name" not in df.columns:
        return []
    return df["column_name"].astype(str).tolist()


def _has_columns(table_name: str, required: list[str]) -> bool:
    cols = set(get_columns(table_name))
    return all(c in cols for c in required)


def refresh_database() -> dict:
    """
    โหลดข้อมูลจาก data_loader.load_all_data() เข้า DuckDB

    ผลลัพธ์:
    - สร้าง/แทนที่ตารางจาก DataFrame ทั้งหมดที่ load_all_data() คืนมา
    - สร้าง data_catalog
    - สร้าง views กลางสำหรับ query ง่ายขึ้น
    """
    con = get_connection()
    data = load_all_data()

    catalog_rows = []

    for raw_name, obj in data.items():
        if not isinstance(obj, pd.DataFrame):
            continue

        table_name = _safe_table_name(raw_name)
        df = _prepare_df(obj)

        if df.empty:
            catalog_rows.append({
                "table_name": table_name,
                "source_key": str(raw_name),
                "rows": 0,
                "columns": len(df.columns),
                "status": "empty_skipped",
            })
            continue

        temp_name = f"tmp_{table_name}"
        con.register(temp_name, df)
        con.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM "{temp_name}"')
        con.unregister(temp_name)

        catalog_rows.append({
            "table_name": table_name,
            "source_key": str(raw_name),
            "rows": len(df),
            "columns": len(df.columns),
            "status": "loaded",
        })

    catalog = pd.DataFrame(catalog_rows)
    if catalog.empty:
        catalog = pd.DataFrame(columns=["table_name", "source_key", "rows", "columns", "status"])

    con.register("tmp_data_catalog", catalog)
    con.execute("""
        CREATE OR REPLACE TABLE data_catalog AS
        SELECT * FROM tmp_data_catalog
    """)
    con.unregister("tmp_data_catalog")

    create_views()

    return {
        "db_path": str(DB_PATH),
        "tables": catalog,
    }


def create_views():
    """สร้าง view กลาง โดยสร้างเฉพาะเมื่อ table/column ที่จำเป็นมีอยู่จริง"""
    con = get_connection()

    if table_exists("province_monthly") and _has_columns(
        "province_monthly",
        ["year", "month_no", "month", "new_count", "closed_count"],
    ):
        # บางไฟล์อาจไม่มี net_growth/new_capital_m/active_count จึงใช้ CASE จาก column ที่มี
        cols = set(get_columns("province_monthly"))

        net_expr = "SUM(net_growth)" if "net_growth" in cols else "SUM(new_count - closed_count)"
        capital_expr = "SUM(new_capital_m)" if "new_capital_m" in cols else "NULL"
        active_expr = "SUM(active_count)" if "active_count" in cols else "NULL"

        con.execute(f"""
            CREATE OR REPLACE VIEW vw_monthly_overview AS
            SELECT
                year,
                month_no,
                month,
                SUM(new_count) AS total_new,
                SUM(closed_count) AS total_closed,
                {net_expr} AS total_net_growth,
                {capital_expr} AS total_new_capital_m,
                {active_expr} AS total_active_count,
                SUM(closed_count) * 100.0 / NULLIF(SUM(new_count), 0) AS closure_rate
            FROM province_monthly
            GROUP BY year, month_no, month
            ORDER BY year, month_no
        """)

    if table_exists("province_monthly") and _has_columns(
        "province_monthly",
        ["province", "year", "month_no", "new_count", "closed_count"],
    ):
        cols = set(get_columns("province_monthly"))
        net_expr = "p.net_growth" if "net_growth" in cols else "(p.new_count - p.closed_count)"
        active_expr = "p.active_count" if "active_count" in cols else "NULL"
        capital_expr = "p.new_capital_m" if "new_capital_m" in cols else "NULL"

        con.execute(f"""
            CREATE OR REPLACE VIEW vw_province_latest_rank AS
            WITH latest_period AS (
                SELECT year, month_no
                FROM province_monthly
                ORDER BY year DESC, month_no DESC
                LIMIT 1
            )
            SELECT
                p.province,
                p.year,
                p.month_no,
                p.month,
                p.new_count,
                p.closed_count,
                {net_expr} AS net_growth,
                {active_expr} AS active_count,
                {capital_expr} AS new_capital_m,
                p.closed_count * 100.0 / NULLIF(p.new_count, 0) AS closure_rate_calc
            FROM province_monthly p
            JOIN latest_period l
              ON p.year = l.year
             AND p.month_no = l.month_no
        """)

    if table_exists("business_2569"):
        cols = set(get_columns("business_2569"))
        if {"type", "regis_count"}.issubset(cols):
            business_group_expr = "business_group" if "business_group" in cols else "'ไม่ระบุกลุ่ม'"
            quit_expr = "quit_count" if "quit_count" in cols else "0"
            active_expr = "active_count" if "active_count" in cols else "0"
            capital_expr = "regis_capital_m" if "regis_capital_m" in cols else "NULL"
            opp_expr = "opportunity_score" if "opportunity_score" in cols else "NULL"

            con.execute(f"""
                CREATE OR REPLACE VIEW vw_business_opportunity AS
                SELECT
                    type,
                    {business_group_expr} AS business_group,
                    regis_count,
                    {quit_expr} AS quit_count,
                    {active_expr} AS active_count,
                    {capital_expr} AS regis_capital_m,
                    {quit_expr} * 100.0 / NULLIF(regis_count, 0) AS closure_rate_calc,
                    {capital_expr} / NULLIF(regis_count, 0) AS avg_capital_m_calc,
                    {opp_expr} AS opportunity_score
                FROM business_2569
            """)


def list_tables() -> pd.DataFrame:
    con = get_connection()
    return con.execute("""
        SELECT
            table_name,
            table_type
        FROM information_schema.tables
        WHERE table_schema = 'main'
        ORDER BY
            CASE WHEN table_name = 'data_catalog' THEN 0 ELSE 1 END,
            table_name
    """).fetchdf()


def describe_table(table_name: str) -> pd.DataFrame:
    con = get_connection()
    table_name = _safe_table_name(table_name)
    return con.execute(f'DESCRIBE "{table_name}"').fetchdf()


def preview_table(table_name: str, limit: int = 20) -> pd.DataFrame:
    con = get_connection()
    table_name = _safe_table_name(table_name)
    limit = int(limit)
    return con.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}').fetchdf()


def run_sql(sql: str) -> pd.DataFrame:
    con = get_connection()
    return con.execute(sql).fetchdf()


def query_df(sql: str, params=None) -> pd.DataFrame:
    con = get_connection()
    if params is None:
        params = []
    return con.execute(sql, params).fetchdf()


# ============================================================
# DuckDB-backed loaders for app pages
# ============================================================

def database_has_data() -> bool:
    """เช็กว่า DuckDB มี data_catalog และมี table ที่โหลดแล้วหรือยัง"""
    try:
        if not table_exists("data_catalog"):
            return False
        cat = query_df("""
            SELECT COUNT(*) AS n
            FROM data_catalog
            WHERE status = 'loaded'
              AND rows > 0
        """)
        return int(cat.iloc[0]["n"]) > 0
    except Exception:
        return False


def ensure_database_ready(auto_refresh: bool = True) -> bool:
    """
    ให้ทุกหน้าเรียกฟังก์ชันนี้ก่อนใช้ DuckDB
    - ถ้า DuckDB มีข้อมูลแล้ว จะไม่ทำอะไร
    - ถ้ายังไม่มี และ auto_refresh=True จะโหลดจาก data_loader เข้า DuckDB ให้
    """
    if database_has_data():
        return True
    if not auto_refresh:
        return False
    try:
        refresh_database()
        return database_has_data()
    except Exception:
        return False


@st.cache_data(show_spinner=False)
def load_all_data_from_duckdb(auto_refresh: bool = True) -> dict:
    """
    คืนค่า dict เหมือน data_loader.load_all_data()
    แต่ดึงจาก DuckDB data_catalog/table ที่ refresh ไว้แล้ว

    ถ้า DuckDB ยังไม่พร้อม จะ fallback ไปใช้ data_loader.load_all_data()
    เพื่อไม่ให้หน้าอื่นพัง
    """
    ready = ensure_database_ready(auto_refresh=auto_refresh)
    if not ready:
        return load_all_data()

    try:
        cat = query_df("""
            SELECT table_name, source_key
            FROM data_catalog
            WHERE status = 'loaded'
            ORDER BY table_name
        """)
        if cat.empty:
            return load_all_data()

        out = {}
        for r in cat.itertuples(index=False):
            table_name = str(r.table_name)
            source_key = str(r.source_key)
            try:
                out[source_key] = query_df(f'SELECT * FROM "{table_name}"')
            except Exception:
                pass

        if not out:
            return load_all_data()
        return out

    except Exception:
        return load_all_data()


@st.cache_data(show_spinner=False)
def load_business_metrics_duckdb(year: int = 2569) -> pd.DataFrame:
    """
    ใช้แทน data_loader.load_business_metrics(year)
    โดยดึงจาก DuckDB table business_2569 / business_2568 ก่อน
    ถ้าไม่มีค่อย fallback ไป data_loader.load_business_metrics
    """
    ensure_database_ready(auto_refresh=True)
    table_name = f"business_{year}"

    try:
        if table_exists(table_name):
            return query_df(f'SELECT * FROM "{table_name}"')
    except Exception:
        pass

    try:
        from data_loader import load_business_metrics
        return load_business_metrics(year)
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_table_duckdb(table_name: str, fallback_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """ดึง table จาก DuckDB แบบปลอดภัย"""
    ensure_database_ready(auto_refresh=True)
    try:
        t = _safe_table_name(table_name)
        if table_exists(t):
            return query_df(f'SELECT * FROM "{t}"')
    except Exception:
        pass
    if fallback_df is not None:
        return fallback_df
    return pd.DataFrame()
