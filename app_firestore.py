import streamlit as st
import pandas as pd
import datetime
import altair as alt
from google.cloud import firestore
import uuid 

# --- 0. 配置與變數 ---
DEFAULT_BG_COLOR = "#f8f9fa"
RECORD_COLLECTION_NAME = "records"       # 交易紀錄 Collection 名稱
BALANCE_COLLECTION_NAME = "account_status" # 餘額/狀態 Collection 名稱
BALANCE_DOC_ID = "current_balance"       # 總餘額文件 ID
BANK_ACCOUNTS_COLLECTION_NAME = "bank_accounts" # 銀行帳戶 Collection 名稱 (保留定義)

# 修改：簡化支出類別
CATEGORIES = {
    '收入': ['薪資', '投資收益', '禮金', '其他收入'],
    '支出': ['食', '衣', '住', '行', '育樂']
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
        
        /* 按鈕樣式 */
        .stButton>button {{
            width: 100%;
            border-radius: 0.5rem;
            font-weight: 600;
        }}
        
        /* 輸入框樣式 */
        .stTextInput, .stNumberInput, .stDateInput, .stSelectbox {{
            border-radius: 0.5rem;
        }}
        
        /* 調整表格細節行的排版 */
        [data-testid="stHorizontalBlock"] > div:nth-child(5) > div {{ 
            text-align: left !important;
        }}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# --- 2. Firestore 連線與認證 ---

@st.cache_resource
def get_firestore_client():
    """初始化並返回 Firestore 客戶端"""
    try:
        if 'private_key' in st.secrets:
            db = firestore.Client.from_service_account_info(dict(st.secrets))
        else:
            db = firestore.Client()
        return db
    except Exception as e:
        st.error(f"Firestore 客戶端初始化失敗: {e}")
        return None

def get_user_id():
    """獲取用戶 ID (使用固定 ID)"""
    if 'user_id' not in st.session_state:
        st.session_state['user_id'] = "family_budget_user"
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
        
        st.toast(f"總餘額已更新: {record_type} {amount:,.0f}。", icon="💰")
    except Exception as e:
        st.error(f"更新總餘額失敗: {e}")


def add_record(db, record_data):
    """向 Firestore 新增一筆交易紀錄並更新餘額"""
    user_id = get_user_id()
    try:
        records_ref = db.collection(RECORD_COLLECTION_NAME).document(user_id) \
                        .collection(RECORD_COLLECTION_NAME)
        
        # 將 date 轉換為 datetime 以便 Firestore 儲存
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
        
        st.success("紀錄新增成功！")

    except Exception as e:
        st.error(f"新增紀錄失敗: {e}")
        st.exception(e)


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
            
            # 處理 Firestore Timestamp 轉換
            record_date = record.get('date')
            if isinstance(record_date, firestore.Timestamp):
                record['date'] = record_date.to_datetime().date()
            elif isinstance(record_date, datetime.datetime):
                record['date'] = record_date.date()
            elif not isinstance(record_date, datetime.date):
                record['date'] = datetime.date(1970, 1, 1) # 預設值

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
        
        st.success(f"紀錄已刪除！")
        st.rerun()

    except Exception as e:
        st.error(f"刪除紀錄失敗: {e}")

# --- 4. 儀表板與視覺化組件 ---

def display_summary(df_records, current_balance):
    """顯示摘要指標"""
    total_income = df_records[df_records['type'] == '收入']['amount'].sum()
    total_expense = df_records[df_records['type'] == '支出']['amount'].sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🏡 當前總餘額", f"NT$ {current_balance:,.0f}")
    col2.metric("📈 總收入", f"NT$ {total_income:,.0f}")
    col3.metric("📉 總支出", f"NT$ {total_expense:,.0f}")

def display_charts(df_records):
    """顯示分析圖表"""
    st.subheader("📊 數據分析")
    
    if df_records.empty:
        st.info("沒有數據可供分析。")
        return

    # 1. 類別支出圓餅圖
    expense_data = df_records[df_records['type'] == '支出']
    
    if not expense_data.empty:
        expense_by_category = expense_data.groupby('category')['amount'].sum().reset_index()
        
        base = alt.Chart(expense_by_category).encode(theta=alt.Theta("amount", stack=True)).properties(title="支出類別分佈")
        pie = base.markArc(outerRadius=120).encode(
            color=alt.Color("category", title="類別"),
            order=alt.Order("amount", sort="descending"),
            tooltip=["category", "amount", alt.Tooltip("amount", format=".2f")]
        )
        text = base.markText(radius=140).encode(
            text=alt.Text("amount", format=".0f"),
            order=alt.Order("amount", sort="descending"),
            color=alt.value("black")
        )
        st.altair_chart(pie + text, use_container_width=True)
    else:
        st.info("沒有支出紀錄可供類別分析。")

    # 2. 每日收支趨勢圖
    df_records['day'] = pd.to_datetime(df_records['date']).dt.to_period('D')
    daily_summary = df_records.groupby(['day', 'type'])['amount'].sum().unstack(fill_value=0).reset_index()
    daily_summary['day'] = daily_summary['day'].dt.to_timestamp()

    if '收入' not in daily_summary.columns: daily_summary['收入'] = 0
    if '支出' not in daily_summary.columns: daily_summary['支出'] = 0

    daily_long = daily_summary.melt('day', var_name='Type', value_name='Amount')

    trend_chart = alt.Chart(daily_long).markLine().encode(
        x=alt.X('day', title='日期'),
        y=alt.Y('Amount', title='金額 (NT$)'),
        color=alt.Color('Type', scale=alt.Scale(domain=['收入', '支出'], range=['#28a745', '#dc3545'])),
        tooltip=['day', 'Type', 'Amount']
    ).properties(title='每日收支趨勢')
    
    st.altair_chart(trend_chart, use_container_width=True)

# --- 5. 交易紀錄列表 ---

def display_record_list(df_records, db, user_id):
    """顯示紀錄列表"""
    st.subheader("📚 交易紀錄明細")
    
    if df_records.empty:
        st.info("目前沒有交易紀錄。")
        return
        
    with st.container():
        col_date, col_cat, col_amount, col_type, col_note, col_btn = st.columns([1.2, 1, 1, 0.7, 6, 1])
        for col, title in zip([col_date, col_cat, col_amount, col_type, col_note, col_btn], 
                              ["**日期**", "**類別**", "**金額**", "**類型**", "**備註**", "**操作**"]):
            col.markdown(title)
        st.markdown("---\n", unsafe_allow_html=True)

    for index, row in df_records.iterrows():
        try:
            record_id = row['id']
            record_date = row['date']
            record_str = record_date.strftime('%Y-%m-%d') if isinstance(record_date, (datetime.date, datetime.datetime)) else "日期錯誤"
            
            color = "#28a745" if row['type'] == '收入' else "#dc3545"
            sign = "+" if row['type'] == '收入' else "-"
            
            with st.container():
                col_date, col_cat, col_amount, col_type, col_note, col_btn = st.columns([1.2, 1, 1, 0.7, 6, 1])
                
                col_date.write(record_str)
                col_cat.write(row['category'])
                col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{sign} {row['amount']:,.0f}</span>", unsafe_allow_html=True)
                col_type.write(row['type'])
                col_note.write(row['note'])
                
                if col_btn.button("刪除", key=f"del_{record_id}"):
                    delete_record(db, user_id, record_id, row['type'], row['amount'])
                    
        except Exception as e:
            st.error(f"顯示紀錄錯誤: {e}")

# --- 6. 輸入表單 ---

def display_record_input(db, user_id):
    """完整新增紀錄表單"""
    st.header("➕ 新增紀錄")

    with st.form(key='new_record_form'):
        col1, col2 = st.columns(2)
        
        record_type = col1.selectbox("交易類型", list(CATEGORIES.keys()), key='type_in')
        
        # 根據類型顯示類別 (包含支出: 食衣住行育樂)
        category = col2.selectbox("選擇類別", CATEGORIES.get(record_type, []), key='cat_in')
        
        amount = col1.number_input("金額 (NT$)", min_value=0.0, step=1.0, format="%.0f", key='amt_in')
        date = col2.date_input("日期", value="today", key='date_in')
        note = st.text_area("備註 (可選)", key='note_in')

        if st.form_submit_button("儲存紀錄", type="primary"):
            if amount > 0 and category:
                data = {
                    'date': date,
                    'type': record_type,
                    'category': category,
                    'amount': amount,
                    'note': note.strip()
                }
                add_record(db, data)
                st.rerun()
            else:
                st.warning("請輸入有效金額並選擇類別。")

def display_quick_entry_on_home(db, user_id):
    """首頁快速記帳 (已更新：移除銀行帳戶，改為選擇類別)"""
    st.subheader("🚀 快速記帳")
    
    # 使用 5 欄佈局
    col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 2, 2, 1])
    
    # 1. 類型
    q_type = col1.selectbox("類型", list(CATEGORIES.keys()), key='q_type', label_visibility="collapsed")
    
    # 2. 類別 (修改：這裡直接選擇類別，取代原本的銀行帳戶)
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

