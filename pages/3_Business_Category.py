# -*- coding: utf-8 -*-
"""
Business Category Intelligence page for ThaiBiz Streamlit app.

อิง feedback จาก categories.pdf:
- Sidebar มี slider + ช่องกรอกเลข
- อธิบายว่ากลุ่มธุรกิจประกอบด้วยธุรกิจอะไรบ้าง
- Opportunity Map ไฮไลท์เฉพาะกลุ่มที่เลือก ส่วนกลุ่มอื่นเป็นสีอ่อน
- มี Note การตีความกราฟ + สรุปตามกลุ่มที่เลือก
- แกน/ชื่อกราฟภาษาไทย และ title ไม่ทับ legend
- Opportunity Score เป็น bar chart ปกติ พร้อมสูตรและคำอธิบาย
- Donut chart แยกตามกลุ่มธุรกิจ ใส่ % ตรงกลางวงกลม
- เพิ่ม Micro-Niche / Province Map จากรายชื่อจัดตั้ง69 และเลิก69 ถ้ามีไฟล์
- เพิ่มคำอธิบายฟีเจอร์ + สรุป stacked graph
- เพิ่ม Box plot และ Treemap เพื่อดูทุนที่ต้องเตรียม
"""

from __future__ import annotations

import re
import math
import unicodedata
from pathlib import Path
from functools import reduce

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from db import ensure_database_ready, load_business_metrics_duckdb as load_business_metrics
    ensure_database_ready(auto_refresh=True)
except Exception:
    from data_loader import load_business_metrics

try:
    from data_loader import DATA_DIR, data_files
except Exception:
    DATA_DIR = Path(__file__).resolve().parents[1] / "data"

    def data_files() -> list[Path]:
        return sorted(DATA_DIR.glob("*.csv"))

try:
    from style import apply_theme, configure_plotly, page_header, metric_card, fig_layout, COLORWAY
except Exception:
    from style import apply_theme, configure_plotly, page_header, metric_card, fig_layout
    COLORWAY = ["#a855f7", "#ec4899", "#14b8a6", "#38bdf8", "#f59e0b", "#22c55e", "#ef4444", "#64748b"]

apply_theme()
configure_plotly()

PRIMARY = "#a855f7"
PINK = "#ec4899"
ACCENT = "#14b8a6"
GREEN = "#22c55e"
RED = "#ef4444"
YELLOW = "#f59e0b"
WHITE_SOFT = "rgba(255,255,255,0.68)"
GRAY = "rgba(148,163,184,0.45)"

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

# ============================================================
# Helpers
# ============================================================

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s))
    s = s.replace("ประเเภท", "ประเภท").replace("เเ", "แ")
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _clean(s: str) -> str:
    return str(s).replace("\ufeff", "").strip()


def _to_num(x) -> pd.Series:
    return pd.to_numeric(
        pd.Series(x).astype(str).str.replace(",", "", regex=False).str.replace("-", "0", regex=False).str.strip(),
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


def _fmt_pct(x) -> str:
    return f"{_fmt_float(x, 2)}%"


def _all_data_files() -> list[Path]:
    paths: list[Path] = []
    if DATA_DIR.exists():
        for pat in ["*.csv", "*.xlsx", "*.xls"]:
            paths.extend(DATA_DIR.glob(pat))
    try:
        paths.extend(data_files())
    except Exception:
        pass
    out = []
    seen = set()
    for p in paths:
        if p.exists() and p not in seen:
            out.append(p)
            seen.add(p)
    return sorted(out)


def _read_table_auto(path: Path) -> pd.DataFrame:
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


def _find_files(*keywords: str, year: int | None = None) -> list[Path]:
    keys = [_norm(k) for k in keywords]
    yy = str(year)[-2:] if year else None
    out = []
    for f in _all_data_files():
        n = _norm(f.name)
        if yy and yy not in n:
            continue
        if all(k in n for k in keys):
            out.append(f)
    return sorted(out)


def _type_key(s: str) -> str:
    return _norm(str(s))[:120]


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
    if any(k in s for k in ["ซอฟต์แวร์", "คอมพิวเตอร์", "ข้อมูล", "เทคโนโลยี", "ดิจิทัล", "ออนไลน์"]):
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


def _ensure_business_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in [
        "regis_count", "regis_capital_m", "quit_count", "quit_capital_m", "active_count", "active_capital_m",
        "size_s_count", "size_m_count", "size_l_count", "size_total_count",
        "size_s_capital_m", "size_m_capital_m", "size_l_capital_m", "size_total_capital_m",
    ]:
        if c not in out.columns:
            out[c] = 0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)

    if "business_group" not in out.columns:
        out["business_group"] = out["type"].apply(_business_group)
    out["business_group"] = out["business_group"].replace({0: "อื่น ๆ", "0": "อื่น ๆ", "": "อื่น ๆ"}).fillna("อื่น ๆ")

    out["net_growth"] = out["regis_count"] - out["quit_count"]
    out["closure_rate"] = np.where(out["regis_count"] > 0, out["quit_count"] / out["regis_count"] * 100, 0)
    out["avg_capital_m"] = np.where(out["regis_count"] > 0, out["regis_capital_m"] / out["regis_count"], 0)
    out["capital_for_size_m"] = np.where(out["size_total_capital_m"] > 0, out["size_total_capital_m"], out["regis_capital_m"])
    out["sme_share"] = np.where(out["size_total_count"] > 0, out["size_s_count"] / out["size_total_count"] * 100, 0)

    # Recalculate opportunity score for consistency and explainability.
    demand_score = _normalize_score(out["regis_count"])
    survival_score = _normalize_score(out["closure_rate"], inverse=True)
    sme_score = _normalize_score(out["sme_share"])
    cap_clip = out["avg_capital_m"].clip(upper=out["avg_capital_m"].quantile(.95) if len(out) else 0)
    capital_score = _normalize_score(cap_clip)
    competition_penalty = _normalize_score(out["regis_count"])
    out["opportunity_score_calc"] = (0.30 * demand_score + 0.35 * survival_score + 0.20 * sme_score + 0.15 * capital_score - 0.15 * competition_penalty).clip(0, 100)
    if "opportunity_score" not in out.columns or out["opportunity_score"].sum() == 0:
        out["opportunity_score"] = out["opportunity_score_calc"]
    return out


def _group_examples(df: pd.DataFrame, group: str, n: int = 8) -> list[str]:
    if group == "ทั้งหมด":
        sample_df = df.sort_values("regis_count", ascending=False)
    else:
        sample_df = df[df["business_group"] == group].sort_values("regis_count", ascending=False)
    return sample_df["type"].astype(str).head(n).tolist()


def _make_group_note(df: pd.DataFrame, group: str) -> str:
    if group == "ทั้งหมด":
        groups = df.groupby("business_group")["type"].count().sort_values(ascending=False)
        top_groups = ", ".join([f"{g} ({int(v)} ประเภท)" for g, v in groups.head(5).items()])
        return f"ภาพรวมทุกกลุ่มธุรกิจ โดยกลุ่มที่มีจำนวนประเภทธุรกิจมากในข้อมูล ได้แก่ {top_groups}"
    examples = _group_examples(df, group, 8)
    ex_text = " / ".join(examples) if examples else "ไม่มีตัวอย่างหลังกรองข้อมูล"
    return f"กลุ่ม **{group}** ประกอบด้วยตัวอย่างธุรกิจ เช่น {ex_text}"


# ============================================================
# Optional raw company loader for province map / micro-niche
# ============================================================

THAI_PROVINCES = [
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท",
    "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก", "นครปฐม", "นครพนม", "นครราชสีมา",
    "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน", "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์",
    "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา", "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์",
    "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง", "ราชบุรี",
    "ลพบุรี", "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ", "สมุทรสงคราม",
    "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย",
    "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี",
]

PROVINCE_COORDS = {
    "กรุงเทพมหานคร": (13.7563, 100.5018), "กระบี่": (8.0863, 98.9063), "กาญจนบุรี": (14.0228, 99.5328),
    "กาฬสินธุ์": (16.4385, 103.5061), "กำแพงเพชร": (16.4828, 99.5227), "ขอนแก่น": (16.4419, 102.8350),
    "จันทบุรี": (12.6113, 102.1030), "ฉะเชิงเทรา": (13.6904, 101.0779), "ชลบุรี": (13.3611, 100.9847),
    "ชัยนาท": (15.1852, 100.1251), "ชัยภูมิ": (15.8068, 102.0315), "ชุมพร": (10.4930, 99.1800),
    "เชียงราย": (19.9105, 99.8406), "เชียงใหม่": (18.7883, 98.9853), "ตรัง": (7.5594, 99.6114),
    "ตราด": (12.2428, 102.5175), "ตาก": (16.8839, 99.1258), "นครนายก": (14.2069, 101.2131),
    "นครปฐม": (13.8199, 100.0622), "นครพนม": (17.3920, 104.7696), "นครราชสีมา": (14.9799, 102.0977),
    "นครศรีธรรมราช": (8.4304, 99.9631), "นครสวรรค์": (15.7047, 100.1372), "นนทบุรี": (13.8591, 100.5217),
    "นราธิวาส": (6.4255, 101.8253), "น่าน": (18.7756, 100.7730), "บึงกาฬ": (18.3609, 103.6464),
    "บุรีรัมย์": (14.9930, 103.1029), "ปทุมธานี": (14.0208, 100.5250), "ประจวบคีรีขันธ์": (11.8124, 99.7972),
    "ปราจีนบุรี": (14.0509, 101.3727), "ปัตตานี": (6.8695, 101.2501), "พระนครศรีอยุธยา": (14.3692, 100.5877),
    "พะเยา": (19.1920, 99.8788), "พังงา": (8.4501, 98.5255), "พัทลุง": (7.6167, 100.0779),
    "พิจิตร": (16.4429, 100.3488), "พิษณุโลก": (16.8211, 100.2659), "เพชรบุรี": (13.1119, 99.9447),
    "เพชรบูรณ์": (16.4190, 101.1606), "แพร่": (18.1446, 100.1403), "ภูเก็ต": (7.8804, 98.3923),
    "มหาสารคาม": (16.1851, 103.3026), "มุกดาหาร": (16.5422, 104.7235), "แม่ฮ่องสอน": (19.3010, 97.9654),
    "ยโสธร": (15.7926, 104.1453), "ยะลา": (6.5411, 101.2804), "ร้อยเอ็ด": (16.0538, 103.6520),
    "ระนอง": (9.9529, 98.6085), "ระยอง": (12.6814, 101.2816), "ราชบุรี": (13.5283, 99.8134),
    "ลพบุรี": (14.7995, 100.6534), "ลำปาง": (18.2888, 99.4909), "ลำพูน": (18.5745, 99.0087),
    "เลย": (17.4860, 101.7223), "ศรีสะเกษ": (15.1186, 104.3220), "สกลนคร": (17.1546, 104.1348),
    "สงขลา": (7.1898, 100.5951), "สตูล": (6.6238, 100.0674), "สมุทรปราการ": (13.5991, 100.5998),
    "สมุทรสงคราม": (13.4098, 100.0023), "สมุทรสาคร": (13.5475, 100.2744), "สระแก้ว": (13.8240, 102.0646),
    "สระบุรี": (14.5289, 100.9101), "สิงห์บุรี": (14.8936, 100.3967), "สุโขทัย": (17.0056, 99.8264),
    "สุพรรณบุรี": (14.4745, 100.1177), "สุราษฎร์ธานี": (9.1382, 99.3215), "สุรินทร์": (14.8829, 103.4937),
    "หนองคาย": (17.8783, 102.7413), "หนองบัวลำภู": (17.2218, 102.4260), "อ่างทอง": (14.5896, 100.4550),
    "อำนาจเจริญ": (15.8585, 104.6288), "อุดรธานี": (17.4138, 102.7872), "อุตรดิตถ์": (17.6201, 100.0993),
    "อุทัยธานี": (15.3835, 100.0246), "อุบลราชธานี": (15.2287, 104.8564),
}


