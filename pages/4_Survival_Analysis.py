# -*- coding: utf-8 -*-
"""
4_Survival_Analysis.py
Survival / Risk page for ThaiBiz Streamlit app.

ปรับตาม survival.pdf:
- ทำเป็นแท็บเหมือน page อื่น
- เพิ่ม slider + ช่องกรอกเลข
- Survival Rate เป็นกราฟต้น-ใบ / lollipop สีเขียว=รอด สีแดง=ร่วง
- Red Ocean Index เป็น gauge chart
- Risk Score ภาษาไทย + บอกสูตร + แหล่งไฟล์ + เดือน/ปี
- ตัดกราฟจังหวัดซ้ำกับหน้า Province/Category ออก
- เพิ่ม SME S/M/L warning, Monthly Risk Bubble, Bullet Chart/Test ก่อนลงทุน
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from db import ensure_database_ready, query_df, table_exists
    ensure_database_ready(auto_refresh=True)
except Exception:
    ensure_database_ready = None
    query_df = None
    table_exists = None

try:
    from data_loader import DATA_DIR, data_files
except Exception:
    DATA_DIR = Path(__file__).resolve().parents[1] / "data"

    def data_files() -> list[Path]:
        return sorted(DATA_DIR.glob("*.csv"))

try:
    from style import apply_theme, configure_plotly, page_header, metric_card, fig_layout
except Exception:
    def apply_theme():
        st.markdown(
            """
            <style>
            .glass-card{background:rgba(15,23,42,.72);border:1px solid rgba(148,163,184,.25);border-radius:18px;padding:20px;margin:10px 0;}
            .section-eyebrow{color:#14b8a6;text-transform:uppercase;letter-spacing:.08em;font-size:.78rem;font-weight:800;margin-bottom:10px;}
            .insight-list li{margin:.45rem 0;}
            </style>
            """,
            unsafe_allow_html=True,
        )

    def configure_plotly():
        pass

    def page_header(title, subtitle, pills=None):
        st.title(title)
        st.caption(subtitle)
        if pills:
            st.write(" · ".join(pills))

    def metric_card(label, value, help_text=""):
        st.metric(label, value, help_text)

    def fig_layout(fig, title=None, height=480, showlegend=True):
        fig.update_layout(
            title=title,
            height=height,
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=showlegend,
            margin=dict(l=20, r=20, t=80, b=50),
            font=dict(family="Tahoma, Arial", color="#f8fafc"),
        )
        return fig

apply_theme()
configure_plotly()

PRIMARY = "#a855f7"
PINK = "#ec4899"
ACCENT = "#14b8a6"
GREEN = "#22c55e"
RED = "#ef4444"
YELLOW = "#f59e0b"
BLUE = "#38bdf8"
GRAY = "rgba(148,163,184,.55)"
MUTED = "#94a3b8"
WHITE = "#f8fafc"

GROUP_COLORS = {
    "บริการ": "#a855f7",
    "ขายส่ง/ขายปลีก": "#ec4899",
    "ก่อสร้าง/อสังหาฯ": "#14b8a6",
    "ผลิต": "#38bdf8",
    "อาหาร/เครื่องดื่ม": "#f59e0b",
    "ขนส่ง/โลจิสติกส์": "#22c55e",
    "เทคโนโลยี": "#ef4444",
    "สุขภาพ/การศึกษา": "#c084fc",
    "เกษตร": "#84cc16",
    "อื่น ๆ": "#94a3b8",
}

TH_PROVINCES = [
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา",
    "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก",
    "นครปฐม", "นครพนม", "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน",
    "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา",
    "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์", "แพร่", "ภูเก็ต",
    "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง", "ราชบุรี",
    "ลพบุรี", "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ",
    "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี",
    "สุรินทร์", "หนองคาย", "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์",
    "อุทัยธานี", "อุบลราชธานี",
]

PROVINCE_ALIASES = {
    "กรุงเทพ": "กรุงเทพมหานคร",
    "กทม": "กรุงเทพมหานคร",
    "กทม.": "กรุงเทพมหานคร",
    "พระนครศรีอยุธยา": "พระนครศรีอยุธยา",
}


MONTH_LABELS = {
    "jan": "ม.ค.", "feb": "ก.พ.", "mar": "มี.ค.", "apr": "เม.ย.",
    "may": "พ.ค.", "jun": "มิ.ย.", "jul": "ก.ค.", "aug": "ส.ค.",
    "sep": "ก.ย.", "oct": "ต.ค.", "nov": "พ.ย.", "dec": "ธ.ค.",
}
MONTH_FULL = {"jan": "มกราคม", "feb": "กุมภาพันธ์", "mar": "มีนาคม", "apr": "เมษายน"}
LATEST_MONTH_TEXT = "เมษายน 2569"


# ============================================================
# Helpers
# ============================================================

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s))
    s = s.replace("ประเเภท", "ประเภท").replace("quiz", "quit").replace("เเ", "แ")
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _clean(s) -> str:
    return str(s).replace("\ufeff", "").strip()


def _to_num(x) -> pd.Series:
    return pd.to_numeric(
        pd.Series(x)
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("-", "0", regex=False)
        .str.strip(),
        errors="coerce",
    ).fillna(0)


def _fmt_int(x) -> str:
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "-"


def _fmt_float(x, digits: int = 2) -> str:
    try:
        return f"{float(x):,.{digits}f}"
    except Exception:
        return "-"


def _wrap_label(text: str, width: int = 28, max_lines: int = 3) -> str:
    s = str(text)
    if len(s) <= width:
        return s
    parts = [s[i:i+width] for i in range(0, len(s), width)]
    if len(parts) > max_lines:
        parts = parts[:max_lines]
        parts[-1] = parts[-1] + "…"
    return "<br>".join(parts)


def _business_group(text: str) -> str:
    s = str(text)
    if any(k in s for k in ["ขาย", "ค้าปลีก", "ค้าส่ง", "ตลาด", "จำหน่าย"]):
        return "ขายส่ง/ขายปลีก"
    if any(k in s for k in ["ผลิต", "โรงงาน", "แปรรูป", "อุตสาหกรรม"]):
        return "ผลิต"
    if any(k in s for k in ["ก่อสร้าง", "อสังหาริมทรัพย์", "อาคาร", "บ้าน", "คอนโด"]):
        return "ก่อสร้าง/อสังหาฯ"
    if any(k in s for k in ["อาหาร", "ภัตตาคาร", "ร้านอาหาร", "เครื่องดื่ม", "กาแฟ", "ขนม"]):
        return "อาหาร/เครื่องดื่ม"
    if any(k in s for k in ["ขนส่ง", "คลังสินค้า", "โลจิสติกส์", "เดินรถ", "ขนถ่าย"]):
        return "ขนส่ง/โลจิสติกส์"
    if any(k in s for k in ["ซอฟต์แวร์", "คอมพิวเตอร์", "ข้อมูล", "เทคโนโลยี", "ดิจิทัล", "ออนไลน์", "อินเทอร์เน็ต"]):
        return "เทคโนโลยี"
    if any(k in s for k in ["การศึกษา", "สุขภาพ", "แพทย์", "โรงพยาบาล", "คลินิก", "เภสัช"]):
        return "สุขภาพ/การศึกษา"
    if any(k in s for k in ["ปลูก", "เลี้ยง", "ประมง", "เกษตร", "ฟาร์ม"]):
        return "เกษตร"
    if any(k in s for k in ["บริการ", "ให้เช่า", "ซ่อม", "ที่ปรึกษา", "บริหาร", "กิจกรรม"]):
        return "บริการ"
    return "อื่น ๆ"


def _normalize_score(s: pd.Series, inverse: bool = False) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0)
    if len(x) == 0 or x.max() == x.min():
        out = pd.Series(50, index=x.index)
    else:
        out = (x - x.min()) / (x.max() - x.min()) * 100
    return 100 - out if inverse else out


def _type_key(s: str) -> str:
    return _norm(str(s))[:150]


def _all_files() -> list[Path]:
    paths = []
    if DATA_DIR.exists():
        for pat in ["*.csv", "*.xlsx", "*.xls", "*.xlsm"]:
            paths.extend(DATA_DIR.glob(pat))
    try:
        paths.extend(data_files())
    except Exception:
        pass
    # For this sandbox while generating files; harmless in user's app because /mnt/data won't exist there.
    try:
        paths.extend(Path("/mnt/data").glob("*.csv"))
        paths.extend(Path("/mnt/data").glob("*.xlsx"))
        paths.extend(Path("/mnt/data").glob("*.xls"))
    except Exception:
        pass
    out, seen = [], set()
    for p in paths:
        if p.exists() and p not in seen:
            out.append(p)
            seen.add(p)
    return sorted(out)


def _find_files(*keywords: str, year: int | None = None) -> list[Path]:
    keys = [_norm(k) for k in keywords]
    yy = str(year)[-2:] if year else None
    out = []
    for f in _all_files():
        n = _norm(f.name)
        if yy and yy not in n:
            continue
        if all(k in n for k in keys):
            out.append(f)
    return sorted(out)


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        last_error = None
        for enc in ["utf-8-sig", "utf-8", "cp874", "tis-620"]:
            try:
                df = pd.read_csv(path, encoding=enc)
                df.columns = [_clean(c) for c in df.columns]
                return df
            except Exception as e:
                last_error = e
        raise RuntimeError(f"อ่านไฟล์ {path.name} ไม่ได้: {last_error}")
    df = pd.read_excel(path)
    df.columns = [_clean(c) for c in df.columns]
    return df


def _source_file_names(*keywords: str, year: int | None = None) -> str:
    files = _find_files(*keywords, year=year)
    return ", ".join([f.name for f in files]) if files else "-"


def _dedupe_type(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "type" not in df.columns:
        return df
    d = df.copy()
    d["type_key"] = d["type"].apply(_type_key)
    sort_cols = [c for c in ["risk_score", "total_regis", "regis_count", "survival_rate", "active_count"] if c in d.columns]
    if sort_cols:
        d = d.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return d.drop_duplicates("type_key", keep="first").drop(columns=["type_key"], errors="ignore")



def _survival_from_duckdb(year: int = 2569) -> pd.DataFrame:
    """โหลดข้อมูล survival จาก DuckDB table business_2569/business_2568 ถ้ามี"""
    if query_df is None or table_exists is None:
        return pd.DataFrame()

    table_name = f"business_{year}"
    try:
        if not table_exists(table_name):
            return pd.DataFrame()
        df = query_df(f'SELECT * FROM "{table_name}"')
    except Exception:
        return pd.DataFrame()

    if df.empty or "type" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    # map columns from business page to survival page naming
    rename_map = {
        "regis_count": "total_regis",
        "quit_count": "total_quit",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # preserve original names too when useful
    if "total_regis" not in df.columns:
        df["total_regis"] = 0
    if "total_quit" not in df.columns:
        df["total_quit"] = 0
    if "active_count" not in df.columns:
        df["active_count"] = 0
    if "regis_capital_m" not in df.columns:
        df["regis_capital_m"] = 0
    if "quit_capital_m" not in df.columns:
        df["quit_capital_m"] = 0

    needed = [
        "jan_regis", "feb_regis", "mar_regis", "apr_regis", "total_regis", "regis_capital_m",
        "jan_quit", "feb_quit", "mar_quit", "apr_quit", "total_quit", "quit_capital_m",
        "active_count", "active_capital_m", "size_s_count", "size_m_count", "size_l_count", "size_total_count",
        "size_s_capital_m", "size_m_capital_m", "size_l_capital_m", "size_total_capital_m",
    ]
    for c in needed:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    if "type_key" not in df.columns:
        df["type_key"] = df["type"].apply(_type_key)
    df["type"] = df["type"].astype(str).str.strip()
    df = df[~df["type"].str.contains("รวม|หมายเหตุ|nan", case=False, na=False)]

    denom = df["active_count"] + df["total_quit"]
    df["survival_rate"] = np.where(denom > 0, df["active_count"] / denom * 100, np.nan)
    df["fall_rate"] = 100 - df["survival_rate"].fillna(0)
    df["closure_rate"] = np.where(df["total_regis"] > 0, df["total_quit"] / df["total_regis"] * 100, 0)
    df["red_ocean_index"] = np.where(df["active_count"] > 0, df["total_regis"] / df["active_count"] * 100, np.nan)
    df["avg_quit_capital_m"] = np.where(df["total_quit"] > 0, df["quit_capital_m"] / df["total_quit"], np.nan)
    df["avg_regis_capital_m"] = np.where(df["total_regis"] > 0, df["regis_capital_m"] / df["total_regis"], np.nan)
    if "business_group" not in df.columns:
        df["business_group"] = df["type"].apply(_business_group)
    df["sme_share"] = np.where(df["size_total_count"] > 0, df["size_s_count"] / df["size_total_count"] * 100, np.nan)

    red_score = _normalize_score(df["red_ocean_index"].replace([np.inf, -np.inf], np.nan).fillna(0))
    closure_score = _normalize_score(df["closure_rate"].fillna(0))
    fall_score = _normalize_score(df["fall_rate"].fillna(0))
    df["risk_score"] = (0.45 * fall_score + 0.35 * closure_score + 0.20 * red_score).clip(0, 100)
    df["year"] = year

    return _dedupe_type(df.reset_index(drop=True))


# ============================================================
# Loaders
# ============================================================

@st.cache_data(show_spinner=False)
def load_survival_business_data() -> pd.DataFrame:
    duck_df = _survival_from_duckdb(2569)
    if not duck_df.empty:
        return duck_df

    regis_files = _find_files("ประเภท", "regis", year=2569) or _find_files("ประเภท", "จัดตั้ง", year=2569)
    quit_files = _find_files("ประเภท", "quit", year=2569) or _find_files("ประเภท", "เลิก", year=2569)
    active_files = _find_files("ประเภท", "active", year=2569) or _find_files("ประเภท", "ดำเนิน", year=2569)
    size_files = _find_files("ประเภท", "size", year=2569) or _find_files("ประเภท", "ขนาด", year=2569)

    pieces = []

    if regis_files:
        r = _read_table(regis_files[0])
        r = r.rename(columns={c: c.lower() for c in r.columns})
        if "type" in r.columns:
            reg_cols = [c for c in r.columns if c.endswith("_regis") or c in ["total_regis"]]
            keep = ["type"] + reg_cols + [c for c in ["jan_m", "feb_m", "mar_m", "apr_m", "total_m"] if c in r.columns]
            r = r[keep].copy()
            for c in r.columns:
                if c != "type":
                    r[c] = _to_num(r[c])
            r = r.rename(columns={"total_regis": "total_regis", "total_m": "regis_capital_m"})
            r["type_key"] = r["type"].apply(_type_key)
            pieces.append(r)

    if quit_files:
        q = _read_table(quit_files[0])
        q = q.rename(columns={c: c.lower() for c in q.columns})
        if "type" in q.columns:
            keep = ["type"] + [c for c in q.columns if c.endswith("_quit") or c in ["total_quit", "jan_m", "feb_m", "mar_m", "apr_m", "total_m"]]
            q = q[keep].copy()
            for c in q.columns:
                if c != "type":
                    q[c] = _to_num(q[c])
            q = q.rename(columns={"total_quit": "total_quit", "total_m": "quit_capital_m"})
            q["type_key"] = q["type"].apply(_type_key)
            pieces.append(q.drop(columns=["type"], errors="ignore"))

    if active_files:
        a = _read_table(active_files[0])
        a = a.rename(columns={c: c.lower() for c in a.columns})
        if "type" in a.columns:
            a = a.copy()
            for c in a.columns:
                if c != "type":
                    a[c] = _to_num(a[c])
            a = a.rename(columns={"p": "active_count", "m": "active_capital_m"})
            a["type_key"] = a["type"].apply(_type_key)
            pieces.append(a[[c for c in ["type_key", "active_count", "active_capital_m"] if c in a.columns]])

    if size_files:
        s = _read_table(size_files[0])
        s = s.rename(columns={c: c.lower() for c in s.columns})
        if "type" in s.columns:
            for c in s.columns:
                if c != "type":
                    s[c] = _to_num(s[c])
            s["type_key"] = s["type"].apply(_type_key)
            rename_map = {
                "p_s": "size_s_count", "p_m": "size_m_count", "p_l": "size_l_count", "p_total": "size_total_count",
                "m_s": "size_s_capital_m", "m_m": "size_m_capital_m", "m_l": "size_l_capital_m", "m_total": "size_total_capital_m",
            }
            s = s.rename(columns=rename_map)
            keep = ["type_key"] + [c for c in rename_map.values() if c in s.columns]
            pieces.append(s[keep])

    if not pieces:
        return pd.DataFrame()

    df = pieces[0]
    for p in pieces[1:]:
        df = df.merge(p, on="type_key", how="outer")

    if "type" not in df.columns:
        df["type"] = df["type_key"]
    df["type"] = df["type"].astype(str).str.strip()
    df = df[~df["type"].str.contains("รวม|หมายเหตุ|nan", case=False, na=False)]

    needed = [
        "jan_regis", "feb_regis", "mar_regis", "apr_regis", "total_regis", "regis_capital_m",
        "jan_quit", "feb_quit", "mar_quit", "apr_quit", "total_quit", "quit_capital_m",
        "active_count", "active_capital_m", "size_s_count", "size_m_count", "size_l_count", "size_total_count",
        "size_s_capital_m", "size_m_capital_m", "size_l_capital_m", "size_total_capital_m",
    ]
    for c in needed:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    # Survival formula requested in PDF:
    # active / (active + quit) * 100
    denom = df["active_count"] + df["total_quit"]
    df["survival_rate"] = np.where(denom > 0, df["active_count"] / denom * 100, np.nan)
    df["fall_rate"] = 100 - df["survival_rate"].fillna(0)
    df["closure_rate"] = np.where(df["total_regis"] > 0, df["total_quit"] / df["total_regis"] * 100, 0)
    df["red_ocean_index"] = np.where(df["active_count"] > 0, df["total_regis"] / df["active_count"] * 100, np.nan)
    df["avg_quit_capital_m"] = np.where(df["total_quit"] > 0, df["quit_capital_m"] / df["total_quit"], np.nan)
    df["avg_regis_capital_m"] = np.where(df["total_regis"] > 0, df["regis_capital_m"] / df["total_regis"], np.nan)
    df["business_group"] = df["type"].apply(_business_group)
    df["sme_share"] = np.where(df["size_total_count"] > 0, df["size_s_count"] / df["size_total_count"] * 100, np.nan)

    red_score = _normalize_score(df["red_ocean_index"].replace([np.inf, -np.inf], np.nan).fillna(0))
    closure_score = _normalize_score(df["closure_rate"].fillna(0))
    fall_score = _normalize_score(df["fall_rate"].fillna(0))
    df["risk_score"] = (0.45 * fall_score + 0.35 * closure_score + 0.20 * red_score).clip(0, 100)

    return _dedupe_type(df.reset_index(drop=True))




@st.cache_data(show_spinner=False)
def load_survival_business_data_year(year: int) -> pd.DataFrame:
    duck_df = _survival_from_duckdb(year)
    if not duck_df.empty:
        return duck_df

    """โหลดข้อมูล survival แบบย่อสำหรับปีที่ระบุ เพื่อใช้เทียบ 2568/2569.
    ต้องมีอย่างน้อย active + quit; ถ้าไม่มี quit จะคืนค่าว่างเพื่อไม่ฝืนสรุปว่า survival = 100%.
    """
    regis_files = _find_files("ประเภท", "regis", year=year) or _find_files("ประเภท", "จัดตั้ง", year=year)
    quit_files = _find_files("ประเภท", "quit", year=year) or _find_files("ประเภท", "เลิก", year=year)
    active_files = _find_files("ประเภท", "active", year=year) or _find_files("ประเภท", "ดำเนิน", year=year)

    if not active_files or not quit_files:
        return pd.DataFrame()

    frames = []

    if active_files:
        a = _read_table(active_files[0])
        a = a.rename(columns={c: c.lower() for c in a.columns})
        if "type" in a.columns:
            for c in a.columns:
                if c != "type":
                    a[c] = _to_num(a[c])
            a = a.rename(columns={"p": "active_count", "m": "active_capital_m"})
            a["type_key"] = a["type"].apply(_type_key)
            keep = [c for c in ["type", "type_key", "active_count", "active_capital_m"] if c in a.columns]
            frames.append(a[keep])

    if quit_files:
        q = _read_table(quit_files[0])
        q = q.rename(columns={c: c.lower() for c in q.columns})
        if "type" in q.columns:
            for c in q.columns:
                if c != "type":
                    q[c] = _to_num(q[c])
            q = q.rename(columns={"total_quit": "total_quit", "total_m": "quit_capital_m"})
            q["type_key"] = q["type"].apply(_type_key)
            keep = ["type_key"] + [c for c in ["jan_quit", "feb_quit", "mar_quit", "apr_quit", "total_quit", "quit_capital_m"] if c in q.columns]
            frames.append(q[keep])

    if regis_files:
        r = _read_table(regis_files[0])
        r = r.rename(columns={c: c.lower() for c in r.columns})
        if "type" in r.columns:
            for c in r.columns:
                if c != "type":
                    r[c] = _to_num(r[c])
            r = r.rename(columns={"total_regis": "total_regis", "total_m": "regis_capital_m"})
            r["type_key"] = r["type"].apply(_type_key)
            keep = ["type_key"] + [c for c in ["jan_regis", "feb_regis", "mar_regis", "apr_regis", "total_regis", "regis_capital_m"] if c in r.columns]
            frames.append(r[keep])

    if not frames:
        return pd.DataFrame()
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on="type_key", how="outer")

    if "type" not in out.columns:
        out["type"] = out["type_key"]
    for c in ["active_count", "total_quit", "total_regis", "quit_capital_m", "regis_capital_m"]:
        if c not in out.columns:
            out[c] = 0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    for c in ["jan_quit", "feb_quit", "mar_quit", "apr_quit", "jan_regis", "feb_regis", "mar_regis", "apr_regis"]:
        if c not in out.columns:
            out[c] = 0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    denom = out["active_count"] + out["total_quit"]
    out["survival_rate"] = np.where((out["active_count"] > 0) & (denom > 0), out["active_count"] / denom * 100, np.nan)
    out["business_group"] = out["type"].apply(_business_group)
    out["year"] = year
    return _dedupe_type(out.reset_index(drop=True))
@st.cache_data(show_spinner=False)
def load_province_latest() -> pd.DataFrame:
    # Prefer latest CSV for Apr 2569; fallback to any province monthly data in app if available.
    province_files = _find_files("จังหวัด", "69", "เมย") or _find_files("จังหวัด", "69", "apr")
    if province_files:
        df = _read_table(province_files[0])
        # Standardize likely column names.
        rename = {}
        for c in df.columns:
            n = _norm(c)
            if n in ["province", "จังหวัด"] or "จังหวัด" in n:
                rename[c] = "province"
            elif n in ["new_count", "จัดตั้งใหม่", "จัดตั้ง"] or "new" in n:
                rename[c] = "new_count"
            elif n in ["closed_count", "เลิก"] or "closed" in n:
                rename[c] = "closed_count"
            elif n in ["active_count", "คงอยู่", "ดำเนินกิจการ"] or "active" in n:
                rename[c] = "active_count"
        df = df.rename(columns=rename)
        if "province" in df.columns:
            for c in ["new_count", "closed_count", "active_count"]:
                if c not in df.columns:
                    df[c] = 0
                df[c] = _to_num(df[c])
            df["province"] = df["province"].astype(str).str.strip()
            df = df[~df["province"].str.contains("รวม|ภาค|nan", case=False, na=False)]
            df["province_red_ocean"] = np.where(df["active_count"] > 0, df["new_count"] / df["active_count"] * 100, np.nan)
            return df[["province", "new_count", "closed_count", "active_count", "province_red_ocean"]]

    try:
        from db import load_all_data_from_duckdb
        data = load_all_data_from_duckdb(auto_refresh=True)
        p = data.get("province_monthly", pd.DataFrame())
        if not p.empty:
            p = p.copy()
            p = p[(p.get("year") == 2569) & (p.get("month_no") == 4)]
            if not p.empty:
                for c in ["new_count", "closed_count", "active_count"]:
                    if c not in p.columns:
                        p[c] = 0
                p["province_red_ocean"] = np.where(p["active_count"] > 0, p["new_count"] / p["active_count"] * 100, np.nan)
                return p[["province", "new_count", "closed_count", "active_count", "province_red_ocean"]]
    except Exception:
        pass
    return pd.DataFrame(columns=["province", "new_count", "closed_count", "active_count", "province_red_ocean"])


# ============================================================
# Charts
# ============================================================

def survival_lollipop(df: pd.DataFrame, threshold: float, n: int = 20) -> go.Figure:
    d = df.dropna(subset=["survival_rate"]).copy()
    d = d[d["active_count"] + d["total_quit"] > 0]
    if d.empty:
        return go.Figure()
    d = d.sort_values("survival_rate", ascending=True).head(n).sort_values("survival_rate", ascending=True)
    d["status"] = np.where(d["survival_rate"] >= threshold, "รอด", "ร่วง")
    colors = np.where(d["status"] == "รอด", GREEN, RED)
    labels = d["type"].astype(str).apply(lambda x: x if len(x) < 52 else x[:52] + "…")

    fig = go.Figure()
    for i, r in enumerate(d.itertuples()):
        color = GREEN if r.survival_rate >= threshold else RED
        fig.add_trace(go.Scatter(
            x=[0, r.survival_rate], y=[labels.iloc[i], labels.iloc[i]],
            mode="lines", line=dict(color=color, width=4), showlegend=False,
            hoverinfo="skip",
        ))
    fig.add_trace(go.Scatter(
        x=d["survival_rate"], y=labels,
        mode="markers+text",
        marker=dict(color=colors, size=np.sqrt(d["active_count"].clip(lower=1)) / np.sqrt(max(d["active_count"].max(), 1)) * 24 + 9,
                    line=dict(color="#f8fafc", width=1.2)),
        text=[f"{x:.1f}%" for x in d["survival_rate"]], textposition="middle right",
        customdata=d[["type", "active_count", "total_quit", "business_group"]],
        hovertemplate="%{customdata[0]}<br>กลุ่ม: %{customdata[3]}<br>Survival Rate: %{x:.2f}%<br>คงอยู่: %{customdata[1]:,.0f} ราย<br>เลิก: %{customdata[2]:,.0f} ราย<extra></extra>",
        showlegend=False,
    ))
    fig.add_vline(x=threshold, line_dash="dash", line_color=YELLOW, annotation_text=f"เกณฑ์รอด {threshold:.0f}%")
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(color=GREEN, size=12), name="สีเขียว = รอด"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(color=RED, size=12), name="สีแดง = ร่วง/เสี่ยง"))
    fig.update_layout(xaxis_title="อัตราการอยู่รอด (%)", yaxis_title="ประเภทธุรกิจ", legend_title_text="คำอธิบายสี", xaxis=dict(range=[0, 104]))
    return fig_layout(fig, "แผนภาพต้น-ใบ Survival Rate รายประเภทธุรกิจ", height=max(560, n * 38 + 160), showlegend=True)



def survival_year_comparison_bar(df: pd.DataFrame, threshold: float = 90, n: int = 15) -> go.Figure:
    """เปรียบเทียบ Survival Rate ปี 2568 และ 2569 จากข้อมูลจริงที่อ่านได้"""
    if "survival_rate_68" not in df.columns:
        fig = go.Figure()
        fig.add_annotation(text="ยังไม่มีข้อมูลปี 2568 สำหรับเปรียบเทียบ", x=.5, y=.5, showarrow=False, font=dict(color=WHITE, size=15))
        return fig_layout(fig, "เปรียบเทียบ Survival Rate 2568 และ 2569", height=360, showlegend=False)

    d = df.copy()
    d["survival_rate_68"] = pd.to_numeric(d["survival_rate_68"], errors="coerce")
    d["survival_rate"] = pd.to_numeric(d["survival_rate"], errors="coerce")
    d = d[d[["survival_rate_68", "survival_rate"]].notna().any(axis=1)].copy()
    if d.empty:
        fig = go.Figure()
        fig.add_annotation(text="ข้อมูลปี 2568/2569 ไม่พอสำหรับเปรียบเทียบ", x=.5, y=.5, showarrow=False, font=dict(color=WHITE, size=15))
        return fig_layout(fig, "เปรียบเทียบ Survival Rate 2568 และ 2569", height=360, showlegend=False)

    # ใช้รายการเดียวกับกราฟหลัก: กลุ่มที่ survival ปีล่าสุดต่ำกว่า/ควรดูมากที่สุด
    d = d.sort_values("survival_rate", ascending=True).head(n).sort_values("survival_rate", ascending=True)
    d["label"] = d["type"].astype(str).apply(lambda x: _wrap_label(x, width=28, max_lines=3))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=d["survival_rate_68"],
        y=d["label"],
        orientation="h",
        name="Survival Rate 2568",
        marker=dict(color="rgba(148,163,184,.85)"),
        text=[f"{v:.1f}%" if pd.notna(v) else "ไม่มีข้อมูล" for v in d["survival_rate_68"]],
        textposition="outside",
        customdata=d[["type", "business_group"]],
        hovertemplate="%{customdata[0]}<br>กลุ่ม: %{customdata[1]}<br>Survival 2568: %{x:.2f}%<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=d["survival_rate"],
        y=d["label"],
        orientation="h",
        name="Survival Rate 2569",
        marker=dict(color=GREEN),
        text=[f"{v:.1f}%" if pd.notna(v) else "ไม่มีข้อมูล" for v in d["survival_rate"]],
        textposition="outside",
        customdata=d[["type", "business_group"]],
        hovertemplate="%{customdata[0]}<br>กลุ่ม: %{customdata[1]}<br>Survival 2569: %{x:.2f}%<extra></extra>",
    ))

    fig.add_vline(
        x=threshold,
        line_dash="dash",
        line_color=YELLOW,
        annotation_text=f"เกณฑ์รอด {threshold:.0f}%",
        annotation_position="top right",
    )
    fig.update_layout(
        barmode="group",
        xaxis_title="อัตราการอยู่รอด (%)",
        yaxis_title="ประเภทธุรกิจ",
        xaxis=dict(range=[0, 105]),
        legend=dict(orientation="h", y=1.10, x=1, xanchor="right"),
        margin=dict(l=20, r=80, t=105, b=50),
    )
    return fig_layout(fig, "เปรียบเทียบ Survival Rate ปี 2568 และ 2569", height=max(560, len(d) * 55 + 190), showlegend=True)

def red_ocean_gauge(value: float, title: str) -> go.Figure:
    if pd.isna(value) or not np.isfinite(value):
        value = 0
    max_range = max(100, float(value) * 1.25, 20)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=float(value),
        number={"suffix": "%", "font": {"size": 38}},
        title={"text": title, "font": {"size": 18}},
        gauge={
            "axis": {"range": [0, max_range], "tickwidth": 1, "tickcolor": "#f8fafc"},
            "bar": {"color": PRIMARY, "thickness": 0.23},
            "bgcolor": "rgba(15,23,42,.35)",
            "borderwidth": 1,
            "bordercolor": "rgba(148,163,184,.4)",
            "steps": [
                {"range": [0, min(10, max_range)], "color": "rgba(34,197,94,.35)"},
                {"range": [min(10, max_range), min(25, max_range)], "color": "rgba(250,204,21,.35)"},
                {"range": [min(25, max_range), max_range], "color": "rgba(239,68,68,.35)"},
            ],
            "threshold": {"line": {"color": RED, "width": 4}, "thickness": 0.78, "value": 25},
        },
    ))
    return fig_layout(fig, title=None, height=360, showlegend=False)


def risk_score_bar(df: pd.DataFrame, n: int = 15) -> go.Figure:
    d = df.dropna(subset=["risk_score"]).sort_values("risk_score", ascending=False).head(n).sort_values("risk_score")
    labels = d["type"].astype(str).apply(lambda x: x if len(x) < 46 else x[:46] + "…")
    fig = go.Figure(go.Bar(
        x=d["risk_score"], y=labels, orientation="h",
        marker=dict(color=PRIMARY),
        text=[f"{v:.1f}" for v in d["risk_score"]], textposition="outside",
        customdata=d[["type", "business_group", "survival_rate", "closure_rate", "red_ocean_index"]],
        hovertemplate="%{customdata[0]}<br>กลุ่ม: %{customdata[1]}<br>Risk Score: %{x:.2f}<br>Survival: %{customdata[2]:.2f}%<br>Closure: %{customdata[3]:.2f}%<br>Market Pressure: %{customdata[4]:.2f}%<extra></extra>",
    ))
    fig.update_layout(xaxis_title="คะแนนความเสี่ยง (0-100)", yaxis_title="ประเภทธุรกิจ", xaxis=dict(range=[0, max(100, d["risk_score"].max() + 10)]))
    return fig_layout(fig, "15 อันดับประเภทธุรกิจที่มีคะแนนความเสี่ยงสูง", height=max(560, n * 38 + 160), showlegend=False)



def sme_warning_chart(df: pd.DataFrame, size_filter: str, n: int = 12) -> go.Figure:
    d = df.copy()
    d = d[d["size_total_count"] > 0]
    if d.empty:
        fig = go.Figure(); fig.add_annotation(text="ข้อมูล S/M/L ไม่เพียงพอ", x=.5, y=.5, showarrow=False)
        return fig_layout(fig, "SME Warning", height=360, showlegend=False)
    if size_filter == "ทั้งหมด":
        d = d.sort_values("risk_score", ascending=False).head(n)
        labels = d["type"].apply(lambda x: _wrap_label(x, width=28, max_lines=2))
        totals = d["size_total_count"].replace(0, np.nan)
        fig = go.Figure()
        for col, name, color in [
            ("size_s_count", "S = ทุน < 1 ลบ.", PRIMARY),
            ("size_m_count", "M = ทุน 1–10 ลบ.", PINK),
            ("size_l_count", "L = ทุน > 10 ลบ.", ACCENT),
        ]:
            pct = d[col] / totals * 100
            fig.add_trace(go.Bar(y=labels, x=pct.fillna(0), name=name, orientation="h", marker=dict(color=color), text=[f"{v:.1f}%" for v in pct.fillna(0)], textposition="inside"))
        fig.update_layout(barmode="stack", xaxis_title="สัดส่วนตามขนาดธุรกิจ (%)", yaxis_title="ประเภทธุรกิจ", legend_title_text="คำอธิบายสี")
    else:
        col_map = {"S": "size_s_count", "M": "size_m_count", "L": "size_l_count"}
        col = col_map[size_filter]
        d = d[d[col] > 0].sort_values("risk_score", ascending=False).head(n)
        if d.empty:
            fig = go.Figure(); fig.add_annotation(text=f"ไม่มีข้อมูลธุรกิจขนาด {size_filter} หลังผ่านตัวกรอง", x=.5, y=.5, showarrow=False)
            return fig_layout(fig, "SME Warning", height=360, showlegend=False)
        labels = d["type"].apply(lambda x: _wrap_label(x, width=28, max_lines=2))
        fig = go.Figure(go.Bar(
            y=labels, x=d[col], orientation="h", name=f"จำนวน Size {size_filter}",
            marker=dict(color=d["risk_score"], colorscale=[[0, GREEN], [0.5, YELLOW], [1, RED]], cmin=0, cmax=100, colorbar=dict(title="Risk")),
            text=[_fmt_int(x) for x in d[col]], textposition="outside",
            customdata=d[["type", "risk_score", "survival_rate"]],
            hovertemplate="%{customdata[0]}<br>จำนวน: %{x:,.0f}<br>Risk Score: %{customdata[1]:.1f}<br>Survival: %{customdata[2]:.2f}%<extra></extra>",
        ))
        fig.update_layout(xaxis_title=f"จำนวนธุรกิจขนาด {size_filter} (ราย)", yaxis_title="ประเภทธุรกิจ")
    return fig_layout(fig, "SME Warning: ขนาดธุรกิจในกลุ่มเสี่ยง", height=max(560, min(1000, n * 50 + 180)), showlegend=True)

def monthly_bubble(df: pd.DataFrame, selected_types: list[str]) -> go.Figure:
    """
    กราฟความเสี่ยงจากการเลิกกิจการรายเดือน
    - ถ้ามี jan/feb/mar/apr_quit จริง: ใช้ Bubble Plot
    - ถ้าไม่มี breakdown รายเดือน แต่มี total_quit: แสดง Bar Chart จากยอดรวมแทนแบบซื่อสัตย์ ไม่แต่งรายเดือน
    - ถ้าไม่มี quit เลย: แสดง annotation ว่าข้อมูลไม่เพียงพอ
    """
    month_cols = ["jan_quit", "feb_quit", "mar_quit", "apr_quit"]
    d = df.copy()
    if selected_types:
        d = d[d["type"].isin(selected_types)]
    if d.empty:
        fig = go.Figure()
        fig.add_annotation(text="ไม่มีธุรกิจที่ผ่านตัวกรอง", x=.5, y=.5, showarrow=False, font=dict(color=WHITE, size=16))
        return fig_layout(fig, "Monthly Risk", height=360, showlegend=False)

    for c in month_cols + ["total_quit", "risk_score"]:
        if c not in d.columns:
            d[c] = 0
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)

    rows = []
    for _, r in d.iterrows():
        for m in month_cols:
            rows.append({
                "type": r["type"],
                "business_group": r.get("business_group", "ไม่ระบุกลุ่ม"),
                "month_key": m.split("_")[0],
                "month": MONTH_LABELS.get(m.split("_")[0], m),
                "quit_count": float(r.get(m, 0)),
                "risk_score": float(r.get("risk_score", 0)),
            })

    long = pd.DataFrame(rows)
    plot_long = long[long["quit_count"] > 0].copy()

    # กรณีข้อมูลแยกรายเดือนเป็น 0 ทั้งหมด แต่ยังมี total_quit:
    # ไม่กระจายยอดรวมไปเดือนต่าง ๆ เอง เพราะจะเป็นการ make data
    if plot_long.empty:
        total_quit_sum = float(d["total_quit"].sum()) if "total_quit" in d.columns else 0
        if total_quit_sum > 0:
            bar = d.sort_values("total_quit", ascending=False).head(12).sort_values("total_quit")
            bar["short_type"] = bar["type"].astype(str).apply(lambda x: _wrap_label(x, width=26, max_lines=3))
            fig = go.Figure(go.Bar(
                x=bar["total_quit"],
                y=bar["short_type"],
                orientation="h",
                marker=dict(
                    color=bar["total_quit"],
                    colorscale=[[0, YELLOW], [1, RED]],
                    colorbar=dict(title="เลิก<br>รวม"),
                ),
                text=[_fmt_int(v) for v in bar["total_quit"]],
                textposition="outside",
                customdata=bar[["type", "business_group", "total_quit", "risk_score"]],
                hovertemplate="%{customdata[0]}<br>กลุ่ม: %{customdata[1]}<br>เลิกรวม: %{customdata[2]:,.0f} ราย<br>Risk Score: %{customdata[3]:.1f}<extra></extra>",
            ))
            fig.add_annotation(
                xref="paper", yref="paper", x=0, y=1.13,
                text="หมายเหตุ: ชุดข้อมูลนี้ยังไม่มีจำนวนเลิกกิจการแยกเดือนที่อ่านได้ จึงแสดงยอดเลิกรวมแทน ไม่ได้กระจายข้อมูลเอง",
                showarrow=False, align="left",
                font=dict(color=MUTED, size=12),
            )
            fig.update_layout(xaxis_title="จำนวนเลิกกิจการรวม (ราย)", yaxis_title="ประเภทธุรกิจ")
            return fig_layout(fig, "Bar Chart: จำนวนเลิกกิจการรวมของธุรกิจที่เลือก", height=max(520, min(950, len(bar) * 70 + 180)), showlegend=False)

        fig = go.Figure()
        fig.add_annotation(
            text="ธุรกิจที่เลือกไม่มีจำนวนเลิกกิจการในช่วง ม.ค.–เม.ย. 2569",
            x=.5, y=.5, showarrow=False, font=dict(color=WHITE, size=16)
        )
        return fig_layout(fig, "Monthly Risk", height=360, showlegend=False)

    plot_long["short_type"] = plot_long["type"].astype(str).apply(lambda x: _wrap_label(x, width=28, max_lines=3))
    fig = px.scatter(
        plot_long,
        x="month",
        y="short_type",
        size="quit_count",
        color="quit_count",
        color_continuous_scale="YlOrRd",
        size_max=48,
        custom_data=["type", "business_group", "quit_count", "risk_score"],
        labels={"month": "เดือน", "short_type": "ประเภทธุรกิจ", "quit_count": "จำนวนเลิกกิจการ"},
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<br>กลุ่ม: %{customdata[1]}<br>เดือน: %{x}<br>เลิกกิจการ: %{customdata[2]:,.0f} ราย<br>Risk Score: %{customdata[3]:.1f}<extra></extra>"
    )
    fig.update_layout(
        xaxis_title="เดือน ปี 2569",
        yaxis_title="ประเภทธุรกิจ",
        coloraxis_colorbar_title="เลิกกิจการ"
    )
    return fig_layout(fig, "Bubble Plot: เดือนที่มีความเสี่ยงจากการเลิกกิจการ", height=max(540, min(950, len(plot_long["type"].unique()) * 70 + 220)), showlegend=False)


def bullet_chart(value: float, title: str, target: float = 1.5) -> go.Figure:
    max_range = max(5, float(value if np.isfinite(value) else 0) * 1.35, target * 1.5)
    fig = go.Figure(go.Indicator(
        mode="number+gauge",
        value=0 if pd.isna(value) or not np.isfinite(value) else float(value),
        number={"suffix": " ลบ./ราย", "font": {"size": 28}},
        title={"text": title, "font": {"size": 17}},
        gauge={
            "shape": "bullet",
            "axis": {"range": [0, max_range]},
            "bar": {"color": PRIMARY, "thickness": 0.30},
            "steps": [
                {"range": [0, min(1, max_range)], "color": "rgba(34,197,94,.35)"},
                {"range": [min(1, max_range), min(5, max_range)], "color": "rgba(250,204,21,.35)"},
                {"range": [min(5, max_range), max_range], "color": "rgba(239,68,68,.35)"},
            ],
            "threshold": {"line": {"color": RED, "width": 3}, "thickness": 0.75, "value": min(target, max_range)},
        },
    ))
    return fig_layout(fig, title=None, height=170, showlegend=False)



# ============================================================
# New readable charts + tab-local filters
# ============================================================


def _clean_province_name(value) -> str | None:
    """คืนชื่อจังหวัดมาตรฐานจาก cell ใด ๆ โดยไม่สร้างข้อมูลใหม่"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = _clean(value)
    if not s or s.lower() in {"nan", "none", "null", "-"}:
        return None
    s = s.replace("จังหวัด", "").replace("จ.", "").replace("ฯ", "").strip()
    s = re.sub(r"\s+", "", s)
    if s in PROVINCE_ALIASES:
        return PROVINCE_ALIASES[s]
    for prov in TH_PROVINCES:
        if s == prov or prov in s:
            return prov
    # บางไฟล์จังหวัดอยู่ใน address เช่น '... แขวง ... กรุงเทพมหานคร 10200'
    for prov in TH_PROVINCES:
        if prov in str(value):
            return prov
    return None


def _extract_province_from_text(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value)
    s_norm = s.replace("จังหวัด", "").replace("จ.", "")
    for alias, prov in PROVINCE_ALIASES.items():
        if alias in s_norm:
            return prov
    for prov in TH_PROVINCES:
        if prov in s_norm:
            return prov
    return None


def _clean_objective_text(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = _clean(value)
    if not s or s.lower() in {"nan", "none", "null", "-"}:
        return None
    bad_words = ["วัตถุประสงค์", "ประเภทธุรกิจ", "รายละเอียด", "objective", "nan"]
    if any(w.lower() in s.lower() for w in bad_words) and len(s) < 30:
        return None
    return s



def _company_file_candidates(kind: str) -> list[Path]:
    """หาไฟล์รายชื่อบริษัทแบบเข้มงวดเพื่อไม่ให้ดึงไฟล์ summary มาปน
    kind='new'    -> รายชื่อจัดตั้ง69.csv / รายชื่อจด69.csv
    kind='closed' -> เลิก69.csv
    """
    all_files = _all_files()

    def is_bad_summary(n: str) -> bool:
        bad = [
            "ชายหญิง", "จังหวัด", "ประเภท", "ประเเภท", "ขนาด", "มูลค่าทุน",
            "active", "regis", "quit", "จัดตั้งเลิกเพิ่ม", "_size", "_cat"
        ]
        return any(x in n for x in bad)

    exact, fallback = [], []
    for f in all_files:
        n = _norm(f.name)
        if not (n.endswith('.csv') or n.endswith('.xls') or n.endswith('.xlsx') or n.endswith('.xlsm')):
            continue
        if "69" not in n and "2569" not in n:
            continue

        if kind == "new":
            # ต้องเป็นรายชื่อบริษัทเท่านั้น ห้ามใช้ ชายหญิง69_newly.csv
            if is_bad_summary(n):
                continue
            if n in ["รายชื่อจัดตั้ง69.csv", "รายชื่อจด69.csv"] or n.startswith("รายชื่อจัดตั้ง69") or n.startswith("รายชื่อจด69"):
                exact.append(f)
            elif "รายชื่อ" in n and any(k in n for k in ["จัดตั้ง", "จด", "new", "newly"]):
                fallback.append(f)
        else:
            # ใช้เฉพาะไฟล์เลิกบริษัท ไม่ดึง ประเภทจัดตั้งเลิก... หรือ จังหวัดจัดตั้งเลิก... มาปน
            if n in ["เลิก69.csv", "เลิก69.xls", "เลิก69.xlsx"] or n.startswith("เลิก69"):
                exact.append(f)
            elif "รายชื่อ" in n and "เลิก" in n and not is_bad_summary(n):
                fallback.append(f)

    # exact first, unique, shorter name first
    out = sorted(dict.fromkeys(exact), key=lambda x: (len(_norm(x.name)), _norm(x.name)))
    out += sorted([f for f in dict.fromkeys(fallback) if f not in out], key=lambda x: (len(_norm(x.name)), _norm(x.name)))
    return out


def _read_csv_any(path: Path, header=None) -> pd.DataFrame:
    """อ่าน CSV หลาย encoding / delimiter โดยไม่บังคับเติมข้อมูล"""
    last_error = None
    encodings = ["utf-8-sig", "utf-8", "cp874", "tis-620"]
    seps = [None, ",", "\t", ";", "|"]
    best = None
    best_score = -1
    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(
                    path,
                    encoding=enc,
                    header=header,
                    dtype=str,
                    engine="python",
                    sep=sep,
                    on_bad_lines="skip",
                )
                if df.empty:
                    continue
                # score by number of columns and presence of Thai business/address words
                joined_cols = " ".join(map(str, df.columns))
                sample = " ".join(df.head(30).astype(str).fillna("").agg(" ".join, axis=1).tolist())
                score = df.shape[1] * 5
                for kw in ["วัตถุประสงค์", "จังหวัด", "กรุงเทพ", "ชลบุรี", "การ", "กิจกรรม", "บริการ", "ขาย", "ผลิต"]:
                    if kw in joined_cols or kw in sample:
                        score += 10
                if score > best_score:
                    best_score = score
                    best = df
            except Exception as e:
                last_error = e
    if best is not None:
        return best
    raise RuntimeError(f"อ่าน CSV {path.name} ไม่ได้: {last_error}")


def _read_company_raw_tables(path: Path) -> list[pd.DataFrame]:
    """อ่านทั้ง header=0 และ header=None เพราะไฟล์รายชื่อ DBD มักมีหัวตารางไม่คงที่"""
    tables = []
    if path.suffix.lower() == ".csv":
        for header in [0, None]:
            try:
                df = _read_csv_any(path, header=header)
                df.columns = [_clean(c) for c in df.columns]
                tables.append(df)
            except Exception:
                pass
    else:
        for header in [0, None]:
            try:
                df = pd.read_excel(path, header=header, dtype=str)
                df.columns = [_clean(c) for c in df.columns]
                tables.append(df)
            except Exception:
                pass
    return tables


def _cell_text(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    s = str(x).replace("\ufeff", "").strip()
    if s.lower() in {"nan", "none", "null"}:
        return ""
    return s


def _province_from_series(s: pd.Series) -> pd.Series:
    return s.apply(lambda x: _clean_province_name(x) or _extract_province_from_text(x))


def _looks_like_objective_text(s: str) -> bool:
    s = _cell_text(s)
    if not s or len(s) < 3:
        return False
    # ตัด header / เลขทะเบียน / วันที่ / ทุน / ที่อยู่ล้วน ๆ ออก
    bad = ["วัตถุประสงค์", "ประเภทธุรกิจ", "เลขทะเบียน", "ชื่อนิติบุคคล", "ลำดับ", "วันที่", "ทุน", "ที่ตั้ง", "ตำบล", "อำเภอ", "จังหวัด", "รหัส"]
    if any(b in s for b in bad) and len(s) < 35:
        return False
    num = pd.to_numeric(pd.Series([s.replace(",", "")]), errors="coerce").notna().iloc[0]
    if num:
        return False
    kws = ["การ", "กิจกรรม", "บริการ", "ขาย", "ค้าปลีก", "ค้าส่ง", "ผลิต", "ก่อสร้าง", "ให้เช่า", "อาหาร", "ขนส่ง", "จำหน่าย", "ซ่อม", "โรงงาน", "อสังหาริมทรัพย์", "ปลูก", "เลี้ยง", "นายหน้า", "บริหาร"]
    # ยอมรับข้อความยาว แม้ keyword ไม่ครบ เพราะบางไฟล์เป็นคำอธิบายยาว
    return any(k in s for k in kws) or len(s) >= 18


def _objective_from_series(s: pd.Series) -> pd.Series:
    return s.apply(lambda x: _cell_text(x) if _looks_like_objective_text(x) else None)


def _score_province_col(df: pd.DataFrame, col) -> tuple[int, pd.Series]:
    ser = _province_from_series(df[col])
    return int(ser.notna().sum()), ser


def _score_objective_col(df: pd.DataFrame, col) -> tuple[float, pd.Series]:
    ser = _objective_from_series(df[col])
    valid = ser.notna()
    if valid.sum() == 0:
        return -999, ser
    province_hits = _province_from_series(df[col]).notna().sum()
    numeric_hits = pd.to_numeric(df[col].astype(str).str.replace(",", "", regex=False), errors="coerce").notna().sum()
    avg_len = ser[valid].astype(str).str.len().mean()
    keywords = ["การ", "กิจกรรม", "บริการ", "ขาย", "ผลิต", "ก่อสร้าง", "ขนส่ง", "อาหาร", "จำหน่าย"]
    kw_hits = df[col].astype(str).apply(lambda x: any(k in x for k in keywords)).sum()
    score = valid.sum() * 2 + kw_hits * 4 + avg_len * 0.08 - province_hits * 4 - numeric_hits * 0.5
    return float(score), ser


def _candidate_columns_by_position(df: pd.DataFrame, kind: str) -> list:
    cols = list(df.columns)
    named, positional, scored = [], [], []

    for c in cols:
        key = _norm(c)
        if kind == "province":
            if key in ["province", "จังหวัด", "province_col"] or "จังหวัด" in key or "province" in key:
                named.append(c)
        else:
            if any(k in key for k in ["objective", "วัตถุประสงค์", "ประเภทธุรกิจ", "business", "type"]):
                named.append(c)

    # ตำแหน่ง DBD ที่พบบ่อย: 0 ลำดับ, 1 เลขทะเบียน, 2 ชื่อ, 3 วันที่, 4 ทุน, 5 รหัส, 6 วัตถุประสงค์, 10 จังหวัด
    preferred = [10, 9, 11, 8, 12, 7, 6, 5, 4] if kind == "province" else [6, 5, 7, 4, 8, 3, 9, 10]
    for i in preferred:
        if i < len(cols) and cols[i] not in positional:
            positional.append(cols[i])

    for c in cols:
        if kind == "province":
            score, _ = _score_province_col(df, c)
        else:
            score, _ = _score_objective_col(df, c)
        if score > 0:
            scored.append((score, c))
    scored_cols = [c for _, c in sorted(scored, key=lambda x: x[0], reverse=True)]

    out = []
    for c in named + positional + scored_cols + cols:
        if c not in out:
            out.append(c)
    return out


def _extract_company_by_best_pair(df: pd.DataFrame) -> pd.DataFrame:
    """หา province + objective จากไฟล์จริงเท่านั้น ไม่สร้างข้อมูลเอง"""
    if df is None or df.empty:
        return pd.DataFrame(columns=["province", "objective"])

    df = df.copy().dropna(how="all")
    if df.empty:
        return pd.DataFrame(columns=["province", "objective"])

    best = None
    best_score = -1
    pcols = _candidate_columns_by_position(df, "province")
    ocols = _candidate_columns_by_position(df, "objective")
    cols = list(df.columns)

    for pc in pcols:
        p_score, pser = _score_province_col(df, pc)
        if p_score <= 0:
            continue
        for oc in ocols:
            if oc == pc:
                continue
            o_score, oser = _score_objective_col(df, oc)
            if o_score <= 0:
                continue
            both = pser.notna() & oser.notna()
            score = int(both.sum()) * 10 + p_score + o_score
            # โบนัสตำแหน่งที่ตรงกับ DBD raw
            try:
                pi, oi = cols.index(pc), cols.index(oc)
                if pi in [10, 9, 11] and oi in [6, 5, 7]:
                    score += 50
            except Exception:
                pass
            if score > best_score:
                best_score = score
                best = (pser, oser, pc, oc)

    if best is None or best_score <= 0:
        # fallback: scan ทั้งแถวหา province และหา objective จากคอลัมน์ที่ดีที่สุด
        row_text = df.astype(str).fillna("").agg(" ".join, axis=1)
        pser = row_text.apply(_extract_province_from_text)
        best_obj_ser = None
        best_obj_score = -999
        for c in df.columns:
            sc, ser = _score_objective_col(df, c)
            if sc > best_obj_score:
                best_obj_score = sc
                best_obj_ser = ser
        if best_obj_ser is None:
            return pd.DataFrame(columns=["province", "objective"])
        oser = best_obj_ser
    else:
        pser, oser, _, _ = best

    tmp = pd.DataFrame({"province": pser.apply(_clean_province_name), "objective": oser.apply(lambda x: _cell_text(x) if _looks_like_objective_text(x) else None)})
    tmp = tmp.dropna(subset=["province", "objective"])
    tmp = tmp[~tmp["objective"].astype(str).str.contains("วัตถุประสงค์|หมายเหตุ|รวม|รายละเอียด|ประเภทธุรกิจ|เลขทะเบียน", na=False)]
    tmp = tmp[tmp["objective"].astype(str).str.len() >= 3]
    return tmp.reset_index(drop=True)


def _standardize_company_table(raw: pd.DataFrame, event_type: str, source_name: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    df.columns = [_clean(c) for c in df.columns]
    df = df.dropna(how="all")
    if df.empty:
        return pd.DataFrame()

    tmp = _extract_company_by_best_pair(df)
    if tmp.empty:
        return pd.DataFrame()

    tmp["event_type"] = event_type
    tmp["source"] = source_name
    tmp["objective_key"] = tmp["objective"].apply(_type_key)
    tmp["business_group"] = tmp["objective"].apply(_business_group)
    # ห้าม drop_duplicates ที่ระดับ province+objective เพราะแต่ละแถวคือบริษัทจริง ใช้นับจำนวน
    return tmp[["province", "objective", "objective_key", "business_group", "event_type", "source"]]


def _load_company_list_from_files(event_type: str, files: list[Path]) -> pd.DataFrame:
    rows = []
    for f in files:
        file_rows = []
        for raw in _read_company_raw_tables(f):
            parsed = _standardize_company_table(raw, event_type=event_type, source_name=f.name)
            if not parsed.empty:
                file_rows.append(parsed)
        if file_rows:
            # เลือก table ที่ parse ได้มากที่สุดเพื่อกัน header=0/header=None ซ้ำกัน
            one = sorted(file_rows, key=len, reverse=True)[0]
            rows.append(one)
            # ถ้าไฟล์หลักอ่านได้แล้ว ไม่อ่าน fallback อื่น
            if (event_type == "จัดตั้งใหม่" and "รายชื่อ" in _norm(f.name)) or (event_type == "เลิกกิจการ" and _norm(f.name).startswith("เลิก69")):
                break
    if not rows:
        return pd.DataFrame(columns=["province", "objective", "objective_key", "business_group", "event_type", "source"])
    return pd.concat(rows, ignore_index=True)


@st.cache_data(show_spinner=False)
def load_company_province_types_2569() -> pd.DataFrame:
    """อ่านรายชื่อจัดตั้ง69.csv และเลิก69.csv เพื่อใช้วิเคราะห์ระดับพื้นที่
    ยืนยัน: ไม่ make ข้อมูล ใช้เฉพาะแถวที่ parser หา province + objective ได้จากไฟล์จริง
    """
    new_df = _load_company_list_from_files("จัดตั้งใหม่", _company_file_candidates("new"))
    closed_df = _load_company_list_from_files("เลิกกิจการ", _company_file_candidates("closed"))
    frames = [x for x in [new_df, closed_df] if isinstance(x, pd.DataFrame) and not x.empty]

    if not frames:
        return pd.DataFrame(columns=["province", "objective", "objective_key", "business_group", "event_type", "source"])

    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["province", "objective"])
    out["province"] = out["province"].apply(_clean_province_name)
    out["objective"] = out["objective"].apply(lambda x: _cell_text(x) if _looks_like_objective_text(x) else None)
    out = out.dropna(subset=["province", "objective"])
    out["objective_key"] = out["objective"].apply(_type_key)
    out["business_group"] = out["objective"].apply(_business_group)

    # ห้าม drop_duplicates ระดับ province/objective เพราะแต่ละแถวคือบริษัทจริงที่ต้องเอาไว้นับจำนวน
    # ถ้าไฟล์มีแถวซ้ำจริงจาก source เดียวกัน ผู้ใช้ควรแก้ที่ไฟล์ต้นทาง ไม่ให้ระบบเดาข้อมูลเอง
    return out.reset_index(drop=True)


def _match_types_from_objectives(all_types: list[str], obj_keys: set[str]) -> list[str]:
    matched = []
    for t in all_types:
        tk = _type_key(t)
        if tk in obj_keys or any((tk and tk in ok) or (ok and ok in tk) for ok in obj_keys):
            matched.append(t)
    return sorted(set(matched))


def local_market_signal(province_name: str, selected_type: str, all_types: list[str] | None = None) -> dict:
    """ดัชนีแรงกดดันในพื้นที่จากรายชื่อจัดตั้ง/เลิก: เลิก ÷ (จัดตั้งใหม่+เลิก) ×100.
    selected_type is expected to be an exact objective from the province-level detail file.
    """
    detail = load_company_province_types_2569()
    if detail.empty or not province_name or not selected_type or selected_type == "ไม่มีข้อมูล":
        return {"ok": False, "reason": "ยังไม่มีข้อมูลจังหวัด/ประเภทธุรกิจเพียงพอ"}
    sub = detail[detail["province"].astype(str) == str(province_name)].copy()
    if sub.empty:
        return {"ok": False, "reason": f"ไม่พบข้อมูลรายชื่อจัดตั้ง/เลิกของจังหวัด {province_name}"}

    # Exact objective first. Fallback to normalized matching only when needed.
    exact = sub[sub["objective"].astype(str) == str(selected_type)].copy()
    if exact.empty:
        tk = _type_key(selected_type)
        sub["is_match"] = sub["objective_key"].apply(lambda ok: (tk and (tk in ok or ok in tk)))
        exact = sub[sub["is_match"]].copy()
    sub = exact
    if sub.empty:
        return {"ok": False, "reason": "ไม่พบธุรกิจที่เลือกในไฟล์รายชื่อของจังหวัดนี้"}
    new_count = int((sub["event_type"] == "จัดตั้งใหม่").sum())
    closed_count = int((sub["event_type"] == "เลิกกิจการ").sum())
    total = new_count + closed_count
    if total <= 0:
        return {"ok": False, "reason": "ไม่มีจำนวนจัดตั้ง/เลิกเพียงพอสำหรับคำนวณ"}
    pressure = closed_count / total * 100
    entry = new_count / total * 100
    return {"ok": True, "new_count": new_count, "closed_count": closed_count, "pressure": pressure, "entry": entry, "rows": sub}


def _apply_business_filter(df: pd.DataFrame, min_regis: int = 0, min_active: int = 0, group: str = "ทั้งหมด") -> pd.DataFrame:
    d = df.copy()
    d = d[(d["total_regis"] >= min_regis) & (d["active_count"] >= min_active)]
    if group != "ทั้งหมด":
        d = d[d["business_group"] == group]
    return _dedupe_type(d.reset_index(drop=True))


def _valid_survival(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = df.copy()
    # กรณี active_count = 0 แต่มีการเลิกกิจการ อาจเป็นข้อมูล active ที่ไม่ match ระดับประเภทธุรกิจ จึงไม่ฝืนตีว่าอยู่รอด 0%
    insufficient = d[((d["active_count"] <= 0) & (d["total_quit"] > 0)) | ((d["active_count"] + d["total_quit"]) <= 0)].copy()
    valid = d[(d["active_count"] > 0) & ((d["active_count"] + d["total_quit"]) > 0)].copy()
    return valid, insufficient


def _red_ocean_text(value: float) -> str:
    if pd.isna(value) or not np.isfinite(value):
        return "ข้อมูลไม่พอสำหรับตีความ"
    if value < 10:
        return "ตลาดยังไม่แดงมาก ผู้เล่นใหม่ยังไม่หนาแน่นเมื่อเทียบกับฐานธุรกิจเดิม"
    if value < 25:
        return "เริ่มมีผู้เล่นใหม่เข้ามา ควรดูทำเล จุดขาย และคู่แข่งให้ละเอียด"
    return "ตลาดค่อนข้างแดง ผู้เล่นใหม่เข้ามาเยอะเมื่อเทียบกับฐานธุรกิจเดิม ต้องมี niche หรือความแตกต่างชัดเจน"


def readable_survival_bar(df: pd.DataFrame, threshold: float = 90, n: int = 20, mode: str = "เสี่ยงสูง") -> go.Figure:
    valid, _ = _valid_survival(df)
    if valid.empty:
        fig = go.Figure()
        fig.add_annotation(text="ข้อมูลไม่เพียงพอสำหรับคำนวณ Survival Rate", x=0.5, y=0.5, showarrow=False)
        return fig_layout(fig, "Survival Rate", height=360, showlegend=False)

    if mode == "รอดสูง":
        d = valid.sort_values("survival_rate", ascending=False).head(n).sort_values("survival_rate")
    else:
        d = valid.sort_values("survival_rate", ascending=True).head(n).sort_values("survival_rate")

    d["label"] = d["type"].astype(str).apply(lambda x: x if len(x) < 54 else x[:54] + "…")
    d["status"] = np.where(d["survival_rate"] >= threshold, "สีเขียว = รอดตามเกณฑ์", "สีแดง = ต่ำกว่าเกณฑ์/ควรระวัง")
    colors = np.where(d["survival_rate"] >= threshold, GREEN, RED)

    fig = go.Figure(go.Bar(
        x=d["survival_rate"],
        y=d["label"],
        orientation="h",
        marker=dict(color=colors, line=dict(color="rgba(255,255,255,.28)", width=.7)),
        text=[f"{v:.1f}%" for v in d["survival_rate"]],
        textposition="outside",
        customdata=d[["type", "active_count", "total_quit", "business_group", "status"]],
        hovertemplate=(
            "%{customdata[0]}<br>กลุ่ม: %{customdata[3]}<br>"
            "Survival Rate: %{x:.2f}%<br>คงอยู่: %{customdata[1]:,.0f} ราย<br>เลิก: %{customdata[2]:,.0f} ราย<br>%{customdata[4]}<extra></extra>"
        ),
        name="Survival Rate",
    ))
    fig.add_vline(x=threshold, line_dash="dash", line_color=YELLOW, annotation_text=f"เกณฑ์รอด {threshold:.0f}%")
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(size=12, color=GREEN), name="สีเขียว = รอด"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(size=12, color=RED), name="สีแดง = ต่ำกว่าเกณฑ์/ร่วง"))
    fig.update_layout(
        xaxis_title="อัตราการอยู่รอด (%)",
        yaxis_title="ประเภทธุรกิจ",
        xaxis=dict(range=[0, 105]),
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right"),
        margin=dict(l=20, r=70, t=100, b=50),
    )
    return fig_layout(fig, "Survival Rate รายประเภทธุรกิจ", height=max(520, n * 34 + 160), showlegend=True)


def red_ocean_gauge_clean(value: float, title: str = "") -> go.Figure:
    if pd.isna(value) or not np.isfinite(value):
        value = 0
    value = float(value)
    max_range = max(100, value * 1.25, 30)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": "%", "font": {"size": 38}},
        title={"text": "", "font": {"size": 1}},
        gauge={
            "axis": {"range": [0, max_range], "tickcolor": "#f8fafc"},
            "bar": {"color": PRIMARY, "thickness": 0.22},
            "bgcolor": "rgba(15,23,42,.35)",
            "borderwidth": 1,
            "bordercolor": "rgba(148,163,184,.4)",
            "steps": [
                {"range": [0, min(10, max_range)], "color": "rgba(34,197,94,.38)"},
                {"range": [min(10, max_range), min(25, max_range)], "color": "rgba(250,204,21,.38)"},
                {"range": [min(25, max_range), max_range], "color": "rgba(239,68,68,.38)"},
            ],
            "threshold": {"line": {"color": RED, "width": 4}, "thickness": 0.78, "value": min(25, max_range)},
        },
    ))
    fig.add_annotation(x=0.5, y=1.05, xref="paper", yref="paper", showarrow=False, text=f"<b>{title}</b>", font=dict(size=18, color="#f8fafc"))
    return fig_layout(fig, "", height=360, showlegend=False)




