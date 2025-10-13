import streamlit as st
import pandas as pd
import sqlite3
import datetime

# --- 1. 資料庫連線與初始化 ---
DB_FILE = 'family_ledger.db' # 資料庫檔案名稱

def init_db():
    """初始化資料庫並創建 Ledger（帳本）表格"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 創建表格：日期、類別、金額、類型、備註
    c.execute('''
        CREATE TABLE IF NOT EXISTS ledger (
            date TEXT,
            category TEXT,
            amount REAL,
            type TEXT,  -- 'Income' or 'Expense'
            note TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_transaction(date, category, amount, type, note):
    """將一筆交易新增到資料庫"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO ledger VALUES (?, ?, ?, ?, ?)",
              (date, category, amount, type, note))
    conn.commit()
    conn.close()

def get_all_transactions():
    """從資料庫獲取所有交易紀錄，並返回 Pandas DataFrame"""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM ledger ORDER BY date DESC", conn)
    conn.close()
    
    # 進行基本的資料處理
    if not df.empty:
        # 將 'amount' 欄位調整為正負數以便計算
        df['amount_adj'] = df.apply(
            lambda row: row['amount'] if row['type'] == 'Income' else -row['amount'],
            axis=1
        )
        df['date'] = pd.to_datetime(df['date']) # 確保日期為日期格式
        
    return df

def set_inter_font():
    """注入客製化 CSS，將應用程式字體設定為 Inter (從 Google Fonts 引入)"""
    
    st.markdown("""
        <style>
        /* 1. 從 Google Fonts 引入 Inter 字體 (包含不同字重，如 400, 600, 700) */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

        /* 2. 將字體套用到 Streamlit 應用程式的所有文字元件 */
        /* [class*="st-"] 選擇所有 Streamlit 相關的類別 */
        html, body, [class*="st-"] {
            font-family: 'Inter', sans-serif;
        }
        
        /* 由於 Inter 對於 CJK (中文、日文、韓文) 支援度不高，
           建議在 Inter 之後加入一個常用的中文字體作為備用字體，
           確保中文字符能夠正常且美觀地顯示。 
           我們使用：Inter, Microsoft YaHei (Windows), PingFang TC (Mac) */
        /* 如果你的應用程式以中文為主，建議使用以下備用方案： */
        html, body, [class*="st-"] {
            font-family: 'Inter', "Microsoft YaHei", "PingFang TC", sans-serif;
        }

        </style>
        """, 
        unsafe_allow_html=True
    )

# --- 2. Streamlit 介面與應用邏輯 ---

def main():
    # 初始化資料庫
    init_db()

    st.set_page_config(layout="wide", page_title="宅宅家族記帳本")

    # === 呼叫自訂字體設定：使用 Inter ===
    set_inter_font() 
    # ==================================

    st.title("宅宅家族記帳本")

    # --- 側邊欄：輸入區 ---
    with st.sidebar:
        st.header("🖊️ 新增交易紀錄")
        
        # 定義固定選項
        CATEGORIES = ['飲食', '交通', '家庭', '娛樂', '教育', '收入', '其他']
        TRANSACTION_TYPES = ['支出', '收入']

        with st.form("transaction_form"):
            # 1. 交易類型
            trans_type = st.radio("交易類型", TRANSACTION_TYPES, index=0)
            
            # 2. 金額
            amount = st.number_input("金額 (新台幣)", min_value=0.01, format="%.2f", step=10.0)
            
            # 3. 類別
            category_options = CATEGORIES.copy()
            # 根據交易類型調整類別選項
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
                # 轉換交易類型和日期格式以符合資料庫
                db_type = 'Income' if trans_type == '收入' else 'Expense'
                db_date = date.strftime('%Y-%m-%d')
                
                add_transaction(db_date, category, amount, db_type, note)
                st.success(f"已新增一筆 {trans_type} 紀錄：{category} {amount} 元！")


    # --- 主畫面：儀表板與紀錄 ---
    
    # 獲取所有交易數據
    df = get_all_transactions()
    
    if df.empty:
        st.warning("目前還沒有交易紀錄，請從左側新增第一筆紀錄！")
        return

    # 篩選月份：讓使用者可以選擇要查看哪個月份的資料
    df['month_year'] = df['date'].dt.to_period('M')
    available_months = df['month_year'].unique().astype(str)
    selected_month = st.selectbox("📅 選擇查看月份", available_months, index=0)
    
    df_filtered = df[df['month_year'] == selected_month]
    
    st.header(f"{selected_month} 月份總結")
    
    # 3.1. 總覽儀表板
    
    col1, col2, col3 = st.columns(3)
    
    # 計算總收入
    total_income = df_filtered[df_filtered['type'] == 'Income']['amount'].sum()
    col1.metric("總收入 (綠色)", f"NT$ {total_income:,.0f}")
    
    # 計算總支出
    total_expense = df_filtered[df_filtered['type'] == 'Expense']['amount'].sum()
    col2.metric("總支出 (紅色)", f"NT$ {total_expense:,.0f}")
    
    # 計算淨現金流
    net_flow = total_income - total_expense
    col3.metric("淨現金流 (藍色)", f"NT$ {net_flow:,.0f}")

    st.markdown("---")
    
    # 3.2. 支出類別圓餅圖
    st.header("支出類別分佈")
    
    expense_data = df_filtered[df_filtered['type'] == 'Expense'].groupby('category')['amount'].sum().reset_index()
    
    if not expense_data.empty and total_expense > 0:
        # 使用 Streamlit 內建的圖表功能
        st.bar_chart(expense_data.set_index('category')) 
        # 註：Streamlit 支援 Plotly/Altair 等更美觀的圓餅圖，但 Bar Chart 更易於實作。
        st.dataframe(expense_data.rename(columns={'category': '類別', 'amount': '支出金額'}))
    else:
        st.info("本月無支出紀錄或總支出為零，無法顯示支出分佈圖。")

    st.markdown("---")

    # 3.3. 交易紀錄區
    st.header("完整交易紀錄")
    
    # 選擇要顯示的欄位
    display_df = df_filtered[['date', 'category', 'amount', 'type', 'note']].copy()
    display_df.rename(columns={
        'date': '日期', 
        'category': '類別', 
        'amount': '金額', 
        'type': '類型', 
        'note': '備註'
    }, inplace=True)
    
    st.dataframe(display_df, use_container_width=True)


if __name__ == "__main__":
    main()