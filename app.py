import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import concurrent.futures
import time
import plotly.graph_objects as go

# --- 網頁基本設定 ---
st.set_page_config(page_title="台美雙引擎量化雷達", page_icon="📈", layout="wide")

# --- Discord 推播模組 ---
def send_discord_webhook(notification_message):
    # 🟢 記得貼上你的專屬 Discord Webhook 網址
    webhook_url = '你的_DISCORD_WEBHOOK_網址_貼在這裡'
    try:
        requests.post(webhook_url, json={"content": notification_message})
    except:
        pass

# ==========================================
# 🧠 核心架構升級：快取記憶體 (Cache)
# ==========================================
# 加上這行魔法裝飾器，讓這段程式每天只會「真正執行」一次，存活 12 小時 (43200秒)
@st.cache_data(ttl=43200, show_spinner=False)
def load_all_market_data():
    target_stocks = []
    try:
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        tables = pd.read_html(requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).text)
        target_stocks.extend(tables[4]['Ticker'].tolist())
        
        twse_url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        twse_data = requests.get(twse_url).json()
        tw_stocks = [f"{item['Code']}.TW" for item in twse_data if len(item['Code']) == 4]
        target_stocks.extend(tw_stocks) 
    except:
        return pd.DataFrame()

    def get_raw_data(ticker):
        try:
            time.sleep(0.5) # 依然要有基本的安全煞車
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 🌟 重構：這裡「只負責抓資料」，不做任何大於小於的篩選淘汰！
            forward_pe = info.get('forwardPE', 0)
            roe = info.get('returnOnEquity', 0)
            ma_200 = info.get('twoHundredDayAverage', 0)
            ma_50 = info.get('fiftyDayAverage', 0)
            operating_cashflow = info.get('operatingCashflow', 0)
            
            api_growth = info.get('earningsGrowth')
            if api_growth is None or api_growth == 0:
                api_growth = info.get('earningsQuarterlyGrowth', 0)
                
            operating_margin = info.get('operatingMargins')
            if operating_margin is None or operating_margin == 0:
                operating_margin = info.get('profitMargins', 0) 
                
            if forward_pe and api_growth and roe and ma_200 and ma_50 and operating_margin:
                final_growth_rate = api_growth * 100
                if final_growth_rate > 0:
                    peg_ratio = forward_pe / final_growth_rate 
                    current_price = stock.history(period="1d")['Close'].iloc[-1]
                    
                    # 把原始數據全部存起來
                    return {
                        "股票代號": ticker,
                        "收盤價": round(current_price, 2),
                        "前瞻 PEG": round(peg_ratio, 2),
                        "成長率 (%)": round(final_growth_rate, 2),
                        "ROE (%)": round(roe * 100, 2),
                        "利潤率 (%)": round(operating_margin * 100, 2),
                        "季線": round(ma_50, 2),
                        "年線": round(ma_200, 2),
                        "營業現金流": operating_cashflow
                    }
        except:
            pass 
        return None

    raw_data_list = []
    # 派 4 個工人慢慢抓，反正一天只要等一次
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(get_raw_data, ticker) for ticker in target_stocks]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res is not None:
                raw_data_list.append(res)
                
    return pd.DataFrame(raw_data_list) # 回傳完整的全市場大表

# ==========================================
# 🎛️ 左側控制面板 (Sidebar)
# ==========================================
st.sidebar.header("⚙️ 嚴格篩選條件設定")
user_max_peg = st.sidebar.slider("⚖️ 前瞻 PEG 上限 (越低越便宜)", 0.1, 3.0, 1.0, 0.1)
user_min_growth = st.sidebar.slider("🚀 預估成長率下限 (%)", 0.0, 50.0, 15.0, 1.0)
user_min_roe = st.sidebar.slider("💰 ROE 下限 (%)", 0.0, 30.0, 15.0, 1.0)
user_min_margin = st.sidebar.slider("🏭 營業利益率下限 (%)", 0.0, 30.0, 15.0, 1.0)
st.sidebar.markdown("---")
user_require_cf = st.sidebar.checkbox("🛡️ 排除營業現金流為負的地雷股", value=True)

