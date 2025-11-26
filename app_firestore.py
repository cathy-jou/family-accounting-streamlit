import streamlit as st
import pandas as pd
import datetime
import altair as alt
from google.cloud import firestore
import uuid # 雖然不再生成，但保留 import 以防未來需要
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
            font-size: 1.5rem; font-weight: 700; color: #343a40; margin-bottom: 2.5rem;
        }}
        h2 {{
            font-size: 1.3rem; font-weight: 600; color: #495057; border-bottom: 2px solid #e9ecef;
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
        .expense-card p {{ 
            color: #dc3545; 
            }}
        /* --- 頁籤 (Tabs) 置中 (已修正) --- */
        div[data-testid="stTabs"] div[role="tablist"] {{
            display: flex;
            justify-content: center;
        }}
        /* --- 📌 調整 Tabs 導航選單字體  --- */
        div[data-testid="stTabs"] div[role="tablist"] button {{
            font-size: 50px;  /* 調整所有頁籤的字體大小 (例如 50px) */
            color: #6c757d;   /* 調整「未選中」頁籤的顏色 (例如 灰色) */
        }}
        div[data-testid="stTabs"] div[role="tablist"] button[aria-selected="true"] {{
            color: #000000;   /* 調整「已選中」頁籤的顏色 (例如 黑色) */
            font-weight: 1000; /* 讓選中的頁籤字體加粗 (可選) */
        }}
        /* --- 📌 結束 --- */
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# --- 2. Firestore 連線與初始化 ---
@st.cache_resource
def get_user_id() -> str:
    """獲取用戶 ID。直接返回硬編碼的固定 ID。"""
    fixed_id = "mABeWsZAaspwFcRNnODI" # <-- 直接在這裡設定您的固定 ID
    # 將固定 ID 存入 session_state 以便後續使用 (如果需要)
    if 'user_id' not in st.session_state or st.session_state['user_id'] != fixed_id:
        st.session_state['user_id'] = fixed_id
    return fixed_id

@st.cache_resource
def get_firestore_client():
    """初始化 Firestore 客戶端，優先使用 secrets，並包含詳細錯誤提示"""
    try:
        if "firestore" in st.secrets:
            # 優先使用 secrets.toml 中的 [firestore] 配置
            creds_info = st.secrets["firestore"]
            if "project_id" not in creds_info or not creds_info["project_id"]:
                 raise ValueError("Firestore 配置錯誤：secrets 中的 'project_id' 缺失或為空。")
            db = firestore.Client.from_service_account_info(creds_info)
            return db
        else:
            # 如果沒有 secrets，則嘗試從環境變數初始化 (用於本地 gcloud auth)
            st.warning("⚠️ 未在 secrets.toml 中找到 'firestore' 配置，嘗試使用環境預設憑證...")
            db = firestore.Client()
            # 嘗試讀取一個文檔以確認連線和 Project ID (可選，確認權限)
            # db.collection(BALANCE_COLLECTION_NAME).document("--test--").get()
            return db

    except Exception as e:
        st.error("🚨 Firestore 初始化失敗！")
        st.error(f"原始錯誤訊息: {e}")
        st.warning("請確保您的環境已正確配置 Google Cloud 憑證：")
        st.markdown("""
            * **Streamlit Cloud:** 在 `Secrets` 中設定 `firestore` 鍵，其值為您的服務帳戶 JSON 內容（包含 `project_id` 等）。
            * **本地開發:**
                * 設定 `GOOGLE_APPLICATION_CREDENTIALS` 環境變數指向您的服務帳戶 JSON 檔案路徑。
                * 或使用 `gcloud auth application-default login` 登入。
            * **確認 Project ID:** 錯誤訊息 `"Project was not passed..."` 表示客戶端無法確定專案 ID。請確保您的服務帳戶 JSON 或 gcloud 配置包含正確的專案 ID。
            * **檢查 IAM 權限:** 確保服務帳戶擁有 `Cloud Firestore User` 或更高權限。
            * **檢查 `secrets.toml` 格式:** 確保 `private_key` 使用 `'''` 
        """)
        st.stop() # 初始化失敗時停止應用程式
        return None

# 初始化放在頂層，確保所有函數都能訪問
try:
    db = get_firestore_client()
    user_id = get_user_id() # 獲取用戶 ID
except Exception as e:
    st.error("應用程式啟動失敗，無法獲取 Firestore 客戶端或用戶 ID。")
    st.stop()


# --- 3. Firestore 路徑輔助函數 ---
def safe_float(v, default=0.0):
    """安全地將值轉換為 float"""
    try:
        return float(v)
    except (ValueError, TypeError, AttributeError):
        try:
            # 嘗試移除逗號和空白
            return float(str(v).replace(',', '').strip())
        except (ValueError, TypeError, AttributeError):
            return default

def safe_int(v, default=0):
    """安全地將值轉換為 int (透過 safe_float)"""
    try:
        # 先轉成 float 再轉 int，以處理 "100.0" 這樣的字串
        return int(safe_float(v, default))
    except (ValueError, TypeError, AttributeError):
        return default

def safe_date(v, default_date=None):
    """安全地將值轉換為 date 物件"""
    if default_date is None:
        default_date = datetime.date.today()
        
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, datetime.datetime):
        return v.date()
    if pd.isna(v) or v is None:
        return default_date
    try:
        # 嘗試從字串或 timestamp 解析
        return pd.to_datetime(v).date()
    except Exception:
        return default_date

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
@st.cache_data(ttl=60, hash_funcs={firestore.Client: id}) # 緩存餘額數據 60 秒
def get_current_balance(db: firestore.Client, user_id: str) -> float:
    """從 Firestore 獲取當前總餘額"""
    if db is None: return 0.0 # 如果 db 未初始化
    balance_ref = get_balance_ref(db, user_id)
    doc = balance_ref.get()
    if doc.exists:
        return doc.to_dict().get('balance', 0.0)
    else:
        # 如果文件不存在，則初始化餘額為 0.0
        try:
            balance_ref.set({'balance': 0.0})
        except Exception as e:
            st.error(f"初始化餘額失敗: {e}")
        return 0.0

def set_balance(db: firestore.Client, user_id: str, new_balance: float):
    """手動設定 Firestore 中的總餘額"""
    if db is None: return
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
    if db is None: return
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


# 📌 修正：加入了 hash_funcs={firestore.Client: id} (修復 UnhashableParamError)
@st.cache_data(ttl=60, hash_funcs={firestore.Client: id}) # 緩存交易紀錄 60 秒
def get_all_records(db: firestore.Client, user_id: str) -> pd.DataFrame:
    """
    從 Firestore 獲取用戶的所有交易紀錄 (強健版本)
    - 優先使用 'date' 欄位
    - 如果 'date' 缺失或無效，自動使用 'timestamp' 欄位作為備援
    """
    if db is None: # 如果 db 未初始化
         return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])

    records_ref = get_record_ref(db, user_id)
    try:
        # 📌 修正：改用 timestamp 排序，這對所有紀錄 (新舊) 都更穩定
        docs = records_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).get()

        data = []
        
        # --- (這是最關鍵的修正：3 步驟備援邏輯) ---
        for doc in docs:
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id
            
            # --- 1. 解析 Timestamp (建立時間) ---
            parsed_timestamp = None # 預設值
            if 'timestamp' in doc_data and hasattr(doc_data['timestamp'], 'to_pydatetime'):
                parsed_timestamp = doc_data['timestamp'].to_pydatetime()
                doc_data['timestamp'] = parsed_timestamp # 儲存 datetime 物件
            elif isinstance(doc_data.get('timestamp'), datetime.datetime):
                parsed_timestamp = doc_data['timestamp']  # 已是 datetime 物件
            else:
                doc_data['timestamp'] = None # 如果無效則存 None

            # --- 2. 解析 Date (交易日期) ---
            parsed_date = None # 預設值
            if 'date' in doc_data and hasattr(doc_data['date'], 'to_pydatetime'):
                # 正常情況： date 是一個 Firestore Timestamp (如 image_502835.png)
                parsed_date = doc_data['date'].to_pydatetime().date()
            elif isinstance(doc_data.get('date'), str): 
                # 舊格式情況： date 是一個字串
                try:
                    parsed_date = datetime.datetime.strptime(doc_data['date'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass # 保持 None，讓它進入備援

            # --- 3. 套用備援 (Fallback) ---
            if parsed_date:
                # 優先使用 'date' 欄位 (轉換為 datetime 物件)
                doc_data['date'] = datetime.datetime.combine(parsed_date, datetime.time.min)
            elif parsed_timestamp:
                # 備援：使用 'timestamp' (它已經是 datetime 物件)
                doc_data['date'] = parsed_timestamp
            else:
                # 最終備援：如果兩者都缺失，才設為 None
                doc_data['date'] = None 
                
            data.append(doc_data)
        # --- (關鍵修正結束) ---


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

        # 先統一時區處理：全部視為 UTC → 再去除時區，避免 tz-aware / tz-naive 混用
        df['date'] = pd.to_datetime(df['date'], errors='coerce', utc=True).dt.tz_convert(None)

        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True).dt.tz_convert(None)
            # 若 date 是 NaT，使用 timestamp 回填
            mask = df['date'].isna() & df['timestamp'].notna()
            df.loc[mask, 'date'] = df.loc[mask, 'timestamp']

        # 其他欄位轉型照舊
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        df['type'] = df['type'].astype(str)
        df['category'] = df['category'].astype(str)
        df['note'] = df['note'].astype(str)

        return df

    except Exception as e:
        st.error(f"❌ 獲取交易紀錄失敗: {e}")
        # 返回帶有正確欄位的空 DataFrame
        return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])


