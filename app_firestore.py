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
            border-bottom: 2px solid #e9ecef; /* 添加簡約底線 */
            padding-bottom: 0.5rem;
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }}
        
        /* 設定 Streamlit 容器背景色 */
        .stApp {{
            background-color: {DEFAULT_BG_COLOR};
        }}

        /* 調整按鈕樣式 */
        .stButton>button {{
            width: 100%;
            border-radius: 0.5rem;
            font-weight: 600;
            transition: all 0.2s;
        }}
        /* 刪除按鈕 (Secondary) 樣式 */
        .stButton>button[kind="secondary"] {{
            background-color: #ffc107; /* 警告黃色 */
            color: #212529; /* 深色文字 */
            border: none;
        }}
        .stButton>button[kind="secondary"]:hover {{
            background-color: #e0a800; /* 較深的黃色 */
            color: #212529;
        }}

        /* 調整輸入框樣式 */
        .stTextInput>div>div>input, .stSelectbox>div>div, .stDateInput>div>div>input {{
            border-radius: 0.5rem;
        }}
        
        /* 隱藏 Streamlit 預設的 footer 和 header */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}

        </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    
# --- 2. Firestore 服務設定與輔助函數 ---
def init_firestore():
    """初始化 Firestore 客戶端和身份驗證"""
    db = None
    user_id = 'default_user'
    
    # 嘗試從環境變數獲取配置和 App ID
    try:
        if 'db' not in st.session_state:
            # 假設 Firebase 已經在 Streamlit 環境中配置好
            db = firestore.Client()
            st.session_state.db = db
            st.session_state.user_id = user_id # 在 Streamlit 環境中，我們使用預設 ID 或自定義 ID
            
        return st.session_state.db, st.session_state.user_id
    except Exception as e:
        # 在本地運行時，如果沒有配置 Google Cloud 憑證，這裡會報錯
        st.error(f"Firestore 初始化失敗。請檢查您的 Google Cloud 環境配置。錯誤: {e}")
        return None, user_id

@st.cache_data(ttl=5) # 緩存資料，每 5 秒更新一次
def get_records(db, user_id):
    """從 Firestore 獲取所有交易紀錄和當前餘額"""
    
    # 獲取餘額
    balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
    balance_doc = balance_ref.get()
    current_balance = balance_doc.to_dict().get('amount', 0) if balance_doc.exists else 0

    # 獲取交易紀錄
    records_ref = db.collection(RECORD_COLLECTION_NAME)
    docs = records_ref.stream()
    
    records_list = []
    for doc in docs:
        record = doc.to_dict()
        record['id'] = doc.id
        # 將 Firestore Timestamp 轉換為 Python datetime.date
        if isinstance(record.get('date'), datetime.datetime):
            record['date'] = record['date'].date()
        elif not isinstance(record.get('date'), datetime.date):
             # 處理日期丟失或格式不正確的情況，給一個默認日期
            record['date'] = datetime.date.today()
        
        records_list.append(record)
    
    # 轉換為 DataFrame 並按日期降序排序
    if records_list:
        df_records = pd.DataFrame(records_list)
        df_records.sort_values(by='date', ascending=False, inplace=True)
    else:
        df_records = pd.DataFrame(columns=['id', 'date', 'category', 'amount', 'type', 'note'])
        
    return df_records, current_balance

def add_record(db, record_data, current_balance):
    """添加新的交易紀錄並更新餘額，使用 Firestore 事務確保原子性"""
    
    record_ref = db.collection(RECORD_COLLECTION_NAME).document(str(uuid.uuid4()))
    balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
    
    @firestore.transactional
    def update_in_transaction(transaction, record_ref, balance_ref, record_data):
        """在事務中更新 Firestore 數據"""
        
        # 1. 讀取現有餘額
        balance_doc = balance_ref.get(transaction=transaction)
        old_balance = balance_doc.to_dict().get('amount', 0) if balance_doc.exists else 0

        # 2. 計算新餘額
        amount = record_data['amount']
        record_type = record_data['type']
        
        if record_type == '收入':
            new_balance = old_balance + amount
        else: # 支出
            new_balance = old_balance - amount
            
        # 3. 寫入新紀錄和新餘額
        transaction.set(record_ref, record_data)
        transaction.set(balance_ref, {'amount': new_balance})
        
        return new_balance

    try:
        transaction = db.transaction()
        new_balance = update_in_transaction(transaction, record_ref, balance_ref, record_data)
        st.session_state.current_balance = new_balance
        st.success("✅ 交易紀錄添加成功並已更新餘額!")
    except Exception as e:
        st.error(f"❌ 交易添加失敗: {e}")