def _find_province_in_row(row: pd.Series) -> str | None:
    combined = " ".join([str(v) for v in row.values if pd.notna(v)])
    combined = combined.replace("จ.", "จังหวัด")
    if "กรุงเทพ" in combined or "กทม" in combined:
        return "กรุงเทพมหานคร"
    for p in THAI_PROVINCES:
        if p in combined:
            return p
    return None


def _find_text_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    for c in df.columns:
        n = _norm(c)
        if any(_norm(k) in n for k in keywords):
            return c
    return None


@st.cache_data(show_spinner=False)
def load_company_province_group(year: int = 2569) -> pd.DataFrame:
    """อ่านรายชื่อจัดตั้ง/เลิก ถ้ามี เพื่อทำ Micro-Niche Map รายจังหวัด"""
    rows = []
    file_specs = [("รายชื่อจัดตั้ง", "new"), ("จัดตั้ง", "new"), ("เลิก", "closed")]
    used_files = set()

    for keyword, status in file_specs:
        for f in _find_files(keyword, year=year):
            # กันไม่ให้อ่านไฟล์ aggregate ประเภท/จังหวัดผิด
            n = _norm(f.name)
            if "จังหวัดจัดตั้ง" in n or "ประเภท" in n:
                continue
            if f in used_files:
                continue
            used_files.add(f)
            try:
                raw = _read_table_auto(f)
            except Exception:
                continue
            if raw.empty:
                continue

            prov_col = _find_text_col(raw, ["province", "จังหวัด"])
            obj_col = _find_text_col(raw, ["objective", "วัตถุ", "ประเภทธุรกิจ", "type", "ธุรกิจ"])
            if obj_col is None:
                # ใช้คอลัมน์ข้อความยาวที่สุดเป็น proxy
                text_cols = [c for c in raw.columns if raw[c].dtype == "object"]
                if text_cols:
                    obj_col = max(text_cols, key=lambda c: raw[c].astype(str).str.len().mean())

            tmp = pd.DataFrame()
            if prov_col:
                tmp["province"] = raw[prov_col].astype(str).str.strip().replace({"กทม.": "กรุงเทพมหานคร", "กรุงเทพฯ": "กรุงเทพมหานคร", "กรุงเทพ": "กรุงเทพมหานคร"})
            else:
                tmp["province"] = raw.apply(_find_province_in_row, axis=1)
            tmp["text"] = raw[obj_col].astype(str) if obj_col else raw.astype(str).agg(" ".join, axis=1)
            tmp["business_group"] = tmp["text"].apply(_business_group)
            tmp["status"] = status
            tmp = tmp.dropna(subset=["province"])
            tmp = tmp[tmp["province"].isin(THAI_PROVINCES)]
            rows.append(tmp[["province", "business_group", "status"]])

    if not rows:
        return pd.DataFrame(columns=["province", "business_group", "new_count", "closed_count", "closure_rate", "micro_score"])

    all_rows = pd.concat(rows, ignore_index=True)
    g = all_rows.groupby(["province", "business_group", "status"]).size().unstack(fill_value=0).reset_index()
    if "new" not in g.columns:
        g["new"] = 0
    if "closed" not in g.columns:
        g["closed"] = 0
    g = g.rename(columns={"new": "new_count", "closed": "closed_count"})
    g["closure_rate"] = np.where(g["new_count"] > 0, g["closed_count"] / g["new_count"] * 100, 0)

    # Micro score: ฟ้า/สูง = คู่แข่งน้อยและเลิกน้อย, แดง/ต่ำ = เปิดเยอะหรือเลิกเยอะ
    competition_penalty = _normalize_score(g["new_count"])
    risk_penalty = _normalize_score(g["closure_rate"])
    g["micro_score"] = (100 - (0.55 * competition_penalty + 0.45 * risk_penalty)).clip(0, 100)
    return g


# ============================================================
# Chart functions
# ============================================================


# ============================================================
# Additional optional imports
# ============================================================
try:
    import pydeck as pdk
except Exception:
    pdk = None

# ============================================================
# Chart / rendering helpers
# ============================================================

def _source_file_names(*keywords: str, year: int | None = None) -> str:
    files = _find_files(*keywords, year=year)
    if not files:
        return "-"
    return ", ".join(f.name for f in files)


def _chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def _metric_emoji(score: float) -> str:
    if score >= 70:
        return "🟢"
    if score >= 45:
        return "🟡"
    return "🔴"


def _wrap_label(text: str, width: int = 28, max_lines: int = 3) -> str:
    """Wrap long Thai labels for Plotly axis labels."""
    s = str(text)
    if len(s) <= width:
        return s
    parts = [s[i:i + width] for i in range(0, len(s), width)]
    if len(parts) > max_lines:
        parts = parts[:max_lines]
        parts[-1] = parts[-1] + "..."
    return "<br>".join(parts)


def _dedupe_types(df: pd.DataFrame, keep: int | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=getattr(df, 'columns', []))
    d = df.copy()
    d["type_key"] = d["type"].apply(_type_key)
    sort_cols = [c for c in ["opportunity_score", "regis_count", "regis_capital_m"] if c in d.columns]
    asc = [False] * len(sort_cols)
    if sort_cols:
        d = d.sort_values(sort_cols, ascending=asc)
    d = d.drop_duplicates(subset=["type_key"], keep="first")
    if keep is not None:
        d = d.head(keep)
    return d