def add_record(db: firestore.Client, user_id: str, record_data: dict):
    """向 Firestore 添加一筆交易紀錄"""
    if db is None: return
    records_ref = get_record_ref(db, user_id)
    try:
        # 1. 獲取用戶選擇的日期 (這是一個 .date 物件)
        record_date_obj = record_data.get('date') 
        
        # 2. 獲取當前的 *UTC* 時間 (使用 timezone-aware)
        # 這樣可以確保無論伺服器在哪個時區，時間都是標準的
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        
        # 3. 判斷 'date' 欄位的值
        if isinstance(record_date_obj, datetime.date) and record_date_obj == now_utc.date():
            # 情況 A: 如果用戶選擇的是 "今天" (以 UTC 日期為準)
            # 讓 'date' 等於 'timestamp'，都設為當下精確的 UTC 時間
            record_data['date'] = now_utc
        
        elif isinstance(record_date_obj, datetime.date):
            # 情況 B: 如果用戶選擇的是 "過去的某天" (補登)
            # 則將 'date' 設為那天的 "午夜 UTC" (00:00 UTC)
            # 我們明確地加入 tzinfo=datetime.timezone.utc
            record_data['date'] = datetime.datetime.combine(record_date_obj, datetime.time.min, tzinfo=datetime.timezone.utc)
        
        else:
            # 情況 C: 備援，如果日期格式不對，也使用當下時間
            st.warning("日期格式無法識別，已使用當前時間。")
            record_data['date'] = now_utc

        # 4. 確保 'timestamp' 欄位 *總是* 儲存當下精確的 UTC 時間
        record_data['timestamp'] = now_utc

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
    if db is None: return
    record_doc_ref = get_record_ref(db, user_id).document(record_id)
    try:
        record_doc_ref.delete()
        
        # 📌 --- 修正：在這裡手動清除快取 --- 📌
        # 確保 get_all_records 函式的快取被清除
        get_all_records.clear() 
        
        st.toast("🗑️ 交易紀錄已刪除！", icon="✅")

        # 回滾餘額
        operation = 'subtract' if record_type == '收入' else 'add' # 注意操作相反
        update_balance_transactional(db, user_id, float(record_amount), operation)

        st.rerun() # 強制刷新頁面

    except Exception as e:
        st.error(f"❌ 刪除紀錄失敗: {e}")

