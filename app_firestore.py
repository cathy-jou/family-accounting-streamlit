import streamlit as st
import pandas as pd
import datetime
from google.cloud import firestore
import altair as alt # 導入 Altair 函式庫

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
        # 連線失敗的處理邏輯
        st.error(f"連線 Firestore 失敗，請檢查 .streamlit/secrets.toml 檔案: {e}")
        st.stop() # 停止應用程式運行，直到連線成功

def add_transaction_to_db(db, date, category, amount, type, note):
    """將一筆交易新增到 Firestore 的 'ledger' 集合中"""
    
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

def delete_transaction_from_db(db, transaction_id):
    """根據文件 ID 從 Firestore 刪除一筆交易紀錄"""
    collection_name = 'family_ledger'
    # 獲取文件參考 (Document Reference)
    doc_ref = db.collection(collection_name).document(transaction_id)
    # 執行刪除
    doc_ref.delete()

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

# --- 2. Streamlit 介面與應用邏輯 ---

def main():
    
    # 初始化並連線到 Firestore
    db = get_firestore_db() 

    # 設置頁面配置
    st.set_page_config(layout="wide", page_title="宅宅家族記帳本")
    set_inter_font()
    st.title("宅宅家族記帳本 (雲端數據)")

    # 獲取所有交易數據 (每次 App 刷新時執行)
    # Streamlit 會在用戶操作時重新運行腳本
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
    
    st.header(f"{selected_month} 月份總結")
    
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
        # 使用 Altair 繪製條狀圖，以控制顏色
        expense_data = expense_data.sort_values(by='amount', ascending=False)
        
        # 繪製 Altair 圖表
        chart = alt.Chart(expense_data).mark_bar(
            # 設定條狀顏色為單一的深灰色 (#333)，在 light/dark 模式下皆有良好對比
            color='#333333' 
        ).encode(
            x=alt.X('amount', title='支出金額 (NT$)'),
            y=alt.Y('category', title='類別', sort='-x'), # 依照金額降冪排序類別
            # 新增工具提示
            tooltip=['category', alt.Tooltip('amount', format=',.0f', title='支出金額')]
        ).properties(
            title="各類別支出總額"
        ).interactive() # 允許縮放和平移

        st.altair_chart(chart, use_container_width=True)

    else:
        st.info("本月無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # 3.3. 交易紀錄區
    st.header("完整交易紀錄")
    
    # 修改：使用 st.columns 來並排顯示紀錄和刪除按鈕
    # 遍歷篩選後的數據框，逐筆顯示
    for index, row in df_filtered.iterrows():
        # 建立兩欄：紀錄內容 (較寬) 和刪除按鈕 (較窄)
        record_col, delete_col = st.columns([0.9, 0.1])
        
        # 顯示交易紀錄的精簡內容
        record_text = f"**{row['date'].strftime('%Y-%m-%d')}** | {row['category']} | **NT$ {row['amount']:,.0f}** ({'收入' if row['type'] == 'Income' else '支出'}) - {row['note']}"
        record_col.markdown(record_text)

        # 刪除按鈕，使用文件 ID 作為 key，確保每個按鈕唯一
        if delete_col.button("🗑️ 刪除", key=f"delete_{row['id']}"):
            # 執行刪除操作
            delete_transaction_from_db(db, row['id'])
            st.success(f"已刪除紀錄: {row['category']} - {row['amount']} 元")
            st.experimental_rerun() # 刪除後立即刷新頁面

    st.markdown("---")
    
    # 由於不再使用 st.dataframe 顯示完整表格，以下代碼可以移除或保留，但不再起作用。
    # display_df = df_filtered[['date', 'category', 'amount', 'type', 'note']].copy()
    # display_df.rename(columns={
    #     'date': '日期', 
    #     'category': '類別', 
    #     'amount': '金額', 
    #     'type': '類型', 
    #     'note': '備註'
    # }, inplace=True)
    
    # st.dataframe(display_df, use_container_width=True)


if __name__ == "__main__":
    main()

