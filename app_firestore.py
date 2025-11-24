import streamlit as st
import pandas as pd
import datetime
import altair as alt
from google.cloud import firestore
import uuid # 雖然不再生成，但保留 import 以防未來需要

# --- 0. 配置與變數 ---
DEFAULT_BG_COLOR = "#f8f9fa"
RECORD_COLLECTION_NAME = "records"       # 交易紀錄 Collection 名稱
BALANCE_COLLECTION_NAME = "account_status" # 餘額/狀態 Collection 名稱
BALANCE_DOC_ID = "current_balance"       # 總餘額文件 ID，固定單一文件 (由交易紀錄計算而來)
BANK_ACCOUNTS_COLLECTION_NAME = "bank_accounts" # 銀行帳戶 Collection 名稱 (保留，但功能已移除)

# 📌 修正點 1: 簡化支出類別為 '食', '衣', '住', '行', '育樂'
CATEGORIES = {
    '收入': ['薪資', '投資收益', '禮金', '其他收入'],
    # 簡化支出類別
    '支出': ['食', '衣', '住', '行', '育樂']
}

# --- 1. Streamlit 介面設定 ---
def set_ui_styles():
    """注入客製化 CSS，設定字體、簡約背景色和排版"""
    css = f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        html, body, [class*="st-"] {{
            font-family: 'Inter', "PingFang TC", "Microsoft YaHei", sans-serif;
            font-size: 15px;
        }}
        /* 保持 Streamlit 內建的樣式 */
        .stButton>button {{
            width: 100%;
            border-radius: 0.5rem;
        }}
        .stTextInput, .stNumberInput, .stDateInput, .stSelectbox {{
            border-radius: 0.5rem;
        }}
        /* 調整表格細節行的排版 */
        [data-testid="stHorizontalBlock"] > div:nth-child(5) > div {{ /* 備註欄位對齊 */
            text-align: left !important;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# --- 2. Firestore 連線與認證 (假設已在環境中設定好金鑰) ---

@st.cache_resource
def get_firestore_client():
    """初始化並返回 Firestore 客戶端"""
    # 嘗試從 Streamlit secrets 載入配置
    try:
        if 'private_key' in st.secrets:
            # 使用服務帳戶金鑰進行認證
            db = firestore.Client.from_service_account_info(dict(st.secrets))
        else:
            # 嘗試使用預設憑證 (例如在 Google Cloud 環境中)
            db = firestore.Client()
        return db
    except Exception as e:
        st.error(f"Firestore 客戶端初始化失敗: {e}")
        return None

def get_user_id():
    """獲取用戶 ID (在此簡單版本中，使用固定的 ID)"""
    # 在真實應用中，這裡應該是 Firebase Auth 的用戶 ID
    # 為了演示和隔離數據，我們使用一個固定的 ID 來代表單個用戶/家庭
    if 'user_id' not in st.session_state:
        st.session_state['user_id'] = "family_budget_user"
    return st.session_state['user_id']

# --- 3. 數據操作函數 (CRUD) ---

# 獲取總餘額
def get_balance(db):
    """從 Firestore 獲取當前總餘額"""
    user_id = get_user_id()
    try:
        # 使用用戶 ID 隔離數據
        doc_ref = db.collection(BALANCE_COLLECTION_NAME).document(user_id) \
                    .collection(RECORD_COLLECTION_NAME).document(BALANCE_DOC_ID)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('total_balance', 0.0)
        return 0.0
    except Exception as e:
        st.error(f"獲取總餘額失敗: {e}")
        return 0.0

# 更新總餘額
def update_balance(db, amount, record_type):
    """更新 Firestore 中的總餘額"""
    user_id = get_user_id()
    try:
        balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME).document(BALANCE_DOC_ID)
        
        # 使用 Firestore 事務 (Transaction) 來確保原子性
        @firestore.transactional
        def update_in_transaction(transaction):
            snapshot = balance_ref.get(transaction=transaction)
            old_balance = snapshot.get('total_balance') if snapshot.exists else 0.0

            if record_type == '收入':
                new_balance = old_balance + amount
            elif record_type == '支出':
                new_balance = old_balance - amount
            else:
                return # 不處理其他類型

            transaction.set(balance_ref, {'total_balance': new_balance})

        transaction = db.transaction()
        update_in_transaction(transaction)
        
        st.toast(f"總餘額已更新: {record_type} {amount:,.0f}。", icon="💰")
    except Exception as e:
        st.error(f"更新總餘額失敗: {e}")


# 新增紀錄
def add_record(db, record_data):
    """向 Firestore 新增一筆交易紀錄並更新餘額"""
    user_id = get_user_id()
    try:
        # 使用用戶 ID 隔離數據
        records_ref = db.collection(RECORD_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME)
        
        # 修正 #1: 將 datetime.date 對象轉換為 datetime.datetime 對象
        # Streamlit Date Input 輸出的是 date 對象，Firestore 最好儲存為 datetime 對象 (Timestamp)
        record_date_time = datetime.datetime.combine(record_data['date'], datetime.time.min)

        # 準備寫入的數據
        data_to_save = {
            'timestamp': firestore.SERVER_TIMESTAMP,
            'date': record_date_time, # 儲存為 datetime.datetime 對象
            'type': record_data['type'], # 收入/支出
            'category': record_data['category'], # 食衣住行育樂/薪資等
            'amount': record_data['amount'],
            # 移除 'bank_account' 欄位
            'note': record_data['note'],
            'user_id': user_id
        }

        # 寫入數據
        records_ref.add(data_to_save)
        
        # 更新餘額
        update_balance(db, record_data['amount'], record_data['type'])
        
        st.success("紀錄新增成功！")

    except Exception as e:
        st.error(f"新增紀錄失敗: {e}")
        st.exception(e)


# 獲取所有紀錄
@st.cache_data(ttl=5) # 緩存數據以提高性能，每 5 秒更新一次
def get_all_records(db, user_id):
    """從 Firestore 獲取所有交易紀錄並返回 DataFrame"""
    try:
        records_ref = db.collection(RECORD_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME)
        
        # 獲取所有文件
        docs = records_ref.order_by('date', direction=firestore.Query.DESCENDING).stream()
        
        data = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id
            
            # 修正 #2: 處理 Firestore Timestamp/Date 字段，確保日期數據被正確轉換
            record_date = record.get('date')
            
            if isinstance(record_date, firestore.Timestamp):
                # 如果是 Firestore Timestamp，轉換為 datetime.date
                record['date'] = record_date.to_datetime().date()
            elif isinstance(record_date, datetime.datetime):
                # 如果是 datetime.datetime 對象，轉換為 datetime.date
                record['date'] = record_date.date()
            elif not isinstance(record_date, datetime.date):
                 # 其他無法識別的類型 (如 DocumentReference 或 None)，設置為預設值 (1970/1/1)
                record['date'] = datetime.date(1970, 1, 1) # 設置一個預設值

            data.append(record)
            
        if not data:
            # 確保欄位名稱正確
            return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])
        
        df = pd.DataFrame(data)
        
        # 排序：優先按日期降序，日期相同則按 Firestore 的 timestamp 降序
        df = df.sort_values(by=['date', 'timestamp'], ascending=[False, False])
        
        return df
        
    except Exception as e:
        st.error(f"獲取所有紀錄失敗: {e}")
        # 返回一個空的 DataFrame
        return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])