def update_record(db: firestore.Client, user_id: str, record_id: str, new_data: dict, old_data: dict):
    """
    更新 Firestore 中的一筆交易紀錄，並重新計算餘額。
    """
    if db is None: return
    
    # 1. 準備要寫入的新資料 (轉換 date 為 datetime)
    record_doc_ref = get_record_ref(db, user_id).document(record_id)
    
    write_data = new_data.copy()
    record_date = write_data.get('date')
    if isinstance(record_date, datetime.date):
        # 轉換為 UTC datetime (與 add_record 邏輯保持一致)
        # 📌 確保您已在檔案頂部 import datetime
        write_data['date'] = datetime.datetime.combine(record_date, datetime.time.min, tzinfo=datetime.timezone.utc)
    
    # 我們只更新這幾個欄位，保留原始的 timestamp
    try:
        record_doc_ref.update({
            'date': write_data['date'],
            'type': write_data['type'],
            'category': write_data['category'],
            'amount': write_data['amount'],
            'note': write_data['note']
        })
        
        # 2. 計算餘額變動
        # 舊的餘額影響
        old_amount = old_data.get('amount', 0)
        old_balance_effect = old_amount if old_data.get('type') == '收入' else -old_amount
        
        # 新的餘額影響
        new_amount = new_data.get('amount', 0)
        new_balance_effect = new_amount if new_data.get('type') == '收入' else -new_amount
        
        # 淨變動
        net_balance_change = new_balance_effect - old_balance_effect
        
        # 3. 套用餘額變動
        if net_balance_change > 0:
            update_balance_transactional(db, user_id, net_balance_change, 'add')
        elif net_balance_change < 0:
            update_balance_transactional(db, user_id, abs(net_balance_change), 'subtract')
        # else: 餘額不變，無需操作
            
        st.toast("✅ 紀錄已更新！", icon="🎉")
        
        # 4. 清除快取 
        get_all_records.clear() 
        get_current_balance.clear()
        
    except Exception as e:
        st.error(f"❌ 更新紀錄失敗: {e}")


@st.cache_data(ttl=300, hash_funcs={firestore.Client: id}) # 緩存銀行帳戶數據 5 分鐘
def load_bank_accounts(db: firestore.Client, user_id: str) -> dict:
    """從 Firestore 加載銀行帳戶列表"""
    if db is None: return {}
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
    if db is None: return
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
# 移除 @st.cache_data 以避免 UnhashableParamError
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
    # st.title("宅宅家庭記帳本")

    # 獲取數據
    df_records = get_all_records(db, user_id)
    current_balance = get_current_balance(db, user_id)

    # --- 概覽卡片 ---
    # st.markdown("## 財務概覽")
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
    # st.markdown("## 數據分析")
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

