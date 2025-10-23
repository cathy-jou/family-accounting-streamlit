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
            margin-top: 2rem;
            margin-bottom: 1.5rem;
            border-left: 5px solid #007bff; /* 藍色側邊條 */
            padding-left: 10px;
        }}
        
        /* 設定背景顏色 */
        .main {{
            background-color: {DEFAULT_BG_COLOR};
            padding-top: 2rem; 
        }}
        [data-testid="stAppViewContainer"] {{
            background-color: {DEFAULT_BG_COLOR};
        }}
        section[data-testid="stSidebar"] {{
            background-color: #ffffff; 
        }}
        
        /* 讓輸入框和按鈕等元件看起來更現代 */
        div.stButton > button:first-child {{
            background-color: #007bff;
            color: white;
            border-radius: 5px;
            border: none;
            padding: 8px 15px;
            font-weight: 600;
            transition: background-color 0.3s;
        }}
        div.stButton > button:first-child:hover {{
            background-color: #0056b3;
        }}
        /* 次要按鈕樣式 */
        [data-testid="stButton"] button.secondary-button {{
            background-color: #6c757d; 
        }}
        [data-testid="stButton"] button.secondary-button:hover {{
            background-color: #5a6268; 
        }}
        
        /* 調整輸入框邊框和圓角 */
        div[data-testid="stTextInput"] > div > input,
        div[data-testid="stNumberInput"] > div > input,
        div[data-testid="stDateInput"] > div > div > input,
        div[data-testid="stSelectbox"] > div > div {{
            border-radius: 5px;
            border: 1px solid #ced4da;
            padding: 5px 10px;
        }}
        
        /* 資訊卡片樣式 */
        .balance-card {{
            background-color: #ffffff;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            text-align: center;
            margin-bottom: 1rem;
        }}
        .balance-label {{
            font-size: 1rem;
            color: #6c757d;
            margin-bottom: 5px;
        }}
        .balance-amount {{
            font-size: 2rem;
            font-weight: 700;
            color: #343a40;
        }}
        
        /* 交易紀錄行樣式，用於更好的分隔 */
        .stContainer {{
            border-bottom: 1px solid #eee;
            padding: 8px 0;
            margin: 0;
        }}
        
        /* 修正 st.columns 內部文字的垂直對齊 */
        [data-testid="column"] > div {{
            display: flex;
            align-items: center;
        }}
        
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    
# --- 2. Firebase/Firestore 設置與認證 ---

# 假設這些變數在環境中已定義
def get_firebase_config():
    """從環境變數中獲取並解析 Firebase 配置"""
    try:
        if '__firebase_config' in st.session_state and st.session_state['__firebase_config']:
            return eval(st.session_state['__firebase_config'])
        elif 'firebaseConfig' in globals():
            return firebaseConfig # 兼容舊版
        else:
            return {}
    except NameError:
        return {} # 如果環境變數不存在

def initialize_firestore_client():
    """初始化 Firestore 客戶端"""
    if 'db' not in st.session_state:
        config = get_firebase_config()
        if config:
            # 必須使用 Streamlit 的 cache 才能在多次運行中保持單例
            @st.cache_resource
            def get_db_client():
                # 這裡假設 Streamlit 環境已配置好 Google Cloud 服務帳號認證
                # 對於 Canvas 環境，通常只需要調用 firestore.client() 即可
                try:
                    return firestore.Client()
                except Exception as e:
                    st.error(f"Firestore 客戶端初始化失敗: {e}")
                    return None
            st.session_state['db'] = get_db_client()
        else:
            st.error("無法加載 Firebase 配置，請檢查環境變數。")

def get_base_path(user_id):
    """生成 Firestore 的基礎路徑，用於私有數據"""
    app_id = st.session_state.get('__app_id', 'default-app-id')
    return f"artifacts/{app_id}/users/{user_id}"

# --- 3. 數據操作函數 ---

