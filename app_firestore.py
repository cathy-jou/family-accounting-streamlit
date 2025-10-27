import streamlit as st
import pandas as pd
import datetime
import altair as alt
from google.cloud import firestore
import uuid # 導入 uuid 庫用於生成唯一 ID
import os # 導入 os 庫用於環境變數檢查
from streamlit_extras.switch_page_button import switch_page # 導入分頁切換功能

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

            # Firestore Timestamp 對象會被自動處理，這裡不需要複雜的手動轉換
            data.append(doc_data)

        if not data:
            return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note'])

        df = pd.DataFrame(data)

        # 轉換數據類型，pd.to_datetime 可以處理 Firestore Timestamp
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

# --- 3. 資料處理與分析函數 ---

@st.cache_data
def convert_df_to_csv(df: pd.DataFrame):
    """
    將 DataFrame 轉換為 CSV 格式 (utf-8 編碼)，供下載使用。
    修正 KeyErorr: 確保選取的欄位與重命名後的欄位名稱一致。
    """
    if df.empty:
        return pd.DataFrame().to_csv(index=False).encode('utf-8')

    # 原始欄位名 (假設為英文小寫) 與目標中文欄位名的映射
    column_mapping = {
        'date': '日期',
        'type': '類型',
        'category': '類別',
        'amount': '金額',
        'note': '備註',
        'id': '文件ID',
        'timestamp': '儲存時間'
    }

    # 確保只有在原始 df 中存在的欄位才進行重命名
    cols_to_rename = {k: v for k, v in column_mapping.items() if k in df.columns}

    # 進行重命名
    df_renamed = df.rename(columns=cols_to_rename)

    # 選取目標欄位
    # 必須選取重命名後的中文名稱
    target_columns = ['日期', '類型', '類別', '金額', '備註', '文件ID', '儲存時間']

    # 過濾出實際存在的欄位，以防資料源不完整
    existing_columns = [col for col in target_columns if col in df_renamed.columns]

    # 確保至少有部分欄位存在，避免 DataFrame 選取錯誤
    if not existing_columns:
        st.warning("無法匯出 CSV：DataFrame 中缺少所有預期的欄位。")
        return pd.DataFrame().to_csv(index=False).encode('utf-8')

    # 使用實際存在的欄位進行選取，修正 KeyError
    df_export = df_renamed[existing_columns]

    # 格式化日期和金額以利閱讀
    if '日期' in df_export.columns:
        df_export['日期'] = df_export['日期'].apply(lambda x: x.strftime('%Y-%m-%d') if isinstance(x, (datetime.date, datetime.datetime)) else str(x))
    if '金額' in df_export.columns:
        # 確保金額是數字類型以便格式化
        df_export['金額'] = pd.to_numeric(df_export['金額'], errors='coerce').fillna(0).astype(int)

    return df_export.to_csv(index=False).encode('utf-8')

def calculate_summary(df):
    """計算收入/支出總額和總收支"""
    if df.empty:
        return 0, 0, 0

    # 確保 'amount' 是數字類型
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)

    income = df[df['type'] == '收入']['amount'].sum()
    expense = df[df['type'] == '支出']['amount'].sum()
    net = income - expense
    return income, expense, net

def get_category_breakdown(df, type_filter='支出'):
    """計算各類別的金額佔比"""
    if df.empty:
        return pd.DataFrame()

    df_filtered = df[df['type'] == type_filter].copy()
    if df_filtered.empty:
        return pd.DataFrame()

    # 確保 'amount' 是數字類型
    df_filtered['amount'] = pd.to_numeric(df_filtered['amount'], errors='coerce').fillna(0)

    breakdown = df_filtered.groupby('category')['amount'].sum().reset_index()
    breakdown.columns = ['類別', '金額']
    # 計算佔比
    total = breakdown['金額'].sum()
    if total > 0:
        breakdown['佔比'] = breakdown['金額'] / total
    else:
        breakdown['佔比'] = 0

    return breakdown.sort_values(by='金額', ascending=False)

