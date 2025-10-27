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
            border-bottom: 2px solid #e9ecef; /* 添加分隔線 */
            padding-bottom: 0.5rem;
        }}
        
        /* 主要背景色 */
        .stApp {{
            background-color: {DEFAULT_BG_COLOR};
        }}

        /* 資訊卡片基礎樣式 */
        .info-card {{
            background-color: #ffffff;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
            text-align: center;
            height: 100%; /* 確保卡片高度一致 */
        }}

        /* 資訊卡片標題 (餘額/收入/支出) */
        .info-title {{
            font-size: 1rem;
            color: #6c757d;
            margin-bottom: 10px;
            font-weight: 600;
        }}

        /* 金額數字樣式 */
        .info-value {{
            font-size: 1.8rem;
            font-weight: 700;
        }}
        
        /* 餘額卡片特定的顏色 */
        .balance-value {{
            color: #007bff; /* 藍色 */
        }}

        /* 收入卡片特定的顏色 */
        .income-value {{
            color: #28a745; /* 綠色 */
        }}

        /* 支出卡片特定的顏色 */
        .expense-value {{
            color: #dc3545; /* 紅色 */
        }}
        
        /* 調整 Streamlit 的 primary button 樣式 */
        .stButton>button {{
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.2s;
        }}
        
        /* 調整 Streamlit 的 secondary button (用於刪除) 樣式 */
        .stButton button[kind="secondary"] {{
             background-color: #f8d7da; /* 淺紅背景 */
             color: #721c24; /* 深紅文字 */
             border-color: #f5c6cb;
        }}
        
        /* 調整多欄位布局的間距，讓交易紀錄顯示更緊湊 */
        [data-testid="stHorizontalBlock"] {{
            gap: 0.5rem;
        }}

        </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    st.set_page_config(layout="wide")

# --- 2. Firebase/Firestore 操作 ---
# 初始化 Firestore 客戶端
# 假定 Streamlit 環境中已設定好 Google 服務帳號憑證
@st.cache_resource
def get_firestore_client():
    """初始化並回傳 Firestore 客戶端。"""
    try:
        # 使用專案 ID 初始化，以讀取 Streamlit Secrets 中的憑證
        return firestore.Client()
    except Exception as e:
        st.error(f"Firestore 初始化失敗: {e}")
        return None

db = get_firestore_client()

def get_balance_ref(user_id):
    """獲取餘額文件的參考 (Reference)。"""
    # 儲存於 /artifacts/{appId}/users/{userId}/account_status/current_balance
    app_id = st.session_state.get('app_id', 'default-app-id')
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)

def get_records_ref(user_id):
    """獲取交易紀錄 Collection 的參考 (Reference)。"""
    # 儲存於 /artifacts/{appId}/users/{userId}/records
    app_id = st.session_state.get('app_id', 'default-app-id')
    return db.collection('artifacts').document(app_id).collection('users').document(user_id).collection(RECORD_COLLECTION_NAME)

def fetch_current_balance(user_id):
    """從 Firestore 獲取當前餘額，如果文件不存在則初始化為 0。"""
    if not db: return 0.0
    try:
        balance_ref = get_balance_ref(user_id)
        doc = balance_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0.0)
        else:
            # 文件不存在，初始化餘額
            balance_ref.set({'balance': 0.0})
            return 0.0
    except Exception as e:
        st.error(f"讀取餘額失敗: {e}")
        return 0.0

def update_current_balance(user_id, amount_change):
    """原子性地更新 Firestore 中的餘額。"""
    if not db: return
    try:
        balance_ref = get_balance_ref(user_id)
        
        # 由於這是單用戶應用，我們使用讀取、計算、寫入模式。
        current_balance = fetch_current_balance(user_id) # 重新讀取確保最新
        new_balance = current_balance + amount_change
        
        balance_ref.set({'balance': new_balance})
        st.session_state['current_balance'] = new_balance # 更新 session state
    except Exception as e:
        st.error(f"更新餘額失敗: {e}")

def add_new_record(db, user_id, record_data):
    """向 Firestore 添加新的交易紀錄並更新餘額。"""
    if not db: return
    try:
        record_ref = get_records_ref(user_id)
        
        # 生成一個唯一的 ID
        new_id = str(uuid.uuid4())
        doc_ref = record_ref.document(new_id)
        
        # 將 ID 加入數據中
        record_data['id'] = new_id
        
        # 寫入交易紀錄
        doc_ref.set(record_data)
        
        # 根據交易類型計算餘額變動
        amount_change = record_data['amount'] if record_data['type'] == '收入' else -record_data['amount']
        update_current_balance(user_id, amount_change)
        
        st.success(f"新增 {record_data['type']} 紀錄成功！")
        st.experimental_rerun() # 重新執行以刷新介面和紀錄列表
    except Exception as e:
        st.error(f"新增紀錄失敗: {e}")

