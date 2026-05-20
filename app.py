import streamlit as st
import requests
from bs4 import BeautifulSoup
import FinanceDataReader as fdr
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta

# 0. 페이지 기본 설정
st.set_page_config(layout="wide")

def safe_float(text):
    try:
        if not text: return 0.0
        clean_text = str(text).replace(",", "").strip()
        if clean_text in ["", "N/A", "-", "NaN"]: return 0.0
        return float(clean_text)
    except:
        return 0.0

@st.cache_data(ttl=1800)
def get_macro_indicators():
    try:
        def fetch_last_two_close(symbol):
            start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
            df = fdr.DataReader(symbol, start=start_date)
            if df.empty or len(df) < 2: return 0.0, 0.0
            close_curr = df['Close'].iloc[-1]
            close_prev = df['Close'].iloc[-2]
            chg_pct = ((close_curr - close_prev) / close_prev) * 100
            return close_curr, chg_pct

        kospi_val, kospi_chg = fetch_last_two_close('KS11')
        sp500_val, sp500_chg = fetch_last_two_close('SPY') 
        usd_krw_val, usd_krw_chg = fetch_last_two_close('USD/KRW')
        us10y_val, us10y_chg = fetch_last_two_close('^TNX') 

        return {
            "kospi": (kospi_val, kospi_chg),
            "sp500": (sp500_val, sp500_chg),
            "usd_krw": (usd_krw_val, usd_krw_chg),
            "us10y": (us10y_val, us10y_chg)
        }
    except:
        return None

@st.cache_data(ttl=60)
def get_naver_stock_data(code, run_mode):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        stock_name_elem = soup.find("div", {"class": "wrap_company"})
        stock_name = stock_name_elem.find("h2").text if stock_name_elem else "종목명 불가"
        
        no_today_elem = soup.find("div", {"class": "rate_info"})
        if no_today_elem and no_today_elem.find("p", {"class": "no_today"}):
            current_price = safe_float(no_today_elem.find("p", {"class": "no_today"}).find("span", {"class": "blind"}).text)
        else:
            current_price = 0.0
        
        aside_aside = soup.find("div", {"class": "aside_invest_info"})
        if aside_aside:
            per_elem = aside_aside.find("em", {"id": "_per"})
            pbr_elem = aside_aside.find("em", {"id": "_pbr"})
            per = safe_float(per_elem.text) if per_elem else 0.0
            pbr = safe_float(pbr_elem.text) if pbr_elem else 0.0
        else:
            per, pbr = 0.0, 0.0

        # 💡 [찐빠 교정 1] 잃어버렸던 동일업종 PER 크롤링 엔진 완벽 복구
        industry_per = 0.0
        ind_table = soup.find("table", {"summary": "동일업종 PER 정보"})
        if ind_table:
            ind_em = ind_table.find("em")
            if ind_em:
                industry_per = safe_float(ind_em.text)
            
        sub_url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        sub_res = requests.get(sub_url, headers=headers, timeout=5)
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')
        
        frgn_table = sub_soup.find("table", {"summary": "외국인 기관 매매동향 연속 정보"})
        rows = frgn_table.find_all("tr") if frgn_table else []
        
        net_foreigner, net_institution = 0.0, 0.0
        target_date_str = ""
        target_row_index = 1 if run_mode == "장중 (전일 확정 데이터 조회)" else 0
        valid_row_count = 0
        
        for row in rows:
            tds = row.find_all("td")
            if len(tds) >= 7:
                if valid_row_count == target_row_index:
                    target_date_str = tds[0].text.strip() 
                    net_institution = safe_float(tds[5].text)
                    net_foreigner = safe_float(tds[6].text)
                    break
                valid_row_count += 1
                
        return {
            "name": stock_name, 
            "price": current_price, 
            "per": per, 
            "pbr": pbr,
            "industry_per": industry_per, # 누락되었던 데이터 수혈 완료
            "target_date": target_date_str, 
            "net_foreigner": net_foreigner, 
            "net_institution": net_institution
        }
    except:
        return None