def display_record_input(db, user_id):
    """顯示新增交易紀錄的表單 (已修改：支援支付方式)"""
    st.markdown("## 新增交易")

    # 將類型選擇移到 Form 外部
    record_type = st.radio(
        "選擇類型",
        options=['支出', '收入'],
        horizontal=True,
        key='record_type_selector',
        help="選擇交易是收入還是支出"
    )

    with st.form("new_record_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        # 類別
        category_options = CATEGORIES.get(record_type, [])
        if record_type == '支出':
            all_db_categories = get_all_categories(db, user_id)
            unique_categories = sorted(list(set(category_options + all_db_categories)))
            category_options = unique_categories + ["⚙️ 新增自訂支出類別..."]
        elif record_type == '收入':
             category_options = CATEGORIES.get('收入', [])

        category = col1.selectbox(
            "選擇類別",
            options=category_options,
            key=f'category_select_{record_type}',
        )

        custom_category = ""
        if category == "⚙️ 新增自訂支出類別...":
            custom_category = col1.text_input("輸入新類別名稱", key='custom_category_input', placeholder="例如：寵物用品")

        # 金額
        amount = col2.number_input(
            "輸入金額 (NTD)",
            min_value=1, value=100, step=1, format="%d",
            key='amount_input'
        )

        col3, col4 = st.columns(2)
        # 日期
        date = col3.date_input(
            "選擇日期", datetime.date.today(), max_value=datetime.date.today(),
            key='date_input'
        )

        # --- 修改開始：支付方式取代銀行帳戶 ---
        try:
            bank_accounts = load_bank_accounts(db, user_id)
        except Exception:
            bank_accounts = {}

        # 準備支付方式選項
        name_to_id = {data.get('name'): aid for aid, data in bank_accounts.items() if isinstance(data, dict)}
        default_methods = ['現金', '信用卡', '悠遊卡']
        # 過濾已存在的名稱，避免重複
        existing_names = list(name_to_id.keys())
        other_accounts = sorted([n for n in existing_names if n not in default_methods])
        
        display_options = ['（未選擇）'] + default_methods + other_accounts + ['⚙️ 新增自訂...']

        payment_method = st.selectbox(
            "支付方式",
            options=display_options,
            index=0,
            key='payment_method_select',
            help="選擇付款方式（將自動更新對應帳戶餘額）"
        )

        custom_payment_method = ""
        if payment_method == '⚙️ 新增自訂...':
            custom_payment_method = st.text_input("輸入新支付方式名稱", placeholder="例如：LINE Pay", key='custom_method_input')

        # 備註
        note = col4.text_area(
            "輸入備註 (可選)", height=80,
            key='note_input'
        )
        # --- 修改結束 ---

        submitted = st.form_submit_button("➕ 儲存", use_container_width=True)

        if submitted:
            # 1. 處理類別
            final_category = category
            if category == "⚙️ 新增自訂支出類別...":
                if not custom_category.strip():
                    st.warning("⚠️ 請輸入自訂類別的名稱。"); st.stop()
                final_category = custom_category.strip()
            elif not category:
                 st.warning("⚠️ 請選擇一個類別。"); st.stop()

            # 2. 處理支付方式 ID
            final_account_name = None
            final_account_id = None
            
            if payment_method == '⚙️ 新增自訂...':
                if not custom_payment_method.strip():
                    st.warning("⚠️ 請輸入自訂支付方式的名稱。"); st.stop()
                final_account_name = custom_payment_method.strip()
            elif payment_method != '（未選擇）':
                final_account_name = payment_method

            # 若有名稱，查找舊 ID 或生成新 ID
            if final_account_name:
                final_account_id = name_to_id.get(final_account_name)
                if not final_account_id:
                    final_account_id = str(uuid.uuid4()) # 新 ID

            # 3. 建立資料
            record_data = {
                'date': date,
                'type': record_type,
                'category': final_category,
                'amount': float(safe_int(amount)),
                'note': note.strip() or "無備註",
                'timestamp': datetime.datetime.now()
            }
            
            if final_account_id:
                record_data['account_id'] = final_account_id
                record_data['account_name'] = final_account_name

            add_record(db, user_id, record_data)

            # 4. 更新餘額 (包含自動建立新帳戶)
            if final_account_id:
                try:
                    ba = load_bank_accounts(db, user_id) or {}
                    if not isinstance(ba, dict): ba = {}
                    
                    # 獲取或初始化帳戶資料
                    acc_data = ba.get(final_account_id, {'name': final_account_name, 'balance': 0})
                    if 'name' not in acc_data: acc_data['name'] = final_account_name
                    
                    current_bal = safe_float(acc_data.get('balance', 0))
                    delta = float(safe_int(amount)) * (-1.0 if record_type == '支出' else 1.0)
                    ba[final_account_id] = {'name': final_account_name, 'balance': current_bal + delta}
                    
                    update_bank_accounts(db, user_id, ba)
                    st.toast(f"🏦 已更新「{final_account_name}」餘額")
                except Exception as _e:
                    st.warning(f"⚠️ 支付方式餘額更新失敗：{_e}")

            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()

@st.cache_data(ttl=300, hash_funcs={firestore.Client: id}) # 緩存類別列表 5 分鐘
def get_all_categories(db: firestore.Client, user_id: str) -> list:
    """從 Firestore 獲取用戶所有使用過的支出類別"""
    if db is None: return []
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
    """顯示交易紀錄列表，包含篩選、刪除 (📌 修正版：加入編輯功能)"""
    st.markdown("## 歷史紀錄")

    if df_records is None or df_records.empty:
        st.info("ℹ️ 目前沒有任何交易紀錄。")
        return

    # --- 篩選器 (保持不變) ---
    # st.markdown("### 篩選紀錄")
    col1, col2, col3, col4 = st.columns([1, 1, 3, 1])
    
    if 'date' not in df_records.columns or not pd.api.types.is_datetime64_any_dtype(df_records['date']):
         st.warning("日期欄位缺失或格式不正確，無法進行月份篩選。")
         all_months = []
         selected_month = None
    else:
        date_series = df_records['date'].dropna()
        if not date_series.empty:
            df_copy = df_records.copy()
            df_copy['month_year_period'] = df_copy['date'].dt.to_period('M')
            all_months = sorted(df_copy['month_year_period'].dropna().unique().astype(str), reverse=True)
        else:
            all_months = []
        if not all_months:
             selected_month = None
             st.info("尚無紀錄可供篩選月份。")
        else:
            #  selected_month = col1.selectbox("選擇月份", options=all_months, index=0, key='month_selector')
             selected_month = col1.selectbox("", options=all_months, index=0, key='month_selector')
    
    # type_filter = col2.selectbox("選擇類型", options=['全部', '收入', '支出'], key='type_filter')
    type_filter = col2.selectbox("", options=['全部', '收入', '支出'], key='type_filter')
    
    df_filtered = df_records.copy()
    if selected_month:
        try:
             selected_month_period = pd.Period(selected_month, freq='M')
             if 'month_year_period' in df_filtered.columns:
                 df_filtered = df_filtered.loc[df_filtered['month_year_period'] == selected_month_period].copy()
             else:
                 if 'date' in df_filtered.columns and pd.api.types.is_datetime64_any_dtype(df_filtered['date']):
                     date_series_filtered = df_filtered['date'].dropna()
                     if not date_series_filtered.empty:
                         df_filtered['month_year_period'] = df_filtered['date'].dt.to_period('M')
                         df_filtered = df_filtered.loc[df_filtered['month_year_period'] == selected_month_period].copy()
        except (ValueError, TypeError):
             st.error("月份格式錯誤，無法篩選。")

    if type_filter != '全部':
        df_filtered = df_filtered.loc[df_filtered['type'] == type_filter].copy()

    if st.session_state.editing_record_id is None:
        df_filtered = df_filtered.sort_values(by='date', ascending=False)
    
    # --- 導出按鈕 (保持不變) ---
    if not df_filtered.empty:
        csv = convert_df_to_csv(df_filtered) 
        file_name_month = selected_month if selected_month else "all"
        if csv:
            col4.download_button(
                label="📥 下載 (CSV)",
                data=csv,
                file_name=f'交易紀錄_{file_name_month}.csv',
                mime='text/csv',
                key='download_csv_button'
            )
    else:
        col4.info("無紀錄")
    # st.markdown("---")

    # --- 紀錄列表標題 ---
    # st.markdown("### 紀錄明細")
    header_cols = st.columns([1.2, 1, 1, 0.7, 7, 2]) 
    headers = ['日期', '類別', '金額', '類型', '備註', '操作']
    for col, header in zip(header_cols, headers):
        col.markdown(f"**{header}**")

    # --- 顯示篩選後的紀錄 (📌 核心修改) ---
    if df_filtered.empty:
        st.info("ℹ️ 無符合篩選條件的交易紀錄。")
    else:
        for index, row in df_filtered.iterrows():
            try:
                record_id = row['id']
                record_date_obj = row.get('date') 
                record_type = row.get('type', 'N/A')
                record_category = row.get('category', 'N/A')
                record_amount = safe_float(row.get('amount', 0)) 
                record_note = row.get('note', 'N/A')
            except KeyError as e:
                st.warning(f"紀錄 {row.get('id', 'N/A')} 缺少欄位: {e}，跳過顯示。")
                continue

            # 📌 關鍵：檢查這筆紀錄是否正在被編輯
            if record_id == st.session_state.get('editing_record_id'):
                

                # 本地 _safe_date，避免 NaT/None/字串 型別錯誤
                def _safe_date(v):
                    import datetime
                    try:
                        try:
                            import pandas as pd
                            if hasattr(pd, "isna") and pd.isna(v):
                                return datetime.date.today()
                            if isinstance(v, pd.Timestamp):
                                return v.to_pydatetime().date()
                        except Exception:
                            pass
                        try:
                            import numpy as np
                            if isinstance(v, np.datetime64):
                                ts = v.astype('M8[ms]').astype('O')
                                if ts is None:
                                    return datetime.date.today()
                                return ts.date() if hasattr(ts, 'date') else datetime.date.today()
                        except Exception:
                            pass
                        if v is None:
                            return datetime.date.today()
                        if isinstance(v, datetime.datetime):
                            return v.date()
                        if isinstance(v, datetime.date):
                            return v
                        if hasattr(v, "date"):
                            try:
                                return v.date()
                            except Exception:
                                pass
                        s = str(v).strip()
                        if not s:
                            return datetime.date.today()
                        try:
                            return datetime.date.fromisoformat(s[:10])
                        except Exception:
                            return datetime.date.today()
                    except Exception:
                        return datetime.date.today()
                st.markdown(f"**正在編輯：** `{(record_note or '')[:20]}...`")
                edit_cols_1 = st.columns(3)
                with edit_cols_1[0]:
                    default_date = safe_date(record_date_obj) # <-- 直接使用全域函式
                    new_date = st.date_input("日期", value=_safe_date(default_date), key=f"edit_date_{record_id}")
                with edit_cols_1[1]:
                    new_type = st.radio("類型", ['支出', '收入'], index=0 if record_type == '支出' else 1, key=f"edit_type_{record_id}", horizontal=True)
                with edit_cols_1[2]:
                    new_amount = st.number_input("金額", min_value=0, value=safe_int(record_amount), step=1, format="%d", key=f"edit_amount_{record_id}")
                
                edit_cols_2 = st.columns(2)
                with edit_cols_2[0]:
                    category_options = CATEGORIES.get(new_type, [])
                    if new_type == '支出':
                        try:
                            all_db_categories = get_all_categories(db, user_id)
                        except Exception:
                            all_db_categories = []
                        category_options = sorted(list(set((category_options or []) + (all_db_categories or []))))
                    try:
                        cat_index = category_options.index(record_category)
                    except ValueError:
                        if record_category:
                            category_options = (category_options or []) + [record_category]
                            cat_index = category_options.index(record_category)
                        else:
                            cat_index = 0
                    new_category = st.selectbox("類別", options=category_options or ["未分類"], index=min(cat_index, max(len(category_options)-1, 0)), key=f"edit_cat_{record_id}")
                with edit_cols_2[1]:
                    new_note = st.text_area("備註", value=record_note or "", key=f"edit_note_{record_id}", height=100)
                
                btn_cols = st.columns([1,1,3])
                save_clicked = btn_cols[0].button("💾 儲存變更", use_container_width=True, key=f"save_btn_{record_id}")
                cancel_clicked = btn_cols[1].button("❌ 取消", use_container_width=True, key=f"cancel_btn_{record_id}")
                
                if cancel_clicked:
                    st.session_state.editing_record_id = None
                    st.rerun()
                
                if save_clicked:
                    if new_amount is None or safe_int(new_amount) <= 0:
                        st.warning("⚠️ 金額需為正整數")
                    elif not isinstance(new_date, datetime.date):
                        st.warning("⚠️ 日期格式不正確")
                    elif not new_category:
                        st.warning("⚠️ 請選擇/輸入類別")
                    else:
                        new_data = {
                            'date': new_date,
                            'type': new_type,
                            'category': new_category,
                            'amount': float(safe_int(new_amount)),
                            'note': (new_note or "").strip() or "無備註",
                        }
                        old_data = {'type': record_type, 'amount': record_amount}
                        update_record(db, user_id, record_id, new_data, old_data)
                        st.session_state.editing_record_id = None
                        st.rerun()
# 📌 表單在這裡結束

            else:
                
                if pd.isna(record_date_obj):
                    record_id_str = row.get('id', 'N/A') 
                    record_date_str = f"日期錯誤 (ID: {record_id_str})"
                else:
                    try:
                        #  record_date_str = record_date_obj.strftime('%Y-%m-%d')
                         record_date_str = safe_date(record_date_obj).strftime('%Y-%m-%d')
                    except Exception:
                         record_date_str = str(record_date_obj).split(' ')[0]

                color = "#28a745" if record_type == '收入' else "#dc3545"
                amount_sign = "+" if record_type == '收入' else "-"

                with st.container(border=True):
                    row_cols = st.columns([1.2, 1, 1, 0.7, 7, 2]) 
                    row_cols[0].write(record_date_str)
                    row_cols[1].write(record_category)
                    row_cols[2].markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {record_amount:,.0f}</span>", unsafe_allow_html=True)
                    row_cols[3].write(record_type)
                    row_cols[4].write(record_note)

                    if row_cols[5].button("✏️", key=f"edit_{record_id}", help="編輯此紀錄"):
                        st.session_state.editing_record_id = record_id
                        st.rerun()

                    if row_cols[5].button("🗑️", key=f"delete_{record_id}", type="secondary", help="刪除此紀錄"):
                        delete_record(
                            db=db,
                            user_id=user_id,
                            record_id=record_id,
                            record_type=record_type,
                            record_amount=record_amount
                        )

def display_balance_management(db, user_id, current_balance):
    """顯示餘額手動管理區塊"""
    st.markdown("## ⚙️ 手動調整總餘額")
    st.info(f"**目前系統計算的總餘額:** NT$ **{current_balance:,.0f}**")
    st.warning("⚠️ **注意：** 請僅在需要校準初始值或修正錯誤時使用")

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
                help="輸入強制設定的總餘額"
            )

            # 加入空行增加間距
            st.markdown("<br>", unsafe_allow_html=True)

            submitted = st.form_submit_button("確認更新餘額", use_container_width=True)

            if submitted:
                set_balance(db, user_id, float(new_balance_input))
                st.rerun() # 更新後立即重跑以顯示新餘額


