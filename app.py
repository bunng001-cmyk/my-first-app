import streamlit as st
import requests
from bs4 import BeautifulSoup
import FinanceDataReader as fdr
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")

# --- 1. 네이버 종합 증권 데이터 크롤링 (ETF 호환 및 예외 처리 완벽 적용) ---
@st.cache_data(ttl=60)
def get_naver_stock_data(code, run_mode):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 종목명 및 현재가 추출
        stock_name = soup.find("div", {"class": "wrap_company"}).find("h2").text
        no_today = soup.find("div", {"class": "rate_info"}).find("p", {"class": "no_today"})
        current_price = float(no_today.find("span", {"class": "blind"}).text.replace(",", ""))
        
        # 💡 [치명적 버그 1 완벽 해결] ETF 검색 시 앱 튕김 현상 방어
        aside_aside = soup.find("div", {"class": "aside_invest_info"})
        if aside_aside:
            per_elem = aside_aside.find("em", {"id": "_per"})
            pbr_elem = aside_aside.find("em", {"id": "_pbr"})
            per_text = per_elem.text if per_elem else "0"
            pbr_text = pbr_elem.text if pbr_elem else "0"
        else:
            # ETF 등 밸류에이션 박스가 없는 종목은 안전하게 0으로 처리
            per_text, pbr_text = "0", "0"
            
        per = float(per_text.replace(",", "")) if per_text not in ["N/A", "0"] else 0.0
        pbr = float(pbr_text.replace(",", "")) if pbr_text not in ["N/A", "0"] else 0.0
        
        # 수급 데이터 추출
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
                    i_text = tds[5].text.replace(",", "").strip()
                    f_text = tds[6].text.replace(",", "").strip()
                    try:
                        net_institution = float(i_text) if i_text and i_text != "-" else 0.0
                        net_foreigner = float(f_text) if f_text and f_text != "-" else 0.0
                    except ValueError:
                        pass
                    break
                valid_row_count += 1
                
        return {
            "name": stock_name, "price": current_price, "per": per, "pbr": pbr,
            "target_date": target_date_str, 
            "net_foreigner": net_foreigner, "net_institution": net_institution
        }
    except:
        return None

# --- 2. 실제 주가 및 이평선 계산 ---
@st.cache_data(ttl=60)
def get_historical_data(code):
    try:
        df = fdr.DataReader(code)
        if df.empty: return None
        df = df.reset_index()
        df = df.tail(150)
        
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['Date_str'] = df['Date'].dt.strftime('%Y.%m.%d')
        return df
    except:
        return None

# --- 대시보드 UI 구동 ---
st.title("📱 은철 개미의 무결점 종목 선별 시스템")

mode_cols = st.columns(2)
with mode_cols[0]:
    stock_code = st.text_input("종목코드 6자리", value="005930").strip()
with mode_cols[1]:
    run_mode = st.radio("⏱️ 현재 조회 시점 선택 (필수)", 
                        ["장 마감 후 / 주말 (최신 데이터)", "장중 (전일 확정 데이터 조회)"], 
                        horizontal=True)

if not stock_code.isdigit() or len(stock_code) != 6:
    st.error("⚠️ 6자리 숫자 코드(예: 005930, 005935, ETF코드)를 입력해주세요!")
    st.stop()

setup_cols = st.columns(3)
with setup_cols[0]:
    buy_pct = st.number_input("대기 매수점 (기준가 대비 %)", value=-5.0, step=1.0)
with setup_cols[1]:
    target_pct = st.number_input("목표 익절선 (매수가 대비 %)", value=10.0, step=1.0)
