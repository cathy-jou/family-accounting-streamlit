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
        
        /* 交易記錄區的卡片樣式 */
        [data-testid="stContainer"] {{
            background-color: #ffffff; 
            padding: 1rem;
            border-radius: 0.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05); /* 輕微陰影 */
            margin-bottom: 1rem;
        }}
        
        /* 主要背景顏色 */
        .stApp {{
            background-color: {DEFAULT_BG_COLOR}; 
        }}
        
        /* Streamlit 內建按鈕的樣式優化 */
        .stButton>button {{
            border-radius: 0.3rem;
            font-weight: 600;
            transition: all 0.2s;
        }}
        
        /* 刪除按鈕特別樣式 */
        .stButton>button[kind="secondary"] {{
            border-color: #dc3545;
            color: #dc3545;
        }}

        /* 金額顯示優化，增加對齊和空間 */
        [data-testid="stMarkdownContainer"] span {{
            display: inline-block;
            text-align: right;
            min-width: 60px; /* 確保金額欄位有最小寬度 */
        }}

        /* 調整輸入欄位樣式 */
        .stTextInput>div>div>input, 
        .stDateInput>div>div>input,
        .stSelectbox>div>div>select,
        .stNumberInput>div>div>input
        {{
            border-radius: 0.3rem;
            border: 1px solid #ced4da;
            padding: 0.5rem 0.75rem;
        }}

        /* 調整 st.columns 內部元素的垂直對齊 */
        [data-testid="column"] > div {{
            display: flex;
            flex-direction: column;
            justify-content: flex-start; /* 或 center,取決於需求 */
            height: 100%;
        }}

        /* 對齊 st.write 內容,尤其是日期和類型 */
        [data-testid^="stTextLabel"] {{
             padding-top: 0.5rem;
             padding-bottom: 0.5rem;
        }}

        /* 調整交易列表標題的樣式 */
        .header-row {{
            font-weight: bold;
            color: #495057;
            padding: 0.5rem 0;
            border-bottom: 1px solid #dee2e6;
            margin-bottom: 0.5rem;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    
# --- 2. Firestore 連線與初始化 ---
# 初始化 Firestore
@st.cache_resource
def get_firestore_db():
    """初始化並回傳 Firestore 客戶端"""
    try:
        # 檢查是否在 Streamlit Cloud 環境中
        if "firestore_credentials" in st.secrets:
            # 使用 Streamlit secrets 提供的服務帳戶 JSON
            db = firestore.Client.from_service_account_info(st.secrets["firestore_credentials"])
        else:
            # 嘗試使用 GOOGLE_APPLICATION_CREDENTIALS 環境變數 (本地開發)
            db = firestore.Client()
        return db
    except Exception as e:
        st.error(f"Firestore 連線失敗: {e}")
        st.stop()
        
db = get_firestore_db()


# --- 3. 數據操作函數 ---

def get_balance(db: firestore.Client) -> float:
    """從 Firestore 獲取當前餘額，如果不存在則創建並返回 0"""
    try:
        balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
        doc = balance_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0.0)
        else:
            # 如果文件不存在，則初始化餘額為 0.0
            balance_ref.set({'balance': 0.0})
            return 0.0
    except Exception as e:
        st.error(f"獲取餘額失敗: {e}")
        return 0.0 # 失敗時返回 0

def update_balance(db: firestore.Client, amount: float, operation: str):
    """更新 Firestore 中的餘額"""
    balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
    
    # 使用 Firestore transaction 確保原子性更新
    @firestore.transactional
    def transaction_update(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        current_balance = snapshot.to_dict().get('balance', 0.0) if snapshot.exists else 0.0
        
        new_balance = current_balance
        if operation == 'add':
            new_balance += amount
        elif operation == 'subtract':
            new_balance -= amount
        else:
            raise ValueError(f"無效的操作: {operation}")
            
        transaction.set(ref, {'balance': new_balance, 'last_updated': datetime.datetime.now()})
        return new_balance

    try:
        transaction = db.transaction()
        transaction_update(transaction, balance_ref)
        # 更新成功後清除 Streamlit 的快取，確保下次讀取最新值
        get_all_records.clear() 
        get_balance.clear()
    except Exception as e:
        st.error(f"更新餘額時發生錯誤: {e}")

@st.cache_data(ttl=60) # 緩存 60 秒
def get_all_records(db: firestore.Client) -> pd.DataFrame:
    """從 Firestore 獲取所有交易紀錄並轉換為 DataFrame"""
    try:
        records_ref = db.collection(RECORD_COLLECTION_NAME)
        # 按照日期降序排列
        query = records_ref.order_by("date", direction=firestore.Query.DESCENDING).stream()
        
        data = []
        for doc in query:
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id # 將文件 ID 加入資料中
            
            # 確保 date 是 datetime 對象
            if 'date' in doc_data and isinstance(doc_data['date'], firestore.client.FieldPath):
                # 如果是 FieldPath，通常是 timestamp 類型，轉換為 datetime
                doc_data['date'] = doc_data['date'].to_dict().get('timestamp').to_datetime()
            elif 'date' in doc_data and hasattr(doc_data['date'], 'to_datetime'):
                doc_data['date'] = doc_data['date'].to_datetime()
            
            data.append(doc_data)

        if not data:
            return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note'])

        df = pd.DataFrame(data)
        
        # 轉換數據類型
        df['date'] = pd.to_datetime(df['date'])
        df['amount'] = pd.to_numeric(df['amount'])
        
        return df
    except Exception as e:
        st.error(f"獲取交易紀錄失敗: {e}")
        return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note']) # 失敗時返回空 DataFrame

def add_record(db: firestore.Client, record: dict):
    """向 Firestore 添加一筆交易紀錄"""
    try:
        # 這裡不需要自定義 ID，讓 Firestore 自動生成
        db.collection(RECORD_COLLECTION_NAME).add(record)
        
        # 更新餘額
        amount = record['amount']
        operation = 'add' if record['type'] == '收入' else 'subtract'
        update_balance(db, amount, operation)
        
        st.success("交易紀錄已成功添加並更新餘額！")
    except Exception as e:
        st.error(f"添加交易紀錄失敗: {e}")

def delete_record(db: firestore.Client, doc_id: str, record_type: str, amount: float):
    """從 Firestore 刪除一筆交易紀錄並回滾餘額"""
    try:
        db.collection(RECORD_COLLECTION_NAME).document(doc_id).delete()
        
        # 餘額回滾操作：刪除收入 -> 餘額減去收入；刪除支出 -> 餘額加上支出
        rollback_amount = amount
        rollback_operation = 'subtract' if record_type == '收入' else 'add'
        
        update_balance(db, rollback_amount, rollback_operation)
        
        st.success("交易紀錄已成功刪除並回滾餘額！")
        
        # 強制刷新整個 Streamlit 頁面以更新列表和餘額
        st.rerun() 
        
    except Exception as e:
        st.error(f"刪除交易紀錄失敗: {e}")

# --- 4. 儀表板組件 ---

def display_summary(df_records: pd.DataFrame, current_balance: float):
    """顯示餘額、總收入和總支出"""
    
    # 設置標題
    st.markdown("## 📊 儀表板", unsafe_allow_html=True)

    # 計算總收入和總支出
    total_income = df_records[df_records['type'] == '收入']['amount'].sum()
    total_expense = df_records[df_records['type'] == '支出']['amount'].sum()

    # 使用 columns 佈局
    col_bal, col_inc, col_exp = st.columns(3)
    
    # 餘額卡片
    with col_bal:
        st.markdown(
            f"""
            <div style='background-color: #e9ecef; padding: 1rem; border-radius: 0.5rem; text-align: center;'>
                <h4 style='color: #495057; margin: 0 0 0.5rem 0; font-size: 1rem;'>當前餘額 (總結算)</h4>
                <p style='color: #343a40; margin: 0; font-size: 1.8rem; font-weight: 700;'>
                    {current_balance:,.0f}
                </p>
            </div>
            """, unsafe_allow_html=True
        )
        
    # 總收入卡片
    with col_inc:
        st.markdown(
            f"""
            <div style='background-color: #d4edda; padding: 1rem; border-radius: 0.5rem; text-align: center;'>
                <h4 style='color: #155724; margin: 0 0 0.5rem 0; font-size: 1rem;'>總收入</h4>
                <p style='color: #28a745; margin: 0; font-size: 1.8rem; font-weight: 700;'>
                    + {total_income:,.0f}
                </p>
            </div>
            """, unsafe_allow_html=True
        )

    # 總支出卡片
    with col_exp:
        st.markdown(
            f"""
            <div style='background-color: #f8d7da; padding: 1rem; border-radius: 0.5rem; text-align: center;'>
                <h4 style='color: #721c24; margin: 0 0 0.5rem 0; font-size: 1rem;'>總支出</h4>
                <p style='color: #dc3545; margin: 0; font-size: 1.8rem; font-weight: 700;'>
                    - {total_expense:,.0f}
                </p>
            </div>
            """, unsafe_allow_html=True
        )

def display_chart(df_records: pd.DataFrame):
    """顯示月度趨勢圖和類別分佈圖"""
    
    if df_records.empty:
        st.info("沒有交易記錄，無法生成圖表。")
        return

    # 1. 準備月度數據
    df_records['month'] = df_records['date'].dt.to_period('M').astype(str)
    
    # 計算每個月的收入和支出
    df_monthly = df_records.groupby(['month', 'type'])['amount'].sum().reset_index()
    
    # 2. 月度趨勢圖
    st.markdown("### 📈 月度收入與支出趨勢", unsafe_allow_html=True)
    
    # 使用 Altair 創建圖表
    chart_trend = alt.Chart(df_monthly).mark_bar().encode(
        # 月份按時間順序排列
        x=alt.X('month', title='月份', sort='ascending'), 
        y=alt.Y('amount', title='金額 (NTD)'),
        color=alt.Color('type', title='類型', scale=alt.Scale(domain=['收入', '支出'], range=['#28a745', '#dc3545'])),
        tooltip=['month', 'type', alt.Tooltip('amount', format=',.0f')]
    ).properties(
        height=300
    ).interactive() # 允許縮放和拖動
    
    st.altair_chart(chart_trend, use_container_width=True)


    # 3. 類別分佈圖 (以支出為主)
    st.markdown("### 🏷️ 支出類別分佈", unsafe_allow_html=True)
    df_expense = df_records[df_records['type'] == '支出'].groupby('category')['amount'].sum().reset_index()
    
    if df_expense.empty:
        st.info("沒有支出記錄，無法生成支出類別分佈圖。")
        return

    # 類別圓餅圖 (Pie Chart)
    base = alt.Chart(df_expense).encode(
        theta=alt.Theta("amount", stack=True)
    )
    
    pie = base.mark_arc(outerRadius=120).encode(
        color=alt.Color("category", title="支出類別"),
        order=alt.Order("amount", sort="descending"),
        tooltip=["category", alt.Tooltip("amount", format=',.0f')]
    ).properties(
        title=""
    )
    
    text = base.mark_text(radius=140).encode(
        text=alt.Text("amount", format=",.0f"),
        order=alt.Order("amount", sort="descending"),
        color=alt.value("black") # 讓標籤顏色固定
    )
    
    st.altair_chart(pie + text, use_container_width=True)

# --- 5. 交易記錄輸入與顯示 ---

def input_record_form(db: firestore.Client):
    """顯示交易記錄輸入表單"""
    st.markdown("## 💰 記錄新交易", unsafe_allow_html=True)
    
    with st.form("record_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        # 交易類型選擇
        record_type = col1.selectbox("類型", ['支出', '收入'], index=0, help="選擇交易是收入還是支出")
        
        # 交易類別選擇
        category_options = CATEGORIES.get(record_type, [])
        category = col2.selectbox("類別", category_options, index=0, help="根據類型選擇細分類別")
        
        col3, col4 = st.columns(2)
        
        # 金額輸入
        amount = col3.number_input("金額 (NTD)", min_value=1, step=1, value=100, format="%d", help="請輸入交易金額")
        
        # 日期選擇
        date = col4.date_input("日期", datetime.date.today(), max_value=datetime.date.today(), help="選擇交易發生的日期")
        
        # 備註輸入
        note = st.text_area("備註", placeholder="例如：晚餐 - 麥當勞套餐、本月薪資", help="輸入交易的詳細描述")
        
        # 提交按鈕
        submitted = st.form_submit_button("💾 儲存紀錄", type="primary")
        
        if submitted:
            # 檢查輸入
            if amount is None or amount <= 0:
                st.warning("金額必須大於 0。")
            elif not category:
                st.warning("請選擇一個類別。")
            else:
                # 準備數據
                record_data = {
                    'date': date, # 日期是 datetime.date，Firestore 會自動轉換為 Timestamp
                    'type': record_type,
                    'category': category,
                    'amount': float(amount),
                    'note': note.strip() or '無備註', # 如果備註為空，則設為 '無備註'
                    'timestamp': datetime.datetime.now() # 紀錄創建時間，用於排序和唯一性
                }
                add_record(db, record_data)
                
                # 儲存後立即清除快取並重新執行，以更新列表和儀表板
                st.cache_data.clear() 
                st.rerun() 

def display_records(db: firestore.Client, df_records: pd.DataFrame):
    """顯示交易紀錄列表，包含標題列和刪除功能"""
    
    st.markdown("## 📜 交易紀錄列表", unsafe_allow_html=True)

    if df_records.empty:
        st.info("沒有任何交易紀錄。")
        return

    # 1. 顯示標題列
    # 比例: [日期 12%, 類別 10%, 金額 10%, 類型 7%, 備註 50%, 操作 11%] (總和 100)
    col_date_h, col_cat_h, col_amount_h, col_type_h, col_note_h, col_btn_h = st.columns([12, 10, 10, 7, 50, 11])
    
    with st.container():
        st.markdown("<div class='header-row'>", unsafe_allow_html=True) # 使用 CSS 類
        col_date_h.markdown("日期")
        col_cat_h.markdown("類別")
        col_amount_h.markdown("金額")
        col_type_h.markdown("類型")
        col_note_h.markdown("備註")
        col_btn_h.markdown("操作")
        st.markdown("</div>", unsafe_allow_html=True)

    # 2. 顯示每一筆交易
    for index, row in df_records.iterrows():
        try:
            # 安全地從 row 中提取數據，防止欄位遺失
            record_id = row['id']
            record_date = row['date']
            record_type = row['type']
            record_category = row['category']
            record_amount = row['amount']
            record_note = row['note']
            
        except KeyError as e:
            st.error(f"交易紀錄中缺少關鍵欄位: {e}。跳過此紀錄。")
            continue     
        except Exception as e:
            st.error(f"在迭代行時發生錯誤 (可能是欄位遺失或數據類型問題): {e}")
            continue
            
        color = "#28a745" if record_type == '收入' else "#dc3545"
        amount_sign = "+" if record_type == '收入' else "-"
        
        # 使用 container 和 columns 創建行布局
        with st.container():
            # 比例: [日期 12%, 類別 10%, 金額 10%, 類型 7%, 備註 50%, 操作 11%]
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([12, 10, 10, 7, 50, 11])
            
            # 使用 st.markdown/write 顯示交易細節
            # 將日期向左微調以對齊標題
            col_date.markdown(f"<div>{record_date.strftime('%Y-%m-%d')}</div>", unsafe_allow_html=True)
            col_cat.write(record_category)
            # 金額使用 markdown 著色
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {record_amount:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(record_type)
            col_note.write(record_note) # 備註內容
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{record_id}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                # 執行刪除操作
                delete_record(
                    db=db,
                    doc_id=record_id,
                    record_type=record_type,
                    amount=record_amount
                )
    
# --- 6. 主應用程式邏輯 ---
def main():
    """主函數，設定頁面並呼叫組件"""
    
    # 頁面配置
    st.set_page_config(
        page_title="家庭記帳本 - Streamlit & Firestore",
        layout="wide",
        initial_sidebar_state="auto"
    )
    
    # 注入樣式
    set_ui_styles()
    
    st.title("👨‍👩‍👧‍👦 雲端家庭記帳本")
    
    # 獲取所有數據
    df_records = get_all_records(db)
    current_balance = get_balance(db)

    # 1. 儀表板區域
    display_summary(df_records, current_balance)
    
    st.markdown("---")
    
    # 2. 交易輸入和圖表區域
    col_input, col_chart = st.columns([1, 1])
    
    with col_input:
        input_record_form(db)
    
    with col_chart:
        # 僅顯示月度趨勢圖，避免空間不足
        st.markdown("## 📈 數據分析", unsafe_allow_html=True)
        display_chart(df_records) # 圖表組件中包含分佈圖
        
    st.markdown("---")

    # 3. 交易紀錄列表
    display_records(db, df_records)

# 運行主函數
if __name__ == '__main__':
    main()
