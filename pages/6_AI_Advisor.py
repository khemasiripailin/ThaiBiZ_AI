import os
import re
import textwrap
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from db import ensure_database_ready, load_all_data_from_duckdb as load_all_data
    ensure_database_ready(auto_refresh=True)
except Exception as e:
    try:
        from data_loader import load_all_data
    except Exception as e2:
        st.error(f"ไม่สามารถเชื่อม DuckDB หรือ import load_all_data จาก data_loader.py ได้: {e} / {e2}")
        st.stop()

# ============================================================
# Theme
# ============================================================
PRIMARY = "#a855f7"
PINK = "#ec4899"
CYAN = "#22d3ee"
GREEN = "#22c55e"
YELLOW = "#f59e0b"
RED = "#ef4444"
BLUE = "#38bdf8"
WHITE = "#f8fafc"
MUTED = "#94a3b8"
PLOT_BG = "#020817"
GRID = "rgba(148,163,184,0.16)"

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
    .hero-card {
        background: linear-gradient(135deg, rgba(76,29,149,0.70), rgba(15,23,42,0.96));
        border: 1px solid rgba(167,139,250,0.28);
        border-radius: 22px;
        padding: 1.25rem 1.35rem;
        margin-bottom: 1.2rem;
    }
    .hero-title {font-size: 2rem; font-weight: 850; color:#f8fafc; margin-bottom:.25rem;}
    .hero-sub {font-size: 1rem; color:#e2e8f0;}
    .pill {
        display:inline-block; padding:.28rem .64rem; border-radius:999px;
        background:rgba(124,58,237,.50); border:1px solid rgba(192,132,252,.38);
        color:#fff; font-size:.78rem; margin:.55rem .28rem 0 0;
    }
    .answer-card {
        background: #171717;
        border: 1px solid rgba(148,163,184,.20);
        border-radius: 22px;
        padding: 1.15rem 1.3rem;
        margin-top: .85rem;
        color: #f8fafc;
        box-shadow: 0 10px 30px rgba(0,0,0,.25);
    }
    .answer-card h3 {font-size: 1.05rem; margin-top: 1.05rem; color:#f8fafc;}
    .answer-card ul {margin-top:.25rem;}
    .answer-card li {margin-bottom:.42rem; line-height:1.55;}
    .metric-card {
        background: rgba(15,23,42,.72);
        border: 1px solid rgba(96,165,250,.18);
        border-radius: 16px; padding:.85rem .95rem; min-height:92px;
    }
    .metric-label {font-size:.74rem;color:#93c5fd;text-transform:uppercase;letter-spacing:.06em}
    .metric-value {font-size:1.55rem;font-weight:850;color:#fff;margin-top:.15rem}
    .metric-sub {font-size:.83rem;color:#cbd5e1;margin-top:.2rem}
    .source-note {color:#94a3b8;font-size:.86rem;line-height:1.55;margin-top:.4rem;}
    div[data-testid="stButton"] > button {
        width: 100%; border: 1px solid rgba(148,163,184,.36);
        background: rgba(15,23,42,.72); color: #f8fafc;
        border-radius: 10px; min-height: 2.5rem;
    }
    div[data-testid="stButton"] > button:hover {border-color: rgba(34,211,238,.65); color:#67e8f9;}
    </style>
    """,
    unsafe_allow_html=True,
)


def fmt_num(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "0"


def fmt_float(x, digits=2):
    try:
        if pd.isna(x):
            return "ไม่พบข้อมูล"
        return f"{float(x):,.{digits}f}"
    except Exception:
        return "ไม่พบข้อมูล"


def wrap_label(txt, width=32, max_lines=3):
    parts = textwrap.wrap(str(txt), width=width, break_long_words=False, break_on_hyphens=False)
    if len(parts) > max_lines:
        parts = parts[:max_lines]
        parts[-1] += "…"
    return "<br>".join(parts)


def safe_numeric(df, cols):
    if df is None or df.empty:
        return df
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def normalize_0_100(s, inverse=False):
    s = pd.to_numeric(s, errors="coerce").fillna(0)
    mn, mx = float(s.min()), float(s.max())
    if mx == mn:
        out = pd.Series(np.full(len(s), 50.0), index=s.index)
    else:
        out = (s - mn) / (mx - mn) * 100
    if inverse:
        out = 100 - out
    return out.clip(0, 100)


def metric_card(label, value, sub):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def plot_style(fig, height=430, showlegend=True):
    fig.update_layout(
        height=height,
        paper_bgcolor=PLOT_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=WHITE, family="Arial"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=55, b=25),
        showlegend=showlegend,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID, tickfont=dict(color=WHITE), title_font=dict(color=WHITE))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=WHITE), title_font=dict(color=WHITE))
    return fig


@st.cache_data(show_spinner=False)
def get_project_data():
    data = load_all_data()
    biz = data.get("business_2569", pd.DataFrame()).copy()
    prov_monthly = data.get("province_monthly", pd.DataFrame()).copy()
    prov_latest = data.get("province_latest", pd.DataFrame()).copy()

    if not biz.empty:
        num_cols = [
            "regis_count", "quit_count", "active_count", "regis_capital_m",
            "size_s_count", "size_m_count", "size_l_count", "opportunity_score",
            "closure_rate", "survival_rate", "avg_capital_m"
        ]
        biz = safe_numeric(biz, num_cols)
        if "type" not in biz.columns:
            for alt in ["business_type", "objective", "name"]:
                if alt in biz.columns:
                    biz["type"] = biz[alt].astype(str)
                    break
        if "business_group" not in biz.columns:
            biz["business_group"] = "ไม่ระบุกลุ่ม"
        for c in ["regis_count", "quit_count", "active_count", "regis_capital_m"]:
            if c not in biz.columns:
                biz[c] = 0

        biz["closure_rate"] = np.where(biz["regis_count"] > 0, biz["quit_count"] * 100 / biz["regis_count"], np.nan)
        biz["survival_rate"] = np.where((biz["active_count"] + biz["quit_count"]) > 0, biz["active_count"] * 100 / (biz["active_count"] + biz["quit_count"]), np.nan)
        biz["avg_capital_m"] = np.where(biz["regis_count"] > 0, biz["regis_capital_m"] / biz["regis_count"], np.nan)

        s_cols = [c for c in ["size_s_count", "size_m_count", "size_l_count"] if c in biz.columns]
        if s_cols:
            biz["sme_total"] = biz[s_cols].sum(axis=1)
            biz["sme_fit_raw"] = np.where(biz["sme_total"] > 0, biz.get("size_s_count", 0) / biz["sme_total"] * 100, 0)
        else:
            biz["sme_fit_raw"] = 50

        demand = normalize_0_100(biz["regis_count"])
        survival = pd.to_numeric(biz["survival_rate"], errors="coerce")
        survival = survival.fillna(survival.median(skipna=True) if survival.notna().any() else 50).clip(0, 100)
        sme_fit = pd.to_numeric(biz["sme_fit_raw"], errors="coerce").fillna(50).clip(0, 100)
        capital_ready = normalize_0_100(biz["avg_capital_m"].fillna(0), inverse=True)
        competition = normalize_0_100(biz["active_count"].fillna(0))
        biz["opportunity_score_calc"] = (0.30 * demand + 0.35 * survival + 0.20 * sme_fit + 0.15 * capital_ready - 0.15 * competition).clip(0, 100)
        if "opportunity_score" not in biz.columns or biz["opportunity_score"].isna().all():
            biz["opportunity_score"] = biz["opportunity_score_calc"]

    if not prov_monthly.empty:
        prov_monthly = safe_numeric(prov_monthly, ["year", "month_no", "new_count", "closed_count", "net_growth", "new_capital_m", "active_count"])
        if {"year", "month_no"}.issubset(prov_monthly.columns):
            latest_period = prov_monthly.sort_values(["year", "month_no"]).tail(1)[["year", "month_no"]].iloc[0]
            latest_view = prov_monthly[(prov_monthly["year"] == latest_period["year"]) & (prov_monthly["month_no"] == latest_period["month_no"])].copy()
        else:
            latest_view = prov_monthly.copy()
    elif not prov_latest.empty:
        latest_view = prov_latest.copy()
    else:
        latest_view = pd.DataFrame()

    if not latest_view.empty:
        latest_view = safe_numeric(latest_view, ["new_count", "closed_count", "net_growth", "new_capital_m", "active_count"])
        if "closure_rate" not in latest_view.columns and {"new_count", "closed_count"}.issubset(latest_view.columns):
            latest_view["closure_rate"] = np.where(latest_view["new_count"] > 0, latest_view["closed_count"] * 100 / latest_view["new_count"], np.nan)
        if "net_growth" not in latest_view.columns and {"new_count", "closed_count"}.issubset(latest_view.columns):
            latest_view["net_growth"] = latest_view["new_count"] - latest_view["closed_count"]

    return {"biz": biz, "province_latest": latest_view, "province_monthly": prov_monthly}


data = get_project_data()
biz = data["biz"]
province_latest = data["province_latest"]


def budget_filter(df, budget_text):
    if df.empty or "avg_capital_m" not in df.columns or budget_text == "ไม่ระบุ":
        return df
    d = df.copy()
    if budget_text == "ไม่เกิน 1 ล้านบาท":
        return d[(d["avg_capital_m"].isna()) | (d["avg_capital_m"] <= 1)]
    if budget_text == "1–10 ล้านบาท":
        return d[(d["avg_capital_m"].isna()) | ((d["avg_capital_m"] > 1) & (d["avg_capital_m"] <= 10))]
    if budget_text == "มากกว่า 10 ล้านบาท":
        return d[(d["avg_capital_m"].isna()) | (d["avg_capital_m"] > 10)]
    return d


def risk_filter(df, risk_text):
    if df.empty or "closure_rate" not in df.columns:
        return df
    d = df.copy()
    valid = d["closure_rate"].dropna()
    if valid.empty:
        return d
    q50 = valid.quantile(0.50)
    q75 = valid.quantile(0.75)
    if risk_text == "ต่ำ":
        return d[(d["closure_rate"].isna()) | (d["closure_rate"] <= q50)]
    if risk_text == "กลาง":
        return d[(d["closure_rate"].isna()) | (d["closure_rate"] <= q75)]
    return d


def build_filtered_biz(goal, budget, risk, group):
    if biz.empty:
        return pd.DataFrame()
    d = biz.copy()
    if group != "ยังไม่แน่ใจ" and "business_group" in d.columns:
        d = d[d["business_group"] == group]
    d = budget_filter(d, budget)
    d = risk_filter(d, risk)
    if "regis_count" in d.columns:
        d = d[d["regis_count"].fillna(0) > 0]
    return d


def top_recommendations(goal, budget, risk, group, n=10):
    d = build_filtered_biz(goal, budget, risk, group)
    if d.empty:
        return d
    sort_cols = ["opportunity_score", "regis_count"]
    asc = [False, False]
    if goal == "ลดความเสี่ยง":
        sort_cols = ["closure_rate", "opportunity_score"]
        asc = [True, False]
    elif goal == "หาธุรกิจทุนต่ำ":
        sort_cols = ["avg_capital_m", "opportunity_score"]
        asc = [True, False]
    elif goal == "หา SME ที่เหมาะเริ่มต้น":
        sort_cols = ["sme_fit_raw", "opportunity_score"]
        asc = [False, False]
    return d.sort_values(sort_cols, ascending=asc).head(n)


def top_provinces(area, n=5):
    if province_latest.empty or "province" not in province_latest.columns:
        return pd.DataFrame()
    d = province_latest.copy()
    if area != "ทั้งประเทศ":
        d = d[d["province"] == area]
    if "net_growth" in d.columns:
        d = d.sort_values(["net_growth", "new_count"], ascending=False)
    elif "new_count" in d.columns:
        d = d.sort_values("new_count", ascending=False)
    return d.head(n)


def make_evidence_chart(rec_df):
    if rec_df.empty:
        fig = go.Figure()
        fig.add_annotation(text="ยังไม่มีข้อมูลพอสำหรับกราฟหลักฐาน", x=.5, y=.5, showarrow=False)
        return plot_style(fig, height=360, showlegend=False)
    show = rec_df.head(10).copy()
    show["label"] = show["type"].astype(str).apply(lambda x: wrap_label(x, width=32, max_lines=3))
    fig = px.bar(
        show.sort_values("opportunity_score"),
        x="opportunity_score",
        y="label",
        orientation="h",
        text="opportunity_score",
        color_discrete_sequence=[PRIMARY],
        title="Top recommended categories"
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig.update_xaxes(title="Opportunity score")
    fig.update_yaxes(title="ประเภทธุรกิจ")
    return plot_style(fig, height=max(420, len(show) * 40 + 120), showlegend=False)


def data_context_for_prompt(goal, budget, risk, group, area, question):
    rec = top_recommendations(goal, budget, risk, group, n=8)
    prov = top_provinces(area, n=5)
    lines = []
    lines.append("คุณคือ AI Business Advisor ใน dashboard วิเคราะห์ข้อมูลธุรกิจไทยจากไฟล์ DBD ของโปรเจกต์นี้")
    lines.append("ห้ามแต่งตัวเลข ห้ามอ้างข้อมูลที่ไม่มีใน context ถ้าข้อมูลไม่พอให้บอกว่าข้อมูลไม่เพียงพอ")
    lines.append(f"คำถามผู้ใช้: {question}")
    lines.append(f"เงื่อนไขผู้ใช้: เป้าหมาย={goal}, เงินทุน={budget}, รับความเสี่ยงได้={risk}, กลุ่มธุรกิจ={group}, พื้นที่={area}")
    lines.append("")
    lines.append("Top business evidence:")
    if rec.empty:
        lines.append("- ไม่มีรายการธุรกิจที่ผ่านตัวกรอง")
    else:
        for i, r in enumerate(rec.itertuples(), start=1):
            lines.append(
                f"{i}. {getattr(r, 'type', '-')}: group={getattr(r, 'business_group', '-')}, "
                f"opportunity={fmt_float(getattr(r, 'opportunity_score', np.nan),1)}, "
                f"regis={fmt_num(getattr(r, 'regis_count', 0))}, "
                f"closure={fmt_float(getattr(r, 'closure_rate', np.nan))}%, "
                f"avg_capital={fmt_float(getattr(r, 'avg_capital_m', np.nan))} ลบ./ราย"
            )
    lines.append("")
    lines.append("Top province evidence:")
    if prov.empty:
        lines.append("- ไม่มีข้อมูลจังหวัดที่ผ่านตัวกรอง")
    else:
        for i, r in enumerate(prov.itertuples(), start=1):
            lines.append(
                f"{i}. {getattr(r, 'province', '-')}: new={fmt_num(getattr(r, 'new_count', 0))}, "
                f"closed={fmt_num(getattr(r, 'closed_count', 0))}, "
                f"net={fmt_num(getattr(r, 'net_growth', 0))}, "
                f"closure_rate={fmt_float(getattr(r, 'closure_rate', np.nan))}%"
            )
    lines.append("")
    lines.append("ตอบเป็นภาษาไทย และบังคับ format นี้เท่านั้น:")
    lines.append("คำแนะนำหลัก:")
    lines.append("...")
    lines.append("")
    lines.append("เหตุผลจากข้อมูล:")
    lines.append("1. ...")
    lines.append("2. ...")
    lines.append("3. ...")
    lines.append("")
    lines.append("ความเสี่ยงที่ควรระวัง:")
    lines.append("...")
    lines.append("")
    lines.append("จังหวัด/ธุรกิจที่แนะนำ:")
    lines.append("1. ...")
    lines.append("2. ...")
    lines.append("3. ...")
    lines.append("")
    lines.append("Next Step:")
    lines.append("ควรไปดูกราฟหน้า Category / Survival / Province ต่อ ...")
    return "\n".join(lines)


def fallback_answer(goal, budget, risk, group, area, question):
    rec = top_recommendations(goal, budget, risk, group, n=5)
    prov = top_provinces(area, n=5)
    if rec.empty and prov.empty:
        return """
คำแนะนำหลัก:
ข้อมูลที่ผ่านตัวกรองยังไม่เพียงพอ จึงยังไม่ควรสรุปว่าควรทำธุรกิจใดในตอนนี้

เหตุผลจากข้อมูล:
1. ไม่พบธุรกิจที่ผ่านเงื่อนไขเป้าหมาย เงินทุน ความเสี่ยง และกลุ่มธุรกิจที่เลือก
2. ระบบไม่สร้างตัวเลขแทนข้อมูลที่ไม่มี เพื่อป้องกันการตัดสินใจผิด
3. ควรผ่อนตัวกรอง เช่น เลือกกลุ่มธุรกิจเป็น "ยังไม่แน่ใจ" หรือเงินทุนเป็น "ไม่ระบุ"

ความเสี่ยงที่ควรระวัง:
ข้อมูลน้อยเกินไปอาจทำให้เห็นภาพตลาดผิด ควรดูข้อมูลเพิ่มก่อนตัดสินใจ

จังหวัด/ธุรกิจที่แนะนำ:
1. ยังไม่มีคำแนะนำจากข้อมูลที่ผ่านตัวกรอง
2. ลองเปลี่ยนตัวกรองพื้นที่หรือกลุ่มธุรกิจ
3. ตรวจสอบไฟล์ข้อมูลในหน้า Raw Data / DuckDB

Next Step:
ควรไปดูกราฟหน้า Category / Survival / Province ต่อ โดยเริ่มจาก Category เพื่อเลือกกลุ่มธุรกิจ แล้วค่อยตรวจจังหวัดใน Province และความเสี่ยงใน Survival
""".strip()

    top_biz = rec.head(3)
    top_prov = prov.head(3)
    best = top_biz.iloc[0] if not top_biz.empty else None
    best_name = best["type"] if best is not None and "type" in top_biz.columns else "ธุรกิจที่ผ่านตัวกรองอันดับต้น"
    best_score = best["opportunity_score"] if best is not None and "opportunity_score" in top_biz.columns else np.nan
    best_closure = best["closure_rate"] if best is not None and "closure_rate" in top_biz.columns else np.nan
    best_cap = best["avg_capital_m"] if best is not None and "avg_capital_m" in top_biz.columns else np.nan

    if best is not None:
        reason_lines = [
            f"1. ธุรกิจอันดับต้นคือ {best_name} โดยมี Opportunity Score {fmt_float(best_score,1)} จากข้อมูลที่ผ่านตัวกรอง",
            f"2. Closure Rate ของธุรกิจนี้อยู่ที่ {fmt_float(best_closure)}% จึงควรใช้เทียบกับธุรกิจอื่นในหน้า Survival",
            f"3. ทุนเฉลี่ยต่อรายที่อ่านได้ประมาณ {fmt_float(best_cap)} ล้านบาท/ราย จึงควรเทียบกับเงินทุนที่มีจริง",
        ]
    else:
        reason_lines = [
            "1. ไม่พบธุรกิจที่ผ่านตัวกรอง แต่ยังมีข้อมูลจังหวัดให้ใช้ประกอบ",
            "2. ควรเปิดตัวกรองกลุ่มธุรกิจให้กว้างขึ้น",
            "3. ควรใช้จังหวัดที่มี net growth สูงเป็นพื้นที่ตั้งต้น",
        ]

    risk_line = "ควรระวังธุรกิจที่มี Closure Rate สูง หรือมีจำนวนผู้เล่นใหม่เยอะมาก เพราะอาจเป็นตลาดที่แข่งขันสูง"
    if risk == "ต่ำ":
        risk_line += " โดยเฉพาะเมื่อคุณเลือกรับความเสี่ยงต่ำ ควรเลี่ยงธุรกิจที่มีอัตราเลิกกิจการสูงกว่าค่ากลาง"

    rec_lines = []
    for i, r in enumerate(top_biz.itertuples(), start=1):
        rec_lines.append(f"{i}. {getattr(r, 'type', '-')} — Opportunity {fmt_float(getattr(r, 'opportunity_score', np.nan),1)}, Closure {fmt_float(getattr(r, 'closure_rate', np.nan))}%")
    if len(rec_lines) < 3:
        for i, r in enumerate(top_prov.itertuples(), start=len(rec_lines)+1):
            if i > 3:
                break
            rec_lines.append(f"{i}. จังหวัด {getattr(r, 'province', '-')} — Net Growth {fmt_num(getattr(r, 'net_growth', 0))}, Closure Rate {fmt_float(getattr(r, 'closure_rate', np.nan))}%")
    while len(rec_lines) < 3:
        rec_lines.append(f"{len(rec_lines)+1}. ข้อมูลไม่พอสำหรับรายการเพิ่มเติม")

    return f"""
คำแนะนำหลัก:
ถ้าต้องการ{goal} ภายใต้เงินทุน "{budget}" และรับความเสี่ยงได้ "{risk}" ควรเริ่มจาก **{best_name}** แล้วตรวจสอบจังหวัดที่มีสัญญาณเติบโตควบคู่กัน

เหตุผลจากข้อมูล:
{chr(10).join(reason_lines)}

ความเสี่ยงที่ควรระวัง:
{risk_line}

จังหวัด/ธุรกิจที่แนะนำ:
{chr(10).join(rec_lines)}

Next Step:
ควรไปดูกราฟหน้า Category / Survival / Province ต่อ โดยเริ่มจาก Category เพื่อดู Opportunity Score จากนั้นดู Survival เพื่อเช็กความอยู่รอด และดู Province เพื่อเลือกพื้นที่ที่เหมาะสม
""".strip()


def get_gemini_key():
    """อ่าน Gemini key จาก .env / environment / Streamlit secrets แบบ robust"""
    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if key:
        return key
    try:
        key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        if key:
            return key
        key = str(st.secrets.get("GOOGLE_API_KEY", "")).strip()
        if key:
            return key
    except Exception:
        pass
    return ""


def _friendly_gemini_error(err: Exception | str) -> str:
    msg = str(err)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        return "Gemini เชื่อมต่อได้แล้ว แต่โควต้า/API quota ของโมเดลที่เลือกหมดหรือไม่เปิดใช้ใน free tier โดยเฉพาะโมเดล Pro ให้เปลี่ยนเป็น gemini-2.5-flash หรือรอสักครู่/เปิด billing แล้วลองใหม่"
    if "API key" in msg or "permission" in msg.lower() or "403" in msg:
        return "พบ API key แล้ว แต่อาจยังไม่มีสิทธิ์ใช้โมเดลนี้ หรือ key/project ยังไม่ได้เปิด Gemini API"
    return f"เรียก Gemini ไม่สำเร็จ: {msg[:350]}"


def call_gemini(prompt, model_name, api_key=None):
    api_key = (api_key or get_gemini_key()).strip()
    if not api_key:
        return None, "ยังไม่ได้ตั้งค่า GEMINI_API_KEY หรือ GOOGLE_API_KEY"

    # กันเผลอใช้ Pro บน free tier แล้วเจอโควต้า 0 บ่อย ๆ
    if "pro" in str(model_name).lower():
        return None, "โมเดล Pro มักติด quota/free tier ในโปรเจกต์นี้ ให้เลือก gemini-2.5-flash ก่อนเพื่อให้ demo ใช้งานได้เสถียรกว่า"

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model_name, contents=prompt)
        text = getattr(response, "text", None)
        if text:
            return text, None
        return None, "Gemini ตอบกลับมาเป็นค่าว่าง"
    except Exception as e_new:
        try:
            import google.generativeai as genai_old
            genai_old.configure(api_key=api_key)
            model = genai_old.GenerativeModel(model_name=model_name)
            response = model.generate_content(prompt)
            text = getattr(response, "text", None)
            if text:
                return text, None
            return None, "Gemini ตอบกลับมาเป็นค่าว่าง"
        except Exception as e_old:
            return None, _friendly_gemini_error(f"{e_new} / {e_old}")


def answer_card(answer_text):
    safe = answer_text.strip()
    safe = re.sub(r"^(คำแนะนำหลัก:)", r"### \1", safe, flags=re.M)
    safe = re.sub(r"^(เหตุผลจากข้อมูล:)", r"### \1", safe, flags=re.M)
    safe = re.sub(r"^(ความเสี่ยงที่ควรระวัง:)", r"### \1", safe, flags=re.M)
    safe = re.sub(r"^(จังหวัด/ธุรกิจที่แนะนำ:)", r"### \1", safe, flags=re.M)
    safe = re.sub(r"^(Next Step:)", r"### \1", safe, flags=re.M)
    st.markdown("<div class='answer-card'>", unsafe_allow_html=True)
    st.markdown(safe)
    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# UI
# ============================================================
st.markdown(
    """
    <div class="hero-card">
        <div class="hero-title">🤖 AI Business Advisor</div>
        <div class="hero-sub">ผู้ช่วยแปล dashboard ให้เป็นคำแนะนำเชิงธุรกิจ โดยตอบแบบ decision support ไม่ใช่ chatbot กว้าง ๆ</div>
        <span class="pill">Gemini optional</span>
        <span class="pill">Decision support</span>
        <span class="pill">Business insight</span>
        <span class="pill">Grounded by project data</span>
    </div>
    """,
    unsafe_allow_html=True,
)

if biz.empty:
    st.warning("ยังไม่มีข้อมูล business_2569 จาก load_all_data() จึงแนะนำได้จำกัด")
if province_latest.empty:
    st.info("ยังไม่มีข้อมูล province_latest / province_monthly สำหรับแนะนำจังหวัด")

st.markdown("## 1) ระบุเป้าหมายและข้อจำกัดของคุณ")
c1, c2, c3, c4 = st.columns(4)
with c1:
    goal = st.selectbox("เป้าหมาย", ["เริ่มธุรกิจใหม่", "หาธุรกิจทุนต่ำ", "ลดความเสี่ยง", "หา SME ที่เหมาะเริ่มต้น"], index=0)
with c2:
    budget = st.selectbox("เงินทุน", ["ไม่ระบุ", "ไม่เกิน 1 ล้านบาท", "1–10 ล้านบาท", "มากกว่า 10 ล้านบาท"], index=0)
with c3:
    risk = st.selectbox("รับความเสี่ยงได้", ["ต่ำ", "กลาง", "สูง"], index=0)
with c4:
    group_options = ["ยังไม่แน่ใจ"]
    if not biz.empty and "business_group" in biz.columns:
        group_options += sorted([x for x in biz["business_group"].dropna().astype(str).unique().tolist() if x.strip()])
    group = st.selectbox("กลุ่มธุรกิจที่สนใจ", group_options, index=0)

area_options = ["ทั้งประเทศ"]
if not province_latest.empty and "province" in province_latest.columns:
    area_options += sorted(province_latest["province"].dropna().astype(str).unique().tolist())
area = st.selectbox("พื้นที่ที่สนใจ", area_options, index=0)

# ============================================================
# Suggested questions + Chat history
# ============================================================
st.markdown("## 2) เลือกคำถามที่อยากให้ AI ช่วยวิเคราะห์")
st.caption("หน้านี้ออกแบบให้เลือกคำถามจากปุ่มด้านล่างร่วมกับ filter ด้านบน เพื่อให้ AI/ระบบตอบจากข้อมูลจริงใน dashboard และลดการถามนอกบริบท")
suggested = [
    "มีทุนไม่เกิน 1 ล้านบาท ควรเริ่มธุรกิจประเภทไหน?",
    "ธุรกิจไหนเปิดน้อยแต่มีโอกาสรอดสูง?",
    "ธุรกิจไหนเป็น Red Ocean ที่ควรระวัง?",
    "จังหวัดไหนเหมาะกับการเริ่มธุรกิจมากที่สุด?",
    "ธุรกิจบริการประเภทไหนเหมาะกับ SME?",
    "สรุป 5 insight สำคัญจากข้อมูลทั้งหมดให้หน่อย",
    "ถ้ารับความเสี่ยงต่ำ ควรเลี่ยงธุรกิจกลุ่มไหน?",
    "ธุรกิจที่เหมาะกับ SME และทุนไม่สูงคืออะไร?",
    "ควรไปดูหน้า Category / Survival / Province ตรงไหนต่อ?",
]

if "advisor_pending_question" not in st.session_state:
    st.session_state["advisor_pending_question"] = ""
if "advisor_chat_history" not in st.session_state:
    st.session_state["advisor_chat_history"] = []
if "advisor_scroll_to_chat" not in st.session_state:
    st.session_state["advisor_scroll_to_chat"] = False

cols_per_row = 3
for row_start in range(0, len(suggested), cols_per_row):
    cols = st.columns(cols_per_row)
    for j, q in enumerate(suggested[row_start:row_start + cols_per_row]):
        i = row_start + j
        with cols[j]:
            if st.button(q, key=f"suggested_{i}"):
                st.session_state["advisor_pending_question"] = q
                st.session_state["advisor_scroll_to_chat"] = True

with st.expander("ตัวอย่างคำถามที่เหมาะกับหน้านี้"):
    st.markdown("""
    - **มีทุนไม่เกิน 1 ล้านบาท ควรเริ่มธุรกิจประเภทไหน?** ใช้คู่กับ filter เงินทุน  
    - **ถ้ารับความเสี่ยงต่ำ ควรเลี่ยงธุรกิจอะไร?** ใช้คู่กับ filter รับความเสี่ยงได้  
    - **จังหวัดไหนเหมาะกับการเริ่มธุรกิจมากที่สุด?** ใช้ข้อมูลจังหวัด/Net Growth/Closure Rate  
    - **ธุรกิจไหนเปิดน้อยแต่มีโอกาสรอดสูง?** ใช้ข้อมูล Opportunity + Survival  
    - **สรุป 5 insight สำคัญจากข้อมูลทั้งหมดให้หน่อย** เหมาะกับใช้ก่อนนำเสนอ  
    """)

st.markdown("## 3) Recommendation Evidence")
rec_df = top_recommendations(goal, budget, risk, group, n=10)
k1, k2, k3 = st.columns(3)
with k1:
    metric_card("รายการที่ผ่านตัวกรอง", fmt_num(len(rec_df)), "ประเภทธุรกิจ")
with k2:
    avg_score = rec_df["opportunity_score"].mean() if not rec_df.empty and "opportunity_score" in rec_df.columns else np.nan
    metric_card("Opportunity เฉลี่ย", fmt_float(avg_score, 1), "0–100")
with k3:
    med_closure = rec_df["closure_rate"].median() if not rec_df.empty and "closure_rate" in rec_df.columns else np.nan
    metric_card("Closure กลาง", f"{fmt_float(med_closure)}%", "ค่ามัธยฐาน")

if not rec_df.empty and "closure_rate" in rec_df.columns:
    if float(pd.to_numeric(rec_df["closure_rate"], errors="coerce").fillna(0).sum()) == 0:
        st.info("Closure Rate เป็น 0.00% เพราะธุรกิจที่ผ่านตัวกรองชุดนี้ไม่มีจำนวนเลิกกิจการในข้อมูลที่อ่านได้ ไม่ได้แปลว่าธุรกิจไม่มีความเสี่ยงจริงเสมอไป ควรดูหน้า Survival และ Data Drilldown เพิ่ม")

st.plotly_chart(make_evidence_chart(rec_df), use_container_width=True, key="ai_advisor_evidence_chart")

with st.expander("ดูตารางหลักฐานที่ AI ใช้ประกอบคำตอบ"):
    if rec_df.empty:
        st.info("ยังไม่มีรายการที่ผ่านตัวกรอง")
    else:
        show_cols = [c for c in ["type", "business_group", "regis_count", "quit_count", "closure_rate", "survival_rate", "avg_capital_m", "opportunity_score"] if c in rec_df.columns]
        st.dataframe(rec_df[show_cols].head(20), use_container_width=True, hide_index=True)

st.markdown('<div id="ai-chat-anchor"></div>', unsafe_allow_html=True)
st.markdown("## 4) Chat")

with st.expander("ตั้งค่า Gemini API", expanded=False):
    gemini_api_key = get_gemini_key()
    current_has_key = bool(gemini_api_key)
    st.write("สถานะ GEMINI_API_KEY / GOOGLE_API_KEY:", "✅ พบแล้ว" if current_has_key else "❌ ยังไม่พบ")
    model_name = st.selectbox(
        "Gemini model name",
        ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"],
        index=0,
        help="ใช้ Flash สำหรับ demo เพราะ Pro มักติด quota ใน free tier ง่ายกว่า",
    )
    st.caption("แนะนำให้เก็บ GEMINI_API_KEY ในไฟล์ .env หรือ Streamlit secrets ไม่ควร hardcode ลง GitHub")
    use_ai = st.toggle("ใช้ Gemini ถ้ามี API key", value=current_has_key, disabled=not current_has_key)
    if current_has_key:
        st.success("พร้อมใช้ Gemini แล้ว — ถ้าตอบไม่ได้ แปลว่าอาจติด model/library/API restriction ไม่ใช่ไม่เจอ key")
    else:
        st.info("ถ้า deploy บน Streamlit Cloud ให้ไปที่ Manage app → Settings → Secrets แล้วใส่ GEMINI_API_KEY หรือ GOOGLE_API_KEY")
        st.code('GEMINI_API_KEY = "ใส่คีย์จริงตรงนี้"', language="toml")

if st.session_state.get("advisor_scroll_to_chat"):
    components.html(
        """
        <script>
        setTimeout(function() {
            const el = window.parent.document.getElementById("ai-chat-anchor");
            if (el) { el.scrollIntoView({behavior: "smooth", block: "start"}); }
        }, 350);
        </script>
        """,
        height=0,
    )
    st.session_state["advisor_scroll_to_chat"] = False

if st.button("🧹 ล้างประวัติแชท", use_container_width=False):
    st.session_state["advisor_chat_history"] = []
    st.session_state["advisor_pending_question"] = ""
    st.rerun()

with st.expander("🕘 ประวัติคำถามที่ค้นหา", expanded=False):
    old_questions = [m["content"] for m in st.session_state["advisor_chat_history"] if m.get("role") == "user"]
    if old_questions:
        for i, q in enumerate(old_questions, start=1):
            st.markdown(f"{i}. {q}")
    else:
        st.caption("ยังไม่มีประวัติคำถามใน session นี้")

# แสดงข้อความเก่าทั้งหมดก่อน เพื่อให้เหมือน chat จริง
for msg in st.session_state["advisor_chat_history"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            answer_card(msg["content"])
            if msg.get("caption"):
                st.caption(msg["caption"])
        else:
            st.write(msg["content"])

st.info("เลือกคำถามจาก Suggested Questions ด้านบนแทนการพิมพ์เอง เพื่อให้คำตอบอิงกับ filter และข้อมูลในโปรเจกต์ได้แม่นกว่า")

pending = st.session_state.get("advisor_pending_question", "").strip()
if pending:
    user_q = pending
    st.session_state["advisor_pending_question"] = ""

    with st.chat_message("user"):
        st.write(user_q)
    st.session_state["advisor_chat_history"].append({"role": "user", "content": user_q})

    prompt = data_context_for_prompt(goal, budget, risk, group, area, user_q)

    with st.chat_message("assistant"):
        if use_ai:
            with st.spinner("รอสักครู่ กำลังให้ AI ประมวลผลจากข้อมูลใน Dashboard..."):
                ai_text, err = call_gemini(prompt, model_name, gemini_api_key)
            if ai_text:
                answer_card(ai_text)
                caption = "ตอบโดย Gemini โดยจำกัด context จากข้อมูลใน dashboard นี้"
                st.caption(caption)
                st.session_state["advisor_chat_history"].append({"role": "assistant", "content": ai_text, "caption": caption})
            else:
                warn = f"ใช้ Gemini ไม่ได้ จึงแสดงคำตอบแบบ rule-based จากข้อมูลจริงแทน: {err}"
                st.warning(warn)
                with st.spinner("กำลังสร้างคำตอบสำรองจากข้อมูลจริงใน Dashboard..."):
                    ans = fallback_answer(goal, budget, risk, group, area, user_q)
                answer_card(ans)
                st.session_state["advisor_chat_history"].append({"role": "assistant", "content": ans, "caption": warn})
        else:
            with st.spinner("กำลังประมวลผลจากข้อมูลจริงใน Dashboard..."):
                ans = fallback_answer(goal, budget, risk, group, area, user_q)
            answer_card(ans)
            caption = "ตอบแบบ rule-based จากข้อมูลจริงใน dashboard; เปิด Gemini API ได้ใน expander ด้านบน"
            st.caption(caption)
            st.session_state["advisor_chat_history"].append({"role": "assistant", "content": ans, "caption": caption})

    st.markdown(
        "<div class='source-note'>หมายเหตุ: หน้านี้ใช้ข้อมูลจาก load_all_data() ของโปรเจกต์เท่านั้น "
        "ถ้าข้อมูลไม่พอ ระบบจะบอกว่าไม่พอแทนการสร้างตัวเลขเอง</div>",
        unsafe_allow_html=True,
    )

elif not st.session_state["advisor_chat_history"]:
    st.info("เลือกคำถามตัวอย่างด้านบน หรือพิมพ์คำถามในช่อง Chat ด้านล่าง แล้วระบบจะตอบตาม format: คำแนะนำหลัก / เหตุผลจากข้อมูล / ความเสี่ยง / จังหวัดหรือธุรกิจที่แนะนำ / Next Step")
