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
    # 這裡的 DEFAULT_BG_COLOR 假設在頂層已經定義為 #f8f9fa
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
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }}

        /* 讓輸入框和按鈕等元件看起來更現代 */
        div.stButton > button:first-child {{
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.2s ease-in-out;
            box-shadow: 1px 1px 5px rgba(0,0,0,0.1);
        }}
        
        div.stButton > button:first-child:hover {{
            transform: translateY(-1px);
            box-shadow: 2px 2px 8px rgba(0,0,0,0.2);
        }}
        
        /* 覆寫 Streamlit 的主要內容區域背景 */
        .main {{
            background-color: {DEFAULT_BG_COLOR};
            padding-top: 2rem; 
        }}
        /* 針對 Streamlit 頁面最外層的背景 */
        [data-testid="stAppViewContainer"] {{
            background-color: {DEFAULT_BG_COLOR};
        }}
        /* 保持側邊欄為白色，與主內容區分隔，增強視覺層次感 */
        section[data-testid="stSidebar"] {{
            background-color: #ffffff; 
        }}
        
        /* 新增 CSS 規則：強制長文本在欄位內換行，避免重疊 */
        [data-testid*="stHorizontalBlock"] > div > div > div {{
            word-wrap: break-word;
            white-space: normal;
        }}
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)

# --- Firestore Initialization and Authentication (Mandatory for Canvas) ---
@st.cache_resource
def initialize_firestore():
    """Initializes Firestore client and handles authentication using global variables."""
    try:
        # Assuming the environment handles GAE/Cloud Run credentials for firestore.Client()
        db = firestore.Client()
        return db
    except Exception as e:
        st.error(f"Firestore initialization failed: {e}")
        st.stop()
    
db = initialize_firestore()
    
# --- Firestore Helper Functions ---
def get_collection_ref(user_id):
    """Returns the records collection reference for the specific user ID."""
    # Placeholder for __app_id access in Python environment
    app_id = 'streamlit-app' 
    return db.collection(f'artifacts/{app_id}/users/{user_id}/{RECORD_COLLECTION_NAME}')

def get_balance_doc_ref(user_id):
    """Returns the balance document reference for the specific user ID."""
    app_id = 'streamlit-app'
    return db.document(f'artifacts/{app_id}/users/{user_id}/{BALANCE_COLLECTION_NAME}/{BALANCE_DOC_ID}')

def get_data(user_id):
    """Fetches all records and current balance."""
    # Fetch records
    records_ref = get_collection_ref(user_id)
    docs = records_ref.stream()
    
    records = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        # Convert Firestore Timestamp to datetime.date
        if 'date' in data and data['date'] is not None:
             # Ensure conversion handles both datetime objects (from Firestore) and existing date objects
             if isinstance(data['date'], datetime.datetime):
                 data['date'] = data['date'].date()
        records.append(data)

    # Fetch balance
    balance_ref = get_balance_doc_ref(user_id)
    balance_doc = balance_ref.get()
    current_balance = balance_doc.to_dict().get('balance', 0) if balance_doc.exists else 0
    
    df = pd.DataFrame(records)
    if not df.empty:
        # Ensure 'amount' is numeric and 'date' is datetime.date
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df['date'] = pd.to_datetime(df['date']).dt.date
        df.sort_values(by='date', ascending=False, inplace=True)

    return df, current_balance

def add_record(user_id, date, category, amount, type, note, current_balance):
    """Adds a new record and updates the balance."""
    try:
        records_ref = get_collection_ref(user_id)
        balance_ref = get_balance_doc_ref(user_id)
        
        # 1. Add new record
        record_data = {
            'date': datetime.datetime.combine(date, datetime.time.min), # Store as Firestore Timestamp
            'category': category,
            'amount': int(amount),
            'type': type,
            'note': note
        }
        records_ref.add(record_data)

        # 2. Update balance
        new_balance = current_balance
        if type == '收入':
            new_balance += int(amount)
        else:
            new_balance -= int(amount)
        
        balance_ref.set({'balance': new_balance})
        st.success(f"成功新增一筆{type}紀錄！ (餘額更新至: {new_balance:,.0f} 元)")
    except Exception as e:
        st.error(f"新增記錄失敗: {e}")

