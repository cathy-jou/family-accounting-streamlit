import streamlit as st
import pandas as pd
import datetime
import altair as alt 
from google.cloud import firestore

# --- 0. Streamlit 介面設定 (字體 Inter) ---

# 設定固定的淺灰色背景
DEFAULT_BG_COLOR = "#f8f9fa" 
COLLECTION_NAME = "records" # 假設交易紀錄儲存在名為 'records' 的 Collection 中

def set_ui_styles():
    """注入客製化 CSS，設定字體、簡約背景色和縮小主標題字體與調整間距"""
    css = f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

        /* 設置字體與基礎大小 (略微縮小基礎字體) */
        html, body, [class*="st-"] {{
            font-family: 'Inter', "PingFang TC", "Microsoft YaHei", sans-serif;
            font-size: 15px; /* 調整基礎字體大小 */
        }}
        
        /* 設定主標題 H1 字體大小並增加間距 */
        h1 {{
            font-size: 1.8rem; /* 將字體微縮 */
            font-weight: 700;
            color: #343a40; /* 深灰色字體 */
            margin-bottom: 2.5rem; /* 拉大與下方內容的間距 */
        }}
        
        /* 設定區塊標題 H2 (st.header) 字體大小並增加間距 */
        h2 {{
            font-size: 1.5rem; 
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 0.5rem;
            margin-top: 1.5rem;
            margin-bottom: 1.5rem;
        }}

        /* 設定背景顏色 */
        .main {{
            background-color: {DEFAULT_BG_COLOR};
            padding-top: 2rem; 
        }}
        [data-testid="stAppViewContainer"] {{
            background-color: {DEFAULT_BG_COLOR};
        }}
        /* 側邊欄 */
        section[data-testid="stSidebar"] {{
            background-color: #ffffff; 
            box-shadow: 2px 0 5px rgba(0,0,0,0.05);
        }}
        
        /* 按鈕、輸入框等現代化樣式 */
        div.stButton > button:first-child {{
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 15px;
            transition: all 0.2s;
        }}
        div.stButton > button:first-child:hover {{
            background-color: #0056b3;
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }}
        
        /* 資料輸入欄位 */
        div[data-testid="stTextInput"], div[data-testid="stSelectbox"], div[data-testid="stDateInput"], div[data-testid="stNumberInput"] {{
            margin-bottom: 1rem;
        }}

        /* Streamlit 訊息方塊 */
        div[data-testid="stNotification"] {{
            border-radius: 8px;
        }}
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)


# --- 1. Firestore 連線與操作 ---

@st.cache_resource(ttl=None) # 確保資源(連線)只初始化一次，且永不過期
def get_firestore_db():
    """
    初始化並連線到 Firestore。
    @st.cache_resource 確保只建立一次連線。
    """
    try:
        # 從 Streamlit secrets 載入 Firebase 服務帳戶憑證
        creds = st.secrets["firestore"]
        
        # 使用憑證初始化 Firestore 客戶端
        db = firestore.Client.from_service_account_info(creds)
        
        return db
    except Exception as e:
        st.error(f"連線 Firestore 失敗，請檢查 .streamlit/secrets.toml 檔案: {e}")
        st.stop()
        return None


@st.cache_data(ttl=3600) # 快取資料 1 小時 (3600 秒)
def get_all_records():
    """
    從 Firestore 取得所有交易紀錄並轉換為 DataFrame。
    這個函數不再接受 'db' 參數。
    """
    db = get_firestore_db() 
    
    # 定義一個空的、結構正確的 DataFrame 模板
    empty_df_template = pd.DataFrame({
        'date': pd.Series([], dtype='datetime64[ns]'),
        'category': pd.Series([], dtype='object'),
        'amount': pd.Series([], dtype='float'),
        'type': pd.Series([], dtype='object'),
        'note': pd.Series([], dtype='object'),
        'id': pd.Series([], dtype='object')
    })
    
    if db is None:
        return empty_df_template

    records = []
    try:
        # 取得集合中的所有文件
        docs = db.collection(COLLECTION_NAME).stream()
        
        for doc in docs:
            # 取得文件資料並包含文件 ID
            record = doc.to_dict()
            record['id'] = doc.id
            
            # 轉換 Firestore Timestamp/Date 物件為標準 Python datetime
            if 'date' in record and hasattr(record['date'], 'to_datetime'):
                record['date'] = record['date'].to_datetime()
            
            records.append(record)
            
        
        if not records:
            # 如果沒有紀錄，返回結構正確的空 DataFrame
            return empty_df_template
        
        # 轉換為 DataFrame
        df = pd.DataFrame(records)
        
        # 【關鍵修正 1】使用 errors='coerce' 確保轉換成功，強制設定 'date' 為 datetime 類型。
        # 無效的日期會被轉換為 NaT (Not a Time)。
        df['date'] = pd.to_datetime(df['date'], errors='coerce') 
        df['amount'] = pd.to_numeric(df['amount'])
            
        # 移除任何因為轉換錯誤而產生的 NaT (Not a Time) 紀錄，以避免篩選錯誤
        df.dropna(subset=['date'], inplace=True)
            
        df.sort_values(by='date', ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)
            
        return df
        
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        return empty_df_template