def local_pressure_gauge(value: float, title: str = "") -> go.Figure:
    if pd.isna(value) or not np.isfinite(value):
        value = 0
    value = float(value)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": "%", "font": {"size": 40}},
        title={"text": "", "font": {"size": 1}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#f8fafc"},
            "bar": {"color": "#f472b6", "thickness": 0.24},
            "bgcolor": "rgba(15,23,42,.35)",
            "borderwidth": 1,
            "bordercolor": "rgba(148,163,184,.4)",
            "steps": [
                {"range": [0, 20], "color": "rgba(45,212,191,.55)"},
                {"range": [20, 50], "color": "rgba(251,191,36,.55)"},
                {"range": [50, 100], "color": "rgba(244,63,94,.55)"},
            ],
            "threshold": {"line": {"color": "#f43f5e", "width": 4}, "thickness": 0.8, "value": 50},
        },
    ))
    fig.add_annotation(x=0.5, y=1.05, xref="paper", yref="paper", showarrow=False, text=f"<b>{title}</b>", font=dict(size=18, color="#f8fafc"))
    return fig_layout(fig, "", height=360, showlegend=False)


def _local_pressure_text(value: float) -> str:
    if pd.isna(value) or not np.isfinite(value):
        return "ข้อมูลไม่พอสำหรับตีความ"
    if value < 20:
        return "แรงกดดันจากการเลิกกิจการยังต่ำ เมื่อเทียบกับกิจกรรมจัดตั้ง/เลิกในพื้นที่"
    if value < 50:
        return "มีสัญญาณควรระวัง ควรตรวจดูคู่แข่ง ทำเล และความต้องการจริงของลูกค้า"
    return "แรงกดดันสูง มีธุรกิจเลิกกิจการมากเมื่อเทียบกับการเกิดใหม่ ต้องวางแผนความต่างและเงินสดให้รัดกุม"