def delete_record(db, record_id, record_type, record_amount, current_balance):
    """刪除交易紀錄並反向更新餘額，使用 Firestore 事務確保原子性"""
    
    record_ref = db.collection(RECORD_COLLECTION_NAME).document(record_id)
    balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)

    @firestore.transactional
    def delete_in_transaction(transaction, record_ref, balance_ref, record_type, record_amount):
        """在事務中更新 Firestore 數據"""
        
        # 1. 讀取現有餘額
        balance_doc = balance_ref.get(transaction=transaction)
        old_balance = balance_doc.to_dict().get('amount', 0) if balance_doc.exists else 0
        
        # 2. 計算新餘額 (反向操作)
        if record_type == '收入':
            # 刪除收入: 餘額減少
            new_balance = old_balance - record_amount
        else: # 刪除支出
            # 刪除支出: 餘額增加
            new_balance = old_balance + record_amount
            
        # 3. 刪除紀錄並寫入新餘額
        transaction.delete(record_ref)
        transaction.set(balance_ref, {'amount': new_balance})
        
        return new_balance

    try:
        transaction = db.transaction()
        new_balance = delete_in_transaction(transaction, record_ref, balance_ref, record_type, record_amount)
        st.session_state.current_balance = new_balance
        st.toast("🗑️ 交易紀錄已刪除，餘額已反向更新!", icon="✅")
        # 刪除後需要刷新 Streamlit (重新運行腳本)
        st.rerun() 
    except Exception as e:
        st.error(f"❌ 交易刪除失敗: {e}")
        
# --- 3. Streamlit 主邏輯 ---