@st.cache_data(ttl=60)
def get_historical_data(code):
    try:
        df = fdr.DataReader(code)
        if df.empty: return None
        df = df.reset_index()
        
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False, min_periods=20).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False, min_periods=50).mean()
        
        df['H-L'] = df['High'] - df['Low']
        df['H-PC'] = (df['High'] - df['Close'].shift(1)).abs()
        df['L-PC'] = (df['Low'] - df['Close'].shift(1)).abs()
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        df['ATR'] = df['TR'].rolling(window=14, min_periods=14).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        loss = loss.replace(0, 1e-10)
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        df['RSI'] = df['RSI'].fillna(50)
        
        df['Date_str'] = df['Date'].dt.strftime('%Y.%m.%d')
        df = df.tail(150)
        
        return df
    except:
        return None

st.title("📱 줏대있는 개미의 무결점 종목 선별 시스템")

macro_data = get_macro_indicators()
if macro_data:
    m_cols = st.columns(4)
    with m_cols[0]: st.metric("국내 코스피 지수", f"{macro_data['kospi'][0]:,.2f}", f"{macro_data['kospi'][1]:+.2f}%")
    with m_cols[1]: st.metric("미국 S&P 500 (SPY)", f"{macro_data['sp500'][0]:,.2f}", f"{macro_data['sp500'][1]:+.2f}%")
    with m_cols[2]: st.metric("원/달러 환율", f"{macro_data['usd_krw'][0]:,.2f}원", f"{macro_data['usd_krw'][1]:+.2f}%", delta_color="inverse")
    with m_cols[3]: st.metric("미국채 10년물 금리", f"{macro_data['us10y'][0]:.3f}%", f"{macro_data['us10y'][1]:+.2f}%", delta_color="inverse")
    st.markdown("---")

mode_cols = st.columns(2)
with mode_cols[0]:
    stock_code = st.text_input("종목코드 6자리", value="005930").strip()
with mode_cols[1]:
    run_mode = st.radio("⏱️ 현재 조회 시점 선택 (필수)", 
                        ["장 마감 후 / 주말 (최신 데이터)", "장중 (전일 확정 데이터 조회)"], 
                        horizontal=True)

if not stock_code.isdigit() or len(stock_code) != 6:
    st.error("⚠️ 6자리 숫자 코드를 입력해주세요!")
    st.stop()

setup_cols = st.columns(3)
with setup_cols[0]:
    buy_pct = st.number_input("대기 매수점 (기준가 대비 %)", value=-5.0, step=1.0)
with setup_cols[1]:
    target_atr_mult = st.number_input("목표 익절 가이드 (ATR 배수)", value=2.0, step=0.1)
with setup_cols[2]:
    loss_atr_mult = st.number_input("철벽 손절 가이드 (ATR 배수)", value=1.5, step=0.1)

basic_data = get_naver_stock_data(stock_code, run_mode)
chart_data = get_historical_data(stock_code)

if basic_data is None:
    st.error("네이버 증권 통신 실패. 네트워크 연결 또는 상장폐지 여부를 확인해 주세요.")
