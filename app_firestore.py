import streamlit as st
import pandas as pd
import datetime
import altair as alt 
from google.cloud import firestore
import uuid # 導入 uuid 庫用於生成唯一 ID

# --- 0. 配置與變數 ---\n
DEFAULT_BG_COLOR = "#f8f9fa" 
RECORD_COLLECTION_NAME = "records"       # 交易紀錄 Collection 名稱
BALANCE_COLLECTION_NAME = "account_status" # 餘額 Collection 名稱
BALANCE_DOC_ID = "current_balance"       # 餘額文件 ID，固定單一文件

# 定義交易類別
CATEGORIES = {
    '收入': ['薪資', '投資收益', '禮金', '其他收入'],
    '支出': ['餐飲', '交通', '購物', '娛樂', '房租/貸款', '教育', '醫療', '其他支出']
}

# --- 1. Streamlit 介面設定 ---\ndef set_ui_styles():
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
            margin-top: 2.5rem;
            margin-bottom: 1.5rem;
        }}

        /* 主要背景色 */
        .stApp {{
            background-color: {DEFAULT_BG_COLOR};
        }}

        /* 隱藏 Streamlit 側邊欄菜單和腳註 */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}

        /* 調整按鈕樣式 */
        div.stButton > button:first-child {{
            border-radius: 8px;
            font-weight: 600;
        }}
        
        /* 交易紀錄列表的行間距 */
        .stContainer {{
            margin-bottom: 0.5rem;
            padding: 0;
            border-bottom: 1px solid #dee2e6;
        }}
        
        /* 調整列的對齊 */
        [data-testid="stColumn"] div {{
            word-wrap: break-word; /* 允許文字換行 */
        }}
        
        /* 讓刪除按鈕更小一些 */
        [data-testid="stColumn"] button[kind="secondary"] {{
            padding-top: 0.2rem;
            padding-bottom: 0.2rem;
            line-height: 1;
            font-size: 0.85rem;
        }}

        </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# --- 2. Firebase/Firestore 設置與認證 (假設已在環境中配置) ---\n

# 確保在 Streamlit 的 session state 中儲存 Firestore 客戶端和使用者 ID
def initialize_firestore_client():
    """初始化 Firestore 客戶端，並使用 __app_id 獲取正確的 Collection 路徑"""
    if 'db' not in st.session_state:
        try:
            # 必須使用預設的 project ID，因為 Streamlit 平台已自動配置
            db = firestore.Client()
            st.session_state.db = db
            
            # 使用環境變數 __app_id 來構建 Collection 路徑
            app_id = st.secrets.get("__app_id", "default_app_id")
            # 這裡假設所有數據都是公開且單一用戶使用，儲存在 /artifacts/{appId}/public/data/records
            st.session_state.app_id = app_id
            st.session_state.user_id = "single_user" # 假定單用戶應用程式
            
            # 紀錄 Collection 的完整路徑
            st.session_state.records_collection_path = f"artifacts/{app_id}/public/data/{RECORD_COLLECTION_NAME}"
            st.session_state.balance_collection_path = f"artifacts/{app_id}/public/data/{BALANCE_COLLECTION_NAME}"
            
            st.success("Firestore 客戶端初始化成功！")
            
        except Exception as e:
            st.error(f"Firestore 初始化失敗: {e}")
            st.stop()
    
    return st.session_state.db, st.session_state.user_id


# --- 3. 數據操作函式 ---\n

def get_current_balance(db, user_id):
    """從 Firestore 獲取當前餘額"""
    balance_doc_ref = db.collection(st.session_state.balance_collection_path).document(BALANCE_DOC_ID)
    try:
        doc = balance_doc_ref.get()
        if doc.exists:
            # 確保餘額是 float 類型
            return float(doc.to_dict().get('balance', 0.0))
        else:
            # 如果文件不存在，初始化為 0
            balance_doc_ref.set({'balance': 0.0})
            return 0.0
    except Exception as e:
        st.error(f"讀取餘額失敗: {e}")
        return 0.0

