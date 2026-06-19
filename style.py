import streamlit as st
import plotly.io as pio

PRIMARY = "#a855f7"
SECONDARY = "#ec4899"
ACCENT = "#14b8a6"
WARNING = "#f59e0b"
DANGER = "#ef4444"
SUCCESS = "#22c55e"
BG = "#0b1020"
CARD = "#111827"
TEXT = "#f8fafc"
MUTED = "#94a3b8"

COLORWAY = ["#a855f7", "#ec4899", "#14b8a6", "#38bdf8", "#f59e0b", "#22c55e", "#ef4444", "#64748b"]


def apply_theme():
    st.markdown(
        f"""
        <style>
        :root {{
          --primary: {PRIMARY};
          --secondary: {SECONDARY};
          --accent: {ACCENT};
          --card: {CARD};
          --muted: {MUTED};
        }}
        .block-container {{
            padding-top: 1.7rem;
            padding-bottom: 2.2rem;
            max-width: 1280px;
        }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
        }}
        h1, h2, h3 {{ letter-spacing: -0.025em; }}
        .hero-card {{
            padding: 1.35rem 1.5rem;
            border-radius: 22px;
            background: radial-gradient(circle at top left, rgba(168,85,247,.25), transparent 32%),
                        linear-gradient(135deg, #111827 0%, #0f172a 100%);
            border: 1px solid rgba(148,163,184,.18);
            box-shadow: 0 16px 40px rgba(0,0,0,.22);
            margin-bottom: 1rem;
        }}
        .hero-title {{
            font-size: 2.1rem;
            font-weight: 850;
            margin-bottom: .35rem;
            color: #f8fafc;
        }}
        .hero-subtitle {{
            color: #cbd5e1;
            font-size: 1.02rem;
            line-height: 1.55;
        }}
        .metric-card {{
            padding: 1rem 1rem .95rem 1rem;
            border-radius: 18px;
            background: linear-gradient(180deg, rgba(17,24,39,.96), rgba(15,23,42,.92));
            border: 1px solid rgba(148,163,184,.18);
            min-height: 116px;
            box-shadow: 0 8px 22px rgba(0,0,0,.18);
        }}
        .metric-label {{
            color: #94a3b8;
            font-size: .78rem;
            text-transform: uppercase;
            letter-spacing: .04em;
            margin-bottom: .4rem;
        }}
        .metric-value {{
            color: #f8fafc;
            font-size: 1.65rem;
            font-weight: 800;
            line-height: 1.1;
        }}
        .metric-delta {{
            color: #cbd5e1;
            margin-top: .42rem;
            font-size: .85rem;
        }}
        .glass-card {{
            padding: 1.1rem 1.15rem;
            border-radius: 18px;
            background: rgba(17,24,39,.74);
            border: 1px solid rgba(148,163,184,.16);
            box-shadow: 0 10px 24px rgba(0,0,0,.16);
            margin-bottom: 1rem;
        }}
        .section-eyebrow {{
            color: {ACCENT};
            font-weight: 700;
            font-size: .82rem;
            text-transform: uppercase;
            letter-spacing: .055em;
            margin-bottom: .12rem;
        }}
        .insight-list li {{
            margin: .35rem 0;
        }}
        .pill {{
            display:inline-block;
            padding: .22rem .55rem;
            border-radius: 999px;
            background: rgba(168,85,247,.18);
            border: 1px solid rgba(168,85,247,.28);
            color: #e9d5ff;
            font-size: .78rem;
            margin-right: .3rem;
        }}
        .stTabs [data-baseweb="tab-list"] {{ gap: .45rem; }}
        .stTabs [data-baseweb="tab"] {{
            padding: .55rem 1rem;
            border-radius: 999px;
            background: rgba(148,163,184,.08);
        }}
        div[data-testid="stDataFrame"] {{
            border-radius: 14px;
            overflow: hidden;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def configure_plotly():
    template = pio.templates["plotly_dark"].layout.template
    pio.templates.default = "plotly_dark"


def fig_layout(fig, title=None, height=420, showlegend=True):
    fig.update_layout(
        title=title,
        height=height,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17,24,39,.15)",
        font=dict(family="Tahoma, Noto Sans Thai, Arial", size=13, color="#e5e7eb"),
        colorway=COLORWAY,
        margin=dict(l=20, r=20, t=65 if title else 30, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1) if showlegend else dict(),
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,.15)", zerolinecolor="rgba(148,163,184,.2)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,.15)", zerolinecolor="rgba(148,163,184,.2)")
    return fig


def fmt_int(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "-"


def fmt_million(x):
    try:
        return f"{float(x):,.2f} ลบ."
    except Exception:
        return "-"


def fmt_pct(x):
    try:
        return f"{float(x):,.2f}%"
    except Exception:
        return "-"


def metric_card(label, value, delta=None, help_text=None):
    delta_html = f'<div class="metric-delta">{delta}</div>' if delta else ""
    help_html = f'<div class="metric-delta" style="color:#94a3b8">{help_text}</div>' if help_text else ""
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            {delta_html}
            {help_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(title, subtitle, pills=None):
    pills_html = ""
    if pills:
        pills_html = "<div style='margin-top:.9rem'>" + "".join([f"<span class='pill'>{p}</span>" for p in pills]) + "</div>"
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-title">{title}</div>
            <div class="hero-subtitle">{subtitle}</div>
            {pills_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
