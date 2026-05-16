import streamlit as st
import requests
from bs4 import BeautifulSoup
import FinanceDataReader as fdr
import plotly.graph_objects as go
import pandas as pd

# 0. 페이지 기본 설정
st.set_page_config(layout="wide")

# --- 1. 네이버 증권 데이터 (안전망 강화 및 Timeout 적용) ---
@st.cache_data(ttl=60)
def get_naver_stock_data(code, run_mode):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        # 💡 [결함 해결] 서버 지연 시 무한 멈춤(Freeze) 방지
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        stock_name = soup.find("div", {"class": "wrap_company"}).find("h2").text
        
        aside_aside = soup.find("div", {"class": "aside_invest_info"})
        per_text = aside_aside.find("em", {"id": "_per"}).text if aside_aside.find("em", {"id": "_per"}) else "0"
        pbr_text = aside_aside.find("em", {"id": "_pbr"}).text if aside_aside.find("em", {"id": "_pbr"}) else "0"
        
        per = float(per_text.replace(",", "")) if per_text != "N/A" else 0.0
        pbr = float(pbr_text.replace(",", "")) if pbr_text != "N/A" else 0.0
        
        sub_url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        sub_res = requests.get(sub_url, headers=headers, timeout=5)
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')
        
        frgn_table = sub_soup.find("table", {"summary": "외국인 기관 매매동향 연속 정보"})
        rows = frgn_table.find_all("tr") if frgn_table else []
        
        net_foreigner = 0.0
        net_institution = 0.0
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
            "name": stock_name, "per": per, "pbr": pbr,
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
st.title("📱 줏대있는 개미의 무결점 종목 선별 시스템")

mode_cols = st.columns(2)
with mode_cols[0]:
    stock_code = st.text_input("종목코드 6자리", value="005930")
with mode_cols[1]:
    run_mode = st.radio("⏱️ 현재 조회 시점 선택 (필수)", 
                        ["장 마감 후 / 주말 (최신 데이터)", "장중 (전일 확정 데이터 조회)"], 
                        horizontal=True)

setup_cols = st.columns(3)
with setup_cols[0]:
    buy_pct = st.number_input("대기 매수점 (기준가 대비 %)", value=-5.0, step=1.0)
with setup_cols[1]:
    target_pct = st.number_input("목표 익절선 (매수가 대비 %)", value=10.0, step=1.0)
with setup_cols[2]:
    loss_pct = st.number_input("철벽 손절선 (매수가 대비 %)", value=-5.0, step=1.0)

basic_data = get_naver_stock_data(stock_code, run_mode)
chart_data = get_historical_data(stock_code)

if basic_data is None or chart_data is None or basic_data['target_date'] == "":
    st.error("종목코드를 확인하시거나 잠시 후 다시 시도해주세요. (서버 응답 지연 또는 상장폐지 종목)")
