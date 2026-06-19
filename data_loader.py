from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from functools import reduce
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

DATA_DIR = Path(r"C:\Users\acer\Downloads\thaibiz_streamlit_app\data")

MONTH_ORDER = {
    "มค": 1, "ม.ค": 1, "มกราคม": 1, "jan": 1,
    "กพ": 2, "ก.พ": 2, "กุมภาพันธ์": 2, "feb": 2,
    "มีค": 3, "มี.ค": 3, "มีนาคม": 3, "mar": 3,
    "เมย": 4, "เม.ย": 4, "เมษายน": 4, "apr": 4,
    "พค": 5, "พ.ค": 5, "พฤษภาคม": 5, "may": 5,
    "มิย": 6, "มิ.ย": 6, "มิถุนายน": 6, "jun": 6,
    "กค": 7, "ก.ค": 7, "กรกฎาคม": 7, "jul": 7,
    "สค": 8, "ส.ค": 8, "สิงหาคม": 8, "aug": 8,
    "กย": 9, "ก.ย": 9, "กันยายน": 9, "sep": 9,
    "ตค": 10, "ต.ค": 10, "ตุลาคม": 10, "oct": 10,
    "พย": 11, "พ.ย": 11, "พฤศจิกายน": 11, "nov": 11,
    "ธค": 12, "ธ.ค": 12, "ธันวาคม": 12, "dec": 12,
}
MONTH_LABEL = {1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.", 5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.", 9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."}

COMPARE_COLUMNS = ["type", "regis_count_69", "regis_count_68", "closure_rate_69", "closure_rate_68", "risk_change", "regis_growth_pct", "net_growth_change"]

PROVINCE_RENAME = {"กทม.": "กรุงเทพมหานคร", "กรุงเทพฯ": "กรุงเทพมหานคร", "กรุงเทพ": "กรุงเทพมหานคร"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s))
    s = s.replace("ประเเภท", "ประเภท")
    s = s.replace("เเ", "แ")
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _clean_name(s: str) -> str:
    return str(s).replace("\ufeff", "").strip()


def _read_csv_auto(path: Path) -> pd.DataFrame:
    last_err = None
    for enc in ["utf-8-sig", "utf-8", "cp874", "tis-620"]:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = [_clean_name(c) for c in df.columns]
            return df
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Cannot read CSV: {path.name}: {last_err}")


def _to_num(s):
    return pd.to_numeric(pd.Series(s).astype(str).str.replace(",", "", regex=False).str.replace("-", "0", regex=False), errors="coerce").fillna(0)


def data_files() -> List[Path]:
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(DATA_DIR.glob("*.csv"))


def find_files(*keywords: str) -> List[Path]:
    keys = [_norm(k) for k in keywords]
    out = []
    for f in data_files():
        n = _norm(f.name)
        if all(k in n for k in keys):
            out.append(f)
    return out


def _extract_year(name: str) -> Optional[int]:
    m = re.search(r"(\d{2})", name)
    if not m:
        return None
    yy = int(m.group(1))
    return 2500 + yy


def _extract_month_from_name(name: str) -> tuple[int, str]:
    n = Path(name).stem.lower()
    # likely suffix after underscore e.g. จังหวัดจัดตั้งเลิกเพิ่มคง68_กค.csv
    parts = re.split(r"[_\-]", n)
    for p in reversed(parts):
        p2 = p.replace(".", "").strip()
        if p2 in MONTH_ORDER:
            no = MONTH_ORDER[p2]
            return no, MONTH_LABEL[no]
    for k, v in MONTH_ORDER.items():
        if k in n:
            return v, MONTH_LABEL[v]
    return 0, "ไม่ระบุเดือน"


