import textwrap
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from db import ensure_database_ready, load_all_data_from_duckdb as load_all_data
    ensure_database_ready(auto_refresh=True)
except Exception as e:
    try:
        from data_loader import load_all_data
    except Exception as e2:
        st.error(f"ไม่สามารถเชื่อม DuckDB หรือ import load_all_data จาก data_loader.py ได้: {e} / {e2}")
        st.stop()

# -----------------------------
# Theme / helpers
# -----------------------------
PRIMARY = "#a855f7"
PINK = "#ec4899"
CYAN = "#22d3ee"
GREEN = "#22c55e"
YELLOW = "#f59e0b"
RED = "#ef4444"
BLUE = "#38bdf8"
CARD_BG = "rgba(15,23,42,0.75)"
BORDER = "rgba(148,163,184,0.25)"
TEXT_MUTED = "#94a3b8"
WHITE = "#f8fafc"
PLOT_BG = "#020817"
GRID = "rgba(148,163,184,0.15)"

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
    .main-title {font-size: 2.2rem; font-weight: 800; color: #f8fafc; margin-bottom: 0.15rem;}
    .sub-title {font-size: 1rem; color: #cbd5e1; margin-bottom: 1rem;}
    .note-box {
        background: linear-gradient(135deg, rgba(30,41,59,0.75), rgba(15,23,42,0.95));
        border: 1px solid rgba(56,189,248,0.18);
        border-radius: 18px; padding: 1rem 1.15rem; margin-bottom: 1rem;
    }
    .note-title {color: #22d3ee; font-weight: 700; letter-spacing: 0.02em; margin-bottom: 0.4rem;}
    .kpi-card {
        background: linear-gradient(135deg, rgba(15,23,42,0.9), rgba(10,18,40,0.95));
        border: 1px solid rgba(96,165,250,0.18);
        border-radius: 18px;
        padding: 1rem 1rem 0.85rem 1rem;
        min-height: 120px;
    }
    .kpi-label {font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.06em;}
    .kpi-value {font-size: 2rem; font-weight: 800; color: #f8fafc; margin-top: 0.2rem; line-height: 1.1;}
    .kpi-sub {font-size: 0.92rem; color: #cbd5e1; margin-top: 0.35rem;}
    .summary-card {
        background: linear-gradient(135deg, rgba(15,23,42,0.82), rgba(15,23,42,0.98));
        border: 1px solid rgba(167,139,250,0.18);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.8rem;
    }
    .summary-title {color: #22d3ee; font-size: 0.82rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.7rem;}
    .summary-card ul {margin: 0.2rem 0 0.1rem 1.0rem; padding-left: 0.2rem;}
    .summary-card li {margin-bottom: 0.45rem; color: #e2e8f0; line-height: 1.55;}
    .leader-item {
        padding: 0.7rem 0.8rem; border-radius: 14px; background: rgba(15,23,42,0.52);
        border: 1px solid rgba(148,163,184,0.14); margin-bottom: 0.55rem;
    }
    .leader-rank {display:inline-block; min-width: 28px; color:#22d3ee; font-weight:800;}
    .caption-small {color: #94a3b8; font-size: 0.85rem;}
    .stTabs [data-baseweb="tab-list"] {gap: 0.4rem;}
    .stTabs [data-baseweb="tab"] {
        background: rgba(15,23,42,0.80); border-radius: 999px; padding: 0.5rem 1rem;
        border: 1px solid rgba(148,163,184,0.16); color: #e2e8f0;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, rgba(124,58,237,0.9), rgba(168,85,247,0.95));
        color: white; border-color: rgba(192,132,252,0.7);
    }
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
        return f"{float(x):,.{digits}f}"
    except Exception:
        return f"{0:.{digits}f}"


def wrap_label(txt, width=22):
    txt = str(txt)
    return "<br>".join(textwrap.wrap(txt, width=width, break_long_words=False, break_on_hyphens=False))


def month_label(year, month_text, month_no):
    if pd.isna(year):
        return str(month_text)
    yy = int(year) % 100
    return f"{month_text} {yy}"


def plot_style(fig, height=420, showlegend=True):
    fig.update_layout(
        height=height,
        paper_bgcolor=PLOT_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=WHITE, family="Arial"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=55, b=20),
        showlegend=showlegend,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID, tickfont=dict(color=WHITE), title_font=dict(color=WHITE))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=WHITE), title_font=dict(color=WHITE))
    return fig


def metric_card(title, value, subtitle):
    st.markdown(
        f"""
        <div class='kpi-card'>
            <div class='kpi-label'>{title}</div>
            <div class='kpi-value'>{value}</div>
            <div class='kpi-sub'>{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def summary_box(title, bullets):
    html = f"<div class='summary-card'><div class='summary-title'>{title}</div><ul>"
    for b in bullets:
        html += f"<li>{b}</li>"
    html += "</ul></div>"
    st.markdown(html, unsafe_allow_html=True)


def ranked_list(df, name_col, value_col, unit="ราย", n=5):
    if df.empty or name_col not in df.columns or value_col not in df.columns:
        st.info("ไม่พบข้อมูล")
        return
    show = df[[name_col, value_col]].head(n).copy()
    for idx, (_, row) in enumerate(show.iterrows(), start=1):
        st.markdown(
            f"<div class='leader-item'><span class='leader-rank'>{idx}.</span> <b>{row[name_col]}</b> — {fmt_num(row[value_col])} {unit}</div>",
            unsafe_allow_html=True,
        )


def _donut_sector_trace(theta1, theta2, outer_r, inner_r, color, name, hover_text):
    """สร้างพื้นที่ donut slice เอง เพื่อให้ลูกศรชี้เข้า slice ได้แม่นกว่า go.Pie"""
    sweep = abs(theta1 - theta2)
    steps = max(22, int(sweep / 3))
    outer_deg = np.linspace(theta1, theta2, steps)
    inner_deg = outer_deg[::-1]
    outer_rad = np.deg2rad(outer_deg)
    inner_rad = np.deg2rad(inner_deg)

    x_poly = np.concatenate([
        outer_r * np.cos(outer_rad),
        inner_r * np.cos(inner_rad),
    ])
    y_poly = np.concatenate([
        outer_r * np.sin(outer_rad),
        inner_r * np.sin(inner_rad),
    ])

    return go.Scatter(
        x=x_poly,
        y=y_poly,
        mode="lines",
        fill="toself",
        fillcolor=color,
        line=dict(color="rgba(15,23,42,.95)", width=1.7),
        name=name,
        hoverinfo="text",
        text=hover_text,
        showlegend=False,
    )


def _finish_manual_donut(fig, annotations, height=300, x_range=(-1.55, 1.55), y_range=(-1.35, 1.35), title=None):
    fig.update_layout(
        title=title,
        title_font=dict(color=WHITE, size=16),
        annotations=annotations,
        height=height,
        paper_bgcolor=PLOT_BG,
        plot_bgcolor=PLOT_BG,
        margin=dict(l=10, r=10, t=48 if title else 12, b=10),
        showlegend=False,
        xaxis=dict(visible=False, range=list(x_range), constrain="domain"),
        yaxis=dict(visible=False, range=list(y_range), scaleanchor="x", scaleratio=1),
    )
    return fig


def size_share_donut(title, label, share, color, total=None):
    """
    Donut ย่อยแบบวาดเอง:
    - หัวลูกศรอยู่บนพื้นที่สีของ slice จริง
    - กล่องข้อความอยู่ด้านนอก เหมือน logic ตัวอย่าง Matplotlib ที่ใช้ xy / xytext
    """
    share = float(share)
    share = max(0.0, min(100.0, share))
    remain = max(0.0, 100.0 - share)

    fig = go.Figure()
    outer_r = 1.00
    inner_r = 0.67
    arrow_r = 0.84
    label_r = 1.27
    start_angle = 90.0

    # colored slice
    sweep = share / 100 * 360
    theta1 = start_angle
    theta2 = start_angle - sweep
    if share > 0:
        fig.add_trace(_donut_sector_trace(
            theta1, theta2, outer_r, inner_r, color,
            f"{label} {share:.1f}%",
            f"{label}<br>{share:.1f}%"
        ))

    # remain slice
    if remain > 0:
        fig.add_trace(_donut_sector_trace(
            theta2, theta2 - remain / 100 * 360, outer_r, inner_r,
            "rgba(148,163,184,0.18)",
            "อื่น ๆ",
            f"อื่น ๆ<br>{remain:.1f}%"
        ))

    center_text = f"<b>{share:.1f}%</b><br><span style='font-size:12px'>{label}</span>"
    if total is not None:
        center_text += f"<br><span style='font-size:11px'>{fmt_num(total)} ราย</span>"

    annotations = [
        dict(
            x=0, y=0, xref="x", yref="y",
            text=center_text,
            showarrow=False,
            font=dict(color=WHITE, size=14),
            align="center",
        )
    ]

    # annotation arrow: midpoint of colored slice
    if share > 0:
        mid = (theta1 + theta2) / 2
        ang = np.deg2rad(mid)
        x = np.cos(ang)
        y = np.sin(ang)
        x_tip, y_tip = arrow_r * x, arrow_r * y
        x_text, y_text = label_r * x, label_r * y
        ha = "center" if abs(x) < abs(y) else ("right" if x < 0 else "left")

        annotations.append(dict(
            x=x_tip, y=y_tip, xref="x", yref="y",
            ax=x_text, ay=y_text, axref="x", ayref="y",
            text=f"<b>{label}</b><br>{share:.1f}%",
            showarrow=True,
            arrowhead=2,
            arrowsize=1.05,
            arrowwidth=1.2,
            arrowcolor=color,
            font=dict(color=color, size=12),
            bgcolor="rgba(2,6,23,0.88)",
            bordercolor=color,
            borderwidth=1,
            borderpad=3,
            xanchor=ha,
            yanchor="middle",
            align="center",
        ))

    return _finish_manual_donut(
        fig,
        annotations,
        height=280,
        x_range=(-1.42, 1.42),
        y_range=(-1.28, 1.28),
        title=title,
    )


def overall_size_mix_donut(size_df):
    """
    Donut ภาพรวม S/M/L แบบวาดเอง
    ให้ลูกศรชี้เข้าไปที่พื้นที่สีของแต่ละ slice จริง ไม่ใช่ชี้ลอยนอกวง
    """
    d = size_df.copy()
    d["count"] = pd.to_numeric(d["count"], errors="coerce").fillna(0)
    d["share"] = pd.to_numeric(d["share"], errors="coerce").fillna(0)
    d = d[d["count"] > 0].copy()

    fig = go.Figure()
    if d.empty or d["count"].sum() <= 0:
        fig.add_annotation(x=0, y=0, text="ไม่มีข้อมูล", showarrow=False, font=dict(color=WHITE))
        return _finish_manual_donut(fig, [], height=340, title="ภาพรวมสัดส่วนธุรกิจตามขนาด")

    size_colors = {"S": PRIMARY, "M": PINK, "L": CYAN}
    total = float(d["count"].sum())
    outer_r = 1.00
    inner_r = 0.60
    arrow_r = 0.82
    label_r = 1.34
    start_angle = 90.0
    current = start_angle
    annotations = []

    for _, row in d.iterrows():
        label = str(row["size"])
        value = float(row["count"])
        share = value / total * 100 if total else 0
        color = size_colors.get(label, PRIMARY)

        sweep = share / 100 * 360
        theta1 = current
        theta2 = current - sweep

        fig.add_trace(_donut_sector_trace(
            theta1, theta2, outer_r, inner_r, color,
            f"{label} {share:.1f}%",
            f"ขนาด {label}<br>{value:,.0f} ราย<br>{share:.1f}%"
        ))

        mid = (theta1 + theta2) / 2
        ang = np.deg2rad(mid)
        x = np.cos(ang)
        y = np.sin(ang)
        x_tip, y_tip = arrow_r * x, arrow_r * y
        x_text, y_text = label_r * x, label_r * y
        ha = "center" if abs(x) < abs(y) else ("right" if x < 0 else "left")

        annotations.append(dict(
            x=x_tip, y=y_tip, xref="x", yref="y",
            ax=x_text, ay=y_text, axref="x", ayref="y",
            text=f"<b>{label}</b><br>{share:.1f}%",
            showarrow=True,
            arrowhead=2,
            arrowsize=1.1,
            arrowwidth=1.25,
            arrowcolor=color,
            font=dict(color=color, size=13),
            bgcolor="rgba(2,6,23,0.90)",
            bordercolor=color,
            borderwidth=1,
            borderpad=3,
            xanchor=ha,
            yanchor="middle",
            align="center",
        ))
        current = theta2

    annotations.append(dict(
        x=0, y=0, xref="x", yref="y",
        text=f"<b>SME Mix</b><br>{fmt_num(total)} ราย",
        showarrow=False,
        font=dict(color=WHITE, size=18),
        align="center",
    ))

    return _finish_manual_donut(
        fig,
        annotations,
        height=420,
        x_range=(-1.55, 1.55),
        y_range=(-1.33, 1.33),
        title="ภาพรวมสัดส่วนธุรกิจตามขนาด",
    )


# -----------------------------
# Load data
# -----------------------------
try:
    data = load_all_data()
except Exception as e:
    st.error(f"โหลดข้อมูลไม่สำเร็จ: {e}")
    st.stop()

prov_monthly = data.get("province_monthly", pd.DataFrame()).copy()
prov_latest = data.get("province_latest", pd.DataFrame()).copy()
biz69 = data.get("business_2569", pd.DataFrame()).copy()

if prov_monthly.empty and prov_latest.empty and biz69.empty:
    st.warning("ยังไม่พบข้อมูลสำหรับหน้า Executive Overview")
    st.stop()

# Ensure required numeric columns
for frame in [prov_monthly, prov_latest, biz69]:
    if not frame.empty:
        for c in frame.columns:
            if any(key in c for key in ["count", "rate", "capital", "growth"]) or c in ["year", "month_no"]:
                try:
                    frame[c] = pd.to_numeric(frame[c], errors="coerce").fillna(frame[c])
                except Exception:
                    pass

# Aggregate province monthly for long trend
if not prov_monthly.empty:
    monthly_sum_cols = [c for c in ["new_count", "closed_count", "net_growth", "new_capital_m", "active_count"] if c in prov_monthly.columns]
    monthly_agg = prov_monthly.groupby(["year", "month_no", "month"], as_index=False)[monthly_sum_cols].sum()
    monthly_agg = monthly_agg.sort_values(["year", "month_no"]).reset_index(drop=True)
    monthly_agg["period_label"] = [month_label(y, m, n) for y, m, n in monthly_agg[["year", "month", "month_no"]].itertuples(index=False)]
    latest_row = monthly_agg.sort_values(["year", "month_no"]).iloc[-1]
    latest_year, latest_month_no = int(latest_row["year"]), int(latest_row["month_no"])
    latest_month_text = str(latest_row["month"])
    latest_view = prov_monthly[(prov_monthly["year"] == latest_year) & (prov_monthly["month_no"] == latest_month_no)].copy()
    start_row = monthly_agg.iloc[0]
else:
    monthly_agg = pd.DataFrame()
    latest_year, latest_month_no, latest_month_text = 2569, 4, "ล่าสุด"
    latest_view = prov_latest.copy()
    start_row = None

if not latest_view.empty and "closure_rate" not in latest_view.columns and {"closed_count", "new_count"}.issubset(latest_view.columns):
    latest_view["closure_rate"] = np.where(latest_view["new_count"] > 0, latest_view["closed_count"] * 100 / latest_view["new_count"], np.nan)

# KPI values based on latest month snapshot
if not latest_view.empty:
    total_new = latest_view["new_count"].sum() if "new_count" in latest_view.columns else 0
    total_closed = latest_view["closed_count"].sum() if "closed_count" in latest_view.columns else 0
    total_net = latest_view["net_growth"].sum() if "net_growth" in latest_view.columns else total_new - total_closed
    total_capital = latest_view["new_capital_m"].sum() if "new_capital_m" in latest_view.columns else 0
    close_rate = (total_closed / total_new * 100) if total_new else 0
    top_prov = latest_view.sort_values("new_count", ascending=False).iloc[0]["province"] if "province" in latest_view.columns and total_new else "-"
else:
    total_new = biz69["regis_count"].sum() if "regis_count" in biz69.columns else 0
    total_closed = biz69["quit_count"].sum() if "quit_count" in biz69.columns else 0
    total_net = total_new - total_closed
    total_capital = biz69["regis_capital_m"].sum() if "regis_capital_m" in biz69.columns else 0
    close_rate = (total_closed / total_new * 100) if total_new else 0
    top_prov = "-"

# Derived business metrics
if not biz69.empty:
    if "business_group" in biz69.columns and "regis_count" in biz69.columns:
        group_reg = biz69.groupby("business_group", as_index=False)["regis_count"].sum().sort_values("regis_count", ascending=False)
    else:
        group_reg = pd.DataFrame()

    size_cols = [c for c in ["size_s_count", "size_m_count", "size_l_count"] if c in biz69.columns]
    size_totals = {"S": 0, "M": 0, "L": 0}
    if size_cols:
        size_totals = {
            "S": float(biz69["size_s_count"].sum()) if "size_s_count" in biz69.columns else 0,
            "M": float(biz69["size_m_count"].sum()) if "size_m_count" in biz69.columns else 0,
            "L": float(biz69["size_l_count"].sum()) if "size_l_count" in biz69.columns else 0,
        }
    size_total_all = sum(size_totals.values())
    size_df = pd.DataFrame({
        "size": ["S", "M", "L"],
        "count": [size_totals["S"], size_totals["M"], size_totals["L"]],
    })
    if size_total_all > 0:
        size_df["share"] = size_df["count"] * 100 / size_total_all
    else:
        size_df["share"] = 0
else:
    group_reg = pd.DataFrame()
    size_df = pd.DataFrame(columns=["size", "count", "share"])

# -----------------------------
# Header and notes
# -----------------------------
st.markdown("<div class='main-title'>📌 Executive Overview</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-title'>สรุปภาพรวมธุรกิจไทยในมุมผู้บริหาร เพื่อดูแนวโน้มระยะยาว จังหวัดเด่น กลุ่มธุรกิจเด่น ความเสี่ยง และสิ่งที่ควรทำต่อ</div>",
    unsafe_allow_html=True,
)

data_note = "ข้อมูลอ้างอิง"
if start_row is not None:
    data_note += f": แนวโน้มจังหวัดรายเดือนตั้งแต่ <b>{start_row['month']} {int(start_row['year'])}</b> ถึง <b>{latest_month_text} {latest_year}</b>"
else:
    data_note += f": ใช้ข้อมูล snapshot ล่าสุด {latest_month_text} {latest_year}"
if not biz69.empty:
    data_note += " · ข้อมูลประเภทธุรกิจ/ขนาดธุรกิจใช้ชุดข้อมูลปี 2569"

st.markdown(f"<div class='note-box'><div class='note-title'>DATA NOTE</div><div style='color:#e2e8f0'>{data_note}</div></div>", unsafe_allow_html=True)

# KPI row
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    metric_card("New Registrations", fmt_num(total_new), f"จัดตั้งใหม่ · {latest_month_text} {latest_year}")
with k2:
    metric_card("Deregistrations", fmt_num(total_closed), "เลิกกิจการ")
with k3:
    metric_card("Net Growth", fmt_num(total_net), "จัดตั้งใหม่ - เลิกกิจการ")
with k4:
    metric_card("Total Investment", f"{fmt_num(total_capital)} ลบ.", "ทุนจัดตั้งใหม่")
with k5:
    metric_card("Top Province", top_prov, f"Closure Rate {fmt_float(close_rate)}%")

# Tabs

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "1) Macro Trend",
    "2) Leaderboards",
    "3) SME Size Mix",
    "4) Top Rankings",
    "5) Opportunity vs Risk",
    "6) Executive Summary",
])

with tab1:
    st.markdown("### ภาพรวมแนวโน้มรายเดือน")
    if monthly_agg.empty:
        st.info("ยังไม่มีข้อมูลรายเดือนเพียงพอสำหรับแสดงแนวโน้ม")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=monthly_agg["period_label"], y=monthly_agg.get("new_count", 0),
            mode="lines+markers", name="จัดตั้งใหม่", line=dict(color=PRIMARY, width=3),
            marker=dict(size=7),
        ))
        fig.add_trace(go.Scatter(
            x=monthly_agg["period_label"], y=monthly_agg.get("closed_count", 0),
            mode="lines+markers", name="เลิกกิจการ", line=dict(color=PINK, width=2.8),
            marker=dict(size=6),
        ))
        if "new_capital_m" in monthly_agg.columns:
            # scale capital to comparable shape for overview, while keeping a clear label in legend
            cap_scaled = monthly_agg["new_capital_m"]
            if cap_scaled.max() > 0 and monthly_agg["new_count"].max() > 0:
                scaled = cap_scaled / cap_scaled.max() * monthly_agg["new_count"].max()
                fig.add_trace(go.Scatter(
                    x=monthly_agg["period_label"], y=scaled,
                    mode="lines+markers", name="เพิ่มทุน (แนวโน้ม)",
                    line=dict(color=CYAN, width=2, dash="dot"),
                    marker=dict(size=5),
                    customdata=np.array(cap_scaled).reshape(-1, 1),
                    hovertemplate="%{x}<br>เพิ่มทุนจริง: %{customdata[0]:,.0f} ลบ.<extra></extra>",
                ))
        fig.update_layout(title="แนวโน้มธุรกิจไทยตั้งแต่ ม.ค. 2568 ถึง เม.ย. 2569")
        fig.update_xaxes(title="เดือน/ปี")
        fig.update_yaxes(title="จำนวน/ดัชนีแนวโน้ม")
        st.plotly_chart(plot_style(fig, height=470), use_container_width=True)

        peak_new = monthly_agg.loc[monthly_agg["new_count"].idxmax()] if "new_count" in monthly_agg.columns and not monthly_agg["new_count"].isna().all() else None
        low_new = monthly_agg.loc[monthly_agg["new_count"].idxmin()] if "new_count" in monthly_agg.columns and not monthly_agg["new_count"].isna().all() else None
        peak_close = monthly_agg.loc[monthly_agg["closed_count"].idxmax()] if "closed_count" in monthly_agg.columns and not monthly_agg["closed_count"].isna().all() else None
        latest_close_rate = (latest_row["closed_count"] / latest_row["new_count"] * 100) if ("closed_count" in latest_row.index and "new_count" in latest_row.index and latest_row["new_count"] > 0) else 0
        bullets = []
        if peak_new is not None:
            bullets.append(f"เดือนที่ <b>จัดตั้งใหม่สูงสุด</b> คือ <b>{peak_new['period_label']}</b> จำนวน <b>{fmt_num(peak_new['new_count'])}</b> ราย")
        if peak_close is not None:
            bullets.append(f"เดือนที่ <b>เลิกกิจการสูงสุด</b> คือ <b>{peak_close['period_label']}</b> จำนวน <b>{fmt_num(peak_close['closed_count'])}</b> ราย")
        if peak_new is not None and low_new is not None:
            bullets.append(f"ช่วงข้อมูลนี้ ตลาดแกว่งอยู่ระหว่าง <b>{fmt_num(low_new['new_count'])}</b> ถึง <b>{fmt_num(peak_new['new_count'])}</b> รายต่อเดือน จึงควรดูแนวโน้มต่อเนื่องมากกว่าดูเดือนเดียว")
        bullets.append(f"ข้อมูลล่าสุด <b>{latest_month_text} {latest_year}</b> มี <b>Closure Rate {fmt_float(latest_close_rate)}%</b> — ขั้นต่อไปควรใช้ตัวเลขนี้ไปเทียบกับหน้า Province / Survival เพื่อหาโซนเสี่ยง")
        summary_box("สรุปจากกราฟแนวโน้ม (อ่านแบบง่าย ๆ)", bullets)

with tab2:
    st.markdown("### Leaderboards ที่อ่านง่าย")
    l1, l2 = st.columns([1, 1])
    with l1:
        st.markdown("#### จังหวัดเด่นเดือนล่าสุด")
        if not latest_view.empty and {"province", "new_count"}.issubset(latest_view.columns):
            top_p = latest_view.sort_values("new_count", ascending=False)
            ranked_list(top_p, "province", "new_count", unit="ราย", n=8)
            summary_box("ควรอ่านอย่างไร", [
                "จังหวัดอันดับต้น ๆ คือพื้นที่ที่มีการเปิดธุรกิจใหม่หนาแน่น เหมาะใช้เป็น <b>benchmark</b> ก่อนตัดสินใจขยายตลาด",
                "ขั้นต่อไป: ไปดูหน้า <b>Province Intelligence</b> เพื่อเช็กต่อว่าจังหวัดเหล่านี้มีความเสี่ยงปิดกิจการสูงหรือต่ำ",
            ])
        else:
            st.info("ยังไม่มีข้อมูลจังหวัด")
    with l2:
        st.markdown("#### กลุ่มธุรกิจเด่นปี 2569")
        if not biz69.empty and {"type", "regis_count"}.issubset(biz69.columns):
            top_b = biz69.sort_values("regis_count", ascending=False)
            ranked_list(top_b, "type", "regis_count", unit="ราย", n=8)
            if not group_reg.empty:
                top_group_name = group_reg.iloc[0]["business_group"]
                example_types = biz69[biz69["business_group"] == top_group_name].sort_values("regis_count", ascending=False).head(3)["type"].tolist()
                examples = ", ".join(example_types)
            else:
                top_group_name, examples = "-", "-"
            summary_box("Action ที่ควรทำต่อ", [
                f"กลุ่มที่แรงสุดตอนนี้คือ <b>{top_group_name}</b> — ขั้นต่อไปควรลงไปดูว่าภายในกลุ่มนี้มีธุรกิจย่อยอะไรเด่น เช่น <b>{examples}</b>",
                "ถ้าต้องการหาไอเดียธุรกิจจริง ควรเลือกจากกลุ่มที่ <b>เปิดใหม่เยอะ + ความเสี่ยงไม่สูงเกินไป</b> ไม่ใช่ดูแค่จำนวนเปิดใหม่อย่างเดียว",
            ])
        else:
            st.info("ยังไม่มีข้อมูลประเภทธุรกิจ")

with tab3:
    st.markdown("### SME Size Mix")
    if size_df.empty or size_df["count"].sum() == 0:
        st.info("ยังไม่มีข้อมูลขนาดธุรกิจ S/M/L")
    else:
        size_colors = {"S": PRIMARY, "M": PINK, "L": CYAN}

        # วงใหญ่ให้อยู่บรรทัดบนเต็มพื้นที่ เพื่ออ่านง่าย
        st.plotly_chart(overall_size_mix_donut(size_df), use_container_width=True, key="exec_size_mix_overall_fixed")

        # กราฟย่อย 3 อันให้อยู่บรรทัดใหม่ตามที่ขอ
        c_s, c_m, c_l = st.columns(3)
        with c_s:
            row = size_df[size_df["size"] == "S"].iloc[0]
            st.plotly_chart(size_share_donut("ขนาด S", "S", float(row["share"]), PRIMARY, total=float(row["count"])), use_container_width=True, key="exec_size_mix_s_fixed")
        with c_m:
            row = size_df[size_df["size"] == "M"].iloc[0]
            st.plotly_chart(size_share_donut("ขนาด M", "M", float(row["share"]), PINK, total=float(row["count"])), use_container_width=True, key="exec_size_mix_m_fixed")
        with c_l:
            row = size_df[size_df["size"] == "L"].iloc[0]
            st.plotly_chart(size_share_donut("ขนาด L", "L", float(row["share"]), CYAN, total=float(row["count"])), use_container_width=True, key="exec_size_mix_l_fixed")

        s_share = float(size_df.loc[size_df["size"] == "S", "share"].iloc[0])
        m_share = float(size_df.loc[size_df["size"] == "M", "share"].iloc[0])
        l_share = float(size_df.loc[size_df["size"] == "L", "share"].iloc[0])
        summary_box("คนไม่เคยดูกราฟก็อ่านได้", [
            f"วงใหญ่ตรงกลางบอกภาพรวมว่า <b>ธุรกิจขนาด S ครองสัดส่วนมากสุด {s_share:.1f}%</b> หมายถึงตลาดส่วนใหญ่ยังเป็นผู้เล่นรายเล็ก",
            f"วง S/M/L ด้านขวาเอาไว้ดูแยกทีละขนาด: ตอนนี้ <b>M = {m_share:.1f}%</b> และ <b>L = {l_share:.1f}%</b>",
            "ขั้นต่อไป: ถ้าอยากทำธุรกิจใหม่ ควรดูต่อว่าในขนาดที่ตนเองสนใจมีการแข่งขันสูงหรือไม่ และต้องใช้เงินทุนระดับไหนในหน้า Category / Survival",
            "นิยามขนาดทุนตามชุดข้อมูล: <b>S &lt; 1 ล้านบาท</b>, <b>M = 1–10 ล้านบาท</b>, <b>L &gt; 10 ล้านบาท</b>",
        ])

with tab4:
    st.markdown("### Top Rankings")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("#### Top 10 จังหวัด Net Growth สูงสุด")
        if not latest_view.empty and {"province", "net_growth"}.issubset(latest_view.columns):
            df_top_p = latest_view.sort_values("net_growth", ascending=False).head(10).copy()
            df_top_p["province_wrap"] = df_top_p["province"].apply(lambda x: wrap_label(x, 16))
            fig = px.bar(df_top_p.sort_values("net_growth"), x="net_growth", y="province_wrap", orientation="h", text="net_growth", color_discrete_sequence=[PRIMARY])
            fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig.update_layout(title="จังหวัดที่มีส่วนต่างจัดตั้งใหม่มากกว่าเลิกกิจการสูงสุด")
            fig.update_xaxes(title="จำนวนสุทธิ (ราย)")
            fig.update_yaxes(title="จังหวัด")
            st.plotly_chart(plot_style(fig, height=480, showlegend=False), use_container_width=True)
            summary_box("สรุปสั้น ๆ", [
                "แท่งยิ่งยาว แปลว่าจังหวัดนั้นมีแรงส่งทางธุรกิจสูงในเดือนล่าสุด",
                "ขั้นต่อไป: เลือก 1–2 จังหวัดจากกราฟนี้ แล้วไปดูหน้า Province Intelligence เพื่อวิเคราะห์เชิงลึกเรื่องความเสี่ยงและโครงสร้างธุรกิจ",
            ])
        else:
            st.info("ยังไม่มีข้อมูลจังหวัด")
    with r2:
        st.markdown("#### Top 10 ธุรกิจจัดตั้งใหม่สูงสุด")
        if not biz69.empty and {"type", "regis_count"}.issubset(biz69.columns):
            df_top_b = biz69.sort_values("regis_count", ascending=False).head(10).copy()
            df_top_b["type_wrap"] = df_top_b["type"].apply(lambda x: wrap_label(x, 26))
            fig = px.bar(df_top_b.sort_values("regis_count"), x="regis_count", y="type_wrap", orientation="h", text="regis_count", color_discrete_sequence=[PINK])
            fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            fig.update_layout(title="ประเภทธุรกิจที่มีผู้เล่นใหม่มากที่สุด")
            fig.update_xaxes(title="จำนวนจัดตั้งใหม่ (ราย)")
            fig.update_yaxes(title="ประเภทธุรกิจ")
            st.plotly_chart(plot_style(fig, height=480, showlegend=False), use_container_width=True)
            summary_box("สรุปสั้น ๆ", [
                "ธุรกิจที่อยู่อันดับต้น ๆ คือหมวดที่ตลาดเห็นดีมานด์ชัด แต่ไม่ได้แปลว่าทำแล้วชนะทันที เพราะอาจมีการแข่งขันสูงด้วย",
                "ขั้นต่อไป: ดูหน้า Business Category เพื่อเทียบ <b>โอกาส</b>, <b>ความเสี่ยง</b> และ <b>เงินทุนเฉลี่ย</b> ของประเภทธุรกิจที่สนใจ",
            ])
        else:
            st.info("ยังไม่มีข้อมูลประเภทธุรกิจ")

with tab5:
    st.markdown("### Opportunity vs Risk Snapshot")
    if latest_view.empty or not {"province", "new_count", "closed_count"}.issubset(latest_view.columns):
        st.info("ข้อมูลจังหวัดไม่เพียงพอสำหรับทำกราฟ Opportunity vs Risk")
    else:
        df = latest_view.copy()
        if "closure_rate" not in df.columns:
            df["closure_rate"] = np.where(df["new_count"] > 0, df["closed_count"] * 100 / df["new_count"], np.nan)
        if "active_count" not in df.columns:
            df["active_count"] = 1
        df["bubble_size"] = pd.to_numeric(df["active_count"], errors="coerce").fillna(1).clip(lower=1)
        df["label"] = df["province"].apply(lambda x: wrap_label(x, 12))
        fig = px.scatter(
            df,
            x="new_count",
            y="closure_rate",
            size="bubble_size",
            color="net_growth" if "net_growth" in df.columns else "new_count",
            hover_name="province",
            color_continuous_scale="Viridis",
            size_max=45,
            title="จังหวัด: จำนวนจัดตั้งใหม่ เทียบกับอัตราเลิกกิจการ",
        )
        fig.add_vline(x=df["new_count"].median(), line_dash="dash", line_color="rgba(255,255,255,0.45)")
        fig.add_hline(y=df["closure_rate"].median(skipna=True), line_dash="dash", line_color="rgba(255,255,255,0.45)")
        fig.update_xaxes(title="จำนวนจัดตั้งใหม่ (ราย)")
        fig.update_yaxes(title="อัตราเลิกกิจการ (%)")
        st.plotly_chart(plot_style(fig, height=520), use_container_width=True)

        # concise summary
        q1 = df[(df["new_count"] >= df["new_count"].median()) & (df["closure_rate"] <= df["closure_rate"].median(skipna=True))]
        best = q1.sort_values(["new_count", "closure_rate"], ascending=[False, True]).head(3)["province"].tolist()
        risky = df.sort_values(["closure_rate", "new_count"], ascending=[False, False]).head(3)["province"].tolist()
        summary_box("สรุปที่กราฟนี้ต้องการสื่อ", [
            f"จุดที่อยู่ <b>ขวาล่าง</b> น่าสนใจกว่า เพราะเปิดใหม่เยอะ แต่เลิกกิจการไม่สูงมาก — จังหวัดเด่นเบื้องต้น เช่น <b>{', '.join(best) if best else '-'}</b>",
            f"จุดที่อยู่ <b>ซ้ายบน / บนสูง</b> ควรระวัง เพราะเลิกกิจการสูงเมื่อเทียบกับการเปิดใหม่ — จังหวัดที่ควรจับตา เช่น <b>{', '.join(risky) if risky else '-'}</b>",
            "ขั้นต่อไป: ถ้าจะเลือกจังหวัดเปิดกิจการ ควรเริ่มจากจังหวัดที่อยู่โซนขวาล่าง แล้วค่อยลงลึกต่อเรื่องประเภทธุรกิจและขนาดเงินทุน",
        ])

with tab6:
    st.markdown("### บทสรุปฉบับผู้บริหาร")
    # derive insights
    insights = []
    if start_row is not None:
        insights.append(f"ข้อมูลอ้างอิงหลักของหน้านี้คือ <b>{start_row['month']} {int(start_row['year'])}</b> ถึง <b>{latest_month_text} {latest_year}</b> และตัวชี้วัด snapshot ใช้เดือนล่าสุดคือ <b>{latest_month_text} {latest_year}</b>")
    if total_net >= 0:
        insights.append(f"ภาพรวมเดือนล่าสุดยังเป็นบวก: <b>จัดตั้งใหม่มากกว่าเลิกกิจการ {fmt_num(total_net)} ราย</b> — ขั้นต่อไปคือคัดจังหวัด/กลุ่มธุรกิจที่น่าสนใจจากหน้า Leaderboards และ Category")
    else:
        insights.append(f"ภาพรวมเดือนล่าสุดเป็นลบ: <b>เลิกกิจการมากกว่าจัดตั้งใหม่ {fmt_num(abs(total_net))} ราย</b> — ขั้นต่อไปควรเน้นกลุ่มธุรกิจที่มี demand สูงแต่ความเสี่ยงต่ำ")
    insights.append(f"Closure Rate ล่าสุดอยู่ที่ <b>{fmt_float(close_rate)}%</b> — ขั้นต่อไปคือไปตรวจสอบต่อในหน้า Survival ว่าธุรกิจประเภทใดอยู่รอดดีกว่าค่าเฉลี่ย")
    if not group_reg.empty:
        top_group_name = group_reg.iloc[0]["business_group"]
        top_group_count = group_reg.iloc[0]["regis_count"]
        examples = []
        if "business_group" in biz69.columns and "type" in biz69.columns:
            examples = biz69[biz69["business_group"] == top_group_name].sort_values("regis_count", ascending=False).head(4)["type"].tolist()
        if top_group_name == "ขายส่ง/ขายปลีก":
            example_text = "ตัวอย่างเช่น ร้านค้าปลีกทั่วไป, ขายอาหาร/เครื่องดื่ม, ร้านออนไลน์, ขายอุปกรณ์อุปโภคบริโภค"
        else:
            example_text = "ตัวอย่างธุรกิจย่อย: " + ", ".join(examples) if examples else ""
        insights.append(f"กลุ่มธุรกิจที่มีผู้เล่นใหม่มากที่สุดคือ <b>{top_group_name}</b> ({fmt_num(top_group_count)} ราย) — {example_text}. ขั้นต่อไปคือเลือก niche ภายในกลุ่มที่ยังไม่แออัดเกินไป")
    if not size_df.empty and size_df['count'].sum() > 0:
        s_share = float(size_df.loc[size_df['size'] == 'S', 'share'].iloc[0])
        insights.append(f"ธุรกิจขนาด <b>S ครองสัดส่วน {s_share:.1f}% </b> ของข้อมูล S/M/L — สะท้อนว่าตลาดเริ่มต้นจำนวนมากเป็นผู้ประกอบการรายเล็ก ดังนั้นผู้เริ่มต้นควรเตรียมแผนแข่งกับ SME ให้ชัด")

    # nicer layout
    left, right = st.columns([1.35, 1])
    with left:
        summary_box("Bottom Line", insights)
    with right:
        next_steps = [
            "<b>Step 1:</b> ดูแท็บ Leaderboards เพื่อคัดจังหวัดและประเภทธุรกิจที่น่าสนใจ",
            "<b>Step 2:</b> เปิดหน้า Business Category เพื่อเช็กว่าธุรกิจที่สนใจ 'โอกาสสูง / เสี่ยงต่ำ' หรือไม่",
            "<b>Step 3:</b> เปิดหน้า Province Intelligence เพื่อดูว่าจังหวัดที่เล็งไว้มีแรงเติบโตจริงไหม",
            "<b>Step 4:</b> ใช้หน้า Survival Analysis เพื่อตรวจสอบความอยู่รอดก่อนตัดสินใจลงทุน",
        ]
        summary_box("ควรทำอะไรต่อหลังอ่านหน้านี้", next_steps)
        st.markdown(
            f"<div class='note-box'><div class='note-title'>หมายเหตุการตีความ</div><div style='color:#e2e8f0'>ตัวเลขในหน้านี้เป็นข้อมูลเชิงสถิติจากชุดข้อมูลที่มี ไม่ใช่คำรับรองผลสำเร็จทางธุรกิจ ดังนั้นควรใช้ร่วมกับข้อมูลลูกค้า ต้นทุน คู่แข่ง และทำเลจริงก่อนตัดสินใจ</div></div>",
            unsafe_allow_html=True,
        )
