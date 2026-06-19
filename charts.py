from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from style import fig_layout, COLORWAY


def bar_top(df: pd.DataFrame, x: str, y: str, title: str, n: int = 10, color: str | None = None, text: str | None = None):
    data = df.dropna(subset=[x, y]).copy()
    data = data.sort_values(x, ascending=True).tail(n)
    fig = px.bar(data, x=x, y=y, orientation="h", color=color, text=text or x, color_discrete_sequence=COLORWAY)
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False)
    return fig_layout(fig, title=title, height=max(380, n * 33 + 120), showlegend=color is not None)


def line_trend(df: pd.DataFrame, title: str):
    if df.empty:
        return go.Figure()
    monthly = df.groupby(["year", "month_no", "month"], as_index=False)[["new_count", "closed_count", "add_fund_count"]].sum()
    monthly["period"] = monthly["month"] + " " + monthly["year"].astype(str)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=monthly["period"], y=monthly["new_count"], mode="lines+markers", name="จัดตั้งใหม่", line=dict(width=3)))
    fig.add_trace(go.Scatter(x=monthly["period"], y=monthly["closed_count"], mode="lines+markers", name="เลิกกิจการ", line=dict(width=3)))
    if monthly["add_fund_count"].sum() > 0:
        fig.add_trace(go.Scatter(x=monthly["period"], y=monthly["add_fund_count"], mode="lines+markers", name="เพิ่มทุน", line=dict(width=2, dash="dot")))
    return fig_layout(fig, title=title, height=430)


def donut(df: pd.DataFrame, names: str, values: str, title: str):
    data = df.copy()
    fig = px.pie(data, names=names, values=values, hole=.62, color_discrete_sequence=COLORWAY)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig_layout(fig, title=title, height=390)


def risk_scatter(df: pd.DataFrame, title: str, label_col: str = "type"):
    data = df.copy()
    data = data[(data["regis_count"] >= 1)]
    if data.empty:
        return go.Figure()
    data["bubble"] = np.sqrt(data.get("regis_capital_m", 0).clip(lower=0) + 1)
    fig = px.scatter(
        data,
        x="regis_count",
        y="closure_rate",
        size="bubble",
        color="business_group" if "business_group" in data.columns else None,
        hover_name=label_col,
        hover_data={"bubble": False, "regis_count": ":,.0f", "closure_rate": ":.2f", "opportunity_score": ":.1f" if "opportunity_score" in data.columns else False},
        size_max=38,
        color_discrete_sequence=COLORWAY,
    )
    fig.add_hline(y=float(data["closure_rate"].median()), line_dash="dash", opacity=.45)
    fig.add_vline(x=float(data["regis_count"].median()), line_dash="dash", opacity=.45)
    return fig_layout(fig, title=title, height=520)


def province_scatter(df: pd.DataFrame, title: str):
    data = df.copy()
    if data.empty:
        return go.Figure()
    data["bubble"] = np.sqrt(data["active_count"].clip(lower=0) + 1)
    fig = px.scatter(
        data,
        x="new_count",
        y="closure_rate",
        size="bubble",
        color="net_growth",
        hover_name="province",
        hover_data={"bubble": False, "new_count": ":,.0f", "closed_count": ":,.0f", "closure_rate": ":.2f", "net_growth": ":,.0f"},
        color_continuous_scale="Viridis",
        size_max=40,
    )
    fig.add_hline(y=float(data["closure_rate"].median()), line_dash="dash", opacity=.45)
    fig.add_vline(x=float(data["new_count"].median()), line_dash="dash", opacity=.45)
    return fig_layout(fig, title=title, height=500)


def stacked_sme(df: pd.DataFrame, title: str, n: int = 10):
    data = df[df["size_total_count"] > 0].copy().sort_values("regis_count", ascending=False).head(n)
    if data.empty:
        return go.Figure()
    data["S"] = data["size_s_count"] / data["size_total_count"] * 100
    data["M"] = data["size_m_count"] / data["size_total_count"] * 100
    data["L"] = data["size_l_count"] / data["size_total_count"] * 100
    fig = go.Figure()
    for col in ["S", "M", "L"]:
        fig.add_trace(go.Bar(y=data["type"], x=data[col], name=col, orientation="h", text=data[col].round(1), texttemplate="%{text}%"))
    fig.update_layout(barmode="stack", xaxis_title="สัดส่วน (%)", yaxis_title="")
    return fig_layout(fig, title=title, height=max(420, n * 36 + 150))
