import streamlit as st
import pandas as pd
import datetime
import altair as alt 
from google.cloud import firestore
import uuid # 導入 uuid 庫用於生成唯一 ID

# --- 0. 配置與變數 ---
DEFAULT_BG_COLOR = "#f8f9fa" 
RECORD_COLLECTION_NAME = "records"       # 交易紀錄 Collection 名稱
BALANCE_COLLECTION_NAME = "account_status" # 餘額 Collection 名稱
BALANCE_DOC_ID = "current_balance"       # 餘額文件 ID，固定單一文件

# 定義交易類別
CATEGORIES = {
    '收入': ['薪資', '投資收益', '禮金', '其他收入'],
    '支出': ['餐飲', '交通', '購物', '娛樂', '房租/貸款', '教育', '醫療', '其他支出']
}

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
            margin-top: 2rem;
            margin-bottom: 1.5rem;
            border-left: 5px solid #007bff; /* 左側藍色線條裝飾 */
            padding-left: 10px;
        }}
        
        /* 統一背景色 */
        .stApp {{
            background-color: {DEFAULT_BG_COLOR};
        }}

        /* 調整 Streamlit 的 input/select 樣式，使其更簡潔 */
        .stTextInput > div > div > input, 
        .stSelectbox > div > div,
        .stDateInput > label + div > div {{
            border-radius: 8px;
            border: 1px solid #ced4da;
            padding: 8px 12px;
        }}
        
        /* 主要按鈕樣式 */
        .stButton button {{
            border-radius: 8px;
            padding: 8px 15px;
            font-weight: 600;
        }}
        
        /* 調整列間距 */
        .st-emotion-cache-p5mhr9 {{ /* 針對 Streamlit 內部 column 容器的 CSS 類別 */
            gap: 1rem;
        }}
        
        /* 餘額卡片樣式 */
        .balance-card {{
            background-color: #ffffff;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
            text-align: center;
        }}
        .balance-label {{
            font-size: 1.1rem;
            color: #6c757d;
            margin-bottom: 5px;
        }}
        .balance-amount {{
            font-size: 2.5rem;
            font-weight: 700;
            color: #007bff; /* 藍色 */
        }}

        </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# --- 2. Firestore 互動函數 ---

def get_current_balance(db, user_id):
    """從 Firestore 獲取當前餘額，如果不存在則初始化為 0。"""
    app_id = st.session_state.app_id
    doc_path = f"artifacts/{app_id}/users/{user_id}/{BALANCE_COLLECTION_NAME}/{BALANCE_DOC_ID}"
    doc_ref = db.document(doc_path)
    
    try:
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0)
        else:
            # 文件不存在，初始化餘額
            doc_ref.set({'balance': 0, 'last_updated': firestore.SERVER_TIMESTAMP})
            return 0
    except Exception as e:
        st.error(f"獲取/初始化餘額時發生錯誤: {e}")
        return 0

