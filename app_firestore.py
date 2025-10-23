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

# 預設類別清單
CATEGORIES = {
    "收入": ["薪水", "獎金", "投資收益", "其他收入"],
    "支出": ["餐飲", "交通", "生活用品", "娛樂", "教育", "醫療", "房租/房貸", "其他支出"]
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
            border-bottom: 2px solid #e9ecef;
            padding-bottom: 0.5rem;
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }}

        /* 讓 Streamlit 的 input/select/button 更有現代感 */
        div.stButton > button:first-child {{
            background-color: #007bff;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 5px;
            font-weight: 600;
            transition: background-color 0.3s;
        }}
        div.stButton > button:first-child:hover {{
            background-color: #0056b3;
        }}

        /* 次要按鈕 (刪除) */
        div.stButton button[data-testid*="stButton-secondary"] {{
            background-color: #dc3545;
            color: white;
            padding: 5px 10px;
        }}
        div.stButton button[data-testid*="stButton-secondary"]:hover {{
            background-color: #c82333;
        }}
        
        /* 調整 Streamlit 警告/資訊框的圓角 */
        .stAlert {{
            border-radius: 8px;
        }}

        /* 覆寫背景顏色 */
        .main {{ background-color: {DEFAULT_BG_COLOR}; }}
        [data-testid="stAppViewContainer"] {{ background-color: {DEFAULT_BG_COLOR}; }}
        section[data-testid="stSidebar"] {{ background-color: #ffffff; }}

        /* 讓文字在欄位內換行，避免備註欄位溢出 */
        .stMarkdown div p {{
            word-wrap: break-word;
            white-space: normal;
        }}
        
        /* 隱藏 Streamlit 的標頭和腳註 */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}
        </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# --- 2. Firestore 操作函式 (簡化為直接使用 try/except) ---

def initialize_firestore_and_auth():
    """初始化 Firebase 並處理認證"""
    # 讀取全局變數
    try:
        firebase_config = st.secrets["firebase"]
    except KeyError:
        st.error("錯誤：找不到 Firebase 配置。請確保在 Streamlit Secrets 中配置了 'firebase' 區塊。")
        return None, None, None

    # 初始化 Firestore
    try:
        db = firestore.Client.from_service_account_info(firebase_config)
        # 在 Streamlit 中，我們假設用戶是透過外部認證機制（例如 Canvas）登入的。
        # 這裡不執行實際的登入，而是使用一個固定的或模擬的用戶 ID。
        # 實際應用中，您會使用 Streamlit Components 或其他機制獲取真實的用戶 ID。
        user_id = "demo_user_001" 
        return db, user_id
    except Exception as e:
        st.error(f"Firestore 初始化失敗：{e}")
        return None, None


def get_current_balance(db, user_id):
    """獲取用戶的當前餘額，如果不存在則創建"""
    doc_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
    try:
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('balance', 0)
        else:
            # 文件不存在，初始化為 0
            doc_ref.set({'balance': 0, 'user_id': user_id, 'last_updated': firestore.SERVER_TIMESTAMP})
            return 0
    except Exception as e:
        st.error(f"獲取餘額失敗：{e}")
        return 0

def update_balance(db, user_id, amount_change):
    """原子性地更新餘額"""
    doc_ref = db.collection(BALANCE_COLLECTION_NAME).document(BALANCE_DOC_ID)
    try:
        db.transaction().run(lambda transaction: _update_balance_transaction(transaction, doc_ref, amount_change))
        st.session_state['current_balance'] += amount_change # 更新 session state
        st.toast("餘額更新成功！", icon='💸')
        return True
    except Exception as e:
        st.error(f"餘額更新失敗：{e}")
        return False

def _update_balance_transaction(transaction, doc_ref, amount_change):
    """用於交易的餘額更新邏輯"""
    snapshot = doc_ref.get(transaction=transaction)
    new_balance = snapshot.get('balance', 0) + amount_change
    transaction.set(doc_ref, {'balance': new_balance, 'last_updated': firestore.SERVER_TIMESTAMP}, merge=True)

def add_record(db, user_id, record):
    """添加新的交易紀錄"""
    try:
        record['id'] = str(uuid.uuid4()) # 為 Streamlit 內部操作添加一個前端 ID
        record['user_id'] = user_id
        doc_ref = db.collection(RECORD_COLLECTION_NAME).document(record['id'])
        doc_ref.set(record)
        st.toast(f"{record['type']} 紀錄添加成功！", icon='🎉')
        return True
    except Exception as e:
        st.error(f"添加紀錄失敗：{e}")
        return False

def delete_record(db, user_id, record_id, record_type, record_amount, current_balance):
    """刪除交易紀錄並反向更新餘額"""
    try:
        # 1. 刪除紀錄
        db.collection(RECORD_COLLECTION_NAME).document(record_id).delete()

        # 2. 計算餘額變動量
        # 刪除收入: 餘額減少 amount
        # 刪除支出: 餘額增加 amount
        amount_change = 0
        if record_type == '收入':
            amount_change = -record_amount
        elif record_type == '支出':
            amount_change = record_amount
        
        # 3. 更新餘額
        update_balance(db, user_id, amount_change)

        st.toast("紀錄已刪除！餘額已更新。", icon='🗑️')
        return True
    except Exception as e:
        st.error(f"刪除紀錄失敗：{e}")
        return False


def get_all_records(db, user_id):
    """獲取用戶的所有交易紀錄並轉換為 DataFrame"""
    try:
        docs = db.collection(RECORD_COLLECTION_NAME).where('user_id', '==', user_id).stream()
        records = []
        for doc in docs:
            record = doc.to_dict()
            record['id'] = doc.id
            # 確保 'date' 欄位是 datetime.date 物件
            if isinstance(record.get('date'), firestore.DocumentReference):
                 # 這裡可能需要根據您的實際存儲方式調整
                 pass
            elif isinstance(record.get('date'), datetime.datetime):
                record['date'] = record['date'].date()
            elif isinstance(record.get('date'), datetime.date):
                pass
            else:
                # 如果是字串或其他格式，嘗試轉換
                try:
                    record['date'] = datetime.datetime.strptime(str(record['date']), '%Y-%m-%d').date()
                except:
                    record['date'] = datetime.date.today() # 失敗則使用今天日期
            records.append(record)
            
        if not records:
            return pd.DataFrame(columns=['id', 'date', 'category', 'amount', 'type', 'note'])

        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']) # 轉換為 pandas datetime
        df = df.sort_values(by='date', ascending=False).reset_index(drop=True)
        return df

    except Exception as e:
        st.error(f"獲取交易紀錄失敗：{e}")
        return pd.DataFrame(columns=['id', 'date', 'category', 'amount', 'type', 'note'])


# --- 3. 介面主邏輯 ---
def main():
    # 1. 初始化
    set_ui_styles()
    st.title("家庭簡易記帳本")
    
    db, user_id = initialize_firestore_and_auth()
    if not db:
        st.stop()
    
    # Session State 初始化
    if 'current_balance' not in st.session_state:
        st.session_state['current_balance'] = get_current_balance(db, user_id)
    if 'category_options' not in st.session_state:
        st.session_state['category_options'] = CATEGORIES['支出'] # 預設顯示支出類別


    # 2. 餘額顯示
    st.markdown(f"**當前帳戶餘額：** <span style='font-size: 2.2rem; font-weight: 700; color: #007bff;'>NT$ {st.session_state['current_balance']:,.0f}</span>", unsafe_allow_html=True)
    st.markdown("---")

    # 3. 交易新增區
    st.header("新增交易紀錄")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        record_type = st.radio("選擇類型", options=["支出", "收入"], index=0, horizontal=True)
    
    with col2:
        # 根據類型更新類別選項
        st.session_state['category_options'] = CATEGORIES[record_type]
        category = st.selectbox("選擇類別", options=st.session_state['category_options'], index=0)

    # 交易細節輸入
    col3, col4, col5 = st.columns([1, 1, 1])
    with col3:
        amount = st.number_input("金額 (NT$)", min_value=1, value=100, step=10, format="%d")
    with col4:
        date = st.date_input("日期", value=datetime.date.today())
    with col5:
        # 由於 Streamlit 的 session state 已經儲存了 current_balance，無需從 firestore 再次獲取
        note = st.text_input("備註 (選填)", max_chars=100)
    
    if st.button("確認新增", key="add_record_btn", type="primary"):
        if amount <= 0:
            st.warning("金額必須大於 0。")
        else:
            new_record = {
                'date': date.strftime('%Y-%m-%d'), # 存儲為 ISO 格式字串
                'category': category,
                'amount': amount,
                'type': record_type,
                'note': note,
                # user_id 會在 add_record 函數中添加
            }
            
            # 計算餘額變動量
            amount_change = amount if record_type == '收入' else -amount
            
            # 執行操作
            if add_record(db, user_id, new_record):
                update_balance(db, user_id, amount_change)
                st.rerun() # 重新執行應用程式以刷新數據和餘額

    st.markdown("---")

    # 4. 數據展示與分析區
    st.header("數據分析與篩選")
    
    # 4.1. 數據獲取
    df_records = get_all_records(db, user_id)
    
    # 處理空數據情況
    if df_records.empty:
        st.info("目前尚無交易紀錄。請先新增一筆紀錄。")
        return # 停止執行後續的分析和顯示邏輯

    # 4.2. 篩選控制
    with st.expander("篩選選項", expanded=True):
        col_start, col_end = st.columns(2)
        
        min_date = df_records['date'].min().date()
        max_date = df_records['date'].max().date()
        
        with col_start:
            start_date = st.date_input("開始日期", value=min_date, min_value=min_date, max_value=max_date)
        with col_end:
            end_date = st.date_input("結束日期", value=max_date, min_value=min_date, max_value=max_date)
        
        filter_type = st.selectbox("篩選類型", options=["所有", "支出", "收入"], index=0)

    # 根據篩選條件過濾數據
    df_filtered = df_records[
        (df_records['date'].dt.date >= start_date) & 
        (df_records['date'].dt.date <= end_date)
    ]
    
    if filter_type != "所有":
        df_filtered = df_filtered[df_filtered['type'] == filter_type]

    # 4.3. 總結統計
    st.subheader("統計摘要")
    
    total_income = df_filtered[df_filtered['type'] == '收入']['amount'].sum()
    total_expense = df_filtered[df_filtered['type'] == '支出']['amount'].sum()
    net_flow = total_income - total_expense
    
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    
    col_stat1.metric("總收入", f"NT$ {total_income:,.0f}", delta=f"淨流動：NT$ {net_flow:,.0f}" if net_flow > 0 else None, delta_color="normal")
    col_stat2.metric("總支出", f"NT$ {total_expense:,.0f}", delta=f"淨流動：NT$ {net_flow:,.0f}" if net_flow < 0 else None, delta_color="inverse")
    col_stat3.metric("淨流動", f"NT$ {net_flow:,.0f}", delta_color="off")
    
    st.markdown("---")

    # 4.4. 支出分佈圖 (僅針對支出)
    st.subheader("選定範圍內各類別支出分佈")
    
    df_expense = df_filtered[df_filtered['type'] == '支出']
    
    if not df_expense.empty and total_expense > 0:
        # 1. 彙總數據
        df_category_sum = df_expense.groupby('category')['amount'].sum().reset_index()
        df_category_sum.rename(columns={'amount': '總支出'}, inplace=True)
        
        # 2. 計算比例
        df_category_sum['比例'] = df_category_sum['總支出'] / total_expense
        
        # 3. 建立圓餅圖
        pie = alt.Chart(df_category_sum).mark_arc(outerRadius=120, innerRadius=50).encode(
            # 角度: 使用總支出
            theta=alt.Theta("總支出", stack=True),
            # 顏色: 根據類別
            color=alt.Color("category", title="類別"),
            # 工具提示: 類別、總支出、比例
            tooltip=[
                "category",
                alt.Tooltip("總支出", format=',.0f', title='總支出 (NT$)'),
                alt.Tooltip("比例", format='.1%', title='佔比')
            ]
        ).properties(
            title="選定範圍內各類別支出金額分佈"
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

    # 4.5. 交易紀錄區 (新增刪除按鈕)
    st.header("完整交易紀錄")
    
    # 準備用於顯示和刪除的 DataFrame
    display_df = df_filtered[['date', 'category', 'amount', 'type', 'note', 'id']].copy()
    
    if display_df.empty:
        st.info("選定範圍內無交易紀錄。**請調整篩選條件。**")
        return
    
    # 標題列
    st.markdown(
        f"""
        <div style='display: flex; font-weight: bold; background-color: #e9ecef; padding: 10px 0; border-radius: 5px; margin-top: 10px;'>
            <div style='width: 15%; padding-left: 1rem;'>日期</div>
            <div style='width: 10%;'>類別</div>
            <div style='width: 10%;'>金額</div>
            <div style='width: 8%;'>類型</div>
            <div style='width: 47%;'>備註</div>
            <div style='width: 10%; text-align: center;'>操作</div>
        </div>
        """, unsafe_allow_html=True
    )
    
    # 數據列
    for index, row in display_df.iterrows():
        # 為了刪除時能反向更新餘額，需要獲取原始紀錄的 type 和 amount
        try:
            record_details_for_delete = df_records[df_records['id'] == row['id']].iloc[0].to_dict()
        except IndexError:
            # 避免找不到 ID 的情況
            continue 
        
        color = "#28a745" if row['type'] == '收入' else "#dc3545"
        amount_sign = "+" if row['type'] == '收入' else "-"
        
        with st.container():
            # 修正點：調整 st.columns 比例，增加備註欄位的權重 (5)
            # 舊比例可能為 [1.2, 1, 1, 0.7, 3, 0.8] (總和 7.7) 導致備註溢出
            # 新比例為 [1.2, 1, 1, 0.7, 5, 1] (總和 9.9) 增加備註空間
            col_date, col_cat, col_amount, col_type, col_note, col_btn_action = st.columns([1.2, 1, 1, 0.7, 5, 1])
            
            # 使用 st.write 顯示交易細節
            col_date.write(row['date'].strftime('%Y-%m-%d'))
            col_cat.write(row['category'])
            col_amount.markdown(f"<span style='font-weight: bold; color: {color};'>{amount_sign} {row['amount']:,.0f}</span>", unsafe_allow_html=True)
            col_type.write(row['type'])
            # 備註內容，給予更多空間避免重疊
            col_note.write(row['note']) 
            
            # 刪除按鈕
            if col_btn_action.button("刪除", key=f"delete_{row['id']}", type="secondary", help="刪除此筆交易紀錄並更新餘額"):
                delete_record(
                    db=db,
                    user_id=user_id,
                    record_id=row['id'],
                    record_type=record_details_for_delete['type'],
                    record_amount=record_details_for_delete['amount'],
                    current_balance=st.session_state['current_balance']
                )
                st.rerun() # 重新執行以刷新列表和餘額

if __name__ == "__main__":
    main()