def main():
    """應用程式主函數"""
    set_ui_styles()
    
    st.title("💸 家庭記帳本 (Firestore 存儲)")
    
    # 初始化 Firestore 連線
    db, user_id = init_firestore()
    if db is None:
        return # 如果連接失敗，停止執行

    # 獲取交易紀錄和餘額
    df_records, current_balance = get_records(db, user_id)
    
    # 將當前餘額存入 session_state，用於刪除操作後的餘額更新顯示
    if 'current_balance' not in st.session_state or st.session_state.current_balance != current_balance:
        st.session_state.current_balance = current_balance

    # 3.1. 餘額顯示
    st.header("當前餘額")
    st.markdown(
        f"<div style='font-size: 2.5rem; font-weight: 700; color: #007bff; text-align: center; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>NTD {st.session_state.current_balance:,.0f}</div>", 
        unsafe_allow_html=True
    )
    st.markdown("---")


    # 3.2. 新增交易區塊
    st.header("新增交易紀錄")
    
    # 使用 st.form 確保輸入不會在每次按鍵時重繪
    with st.form("new_record_form", clear_on_submit=True):
        
        col1, col2 = st.columns([1, 1])
        record_type = col1.radio("類型", ['支出', '收入'], horizontal=True)
        
        # 根據類型動態更新類別選項
        category_options = CATEGORIES[record_type]
        category = col2.selectbox("類別", category_options)
        
        col3, col4 = st.columns([1, 1])
        amount = col3.number_input("金額 (NTD)", min_value=1, step=100, format="%d")
        date = col4.date_input("日期", datetime.date.today())
        
        note = st.text_input("備註 (可選)", placeholder="例如: 晚餐費用、本月薪水")
        
        submitted = st.form_submit_button("💾 儲存紀錄", type="primary")
        
        if submitted:
            if amount is None or amount <= 0:
                st.error("金額必須大於零。")
            else:
                new_record = {
                    'date': date,
                    'category': category,
                    'amount': amount,
                    'type': record_type,
                    'note': note,
                    # 'user_id': user_id # 暫時不需要，因為所有數據都在同一 Collection
                }
                add_record(db, new_record, st.session_state.current_balance)
                # 儲存後立即重新運行以刷新數據和圖表
                st.rerun()

    st.markdown("---")

    # 3.3. 儀表板與篩選
    st.header("數據儀表板")
    
    # 日期篩選器
    st.subheader("篩選時間範圍")
    col_start, col_end = st.columns(2)
    
    # 設置篩選範圍的默認值
    min_date = df_records['date'].min() if not df_records.empty else datetime.date.today()
    max_date = df_records['date'].max() if not df_records.empty else datetime.date.today()
    
    # 確保開始日期不晚於結束日期，如果數據為空，則默認顯示今天
    if min_date > max_date:
        start_date = max_date
        end_date = max_date
    else:
        start_date = col_start.date_input("起始日期", min_date)
        end_date = col_end.date_input("結束日期", max_date)
        
    if start_date > end_date:
        st.warning("起始日期不能晚於結束日期。請重新選擇。")
        # 如果日期無效，則不進行後續計算和顯示
        df_filtered = pd.DataFrame()
    else:
        # 篩選數據
        df_filtered = df_records[
            (df_records['date'] >= start_date) & 
            (df_records['date'] <= end_date)
        ]

    # 顯示總結
    if not df_filtered.empty:
        total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
        total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
        
        st.subheader("期間總結")
        summary_cols = st.columns(3)
        
        summary_cols[0].metric(
            label="總收入", 
            value=f"NTD {total_income:,.0f}", 
            delta_color="off"
        )
        summary_cols[1].metric(
            label="總支出", 
            value=f"NTD {total_expense:,.0f}", 
            delta_color="off"
        )
        summary_cols[2].metric(
            label="淨額 (收 - 支)", 
            value=f"NTD {total_income - total_expense:,.0f}", 
            delta_color="off"
        )
    else:
        st.info("選定範圍內無交易紀錄。")

    st.markdown("---")
    
    # 3.3.1. 支出分佈圖
    st.subheader("支出分佈圖 (按類別)")
    
    df_expense = df_filtered[df_filtered['type'] == '支出'].copy()
    
    if not df_expense.empty and df_expense['amount'].sum() > 0:
        
        # 計算各類別支出總和
        df_category_sum = df_expense.groupby('category')['amount'].sum().reset_index()
        df_category_sum.rename(columns={'amount': 'total_amount'}, inplace=True)
        
        # 計算百分比
        total_expense = df_category_sum['total_amount'].sum()
        df_category_sum['percentage'] = df_category_sum['total_amount'] / total_expense
        
        # 為了美觀，將金額轉換為字串，用於工具提示 (tooltip)
        df_category_sum['amount_label'] = df_category_sum['total_amount'].apply(lambda x: f"NTD {x:,.0f}")
        df_category_sum['percentage_label'] = df_category_sum['percentage'].apply(lambda x: f"{x:.1%}")

        # 1. 基礎圖表設定
        base = alt.Chart(df_category_sum).encode(
            theta=alt.Theta("total_amount", stack=True)
        )
        
        # 2. 圓餅圖/甜甜圈圖
        pie = base.mark_arc(outerRadius=120, innerRadius=50).encode(
            color=alt.Color("category", title="支出類別"),
            order=alt.Order("total_amount", sort="descending"),
            tooltip=[
                alt.Tooltip("category", title="類別"),
                alt.Tooltip("amount_label", title="總金額"),
                alt.Tooltip("percentage_label", title="佔比")
            ],
            # 增加一個透明度編碼，用於互動 (滑鼠懸停效果)
            opacity=alt.condition(alt.datum.category, alt.value(0.9), alt.value(0.5))
        )
        
        # 3. 文本標籤 (顯示類別) - 可選
        text = base.mark_text(radius=140).encode(
            text=alt.Text("category"),
            order=alt.Order("total_amount", sort="descending"),
            color=alt.value("black")
        )
        
        # 4. 組合圖表並居中顯示
        chart = pie # (pie + text) 帶文本標籤可能會導致重疊，暫時只顯示圓餅圖
        
        # 為了讓圓餅圖在 Streamlit 內置的容器中能保持正確的寬高比，
        # 這裡設定較為固定的寬高，讓圓形居中顯示。
        st.altair_chart(chart, use_container_width=True)

        # --------------------------------------
        
    else:
        st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")
    
    # 3.4. 交易紀錄區 (新增刪除按鈕)
    st.header("完整交易紀錄")
    
    if df_filtered.empty:
        st.info("選定範圍內無交易紀錄。")
        return

    # 準備用於顯示的 DataFrame，只包含需要的欄位
    display_df = df_filtered[['id', 'date', 'category', 'amount', 'type', 'note']].copy()
    
    # 標題列 (使用 Markdown/HTML 保持一致的欄位視覺對齊)
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px;'>
            <div style='width: 11.5%; padding-left: 1rem;'>日期</div>
            <div style='width: 9.2%;'>類別</div>
            <div style='width: 9.2%;'>金額</div>
            <div style='width: 6.4%;'>類型</div>
            <div style='width: 48.6%;'>備註</div>
            <div style='width: 9.2%; text-align: center;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    for index, row in display_df.iterrows():
        try:
            # 從完整的紀錄中獲取刪除所需的資訊
            # 這裡使用 row['id']，因為 display_df 是 df_filtered 的子集，包含了 'id'
            record_details_for_delete = df_records[df_records['id'] == row['id']].iloc[0].to_dict()
        except IndexError:
            # 如果找不到原始紀錄，則跳過，避免刪除時報錯
            st.error(f"找不到文件ID為 {row['id']} 的原始紀錄，可能已被刪除。")
            continue
            
        color = "#28a745" if row['type'] == '收入' else "#dc3545"
        amount_sign = "+" if row['type'] == '收入' else "-"
        
        # 使用 container 和 columns 創建行布局
        with st.container():
            # **修正點: 調整 st.columns 比例，使總和為 10.0 (1.2 + 1 + 1 + 0.7 + 5.3 + 0.8 = 10.0)**
            # 這解決了 StreamlitAPIException 的問題。
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 5.3, 0.8])
            
            # 使用 st.write 顯示交易細節
            col_date.write(row['date'].strftime('%Y-%m-%d'))
            col_cat.write(row['category'])
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row['amount']:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(row['type'])
            col_note.write(row['note']) # 備註內容
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{row['id']}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                delete_record(
                    db=db,
                    record_id=row['id'],
                    record_type=record_details_for_delete['type'],
                    record_amount=record_details_for_delete['amount'],
                    current_balance=st.session_state.current_balance
                )
    
    # 重新執行主函數以確保 Streamlit 刷新 (由於 st.button 按下後會執行整個腳本)
    # 這裡不需要額外的 st.rerun()，因為 delete_record 已經包含了它。
    

if __name__ == "__main__":
    main()

