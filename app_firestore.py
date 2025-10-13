import streamlit as st
import pandas as pd
import datetime
from google.cloud import firestore

# --- 0. Streamlit 介面設定 (字體 Inter) ---

def set_inter_font():
    """注入客製化 CSS，將應用程式字體設定為 Inter 並加入中文字體備用"""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

        /* 設置整個頁面使用 Inter，並以常用的中文字體作為備用 */
        html, body, [class*="st-"] {
            font-family: 'Inter', "PingFang TC", "Microsoft YaHei", sans-serif;
        }
        </style>
        """, 
        unsafe_allow_html=True
    )

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
        st.stop() # 停止應用程式運行，直到連線成功

def add_transaction_to_db(db, date, category, amount, type, note):
    """將一筆交易新增到 Firestore 的 'family_ledger' 集合中"""
    
    # 集合路徑：協作應用程式通常使用單一集合來儲存所有紀錄
    collection_name = 'family_ledger'
    
    # 建立數據字典
    transaction_data = {
        'date': date.strftime('%Y-%m-%d'),
        'category': category,
        # 將金額儲存為浮點數
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

def main():
    
    # 初始化並連線到 Firestore
    db = get_firestore_db() 

    # 設置頁面配置
    st.set_page_config(layout="wide", page_title="宅宅家族記帳本")
    set_inter_font()
    st.title("宅宅家族記帳本 (雲端數據)")

    # 獲取所有交易數據 (每次 App 刷新時執行)
    df = get_all_transactions_from_db(db)
    
    # --- 側邊欄：輸入區 ---
    with st.sidebar:
        st.header("新增交易紀錄")
        
        CATEGORIES = ['飲食', '交通', '家庭', '娛樂', '教育', '收入', '其他']
        TRANSACTION_TYPES = ['支出', '收入']

        with st.form("transaction_form"):
            # 1. 交易類型
            trans_type = st.radio("交易類型", TRANSACTION_TYPES, index=0)
            
            # 2. 金額
            amount = st.number_input("金額 (新台幣)", min_value=0.01, format="%.2f", step=10.0)
            
            # 3. 類別
            category_options = CATEGORIES.copy()
            if trans_type == '支出':
                category_options.remove('收入')
            elif trans_type == '收入':
                category_options = ['收入']
            
            category = st.selectbox("類別", category_options)
            
            # 4. 日期
            date = st.date_input("日期", datetime.date.today())
            
            # 5. 備註
            note = st.text_input("備註 (例如: 晚餐-麥當勞)")
            
            submitted = st.form_submit_button("✅ 新增交易")
            
            if submitted:
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

    # 篩選月份
    available_months = df['month_year'].unique().astype(str)
    # 預設選取最新的月份
    selected_month = st.selectbox("📅 選擇查看月份", available_months, index=0)
    
    df_filtered = df[df['month_year'] == selected_month]
    
    st.header(f"📊 {selected_month} 月份總結")
    
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
    st.header("支出類別分佈")
    
    expense_data = df_filtered[df_filtered['type'] == 'Expense'].groupby('category')['amount'].sum().reset_index()
    
    if not expense_data.empty and total_expense > 0:
        # 使用 Streamlit 內建的圖表功能 (Bar Chart)
        expense_data = expense_data.sort_values(by='amount', ascending=False)
        st.bar_chart(expense_data.set_index('category')) 
        #st.dataframe(expense_data.rename(columns={'category': '類別', 'amount': '支出金額'}))
    else:
        st.info("本月無支出紀錄或總支出為零，無法顯示支出分佈圖。")

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
        col_amount.write(f"NT$ {row['金額']:,.2f}")
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