def delete_record(db, user_id, record_id, record_type, record_amount, current_balance):
    """從 Firestore 刪除交易紀錄並反向更新餘額。"""
    if not db: return
    try:
        record_ref = get_records_ref(user_id)
        record_ref.document(record_id).delete()
        
        # 反向計算餘額變動: 
        # 如果是收入，餘額變動為 -amount
        # 如果是支出，餘額變動為 +amount
        amount_reversal = -record_amount if record_type == '收入' else record_amount
        
        new_balance = current_balance + amount_reversal
        
        # 直接更新餘額文件
        get_balance_ref(user_id).set({'balance': new_balance})
        st.session_state['current_balance'] = new_balance # 更新 session state
        
        st.success("紀錄刪除成功，餘額已更新！")
        st.experimental_rerun() # 重新執行以刷新介面
    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")


def fetch_all_records(user_id):
    """從 Firestore 獲取所有交易紀錄，並轉換為 DataFrame。"""
    if not db: return pd.DataFrame()
    try:
        records_ref = get_records_ref(user_id)
        docs = records_ref.stream()
        
        data = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id # 儲存文件 ID
            # 將 Firestore 的日期時間戳轉換為 Python 的 datetime.date
            if 'date' in record and isinstance(record['date'], datetime.datetime):
                 record['date'] = record['date'].date()
            data.append(record)
            
        df = pd.DataFrame(data)
        
        if not df.empty:
            # 確保 'date' 欄位是日期類型，便於篩選
            df['date'] = pd.to_datetime(df['date']).dt.date 
            # 確保 'amount' 是數字類型
            df['amount'] = pd.to_numeric(df['amount'])
            # 按日期降序排序 (最新在最上)
            df.sort_values(by='date', ascending=False, inplace=True)
            
        return df
        
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        return pd.DataFrame()

# --- 3. Streamlit 應用主邏輯 ---

