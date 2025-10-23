import streamlit as st
import pandas as pd
import datetime
import altair as alt 
from google.cloud import firestore

# --- 0. 配置與變數 ---
DEFAULT_BG_COLOR = "#f8f9fa" 
RECORD_COLLECTION_NAME = "records"       # 交易紀錄 Collection 名稱
BALANCE_COLLECTION_NAME = "account_status" # 餘額 Collection 名稱
BALANCE_DOC_ID = "current_balance"       # 餘額文件 ID，固定單一文件

# --- 1. Streamlit 介面設定 ---
def set_ui_styles():
    """注入客製化 CSS，設定字體、簡約背景色和排版"""
    css = f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

        /* 設置字體與基礎大小 */
        html, body, [class*="st-"] {{
            font-family: 'Inter', "PingFang TC", "Microsoft YaHei", sans-serif;
            font-size: 15px; 
        }}
        
        /* 設定主標題 H1 字體大小 */
        h1 {{
            font-size: 1.8rem;
            font-weight: 700;
            color: #343a40;
            margin-bottom: 2.5rem; 
        }}
        
        /* 設定區塊標題 H2 */
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
        .main, [data-testid="stAppViewContainer"] {{
            background-color: {DEFAULT_BG_COLOR};
        }}
        
        /* 按鈕樣式 */
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
        
        /* 餘額卡片樣式 */
        .balance-card {{
            background-color: #ffffff;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            text-align: center;
        }}
        .balance-label {{
            font-size: 1.1rem;
            color: #6c757d;
            margin-bottom: 5px;
        }}
        .balance-value {{
            font-size: 2.5rem;
            font-weight: 700;
            color: #28a745; /* 預設綠色 */
        }}
        .balance-negative {{
            color: #dc3545; /* 負數紅色 */
        }}
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)


# --- 2. Firestore 連線與資源快取 ---

@st.cache_resource(ttl=None)
def get_firestore_db():
    """初始化並連線到 Firestore。"""
    try:
        creds = st.secrets["firestore"]
        db = firestore.Client.from_service_account_info(creds)
        return db
    except Exception as e:
        st.error(f"連線 Firestore 失敗，請檢查 .streamlit/secrets.toml 檔案: {e}")
        st.stop()
        return None

# --- 3. 數據快取與讀取 (交易紀錄) ---

@st.cache_data(ttl=3600)
def get_all_records():
    """從 Firestore 取得所有交易紀錄並轉換為 DataFrame。"""
    db = get_firestore_db() 
    
    # 定義一個空的、結構正確的 DataFrame 模板 (防止 .dt 錯誤)
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
        docs = db.collection(RECORD_COLLECTION_NAME).stream()
        
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id
            
            # 將 Firestore Timestamp 轉換為 Python datetime
            if 'date' in record and hasattr(record['date'], 'to_datetime'):
                record['date'] = record['date'].to_datetime()
            
            records.append(record)
            
        
        if not records:
            return empty_df_template
        
        df = pd.DataFrame(records)
        
        # 強制轉換 'date' 欄位為 datetime 類型
        df['date'] = pd.to_datetime(df['date'], errors='coerce') 
        df['amount'] = pd.to_numeric(df['amount'])
            
        df.dropna(subset=['date', 'amount'], inplace=True) # 移除無效日期或金額的紀錄
            
        df.sort_values(by='date', ascending=False, inplace=True)
        df.reset_index(drop=True, inplace=True)
            
        return df
        
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        return empty_df_template

# --- 4. 數據快取與讀取 (帳戶餘額) ---

@st.cache_data(ttl=3600)
def get_account_balance():
    """從 Firestore 取得當前總餘額，如果文件不存在則返回 0.0。"""
    db = get_firestore_db()
    if db is None: 
        return 0.0
    
    try:
        doc_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
        doc = doc_ref.get()
        if doc.exists:
            # 確保返回的是 float 類型
            return float(doc.to_dict().get('balance', 0.0))
        return 0.0
    except Exception as e:
        st.error(f"讀取帳戶餘額失敗: {e}")
        return 0.0

