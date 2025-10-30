import streamlit as st
import pandas as pd
import datetime
from typing import Optional
from google.cloud import firestore

# =============================
# 🔧 Firestore 基本設定與工具函式
# =============================

RECORD_COLLECTION_NAME = 'records'
BALANCE_COLLECTION_NAME = 'account_status'
BALANCE_DOC_ID = 'balance_doc'


def get_record_ref(db: firestore.Client, user_id: str):
    """獲取用戶交易紀錄的 Collection 參考"""
    return db.collection('users').document(user_id).collection(RECORD_COLLECTION_NAME)


def get_balance_ref(db: firestore.Client, user_id: str):
    """獲取用戶餘額狀態的 Document 參考"""
    return db.collection('users').document(user_id).collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)


def get_bank_accounts_ref(db: firestore.Client, user_id: str):
    """獲取用戶銀行帳戶列表的 Document 參考"""
    return db.collection('users').document(user_id).collection('bank_accounts').document('accounts')


# =============================
# 🧮 餘額讀取（快取）
# =============================

@st.cache_data(ttl=60, hash_funcs={firestore.Client: id})
def get_current_balance(db: firestore.Client, user_id: str) -> float:
    """從 Firestore 獲取當前總餘額"""
    if db is None:
        return 0.0
    balance_ref = get_balance_ref(db, user_id)
    doc = balance_ref.get()
    if doc.exists:
        return float(doc.to_dict().get('balance', 0.0))
    # 初始化
    try:
        balance_ref.set({'balance': 0.0})
    except Exception as e:
        st.error(f"初始化餘額失敗: {e}")
    return 0.0


# =============================
# 📥 讀取所有紀錄（快取）
# =============================

@st.cache_data(ttl=60, hash_funcs={firestore.Client: id})
def get_all_records(db: firestore.Client, user_id: str) -> pd.DataFrame:
    """
    從 Firestore 獲取用戶的所有交易紀錄 (強健版本)
    - 優先使用 'date' 欄位
    - 如果 'date' 缺失或無效，自動使用 'timestamp' 欄位作為備援
    """
    if db is None:
        return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])

    records_ref = get_record_ref(db, user_id)
    try:
        # 用 timestamp 排序，對新舊資料都穩定
        docs = records_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).get()
        data = []

        for doc in docs:
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id

            # --- 1) 解析 timestamp ---
            parsed_timestamp = None
            if 'timestamp' in doc_data and hasattr(doc_data['timestamp'], 'to_pydatetime'):
                parsed_timestamp = doc_data['timestamp'].to_pydatetime()
                doc_data['timestamp'] = parsed_timestamp
            elif isinstance(doc_data.get('timestamp'), datetime.datetime):
                # 已是 datetime
                pass
            else:
                doc_data['timestamp'] = None

            # --- 2) 解析 date ---
            parsed_date = None
            if 'date' in doc_data and hasattr(doc_data['date'], 'to_pydatetime'):
                # Firestore Timestamp
                parsed_date = doc_data['date'].to_pydatetime().date()
            elif isinstance(doc_data.get('date'), str):
                try:
                    parsed_date = datetime.datetime.strptime(doc_data['date'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    parsed_date = None
            elif isinstance(doc_data.get('date'), datetime.datetime):
                parsed_date = doc_data['date'].date()
            elif isinstance(doc_data.get('date'), datetime.date):
                parsed_date = doc_data['date']

            # --- 3) 決定最終 date 欄位 ---
            if parsed_date:
                # 轉成當天 00:00 (naive，後面會統一處理時區)
                doc_data['date'] = datetime.datetime.combine(parsed_date, datetime.time.min)
            elif isinstance(doc_data.get('timestamp'), datetime.datetime):
                # 用 timestamp 當備援
                doc_data['date'] = doc_data['timestamp']
            else:
                doc_data['date'] = None

            data.append({
                'id': doc_data.get('id'),
                'date': doc_data.get('date'),
                'type': doc_data.get('type'),
                'category': doc_data.get('category'),
                'amount': doc_data.get('amount'),
                'note': doc_data.get('note'),
                'timestamp': doc_data.get('timestamp'),
            })

        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])

        # --- 統一時區：全部先視為 UTC，再移除 tz，避免 tz/naive 混用 ---
        df['date'] = pd.to_datetime(df['date'], errors='coerce', utc=True).dt.tz_convert(None)

        # 🔁 若 date 仍為 NaT，嘗試以 timestamp 回填
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True).dt.tz_convert(None)
            mask = df['date'].isna() & df['timestamp'].notna()
            df.loc[mask, 'date'] = df.loc[mask, 'timestamp']

        # 其餘欄位
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
        df['type'] = df['type'].astype(str)
        df['category'] = df['category'].astype(str)
        df['note'] = df['note'].astype(str)

        return df

    except Exception as e:
        st.error(f"❌ 讀取交易紀錄失敗: {e}")
        return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])


