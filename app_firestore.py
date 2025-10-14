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
            font-size: 1.4rem; /* H2 字體縮小 */
            font-weight: 600;
            color: #495057;
            margin-top: 2rem; /* 拉大頂部間距 */
            margin-bottom: 1.5rem; /* 拉大底部間距 */
        }}

        /* 設置簡約背景顏色 */
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
        }}
        
        /* 讓輸入框和按鈕等元件看起來更現代 */
        div.stButton > button:first-child {{
            border-radius: 8px;
            border: 1px solid #ddd;
            transition: all 0.2s;
        }}
        
        /* 側邊欄輸入框背景色 (讓邊界清晰可見) */
        /* 針對側邊欄內的主要輸入元件容器設定淺灰色背景 */
        section[data-testid="stSidebar"] div.stTextInput > div:first-child,
        section[data-testid="stSidebar"] div.stNumberInput > div:first-child,
        section[data-testid="stSidebar"] div.stDateInput > div:first-child,
        section[data-testid="stSidebar"] div.stSelectbox > div:first-child
        {{
            background-color: #f5f5f5; /* 柔和的淺灰色背景 */
            padding: 10px;
            border-radius: 6px;
            border: 1px solid #e9ecef; /* 加上極淺的邊界 */
        }}
        
        /* --- 新增：Placeholder 樣式，設定為柔和的淺灰色 --- */
        /* 針對數字輸入框 */
        section[data-testid="stSidebar"] input[type="number"]::placeholder {{
            color: #adb5bd !important; /* 柔和的淺灰色，接近文字提示效果 */
            opacity: 1; /* 確保在所有瀏覽器中都可見 */
        }}

        /* 針對文字輸入框 */
        section[data-testid="stSidebar"] input[type="text"]::placeholder {{
            color: #adb5bd !important;
            opacity: 1;
        }}
        /* --- 結束：Placeholder 樣式 --- */
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
        
        # 移除 st.success 提示，讓介面更乾淨
        # st.success("成功連線到 Firestore!") 
        return db
    except Exception as e:
        st.error(f"連線 Firestore 失敗，請檢查 .streamlit/secrets.toml 檔案: {e}")
        st.stop() # 停止應用程式運行，直到連線成功

def add_transaction_to_db(db, date, category, amount, type, note):
    """將一筆交易新增到 Firestore 的 'family_ledger' 集合中"""
    
    # 集合路徑：協作應用程式通常使用單一集合來儲存所有紀錄
    collection_name = 'family_ledger'
    
    # 建立數據字典
    transaction_data = {
        'date': date.strftime('%Y-%m-%d'),
        'category': category,
        # 將金額儲存為浮點數 (Firestore 建議儲存為數字類型，即使是整數)
        'amount': float(amount), 
        'type': type,  # 'Income' or 'Expense'
        'note': note,
        'timestamp': firestore.SERVER_TIMESTAMP # 加入伺服器時間戳，方便排序
    }
    
    # 新增文件到集合
    db.collection(collection_name).add(transaction_data)

def get_all_transactions_from_db(db):
    """從 Firestore 獲取所有交易紀錄，並返回 Pandas DataFrame"""
    collection_name = 'family_ledger'
    
    # 使用快照監聽，獲取最新的數據，並按日期倒序
    # 注意：Firestore 的 get() 是單次讀取，如果需要即時更新，需要使用 on_snapshot
    docs = db.collection(collection_name).order_by('date', direction=firestore.Query.DESCENDING).get()
    
    data = []
    for doc in docs:
        record = doc.to_dict()
        record['id'] = doc.id # 儲存文件 ID，方便未來刪除或修改
        data.append(record)
    
    df = pd.DataFrame(data)
    
    if not df.empty:
        # 進行基本的資料處理
        df['amount_adj'] = df.apply(
            lambda row: row['amount'] if row['type'] == 'Income' else -row['amount'],
            axis=1
        )
        df['date'] = pd.to_datetime(df['date']) # 確保日期為日期格式
        df['month_year'] = df['date'].dt.to_period('M') # 計算月份，用於篩選

    return df

# --- 新增的刪除函數 ---
def delete_transaction_from_db(db, doc_id):
    """根據文件 ID 刪除 Firestore 中的一筆交易紀錄"""
    collection_name = 'family_ledger'
    
    try:
        # 建立文件引用並刪除
        doc_ref = db.collection(collection_name).document(doc_id)
        doc_ref.delete()
        st.success(f"紀錄 (ID: {doc_id}) 已成功刪除。")
    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")

# --- 2. Streamlit 介面與應用邏輯 ---