def survival_compare_bar(df: pd.DataFrame, threshold: float = 90, n: int = 15, mode: str = "เสี่ยงสูง") -> go.Figure:
    """Show fall rate (100-survival) so differences are readable, while keeping survival in hover/text."""
    valid, _ = _valid_survival(df)
    if valid.empty:
        fig = go.Figure()
        fig.add_annotation(text="ข้อมูลไม่เพียงพอสำหรับคำนวณ Survival Rate", x=0.5, y=0.5, showarrow=False)
        return fig_layout(fig, "Survival Rate", height=360, showlegend=False)
    valid = valid.copy()
    valid["fall_rate_plot"] = 100 - valid["survival_rate"]
    if "survival_rate_68" in valid.columns:
        valid["fall_rate_68"] = 100 - valid["survival_rate_68"]
    if mode == "รอดสูง":
        d = valid.sort_values("survival_rate", ascending=False).head(n)
    else:
        d = valid.sort_values("fall_rate_plot", ascending=False).head(n)
    d = d.sort_values("fall_rate_plot")
    d["label"] = d["type"].apply(lambda x: _wrap_label(x, width=30, max_lines=4))
    fall_threshold = max(0, 100 - threshold)

    fig = go.Figure()
    if "fall_rate_68" in d.columns and d["fall_rate_68"].notna().any():
        fig.add_trace(go.Bar(
            x=d["fall_rate_68"], y=d["label"], orientation="h",
            marker=dict(color="rgba(148,163,184,.55)"), name="อัตราร่วง ปี 2568",
            text=["" if pd.isna(v) else f"{v:.2f}%" for v in d["fall_rate_68"]], textposition="outside",
            customdata=d[["type"]], hovertemplate="%{customdata[0]}<br>อัตราร่วง 2568: %{x:.2f}%<extra></extra>",
        ))
    colors = np.where(d["fall_rate_plot"] <= fall_threshold, GREEN, RED)
    fig.add_trace(go.Bar(
        x=d["fall_rate_plot"], y=d["label"], orientation="h",
        marker=dict(color=colors, line=dict(color="rgba(255,255,255,.25)", width=0.8)),
        name="อัตราร่วง ปี 2569",
        text=[f"ร่วง {v:.2f}%" for v in d["fall_rate_plot"]], textposition="outside",
        customdata=d[["type", "active_count", "total_quit", "business_group", "survival_rate"]],
        hovertemplate="%{customdata[0]}<br>กลุ่ม: %{customdata[3]}<br>อัตราร่วง 2569: %{x:.2f}%<br>Survival Rate: %{customdata[4]:.2f}%<br>คงอยู่: %{customdata[1]:,.0f}<br>เลิก: %{customdata[2]:,.0f}<extra></extra>",
    ))
    fig.add_vline(x=fall_threshold, line_dash="dash", line_color=YELLOW, annotation_text=f"เกณฑ์ร่วง {fall_threshold:.0f}%")
    fig.update_layout(
        barmode="group",
        xaxis_title="อัตราร่วง (%) = 100 - Survival Rate",
        yaxis_title="ประเภทธุรกิจ",
        xaxis=dict(range=[0, max(10, float(d["fall_rate_plot"].max()) * 1.25 + 1)]),
        legend=dict(orientation="h", y=1.12, x=1, xanchor="right"),
        margin=dict(l=20, r=90, t=110, b=50),
    )
    return fig_layout(fig, "อัตราร่วงรายประเภทธุรกิจ (อ่านง่ายกว่า Survival ที่มักสูงมาก)", height=max(620, n * 68 + 180), showlegend=True)