@st.cache_data(show_spinner=False)
def load_province_monthly() -> pd.DataFrame:
    files = find_files("จังหวัด", "จัดตั้ง", "เลิก", "เพิ่ม", "คง")
    frames = []
    for f in files:
        df = _read_csv_auto(f)
        # Expected CSV schema: place, esta, esta_m, quit, quit_m, add_fund, add_fund_m, active, active_m
        rename = {
            "place": "province", "จังหวัด": "province",
            "esta": "new_count", "จัดตั้ง": "new_count",
            "esta_m": "new_capital_m", "ทุนจัดตั้ง": "new_capital_m",
            "quit": "closed_count", "เลิก": "closed_count",
            "quit_m": "closed_capital_m", "ทุนเลิก": "closed_capital_m",
            "add_fund": "add_fund_count", "เพิ่มทุน": "add_fund_count",
            "add_fund_m": "add_fund_capital_m", "ทุนเพิ่ม": "add_fund_capital_m",
            "active": "active_count", "คงอยู่": "active_count",
            "active_m": "active_capital_m", "ทุนคงอยู่": "active_capital_m",
        }
        df = df.rename(columns={c: rename.get(c, c) for c in df.columns})
        if "province" not in df.columns:
            continue
        year = _extract_year(f.name)
        month_no, month_label = _extract_month_from_name(f.name)
        df["source_file"] = f.name
        df["year"] = year
        df["month_no"] = month_no
        df["month"] = month_label
        for c in ["new_count", "new_capital_m", "closed_count", "closed_capital_m", "add_fund_count", "add_fund_capital_m", "active_count", "active_capital_m"]:
            if c not in df.columns:
                df[c] = 0
            df[c] = _to_num(df[c])
        df["province"] = df["province"].astype(str).str.strip().replace(PROVINCE_RENAME)
        df = df[~df["province"].str.contains("รวม|ทั่วประเทศ|ภาค|nan", case=False, na=False)]
        df["net_growth"] = df["new_count"] - df["closed_count"]
        df["closure_rate"] = np.where(df["new_count"] > 0, df["closed_count"] / df["new_count"] * 100, 0)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["province", "year", "month_no", "month", "new_count", "closed_count", "net_growth", "closure_rate"])
    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["year", "month_no", "province"], na_position="last")
    return out


def _pick_file(year: int, kind: str) -> Optional[Path]:
    # kind: regis / quit / active / size
    yy = str(year)[-2:]
    candidates = []
    for f in data_files():
        n = _norm(f.name)
        if "ประเภท" not in n:
            continue
        if yy not in n:
            continue
        if kind == "active" and "active" in n:
            candidates.append(f)
        elif kind == "regis" and "regis" in n:
            candidates.append(f)
        elif kind == "quit" and "quit" in n:
            candidates.append(f)
        elif kind == "size" and "size" in n:
            candidates.append(f)
    return sorted(candidates)[0] if candidates else None


def _read_type_file(path: Optional[Path], kind: str) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame({"type": []})
    df = _read_csv_auto(path)
    if "type" not in df.columns:
        first = df.columns[0]
        df = df.rename(columns={first: "type"})
    df["type"] = df["type"].astype(str).str.strip()
    df = df[~df["type"].isin(["", "nan", "None"])]
    if kind == "regis":
        if "total_regis" in df.columns:
            out = df[["type", "total_regis", "total_m"]].copy()
            out = out.rename(columns={"total_regis": "regis_count", "total_m": "regis_capital_m"})
        elif {"p", "m"}.issubset(df.columns):
            out = df[["type", "p", "m"]].copy().rename(columns={"p": "regis_count", "m": "regis_capital_m"})
        else:
            out = pd.DataFrame({"type": df["type"], "regis_count": 0, "regis_capital_m": 0})
    elif kind == "quit":
        if "total_quit" in df.columns:
            out = df[["type", "total_quit", "total_m"]].copy()
            out = out.rename(columns={"total_quit": "quit_count", "total_m": "quit_capital_m"})
        elif {"p", "m"}.issubset(df.columns):
            out = df[["type", "p", "m"]].copy().rename(columns={"p": "quit_count", "m": "quit_capital_m"})
        else:
            out = pd.DataFrame({"type": df["type"], "quit_count": 0, "quit_capital_m": 0})
    elif kind == "active":
        if {"p", "m"}.issubset(df.columns):
            out = df[["type", "p", "m"]].copy().rename(columns={"p": "active_count", "m": "active_capital_m"})
        else:
            out = pd.DataFrame({"type": df["type"], "active_count": 0, "active_capital_m": 0})
    elif kind == "size":
        cols = ["type", "p_s", "p_m", "p_l", "p_total", "m_s", "m_m", "m_l", "m_total"]
        for c in cols:
            if c not in df.columns:
                df[c] = 0
        out = df[cols].copy().rename(columns={
            "p_s": "size_s_count", "p_m": "size_m_count", "p_l": "size_l_count", "p_total": "size_total_count",
            "m_s": "size_s_capital_m", "m_m": "size_m_capital_m", "m_l": "size_l_capital_m", "m_total": "size_total_capital_m",
        })
    else:
        out = pd.DataFrame({"type": df["type"]})
    for c in out.columns:
        if c != "type":
            out[c] = _to_num(out[c])
    return out