def get_user_id():
    """獲取用戶 ID。在 Streamlit 中，我們使用一個固定 ID 或 session ID 作為模擬"""
    # 在 Canvas 環境中，我們假設用戶已經通過某種方式認證（例如 custom auth token）
    # 但由於此處我們沒有完整的 Firebase Auth 流程，我們使用一個模擬 ID。
    # 實際上線時，應該使用 Firebase Auth 的 current_user.uid。
    if 'user_id' not in st.session_state:
        st.session_state['user_id'] = "demo_user_001" # 模擬單用戶
    return st.session_state['user_id']

def fetch_records(user_id):
    """從 Firestore 獲取所有交易紀錄"""
    db = st.session_state.get('db')
    if not db:
        return pd.DataFrame()

    try:
        records_ref = db.collection(get_base_path(user_id)).document(RECORD_COLLECTION_NAME).collection("items")
        docs = records_ref.stream()
        
        data = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id
            # 確保日期是 datetime.date 對象，以便後續篩選
            if 'date' in record and isinstance(record['date'], datetime.date):
                 # 已經是 date
                 pass
            elif 'date' in record and hasattr(record['date'], 'toDate'):
                # 處理 Firestore Timestamp
                record['date'] = record['date'].toDate().date()
            elif 'date' in record and isinstance(record['date'], datetime.datetime):
                # 處理 Python datetime
                 record['date'] = record['date'].date()
            else:
                # 默認為今天
                record['date'] = datetime.date.today()
            
            data.append(record)
        
        if not data:
            return pd.DataFrame(columns=['date', 'category', 'amount', 'type', 'note', 'id'])
            
        df = pd.DataFrame(data)
        # 確保 amount 是數值類型
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        # 按日期降序排列
        df.sort_values(by='date', ascending=False, inplace=True)
        return df

    except Exception as e:
        st.error(f"獲取交易紀錄失敗: {e}")
        return pd.DataFrame()

def fetch_balance(user_id):
    """從 Firestore 獲取當前餘額"""
    db = st.session_state.get('db')
    if not db:
        return 0.0

    try:
        balance_ref = db.collection(get_base_path(user_id)).document(BALANCE_COLLECTION_NAME).collection("data").document(BALANCE_DOC_ID)
        doc = balance_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0.0)
        else:
            # 初始化餘額文件
            balance_ref.set({'balance': 0.0})
            return 0.0
    except Exception as e:
        st.error(f"獲取或初始化餘額失敗: {e}")
        return 0.0

def update_balance(user_id, amount_change):
    """更新 Firestore 中的餘額"""
    db = st.session_state.get('db')
    if not db:
        return False

    balance_ref = db.collection(get_base_path(user_id)).document(BALANCE_COLLECTION_NAME).collection("data").document(BALANCE_DOC_ID)
    
    # 這裡應該使用事務(transaction)來確保原子性，但在 Streamlit 中直接使用 set/update 簡化
    try:
        # 先獲取當前餘額
        current_balance = fetch_balance(user_id)
        new_balance = current_balance + amount_change
        
        balance_ref.set({'balance': new_balance})
        st.session_state['current_balance'] = new_balance # 更新 session state
        return True
    except Exception as e:
        st.error(f"更新餘額失敗: {e}")
        return False

def add_record(user_id, date, category, amount, type, note):
    """將新的交易紀錄添加到 Firestore"""
    db = st.session_state.get('db')
    if not db:
        return False
        
    records_ref = db.collection(get_base_path(user_id)).document(RECORD_COLLECTION_NAME).collection("items")
    amount_float = float(amount)
    amount_change = amount_float if type == '收入' else -amount_float
    
    try:
        # 1. 新增交易紀錄
        records_ref.add({
            'date': date,
            'category': category,
            'amount': amount_float,
            'type': type,
            'note': note,
            'timestamp': firestore.SERVER_TIMESTAMP # 記錄伺服器時間戳
        })
        
        # 2. 更新餘額
        if update_balance(user_id, amount_change):
            st.success("成功新增交易並更新餘額！")
            return True
        else:
            st.warning("交易紀錄已新增，但餘額更新失敗。")
            return False
            
    except Exception as e:
        st.error(f"新增交易紀錄失敗: {e}")
        return False