# --- 5. 寫入操作 (餘額更新是核心) ---

def update_account_balance(db, new_balance):
    """更新 Firestore 中的帳戶總餘額並清除快取。"""
    try:
        db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID).set(
            {
                'balance': float(new_balance), 
                'last_updated': firestore.SERVER_TIMESTAMP
            }
        )
        # 清除餘額快取，確保下次 get_account_balance 獲取最新值
        get_account_balance.clear() 
        return True
    except Exception as e:
        st.error(f"更新餘額失敗: {e}")
        return False

def add_record_and_update_balance(db, data, current_balance):
    """將新的交易紀錄寫入 Firestore，並根據交易類型更新餘額。"""
    
    new_amount = data['amount']
    is_income = data['type'] == '收入'
    
    # 1. 計算新的餘額
    new_balance = current_balance + new_amount if is_income else current_balance - new_amount
    
    try:
        # 2. 新增紀錄
        db.collection(RECORD_COLLECTION_NAME).add(data) 
        
        # 3. 更新帳戶餘額 (如果紀錄新增成功)
        update_account_balance(db, new_balance)
        
        # 4. 清除紀錄快取，以刷新交易列表
        get_all_records.clear()
        
        st.success("成功新增交易紀錄並更新餘額！")
    except Exception as e:
        st.error(f"新增交易紀錄失敗: {e}")

def delete_record_and_update_balance(db, doc_id, current_balance, record_details):
    """刪除指定的交易紀錄，並反向更新餘額。"""
    
    amount_to_reverse = record_details['amount']
    is_income = record_details['type'] == '收入'

    # 1. 反向計算新的餘額
    # 如果刪除收入 (餘額應該減少)，如果刪除支出 (餘額應該增加)
    if is_income:
        new_balance = current_balance - amount_to_reverse
    else:
        new_balance = current_balance + amount_to_reverse

    try:
        # 2. 刪除文件
        db.collection(RECORD_COLLECTION_NAME).document(doc_id).delete()
        
        # 3. 更新帳戶餘額 (如果刪除成功)
        update_account_balance(db, new_balance)

        # 4. 清除紀錄快取
        get_all_records.clear() 
        
        st.success("成功刪除交易紀錄並反向更新餘額！")
    except Exception as e:
        st.error(f"刪除交易紀錄失敗: {e}")


# --- 6. Streamlit App 主函數 ---