def create_altair_chart(df_breakdown, chart_title):
    """創建 Altair 圓餅圖/環形圖"""
    if df_breakdown.empty:
        return None

    # 顏色配置
    color_scale = alt.Scale(range=alt.Scheme('category10').domain)

    chart = alt.Chart(df_breakdown).mark_arc(outerRadius=120, innerRadius=80).encode(
        theta=alt.Theta("金額", stack=True),
        color=alt.Color("類別", scale=color_scale),
        order=alt.Order("佔比", sort="descending"),
        tooltip=['類別', alt.Tooltip('金額', format=',.0f'), alt.Tooltip('佔比', format='.1%')]
    ).properties(
        title=chart_title
    ).interactive() # 允許互動縮放

    # 文字標籤
    text = alt.Chart(df_breakdown).mark_text(radius=140).encode(
        theta=alt.Theta("金額", stack=True),
        text=alt.Text("佔比", format=".1%"),
        order=alt.Order("佔比", sort="descending"),
        color=alt.value("black")
    )

    return (chart).configure_title(
        fontSize=18,
        anchor='start',
        color='#495057'
    )


# --- 4. 頁面函數 ---

def page_dashboard(db, df_records, current_balance):
    """儀表板：顯示總覽和圖表"""
    st.title(PAGES['Dashboard'])

    # 總餘額顯示
    st.markdown("## 💰 總資產概覽")

    # 調整佈局，讓餘額更顯眼
    col_bal, col_space = st.columns([1, 2])
    with col_bal:
        st.metric(
            label="總餘額",
            value=f"NT$ {current_balance:,.0f}",
            delta=None
        )

    st.markdown("---")

    # 交易總覽
    st.markdown("## 📊 期間收支總結")

    # 計算總結 (這裡我們使用所有紀錄)
    income_total, expense_total, net_total = calculate_summary(df_records)

    col_inc, col_exp, col_net = st.columns(3)

    with col_inc:
        st.metric("總收入", f"NT$ {income_total:,.0f}", delta_color="normal")

    with col_exp:
        # 將支出顯示為負數變化
        st.metric("總支出", f"NT$ {expense_total:,.0f}", delta=-expense_total, delta_color="inverse")

    with col_net:
        st.metric("淨收支", f"NT$ {net_total:,.0f}", delta=net_total, delta_color="normal")

    st.markdown("---")

    # 類別分析圖表
    st.markdown("## 📈 支出類別分析")

    # 獲取支出分類數據
    df_expense_breakdown = get_category_breakdown(df_records, type_filter='支出')

    if not df_expense_breakdown.empty:
        # 建立圖表
        chart_title = "各支出類別金額佔比"
        expense_chart = create_altair_chart(df_expense_breakdown, chart_title)

        st.altair_chart(expense_chart, use_container_width=True)

        # 顯示詳細表格
        st.markdown("#### 支出細項")
        # 隱藏佔比欄位，只顯示類別和金額
        st.dataframe(
            df_expense_breakdown[['類別', '金額']].style.format({'金額': 'NT$ {:,d}'}),
            hide_index=True,
            use_container_width=True
        )

    else:
        st.info("暫無支出紀錄可供分析。")