# 刪除紀錄
def delete_record(db, user_id, record_id, record_type, record_amount):
    """從 Firestore 刪除一筆交易紀錄並反向更新餘額"""
    try:
        records_ref = db.collection(RECORD_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME)
        
        # 刪除文件
        records_ref.document(record_id).delete()
        
        # 反向更新餘額 (收入刪除視為餘額減少，支出刪除視為餘額增加)
        reverse_type = '支出' if record_type == '收入' else '收入'
        update_balance(db, record_amount, reverse_type)
        
        st.success(f"紀錄 ID: {record_id} 已成功刪除！")
        st.rerun() # 刪除後強制 Streamlit 重新運行以更新列表

    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")
        st.exception(e)
        
# -----------------------------------------------------------
# 移除銀行帳戶相關的 CRUD 函數
# -----------------------------------------------------------

# --- 4. 儀表板與視覺化組件 ---

# 顯示總結數據
def display_summary(df_records, current_balance):
    """顯示總餘額、總收入和總支出"""
    
    # 計算總收入和總支出
    total_income = df_records[df_records['type'] == '收入']['amount'].sum()
    total_expense = df_records[df_records['type'] == '支出']['amount'].sum()
    
    # 建立三欄佈局
    col1, col2, col3 = st.columns(3)
    
    # 總餘額 (使用 FireStore 讀取的值，確保一致性)
    col1.metric(
        label="🏡 當前家庭總餘額", 
        value=f"NT$ {current_balance:,.0f}", 
        delta=None
    )

    # 總收入 (當月或全部)
    col2.metric(
        label="📈 總收入", 
        value=f"NT$ {total_income:,.0f}", 
        delta=None,
        delta_color="normal"
    )

    # 總支出 (當月或全部)
    col3.metric(
        label="📉 總支出", 
        value=f"NT$ {total_expense:,.0f}", 
        delta=None,
        delta_color="inverse"
    )

