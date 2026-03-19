import streamlit as st
import yfinance as yf
import requests
import pandas as pd
import concurrent.futures
import time
import plotly.graph_objects as go # 畫圖神器

# --- 網頁基本設定 ---
st.set_page_config(page_title="台美雙引擎量化雷達", page_icon="📈", layout="wide")

# 🛡️ 網頁短期記憶：記錄上次掃描的時間 (冷卻防護)
if 'last_scan_time' not in st.session_state:
    st.session_state.last_scan_time = 0

# ==========================================
# 🎛️ 左側控制面板 (Sidebar)
# ==========================================
st.sidebar.header("⚙️ 嚴格篩選條件設定")
st.sidebar.write("拖曳下方拉桿，自訂你的雷達敏感度：")

user_max_peg = st.sidebar.slider("⚖️ 前瞻 PEG 上限 (越低越便宜)", 0.1, 3.0, 1.0, 0.1)
user_min_growth = st.sidebar.slider("🚀 預估成長率下限 (%)", 0.0, 50.0, 15.0, 1.0)
user_min_roe = st.sidebar.slider("💰 ROE 下限 (%)", 0.0, 30.0, 15.0, 1.0)
user_min_margin = st.sidebar.slider("🏭 營業利益率下限 (%)", 0.0, 30.0, 15.0, 1.0)

st.sidebar.markdown("---")
user_require_cf = st.sidebar.checkbox("🛡️ 排除營業現金流為負的地雷股", value=True, help="強烈建議開啟！剔除帳面賺錢但實際上在燒現金的危險公司。")
st.sidebar.info("💡 提示：設定越嚴格，選出的股票越少，但勝率通常越高。")

# ==========================================
# 主畫面 UI 與 發送模組
# ==========================================
st.title("📈 台美雙引擎量化雷達")
st.write("透過左側面板調整你的專屬篩選條件，點擊下方按鈕啟動全市場掃描！")

def send_discord_webhook(notification_message):
    # 🟢 記得貼上你的專屬 Discord Webhook 網址
    webhook_url = 'https://discord.com/api/webhooks/1479141302892236853/FocNZI_HgmxLJomHSe70zyHqxULfuhKxNKb4lNMPv3zsTsRAYF2-xOfMvEdV95GFZ4Zx'
    try:
        requests.post(webhook_url, json={"content": notification_message})
    except:
        pass

# --- 核心分析模組 ---
def analyze_stock(ticker, max_peg, min_growth, min_roe, min_margin, require_cf):
    try:
        time.sleep(0.5) # 煞車系統
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # 現金流照妖鏡
        operating_cashflow = info.get('operatingCashflow')
        if require_cf and operating_cashflow is not None and operating_cashflow < 0:
            return None
        
        forward_pe = info.get('forwardPE', 0) 
        roe = info.get('returnOnEquity', 0)
        ma_200 = info.get('twoHundredDayAverage', 0)
        ma_50 = info.get('fiftyDayAverage', 0)
        
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
                
                if (peg_ratio <= max_peg) and (final_growth_rate >= min_growth) and \
                   (roe >= min_roe / 100) and (operating_margin >= min_margin / 100) and \
                   (current_price > ma_200) and (current_price > ma_50):
                    
                    return {
                        "股票代號": ticker,
                        "收盤價": round(current_price, 2),
                        "前瞻 PEG": round(peg_ratio, 2),
                        "成長率 (%)": round(final_growth_rate, 2),
                        "ROE (%)": round(roe * 100, 2),
                        "利潤率 (%)": round(operating_margin * 100, 2)
                    }
    except:
        pass 
    return None 

# --- 啟動按鈕與流程 ---
if st.button("🚀 依照左側條件，啟動全市場掃描", type="primary"):
    current_time = time.time()
    time_since_last_scan = current_time - st.session_state.last_scan_time
    
    if time_since_last_scan < 180:
        st.warning(f"⏳ 系統冷卻中！為保護您的 IP，請等待 {int(180 - time_since_last_scan)} 秒後再掃描。")
    else:
        st.session_state.last_scan_time = current_time
        
        with st.spinner('雷達全速運轉中，正在分析台美破千檔標的 (大約需 2 分鐘，請勿重新整理網頁)...'):
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
                st.error("名單抓取發生錯誤，請檢查網路連線。")

            passed_stocks = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(analyze_stock, ticker, user_max_peg, user_min_growth, user_min_roe, user_min_margin, user_require_cf) for ticker in target_stocks]
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res is not None:
                        passed_stocks.append(res)

        # --- 掃描結束後的顯示區塊 ---
        if len(passed_stocks) > 0:
            st.success(f"🎯 掃描完成！共發現 {len(passed_stocks)} 檔體質強健的潛力飆股！")
            
            # 1. 顯示表格
            df = pd.DataFrame(passed_stocks)
            st.dataframe(df, use_container_width=True)
            
            # 2. 顯示互動式 K 線圖
            st.markdown("---")
            st.subheader("📊 達標標的走勢圖 (近半年)")
            
            tickers_list = [s['股票代號'] for s in passed_stocks]
            selected_ticker = st.selectbox("請選擇要查看 K 線圖的股票：", tickers_list)
            
            if selected_ticker:
                with st.spinner(f"正在載入 {selected_ticker} 的歷史數據..."):
                    hist_data = yf.Ticker(selected_ticker).history(period="6mo")
                    if not hist_data.empty:
                        hist_data['50MA'] = hist_data['Close'].rolling(window=50).mean()
                        hist_data['200MA'] = hist_data['Close'].rolling(window=200).mean()
                        
                        fig = go.Figure(data=[go.Candlestick(x=hist_data.index,
                                        open=hist_data['Open'], high=hist_data['High'],
                                        low=hist_data['Low'], close=hist_data['Close'], name="K線")])
                        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['50MA'], mode='lines', name='季線 (50MA)', line=dict(color='#00BFFF', width=1.5)))
                        fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['200MA'], mode='lines', name='年線 (200MA)', line=dict(color='#FF4500', width=1.5)))
                        
                        fig.update_layout(title=f"{selected_ticker} 近半年走勢與均線分析", yaxis_title="股價", template="plotly_dark", xaxis_rangeslider_visible=False, height=500)
                        st.plotly_chart(fig, use_container_width=True)
            
            # 3. 發送 Discord 訊息
            discord_msgs = [f"🎯 **{s['股票代號']}** | 💵 `{s['收盤價']}` | ⚖️ 前瞻 PEG: `{s['前瞻 PEG']}` | 🚀 成長: `{s['成長率 (%)']}%`" for s in passed_stocks]
            send_discord_webhook("🏆 **【網頁雷達：自訂條件掃描報告】**\n\n" + "\n".join(discord_msgs))
            
        else:
            st.warning("💡 掃描完成。在目前的嚴格條件下，今天市場上沒有標的過關。")