# 定義基礎類別和常數
BASE_EXPENSE_CATEGORIES = ['飲食', '交通', '家庭', '娛樂', '教育', '其他']
INCOME_CATEGORY = '收入'
TRANSACTION_TYPES = ['支出', '收入']
CUSTOM_OPTION = "⚙️ 新增自訂支出類別..." # 用於觸發自訂輸入框的選項

def main():
    
    # 初始化並連線到 Firestore
    db = get_firestore_db() 

    # 設置頁面配置
    st.set_page_config(layout="wide", page_title="宅宅家族記帳本")
    
    # 注入 CSS 樣式
    set_ui_styles() 
    
    st.title("宅宅家族記帳本 (雲端數據)")

    # 獲取所有交易數據 (每次 App 刷新時執行)
    df = get_all_transactions_from_db(db)
    
    # --- 側邊欄：輸入區 ---
    with st.sidebar:
        # 移除介面設定區
        st.header("新增交易紀錄")
        
        # 準備動態類別列表
        all_expense_categories = []
        if not df.empty:
            # 找出所有已儲存的支出類別
            all_expense_categories = df[df['type'] == 'Expense']['category'].unique().tolist()
        
        # 合併基礎類別和已儲存類別，確保不重複並排序
        combined_expense_categories = sorted(list(set(BASE_EXPENSE_CATEGORIES + all_expense_categories)))
        
        # 加入「新增自訂類別」的選項
        expense_category_options = combined_expense_categories + [CUSTOM_OPTION]

        # 設定預設選項為「飲食」，若「飲食」不在列表中則預設選第一個
        default_index = expense_category_options.index('飲食') if '飲食' in expense_category_options else 0


        with st.form("transaction_form"):
            # 1. 交易類型
            trans_type = st.radio("交易類型", TRANSACTION_TYPES, index=0)
            
            # 2. 金額
            # 新增 placeholder 參數
            amount = st.number_input("金額 (新台幣)", min_value=1, format="%d", step=1, 
                                     placeholder="例如: 350")
            
            # 3. 類別 - 動態處理區
            category = "" # 初始化 category
            
            if trans_type == '收入':
                # 收入類別固定，不提供自訂
                category = INCOME_CATEGORY
                st.markdown(f"**類別**: **{category}** (固定)")
            else:
                # 支出類別：允許選擇或自訂
                selected_category = st.selectbox("類別", expense_category_options, index=default_index)
                
                if selected_category == CUSTOM_OPTION:
                    # 顯示自訂輸入框，新增 placeholder 參數
                    custom_category = st.text_input("請輸入新的支出類別名稱", 
                                                   value="", # 清空預設值
                                                   key="custom_cat_input",
                                                   placeholder="例如: 醫療、寵物")
                    if custom_category:
                        # 使用者輸入了自訂類別
                        category = custom_category.strip()
                    else:
                        # 提醒使用者輸入
                        category = ""
                        st.warning("請輸入自訂類別名稱。")
                else:
                    # 使用者選擇了現有類別
                    category = selected_category
            
            # 4. 日期
            # st.date_input 不支援 placeholder，但已是日曆選擇器，足夠清晰
            date = st.date_input("日期", datetime.date.today())
            
            # 5. 備註
            # 新增 placeholder 參數
            note = st.text_input("備註 (例如: 晚餐-麥當勞)", placeholder="例如: 晚餐-麥當勞，或薪水入帳")
            
            submitted = st.form_submit_button("✅ 新增交易")
            
            if submitted:
                # 檢查類別是否有效（主要針對自訂類別的情況）
                if not category:
                    st.error("請提供一個有效的支出類別名稱。")
                    # 停止應用程式運行，以防止提交空類別
                    st.stop()
                
                # 轉換交易類型
                db_type = 'Income' if trans_type == '收入' else 'Expense'
                
                # 新增到 Firestore
                add_transaction_to_db(db, date, category, amount, db_type, note)
                st.success(f"已新增一筆 {trans_type} 紀錄：{category} {amount} 元！")
                st.balloons() # 增加成功視覺效果
                # 重新運行應用程式以刷新數據
                st.rerun()

    # --- 主畫面：儀表板與紀錄 ---
    
    if df.empty:
        st.warning("目前雲端資料庫中還沒有交易紀錄，請從左側新增第一筆紀錄！")
        return

    # 1. 準備日期範圍篩選
    min_date_in_data = df['date'].min().date()
    today = datetime.date.today()
    
    # 計算當月的第一天作為新的預設起始日期
    first_day_of_current_month = today.replace(day=1)
    
    # 修正點：確保預設的起始日期不會早於資料中最早的日期 (min_date_in_data)
    default_start_date = max(first_day_of_current_month, min_date_in_data)


    st.header("🔍 選擇查看日期範圍")

    # 使用 st.date_input 選擇日期範圍，支援日曆點選
    date_range = st.date_input(
        "選擇起始與結束日期",
        # 預設值變更為：當月的第一天到今天 (但受限於最早的資料日期)
        value=(default_start_date, today),
        min_value=min_date_in_data,
        max_value=today,
        key="date_range_picker"
    )
    
    # 2. 處理選擇的日期範圍
    # st.date_input 在選擇一個或兩個日期時返回一個 tuple
    start_date = min_date_in_data
    end_date = today
    
    if len(date_range) == 2:
        start_date = date_range[0]
        end_date = date_range[1]
        
    elif len(date_range) == 1:
        # 僅選擇了一個日期，視為起始日期，結束日期為今天
        start_date = date_range[0]
        end_date = today

    # 確保 start_date 在 end_date 之前
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    # 3. 執行篩選
    # df['date'] 是 datetime 類型，df['date'].dt.date 是 date 類型
    df_filtered = df[
        (df['date'].dt.date >= start_date) & 
        (df['date'].dt.date <= end_date)
    ]
    
    # 確保篩選後的資料是以日期(最新到最舊)排序，保障顯示順序
    df_filtered = df_filtered.sort_values(by='date', ascending=False)
    
    # 更新標題顯示選擇的日期範圍
    st.header(f" {start_date} 至 {end_date} 總結")
    
    if df_filtered.empty:
        st.warning(f"在 {start_date} 至 {end_date} 範圍內沒有找到交易紀錄。請調整日期篩選條件。")
        return

    # 3.1. 總覽儀表板
    col1, col2, col3 = st.columns(3)
    
    total_income = df_filtered[df_filtered['type'] == 'Income']['amount'].sum()
    col1.metric("總收入 (綠色)", f"NT$ {total_income:,.0f}")
    
    total_expense = df_filtered[df_filtered['type'] == 'Expense']['amount'].sum()
    col2.metric("總支出 (紅色)", f"NT$ {total_expense:,.0f}")
    
    net_flow = total_income - total_expense
    flow_delta = f"{net_flow:,.0f}" # 顯示與零的差異
    col3.metric("淨現金流 (藍色)", f"NT$ {net_flow:,.0f}", delta=flow_delta)

    st.markdown("---")
    
    # 3.2. 支出類別圖表
    # 標題維持不變
    st.header("支出類別分佈")
    
    expense_data = df_filtered[df_filtered['type'] == 'Expense'].groupby('category')['amount'].sum().reset_index()
    
    if not expense_data.empty and total_expense > 0:
        
        # 計算百分比欄位，用於圓餅圖的 Tooltip
        expense_data['percentage'] = expense_data['amount'] / total_expense
        
        # --------------------------------------
        # --- 使用 Altair 創建圓餅圖 (甜甜圈圖) ---
        # --------------------------------------
        
        # 1. 建立基礎圖表 (Pie Chart / Arc Mark)
        base = alt.Chart(expense_data).encode(
            # 角度/大小：依據金額
            theta=alt.Theta("amount", stack=True)
        ).properties(
            title="支出類別金額佔比圓餅圖"
        )
        
        # 2. 建立圓弧圖層
        # 顏色：依據類別
        # order：確保最大的扇形在起始位置
        pie = base.mark_arc(outerRadius=120, innerRadius=60).encode( # 內半徑 60 形成甜甜圈效果
            color=alt.Color("category", title="類別"),
            order=alt.Order("amount", sort="descending"),
            tooltip=[
                "category", 
                alt.Tooltip("amount", format=',.0f', title="總支出 (NT$)"),
                # 顯示百分比
                alt.Tooltip("percentage", format='.1%', title="佔比")
            ]
        )
        
        # 3. 建立文字標籤圖層 (顯示類別) - 可選，Altair 在圓餅圖上顯示標籤較為複雜，這裡先省略以保持簡潔
        
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
    for index, row in display_df.iterrows():
        col_date, col_cat, col_amount, col_note, col_btn = st.columns([1, 1, 1, 3, 1])
        
        # 顯示交易細節
        col_date.write(row['日期'].strftime('%Y-%m-%d'))
        col_cat.write(f"**{row['類型']}**")
        col_amount.write(f"NT$ {row['金額']:,.0f}") # 這裡也改為不顯示小數點
        col_note.write(row['備註'])
        
        # 刪除按鈕
        # 使用唯一 key 確保 Streamlit 能夠識別每個按鈕
        btn_key = f"delete_btn_{row['文件ID']}"
        
        if col_btn.button("🗑️ 刪除", key=btn_key):
            # 執行刪除操作
            delete_transaction_from_db(db, row['文件ID'])
            # 刪除成功後重新運行應用程式以刷新數據
            st.rerun()

    st.markdown("---")


if __name__ == "__main__":
    main()



