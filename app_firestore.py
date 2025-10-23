import streamlit as st
import pandas as pd
import datetime
import altair as alt # 導入 Altair 庫用於進階圖表控制
from google.cloud import firestore
import time # 導入 time 模組用於延遲操作

# --- 0. Streamlit 介面設定 (字體 Inter) ---

# 設定固定的淺灰色背景
DEFAULT_BG_COLOR = "#f8f9fa" 

def set_ui_styles():
    """注入客製化 CSS，設定字體、簡約背景色和縮小主標題字體與調整間距"""
    css = f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

        /* 設置字體與基礎大小 (略微縮小基礎字體) */
        html, body, [class*="st-"] {{
            font-family: 'Inter', "PingFang TC", "Microsoft YaHei", sans-serif;
            font-size: 15px; /* 調整基礎字體大小 */
        }}
        
        /* 設定主標題 H1 字體大小並增加間距 */
        h1 {{
            font-size: 1.8rem; /* 將字體微縮 */
            font-weight: 700;
            color: #343a40; /* 深灰色字體 */
            margin-bottom: 2.5rem; /* 拉大與下方內容的間距 */
        }}
        
        /* 設定區塊標題 H2 (st.header) 字體大小並增加間距 */
        h2 {{
            font-size: 1.4rem;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 0.5rem;
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }}

        /* 讓輸入框和按鈕等元件看起來更現代 */
        div.stButton > button:first-child {{
            background-color: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 14px;
            margin: 4px 2px;
            transition-duration: 0.4s;
            cursor: pointer;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        div.stButton > button:first-child:hover {{
            background-color: #0056b3;
            box-shadow: 0 6px 8px rgba(0, 0, 0, 0.15);
        }}

        /* 針對刪除按鈕設置紅色樣式 */
        .delete-btn {{
            background-color: #dc3545 !important;
        }}
        .delete-btn:hover {{
            background-color: #c82333 !important;
        }}

        /* 覆寫 Streamlit 的主要內容區域背景 */
        .main {{
            background-color: {DEFAULT_BG_COLOR};
            padding-top: 2rem; 
        }}
        /* 針對 Streamlit 頁面最外層的背景 */
        [data-testid="stAppViewContainer"] {{
            background-color: {DEFAULT_BG_COLOR};
        }}
        /* 保持側邊欄為白色，與主內容區分隔，增強視覺層次感 */
        section[data-testid="stSidebar"] {{
            background-color: #ffffff; 
            box-shadow: 2px 0 5px rgba(0,0,0,0.05);
        }}
        
        /* 調整輸入框樣式 */
        .stTextInput > div > div > input, .stSelectbox > div > div > div > div > div, .stDateInput > label + div > div > input {{
            border-radius: 8px;
            border: 1px solid #ced4da;
            padding: 8px;
        }}

        /* 調整資訊/成功/錯誤訊息的樣式 */
        .stAlert {{
            border-radius: 8px;
        }}
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)


# --- 1. Firestore 連線與操作 ---

@st.cache_resource
def get_firestore_db():
    """
    初始化並連線到 Firestore。
    @st.cache_resource 確保只建立一次連線。
    """
    try:
        # 從 Streamlit secrets 載入 Firebase 服務帳戶憑證
        creds = st.secrets["firestore"]
        
        # 使用憑證初始化 Firestore 客戶端
        db = firestore.Client.from_service_account_info(creds)
        
        st.success("成功連線到 Firestore!")
        return db
    except Exception as e:
        st.error(f"連線 Firestore 失敗，請檢查 .streamlit/secrets.toml 檔案: {e}")
        st.stop() # 停止應用程式運行
        return None

# 預先定義常數
COLLECTION_NAME = "finance_records"
EXPENSE_CATEGORIES = ["餐飲", "交通", "購物", "娛樂", "房租/水電", "醫療", "教育", "其他"]
INCOME_CATEGORIES = ["薪資", "投資收益", "獎金", "其他收入"]


def add_record(db, record_data):
    """
    將一筆新的記帳紀錄寫入 Firestore。
    """
    try:
        collection_ref = db.collection(COLLECTION_NAME)
        # Firestore 會自動生成文件 ID
        collection_ref.add(record_data) 
        st.success("成功新增紀錄！")
        # 手動觸發 Streamlit 重新運行以更新數據
        st.rerun() 
    except Exception as e:
        st.error(f"寫入紀錄失敗: {e}")


def delete_record(db, doc_id):
    """
    從 Firestore 刪除指定 ID 的文件。
    """
    try:
        db.collection(COLLECTION_NAME).document(doc_id).delete()
        st.success("成功刪除紀錄！")
        # 手動觸發 Streamlit 重新運行以更新數據
        st.rerun() 
    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")


@st.cache_data(ttl=600) # 緩存數據 10 分鐘
def get_all_records(db):
    """
    從 Firestore 讀取所有記帳紀錄並轉換為 DataFrame。
    """
    try:
        collection_ref = db.collection(COLLECTION_NAME)
        docs = collection_ref.stream()
        records = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id # 儲存文件 ID
            
            # 確保 'date' 欄位是 datetime.date 物件
            if 'date' in record and isinstance(record['date'], firestore.client.base_client.datetime.date):
                # 如果是 Firestore 的 date 物件，轉換為 pandas/python datetime
                record['date'] = datetime.datetime.combine(record['date'], datetime.time.min)
            
            # 確保金額是數字
            if 'amount' in record:
                try:
                    record['amount'] = float(record['amount'])
                except ValueError:
                    st.warning(f"文件 {doc.id} 的金額格式錯誤，已跳過。")
                    continue

            records.append(record)
            
        if not records:
            return pd.DataFrame(columns=['id', 'date', 'category', 'amount', 'type', 'note'])

        df = pd.DataFrame(records)
        
        # 轉換日期格式
        # 由於 Firestore 儲存的可能是 date object, 在上面已經處理成 datetime object
        df['date'] = pd.to_datetime(df['date'])
        
        # 確保 amount 是 float
        df['amount'] = df['amount'].astype(float)
        
        return df.sort_values(by='date', ascending=False)
        
    except Exception as e:
        st.error(f"讀取紀錄失敗: {e}")
        return pd.DataFrame(columns=['id', 'date', 'category', 'amount', 'type', 'note'])


# --- 2. 新增交易介面 ---

def render_add_transaction_form(db):
    """
    渲染新增交易的側邊欄表單。
    """
    st.sidebar.header("新增一筆交易")
    
    with st.sidebar.form(key='add_transaction_form'):
        
        transaction_type = st.radio("類型", ["支出", "收入"], horizontal=True, index=0, key='radio_type')
        
        today = datetime.date.today()
        date = st.date_input("日期", value=today, max_value=today, key='input_date')
        
        # 根據類型選擇類別
        category_options = EXPENSE_CATEGORIES if transaction_type == "支出" else INCOME_CATEGORIES
        category = st.selectbox("類別", category_options, key='select_category')
        
        amount = st.number_input("金額 (TWD)", min_value=0.01, step=100.0, format="%.2f", key='input_amount')
        
        note = st.text_area("備註 (選填)", key='input_note')
        
        submit_button = st.form_submit_button(label='💾 新增紀錄')

        if submit_button:
            if amount is None or amount <= 0:
                st.sidebar.error("請輸入有效金額。")
            else:
                # 準備數據，將 date 轉換為 date object (Firestore 偏好)
                record_data = {
                    'date': date,
                    'type': transaction_type,
                    'category': category,
                    # 金額為 float
                    'amount': amount, 
                    'note': note,
                    'created_at': firestore.SERVER_TIMESTAMP # 記錄伺服器創建時間
                }
                add_record(db, record_data)
                
# --- 3. 主要內容與儀表板 ---

def main():
    """
    主應用程式邏輯。
    """
    set_ui_styles()
    st.title("💰 個人家庭記帳本 (Firestore)")

    db = get_firestore_db()
    if db is None:
        return

    # 渲染新增表單 (側邊欄)
    render_add_transaction_form(db)

    # 獲取數據
    df_records = get_all_records(db)
    
    if df_records.empty:
        st.info("目前沒有任何交易紀錄，請在左側側邊欄新增第一筆紀錄。")
        return

    # ----------------------------------------------------
    # 3.1. 篩選與總覽

    # 取得所有月份列表
    # dt.to_period('M') 轉換為月度時間段，astype(str) 轉換為 'YYYY-MM' 格式的字串
    months_list = sorted(list(df_records['date'].dt.to_period('M').astype(str).unique()), reverse=True)
    
    # 設置當前月份 (預設值)
    # 預設顯示最新月份的數據
    current_month_str = months_list[0] 
    
    # --- Month Selector ---
    
    # *** 修正錯誤: 避免使用 months_list.index(...) 導致的 TypeError/ValueError ***
    # 由於 months_list 已經是倒序排列 (最新月份在 months_list[0])，
    # 故直接將初始索引設定為 0 即可，避免因 Streamlit 緩存或重跑導致的索引錯誤。
    selected_month = st.selectbox(
        "選擇月份",
        months_list,
        index=0 # 預設顯示最新的月份
    )
    
    # 篩選數據
    df_filtered = df_records[df_records['date'].dt.strftime('%Y-%m') == selected_month]
    
    # ----------------------------------------------------
    
    # 3.2. 儀表板計算與顯示
    
    st.header(f"📊 {selected_month} 月份總覽")

    # 計算總收入和總支出
    total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
    total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
    net_flow = total_income - total_expense

    # 格式化輸出
    col1, col2, col3 = st.columns(3)
    
    col1.metric("總收入", f"TWD {total_income:,.0f}", delta_color="off")
    col2.metric("總支出", f"TWD {total_expense:,.0f}", delta_color="off")
    
    # 根據淨現金流的正負設置 delta 顏色
    delta_color = "normal" if net_flow >= 0 else "inverse"
    col3.metric("淨現金流 (結餘)", f"TWD {net_flow:,.0f}", delta=f"TWD {net_flow:,.0f}", delta_color=delta_color)

    st.markdown("---")
    
    # 支出分佈圖 (圓餅圖)
    st.header("📉 支出分佈分析")
    
    expense_data = df_filtered[df_filtered['type'] == '支出'].groupby('category')['amount'].sum().reset_index()
    expense_data.columns = ['category', 'amount']
    
    if total_expense > 0:
        
        # 1. 計算比例 (用於標籤)
        expense_data['percentage'] = (expense_data['amount'] / total_expense) * 100
        
        # 2. 建立圓餅圖
        pie = alt.Chart(expense_data).mark_arc(outerRadius=120).encode(
            # 角度 (扇區大小)
            theta=alt.Theta("amount", stack=True), 
            # 顏色 (根據類別)
            color=alt.Color("category", title="支出類別"),
            # 懸停提示
            tooltip=['category', alt.Tooltip('amount', format=',.0f', title='總支出'), alt.Tooltip('percentage', format='.1f', title='比例 (%)')]
        ).properties(
            title="選定範圍內各類別支出金額分佈"
        )
        
        # 3. 添加文字標籤 (放置在扇形的中間)
        text = pie.mark_text(radius=140).encode(
            text=alt.Text("percentage", format=".1f"),
            order=alt.Order("amount", sort="descending"),
            color=alt.value("black") # 確保標籤顏色可見
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
    
    # 遍歷每一筆紀錄，並為其添加一個刪除按鈕
    st.markdown("---")
    
    # 排序以確保刪除後介面更穩定 (雖然 Streamlit reruns，但視覺上更好)
    display_df = display_df.sort_values(by='日期', ascending=False)
    
    # 創建一個容器用於提示信息
    message_container = st.empty() 

    for index, row in display_df.iterrows():
        # 為每行創建 5 欄：日期, 類別, 金額, 備註, 刪除按鈕
        col_date, col_cat, col_amount, col_note, col_btn = st.columns([1, 1, 1, 3, 1])
        
        # 顯示交易細節
        # 將日期格式化為 YYYY-MM-DD
        col_date.write(row['日期'].strftime('%Y-%m-%d'))
        col_cat.write(row['類別'])
        
        # 根據類型設置金額顏色
        amount_color = "red" if row['類型'] == '支出' else "green"
        col_amount.markdown(f"<span style='color: {amount_color}; font-weight: bold;'>{row['金額']:,.0f}</span>", unsafe_allow_html=True)
        
        col_note.write(row['備註'])
        
        # 刪除按鈕
        # 使用唯一鍵 'delete_{row["文件ID"]}'
        if col_btn.button("🗑️ 刪除", key=f'delete_{row["文件ID"]}', help="點擊刪除這筆紀錄", type="secondary"):
            # 避免直接刪除，改為在 session state 標記準備刪除
            st.session_state['delete_doc_id'] = row['文件ID']
            st.session_state['show_confirm'] = True
            st.rerun() # 觸發 rerun 以顯示確認框

    # ----------------- 刪除確認模態框 (使用 Streamlit 容器模擬) -----------------
    if 'show_confirm' in st.session_state and st.session_state['show_confirm']:
        doc_id_to_delete = st.session_state['delete_doc_id']
        
        # 模擬 Modal 或使用 st.expander 也可以，但這裡用 st.container 來覆蓋/強調
        with st.container(border=True):
            st.warning("⚠️ 確認刪除")
            st.write(f"您確定要刪除文件ID為 **`{doc_id_to_delete}`** 的這筆紀錄嗎？此操作不可逆轉。")
            
            col_yes, col_no = st.columns([1, 5])
            
            # 確認刪除
            if col_yes.button("✅ 是，刪除", key="confirm_delete_yes", type="primary"):
                delete_record(db, doc_id_to_delete)
                # 清理 session state
                del st.session_state['show_confirm']
                del st.session_state['delete_doc_id']
                # delete_record 內部會 st.rerun()
                
            # 取消刪除
            if col_no.button("❌ 否，取消", key="confirm_delete_no", type="secondary"):
                st.session_state['show_confirm'] = False
                del st.session_state['delete_doc_id']
                st.info("已取消刪除操作。")
                time.sleep(1) # 增加延遲讓用戶看到取消訊息
                st.rerun() # 觸發 rerun 移除確認框
    
    # ----------------------------------------------------------------------


if __name__ == "__main__":
    main()



