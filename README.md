# ThaiBiz AI - Streamlit Multipage App

แอปวิเคราะห์ข้อมูลการจดทะเบียนนิติบุคคลไทยจากไฟล์ CSV ของ DBD เพื่อช่วยผู้ประกอบการดูโอกาส ความเสี่ยง จังหวัดที่น่าลงทุน และประเภทธุรกิจที่เหมาะกับ SME

## Pages

1. **Executive Overview** - KPI ภาพรวม, macro trend, leaderboards, bottom-line insight
2. **Province Intelligence** - วิเคราะห์จังหวัด, net growth, closure rate, opportunity-risk matrix
3. **Business Category** - วิเคราะห์ประเภทธุรกิจ, market demand, SME fit, capital intensity, opportunity score
4. **Business Survival** - วิเคราะห์ความเสี่ยงเลิกกิจการ, risk matrix, YoY risk change, SME risk
5. **DuckDB SQL Explorer** - เขียน SQL วิเคราะห์ข้อมูลเอง พร้อม auto chart และ export CSV
6. **AI Advisor** - ถามคำถามเชิงธุรกิจ พร้อม Gemini optional และ fallback rule-based

## Folder structure

```text
thaibiz_streamlit_app/
├─ app.py
├─ data_loader.py
├─ charts.py
├─ db.py
├─ style.py
├─ requirements.txt
├─ .env.example
├─ data/
│  └─ วางไฟล์ CSV ทั้งหมดที่นี่
└─ pages/
   ├─ 1_Executive_Overview.py
   ├─ 2_Province_Intelligence.py
   ├─ 3_Business_Category.py
   ├─ 4_Business_Survival.py
   ├─ 5_DuckDB_SQL.py
   └─ 6_AI_Advisor.py
```

## Expected data filenames

แอปจะค้นหาไฟล์ CSV โดยดู keyword ในชื่อไฟล์ เช่น

- `จังหวัดจัดตั้งเลิกเพิ่มคง68_มค.csv`, `จังหวัดจัดตั้งเลิกเพิ่มคง69_เมย.csv`
- `ประเภทจัดตั้งเลิกขนาด68_regis.csv`
- `ประเภทจัดตั้งเลิกขนาด68_quit.csv`
- `ประเภทจัดตั้งเลิกขนาด68_active.csv`
- `ประเภทจัดตั้งเลิกขนาด68_size.csv`
- `ประเเภทจัดตั้งเลิกขนาด69_regis.csv`
- `ประเเภทจัดตั้งเลิกขนาด69_quit.csv`
- `ประเเภทจัดตั้งเลิกขนาด69_active_apr.csv`
- `ประเเภทจัดตั้งเลิกขนาด69_size.csv`

> หมายเหตุ: โค้ดรองรับทั้ง `ประเภท` และชื่อที่สะกดเป็น `ประเเภท` ตามไฟล์ที่แนบมา

## Install

```bash
cd thaibiz_streamlit_app
python -m venv myvenv
myvenv\Scripts\activate
pip install -r requirements.txt
```

Mac/Linux:

```bash
python -m venv myvenv
source myvenv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m streamlit run app.py
```

## Optional: Gemini AI

สร้างไฟล์ `.env` ในโฟลเดอร์เดียวกับ `app.py`

```bash
GEMINI_API_KEY=your_key_here
```

ถ้าไม่ใส่ key หน้า AI Advisor จะยังใช้งานได้ด้วย rule-based fallback

## Notes

- ใช้ `st.cache_data` สำหรับ cache dataframe
- ใช้ `st.cache_resource` สำหรับ DuckDB connection
- ใช้ Plotly สำหรับกราฟ interactive
- ใช้ DuckDB สำหรับ SQL query ในหน้า DuckDB SQL Explorer
