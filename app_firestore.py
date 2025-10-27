import streamlit as st
import pandas as pd
import datetime
import altair as alt 
from google.cloud import firestore
import uuid # 導入 uuid 庫用於生成唯一 ID
# 移除 os 庫，因為它不再需要

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
            border-bottom: 2px solid #e9ecef; /* 淡灰色底線 */
            padding-bottom: 5px;
            margin-top: 1.5rem;
            margin-bottom: 1.5rem;
        }}
        
        /* 餘額卡片樣式 */
        .balance-card {{
            background-color: #ffffff;
            border: 1px solid #dee2e6;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            text-align: center;
            margin-bottom: 20px;
        }}
        .balance-text {{
            font-size: 1.1rem;
            color: #6c757d;
            margin-bottom: 5px;
        }}
        .balance-amount {{
            font-size: 2.5rem;
            font-weight: 700;
            color: #007bff; /* 藍色主色調 */
        }}
        
        /* 刪除按鈕更緊湊 */
        .stButton>button {{
            padding: 0.25rem 0.5rem;
            font-size: 0.8rem;
            line-height: 1;
        }}
        
        /* 表格行間距 */
        [data-testid="stContainer"] > div > div:nth-child(2) > div:nth-child(2) [data-testid="stContainer"] {{
            padding: 5px 0;
            border-bottom: 1px dashed #e9ecef;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# --- 2. GCP Firestore 連線與認證 (使用 st.cache_resource) ---

@st.cache_resource(ttl=600) # 緩存客戶端 10 分鐘
def get_user_id():
    """模擬單一用戶 ID，確保數據路徑穩定"""
    return str(uuid.uuid4())

@st.cache_resource(ttl=3600) # 緩存客戶端，避免每次運行都重新驗證
def get_firestore_client():
    """
    初始化 Firestore 客戶端。
    它從 .streamlit/secrets.toml 中的 [gcp_service_account] 區段讀取認證資訊。
    """
    # 1. 檢查 secrets 配置是否存在
    if "gcp_service_account" not in st.secrets:
        # --- 診斷程式碼 ---
        available_keys = list(st.secrets.keys())
        error_msg = (
            f"❌ 錯誤：找不到服務帳戶配置！\n\n"
            f"請確保您的 `.streamlit/secrets.toml` 檔案中包含 `[gcp_service_account]` 區段。\n\n"
            f"--- Streamlit 診斷訊息 ---\n"
            f"目前 Streamlit 讀取到的密鑰鍵值為: {available_keys}\n"
            f"--------------------------"
        )
        st.error(error_msg)
        st.stop() # 停止運行
        return None
    
    try:
        # 2. 使用 st.secrets 字典來初始化 Firestore 客戶端
        db = firestore.Client.from_service_account_info(st.secrets["gcp_service_account"])
        return db
    except Exception as e:
        # 3. 錯誤處理，提供格式提示
        st.error(f"⚠️ GCP Firestore 連線失敗：\n\n請檢查服務帳戶金鑰格式（尤其是 private_key 的三重引號 `\"\"\"` 和換行符）以及 IAM 權限。\n錯誤訊息: {e}")
        st.stop() # 停止運行
        return None

# --- 3. 數據庫路徑輔助函數 (使用 user_id 隔離數據) ---

def get_record_ref(db, user_id):
    """取得交易紀錄集合的參考"""
    # 假設數據結構為: users/{user_id}/records/{record_id}
    return db.collection(f"users/{user_id}/{RECORD_COLLECTION_NAME}")

def get_balance_ref(db, user_id):
    """取得餘額文件的參考"""
    # 假設數據結構為: users/{user_id}/account_status/current_balance
    return db.collection(f"users/{user_id}/{BALANCE_COLLECTION_NAME}").document(BALANCE_DOC_ID)

# --- 4. 數據庫操作函數 ---

def get_current_balance(db, user_id):
    """從 Firestore 讀取當前餘額"""
    balance_doc_ref = get_balance_ref(db, user_id)
    try:
        doc = balance_doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0)
        else:
            # 如果文件不存在，初始化餘額為 0
            balance_doc_ref.set({'balance': 0, 'last_update': datetime.datetime.now()}, merge=True)
            return 0
    except Exception as e:
        st.error(f"讀取餘額失敗: {e}")
        return 0

def update_balance(db, user_id, amount, record_type, is_deletion=False):
    """原子性更新餘額"""
    balance_doc_ref = get_balance_ref(db, user_id)
    
    # 獲取 Transaction 物件
    transaction = db.transaction()
    
    # 定義更新函數
    @firestore.transactional
    def update_in_transaction(transaction, balance_doc_ref, amount, record_type, is_deletion):
        snapshot = balance_doc_ref.get(transaction=transaction)
        
        # 獲取當前餘額，如果文件不存在，則從 0 開始
        current_balance = snapshot.to_dict().get('balance', 0) if snapshot.exists else 0
        
        # 計算新的餘額
        if is_deletion:
            # 刪除時，如果是收入，則扣除；如果是支出，則加回
            new_balance = current_balance - amount if record_type == '收入' else current_balance + amount
        else:
            # 新增時，如果是收入，則增加；如果是支出，則扣除
            new_balance = current_balance + amount if record_type == '收入' else current_balance - amount
            
        # 更新餘額文件
        transaction.set(balance_doc_ref, {
            'balance': new_balance,
            'last_update': firestore.SERVER_TIMESTAMP # 使用服務器時間戳
        })
        
        return new_balance

    # 執行事務
    try:
        new_balance = update_in_transaction(transaction, balance_doc_ref, amount, record_type, is_deletion)
        return new_balance
    except Exception as e:
        st.error(f"餘額更新事務失敗: {e}")
        return get_current_balance(db, user_id) # 失敗時返回舊餘額

def add_record(db, user_id, date, record_type, category, amount, note):
    """新增交易紀錄並更新餘額"""
    records_collection = get_record_ref(db, user_id)
    
    new_record = {
        'id': str(uuid.uuid4()), # 在 Firestore 中，文件 ID 和 document 內容中的 ID 一致
        'date': date,
        'type': record_type,
        'category': category,
        'amount': int(amount),
        'note': note,
        'timestamp': firestore.SERVER_TIMESTAMP # 使用服務器時間戳排序
    }
    
    try:
        # 將紀錄寫入 Firestore，並使用 new_record['id'] 作為文件 ID
        records_collection.document(new_record['id']).set(new_record)
        
        # 更新餘額
        update_balance(db, user_id, new_record['amount'], new_record['type'], is_deletion=False)
        st.success("🎉 紀錄新增成功並已更新餘額!")
    except Exception as e:
        st.error(f"新增紀錄失敗: {e}")

def delete_record(db, user_id, record_id, record_type, record_amount):
    """刪除交易紀錄並反向更新餘額"""
    records_collection = get_record_ref(db, user_id)
    
    try:
        # 刪除交易紀錄
        records_collection.document(record_id).delete()
        
        # 反向更新餘額 (is_deletion=True)
        update_balance(db, user_id, record_amount, record_type, is_deletion=True)
        st.success("🗑️ 紀錄刪除成功並已反向更新餘額!")
    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")

def load_records(db, user_id):
    """從 Firestore 載入所有交易紀錄"""
    records_collection = get_record_ref(db, user_id)
    
    try:
        # 載入所有紀錄，並按時間戳降序排列
        docs = records_collection.order_by('timestamp', direction=firestore.Query.DESCENDING).get()
        
        data = []
        for doc in docs:
            record = doc.to_dict()
            # 確保日期是 datetime.date 對象，方便 pandas 處理
            if isinstance(record.get('date'), datetime.datetime):
                record['date'] = record['date'].date()
            data.append(record)
            
        if not data:
            return pd.DataFrame()
            
        # 轉換為 DataFrame
        df = pd.DataFrame(data)
        
        # 數據清理和類型轉換
        df['amount'] = df['amount'].astype(int)
        df['date'] = pd.to_datetime(df['date'])
        
        return df
    except Exception as e:
        st.error(f"載入交易紀錄失敗: {e}")
        return pd.DataFrame()


# --- 5. Streamlit 主程式 ---

def app():
    # 確保只執行一次 CSS
    set_ui_styles()
    
    st.title("💰 個人記帳本 (Firestore 資料庫版)")
    
    # ---------------------------------------------
    # 關鍵修正: 確保 DB 連線成功並獲取用戶 ID
    # ---------------------------------------------
    db = get_firestore_client()
    user_id = get_user_id()
    
    # 如果連線失敗 (get_firestore_client 會 st.stop())，下面的程式碼將不會執行
    if db is None:
        return
    
    # 在 sidebar 顯示連線狀態
    with st.sidebar:
        st.markdown("### 狀態資訊")
        st.success("🟢 數據庫連線正常")
        st.code(f"用戶 ID: {user_id}", language="text")

    # ---------------------------------------------
    # 側邊欄：新增交易
    # ---------------------------------------------
    with st.sidebar:
        st.header("新增交易紀錄")
        
        with st.form("new_record_form"):
            date = st.date_input("日期", datetime.date.today())
            
            # 類型選擇 (收入/支出)
            record_type = st.radio("類型", list(CATEGORIES.keys()), key="record_type", horizontal=True)
            
            # 類別選擇 (根據類型變動)
            category = st.selectbox("類別", CATEGORIES[record_type], key="record_category")
            
            amount = st.number_input("金額 (TWD)", min_value=1, step=1, key="record_amount")
            note = st.text_area("備註", max_chars=100, key="record_note")
            
            submitted = st.form_submit_button("儲存紀錄", type="primary")

            if submitted:
                if amount <= 0:
                    st.error("金額必須大於 0。")
                else:
                    # 提交數據
                    add_record(db, user_id, date, record_type, category, amount, note)
                    # 提交後需要強制 Streamlit 重新運行以更新數據
                    st.experimental_rerun()
    
    
    # ---------------------------------------------
    # 數據主區塊
    # ---------------------------------------------
    
    # 1. 讀取數據 (從 Firestore 載入)
    df_records = load_records(db, user_id)

    # 2. 餘額顯示
    current_balance = get_current_balance(db, user_id)
    
    st.markdown(
        f"""
        <div class="balance-card">
            <p class="balance-text">當前總餘額</p>
            <p class="balance-amount">TWD {current_balance:,.0f}</p>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 3. 數據分析與視覺化
    st.header("💸 財務概覽與分析")
    
    if df_records.empty:
        st.info("目前沒有任何交易紀錄，請從左側欄新增第一筆紀錄。")
        return # 如果沒有數據，則停止後續的圖表和列表顯示

    
    # 創建一個數據框用於計算月度收支，並按月份排序
    df_records['year_month'] = df_records['date'].dt.to_period('M')
    
    # 計算每筆交易的金額符號
    df_records['signed_amount'] = df_records.apply(
        lambda row: row['amount'] if row['type'] == '收入' else -row['amount'], 
        axis=1
    )
    
    # 按月分組計算總收入和總支出
    monthly_summary = df_records.groupby('year_month').agg(
        total_income=('signed_amount', lambda x: x[x > 0].sum()),
        total_expense=('signed_amount', lambda x: x[x < 0].sum() * -1) # 轉換為正值
    ).fillna(0).reset_index()
    
    monthly_summary['month_str'] = monthly_summary['year_month'].astype(str)
    
    # 融合成適合 Altair 的長格式
    monthly_long = pd.melt(
        monthly_summary, 
        id_vars='month_str', 
        value_vars=['total_income', 'total_expense'],
        var_name='Transaction Type', 
        value_name='Amount'
    )
    
    # 繪製每月收支長條圖
    chart = alt.Chart(monthly_long).mark_bar().encode(
        # 確保 x 軸標籤是月份
        x=alt.X('month_str', title='月份', sort=monthly_summary['month_str'].tolist()),
        y=alt.Y('Amount', title='金額 (TWD)'),
        color=alt.Color('Transaction Type', scale=alt.Scale(domain=['total_income', 'total_expense'], range=['#28a745', '#dc3545'])),
        tooltip=['month_str', 'Transaction Type', alt.Tooltip('Amount', format=',.0f')]
    ).properties(
        title="每月收支趨勢"
    ).interactive() # 允許縮放和平移

    st.altair_chart(chart, use_container_width=True)
    
    # 4. 支出類別圓餅圖 (只看支出)
    st.header("📊 支出類別分佈")
    
    df_expense = df_records[df_records['type'] == '支出'].copy()
    
    if not df_expense.empty:
        category_summary = df_expense.groupby('category')['amount'].sum().reset_index()
        
        # 計算佔比
        category_summary['percentage'] = (category_summary['amount'] / category_summary['amount'].sum())
        
        # 繪製圓餅圖
        pie_chart = alt.Chart(category_summary).mark_arc(outerRadius=120, innerRadius=50).encode(
            theta=alt.Theta("amount", stack=True),
            color=alt.Color("category", title="類別"),
            order=alt.Order("amount", sort="descending"),
            tooltip=["category", alt.Tooltip("amount", format=',.0f'), alt.Tooltip("percentage", format='.1%')]
        ).properties(
            title="支出類別佔比"
        ).view(
            stroke=None # 移除圖表邊框
        )

        st.altair_chart(pie_chart, use_container_width=True)
    else:
        st.info("目前沒有支出紀錄可供分析。")

    # 5. 交易紀錄列表
    st.header("📋 所有交易紀錄")
    
    # 創建一個只包含必要欄位的數據框用於顯示
    display_df = df_records[['id', 'date', 'type', 'category', 'amount', 'note']].rename(columns={
        'id': '文件ID',
        'date': '日期',
        'type': '類型',
        'category': '類別',
        'amount': '金額',
        'note': '備註'
    })
    
    # 調整 st.columns 比例
    col_date_header, col_cat_header, col_amount_header, col_type_header, col_note_header, col_btn_header = st.columns([1.2, 1, 1, 0.7, 6, 1])
    
    col_date_header.markdown(f"<div style='font-weight: bold; background-color: {DEFAULT_BG_COLOR}; padding: 10px 0;'>日期</div>", unsafe_allow_html=True)
    col_cat_header.markdown(f"<div style='font-weight: bold; background-color: {DEFAULT_BG_COLOR}; padding: 10px 0;'>類別</div>", unsafe_allow_html=True)
    col_amount_header.markdown(f"<div style='font-weight: bold; background-color: {DEFAULT_BG_COLOR}; padding: 10px 0;'>金額</div>", unsafe_allow_html=True)
    col_type_header.markdown(f"<div style='font-weight: bold; background-color: {DEFAULT_BG_COLOR}; padding: 10px 0;'>類型</div>", unsafe_allow_html=True)
    col_note_header.markdown(f"<div style='font-weight: bold; background-color: {DEFAULT_BG_COLOR}; padding: 10px 0;'>備註</div>", unsafe_allow_html=True)
    col_btn_header.markdown(f"<div style='font-weight: bold; background-color: {DEFAULT_BG_COLOR}; padding: 10px 0; text-align: center;'>操作</div>", unsafe_allow_html=True)

    # 數據列
    for _, row in df_records.iterrows():
        try:
            # 這裡可以直接使用 row 的值，避免不必要的 to_dict() 調用
            record_id = row['id']
            record_type = row['type']
            record_amount = row['amount']
            record_date = row['date']
            record_category = row['category']
            record_note = row['note']
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
            col_date.write(record_date.strftime('%Y-%m-%d'))
            col_cat.write(record_category)
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {record_amount:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(record_type)
            col_note.write(record_note) # 備註內容
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{record_id}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                # 調用刪除函數
                delete_record(
                    db=db,
                    user_id=user_id,
                    record_id=record_id,
                    record_type=record_type,
                    record_amount=record_amount
                )
                # 刪除後需要強制 Streamlit 重新運行以更新數據
                st.experimental_rerun()


if __name__ == "__main__":
    app()