def page_record(db, current_balance):
    """新增紀錄頁面"""
    st.title(PAGES['Record'])
    st.markdown(f"**當前餘額:** NT$ **{current_balance:,.0f}**")

    st.markdown("---")

    st.markdown("## 📝 填寫交易細節")

    with st.form("new_record_form", clear_on_submit=True):
        # 交易日期 (預設今天)
        date = st.date_input("日期", datetime.date.today(), max_value=datetime.date.today())

        # 交易類型 (收入/支出)
        type_selected = st.radio(
            "類型",
            options=list(CATEGORIES.keys()),
            horizontal=True,
            help="選擇此筆交易是收入還是支出"
        )

        # 類別 (根據類型動態更新)
        category_options = CATEGORIES.get(type_selected, [])
        category_selected = st.selectbox(
            "類別",
            options=category_options,
            key=f"category_select_{type_selected}", # 用類型作為 key，確保切換時選單重置
            help="選擇此筆交易的具體分類"
        )

        # 金額
        amount = st.number_input(
            "金額 (NT$)",
            min_value=1,
            value=100,
            step=1,
            format="%d",
            help="請輸入交易金額，只能是正整數"
        )

        # 備註
        note = st.text_area(
            "備註 (可選)",
            placeholder="例如: 週末採購、房租繳納...",
            height=80
        )

        submitted = st.form_submit_button("💾 儲存紀錄")

        if submitted:
            # 基本輸入驗證
            if not category_selected:
                st.error("請選擇一個類別。")
                return

            record_data = {
                'date': date,
                'type': type_selected,
                'category': category_selected,
                'amount': amount,
                'note': note.strip()
            }

            add_record(db, record_data, current_balance)


def page_records_view(db, df_records, current_balance):
    """所有交易紀錄頁面：顯示列表、篩選和下載"""
    st.title(PAGES['Records_View'])

    st.markdown(f"**當前餘額:** NT$ **{current_balance:,.0f}**")
    st.markdown("---")

    st.markdown("## 🔍 紀錄篩選與管理")

    # 篩選欄位
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])

    # 類型篩選
    type_filter = col1.selectbox("過濾類型", ['所有類型'] + list(CATEGORIES.keys()))

    # 類別篩選
    category_options = []
    if type_filter == '所有類型':
        for categories in CATEGORIES.values():
            category_options.extend(categories)
    else:
        category_options = CATEGORIES.get(type_filter, [])

    category_filter = col2.selectbox("過濾類別", ['所有類別'] + category_options)

    # 日期範圍篩選
    # 尋找最早和最晚日期，如果 df_records 為空，則使用今天
    min_date = df_records['date'].min() if not df_records.empty else datetime.date.today()
    max_date = df_records['date'].max() if not df_records.empty else datetime.date.today()

    date_range = col3.date_input(
        "日期範圍",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=datetime.date.today()
    )

    # 應用篩選
    df_filtered = df_records.copy()

    if type_filter != '所有類型':
        df_filtered = df_filtered[df_filtered['type'] == type_filter]

    if category_filter != '所有類別':
        df_filtered = df_filtered[df_filtered['category'] == category_filter]

    if len(date_range) == 2:
        start_date, end_date = date_range
        # 確保 start_date <= end_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        df_filtered = df_filtered[(df_filtered['date'] >= start_date) & (df_filtered['date'] <= end_date)]

    # 顯示總紀錄數
    col4.markdown(f"**篩選結果:** 共 **{len(df_filtered)}** 筆紀錄")

    # 下載按鈕
    csv_data = convert_df_to_csv(df_filtered)
    col4.download_button(
        label="📥 下載 CSV",
        data=csv_data,
        file_name="family_accounting_records.csv",
        mime="text/csv",
        help="下載當前篩選結果為 CSV 檔案"
    )

    st.markdown("---")

    # 交易列表顯示
    st.markdown("## 📜 交易列表")

    if df_filtered.empty:
        st.info("沒有符合條件的交易紀錄。")
        return

    # 列表標頭
    with st.container():
        # 修正: 調整 st.columns 比例，使備註欄位有足夠的空間 (50%)
        col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([12, 10, 10, 7, 50, 11])
        col_date.markdown("**日期**", help="交易發生日期")
        col_cat.markdown("**類別**")
        col_amount.markdown("**金額**")
        col_type.markdown("**類型**")
        col_note.markdown("**備註**")
        col_btn_action.markdown("**操作**")

    st.markdown("---") # 分隔線

    # 顯示每一筆紀錄
    for index, row in df_filtered.iterrows():
        try:
            # 從 DataFrame 提取必要的欄位 (使用英文 key)
            record_id = row['id']
            record_date = row['date']
            record_type = row['type']
            record_category = row['category']
            record_amount = row['amount']
            record_note = row['note']

            # 從完整的紀錄中獲取刪除所需的資訊 (這是為了確保刪除時資訊的完整性)
            record_details_for_delete = df_records[df_records['id'] == record_id].iloc[0].to_dict()
        except IndexError:
            st.error(f"找不到文件ID為 {record_id} 的原始紀錄，可能已被刪除。")
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
                delete_record(
                    db=db,
                    record_data=record_details_for_delete, # 使用從完整紀錄中獲取的資料
                    current_balance=current_balance
                )

        st.markdown(f"<hr style='margin-top: 0.5rem; margin-bottom: 0.5rem; border: 0; border-top: 1px dashed #e9ecef;'>", unsafe_allow_html=True)