def display_charts(df_records):
    """顯示收入/支出圓餅圖和趨勢圖"""
    st.subheader("📊 數據分析與視覺化")
    
    if df_records.empty:
        st.info("沒有數據可供分析。")
        return

    # 1. 類別支出圓餅圖 (只分析支出)
    expense_data = df_records[df_records['type'] == '支出']
    
    if not expense_data.empty:
        expense_by_category = expense_data.groupby('category')['amount'].sum().reset_index()
        
        # 使用 Altair 創建圓餅圖
        base = alt.Chart(expense_by_category).encode(
            theta=alt.Theta("amount", stack=True)
        ).properties(title="支出類別分佈")

        pie = base.markArc(outerRadius=120).encode(
            color=alt.Color("category", title="類別"),
            order=alt.Order("amount", sort="descending"),
            tooltip=["category", "amount", alt.Tooltip("amount", format=".2f")]
        )

        text = base.markText(radius=140).encode(
            text=alt.Text("amount", format=".0f"),
            order=alt.Order("amount", sort="descending"),
            color=alt.value("black") # 讓文字為黑色以確保可讀性
        )
        
        st.altair_chart(pie + text, use_container_width=True)
    else:
        st.info("沒有支出紀錄可供類別分析。")

    # 2. 每日收支趨勢圖
    # 這裡假設 df_records['date'] 已經是 datetime.date 或 datetime.datetime
    df_records['day'] = pd.to_datetime(df_records['date']).dt.to_period('D')
    daily_summary = df_records.groupby(['day', 'type'])['amount'].sum().unstack(fill_value=0).reset_index()
    daily_summary['day'] = daily_summary['day'].dt.to_timestamp() # 轉換回 timestamp 以便 Altair 繪圖

    # 確保包含所有必要的欄位，即使沒有收入或支出
    if '收入' not in daily_summary.columns:
        daily_summary['收入'] = 0
    if '支出' not in daily_summary.columns:
        daily_summary['支出'] = 0

    # 轉換數據為長格式以便於繪製多線圖
    daily_long = daily_summary.melt('day', var_name='Type', value_name='Amount')

    # 繪製趨勢圖
    trend_chart = alt.Chart(daily_long).markLine().encode(
        x=alt.X('day', title='日期'),
        y=alt.Y('Amount', title='金額 (NT$)'),
        color=alt.Color('Type', scale=alt.Scale(domain=['收入', '支出'], range=['#28a745', '#dc3545'])),
        tooltip=['day', 'Type', 'Amount']
    ).properties(
        title='每日收支趨勢'
    )
    
    st.altair_chart(trend_chart, use_container_width=True)

# --- 5. 交易紀錄列表組件 ---