def _ordered_group_totals(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("business_group", as_index=False)["regis_count"].sum()
    order = list(GROUP_COLORS.keys())
    g["order"] = g["business_group"].apply(lambda x: order.index(x) if x in order else 999)
    return g.sort_values(["order", "regis_count"], ascending=[True, False]).reset_index(drop=True)


def overall_group_donut(df: pd.DataFrame) -> go.Figure:
    """
    Donut chart แบบวาดเองด้วย Cartesian coordinates
    เพื่อให้ annotation arrow ชี้เข้าไปที่พื้นที่ slice จริงเหมือนตัวอย่าง Matplotlib:
        xy     = จุดหัวลูกศรบนพื้นที่ donut slice
        xytext = กล่องข้อความด้านนอก
    """
    g = _ordered_group_totals(df)
    total = float(g["regis_count"].sum())
    if g.empty or total <= 0:
        return go.Figure()

    values = g["regis_count"].astype(float).tolist()
    labels = g["business_group"].astype(str).tolist()
    colors = [GROUP_COLORS.get(x, PRIMARY) for x in labels]

    fig = go.Figure()

    outer_r = 1.00
    inner_r = 0.55
    arrow_r = 0.78      # หัวลูกศรอยู่บนพื้นที่สีของ donut
    label_r = 1.36      # ตำแหน่งกล่องข้อความด้านนอก
    start_angle = 90.0  # เริ่มจากด้านบน แล้วหมุนตามเข็มนาฬิกา

    current = start_angle
    annotations = []

    for label, value, color in zip(labels, values, colors):
        frac = value / total if total else 0
        sweep = frac * 360.0

        theta1 = current
        theta2 = current - sweep
        mid = (theta1 + theta2) / 2.0

        # points ของ annular sector / donut slice
        outer_deg = np.linspace(theta1, theta2, max(18, int(abs(sweep) / 3)))
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

        fig.add_trace(go.Scatter(
            x=x_poly,
            y=y_poly,
            mode="lines",
            fill="toself",
            fillcolor=color,
            line=dict(color="rgba(15,23,42,.92)", width=2),
            name=f"{label} — {frac * 100:.1f}%",
            hoverinfo="text",
            text=f"{label}<br>{value:,.0f} ราย<br>{frac * 100:.1f}%",
            showlegend=False,
        ))

        # เหมือน logic Matplotlib:
        # xy = 0.75*x, 0.75*y / xytext = 1.3*x, 1.3*y
        ang = math.radians(mid)
        x = math.cos(ang)
        y = math.sin(ang)

        x_tip = arrow_r * x
        y_tip = arrow_r * y
        x_text = label_r * x
        y_text = label_r * y

        if abs(x) < abs(y):
            xanchor = "center"
        elif x < 0:
            xanchor = "right"
        else:
            xanchor = "left"

        annotations.append(dict(
            x=x_tip,
            y=y_tip,
            xref="x",
            yref="y",
            ax=x_text,
            ay=y_text,
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1.35,
            arrowcolor=color,
            text=f"<b>{label}</b><br>{frac * 100:.1f}%",
            font=dict(size=12, color=color),
            bgcolor="rgba(15,23,42,.88)",
            bordercolor=color,
            borderwidth=0.9,
            borderpad=4,
            xanchor=xanchor,
            yanchor="middle",
            align="center",
        ))

        current = theta2

    # ข้อความกลางวง
    annotations.append(dict(
        x=0,
        y=0,
        xref="x",
        yref="y",
        showarrow=False,
        text=f"<b>ภาพรวมทั้ง 10 กลุ่ม</b><br><span style='font-size:26px'><b>{total:,.0f}</b></span><br><span style='font-size:13px'>ราย</span>",
        font=dict(size=22, color="#f8fafc"),
        align="center",
    ))

    fig.update_layout(
        annotations=annotations,
        height=560,
        margin=dict(l=40, r=40, t=35, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            visible=False,
            range=[-1.62, 1.62],
            constrain="domain",
        ),
        yaxis=dict(
            visible=False,
            range=[-1.42, 1.42],
            scaleanchor="x",
            scaleratio=1,
        ),
        showlegend=False,
    )

    return fig


def mini_group_donut(group_name: str, value: float, total: float, color: str) -> go.Figure:
    other = max(total - value, 0)
    pct = value / total * 100 if total else 0

    fig = go.Figure(go.Pie(
        values=[value, other],
        labels=[group_name, "กลุ่มอื่นรวม"],
        hole=0.67,
        sort=False,
        direction="clockwise",
        rotation=90,
        marker=dict(
            colors=[color, "rgba(255,255,255,0.10)"],
            line=dict(color="rgba(15,23,42,.85)", width=1.1)
        ),
        textinfo="none",
        hovertemplate="%{label}<br>%{value:,.0f} ราย<br>%{percent}<extra></extra>",
        showlegend=False,
    ))

    fig.add_annotation(
        x=0.5, y=0.5, showarrow=False,
        text=f"<b>{pct:.1f}%</b><br><span style='font-size:12px'>{group_name}</span>",
        font=dict(size=18, color="#f8fafc"),
    )

    fig.update_layout(
        title=dict(text=f"<b>{group_name}</b>", x=0.5, y=0.96, xanchor="center"),
        margin=dict(l=2, r=2, t=28, b=2),
        height=250,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render_group_donut_grid(df: pd.DataFrame):
    g = _ordered_group_totals(df)
    total = float(g["regis_count"].sum())
    if g.empty or total <= 0:
        st.info("ไม่มีข้อมูลพอสำหรับแสดงสัดส่วนวงกลม")
        return

    st.plotly_chart(overall_group_donut(df), use_container_width=True)
    for groups in _chunk(g.to_dict("records"), 5):
        cols = st.columns(5)
        for col, row in zip(cols, groups):
            with col:
                fig = mini_group_donut(
                    row["business_group"],
                    row["regis_count"],
                    total,
                    GROUP_COLORS.get(row["business_group"], PRIMARY)
                )
                st.plotly_chart(fig, use_container_width=True)


def horizontal_bar(df: pd.DataFrame, metric: str, label: str, title: str, x_title: str, n: int = 15,
                   selected_group: str = "ทั้งหมด", value_suffix: str = "", color_by_group: bool = False) -> go.Figure:
    d = df.dropna(subset=[metric, label]).copy().sort_values(metric, ascending=False).head(n).sort_values(metric)
    if d.empty:
        return go.Figure()
    if color_by_group:
        colors = [GROUP_COLORS.get(g, PRIMARY) if (selected_group == "ทั้งหมด" or g == selected_group) else "rgba(255,255,255,0.28)" for g in d["business_group"]]
    else:
        colors = [PRIMARY] * len(d)
    text = [f"{v:,.1f}{value_suffix}" if abs(v) < 100 else f"{v:,.0f}{value_suffix}" for v in d[metric]]
    fig = go.Figure(go.Bar(
        x=d[metric], y=d[label], orientation="h",
        marker=dict(color=colors, line=dict(color="rgba(255,255,255,.25)", width=0.5)),
        text=text, textposition="outside",
        hovertemplate=f"%{{y}}<br>{x_title}: %{{x:,.2f}}{value_suffix}<extra></extra>",
    ))
    fig.update_layout(margin=dict(t=80, l=10, r=30, b=50), xaxis_title=x_title, yaxis_title="ประเภทธุรกิจ", showlegend=False)
    return fig_layout(fig, title=title, height=max(440, n * 35 + 150), showlegend=False)


def opportunity_scatter(df: pd.DataFrame, selected_group: str) -> tuple[go.Figure, pd.DataFrame, float, float]:
    d = df[df["regis_count"] >= 1].copy()
    if d.empty:
        return go.Figure(), pd.DataFrame(), 0.0, 0.0

    d["bubble"] = np.sqrt(d["regis_capital_m"].clip(lower=0) + 1)
    bubble_max = float(d["bubble"].max()) if len(d) else 0
    d["bubble"] = d["bubble"] / bubble_max * 42 + 10 if bubble_max > 0 else 12

    ref = d if selected_group == "ทั้งหมด" else d[d["business_group"] == selected_group].copy()
    if ref.empty:
        ref = d.copy()
    med_x = float(ref["regis_count"].median()) if not ref.empty else 0.0
    med_y = float(ref["closure_rate"].median()) if not ref.empty else 0.0

    fig = go.Figure()
    if selected_group == "ทั้งหมด":
        for group, gd in d.groupby("business_group"):
            fig.add_trace(go.Scatter(
                x=gd["regis_count"], y=gd["closure_rate"], mode="markers", name=group,
                marker=dict(size=gd["bubble"], color=GROUP_COLORS.get(group, PRIMARY), opacity=0.82, line=dict(width=0.8, color="rgba(255,255,255,.35)")),
                text=gd["type"],
                customdata=np.stack([gd["opportunity_score"], gd["regis_capital_m"], gd["business_group"]], axis=-1),
                hovertemplate="%{text}<br>กลุ่ม: %{customdata[2]}<br>จัดตั้งใหม่: %{x:,.0f} ราย<br>Closure Rate: %{y:.2f}%<br>Opportunity Score: %{customdata[0]:.1f}<br>ทุน: %{customdata[1]:,.2f} ลบ.<extra></extra>",
            ))
    else:
        other = d[d["business_group"] != selected_group]
        sel = d[d["business_group"] == selected_group].copy()
        fig.add_trace(go.Scatter(
            x=other["regis_count"], y=other["closure_rate"], mode="markers", name="กลุ่มอื่น",
            marker=dict(size=other["bubble"], color="rgba(255,255,255,.15)", opacity=0.45, line=dict(width=0.5, color="rgba(255,255,255,.10)")),
            text=other["type"], hovertemplate="%{text}<br>จัดตั้งใหม่: %{x:,.0f}<br>Closure Rate: %{y:.2f}%<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=sel["regis_count"], y=sel["closure_rate"], mode="markers", name=selected_group,
            marker=dict(size=sel["bubble"], color=sel["opportunity_score"], colorscale="RdYlGn", cmin=0, cmax=100,
                        opacity=0.92, line=dict(width=1.1, color="#f8fafc"), colorbar=dict(title="Opportunity")),
            text=sel["type"],
            customdata=np.stack([sel["opportunity_score"], sel["regis_capital_m"], sel["business_group"]], axis=-1) if not sel.empty else None,
            hovertemplate="%{text}<br>กลุ่ม: %{customdata[2]}<br>จัดตั้งใหม่: %{x:,.0f} ราย<br>Closure Rate: %{y:.2f}%<br>Opportunity Score: %{customdata[0]:.1f}<br>ทุน: %{customdata[1]:,.2f} ลบ.<extra></extra>",
        ))

    fig.add_vline(x=med_x, line_dash="dash", opacity=.50, line_color="rgba(255,255,255,.55)", annotation_text=f"ค่ากลางจัดตั้งใหม่ {_fmt_int(med_x)}")
    fig.add_hline(y=med_y, line_dash="dash", opacity=.50, line_color="rgba(255,255,255,.55)", annotation_text=f"ค่ากลาง Closure Rate {_fmt_float(med_y)}%")
    fig.update_layout(
        title=dict(text="Business Opportunity-Risk Map", x=0.02, y=0.98, xanchor="left"),
        margin=dict(t=95, l=10, r=10, b=55),
        xaxis_title="จำนวนจัดตั้งใหม่ (ราย)",
        yaxis_title="Closure Rate (%)",
        legend_title_text="กลุ่มธุรกิจ",
    )
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1), title=dict(y=0.98))
    fig = fig_layout(fig, title="Business Opportunity-Risk Map", height=620, showlegend=True)
    return fig, ref, med_x, med_y


def opportunity_bar(df: pd.DataFrame, selected_group: str, n: int = 15) -> go.Figure:
    d = _dedupe_types(df.copy())
    d = d.sort_values("opportunity_score", ascending=False).head(n).sort_values("opportunity_score")
    if d.empty:
        return go.Figure()

    d["short_label"] = d["type"].astype(str).apply(lambda x: x if len(x) <= 42 else x[:42] + "…")
    colors = [
        GROUP_COLORS.get(g, PRIMARY) if selected_group == "ทั้งหมด" or g == selected_group else "rgba(255,255,255,0.26)"
        for g in d["business_group"]
    ]

    fig = go.Figure(go.Bar(
        x=d["opportunity_score"],
        y=d["short_label"],
        orientation="h",
        marker=dict(color=colors),
        text=[f"{v:.1f}" for v in d["opportunity_score"]],
        textposition="outside",
        cliponaxis=False,
        customdata=d[["type", "business_group", "regis_count", "closure_rate", "sme_share", "avg_capital_m"]],
        hovertemplate=(
            "%{customdata[0]}<br>"
            "กลุ่ม: %{customdata[1]}<br>"
            "Opportunity Score: %{x:.1f}<br>"
            "จัดตั้งใหม่: %{customdata[2]:,.0f}<br>"
            "Closure Rate: %{customdata[3]:.2f}%<br>"
            "SME Share: %{customdata[4]:.1f}%<br>"
            "ทุนเฉลี่ย: %{customdata[5]:,.2f} ลบ./ราย<extra></extra>"
        ),
    ))

    fig.update_layout(
        xaxis_title="Opportunity Score (0-100)",
        yaxis_title="ประเภทธุรกิจ",
        showlegend=False,
        margin=dict(t=90, l=30, r=70, b=55),
        xaxis=dict(range=[0, max(105, float(d["opportunity_score"].max()) + 12)]),
        yaxis=dict(tickfont=dict(size=11), automargin=True),
    )
    return fig_layout(fig, title="Top Opportunity Score", height=max(560, n * 34 + 180), showlegend=False)