else:
    is_chart_available = True
    if chart_data is None:
        is_chart_available = False
        now_price = basic_data['price']
        latest_date = datetime.now().strftime('%Y-%m-%d (거래소점검비상모드)')
        ema20, ema50, rsi_val, atr_val = 0.0, 0.0, 50.0, 0.0
    else:
        target_date = basic_data['target_date']
        matching_rows = chart_data[chart_data['Date_str'] == target_date]
        
        if len(matching_rows) > 0:
            pos = chart_data.index.get_loc(matching_rows.index[0])
            latest = chart_data.iloc[pos]
            prev = chart_data.iloc[pos - 1] if pos > 0 else latest
            plot_df = chart_data.iloc[:pos+1]
        else:
            if "장중" in run_mode and len(chart_data) > 1:
                latest = chart_data.iloc[-2]
                prev = chart_data.iloc[-3] if len(chart_data) > 2 else latest
                plot_df = chart_data.iloc[:-1]
            else:
                latest = chart_data.iloc[-1]
                prev = chart_data.iloc[-2] if len(chart_data) > 1 else latest
                plot_df = chart_data
            
        latest_date = latest['Date'].strftime('%Y-%m-%d')
        now_price = latest['Close']
        ema20 = latest['EMA20']
        ema50 = latest['EMA50']
        rsi_val = latest['RSI']
        atr_val = latest['ATR']

    now_per = basic_data['per']
    now_pbr = basic_data['pbr']
    ind_per = basic_data['industry_per']
    net_f = basic_data['net_foreigner'] 
    net_i = basic_data['net_institution'] 
    
    buy_target = now_price * (1 + (buy_pct / 100))
    if is_chart_available and not pd.isna(atr_val) and atr_val > 0:
        stop_loss = max(0.0, buy_target - (loss_atr_mult * atr_val)) 
        profit_target = buy_target + (target_atr_mult * atr_val)
        atr_desc_text = f" (ATR {int(atr_val):,}원 적용)"
    else:
        stop_loss = buy_target * 0.95
        profit_target = buy_target * 1.10
        atr_desc_text = " (데이터 부족 고정 % 대체)"

    etf_keywords = ["KODEX", "TIGER", "KBSTAR", "ARIRANG", "KOSEF", "HANARO", "SOL", "ACE", "TIMEFOLIO", "FOCUS", "스팩", "ETF"]
    is_real_etf = (now_per == 0.0 and now_pbr == 0.0) and any(kw in basic_data['name'].upper() for kw in etf_keywords)

    if is_real_etf:
        # 💡 [찐빠 교정 2] ETF일 경우 0점이 아니라 '50점(중립)'으로 표출하여 시각적 공포 방지
        f1_score, f1_desc = 50.0, "ETF/스팩주 (가치평가 면제/중립)"
        f2_score, f2_desc = 50.0, "ETF/스팩주 (가치평가 면제/중립)"
    else:
        # 💡 누락되었던 업종 PER 상대평가 로직 정상 가동!
        if now_per <= 0: 
            f1_score, f1_desc = 30.0, "🚨 적자 기업 리스크 (진입 주의)"
        elif ind_per > 0:
            if now_per <= ind_per * 0.85: f1_score, f1_desc = 90.0, f"PER {now_per}배 (업종 {ind_per} 대비 저평가)"
            elif now_per <= ind_per * 1.15: f1_score, f1_desc = 70.0, f"PER {now_per}배 (업종 {ind_per} 수준)"
            else: f1_score, f1_desc = 40.0, f"PER {now_per}배 (업종 {ind_per} 대비 고평가)"
        else:
            if now_per < 15: f1_score, f1_desc = 90.0, f"PER {now_per}배 (절대적 밸류 우량)"
            elif now_per < 30: f1_score, f1_desc = 70.0, f"PER {now_per}배 (절대적 적정 수준)"
            else: f1_score, f1_desc = 40.0, f"PER {now_per}배 (고평가 리스크)"
        
        if now_pbr <= 0: f2_score, f2_desc = 30.0, "🚨 자본 잠식 리스크 (진입 주의)"
        elif now_pbr < 2.5: f2_score, f2_desc = 90.0, f"PBR {now_pbr}배 (자산가치 안정권)"
        elif now_pbr < 5.0: f2_score, f2_desc = 70.0, f"PBR {now_pbr}배 (적정 수준)"
        else: f2_score, f2_desc = 40.0, f"PBR {now_pbr}배 (과열 상태)"
    
    if not is_chart_available or pd.isna(ema50) or pd.isna(ema20):
        f3_score, f3_desc = 50.0, "상장 초기/서버 점검으로 이평선 유보"
        f4_score, f4_desc = 50.0, "상장 초기/서버 점검으로 거래량 유보"
        f9_score, f9_desc = 50.0, "상장 초기/서버 점검으로 지지선 유보"
    else:
        if now_price > ema20 > ema50: 
            f3_score, f3_desc = 95.0, f"상승 정배열 안착 (RSI: {rsi_val:.1f})"
        else: 
            f3_score, f3_desc = 35.0, f"역배열 또는 추세 이탈 (RSI: {rsi_val:.1f})"
        
        if rsi_val >= 70:
            f3_score = max(10.0, f3_score - 20.0)
            f3_desc += " ⚠️ 과열 (추격 매수 경고)"
        elif rsi_val <= 30:
            f3_score = min(100.0, f3_score + 10.0)
            f3_desc += " ✨ 과매도 (반등 기대)"
            
        if latest['Volume'] == 0:
            f4_score, f4_desc = 0.0, "🚨 거래정지 또는 비정상 호가 감지"
        else:
            if prev['Volume'] > 0:
                vol_ratio = latest['Volume'] / prev['Volume']
            else:
                vol_ratio = 99.0 if latest['Volume'] > 0 else 1.0

            is_bullish_candle = latest['Close'] >= latest['Open']
            
            if vol_ratio >= 2.0:
                if is_bullish_candle:
                    f4_score, f4_desc = 95.0, f"🔥 거래량 {vol_ratio:.1f}배 돌파 + 양봉 매집"
                else:
                    f4_score, f4_desc = 25.0, f"🚨 거래량 {vol_ratio:.1f}배 폭발 장대음봉"
            elif vol_ratio >= 1.0:
                f4_score, f4_desc = 75.0, f"거래량 {vol_ratio:.1f}배 (평이한 매매)"
                if not is_bullish_candle: f4_score -= 10
            else:
                f4_score, f4_desc = 40.0, f"거래량 {vol_ratio:.1f}배 소외"

        disparity = (now_price / ema20) * 100 if ema20 > 0 else 100
        if disparity < 50 or disparity > 200:
            f9_score, f9_desc = 50.0, f"⚠️ 가격 왜곡 감지 (분할/배당락 의심)"
        elif 98 <= disparity <= 102: 
            f9_score, f9_desc = 95.0, f"🎯 핵심 지지선 안착 (이격도 {disparity:.1f}%)"
        else: 
            f9_score, f9_desc = 55.0, f"지지선 이탈/이격 과다 (이격도 {disparity:.1f}%)"
        
    if net_f > 0 and net_i > 0: f6_score, f6_desc = 95.0, f"🎯 쌍끌이 매수 (외인:{int(net_f):,}, 기관:{int(net_i):,})"
    elif net_f > 0 or net_i > 0:
        buyer = "외국인" if net_f > 0 else "기관"
        f6_score, f6_desc = 75.0, f"메이저 단일 수급 ({buyer} 매수)"
    elif net_f < 0 and net_i < 0: f6_score, f6_desc = 35.0, f"🚨 쌍끌이 매도 리스크 (외인:{int(net_f):,}, 기관:{int(net_i):,})"
    elif net_f < 0 or net_i < 0:
        seller = "외국인" if net_f < 0 else "기관"
        f6_score, f6_desc = 45.0, f"메이저 단일 이탈 ({seller} 매도)"
    else: 
        f6_score, f6_desc = 50.0, "메이저 수급 없음 (관망/소외)"

    st.markdown("---")
    st.markdown("### 💡 정성적 필터 수동 체크 (스마트폰 터치)")
    input_cols = st.columns(3)
    with input_cols[0]: f5_score = st.slider("L: 주도주 매력도 판단", 0, 100, 50, step=5)
    with input_cols[1]: f7_score = st.slider("M: 시장 위험도 판단", 0, 100, 50, step=5)
    with input_cols[2]: f8_score = st.slider("Quant: 경영진/공시 리스크", 0, 100, 50, step=5)

    if is_real_etf:
        total_score = int((f3_score + f4_score + f5_score + f6_score + f7_score + f8_score + f9_score) / 7)
    else:
        total_score = int((f1_score + f2_score + f3_score + f4_score + f5_score + f6_score + f7_score + f8_score + f9_score) / 9)

    st.markdown("---")
    st.subheader(f"📊 {basic_data['name']} ({stock_code}) 종목 선별 리포트")
    
    left_col, right_col = st.columns([1, 3])
    with left_col:
        with st.container(border=True):
            st.markdown("### **철벽 필터 총점**")
            main_color = "#2ECC71" if total_score >= 80 else "#F1C40F" if total_score >= 60 else "#E74C3C"
            
            if is_chart_available and latest['Volume'] == 0:
                sig_color, sig_text, sig_desc = "#E74C3C", "🔴 RED / 진입 불가", "거래정지 또는 비정상 호가입니다."
            elif total_score >= 80 and rsi_val < 70:
                sig_color, sig_text, sig_desc = "#2ECC71", "🟢 GREEN / 진입 적합", "철벽 필터 통과. 타점 진입을 고려하세요."
            elif total_score >= 80 and rsi_val >= 70:
                sig_color, sig_text, sig_desc = "#F1C40F", "🟡 YELLOW / 눌림 대기", "완벽하나 단기 과열(RSI)입니다. 눌림을 기다리세요."
            elif total_score >= 60:
                sig_color, sig_text, sig_desc = "#F1C40F", "🟡 YELLOW / 관망 유지", "에너지가 부족합니다. 수급/돌파를 확인하세요."
            else:
                sig_color, sig_text, sig_desc = "#E74C3C", "🔴 RED / 진입 부적합", "필터 미달. 매수 버튼에서 손을 떼십시오."

            st.markdown(f"<h1 style='color: {main_color}; text-align: center; font-size: 60px; margin-bottom: 0;'>{total_score} <span style='font-size:24px;'>점</span></h1>", unsafe_allow_html=True)
            
            st.markdown(f"<div style='text-align: center; padding: 10px; margin-bottom: 15px; background-color: {sig_color}15; border-radius: 8px; border: 1.5px solid {sig_color};'>"
                        f"<h4 style='color: {sig_color}; margin: 0; font-weight: bold;'>{sig_text}</h4>"
                        f"<span style='font-size: 13px; color: gray;'>{sig_desc}</span></div>", unsafe_allow_html=True)
            
            st.markdown(f"**확정 기준일 ({latest_date}):** {int(now_price):,}원")
            st.caption(f"PER: {now_per}배 | PBR: {now_pbr}배")
            st.markdown("---")
            st.markdown("### **🎯 매매 전략 단가**")
            st.success(f"대기 매수선: {int(buy_target):,}원")
            st.error(f"철벽 손절선: {int(stop_loss):,}원" + atr_desc_text)
            st.info(f"목표 익절선: {int(profit_target):,}원" + atr_desc_text)
            
    with right_col:
        if is_chart_available:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['Close'], name='종가 추이', line=dict(color='black', width=2)))
            fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['EMA20'], name='EMA20', line=dict(color='blue', dash='dot')))
            fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['EMA50'], name='EMA50', line=dict(color='orange')))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("⚠️ 현재 한국거래소(FDR) 서버 점검으로 차트 출력을 생략하고 비상 정량 점수만 표출합니다.")
        
        st.markdown("---")
        grid_cols = st.columns(3)
        all_filters = [
            {"title": "C: 분기 EPS 성장성", "score": f1_score, "desc": f1_desc},
            {"title": "A: 연간 ROE 실적", "score": f2_score, "desc": f2_desc},
            {"title": "N: 신고가 및 추세 정배열", "score": f3_score, "desc": f3_desc},
            {"title": "S: 거래량 돌파 에너지", "score": f4_score, "desc": f4_desc},
            {"title": "L: 주도주 대장 여부", "score": f5_score, "desc": "업황 체크"},
            {"title": "I: 메이저 수급 (기관/외인)", "score": f6_score, "desc": f6_desc},
            {"title": "M: 시장 방향성 위기 감지", "score": f7_score, "desc": "지수 체크"},
            {"title": "Quant: 경영/공시 리스크", "score": f8_score, "desc": "DART 체크"},
            {"title": "Quant: 차트 지지선 확인", "score": f9_score, "desc": is_chart_available and f9_desc or "서버점검"},
        ]
        for idx, item in enumerate(all_filters):
            with grid_cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"**{item['title']}**")
                    # 💡 [찐빠 교정 2 연장] 50점일 때는 무조건 노란색(중립)이 뜨도록 색상 방어벽 갱신
                    color = "#2ECC71" if item['score'] >= 80 else "#F1C40F" if item['score'] >= 50 else "#E74C3C"
                    st.markdown(f"<h3 style='color: {color}; margin:0;'>{item['score']} 점</h3>", unsafe_allow_html=True)
                    st.caption(item['desc'])
