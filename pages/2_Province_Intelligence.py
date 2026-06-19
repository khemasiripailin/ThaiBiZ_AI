# -*- coding: utf-8 -*-
"""
Province Intelligence page for ThaiBiz Streamlit app.
เวอร์ชันแก้ไขตาม feedback:
- กลับไปใช้แท็บเพื่อให้อ่านง่าย
- แก้ caption แหล่งข้อมูล
- ทำกราฟ Closure Rate ให้มีจังหวัดที่เลือกติดอยู่เสมอ
- เพิ่มความยืดหยุ่นในการอ่านไฟล์ จังหวัดมูลค่าทุน*_cat / จังหวัดขนาด*_size
- เพิ่มคำอธิบาย feature ของ Raw Data
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
    from db import ensure_database_ready, load_all_data_from_duckdb as load_all_data
    ensure_database_ready(auto_refresh=True)
except Exception:
    from data_loader import load_all_data

try:
    from data_loader import DATA_DIR, data_files
except Exception:
    DATA_DIR = Path(__file__).resolve().parents[1] / "data"

    def data_files() -> list[Path]:
        return sorted(DATA_DIR.glob("*.csv"))

from style import apply_theme, configure_plotly, page_header, metric_card, fig_layout

apply_theme()
configure_plotly()


# ============================================================
# Helpers
# ============================================================

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s))
    s = s.replace("ประเเภท", "ประเภท").replace("เเ", "แ")
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _strip_suffix(name: str) -> str:
    return re.sub(r"\.\d+$", "", str(name).strip())


def _all_data_files() -> list[Path]:
    paths: list[Path] = []
    if DATA_DIR.exists():
        for pat in ["*.csv", "*.xlsx", "*.xls"]:
            paths.extend(DATA_DIR.glob(pat))
    paths.extend(data_files())
    unique = []
    seen = set()
    for p in paths:
        if p.exists() and p not in seen:
            unique.append(p)
            seen.add(p)
    return sorted(unique)


def _read_table_auto(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        last_error = None
        for enc in ["utf-8-sig", "utf-8", "cp874", "tis-620"]:
            try:
                df = pd.read_csv(path, encoding=enc)
                df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
                return df
            except Exception as e:
                last_error = e
        raise RuntimeError(f"อ่านไฟล์ {path.name} ไม่ได้: {last_error}")
    df = pd.read_excel(path)
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


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


def _province_col(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        n = _norm(c)
        if n in ["province", "place", "จังหวัด"] or "จังหวัด" in n:
            return c
    return df.columns[0] if len(df.columns) else None


def _rename_province(s: str) -> str:
    s = str(s).strip()
    if s in ["กทม.", "กรุงเทพ", "กรุงเทพฯ", "Bangkok"]:
        return "กรุงเทพมหานคร"
    return s


def _drop_aggregate_rows(df: pd.DataFrame, pcol: str) -> pd.DataFrame:
    return df[~df[pcol].astype(str).str.contains("รวม|ทั่วประเทศ|ภาค|nan|หมายเหตุ", case=False, na=False)].copy()


def _detect_group(col_name: str) -> str | None:
    n = _norm(col_name)
    if any(k in n for k in ["รวม", "total", "sum"]):
        return None
    if any(k in n for k in ["ขายส่ง", "ขายปลีก", "ค้าส่ง", "ค้าปลีก", "retail", "wholesale"]):
        return "ขายส่ง/ขายปลีก"
    if any(k in n for k in ["ผลิต", "manufact", "industry", "factory"]):
        return "ผลิต"
    if any(k in n for k in ["บริการ", "service", "serv"]):
        return "บริการ"
    return None


def _find_matching_files(prefix_keyword: str, year: int, preferred_tag: str | None = None) -> list[Path]:
    yy = str(year)[-2:]
    out = []
    for f in _all_data_files():
        n = _norm(f.name)
        if _norm(prefix_keyword) not in n:
            continue
        if yy not in n:
            continue
        if preferred_tag and _norm(preferred_tag) in n:
            out.append(f)
    if out:
        return sorted(out)

    for f in _all_data_files():
        n = _norm(f.name)
        if _norm(prefix_keyword) in n and yy in n:
            out.append(f)
    return sorted(out)


# ============================================================
# Province-level optional loaders
# ============================================================



def _parse_province_capital_raw(path: Path) -> pd.DataFrame:
    """Parse DBD province capital/category files with flexible multi-row headers."""
    try:
        raw = _read_table_auto(path) if path.suffix.lower() == ".csv" else None
    except Exception:
        raw = None

    # For raw header detection, read with header=None
    if path.suffix.lower() == ".csv":
        raw = None
        for enc in ["utf-8-sig", "utf-8", "cp874", "tis-620"]:
            try:
                raw = pd.read_csv(path, encoding=enc, header=None)
                break
            except Exception:
                pass
        if raw is None:
            return pd.DataFrame(columns=["province", "group", "capital_m"])
    else:
        try:
            xl = pd.ExcelFile(path)
            # Prefer sheets related to capital / category
            sheet = next((s for s in xl.sheet_names if any(k in str(s) for k in ["มูลค่าทุน", "ทุน", "cat"])), xl.sheet_names[0])
            raw = pd.read_excel(path, sheet_name=sheet, header=None)
        except Exception:
            return pd.DataFrame(columns=["province", "group", "capital_m"])

    if raw.empty or raw.shape[1] < 3:
        return pd.DataFrame(columns=["province", "group", "capital_m"])

    # Find the row that contains business groups such as ขายส่ง/ขายปลีก, ผลิต, บริการ
    group_row_idx = None
    scan_rows = min(12, len(raw))
    for i in range(scan_rows):
        detected = [_detect_group(x) for x in raw.iloc[i].tolist()]
        if sum(g is not None for g in detected) >= 2:
            group_row_idx = i
            break

    if group_row_idx is None:
        return pd.DataFrame(columns=["province", "group", "capital_m"])

    # Province column is usually the first column; find data start as the first row after header with a Thai province-like value
    province_col_idx = 0
    data_start_idx = group_row_idx + 1
    for i in range(group_row_idx + 1, min(group_row_idx + 8, len(raw))):
        val = str(raw.iloc[i, province_col_idx]).strip()
        if val and val.lower() != "nan" and "จังหวัด" not in val:
            data_start_idx = i
            break

    groups = raw.iloc[group_row_idx].astype(str).map(lambda x: x.strip())
    data = raw.iloc[data_start_idx:].copy()

    rows = []
    for c in range(1, raw.shape[1]):
        group = _detect_group(groups.iloc[c])
        if group is None:
            continue
        tmp = pd.DataFrame({
            "province": data.iloc[:, province_col_idx].map(_rename_province),
            "group": group,
            "capital_m": _to_num(data.iloc[:, c]),
        })
        rows.append(tmp)

    if not rows:
        return pd.DataFrame(columns=["province", "group", "capital_m"])

    out = pd.concat(rows, ignore_index=True)
    out = out.dropna(subset=["province"])
    out = _drop_aggregate_rows(out, "province")
    out = out[out["capital_m"] > 0]
    return out[["province", "group", "capital_m"]]


def load_province_capital_category(year: int) -> pd.DataFrame:
    """
    รองรับไฟล์จังหวัดมูลค่าทุน*_cat.csv / xlsx แบบ DBD multi-row header
    output: province, group, capital_m
    """
    files = _find_matching_files("จังหวัดมูลค่าทุน", year, preferred_tag="cat")
    rows = []

    for f in files:
        raw_parsed = _parse_province_capital_raw(f)
        # Accept only meaningful parse: at least one group and positive value
        if (not raw_parsed.empty) and raw_parsed["capital_m"].sum() > 0 and raw_parsed["group"].nunique() >= 1:
            rows.append(raw_parsed)
            continue

        # Fallback: tidy/wide normal header
        try:
            df = _read_table_auto(f)
        except Exception:
            continue
        if df.empty:
            continue
        pcol = _province_col(df)
        if not pcol:
            continue
        df[pcol] = df[pcol].map(_rename_province)
        df = _drop_aggregate_rows(df, pcol)

        category_col = None
        value_col = None
        for c in df.columns:
            n = _norm(c)
            if c == pcol:
                continue
            if any(k in n for k in ["category", "group", "sector", "ประเภท", "กลุ่ม"]):
                category_col = c
            if any(k in n for k in ["capital", "ทุน", "มูลค่า", "value", "amount"]):
                value_col = c
        if category_col and value_col:
            tmp = df[[pcol, category_col, value_col]].copy()
            tmp.columns = ["province", "group", "capital_m"]
            tmp["group"] = tmp["group"].astype(str).str.strip()
            tmp["capital_m"] = _to_num(tmp["capital_m"])
            rows.append(tmp)
            continue

        for c in df.columns:
            if c == pcol:
                continue
            group = _detect_group(c)
            if group is None:
                continue
            rows.append(pd.DataFrame({"province": df[pcol], "group": group, "capital_m": _to_num(df[c])}))

    if not rows:
        return pd.DataFrame(columns=["province", "group", "capital_m"])

    out = pd.concat(rows, ignore_index=True)
    out = out.dropna(subset=["province"])
    out = out.groupby(["province", "group"], as_index=False)["capital_m"].sum()
    out = out[out["capital_m"] > 0]
    return out


def _parse_size_raw_table(raw: pd.DataFrame, value_kind_hint: str | None = None) -> pd.DataFrame:
    """Parse one raw DBD size table. value_kind_hint can be 'count' or 'capital'."""
    if raw.empty or raw.shape[1] < 4:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m"])

    # Find row containing S/M/L repeated
    size_row_idx = None
    scan_rows = min(12, len(raw))
    for i in range(scan_rows):
        vals = [str(x).strip().upper() for x in raw.iloc[i].tolist()]
        n_sizes = sum(v in ["S", "M", "L"] for v in vals)
        if n_sizes >= 3:
            size_row_idx = i
            break

    if size_row_idx is None:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m"])

    province_col_idx = 0
    data_start_idx = size_row_idx + 1
    for i in range(size_row_idx + 1, min(size_row_idx + 8, len(raw))):
        val = str(raw.iloc[i, province_col_idx]).strip()
        if val and val.lower() != "nan" and "จังหวัด" not in val:
            data_start_idx = i
            break

    size_row = raw.iloc[size_row_idx].astype(str).map(lambda x: x.strip().upper())
    data = raw.iloc[data_start_idx:].copy()
    rows = []

    for c in range(1, raw.shape[1]):
        size = size_row.iloc[c]
        if size not in ["S", "M", "L"]:
            continue

        # Determine count vs capital by looking above the S/M/L row or using file/sheet hint
        header_text = " ".join(str(raw.iloc[r, c]) for r in range(0, size_row_idx + 1))
        header_norm = _norm(header_text)
        if value_kind_hint == "capital" or any(k in header_norm for k in ["มูลค่าทุน", "capital", "ล้านบาท", "ทุน"]):
            count_vals = 0
            capital_vals = _to_num(data.iloc[:, c])
        else:
            count_vals = _to_num(data.iloc[:, c])
            capital_vals = 0

        rows.append(pd.DataFrame({
            "province": data.iloc[:, province_col_idx].map(_rename_province),
            "size": size,
            "count": count_vals,
            "capital_m": capital_vals,
        }))

    if not rows:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m"])

    out = pd.concat(rows, ignore_index=True)
    out = out.dropna(subset=["province"])
    out = _drop_aggregate_rows(out, "province")
    return out[["province", "size", "count", "capital_m"]]


def _parse_province_size_raw(path: Path) -> pd.DataFrame:
    """Parse DBD province size CSV/Excel with flexible multi-row headers."""
    rows = []

    if path.suffix.lower() == ".csv":
        raw = None
        for enc in ["utf-8-sig", "utf-8", "cp874", "tis-620"]:
            try:
                raw = pd.read_csv(path, encoding=enc, header=None)
                break
            except Exception:
                pass
        if raw is None:
            return pd.DataFrame(columns=["province", "size", "count", "capital_m"])
        # Guess by filename/header. Most *_size.csv exported from count sheet; if header says capital, parser will catch.
        rows.append(_parse_size_raw_table(raw))
    else:
        try:
            xl = pd.ExcelFile(path)
            for sheet in xl.sheet_names:
                if not any(k in str(sheet) for k in ["จำนวน", "มูลค่าทุน", "ทุน", "size", "ขนาด"]):
                    continue
                raw = pd.read_excel(path, sheet_name=sheet, header=None)
                hint = "capital" if any(k in str(sheet) for k in ["มูลค่าทุน", "ทุน"]) else "count"
                rows.append(_parse_size_raw_table(raw, value_kind_hint=hint))
        except Exception:
            return pd.DataFrame(columns=["province", "size", "count", "capital_m"])

    rows = [r for r in rows if not r.empty]
    if not rows:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m"])

    return pd.concat(rows, ignore_index=True)


def load_province_size(year: int) -> pd.DataFrame:
    """
    รองรับไฟล์จังหวัดขนาด*_size.csv / xlsx แบบ DBD multi-row header
    output: province, size, count, capital_m, avg_capital_m
    """
    files = _find_matching_files("จังหวัดขนาด", year, preferred_tag="size")
    rows = []

    for f in files:
        raw_parsed = _parse_province_size_raw(f)
        # Accept raw parse only if it has at least 2 sizes and positive values.
        if (not raw_parsed.empty) and raw_parsed["size"].nunique() >= 2 and (raw_parsed["count"].sum() + raw_parsed["capital_m"].sum() > 0):
            rows.append(raw_parsed)
            continue

        # Fallback: normal header, e.g. p_s,p_m,p_l,m_s,m_m,m_l or S/M/L/S.1/M.1/L.1
        try:
            df = _read_table_auto(f)
        except Exception:
            continue
        if df.empty:
            continue

        pcol = _province_col(df)
        if not pcol:
            continue
        df[pcol] = df[pcol].map(_rename_province)
        df = _drop_aggregate_rows(df, pcol)

        size_col = None
        count_col = None
        capital_col = None
        for c in df.columns:
            n = _norm(c)
            if c == pcol:
                continue
            if n == "size" or "ขนาด" in n:
                size_col = c
            elif any(k in n for k in ["count", "จำนวน", "ราย"]):
                count_col = c
            elif any(k in n for k in ["capital", "ทุน", "มูลค่า"]):
                capital_col = c

        if size_col:
            rows.append(pd.DataFrame({
                "province": df[pcol],
                "size": df[size_col].astype(str).str.upper().str.strip(),
                "count": _to_num(df[count_col]) if count_col else 0,
                "capital_m": _to_num(df[capital_col]) if capital_col else 0,
            }))
            continue

        orig_cols = [c for c in df.columns if c != pcol]
        for size in ["S", "M", "L"]:
            count_series = pd.Series(0, index=df.index, dtype="float64")
            capital_series = pd.Series(0, index=df.index, dtype="float64")
            found_any = False
            for c in orig_cols:
                raw_name = str(c).strip()
                base = _strip_suffix(raw_name).strip().lower()
                norm = _norm(raw_name)
                if base == size.lower() and "." not in raw_name:
                    count_series = count_series.add(_to_num(df[c]), fill_value=0)
                    found_any = True
                elif base == size.lower() and "." in raw_name:
                    capital_series = capital_series.add(_to_num(df[c]), fill_value=0)
                    found_any = True
                elif any(pat in norm for pat in [f"count{size.lower()}", f"count_{size.lower()}", f"จำนวน{size.lower()}", f"ราย{size.lower()}", f"p_{size.lower()}", f"p{size.lower()}"]):
                    count_series = count_series.add(_to_num(df[c]), fill_value=0)
                    found_any = True
                elif any(pat in norm for pat in [f"capital{size.lower()}", f"capital_{size.lower()}", f"ทุน{size.lower()}", f"มูลค่า{size.lower()}", f"m_{size.lower()}", f"m{size.lower()}"]):
                    capital_series = capital_series.add(_to_num(df[c]), fill_value=0)
                    found_any = True
            if found_any:
                rows.append(pd.DataFrame({"province": df[pcol], "size": size, "count": count_series, "capital_m": capital_series}))

    if not rows:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m", "avg_capital_m"])

    out = pd.concat(rows, ignore_index=True)
    out = out[out["size"].isin(["S", "M", "L"])]
    out = out.groupby(["province", "size"], as_index=False)[["count", "capital_m"]].sum()
    out["avg_capital_m"] = np.where(out["count"] > 0, out["capital_m"] / out["count"], np.nan)
    return out



# ============================================================
# SUPER ROBUST province capital / size readers
# วาง override ตรงนี้เพื่อไม่แก้ data_loader.py และไม่กระทบหน้าอื่น
# ============================================================

TH_PROVINCES = [
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา",
    "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก",
    "นครปฐม", "นครพนม", "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน",
    "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา",
    "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์", "แพร่", "ภูเก็ต",
    "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง", "ราชบุรี",
    "ลพบุรี", "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ",
    "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี",
    "สุรินทร์", "หนองคาย", "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี",
    "อุบลราชธานี",
]


def _super_norm_name(x: str) -> str:
    s = unicodedata.normalize("NFC", str(x))
    s = s.replace("ประเเภท", "ประเภท").replace("เเ", "แ")
    s = re.sub(r"[\s_\-–—]+", "", s)
    return s.lower()


def _file_candidates(kind: str, year: int) -> list[Path]:
    """Find files by meaning, not by exact filename."""
    yy = str(year)[-2:]
    files = _all_data_files()
    out = []
    for f in files:
        n = _super_norm_name(f.name)
        if yy not in n:
            continue
        if kind == "capital":
            if ("จังหวัด" in n and ("มูลค่าทุน" in n or "ทุน" in n or "capital" in n) and ("cat" in n or "มูล" in n)):
                out.append(f)
        elif kind == "size":
            if ("จังหวัด" in n and ("ขนาด" in n or "size" in n)):
                out.append(f)
    # prioritize csv *_cat / *_size, but allow xlsx fallback
    return sorted(set(out), key=lambda p: (0 if p.suffix.lower()==".csv" else 1, p.name))


def _read_raw_sheets(path: Path) -> list[tuple[str, pd.DataFrame]]:
    """Read a CSV/Excel as raw header=None tables."""
    out = []
    if path.suffix.lower() == ".csv":
        for enc in ["utf-8-sig", "utf-8", "cp874", "tis-620"]:
            try:
                raw = pd.read_csv(path, encoding=enc, header=None, dtype=object)
                raw = raw.dropna(how="all").dropna(axis=1, how="all")
                out.append((path.stem, raw))
                break
            except Exception:
                continue
    else:
        try:
            xl = pd.ExcelFile(path)
            for sheet in xl.sheet_names:
                try:
                    raw = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)
                    raw = raw.dropna(how="all").dropna(axis=1, how="all")
                    if not raw.empty:
                        out.append((str(sheet), raw))
                except Exception:
                    pass
        except Exception:
            pass
    return out


def _cell_text(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def _clean_province_value(x) -> str:
    s = _cell_text(x)
    s = s.replace("จังหวัด", "").strip()
    return _rename_province(s)


def _is_province_value(x) -> bool:
    s = _clean_province_value(x)
    if not s or s.lower() == "nan":
        return False
    if any(bad in s for bad in ["รวม", "ทั่วประเทศ", "ภาค", "หมายเหตุ", "ข้อมูล", "จังหวัด"]):
        return False
    return s in TH_PROVINCES


def _best_province_col(raw: pd.DataFrame) -> int:
    best_col = 0
    best_score = -1
    for c in range(raw.shape[1]):
        vals = raw.iloc[:, c]
        score = int(vals.map(_is_province_value).sum())
        # Give a tiny bonus if header mentions province
        head = " ".join(_cell_text(x) for x in raw.iloc[:8, c].tolist())
        if "จังหวัด" in head or "province" in head.lower():
            score += 2
        if score > best_score:
            best_col, best_score = c, score
    return best_col


def _header_context(raw: pd.DataFrame, row_idx: int, col_idx: int, max_rows: int = 12) -> str:
    upper = raw.iloc[max(0, row_idx-max_rows):row_idx+1, col_idx].tolist()
    # also inspect nearby left/right header cells on upper rows, useful with merged-cell exports
    nearby = []
    for r in range(max(0, row_idx-max_rows), row_idx+1):
        for c in range(max(0, col_idx-2), min(raw.shape[1], col_idx+3)):
            nearby.append(raw.iat[r, c])
    return " ".join(_cell_text(x) for x in upper + nearby)


def _safe_num_cell(x) -> float | None:
    if pd.isna(x):
        return None
    s = str(x).strip()
    if not s or s in ["-", "–", "—"] or s.lower() == "nan":
        return None
    s = s.replace(",", "")
    # reject pure text
    try:
        val = float(s)
    except Exception:
        return None
    return val


def _detect_group_from_context(ctx: str) -> str | None:
    n = _norm(ctx)
    if any(k in n for k in ["ขายส่ง", "ขายปลีก", "ค้าส่ง", "ค้าปลีก", "wholesale", "retail"]):
        return "ขายส่ง/ขายปลีก"
    if any(k in n for k in ["ผลิต", "manufact", "โรงงาน", "อุตสาห"]):
        return "ผลิต"
    if any(k in n for k in ["บริการ", "service"]):
        return "บริการ"
    return None


def _detect_size_from_context(ctx: str) -> str | None:
    # scan each token and allow S.1 / M.1 / L.1 from pandas-exported duplicate columns
    tokens = re.split(r"[\s,|/]+", str(ctx).upper())
    for tok in reversed(tokens):
        tok = tok.strip().replace("'", "").replace('"', "")
        base = re.sub(r"\.\d+$", "", tok)
        if base in ["S", "M", "L"]:
            return base
    # extra fallback: exact cell text may be embedded in Thai header
    for size in ["S", "M", "L"]:
        if re.search(rf"(^|[^A-Z]){size}(\.|$|[^A-Z])", str(ctx).upper()):
            return size
    return None


def _looks_like_capital_context(ctx: str, file_name: str = "") -> bool:
    n = _norm(str(ctx) + " " + str(file_name))
    return any(k in n for k in ["มูลค่าทุน", "ทุนจดทะเบียน", "ล้านบาท", "capital", "amount", "value"])


def _try_tidy_capital(path: Path) -> pd.DataFrame:
    """Try already-normalized CSV with columns like province/group/capital."""
    try:
        df = _read_table_auto(path)
    except Exception:
        return pd.DataFrame(columns=["province", "group", "capital_m"])
    if df.empty:
        return pd.DataFrame(columns=["province", "group", "capital_m"])

    # Normalize columns for common exported formats
    cols_norm = {c: _norm(c) for c in df.columns}
    pcol = next((c for c,n in cols_norm.items() if "province" in n or "จังหวัด" in n), None)
    gcol = next((c for c,n in cols_norm.items() if any(k in n for k in ["businessgroup", "group", "category", "sector", "กลุ่ม", "ประเภท"])), None)
    vcol = next((c for c,n in cols_norm.items() if any(k in n for k in ["capital", "ทุน", "มูลค่า", "value", "amount"])), None)
    if pcol and gcol and vcol:
        out = pd.DataFrame({
            "province": df[pcol].map(_clean_province_value),
            "group": df[gcol].astype(str).map(lambda x: _detect_group_from_context(x) or x.strip()),
            "capital_m": _to_num(df[vcol]),
        })
        out = out[out["province"].map(_is_province_value)]
        out = out[out["capital_m"] > 0]
        return out[["province", "group", "capital_m"]]
    return pd.DataFrame(columns=["province", "group", "capital_m"])


def _try_tidy_size(path: Path) -> pd.DataFrame:
    """Try already-normalized CSV with columns like province/size/count/capital."""
    try:
        df = _read_table_auto(path)
    except Exception:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m"])
    if df.empty:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m"])

    cols_norm = {c: _norm(c) for c in df.columns}
    pcol = next((c for c,n in cols_norm.items() if "province" in n or "จังหวัด" in n), None)
    scol = next((c for c,n in cols_norm.items() if n == "size" or "ขนาด" in n), None)
    ccol = next((c for c,n in cols_norm.items() if any(k in n for k in ["count", "จำนวน", "ราย"])), None)
    mcol = next((c for c,n in cols_norm.items() if any(k in n for k in ["capital", "ทุน", "มูลค่า"])), None)
    if pcol and scol:
        out = pd.DataFrame({
            "province": df[pcol].map(_clean_province_value),
            "size": df[scol].astype(str).str.upper().str.strip().str.replace(r"\.\d+$", "", regex=True),
            "count": _to_num(df[ccol]) if ccol else 0,
            "capital_m": _to_num(df[mcol]) if mcol else 0,
        })
        out = out[out["province"].map(_is_province_value)]
        out = out[out["size"].isin(["S", "M", "L"])]
        return out[["province", "size", "count", "capital_m"]]

    # Wide, clean CSV: province + S/M/L or S.1/M.1/L.1 columns
    if pcol:
        rows = []
        for size in ["S", "M", "L"]:
            count_series = pd.Series(0.0, index=df.index)
            cap_series = pd.Series(0.0, index=df.index)
            found = False
            for c in df.columns:
                if c == pcol:
                    continue
                raw = str(c).strip().upper()
                base = re.sub(r"\.\d+$", "", raw)
                if base == size:
                    # if duplicate suffix or capital wording, treat as capital, otherwise count
                    if "." in raw or _looks_like_capital_context(raw, path.name):
                        cap_series = cap_series.add(_to_num(df[c]), fill_value=0)
                    else:
                        count_series = count_series.add(_to_num(df[c]), fill_value=0)
                    found = True
            if found:
                rows.append(pd.DataFrame({"province": df[pcol].map(_clean_province_value), "size": size, "count": count_series, "capital_m": cap_series}))
        if rows:
            out = pd.concat(rows, ignore_index=True)
            out = out[out["province"].map(_is_province_value)]
            return out
    return pd.DataFrame(columns=["province", "size", "count", "capital_m"])


def _scan_raw_capital(path: Path) -> pd.DataFrame:
    rows = []
    for sheet_name, raw in _read_raw_sheets(path):
        if raw.empty:
            continue
        pcol = _best_province_col(raw)
        for r in range(raw.shape[0]):
            province = _clean_province_value(raw.iat[r, pcol])
            if province not in TH_PROVINCES:
                continue
            for c in range(raw.shape[1]):
                if c == pcol:
                    continue
                val = _safe_num_cell(raw.iat[r, c])
                if val is None or val <= 0:
                    continue
                ctx = _header_context(raw, r, c) + " " + sheet_name + " " + path.name
                group = _detect_group_from_context(ctx)
                if group is None:
                    continue
                # avoid accidental count columns if context says จำนวนราย strongly and notทุน
                if ("จำนวน" in ctx or "ราย" in ctx) and not _looks_like_capital_context(ctx, path.name):
                    continue
                rows.append({"province": province, "group": group, "capital_m": float(val)})
    if not rows:
        return pd.DataFrame(columns=["province", "group", "capital_m"])
    return pd.DataFrame(rows)


def _scan_raw_size(path: Path) -> pd.DataFrame:
    rows = []
    for sheet_name, raw in _read_raw_sheets(path):
        if raw.empty:
            continue
        pcol = _best_province_col(raw)
        for r in range(raw.shape[0]):
            province = _clean_province_value(raw.iat[r, pcol])
            if province not in TH_PROVINCES:
                continue
            for c in range(raw.shape[1]):
                if c == pcol:
                    continue
                val = _safe_num_cell(raw.iat[r, c])
                if val is None or val <= 0:
                    continue
                ctx = _header_context(raw, r, c) + " " + sheet_name + " " + path.name
                size = _detect_size_from_context(ctx)
                if size is None:
                    continue
                is_cap = _looks_like_capital_context(ctx, path.name)
                rows.append({
                    "province": province,
                    "size": size,
                    "count": 0.0 if is_cap else float(val),
                    "capital_m": float(val) if is_cap else 0.0,
                })
    if not rows:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m"])
    return pd.DataFrame(rows)


# Override previous loaders with stronger readers
def load_province_capital_category(year: int) -> pd.DataFrame:
    files = _file_candidates("capital", year)
    rows = []
    for f in files:
        tidy = _try_tidy_capital(f)
        if not tidy.empty:
            rows.append(tidy)
        raw = _scan_raw_capital(f)
        if not raw.empty:
            rows.append(raw)
    if not rows:
        return pd.DataFrame(columns=["province", "group", "capital_m"])
    out = pd.concat(rows, ignore_index=True)
    out["province"] = out["province"].map(_clean_province_value)
    out["group"] = out["group"].astype(str).map(lambda x: _detect_group_from_context(x) or x.strip())
    out["capital_m"] = pd.to_numeric(out["capital_m"], errors="coerce").fillna(0)
    out = out[out["province"].isin(TH_PROVINCES)]
    out = out[out["group"].isin(["ขายส่ง/ขายปลีก", "ผลิต", "บริการ"])]
    out = out[out["capital_m"] > 0]
    # Drop duplicate rows caused by trying both tidy and raw parse on same file
    out = out.drop_duplicates(subset=["province", "group", "capital_m"])
    return out.groupby(["province", "group"], as_index=False)["capital_m"].sum()


def load_province_size(year: int) -> pd.DataFrame:
    files = _file_candidates("size", year)
    rows = []
    for f in files:
        tidy = _try_tidy_size(f)
        if not tidy.empty:
            rows.append(tidy)
        raw = _scan_raw_size(f)
        if not raw.empty:
            rows.append(raw)
    if not rows:
        return pd.DataFrame(columns=["province", "size", "count", "capital_m", "avg_capital_m"])
    out = pd.concat(rows, ignore_index=True)
    out["province"] = out["province"].map(_clean_province_value)
    out["size"] = out["size"].astype(str).str.upper().str.strip().str.replace(r"\.\d+$", "", regex=True)
    out["count"] = pd.to_numeric(out["count"], errors="coerce").fillna(0)
    out["capital_m"] = pd.to_numeric(out["capital_m"], errors="coerce").fillna(0)
    out = out[out["province"].isin(TH_PROVINCES)]
    out = out[out["size"].isin(["S", "M", "L"])]
    out = out[(out["count"] > 0) | (out["capital_m"] > 0)]
    out = out.drop_duplicates(subset=["province", "size", "count", "capital_m"])
    out = out.groupby(["province", "size"], as_index=False)[["count", "capital_m"]].sum()
    out["avg_capital_m"] = np.where(out["count"] > 0, out["capital_m"] / out["count"], np.nan)
    return out


# ============================================================
# Province coordinates
# ============================================================

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
    "พะเยา": (19.1920, 99.8788), "พังงา": (8.4501, 98.5255), "พัทลุง": (7.6167, 100.0779), "พิจิตร": (16.4429, 100.3488),
    "พิษณุโลก": (16.8211, 100.2659), "เพชรบุรี": (13.1119, 99.9447), "เพชรบูรณ์": (16.4190, 101.1606),
    "แพร่": (18.1446, 100.1403), "ภูเก็ต": (7.8804, 98.3923), "มหาสารคาม": (16.1851, 103.3026),
    "มุกดาหาร": (16.5422, 104.7235), "แม่ฮ่องสอน": (19.3010, 97.9654), "ยโสธร": (15.7926, 104.1453),
    "ยะลา": (6.5411, 101.2804), "ร้อยเอ็ด": (16.0538, 103.6520), "ระนอง": (9.9529, 98.6085),
    "ระยอง": (12.6814, 101.2816), "ราชบุรี": (13.5283, 99.8134), "ลพบุรี": (14.7995, 100.6534),
    "ลำปาง": (18.2888, 99.4909), "ลำพูน": (18.5745, 99.0087), "เลย": (17.4860, 101.7223),
    "ศรีสะเกษ": (15.1186, 104.3220), "สกลนคร": (17.1546, 104.1348), "สงขลา": (7.1898, 100.5951),
    "สตูล": (6.6238, 100.0674), "สมุทรปราการ": (13.5991, 100.5998), "สมุทรสงคราม": (13.4098, 100.0023),
    "สมุทรสาคร": (13.5475, 100.2744), "สระแก้ว": (13.8240, 102.0646), "สระบุรี": (14.5289, 100.9101),
    "สิงห์บุรี": (14.8936, 100.3967), "สุโขทัย": (17.0056, 99.8264), "สุพรรณบุรี": (14.4745, 100.1177),
    "สุราษฎร์ธานี": (9.1382, 99.3215), "สุรินทร์": (14.8829, 103.4937), "หนองคาย": (17.8783, 102.7413),
    "หนองบัวลำภู": (17.2218, 102.4260), "อ่างทอง": (14.5896, 100.4550), "อำนาจเจริญ": (15.8585, 104.6288),
    "อุดรธานี": (17.4138, 102.7872), "อุตรดิตถ์": (17.6201, 100.0993), "อุทัยธานี": (15.3835, 100.0246),
    "อุบลราชธานี": (15.2287, 104.8564),
}


# ============================================================
# Charts
# ============================================================

def chart_monthly_trend(pdf: pd.DataFrame, province: str) -> go.Figure:
    d = pdf.sort_values([c for c in ["year", "month_no"] if c in pdf.columns]).copy()
    d["period"] = d["month"].astype(str) + " " + d["year"].astype(str)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["period"], y=d["new_count"], mode="lines+markers+text", name="จัดตั้งใหม่",
                             text=[_fmt_int(x) for x in d["new_count"]], textposition="top center", line=dict(width=3), marker=dict(size=9)))
    fig.add_trace(go.Scatter(x=d["period"], y=d["closed_count"], mode="lines+markers+text", name="เลิกกิจการ",
                             text=[_fmt_int(x) for x in d["closed_count"]], textposition="bottom center", line=dict(width=3), marker=dict(size=9)))
    if "add_fund_count" in d.columns and d["add_fund_count"].sum() > 0:
        fig.add_trace(go.Scatter(x=d["period"], y=d["add_fund_count"], mode="lines+markers+text", name="เพิ่มทุน",
                                 text=[_fmt_int(x) for x in d["add_fund_count"]], textposition="middle right",
                                 line=dict(width=2, dash="dot"), marker=dict(size=8)))
    fig.update_layout(xaxis_title="เดือน", yaxis_title="จำนวนธุรกิจ (ราย)", hovermode="x unified")
    return fig_layout(fig, title=f"แนวโน้มธุรกิจรายเดือน: {province}", height=470)


def monthly_insight(pdf: pd.DataFrame, province: str) -> list[str]:
    d = pdf.sort_values([c for c in ["year", "month_no"] if c in pdf.columns]).copy()
    if d.empty:
        return ["ยังไม่มีข้อมูลเพียงพอสำหรับสรุปแนวโน้ม"]
    best = d.loc[d["new_count"].idxmax()]
    latest = d.iloc[-1]
    previous = d.iloc[-2] if len(d) >= 2 else None
    msgs = [
        f"เดือนที่มีการจัดตั้งใหม่สูงสุดของ **{province}** คือ **{best.month} {int(best.year)}** จำนวน **{_fmt_int(best.new_count)} ราย**",
        f"เดือนล่าสุดมี **Net Growth = {_fmt_int(latest.net_growth)} ราย** (จัดตั้งใหม่ - เลิกกิจการ)",
    ]
    if previous is not None:
        diff = latest.new_count - previous.new_count
        direction = "เพิ่มขึ้น" if diff >= 0 else "ลดลง"
        msgs.append(f"จำนวนจัดตั้งใหม่เดือนล่าสุด{direction}จากเดือนก่อน **{_fmt_int(abs(diff))} ราย**")
    msgs.append(
        "Closure Rate สูง หมายถึงจังหวัดนั้นมีธุรกิจเลิกกิจการมากเมื่อเทียบกับจำนวนที่เปิดใหม่ในเดือนเดียวกัน"
    )
    return msgs


def thai_bar_top(df: pd.DataFrame, metric: str, label: str, title: str, x_title: str, n: int = 10,
                 selected: str | None = None, percent: bool = False) -> go.Figure:
    d = df.dropna(subset=[metric, label]).copy()
    d = d.sort_values(metric, ascending=False).head(n).sort_values(metric, ascending=True)
    colors = ["#a855f7" if str(p) == str(selected) else "rgba(255,255,255,0.72)" for p in d[label]]
    text = [f"{v:,.2f}%" if percent else f"{v:,.0f}" for v in d[metric]]
    fig = go.Figure(go.Bar(x=d[metric], y=d[label], orientation="h", marker=dict(color=colors), text=text, textposition="outside"))
    fig.update_layout(xaxis_title=x_title, yaxis_title="จังหวัด", showlegend=False)
    return fig_layout(fig, title=title, height=max(430, n * 36 + 130), showlegend=False)


def ranking_context_chart(df: pd.DataFrame, metric: str, selected: str, title: str, x_title: str,
                          higher_is_better: bool = True, percent: bool = False, filter_expr=None) -> go.Figure:
    d = df.copy()
    if filter_expr is not None:
        d = d.loc[filter_expr(d)]
    d = d.dropna(subset=["province", metric]).copy()
    d = d.sort_values(metric, ascending=not higher_is_better).reset_index(drop=True)
    d["rank"] = np.arange(1, len(d) + 1)

    if selected not in d["province"].values:
        window = d.head(min(9, len(d))).copy()
    else:
        idx = int(d.index[d["province"] == selected][0])
        start = max(0, idx - 4)
        end = min(len(d), idx + 5)
        window = d.iloc[start:end].copy()
        while len(window) < min(9, len(d)) and start > 0:
            start -= 1
            window = d.iloc[start:end].copy()
        while len(window) < min(9, len(d)) and end < len(d):
            end += 1
            window = d.iloc[start:end].copy()

    window = window.sort_values(metric, ascending=True)
    window["label"] = window.apply(lambda r: f"#{int(r['rank'])} {r['province']}", axis=1)
    colors = ["#a855f7" if p == selected else "rgba(255,255,255,0.72)" for p in window["province"]]
    text = [f"{v:,.2f}%" if percent else f"{v:,.0f}" for v in window[metric]]

    fig = go.Figure(go.Bar(
        x=window[metric], y=window["label"], orientation="h", marker=dict(color=colors),
        text=text, textposition="outside",
        hovertemplate="จังหวัด: %{y}<br>ค่า: %{x}<extra></extra>"
    ))
    fig.update_layout(xaxis_title=x_title, yaxis_title="อันดับใกล้เคียง", showlegend=False)
    return fig_layout(fig, title=title, height=430, showlegend=False)


def province_risk_matrix(view: pd.DataFrame, selected: str) -> go.Figure:
    d = view.copy()
    d["marker_size"] = np.sqrt(d["active_count"].clip(lower=0) + 1)
    if d["marker_size"].max() > 0:
        d["marker_size"] = d["marker_size"] / d["marker_size"].max() * 34 + 8
    else:
        d["marker_size"] = 14
    other = d[d["province"] != selected]
    sel = d[d["province"] == selected]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=other["new_count"], y=other["closure_rate"], mode="markers", name="จังหวัดอื่น",
                             marker=dict(size=other["marker_size"], color="rgba(255,255,255,.62)"), text=other["province"],
                             hovertemplate="%{text}<br>จัดตั้งใหม่: %{x:,.0f} ราย<br>Closure Rate: %{y:.2f}%<extra></extra>"))
    if not sel.empty:
        r = sel.iloc[0]
        fig.add_trace(go.Scatter(x=[r["new_count"]], y=[r["closure_rate"]], mode="markers+text", name="จังหวัดที่เลือก",
                                 marker=dict(size=max(float(r["marker_size"]), 26), color="#a855f7", line=dict(color="#f8fafc", width=2)),
                                 text=[f"{r['province']}<br>{r['new_count']:,.0f} ราย<br>{r['closure_rate']:.1f}%"], textposition="top center"))
    if not d.empty:
        fig.add_hline(y=float(d["closure_rate"].median()), line_dash="dash", opacity=.45, annotation_text="ค่ากลาง Closure Rate")
        fig.add_vline(x=float(d["new_count"].median()), line_dash="dash", opacity=.45, annotation_text="ค่ากลางจัดตั้งใหม่")
    fig.update_layout(xaxis_title="จำนวนจัดตั้งใหม่ (ราย)", yaxis_title="Closure Rate (%)")
    return fig_layout(fig, title="แผนภาพโอกาสและความเสี่ยงรายจังหวัด", height=500)


def _safe_zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").fillna(0)
    std = s.std(ddof=0)
    if std == 0 or np.isnan(std):
        return pd.Series(0, index=s.index, dtype="float64")
    return (s - s.mean()) / std


def province_dot_map(view: pd.DataFrame, selected: str) -> go.Figure:
    d = view.copy()
    d["lat"] = d["province"].map(lambda x: PROVINCE_COORDS.get(str(x), (None, None))[0])
    d["lon"] = d["province"].map(lambda x: PROVINCE_COORDS.get(str(x), (None, None))[1])
    d = d.dropna(subset=["lat", "lon"])

    if d.empty:
        fig = go.Figure()
        fig.update_layout(title="แผนที่ตำแหน่งจังหวัดที่เลือก")
        return fig_layout(fig, title="แผนที่ตำแหน่งจังหวัดที่เลือก", height=500, showlegend=False)

    # Opportunity Score: ยิ่งสูงยิ่งเขียว / ขนาดจุดใหญ่ขึ้น
    d["opportunity_score"] = (
        0.45 * _safe_zscore(d["net_growth"]) +
        0.25 * _safe_zscore(d["new_count"]) +
        0.20 * _safe_zscore(d["active_count"]) -
        0.35 * _safe_zscore(d["closure_rate"])
    )
    mn, mx = d["opportunity_score"].min(), d["opportunity_score"].max()
    if mx != mn:
        d["opportunity_scaled"] = (d["opportunity_score"] - mn) / (mx - mn)
    else:
        d["opportunity_scaled"] = 0.5
    d["marker_size"] = 8 + d["opportunity_scaled"] * 24
    d["zone"] = np.where(d["opportunity_score"] >= d["opportunity_score"].median(), "โซนโอกาส", "โซนเสี่ยง")

    other = d[d["province"] != selected]
    sel = d[d["province"] == selected]

    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lon=other["lon"],
        lat=other["lat"],
        mode="markers",
        marker=dict(
            size=other["marker_size"],
            color=other["opportunity_score"],
            colorscale="RdYlGn",
            cmin=float(d["opportunity_score"].min()),
            cmax=float(d["opportunity_score"].max()),
            colorbar=dict(title="Opportunity"),
            line=dict(width=0.7, color="rgba(15,23,42,.8)"),
            opacity=0.82,
        ),
        text=other["province"],
        customdata=np.stack([
            other["net_growth"], other["closure_rate"], other["opportunity_score"], other["zone"]
        ], axis=-1),
        name="จังหวัดอื่น",
        hovertemplate=(
            "%{text}<br>Net Growth: %{customdata[0]:,.0f} ราย"
            "<br>Closure Rate: %{customdata[1]:.2f}%"
            "<br>Opportunity Score: %{customdata[2]:.2f}"
            "<br>%{customdata[3]}<extra></extra>"
        ),
    ))

    if not sel.empty:
        fig.add_trace(go.Scattergeo(
            lon=sel["lon"],
            lat=sel["lat"],
            mode="markers+text",
            marker=dict(
                size=sel["marker_size"] + 8,
                color=sel["opportunity_score"],
                colorscale="RdYlGn",
                cmin=float(d["opportunity_score"].min()),
                cmax=float(d["opportunity_score"].max()),
                line=dict(width=3, color="#ffffff"),
                opacity=1,
            ),
            text=[f"{r.province}<br>Score {r.opportunity_score:.2f}" for r in sel.itertuples()],
            textposition="top center",
            name="จังหวัดที่เลือก",
            hovertemplate="%{text}<extra></extra>",
        ))

    fig.update_geos(
        lonaxis_range=[96, 106.5], lataxis_range=[5, 21],
        showland=True, landcolor="rgba(30,41,59,.9)",
        showocean=True, oceancolor="rgba(15,23,42,.7)",
        showcountries=True, countrycolor="rgba(148,163,184,.45)",
        showcoastlines=True, coastlinecolor="rgba(148,163,184,.35)",
        projection_type="mercator",
    )
    fig.update_layout(showlegend=False)
    return fig_layout(fig, title="แผนที่ Opportunity Score รายจังหวัด", height=500, showlegend=False)



def opportunity_score_table(view: pd.DataFrame) -> pd.DataFrame:
    """Return province opportunity scores used by the map."""
    d = view.copy()
    required = ["province", "net_growth", "new_count", "active_count", "closure_rate"]
    for c in required:
        if c not in d.columns:
            d[c] = 0
    d["opportunity_score"] = (
        0.45 * _safe_zscore(d["net_growth"]) +
        0.25 * _safe_zscore(d["new_count"]) +
        0.20 * _safe_zscore(d["active_count"]) -
        0.35 * _safe_zscore(d["closure_rate"])
    )
    d["zone"] = np.where(d["opportunity_score"] >= d["opportunity_score"].median(), "โซนโอกาส", "โซนเสี่ยง")
    return d[["province", "net_growth", "closure_rate", "opportunity_score", "zone"]].copy()


def render_opportunity_summary(view: pd.DataFrame, selected: str) -> None:
    """Cards under map: top opportunity and risk provinces."""
    d = opportunity_score_table(view)
    if d.empty:
        return
    top5 = d.sort_values("opportunity_score", ascending=False).head(5)
    bottom5 = d.sort_values("opportunity_score", ascending=True).head(5)
    sel = d[d["province"] == selected]

    st.markdown("### สรุปจาก Opportunity Score")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>โซนโอกาสสูง</div><h3>สีเขียว / คะแนนสูง</h3>", unsafe_allow_html=True)
        for r in top5.itertuples():
            st.markdown(f"- **{r.province}** — Score {_fmt_float(r.opportunity_score)} | Net {_fmt_int(r.net_growth)} | Closure {_fmt_float(r.closure_rate)}%")
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>โซนเสี่ยง</div><h3>สีแดง / คะแนนต่ำ</h3>", unsafe_allow_html=True)
        for r in bottom5.itertuples():
            st.markdown(f"- **{r.province}** — Score {_fmt_float(r.opportunity_score)} | Net {_fmt_int(r.net_growth)} | Closure {_fmt_float(r.closure_rate)}%")
        st.markdown("</div>", unsafe_allow_html=True)
    with c3:
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>จังหวัดที่เลือก</div>", unsafe_allow_html=True)
        if sel.empty:
            st.markdown(f"### {selected}")
            st.markdown("ยังไม่มีข้อมูลสำหรับจังหวัดนี้ในเดือนที่เลือก")
        else:
            r = sel.iloc[0]
            rank = int(d["opportunity_score"].rank(ascending=False, method="min").loc[sel.index[0]])
            st.markdown(f"### {selected}")
            st.markdown(f"- อันดับ Opportunity Score: **#{rank}** จาก {len(d)} จังหวัด")
            st.markdown(f"- Score: **{_fmt_float(r.opportunity_score)}**")
            st.markdown(f"- Zone: **{r.zone}**")
            st.markdown(f"- Net Growth: **{_fmt_int(r.net_growth)} ราย**")
            st.markdown(f"- Closure Rate: **{_fmt_float(r.closure_rate)}%**")
        st.markdown("</div>", unsafe_allow_html=True)


def capital_pie(capital_df: pd.DataFrame, selected: str) -> go.Figure:
    d = capital_df[capital_df["province"] == selected].groupby("group", as_index=False)["capital_m"].sum()
    fig = px.pie(d, names="group", values="capital_m", hole=.58,
                 color_discrete_sequence=["#a855f7", "#ec4899", "#14b8a6", "#f59e0b"])
    fig.update_traces(textposition="inside", textinfo="percent+label", hovertemplate="%{label}<br>ทุน: %{value:,.2f} ลบ.<extra></extra>")
    return fig_layout(fig, title=f"สัดส่วนมูลค่าทุนตามกลุ่มธุรกิจ: {selected}", height=420)


def size_box(size_df: pd.DataFrame, selected: str, value_col: str = "count") -> go.Figure:
    d = size_df.copy()
    y_title = "จำนวนธุรกิจ (ราย)" if value_col == "count" else "ทุนเฉลี่ยต่อราย (ล้านบาท)"
    title = "การกระจายตัวของจำนวนธุรกิจตามขนาด S/M/L ในแต่ละจังหวัด" if value_col == "count" else "การกระจายตัวของทุนเฉลี่ยต่อรายตามขนาด S/M/L"
    fig = px.box(d, x="size", y=value_col, points="all", color="size", color_discrete_sequence=["#a855f7", "#ec4899", "#14b8a6"])
    sel = d[d["province"] == selected]
    if not sel.empty:
        fig.add_trace(go.Scatter(x=sel["size"], y=sel[value_col], mode="markers+text", marker=dict(size=14, color="#f59e0b", line=dict(color="#fff", width=2)),
                                 text=[selected] * len(sel), textposition="top center", name="จังหวัดที่เลือก"))
    fig.update_layout(xaxis_title="ขนาดธุรกิจ", yaxis_title=y_title)
    return fig_layout(fig, title=title, height=460)


# ============================================================
# Main page
# ============================================================

data = load_all_data()
prov = data.get("province_monthly", pd.DataFrame())

page_header(
    "📍 Province Intelligence",
    "วิเคราะห์จังหวัดที่เหมาะกับการเริ่มธุรกิจ: ดูแนวโน้มรายเดือน Net Growth, Closure Rate, โอกาส/ความเสี่ยง, กลุ่มธุรกิจหลัก และความพร้อมด้านเงินทุน",
    pills=["Monthly Trend", "Net Growth", "Risk Matrix", "Market Analysis", "Financial Analysis"],
)

if prov.empty:
    st.warning("ยังไม่พบไฟล์จังหวัดจัดตั้งเลิกเพิ่มคง*.csv ในโฟลเดอร์ data")
    st.stop()

years = sorted([int(y) for y in prov["year"].dropna().unique()])
year_options = ["ทุกปี"] + years
selected_year = st.sidebar.selectbox("เลือกปี", year_options, index=len(year_options) - 1)

if selected_year == "ทุกปี":
    ydf = prov.copy()
else:
    ydf = prov[prov["year"] == selected_year].copy()

valid_months = ydf[["month_no", "month"]].drop_duplicates().sort_values("month_no")
month_options = ["ทุกเดือน"] + [f"{r.month} ({int(r.month_no)})" for r in valid_months.itertuples() if int(r.month_no) > 0]
month_lookup = {f"{r.month} ({int(r.month_no)})": int(r.month_no) for r in valid_months.itertuples() if int(r.month_no) > 0}
selected_month_label = st.sidebar.selectbox("เดือนสำหรับเปรียบเทียบจังหวัด", month_options, index=len(month_options) - 1)
selected_month = None if selected_month_label == "ทุกเดือน" else month_lookup[selected_month_label]

province_options = sorted(ydf["province"].dropna().unique())
default_index = province_options.index("กรุงเทพมหานคร") if "กรุงเทพมหานคร" in province_options else 0
selected_province = st.sidebar.selectbox("เลือกจังหวัด", province_options, index=default_index)

# ถ้าเลือกทุกปี/ทุกเดือน ให้ aggregate รายจังหวัด เพื่อให้ KPI และ leaderboard ไม่ว่าง
if selected_month is None:
    view_source = ydf.copy()
else:
    view_source = ydf[ydf["month_no"] == selected_month].copy()

def _aggregate_province_view(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    sum_cols = [c for c in ["new_count", "closed_count", "net_growth", "add_fund_count", "active_count", "new_capital_m"] if c in df.columns]
    out = df.groupby("province", as_index=False)[sum_cols].sum()
    out["year"] = "ทุกปี" if selected_year == "ทุกปี" else selected_year
    out["month_no"] = 0 if selected_month is None else selected_month
    out["month"] = "ทุกเดือน" if selected_month is None else selected_month_label.split(" (")[0]
    if {"new_count", "closed_count"}.issubset(out.columns):
        out["closure_rate"] = np.where(out["new_count"] > 0, out["closed_count"] / out["new_count"] * 100, 0)
    if "net_growth" not in out.columns and {"new_count", "closed_count"}.issubset(out.columns):
        out["net_growth"] = out["new_count"] - out["closed_count"]
    return out

view = _aggregate_province_view(view_source)
pdf = ydf[ydf["province"] == selected_province].sort_values([c for c in ["year", "month_no"] if c in ydf.columns]).copy()
current = view[view["province"] == selected_province]
current = current.iloc[0] if not current.empty else pdf.tail(1).iloc[0]

# ไฟล์ทุน/ขนาดมีแยกตามปี จึงใช้ปีล่าสุดเมื่อเลือก "ทุกปี"
selected_year_for_files = max(years) if selected_year == "ทุกปี" else selected_year
capital_df = load_province_capital_category(selected_year_for_files)
size_df = load_province_size(selected_year_for_files)

data_caption = "ข้อมูล: มาจาก DBD ตั้งแต่เดือน มกราคม 2568 ถึง เมษายน 2569"

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    metric_card("จัดตั้งใหม่", _fmt_int(current.new_count), "ราย")
with c2:
    metric_card("เลิกกิจการ", _fmt_int(current.closed_count), "ราย")
with c3:
    metric_card("Net Growth", _fmt_int(current.net_growth), "จัดตั้งใหม่ - เลิกกิจการ")
with c4:
    metric_card("Closure Rate", f"{_fmt_float(current.closure_rate)}%", "เลิก / จัดตั้งใหม่")
with c5:
    metric_card("ธุรกิจคงอยู่", _fmt_int(current.active_count), "ราย")


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1) แนวโน้มรายเดือน",
    "2) อันดับจังหวัด",
    "3) Opportunity-Risk Matrix",
    "4) Financial / Size",
    "5) Raw Data",
])

with tab1:
    st.markdown(f"## คำถาม: เดือนใดคือจังหวะที่ธุรกิจใน **{selected_province}** คึกคักที่สุด?")
    st.caption(data_caption)
    col1, col2 = st.columns([1.7, 1])
    with col1:
        st.plotly_chart(chart_monthly_trend(pdf, selected_province), use_container_width=True)
    with col2:
        st.markdown("<div class='glass-card'><div class='section-eyebrow'>Insight Summary</div><h3>อ่านกราฟนี้อย่างไร</h3>", unsafe_allow_html=True)
        for msg in monthly_insight(pdf, selected_province):
            st.markdown(f"- {msg}")
        st.markdown("</div>", unsafe_allow_html=True)
        st.info("กราฟนี้ช่วยดู seasonality หรือช่วงเวลาที่เหมาะกับการเตรียมเปิดธุรกิจ / วางแผนการลงทุน")

with tab2:
    st.markdown("## คำถาม: จังหวัดใดเติบโตสุทธิสูง และจังหวัดใดมีความเสี่ยงปิดกิจการสูง?")
    st.caption(data_caption)
    st.caption("สูตร Net Growth = จำนวนจัดตั้งใหม่ - จำนวนเลิกกิจการ")
    st.caption("สูตร Closure Rate = จำนวนเลิกกิจการ ÷ จำนวนจัดตั้งใหม่ × 100")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            ranking_context_chart(
                view,
                metric="net_growth",
                selected=selected_province,
                title=f"อันดับ Net Growth ของ {selected_province} เทียบกับจังหวัดใกล้เคียง",
                x_title="Net Growth (ราย)",
                higher_is_better=True,
                percent=False,
            ),
            use_container_width=True,
        )
        st.success("กราฟนี้บังคับให้มีจังหวัดที่เลือกอยู่เสมอ พร้อมจังหวัดใกล้เคียงในอันดับ เพื่อดูบริบทได้ง่ายขึ้น")
    with col2:
        st.plotly_chart(
            ranking_context_chart(
                view,
                metric="closure_rate",
                selected=selected_province,
                title=f"อันดับ Closure Rate ของ {selected_province} เทียบกับจังหวัดใกล้เคียง",
                x_title="Closure Rate (%)",
                higher_is_better=True,
                percent=True,
                filter_expr=lambda d: d["new_count"] >= 20,
            ),
            use_container_width=True,
        )
        st.warning("กราฟขวาบังคับให้มีจังหวัดที่เลือกอยู่เสมอ และแสดงจังหวัดใกล้เคียงรอบ ๆ เพื่อให้เทียบอันดับได้ง่าย")

with tab3:
    st.markdown("## คำถาม: จังหวัดที่เลือกอยู่ในโซนโอกาสหรือโซนเสี่ยง?")
    st.caption(data_caption)
    st.caption("แผนที่ใช้สีไล่ระดับ: เขียว = Opportunity Score สูง, แดง = โซนเสี่ยง / โอกาสต่ำ และขนาดจุดยิ่งใหญ่ยิ่งมีโอกาสสูง")
    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.plotly_chart(province_risk_matrix(view, selected_province), use_container_width=True)
    with col2:
        st.plotly_chart(province_dot_map(view, selected_province), use_container_width=True)
    st.markdown(
        """
        <div class='glass-card'>
        <div class='section-eyebrow'>How to read</div>
        <ul class='insight-list'>
          <li><b>ขวาล่าง</b>: จัดตั้งใหม่สูง + Closure ต่ำ = โซนโอกาส</li>
          <li><b>ขวาบน</b>: จัดตั้งใหม่สูง + Closure สูง = ตลาดคึกคักแต่แข่งขัน/เสี่ยงสูง</li>
          <li><b>ซ้ายล่าง</b>: ตลาดนิ่งหรือเฉพาะทาง ความเสี่ยงต่ำ</li>
          <li><b>ซ้ายบน</b>: ตลาดเล็กและเสี่ยง ควรระวัง</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_opportunity_summary(view, selected_province)