def risk_score_bar_gradient(df: pd.DataFrame, n: int = 15) -> go.Figure:
    d = df.dropna(subset=["risk_score"]).sort_values("risk_score", ascending=False).head(n).copy()
    if d.empty:
        fig = go.Figure(); fig.add_annotation(text="ไม่มีข้อมูลพอสำหรับ Risk Score", x=.5, y=.5, showarrow=False)
        return fig_layout(fig, "Risk Score", height=360, showlegend=False)
    d["rank_no"] = np.arange(1, len(d) + 1)
    d = d.sort_values("risk_score")
    d["label"] = d.apply(lambda r: f"{int(r['rank_no'])}. " + _wrap_label(r['type'], width=28, max_lines=4), axis=1)
    median_risk = float(d["risk_score"].median()) if len(d) else 0
    top_name = str(d.sort_values("risk_score", ascending=False).iloc[0]["type"])
    low_name = str(d.sort_values("risk_score", ascending=True).iloc[0]["type"])
    fig = go.Figure(go.Bar(
        x=d["risk_score"],
        y=d["label"],
        orientation="h",
        marker=dict(
            color=d["risk_score"],
            colorscale=[[0, GREEN], [0.5, YELLOW], [1, RED]],
            cmin=0,
            cmax=100,
            colorbar=dict(title="ระดับ<br>ความเสี่ยง"),
        ),
        text=[f"{v:.1f}" for v in d["risk_score"]],
        textposition="outside",
        customdata=d[["rank_no", "type", "survival_rate", "closure_rate", "red_ocean_index"]],
        hovertemplate="#%{customdata[0]:.0f} %{customdata[1]}<br>Risk Score: %{x:.1f}<br>Survival: %{customdata[2]:.2f}%<br>Closure: %{customdata[3]:.2f}%<br>Market Pressure: %{customdata[4]:.2f}%<extra></extra>",
    ))
    fig.add_vline(x=median_risk, line_dash="dash", line_color="rgba(255,255,255,.65)", annotation_text=f"ค่ามัธยฐาน {median_risk:.1f}", annotation_position="top")
    fig.add_annotation(xref="paper", yref="paper", x=1.02, y=1.13, showarrow=False,
                       text=f"เสี่ยงสุด: {top_name}<br>เสี่ยงต่ำสุด: {low_name}",
                       align="left", bgcolor="rgba(15,23,42,.85)", bordercolor="rgba(148,163,184,.35)", borderwidth=1)
    fig.update_layout(xaxis_title="คะแนนความเสี่ยง (0-100)", yaxis_title="ประเภทธุรกิจ", xaxis=dict(range=[0, 105]), margin=dict(l=20, r=180, t=90, b=50))
    return fig_layout(fig, "กราฟแท่งแนวนอนไล่สี: อันดับประเภทธุรกิจที่มีคะแนนความเสี่ยงสูง", height=max(640, n * 56 + 170), showlegend=False)


