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
            margin-top: 1.5rem;
            margin-bottom: 1rem;
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
        /* 側邊欄保持白色 */
        section[data-testid="stSidebar"] {{
            background-color: #ffffff; 
        }}
        
        /* 讓輸入框和按鈕等元件看起來更現代 */
        div.stButton > button:first-child {{
            border-radius: 8px;
            border: 1px solid #007bff;
            background-color: #007bff;
            color: white;
            padding: 8px 16px;
            transition: all 0.3s ease;
        }}
        div.stButton > button:first-child:hover {{
            background-color: #0056b3;
            border-color: #0056b3;
        }}
        /* 欄位微調 */
        .stTextInput, .stNumberInput, .stSelectbox {{
            padding-bottom: 0.5rem;
        }}

        /* 調整分頁標籤樣式 */
        .stTabs [data-testid="stBlock"] {{
            gap: 1.5rem;
        }}
        .stTabs button {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #495057;
        }}
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)


# --- 1. Firestore 連線與操作 ---
# 更改 Collection 名稱以區分交易和帳戶
COLLECTION_NAME_TRANSACTIONS = "transactions"
COLLECTION_NAME_ACCOUNTS = "accounts" 

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
        
        # st.success("成功連線到 Firestore!")
        return db
    except Exception as e:
        st.error(f"連線 Firestore 失敗，請檢查 .streamlit/secrets.toml 檔案: {e}")
        return None

def get_transaction_collection(db):
    """取得交易資料的 Firestore Collection Reference。"""
    return db.collection(COLLECTION_NAME_TRANSACTIONS)

def get_account_collection(db):
    """取得帳戶資料的 Firestore Collection Reference。"""
    return db.collection(COLLECTION_NAME_ACCOUNTS)


# @st.cache_data 確保資料獲取後會在緩存中保持 5 秒，減少 DB 存取次數
@st.cache_data(ttl=5) 
def get_data(db) -> pd.DataFrame:
    """從 Firestore 獲取所有交易資料並轉換為 DataFrame。"""
    transactions = []
    try:
        transactions_ref = get_transaction_collection(db)
        docs = transactions_ref.stream()
        for doc in docs:
            transaction_data = doc.to_dict()
            transaction_data['id'] = doc.id
            
            # 確保 'date' 欄位轉換為 datetime.datetime 類型
            if 'date' in transaction_data:
                # 處理 Firestore Timestamp 轉換為 Python datetime
                if hasattr(transaction_data['date'], 'to_datetime'):
                    transaction_data['date'] = transaction_data['date'].to_datetime()
                # 如果是 datetime.date，也轉成 datetime.datetime
                elif isinstance(transaction_data['date'], datetime.date) and not isinstance(transaction_data['date'], datetime.datetime):
                    transaction_data['date'] = datetime.datetime.combine(transaction_data['date'], datetime.time())
            
            transactions.append(transaction_data)
        
        df = pd.DataFrame(transactions)
        
        if not df.empty:
            # 確保 'amount' 是數字類型，如果無法轉換則設為 NaN
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            df.dropna(subset=['amount'], inplace=True) # 刪除無效金額的行
            
            # 確保 'date' 是日期時間類型
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df.dropna(subset=['date'], inplace=True) # 刪除無效日期的行

            # 確保 'type' 是分類類型
            df['type'] = df['type'].astype('category')
            # 排序：最新紀錄在前
            df = df.sort_values(by='date', ascending=False).reset_index(drop=True)
            
        return df
    except Exception as e:
        st.error(f"載入交易資料失敗: {e}")
        return pd.DataFrame([])

def add_transaction(db, transaction_data: dict):
    """向 Firestore 添加一筆新的交易紀錄。"""
    try:
        transactions_ref = get_transaction_collection(db)
        transactions_ref.add(transaction_data)
        # 清除緩存以強制重新載入數據
        get_data.clear()
        # 清除帳戶緩存 
        get_accounts.clear() 
        st.success("🎉 交易記錄成功新增！")
        st.rerun() # 重新運行以更新介面
    except Exception as e:
        st.error(f"新增交易失敗: {e}")

def delete_transaction(db, doc_id: str):
    """從 Firestore 刪除指定 ID 的交易紀錄。"""
    try:
        transactions_ref = get_transaction_collection(db)
        transactions_ref.document(doc_id).delete()
        # 清除緩存以強制重新載入數據
        get_data.clear()
        get_accounts.clear()
        st.success("🗑️ 交易記錄已刪除！")
        st.rerun() # 重新運行以更新介面
    except Exception as e:
        st.error(f"刪除交易失敗: {e}")