with tab4:
    st.markdown(f"## คำถาม: ถ้าจะเปิดธุรกิจใน **{selected_province}** ควรเตรียมทุนประมาณเท่าไร และธุรกิจไซส์ไหนครองตลาด?")
    st.caption(data_caption)
    if size_df.empty:
        st.warning("ยังไม่พบ/อ่านไฟล์จังหวัดขนาด*_size.csv หรือไฟล์ต้นทางที่เกี่ยวข้อง")
        with st.expander("Debug: ชื่อไฟล์ที่ระบบเห็น"):
            st.write([f.name for f in _all_data_files()])
    else:
        # Keep only meaningful S/M/L rows. Some exports may have empty future months; remove all-zero rows for clearer charts.
        size_clean = size_df.copy()
        size_clean["count"] = pd.to_numeric(size_clean["count"], errors="coerce").fillna(0)
        size_clean["capital_m"] = pd.to_numeric(size_clean["capital_m"], errors="coerce").fillna(0)
        size_clean = size_clean[(size_clean["count"] > 0) | (size_clean["capital_m"] > 0)]

        if size_clean.empty:
            st.warning("อ่านไฟล์จังหวัดขนาดได้แล้ว แต่ค่าจำนวนราย/ทุนเป็น 0 ทั้งหมด อาจต้องเช็กไฟล์ CSV ว่ามีข้อมูลจริงหรือไม่")
        else:
            has_capital = size_clean["capital_m"].sum() > 0
            box_col, fin_col = st.columns([1.1, 1])
            with box_col:
                value_col = "count"
                st.caption("กราฟนี้แสดงเฉพาะจำนวนธุรกิจตามขนาด S/M/L เพื่อให้ดูง่าย และไม่ต้องให้ผู้ใช้เลือกสลับเอง")
                if not has_capital:
                    st.info("ไฟล์ที่อ่านได้มีเฉพาะจำนวนรายตามขนาดธุรกิจ ยังไม่พบมูลค่าทุนตาม S/M/L จึงแสดง Box plot เป็นจำนวนธุรกิจแทน")
                st.plotly_chart(size_box(size_clean, selected_province, value_col=value_col), use_container_width=True)
                st.info("จุดสีส้มคือจังหวัดที่เลือก ใช้ดูว่าจังหวัดนี้มีจำนวนธุรกิจขนาด S / M / L สูงหรือต่ำกว่าการกระจายของจังหวัดอื่นอย่างไร")

            with fin_col:
                s = size_clean[size_clean["province"] == selected_province].copy()
                order = {"S": 1, "M": 2, "L": 3}
                s["_order"] = s["size"].map(order).fillna(99)
                s = s.sort_values("_order")
                if s.empty:
                    st.warning(f"ยังไม่มีข้อมูล S/M/L ของ {selected_province}")
                else:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=s["size"],
                        y=s["count"],
                        name="จำนวนราย",
                        text=[_fmt_int(x) for x in s["count"]],
                        textposition="outside",
                    ))
                    fig.update_layout(xaxis_title="ขนาดธุรกิจ", yaxis_title="จำนวนธุรกิจ (ราย)")
                    st.plotly_chart(fig_layout(fig, title=f"จำนวนธุรกิจตามขนาด: {selected_province}", height=340, showlegend=False), use_container_width=True)

                    st.markdown("<div class='glass-card'><div class='section-eyebrow'>Financial Readiness</div>", unsafe_allow_html=True)
                    if has_capital and s["capital_m"].sum() > 0:
                        st.markdown("### ทุนเฉลี่ยต่อรายตามขนาด")
                        for r in s.itertuples():
                            avg = r.avg_capital_m if pd.notna(r.avg_capital_m) else 0
                            st.markdown(f"- Size **{r.size}**: **{_fmt_float(avg)} ล้านบาท/ราย** จาก **{_fmt_int(r.count)} ราย**")
                    else:
                        st.markdown("### โครงสร้างธุรกิจตามขนาด")
                        st.markdown("ไฟล์นี้ยังไม่มีมูลค่าทุนตาม S/M/L จึงสรุปจากจำนวนรายแทน")
                        for r in s.itertuples():
                            st.markdown(f"- Size **{r.size}**: **{_fmt_int(r.count)} ราย**")

                    dominant = s.loc[s["count"].idxmax()]
                    st.markdown(f"**ขนาดที่พบมากที่สุด:** Size {dominant['size']} ({_fmt_int(dominant['count'])} ราย)")
                    st.markdown("</div>", unsafe_allow_html=True)

                    total_size_count = s["count"].sum()
                    if total_size_count:
                        cc1, cc2, cc3 = st.columns(3)
                        for col, size in zip([cc1, cc2, cc3], ["S", "M", "L"]):
                            row = s[s["size"] == size]
                            cnt = float(row["count"].sum()) if not row.empty else 0
                            share = cnt / total_size_count * 100 if total_size_count else 0
                            with col:
                                metric_card(f"Size {size}", f"{share:,.1f}%", f"{_fmt_int(cnt)} ราย")

