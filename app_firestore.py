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
            font-size: 1.3rem;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 5px;
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }}

        /* Streamlit 基本樣式覆寫 */
        .main {{
            background-color: {DEFAULT_BG_COLOR};
            padding-top: 1rem; 
        }}
        [data-testid="stAppViewContainer"] {{
            background-color: {DEFAULT_BG_COLOR};
        }}
        /* 保持側邊欄為白色，與主內容區分隔，增強視覺層次感 */
        section[data-testid="stSidebar"] {{
            background-color: #ffffff; 
        }}
        
        /* 按鈕優化 */
        div.stButton > button:first-child {{
            border-radius: 8px;
            border: 1px solid #007bff;
            background-color: #007bff;
            color: white;
            padding: 8px 16px;
            font-weight: 600;
        }}
        /* 上傳按鈕優化 */
        div.stDownloadButton > button:first-child, 
        div.stFileUploadDropzone > button:first-child {{
            border-radius: 8px;
            border: 1px solid #28a745;
            background-color: #28a745;
            color: white;
            padding: 8px 16px;
            font-weight: 600;
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
        st.stop() # 連線失敗則停止應用程式運行

def add_record(db, date, category, amount, type_of_record, note=""):
    """新增一筆記帳紀錄到 Firestore。"""
    try:
        # 建立一個新的文件參考
        doc_ref = db.collection("transactions").document()
        
        # 準備數據
        data = {
            # 確保儲存的是 datetime.date 或 datetime.datetime 物件
            "date": datetime.datetime.combine(date, datetime.time.min) if isinstance(date, datetime.date) else date,
            "category": category,
            "amount": float(amount),
            "type": type_of_record, # '支出' 或 '收入'
            "note": note,
            "created_at": datetime.datetime.now()
        }
        
        # 寫入 Firestore
        doc_ref.set(data)
        return True
    except Exception as e:
        st.error(f"新增紀錄失敗: {e}")
        return False

def get_all_records(db):
    """從 Firestore 獲取所有記帳紀錄並轉換為 DataFrame。"""
    try:
        docs = db.collection("transactions").stream()
        
        records = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id # 保留文件 ID
            
            # --- 核心錯誤修正：穩健處理日期類型 ---
            date_field = record.get('date')
            
            if isinstance(date_field, datetime.datetime):
                # 如果是 datetime.datetime (來自 Firestore 的儲存)，則取日期部分
                # 必須移除時區資訊 (tzinfo) 才能與 Pandas 和 Streamlit 良好互動
                if date_field.tzinfo is not None:
                    record['date'] = date_field.replace(tzinfo=None).date()
                else:
                    record['date'] = date_field.date()
                    
            elif isinstance(date_field, datetime.date):
                # 如果是 datetime.date (來自某些特定的寫入或 CSV 導入)
                record['date'] = date_field
                
            elif isinstance(date_field, str):
                # 處理字串格式的日期 (例如來自 CSV 匯入)
                try:
                    record['date'] = datetime.datetime.strptime(date_field, '%Y-%m-%d').date()
                except ValueError:
                    # 嘗試其他格式或設為今日 (作為備案)
                    record['date'] = datetime.date.today()
            else:
                 # 日期無效，設為今日
                 record['date'] = datetime.date.today() 
            # --- 結束日期處理 ---
            
            records.append(record)
        
        # 如果沒有紀錄，返回空的 DataFrame
        if not records:
            return pd.DataFrame(columns=['date', 'category', 'amount', 'type', 'note', 'id'])
            
        df = pd.DataFrame(records)
        
        # 確保 amount 是數字，date 是日期類型
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        # date 已經在上面轉換為 datetime.date，這裡只需要排序
        df = df.sort_values(by='date', ascending=False)
        return df.dropna(subset=['amount', 'date']) # 移除 amount 或 date 無效的行
        
    except Exception as e:
        # st.error(f"讀取紀錄失敗: {e}") # 為了不中斷應用程式，只在控制台輸出錯誤
        print(f"Error reading records: {e}")
        return pd.DataFrame(columns=['date', 'category', 'amount', 'type', 'note', 'id'])

def delete_record(db, doc_id):
    """從 Firestore 刪除一筆紀錄。"""
    try:
        db.collection("transactions").document(doc_id).delete()
        st.toast(f"成功刪除文件 ID: {doc_id}", icon="🗑️")
        # 設置一個狀態來觸發應用程式重新運行
        st.session_state['refresh_data'] = True
        return True
    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")
        return False

# --- 2. 應用程式介面功能 (單筆輸入) ---

def input_form_page(db):
    """記帳輸入頁面 (包含手動輸入和 CSV 導入)"""
    st.header("手動記帳 / 批量導入")
    
    # 建立兩個頁籤
    tab1, tab2 = st.tabs(["📝 手動輸入", "📂 批量導入 (CSV/Excel)"])

    with tab1:
        st.subheader("新增單筆交易")
        
        # 類別選項
        expense_categories = ["餐飲", "交通", "購物", "娛樂", "住房", "醫療", "教育", "投資", "其他支出"]
        income_categories = ["薪資", "獎金", "投資收益", "其他收入"]
        
        # 交易類型選擇
        type_of_record = st.radio("類型", ['支出', '收入'], index=0, horizontal=True)
        
        # 根據類型顯示不同類別
        if type_of_record == '支出':
            categories = expense_categories
        else:
            categories = income_categories

        # 欄位輸入
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("日期", datetime.date.today())
        with col2:
            amount = st.number_input("金額", min_value=0.01, step=1.0, format="%.2f")
            
        category = st.selectbox("類別", categories)
        note = st.text_input("備註/說明", "")
        
        # 新增按鈕
        if st.button("確認新增", type="primary"):
            if amount and category:
                if add_record(db, date, category, amount, type_of_record, note):
                    st.success("紀錄新增成功！")
                    # 設置狀態來觸發應用程式重新載入數據
                    st.session_state['refresh_data'] = True
                else:
                    st.error("紀錄新增失敗，請重試。")
            else:
                st.warning("請輸入金額和類別！")

    with tab2:
        st.subheader("從銀行交易紀錄批量導入")
        st.info("""
        請從您的銀行或信用卡網站下載交易紀錄 CSV/Excel 檔案。
        **數據格式要求：** 檔案中必須包含以下欄位（名稱需準確）：
        - **日期** (例如: `2025/10/23` 或 `2025-10-23`)
        - **金額** (必須是數字)
        - **交易摘要** 或 **備註** (用於自動或手動分類)
        - **類型** (可選，如果沒有類型，則預設所有正數為收入，負數為支出)
        """)

        uploaded_file = st.file_uploader("上傳 CSV 或 Excel 檔案", type=["csv", "xlsx"])

        if uploaded_file is not None:
            try:
                # 根據副檔名讀取文件
                if uploaded_file.name.endswith('.csv'):
                    df_upload = pd.read_csv(uploaded_file)
                elif uploaded_file.name.endswith('.xlsx'):
                    df_upload = pd.read_excel(uploaded_file)
                else:
                    st.error("不支援的檔案格式。")
                    return

                st.markdown("##### 步驟 1: 確認檔案內容")
                st.dataframe(df_upload.head())
                
                # 嘗試自動識別欄位
                date_cols = [c for c in df_upload.columns if '日' in c and '期' in c]
                amount_cols = [c for c in df_upload.columns if '金額' in c or '數' in c]
                note_cols = [c for c in df_upload.columns if '摘要' in c or '說明' in c]

                # 讓使用者選擇正確的欄位名稱
                st.markdown("##### 步驟 2: 選擇對應的欄位")
                
                # 確保下拉選單至少有一個選項
                default_date_index = df_upload.columns.get_loc(date_cols[0]) if date_cols else 0
                default_amount_index = df_upload.columns.get_loc(amount_cols[0]) if amount_cols else 0
                default_note_index = df_upload.columns.get_loc(note_cols[0]) if note_cols else 0
                
                col_date = st.selectbox("選擇【日期】欄位", df_upload.columns, index=default_date_index)
                col_amount = st.selectbox("選擇【金額】欄位", df_upload.columns, index=default_amount_index)
                col_note = st.selectbox("選擇【備註/摘要】欄位", df_upload.columns, index=default_note_index)
                
                # 金額處理方式（銀行導出的金額可能都是正數，需要判斷）
                amount_sign_option = st.radio(
                    "如何判斷交易類型 (收入/支出)?",
                    ["金額正負 (推薦)", "單獨欄位 (如果檔案有)"],
                    index=0,
                    horizontal=True
                )
                
                if st.button("確認導入並存儲到 Firestore", key="upload_button", type="primary"):
                    
                    df_processed = df_upload.copy()
                    
                    # 1. 數據清洗與轉換
                    df_processed[col_amount] = pd.to_numeric(df_processed[col_amount], errors='coerce').fillna(0)
                    
                    # 2. 定義類型 (type) 和類別 (category)
                    if amount_sign_option == "金額正負 (推薦)":
                        # 正數為收入，負數為支出
                        df_processed['type'] = df_processed[col_amount].apply(lambda x: '收入' if x > 0 else '支出')
                        df_processed['amount'] = df_processed[col_amount].abs()
                    # 這裡可以加入更複雜的自動分類邏輯 (例如，根據備註關鍵字自動分類)
                    df_processed['category'] = '待分類' # 預設為待分類
                    
                    # 3. 統一日期格式
                    # 嘗試將欄位轉換為日期時間物件
                    df_processed['date'] = pd.to_datetime(df_processed[col_date], errors='coerce')
                    # 取出日期部分
                    df_processed['date'] = df_processed['date'].dt.date
                    
                    # 過濾掉日期和金額無效的行
                    df_final = df_processed.dropna(subset=['date', 'amount']).copy()
                    
                    # 4. 批量寫入 Firestore
                    count = 0
                    with st.spinner("正在批量導入資料..."):
                        for index, row in df_final.iterrows():
                            # 使用摘要作為備註
                            note_content = str(row[col_note]) if col_note in row else ""
                            
                            add_record(
                                db=db, 
                                date=row['date'], 
                                category=row['category'], 
                                amount=row['amount'], 
                                type_of_record=row['type'], 
                                note=note_content
                            )
                            count += 1
                            
                    st.success(f"✅ 成功導入 {count} 筆交易紀錄！請至財務總覽頁面查看。")
                    st.session_state['refresh_data'] = True
                    
            except Exception as e:
                st.error(f"檔案處理發生錯誤，請檢查檔案格式與欄位選擇: {e}")
                import traceback
                st.code(traceback.format_exc()) # 顯示詳細的錯誤追蹤

# --- 3. 應用程式介面功能 (總覽與分析) ---

def overview_page(db):
    """財務總覽與分析頁面"""
    st.header("財務總覽與分析")
    
    # 獲取所有數據
    df = get_all_records(db)
    
    if df.empty:
        st.info("目前無交易紀錄，請在記帳頁面新增或導入數據。")
        return

    # --- 篩選器 ---
    st.subheader("篩選條件")
    
    # 確保日期欄位是 datetime.date 類型以便 min/max 運算
    df['date'] = df['date'].apply(lambda x: x if isinstance(x, datetime.date) else datetime.date.today())
    
    min_date = df['date'].min()
    max_date = df['date'].max()

    col_start, col_end = st.columns(2)
    
    with col_start:
        # 使用最舊的日期作為預設起始日期
        start_date = st.date_input("起始日期", min_date)
    with col_end:
        # 使用最新的日期作為預設結束日期
        end_date = st.date_input("結束日期", max_date)
        
    # 過濾數據
    df_filtered = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
    
    if df_filtered.empty:
        st.warning(f"在 {start_date} 到 {end_date} 範圍內無紀錄。")
        return
        
    # --- 3.1. 核心指標 ---
    st.subheader("核心財務指標")
    
    # 計算收入和支出
    total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
    total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
    net_flow = total_income - total_expense

    col_income, col_expense, col_net = st.columns(3)

    col_income.metric("總收入", f"NT$ {total_income:,.0f}", delta_color="normal")
    col_expense.metric("總支出", f"NT$ {total_expense:,.0f}", delta_color="inverse")
    
    # 淨流量計算與顯示
    net_delta = f"本期淨流量"
    if net_flow > 0:
        col_net.metric(net_delta, f"NT$ {net_flow:,.0f}", "盈餘", delta_color="normal")
    elif net_flow < 0:
        col_net.metric(net_delta, f"NT$ {net_flow:,.0f}", "赤字", delta_color="inverse")
    else:
        col_net.metric(net_delta, f"NT$ {net_flow:,.0f}", "持平")
        
    st.markdown("---")

    # --- 3.2. 支出分佈圖 (圓餅圖) ---
    st.subheader("支出類別分佈")
    
    expense_data = df_filtered[df_filtered['type'] == '支出'].groupby('category').agg(
        amount=('amount', 'sum')
    ).reset_index()
    
    if total_expense > 0:
        
        # 為了圓餅圖視覺效果更好，使用 Altair 
        pie = alt.Chart(expense_data).mark_arc(outerRadius=120, innerRadius=50).encode(
            theta=alt.Theta("amount", stack=True),
            color=alt.Color("category", title="類別"),
            order=alt.Order("amount", sort="descending"),
            tooltip=["category", alt.Tooltip('amount', format=',.0f', title='總支出')]
        ).properties(
            title="選定範圍內各類別支出金額分佈"
        )
        
        text = pie.mark_text(radius=140).encode(
            text=alt.Text("amount", format=","),
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

    # --- 3.3. 交易紀錄區 (新增刪除按鈕) ---
    st.subheader("完整交易紀錄")
    
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
    st.markdown("""
        <div style='font-weight: bold; display: flex; border-bottom: 2px solid #ccc; padding: 5px 0;'>
            <div style='width: 15%;'>日期</div>
            <div style='width: 15%;'>類別</div>
            <div style='width: 15%;'>金額</div>
            <div style='width: 35%;'>備註</div>
            <div style='width: 20%;'>操作</div>
        </div>
        """, unsafe_allow_html=True)

    for index, row in display_df.iterrows():
        # 根據類型設置顏色
        color = "#dc3545" if row['類型'] == '支出' else "#28a745"
        sign = "-" if row['類型'] == '支出' else "+"
        
        col_date, col_cat, col_amount, col_note, col_btn = st.columns([1, 1, 1, 3, 1])
        
        # 顯示交易細節
        col_date.write(row['日期'].strftime('%Y/%m/%d'))
        col_cat.write(row['類別'])
        col_amount.markdown(f"<span style='color: {color}; font-weight: bold;'>{sign} {row['金額']:,.0f}</span>", unsafe_allow_html=True)
        col_note.write(row['備註'])
        
        # 刪除按鈕
        if col_btn.button("🗑️ 刪除", key=f"delete_{row['文件ID']}", help="永久刪除此筆紀錄"):
            delete_record(db, row['文件ID'])
            # 刷新頁面以更新列表 (通過 session_state 觸發重新執行)
            st.rerun()

# --- 主程式 ---

def main():
    """應用程式主入口"""
    # 設置頁面配置
    st.set_page_config(
        page_title="個人財務儀表板 (記帳本)",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 注入樣式
    set_ui_styles()
    
    st.title("💸 個人財務儀表板")
    
    # 初始化 Firestore 連線 (只會執行一次)
    db = get_firestore_db()
    
    # 處理數據刷新狀態
    if 'refresh_data' not in st.session_state:
        st.session_state['refresh_data'] = False
        
    if st.session_state['refresh_data']:
        # 重設狀態並觸發重新運行
        st.session_state['refresh_data'] = False
        st.rerun()
        return


    # 使用 Streamlit 側邊欄作為導航
    with st.sidebar:
        st.header("導航")
        page = st.radio("選擇功能頁面", ["記帳頁面", "財務總覽"])
        st.markdown("---")
        st.caption("數據儲存於 Google Firestore，由 Streamlit 應用程式運行。")

    
    # 頁面分流
    if page == "記帳頁面":
        input_form_page(db)
    elif page == "財務總覽":
        overview_page(db)


if __name__ == "__main__":
    main()