def display_bank_account_management(db, user_id):
    """顯示銀行帳戶管理區塊 (📌 修正版：允許直接更新餘額)"""
    st.markdown("## 銀行帳戶 (手動)")
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
        
        # 📌 修正：調整欄位寬度以容納兩個按鈕
        col_name_header, col_balance_header, col_actions_header = st.columns([3, 2, 2])
        col_name_header.markdown("**帳戶名稱**")
        col_balance_header.markdown("**目前餘額**")
        col_actions_header.markdown("**操作**")

        for acc_id in account_ids:
            acc_data = bank_accounts.get(acc_id)
            if not isinstance(acc_data, dict): continue # 跳過無效數據

            # 📌 修正：使用 st.columns 來對齊每一行
            col_name, col_balance, col_actions = st.columns([3, 2, 2])
            
            col_name.write(acc_data.get('name', '未命名帳戶'))

            # 📌 修正：將 st.metric 替換為 st.number_input
            # 使用唯一的 key (acc_id) 來讓 Streamlit 追蹤每個輸入框的狀態
            col_balance.number_input(
                "餘額",
                value=int(acc_data.get('balance', 0)),
                step=100,
                format="%d",
                key=f"balance_{acc_id}", # 關鍵：唯一的 key
                label_visibility="collapsed" # 隱藏標籤，節省空間
            )

            # 📌 修正：新增 "更新" 按鈕
            if col_actions.button("🔄 更新", key=f"update_acc_{acc_id}"):
                # 從 st.session_state 讀取 number_input 的當前值
                new_balance = st.session_state[f"balance_{acc_id}"]
                bank_accounts[acc_id]['balance'] = float(new_balance)
                
                # 更新 Firestore
                update_bank_accounts(db, user_id, bank_accounts)
                st.toast(f"✅ 已更新 '{acc_data.get('name')}' 餘額")
                st.rerun() # 重新整理以確保狀態一致

            # 📌 修正：將 "刪除" 按鈕移到 col_actions 欄位中
            if col_actions.button("🗑️ 刪除", key=f"del_acc_{acc_id}", type="secondary"):
                if acc_id in bank_accounts: # 再次確認 key 存在
                    del bank_accounts[acc_id] # 從字典中移除
                    update_bank_accounts(db, user_id, bank_accounts)
                    st.toast(f"🗑️ 已刪除 '{acc_data.get('name')}'")
                    st.rerun() # 更新後重跑
        
        st.markdown("---")
    else:
        st.info("尚未新增任何銀行帳戶。")

    # (新增帳戶的表單保持不變)
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