def sme_stacked_bar(df: pd.DataFrame, n: int = 12) -> go.Figure:
    d = df[df["size_total_count"] > 0].copy().sort_values("regis_count", ascending=False).head(n)
    if d.empty:
        return go.Figure()
    for size in ["s", "m", "l"]:
        d[size.upper()] = np.where(d["size_total_count"] > 0, d[f"size_{size}_count"] / d["size_total_count"] * 100, 0)
    d = d.sort_values("S", ascending=True)
    fig = go.Figure()
    for col, color in [("S", PRIMARY), ("M", PINK), ("L", ACCENT)]:
        fig.add_trace(go.Bar(y=d["type"], x=d[col], name=col, orientation="h", marker=dict(color=color), text=d[col].round(1), texttemplate="%{text}%"))
    fig.update_layout(barmode="stack", xaxis_title="สัดส่วน (%)", yaxis_title="ประเภทธุรกิจ", legend_title_text="ขนาดธุรกิจ")
    return fig_layout(fig, title="สัดส่วน S/M/L ของธุรกิจยอดนิยม", height=max(500, n * 42 + 170), showlegend=True)


def _size_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for size_label, c_col, m_col in [
        ("S", "size_s_count", "size_s_capital_m"),
        ("M", "size_m_count", "size_m_capital_m"),
        ("L", "size_l_count", "size_l_capital_m"),
    ]:
        count = float(df[c_col].sum()) if c_col in df.columns else 0
        capital = float(df[m_col].sum()) if m_col in df.columns else 0
        avg = capital / count if count > 0 else 0
        rows.append({"size": size_label, "count": count, "capital_m": capital, "avg_capital_m": avg})
    return pd.DataFrame(rows)


def capital_box(df: pd.DataFrame, selected_group: str, remove_outliers: bool = False) -> tuple[go.Figure, pd.DataFrame]:
    d = df[(df["avg_capital_m"] > 0) & np.isfinite(df["avg_capital_m"])].copy()
    if selected_group != "ทั้งหมด":
        d = d[d["business_group"] == selected_group].copy()
    if d.empty:
        return go.Figure(), d
    if remove_outliers:
        q1 = d["avg_capital_m"].quantile(0.25)
        q3 = d["avg_capital_m"].quantile(0.75)
        iqr = q3 - q1
        upper = q3 + 1.5 * iqr
        lower = max(0, q1 - 1.5 * iqr)
        d = d[(d["avg_capital_m"] >= lower) & (d["avg_capital_m"] <= upper)].copy()

    d["group_label"] = d["business_group"] if selected_group == "ทั้งหมด" else selected_group
    color_map = GROUP_COLORS if selected_group == "ทั้งหมด" else {selected_group: GROUP_COLORS.get(selected_group, PRIMARY)}

    fig = px.box(
        d,
        x="group_label",
        y="avg_capital_m",
        points="all",
        color="group_label",
        color_discrete_map=color_map,
        hover_name="type",
    )

    # สำคัญ: pointpos=0 ทำให้จุดข้อมูลซ้อนอยู่ “กลางกล่อง” ไม่ถูกดันไปด้านข้าง
    # jitter เล็กน้อยเพื่อไม่ให้จุดทับกัน 100% แต่ยังอยู่บนพื้นที่กล่อง
    fig.update_traces(
        boxpoints="all",
        pointpos=0,
        jitter=0.18,
        width=0.72,  # ทำให้ตัวกล่อง Box Plot กว้างขึ้นในแต่ละกลุ่ม
        marker=dict(size=6.5, opacity=0.78, line=dict(width=0.45, color="rgba(255,255,255,0.45)")),
        line=dict(width=2.4),
        selector=dict(type="box"),
    )

    fig.update_layout(
        xaxis_title="กลุ่มธุรกิจ",
        yaxis_title="ทุนเฉลี่ยต่อราย (ล้านบาท)",
        showlegend=False,
        margin=dict(t=95, l=20, r=20, b=80),
        boxmode="group",
        boxgap=0.18,      # ลดช่องว่างระหว่างกล่อง เพื่อให้กล่องใหญ่ขึ้น
        boxgroupgap=0.08, # ลดช่องว่างภายในกลุ่ม
    )
    title = "การกระจายของทุนเฉลี่ยต่อราย"
    if remove_outliers:
        title += " (ตัด Outliers เพื่อให้อ่านภาพรวมง่ายขึ้น)"
    return fig_layout(fig, title=title, height=720, showlegend=False), d


def capital_scatter(df: pd.DataFrame, selected_group: str) -> go.Figure:
    d = df[(df["avg_capital_m"] > 0) & (df["regis_count"] > 0)].copy()
    if d.empty:
        return go.Figure()
    if selected_group != "ทั้งหมด":
        d["plot_group"] = np.where(d["business_group"] == selected_group, selected_group, "กลุ่มอื่น")
        color_map = {selected_group: GROUP_COLORS.get(selected_group, PRIMARY), "กลุ่มอื่น": "rgba(255,255,255,.25)"}
    else:
        d["plot_group"] = d["business_group"]
        color_map = GROUP_COLORS
    fig = px.scatter(
        d,
        x="regis_count", y="avg_capital_m", color="plot_group", size="closure_rate", size_max=22,
        hover_name="type", color_discrete_map=color_map,
        labels={"regis_count": "จำนวนจัดตั้งใหม่ (ราย)", "avg_capital_m": "ทุนเฉลี่ยต่อราย (ล้านบาท)", "plot_group": "กลุ่มธุรกิจ"},
    )
    fig.update_layout(margin=dict(t=90, l=10, r=10, b=55), legend_title_text="กลุ่มธุรกิจ")
    return fig_layout(fig, title="Scatter Plot: จำนวนจัดตั้งใหม่ vs ทุนเฉลี่ยต่อราย", height=560, showlegend=True)


def size_profile_chart(df: pd.DataFrame, selected_group: str, metric: str = "count") -> tuple[go.Figure, pd.DataFrame]:
    d = df.copy()
    if selected_group != "ทั้งหมด":
        d = d[d["business_group"] == selected_group].copy()
    s = _size_summary_df(d)
    y_col = "count" if metric == "count" else "avg_capital_m"
    y_title = "จำนวนธุรกิจ (ราย)" if metric == "count" else "ทุนเฉลี่ยต่อราย (ล้านบาท)"
    text = s[y_col].map(lambda v: _fmt_int(v) if metric == "count" else _fmt_float(v))
    fig = go.Figure(go.Bar(
        x=s["size"], y=s[y_col], marker=dict(color=[PRIMARY, PINK, ACCENT]), text=text, textposition="outside"
    ))
    fig.update_layout(xaxis_title="ขนาดธุรกิจ", yaxis_title=y_title, showlegend=False, margin=dict(t=90, l=10, r=10, b=50))
    title = "จำนวนธุรกิจตามขนาด" if metric == "count" else "ทุนเฉลี่ยต่อรายตามขนาด"
    return fig_layout(fig, title=title, height=500, showlegend=False), s


def capital_treemap(df: pd.DataFrame, selected_group: str) -> go.Figure:
    d = df.copy()
    d["capital_value"] = np.where(d["capital_for_size_m"] > 0, d["capital_for_size_m"], d["regis_capital_m"])
    if selected_group != "ทั้งหมด":
        d = d[d["business_group"] == selected_group]
    d = d[d["capital_value"] > 0].sort_values("capital_value", ascending=False).head(80)
    if d.empty:
        return go.Figure()
    fig = px.treemap(
        d, path=["business_group", "type"], values="capital_value", color="avg_capital_m",
        color_continuous_scale="Viridis",
        hover_data={"regis_count": ":,.0f", "avg_capital_m": ":,.2f"}
    )
    fig.update_traces(
        textinfo="label+percent parent",
        textfont_size=16,
        hovertemplate="%{label}<br>ทุนรวม: %{value:,.2f} ลบ.<br>ทุนเฉลี่ยต่อราย: %{color:,.2f} ลบ.<extra></extra>"
    )
    fig.update_layout(margin=dict(t=90, l=10, r=10, b=10))
    return fig_layout(fig, title="Treemap สัดส่วนมูลค่าทุน", height=780, showlegend=False)


def _score_to_rgb(score: float) -> list[int]:
    score = max(0.0, min(100.0, float(score)))
    if score >= 80:
        return [34, 197, 94, 230]
    if score >= 65:
        return [132, 204, 22, 225]
    if score >= 50:
        return [250, 204, 21, 220]
    if score >= 35:
        return [249, 115, 22, 225]
    return [239, 68, 68, 230]


def company_province_map_data(raw_map: pd.DataFrame, selected_group: str) -> pd.DataFrame:
    d = raw_map.copy()
    if selected_group != "ทั้งหมด":
        d = d[d["business_group"] == selected_group]
    if d.empty:
        return d
    d["lat"] = d["province"].map(lambda x: PROVINCE_COORDS.get(str(x), (None, None))[0])
    d["lon"] = d["province"].map(lambda x: PROVINCE_COORDS.get(str(x), (None, None))[1])
    d = d.dropna(subset=["lat", "lon"]).copy()
    d["elevation"] = d["micro_score"].clip(lower=5) * 1200
    d["fill_color"] = d["micro_score"].apply(_score_to_rgb)
    d["score_band"] = pd.cut(d["micro_score"], bins=[-1, 35, 50, 65, 80, 100], labels=["เสี่ยงสูง", "เฝ้าระวัง", "กลาง", "ดี", "ดีมาก"])
    d["label_text"] = d["province"] + "\n" + d["micro_score"].round(0).astype(int).astype(str)
    return d


