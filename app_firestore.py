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
            border-left: 4px solid #007bff; /* 藍色裝飾線 */
            padding-left: 10px;
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }}
        
        /* Streamlit 頁面背景 */
        .stApp {{
            background-color: {DEFAULT_BG_COLOR};
        }}

        /* 調整按鈕樣式，使其更美觀 */
        div.stButton > button:first-child {{
            border-radius: 0.5rem;
            border: 1px solid #007bff;
            color: white;
            background-color: #007bff;
            font-weight: 600;
            transition: all 0.2s ease-in-out;
        }}
        div.stButton > button:first-child:hover {{
            background-color: #0056b3;
            border-color: #0056b3;
        }}

        /* 調整次級按鈕（刪除按鈕）樣式 */
        div.stButton > button[kind="secondary"] {{
            background-color: #dc3545; /* 紅色用於刪除 */
            border-color: #dc3545;
            color: white;
            font-weight: 400;
            padding: 0.3rem 0.5rem;
            line-height: 1;
        }}
        div.stButton > button[kind="secondary"]:hover {{
            background-color: #c82333;
            border-color: #c82333;
        }}

        /* 確保 st.container 容器內容有適當的間距 */
        .stContainer {{
            padding: 1rem;
        }}
        
        /* 圓餅圖調整，確保圖表下方的文字不被切除 */
        [data-testid="stVegaLiteChart"] {{
            padding-bottom: 20px;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    
# --- 2. Firebase 設置與工具函數 ---
@st.cache_resource
def get_firestore_client():
    """初始化並快取 Firestore 客戶端"""
    try:
        # 在 Streamlit Cloud 上，使用 st.secrets 取得服務帳號憑證
        # 在本地運行時，可能需要其他認證方式，這裡假設在 Streamlit 環境中
        if "firestore_client" not in st.session_state:
            db = firestore.Client.from_service_account_info(st.secrets["firebase"]["service_account"])
            st.session_state.firestore_client = db
        return st.session_state.firestore_client
    except Exception as e:
        st.error(f"Firestore 初始化失敗：{e}")
        st.stop()

# 獲取使用者 ID
# 在 Streamlit 環境中，我們沒有內建的認證系統，
# 這裡使用一個固定的 ID 作為示範，但在實際應用中，應替換為真實的用戶 ID
def get_user_id():
    """獲取一個固定的使用者 ID 用於隔離資料"""
    return "demo_user_001" 

# 獲取使用者專屬的 Collection 參考 (用於 records 和 account_status)
def get_collection_ref(db, user_id, collection_name):
    """取得使用者專屬的 Collection 參考路徑"""
    # 遵循安全性規則: /artifacts/{appId}/users/{userId}/{your_collection_name}
    appId = st.secrets["firebase"]["app_id"] # 假設 app_id 存在於 secrets
    return db.collection('artifacts').document(appId).collection('users').document(user_id).collection(collection_name)

# 獲取使用者專屬的餘額文件參考
def get_balance_doc_ref(db, user_id):
    """取得使用者專屬的餘額文件參考路徑"""
    # 餘額文件路徑: /artifacts/{appId}/users/{userId}/account_status/current_balance
    return get_collection_ref(db, user_id, BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)

# 載入所有交易紀錄
@st.cache_data(ttl=5) # 快取 5 秒，避免過度讀取 Firestore
def load_records(db, user_id):
    """從 Firestore 載入所有交易紀錄"""
    records_ref = get_collection_ref(db, user_id, RECORD_COLLECTION_NAME)
    
    try:
        docs = records_ref.stream()
        records_list = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id
            record['date'] = record['date'].date() # 將 Firestore Timestamp 轉換為 Python date
            records_list.append(record)
        
        if records_list:
            df = pd.DataFrame(records_list)
            # 確保 'date' 欄位是 datetime.date 類型
            df['date'] = pd.to_datetime(df['date'])
            # 依日期降序排列
            df.sort_values(by='date', ascending=False, inplace=True)
            return df
        else:
            return pd.DataFrame(columns=['id', 'date', 'category', 'amount', 'type', 'note'])

    except Exception as e:
        st.error(f"載入紀錄失敗: {e}")
        return pd.DataFrame(columns=['id', 'date', 'category', 'amount', 'type', 'note'])

# 載入當前餘額
@st.cache_data(ttl=5)
def load_current_balance(db, user_id):
    """從 Firestore 載入當前餘額"""
    balance_doc_ref = get_balance_doc_ref(db, user_id)
    try:
        doc = balance_doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0)
        else:
            # 第一次使用，初始化餘額為 0
            balance_doc_ref.set({'balance': 0, 'last_updated': firestore.SERVER_TIMESTAMP})
            return 0
    except Exception as e:
        st.error(f"載入餘額失敗: {e}")
        return 0

# 刪除交易紀錄並更新餘額
def delete_record(db, user_id, record_id, record_type, record_amount, current_balance):
    """刪除一筆交易紀錄並反向更新餘額"""
    records_ref = get_collection_ref(db, user_id, RECORD_COLLECTION_NAME)
    balance_doc_ref = get_balance_doc_ref(db, user_id)

    # 1. 執行餘額更新
    new_balance = current_balance
    if record_type == '收入':
        # 刪除收入：餘額減少
        new_balance -= record_amount
    else: # 支出
        # 刪除支出：餘額增加
        new_balance += record_amount
        
    try:
        # 使用 transaction 確保原子性操作（雖然 Streamlit 刷新會重載，但習慣上還是用）
        @firestore.transactional
        def update_in_transaction(transaction):
            # 寫入新的餘額
            transaction.set(
                balance_doc_ref, 
                {'balance': new_balance, 'last_updated': firestore.SERVER_TIMESTAMP}
            )
            # 刪除交易紀錄
            transaction.delete(records_ref.document(record_id))
            
        transaction = db.transaction()
        update_in_transaction(transaction)
        
        # 刪除成功後，清除快取並重新運行
        st.cache_data.clear()
        st.success("紀錄已刪除，餘額已更新！")
        st.rerun()

    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")


# --- 3. 主要應用邏輯 ---
def main():
    """主要的 Streamlit 應用程式函數"""
    
    # 設置 UI 樣式
    set_ui_styles()

    st.title("簡易個人記帳本 📊")
    
    # 獲取 Firestore 客戶端和使用者 ID
    db = get_firestore_client()
    user_id = get_user_id()
    
    # 載入資料
    df_records = load_records(db, user_id)
    current_balance = load_current_balance(db, user_id)
    
    # 將餘額儲存到 session_state，供刪除功能使用
    st.session_state.current_balance = current_balance

    # 3.1. 餘額顯示
    st.header("當前餘額")
    
    balance_display = f"<div style='background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;'>"\
                      f"  <h3 style='margin: 0; color: #6c757d; font-weight: 400;'>總餘額</h3>"\
                      f"  <p style='font-size: 2.5rem; font-weight: 700; color: #007bff; margin: 5px 0 0 0;'>NT$ {current_balance:,.0f}</p>"\
                      f"</div>"
    st.markdown(balance_display, unsafe_allow_html=True)
    
    st.markdown("---")


    # 3.2. 新增交易紀錄表單
    st.header("新增交易")

    with st.form(key='record_form'):
        col1, col2 = st.columns(2)
        
        # 選擇類型
        record_type = col1.radio(
            "類型", 
            ['支出', '收入'], 
            horizontal=True,
            index=0 # 預設為支出
        )
        
        # 根據類型動態顯示類別選項
        category_options = CATEGORIES[record_type]
        category = col2.selectbox("類別", category_options)
        
        col3, col4 = st.columns(2)
        
        # 金額
        amount = col3.number_input("金額 (NT$)", min_value=1, value=100, step=1)
        
        # 日期
        date = col4.date_input("日期", datetime.date.today())
        
        # 備註
        note = st.text_input("備註 (可選)", max_chars=100)
        
        submitted = st.form_submit_button("儲存紀錄")

        if submitted:
            # 確保金額為正整數
            if amount is None or amount <= 0:
                st.error("請輸入有效金額。")
            else:
                # 1. 準備新的交易紀錄
                new_record = {
                    'id': str(uuid.uuid4()), # 生成唯一 ID
                    'date': date,
                    'category': category,
                    'amount': int(amount),
                    'type': record_type,
                    'note': note,
                    'timestamp': firestore.SERVER_TIMESTAMP
                }

                # 2. 計算新的餘額
                change = new_record['amount'] if new_record['type'] == '收入' else -new_record['amount']
                new_balance = current_balance + change

                # 3. 執行 Firestore 寫入
                records_ref = get_collection_ref(db, user_id, RECORD_COLLECTION_NAME)
                balance_doc_ref = get_balance_doc_ref(db, user_id)
                
                try:
                    @firestore.transactional
                    def update_in_transaction(transaction):
                        # 寫入新的餘額
                        transaction.set(
                            balance_doc_ref, 
                            {'balance': new_balance, 'last_updated': firestore.SERVER_TIMESTAMP}
                        )
                        # 寫入新的交易紀錄 (使用 set 而非 add，以確保使用自定義 ID)
                        transaction.set(records_ref.document(new_record['id']), new_record)
                        
                    transaction = db.transaction()
                    update_in_transaction(transaction)
                    
                    st.success("交易紀錄儲存成功！餘額已更新。")
                    
                    # 儲存成功後清除快取並重新運行
                    st.cache_data.clear()
                    st.rerun()

                except Exception as e:
                    st.error(f"資料儲存失敗: {e}")
                    
    st.markdown("---")

    # 3.3. 支出分佈圖
    st.header("支出分佈 (圓餅圖)")

    if not df_records.empty:
        # 篩選出日期範圍
        with st.expander("選擇分析期間", expanded=False):
            min_date = df_records['date'].min().date()
            max_date = df_records['date'].max().date()
            
            start_date, end_date = st.date_input(
                "選擇開始和結束日期", 
                value=[min_date, max_date],
                min_value=min_date,
                max_value=max_date
            )
        
        # 過濾 DataFrame
        df_range = df_records[(df_records['date'].dt.date >= start_date) & (df_records['date'].dt.date <= end_date)].copy()
        
        # 計算支出分佈
        df_expenses = df_range[df_range['type'] == '支出'].copy()
        
        if not df_expenses.empty:
            df_pie = df_expenses.groupby('category')['amount'].sum().reset_index()
            df_pie.rename(columns={'amount': '總支出'}, inplace=True)
            
            total_expense = df_pie['總支出'].sum()
            
            if total_expense > 0:
                df_pie['比例'] = df_pie['總支出'] / total_expense
                
                # 1. 建立圓餅圖
                base = alt.Chart(df_pie).encode(
                    theta=alt.Theta("總支出", stack=True)
                ).properties(
                    title="選定期間支出類別分佈"
                )

                # 2. 建立弧線（Arc）
                # 顏色使用 category 欄位，並添加工具提示
                pie = base.mark_arc(outerRadius=120, innerRadius=50).encode( # 增加 outerRadius 讓圖表更大
                    color=alt.Color("category", title="類別"),
                    order=alt.Order("總支出", sort="descending"),
                    tooltip=["category", alt.Tooltip("總支出", format=",.0f"), alt.Tooltip("比例", format=".1%")]
                )
                
                # 3. 建立文字標籤
                text = base.mark_text(radius=140).encode(
                    text=alt.Text("比例", format=".1%"),
                    order=alt.Order("總支出", sort="descending"),
                    color=alt.value("black") # 確保標籤顏色為黑色
                )
                
                # 4. 組合圖表並居中顯示
                chart = (pie + text).interactive()
                
                # 為了讓圓餅圖在 Streamlit 內置的容器中能保持正確的寬高比，
                # 這裡設定較為固定的寬高，讓圓形居中顯示。
                st.altair_chart(chart, use_container_width=True)

            else:
                st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")
                
        else:
             st.info("選定範圍內無支出紀錄，無法顯示支出分佈圖。")
    
    else:
        st.info("選定範圍內無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # 3.4. 交易紀錄區 (新增刪除按鈕)
    st.header("完整交易紀錄")
    
    # 準備用於顯示的 DataFrame
    if df_records.empty:
        st.info("目前尚無交易紀錄。請新增紀錄開始記帳！")
        return

    # 由於 DataFrame 已經包含所需欄位且已排序，直接使用
    display_df = df_records.copy()
    
    # 標題列
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px; border: 1px solid #dee2e6;'>
            <div style='width: 11%; padding-left: 1rem;'>日期</div>
            <div style='width: 10%;'>類別</div>
            <div style='width: 10%;'>金額</div>
            <div style='width: 7%;'>類型</div>
            <div style='width: 50%;'>備註</div>
            <div style='width: 12%; text-align: center;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    for row in display_df.itertuples(index=False):
        try:
            # 從完整的紀錄中獲取刪除所需的資訊 (使用 row['id'] 作為查找依據)
            # 注意: itertuples 訪問欄位使用 .column_name (如果沒有 index=False, 則第一個是 Index)
            # 但這裡直接從 df_records 獲取 details 更安全
            record_details_for_delete = df_records[df_records['id'] == row.id].iloc[0].to_dict()
        except IndexError:
            st.error(f"找不到文件ID為 {row.id} 的原始紀錄，可能已被刪除。")
            continue
            
        color = "#28a745" if row.type == '收入' else "#dc3545"
        amount_sign = "+" if row.type == '收入' else "-"
        
        # 使用 container 和 columns 創建行布局
        with st.container():
            # ***************************************************************
            # **修正點 1: 調整 st.columns 比例，增加備註欄位的權重 (7)**
            # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 7, 操作 1] (總和 11.9)
            # 這裡微調了列數組，並將備註欄位權重增加到 7
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 7, 1])
            # ***************************************************************
            
            # 使用 st.write 顯示交易細節
            col_date.write(row.date.strftime('%Y-%m-%d'))
            col_cat.write(row.category)
            # 使用 markdown 顯示金額和顏色
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row.amount:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(row.type)
            col_note.write(row.note) # 備註內容，給予更多空間避免重疊
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{row.id}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                delete_record(
                    db=db,
                    user_id=user_id,
                    record_id=row.id,
                    record_type=record_details_for_delete['type'],
                    record_amount=record_details_for_delete['amount'],
                    current_balance=st.session_state.current_balance # 從 session_state 獲取最新餘額
                )

# 運行主應用程式
if __name__ == "__main__":
    main()

