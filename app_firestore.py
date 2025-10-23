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
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 0.5rem;
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }}

        /* 主要背景色 */
        .stApp {{
            background-color: {DEFAULT_BG_COLOR};
        }}

        /* 調整按鈕樣式 */
        .stButton>button {{
            border-radius: 8px;
            font-weight: 600;
        }}
        
        /* 隱藏 Streamlit 預設的 footer/menu */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}
        
        /* 調整 st.columns 內的間距 */
        .st-emotion-cache-12ttj6z {{ /* Streamlit column style class */
            padding-top: 0rem;
            padding-bottom: 0rem;
        }}
        
        /* 調整訊息框的樣式 */
        .stAlert {{
            border-radius: 8px;
        }}
        
        /* 讓表格標題列看起來更整潔 */
        .header-row {{
            font-weight: bold; 
            background-color: #e9ecef; 
            padding: 10px 1rem; 
            border-radius: 5px; 
            margin-top: 10px;
            display: flex;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    
# --- 2. Firestore 數據操作函數 ---

@st.cache_resource
def get_firestore_db():
    """初始化並快取 Firestore 客戶端"""
    try:
        # 使用 Streamlit Secrets 進行認證
        if st.secrets.get("gcp_service_account"):
            # 確保使用 Streamlit Cloud 環境提供的認證
            db = firestore.Client.from_service_account_info(st.secrets["gcp_service_account"])
        else:
            # 適用於本地測試或其他環境
            db = firestore.Client()
        return db
    except Exception as e:
        st.error(f"Firestore 初始化失敗: {e}")
        st.stop()
        
db = get_firestore_db()

def get_balance(db, user_id):
    """從 Firestore 獲取當前帳戶餘額"""
    try:
        doc_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
        doc = doc_ref.get()
        if doc.exists:
            # 餘額儲存於 documents/account_status/current_balance 內
            # 並假設餘額儲存在 'balance' 欄位，類型為數字
            balance_data = doc.to_dict().get('users', {}).get(user_id, {})
            current_balance = balance_data.get('balance', 0.0)
            return float(current_balance)
        else:
            # 如果文件不存在，代表第一次使用，初始化餘額
            return 0.0
    except Exception as e:
        st.error(f"獲取餘額失敗: {e}")
        return 0.0

def update_balance(db, user_id, new_balance):
    """更新 Firestore 中的帳戶餘額"""
    try:
        doc_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
        # 由於是多用戶應用，餘額應該存儲在以 user_id 為鍵的 map 中
        doc_ref.set({
            'users': {
                user_id: {'balance': float(new_balance), 'last_update': firestore.SERVER_TIMESTAMP}
            }
        }, merge=True)
        return True
    except Exception as e:
        st.error(f"更新餘額失敗: {e}")
        return False

def add_record(db, user_id, record):
    """新增一筆交易紀錄到 Firestore"""
    try:
        # 新增交易紀錄到 /artifacts/{appId}/users/{userId}/records
        collection_path = f"artifacts/{st.session_state['app_id']}/users/{user_id}/{RECORD_COLLECTION_NAME}"
        doc_ref = db.collection(collection_path).document(str(uuid.uuid4()))
        doc_ref.set(record)
        return True
    except Exception as e:
        st.error(f"新增紀錄失敗: {e}")
        return False

def get_records(db, user_id):
    """從 Firestore 獲取所有交易紀錄並轉換為 DataFrame"""
    try:
        # 從 /artifacts/{appId}/users/{userId}/records 獲取紀錄
        collection_path = f"artifacts/{st.session_state['app_id']}/users/{user_id}/{RECORD_COLLECTION_NAME}"
        records = []
        docs = db.collection(collection_path).stream()
        
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id
            
            # 將 Firestore Timestamp 轉換為 Python datetime
            if isinstance(record.get('date'), firestore.client.base_client.ServerTimestamp):
                 record['date'] = record['date'].get().to_datetime()
            elif isinstance(record.get('date'), datetime.datetime):
                pass
            else:
                 # 處理其他可能的日期格式（例如字串），如果需要
                 record['date'] = datetime.datetime.now() # 避免程式崩潰，給一個預設值

            records.append(record)
            
        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']) # 確保日期是 datetime 類型
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0).astype(int) # 確保金額是整數
        
        # 排序：最新紀錄在前
        df.sort_values(by='date', ascending=False, inplace=True)
        return df

    except Exception as e:
        st.error(f"獲取交易紀錄失敗: {e}")
        return pd.DataFrame()

def delete_record(db, user_id, record_id, record_type, record_amount, current_balance):
    """刪除一筆交易紀錄並更新餘額"""
    try:
        # 刪除交易紀錄
        collection_path = f"artifacts/{st.session_state['app_id']}/users/{user_id}/{RECORD_COLLECTION_NAME}"
        db.collection(collection_path).document(record_id).delete()
        
        # 反向計算新的餘額
        if record_type == '收入':
            new_balance = current_balance - record_amount
        elif record_type == '支出':
            new_balance = current_balance + record_amount
        else:
            new_balance = current_balance # 未知類型，餘額不變
            
        # 更新 Firestore 餘額
        update_balance(db, user_id, new_balance)
        st.session_state['current_balance'] = new_balance # 更新 session state
        
        st.rerun() # 重新執行應用程式以刷新數據
        return True
    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")
        return False

# --- 3. 主應用程式邏輯 ---
def main():
    
    # 設置 UI 樣式
    set_ui_styles()

    st.title("家庭記帳本 📝")
    
    # --------------------------------------
    # 2. 認證與初始化
    # --------------------------------------
    
    # 獲取全局變量 (Streamlit Cloud Canvas 環境提供)
    app_id = typeof(__app_id) !== 'undefined' ? __app_id : 'default-app-id'
    st.session_state['app_id'] = app_id
    
    # 假設 Streamlit 內建認證機制已經設置並將 user_id 存儲在 session_state
    # 如果是 Canvas 環境，這通常是 `auth.currentUser.uid`
    # 在這個模擬環境中，我們使用一個預設的 ID
    if 'user_id' not in st.session_state:
        # 在實際的 Firebase 應用中，這裡應該是 Firebase Auth 的 UID
        st.session_state['user_id'] = "anonymous_user_001" 
        
    user_id = st.session_state['user_id']

    st.sidebar.markdown(f"**用戶 ID:** `{user_id}`")
    
    # --------------------------------------
    # 3. 數據獲取與處理
    # --------------------------------------
    
    # 3.1. 獲取並顯示餘額
    if 'current_balance' not in st.session_state:
        st.session_state['current_balance'] = get_balance(db, user_id)
        
    current_balance = st.session_state['current_balance']
    balance_color = "#28a745" if current_balance >= 0 else "#dc3545"

    st.markdown(
        f"""
        <div style='text-align: center; background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 2rem;'>
            <h2 style='border-bottom: none; margin-bottom: 0.5rem; color: #6c757d; font-size: 1.2rem;'>
                當前帳戶餘額 (NT$)
            </h2>
            <p style='font-size: 3.5rem; font-weight: 700; color: {balance_color}; margin: 0;'>
                NT$ {current_balance:,.0f}
            </p>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 3.2. 交易紀錄表格
    df_records = get_records(db, user_id)
    
    # --------------------------------------
    # 4. 新增交易區 (表單)
    # --------------------------------------
    st.subheader("新增交易")
    with st.form(key='add_record_form'):
        
        # 頂部欄位：日期、類型、金額
        cols_top = st.columns([1, 1, 1.5])
        
        record_date = cols_top[0].date_input(
            "日期", 
            value=datetime.date.today(), 
            key='record_date'
        )
        
        record_type = cols_top[1].selectbox(
            "類型", 
            options=list(CATEGORIES.keys()), 
            key='record_type'
        )
        
        record_amount = cols_top[2].number_input(
            "金額 (NT$)", 
            min_value=1, 
            value=100, 
            step=10,
            key='record_amount'
        )
        
        # 底部欄位：類別、備註
        cols_bottom = st.columns([1, 2])
        
        # 根據選擇的類型動態更新類別選項
        category_options = CATEGORIES.get(record_type, [])
        record_category = cols_bottom[0].selectbox(
            "類別", 
            options=category_options, 
            key='record_category'
        )
        
        record_note = cols_bottom[1].text_input(
            "備註 (選填)", 
            key='record_note'
        )
        
        submit_button = st.form_submit_button("新增紀錄", type="primary")

        if submit_button:
            if not record_amount or not record_category:
                st.error("請填寫金額和類別！")
            else:
                # 建立新紀錄
                new_record = {
                    'date': datetime.datetime.combine(record_date, datetime.time()), # 轉換為 datetime 物件
                    'type': record_type,
                    'amount': int(record_amount),
                    'category': record_category,
                    'note': record_note
                }
                
                # 計算新餘額
                if record_type == '收入':
                    new_balance = current_balance + record_amount
                elif record_type == '支出':
                    new_balance = current_balance - record_amount
                else:
                    new_balance = current_balance
                
                # 執行寫入操作
                if add_record(db, user_id, new_record) and update_balance(db, user_id, new_balance):
                    st.success(f"成功新增 {record_type}：NT$ {record_amount:,.0f}，新餘額為 NT$ {new_balance:,.0f}")
                    # 更新 session state
                    st.session_state['current_balance'] = new_balance
                    st.rerun()
                else:
                    st.error("新增紀錄失敗，請檢查網路連線或權限。")

    st.markdown("---")
    
    # --------------------------------------
    # 5. 餘額調整區
    # --------------------------------------
    st.subheader("餘額調整")
    with st.expander("設定/調整帳戶餘額", expanded=False):
        # 從 st.session_state 獲取當前餘額作為預設值
        current_balance_value = st.session_state.get('current_balance', 0)

        # 修正點：將 min_value 從 0 調整為較大的負數，以允許負數餘額作為預設值
        # 避免當 current_balance_value < 0 時拋出 StreamlitValueBelowMinError
        new_balance = st.number_input(
            "新的帳戶餘額 (NT$)",
            min_value=-1_000_000_000,  # 允許負數餘額 (例如：負債)，避免當前餘額為負時報錯
            value=current_balance_value,
            step=100,
            format="%d",
            key='new_balance_input'
        )

        if st.button("更新餘額", key='update_balance_btn', type="secondary"):
            if update_balance(db, user_id, new_balance):
                st.success(f"帳戶餘額已更新為 NT$ {new_balance:,.0f}")
                st.session_state['current_balance'] = new_balance
                st.rerun()
            else:
                st.error("更新餘額失敗。")

    st.markdown("---")
    
    # --------------------------------------
    # 6. 數據分析與展示區
    # --------------------------------------
    st.subheader("交易紀錄與分析")
    
    if df_records.empty:
        st.info("目前尚無交易紀錄。")
        return # 如果沒有紀錄，則不執行後續的分析和表格顯示
        
    # 6.1. 篩選控制項
    st.markdown("##### 篩選範圍")
    col_start, col_end = st.columns(2)
    
    # 確保日期範圍有效
    min_date = df_records['date'].min().date() if not df_records.empty else datetime.date.today()
    max_date = df_records['date'].max().date() if not df_records.empty else datetime.date.today()
    
    # 預設篩選範圍為近一個月 (如果紀錄足夠多)
    default_start_date = max(min_date, max_date - datetime.timedelta(days=30))
    
    start_date = col_start.date_input("開始日期", value=default_start_date, min_value=min_date, max_value=max_date)
    end_date = col_end.date_input("結束日期", value=max_date, min_value=min_date, max_value=max_date)

    # 篩選數據
    df_filtered = df_records[
        (df_records['date'].dt.date >= start_date) & 
        (df_records['date'].dt.date <= end_date)
    ].copy()
    
    if df_filtered.empty:
        st.info("在選定的日期範圍內沒有交易紀錄。")
        return
    
    # 6.2. 支出分佈圓餅圖
    st.header("支出分佈 (圓餅圖)")

    # 篩選出支出紀錄
    df_expense = df_filtered[df_filtered['type'] == '支出'].copy()
    
    if not df_expense.empty and df_expense['amount'].sum() > 0:
        # 1. 數據分組：計算每個類別的總支出
        df_category_sum = df_expense.groupby('category')['amount'].sum().reset_index()
        df_category_sum.rename(columns={'amount': '總支出'}, inplace=True)
        
        # 2. 計算百分比
        total_expense = df_category_sum['總支出'].sum()
        df_category_sum['percent'] = df_category_sum['總支出'] / total_expense
        df_category_sum['label'] = df_category_sum.apply(
            lambda row: f"{row['category']} ({row['percent']:.1%})", 
            axis=1
        )

        # 3. Altair 圖表設定 (使用交互式圓餅圖)
        
        # 基礎圓餅圖 (使用 Theta 來編碼角度)
        base = alt.Chart(df_category_sum).encode(
            theta=alt.Theta("總支出", stack=True)
        )

        # 顏色編碼
        pie = base.mark_arc(outerRadius=120, innerRadius=40).encode(
            color=alt.Color("category", title="支出類別"),
            order=alt.Order("總支出", sort="descending"),
            tooltip=["category", alt.Tooltip("總支出", format=",.0f"), alt.Tooltip("percent", format=".1%")]
        ).properties(
            title="選定期間支出佔比"
        )
        
        # 標籤文本 (顯示百分比)
        text = base.mark_text(radius=140).encode(
            text=alt.Text("percent", format=".1%"),
            order=alt.Order("總支出", sort="descending"),
            color=alt.value("black") 
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

    # 6.3. 交易紀錄區 (新增刪除按鈕)
    st.header("完整交易紀錄")
    
    # 準備用於顯示和刪除的 DataFrame
    display_df = df_filtered.copy()
    
    # 標題列
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px;'>
            <div style='width: 12%; padding-left: 1rem;'>日期</div>
            <div style='width: 10%;'>類別</div>
            <div style='width: 10%;'>金額</div>
            <div style='width: 7%;'>類型</div>
            <div style='width: 50%;'>備註</div>
            <div style='width: 10%; text-align: center;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    for index, row in display_df.iterrows():
        try:
            # 從完整的紀錄中獲取刪除所需的資訊 (避免篩選後的 df 缺少必要欄位)
            # 這裡我們直接使用 row['id'] 即可，因為 display_df 是 df_filtered 的副本，它包含 'id'
            record_details_for_delete = df_records[df_records['id'] == row['id']].iloc[0].to_dict()
        except IndexError:
            st.error(f"找不到文件ID為 {row['id']} 的原始紀錄，可能已被刪除。")
            continue
            
        color = "#28a745" if row['type'] == '收入' else "#dc3545"
        amount_sign = "+" if row['type'] == '收入' else "-"
        
        # 使用 container 和 columns 創建行布局
        with st.container():
            # 調整 st.columns 比例，使備註欄位有足夠的空間
            # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 6, 操作 1] (總和 10.9)
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 6, 1])
            
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
                    user_id=user_id,
                    record_id=row['id'],
                    record_type=record_details_for_delete['type'],
                    record_amount=record_details_for_delete['amount'],
                    current_balance=st.session_state['current_balance']
                )
    
    # 確保底部有足夠間距
    st.markdown("<br><br>", unsafe_allow_html=True)


if __name__ == '__main__':
    main()