# =============================
# ➕ 新增紀錄
# =============================

def add_record(db: firestore.Client, user_id: str, record_data: dict):
    """向 Firestore 添加一筆交易紀錄"""
    if db is None:
        return
    records_ref = get_record_ref(db, user_id)
    try:
        record_date_obj = record_data.get('date')  # 可能是 date 物件

        # 以 UTC 保存時間，避免時區差異
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # 規則：
        # A. 若選今天 => date 與 timestamp 都設為 now_utc
        # B. 若選過去日期 => date 設為該日 00:00 UTC；timestamp 仍為 now_utc
        # C. 解析失敗 => 兩者都用 now_utc
        if isinstance(record_date_obj, datetime.date) and record_date_obj == now_utc.date():
            record_data['date'] = now_utc
        elif isinstance(record_date_obj, datetime.date):
            record_data['date'] = datetime.datetime.combine(record_date_obj, datetime.time.min, tzinfo=datetime.timezone.utc)
        else:
            st.warning("日期格式無法識別，已使用當前時間。")
            record_data['date'] = now_utc

        record_data['timestamp'] = now_utc

        records_ref.add(record_data)

        # 寫入成功 → 清掉快取，避免看到舊資料
        get_all_records.clear()

        st.toast("✅ 交易紀錄已新增！")

        # 同步更新餘額
        try:
            amount = float(record_data.get('amount') or 0)
            operation = 'add' if record_data.get('type') == '收入' else 'subtract'
            update_balance_transactional(db, user_id, amount, operation)
            get_all_records.clear()
        except Exception as e:
            st.error(f"更新餘額時發生錯誤: {e}")

    except Exception as e:
        st.error(f"❌ 新增紀錄失敗: {e}")
        st.error(f"紀錄數據: {record_data}")


# =============================
# 🗑️ 刪除紀錄
# =============================

def delete_record(db: firestore.Client, user_id: str, record_id: str, record_type: str, record_amount: float):
    """從 Firestore 刪除一筆交易紀錄並回滾餘額"""
    if db is None:
        return
    record_doc_ref = get_record_ref(db, user_id).document(record_id)
    try:
        record_doc_ref.delete()

        # 清除快取
        get_all_records.clear()

        # 回滾餘額
        operation = 'subtract' if record_type == '收入' else 'add'
        update_balance_transactional(db, user_id, record_amount, operation)

        st.toast("🗑️ 已刪除紀錄並更新餘額")

    except Exception as e:
        st.error(f"❌ 刪除紀錄失敗: {e}")


# =============================
# 💸 餘額更新（交易）
# =============================

def update_balance_transactional(db: firestore.Client, user_id: str, amount: float, operation: str):
    """
    以 Firestore 交易機制安全地更新餘額：
    - operation: 'add' | 'subtract'
    """
    if db is None:
        return
    balance_ref = get_balance_ref(db, user_id)

    @firestore.transactional
    def txn(transaction):
        snapshot = balance_ref.get(transaction=transaction)
        curr = 0.0
        if snapshot.exists:
            curr = float(snapshot.to_dict().get('balance', 0.0))
        new_val = curr + amount if operation == 'add' else curr - amount
        transaction.set(balance_ref, {'balance': new_val})

    try:
        txn(db.transaction())
        get_current_balance.clear()
        get_all_records.clear()  # 也清一下交易清單
    except Exception as e:
        st.error(f"❌ 餘額更新失敗: {e}")


# =============================
# 🧯 安全日期工具
# =============================

def safe_date(dt_like: Optional[datetime.datetime]) -> datetime.datetime:
    """將 None/NaT 轉為今天 00:00，避免渲染報錯。"""
    default_date = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    try:
        if dt_like is None:
            return default_date
        if isinstance(dt_like, pd.Timestamp):
            if pd.isna(dt_like):
                return default_date
            # 若為 tz-aware，轉為 naive
            if dt_like.tzinfo is not None:
                return dt_like.tz_convert(None).to_pydatetime()
            return dt_like.to_pydatetime()
        if isinstance(dt_like, datetime.datetime):
            return dt_like.replace(tzinfo=None) if dt_like.tzinfo else dt_like
        if isinstance(dt_like, datetime.date):
            return datetime.datetime.combine(dt_like, datetime.time.min)
        return default_date
    except Exception:
        return default_date


# =============================
# 🖼️（其餘：頁面、UI、表單等程式）
# ※ 省略：與「錯誤日期」無關的 UI / Flow，可保留你原始檔案內容。
# =============================

# 提示：把這份檔覆蓋你的 app_firestore.py 後執行即可。