def delete_record(user_id, record_id, record_type, record_amount, current_balance):
    """從 Firestore 刪除交易紀錄並反向更新餘額"""
    db = st.session_state.get('db')
    if not db:
        return False

    records_ref = db.collection(get_base_path(user_id)).document(RECORD_COLLECTION_NAME).collection("items")
    
    # 計算餘額的變動：刪除收入記錄是減少，刪除支出記錄是增加
    amount_float = float(record_amount)
    if record_type == '收入':
        amount_change = -amount_float # 刪除收入 -> 餘額減少
    else: # 支出
        amount_change = amount_float # 刪除支出 -> 餘額增加
        
    try:
        # 1. 刪除交易紀錄
        records_ref.document(record_id).delete()
        
        # 2. 更新餘額
        new_balance = current_balance + amount_change
        if update_balance(user_id, amount_change):
            st.success(f"交易紀錄 (ID: {record_id[:4]}...) 已刪除，餘額已更新。")
            # 必須設置 rerun，因為刪除按鈕會觸發整個應用程式的重新運行，但確保數據是最新的
            st.experimental_rerun()
            return True
        else:
            st.warning("交易紀錄已刪除，但餘額反向更新失敗。")
            return False
            
    except Exception as e:
        st.error(f"刪除交易紀錄失敗: {e}")
        return False

# --- 4. Streamlit UI 結構 ---