def _business_group(t: str) -> str:
    s = str(t)
    if any(k in s for k in ["ขาย", "ค้าปลีก", "ค้าส่ง", "ตลาด"]):
        return "ขายส่ง/ขายปลีก"
    if any(k in s for k in ["ผลิต", "โรงงาน", "แปรรูป", "อุตสาหกรรม"]):
        return "ผลิต"
    if any(k in s for k in ["ก่อสร้าง", "อสังหาริมทรัพย์", "อาคาร"]):
        return "ก่อสร้าง/อสังหาฯ"
    if any(k in s for k in ["อาหาร", "ภัตตาคาร", "ร้านอาหาร", "เครื่องดื่ม"]):
        return "อาหาร/เครื่องดื่ม"
    if any(k in s for k in ["ขนส่ง", "คลังสินค้า", "โลจิสติกส์"]):
        return "ขนส่ง/โลจิสติกส์"
    if any(k in s for k in ["ซอฟต์แวร์", "คอมพิวเตอร์", "ข้อมูล", "เทคโนโลยี"]):
        return "เทคโนโลยี"
    if any(k in s for k in ["การศึกษา", "สุขภาพ", "แพทย์", "โรงพยาบาล"]):
        return "สุขภาพ/การศึกษา"
    if any(k in s for k in ["บริการ", "ให้เช่า", "ซ่อม", "ที่ปรึกษา"]):
        return "บริการ"
    if any(k in s for k in ["ปลูก", "เลี้ยง", "ประมง", "เกษตร"]):
        return "เกษตร"
    return "อื่น ๆ"


def _normalize_score(series: pd.Series, inverse: bool = False) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    if s.max() == s.min():
        out = pd.Series(50, index=s.index)
    else:
        out = (s - s.min()) / (s.max() - s.min()) * 100
    return 100 - out if inverse else out


@st.cache_data(show_spinner=False)
def load_business_metrics(year: int = 2569) -> pd.DataFrame:
    regis = _read_type_file(_pick_file(year, "regis"), "regis")
    quit_ = _read_type_file(_pick_file(year, "quit"), "quit")
    active = _read_type_file(_pick_file(year, "active"), "active")
    size = _read_type_file(_pick_file(year, "size"), "size")
    dfs = [d for d in [regis, quit_, active, size] if not d.empty]
    if not dfs:
        return pd.DataFrame(columns=["type", "year", "regis_count", "quit_count", "closure_rate"])
    df = reduce(lambda left, right: pd.merge(left, right, on="type", how="outer"), dfs)
    df = df.fillna(0)
    df["year"] = year
    for c in [
        "regis_count", "regis_capital_m", "quit_count", "quit_capital_m", "active_count", "active_capital_m",
        "size_s_count", "size_m_count", "size_l_count", "size_total_count", "size_s_capital_m", "size_m_capital_m", "size_l_capital_m", "size_total_capital_m",
    ]:
        if c not in df.columns:
            df[c] = 0
        df[c] = _to_num(df[c])
    df["net_growth"] = df["regis_count"] - df["quit_count"]
    df["closure_rate"] = np.where(df["regis_count"] > 0, df["quit_count"] / df["regis_count"] * 100, 0)
    df["survival_proxy"] = np.where(df["active_count"] + df["quit_count"] > 0, df["active_count"] / (df["active_count"] + df["quit_count"]) * 100, 0)
    df["avg_capital_m"] = np.where(df["regis_count"] > 0, df["regis_capital_m"] / df["regis_count"], 0)
    df["sme_share"] = np.where(df["size_total_count"] > 0, df["size_s_count"] / df["size_total_count"] * 100, 0)
    df["business_group"] = df["type"].apply(_business_group)
    # Scores: higher is better except competition and risk.
    demand_score = _normalize_score(df["regis_count"])
    survival_score = _normalize_score(df["closure_rate"], inverse=True)
    capital_score = _normalize_score(df["avg_capital_m"].clip(upper=df["avg_capital_m"].quantile(.95) if len(df) else 0))
    sme_score = _normalize_score(df["sme_share"])
    competition_penalty = _normalize_score(df["regis_count"])
    df["opportunity_score"] = (0.30 * demand_score + 0.35 * survival_score + 0.20 * sme_score + 0.15 * capital_score - 0.15 * competition_penalty).clip(0, 100)
    df["risk_score"] = (0.55 * _normalize_score(df["closure_rate"]) + 0.30 * _normalize_score(df["regis_count"]) + 0.15 * _normalize_score(df["avg_capital_m"])).clip(0, 100)
    df = df[(df[["regis_count", "quit_count", "active_count", "size_total_count"]].sum(axis=1) > 0)]
    return df.sort_values("opportunity_score", ascending=False)