def budget_bullet_chart(avg_loss: float, budget: float) -> go.Figure:
    if pd.isna(avg_loss) or not np.isfinite(avg_loss):
        avg_loss = 0
    avg_loss = float(avg_loss)
    budget = float(budget)
    max_range = max(5, avg_loss * 1.4, budget * 1.4, 1)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[max_range], y=["ทุน"], orientation="h", marker=dict(color="rgba(239,68,68,.22)"), name="โซนเสี่ยงสูง", hoverinfo="skip"))
    fig.add_trace(go.Bar(x=[min(5, max_range)], y=["ทุน"], orientation="h", marker=dict(color="rgba(250,204,21,.32)"), name="โซนระวัง", hoverinfo="skip"))
    fig.add_trace(go.Bar(x=[min(1, max_range)], y=["ทุน"], orientation="h", marker=dict(color="rgba(34,197,94,.35)"), name="โซนเบา", hoverinfo="skip"))
    fig.add_trace(go.Bar(x=[avg_loss], y=["ทุน"], orientation="h", marker=dict(color=PRIMARY), width=.32, name="แท่งสีม่วง = ทุนเฉลี่ยของธุรกิจที่เลิกกิจการ", text=[f"{avg_loss:.2f} ลบ./ราย"], textposition="outside"))
    fig.add_vline(x=budget, line_color=RED, line_width=3, annotation_text=f"เส้นแดง = งบผู้ใช้ {budget:.2f} ลบ.")
    fig.update_layout(barmode="overlay", xaxis_title="ล้านบาทต่อราย", yaxis_title="", legend=dict(orientation="h", y=1.22), margin=dict(l=20, r=40, t=90, b=50))
    return fig_layout(fig, "Bullet Chart: เทียบงบผู้ใช้กับทุนเฉลี่ยของธุรกิจที่เลิกกิจการ", height=260, showlegend=True)


def province_available_type_options(all_types: list[str], province_name: str) -> tuple[list[str], str]:
    """Backward-compatible helper; prefers exact objectives from รายชื่อจัดตั้ง/เลิก by province."""
    detail = load_company_province_types_2569()
    if detail.empty or province_name == "ไม่เลือกจังหวัด":
        return all_types, "ยังไม่ได้เลือกจังหวัด หรือยังไม่มีไฟล์รายชื่อจัดตั้ง/เลิกที่อ่านได้"
    sub = detail[detail["province"].astype(str) == str(province_name)].copy()
    if sub.empty:
        return [], f"ยังไม่พบข้อมูลรายชื่อจัดตั้ง/เลิกของจังหวัด {province_name}"
    opts = (
        sub.groupby(["objective", "business_group"], as_index=False)
        .size()
        .sort_values("size", ascending=False)["objective"]
        .dropna()
        .astype(str)
        .tolist()
    )
    return opts, f"พบ {len(opts):,} ประเภทธุรกิจจริงในจังหวัด {province_name} จากไฟล์รายชื่อจัดตั้ง/เลิก"


def province_detail_data() -> pd.DataFrame:
    """Alias for readability in tabs that need province-level detail."""
    return load_company_province_types_2569()


def province_options_from_detail() -> list[str]:
    detail = province_detail_data()
    if detail.empty:
        return []
    counts = detail.groupby("province").size().sort_values(ascending=False)
    return counts.index.astype(str).tolist()


def group_options_for_province(province_name: str) -> list[str]:
    detail = province_detail_data()
    if detail.empty or not province_name:
        return ["ทั้งหมด"]
    sub = detail[detail["province"].astype(str) == str(province_name)].copy()
    groups = sorted(sub["business_group"].dropna().astype(str).unique().tolist())
    return ["ทั้งหมด"] + groups if groups else ["ทั้งหมด"]


def objective_options_for_province_group(province_name: str, group: str = "ทั้งหมด") -> list[str]:
    detail = province_detail_data()
    if detail.empty or not province_name:
        return []
    sub = detail[detail["province"].astype(str) == str(province_name)].copy()
    if group != "ทั้งหมด":
        sub = sub[sub["business_group"] == group]
    if sub.empty:
        return []
    obj = (
        sub.groupby("objective", as_index=False)
        .size()
        .sort_values("size", ascending=False)["objective"]
        .dropna()
        .astype(str)
        .tolist()
    )
    return obj