def update_balance(db, user_id, amount_change):
    """更新當前餘額"""
    balance_doc_ref = db.collection(st.session_state.balance_collection_path).document(BALANCE_DOC_ID)
    
    # 使用事務 (Transaction) 確保原子性操作 (讀取 -> 修改 -> 寫入)
    @firestore.transactional
    def transaction_update(transaction):
        snapshot = balance_doc_ref.get(transaction=transaction)
        
        if snapshot.exists:
            current_balance = float(snapshot.to_dict().get('balance', 0.0))
        else:
            current_balance = 0.0
        
        new_balance = current_balance + amount_change
        
        transaction.set(balance_doc_ref, {'balance': new_balance})
        return new_balance
        
    try:
        transaction = db.transaction()
        new_balance = transaction_update(transaction)
        return new_balance
    except Exception as e:
        st.error(f"更新餘額失敗: {e}")
        return None

def add_record(db, user_id, record_data):
    """添加交易紀錄到 Firestore"""
    record_collection_ref = db.collection(st.session_state.records_collection_path)
    try:
        # 生成一個唯一的 ID 作為 Firestore Document ID
        record_id = str(uuid.uuid4())
        record_doc_ref = record_collection_ref.document(record_id)
        
        # 設置紀錄數據
        # 備註: Streamlit 運行時狀態不能直接在非 Streamlit 回調函數中修改 (如 st.session_state.db)
        # 但在 Streamlit 的環境中，我們可以依靠 Streamlit 的 re-run 機制來反映變化。
        record_doc_ref.set({
            'id': record_id, # 確保文件內也有 ID
            'date': record_data['date'],
            'type': record_data['type'],
            'category': record_data['category'],
            'amount': record_data['amount'],
            'note': record_data['note'],
            'timestamp': datetime.datetime.now() # 添加時間戳用於排序或日後分析
        })
        
        # 同步更新餘額
        amount_change = record_data['amount'] if record_data['type'] == '收入' else -record_data['amount']
        update_balance(db, user_id, amount_change)
        
        st.success(f"{record_data['type']}紀錄添加成功！")
        # 觸發 Streamlit 重新執行以刷新列表和餘額
        st.rerun() 
        
    except Exception as e:
        st.error(f"添加紀錄失敗: {e}")

def delete_record(db, user_id, record_id, record_type, record_amount, current_balance):
    """刪除交易紀錄並更新餘額"""
    record_doc_ref = db.collection(st.session_state.records_collection_path).document(record_id)
    try:
        # 1. 刪除紀錄
        record_doc_ref.delete()
        
        # 2. 反向計算餘額變動
        # 如果是收入，餘額要減去該金額；如果是支出，餘額要加上該金額
        amount_change = -record_amount if record_type == '收入' else record_amount
        
        # 3. 更新餘額（使用 update_balance 確保原子性）
        update_balance(db, user_id, amount_change)

        st.success("紀錄刪除成功！")
        # 觸發 Streamlit 重新執行以刷新列表和餘額
        st.rerun() 
        
    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")

def get_all_records(db, user_id):
    """獲取所有交易紀錄並轉換為 DataFrame"""
    record_collection_ref = db.collection(st.session_state.records_collection_path)
    try:
        docs = record_collection_ref.stream()
        records_list = []
        for doc in docs:
            data = doc.to_dict()
            # 確保 'id' 欄位存在
            data['id'] = doc.id 
            # 將 Firestore Timestamp 轉換為 datetime.date 對象以便於 Streamlit date_input 處理
            if isinstance(data.get('date'), datetime.datetime):
                data['date'] = data['date'].date()
            elif isinstance(data.get('date'), firestore.client.base_client.BaseTimestamp):
                data['date'] = data['date'].astimezone(datetime.timezone.utc).date()
            
            # 確保 amount 是 float 或 int
            try:
                data['amount'] = float(data['amount'])
            except (ValueError, TypeError):
                data['amount'] = 0.0 # 數據清理
                
            records_list.append(data)
            
        if not records_list:
            return pd.DataFrame(), pd.DataFrame() # 返回兩個空的 DataFrame
        
        df = pd.DataFrame(records_list)
        # 確保日期欄位是 datetime.date 類型以便過濾
        df['date'] = pd.to_datetime(df['date']).dt.date 
        
        # 確保按時間戳降序排序 (最近的在最上面)
        df_sorted = df.sort_values(by='timestamp', ascending=False)
        
        # 過濾支出紀錄用於圖表
        df_expenses = df_sorted[df_sorted['type'] == '支出'].copy()
        
        return df_sorted, df_expenses
        
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        return pd.DataFrame(), pd.DataFrame()