def main():
    """主應用程式邏輯。"""
    set_ui_styles()
    st.title("家庭記帳本 📊")

    # 1. 初始化 Firestore Client
    db = get_firestore_db() 
    if db is None:
        st.stop()

    # 2. 獲取當前餘額 (使用快取)
    current_balance = get_account_balance()
    
    # 餘額初始化檢查（如果餘額為 0 且沒有紀錄，詢問是否初始化）
    if current_balance == 0.0 and len(get_all_records()) == 0:
        st.warning("歡迎使用！您的帳戶餘額目前為零，請設定初始金額或新增第一筆紀錄。")
        with st.expander("設定初始帳戶餘額"):
            with st.form("initial_balance_form"):
                initial_amount = st.number_input("初始金額 (NT$)", min_value=0, step=1000, value=0, key='initial_amount_input')
                submitted_init = st.form_submit_button("設定餘額並開始記帳")
                
                if submitted_init:
                    if initial_amount > 0:
                        update_account_balance(db, initial_amount)
                        st.success(f"初始餘額已設定為 NT$ {initial_amount:,.0f}！")
                    st.rerun()

    # 3. 顯示總餘額卡片
    balance_color_class = "balance-negative" if current_balance < 0 else ""
    st.markdown(
        f"""
        <div class="balance-card">
            <div class="balance-label">當前帳戶總餘額</div>
            <div class="balance-value {balance_color_class}">NT$ {current_balance:,.0f}</div>
        </div>
        """, unsafe_allow_html=True
    )
    st.markdown("---")

    # 4. 側邊欄：新增交易
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
            
            amount_val = st.number_input("金額 (NT$)", min_value=1, step=1, format="%d", value=100, key='new_record_amount')
            date_val = st.date_input("日期", datetime.date.today(), key='new_record_date')
            note_val = st.text_area("備註", max_chars=100, key='new_record_note')
            
            submitted = st.form_submit_button("💾 儲存紀錄並更新餘額")
            
            if submitted:
                # 準備寫入 Firestore 的數據
                new_data = {
                    'type': type_val,
                    'category': category_val,
                    'amount': int(amount_val),
                    # 儲存為 Firestore Timestamp 類型
                    'date': datetime.datetime.combine(date_val, datetime.time.min), 
                    'note': note_val,
                    'created_at': firestore.SERVER_TIMESTAMP 
                }
                
                # 新增紀錄並自動更新餘額
                add_record_and_update_balance(db, new_data, current_balance) 
                st.rerun() # 儲存後重新執行，以刷新數據

    # 5. 主頁面：數據分析與展示
    df_records = get_all_records()
    
    if df_records.empty:
        # 如果經過初始化檢查後仍然沒有紀錄，則結束
        return 

    st.header("數據總覽")
    
    # 5.1. 篩選控制項
    min_year = df_records['date'].dt.year.min()
    max_year = df_records['date'].dt.year.max()
    current_year = datetime.date.today().year
    
    year_options = sorted(list(range(min(min_year, current_year), max(max_year, current_year) + 1)), reverse=True)
    
    # 設置預設年份為數據中最新年份
    default_year_index = year_options.index(max_year) if max_year in year_options else 0
    default_month = datetime.date.today().month
    
    col_year, col_month = st.columns(2)
    
    selected_year = col_year.selectbox("選擇年份", year_options, 
                                       index=default_year_index, 
                                       key="year_select")
    
    selected_month = col_month.selectbox("選擇月份", range(1, 13), 
                                         format_func=lambda x: f"{x} 月", 
                                         index=default_month - 1, 
                                         key="month_select")
    
    
    # 5.2. 根據選擇進行數據篩選
    df_filtered = df_records[
        (df_records['date'].dt.year == selected_year) & 
        (df_records['date'].dt.month == selected_month)
    ].copy()
    
    # 5.3. 財務摘要 (僅限當月)
    total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
    total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
    net_balance_month = total_income - total_expense

    st.markdown(f"### 💸 {selected_year} 年 {selected_month} 月 財務摘要")
    col1, col2, col3 = st.columns(3)
    
    col1.metric("當月總收入", f"NT$ {total_income:,.0f}", delta_color="off")
    col2.metric("當月總支出", f"NT$ {total_expense:,.0f}", delta_color="off")
    col3.metric("當月淨結餘", f"NT$ {net_balance_month:,.0f}", 
                delta=f"{net_balance_month:,.0f}", 
                delta_color=("inverse" if net_balance_month < 0 else "normal"))

    st.markdown("---")

    # 5.4. 支出分佈圖
    st.header("支出分佈圖 (圓餅圖)")
    expense_data = df_filtered[df_filtered['type'] == '支出'].groupby('category')['amount'].sum().reset_index()
    
    if total_expense > 0 and not expense_data.empty:
        expense_data['percentage'] = (expense_data['amount'] / total_expense) * 100
        
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
            title=f"{selected_year}年{selected_month}月 支出分佈"
        ).interactive()
        
        st.altair_chart(chart, use_container_width=True)

    else:
        st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # 5.5. 交易紀錄區 (數據列)
    st.header("完整交易紀錄")
    
    display_df = df_filtered[['date', 'category', 'amount', 'type', 'note', 'id']].copy()
    display_df.rename(columns={
        'date': '日期', 'category': '類別', 'amount': '金額', 
        'type': '類型', 'note': '備註', 'id': '文件ID' 
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
        # 這裡需要從完整的 df_records 中取得交易細節用於反向計算餘額
        record_details_for_delete = df_records[df_records['id'] == row['文件ID']].iloc[0].to_dict()
        
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
                # 執行刪除並更新餘額
                delete_record_and_update_balance(db, row['文件ID'], current_balance, record_details_for_delete)
                st.rerun() 
                

if __name__ == "__main__":
    main()