def local_data_examples(n: int = 8) -> pd.DataFrame:
    detail = province_detail_data()
    if detail.empty:
        return pd.DataFrame(columns=["จังหวัด", "จำนวนรายการ", "ตัวอย่างธุรกิจ"])
    rows = []
    for prov, gd in detail.groupby("province"):
        examples = gd["objective"].dropna().astype(str).value_counts().head(3).index.tolist()
        rows.append({
            "จังหวัด": prov,
            "จำนวนรายการ": len(gd),
            "จำนวนประเภทธุรกิจ": gd["objective"].nunique(),
            "ตัวอย่างธุรกิจ": " / ".join(examples),
        })
    return pd.DataFrame(rows).sort_values("จำนวนรายการ", ascending=False).head(n)



def company_read_debug_summary() -> pd.DataFrame:
    rows = []
    for kind, files in [("จัดตั้งใหม่", _company_file_candidates("new")), ("เลิกกิจการ", _company_file_candidates("closed"))]:
        for f in files:
            parsed_rows = 0
            raw_shapes = []
            try:
                for raw in _read_company_raw_tables(f):
                    raw_shapes.append(f"{raw.shape[0]}x{raw.shape[1]}")
                    parsed = _standardize_company_table(raw, kind, f.name)
                    parsed_rows += len(parsed)
            except Exception as e:
                rows.append({"ชนิด": kind, "ไฟล์": f.name, "raw shapes": "error", "แถวที่อ่านได้": 0, "หมายเหตุ": str(e)[:120]})
                continue
            rows.append({"ชนิด": kind, "ไฟล์": f.name, "raw shapes": ", ".join(raw_shapes), "แถวที่อ่านได้": parsed_rows, "หมายเหตุ": ""})
    return pd.DataFrame(rows)




def local_activity_table(detail: pd.DataFrame, province: str | None = None, group: str = "ทั้งหมด") -> pd.DataFrame:
    """สรุปจำนวนจัดตั้ง/เลิกจากไฟล์รายชื่อจริงเท่านั้น ระดับจังหวัด+ประเภทธุรกิจ."""
    if detail is None or detail.empty:
        return pd.DataFrame(columns=["province", "objective", "business_group", "new_count", "closed_count", "total_event", "exit_share"])
    d = detail.copy()
    if province and province != "ทั้งหมด":
        d = d[d["province"].astype(str) == str(province)]
    if group != "ทั้งหมด":
        d = d[d["business_group"].astype(str) == str(group)]
    if d.empty:
        return pd.DataFrame(columns=["province", "objective", "business_group", "new_count", "closed_count", "total_event", "exit_share"])
    piv = (
        d.pivot_table(
            index=["province", "objective", "business_group"],
            columns="event_type",
            values="source",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
    )
    if "จัดตั้งใหม่" not in piv.columns:
        piv["จัดตั้งใหม่"] = 0
    if "เลิกกิจการ" not in piv.columns:
        piv["เลิกกิจการ"] = 0
    piv = piv.rename(columns={"จัดตั้งใหม่": "new_count", "เลิกกิจการ": "closed_count"})
    piv["new_count"] = pd.to_numeric(piv["new_count"], errors="coerce").fillna(0)
    piv["closed_count"] = pd.to_numeric(piv["closed_count"], errors="coerce").fillna(0)
    piv["total_event"] = piv["new_count"] + piv["closed_count"]
    piv["exit_share"] = np.where(piv["total_event"] > 0, piv["closed_count"] / piv["total_event"] * 100, np.nan)
    return piv.sort_values(["total_event", "new_count"], ascending=False).reset_index(drop=True)


def province_entry_exit_summary(detail: pd.DataFrame, group: str = "ทั้งหมด") -> pd.DataFrame:
    """สรุประดับจังหวัดจากไฟล์รายชื่อจริง: new/closed/exit_share."""
    if detail is None or detail.empty:
        return pd.DataFrame(columns=["province", "new_count", "closed_count", "total_event", "exit_share", "n_types"])
    d = detail.copy()
    if group != "ทั้งหมด":
        d = d[d["business_group"].astype(str) == str(group)]
    if d.empty:
        return pd.DataFrame(columns=["province", "new_count", "closed_count", "total_event", "exit_share", "n_types"])
    piv = (
        d.pivot_table(index="province", columns="event_type", values="source", aggfunc="count", fill_value=0)
        .reset_index()
    )
    if "จัดตั้งใหม่" not in piv.columns:
        piv["จัดตั้งใหม่"] = 0
    if "เลิกกิจการ" not in piv.columns:
        piv["เลิกกิจการ"] = 0
    piv = piv.rename(columns={"จัดตั้งใหม่": "new_count", "เลิกกิจการ": "closed_count"})
    n_types = d.groupby("province")["objective"].nunique().reset_index(name="n_types")
    out = piv.merge(n_types, on="province", how="left")
    out["total_event"] = out["new_count"] + out["closed_count"]
    out["exit_share"] = np.where(out["total_event"] > 0, out["closed_count"] / out["total_event"] * 100, np.nan)
    return out.sort_values("total_event", ascending=False).reset_index(drop=True)


def entry_exit_scatter(df: pd.DataFrame) -> go.Figure:
    if df is None or df.empty:
        fig = go.Figure(); fig.add_annotation(text="ข้อมูลไม่เพียงพอ", x=.5, y=.5, showarrow=False)
        return fig_layout(fig, "Local Entry-Exit", height=360, showlegend=False)
    d = df.copy()
    fig = px.scatter(
        d,
        x="new_count",
        y="closed_count",
        size="total_event",
        color="exit_share",
        color_continuous_scale="RdYlGn_r",
        hover_name="province",
        custom_data=["province", "new_count", "closed_count", "exit_share", "n_types"],
        size_max=48,
        labels={
            "new_count": "จำนวนจัดตั้งใหม่ (ราย)",
            "closed_count": "จำนวนเลิกกิจการ (ราย)",
            "exit_share": "สัดส่วนเลิกกิจการ (%)",
            "total_event": "กิจกรรมรวม",
        },
    )
    fig.update_traces(
        marker=dict(line=dict(color="rgba(255,255,255,.45)", width=0.8)),
        hovertemplate="%{customdata[0]}<br>จัดตั้งใหม่: %{customdata[1]:,.0f} ราย<br>เลิกกิจการ: %{customdata[2]:,.0f} ราย<br>สัดส่วนเลิก: %{customdata[3]:.2f}%<br>จำนวนประเภทธุรกิจ: %{customdata[4]:,.0f}<extra></extra>",
    )
    med_x = d["new_count"].median() if len(d) else 0
    med_y = d["closed_count"].median() if len(d) else 0
    fig.add_vline(x=med_x, line_dash="dash", line_color="rgba(255,255,255,.45)", annotation_text="ค่ากลางจัดตั้ง")
    fig.add_hline(y=med_y, line_dash="dash", line_color="rgba(255,255,255,.45)", annotation_text="ค่ากลางเลิก")
    fig.update_layout(xaxis_title="จำนวนจัดตั้งใหม่ (ราย)", yaxis_title="จำนวนเลิกกิจการ (ราย)", coloraxis_colorbar_title="สัดส่วนเลิก (%)")
    return fig_layout(fig, "จังหวัด: จัดตั้งใหม่ vs เลิกกิจการ", height=560, showlegend=False)


def entry_exit_stacked_bar(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    if df is None or df.empty:
        fig = go.Figure(); fig.add_annotation(text="ข้อมูลไม่เพียงพอ", x=.5, y=.5, showarrow=False)
        return fig_layout(fig, "Local Entry-Exit", height=360, showlegend=False)
    d = df.sort_values("total_event", ascending=False).head(top_n).sort_values("total_event")
    fig = go.Figure()
    # วาง "เลิกกิจการ" ไว้ซ้ายก่อน เพราะมีค่าน้อยกว่าและเป็นส่วนที่ต้องการให้ผู้ใช้เห็นเป็นฐานเปรียบเทียบ
    fig.add_trace(go.Bar(
        y=d["province"], x=d["closed_count"], orientation="h", name="เลิกกิจการ",
        marker=dict(color=RED), text=[_fmt_int(v) for v in d["closed_count"]], textposition="inside"
    ))
    fig.add_trace(go.Bar(
        y=d["province"], x=d["new_count"], orientation="h", name="จัดตั้งใหม่",
        marker=dict(color=GREEN), text=[_fmt_int(v) for v in d["new_count"]], textposition="inside"
    ))
    fig.update_layout(
        barmode="stack",
        xaxis_title="จำนวนรายการจากไฟล์รายชื่อ",
        yaxis_title="จังหวัด",
        legend_title_text="ประเภทเหตุการณ์"
    )
    return fig_layout(fig, "กราฟแท่งซ้อนแนวนอน: Top จังหวัดที่มีข้อมูลจัดตั้ง/เลิกมากที่สุด", height=max(520, top_n * 34 + 160), showlegend=True)


def local_objective_stacked_bar(df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    if df is None or df.empty:
        fig = go.Figure(); fig.add_annotation(text="ข้อมูลไม่เพียงพอ", x=.5, y=.5, showarrow=False)
        return fig_layout(fig, "Local Business Finder", height=360, showlegend=False)
    d = df.sort_values("total_event", ascending=False).head(top_n).sort_values("total_event")
    # ย่อชื่อและขึ้นบรรทัดใหม่เพื่อไม่ให้ซ้อนกับกราฟแท่งอื่น แต่ยังอ่านได้ครบ
    d["label"] = d["objective"].apply(lambda x: _wrap_label(x, width=18, max_lines=5))
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=d["label"], x=d["closed_count"], orientation="h", name="เลิกกิจการ",
        marker=dict(color=RED), text=[_fmt_int(v) for v in d["closed_count"]], textposition="inside"
    ))
    fig.add_trace(go.Bar(
        y=d["label"], x=d["new_count"], orientation="h", name="จัดตั้งใหม่",
        marker=dict(color=GREEN), text=[_fmt_int(v) for v in d["new_count"]], textposition="inside"
    ))
    fig.update_layout(
        barmode="stack",
        xaxis_title="จำนวนรายการจากไฟล์รายชื่อ",
        yaxis_title="ประเภทธุรกิจ",
        legend_title_text="ประเภทเหตุการณ์"
    )
    return fig_layout(fig, "กราฟแท่งซ้อนแนวนอน: ธุรกิจที่พบจริงในจังหวัดที่เลือก", height=max(760, top_n * 82 + 180), showlegend=True)


def local_finder_summary_cards(df: pd.DataFrame, province_name: str, group: str):
    if df is None or df.empty:
        st.warning("ข้อมูลไม่เพียงพอ ขออภัยในความไม่สะดวก: ไม่มีประเภทธุรกิจที่ผ่านตัวกรองนี้")
        return

    total_new = float(df["new_count"].sum())
    total_closed = float(df["closed_count"].sum())
    total_event = float(df["total_event"].sum())
    exit_share = total_closed / total_event * 100 if total_event else np.nan
    top_new = df.sort_values(["new_count", "total_event"], ascending=False).head(5)
    top_risk = df[df["total_event"] >= 2].sort_values(["exit_share", "closed_count"], ascending=False).head(5)

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("จัดตั้งใหม่", _fmt_int(total_new), f"จังหวัด {province_name}")
    with c2:
        metric_card("เลิกกิจการ", _fmt_int(total_closed), f"กลุ่ม {group}")
    with c3:
        metric_card("สัดส่วนเลิก", f"{_fmt_float(exit_share)}%", "เลิก ÷ (จัดตั้ง+เลิก)")

    left, right = st.columns(2)
    with left:
        st.markdown("<div class='glass-card'><div class='section-eyebrow' style='color:#22c55e'>ธุรกิจที่มีสัญญาณเกิดใหม่สูงในพื้นที่</div>", unsafe_allow_html=True)
        for r in top_new.itertuples():
            st.markdown(f"- **{r.objective}**  \
  จัดตั้งใหม่ **{_fmt_int(r.new_count)}** ราย · เลิก **{_fmt_int(r.closed_count)}** ราย")
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown("<div class='glass-card'><div class='section-eyebrow' style='color:#ef4444'>ธุรกิจที่ควรระวังจากสัดส่วนเลิกกิจการ</div>", unsafe_allow_html=True)
        if top_risk.empty:
            st.markdown("- ข้อมูลเลิกกิจการยังน้อยเกินไปสำหรับจัดอันดับความเสี่ยง")
        else:
            for r in top_risk.itertuples():
                st.markdown(f"- **{r.objective}**  \
  สัดส่วนเลิก **{_fmt_float(r.exit_share)}%** · รวม **{_fmt_int(r.total_event)}** ราย")
        st.markdown("</div>", unsafe_allow_html=True)

    st.info("สรุปการอ่านแท็บนี้: ใช้ดูว่าจังหวัดนั้นมีธุรกิจอะไร 'เกิดขึ้นจริง' บ้าง ถ้าธุรกิจใดเปิดใหม่มากและเลิกต่ำ ให้คัดไปดูต่อใน Risk Score / SME Warning ส่วนธุรกิจที่สัดส่วนเลิกสูงควรระวังเป็นพิเศษ")

# ============================================================
# Page
# ============================================================
page_header(
    "🛟 Business Survival Analysis",
    "วิเคราะห์ธุรกิจที่อยู่รอด / ร่วงเร็ว / ตลาดเลือด และช่วยเตือนผู้ประกอบการก่อนลงทุน",
    pills=["Survival Rate", "Local Entry-Exit", "Risk Score", "SME Warning", "Monthly Bubble", "Local Business Finder", "Drilldown"],
)

biz = load_survival_business_data()
province = load_province_latest()

if biz.empty:
    st.warning("ยังไม่พบ/อ่านไฟล์ประเภทจัดตั้งเลิกขนาด69_* ในโฟลเดอร์ data ไม่ได้")
    with st.expander("Debug: ไฟล์ที่ระบบเห็น"):
        st.write([f.name for f in _all_files()])
    st.stop()

# Sidebar: only guide, no calculation filters. Filters are placed inside each tab.
st.sidebar.markdown("### 🧭 ตัวช่วยอ่านหน้า")
st.sidebar.caption("เลือกตัวกรองในแต่ละแท็บได้เลย เพื่อให้รู้ว่าฟิลเตอร์นั้นใช้กับกราฟไหน")

groups = ["ทั้งหมด"] + sorted(biz["business_group"].dropna().unique().tolist())
all_types_master = sorted(biz["type"].dropna().unique().tolist())
province_options = ["ไม่เลือกจังหวัด"] + sorted(province["province"].dropna().unique().tolist()) if not province.empty else ["ไม่เลือกจังหวัด"]
local_province_options = province_options_from_detail() or [p for p in province_options if p != "ไม่เลือกจังหวัด"]

valid_all, invalid_all = _valid_survival(biz)
weighted_survival = (valid_all["active_count"].sum() / (valid_all["active_count"].sum() + valid_all["total_quit"].sum()) * 100) if (valid_all["active_count"].sum() + valid_all["total_quit"].sum()) > 0 else np.nan
avg_red = biz["red_ocean_index"].replace([np.inf, -np.inf], np.nan).mean()

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card("ประเภทธุรกิจ", f"{len(biz):,.0f}", "ทั้งหมดในไฟล์")
with c2:
    metric_card("Survival Rate", f"{_fmt_float(weighted_survival)}%", "weighted จากรายการที่คำนวณได้")
with c3:
    metric_card("เลิกกิจการรวม", _fmt_int(biz["total_quit"].sum()), "ม.ค.–เม.ย. 2569")
with c4:
    metric_card("แรงกดดันตลาดเฉลี่ย", f"{_fmt_float(avg_red)}%", "จัดตั้งใหม่ / คงอยู่")

st.markdown(
    f"""
    <div class='glass-card'>
      <div class='section-eyebrow'>ข้อมูลที่ใช้</div>
      ข้อมูลล่าสุดที่ใช้ในหน้านี้คือ <b>{LATEST_MONTH_TEXT}</b><br>
      ไฟล์หลัก: <b>{_source_file_names('ประเภท', 'active', year=2569)}</b> · <b>{_source_file_names('ประเภท', 'quit', year=2569)}</b> · <b>{_source_file_names('ประเภท', 'regis', year=2569)}</b><br>
      สูตร Survival Rate = <b>จำนวนคงอยู่ ÷ (จำนวนคงอยู่ + จำนวนเลิกกิจการ) × 100</b><br>
      หมายเหตุ: ถ้า Active เป็น 0 แต่มี Quit ระบบจะแยกเป็น <b>ข้อมูลไม่พอ</b> ไม่ตีความว่า Survival = 0% แบบสุ่มสี่สุ่มห้า
    </div>
    """,
    unsafe_allow_html=True,
)

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "1) Survival Rate",
    "2) Local Entry-Exit",
    "3) Risk Score",
    "4) SME Warning",
    "5) Monthly Bubble",
    "6) Local Business Finder",
    "7) Data Drilldown",
])