# ==========================================
# 主畫面 UI 與 瞬間篩選邏輯
# ==========================================
st.title("📈 台美雙引擎量化雷達 (極速版)")

# 用來記錄是否已經啟動過下載引擎
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False

if st.button("📥 1. 建立今日市場總表 (只需執行一次，耗時約 3~5 分鐘)", type="primary"):
    st.session_state.data_loaded = True

if st.session_state.data_loaded:
    with st.spinner("資料庫建立中... (若為今日首次點擊需較久時間，後續操作皆為 0.1 秒)"):
        df_market = load_all_market_data() # 呼叫快取函數
    
    st.success(f"✅ 成功載入 {len(df_market)} 檔完整財報數據！請任意拉動左側拉桿，享受瞬間篩選。")
    
    # 🌟 瞬間過濾法：直接在 DataFrame 上套用拉桿的條件
    mask = (
        (df_market['前瞻 PEG'] <= user_max_peg) &
        (df_market['成長率 (%)'] >= user_min_growth) &
        (df_market['ROE (%)'] >= user_min_roe) &
        (df_market['利潤率 (%)'] >= user_min_margin) &
        (df_market['收盤價'] > df_market['季線']) &
        (df_market['收盤價'] > df_market['年線'])
    )
    if user_require_cf:
         mask = mask & (df_market['營業現金流'] > 0)
         
    filtered_df = df_market[mask] # 瞬間得到結果！
    
    # --- 顯示區塊 ---
    st.subheader(f"🎯 篩選結果：共發現 {len(filtered_df)} 檔潛力飆股")
    
    if len(filtered_df) > 0:
        # 把不想在畫面上看到的雜訊欄位藏起來
        display_df = filtered_df.drop(columns=['季線', '年線', '營業現金流'])
        st.dataframe(display_df, use_container_width=True)
        
        # 獨立的 Discord 發送按鈕 (避免每拉一次拉桿就洗版 Discord)
        if st.button("📨 將目前名單發送至 Discord"):
            discord_msgs = [f"🎯 **{row['股票代號']}** | 💵 `{row['收盤價']}` | ⚖️ PEG: `{row['前瞻 PEG']}` | 🚀 成長: `{row['成長率 (%)']}%`" for index, row in filtered_df.iterrows()]
            send_discord_webhook("🏆 **【極速雷達：自訂條件掃描報告】**\n\n" + "\n".join(discord_msgs))
            st.toast("✅ 已成功發送至 Discord！")
            
        # 畫 K 線圖
        st.markdown("---")
        st.subheader("📊 達標標的走勢圖 (近半年)")
        tickers_list = filtered_df['股票代號'].tolist()
        selected_ticker = st.selectbox("請選擇要查看 K 線圖的股票：", tickers_list)
        
        if selected_ticker:
            hist_data = yf.Ticker(selected_ticker).history(period="6mo")
            if not hist_data.empty:
                hist_data['50MA'] = hist_data['Close'].rolling(window=50).mean()
                hist_data['200MA'] = hist_data['Close'].rolling(window=200).mean()
                
                fig = go.Figure(data=[go.Candlestick(x=hist_data.index,
                                open=hist_data['Open'], high=hist_data['High'],
                                low=hist_data['Low'], close=hist_data['Close'], name="K線")])
                fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['50MA'], mode='lines', name='季線 (50MA)', line=dict(color='#00BFFF', width=1.5)))
                fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['200MA'], mode='lines', name='年線 (200MA)', line=dict(color='#FF4500', width=1.5)))
                
                fig.update_layout(title=f"{selected_ticker} 近半年走勢與均線", yaxis_title="股價", template="plotly_dark", xaxis_rangeslider_visible=False, height=500)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("💡 在目前的嚴格條件下沒有標的過關。請試著放寬左側的條件。")
else:
    st.info("👈 請先點擊上方的「建立今日市場總表」按鈕來初始化資料庫。")