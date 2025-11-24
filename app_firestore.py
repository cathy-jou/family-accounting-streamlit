import streamlit as st
import pandas as pd
import datetime
import altair as alt
from google.cloud import firestore
import uuid 

# --- 0. 配置與變數 ---
DEFAULT_BG_COLOR = "#f8f9fa"
RECORD_COLLECTION_NAME = "records"       # 交易紀錄 Collection 名稱
BALANCE_COLLECTION_NAME = "account_status" # 餘額 Collection 名稱
BALANCE_DOC_ID = "current_balance"       # 總餘額文件 ID

# 📌 修改：簡化支出類別 (食衣住行育樂)
CATEGORIES = {
    '收入': ['薪資', '投資收益', '禮金', '其他收入'],
    '支出': ['食', '衣', '住', '行', '育樂', '其他']
}

# --- 1. Streamlit 介面設定 ---
def set_ui_styles():
    """注入客製化 CSS，設定字體、簡約背景色和排版"""
    css = f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        html, body, [class*="st-"] {{
            font-family: 'Inter', "PingFang TC", "Microsoft YaHei", sans-serif;
            font-size: 15px;
        }}
        h1 {{ font-weight: 700; color: #343a40; }}
        h2 {{
            font-size: 1.5rem; font-weight: 600; color: #495057;
            border-bottom: 2px solid #e9ecef; padding-bottom: 0.5rem; margin-top: 2rem;
        }}
        /* 側邊欄樣式 */
        [data-testid="stSidebar"] {{
            background-color: #ffffff;
            border-right: 1px solid #e9ecef;
        }}
        /* 按鈕樣式 */
        .stButton>button {{
            width: 100%; border-radius: 0.5rem; font-weight: 600;
        }}
        /* 輸入框樣式 */
        .stTextInput, .stNumberInput, .stDateInput, .stSelectbox {{
            border-radius: 0.5rem;
        }}
        /* 資訊卡片樣式 */
        .info-card {{
            background-color: #ffffff; padding: 1.5rem; border-radius: 0.5rem;
            text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #e9ecef;
        }}
        .info-card h4 {{ color: #6c757d; font-size: 1rem; margin-bottom: 0.5rem; }}
        .info-card p {{ font-size: 1.8rem; font-weight: 700; color: #343a40; margin: 0; }}
        
        /* 調整快速記帳區塊的緊湊度 */
        [data-testid="stHorizontalBlock"] > div {{
            vertical-align: bottom;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# --- 2. Firestore 連線與認證 ---

@st.cache_resource
def get_firestore_client():
    """初始化並返回 Firestore 客戶端"""
    try:
        if 'firestore' in st.secrets:
             # 優先從 secrets 讀取 (Streamlit Cloud)
             db = firestore.Client.from_service_account_info(dict(st.secrets['firestore']))
        elif 'private_key' in st.secrets:
             # 相容舊格式
             db = firestore.Client.from_service_account_info(dict(st.secrets))
        else:
            # 本地環境 (需設定 GOOGLE_APPLICATION_CREDENTIALS)
            db = firestore.Client()
        return db
    except Exception as e:
        st.error(f"Firestore 初始化失敗: {e}")
        return None

def get_user_id():
    """獲取用戶 ID (固定 ID)"""
    if 'user_id' not in st.session_state:
        st.session_state['user_id'] = "family_budget_user_v2"
    return st.session_state['user_id']

# --- 3. 數據操作函數 (CRUD) ---

def get_balance(db):
    """從 Firestore 獲取當前總餘額"""
    user_id = get_user_id()
    try:
        doc_ref = db.collection(BALANCE_COLLECTION_NAME).document(user_id) \
                    .collection(RECORD_COLLECTION_NAME).document(BALANCE_DOC_ID)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('total_balance', 0.0)
        return 0.0
    except Exception as e:
        st.error(f"獲取總餘額失敗: {e}")
        return 0.0

def update_balance(db, amount, record_type):
    """更新 Firestore 中的總餘額"""
    user_id = get_user_id()
    try:
        balance_ref = db.collection(BALANCE_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME).document(BALANCE_DOC_ID)
        
        @firestore.transactional
        def update_in_transaction(transaction):
            snapshot = balance_ref.get(transaction=transaction)
            old_balance = snapshot.get('total_balance') if snapshot.exists else 0.0

            if record_type == '收入':
                new_balance = old_balance + amount
            elif record_type == '支出':
                new_balance = old_balance - amount
            else:
                return 

            transaction.set(balance_ref, {'total_balance': new_balance})

        transaction = db.transaction()
        update_in_transaction(transaction)
    except Exception as e:
        st.error(f"更新總餘額失敗: {e}")

def add_record(db, record_data):
    """向 Firestore 新增一筆交易紀錄並更新餘額"""
    user_id = get_user_id()
    try:
        records_ref = db.collection(RECORD_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME)
        
        # 轉換日期格式
        record_date_time = datetime.datetime.combine(record_data['date'], datetime.time.min)

        data_to_save = {
            'timestamp': firestore.SERVER_TIMESTAMP,
            'date': record_date_time,
            'type': record_data['type'], 
            'category': record_data['category'], 
            'amount': record_data['amount'],
            'note': record_data['note'],
            'user_id': user_id
        }

        records_ref.add(data_to_save)
        update_balance(db, record_data['amount'], record_data['type'])
        
        st.toast("紀錄新增成功！", icon="✅")

    except Exception as e:
        st.error(f"新增紀錄失敗: {e}")

@st.cache_data(ttl=5) 
def get_all_records(db, user_id):
    """從 Firestore 獲取所有交易紀錄並返回 DataFrame"""
    try:
        records_ref = db.collection(RECORD_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME)
        
        docs = records_ref.order_by('date', direction=firestore.Query.DESCENDING).stream()
        
        data = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id
            
            # 處理日期
            record_date = record.get('date')
            if isinstance(record_date, firestore.Timestamp):
                record['date'] = record_date.to_datetime().date()
            elif isinstance(record_date, datetime.datetime):
                record['date'] = record_date.date()
            elif not isinstance(record_date, datetime.date):
                record['date'] = datetime.date(1970, 1, 1)

            data.append(record)
            
        if not data:
            return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])
        
        df = pd.DataFrame(data)
        df = df.sort_values(by=['date', 'timestamp'], ascending=[False, False])
        return df
        
    except Exception as e:
        st.error(f"獲取所有紀錄失敗: {e}")
        return pd.DataFrame(columns=['id', 'date', 'type', 'category', 'amount', 'note', 'timestamp'])

def delete_record(db, user_id, record_id, record_type, record_amount):
    """刪除紀錄並反向更新餘額"""
    try:
        records_ref = db.collection(RECORD_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME)
        
        records_ref.document(record_id).delete()
        
        reverse_type = '支出' if record_type == '收入' else '收入'
        update_balance(db, record_amount, reverse_type)
        
        st.toast("紀錄已刪除！", icon="🗑️")
        st.rerun()

    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")

def convert_df_to_csv(df):
    """將 DataFrame 轉換為 CSV"""
    return df.to_csv(index=False).encode('utf-8')

# --- 4. UI 組件與頁面 ---

# 📌 修正：快速記帳組件 (用於首頁)
def display_quick_entry(db, user_id):
    st.markdown("### 🚀 快速記帳")
    
    # 使用 5 欄佈局
    col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 2, 2, 1])
    
    # 1. 類型
    q_type = col1.selectbox("類型", list(CATEGORIES.keys()), key='q_type', label_visibility="collapsed")
    
    # 2. 類別 (依據需求：改為選擇類別，取代銀行帳戶)
    q_categories = CATEGORIES.get(q_type, [])
    q_category = col2.selectbox("類別", q_categories, key='q_cat', label_visibility="collapsed")
    
    # 3. 金額
    q_amount = col3.number_input("金額", min_value=0.0, step=1.0, placeholder="金額", key='q_amt', label_visibility="collapsed", format="%.0f")
    
    # 4. 備註
    q_note = col4.text_input("備註", placeholder="備註 (選填)", key='q_note', label_visibility="collapsed")
    
    # 5. 儲存
    if col5.button("儲存", key='q_save', type="primary"):
        if q_amount > 0:
            data = {
                'date': datetime.date.today(),
                'type': q_type,
                'category': q_category,
                'amount': q_amount,
                'note': q_note
            }
            add_record(db, data)
            st.rerun()
        else:
            st.toast("請輸入有效金額", icon="⚠️")

# 首頁：儀表板
def page_dashboard(db, user_id):
    # 1. 快速記帳區 (整合在首頁最上方)
    display_quick_entry(db, user_id)
    
    st.markdown("---")
    
    # 2. 數據概覽
    df_records = get_all_records(db, user_id)
    current_balance = get_balance(db)
    
    total_income = df_records[df_records['type'] == '收入']['amount'].sum()
    total_expense = df_records[df_records['type'] == '支出']['amount'].sum()
    
    st.markdown("### 📊 資產概況")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="info-card">
            <h4>當前總餘額</h4>
            <p style="color: #0d6efd;">NT$ {current_balance:,.0f}</p>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
        <div class="info-card">
            <h4>總收入</h4>
            <p style="color: #198754;">+ {total_income:,.0f}</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="info-card">
            <h4>總支出</h4>
            <p style="color: #dc3545;">- {total_expense:,.0f}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # 3. 簡單圖表 (支出分佈)
    st.markdown("### 📉 支出分析")
    expense_data = df_records[df_records['type'] == '支出']
    
    if not expense_data.empty:
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            expense_by_cat = expense_data.groupby('category')['amount'].sum().reset_index()
            base = alt.Chart(expense_by_cat).encode(theta=alt.Theta("amount", stack=True))
            pie = base.markArc(outerRadius=100).encode(
                color=alt.Color("category", title="類別"),
                order=alt.Order("amount", sort="descending"),
                tooltip=["category", "amount"]
            )
            st.altair_chart(pie, use_container_width=True)
            
        with col_chart2:
            # 最近 5 筆紀錄
            st.markdown("##### 最近交易")
            st.dataframe(
                df_records[['date', 'category', 'amount', 'type']].head(5),
                hide_index=True,
                use_container_width=True
            )
    else:
        st.info("尚無支出紀錄。")

# 詳細新增頁面
def page_add_record(db, user_id):
    st.markdown("## 📝 詳細新增紀錄")
    
    with st.form("full_record_form"):
        col1, col2 = st.columns(2)
        r_type = col1.radio("類型", list(CATEGORIES.keys()), horizontal=True)
        r_cat = col2.selectbox("類別", CATEGORIES[r_type])
        
        col3, col4 = st.columns(2)
        r_amt = col3.number_input("金額", min_value=0.0, step=1.0, format="%.0f")
        r_date = col4.date_input("日期", datetime.date.today())
        
        r_note = st.text_area("備註")
        
        if st.form_submit_button("儲存", type="primary"):
            if r_amt > 0:
                data = {
                    'date': r_date, 'type': r_type, 'category': r_cat, 
                    'amount': r_amt, 'note': r_note
                }
                add_record(db, data)
                st.rerun()
            else:
                st.warning("請輸入金額")

# 交易紀錄列表頁面
def page_records_list(db, user_id):
    st.markdown("## 📜 完整交易紀錄")
    
    df = get_all_records(db, user_id)
    if df.empty:
        st.info("無紀錄")
        return

    # 下載
    csv = convert_df_to_csv(df)
    st.download_button("📥 下載 CSV", csv, "records.csv", "text/csv")
    
    st.markdown("---")

    # 列表標頭
    cols = st.columns([1.5, 1, 1, 0.8, 4, 1])
    headers = ["日期", "類別", "金額", "類型", "備註", "操作"]
    for col, h in zip(cols, headers):
        col.markdown(f"**{h}**")
        
    # 列表內容
    for idx, row in df.iterrows():
        with st.container():
            cols = st.columns([1.5, 1, 1, 0.8, 4, 1])
            cols[0].write(row['date'].strftime('%Y-%m-%d'))
            cols[1].write(row['category'])
            
            color = "green" if row['type'] == "收入" else "red"
            cols[2].markdown(f":{color}[{row['amount']:,.0f}]")
            
            cols[3].write(row['type'])
            cols[4].write(row['note'])
            
            if cols[5].button("🗑️", key=f"del_{row['id']}"):
                delete_record(db, user_id, row['id'], row['type'], row['amount'])

# 設定頁面 (僅保留餘額修正)
def page_settings(db, user_id):
    st.markdown("## ⚙️ 設定")
    st.warning("手動修改總餘額 (僅用於校正)")
    
    curr = get_balance(db)
    new_bal = st.number_input("設定新餘額", value=curr, format="%.0f")
    
    if st.button("更新餘額"):
        try:
            ref = db.collection(BALANCE_COLLECTION_NAME).document(user_id) \
                    .collection(RECORD_COLLECTION_NAME).document(BALANCE_DOC_ID)
            ref.set({'total_balance': new_val}) # 注意：這裡應使用 new_bal 變數
            # 修正變數名稱錯誤
            ref.set({'total_balance': float(new_bal)})
            st.success("已更新")
            st.rerun()
        except Exception as e:
            st.error(f"錯誤: {e}")

# --- 主程式 ---
def app():
    st.set_page_config(page_title="家庭記帳本", layout="wide", initial_sidebar_state="expanded")
    set_ui_styles()
    
    db = get_firestore_client()
    if not db: st.stop()
    user_id = get_user_id()
    
    # 側邊欄導航 (還原為 Radio)
    with st.sidebar:
        st.title("💰 記帳本")
        page = st.radio("導航", ["儀表板", "新增紀錄", "交易紀錄", "設定"])
        st.markdown("---")
        st.caption(f"User: {user_id}")

    # 頁面路由
    if page == "儀表板":
        page_dashboard(db, user_id)
    elif page == "新增紀錄":
        page_add_record(db, user_id)
    elif page == "交易紀錄":
        page_records_list(db, user_id)
    elif page == "設定":
        page_settings(db, user_id)

if __name__ == "__main__":
    app()