# --- 7. 其他設定頁面 ---

def display_set_initial_balance(db, user_id):
    """手動設定總餘額"""
    st.header("⚙️ 設定初始總餘額")
    st.warning("注意：此功能用於校正初始餘額。")

    current = get_balance(db)
    st.info(f"當前系統記錄餘額: NT$ {current:,.0f}")
    
    new_val = st.number_input("設定新餘額", value=current, step=100.0, format="%.0f")
    
    if st.button("更新餘額"):
        try:
            ref = db.collection(BALANCE_COLLECTION_NAME).document(user_id) \
                    .collection(RECORD_COLLECTION_NAME).document(BALANCE_DOC_ID)
            ref.set({'total_balance': new_val})
            st.success("餘額已更新！")
            st.rerun()
        except Exception as e:
            st.error(f"更新失敗: {e}")

# --- 主程式 ---

def app():
    st.set_page_config(page_title="家庭記帳本", layout="wide", initial_sidebar_state="auto")
    set_ui_styles()
    st.title("👨‍👩‍👧‍👦 雲端家庭記帳本")
    
    db = get_firestore_client()
    user_id = get_user_id()
    
    if not db: st.stop()
    
    # 使用 Tabs 分頁
    tab1, tab2, tab3, tab4 = st.tabs(["首頁", "記帳管理", "帳戶管理", "其他設定"])

    with tab1:
        display_quick_entry_on_home(db, user_id)
        st.markdown('---')
        df = get_all_records(db, user_id)
        bal = get_balance(db)
        display_summary(df, bal)
        st.markdown('---')
        display_charts(df)

    with tab2:
        display_record_input(db, user_id)
        st.markdown("---")
        df = get_all_records(db, user_id)
        display_record_list(df, db, user_id)

    with tab3:
        st.header("🏦 帳戶管理")
        st.info("此版本已簡化，專注於收支分類記帳。")

    with tab4:
        display_set_initial_balance(db, user_id)

    st.sidebar.markdown('---')
    st.sidebar.info(f"用戶 ID: `{user_id}`")

if __name__ == '__main__':
    app()