# --- 7. 主應用程式框架 (使用 st.tabs) ---

def display_quick_entry_on_home(db, user_id):
    """首頁的『快速記帳』：新增淡灰色示範提示 (Placeholder)"""
    
    if 'show_quick_entry' not in st.session_state:
        st.session_state.show_quick_entry = False

    st.markdown("### 🧾 快速記帳")

    if not st.session_state.show_quick_entry:
        c_left, c_mid, c_right = st.columns([1,2,1])
        with c_mid:
            if st.button("🧾 快速記帳", use_container_width=True, key="btn_show_quick_entry"):
                st.session_state.show_quick_entry = True
                st.rerun()
        return

    # --- 準備數據 ---
    CATEGORY_OPTIONS = ["食", "衣", "住", "行", "育樂", "其他"]
    
    try:
        bank_accounts = load_bank_accounts(db, user_id)
    except:
        bank_accounts = {}
    
    name_to_id = {data.get('name'): aid for aid, data in bank_accounts.items() if isinstance(data, dict)}
    default_methods = ['現金', '信用卡', '悠遊卡']
    existing_names = list(name_to_id.keys())
    
    # 🔴 修改 1: 移除 '(未選擇)'，直接準備純淨的選項列表，讓 placeholder 生效
    payment_options = default_methods + sorted([n for n in existing_names if n not in default_methods])

    # --- 版面配置 ---
    row1 = st.columns([2, 2, 2, 2.5, 1.5])

    with row1[0]:
        # 🔴 修改 2: index=None 讓框框變空，並加上 placeholder
        category = st.selectbox(
            "類別", 
            options=CATEGORY_OPTIONS, 
            index=None,  # 預設不選
            key='quick_entry_category', 
            label_visibility="collapsed", 
            placeholder="類別" # 提示詞
        )
    with row1[1]:
        # 🔴 修改 3: value=None 讓框框變空，並加上 placeholder
        amount = st.number_input(
            "金額", 
            min_value=0, 
            value=None, # 預設為空
            step=100, 
            format="%d", 
            key='quick_entry_amount', 
            label_visibility="collapsed", 
            placeholder="支出 (臺幣)" # 提示詞
        )
    with row1[2]:
        # 🔴 修改 4: index=None 且加上 placeholder
        payment_method = st.selectbox(
            "支付方式", 
            options=payment_options, 
            index=None, # 預設不選
            key='quick_entry_payment', 
            label_visibility="collapsed",
            placeholder="支付方式" # 提示詞
        )
    with row1[3]:
        # 🔴 修改 5: 調整 placeholder 文字
        note = st.text_input(
            "備註", 
            placeholder="備註", # 提示詞
            key='quick_entry_note', 
            label_visibility="collapsed"
        )
    with row1[4]:
        save_clicked = st.button("新增", use_container_width=True, key="quick_entry_save")
        if st.button("❌", key="quick_entry_cancel"):
             st.session_state.show_quick_entry = False
             st.rerun()

    # --- 儲存邏輯 ---
    if save_clicked:
        # 🔴 修改 6: 增加驗證邏輯，因為現在預設值可能是 None
        if not category:
            st.toast("⚠️ 請選擇類別")
            return
        if amount is None or amount <= 0:
            st.toast("⚠️ 請輸入有效金額")
            return

        amt = int(amount)
        record_data = {
            'date': datetime.date.today(),
            'type': '支出',
            'category': category,
            'amount': float(amt),
            'note': (note or "").strip() or f"{category} 支出",
            'timestamp': datetime.datetime.now(),
        }

        # 處理支付方式
        final_acc_id = None
        final_acc_name = None

        # 🔴 修改 7: 判斷 payment_method 是否有值 (因改為 index=None，未選即為 None)
        if payment_method: 
            final_acc_name = payment_method
            final_acc_id = name_to_id.get(final_acc_name)
            if not final_acc_id:
                final_acc_id = str(uuid.uuid4())
            
            record_data['account_id'] = final_acc_id
            record_data['account_name'] = final_acc_name

        add_record(db, user_id, record_data)

        # 更新餘額
        if final_acc_id:
            try:
                ba = load_bank_accounts(db, user_id) or {}
                if not isinstance(ba, dict): ba = {}
                
                acc_data = ba.get(final_acc_id, {'name': final_acc_name, 'balance': 0})
                if 'name' not in acc_data: acc_data['name'] = final_acc_name
                
                current_bal = safe_float(acc_data.get('balance', 0))
                new_bal = current_bal - float(amt)
                
                ba[final_acc_id] = {'name': final_acc_name, 'balance': new_bal}
                update_bank_accounts(db, user_id, ba)
                st.toast(f"已從 {final_acc_name} 扣款")
            except Exception as e:
                st.warning(f"餘額更新失敗: {e}")
        else:
            st.toast(f"✅ 已記帳：{category} NT$ {amt:,}")

        st.session_state.show_quick_entry = False
        # 清理 Session State
        keys_to_clear = ['quick_entry_category', 'quick_entry_amount', 'quick_entry_note', 'quick_entry_payment']
        for k in keys_to_clear:
            if k in st.session_state: del st.session_state[k]
        
        st.cache_data.clear()
        st.rerun()