def delete_record(user_id, record_id, record_type, record_amount, current_balance):
    """Deletes a record and reverses the balance change."""
    try:
        records_ref = get_collection_ref(user_id)
        balance_ref = get_balance_doc_ref(user_id)

        # 1. Delete record
        records_ref.document(record_id).delete()
        
        # 2. Reverse balance update
        new_balance = current_balance
        if record_type == '收入':
            new_balance -= record_amount # If it was income, subtract it back
        else: # type == '支出'
            new_balance += record_amount # If it was expense, add it back
        
        balance_ref.set({'balance': new_balance})
        st.success(f"紀錄已刪除，餘額已恢復！ (餘額更新至: {new_balance:,.0f} 元)")
    except Exception as e:
        st.error(f"刪除記錄失敗: {e}")

# --- Main App Logic ---
def app():
    # 這裡我們使用一個固定的 userId，因為 Streamlit 不直接支援 Firebase Auth，
    # 在 Canvas 環境中，我們假設 userId 已經被處理或為單用戶模式。
    user_id = "default_user_123" 
    
    # 設置 UI 樣式
    set_ui_styles()

    st.title("簡易個人記帳本 💰")

    # 1. 數據獲取與快取 (依賴 Streamlit Rerun 機制來模擬數據刷新)
    df_records, current_balance = get_data(user_id)
    
    st.session_state['current_balance'] = current_balance
    st.session_state['df_records'] = df_records

    # 2. 顯示當前餘額
    st.header("當前餘額")
    st.metric(label="帳戶總餘額", value=f"{st.session_state['current_balance']:,.0f} 元", delta_color="off")
    st.markdown("---")

    # 3. 新增交易區
    st.header("新增交易")
    with st.form("new_transaction", clear_on_submit=True):
        col1, col2 = st.columns(2)
        date = col1.date_input("日期", datetime.date.today())
        type = col2.selectbox("類型", ['支出', '收入'])
        
        col3, col4 = st.columns(2)
        
        # 類別選項
        expense_categories = ['餐飲', '交通', '購物', '娛樂', '住房', '醫療', '教育', '其他支出']
        income_categories = ['薪資', '投資', '獎金', '其他收入']
        
        categories = income_categories if type == '收入' else expense_categories
        category = col3.selectbox("類別", categories)
        
        amount = col4.number_input("金額 (新台幣)", min_value=1, format="%d", value=100)
        
        note = st.text_input("備註 (選填)")
        
        submitted = st.form_submit_button("新增紀錄")
        
        if submitted:
            # 由於 st.session_state['current_balance'] 已經包含了最新的餘額，直接使用它
            if amount is not None and amount > 0:
                 add_record(user_id, date, category, amount, type, note, st.session_state['current_balance'])
                 st.experimental_rerun() # 強制刷新以更新列表和餘額
            else:
                st.error("金額必須大於 0。")

    st.markdown("---")
    
    # 4. 數據分析與交易紀錄區
    if st.session_state['df_records'].empty:
        st.info("目前沒有任何交易紀錄，請新增紀錄。")
        return

    df_records = st.session_state['df_records']

    # 4.1. 篩選器
    st.header("數據分析與篩選")
    
    col_start, col_end, col_cat_filter = st.columns([1, 1, 2])
    
    min_date = df_records['date'].min()
    max_date = df_records['date'].max()

    start_date = col_start.date_input("開始日期", min_date)
    end_date = col_end.date_input("結束日期", max_date)
    
    all_categories = sorted(df_records['category'].unique())
    selected_categories = col_cat_filter.multiselect("篩選類別", all_categories, default=all_categories)
    
    # 應用篩選
    df_filtered = df_records[
        (df_records['date'] >= start_date) & 
        (df_records['date'] <= end_date) &
        (df_records['category'].isin(selected_categories))
    ]

    # 4.2. 期間總覽
    st.subheader("選定期間總覽")
    
    total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
    total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
    net_flow = total_income - total_expense
    
    col_i, col_e, col_n = st.columns(3)
    col_i.metric(label="期間總收入", value=f"{total_income:,.0f} 元", delta_color="off")
    col_e.metric(label="期間總支出", value=f"{total_expense:,.0f} 元", delta_color="off")
    col_n.metric(label="期間淨流量", value=f"{net_flow:,.0f} 元", delta=(f"{net_flow:,.0f}"), delta_color="normal")
    
    st.markdown("---")

    # 4.3. 支出分佈圖
    st.header("支出類別分佈 (圓餅圖)")

    # 僅篩選支出
    expense_df = df_filtered[df_filtered['type'] == '支出'].groupby('category')['amount'].sum().reset_index()
    expense_df.rename(columns={'amount': '總支出'}, inplace=True)
    
    total_expense_sum = expense_df['總支出'].sum()
    
    if total_expense_sum > 0:
        # 1. 創建一個基礎圖表對象
        base = alt.Chart(expense_df).encode(
            theta=alt.Theta("總支出", stack=True)
        )

        # 2. 創建圓餅圖部分 (Pie)
        pie = base.mark_arc(outerRadius=120, innerRadius=50).encode(
            color=alt.Color("category", title="類別"),
            order=alt.Order("總支出", sort="descending"),
            tooltip=["category", alt.Tooltip("總支出", format=',.0f', title='總支出'), alt.Tooltip("總支出", aggregate="sum", format=".1%", title="比例")]
        ).properties(
            title="選定範圍內各類別支出金額分佈"
        )
        
        # 3. 添加文字標籤 (Text)
        # text = base.mark_text(radius=140).encode(
        #     text=alt.Text("總支出", format=",.0f"),
        #     order=alt.Order("總支出", sort="descending"),
        #     color=alt.value("black") 
        # )
        
        # 4. 組合圖表並居中顯示
        chart = pie 
        
        # 為了讓圓餅圖在 Streamlit 內置的容器中能保持正確的寬高比，
        # 這裡設定較為固定的寬高，讓圓形居中顯示。
        st.altair_chart(chart, use_container_width=True)

        # --------------------------------------
        
    else:
        st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # 4.4. 交易紀錄區 (新增刪除按鈕)
    st.header("完整交易紀錄")
    
    # 準備用於顯示和刪除的 DataFrame
    display_df = df_filtered[['date', 'category', 'amount', 'type', 'note', 'id']].copy()
    display_df.rename(columns={
        'date': '日期', 
        'category': '類別', 
        'amount': '金額', 
        'type': '類型', 
        'note': '備註',
        'id': '文件ID' # 保留 ID 用於刪除
    }, inplace=True)
    
    if display_df.empty:
         st.info("在當前篩選條件下，無交易紀錄。")
         return
    
    st.markdown("---")
    
    # 標題列
    # **修正點 1: 調整 HTML 寬度，增加備註欄位的空間 (46%)**
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px; margin-bottom: 5px;'>
            <div style='width: 12%; padding-left: 1rem;'>日期</div>
            <div style='width: 12%;'>類別</div>
            <div style='width: 12%;'>金額</div>
            <div style='width: 8%;'>類型</div>
            <div style='width: 46%;'>備註</div> 
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
            # **修正點 2: 調整 st.columns 比例，增加備註欄位的權重 (5)**
            # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 5, 操作 1] (Sum: 9.9)
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 5, 1])
            
            # 使用 st.write 顯示交易細節
            col_date.write(row['日期'].strftime('%Y-%m-%d'))
            col_cat.write(row['類別'])
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row['金額']:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(row['類型'])
            col_note.write(row['備註']) # 備註內容，給予更多空間避免重疊
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{row['文件ID']}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                delete_record(
                    user_id=user_id,
                    record_id=row['文件ID'],
                    record_type=record_details_for_delete['type'],
                    record_amount=record_details_for_delete['amount'],
                    current_balance=st.session_state['current_balance']
                )
                st.experimental_rerun() # 強制刷新以更新列表和餘額

        st.markdown("<hr style='margin: 0.5rem 0; border-top: 1px solid #eee;'>", unsafe_allow_html=True)


if __name__ == '__main__':
    # Streamlit Page Config MUST be the first command
    st.set_page_config(
        page_title="簡易個人記帳本",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    app()