# --- 新增帳戶相關的 Firestore 操作 ---

@st.cache_data(ttl=5) # 緩存，5 秒更新一次
def get_accounts(db) -> pd.DataFrame:
    """從 Firestore 獲取所有帳戶資料。"""
    accounts = []
    try:
        accounts_ref = get_account_collection(db)
        docs = accounts_ref.stream()
        for doc in docs:
            account_data = doc.to_dict()
            account_data['id'] = doc.id
            accounts.append(account_data)
        
        df_accounts = pd.DataFrame(accounts)
        
        if not df_accounts.empty:
            # 確保 'balance' 是浮點數
            df_accounts['balance'] = pd.to_numeric(df_accounts['balance'], errors='coerce')
            df_accounts.dropna(subset=['balance'], inplace=True)

            # 確保 'created_at' 是 datetime
            df_accounts['created_at'] = pd.to_datetime(df_accounts['created_at'], errors='coerce')
            df_accounts.dropna(subset=['created_at'], inplace=True)

            
        return df_accounts
    except Exception as e:
        st.error(f"載入帳戶資料失敗: {e}")
        return pd.DataFrame([])

def add_new_account(db, bank_name: str, initial_balance: float):
    """向 Firestore 添加一個新的銀行帳戶。"""
    try:
        accounts_ref = get_account_collection(db)
        accounts_ref.add({
            "bank_name": bank_name,
            "balance": initial_balance,
            "created_at": datetime.datetime.now(),
        })
        # 清除緩存以強制更新
        get_accounts.clear()
        get_data.clear()
        st.success(f"✅ 成功新增帳戶: **{bank_name}**，初始餘額: **${initial_balance:,.0f}**")
        st.rerun()
    except Exception as e:
        st.error(f"新增帳戶失敗: {e}")

# --- 2. Streamlit 應用程式主體 ---