# --- 4. Streamlit 主要應用程式佈局 ---

def main():
    set_ui_styles()
    
    st.title("家庭簡易記帳本 💰")
    
    # 1. 初始化 Firestore
    db, user_id = initialize_firestore_client()
    
    # 2. 獲取所有紀錄和當前餘額
    df_records, df_expenses = get_all_records(db, user_id)
    current_balance = get_current_balance(db, user_id)
    
    # 顯示當前餘額
    st.markdown(f"**當前總餘額:** <span style='font-size: 2em; font-weight: bold; color: {'#28a745' if current_balance >= 0 else '#dc3545'};'>{current_balance:,.0f} TWD</span>", unsafe_allow_html=True)
    st.markdown("---")


    # 3. 交易紀錄輸入區
    st.header("新增交易紀錄")
    
    # 創建兩個欄位用於輸入類型和類別
    col_type, col_category = st.columns([1, 2])
    
    # 選擇交易類型 (收入/支出)
    transaction_type = col_type.selectbox(
        "選擇類型",
        options=['支出', '收入'],
        index=0, # 預設為支出
        key='transaction_type'
    )
    
    # 根據類型顯示不同的類別下拉選單
    category_options = CATEGORIES[transaction_type]
    selected_category = col_category.selectbox(
        "選擇類別",
        options=category_options,
        index=0,
        key='selected_category'
    )
    
    # 創建日期、金額和備註的輸入欄位
    col_date_input, col_amount_input = st.columns([1, 2])
    
    record_date = col_date_input.date_input(
        "日期",
        datetime.date.today(),
        key='record_date'
    )
    
    amount = col_amount_input.number_input(
        "金額",
        min_value=0.0,
        value=0.0,
        step=100.0,
        key='amount_input'
    )
    
    note = st.text_input(
        "備註 (可選)",
        placeholder="例如: 晚餐, 交通費, 薪資入帳...",
        key='note_input'
    )
    
    # 新增按鈕
    if st.button("確認新增", type="primary", help="儲存此筆交易紀錄並更新餘額"):
        if amount <= 0:
            st.warning("請輸入有效的金額。")
        else:
            record_data = {
                'date': record_date,
                'type': transaction_type,
                'category': selected_category,
                'amount': amount,
                'note': note,
            }
            add_record(db, user_id, record_data)


    st.markdown("---")
    
    # 4. 數據分析與視覺化
    st.header("數據分析與支出分佈")

    # 4.1. 篩選日期範圍 (預設為近 30 天)
    end_date = datetime.date.today()
    start_date_default = end_date - datetime.timedelta(days=30)
    
    col_start, col_end = st.columns(2)
    start_date = col_start.date_input("開始日期", start_date_default, key='start_date')
    end_date = col_end.date_input("結束日期", end_date, key='end_date')

    if start_date > end_date:
        st.error("開始日期不能晚於結束日期。")
        df_filtered = pd.DataFrame()
    else:
        # 根據日期和類型篩選數據 (用於圖表和列表)
        df_filtered = df_records[
            (df_records['date'] >= start_date) & 
            (df_records['date'] <= end_date)
        ].copy()


    # 4.2. 支出分佈圓餅圖
    df_expenses_filtered = df_filtered[df_filtered['type'] == '支出'].copy()
    
    total_expense = df_expenses_filtered['amount'].sum()
    
    if total_expense > 0:
        # 計算每個類別的支出總和
        df_pie = df_expenses_filtered.groupby('category')['amount'].sum().reset_index()
        df_pie.rename(columns={'amount': '總支出'}, inplace=True)
        
        # 計算百分比
        df_pie['百分比'] = (df_pie['總支出'] / total_expense)
        
        # 1. 基礎圓餅圖設定
        base = alt.Chart(df_pie).encode(
            theta=alt.Theta("總支出", stack=True)
        ).properties(
            title='選定期間支出類別分佈'
        )
        
        # 2. 圓餅圖/圓弧
        pie = base.mark_arc(outerRadius=120, innerRadius=40).encode(
            color=alt.Color("category", title="支出類別"),
            order=alt.Order("總支出", sort="descending"),
            tooltip=["category", alt.Tooltip("總支出", format=",.0f"), alt.Tooltip("百分比", format=".1%")]
        )
        
        # 3. 圓心文字標籤 (顯示總支出)
        text = alt.Chart(pd.DataFrame({'text': [f"總支出: {total_expense:,.0f} TWD"]})).mark_text(
            align='center', 
            baseline='middle', 
            fontSize=16, 
            fontWeight='bold'
        ).encode(
            text=alt.Text('text', type='nominal')
        )
        
        # 4. 組合圖表並居中顯示
        chart = (pie + text).interactive()
        
        # 為了讓圓餅圖在 Streamlit 內置的容器中能保持正確的寬高比，
        # 這裡設定較為固定的寬高，讓圓形居中顯示。
        st.altair_chart(chart, use_container_width=True)

        # --------------------------------------
        
    else:
        st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # 5. 交易紀錄列表區
    st.header("完整交易紀錄")
    
    if df_filtered.empty:
        st.markdown("**所選日期範圍內沒有交易紀錄。**")
        return # 如果沒有數據則直接返回
        
    
    # 準備用於顯示的 DataFrame (使用原始欄位名稱進行內部處理)
    display_df = df_filtered[['date', 'category', 'amount', 'type', 'note', 'id']].copy()

    # 標題列
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px;'>
            <div style='width: 12%; padding-left: 1rem;'>日期</div>
            <div style='width: 10%;'>類別</div>
            <div style='width: 10%;'>金額</div>
            <div style='width: 7%;'>類型</div>
            <div style='width: 48%;'>備註</div>
            <div style='width: 8%; text-align: center;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    for index, row in display_df.iterrows():
        try:
            # 從完整的紀錄中獲取刪除所需的資訊
            record_details_for_delete = df_records[df_records['id'] == row['id']].iloc[0].to_dict()
        except IndexError:
            st.error(f"找不到文件ID為 {row['id']} 的原始紀錄，可能已被刪除。")
            continue
            
        color = "#28a745" if row['type'] == '收入' else "#dc3545"
        amount_sign = "+" if row['type'] == '收入' else "-"
        
        # 使用 container 和 columns 創建行布局
        with st.container():
            # **修正點: 調整 st.columns 比例，大幅增加備註欄位的權重 (9)**
            # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 9, 操作 1] (總和 13.9)
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 9, 1])
            
            # 使用 st.write 顯示交易細節
            col_date.write(row['date'].strftime('%Y-%m-%d'))
            col_cat.write(row['category'])
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row['amount']:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(row['type'])
            col_note.write(row['note']) # 備註內容，給予更多空間避免重疊
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{row['id']}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                # 刪除操作需要使用原始的金額和類型
                delete_record(
                    db=db,
                    user_id=user_id,
                    record_id=row['id'],
                    record_type=record_details_for_delete['type'],
                    record_amount=record_details_for_delete['amount'],
                    current_balance=current_balance # 雖然 update_balance 內部會重新獲取，但這裡傳遞一個參考值
                )


if __name__ == "__main__":
    main()

