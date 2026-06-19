import time

import pandas as pd
import streamlit as st

from db import (
    refresh_database,
    list_tables,
    describe_table,
    preview_table,
    run_sql,
)


st.set_page_config(page_title="DuckDB SQL", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.25rem; padding-bottom: 2rem;}
    .hero-card {
        background: linear-gradient(135deg, rgba(76,29,149,0.70), rgba(15,23,42,0.96));
        border: 1px solid rgba(167,139,250,0.28);
        border-radius: 22px;
        padding: 1.25rem 1.35rem;
        margin-bottom: 1rem;
    }
    .hero-title {font-size: 2rem; font-weight: 850; color:#f8fafc; margin-bottom:.25rem;}
    .hero-sub {font-size: 1rem; color:#e2e8f0;}
    .glass-card {
        background: linear-gradient(135deg, rgba(15,23,42,0.82), rgba(15,23,42,0.98));
        border: 1px solid rgba(148,163,184,0.20);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        margin: .6rem 0 .9rem 0;
    }
    .section-eyebrow {
        color:#22d3ee; font-size:.78rem; font-weight:850; letter-spacing:.08em;
        text-transform:uppercase; margin-bottom:.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-title">🦆 DuckDB SQL Explorer</div>
        <div class="hero-sub">โหลดข้อมูลทั้งหมดจาก data_loader.py เข้า DuckDB แล้ว query ด้วย SQL ได้โดยตรง</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Database Control
# ============================================================
left, right = st.columns([1, 2.2])

with left:
    st.markdown("### 1) Database Control")

    if st.button("🔄 Refresh DuckDB จาก data_loader", use_container_width=True, type="primary"):
        try:
            started = time.perf_counter()
            with st.spinner("กำลังโหลดข้อมูลทั้งหมดจาก data_loader.py เข้า DuckDB..."):
                result = refresh_database()
            elapsed = time.perf_counter() - started

            st.success(f"โหลดข้อมูลเข้า DuckDB สำเร็จใน {elapsed:.2f} วินาที")
            st.caption(f"DB path: {result['db_path']}")
            st.session_state["duckdb_last_refresh"] = time.strftime("%Y-%m-%d %H:%M:%S")
            st.session_state["duckdb_refresh_result"] = result["tables"]

        except Exception as e:
            st.error(f"Refresh DuckDB ไม่สำเร็จ: {e}")

    if "duckdb_last_refresh" in st.session_state:
        st.info(f"Refresh ล่าสุด: {st.session_state['duckdb_last_refresh']}")

    with st.expander("วิธีใช้หน้านี้", expanded=False):
        st.markdown(
            """
            1. กด **Refresh DuckDB จาก data_loader** ก่อน  
            2. ดูว่า table เข้า DuckDB แล้วในหัวข้อ Tables  
            3. เขียน SQL หรือเลือกตัวอย่าง query  
            4. กด **Run SQL** เพื่อดูผลลัพธ์
            """
        )

with right:
    st.markdown("### 2) Tables in DuckDB")
    try:
        tables = list_tables()
        if tables.empty:
            st.warning("ยังไม่มี table ใน DuckDB ให้กด Refresh DuckDB ก่อน")
        else:
            st.dataframe(tables, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning(f"ยังอ่านรายชื่อ table ไม่ได้: {e}")
        tables = pd.DataFrame()

    if "duckdb_refresh_result" in st.session_state:
        with st.expander("ตารางที่โหลดเข้ารอบล่าสุด", expanded=False):
            st.dataframe(st.session_state["duckdb_refresh_result"], use_container_width=True, hide_index=True)


# ============================================================
# Table Inspector
# ============================================================
st.markdown("---")
st.markdown("### 3) Table Inspector")

try:
    table_options = list_tables()
except Exception:
    table_options = pd.DataFrame()

if table_options.empty:
    st.info("ยังไม่มี table ให้ inspect")
else:
    names = table_options["table_name"].astype(str).tolist()
    selected_table = st.selectbox("เลือก table/view เพื่อดู schema และ preview", names)

    c1, c2 = st.columns([1, 1.4])
    with c1:
        st.markdown("#### Schema")
        try:
            st.dataframe(describe_table(selected_table), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Describe table ไม่ได้: {e}")

    with c2:
        st.markdown("#### Preview")
        preview_n = st.slider("จำนวน row preview", 5, 100, 20, step=5)
        try:
            st.dataframe(preview_table(selected_table, preview_n), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Preview table ไม่ได้: {e}")


# ============================================================
# SQL Explorer
# ============================================================
st.markdown("---")
st.markdown("### 4) SQL Query")

example_queries = {
    "ดู catalog ของข้อมูลทั้งหมด": """
SELECT *
FROM data_catalog
ORDER BY table_name;
""".strip(),
    "แนวโน้มรายเดือนภาพรวม": """
SELECT *
FROM vw_monthly_overview
ORDER BY year, month_no;
""".strip(),
    "Top จังหวัดล่าสุดตาม Net Growth": """
SELECT
    province,
    year,
    month,
    new_count,
    closed_count,
    net_growth,
    active_count,
    closure_rate_calc
FROM vw_province_latest_rank
ORDER BY net_growth DESC
LIMIT 10;
""".strip(),
    "Top ธุรกิจ Opportunity": """
SELECT
    type,
    business_group,
    regis_count,
    quit_count,
    closure_rate_calc,
    avg_capital_m_calc,
    opportunity_score
FROM vw_business_opportunity
WHERE regis_count > 0
ORDER BY opportunity_score DESC
LIMIT 20;
""".strip(),
    "ธุรกิจทุนเฉลี่ยไม่เกิน 1 ล้านบาท": """
SELECT
    type,
    business_group,
    regis_count,
    avg_capital_m_calc,
    closure_rate_calc,
    opportunity_score
FROM vw_business_opportunity
WHERE regis_count > 0
  AND avg_capital_m_calc <= 1
ORDER BY opportunity_score DESC
LIMIT 20;
""".strip(),
}

selected_example = st.selectbox("เลือกตัวอย่าง SQL", list(example_queries.keys()), key="duckdb_example_select")
# เปลี่ยน dropdown แล้วให้ SQL เปลี่ยนตามทันที ไม่ต้องกดปุ่มซ้ำ
if st.session_state.get("duckdb_last_example") != selected_example:
    st.session_state["duckdb_sql_text"] = example_queries[selected_example]
    st.session_state["duckdb_last_example"] = selected_example

col_a, col_b = st.columns([1, 4])
with col_a:
    if st.button("ใส่ SQL ตัวอย่างนี้", use_container_width=True):
        st.session_state["duckdb_sql_text"] = example_queries[selected_example]
        st.session_state["duckdb_last_example"] = selected_example

with col_b:
    st.caption("เลือกตัวอย่างแล้ว SQL จะเปลี่ยนตามทันที หรือเขียน SQL เองได้เลย")

sql = st.text_area(
    "เขียน SQL ตรงนี้",
    key="duckdb_sql_text",
    height=240,
)

if st.button("▶️ Run SQL", use_container_width=True, type="primary"):
    try:
        started = time.perf_counter()
        df = run_sql(sql)
        elapsed = time.perf_counter() - started

        st.success(f"Query สำเร็จ: {len(df):,} rows · {elapsed:.3f} วินาที")
        st.dataframe(df, use_container_width=True, hide_index=True)

        if not df.empty:
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Download result as CSV",
                data=csv,
                file_name="duckdb_query_result.csv",
                mime="text/csv",
                use_container_width=True,
            )

    except Exception as e:
        st.error(f"SQL Error: {e}")


# ============================================================
# Teaching note
# ============================================================
st.markdown("---")
st.markdown(
    """
    <div class="glass-card">
        <div class="section-eyebrow">Presentation Note</div>
        <b>DuckDB ในโปรเจกต์นี้ทำหน้าที่เป็น analytical SQL engine</b><br>
        ข้อมูลจากไฟล์ DBD ถูกอ่านและทำความสะอาดด้วย <code>data_loader.py</code> ก่อน
        จากนั้นโหลดเข้า DuckDB เป็น table กลาง เพื่อให้หน้า SQL Explorer, dashboard และ AI Advisor query ข้อมูลซ้ำได้อย่างเป็นระบบ
    </div>
    """,
    unsafe_allow_html=True,
)