def render_company_province_map(raw_map: pd.DataFrame, selected_group: str):
    d = company_province_map_data(raw_map, selected_group)
    if d.empty:
        st.info("ไม่มีข้อมูลพอสำหรับทำแผนที่รายจังหวัด")
        return d

    # ใช้แผนที่ 2D สีไล่ระดับแทนคอลัมน์ 3D เพื่อให้อ่านง่ายขึ้น
    label_df = pd.concat([
        d.sort_values("micro_score", ascending=False).head(8),
        d.sort_values("micro_score", ascending=True).head(8)
    ]).drop_duplicates(subset=["province"]).copy()

    d["marker_size"] = np.clip(np.sqrt(d["new_count"] + d["closed_count"] + 1) * 4.2, 10, 34)

    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lon=d["lon"],
        lat=d["lat"],
        mode="markers",
        marker=dict(
            size=d["marker_size"],
            color=d["micro_score"],
            colorscale=[
                [0.00, '#ef4444'],
                [0.25, '#f97316'],
                [0.50, '#facc15'],
                [0.75, '#84cc16'],
                [1.00, '#22c55e']
            ],
            cmin=0,
            cmax=100,
            opacity=0.95,
            line=dict(color="#f8fafc", width=0.8),
            colorbar=dict(title="Micro Score", len=0.72, thickness=18),
        ),
        text=d["province"],
        customdata=d[["business_group", "new_count", "closed_count", "closure_rate", "micro_score"]],
        hovertemplate=(
            "%{text}<br>กลุ่ม: %{customdata[0]}<br>จัดตั้ง: %{customdata[1]:,.0f}<br>เลิก: %{customdata[2]:,.0f}"
            "<br>Closure Rate: %{customdata[3]:.2f}%<br>Micro Score: %{customdata[4]:.1f}<extra></extra>"
        ),
    ))
    fig.add_trace(go.Scattergeo(
        lon=label_df["lon"],
        lat=label_df["lat"],
        mode="text",
        text=label_df["province"],
        textfont=dict(size=11, color="#0f172a"),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.update_geos(
        lonaxis_range=[96, 106.5],
        lataxis_range=[5, 21],
        showland=True,
        landcolor="rgba(241,245,249,0.96)",
        showocean=True,
        oceancolor="rgba(191,219,254,0.55)",
        showcountries=True,
        countrycolor="rgba(148,163,184,0.75)",
        showcoastlines=True,
        coastlinecolor="rgba(100,116,139,0.85)",
        projection_type="mercator",
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        title="Micro-Niche Heat Map: สี = คะแนนโอกาสรายจังหวัด · ขนาดจุด = จำนวนกิจกรรมรวม",
        height=700,
        margin=dict(l=10, r=10, t=70, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#f8fafc"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("หมายเหตุ: แผนที่นี้ใช้จุดศูนย์กลางของแต่ละจังหวัดเป็นตัวแทนเชิงพื้นที่ โดยสีเข้มขึ้นหมายถึงคะแนน Micro Opportunity สูงขึ้น")
    return d


def _styled_matcher(df: pd.DataFrame):
    """Return a pandas Styler compatible with both pandas<3 and pandas>=3."""
    def row_style(row):
        if row.name < 3:
            return ['background-color: rgba(34,197,94,0.12);'] * len(row)
        return [''] * len(row)

    styler = df.style.apply(row_style, axis=1)

    # pandas 3 removed Styler.applymap; use Styler.map when available.
    if hasattr(styler, "map"):
        styler = styler.map(lambda _: 'color: #f87171; font-weight: 800;', subset=['type'])
    else:
        styler = styler.applymap(lambda _: 'color: #f87171; font-weight: 800;', subset=['type'])

    return styler.format({
        'avg_capital_m': '{:,.2f}',
        'regis_count': '{:,.0f}',
        'closure_rate': '{:,.2f}',
        'opportunity_score': '{:,.1f}',
    })


# ============================================================
# Page header + data
# ============================================================
page_header(
    "🏷️ Business Category Intelligence",
    "ช่วยผู้ใช้เลือก ‘ประเภทธุรกิจที่น่าทำ’ จากความนิยม การแข่งขัน ความเสี่ยง เงินทุน และความเหมาะสมกับ SME",
    pills=["Market Demand", "Opportunity Map", "Opportunity Score", "SME Fit", "Capital Readiness", "Micro-Niche", "Raw Data"],
)

year = st.sidebar.selectbox("ปีข้อมูล", [2569, 2568], index=0)
raw_df = load_business_metrics(year)
if raw_df.empty:
    st.warning("ยังไม่พบไฟล์ประเภทจัดตั้งเลิกขนาด*.csv ในโฟลเดอร์ data")
    st.stop()

df = _ensure_business_columns(raw_df)
max_regis = int(max(df["regis_count"].max(), 1))

groups = ["ทั้งหมด"] + sorted(df["business_group"].dropna().unique().tolist())

st.sidebar.markdown("### 🔎 ตัวกรองหลัก")
st.sidebar.caption("ใช้กับแท็บ 1) Market Demand · 2) Opportunity Map · 3) Opportunity Score · 4) SME Fit · 5) Capital Readiness · 6) Micro-Niche · 7) Raw Data")
slider_val = st.sidebar.slider("ขั้นต่ำจำนวนจัดตั้งใหม่", 0, max_regis, min(5, max_regis))
min_regis = st.sidebar.number_input("กรอกขั้นต่ำจำนวนจัดตั้งใหม่", min_value=0, max_value=max_regis, value=int(slider_val), step=1)
selected_group = st.sidebar.selectbox("กลุ่มธุรกิจ", groups)

st.sidebar.markdown("---")
st.sidebar.markdown("### 💸 Business Matcher")
st.sidebar.caption("ใช้กับแท็บ 5) Capital Readiness")
budget = st.sidebar.number_input("งบลงทุนโดยประมาณ (ล้านบาท)", min_value=0.0, value=1.50, step=0.5)
risk_tolerance = st.sidebar.selectbox("ระดับความเสี่ยงที่รับได้", ["ต่ำ", "กลาง", "สูง"], index=1)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🧭 ตัวช่วยอ่านหน้า")
st.sidebar.caption("- Opportunity Score ใช้ดูความน่าทำแบบหลายมิติ\n\n- Closure Rate = จำนวนเลิกกิจการ ÷ จำนวนจัดตั้งใหม่ × 100\n\n- S/M/L คือขนาดธุรกิจจากทุนจดทะเบียน\n  • S < 1 ล้านบาท\n  • M = 1–10 ล้านบาท\n  • L > 10 ล้านบาท")

base_view = df[df["regis_count"] >= min_regis].copy()
view = base_view.copy()
if selected_group != "ทั้งหมด":
    view = view[view["business_group"] == selected_group].copy()
if view.empty:
    st.warning("ไม่มีข้อมูลที่ผ่านตัวกรอง ลองลดขั้นต่ำจำนวนจัดตั้งใหม่หรือเลือกกลุ่มธุรกิจอื่น")
    st.stop()

# KPI cards
c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card("Business Types", f"{len(view):,.0f}", "ผ่าน filter")
with c2:
    metric_card("New Registrations", f"{view['regis_count'].sum():,.0f}", "จัดตั้งใหม่รวม")
with c3:
    metric_card("Capital", f"{view['regis_capital_m'].sum():,.0f} ลบ.", "ทุนจัดตั้งรวม")
with c4:
    avg_closure = view["quit_count"].sum() / view["regis_count"].sum() * 100 if view["regis_count"].sum() else 0
    metric_card("Closure Rate", f"{avg_closure:,.2f}%", "weighted")

st.markdown(
    f"""
    <div class='glass-card'>
      <div class='section-eyebrow'>Category note</div>
      {_make_group_note(base_view, selected_group)}<br><br>
      <b>แหล่งข้อมูล:</b> มาจาก DBD ช่วงเดือนมกราคม 2568 ถึง เมษายน 2569
    </div>
    """,
    unsafe_allow_html=True,
)

# Build compare locally
try:
    df69 = _ensure_business_columns(load_business_metrics(2569))
    df68 = _ensure_business_columns(load_business_metrics(2568))
except Exception:
    df69 = pd.DataFrame()
    df68 = pd.DataFrame()
compare = pd.DataFrame()
if not df69.empty and not df68.empty:
    a = df69.copy(); b = df68.copy()
    a["type_key"] = a["type"].apply(_type_key)
    b["type_key"] = b["type"].apply(_type_key)
    compare = pd.merge(a.add_suffix("_69"), b.add_suffix("_68"), left_on="type_key_69", right_on="type_key_68", how="inner")
    if not compare.empty:
        compare["type"] = compare["type_69"]
        compare["regis_growth_pct"] = np.where(compare["regis_count_68"] > 0,
                                                (compare["regis_count_69"] - compare["regis_count_68"]) / compare["regis_count_68"] * 100,
                                                np.where(compare["regis_count_69"] > 0, 100.0, 0.0))
        compare["risk_change"] = compare["closure_rate_69"] - compare["closure_rate_68"]
        compare["business_group_69"] = compare["business_group_69"].fillna(compare.get("business_group_68", "อื่น ๆ"))


tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "1) Market Demand",
    "2) Opportunity Map",
    "3) Opportunity Score",
    "4) SME Fit",
    "5) Capital Readiness",
    "6) Micro-Niche Map",
    "7) Raw Data",
])

# ============================================================
# Tab 1: Market Demand
# ============================================================
with tab1:
    st.markdown("## คำถาม: ธุรกิจประเภทไหนกำลังเป็นที่นิยมและเงินทุนไหลเข้า?")
    st.caption("ข้อมูลจาก DBD ช่วงเดือนมกราคม 2568 ถึง เมษายน 2569 · ใช้จำนวนจัดตั้งใหม่และมูลค่าทุนเพื่อตีความ demand และกระแสเงินทุน")

    st.markdown("### วงกลมสัดส่วนการจัดตั้งใหม่แยกตามกลุ่มธุรกิจ")
    st.caption("วงกลมใหญ่ด้านบน = ภาพรวมทั้ง 10 กลุ่มธุรกิจ ส่วน 10 วงเล็กด้านล่างช่วยให้มองสัดส่วนของแต่ละกลุ่มได้ชัดขึ้น")
    render_group_donut_grid(base_view)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(horizontal_bar(view, "regis_count", "type", "Top 15 ธุรกิจที่จัดตั้งใหม่สูงสุด", "จำนวนจัดตั้งใหม่ (ราย)", n=15, selected_group=selected_group, color_by_group=True), use_container_width=True)
    with col2:
        capital_view = _dedupe_types(view.sort_values("regis_capital_m", ascending=False))
        st.plotly_chart(horizontal_bar(capital_view, "regis_capital_m", "type", "Top 15 ธุรกิจที่มีมูลค่าทุนสูงสุด", "มูลค่าทุนจดทะเบียน (ล้านบาท)", n=15, selected_group=selected_group, color_by_group=True), use_container_width=True)

    top_type = _dedupe_types(view.sort_values("regis_count", ascending=False)).iloc[0]
    top_cap = _dedupe_types(view.sort_values("regis_capital_m", ascending=False)).iloc[0]
    group_share = base_view.groupby("business_group")["regis_count"].sum().sort_values(ascending=False)
    recommended = _dedupe_types(view[view["closure_rate"] <= view["closure_rate"].median()]).sort_values(["opportunity_score", "regis_count"], ascending=[False, False]).head(5)

    st.markdown("<div class='glass-card'><div class='section-eyebrow'>Market Insight</div>", unsafe_allow_html=True)
    st.markdown(f"- ธุรกิจที่จัดตั้งใหม่สูงสุด: **{top_type['type']}** ({_fmt_int(top_type['regis_count'])} ราย)")
    st.markdown(f"- ธุรกิจที่ทุนไหลเข้าสูงสุด: **{top_cap['type']}** ({_fmt_float(top_cap['regis_capital_m'])} ลบ.)")
    st.markdown(f"- กลุ่มธุรกิจที่มีสัดส่วนมากสุดในภาพรวม: **{group_share.index[0]}** คิดเป็น **{group_share.iloc[0] / group_share.sum() * 100:.1f}%** ของการจัดตั้งใหม่ทั้งหมด")
    st.markdown("- ถ้าจำนวนเปิดสูงมาก แปลว่าตลาดมี demand แต่ก็อาจแข่งขันสูง ควรดูต่อที่ Opportunity Map และ Closure Rate")
    st.markdown("- **อุตสาหกรรม/ธุรกิจที่ควรดูต่อ** (เปิดใหม่ดี + ความเสี่ยงไม่สูง):")
    for r in recommended.itertuples():
        st.markdown(f"  - **{r.type}** | จัดตั้งใหม่ {_fmt_int(r.regis_count)} ราย | Closure {_fmt_float(r.closure_rate)}% | Opportunity {_fmt_float(r.opportunity_score,1)}")
    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# Tab 2: Opportunity Map
# ============================================================
with tab2:
    st.markdown("## คำถาม: ธุรกิจไหนเปิดไม่เยอะ แต่เสี่ยงต่ำและน่าต่อยอด?")
    st.caption("แกน X = จำนวนจัดตั้งใหม่ · แกน Y = Closure Rate · ขนาดจุด = มูลค่าทุนจดทะเบียน · ค่ากลางจะคำนวณจากกลุ่มธุรกิจที่เลือก")

    fig_opp, ref_opp, med_x, med_y = opportunity_scatter(base_view, selected_group)
    st.plotly_chart(fig_opp, use_container_width=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("""
        <div class='glass-card'>
        <div class='section-eyebrow'>How to read + สูตร</div>
        <ul class='insight-list'>
          <li><b>ซ้ายล่าง</b>: เปิดไม่เยอะ + เลิกต่ำ = โอกาสเฉพาะทาง / คู่แข่งยังไม่หนาแน่น</li>
          <li><b>ขวาล่าง</b>: เปิดเยอะ + เลิกต่ำ = ตลาดใหญ่และค่อนข้างแข็งแรง</li>
          <li><b>ขวาบน</b>: เปิดเยอะ + เลิกสูง = ตลาดแดง แข่งขันสูง</li>
          <li><b>ซ้ายบน</b>: เปิดน้อย + เลิกสูง = ตลาดเล็กและเสี่ยง</li>
        </ul>
        <b>Closure Rate</b> = จำนวนเลิกกิจการ ÷ จำนวนจัดตั้งใหม่ × 100<br>
        <span style="font-size:.92rem;color:#cbd5e1;">แหล่งข้อมูล: <a href="https://www.dbd.go.th" target="_blank" style="color:#38bdf8;">กรมพัฒนาธุรกิจการค้า (DBD)</a> และสูตรนี้เป็นสูตรคำนวณเชิงเปรียบเทียบที่พัฒนาในแดชบอร์ด เพื่อวัดอัตราเลิกกิจการเทียบกับจำนวนจัดตั้งใหม่ของชุดข้อมูลเดียวกัน</span><br><br>
        <b>Opportunity Score</b> = 0.30×Demand + 0.35×Survival + 0.20×SME Fit + 0.15×Capital − 0.15×Competition<br>
        <span style="font-size:.92rem;color:#cbd5e1;">แหล่งที่มาของสูตร: เป็น Composite Score ที่ออกแบบขึ้นภายในแดชบอร์ดนี้จากตัวแปรที่อ้างอิงข้อมูล DBD เพื่อช่วยจัดลำดับโอกาสทางธุรกิจ ไม่ใช่สูตรทางการจาก DBD โดยตรง</span>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        focus_df = _dedupe_types(ref_opp.copy())
        low_risk = focus_df[(focus_df["closure_rate"] <= med_y) & (focus_df["regis_count"] <= med_x)]
        if low_risk.empty:
            low_risk = focus_df.sort_values("opportunity_score", ascending=False).head(5)
        else:
            low_risk = low_risk.sort_values(["opportunity_score", "regis_count"], ascending=[False, False]).head(5)

        high_risk = focus_df.sort_values(["closure_rate", "regis_count"], ascending=[False, False]).head(5)

        st.markdown("<div class='glass-card'><div class='section-eyebrow'>Selected group summary</div>", unsafe_allow_html=True)
        st.markdown(f"**กลุ่มที่เลือก:** {selected_group}")
        st.markdown(f"- ค่ากลางของกลุ่มที่ใช้แบ่งโซน: จำนวนจัดตั้งใหม่ **{_fmt_int(med_x)}** ราย และ Closure Rate **{_fmt_float(med_y)}%**")
        st.markdown("- วงกลม **🟢** = Opportunity สูง · **🟡** = Opportunity กลาง · **🔴** = Opportunity ต่ำ")
        zero_share = (focus_df["closure_rate"].eq(0).mean() * 100) if len(focus_df) else 0
        if float(focus_df['quit_count'].sum()) == 0:
            st.markdown("- ค่า Closure Rate เป็น 0% เพราะในข้อมูลกลุ่มที่เลือก **ยังไม่พบการเลิกกิจการ** ในช่วงข้อมูลนี้")
        else:
            st.markdown(f"- ธุรกิจที่ Closure Rate = 0% มีประมาณ **{zero_share:.1f}%** ของธุรกิจในกลุ่มที่เลือก ซึ่งหมายถึงในช่วงข้อมูลนี้ยังไม่พบการเลิกกิจการของรายการนั้น")

        st.markdown("**ธุรกิจที่ควรดูต่อ:**")
        for r in low_risk.itertuples():
            st.markdown(f"- {_metric_emoji(r.opportunity_score)} **{r.type}** — Opportunity {_fmt_float(r.opportunity_score, 1)} | Closure {_fmt_float(r.closure_rate)}% | เปิดใหม่ {_fmt_int(r.regis_count)} ราย")

        st.markdown("**ธุรกิจที่ควรระวังในกลุ่มนี้:**")
        for r in high_risk.itertuples():
            st.markdown(f"- 🔴 **{r.type}** — Closure {_fmt_float(r.closure_rate)}% | เปิดใหม่ {_fmt_int(r.regis_count)} ราย")
        st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# Tab 3: Opportunity Score
# ============================================================
with tab3:
    st.markdown("## คำถาม: ธุรกิจไหนน่าทำที่สุดเมื่อรวมหลายปัจจัย?")
    st.caption("แสดงคะแนนรวมแบบหลายมิติ เพื่อดูว่าธุรกิจใดน่าทำที่สุดในมุมมองข้อมูลชุดนี้")

    c1, c2 = st.columns([1.45, 1])
    with c1:
        st.plotly_chart(opportunity_bar(view, selected_group, n=15), use_container_width=True)
    with c2:
        st.markdown(
            """
            <div class='glass-card'>
            <div class='section-eyebrow'>สูตร Opportunity Score</div>
            <b>Opportunity Score =</b><br>
            0.30×Demand Score + 0.35×Survival Score + 0.20×SME Fit Score + 0.15×Capital Score − 0.15×Competition Penalty
            <hr/>
            คะแนนยิ่งสูง แปลว่าธุรกิจนั้นมีภาพรวมด้านโอกาสดีกว่าเมื่อเทียบกับธุรกิจอื่นในข้อมูลชุดเดียวกัน
            </div>
            """,
            unsafe_allow_html=True,
        )
        top_opp = _dedupe_types(view).sort_values("opportunity_score", ascending=False).head(8)
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>Opportunity Summary</div>", unsafe_allow_html=True)
        if not top_opp.empty:
            best = top_opp.iloc[0]
            st.markdown(f"- ธุรกิจเด่นสุดคือ **{best['type']}** ด้วยคะแนน **{_fmt_float(best['opportunity_score'],1)}**")
            st.markdown(f"- จุดร่วมของธุรกิจคะแนนสูง: Closure Rate ต่ำ, เปิดใหม่พอสมควร, SME เข้าได้ และทุนไม่หนักเกินไป")
            st.markdown("- ถ้าคะแนนใกล้กัน ให้ดู **Closure Rate** และ **ทุนเฉลี่ยต่อราย** เพิ่มเพื่อคัดเลือกต่อ")
        st.markdown("</div>", unsafe_allow_html=True)

    st.dataframe(
        _dedupe_types(view)[["type", "business_group", "regis_count", "closure_rate", "sme_share", "avg_capital_m", "opportunity_score"]]
        .sort_values("opportunity_score", ascending=False)
        .head(15),
        use_container_width=True, hide_index=True
    )

# ============================================================
# Tab 4: SME Fit
# ============================================================
with tab4:
    st.markdown("## คำถาม: ธุรกิจไหนเหมาะกับ SME / คนทุนน้อย?")
    st.caption("S/M/L คือขนาดธุรกิจตามทุนจดทะเบียนในไฟล์ DBD: S = ขนาดเล็ก, M = ขนาดกลาง, L = ขนาดใหญ่")
    st.plotly_chart(sme_stacked_bar(view, n=12), use_container_width=True)
    st.info("ถ้าแถบ S มีสัดส่วนสูง แปลว่าธุรกิจนั้นมีผู้เล่นรายเล็กจำนวนมาก อาจเหมาะกับผู้เริ่มต้นมากกว่าธุรกิจที่ L ครองตลาด")

    sme = view[(view["sme_share"] >= 70) & (view["regis_count"] >= min_regis)].sort_values("opportunity_score", ascending=False)
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>SME summary</div>", unsafe_allow_html=True)
        if not sme.empty:
            best = sme.iloc[0]
            st.markdown(f"ธุรกิจที่เหมาะกับ SME เด่นสุดในตัวกรองนี้คือ **{best['type']}** เพราะมี SME Share **{_fmt_float(best['sme_share'])}%** และ Opportunity Score **{_fmt_float(best['opportunity_score'], 1)}**")
        else:
            st.markdown("ยังไม่มีธุรกิจที่ผ่านเงื่อนไข SME Share ≥ 70% หลังกรองข้อมูล")
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        feature_df = pd.DataFrame([
            ["size_s_count", "จำนวนธุรกิจขนาด S"],
            ["size_m_count", "จำนวนธุรกิจขนาด M"],
            ["size_l_count", "จำนวนธุรกิจขนาด L"],
            ["sme_share", "สัดส่วนธุรกิจขนาด S ต่อจำนวน S+M+L"],
            ["closure_rate", "อัตราเลิกกิจการ เทียบกับจำนวนจัดตั้งใหม่"],
        ], columns=["Feature", "Meaning"])
        st.dataframe(feature_df, use_container_width=True, hide_index=True)
    st.dataframe(sme[["type", "business_group", "regis_count", "sme_share", "closure_rate", "opportunity_score"]].head(25), use_container_width=True, hide_index=True)

# ============================================================
# Tab 5: Capital Readiness
# ============================================================
with tab5:
    st.markdown("## คำถาม: ถ้าจะเข้าวงการนี้ ต้องเตรียมเงินทุนประมาณเท่าไร และธุรกิจไซส์ไหนครองตลาด?")
    st.caption("ข้อมูลจาก DBD ช่วงมกราคม 2568 ถึง เมษายน 2569 · ใช้ดู distribution ของทุนเฉลี่ยต่อราย, outliers, ขนาดธุรกิจ และตัวช่วย Business Matcher")

    # 1) Box plot overview
    box_full, box_data = capital_box(base_view, selected_group, remove_outliers=False)
    box_trim, trim_data = capital_box(base_view, selected_group, remove_outliers=True)
    scatter_fig = capital_scatter(base_view, selected_group)

    st.markdown("### 1) Box Plot: ทุนเฉลี่ยต่อราย")
    st.plotly_chart(box_full, use_container_width=True)
    with st.container():
        sum1, sum2 = st.columns(2)
        with sum1:
            if not box_data.empty:
                med = box_data["avg_capital_m"].median()
                q3 = box_data["avg_capital_m"].quantile(0.75)
                st.markdown("<div class='glass-card'><div class='section-eyebrow'>Box Plot Summary</div>", unsafe_allow_html=True)
                st.markdown(f"- ค่ากลางทุนเฉลี่ยต่อรายของกลุ่มที่เลือก ≈ **{_fmt_float(med)} ล้านบาท**")
                st.markdown(f"- 75% ของธุรกิจมีทุนเฉลี่ยไม่เกินประมาณ **{_fmt_float(q3)} ล้านบาท/ราย**")
                st.markdown("- กล่องสูง/กว้างมาก แปลว่ากลุ่มนั้นมีความหลากหลายของทุนต่อรายสูง")
                st.markdown("</div>", unsafe_allow_html=True)
        with sum2:
            if not box_data.empty:
                q1 = box_data["avg_capital_m"].quantile(0.25)
                q3 = box_data["avg_capital_m"].quantile(0.75)
                iqr = q3 - q1
                upper = q3 + 1.5 * iqr
                lower = max(0, q1 - 1.5 * iqr)
                outliers = box_data[(box_data["avg_capital_m"] > upper) | (box_data["avg_capital_m"] < lower)].sort_values("avg_capital_m", ascending=False)
                st.markdown("<div class='glass-card'><div class='section-eyebrow'>Outliers Example</div>", unsafe_allow_html=True)
                if outliers.empty:
                    st.markdown("- ในตัวกรองนี้ยังไม่พบ outlier ที่เด่นชัด จึงสามารถอ่านกราฟหลักได้โดยตรง")
                else:
                    st.markdown(f"- มี outliers ประมาณ **{len(outliers)} รายการ** เช่น:")
                    for r in outliers.head(10).itertuples():
                        st.markdown(f"  - **{r.type}** — ทุนเฉลี่ยต่อราย {_fmt_float(r.avg_capital_m)} ล้านบาท")
                st.markdown("</div>", unsafe_allow_html=True)

    # 2) Trimmed box plot only when useful
    st.markdown("### 2) Box Plot แบบตัด Outliers")
    if not box_data.empty and len(trim_data) < len(box_data):
        st.plotly_chart(box_trim, use_container_width=True)
        st.caption("กราฟนี้ตัด outliers ด้วยเกณฑ์ IQR เฉพาะเมื่อมีค่าที่โดดมาก เพื่อให้อ่านการกระจายหลักได้ง่ายขึ้น")
    else:
        st.info("ในชุดข้อมูลที่กรองอยู่ กราฟหลักยังอ่านได้ชัด จึงไม่จำเป็นต้องตัด outliers เพิ่ม")

    # 3) Scatter + summary
    st.markdown("### 3) Scatter Plot: จำนวนจัดตั้งใหม่ vs ทุนเฉลี่ยต่อราย")
    st.plotly_chart(scatter_fig, use_container_width=True)
    st.markdown("<div class='glass-card'><div class='section-eyebrow'>Scatter Summary</div>", unsafe_allow_html=True)
    st.markdown("- จุดที่อยู่ **ขวาบน** คือธุรกิจที่ทั้งเปิดใหม่มากและใช้ทุนต่อรายสูง เหมาะกับผู้เล่นที่มีงบและรับการแข่งขันได้")
    st.markdown("- จุดที่อยู่ **ซ้ายล่าง** คือธุรกิจที่เปิดใหม่ไม่มากและใช้ทุนต่ำกว่า เหมาะสำหรับใช้เป็นตลาดเฉพาะทางหรือจุดเริ่มต้น")
    st.markdown("</div>", unsafe_allow_html=True)

    # 4) Size profile in one row
    st.markdown("### 4) โครงสร้างธุรกิจตามขนาด S/M/L")
    size_count_fig, size_summary = size_profile_chart(base_view, selected_group, metric="count")
    size_avg_fig, _ = size_profile_chart(base_view, selected_group, metric="avg_capital_m")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(size_count_fig, use_container_width=True)
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>อธิบายกราฟ: จำนวนธุรกิจตามขนาด</div>ถ้าแท่ง S สูงมาก แปลว่าตลาดมีผู้เล่นรายเล็กจำนวนมาก หากแท่ง L สูง แปลว่าตลาดมีผู้เล่นทุนใหญ่ค่อนข้างมาก</div>", unsafe_allow_html=True)
    with c2:
        st.plotly_chart(size_avg_fig, use_container_width=True)
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>อธิบายกราฟ: ทุนเฉลี่ยต่อราย</div>ช่วยดูว่าขนาดธุรกิจใดต้องใช้ทุนต่อรายมากที่สุด เพื่อประเมินความพร้อมด้านการเงินก่อนเริ่มธุรกิจ</div>", unsafe_allow_html=True)

    if not size_summary.empty:
        top_size_count = size_summary.sort_values("count", ascending=False).iloc[0]
        top_size_avg = size_summary.sort_values("avg_capital_m", ascending=False).iloc[0]
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>Size Summary</div>", unsafe_allow_html=True)
        st.markdown(f"- ขนาดที่มีจำนวนธุรกิจมากสุด: **{top_size_count['size']}** ({_fmt_int(top_size_count['count'])} ราย)")
        st.markdown(f"- ขนาดที่มีทุนเฉลี่ยต่อรายสูงสุด: **{top_size_avg['size']}** ({_fmt_float(top_size_avg['avg_capital_m'])} ล้านบาท/ราย)")
        st.markdown("- ช่วงมูลค่าทุนที่ใช้ตีความจากข้อมูลหน้าแอป: **S < 1 ล้านบาท · M = 1–10 ล้านบาท · L > 10 ล้านบาท**")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 5) Treemap สัดส่วนมูลค่าทุน")
    st.plotly_chart(capital_treemap(view, selected_group), use_container_width=True)
    if not view.empty:
        capital_rank = view.assign(capital_value=np.where(view["capital_for_size_m"] > 0, view["capital_for_size_m"], view["regis_capital_m"]))
        capital_rank = _dedupe_types(capital_rank.sort_values("capital_value", ascending=False)).head(5)
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>Treemap Summary</div>", unsafe_allow_html=True)
        st.markdown("ธุรกิจที่กินสัดส่วนทุนเด่นที่สุดในกลุ่มที่เลือก:")
        for r in capital_rank.itertuples():
            st.markdown(f"- **{r.type}** — ทุนรวม {_fmt_float(r.capital_value)} ล้านบาท | ทุนเฉลี่ยต่อราย {_fmt_float(r.avg_capital_m)} ล้านบาท")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 6) Business Matcher: ธุรกิจที่เข้ากับงบและความเสี่ยง")
    st.caption("ใช้กับตัวกรองฝั่งซ้าย: งบลงทุนโดยประมาณ + ระดับความเสี่ยงที่รับได้")
    st.markdown(
        """
        <div class='glass-card'>
        <div class='section-eyebrow'>คำอธิบายฟีเจอร์</div>
        <ul class='insight-list'>
          <li><b>avg_capital_m</b> = ทุนเฉลี่ยต่อราย</li>
          <li><b>regis_count</b> = จำนวนจัดตั้งใหม่</li>
          <li><b>closure_rate</b> = อัตราเลิกกิจการ</li>
          <li><b>opportunity_score</b> = คะแนนโอกาสเชิงรวม</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    threshold = {"ต่ำ": 10, "กลาง": 25, "สูง": 100}.get(risk_tolerance, 25)
    matcher = view[(view["avg_capital_m"] <= budget) & (view["closure_rate"] <= threshold) & (view["regis_count"] >= min_regis)].copy()
    matcher = _dedupe_types(matcher).sort_values(["opportunity_score", "regis_count"], ascending=[False, False]).head(12)
    if matcher.empty:
        st.warning("ยังไม่พบธุรกิจที่เข้าเงื่อนไขงบ/ความเสี่ยง ลองเพิ่มงบหรือลดระดับความเข้มของตัวกรอง")
    else:
        st.dataframe(_styled_matcher(matcher[["type", "business_group", "avg_capital_m", "regis_count", "closure_rate", "opportunity_score"]]), use_container_width=True, hide_index=True)
        best = matcher.iloc[0]
        st.success(f"คำแนะนำเบื้องต้น: ถ้ามีงบประมาณ {_fmt_float(budget)} ล้านบาท ธุรกิจที่ควรดูต่อคือ **{best['type']}** เพราะทุนเฉลี่ย {_fmt_float(best['avg_capital_m'])} ลบ./ราย และ Closure Rate {_fmt_float(best['closure_rate'])}%")

# ============================================================
# Tab 6: Micro-Niche Map
# ============================================================
with tab6:
    st.markdown("## คำถาม: พื้นที่ไหนอาจเป็น Micro-Niche สำหรับกลุ่มธุรกิจที่เลือก?")
    st.caption(f"ข้อมูลจากไฟล์: {_source_file_names('รายชื่อจัดตั้ง', year=2569)} | {_source_file_names('เลิก', year=2569)}")
    raw_map = load_company_province_group(2569)
    if raw_map.empty:
        st.warning("ยังไม่พบ/อ่านไฟล์รายชื่อจัดตั้ง69 หรือ เลิก69 ไม่ได้ จึงยังสร้าง Micro-Niche Map ไม่ได้")
        with st.expander("Debug: ชื่อไฟล์ที่ระบบเห็น"):
            st.write([f.name for f in _all_data_files()])
    else:
        rendered = render_company_province_map(raw_map, selected_group)
        if isinstance(rendered, pd.DataFrame) and not rendered.empty:
            top_green = rendered.sort_values("micro_score", ascending=False).head(5)
            top_red = rendered.sort_values("micro_score", ascending=True).head(5)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("<div class='glass-card'><div class='section-eyebrow'>จังหวัดสีเขียว (Opportunity สูง)</div>", unsafe_allow_html=True)
                for r in top_green.itertuples():
                    st.markdown(f"- **{r.province}** — Micro Score {_fmt_float(r.micro_score,1)} | จัดตั้ง {int(r.new_count)} | เลิก {int(r.closed_count)}")
                st.markdown("</div>", unsafe_allow_html=True)
            with c2:
                st.markdown("<div class='glass-card'><div class='section-eyebrow'>จังหวัดสีแดง (ควรระวัง)</div>", unsafe_allow_html=True)
                for r in top_red.itertuples():
                    st.markdown(f"- **{r.province}** — Micro Score {_fmt_float(r.micro_score,1)} | จัดตั้ง {int(r.new_count)} | เลิก {int(r.closed_count)}")
                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown(
                """
                <div class='glass-card'>
                    <div class='section-eyebrow'>Micro-Niche Summary</div>
                    <ul class='insight-list'>
                        <li><b>กราฟนี้คือแผนที่โอกาสรายจังหวัด</b> จุดแต่ละจุดแทนจังหวัด โดยใช้ตำแหน่งกลางจังหวัดเพื่อให้เห็นภาพรวมเชิงพื้นที่</li>
                        <li><b>สีของจุด</b>: เขียว = Micro Opportunity สูงกว่า, เหลือง/ส้ม = ควรตรวจเพิ่ม, แดง = ความเสี่ยงหรือแรงกดดันสูงกว่าในกลุ่มที่เลือก</li>
                        <li><b>ขนาดจุด</b>: ยิ่งใหญ่ แปลว่ามีจำนวนกิจกรรมธุรกิจรวมมากขึ้น เช่น จัดตั้งใหม่ + เลิกกิจการ จึงเป็นพื้นที่ที่ตลาดเคลื่อนไหวมาก</li>
                        <li><b>วิธีใช้จริง</b>: อย่าเลือกจากสีเขียวอย่างเดียว ให้เลือกจังหวัดสีเขียวที่มีจำนวนจัดตั้งใหม่พอสมควร และจำนวนเลิกกิจการไม่สูงผิดปกติ</li>
                        <li><b>สิ่งที่ผู้ใช้ควรทำต่อ</b>: เลือก 2–3 จังหวัดจากกล่อง “จังหวัดสีเขียว” แล้วไปดูต่อที่หน้า Province เพื่อดู Net Growth / Closure Rate และหน้า Survival เพื่อเช็กความเสี่ยงก่อนตัดสินใจ</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )

# ============================================================
# Tab 7: Raw Data
# ============================================================
with tab7:
    st.markdown("## Raw Data / Feature Dictionary")
    feature_df = pd.DataFrame([
        ["type", "ชื่อประเภทธุรกิจ / TSIC description"],
        ["business_group", "กลุ่มธุรกิจที่ระบบจัดหมวดจากชื่อประเภทธุรกิจ"],
        ["regis_count", "จำนวนจัดตั้งใหม่"],
        ["regis_capital_m", "มูลค่าทุนจดทะเบียนของธุรกิจจัดตั้งใหม่ (ล้านบาท)"],
        ["quit_count", "จำนวนเลิกกิจการ"],
        ["closure_rate", "อัตราเลิกกิจการ = quit_count / regis_count × 100"],
        ["avg_capital_m", "ทุนเฉลี่ยต่อราย = regis_capital_m / regis_count"],
        ["sme_share", "สัดส่วนธุรกิจขนาด S ต่อ S+M+L"],
        ["opportunity_score", "คะแนนโอกาสรวมจาก Demand, Survival, SME Fit, Capital และ Competition"],
        ["risk_change", "ความเปลี่ยนแปลงของ Closure Rate จากปี 2568 เป็น 2569"],
    ], columns=["Feature", "Meaning"])
    st.dataframe(feature_df, use_container_width=True, hide_index=True)
    st.markdown(
        """
        <div class='glass-card'>
        <div class='section-eyebrow'>อธิบายฟีเจอร์เพิ่มเติม</div>
        <b>S / M / L ตามข้อมูลหน้าแอป</b><br>
        - <b>S</b> = ทุนจดทะเบียนต่ำกว่า 1 ล้านบาท<br>
        - <b>M</b> = ทุนจดทะเบียน 1–10 ล้านบาท<br>
        - <b>L</b> = ทุนจดทะเบียนมากกว่า 10 ล้านบาท
        </div>
        """, unsafe_allow_html=True
    )
    st.markdown("<div class='glass-card'><div class='section-eyebrow'>Summary</div>ตารางด้านล่างคือข้อมูลหลังผ่านตัวกรองที่ผู้ใช้เลือก สามารถใช้ตรวจสอบว่าธุรกิจแต่ละประเภทมีจำนวนจัดตั้งใหม่ ความเสี่ยง และคะแนนโอกาสอย่างไร</div>", unsafe_allow_html=True)

    st.markdown("### ตารางข้อมูลหลังผ่านตัวกรอง")
    show_cols = ["type", "business_group", "regis_count", "regis_capital_m", "quit_count", "closure_rate", "avg_capital_m", "sme_share", "opportunity_score"]
    st.dataframe(_dedupe_types(view[[c for c in show_cols if c in view.columns]]).sort_values("opportunity_score", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("### Growth 2568 → 2569")
    st.caption(f"ข้อมูลจากไฟล์: 2569 = {_source_file_names('regis', year=2569)} | 2568 = {_source_file_names('regis', year=2568)}")
    if compare.empty:
        st.info("ยังไม่มีข้อมูล 2568/2569 ครบพอสำหรับเปรียบเทียบ YoY")
    else:
        comp = compare.copy()
        if selected_group != "ทั้งหมด" and "business_group_69" in comp.columns:
            comp = comp[comp["business_group_69"] == selected_group]
        comp = comp[(comp["regis_count_69"] >= min_regis) | (comp["regis_count_68"] >= min_regis)].copy()
        comp = _dedupe_types(comp.rename(columns={"type": "type"}))
        if comp.empty:
            st.info("ไม่มีข้อมูลที่ผ่านตัวกรองสำหรับ YoY")
        else:
            top_pos = comp.sort_values("regis_growth_pct", ascending=False).head(10)
            top_neg = comp.sort_values("regis_growth_pct", ascending=True).head(10)
            plot_df = pd.concat([top_pos, top_neg], ignore_index=True).drop_duplicates(subset=["type"])
            plot_df = plot_df.sort_values("regis_growth_pct")
            fig = go.Figure(go.Bar(
                x=plot_df["regis_growth_pct"],
                y=plot_df["type"].apply(lambda x: x if len(str(x)) <= 40 else str(x)[:40] + "…"),
                orientation="h",
                marker=dict(color=np.where(plot_df["regis_growth_pct"] >= 0, GREEN, RED)),
                text=[f"{v:.1f}%" for v in plot_df["regis_growth_pct"]],
                textposition="outside",
            ))
            fig.update_layout(xaxis_title="อัตราเติบโตของจำนวนจัดตั้งใหม่ (%)", yaxis_title="ประเภทธุรกิจ", margin=dict(t=95, l=20, r=30, b=55))
            st.plotly_chart(fig_layout(fig, "ธุรกิจที่เติบโต / หดตัวจากปี 2568 เป็น 2569", height=760, showlegend=False), use_container_width=True)

            pos_cnt = int((comp["regis_growth_pct"] > 0).sum())
            neg_cnt = int((comp["regis_growth_pct"] < 0).sum())
            best_val = comp["regis_growth_pct"].max()
            worst_val = comp["regis_growth_pct"].min()
            best_rows = comp[comp["regis_growth_pct"] == best_val]
            worst_rows = comp[comp["regis_growth_pct"] == worst_val]
            st.markdown("<div class='glass-card'><div class='section-eyebrow'>Growth Summary</div>", unsafe_allow_html=True)
            st.markdown(f"- ธุรกิจที่เติบโตเป็นบวกมี **{pos_cnt} ประเภท** และธุรกิจที่หดตัวมี **{neg_cnt} ประเภท**")
            st.markdown(f"- ตัวเด่นสุด ({_fmt_float(best_val)}%): " + " / ".join([f"**{t}**" for t in best_rows['type'].head(5)]))
            st.markdown(f"- ตัวที่ควรระวัง ({_fmt_float(worst_val)}%): " + " / ".join([f"**{t}**" for t in worst_rows['type'].head(5)]))
            st.markdown("- แท่งสีเขียว = เติบโตเพิ่มขึ้นจากปี 2568 → 2569, แท่งสีแดง = เติบโตติดลบหรือหดตัว")
            st.markdown("</div>", unsafe_allow_html=True)

            display_cols = ["type", "regis_count_69", "regis_count_68", "regis_growth_pct", "risk_change"]
            st.markdown("### ตารางเปรียบเทียบ YoY")
            st.dataframe(comp[display_cols].sort_values(["regis_growth_pct", "type"], ascending=[False, True]), use_container_width=True, hide_index=True)
            st.markdown("<div class='glass-card'><div class='section-eyebrow'>คำอธิบายฟีเจอร์เพิ่ม</div><b>regis_growth_pct</b> = อัตราเติบโตของจำนวนจัดตั้งใหม่เทียบปีก่อน<br><b>risk_change</b> = ความเปลี่ยนแปลงของอัตราเลิกกิจการ ถ้าเป็นค่าบวกแปลว่าความเสี่ยงเพิ่มขึ้น</div>", unsafe_allow_html=True)