def page_balance_management(db, current_balance):
    """餘額調整頁面：手動設定餘額"""
    st.title(PAGES['Balance_Management'])

    st.markdown(f"**當前餘額:** NT$ **{current_balance:,.0f}**")
    st.markdown("---")

    st.markdown("## ⚙️ 手動調整總餘額")
    st.warning("請注意：手動調整餘額將覆蓋基於所有交易紀錄計算的餘額。僅在需要修正初始值或進行一次性調整時使用。")

    with st.form("set_balance_form"):
        new_balance = st.number_input(
            "設定新的總餘額 (NT$)",
            value=current_balance,
            step=1000,
            format="%d",
            help="輸入您希望設定的總餘額數值"
        )

        submitted = st.form_submit_button("💰 確認更新餘額")

        if submitted:
            set_current_balance(db, new_balance)
            st.toast("總餘額已手動更新！", icon="✅")
            st.rerun()

# --- 5. 主應用程式邏輯 ---

# 修正點 3: 移除 Streamlit Extras 的導入和頁面字典
# 定義主函數
def app():
    """主應用程式入口點，管理狀態和頁面"""
    set_ui_styles()

    # 初始化 Firestore 和用戶 ID
    db = init_firestore()
    if db is None:
        st.stop()

    # 初始化用戶 ID (使用 UUID 模擬匿名用戶，因為這裡沒有 Firebase Auth)
    if 'user_id' not in st.session_state:
        # 在實際環境中，這裡應該是從 Firebase Auth 獲取的 uid
        st.session_state['user_id'] = str(uuid.uuid4())

    # 獲取資料
    df_records = get_records(db)
    current_balance = get_current_balance(db)

    # 側邊欄
    with st.sidebar:
        st.image("https://placehold.co/120x40/007bff/ffffff?text=Family+Account", use_column_width=True)
        st.markdown("## 導航選單")

        # 使用 Streamlit 內建的 radio 作為頁面導航
        page_options = {
            "🏠 儀表板": "Dashboard",
            "✍️ 新增紀錄": "Record",
            "📜 所有交易紀錄": "Records_View",
            "💰 餘額調整": "Balance_Management"
        }
        selected_page_title = st.radio("選擇頁面", list(page_options.keys()))
        current_page_key = page_options[selected_page_title]

    # 根據選擇顯示頁面內容 (使用 if/elif)
    if current_page_key == 'Dashboard':
        page_dashboard(db, df_records, current_balance)
    elif current_page_key == 'Record':
        page_record(db, current_balance)
    elif current_page_key == 'Records_View':
        page_records_view(db, df_records, current_balance)
    elif current_page_key == 'Balance_Management':
        page_balance_management(db, current_balance)
    else:
        st.error("頁面未找到。")


if __name__ == '__main__':
    # Streamlit 頁面配置
    st.set_page_config(
        page_title="家庭記帳應用程式",
        page_icon="🏠",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 確保在應用程式啟動時執行 app()
    app()


