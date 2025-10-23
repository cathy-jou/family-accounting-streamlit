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
            border-bottom: 2px solid #e9ecef; /* 添加淺色下劃線 */
            padding-bottom: 5px;
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }}

        /* 主要按鈕顏色調整 */
        div.stButton > button:first-child {{
            background-color: #007bff; /* 藍色 */
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 15px;
            font-weight: 600;
            transition: background-color 0.2s;
        }}
        div.stButton > button:first-child:hover {{
            background-color: #0056b3;
        }}
        
        /* 避免日期欄位文字重疊 */
        [data-testid="stSidebar"] div.stRadio {{
            gap: 0.5rem; /* 縮小單選按鈕間距 */
        }}

        /* 表格標題行樣式 */
        .header-row {{
            display: flex; 
            font-weight: bold; 
            background-color: #e9ecef; 
            padding: 10px 0; 
            border-radius: 5px; 
            margin-top: 10px;
        }}
        
        /* 移除 Streamlit 預設的 padding，讓內容更緊湊 */
        .main > div {{
            padding-top: 2rem;
            padding-right: 1rem;
            padding-left: 1rem;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# --- 2. 數據庫初始化與連接 ---
@st.cache_resource(ttl=600)
def initialize_firestore():
    """
    初始化 Firestore 連接。
    使用 Streamlit secrets 來讀取服務帳戶憑證。
    """
    try:
        # 從 st.secrets 中取得 [firestore] 區塊的所有配置
        firestore_secrets = st.secrets.firestore
        
        # 使用 from_service_account_info 方法初始化 Firestore
        # 該方法可以直接接受 Streamlit secrets 讀取的字典
        db = firestore.Client.from_service_account_info(firestore_secrets)
        return db
        
    except KeyError as e:
        # 找不到 [firestore] 區塊或其內部某個 key
        st.error(f"❌ 無法加載 Firebase 配置：在 `.streamlit/secrets.toml` 中找不到 `[firestore]` 區塊或必要的配置 {e}。請確認檔案是否存在且配置正確。")
        st.stop()
    except Exception as e:
        # 處理其他連接錯誤 (如私鑰格式錯誤)
        st.error(f"❌ Firebase 連接錯誤：請檢查 `secrets.toml` 中的內容是否正確。詳細錯誤: {e}")
        st.stop()

# -----------------------------------------------------------
# Firestore 讀取/寫入函式 (包含錯誤處理)
# -----------------------------------------------------------

def get_current_balance(db):
    """從 Firestore 獲取當前餘額"""
    try:
        balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
        doc = balance_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0)
        else:
            # 如果文件不存在，則初始化為 0
            balance_ref.set({'balance': 0})
            return 0
    except Exception as e:
        st.error(f"讀取餘額失敗: {e}")
        return 0

def update_balance(db, amount, is_income, current_balance):
    """更新 Firestore 中的餘額"""
    try:
        new_balance = current_balance + amount if is_income else current_balance - amount
        
        balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
        balance_ref.set({'balance': new_balance})
        st.session_state.current_balance = new_balance # 更新 session state
        return True
    except Exception as e:
        st.error(f"更新餘額失敗: {e}")
        return False

def add_record(db, record_data):
    """新增交易紀錄到 Firestore"""
    try:
        # 使用 Firestore 內建的 ID
        record_ref = db.collection(RECORD_COLLECTION_NAME).document()
        # 將文件 ID 加入資料中以便後續刪除操作使用
        record_data['id'] = record_ref.id 
        record_ref.set(record_data)
        return True
    except Exception as e:
        st.error(f"新增交易紀錄失敗: {e}")
        return False

def delete_record(db, record_id, record_type, record_amount, current_balance):
    """刪除交易紀錄並反向更新餘額"""
    try:
        # 1. 刪除紀錄
        db.collection(RECORD_COLLECTION_NAME).document(record_id).delete()
        
        # 2. 反向更新餘額
        if record_type == '收入':
            # 刪除收入 => 餘額減少
            reverse_amount = -record_amount
        else:
            # 刪除支出 => 餘額增加
            reverse_amount = record_amount
            
        new_balance = current_balance + reverse_amount
        
        balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
        balance_ref.set({'balance': new_balance})
        st.session_state.current_balance = new_balance # 更新 session state
        
        st.success("✅ 紀錄已成功刪除並更新餘額！")
        # 觸發 Streamlit 重跑以更新顯示的紀錄
        st.rerun() 
        return True
    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")
        return False
        
def fetch_all_records(db):
    """從 Firestore 獲取所有交易紀錄並轉換為 DataFrame"""
    try:
        records_ref = db.collection(RECORD_COLLECTION_NAME)
        docs = records_ref.stream()
        
        data = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id # 確保獲取文件ID
            data.append(record)
            
        df = pd.DataFrame(data)
        
        # 確保日期是 datetime 對象，如果沒有紀錄，返回空 DataFrame
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values(by='date', ascending=False).reset_index(drop=True)
            
        return df
    except Exception as e:
        st.error(f"讀取交易紀錄失敗: {e}")
        return pd.DataFrame()

# -----------------------------------------------------------
# 主應用程式邏輯
# -----------------------------------------------------------

def main():
    set_ui_styles()
    st.title("💸 簡約家庭記帳本 (Firestore)")

    # 數據庫連接初始化 (包含錯誤處理)
    db = initialize_firestore()
    
    # Session State 初始化
    if 'current_balance' not in st.session_state:
        # 首次啟動時從 Firestore 讀取餘額
        st.session_state.current_balance = get_current_balance(db)
        
    # 獲取所有紀錄
    df_records = fetch_all_records(db)
    
    # --------------------------------------
    # 1. 餘額顯示
    # --------------------------------------
    
    st.markdown("## 💰 您的當前餘額")
    st.markdown(f"""
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; border: 1px solid #ced4da;">
        <h3 style="margin: 0; color: #495057;">總餘額</h3>
        <p style="font-size: 2.5rem; font-weight: 700; color: #007bff; margin-top: 5px;">
            NT$ {st.session_state.current_balance:,.0f}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # --------------------------------------
    # 2. 新增交易區
    # --------------------------------------

    st.header("新增交易紀錄")
    
    # 建立一個表單
    with st.form(key='transaction_form'):
        
        # 輸入區：日期、類型、金額
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            date = st.date_input("日期", datetime.date.today(), max_value=datetime.date.today())
        
        with col2:
            type_select = st.selectbox("類型", list(CATEGORIES.keys()))
            
        with col3:
            amount = st.number_input("金額 (NT$)", min_value=0, step=100, format="%d")

        # 輸入區：類別、備註
        category_options = CATEGORIES[type_select]
        col4, col5 = st.columns([1, 2])
        
        with col4:
            category = st.selectbox("類別", category_options)
            
        with col5:
            note = st.text_input("備註 (可選)", max_chars=100)

        # 提交按鈕
        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("💾 提交交易紀錄", type="primary")

        if submitted:
            if amount > 0:
                is_income = (type_select == '收入')
                
                # 1. 更新餘額
                if update_balance(db, amount, is_income, st.session_state.current_balance):
                    # 2. 新增交易紀錄
                    record_data = {
                        'date': date.strftime('%Y-%m-%d'),
                        'type': type_select,
                        'category': category,
                        'amount': amount,
                        'note': note,
                        'timestamp': datetime.datetime.now().isoformat()
                    }
                    if add_record(db, record_data):
                        st.success(f"✅ 成功新增 {type_select} {amount:,.0f} 元！")
                        st.rerun() # 重新運行以更新畫面
                    else:
                        # 如果紀錄新增失敗，考慮回滾餘額 (但這裡為簡潔性，暫不實作複雜回滾)
                        st.warning("⚠️ 餘額已更新，但紀錄寫入失敗。請手動檢查。")

            else:
                st.error("請輸入有效的金額！")

    # --------------------------------------
    # 3. 數據分析與紀錄顯示
    # --------------------------------------

    if not df_records.empty:
        # 3.1. 篩選控制項
        st.header("數據篩選")
        
        # 篩選月份的 Sidebar
        st.sidebar.title("📅 月份篩選")
        all_months = df_records['date'].dt.to_period('M').unique().sort_values(ascending=False)
        month_options = [m.strftime('%Y-%m') for m in all_months]
        month_options.insert(0, '所有月份')
        
        selected_month_str = st.sidebar.selectbox(
            "選擇要查看的月份:",
            options=month_options,
            key='month_selector'
        )
        
        # 過濾 DataFrame
        df_filtered = df_records.copy()
        if selected_month_str != '所有月份':
            selected_month = pd.to_datetime(selected_month_str).to_period('M')
            df_filtered = df_filtered[df_filtered['date'].dt.to_period('M') == selected_month]

        # 3.2. 支出分佈圓餅圖 (只顯示支出)
        df_expense = df_filtered[df_filtered['type'] == '支出']
        
        if not df_expense.empty and df_expense['amount'].sum() > 0:
            st.header(f"{selected_month_str} 支出分佈圖")
            
            # 將相同類別的支出加總
            df_pie = df_expense.groupby('category')['amount'].sum().reset_index()
            df_pie.rename(columns={'amount': '總金額', 'category': '類別'}, inplace=True)
            
            # 使用 Altair 建立圓餅圖
            # 1. 建立基礎圖表
            base = alt.Chart(df_pie).encode(
                theta=alt.Theta("總金額", stack=True)
            ).properties(
                title=f"{selected_month_str} 總支出: NT$ {df_expense['amount'].sum():,.0f}"
            )
            
            # 2. 建立弧形 (圓餅)
            pie = base.mark_arc(outerRadius=120, innerRadius=50).encode(
                color=alt.Color("類別"),
                order=alt.Order("總金額", sort="descending"),
                tooltip=["類別", "總金額", alt.Tooltip("總金額", format=".1%")] # 加入百分比的 Tooltip
            )
            
            # 3. 加入文字標籤
            text = base.mark_text(radius=140).encode(
                text=alt.Text("總金額", format="~s"), # 顯示金額 (簡化格式)
                order=alt.Order("總金額", sort="descending"),
                color=alt.value("black") 
            )
            
            # 4. 組合圖表並居中顯示
            chart = (pie + text).interactive()
            
            st.altair_chart(chart, use_container_width=True)
            
        else:
            if selected_month_str != '所有月份':
                 st.info(f"在 {selected_month_str} 內無支出紀錄或總支出為零，無法顯示支出分佈圖。")
            else:
                 st.info("目前無支出紀錄，無法顯示支出分佈圖。")

        st.markdown("---")

        # 3.3. 交易紀錄區 (新增刪除按鈕)
        st.header("完整交易紀錄")
        
        # 準備用於顯示和刪除的 DataFrame
        # 這裡需要從完整的 df_records 中取得交易細節用於反向計算餘額
        display_df = df_filtered[['date', 'category', 'amount', 'type', 'note', 'id']].copy()
        
        # 標題列 (使用 CSS)
        st.markdown(
            f"""
            <div class='header-row'>
                <div style='width: 11%; padding-left: 1rem;'>日期</div>
                <div style='width: 10%;'>類別</div>
                <div style='width: 10%;'>金額</div>
                <div style='width: 7%;'>類型</div>
                <div style='width: 52%;'>備註</div>
                <div style='width: 10%; text-align: center;'>操作</div>
            </div>
            """, unsafe_allow_html=True
        )
        
        # 數據列
        for index, row in display_df.iterrows():
            try:
                # 從完整的紀錄中獲取刪除所需的資訊
                # 確保我們傳遞給 delete_record 的是原始的金額和類型
                record_details_for_delete = df_records[df_records['id'] == row['id']].iloc[0].to_dict()
            except IndexError:
                # 如果找不到原始紀錄，則跳過，避免刪除時報錯
                st.error(f"找不到文件ID為 {row['id']} 的原始紀錄，可能已被刪除。")
                continue
                
            color = "#28a745" if row['type'] == '收入' else "#dc3545"
            amount_sign = "+" if row['type'] == '收入' else "-"
            
            # 使用 container 和 columns 創建行布局
            with st.container():
                # 調整 st.columns 比例，使備註欄位有足夠的空間
                # 比例: [日期 1.2, 類別 1, 金額 1, 類型 0.7, 備註 6, 操作 1] (總和 10.9)
                col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 6, 1])
                
                # 使用 st.write 顯示交易細節
                col_date.write(row['date'].strftime('%Y-%m-%d'))
                col_cat.write(row['category'])
                col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row['amount']:,.0f}</span>", unsafe_allow_html=True)
                col_type.write(row['type'])
                col_note.write(row['note']) # 備註內容
                
                # 刪除按鈕
                if col_btn_action.button("刪除", key=f"delete_{row['id']}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                    delete_record(
                        db=db,
                        record_id=row['id'],
                        record_type=record_details_for_delete['type'],
                        record_amount=record_details_for_delete['amount'],
                        current_balance=st.session_state.current_balance
                    )
    else:
        st.info("當前沒有任何交易紀錄。請在上方新增一筆紀錄。")


if __name__ == '__main__':
    main()