else:
    target_date = basic_data['target_date']
    matching_rows = chart_data[chart_data['Date_str'] == target_date]
    
    # 💡 [결함 해결] 신규 상장주 검색 시 앱이 튕기는 KeyError 완벽 차단
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
    now_per = basic_data['per']
    now_pbr = basic_data['pbr']
    net_f = basic_data['net_foreigner'] 
    net_i = basic_data['net_institution'] 
    ema20 = latest['EMA20']
    ema50 = latest['EMA50']
    
    # 🎯 1. 매매 가이드라인
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
    
    if pd.isna(ema50) or pd.isna(ema20):
        f3_score, f3_desc = 50.0, "상장 기간 부족 (이평선 유보)"
        f9_score, f9_desc = 50.0, "상장 기간 부족 (지지선 유보)"
    else:
        if now_price > ema20 > ema50: f3_score, f3_desc = 95.0, "완벽한 상승 정배열 안착"
        else: f3_score, f3_desc = 35.0, "이평선 역배열 또는 추세 이탈"
            
        disparity = (now_price / ema20) * 100
        if 98 <= disparity <= 102: f9_score, f9_desc = 95.0, f"🎯 핵심 지지선 안착 (이격도 {disparity:.1f}%)"
        else: f9_score, f9_desc = 55.0, f"지지선 이탈 또는 이격 과다 (이격도 {disparity:.1f}%)"
        
    vol_ratio = latest['Volume'] / prev['Volume'] if prev['Volume'] > 0 else 1.0
    if vol_ratio >= 2.0: f4_score, f4_desc = 95.0, f"🔥 거래량 {vol_ratio:.1f}배 돌파 (에너지 분출)"
    elif vol_ratio >= 1.0: f4_score, f4_desc = 75.0, f"거래량 {vol_ratio:.1f}배 (평이한 유입)"
    else: f4_score, f4_desc = 40.0, f"거래량 {vol_ratio:.1f}배 (시장 소외)"

    if net_f > 0 and net_i > 0: f6_score, f6_desc = 95.0, f"🎯 쌍끌이 매수 확인 (외인:{int(net_f):,}, 기관:{int(net_i):,})"
    elif net_f > 0 or net_i > 0:
        buyer = "외국인" if net_f > 0 else "기관"
        f6_score, f6_desc = 75.0, f"메이저 단일 수급 유입 ({buyer} 매수)"
    else: f6_score, f6_desc = 35.0, "외인/기관 동반 매도 (리스크 발생)"

    # --- 정성적 필터 수동 슬라이더 ---
    st.markdown("---")
    st.markdown("### 💡 정성적 필터 수동 체크 (스마트폰 터치)")
    
    input_cols = st.columns(3)
    with input_cols[0]:
        f5_score = st.slider("L: 주도주 매력도 판단", 0, 100, 50, step=5)
        f5_desc = "업황 대장 여부 체크"
    with input_cols[1]:
        f7_score = st.slider("M: 시장 위험도 판단", 0, 100, 50, step=5)
        f7_desc = "지수 추세선/매물대 방어력 체크"
    with input_cols[2]:
        f8_score = st.slider("Quant: 경영진/공시 리스크", 0, 100, 50, step=5)
        f8_desc = "DART 특이공시 체크"

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
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['Close'], name='종가 추이', line=dict(color='black', width=2)))
        if not pd.isna(latest['EMA20']):
            fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['EMA20'], name='EMA20', line=dict(color='blue', dash='dot')))
        if not pd.isna(latest['EMA50']):
            fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['EMA50'], name='EMA50', line=dict(color='orange')))
            
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        grid_cols = st.columns(3)
        all_filters = [
            {"title": "C: 분기 EPS 성장성", "score": f1_score, "desc": f1_desc},
            {"title": "A: 연간 ROE 실적", "score": f2_score, "desc": f2_desc},
            {"title": "N: 신고가 및 추세 정배열", "score": f3_score, "desc": f3_desc},
            {"title": "S: 거래량 돌파 에너지", "score": f4_score, "desc": f4_desc},
            {"title": "L: 주도주 대장 여부", "score": f5_score, "desc": f5_desc},
            {"title": "I: 메이저 수급 (기관/외인)", "score": f6_score, "desc": f6_desc},
            {"title": "M: 시장 방향성 위기 감지", "score": f7_score, "desc": f7_desc},
            {"title": "Quant: 경영/공시 리스크", "score": f8_score, "desc": f8_desc},
            {"title": "Quant: 차트 지지선 확인", "score": f9_score, "desc": f9_desc},
        ]
        for idx, item in enumerate(all_filters):
            with grid_cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"**{item['title']}**")
                    color = "#2ECC71" if item['score'] >= 80 else "#E67E22" if item['score'] >= 60 else "#C0392B"
                    st.markdown(f"<h3 style='color: {color}; margin:0;'>{item['score']} 점</h3>", unsafe_allow_html=True)
                    st.caption(item['desc'])
