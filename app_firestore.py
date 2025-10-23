import streamlit as st
import pandas as pd
import datetime
import altair as alt # 導入 Altair 庫用於進階圖表控制
from google.cloud import firestore

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
            font-size: 1.5rem;
            font-weight: 600;
            color: #495057; 
            border-bottom: 2px solid #e9ecef; /* 區塊分隔線 */
            padding-bottom: 0.5rem;
            margin-top: 2rem;
        }}
        
        /* 設置背景顏色 */
        .main {{
            background-color: {DEFAULT_BG_COLOR};
            padding-top: 2rem; 
        }}
        [data-testid="stAppViewContainer"] {{
            background-color: {DEFAULT_BG_COLOR};
        }}
        /* 側邊欄背景色 */
        section[data-testid="stSidebar"] {{
            background-color: #ffffff; 
            border-right: 1px solid #dee2e6;
        }}
        
        /* 按鈕樣式美化 */
        div.stButton > button:first-child {{
            background-color: #007bff;
            color: white;
            border-radius: 8px;
            border: none;
            padding: 8px 16px;
            font-weight: 600;
            transition: all 0.2s ease-in-out;
        }}
        div.stButton > button:first-child:hover {{
            background-color: #0056b3;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }}
        
        /* 讓 st.info 等訊息框更簡潔 */
        div[data-testid="stAlert"] {{
            border-radius: 8px;
        }}
        
        /* 調整欄位間距 */
        .st-emotion-cache-1r6r89q {{ /* 針對 st.columns 內的 div */
            padding: 0 0.5rem;
        }}
        
        /* 調整 st.expander 樣式 */
        div[data-testid="stExpander"] {{
            border-radius: 8px;
            border: 1px solid #ced4da;
            background-color: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
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
        # 注意: 這裡假設您的 secrets.toml 檔案中包含 [firestore] 區塊
        creds = st.secrets["firestore"]
        
        # 使用憑證初始化 Firestore 客戶端
        db = firestore.Client.from_service_account_info(creds)
        
        # st.success("成功連線到 Firestore!")
        return db
    except Exception as e:
        st.error(f"連線 Firestore 失敗，請檢查 .streamlit/secrets.toml 檔案: {e}")
        st.stop()
        return None

def fetch_data(db):
    """從 Firestore 獲取所有交易資料並轉換為 DataFrame"""
    collection_ref = db.collection("transactions")
    docs = collection_ref.stream()
    
    records = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        # 轉換 Firestore Timestamp 到 Python datetime.datetime
        if 'date' in data and hasattr(data['date'], 'to_datetime'):
             data['date'] = data['date'].to_datetime()
        elif 'date' in data and isinstance(data['date'], datetime.datetime):
             pass # 已經是 datetime.datetime
        elif 'date' in data and isinstance(data['date'], datetime.date):
             # 如果是 date 物件，轉換為 datetime.datetime
             data['date'] = datetime.datetime.combine(data['date'], datetime.datetime.min.time())
        
        records.append(data)
        
    if not records:
        return pd.DataFrame({
            'date': pd.Series([], dtype='datetime64[ns]'), 
            'category': [], 
            'amount': [], 
            'type': [], 
            'note': [], 
            'id': []
        })

    df = pd.DataFrame(records)
    
    # 確保 date 欄位是 datetime 類型
    if not pd.api.types.is_datetime64_any_dtype(df['date']):
        df['date'] = pd.to_datetime(df['date'])
        
    # 確保 amount 是數值類型
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    
    # 移除 amount 為 NaN 的行
    df.dropna(subset=['amount'], inplace=True)
    
    # 按照日期降序排序，最新的在最前面
    df.sort_values(by='date', ascending=False, inplace=True)
    
    return df


def add_transaction(db, date, category, amount, type_name, note=""):
    """新增交易紀錄到 Firestore"""
    # 儲存到 Firestore 的 date 欄位會自動轉為 Timestamp
    try:
        db.collection("transactions").add({
            "date": date,
            "category": category,
            "amount": amount,
            "type": type_name,
            "note": note,
            "created_at": firestore.SERVER_TIMESTAMP # 記錄伺服器時間
        })
        st.success("✅ 交易紀錄成功新增！")
    except Exception as e:
        st.error(f"❌ 新增交易紀錄失敗: {e}")


def delete_transaction(db, doc_id):
    """從 Firestore 刪除特定的交易紀錄"""
    try:
        db.collection("transactions").document(doc_id).delete()
        st.success(f"🗑️ 交易紀錄 (ID: {doc_id[:5]}...) 成功刪除！")
        # 刪除後需要重新執行 Streamlit 以更新列表
        st.rerun() 
    except Exception as e:
        st.error(f"❌ 刪除交易紀錄失敗 (ID: {doc_id[:5]}...): {e}")


# --- 2. Streamlit 介面主體 ---

def main():
    """應用程式的主要邏輯"""
    
    set_ui_styles()
    
    st.title("💸 簡約記帳本 (Firestore 版)")
    
    db = get_firestore_db()
    if db is None:
        st.stop() # 連線失敗則停止
    
    # 使用 Streamlit 的 state 來追蹤是否需要重新載入資料
    if 'data_refresh_needed' not in st.session_state:
        st.session_state['data_refresh_needed'] = 0

    # 每次需要重新載入時，Streamlit 會自動重新執行 main()，從 Firestore 獲取最新資料
    df = fetch_data(db)

    # --- 2.1. 側邊欄 - 新增交易 ---
    with st.sidebar:
        st.header("➕ 新增交易")
        
        # 交易類型選擇
        type_choice = st.radio("類型", ["支出", "收入"], horizontal=True, index=0)
        
        # 類別選擇 (依類型調整)
        if type_choice == "支出":
            categories = ["食物", "交通", "購物", "娛樂", "帳單", "住房", "其他"]
            default_category = "食物"
        else: # 收入
            categories = ["薪水", "投資", "兼職", "禮金", "其他"]
            default_category = "薪水"

        new_date = st.date_input("日期", datetime.date.today())
        new_category = st.selectbox("類別", categories, index=categories.index(default_category) if default_category in categories else 0)
        new_amount = st.number_input("金額 (NT$)", min_value=0.01, format="%.2f", step=10.0)
        new_note = st.text_area("備註 (選填)", max_chars=100, height=50)

        if st.button("💾 儲存紀錄"):
            if new_date and new_category and new_amount > 0:
                # Firestore 偏好儲存 datetime.datetime，即使我們從 date_input 拿到的是 datetime.date
                dt_to_store = datetime.datetime.combine(new_date, datetime.datetime.min.time())
                add_transaction(db, dt_to_store, new_category, new_amount, type_choice, new_note)
                st.session_state['data_refresh_needed'] += 1 # 觸發重新執行以更新介面
                st.rerun()
            else:
                st.error("請確保日期、類別已選，且金額大於零。")
                

    # --- 3. 數據展示區 ---
    
    st.header("📊 總覽與分析")
    
    # --- 3.1. 篩選和統計區 ---
    st.sidebar.subheader("📅 篩選範圍")
    
    # 預設為當月第一天到今天
    today = datetime.date.today()
    first_day_of_month = today.replace(day=1)

    # 讓使用者選擇日期範圍
    start_date = st.sidebar.date_input("開始日期", first_day_of_month, key="start_date_input")
    end_date = st.sidebar.date_input("結束日期", today, key="end_date_input")

    # === [修復: 處理 Streamlit 日期輸入可能為 None 的情況] ===
    # 即使設置了預設值，在 Streamlit 的重新執行生命週期中，日期輸入仍可能短暫返回 None，導致後續比較出錯。
    if start_date is None or end_date is None:
        # 顯示提示訊息並停止執行，直到日期元件正確初始化
        st.info("日期篩選元件正在初始化中，請稍候。")
        st.stop()
    # ========================================================

    # 確保結束日期不早於開始日期
    if start_date > end_date:
        st.sidebar.error("❌ 錯誤: 結束日期不能早於開始日期！")
        # 暫停執行以防止後續計算出錯
        st.stop() 

    # 篩選資料
    if not df.empty:
        # 將 DataFrame 的 date 欄位轉換為 datetime.date 進行比較
        # 注意: Firestore 儲存的是 datetime.datetime，但 date_input 返回的是 datetime.date。
        # 這裡需要統一類型。
        df_filtered = df[
            (df['date'].dt.date >= start_date) & 
            (df['date'].dt.date <= end_date)
        ]
    else:
        df_filtered = pd.DataFrame()
        
    st.markdown("---")


    # 3.2. 摘要卡片與支出分佈圖
    
    # 計算總和
    total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
    total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
    net_balance = total_income - total_expense

    # 顯示摘要卡片
    col1, col2, col3 = st.columns(3)
    
    col1.metric(
        label="💰 總收入 (NT$)", 
        value=f"{total_income:,.0f}", 
        delta_color="off"
    )
    col2.metric(
        label="💸 總支出 (NT$)", 
        value=f"{total_expense:,.0f}",
        delta_color="off"
    )
    # 餘額顯示顏色 (綠色為正，紅色為負)
    balance_delta = f"{net_balance:,.0f}"
    balance_color = "inverse" if net_balance < 0 else "normal"
    col3.metric(
        label="淨餘額 (NT$)", 
        value=balance_delta,
        delta=f"當月結餘", 
        delta_color=balance_color # Streamlit 的顏色控制
    )

    st.markdown("---")
    
    # 支出分佈圓餅圖 (只針對支出類型)
    expense_data = df_filtered[df_filtered['type'] == '支出'].groupby('category')['amount'].sum().reset_index()
    
    if total_expense > 0 and not expense_data.empty:
        st.header("支出類別分佈圖")

        # 1. 基礎圓餅圖設定
        base = alt.Chart(expense_data).encode(
            # 設定顏色編碼和提示框 (Tooltip)
            color=alt.Color("category", title="類別"),
            # 確保排序與圖例一致
            order=alt.Order("amount", sort="descending") 
        )

        # 2. 圓弧圖 (Pie Chart)
        pie = base.mark_arc(outerRadius=120, innerRadius=50).encode(
            theta=alt.Theta("amount", stack=True), # 根據金額大小決定角度
            tooltip=[
                alt.Tooltip("category", title="類別"),
                alt.Tooltip("amount", format=',.0f', title="總支出 (NT$)"),
                # 計算並顯示百分比
                alt.Tooltip("amount", title="比例", format=".1%", stack="normalize") 
            ]
        )

        # 3. 中間文字標籤 (顯示總支出)
        text = base.mark_text(
            align='center', 
            baseline='middle', 
            dx=0, 
            dy=0,
            color="#495057",
            fontWeight="bold",
        ).encode(
            text=alt.value(f"總計\n{total_expense:,.0f}"), # 這裡顯示計算出的總支出
            order=alt.Order("amount", sort="descending")
        )

        # 4. 組合圖表並居中顯示
        # 結合圓餅圖、圖例 (預設在右側)
        chart = alt.layer(pie, text).interactive()
        
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
    for index, row in display_df.iterrows():
        # 設定欄位比例: 日期(1), 類別(1), 金額(1), 備註(3), 刪除按鈕(1)
        col_date, col_cat, col_amount, col_note, col_btn = st.columns([1, 1, 1, 3, 1])
        
        # 顯示交易細節
        date_str = row['日期'].strftime('%Y-%m-%d')
        # 根據類型設定金額顏色
        amount_color = "red" if row['類型'] == '支出' else "green"
        
        col_date.write(f"**{date_str}**")
        col_cat.markdown(f"**{row['類別']}**")
        col_amount.markdown(f"<span style='color: {amount_color}; font-weight: bold;'>{row['金額']:,.0f}</span>", unsafe_allow_html=True)
        col_note.markdown(f"<span style='color: #6c757d; font-size: 0.9em;'>{row['備註']}</span>", unsafe_allow_html=True)
        
        # 刪除按鈕
        if col_btn.button("🗑️ 刪除", key=f"delete_btn_{row['文件ID']}"):
            delete_transaction(db, row['文件ID'])
            # delete_transaction 內部會呼叫 st.rerun()

    if df_filtered.empty:
        st.info("在選定的日期範圍內沒有交易紀錄。")
        
    st.markdown("---")

# 確保程式從 main 函數開始執行
if __name__ == '__main__':
    main()


