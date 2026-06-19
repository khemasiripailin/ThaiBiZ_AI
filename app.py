import streamlit as st
from style import apply_theme, page_header, configure_plotly, metric_card
from data_loader import load_all_data, app_data_status

st.set_page_config(
    page_title="ThaiBiz AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()
configure_plotly()

page_header(
    "📊 ThaiBiz AI",
    "Thailand Business Opportunity Intelligence Dashboard - แปลงข้อมูลจัดตั้ง เลิกกิจการ เงินทุน และขนาดธุรกิจ ให้กลายเป็น insight สำหรับคนที่กำลังจะเริ่มธุรกิจ",
    pills=["Streamlit", "DuckDB", "Plotly", "AI Advisor", "DBD CSV"],
)

data = load_all_data()
prov = data["province_latest"]
biz = data["business_2569"]

c1, c2, c3, c4 = st.columns(4)
if not prov.empty:
    with c1:
        metric_card("New Registrations", f"{prov['new_count'].sum():,.0f}", "รวมจังหวัดล่าสุด")
    with c2:
        metric_card("Deregistrations", f"{prov['closed_count'].sum():,.0f}", "รวมจังหวัดล่าสุด")
    with c3:
        rate = prov['closed_count'].sum() / prov['new_count'].sum() * 100 if prov['new_count'].sum() else 0
        metric_card("Closure Rate", f"{rate:,.2f}%", "เลิก / จัดตั้งใหม่")
    with c4:
        metric_card("Total Capital", f"{prov['new_capital_m'].sum():,.0f} ลบ.", "ทุนจดทะเบียนจัดตั้งใหม่")
else:
    with c1:
        metric_card("Data status", "No province data", "ใส่ CSV ในโฟลเดอร์ data")
    with c2:
        metric_card("Business data", f"{len(biz):,.0f} rows", "ประเภทธุรกิจ")
    with c3:
        metric_card("Tables", f"{len(data)}", "loaded dataframes")
    with c4:
        metric_card("Mode", "Demo-ready", "รอข้อมูลครบ")

st.markdown("### 🧭 Navigation Guide")
cols = st.columns(3)
features = [
    ("📌 Executive Overview", "สรุปภาพรวมธุรกิจไทย: KPI, แนวโน้ม, จังหวัดเด่น, ธุรกิจมาแรง"),
    ("📍 Province Intelligence", "วิเคราะห์จังหวัดที่น่าลงทุนและจังหวัดที่ควรระวัง"),
    ("🏷️ Business Category", "ค้นหาประเภทธุรกิจที่น่าทำจาก demand, SME fit, capital, risk"),
    ("🛡️ Business Survival", "ดูธุรกิจหรือพื้นที่ที่มีความเสี่ยงปิดกิจการสูง"),
    ("🦆 DuckDB SQL", "เขียน SQL วิเคราะห์ข้อมูลเอง พร้อม export ผลลัพธ์"),
    ("🤖 AI Advisor", "ถาม AI เพื่อสรุปคำแนะนำจากข้อมูลจริงใน dashboard"),
]
for i, (name, desc) in enumerate(features):
    with cols[i % 3]:
        st.markdown(f"""
        <div class='glass-card'>
            <h3 style='margin-top:0'>{name}</h3>
            <p style='color:#cbd5e1; line-height:1.55'>{desc}</p>
        </div>
        """, unsafe_allow_html=True)

with st.expander("📂 Data files detected"):
    st.dataframe(app_data_status(), use_container_width=True, hide_index=True)

st.sidebar.success("เลือกหน้าจากเมนูด้านบน/ซ้ายเพื่อเริ่มวิเคราะห์")
with st.sidebar:
    if st.button("🔄 Reload data / Clear cache"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()