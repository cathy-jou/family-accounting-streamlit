import streamlit as st
import pandas as pd
import datetime
import altair as alt
from google.cloud import firestore
import uuid # 導入 uuid 庫用於生成唯一 ID
import os # 導入 os 庫用於環境變數檢查

# --- 0. 配置與變數 ---
DEFAULT_BG_COLOR = "#f8f9fa"
RECORD_COLLECTION_NAME = "records"       # 交易紀錄 Collection 名稱
BALANCE_COLLECTION_NAME = "account_status" # 餘額 Collection 名稱
BALANCE_DOC_ID = "current_balance"       # 餘額文件 ID，固定單一文件
BANK_ACCOUNTS_COLLECTION_NAME = "bank_accounts" # 銀行帳戶 Collection 名稱

# 定義交易類別
CATEGORIES = {
    '收入': ['薪資', '投資收益', '禮金', '其他收入'],
    '支出': ['餐飲', '交通', '購物', '娛樂', '房租/貸款', '教育', '醫療', '其他支出']
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
        h1 {{
            font-size: 1.8rem; font-weight: 700; color: #343a40; margin-bottom: 2.5rem;
        }}
        h2 {{
            font-size: 1.5rem; font-weight: 600; color: #495057; border-bottom: 2px solid #e9ecef;
            padding-bottom: 0.5rem; margin-top: 2rem; margin-bottom: 1.5rem;
        }}
        /* 主要背景顏色 */
        .stApp {{ background-color: {DEFAULT_BG_COLOR}; }}
        /* 交易記錄區塊樣式 */
        .record-row-container {{
            background-color: #ffffff; padding: 0.8rem 1rem; border-radius: 0.5rem;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05); margin-bottom: 0.8rem;
            border: 1px solid #e9ecef;
        }}
        /* Streamlit 按鈕樣式 */
        .stButton>button {{
            border-radius: 0.3rem; font-weight: 600; transition: all 0.2s;
        }}
        /* 刪除按鈕樣式 */
        .stButton>button[kind="secondary"] {{
            border-color: #dc3545; color: #dc3545;
        }}
        .stButton>button[kind="secondary"]:hover {{
             background-color: #f8d7da; /* 懸停時淡紅色背景 */
        }}
        /* 金額顯示對齊 */
        [data-testid="stMarkdownContainer"] span {{
            display: inline-block; text-align: right; min-width: 60px;
        }}
        /* 輸入欄位樣式 */
        .stTextInput>div>div>input, .stDateInput>div>div>input,
        .stSelectbox>div>div>select, .stNumberInput>div>div>input {{
            border-radius: 0.3rem; border: 1px solid #ced4da; padding: 0.5rem 0.75rem;
        }}
        /* 側邊欄輸入框背景和提示文字 */
        section[data-testid="stSidebar"] .stTextInput input,
        section[data-testid="stSidebar"] .stNumberInput input,
        section[data-testid="stSidebar"] .stSelectbox select,
        section[data-testid="stSidebar"] .stTextArea textarea {{
            background-color: #f5f5f5 !important; /* 強制背景色 */
            border: 1px solid #e0e0e0;
        }}
        section[data-testid="stSidebar"] input::placeholder,
        section[data-testid="stSidebar"] textarea::placeholder {{
            color: #adb5bd !important; /* 淡灰色提示文字 */
            opacity: 1 !important;
        }}
        /* 調整 st.columns 內部元素的垂直對齊 */
        [data-testid="column"] > div {{
            display: flex; flex-direction: column; justify-content: flex-start; height: 100%;
        }}
        /* 交易列表標題樣式 */
        .header-row {{
            font-weight: bold; color: #495057; padding: 0.5rem 0;
            border-bottom: 1px solid #dee2e6; margin-bottom: 0.5rem;
        }}
        /* 信息卡片樣式 */
        .info-card {{
            background-color: #ffffff; padding: 1rem; border-radius: 0.5rem;
            text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #e9ecef;
            height: 100%; /* 讓卡片等高 */
            display: flex; flex-direction: column; justify-content: center;
        }}
        .info-card h4 {{ color: #495057; margin: 0 0 0.5rem 0; font-size: 1rem; font-weight: 600; }}
        .info-card p {{ margin: 0; font-size: 1.8rem; font-weight: 700; }}
        .balance-card p {{ color: #343a40; }}
        .income-card {{ background-color: #d4edda; border-color: #c3e6cb; }}
        .income-card h4 {{ color: #155724; }}
        .income-card p {{ color: #28a745; }}
        .expense-card {{ background-color: #f8d7da; border-color: #f5c6cb; }}
        .expense-card h4 {{ color: #721c24; }}
        .expense-card p {{ color: #dc3545; }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# --- 2. Firestore 連線與初始化 ---
@st.cache_resource
def get_user_id() -> str:
    """獲取或生成用戶 ID (簡化版，實際應使用 Firebase Auth)"""
    if 'user_id' not in st.session_state:
        st.session_state['user_id'] = str(uuid.uuid4())
    return st.session_state['user_id']

@st.cache_resource
def get_firestore_client():
    """初始化 Firestore 客戶端，優先使用 secrets，並包含詳細錯誤提示"""
    try:
        if "firestore" in st.secrets:
            # 優先使用 secrets.toml 中的 [firestore] 配置
            creds_info = st.secrets["firestore"]
            # 檢查 project_id 是否存在
            if "project_id" not in creds_info or not creds_info["project_id"]:
                 raise ValueError("Firestore 配置錯誤：'project_id' 缺失或為空。")
            db = firestore.Client.from_service_account_info(creds_info)
            return db
        else:
            # 如果沒有 secrets，則嘗試從環境變數初始化 (用於本地 gcloud auth)
            db = firestore.Client()
            # 嘗試讀取一個文檔以確認連線和 Project ID
            db.collection(BALANCE_COLLECTION_NAME).document("--test--").get()
            return db

    except Exception as e:
        st.error("🚨 Firestore 初始化失敗！")
        st.error(f"原始錯誤訊息: {e}")
        st.warning("請確保您的環境已正確配置 Google Cloud 憑證：")
        st.markdown("""
            * **Streamlit Cloud:** 在 `Secrets` 中設定 `firestore` 鍵，其值為您的服務帳戶 JSON 內容。
            * **本地開發:**
                * 設定 `GOOGLE_APPLICATION_CREDENTIALS` 環境變數指向您的服務帳戶 JSON 檔案路徑。
                * 或使用 `gcloud auth application-default login` 登入。
            * **確認 Project ID:** 錯誤訊息 `"Project was not passed..."` 表示客戶端無法確定專案 ID。請確保您的服務帳戶 JSON 或 gcloud 配置包含正確的專案 ID。
            * **檢查 IAM 權限:** 確保服務帳戶擁有 `Cloud Firestore User` 或更高權限。
            * **檢查 `secrets.toml` 格式:** 確保 `private_key` 使用 `'''` 或 `"""` 包裹且格式正確。
        """)
        st.stop() # 初始化失敗時停止應用程式
        return None # 理論上不會執行到這裡

db = get_firestore_client()
user_id = get_user_id() # 獲取用戶 ID

# --- 3. Firestore 路徑輔助函數 ---
def get_record_ref(db: firestore.Client, user_id: str):
    """獲取用戶交易紀錄的 Collection 參考"""
    return db.collection('users').document(user_id).collection(RECORD_COLLECTION_NAME)

def get_balance_ref(db: firestore.Client, user_id: str):
    """獲取用戶餘額狀態的 Document 參考"""
    return db.collection('users').document(user_id).collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)

def get_bank_accounts_ref(db: firestore.Client, user_id: str):
    """獲取用戶銀行帳戶列表的 Document 參考"""
    # 將銀行帳戶存在 users/{user_id}/account_status/bank_accounts 文件中
    return db.collection('users').document(user_id).collection(BALANCE_COLLECTION_NAME).document(BANK_ACCOUNTS_COLLECTION_NAME)


# --- 4. 數據操作函數 ---
@st.cache_data(ttl=60) # 緩存餘額數據 60 秒
def get_current_balance(db: firestore.Client, user_id: str) -> float:
    """從 Firestore 獲取當前總餘額"""
    balance_ref = get_balance_ref(db, user_id)
    doc = balance_ref.get()
    if doc.exists:
        return doc.to_dict().get('balance', 0.0)
    else:
        # 如果文件不存在，則初始化餘額為 0.0
        balance_ref.set({'balance': 0.0})
        return 0.0

def set_balance(db: firestore.Client, user_id: str, new_balance: float):
    """手動設定 Firestore 中的總餘額"""
    balance_ref = get_balance_ref(db, user_id)
    try:
        balance_ref.set({'balance': float(new_balance), 'last_updated': datetime.datetime.now()})
        st.toast("✅ 總餘額已手動更新！", icon="🎉")
        # 清除快取以強制重新讀取
        get_current_balance.clear()
        # st.rerun() # 通常不需要手動 rerun，Streamlit 會自動檢測變化
    except Exception as e:
        st.error(f"❌ 更新餘額失敗: {e}")

def update_balance_transactional(db: firestore.Client, user_id: str, amount: float, operation: str):
    """使用 Transaction 更新 Firestore 中的餘額"""
    balance_ref = get_balance_ref(db, user_id)

    @firestore.transactional
    def transaction_update(transaction, ref, amount_change):
        snapshot = ref.get(transaction=transaction)
        current_balance = snapshot.to_dict().get('balance', 0.0) if snapshot.exists else 0.0
        new_balance = current_balance + amount_change
        transaction.set(ref, {'balance': new_balance, 'last_updated': datetime.datetime.now()})
        return new_balance

    try:
        transaction = db.transaction()
        amount_change = amount if operation == 'add' else -amount
        transaction_update(transaction, balance_ref, amount_change)
        # 更新成功後清除相關快取
        get_current_balance.clear()
        get_all_records.clear() # 餘額變動，交易紀錄的快取也應清除
    except Exception as e:
        st.error(f"❌ 更新餘額時發生錯誤: {e}")

@st.cache_data(ttl=60) # 緩存交易紀錄 60 秒
def get_all_records(db: firestore.Client, user_id: str) -> pd.DataFrame:
    """從 Firestore 獲取用戶的所有交易紀錄"""
    records_ref = get_record_ref(db, user_id)
    try:
        # 使用 get() 一次性獲取所有文件快照，更穩定
        docs = records_ref.order_by("date", direction=firestore.Query.DESCENDING).get()

        data = []
        for doc in docs:
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id
            # 將 Firestore Timestamp 轉換為 Python datetime (如果需要)
            if 'date' in doc_data and hasattr(doc_data['date'], 'to_pydatetime'):
                 # 只取日期部分，並確保是 date 物件
                 doc_data['date'] = doc_data['date'].to_pydatetime().date()
            elif isinstance(doc_data.get('date'), str): # 處理舊格式 (字串)
                try:
                    doc_data['date'] = datetime.datetime.strptime(doc_data['date'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    doc_data['date'] = None # 或設為預設值
            else:
                 # 確保 date 欄位存在且類型可處理
                 doc_data['date'] = None

            # 確保 timestamp 存在且是 datetime 物件
            if 'timestamp' in doc_data and hasattr(doc_data['timestamp'], 'to_pydatetime'):
                doc_data['timestamp'] = doc_data['timestamp'].to_pydatetime()
            else:
                doc_data['timestamp'] = None # 或使用文件的 create_time/update_time

            data.append(doc_data)

        # 預期從 Firestore 讀取的欄位
        expected_columns = ['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp']

        if not data:
            # 返回帶有正確欄位的空 DataFrame
            return pd.DataFrame(columns=expected_columns)

        df = pd.DataFrame(data)

        # 確保所有預期欄位都存在，若不存在則補上空值
        for col in expected_columns:
            if col not in df.columns:
                df[col] = None

        # 確保 'date' 欄位是日期時間類型，並處理可能的錯誤
        # errors='coerce' 會將無法轉換的值設為 NaT (Not a Time)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        # 移除日期轉換失敗的行 (NaT) - 改為保留，後續處理顯示
        # df = df.dropna(subset=['date'])

        # 轉換其他類型
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        df['type'] = df['type'].astype(str)
        df['category'] = df['category'].astype(str)
        df['note'] = df['note'].astype(str)
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

        # 只保留預期的欄位 - 修正: 確保不丟失必要欄位
        # df = df[expected_columns]

        return df

    except Exception as e:
        st.error(f"❌ 獲取交易紀錄失敗: {e}")
        # 返回帶有正確欄位的空 DataFrame
        return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])


def add_record(db: firestore.Client, user_id: str, record_data: dict):
    """向 Firestore 添加一筆交易紀錄"""
    records_ref = get_record_ref(db, user_id)
    try:
        # 將 date 轉換為 datetime 儲存 (Firestore 要求 datetime)
        record_date = record_data.get('date')
        if isinstance(record_date, datetime.date):
            record_data['date'] = datetime.datetime.combine(record_date, datetime.time.min)
        elif not isinstance(record_date, datetime.datetime):
             # 如果不是 date 或 datetime，嘗試轉換或設為當前時間
             record_data['date'] = datetime.datetime.now()
             st.warning("日期格式無法識別，已使用當前時間。")

        # 確保 timestamp 是 datetime
        record_data['timestamp'] = datetime.datetime.now()

        doc_ref = records_ref.add(record_data) # add 會返回 DocumentReference 和 timestamp
        st.toast("✅ 交易紀錄已新增！", icon="🎉")

        # 更新餘額
        amount = float(record_data['amount'])
        operation = 'add' if record_data['type'] == '收入' else 'subtract'
        update_balance_transactional(db, user_id, amount, operation)

    except Exception as e:
        st.error(f"❌ 新增紀錄失敗: {e}")
        st.error(f"紀錄數據: {record_data}") # 打印出問題數據幫助除錯

def delete_record(db: firestore.Client, user_id: str, record_id: str, record_type: str, record_amount: float):
    """從 Firestore 刪除一筆交易紀錄並回滾餘額"""
    record_doc_ref = get_record_ref(db, user_id).document(record_id)
    try:
        record_doc_ref.delete()
        st.toast("🗑️ 交易紀錄已刪除！", icon="✅")

        # 回滾餘額
        operation = 'subtract' if record_type == '收入' else 'add' # 注意操作相反
        update_balance_transactional(db, user_id, float(record_amount), operation)

        st.rerun() # 強制刷新頁面

    except Exception as e:
        st.error(f"❌ 刪除紀錄失敗: {e}")


@st.cache_data(ttl=300) # 緩存銀行帳戶數據 5 分鐘
def load_bank_accounts(db: firestore.Client, user_id: str) -> dict:
    """從 Firestore 加載銀行帳戶列表"""
    accounts_ref = get_bank_accounts_ref(db, user_id)
    try:
        doc = accounts_ref.get()
        if doc.exists:
            # 確保返回的是字典
            data = doc.to_dict()
            return data.get("accounts", {}) if isinstance(data, dict) else {}
        else:
            # 如果文件不存在，創建一個空的
            accounts_ref.set({"accounts": {}})
            return {}
    except Exception as e:
        st.error(f"❌ 加載銀行帳戶失敗: {e}")
        return {}


def update_bank_accounts(db: firestore.Client, user_id: str, accounts_data: dict):
    """更新 Firestore 中的銀行帳戶列表"""
    accounts_ref = get_bank_accounts_ref(db, user_id)
    try:
        # 確保 accounts_data 是字典
        if not isinstance(accounts_data, dict):
            raise TypeError("accounts_data 必須是字典")
        accounts_ref.set({"accounts": accounts_data, 'last_updated': datetime.datetime.now()})
        # 清除快取
        load_bank_accounts.clear()
        st.toast("🏦 銀行帳戶資訊已更新！")
    except Exception as e:
        st.error(f"❌ 更新銀行帳戶失敗: {e}")

# --- 5. CSV/Excel 導出函數 ---
@st.cache_data
def convert_df_to_csv(df: pd.DataFrame):
    """
    將 DataFrame 轉換為 CSV 格式 (utf-8 編碼)，供下載使用。
    修正 KeyError: 使用更健壯的方式處理欄位重命名和選取。
    """
    if df is None or df.empty:
        return "".encode('utf-8') # 返回空的字節串

    # 複製 DataFrame 以避免修改原始數據
    df_copy = df.copy()

    # 原始欄位名 (必須與 get_all_records 返回的 DataFrame 一致)
    # 假設為: 'id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'
    column_mapping = {
        'date': '日期',
        'type': '類型',
        'category': '類別',
        'amount': '金額',
        'note': '備註',
        'id': '文件ID',
        'timestamp': '儲存時間'
    }

    # 實際存在的欄位進行重命名
    cols_to_rename = {k: v for k, v in column_mapping.items() if k in df_copy.columns}
    df_renamed = df_copy.rename(columns=cols_to_rename)

    # 定義最終要匯出的欄位順序 (使用中文名稱)
    target_columns_ordered = ['日期', '類型', '類別', '金額', '備註', '文件ID', '儲存時間']

    # 過濾出重命名後實際存在的欄位，並保持順序
    existing_columns_in_order = [col for col in target_columns_ordered if col in df_renamed.columns]

    # 確保至少有部分欄位存在
    if not existing_columns_in_order:
        st.warning("無法匯出 CSV：處理後的 DataFrame 中缺少所有預期的欄位。")
        return "".encode('utf-8')

    # 使用實際存在的欄位列表進行選取
    df_export = df_renamed[existing_columns_in_order].copy() # 使用 .copy() 避免 SettingWithCopyWarning

    # --- 格式化 ---
    # 格式化日期 (只保留 YYYY-MM-DD)
    if '日期' in df_export.columns:
        # 確保日期是 datetime 類型再格式化
        # 先轉換為 datetime64[ns]，處理 NaT，再格式化
        df_export['日期'] = pd.to_datetime(df_export['日期'], errors='coerce').dt.strftime('%Y-%m-%d').fillna('')

    # 格式化儲存時間 (如果存在)
    if '儲存時間' in df_export.columns:
         df_export['儲存時間'] = pd.to_datetime(df_export['儲存時間'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

    # 確保金額是整數
    if '金額' in df_export.columns:
        df_export['金額'] = pd.to_numeric(df_export['金額'], errors='coerce').fillna(0).astype(int)

    # 轉換為 CSV 字節串
    try:
        return df_export.to_csv(index=False).encode('utf-8')
    except Exception as e:
        st.error(f"轉換 CSV 失敗: {e}")
        return "".encode('utf-8')


# --- 6. UI 組件 ---
def display_dashboard(db, user_id):
    """顯示儀表板主頁內容"""
    st.title("👨‍👩‍👧‍👦 雲端家庭記帳本")

    # 獲取數據
    df_records = get_all_records(db, user_id)
    current_balance = get_current_balance(db, user_id)

    # --- 概覽卡片 ---
    st.markdown("## 📊 財務概覽")
    total_income = df_records[df_records['type'] == '收入']['amount'].sum() if not df_records.empty else 0
    total_expense = df_records[df_records['type'] == '支出']['amount'].sum() if not df_records.empty else 0

    col_bal, col_inc, col_exp = st.columns(3)
    with col_bal:
        st.markdown(f"<div class='info-card balance-card'><h4>當前總餘額</h4><p>{current_balance:,.0f}</p></div>", unsafe_allow_html=True)
    with col_inc:
        st.markdown(f"<div class='info-card income-card'><h4>期間總收入</h4><p>+ {total_income:,.0f}</p></div>", unsafe_allow_html=True)
    with col_exp:
        st.markdown(f"<div class='info-card expense-card'><h4>期間總支出</h4><p>- {total_expense:,.0f}</p></div>", unsafe_allow_html=True)

    st.markdown("---", unsafe_allow_html=True) # 分隔線

    # --- 數據分析圖表 ---
    st.markdown("## 📈 數據分析")
    if df_records.empty:
        st.info("ℹ️ 尚無交易紀錄可供分析。")
    else:
        # 月度趨勢圖
        st.markdown("### 月度收支趨勢")
        try:
            # 確保 'date' 欄位存在且是 datetime 類型
            if 'date' in df_records.columns and pd.api.types.is_datetime64_any_dtype(df_records['date']):
                # 確保 DataFrame 非空才計算
                if not df_records['date'].dropna().empty:
                    df_records['month'] = df_records['date'].dt.to_period('M').astype(str)
                    df_monthly = df_records.groupby(['month', 'type'])['amount'].sum().reset_index()

                    chart_trend = alt.Chart(df_monthly).mark_bar().encode(
                        x=alt.X('month', title='月份', sort='ascending'),
                        y=alt.Y('amount', title='金額 (NTD)'),
                        color=alt.Color('type', title='類型', scale=alt.Scale(domain=['收入', '支出'], range=['#28a745', '#dc3545'])),
                        tooltip=['month', 'type', alt.Tooltip('amount', format=',.0f')]
                    ).properties(height=300).interactive()
                    st.altair_chart(chart_trend, use_container_width=True)
                else:
                    st.info("日期數據不足，無法生成月度趨勢圖。")
            else:
                 st.warning("日期欄位格式不正確，無法生成月度趨勢圖。")

        except Exception as e:
            st.error(f"生成月度趨勢圖失敗: {e}")


        # 支出類別分佈圖
        st.markdown("### 支出類別分佈")
        df_expense = df_records[df_records['type'] == '支出'].copy()
        if not df_expense.empty:
            df_expense_grouped = df_expense.groupby('category')['amount'].sum().reset_index()
            # 確保金額大於 0 才繪圖
            df_expense_grouped = df_expense_grouped[df_expense_grouped['amount'] > 0]

            if not df_expense_grouped.empty:
                total_expense_chart = df_expense_grouped['amount'].sum()
                if total_expense_chart > 0: # 避免除以零
                    df_expense_grouped['percentage'] = (df_expense_grouped['amount'] / total_expense_chart)
                else:
                    df_expense_grouped['percentage'] = 0.0


                base = alt.Chart(df_expense_grouped).encode(
                    theta=alt.Theta("amount", stack=True)
                )
                pie = base.mark_arc(outerRadius=120, innerRadius=60).encode(
                    color=alt.Color("category", title="類別"),
                    order=alt.Order("amount", sort="descending"),
                    tooltip=["category",
                             alt.Tooltip("amount", format=',.0f', title="金額"),
                             alt.Tooltip("percentage", format=".1%", title="佔比")]
                ).properties(title="支出金額分佈圖")

                # 移除文字標籤，避免重疊
                # text = base.mark_text(radius=140).encode(
                #     text=alt.Text("percentage", format=".1%"),
                #     order=alt.Order("amount", sort="descending"),
                #     color=alt.value("black") # 固定標籤顏色
                # )
                st.altair_chart(pie, use_container_width=True) # 只顯示 pie chart
            else:
                st.info("ℹ️ 支出金額皆為零，無法生成分佈圖。")
        else:
            st.info("ℹ️ 尚無支出紀錄可繪製分佈圖。")

    st.markdown("---", unsafe_allow_html=True) # 分隔線

def display_record_input(db, user_id):
    """顯示新增交易紀錄的表單"""
    st.markdown("## 📝 新增交易紀錄")

    # 將類型選擇移到 Form 外部，以便觸發類別更新
    record_type = st.radio(
        "選擇類型",
        options=['支出', '收入'],
        horizontal=True,
        key='record_type_selector', # 給定 key 避免狀態混亂
        help="選擇交易是收入還是支出"
    )

    with st.form("new_record_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        # 類別 (根據外部的 record_type 動態更新)
        category_options = CATEGORIES.get(record_type, [])
        # 新增自訂選項
        if record_type == '支出':
            all_db_categories = get_all_categories(db, user_id)
            # 合併預設和資料庫中的類別，去重並排序
            unique_categories = sorted(list(set(category_options + all_db_categories)))
            category_options = unique_categories + ["⚙️ 新增自訂支出類別..."]
        elif record_type == '收入':
             category_options = CATEGORIES.get('收入', []) # 收入類別固定

        category = col1.selectbox(
            "選擇類別",
            options=category_options,
            key=f'category_select_{record_type}', # 使用類型作為 key
            help="選擇交易的細分類別，或新增自訂類別"
        )

        # 如果選擇自訂，則顯示輸入框
        custom_category = ""
        if category == "⚙️ 新增自訂支出類別...":
            custom_category = col1.text_input("輸入新類別名稱", key='custom_category_input', placeholder="例如：寵物用品")

        # 金額
        amount = col2.number_input(
            "輸入金額 (NTD)",
            min_value=1, value=100, step=1, format="%d",
            key='amount_input',
            placeholder="請輸入正整數金額"
        )

        col3, col4 = st.columns(2)
        # 日期
        date = col3.date_input(
            "選擇日期", datetime.date.today(), max_value=datetime.date.today(),
            key='date_input'
        )

        # 備註
        note = col4.text_area(
            "輸入備註 (可選)", height=80,
            key='note_input',
            placeholder="例如：晚餐 - 麥當勞"
        )

        submitted = st.form_submit_button("💾 儲存紀錄", use_container_width=True)

        if submitted:
            final_category = category
            if category == "⚙️ 新增自訂支出類別...":
                if not custom_category.strip():
                    st.warning("⚠️ 請輸入自訂類別的名稱。")
                    st.stop() # 阻止提交
                final_category = custom_category.strip()
            elif not category:
                 st.warning("⚠️ 請選擇一個類別。")
                 st.stop() # 阻止提交

            record_data = {
                'date': date,
                'type': record_type,
                'category': final_category,
                'amount': float(amount),
                'note': note.strip() or "無備註",
                'timestamp': datetime.datetime.now()
            }
            add_record(db, user_id, record_data)
            # 清除快取並重跑以更新儀表板
            st.cache_data.clear() # 清除所有 @st.cache_data
            st.cache_resource.clear() # 清除所有 @st.cache_resource (包括 DB 連線，下次自動重連)
            st.rerun()

@st.cache_data(ttl=300) # 緩存類別列表 5 分鐘
def get_all_categories(db: firestore.Client, user_id: str) -> list:
    """從 Firestore 獲取用戶所有使用過的支出類別"""
    records_ref = get_record_ref(db, user_id)
    try:
        # 只查詢支出類別
        query = records_ref.where('type', '==', '支出').select(['category']).stream()
        # 使用 set 處理 None 的情況
        categories = set(doc.to_dict().get('category') for doc in query if doc.to_dict() and doc.to_dict().get('category'))
        return sorted(list(categories))
    except Exception as e:
        # st.warning(f"獲取歷史類別失敗: {e}") # 正式版可移除警告
        return []


def display_records_list(db, user_id, df_records):
    """顯示交易紀錄列表，包含篩選和刪除"""
    st.markdown("## 📜 交易紀錄")

    if df_records is None or df_records.empty:
        st.info("ℹ️ 目前沒有任何交易紀錄。")
        return

    # --- 篩選器 ---
    st.markdown("### 篩選紀錄")
    col1, col2, col3 = st.columns([1, 1, 2])

    # 1. 月份篩選 (使用最新資料中的月份)
    # 確保 'date' 欄位存在且為 datetime 類型
    if 'date' not in df_records.columns or not pd.api.types.is_datetime64_any_dtype(df_records['date']):
         st.warning("日期欄位缺失或格式不正確，無法進行月份篩選。")
         all_months = []
         selected_month = None
    else:
        # 使用 .dt accessor 前確保非空且無 NaT
        date_series = df_records['date'].dropna()
        if not date_series.empty:
            df_records['month_year_period'] = df_records['date'].dt.to_period('M')
            all_months = sorted(df_records['month_year_period'].dropna().unique().astype(str), reverse=True)
        else:
            all_months = []

        if not all_months:
             selected_month = None
             st.info("尚無紀錄可供篩選月份。")
        else:
             # 預設選中最新月份 (索引 0)
             selected_month = col1.selectbox(
                 "選擇月份",
                 options=all_months,
                 index=0, # 預設最新月份
                 key='month_selector'
             )

    # 2. 類型篩選
    type_filter = col2.selectbox(
        "選擇類型",
        options=['全部', '收入', '支出'],
        key='type_filter'
    )

    # 根據選定月份和類型篩選 DataFrame
    df_filtered = df_records.copy()
    if selected_month:
        try:
             # 將選中的月份字串轉回 Period 物件進行比較
             selected_month_period = pd.Period(selected_month, freq='M')
             # 確保 'month_year_period' 欄位存在
             if 'month_year_period' in df_filtered.columns:
                 # 使用 .loc 避免 SettingWithCopyWarning
                 df_filtered = df_filtered.loc[df_filtered['month_year_period'] == selected_month_period].copy()
             else:
                 st.warning("無法按月份篩選，月份欄位處理出錯。")
        except (ValueError, TypeError):
             st.error("月份格式錯誤，無法篩選。")

    if type_filter != '全部':
        # 使用 .loc 避免 SettingWithCopyWarning
        df_filtered = df_filtered.loc[df_filtered['type'] == type_filter].copy()

    # 確保篩選後按日期倒序
    df_filtered = df_filtered.sort_values(by='date', ascending=False)


    # --- 導出按鈕 ---
    if not df_filtered.empty:
        csv = convert_df_to_csv(df_filtered) # 使用篩選後的數據
        file_name_month = selected_month if selected_month else "all"
        # 檢查 csv 是否為空字節串
        if csv:
            col3.download_button(
                label="📥 下載篩選結果 (CSV)",
                data=csv,
                file_name=f'交易紀錄_{file_name_month}.csv',
                mime='text/csv',
                key='download_csv_button'
            )
        else:
            col3.warning("CSV 轉換失敗，無法下載。")
    else:
        col3.info("沒有符合篩選條件的紀錄可供下載。")


    st.markdown("---") # 分隔線

    # --- 紀錄列表標題 ---
    st.markdown("### 紀錄明細")
    header_cols = st.columns([1.2, 1, 1, 0.7, 9, 1]) # 增加備註寬度
    headers = ['日期', '類別', '金額', '類型', '備註', '操作']
    for col, header in zip(header_cols, headers):
        col.markdown(f"**{header}**")

    # --- 顯示篩選後的紀錄 ---
    if df_filtered.empty:
        st.info("ℹ️ 沒有符合篩選條件的交易紀錄。")
    else:
        for index, row in df_filtered.iterrows():
            try:
                record_id = row['id']
                # 檢查 date 是否為 NaT
                record_date_obj = row.get('date')
                if pd.isna(record_date_obj):
                    record_date_str = "日期錯誤"
                else:
                    # 嘗試格式化日期
                     try:
                          record_date_str = record_date_obj.strftime('%Y-%m-%d')
                     except AttributeError: # 如果不是 datetime 物件
                          record_date_str = str(record_date_obj).split(' ')[0] # 嘗試取日期部分
                     except ValueError: # 無效日期
                          record_date_str = "日期格式無效"

                record_type = row.get('type', 'N/A')
                record_category = row.get('category', 'N/A')
                record_amount = row.get('amount', 0)
                record_note = row.get('note', 'N/A')
            except KeyError as e:
                st.warning(f"紀錄 {row.get('id', 'N/A')} 缺少欄位: {e}，跳過顯示。")
                continue

            color = "#28a745" if record_type == '收入' else "#dc3545"
            amount_sign = "+" if record_type == '收入' else "-"

            with st.container(border=True, height=None): # 使用 container 包裝每一行
                # 使用與標題相同的比例
                row_cols = st.columns([1.2, 1, 1, 0.7, 9, 1])
                row_cols[0].write(record_date_str)
                row_cols[1].write(record_category)
                row_cols[2].markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {record_amount:,.0f}</span>", unsafe_allow_html=True)
                row_cols[3].write(record_type)
                row_cols[4].write(record_note)

                # 刪除按鈕
                delete_button_key = f"delete_{record_id}"
                if row_cols[5].button("🗑️", key=delete_button_key, type="secondary", help="刪除此紀錄"):
                    delete_record(
                        db=db,
                        user_id=user_id,
                        record_id=record_id,
                        record_type=record_type,
                        record_amount=record_amount
                    )
            # st.markdown("---", unsafe_allow_html=True) # 移除行間分隔線，改用 container


def display_balance_management(db, user_id, current_balance):
    """顯示餘額手動管理區塊"""
    st.markdown("## ⚙️ 手動調整總餘額")
    st.info(f"**目前系統計算的總餘額:** NT$ **{current_balance:,.0f}**")
    st.warning("⚠️ **注意：** 手動設定的餘額會覆蓋由交易紀錄計算得出的餘額。請僅在需要校準初始值或修正錯誤時使用。")

    with st.expander("點擊展開以手動設定餘額", expanded=False): # 預設不展開
        with st.form("set_balance_form"):
            new_balance_input = st.number_input(
                "設定新的總餘額 (NT$)",
                min_value=-10_000_000, # 允許負數
                max_value=1_000_000_000, # 設定上限
                value=int(current_balance), # 預設顯示當前餘額
                step=1000,
                format="%d",
                key='new_balance_input',
                help="輸入您希望強制設定的總餘額數值"
            )

            # 加入空行增加間距
            st.markdown("<br>", unsafe_allow_html=True)

            submitted = st.form_submit_button("💰 確認更新餘額", use_container_width=True)

            if submitted:
                set_balance(db, user_id, float(new_balance_input))
                st.rerun() # 更新後立即重跑以顯示新餘額


def display_bank_account_management(db, user_id):
    """顯示銀行帳戶管理區塊"""
    st.markdown("## 🏦 銀行帳戶管理 (手動餘額)")
    st.info("ℹ️ 在此處新增您的銀行、信用卡或電子支付帳戶，並手動記錄其當前餘額。")

    # 加載現有帳戶
    bank_accounts = load_bank_accounts(db, user_id) # 返回字典 {id: {'name': '...', 'balance': ...}}
    account_list = list(bank_accounts.values()) if isinstance(bank_accounts, dict) else [] # 確保是字典

    # 顯示帳戶列表和總額
    total_manual_balance = 0
    if bank_accounts and isinstance(bank_accounts, dict):
        total_manual_balance = sum(float(acc.get('balance', 0)) for acc in bank_accounts.values() if isinstance(acc, dict))
        st.metric("手動帳戶總餘額", f"NT$ {total_manual_balance:,.0f}")

        st.markdown("### 現有帳戶列表")
        # 複製一份 keys 來迭代，避免在迭代過程中修改字典
        account_ids = list(bank_accounts.keys())
        for acc_id in account_ids:
            acc_data = bank_accounts.get(acc_id)
            if not isinstance(acc_data, dict): continue # 跳過無效數據

            col_name, col_balance, col_actions = st.columns([3, 2, 1])
            col_name.write(acc_data.get('name', '未命名帳戶'))
            col_balance.metric("", f"{float(acc_data.get('balance', 0)):,.0f}") # 使用 metric 顯示餘額

            # 刪除按鈕
            if col_actions.button("🗑️ 刪除", key=f"del_acc_{acc_id}", type="secondary"):
                if acc_id in bank_accounts: # 再次確認 key 存在
                    del bank_accounts[acc_id] # 從字典中移除
                    update_bank_accounts(db, user_id, bank_accounts)
                    st.rerun() # 更新後重跑
        st.markdown("---")
    else:
        st.info("尚未新增任何銀行帳戶。")

    # 新增帳戶表單
    st.markdown("### 新增銀行帳戶")
    with st.form("add_bank_account_form", clear_on_submit=True):
        new_account_name = st.text_input("帳戶名稱", placeholder="例如：玉山銀行 活存、街口支付")
        new_account_balance = st.number_input("目前餘額 (NT$)", min_value=-10_000_000, value=0, step=100, format="%d")
        submitted = st.form_submit_button("➕ 新增帳戶")

        if submitted and new_account_name:
            new_account_id = str(uuid.uuid4()) # 為新帳戶生成唯一 ID
            if not isinstance(bank_accounts, dict): bank_accounts = {} # 確保是字典
            bank_accounts[new_account_id] = {'name': new_account_name, 'balance': float(new_account_balance)}
            update_bank_accounts(db, user_id, bank_accounts)
            st.rerun() # 新增後重跑
        elif submitted:
            st.warning("請輸入帳戶名稱。")


# --- 7. 主應用程式框架 ---
def app():
    """主應用程式入口點"""
    set_ui_styles()

    # 初始化 Firestore 和用戶 ID
    db = get_firestore_client()
    user_id = get_user_id()

    # 側邊欄導航
    with st.sidebar:
        st.image("https://placehold.co/150x50/0d6efd/ffffff?text=記帳本", use_column_width=True)
        st.markdown("---")
        st.markdown("## 導航選單")
        page = st.radio(
            "選擇頁面",
            ["📊 儀表板", "📝 新增紀錄", "📜 交易紀錄", "🏦 帳戶管理", "⚙️ 設定餘額"],
            key='page_selector'
        )
        st.markdown("---")
        st.info(f"用戶 ID: `{user_id}`") # 顯示用戶 ID 方便調試

    # --- 頁面內容渲染 ---
    if page == "📊 儀表板":
        display_dashboard(db, user_id)

    elif page == "📝 新增紀錄":
        display_record_input(db, user_id)

    elif page == "📜 交易紀錄":
        df_records = get_all_records(db, user_id)
        display_records_list(db, user_id, df_records)

    elif page == "🏦 帳戶管理":
        display_bank_account_management(db, user_id)

    elif page == "⚙️ 設定餘額":
        current_balance = get_current_balance(db, user_id)
        display_balance_management(db, user_id, current_balance)

# --- 應用程式啟動 ---
if __name__ == '__main__':
    st.set_page_config(
        page_title="個人記帳本",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    app()