def main():
    set_ui_styles()
    
    # 模擬用戶 ID (在實際應用中應從 Auth 獲取)
    # 這裡使用一個固定的虛擬 ID 來模擬單一用戶的數據隔離
    user_id = 'demo_user_001' 
    st.session_state['app_id'] = 'personal-finance-tracker' # 確保 app_id 存在

    st.title("💸 簡約個人財務追蹤器 (Streamlit + Firestore)")
    
    # 初始化 session state 中的餘額
    if 'current_balance' not in st.session_state:
        st.session_state['current_balance'] = fetch_current_balance(user_id)

    # 3.1. 交易輸入區
    st.header("新增交易紀錄")
    
    # 使用 st.form 來包裹輸入，確保輸入一致性
    with st.form("new_record_form", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns([1, 1, 1, 3])
        
        # 類型選擇
        record_type = col1.selectbox("類型", ['支出', '收入'], key="type_select")
        
        # 類別選擇 (根據類型動態更新)
        category_options = CATEGORIES[record_type]
        category = col2.selectbox("類別", category_options, key="category_select")
        
        # 金額輸入
        amount = col3.number_input("金額 (NT$)", min_value=1, step=100, format="%d", key="amount_input")
        
        # 日期選擇 (預設為今天)
        date = col4.date_input("日期", datetime.date.today(), key="date_input")

        # 備註/說明 (跨欄位)
        note = st.text_input("備註 (可選)", key="note_input")
        
        # 提交按鈕
        submitted = st.form_submit_button("提交紀錄", type="primary")

        if submitted:
            if amount is None or amount <= 0:
                st.error("請輸入有效的金額。")
            else:
                record_data = {
                    'type': record_type,
                    'category': category,
                    'amount': float(amount),
                    # 將 date 轉換為 datetime.datetime 類型以便 Firestore 儲存
                    'date': datetime.datetime.combine(date, datetime.time()),
                    'note': note if note else ""
                }
                add_new_record(db, user_id, record_data)
    
    st.markdown("---")
    
    # --- 3.2. 財務概覽與圖表區 ---
    
    # 獲取所有交易紀錄
    df_records = fetch_all_records(user_id)
    
    if df_records.empty:
        st.info("目前沒有交易紀錄。請新增第一筆紀錄。")
        return # 如果沒有紀錄，則不執行後續的篩選和圖表

    # 設置篩選日期範圍 (預設為本月)
    st.header("篩選與分析")
    
    today = datetime.date.today()
    first_day_of_month = today.replace(day=1)
    
    col_start, col_end = st.columns(2)
    start_date = col_start.date_input("起始日期", value=first_day_of_month)
    end_date = col_end.date_input("結束日期", value=today)

    # 篩選數據
    df_filtered = df_records[
        (df_records['date'] >= start_date) & 
        (df_records['date'] <= end_date)
    ].copy()
    
    # --- 3.2.1 總覽資訊卡片 (新增區塊) ---
    st.subheader("財務概覽")
    
    # 計算篩選期間的收入和支出
    total_income_filtered = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
    total_expense_filtered = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
    
    # 餘額使用 session state 中的即時餘額
    current_balance = st.session_state.get('current_balance', 0.0)
    
    # 格式化金額
    def format_currency(amount):
        return f"NT$ {amount:,.0f}"

    col_balance, col_income, col_expense = st.columns(3)
    
    # 卡片 1: 總餘額
    with col_balance:
        st.markdown(f"""
            <div class="info-card">
                <div class="info-title">目前總餘額</div>
                <div class="info-value balance-value">{format_currency(current_balance)}</div>
            </div>
        """, unsafe_allow_html=True)

    # 卡片 2: 期間總收入
    with col_income:
        st.markdown(f"""
            <div class="info-card">
                <div class="info-title">期間總收入</div>
                <div class="info-value income-value">{format_currency(total_income_filtered)}</div>
            </div>
        """, unsafe_allow_html=True)

    # 卡片 3: 期間總支出
    with col_expense:
        st.markdown(f"""
            <div class="info-card">
                <div class="info-title">期間總支出</div>
                <div class="info-value expense-value">{format_currency(total_expense_filtered)}</div>
            </div>
        """, unsafe_allow_html=True)
        
    st.markdown("---") # 分隔線

    # --- 3.2.2 支出分佈圖 ---
    st.header("支出分佈圖 (期間)")
    
    # 過濾出支出，並按 'category' 分組求和
    expense_data = df_filtered[df_filtered['type'] == '支出'].groupby('category')['amount'].sum().reset_index()
    expense_data.rename(columns={'amount': 'total_amount'}, inplace=True)
    
    if not expense_data.empty and expense_data['total_amount'].sum() > 0:
        
        # 計算佔比
        total_expense = expense_data['total_amount'].sum()
        expense_data['percentage'] = (expense_data['total_amount'] / total_expense) * 100
        
        # 設置基礎圖表
        base = alt.Chart(expense_data).encode(
            theta=alt.Theta("total_amount", stack=True)
        )
        
        # 圓餅圖/弧形
        pie = base.mark_arc(outerRadius=120).encode(
            color=alt.Color("category", title="支出類別"),
            order=alt.Order("total_amount", sort="descending"),
            tooltip=["category", alt.Tooltip("total_amount", title="金額", format=",.0f"), alt.Tooltip("percentage", title="佔比", format=".1f") + "%"],
        )
        
        # 文本標籤 (計算標籤位置)
        text = base.mark_text(radius=140).encode(
            text=alt.Text("percentage", format=".1f"), # 顯示百分比
            order=alt.Order("total_amount", sort="descending"),
            color=alt.value("black") # 標籤顏色
        )
        
        # 組合圖表並居中顯示
        chart = pie.interactive() 
        
        st.altair_chart(chart, use_container_width=True)
        
    else:
        st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # --- 3.3. 交易紀錄區 (新增刪除按鈕) ---
    st.header("完整交易紀錄 (期間)")
    
    # 準備用於顯示和刪除的 DataFrame
    # 顯示的欄位: 日期, 類別, 金額, 類型, 備註, (文件ID隱藏在刪除按鈕邏輯中)
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
        st.info(f"在 {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')} 期間沒有交易紀錄。")
        return

    # 標題列 (使用 Markdown/HTML 來控制寬度並保持簡約樣式)
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px;'>
            <div style='width: 12%; padding-left: 1rem;'>日期</div>
            <div style='width: 10%;'>類別</div>
            <div style='width: 10%;'>金額</div>
            <div style='width: 7%;'>類型</div>
            <div style='width: 51%;'>備註</div>
            <div style='width: 10%; text-align: center; padding-right: 0.5rem;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    for index, row in display_df.iterrows():
        # 從完整的 df_records 中獲取刪除所需的資訊
        try:
            # 使用文件 ID 進行查找
            record_details_for_delete = df_records[df_records['id'] == row['文件ID']].iloc[0].to_dict()
        except IndexError:
            # 如果找不到原始紀錄，則跳過，避免刪除時報錯
            st.error(f"找不到文件ID為 {row['文件ID']} 的原始紀錄，可能已被刪除。")
            continue
            
        color = "#28a745" if row['類型'] == '收入' else "#dc3545"
        amount_sign = "+" if row['類型'] == '收入' else "-"
        
        # 使用 container 和 columns 創建行布局
        with st.container():
            # 調整 st.columns 比例，增加備註欄位的權重 (6)
            # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 6, 操作 1] (總和 10.9)
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 6, 1])
            
            # 使用 st.write 顯示交易細節
            col_date.write(row['日期'].strftime('%Y-%m-%d'))
            col_cat.write(row['類別'])
            # 使用 Markdown/HTML 顯示金額，帶有顏色和正負號
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row['金額']:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(row['類型'])
            col_note.write(row['備註']) # 備註內容，給予更多空間避免重疊
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{row['文件ID']}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                delete_record(
                    db=db,
                    user_id=user_id,
                    record_id=row['文件ID'],
                    record_type=record_details_for_delete['type'],
                    record_amount=record_details_for_delete['amount'],
                    current_balance=st.session_state.get('current_balance', 0.0)
                )

if __name__ == '__main__':
    main()