@st.cache_data(show_spinner=False)
def load_business_compare() -> pd.DataFrame:
    df69 = load_business_metrics(2569).add_suffix("_69").rename(columns={"type_69": "type"})
    df68 = load_business_metrics(2568).add_suffix("_68").rename(columns={"type_68": "type"})
    if df69.empty or df68.empty:
        return pd.DataFrame(columns=COMPARE_COLUMNS)
    # Avoid misleading YoY comparison when one year only has active data but no regis/quit file.
    if df68.get("regis_count", pd.Series(dtype=float)).sum() == 0 and df68.get("quit_count", pd.Series(dtype=float)).sum() == 0:
        return pd.DataFrame(columns=COMPARE_COLUMNS)
    if df69.get("regis_count", pd.Series(dtype=float)).sum() == 0 and df69.get("quit_count", pd.Series(dtype=float)).sum() == 0:
        return pd.DataFrame(columns=COMPARE_COLUMNS)
    out = pd.merge(df69, df68, on="type", how="inner")
    out["regis_growth_pct"] = np.where(out["regis_count_68"] > 0, (out["regis_count_69"] - out["regis_count_68"]) / out["regis_count_68"] * 100, 0)
    out["risk_change"] = out["closure_rate_69"] - out["closure_rate_68"]
    out["net_growth_change"] = out["net_growth_69"] - out["net_growth_68"]
    return out


@st.cache_data(show_spinner=False)
def load_all_data() -> Dict[str, pd.DataFrame]:
    province = load_province_monthly()
    latest = pd.DataFrame()
    if not province.empty:
        tmp = province.sort_values(["year", "month_no"])
        latest_period = tmp[["year", "month_no"]].drop_duplicates().tail(1)
        if not latest_period.empty:
            y, m = int(latest_period.iloc[0]["year"]), int(latest_period.iloc[0]["month_no"])
            latest = province[(province["year"] == y) & (province["month_no"] == m)].copy()
    return {
        "province_monthly": province,
        "province_latest": latest,
        "business_2569": load_business_metrics(2569),
        "business_2568": load_business_metrics(2568),
        "business_compare": load_business_compare(),
    }


def app_data_status() -> pd.DataFrame:
    files = data_files()
    rows = []
    for f in files:
        rows.append({"file": f.name, "size_kb": round(f.stat().st_size / 1024, 1)})
    return pd.DataFrame(rows)


def ai_context_text(max_rows: int = 12) -> str:
    data = load_all_data()
    parts = []
    prov = data["province_latest"]
    if not prov.empty:
        top = prov.sort_values("new_count", ascending=False).head(5)
        risky = prov[prov["new_count"] >= 20].sort_values("closure_rate", ascending=False).head(5)
        parts.append("Top provinces by new registrations: " + "; ".join([f"{r.province}: {r.new_count:.0f}" for r in top.itertuples()]))
        parts.append("High-risk provinces by closure rate: " + "; ".join([f"{r.province}: {r.closure_rate:.1f}%" for r in risky.itertuples()]))
    biz = data["business_2569"]
    if not biz.empty:
        opp = biz.sort_values("opportunity_score", ascending=False).head(max_rows)
        risk = biz[biz["regis_count"] >= 10].sort_values("risk_score", ascending=False).head(max_rows)
        parts.append("Business opportunity candidates: " + "; ".join([f"{r.type}: opportunity {r.opportunity_score:.1f}, regis {r.regis_count:.0f}, closure {r.closure_rate:.1f}%" for r in opp.itertuples()]))
        parts.append("Business risk candidates: " + "; ".join([f"{r.type}: risk {r.risk_score:.1f}, closure {r.closure_rate:.1f}%" for r in risk.itertuples()]))
    return "\n".join(parts)