def display_record_list(df_records, db, user_id):
    """顯示詳細的交易紀錄列表"""
    st.subheader("📚 交易紀錄明細")
    
    if df_records.empty:
        st.info("目前沒有交易紀錄。")
        return
        
    # 顯示表頭
    with st.container():
        # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 6, 操作 1] (總和 10.9)
        col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 6, 1])
        
        # 設置粗體表頭
        for col, title in zip(
            [col_date, col_cat, col_amount, col_type, col_note, col_btn_action], 
            ["**日期**", "**類別**", "**金額**", "**類型**", "**備註**", "**操作**"]
        ):
            col.markdown(title)
        
        st.markdown("---\n", unsafe_allow_html=True) # 表頭下的分隔線

    # 迭代每一行數據
    for index, row in df_records.iterrows():
        try:
            record_id = row['id']
            # 從 DataFrame 中讀取的 'date' 應已是 datetime.date 對象 (在 get_all_records 中已處理)
            record_date = row['date']
            record_category = row['category']
            record_amount = row['amount']
            record_type = row['type']
            record_note = row['note']

            # 📌 修正點 4: 確保日期是可格式化的對象 (已在 get_all_records 中修復，這裡只是防禦性檢查)
            if not isinstance(record_date, (datetime.date, datetime.datetime)):
                record_date_str = "日期錯誤"
            else:
                record_date_str = record_date.strftime('%Y-%m-%d')
                
        except Exception as e:
            st.error(f"在迭代行時發生錯誤 (可能是欄位遺失或數據類型問題): {e}")
            continue
            
        color = "#28a745" if record_type == '收入' else "#dc3545"
        amount_sign = "+" if record_type == '收入' else "-"
        
        # 使用 container 和 columns 創建行布局
        with st.container():
            # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 6, 操作 1] (總和 10.9)
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 6, 1])
            
            # 使用 st.markdown/write 顯示交易細節
            col_date.write(record_date_str) # 使用處理過的日期字串
            col_cat.write(record_category)
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {record_amount:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(record_type)
            col_note.write(record_note) # 備註內容
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{record_id}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):\
                # 調用刪除函數
                delete_record(
                    db=db,
                    user_id=user_id,
                    record_id=record_id,
                    record_type=record_type,
                    record_amount=record_amount
                )
                # 刪除後需要強制 Streamlit 重新運行以更新列表

# --- 6. 紀錄輸入表單組件 ---

# 📌 修正點 5: 移除銀行帳戶相關邏輯，將類別選擇替換為新的簡化分類
def display_record_input(db, user_id):
    """顯示新增交易紀錄的輸入表單"""
    st.header("➕ 新增紀錄")

    with st.form(key='new_record_form'):
        
        col1, col2 = st.columns(2)
        
        # 1. 交易類型 (收入/支出)
        record_type = col1.selectbox(
            "交易類型", 
            list(CATEGORIES.keys()), 
            key='record_type_input'
        )
        
        # 2. 選擇類別 (替換原銀行帳戶功能)
        # 根據選定的類型獲取對應的類別列表
        sub_categories = CATEGORIES.get(record_type, [])
        record_category = col2.selectbox(
            "選擇類別", # Label 替換為 "選擇類別"
            sub_categories,
            key='record_category_input'
        )
        
        # 3. 金額
        record_amount = st.number_input(
            "金額 (NT$)", 
            min_value=0.0, 
            value=None, 
            placeholder="輸入交易金額", 
            key='amount_input', 
            format="%.0f"
        )
        
        # 4. 日期
        record_date = st.date_input(
            "日期", 
            value="today", # 預設為今天
            key='date_input'
        )
        
        # 5. 備註 (可選)
        record_note = st.text_area(
            "備註 (可選)", 
            key='note_input'
        )

        submitted = st.form_submit_button("儲存紀錄", type="primary")

        if submitted:
            if record_amount is None or record_amount <= 0:
                st.error("請輸入有效的金額。")
            elif not record_category:
                st.error("請選擇類別。")
            else:
                # 構造紀錄數據
                record_data = {
                    'date': record_date,
                    'type': record_type,
                    'category': record_category,
                    'amount': record_amount,
                    'note': record_note
                }
                
                # 調用新增函數
                add_record(db, record_data)
                
                # 成功後強制重新運行以清空表單並更新數據
                st.rerun()

# 📌 修正點 6: 快速記帳也應該使用新的類別
def display_quick_entry_on_home(db, user_id):
    """在首頁顯示快速記帳輸入框"""
    st.subheader("🚀 快速記帳")
    
    # 使用 Streamlit columns 橫向佈局輸入框
    col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 2, 2, 1])
    
    # 1. 交易類型
    q_type = col1.selectbox("類型", list(CATEGORIES.keys()), key='quick_type', label_visibility="collapsed")
    
    # 2. 選擇類別 (替換原銀行帳戶選擇)
    q_categories = CATEGORIES.get(q_type, [])
    q_category = col2.selectbox("類別", q_categories, key='quick_category', label_visibility="collapsed")
    
    # 3. 金額
    q_amount = col3.number_input("金額", min_value=0.0, value=None, placeholder="金額", key='quick_amount', format="%.0f", label_visibility="collapsed")
    
    # 4. 備註
    q_note = col4.text_input("備註 (可選)", key='quick_note', label_visibility="collapsed")
    
    # 5. 儲存按鈕
    if col5.button("儲存", key='quick_save', type="primary"):
        if q_amount is None or q_amount <= 0:
            st.error("請輸入有效的金額。")
        elif not q_category:
            st.error("請選擇類別。")
        else:
            # 構造紀錄數據
            record_data = {
                'date': datetime.date.today(), # 快速記帳使用當日日期
                'type': q_type,
                'category': q_category,
                'amount': q_amount,
                'note': q_note
            }
            
            # 調用新增函數
            add_record(db, record_data)
            
            # 成功後強制重新運行以清空表單並更新數據
            st.rerun()