def app():
    """主應用程式入口點"""
    set_ui_styles()

    # 初始化 session_state，用於追蹤正在編輯的紀錄 ID
    if 'editing_record_id' not in st.session_state:
        st.session_state.editing_record_id = None

    # 初始化 Firestore 和用戶 ID
    db = get_firestore_client()
    user_id = get_user_id()

    # # 側邊欄 (這段程式碼在您的版本中應該是註解掉的，保持原樣即可)
    # with st.sidebar:
    #     # 📌 您可以在這裡更換您的圖片 URL 或本地路徑
    #     st.image("https://placehold.co/150x50/0d6efd/ffffff?text=記帳本", use_container_width=True) 
    #     st.markdown("---")
    #     # 您也可以在側邊欄放一些說明文字
    #     st.markdown("### 關於此應用")
    #     st.write("這是一個使用 Streamlit 和 Firestore 打造的雲端記帳本。")


    # --- 頁面內容渲染 (使用 st.tabs) ---
    
    # 📌 修正 #1: 將 "交易紀錄" 移除，只保留 4 個頁籤
    tab_list = ["首頁", "記帳管理", "帳戶管理", "其他設定"]
    
    # 📌 修正 #2: 只解構 4 個 tab 變數
    tab1, tab2, tab3, tab4 = st.tabs(tab_list)

    # 📌 2. 將原來的 if/elif 內容放入對應的 tab 中
    with tab1:
        # 原本 "儀表板" 的內容
        display_quick_entry_on_home(db, user_id)
        st.markdown('---')
        display_dashboard(db, user_id)
        st.markdown('---')

    # 📌 修正 #3: 將 "新增" 和 "查看" 合併到 tab2
    with tab2:
        # (1) 先顯示 "新增紀錄" 的區塊
        display_record_input(db, user_id)
        
        # (2) 加入分隔線
        st.markdown("---") 
        
        # (3) 在下方接著顯示 "交易紀錄" 的區塊
        df_records = get_all_records(db, user_id) 
        display_records_list(db, user_id, df_records)

    # 📌 修正 #4: "帳戶管理" 移到 tab3
    with tab3:
        # 原本 "帳戶管理" 的內容
        display_bank_account_management(db, user_id)

    # 📌 修正 #5: "設定餘額" 移到 tab4
    with tab4:
        # 原本 "設定餘額" 的內容
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