def update_balance(db, user_id, amount_change):
    """更新餘額文件。"""
    app_id = st.session_state.app_id
    doc_path = f"artifacts/{app_id}/users/{user_id}/{BALANCE_COLLECTION_NAME}/{BALANCE_DOC_ID}"
    doc_ref = db.document(doc_path)
    
    try:
        doc_ref.update({
            'balance': firestore.firestore.Increment(amount_change),
            'last_updated': firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        # 如果是文件不存在的錯誤，則嘗試 set 重新創建 (通常發生在第一次交易時)
        if "NOT_FOUND" in str(e):
             # 重新嘗試獲取當前餘額並進行 set
            current_balance = get_current_balance(db, user_id)
            doc_ref.set({
                'balance': current_balance + amount_change,
                'last_updated': firestore.SERVER_TIMESTAMP
            })
        else:
            st.error(f"更新餘額時發生錯誤: {e}")

def add_record(db, user_id, data):
    """新增一筆交易紀錄。"""
    app_id = st.session_state.app_id
    collection_path = f"artifacts/{app_id}/users/{user_id}/{RECORD_COLLECTION_NAME}"
    
    try:
        # 紀錄的 ID 由 uuid.uuid4() 生成，以確保 Streamlit 重新執行時 ID 不變
        doc_id = str(uuid.uuid4())
        doc_ref = db.collection(collection_path).document(doc_id)
        
        # 將 ID 加入數據中以供後續操作使用
        data['id'] = doc_id 
        data['created_at'] = firestore.SERVER_TIMESTAMP
        
        doc_ref.set(data)
        return doc_id
    except Exception as e:
        st.error(f"新增交易紀錄時發生錯誤: {e}")
        return None

def delete_record(db, user_id, record_id, record_type, record_amount, current_balance):
    """刪除一筆交易紀錄並反向更新餘額。"""
    app_id = st.session_state.app_id
    doc_path = f"artifacts/{app_id}/users/{user_id}/{RECORD_COLLECTION_NAME}/{record_id}"
    doc_ref = db.document(doc_path)
    
    # 計算餘額變動
    # 如果原始紀錄是收入，則刪除時餘額減少；如果是支出，則刪除時餘額增加。
    amount_change = -record_amount if record_type == '收入' else record_amount
    
    try:
        # 1. 刪除紀錄
        doc_ref.delete()
        
        # 2. 更新餘額
        # 直接使用 update_balance 函數，傳入負向變動
        update_balance(db, user_id, amount_change)
        
        st.toast(f"成功刪除交易紀錄並更新餘額！", icon="✅")
        # 刷新 Streamlit 頁面以重新載入數據
        st.rerun() 
        
    except Exception as e:
        st.error(f"刪除交易紀錄時發生錯誤: {e}")


def get_all_records(db, user_id):
    """從 Firestore 獲取所有交易紀錄，並返回 DataFrame。"""
    app_id = st.session_state.app_id
    
    # 使用正確的 Firestore 集合路徑
    collection_path = f"artifacts/{app_id}/users/{user_id}/{RECORD_COLLECTION_NAME}"
    
    # 查詢並排序
    # 這裡假設 'date' 欄位存在且是 Firestore Timestamp 或 datetime 物件
    records_ref = db.collection(collection_path).order_by('date', direction=firestore.Query.DESCENDING)

    records = []
    try:
        # **修正點: 將 stream() 替換為 get() 來避免潛在的 'method' object 錯誤**
        # get() 返回一個 DocumentSnapshot 列表，通常更穩定，且不涉及複雜的 transaction 邏輯
        snapshots = records_ref.get() 
        for doc in snapshots:
            record = doc.to_dict()
            record['id'] = doc.id # 加入文件 ID
            
            # 將 Firestore Timestamp 轉換為 Python datetime.date
            if 'date' in record:
                if hasattr(record['date'], 'toDate'): # 檢查是否為 Firestore Timestamp (Python SDK)
                    record['date'] = record['date'].toDate().date()
                elif isinstance(record['date'], datetime.datetime):
                    record['date'] = record['date'].date()
            
            records.append(record)
            
    except Exception as e:
        # 捕獲所有可能的錯誤 (包括潛在的權限或路徑錯誤)
        st.error(f"讀取交易紀錄時發生錯誤: {e}")
        return pd.DataFrame(columns=['date', 'category', 'amount', 'type', 'note', 'id']) # 返回空 DataFrame
        
    # 將列表轉換為 DataFrame
    if records:
        df = pd.DataFrame(records)
        # 確保 'date' 欄位是 datetime.date 類型
        df['date'] = pd.to_datetime(df['date']).dt.date
        # 確保 'amount' 是數字
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        # 由於排序已經在 Firestore 端完成，這裡只需返回
        return df
    else:
        # 集合為空
        return pd.DataFrame(columns=['date', 'category', 'amount', 'type', 'note', 'id'])


# --- 3. Streamlit UI 結構與邏輯 ---

def main():
    # --- 1. 初始化與設定 ---
    
    # 1.1 確保 app_id 存在 (用於 Firestore 路徑)
    if 'app_id' not in st.session_state:
        # 使用一個固定的預設 ID
        st.session_state.app_id = 'streamlit-finance-app-v3' 
        
    # 1.2 設置 user_id (用於 Firestore 路徑隔離)
    if 'user_id' not in st.session_state:
        # 使用簡單的隨機 UUID 作為單一用戶識別符 (在 Streamlit session 中保持不變)
        st.session_state.user_id = str(uuid.uuid4())
        
    # 1.3 確保 Streamlit 僅在頁面加載時執行一次 UI 設定
    if 'initialized' not in st.session_state:
        set_ui_styles()
        st.session_state.initialized = True
        
    # 1.4 初始化 Firestore 客戶端
    if 'db' not in st.session_state:
        try:
            # st.cache_resource is typically preferred for creating expensive,
            # session-independent objects like database connections.
            @st.cache_resource
            def init_firestore_client():
                return firestore.Client()
            
            st.session_state.db = init_firestore_client()
        except Exception as e:
            st.error(f"初始化 Firestore 客戶端失敗。請確保環境已正確配置。錯誤: {e}")
            return # 停止執行
    
    # 取得當前使用的變數
    db = st.session_state.db
    user_id = st.session_state.user_id
    app_id = st.session_state.app_id

    # 顯示 App ID 和 User ID (用於除錯/驗證路徑)
    st.sidebar.markdown(f"**App ID:** `{app_id}`")
    st.sidebar.markdown(f"**User ID:** `{user_id}`")
    st.sidebar.markdown("---")
    
    st.title("簡易個人財務管理 🌱")

    # --- 2. 數據獲取 ---
    # 2.1 獲取餘額
    current_balance = get_current_balance(db, user_id)
    st.session_state.current_balance = current_balance # 存入 session state 供其他函數使用

    # 2.2 獲取所有交易紀錄
    df_records = get_all_records(db, user_id)

    # --- 3. UI 呈現 ---
    
    # 3.1 餘額顯示
    st.markdown(
        f"""
        <div class="balance-card">
            <div class="balance-label">當前餘額</div>
            <div class="balance-amount">${current_balance:,.0f}</div>
        </div>
        """, unsafe_allow_html=True
    )
    st.markdown("---")

    # 3.2 交易新增區
    st.header("新增交易")
    with st.form("new_transaction_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([1, 1, 2])
        
        type_choice = col1.radio("類型", options=list(CATEGORIES.keys()), index=1, horizontal=True) # 預設為支出
        
        # 根據類型動態選擇類別
        category_options = CATEGORIES.get(type_choice, [])
        category = col2.selectbox("類別", options=category_options)
        
        date = col1.date_input("日期", value=datetime.date.today(), max_value=datetime.date.today())
        
        # 金額輸入
        amount_input = col2.number_input("金額 (正數)", min_value=1, step=100, format="%d")
        
        note = col3.text_area("備註 (可選)", height=100)
        
        submitted = st.form_submit_button("💾 儲存交易")
        
        if submitted:
            if amount_input and category:
                try:
                    amount = int(amount_input)
                    
                    # 餘額變動量
                    amount_change = amount if type_choice == '收入' else -amount
                    
                    # 準備數據
                    new_record = {
                        'date': datetime.datetime.combine(date, datetime.time()), # 存儲為 datetime 物件
                        'type': type_choice,
                        'category': category,
                        'amount': amount,
                        'note': note,
                    }
                    
                    # 1. 儲存紀錄
                    add_record(db, user_id, new_record)
                    
                    # 2. 更新餘額
                    update_balance(db, user_id, amount_change)
                    
                    st.toast(f"成功新增一筆 {type_choice} 紀錄！", icon="🎉")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"處理交易時發生錯誤: {e}")
            else:
                st.warning("請輸入有效的金額和選擇類別。")
    
    st.markdown("---")

    # --- 3.3 數據過濾與統計分析區 ---
    st.header("數據篩選與分析")
    
    # 篩選器
    col_start, col_end, col_type_filter, col_category_filter = st.columns([1.5, 1.5, 1, 1.5])
    
    # 設定預設開始日期為 30 天前
    default_start_date = datetime.date.today() - datetime.timedelta(days=30)
    
    filter_start_date = col_start.date_input("起始日期", value=default_start_date)
    filter_end_date = col_end.date_input("結束日期", value=datetime.date.today())
    
    all_types = list(CATEGORIES.keys())
    type_filter = col_type_filter.selectbox("篩選類型", options=['所有'] + all_types, index=0)
    
    # 篩選類別 (根據選擇的類型動態更新)
    available_categories = []
    if type_filter == '所有':
        for cats in CATEGORIES.values():
            available_categories.extend(cats)
    else:
        available_categories = CATEGORIES.get(type_filter, [])
        
    category_filter = col_category_filter.selectbox("篩選類別", options=['所有'] + available_categories, index=0)

    # 執行篩選
    df_filtered = df_records.copy()
    
    # 確保日期是可比較的
    if not df_filtered.empty:
        df_filtered['date'] = pd.to_datetime(df_filtered['date']).dt.date
        df_filtered = df_filtered[
            (df_filtered['date'] >= filter_start_date) & 
            (df_filtered['date'] <= filter_end_date)
        ]
        
        if type_filter != '所有':
            df_filtered = df_filtered[df_filtered['type'] == type_filter]
            
        if category_filter != '所有':
            df_filtered = df_filtered[df_filtered['category'] == category_filter]

    # 顯示總結
    if not df_filtered.empty:
        total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
        total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
        net_change = total_income - total_expense
        
        col_total_income, col_total_expense, col_net_change = st.columns(3)
        col_total_income.metric("總收入", f"${total_income:,.0f}", delta_color="normal")
        col_total_expense.metric("總支出", f"${total_expense:,.0f}", delta_color="inverse")
        col_net_change.metric("淨變動", f"${net_change:,.0f}", delta_color="off")
    else:
        st.info("選定範圍內無交易紀錄。")


    st.markdown("---")
    st.header("支出分佈圖 (僅顯示支出)")
    
    df_expenses = df_filtered[df_filtered['type'] == '支出'].copy()

    if not df_expenses.empty and df_expenses['amount'].sum() > 0:
        # 1. 計算按類別分組的總支出
        df_category_sum = df_expenses.groupby('category')['amount'].sum().reset_index()
        df_category_sum.columns = ['category', 'total_amount']
        
        # 2. 計算百分比
        total_expense_sum = df_category_sum['total_amount'].sum()
        df_category_sum['percentage'] = df_category_sum['total_amount'] / total_expense_sum
        
        # 3. 使用 Altair 創建圓餅圖 (甜甜圈圖)
        
        # 定義顏色比例尺
        color_scale = alt.Scale(domain=df_category_sum['category'].tolist(), range=alt.Scheme('category20')['range'])
        
        # 基礎圓餅圖
        base = alt.Chart(df_category_sum).encode(
            theta=alt.Theta("total_amount", stack=True)
        ).properties(
            title="支出類別百分比分佈",
        )

        # 扇形
        pie = base.mark_arc(outerRadius=120, innerRadius=80).encode(
            color=alt.Color("category", scale=color_scale, title="類別"),
            order=alt.Order("percentage", sort="descending"),
            tooltip=[
                alt.Tooltip("category", title="類別"),
                alt.Tooltip("total_amount", title="金額", format="$,.0f"),
                alt.Tooltip("percentage", title="比例", format=".1%")
            ]
        )
        
        # 標籤文本 (顯示百分比)
        text = base.mark_text(radius=140).encode(
            text=alt.Text("percentage", format=".1%"),
            order=alt.Order("percentage", sort="descending"),
            color=alt.value("black") # 讓標籤顏色固定
        )
    
        # 4. 組合圖表並居中顯示
        chart = pie.interactive()
        
        # 為了讓圓餅圖在 Streamlit 內置的容器中能保持正確的寬高比，
        # 這裡設定較為固定的寬高，讓圓形居中顯示。
        st.altair_chart(chart, use_container_width=True)

        # --------------------------------------
        
    else:
        st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # 3.4. 交易紀錄區 (新增刪除按鈕)
    st.header("完整交易紀錄")
    
    # 準備用於顯示的 DataFrame
    display_df = df_filtered.copy()
    
    if display_df.empty:
        st.info("當前篩選條件下無交易紀錄。**請注意，Firestore 讀取錯誤也會導致這裡為空。**")
    
    # 標題列
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px;'>
            <div style='width: 12%; padding-left: 1rem;'>日期</div>
            <div style='width: 10%;'>類別</div>
            <div style='width: 10%;'>金額</div>
            <div style='width: 7%;'>類型</div>
            <div style='width: 50%;'>備註</div>
            <div style='width: 11%; text-align: center;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    # 遍歷篩選後的數據框，以便只顯示符合條件的紀錄
    for index, row in display_df.iterrows():
        try:
            # 從完整的紀錄中獲取刪除所需的資訊 (確保資訊完整且來源可靠)
            # 這裡 row 已經包含了所有的原始欄位，包括 'id', 'type', 'amount'
            record_details_for_delete = row.to_dict()
        except IndexError:
            # 如果找不到原始紀錄，則跳過，避免刪除時報錯
            st.error(f"找不到文件ID為 {row['id']} 的原始紀錄，可能已被刪除。")
            continue
            
        color = "#28a745" if row['type'] == '收入' else "#dc3545"
        amount_sign = "+" if row['type'] == '收入' else "-"
        
        # 使用 container 和 columns 創建行布局
        with st.container():
            # 調整 st.columns 比例，使備註欄位有足夠的空間
            # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 6, 操作 1] (總和 10.9 - 調整為 10 份的比例: [1.2, 1, 1, 0.7, 5, 1.1])
            # 重新分配以符合標題列的寬度 [12%, 10%, 10%, 7%, 50%, 11%]
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([12, 10, 10, 7, 50, 11])
            
            # 使用 st.write 顯示交易細節
            col_date.markdown(f"<div style='padding-left: 1rem;'>{row['date'].strftime('%Y-%m-%d')}</div>", unsafe_allow_html=True)
            col_cat.write(row['category'])
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row['amount']:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(row['type'])
            col_note.write(row['note']) # 備註內容
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{row['id']}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                delete_record(
                    db=db,
                    user_id=user_id,
                    record_id=record_details_for_delete['id'],
                    record_type=record_details_for_delete['type'],
                    record_amount=record_details_for_delete['amount'],
                    current_balance=st.session_state.current_balance
                )
        st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True) # 分隔線
            

if __name__ == '__main__':
    main()

