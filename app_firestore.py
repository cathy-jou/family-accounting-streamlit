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
# 修正點 1: 確保所有頁面名稱正確
PAGES = {
    "Dashboard": "🏠 儀表板",
    "Record": "✍️ 新增紀錄",
    "Records_View": "📜 所有交易紀錄",
    "Balance_Management": "💰 餘額調整"
}

# 定義交易類別
CATEGORIES = {
    '收入': ['薪資', '投資收益', '禮金', '其他收入'],
    '支出': ['餐飲', '交通', '購物', '娛樂', '房租/貸款', '教育', '醫療', '其他支出']
}

# --- 1. Streamlit 介面設定 ---
def set_ui_styles():
    """注入客製化 CSS，設定字體、簡約背景色和排版"""
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
            font-size: 1.4rem;
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
        
        /* 隱藏 Streamlit 預設樣式 (選單, footer) */
        #MainMenu, footer {{
            visibility: hidden;
        }}
        
        /* 側邊欄樣式 */
        .stSidebar {{
            background-color: #ffffff; /* 側邊欄使用白色背景 */
            padding-top: 2rem;
        }}
        
        /* 交易紀錄列表的樣式調整，增加行間距和視覺區隔 */
        .stContainer {{
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 0.5rem;
            background-color: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        
        /* 按鈕樣式美化 */
        .stButton>button {{
            width: 100%;
            border-radius: 6px;
            font-weight: 600;
            transition: all 0.2s;
        }}
        
        /* 刪除按鈕特別樣式 */
        .stButton button[kind="secondary"] {{
            color: #dc3545;
            border-color: #dc3545;
        }}
        .stButton button[kind="secondary"]:hover {{
            background-color: #dc3545;
            color: white;
        }}
        
        /* 欄位對齊和內邊距調整 */
        [data-testid="stColumn"] div {{
            word-wrap: break-word; /* 允許長文字換行 */
            overflow-wrap: break-word;
        }}
        
        /* 調整 Streamlit 的 dataframe 顯示樣式 */
        .stDataFrame {{
            border-radius: 8px;
            overflow: hidden;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    
# --- 2. 資料庫操作函數 (CRUD & Balance) ---

@st.cache_resource
def init_firestore():
    """初始化 Firestore 客戶端"""
    try:
        # 使用 Streamlit Secrets 或預設路徑 (如果運行在其他環境)
        if "firestore_credentials" in st.secrets:
            # 確保 'type' 鍵存在於憑證中，這是 Streamlit Secrets 的標準格式
            if 'type' not in st.secrets.firestore_credentials:
                st.error("Streamlit Secrets 格式錯誤：'type' 鍵不存在。")
                return None
            
            # 使用 Service Account 憑證
            db = firestore.Client.from_service_account_info(st.secrets.firestore_credentials)
        else:
            # 如果沒有 secrets，嘗試從環境變數初始化 (例如 GAE 或 GCP)
            db = firestore.Client()
            
        return db
    except Exception as e:
        st.error(f"Firestore 初始化失敗: {e}")
        return None

def get_db_path(db, collection_name, doc_id=None):
    """
    根據 Collection 名稱和可選的 Document ID 構建 Firestore 路徑
    用於私人資料: /artifacts/{__app_id}/users/{userId}/{collection_name}/{doc_id}
    """
    app_id = os.environ.get('CANVAS_APP_ID', 'default-app-id')
    user_id = st.session_state.get('user_id', 'anonymous')
    
    path = db.collection('artifacts').document(app_id).collection('users').document(user_id).collection(collection_name)
    
    if doc_id:
        return path.document(doc_id)
    return path

def get_records(db):
    """從 Firestore 獲取所有交易紀錄，並轉換為 DataFrame"""
    try:
        records_ref = get_db_path(db, RECORD_COLLECTION_NAME)
        docs = records_ref.stream()
        
        data = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id # 將文件 ID 作為 DataFrame 的一欄
            
            # 確保日期欄位是 datetime.date 對象，以便後續處理
            if 'date' in record and isinstance(record['date'], datetime.datetime):
                record['date'] = record['date'].date()
            elif 'date' in record and isinstance(record['date'], firestore.client.base_client.ServerTimestamp):
                 # For ServerTimestamp, it usually resolves to datetime.datetime on read
                 record['date'] = record['date'].date()
            
            # 確保 timestamp 欄位存在，用於排序 (如果不存在則設為 None)
            if 'timestamp' not in record:
                record['timestamp'] = None
                
            data.append(record)
        
        if not data:
            return pd.DataFrame({
                'id': [], 'date': [], 'type': [], 'category': [], 
                'amount': [], 'note': [], 'timestamp': []
            })
            
        df = pd.DataFrame(data)
        
        # 排序: 優先按日期降序，次按儲存時間降序 (最新紀錄在最上方)
        df = df.sort_values(by=['date', 'timestamp'], ascending=[False, False])
        return df.reset_index(drop=True)

    except Exception as e:
        st.error(f"獲取交易紀錄失敗: {e}")
        return pd.DataFrame()

def get_current_balance(db):
    """獲取當前餘額"""
    try:
        balance_doc_ref = get_db_path(db, BALANCE_COLLECTION_NAME, BALANCE_DOC_ID)
        doc = balance_doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0)
        else:
            # 文件不存在，設置初始餘額為 0
            set_current_balance(db, 0, initial=True)
            return 0
    except Exception as e:
        st.error(f"獲取餘額失敗: {e}")
        return 0

def set_current_balance(db, new_balance, initial=False):
    """設置或更新當前餘額"""
    try:
        balance_doc_ref = get_db_path(db, BALANCE_COLLECTION_NAME, BALANCE_DOC_ID)
        
        # 建立更新內容
        update_data = {
            'balance': int(new_balance),
            'last_updated': datetime.datetime.now(datetime.timezone.utc)
        }
        
        if initial:
            balance_doc_ref.set(update_data) # set 用於文件不存在時創建
            st.toast("已初始化餘額為 0。")
        else:
            balance_doc_ref.update(update_data) # update 用於文件已存在時更新
            # st.toast("餘額已更新！", icon="💰") # 避免在 app() 外部使用 toast

    except Exception as e:
        st.error(f"設定餘額失敗: {e}")

def add_record(db, record_data, current_balance):
    """新增交易紀錄並更新餘額"""
    try:
        # 1. 儲存交易紀錄
        records_ref = get_db_path(db, RECORD_COLLECTION_NAME)
        # 確保 amount 是數字
        amount = int(record_data['amount'])
        
        # 建立 Firestore 文件內容
        firestore_data = {
            'date': record_data['date'],
            'type': record_data['type'],
            'category': record_data['category'],
            'amount': amount,
            'note': record_data.get('note', ''),
            'timestamp': firestore.SERVER_TIMESTAMP # 使用伺服器時間戳記
        }
        
        # 使用 add_record 讓 Firestore 自動生成文件 ID
        records_ref.add(firestore_data)
        
        # 2. 更新餘額
        if record_data['type'] == '收入':
            new_balance = current_balance + amount
        else:
            new_balance = current_balance - amount
            
        set_current_balance(db, new_balance)
        st.toast(f"成功新增 {record_data['type']} 紀錄並更新餘額！", icon="✅")
        st.session_state['current_page'] = 'Records_View' # 跳轉到紀錄頁面
        st.rerun()

    except Exception as e:
        st.error(f"新增紀錄失敗: {e}")

def delete_record(db, record_data, current_balance):
    """刪除交易紀錄並反向更新餘額"""
    try:
        # 1. 刪除交易紀錄
        doc_id = record_data['id']
        records_ref = get_db_path(db, RECORD_COLLECTION_NAME)
        records_ref.document(doc_id).delete()
        
        # 2. 反向更新餘額
        amount = record_data['amount']
        
        if record_data['type'] == '收入':
            # 刪除收入：餘額減少
            new_balance = current_balance - amount
        else:
            # 刪除支出：餘額增加
            new_balance = current_balance + amount
            
        set_current_balance(db, new_balance)
        st.toast(f"成功刪除交易紀錄並更新餘額！", icon="🗑️")
        st.rerun()

    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")

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
            col_date.markdown(f"<div style='padding-left: 1rem;'>{record_date.strftime('%Y-%m-%d')}</div>", unsafe_allow_html=True)
            col_cat.write(record_category)
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
    
    # 初始化頁面狀態
    if 'current_page' not in st.session_state:
        st.session_state['current_page'] = 'Dashboard'
        
    # 獲取資料
    df_records = get_records(db)
    current_balance = get_current_balance(db)
    
    # 側邊欄導航
    with st.sidebar:
        st.image("https://placehold.co/120x40/007bff/ffffff?text=Family+Account", use_column_width=True)
        st.markdown("## 導航選單")
        
        # 創建導航按鈕
        for page_key, page_title in PAGES.items():
            if st.button(page_title, key=f"nav_{page_key}", use_container_width=True, type="primary" if st.session_state['current_page'] == page_key else "secondary"):
                st.session_state['current_page'] = page_key
                st.rerun()

    # 根據狀態顯示頁面
    page_name = st.session_state['current_page']
    
    if page_name == 'Dashboard':
        page_dashboard(db, df_records, current_balance)
    elif page_name == 'Record':
        page_record(db, current_balance)
    elif page_name == 'Records_View':
        page_records_view(db, df_records, current_balance)
    elif page_name == 'Balance_Management':
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