with tab1:
    st.markdown("## 1) ธุรกิจไหนอยู่รอด และธุรกิจไหนร่วงเร็ว?")
    st.caption(f"ข้อมูล: ประเภทจัดตั้งเลิกขนาด68/69 active + quit · ใช้เปรียบเทียบ Survival Rate ปี 2568 และ 2569")

    f1, f2, f3, f4 = st.columns([1, 1, 1, 1])
    with f1:
        min_regis_1 = st.number_input("ขั้นต่ำจำนวนจัดตั้งใหม่", 0, int(max(biz["total_regis"].max(), 1)), 10, step=1, key="surv_min_regis")
    with f2:
        group_1 = st.selectbox("กลุ่มธุรกิจ", groups, key="surv_group")
    with f3:
        threshold_1 = st.number_input("เกณฑ์ที่ถือว่า ‘รอด’ (%)", 0.0, 100.0, 90.0, step=1.0, key="surv_threshold")
    with f4:
        mode_1 = st.selectbox("เรียงลำดับ", ["เสี่ยงสูง", "รอดสูง"], key="surv_mode")
    n_show = st.number_input("จำนวนธุรกิจที่ต้องการแสดง", min_value=5, max_value=30, value=15, step=5, key="survival_n")

    base1 = _apply_business_filter(biz, min_regis=min_regis_1, group=group_1)
    biz68 = load_survival_business_data_year(2568)
    if not biz68.empty:
        merge68 = biz68[["type", "survival_rate"]].rename(columns={"survival_rate": "survival_rate_68"})
        base1 = base1.merge(merge68, on="type", how="left")

    valid1, invalid1 = _valid_survival(base1)

    if valid1.empty:
        st.warning("ข้อมูลไม่เพียงพอสำหรับคำนวณ Survival Rate เพราะไม่พบจำนวนคงอยู่ในกลุ่มที่เลือก")
    else:
        # ลบกราฟ lollipop เดิมออกแล้ว เหลือกราฟเปรียบเทียบปี 2568/2569 เป็นกราฟหลัก
        if biz68.empty or "survival_rate_68" not in valid1.columns or valid1["survival_rate_68"].dropna().empty:
            st.warning("ยังไม่พบข้อมูลปี 2568 ที่เพียงพอสำหรับเปรียบเทียบ จึงยังแสดงกราฟเทียบปีไม่ได้")
            st.info("ข้อมูลปี 2569 ยังอ่านได้อยู่ แต่เพื่อไม่ให้ผู้ใช้เข้าใจผิด หน้านี้จะไม่สรุปแนวโน้มข้ามปีจนกว่าจะมีข้อมูลปี 2568 ที่ match กับประเภทธุรกิจได้")
        else:
            st.markdown("### เปรียบเทียบ Survival Rate ปี 2568 และ 2569")
            st.markdown(
                """
                <div class='glass-card'>
                    <div class='section-eyebrow'>How to read</div>
                    <ul class='insight-list'>
                        <li><b>สีเทา</b> = Survival Rate ปี 2568 และ <b>สีเขียว</b> = Survival Rate ปี 2569</li>
                        <li>ถ้าแท่งสีเขียวยาวกว่าแท่งสีเทา แปลว่าในปี 2569 ธุรกิจนั้นมีสัญญาณอยู่รอดดีขึ้นเมื่อเทียบกับปีก่อน</li>
                        <li>ถ้าแท่งสีเขียวสั้นกว่าแท่งสีเทา แปลว่าควรตรวจสอบเพิ่ม เพราะอัตราอยู่รอดลดลงเมื่อเทียบกับปี 2568</li>
                        <li>เส้นประสีเหลืองคือเกณฑ์ที่ผู้ใช้ตั้งไว้ เช่น 90% ถ้าต่ำกว่าเส้นนี้ให้ถือว่าเป็นกลุ่มที่ควรระวัง</li>
                        <li><b>สิ่งที่ผู้ใช้ควรทำต่อ:</b> เลือกธุรกิจที่ Survival Rate สูงและค่อนข้างคงที่ทั้ง 2 ปี แล้วไปดูหน้า Category เพื่อดูโอกาสทางตลาด และหน้า Province เพื่อเลือกพื้นที่ที่เหมาะสม</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.plotly_chart(
                survival_year_comparison_bar(valid1, threshold_1, int(n_show)),
                use_container_width=True,
                key="survival_compare_68_69_tab1",
            )

            comp = valid1.dropna(subset=["survival_rate_68", "survival_rate"]).copy()
            comp["survival_change"] = comp["survival_rate"] - comp["survival_rate_68"]

            improve = comp.sort_values("survival_change", ascending=False).head(5)
            decline = comp.sort_values("survival_change", ascending=True).head(5)
            stable_high = comp[
                (comp["survival_rate"] >= threshold_1) &
                (comp["survival_rate_68"] >= threshold_1)
            ].sort_values("survival_rate", ascending=False).head(5)

            s1, s2 = st.columns(2)
            with s1:
                st.markdown("<div class='glass-card'><div class='section-eyebrow'>สัญญาณดีขึ้นมากสุด</div>", unsafe_allow_html=True)
                if improve.empty:
                    st.markdown("- ยังไม่มีข้อมูลพอสำหรับสรุป")
                else:
                    for r in improve.itertuples():
                        st.markdown(f"- **{r.type}** — 2568: {_fmt_float(r.survival_rate_68)}% → 2569: {_fmt_float(r.survival_rate)}% (**{r.survival_change:+.2f} จุด**)") 
                st.markdown("</div>", unsafe_allow_html=True)
            with s2:
                st.markdown("<div class='glass-card'><div class='section-eyebrow'>ควรตรวจสอบเพิ่ม</div>", unsafe_allow_html=True)
                if decline.empty:
                    st.markdown("- ยังไม่มีข้อมูลพอสำหรับสรุป")
                else:
                    for r in decline.itertuples():
                        st.markdown(f"- **{r.type}** — 2568: {_fmt_float(r.survival_rate_68)}% → 2569: {_fmt_float(r.survival_rate)}% (**{r.survival_change:+.2f} จุด**)") 
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div class='glass-card'><div class='section-eyebrow'>สรุปจากกราฟ</div>", unsafe_allow_html=True)
            if not stable_high.empty:
                top_stable = stable_high.iloc[0]
                st.markdown(f"- ธุรกิจที่อยู่รอดสูงและค่อนข้างน่าสนใจให้ตรวจต่อ เช่น **{top_stable['type']}** เพราะ Survival Rate สูงกว่าเกณฑ์ทั้ง 2 ปี")
            st.markdown("- ถ้าธุรกิจใด Survival Rate สูงมากทั้งสองปี ไม่ได้แปลว่าลงทุนแล้วสำเร็จแน่นอน แต่แปลว่าจากฐานข้อมูลที่มี จำนวนเลิกกิจการต่ำเมื่อเทียบกับธุรกิจคงอยู่")
            st.markdown("- ถ้าธุรกิจใดปี 2569 ต่ำกว่าปี 2568 ชัดเจน ควรไปดูหน้า Survival tab อื่น ๆ เพื่อเช็กจำนวนเลิกกิจการ และไปดูหน้า Category เพื่อเช็กการแข่งขัน")
            st.markdown("</div>", unsafe_allow_html=True)

    if not invalid1.empty:
        with st.expander(f"รายการที่ข้อมูลไม่พอสำหรับ Survival Rate ({len(invalid1):,.0f} รายการ)"):
            st.write("สาเหตุหลักคือ active_count เป็น 0 หรือไม่พบในไฟล์ active แต่มีจำนวนเลิกกิจการ จึงไม่ควรฝืนตีความเป็น Survival 0%")
            st.dataframe(invalid1[["type", "business_group", "active_count", "total_quit", "total_regis"]].head(30), use_container_width=True, hide_index=True)

with tab2:
    st.markdown("## 2) Local Entry-Exit: จังหวัดไหนมีธุรกิจเกิดใหม่/เลิกกิจการมาก?")
    st.caption("ใช้ข้อมูลจริงจากไฟล์รายชื่อจัดตั้ง69.csv และ เลิก69.csv เท่านั้น เพื่อดูแรงเคลื่อนไหวของตลาดระดับพื้นที่")
    st.markdown("สูตรสัดส่วนเลิกกิจการ = **จำนวนเลิกกิจการ ÷ (จำนวนจัดตั้งใหม่ + จำนวนเลิกกิจการ) × 100**")
    st.markdown("**กราฟที่ใช้:** กราฟกระจาย (Scatter Plot) และกราฟแท่งซ้อนแนวนอน (Horizontal Stacked Bar Chart)")

    detail2 = province_detail_data()
    if detail2.empty:
        st.warning("ข้อมูลไม่เพียงพอ ขออภัยในความไม่สะดวก: ยังอ่านไฟล์รายชื่อจัดตั้ง/เลิกไม่ได้")
        with st.expander("Debug การอ่านไฟล์รายชื่อ", expanded=True):
            st.write("new candidates", [f.name for f in _company_file_candidates("new")])
            st.write("closed candidates", [f.name for f in _company_file_candidates("closed")])
            st.dataframe(company_read_debug_summary(), use_container_width=True, hide_index=True)
    else:
        with st.expander("ตัวอย่างจังหวัดที่มีข้อมูลจริงในไฟล์รายชื่อจัดตั้ง/เลิก", expanded=False):
            st.dataframe(local_data_examples(10), use_container_width=True, hide_index=True)

        f1, f2 = st.columns([1, 1])
        local_groups = ["ทั้งหมด"] + sorted(detail2["business_group"].dropna().astype(str).unique().tolist())
        with f1:
            group_2 = st.selectbox("กลุ่มธุรกิจ", local_groups, key="entry_exit_group")
        with f2:
            top_n_2 = st.number_input("จำนวนจังหวัดที่แสดงในกราฟแท่ง", 5, 30, 15, step=5, key="entry_exit_topn")

        prov_sum = province_entry_exit_summary(detail2, group_2)
        if prov_sum.empty:
            st.warning("ไม่มีข้อมูลหลังผ่านตัวกรองนี้")
        else:
            st.plotly_chart(entry_exit_scatter(prov_sum), use_container_width=True, key=f"entry_exit_scatter_{group_2}")
            st.plotly_chart(entry_exit_stacked_bar(prov_sum, int(top_n_2)), use_container_width=True, key=f"entry_exit_bar_{group_2}_{top_n_2}")

            high_activity = prov_sum.sort_values("total_event", ascending=False).head(5)
            high_exit = prov_sum[prov_sum["total_event"] >= 2].sort_values("exit_share", ascending=False).head(5)
            s1, s2 = st.columns(2)
            with s1:
                st.markdown("<div class='glass-card'><div class='section-eyebrow' style='color:#22c55e'>1) จังหวัดที่มีความเคลื่อนไหวทางธุรกิจมากที่สุด</div>", unsafe_allow_html=True)
                st.markdown("กราฟฝั่งนี้ช่วยหาจังหวัดที่มีทั้งการเปิดใหม่และเลิกกิจการจำนวนมาก ซึ่งมักเป็นตลาดใหญ่และมีการเคลื่อนไหวสูง")
                for r in high_activity.itertuples():
                    st.markdown(f"- **{r.province}** — จัดตั้ง **{_fmt_int(r.new_count)}** | เลิก **{_fmt_int(r.closed_count)}** | รวม **{_fmt_int(r.total_event)}** ราย")
                st.markdown("</div>", unsafe_allow_html=True)
            with s2:
                st.markdown("<div class='glass-card'><div class='section-eyebrow' style='color:#ef4444'>2) จังหวัดที่ควรตรวจสอบความเสี่ยงเพิ่มเติม</div>", unsafe_allow_html=True)
                st.markdown("ฝั่งนี้ใช้ดูจังหวัดที่สัดส่วนเลิกกิจการสูง เพื่อเตือนว่าตลาดอาจมีแรงกดดันมากกว่าพื้นที่อื่น")
                if high_exit.empty:
                    st.markdown("- ข้อมูลเลิกกิจการยังน้อยเกินไปสำหรับจัดอันดับความเสี่ยง")
                else:
                    for r in high_exit.itertuples():
                        st.markdown(f"- **{r.province}** — สัดส่วนเลิก **{_fmt_float(r.exit_share)}%** จากข้อมูลรวม **{_fmt_int(r.total_event)}** ราย")
                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("<div class='glass-card'><div class='section-eyebrow'>สรุปแบบอ่านเร็ว</div><ul class='insight-list'><li><b>สิ่งที่กราฟสื่อ:</b> จังหวัดที่แท่งสีเขียวยาว แปลว่ามีธุรกิจใหม่เข้ามามาก ส่วนแท่งสีแดงถ้ายาวผิดปกติแปลว่าต้องระวังแรงปิดกิจการ</li><li><b>สิ่งที่ผู้ใช้ควรทำต่อ:</b> เลือกจังหวัดที่จัดตั้งใหม่สูงแต่สัดส่วนเลิกไม่สูงเกินไป แล้วไปดูต่อในแท็บ Risk Score และ Drilldown เพื่อดูว่าเป็นธุรกิจประเภทใด</li></ul></div>", unsafe_allow_html=True)


with tab3:
    st.markdown("## 3) ธุรกิจใดมี Risk Score สูงสุด?")
    st.caption(f"ข้อมูล: ประเภทจัดตั้งเลิกขนาด69_regis / active / quit · ช่วง ม.ค.–เม.ย. 2569")
    st.markdown("สูตร Risk Score = **0.45×Fall Score + 0.35×Closure Score + 0.20×Market Pressure Score**")
    st.markdown("**กราฟที่ใช้:** กราฟแท่งแนวนอนไล่สี (Horizontal Gradient Bar Chart)")
    r1, r2, r3 = st.columns(3)
    with r1:
        min_regis_3 = st.number_input("ขั้นต่ำจำนวนจัดตั้งใหม่", 0, int(max(biz["total_regis"].max(), 1)), 10, step=1, key="risk_min_regis")
    with r2:
        group_3 = st.selectbox("กลุ่มธุรกิจ", groups, key="risk_group")
    with r3:
        n_3 = st.number_input("จำนวนอันดับที่แสดง", 5, 30, 15, step=5, key="risk_n")
    base3 = _apply_business_filter(biz, min_regis=min_regis_3, group=group_3)
    st.plotly_chart(risk_score_bar_gradient(base3, n=int(n_3)), use_container_width=True, key="risk_score_bar_tab3")
    top_all = base3.dropna(subset=["risk_score"]).sort_values("risk_score", ascending=False).copy()
    top = top_all.head(5)
    median_risk = float(top_all["risk_score"].median()) if not top_all.empty else np.nan
    csum1, csum2 = st.columns([1.1, 1])
    with csum1:
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>Risk Summary</div>", unsafe_allow_html=True)
        if len(top_all) < int(n_3):
            st.markdown(f"- หมายเหตุ: แสดงได้เพียง **{len(top_all):,.0f}** รายการ จากที่ขอ {int(n_3):,.0f} เพราะข้อมูลที่เหลือไม่ผ่านตัวกรองหรือไม่พอสำหรับคำนวณ Risk Score")
        else:
            st.markdown(f"- กราฟแสดง **{int(n_3):,.0f}** อันดับแรก และเส้นประคือ **ค่ามัธยฐานของคะแนนความเสี่ยง = {_fmt_float(median_risk,1)}**")
        st.markdown("- สีเขียว = เสี่ยงต่ำกว่าในชุดที่แสดง, สีเหลือง = ปานกลาง, สีแดง = เสี่ยงสูง")
        st.markdown("- ชื่อธุรกิจในกราฟมีหมายเลขลำดับเดียวกับสรุปด้านขวา เพื่อให้อ่านจับคู่ได้ง่าย")
        st.markdown("</div>", unsafe_allow_html=True)
    with csum2:
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>Top 5 ที่ควรระวัง</div>", unsafe_allow_html=True)
        for i, r in enumerate(top.itertuples(), start=1):
            st.markdown(f"**{i}. {r.type}**  \n- Risk Score: **{_fmt_float(r.risk_score,1)}**  \n- Survival: **{_fmt_float(r.survival_rate)}%** | Closure: **{_fmt_float(r.closure_rate)}%** | Market Pressure: **{_fmt_float(r.red_ocean_index)}%**")
        st.markdown("</div>", unsafe_allow_html=True)
    st.info("วิธีใช้ผลลัพธ์: เลือกธุรกิจที่คะแนนความเสี่ยงต่ำกว่าค่ามัธยฐานเป็นตัวเลือกตั้งต้น และถ้าจำเป็นต้องลงทุนในธุรกิจที่คะแนนสูง ให้ไปตรวจสอบเหตุผลต่อในแท็บ SME Warning และ Drilldown")

with tab4:
    st.markdown("## 4) SME ขนาดเล็กควรระวังธุรกิจประเภทไหน?")
    st.caption("ใช้ข้อมูลประเภทจัดตั้งเลิกขนาด69_size ร่วมกับ Risk Score เพื่อเตือนผู้ใช้ก่อนเลือกอาชีพ/ธุรกิจ")
    f1, f2 = st.columns(2)
    with f1:
        size_filter = st.selectbox("เลือกขนาดธุรกิจ", ["ทั้งหมด", "S", "M", "L"], key="size_filter")
    with f2:
        group_4 = st.selectbox("กลุ่มธุรกิจ", groups, key="sme_group")
    size_view = _apply_business_filter(biz, group=group_4)
    col_map = {"S": "size_s_count", "M": "size_m_count", "L": "size_l_count"}
    if size_filter != "ทั้งหมด":
        size_view = size_view[size_view[col_map[size_filter]] > 0]
    type_filter = st.multiselect("เลือกประเภทธุรกิจที่อยากโฟกัส", options=sorted(size_view["type"].dropna().unique().tolist()), default=[], key="sme_types")
    if type_filter:
        size_view = size_view[size_view["type"].isin(type_filter)]
    if size_view.empty or size_view["size_total_count"].sum() <= 0:
        st.warning("ข้อมูล S/M/L ไม่เพียงพอสำหรับคำนวณกราฟนี้ ขออภัยในความไม่สะดวก ระบบจึงไม่ฝืนคำนวณเพื่อเลี่ยงการตีความผิด")
    else:
        st.plotly_chart(sme_warning_chart(size_view, size_filter, n=12), use_container_width=True, key="sme_warning_chart_tab4")
        risky = size_view.sort_values("risk_score", ascending=False).head(5)
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>SME Warning Summary</div>", unsafe_allow_html=True)
        if size_filter != "ทั้งหมด":
            st.markdown(f"ระบบแสดงเฉพาะธุรกิจที่มีข้อมูลขนาด **{size_filter}** จริงหลังผ่านตัวกรอง เพื่อลดความรกของกราฟ")
        size_totals = {k: float(size_view[v].sum()) for k, v in col_map.items()}
        scarce = [k for k, v in size_totals.items() if v <= 0]
        if scarce:
            st.markdown(f"- ขนาดที่แทบไม่มีข้อมูลในตัวกรองนี้: **{', '.join(scarce)}** จึงไม่ควรฝืนตีความ")
        st.markdown("ถ้าผู้ใช้เป็น SME หรือทุนน้อย ควรดูธุรกิจเหล่านี้อย่างระมัดระวัง:")
        for r in risky.itertuples():
            st.markdown(f"- **{r.type}** — Risk {_fmt_float(r.risk_score,1)} | SME Share {_fmt_float(r.sme_share)}% | Survival {_fmt_float(r.survival_rate)}%")
        st.markdown("</div>", unsafe_allow_html=True)

with tab5:
    st.markdown("## 5) เดือนใดมีความเสี่ยงจากการเลิกกิจการมากที่สุด?")
    st.caption("ข้อมูล: ประเภทจัดตั้งเลิกขนาด69_quit · ช่วง ม.ค.–เม.ย. 2569")
    group_5 = st.selectbox("กลุ่มธุรกิจ", groups, key="bubble_group")
    base5 = _apply_business_filter(biz, group=group_5)
    default_types = base5.sort_values("total_quit", ascending=False)["type"].head(8).tolist()
    selected_bubble = st.multiselect("เลือกธุรกิจที่สนใจ", options=sorted(base5["type"].dropna().unique().tolist()), default=default_types, key="bubble_types")
    if not selected_bubble:
        st.warning("กรุณาเลือกอย่างน้อย 1 ธุรกิจเพื่อสร้าง Bubble Plot")
    else:
        st.plotly_chart(monthly_bubble(base5, selected_bubble), use_container_width=True, key="monthly_bubble_tab5")
        rows = []
        for t in selected_bubble:
            rr = base5[base5["type"] == t]
            if rr.empty:
                continue
            r = rr.iloc[0]
            vals = {m: r.get(f"{m}_quit", 0) for m in ["jan", "feb", "mar", "apr"]}
            best_month = max(vals, key=vals.get)
            rows.append((t, MONTH_FULL.get(best_month, best_month), vals[best_month]))
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>Professional Summary</div>", unsafe_allow_html=True)
        if not rows or max([x[2] for x in rows]) == 0:
            total_quit_selected = base5[base5["type"].isin(selected_bubble)]["total_quit"].sum() if "total_quit" in base5.columns else 0
            if total_quit_selected > 0:
                st.markdown("- ข้อมูลรายเดือนที่อ่านได้เป็น 0 ทั้งหมด แต่มี **จำนวนเลิกกิจการรวม** อยู่ จึงแสดงกราฟแท่งยอดรวมแทน Bubble รายเดือน")
                st.markdown("- การตีความ: ใช้กราฟนี้เพื่อดูว่าในธุรกิจที่เลือก ตัวไหนมีการเลิกกิจการสะสมมากกว่า แล้วนำไปตรวจใน Data Drilldown เพิ่ม")
                st.markdown("- สิ่งที่ควรทำต่อ: ถ้าต้องการวิเคราะห์ seasonality จริง ๆ ควรกลับไปตรวจไฟล์ quit รายเดือนว่ามีคอลัมน์ ม.ค./ก.พ./มี.ค./เม.ย. ครบหรือไม่")
            else:
                st.markdown("ธุรกิจที่เลือกไม่มีจำนวนเลิกกิจการในช่วง ม.ค.–เม.ย. 2569 จึงไม่ควรฝืนสรุปเดือนเสี่ยง")
        else:
            for t, m, v in sorted(rows, key=lambda x: x[2], reverse=True)[:8]:
                st.markdown(f"- **{t}** เสี่ยงเด่นสุดในเดือน **{m} 2569** โดยมีเลิกกิจการ **{_fmt_int(v)} ราย**")
            st.markdown("- ถ้า bubble ใหญ่หลายเดือนต่อเนื่อง แปลว่าความเสี่ยงไม่ได้เกิดครั้งเดียว ควรตรวจสอบสาเหตุเชิงตลาดก่อนลงทุน")
        st.markdown("</div>", unsafe_allow_html=True)

with tab6:
    st.markdown("## 6) Local Business Finder: จังหวัดนี้มีธุรกิจอะไรเกิดขึ้นจริงบ้าง?")
    st.caption("แท็บนี้เหมาะกับบริบทของไฟล์รายชื่อจัดตั้ง/เลิก เพราะช่วยให้ผู้ใช้เลือกจังหวัดแล้วเห็นธุรกิจที่มีข้อมูลจริง ไม่ต้องสุ่มเลือกจนเจอค่าว่าง")

    detail6 = province_detail_data()
    if detail6.empty:
        st.warning("ข้อมูลไม่เพียงพอ ขออภัยในความไม่สะดวก: ยังอ่านไฟล์รายชื่อจัดตั้ง/เลิกไม่ได้")
        with st.expander("Debug การอ่านไฟล์รายชื่อ", expanded=True):
            st.write("new candidates", [f.name for f in _company_file_candidates("new")])
            st.write("closed candidates", [f.name for f in _company_file_candidates("closed")])
            st.dataframe(company_read_debug_summary(), use_container_width=True, hide_index=True)
    else:
        with st.expander("ตัวอย่างจังหวัดและธุรกิจที่มีข้อมูลจริง", expanded=False):
            st.dataframe(local_data_examples(10), use_container_width=True, hide_index=True)

        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            test_province = st.selectbox("จังหวัดที่สนใจ", local_province_options, key="finder_province")
        group_options_6 = group_options_for_province(test_province)
        with cc2:
            test_group = st.selectbox("กลุ่มธุรกิจที่มีในจังหวัดนี้", group_options_6, key="finder_group")
        with cc3:
            min_events_6 = st.number_input("ขั้นต่ำกิจกรรมรวม", min_value=1, max_value=50, value=1, step=1, key="finder_min_events")

        local_df = local_activity_table(detail6, province=test_province, group=test_group)
        local_df = local_df[local_df["total_event"] >= min_events_6].copy()
        if local_df.empty:
            st.warning("ข้อมูลไม่เพียงพอ ขออภัยในความไม่สะดวก: จังหวัด/กลุ่มธุรกิจนี้ไม่มีข้อมูลที่ผ่านตัวกรอง")
        else:
            local_finder_summary_cards(local_df, test_province, test_group)
            st.markdown("**กราฟที่ใช้:** กราฟแท่งซ้อนแนวนอน (Horizontal Stacked Bar Chart)")
            st.plotly_chart(local_objective_stacked_bar(local_df, top_n=15), use_container_width=True, key=f"local_objective_bar_{test_province}_{test_group}_{min_events_6}")
            top_local = local_df.sort_values(["new_count", "total_event"], ascending=False).head(3)
            st.markdown("<div class='glass-card'><div class='section-eyebrow'>สรุปจากกราฟ</div><ul class='insight-list'>", unsafe_allow_html=True)
            st.markdown("<li><b>สิ่งที่กราฟสื่อ:</b> แท่งสีเขียวคือจำนวนจัดตั้งใหม่ ส่วนแท่งสีแดงคือจำนวนเลิกกิจการของประเภทธุรกิจที่พบจริงในจังหวัดนี้</li>", unsafe_allow_html=True)
            if not top_local.empty:
                lead = top_local.iloc[0]
                st.markdown(f"<li><b>ธุรกิจเด่นสุดตอนนี้:</b> {lead['objective']} มีจัดตั้งใหม่ {_fmt_int(lead['new_count'])} ราย และเลิก {_fmt_int(lead['closed_count'])} ราย</li>", unsafe_allow_html=True)
            st.markdown("<li><b>สิ่งที่ควรทำต่อ:</b> เลือกธุรกิจที่สีเขียวเด่นและสีแดงยังไม่สูงมาก ไปดูต่อในแท็บ Risk Score หรือ Data Drilldown ก่อนตัดสินใจ</li></ul></div>", unsafe_allow_html=True)

            st.markdown("### ตารางธุรกิจจริงในจังหวัดที่เลือก")
            show = local_df[["province", "objective", "business_group", "new_count", "closed_count", "total_event", "exit_share"]].copy()
            show = show.rename(columns={
                "province": "จังหวัด",
                "objective": "ประเภทธุรกิจ",
                "business_group": "กลุ่มธุรกิจ",
                "new_count": "จัดตั้งใหม่",
                "closed_count": "เลิกกิจการ",
                "total_event": "รวมกิจกรรม",
                "exit_share": "สัดส่วนเลิก (%)",
            })
            st.dataframe(show.sort_values("รวมกิจกรรม", ascending=False), use_container_width=True, hide_index=True)

            with st.expander("Data Drilldown แถวจริงจากไฟล์รายชื่อจัดตั้ง/เลิก"):
                raw_rows = detail6[(detail6["province"].astype(str) == str(test_province))].copy()
                if test_group != "ทั้งหมด":
                    raw_rows = raw_rows[raw_rows["business_group"] == test_group]
                st.dataframe(raw_rows[["province", "objective", "business_group", "event_type", "source"]].head(300), use_container_width=True, hide_index=True)


with tab7:
    st.markdown("## 7) Data Drilldown / ดูรายละเอียดประเภทธุรกิจ")
    st.caption("ใช้แท็บนี้เพื่อกดดูว่ากลุ่มธุรกิจประกอบด้วยประเภทอะไรบ้าง และตรวจสอบข้อมูลที่นำไปคำนวณ")
    group_7 = st.selectbox("เลือกกลุ่มธุรกิจสำหรับ Drilldown", groups, key="drill_group")
    drill = biz if group_7 == "ทั้งหมด" else biz[biz["business_group"] == group_7]
    with st.expander("ดูรายการประเภทธุรกิจในแต่ละกลุ่ม", expanded=True):
        for g, gd in drill.groupby("business_group"):
            with st.expander(f"{g} ({len(gd):,.0f} ประเภท)"):
                st.dataframe(gd[["type", "total_regis", "total_quit", "active_count", "survival_rate", "closure_rate", "risk_score"]].sort_values("risk_score", ascending=False), use_container_width=True, hide_index=True)

    feature_df = pd.DataFrame([
        ["type", "ชื่อประเภทธุรกิจ"],
        ["business_group", "กลุ่มธุรกิจที่ระบบจัดหมวด"],
        ["total_regis", "จำนวนจัดตั้งใหม่รวม ม.ค.–เม.ย. 2569"],
        ["total_quit", "จำนวนเลิกกิจการรวม ม.ค.–เม.ย. 2569"],
        ["active_count", "จำนวนธุรกิจดำเนินกิจการอยู่ ณ เม.ย. 2569"],
        ["survival_rate", "อัตราอยู่รอด = active_count / (active_count + total_quit) × 100"],
        ["red_ocean_index", "จำนวนจัดตั้งใหม่ / จำนวนคงอยู่ × 100"],
        ["risk_score", "คะแนนความเสี่ยงรวมจาก Fall, Closure และ Market Pressure"],
        ["S/M/L", "S < 1 ล้านบาท · M = 1–10 ล้านบาท · L > 10 ล้านบาท"],
    ], columns=["ฟีเจอร์", "ความหมาย"])
    st.markdown("### คำอธิบายฟีเจอร์")
    st.dataframe(feature_df, use_container_width=True, hide_index=True)

    show_cols = ["type", "business_group", "total_regis", "total_quit", "active_count", "survival_rate", "closure_rate", "red_ocean_index", "risk_score", "sme_share"]
    st.markdown("### ตารางข้อมูลหลังผ่านตัวกรอง")
    st.dataframe(drill[[c for c in show_cols if c in drill.columns]].sort_values("risk_score", ascending=False), use_container_width=True, hide_index=True)