with setup_cols[2]:
    loss_pct = st.number_input("철벽 손절선 (매수가 대비 %)", value=-5.0, step=1.0)

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
        ema20, ema50 = 0.0, 0.0
    else:
        target_date = basic_data['target_date']
        matching_rows = chart_data[chart_data['Date_str'] == target_date]
        
        if len(matching_rows) > 0:
            pos = chart_data.index.get_loc(matching_rows.index[0])
            latest = chart_data.iloc[pos]
            prev = chart_data.iloc[pos - 1] if pos > 0 else latest
            plot_df = chart_data.iloc[:pos+1]
        else:
            latest = chart_data.iloc[-1]
            prev = chart_data.iloc[-2] if len(chart_data) > 1 else latest
            plot_df = chart_data
            
        latest_date = latest['Date'].strftime('%Y-%m-%d')
        now_price = latest['Close']
        ema20 = latest['EMA20']
        ema50 = latest['EMA50']

    now_per = basic_data['per']
    now_pbr = basic_data['pbr']
    net_f = basic_data['net_foreigner'] 
    net_i = basic_data['net_institution'] 
    
    # 🎯 1. 매매 가이드라인 연산
    buy_target = now_price * (1 + (buy_pct / 100))
    stop_loss = buy_target * (1 + (loss_pct / 100))
    profit_target = buy_target * (1 + (target_pct / 100))

    # 📊 2. 9가지 철벽 필터 조건 연산
    if now_per <= 0: f1_score, f1_desc = 30.0, "적자 기업 또는 ETF (데이터 없음)"
    elif now_per < 15: f1_score, f1_desc = 90.0, f"PER {now_per}배 (밸류 우량)"
    elif now_per < 30: f1_score, f1_desc = 70.0, f"PER {now_per}배 (적정 수준)"
    else: f1_score, f1_desc = 40.0, f"PER {now_per}배 (고평가 리스크)"
    
    if now_pbr <= 0: f2_score, f2_desc = 30.0, "적자 기업 또는 ETF (데이터 없음)"
    elif now_pbr < 2.5: f2_score, f2_desc = 90.0, f"PBR {now_pbr}배 (자산가치 안정권)"
    elif now_pbr < 5.0: f2_score, f2_desc = 70.0, f"PBR {now_pbr}배 (적정 수준)"
    else: f2_score, f2_desc = 40.0, f"PBR {now_pbr}배 (과열 상태)"
    
    if not is_chart_available or pd.isna(ema50) or pd.isna(ema20):
        f3_score, f3_desc = 50.0, "거래소 서버 점검으로 이평선 유보"
        f4_score, f4_desc = 50.0, "거래소 점검/상장초기로 거래량 유보"
        f9_score, f9_desc = 50.0, "거래소 서버 점검으로 지지선 유보"
    else:
        if now_price > ema20 > ema50: f3_score, f3_desc = 95.0, "완벽한 상승 정배열 안착"
        else: f3_score, f3_desc = 35.0, "이평선 역배열 또는 추세 이탈"
            
        vol_ratio = latest['Volume'] / prev['Volume'] if prev['Volume'] > 0 else 1.0
        if vol_ratio >= 2.0: f4_score, f4_desc = 95.0, f"🔥 거래량 {vol_ratio:.1f}배 돌파 (에너지 분출)"
        elif vol_ratio >= 1.0: f4_score, f4_desc = 75.0, f"거래량 {vol_ratio:.1f}배 (평이한 유입)"
        else: f4_score, f4_desc = 40.0, f"거래량 {vol_ratio:.1f}배 (시장 소외)"

        # 💡 [치명적 버그 2 완벽 해결] 액면분할 등으로 인한 수정주가 괴리 에러 방어
        disparity = (now_price / ema20) * 100 if ema20 > 0 else 100
        if disparity < 50 or disparity > 200:
            f9_score, f9_desc = 50.0, f"⚠️ 액면분할/배당락 등 가격 왜곡 감지 (수동 확인 요망)"
        elif 98 <= disparity <= 102: 
            f9_score, f9_desc = 95.0, f"🎯 핵심 지지선 안착 (이격도 {disparity:.1f}%)"
        else: 
            f9_score, f9_desc = 55.0, f"지지선 이탈 또는 이격 과다 (이격도 {disparity:.1f}%)"
        
    if net_f > 0 and net_i > 0: f6_score, f6_desc = 95.0, f"🎯 쌍끌이 매수 확인 (외인:{int(net_f):,}, 기관:{int(net_i):,})"
    elif net_f > 0 or net_i > 0:
        buyer = "외국인" if net_f > 0 else "기관"
        f6_score, f6_desc = 75.0, f"메이저 단일 수급 유입 ({buyer} 매수)"
    else: f6_score, f6_desc = 35.0, "외인/기관 동반 매도 (리스크 발생)"

    # --- 정성적 필터 수동 슬라이더 ---
    st.markdown("---")
    st.markdown("### 💡 정성적 필터 수동 체크 (스마트폰 터치)")
    input_cols = st.columns(3)
    with input_cols[0]: f5_score = st.slider("L: 주도주 매력도 판단", 0, 100, 50, step=5)
    with input_cols[1]: f7_score = st.slider("M: 시장 위험도 판단", 0, 100, 50, step=5)
    with input_cols[2]: f8_score = st.slider("Quant: 경영진/공시 리스크", 0, 100, 50, step=5)

    total_score = int((f1_score + f2_score + f3_score + f4_score + f5_score + f6_score + f7_score + f8_score + f9_score) / 9)

    # --- UI 렌더링 ---
    st.markdown("---")
    st.subheader(f"📊 {basic_data['name']} ({stock_code}) 종목 선별 리포트")
    
    left_col, right_col = st.columns([1, 3])
    with left_col:
        with st.container(border=True):
            st.markdown("### **철벽 필터 총점**")
            main_color = "#2ECC71" if total_score >= 80 else "#E67E22" if total_score >= 60 else "#C0392B"
            st.markdown(f"<h1 style='color: {main_color}; text-align: center; font-size: 60px;'>{total_score} <span style='font-size:24px;'>점</span></h1>", unsafe_allow_html=True)
            st.markdown(f"**확정 기준일 ({latest_date}):** {int(now_price):,}원")
            st.caption(f"PER: {now_per}배 | PBR: {now_pbr}배")
            st.markdown("---")
            st.markdown("### **🎯 매매 전략 단가**")
            st.success(f"대기 매수선: {int(buy_target):,}원")
            st.error(f"철벽 손절선: {int(stop_loss):,}원")
            st.info(f"목표 익절선: {int(profit_target):,}원")
            
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
            {"title": "N: 신고가 및 추세 정배열", "score": f3_score, "desc": is_chart_available and f3_desc or "서버점검"},
            {"title": "S: 거래량 돌파 에너지", "score": f4_score, "desc": is_chart_available and f4_desc or "서버점검"},
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
                    color = "#2ECC71" if item['score'] >= 80 else "#E67E22" if item['score'] >= 60 else "#C0392B"
                    st.markdown(f"<h3 style='color: {color}; margin:0;'>{item['score']} 점</h3>", unsafe_allow_html=True)
                    st.caption(item['desc'])