def app():
    # 0. UI 設定
    st.set_page_config(layout="wide", page_title="簡約個人記帳本")
    set_ui_styles()
    
    st.title("🌟 簡約個人記帳本")

    # 1. DB 初始化
    db = get_firestore_db()
    if db is None:
        return

    # 提前獲取數據
    df_transactions = get_data(db)
    df_accounts = get_accounts(db)
    
    # 獲取帳戶名稱列表，用於交易表單
    account_options = ["現金 Cash", "其他 Other"] # 預設選項
    if not df_accounts.empty:
        account_options.extend(df_accounts['bank_name'].tolist())

    # --- 2. 應用程式主介面 (使用 Tab) ---
    tab_transactions, tab_accounts = st.tabs(["📊 記帳與報表", "🏦 資產管理"])

    # ======================================================================
    # TAB 1: 記帳與報表 (原有功能)
    # ======================================================================
    with tab_transactions:
        
        # 2.1. 新增交易表單
        st.header("📝 記錄新交易")
        
        with st.form("transaction_form", clear_on_submit=True):
            col_date, col_type = st.columns(2)
            col_cat, col_amount = st.columns(2)
            col_acc, col_note = st.columns(2)
            
            # 交易日期
            date_input = col_date.date_input("日期", datetime.date.today(), key="tx_date")
            
            # 交易類型
            type_options = ["支出 Expense", "收入 Income"]
            type_input = col_type.selectbox("類型", options=type_options, index=0, key="tx_type")
            
            # 類別選項 (可根據類型動態調整)
            if type_input == "支出 Expense":
                categories = ["餐飲", "交通", "購物", "娛樂", "住房", "醫療", "教育", "投資", "其他"]
                default_index = categories.index("餐飲") if "餐飲" in categories else 0
            else:
                categories = ["薪資", "獎金", "投資收益", "禮金", "其他"]
                default_index = categories.index("薪資") if "薪資" in categories else 0
                
            category_input = col_cat.selectbox("類別", options=categories, index=default_index, key="tx_category")
            
            # 金額
            amount_input = col_amount.number_input("金額 ($)", min_value=0.0, value=0.0, step=100.0, format="%.0f", key="tx_amount")
            
            # 交易帳戶 (NEW)
            account_name = col_acc.selectbox("交易帳戶", options=account_options, index=0, key="tx_account_name")
            
            # 備註
            note_input = col_note.text_input("備註 (可選)", key="tx_note")

            submitted = st.form_submit_button("💾 儲存交易")
            
            if submitted:
                if amount_input > 0:
                    transaction_data = {
                        "date": datetime.datetime.combine(date_input, datetime.time()),
                        "type": type_input,
                        "category": category_input,
                        "amount": amount_input,
                        "account": account_name, # 儲存帳戶名稱
                        "note": note_input,
                        "timestamp": datetime.datetime.now()
                    }
                    add_transaction(db, transaction_data)
                else:
                    st.error("請輸入有效金額。")

        st.markdown("---")

        # 3. 數據總覽區
        st.header("數據總覽")

        if df_transactions.empty:
            st.info("目前沒有任何交易記錄。")
            # 即使 dataframe 是空的，也要確保 start_date 和 end_date 不為 None (上一個修復)
            # 預設為本月第一天到今天
            default_start = datetime.date.today().replace(day=1)
            default_end = datetime.date.today()
            # 這裡我們不需要 date_input 的結果，因為沒有資料。但需要確保後續代碼的健壯性。
            with st.expander("篩選和統計範圍", expanded=True):
                col_start, col_end = st.columns(2)
                col_start.date_input("起始日期", default_start, key="filter_start_date_empty")
                col_end.date_input("結束日期", default_end, key="filter_end_date_empty")

            return

        # 3.1. 過濾器
        with st.expander("篩選和統計範圍", expanded=True):
            col_start, col_end = st.columns(2)
            
            # 預設為本月第一天到今天
            default_start = datetime.date.today().replace(day=1)
            default_end = datetime.date.today()
            
            start_date = col_start.date_input("起始日期", default_start, key="filter_start_date")
            end_date = col_end.date_input("結束日期", default_end, key="filter_end_date")
            
            # === [上一個修復: 處理 Streamlit 日期輸入可能為 None 的情況] ===
            if start_date is None or end_date is None:
                st.info("日期篩選元件正在初始化中，請稍候。")
                return
            # ===============================================================
            
            # 確保起始日期不晚於結束日期
            if start_date > end_date:
                st.error("起始日期不能晚於結束日期！")
                return

        # 過濾數據
        # df_transactions['date'].dt.date 確保我們是用日期物件來比較
        df_filtered = df_transactions[
            (df_transactions['date'].dt.date >= start_date) & 
            (df_transactions['date'].dt.date <= end_date)
        ]
        
        # 3.2. 摘要與圖表
        total_income = df_filtered[df_filtered['type'] == '收入 Income']['amount'].sum()
        total_expense = df_filtered[df_filtered['type'] == '支出 Expense']['amount'].sum()
        net_balance = total_income - total_expense
        
        col_income, col_expense, col_net = st.columns(3)

        col_income.metric("總收入", f"${total_income:,.0f}", delta_color="off")
        col_expense.metric("總支出", f"${total_expense:,.0f}", delta_color="off")
        
        net_delta = f"本期淨額"
        # 根據淨額設定顏色
        net_color = "normal" if net_balance >= 0 else "inverse" 
        col_net.metric(net_delta, f"${net_balance:,.0f}", delta=f"{'盈餘' if net_balance >= 0 else '赤字'}", delta_color=net_color)

        # 支出分佈圓餅圖 (只針對支出)
        st.markdown("#### 支出類別分佈圖")
        
        # 聚合支出數據
        expense_data_raw = df_filtered[df_filtered['type'] == '支出 Expense']
        expense_data = expense_data_raw.groupby('category')['amount'].sum().reset_index()
        
        # === FIX: 增加嚴格的數據檢查，以避免 Altair ValueError ===
        if total_expense > 0 and not expense_data.empty:
            
            # 清理：確保 amount 是正數且非 NaN
            expense_data.dropna(subset=['amount'], inplace=True)
            expense_data = expense_data[expense_data['amount'] > 0]
            
            if not expense_data.empty:
                
                # 1. 基礎圓餅圖 (用於計算角度/比例)
                base = alt.Chart(expense_data).encode(
                    theta=alt.Theta("amount", stack=True)
                )

                # 2. 圓弧圖層
                pie = base.mark_arc(outerRadius=120, innerRadius=50).encode(
                    color=alt.Color("category", title="類別"), # 顏色代表類別
                    order=alt.Order("amount", sort="descending"), # 依金額排序
                    tooltip=["category", alt.Tooltip("amount", format="$,.0f", title="總支出"), alt.Tooltip("amount", format=".1%", title="比例", aggregate="sum")]
                )

                # 3. 文字標籤圖層 (顯示比例)
                text = base.mark_text(radius=140).encode(
                    text=alt.Text("amount", format=".1%"), # 顯示百分比
                    order=alt.Order("amount", sort="descending"),
                    color=alt.value("black") # 讓文字為黑色
                )
                
                # 4. 組合圖表並居中顯示
                chart = alt.layer(pie, text).interactive()
                
                # 為了讓圓餅圖在 Streamlit 內置的容器中能保持正確的寬高比，
                # 這裡設定較為固定的寬高，讓圓形居中顯示。
                st.altair_chart(chart, use_container_width=True)
            
            else:
                 st.info("選定範圍內無有效的支出紀錄（金額必須大於零）。")

        else:
            st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

        st.markdown("---")

        # 3.3. 交易紀錄區 (新增刪除按鈕)
        st.header("完整交易紀錄")
        
        # 準備用於顯示和刪除的 DataFrame
        display_df = df_filtered[['date', 'category', 'amount', 'type', 'account', 'note', 'id']].copy()
        display_df.rename(columns={
            'date': '日期', 
            'category': '類別', 
            'amount': '金額', 
            'type': '類型', 
            'account': '帳戶', # 新增帳戶欄位
            'note': '備註',
            'id': '文件ID' # 保留 ID 用於刪除
        }, inplace=True)
        
        # 遍歷每一筆紀錄，並為其添加一個刪除按鈕
        st.markdown("---")
        if not display_df.empty:
            for index, row in display_df.iterrows():
                # 調整欄位寬度以容納新的帳戶欄位
                col_date, col_cat, col_amount, col_acc, col_note, col_btn = st.columns([1, 1, 1, 1, 3, 0.8])
                
                # 顯示交易細節
                col_date.write(row['日期'].strftime('%Y/%m/%d'))
                col_cat.write(row['類別'])
                
                # 根據類型設定顏色
                amount_color = "red" if row['類型'] == '支出 Expense' else "green"
                col_amount.markdown(f"<span style='color:{amount_color}; font-weight: 600;'>{row['金額']:,.0f}</span>", unsafe_allow_html=True)
                
                col_acc.write(row['帳戶']) # 顯示帳戶
                col_note.caption(row['備註'])
                
                # 刪除按鈕
                if col_btn.button("刪除", key=f"del_{row['文件ID']}", type="secondary"):
                    delete_transaction(db, row['文件ID'])
        else:
            st.info("在選定的日期範圍內沒有交易紀錄。")
        
    # ======================================================================
    # TAB 2: 資產管理 (新增功能)
    # ======================================================================
    with tab_accounts:
        st.header("🏦 帳戶與資產總覽")
        
        # 2.1. 獲取並顯示帳戶總覽
        
        if not df_accounts.empty:
            total_balance = df_accounts['balance'].sum()
            
            # 使用 metrics 顯示總資產
            st.metric(
                label="總資產淨值 (Total Net Worth)", 
                value=f"${total_balance:,.0f}", 
                delta_color="off" # 避免顯示不必要的箭頭
            )
            
            st.markdown("---")
            st.subheader("現有資產帳戶列表")
            
            # 顯示帳戶表格
            # 只顯示關鍵欄位，並格式化金額
            display_accounts_df = df_accounts[['bank_name', 'balance', 'created_at', 'id']].copy()
            display_accounts_df.columns = ['銀行/帳戶名稱', '當前餘額', '建立日期', '文件ID']
            
            st.dataframe(
                display_accounts_df[['銀行/帳戶名稱', '當前餘額', '建立日期']], # 不顯示ID
                column_config={
                    "當前餘額": st.column_config.NumberColumn(
                        "當前餘額",
                        format="$%,.0f",
                    ),
                    "建立日期": st.column_config.DatetimeColumn(
                        "建立日期",
                        format="YYYY/MM/DD hh:mm"
                    )
                },
                hide_index=True,
                use_container_width=True
            )

        else:
            st.info("目前沒有任何帳戶紀錄，請新增您的銀行/資產帳戶。")
            
        st.markdown("---")
        
        # 2.2. 新增帳戶表單
        st.subheader("➕ 新增資產帳戶")
        with st.form("new_account_form", clear_on_submit=True):
            col_bank, col_balance = st.columns(2)
            
            bank_name = col_bank.text_input("銀行/帳戶名稱 (例如: 薪轉戶、投資帳戶)", key="input_bank_name")
            initial_balance = col_balance.number_input(
                "初始/當前餘額 ($)", 
                min_value=0.0, 
                value=0.0, 
                step=100.0, 
                format="%.0f",
                key="input_initial_balance"
            )
            
            submitted = st.form_submit_button("💾 新增帳戶")
            
            if submitted:
                if bank_name and initial_balance >= 0:
                    add_new_account(db, bank_name, initial_balance)
                else:
                    st.error("請填寫有效的銀行/帳戶名稱和餘額。")


if __name__ == '__main__':
    app()