# --- 7. 主應用程式框架 ---

# 📌 修正點 7: 移除帳戶管理頁面中所有關於銀行帳戶的操作
def display_account_management(db, user_id):
    """顯示帳戶管理頁面 (在此版本中已無作用，僅作為占位符)"""
    st.header("🏦 帳戶管理")
    st.info("此版本已移除銀行帳戶管理功能，專注於簡單的收支分類記帳 (食、衣、住、行、育、樂)。")
    st.subheader("未來功能：")
    st.markdown("- **多帳戶餘額追蹤**: 記錄現金、信用卡、不同銀行存款的餘額。")
    st.markdown("- **帳戶間轉帳**")

# 📌 修正點 8: 移除設定餘額頁面中所有關於銀行帳戶的操作，僅保留總餘額設置提示
def display_set_initial_balance(db, user_id):
    """顯示設定初始總餘額的頁面"""
    st.header("⚙️ 其他設定 / 初始總餘額")
    
    st.warning("請注意：總餘額應由交易紀錄自動計算。此功能僅用於*首次設定*或在數據異常時進行手動校準。")

    current_balance = get_balance(db)
    st.subheader(f"當前總餘額: NT$ {current_balance:,.0f}")
    
    new_balance = st.number_input(
        "設定新的總餘額 (僅用於校準)",
        value=current_balance,
        min_value=0.0,
        key='new_balance_input',
        format="%.0f"
    )
    
    if st.button("更新總餘額", type="primary"):
        try:
            # 直接更新總餘額文件
            balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(user_id) \
                            .collection(RECORD_COLLECTION_NAME).document(BALANCE_DOC_ID)
            
            balance_ref.set({'total_balance': float(new_balance)})
            st.success(f"總餘額已手動設定為 NT$ {new_balance:,.0f}。")
            st.rerun()
        except Exception as e:
            st.error(f"手動更新餘額失敗: {e}")

# 主應用入口
def app():
    """主應用程式入口點"""
    st.set_page_config(
        page_title="家庭記帳本 - Streamlit & Firestore",
        layout="wide",
        initial_sidebar_state="auto"
    )
    set_ui_styles()

    st.title("👨‍👩‍👧‍👦 雲端家庭記帳本")
    
    # 初始化 Firestore 和用戶 ID
    db = get_firestore_client()
    user_id = get_user_id()
    
    # --- 頁面內容渲染 (使用 st.tabs) ---
    
    tab_list = ["首頁", "記帳管理", "帳戶管理", "其他設定"]
    
    tab1, tab2, tab3, tab4 = st.tabs(tab_list)

    with tab1:
        # 首頁：快速記帳 + 儀表板
        display_quick_entry_on_home(db, user_id)
        st.markdown('---')
        # 獲取總結數據
        df_records = get_all_records(db, user_id)
        current_balance = get_balance(db)
        display_summary(df_records, current_balance)
        st.markdown('---')
        display_charts(df_records)


    with tab2:
        # 記帳管理：新增紀錄 + 交易明細
        # (1) 先顯示 "新增紀錄" 的區塊
        display_record_input(db, user_id)
        
        # (2) 加入分隔線
        st.markdown("---") 
        
        # (3) 顯示 "交易紀錄" 區塊 (使用最新的 df_records)
        df_records = get_all_records(db, user_id) # 重新獲取確保是最新的
        display_record_list(df_records, db, user_id)

    with tab3:
        # 帳戶管理 (已簡化)
        display_account_management(db, user_id)

    with tab4:
        # 其他設定/餘額設定
        display_set_initial_balance(db, user_id)

    # 確保用戶 ID 始終顯示在底部 (方便除錯)
    st.sidebar.markdown('---')
    st.sidebar.info(f"用戶 ID: `{user_id}`") # 顯示用戶 ID 方便調試
    
if __name__ == '__main__':
    app()