with tab5:
    st.markdown("## Raw Data / ตารางข้อมูล")
    st.caption(data_caption)
    with st.expander("คำอธิบายฟีเจอร์ / Feature Dictionary", expanded=True):
        feature_desc = pd.DataFrame([
            ["province", "จังหวัด"],
            ["year", "ปี พ.ศ."],
            ["month_no", "เลขเดือน (1-12)"],
            ["month", "ชื่อย่อเดือน"],
            ["new_count", "จำนวนธุรกิจจดทะเบียนจัดตั้งใหม่ (ราย)"],
            ["closed_count", "จำนวนธุรกิจเลิกกิจการ (ราย)"],
            ["net_growth", "การเติบโตสุทธิ = new_count - closed_count"],
            ["closure_rate", "อัตราการเลิกกิจการ = closed_count / new_count × 100"],
            ["add_fund_count", "จำนวนนิติบุคคลที่เพิ่มทุน (ราย)"],
            ["active_count", "จำนวนนิติบุคคลที่ดำเนินกิจการอยู่"],
            ["new_capital_m", "มูลค่าทุนจดทะเบียนใหม่ (ล้านบาท)"],
        ], columns=["ฟีเจอร์", "ความหมาย"])
        st.dataframe(feature_desc, use_container_width=True, hide_index=True)

    cols = [
        "province", "year", "month_no", "month", "new_count", "closed_count",
        "net_growth", "closure_rate", "add_fund_count", "active_count", "new_capital_m",
    ]

    st.markdown("### ข้อมูลจังหวัดในเดือนที่เลือก")
    available_view = [c for c in cols if c in view.columns]
    view_show = view[available_view].copy()
    if "new_count" in view_show.columns:
        view_show = view_show.sort_values("new_count", ascending=False)
    st.dataframe(view_show, use_container_width=True, hide_index=True)

    st.markdown("### ข้อมูลรายเดือนของจังหวัดที่เลือก")
    available_pdf = [c for c in cols if c in pdf.columns]
    pdf_show = pdf[available_pdf].copy()
    sort_cols = [c for c in ["year", "month_no"] if c in pdf_show.columns]
    if sort_cols:
        pdf_show = pdf_show.sort_values(sort_cols)
    st.dataframe(pdf_show, use_container_width=True, hide_index=True)