def main():
    # 0. 初始設定
    initialize_firestore_client()
    user_id = get_user_id()
    set_ui_styles()
    
    st.title("簡易個人記帳本 📊")
    
    # 確保 current_balance 在 session state 中初始化或更新
    if 'current_balance' not in st.session_state:
        st.session_state['current_balance'] = fetch_balance(user_id)

    # 1. 顯示餘額
    st.header("當前餘額")
    
    col_bal, col_id = st.columns([3, 1])
    
    with col_bal:
        st.markdown(
            f"""
            <div class="balance-card">
                <div class="balance-label">總帳戶餘額</div>
                <div class="balance-amount">${st.session_state['current_balance']:,.0f}</div>
            </div>
            """, 
            unsafe_allow_html=True
        )
    with col_id:
        st.caption(f"用戶ID: `{user_id}`")
        
    st.markdown("---")

    # 2. 紀錄新的交易
    st.header("紀錄新交易")
    
    with st.form("new_transaction_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 1])
        
        # 交易日期
        date = col1.date_input(
            "日期", 
            value=datetime.date.today(),
            max_value=datetime.date.today(),
            help="選擇交易發生的日期"
        )
        
        # 交易類型
        type_options = ['支出', '收入']
        record_type = col2.selectbox(
            "類型", 
            options=type_options,
            index=0,
            help="選擇是支出還是收入"
        )
        
        # 類別
        default_categories = {
            '支出': ['餐飲', '交通', '生活用品', '娛樂', '房租/貸款', '其他支出'],
            '收入': ['薪水', '兼職', '投資收益', '禮金', '其他收入']
        }
        category = st.selectbox(
            "類別", 
            options=default_categories[record_type],
            help="選擇對應的交易類別"
        )
        
        col3, col4 = st.columns([1, 3])
        
        # 金額
        amount = col3.number_input(
            "金額", 
            min_value=0.01, 
            value=100.00, 
            step=1.00,
            format="%.2f",
            help="輸入交易金額"
        )
        
        # 備註
        note = col4.text_input(
            "備註 (選填)", 
            placeholder="例如：晚餐費、本月薪水",
            help="輸入簡短備註"
        )
        
        submitted = st.form_submit_button("新增交易")
        
        if submitted:
            if amount > 0:
                add_record(user_id, date, category, amount, record_type, note)
            else:
                st.error("金額必須大於零。")
    
    st.markdown("---")

    # 3. 交易分析與紀錄顯示
    st.header("交易分析與紀錄")

    # 3.1. 數據獲取與過濾
    df_records = fetch_records(user_id)
    
    if df_records.empty:
        st.info("目前沒有任何交易紀錄。")
        return

    # 篩選區
    col_date_range, col_cat_filter = st.columns([1, 1])
    
    min_date = df_records['date'].min()
    max_date = df_records['date'].max()

    with col_date_range:
        # 選擇日期範圍
        start_date = st.date_input("開始日期", min_value=min_date, max_value=max_date, value=min_date)
        end_date = st.date_input("結束日期", min_value=min_date, max_value=max_date, value=max_date)

    with col_cat_filter:
        # 選擇類別篩選
        all_categories = sorted(df_records['category'].unique().tolist())
        selected_categories = st.multiselect("篩選類別", all_categories, default=all_categories)
        
    
    # 應用篩選
    df_filtered = df_records[
        (df_records['date'] >= start_date) & 
        (df_records['date'] <= end_date) &
        (df_records['category'].isin(selected_categories))
    ].copy()


    # 3.2. 支出分佈圖
    st.subheader("選定範圍內支出分佈")
    
    df_expenses = df_filtered[df_filtered['type'] == '支出'].copy()
    total_expense = df_expenses['amount'].sum()
    
    if not df_expenses.empty and total_expense > 0:
        # 計算每個類別的總支出
        df_category_sum = df_expenses.groupby('category')['amount'].sum().reset_index()
        df_category_sum['percentage'] = df_category_sum['amount'] / total_expense
        
        # 1. 基礎圓餅圖
        base = alt.Chart(df_category_sum).encode(
            theta=alt.Theta("amount", stack=True)
        )
        
        # 2. 建立弧線（Arc）圖層
        pie = base.mark_arc(outerRadius=120, innerRadius=50).encode(
            color=alt.Color("category", title="支出類別"), 
            order=alt.Order("amount", sort="descending"),
            tooltip=["category", alt.Tooltip("amount", format=',.0f', title='支出金額'), alt.Tooltip("percentage", format='.1%', title='比例')]
        ).properties(
            title="選定範圍內各類別支出金額分佈"
        )
        
        # 3. 建立中央總支出文字層
        text = base.mark_text(radius=140).encode(
            text=alt.Text("percentage", format=".1%"),
            order=alt.Order("amount", sort="descending"),
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

    # 3.3. 交易紀錄區 (新增刪除按鈕)
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
        st.markdown("**無符合篩選條件的交易紀錄。**")
        return # 結束函數
    
    # 標題列
    # 調整 HTML 寬度比例以匹配 Streamlit 欄位，並給予備註更多空間
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px;'>
            <div style='width: 12%; padding-left: 1rem;'>日期</div>
            <div style='width: 9%;'>類別</div>
            <div style='width: 9%;'>金額</div>
            <div style='width: 6%;'>類型</div>
            <div style='width: 54%;'>備註</div> <!-- 顯著增加備註寬度 -->
            <div style='width: 10%; text-align: center;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    for index, row in display_df.iterrows():
        # 這裡需要從完整的 df_records 中取得交易細節用於反向計算餘額
        # .iloc[0] 用於從單行 DataFrame 中提取 Series
        try:
            record_details_for_delete = df_records[df_records['id'] == row['文件ID']].iloc[0].to_dict()
        except IndexError:
            # 如果找不到原始紀錄，則跳過，避免刪除時報錯
            st.error(f"找不到文件ID為 {row['文件ID']} 的原始紀錄，可能已被刪除。")
            continue
            
        color = "#28a745" if row['類型'] == '收入' else "#dc3545"
        amount_sign = "+" if row['類型'] == '收入' else "-"
        
        with st.container():
            # **修正點 2: 調整 st.columns 比例，增加備註欄位的權重 (6)**
            # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 6, 操作 1] (總和 10.9)
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 6, 1])
            
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
                    current_balance=st.session_state['current_balance'] # 使用 session state 中的最新餘額
                )

if __name__ == '__main__':
    main()