# --- 2. 資料新增/刪除/更新操作 ---

def add_record(db, data):
    """將新的交易紀錄寫入 Firestore。"""
    try:
        # 使用 firestore.client.base_client.datetime.date 確保日期格式正確
        # 由於我們在 main 中已經轉換為 datetime.datetime，這裡確保是正確的日期類型
        if 'date' in data:
            data['date'] = data['date'].date() # 寫入 Firestore 時只保留日期部分 (date object)
            
        db.collection(COLLECTION_NAME).add(data)
        st.success("成功新增交易紀錄！")
        # 成功新增後，清除快取，以便重新載入最新資料
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"新增交易紀錄失敗: {e}")

def delete_record(db, doc_id):
    """從 Firestore 刪除指定的交易紀錄。"""
    try:
        db.collection(COLLECTION_NAME).document(doc_id).delete()
        st.success("成功刪除交易紀錄！")
        # 成功刪除後，清除快取
        st.cache_data.clear() 
    except Exception as e:
        st.error(f"刪除交易紀錄失敗: {e}")


# --- 3. Streamlit App 主函數 ---

def main():
    """主應用程式邏輯。"""
    set_ui_styles()

    st.title("家庭記帳本 📊")

    # 1. 初始化 Firestore Client
    db = get_firestore_db() 
    
    if db is None:
        st.stop()

    # 2. 數據讀取 (已修正為不傳遞 db 參數)
    df_records = get_all_records() 
    
    
    # 3. 側邊欄：新增交易
    with st.sidebar:
        st.header("新增交易")
        
        CATEGORIES = ['餐飲', '交通', '購物', '娛樂', '住房', '醫療', '教育', '收入', '其他']
        
        with st.form("new_record_form", clear_on_submit=True):
            type_val = st.radio("類型", ["支出", "收入"], horizontal=True, key='new_record_type')
            
            if type_val == "支出":
                category_options = [c for c in CATEGORIES if c != '收入']
                default_category = '餐飲'
            else:
                category_options = ['收入']
                default_category = '收入'
                
            category_val = st.selectbox("類別", category_options, index=category_options.index(default_category), key='new_record_category')
            
            amount_val = st.number_input("金額 (NT$)", min_value=1, step=100, format="%d", value=100, key='new_record_amount')
            date_val = st.date_input("日期", datetime.date.today(), key='new_record_date')
            note_val = st.text_area("備註", max_chars=100, key='new_record_note')
            
            submitted = st.form_submit_button("💾 儲存紀錄")
            
            if submitted:
                new_data = {
                    'type': type_val,
                    'category': category_val,
                    'amount': int(amount_val),
                    'date': datetime.datetime.combine(date_val, datetime.time.min), # 暫時用 datetime 方便寫入
                    'note': note_val,
                    'created_at': firestore.SERVER_TIMESTAMP 
                }
                
                add_record(db, new_data) 
                st.rerun() # 儲存後重新執行，以刷新數據

    # 4. 主頁面：數據分析與展示
    
    if df_records.empty:
        st.info("目前沒有任何交易紀錄，請在側邊欄新增第一筆紀錄。")
        return # 如果是空 DataFrame 則停止後續操作

    st.header("數據總覽")
    
    # 4.1. 篩選控制項
    
    # 確保只有在有數據時才計算這些值
    min_year = df_records['date'].dt.year.min()
    max_year = df_records['date'].dt.year.max()
    current_year = datetime.date.today().year
    
    # 確保選項範圍包含當前年份，且至少從 min_year 開始
    year_options = sorted(list(range(min(min_year, current_year), max(max_year, current_year) + 1)), reverse=True)
    
    # 設置預設年份為數據中最新年份
    default_year_index = year_options.index(max_year) if max_year in year_options else 0
    
    col_year, col_month = st.columns(2)
    
    selected_year = col_year.selectbox("選擇年份", year_options, 
                                       index=default_year_index, 
                                       key="year_select")
    
    # 設置預設月份為當前月份 (如果當前年份有數據)
    default_month = datetime.date.today().month
    selected_month = col_month.selectbox("選擇月份", range(1, 13), 
                                         format_func=lambda x: f"{x} 月", 
                                         index=default_month - 1, # index 從 0 開始
                                         key="month_select")
    
    
    # 4.2. 根據選擇進行數據篩選
    # 這裡現在是安全的，因為 df_records['date'] 已經確定是 datetime 類型
    df_filtered = df_records[
        (df_records['date'].dt.year == selected_year) & 
        (df_records['date'].dt.month == selected_month)
    ].copy()
    
    # 4.3. 總覽卡片
    total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
    total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
    net_balance = total_income - total_expense

    st.markdown(f"### 💸 {selected_year} 年 {selected_month} 月 財務摘要")
    col1, col2, col3 = st.columns(3)
    
    col1.metric("總收入", f"NT$ {total_income:,.0f}", delta_color="off")
    col2.metric("總支出", f"NT$ {total_expense:,.0f}", delta_color="off")
    col3.metric("淨結餘", f"NT$ {net_balance:,.0f}", 
                delta=f"{net_balance:,.0f}", 
                delta_color=("inverse" if net_balance < 0 else "normal"))

    st.markdown("---")

    # 4.4. 支出分佈圖 (圓餅圖)
    st.header("支出分佈圖 (圓餅圖)")
    expense_data = df_filtered[df_filtered['type'] == '支出'].groupby('category')['amount'].sum().reset_index()
    
    if total_expense > 0 and not expense_data.empty:
        expense_data['percentage'] = (expense_data['amount'] / total_expense) * 100
        
        # 使用 Altair 內建的顏色方案
        color_scale = alt.Scale(domain=expense_data['category'].tolist(), range=alt.Scheme('category10').range)

        pie = alt.Chart(expense_data).mark_arc(outerRadius=120).encode(
            theta=alt.Theta("amount", stack=True), 
            color=alt.Color("category", title="類別", scale=color_scale), 
            order=alt.Order("percentage", sort="descending"),
            tooltip=['category', alt.Tooltip('amount', format=',.0f', title='總支出'), alt.Tooltip('percentage', format='.1f', title='比例 (%)')]
        )
        
        text = alt.Chart(expense_data).mark_text(radius=140).encode(
            theta=alt.Theta("amount", stack=True),
            order=alt.Order("percentage", sort="descending"),
            text=alt.Text("percentage", format=".1f%"), 
            color=alt.value("black") 
        )
     
        chart = (pie + text).properties(
            title="選定範圍內各類別支出金額分佈"
        ).interactive()
        
        st.altair_chart(chart, use_container_width=True)

    else:
        st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # 4.5. 交易紀錄區
    st.header("完整交易紀錄")
    
    display_df = df_filtered[['date', 'category', 'amount', 'type', 'note', 'id']].copy()
    display_df.rename(columns={
        'date': '日期', 
        'category': '類別', 
        'amount': '金額', 
        'type': '類型', 
        'note': '備註',
        'id': '文件ID' 
    }, inplace=True)
    
    st.markdown(f"**共找到 {len(display_df)} 筆紀錄。**")
    
    # 標題列
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px;'>
            <div style='width: 15%; padding-left: 1rem;'>日期</div>
            <div style='width: 15%;'>類別</div>
            <div style='width: 15%;'>金額</div>
            <div style='width: 10%;'>類型</div>
            <div style='width: 35%;'>備註</div>
            <div style='width: 10%; text-align: center;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    for index, row in display_df.iterrows():
        color = "#28a745" if row['類型'] == '收入' else "#dc3545"
        amount_sign = "+" if row['類型'] == '收入' else "-"
        
        with st.container():
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 3, 0.8])
            
            col_date.write(row['日期'].strftime('%Y-%m-%d'))
            col_cat.write(row['類別'])
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row['金額']:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(row['類型'])
            col_note.write(row['備註'])
            
            delete_key = f"delete_btn_{row['文件ID']}"
            if col_btn_action.button("🗑️", key=delete_key, help="刪除此筆交易紀錄"):
                delete_record(db, row['文件ID'])
                st.rerun() 
                

if __name__ == "__main__":
    main()