import streamlit as st
import requests
from bs4 import BeautifulSoup
import FinanceDataReader as fdr
import plotly.graph_objects as go
import pandas as pd

# 0. 페이지 기본 설정
st.set_page_config(layout="wide")

# --- 1. 네이버 증권 데이터 크롤링 ---
@st.cache_data(ttl=10)
def get_naver_stock_data(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        stock_name = soup.find("div", {"class": "wrap_company"}).find("h2").text
        current_price = float(soup.find("div", {"class": "rate_info"}).find("p", {"class": "no_today"}).find("span", {"class": "blind"}).text.replace(",", ""))
        
        aside_aside = soup.find("div", {"class": "aside_invest_info"})
        per_text = aside_aside.find("em", {"id": "_per"}).text if aside_aside.find("em", {"id": "_per"}) else "0"
        pbr_text = aside_aside.find("em", {"id": "_pbr"}).text if aside_aside.find("em", {"id": "_pbr"}) else "0"
        
        per = float(per_text.replace(",", "")) if per_text != "N/A" else 0.0
        pbr = float(pbr_text.replace(",", "")) if pbr_text != "N/A" else 0.0
        
        return {"name": stock_name, "price": current_price, "per": per, "pbr": pbr}
    except:
        return None

# --- 2. 실제 주가 데이터 및 이평선 계산 ---
@st.cache_data(ttl=60)
def get_historical_data(code):
    try:
        df = fdr.DataReader(code)
        if df.empty: return None
        df = df.tail(100).reset_index()
        
        # 💡 지수이동평균(EMA) 및 거래량 이평 계산
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['Vol_Avg20'] = df['Volume'].rolling(window=20).mean() # 20일 평균 거래량
        return df
    except:
        return None

# --- 대시보드 UI 시작 ---
st.title("📱 줏대있는 개미의 모바일 철벽 필터 시스템")
stock_code = st.text_input("종목코드를 입력하세요", value="005930")

basic_data = get_naver_stock_data(stock_code)
chart_data = get_historical_data(stock_code)

if basic_data is None or chart_data is None:
    st.error("종목코드를 확인하시거나 잠시 후 다시 시도해주세요.")
else:
    # 데이터 변수 바인딩
    now_price = basic_data['price']
    now_per = basic_data['per']
    now_pbr = basic_data['pbr']
    
    latest = chart_data.iloc[-1]
    ema20 = latest['EMA20']
    ema50 = latest['EMA50']
    today_volume = latest['Volume']
    vol_avg20 = latest['Vol_Avg20']
    
    # -------------------------------------------------------------
    # 🧠 [선생님 수정 구간] 데이터와 실시간 연동되는 필터 연산 수식
    # -------------------------------------------------------------
    
    # 🎯 1. 매매 가격 가이드라인 수식
    buy_target = now_price * 0.95        
    stop_loss = buy_target * 0.95        
    profit_target = now_price * 1.10     

    # 📊 2. 9가지 철벽 필터 조건 실시간 연산
    
    # [필터 1] C: 분기 EPS 성장성 (PER 기준 연동)
    f1_score = 90.0 if 0 < now_per < 15 else 70.0 if now_per < 25 else 40.0
    f1_desc = f"실시간 PER {now_per}배 기준 정량 점수"
    
    # [필터 2] A: 연간 ROE 실적 (PBR 기준 연동)
    f2_score = 90.0 if 0 < now_pbr < 1.5 else 60.0 if now_pbr < 3.0 else 30.0
    f2_desc = f"실시간 PBR {now_pbr}배 기준 정량 점수"
    
    # [필터 3] N: 신고가 및 추세 정배열 (이평선 연동)
    if now_price > ema20 > ema50:
        f3_score = 95.0
        f3_desc = "주가가 20일, 50일선 위에 위치한 완벽한 정배열"
    elif now_price > ema20:
        f3_score = 70.0
        f3_desc = "20일선 위로 반등했으나 중기 이평선 저항 확인 필요"
    else:
        f3_score = 35.0
        f3_desc = "주가가 이평선 아래에 위치한 역배열 추세 (위험)"
        
    # [필터 4] ★진짜 연동★ S: 거래량 돌파 에너지
    # 오늘 거래량이 20일 평균 거래량의 몇 배인가를 실시간 연산합니다.
    if today_volume > (vol_avg20 * 2.0):
        f4_score = 95.0
        f4_desc = f"🔥 거래량 폭발! 20일 평균 대비 {(today_volume/vol_avg20):.1f}배 돌파"
    elif today_volume > vol_avg20:
        f4_score = 75.0
        f4_desc = "거래량 양호. 평균 거래량 상회 중"
    else:
        f4_score = 45.0
        f4_desc = "거래량 침체. 시장 소외 가능성 우려"

    # [필터 9] ★진짜 연동★ Quant: 차트 지지선 확인
    # 현재 주가가 단기 지지선(EMA20)과 얼마나 가까운지 이격도를 계산하여 지지 여부를 체크합니다.
    disparity = (now_price / ema20) * 100
    if 98 <= disparity <= 102:
        f9_score = 95.0
        f9_desc = f"🎯 핵심 지지선 근접! 20일선 이격도 {disparity:.1f}%로 강력한 지지대 배치"
    elif disparity > 102:
        f9_score = 65.0
        f9_desc = f"20일선과 이격이 다소 벌어짐 (이격도 {disparity:.1f}%), 추격매수 유의"
    else:
        f9_score = 40.0
        f9_desc = f"20일선 지지 붕괴 후 하회 중 (이격도 {disparity:.1f}%)"

    # 나머지 수동 필터 (5~8번은 정성적 원칙이므로 일단 70점 고정, 추후 데이터 확충 가능)
    f5_score, f5_desc = 70.0, "주도주 섹터 매력도 필터"
    f6_score, f6_desc = 70.0, "메이저 수급 유입 필터"
    f7_score, f7_desc = 70.0, "시장 방향성 위기 감지"
    f8_score, f8_desc = 70.0, "경영진 및 공시 리스크"

    # 🔥 9가지 필터 평균으로 종합 점수 자동 계산
    total_score = int((f1_score + f2_score + f3_score + f4_score + f5_score + f6_score + f7_score + f8_score + f9_score) / 9)

    # -------------------------------------------------------------
    # 🖥️ 화면 레이아웃 배치
    # -------------------------------------------------------------
    st.subheader(f"📊 {basic_data['name']} ({stock_code}) 모바일 계측 결과")
    
    left_col, right_col = st.columns([1, 3])
    
    with left_col:
        with st.container(border=True):
            st.markdown("### **철벽 필터 종합 점수**")
            st.markdown(f"<h1 style='color: #2ECC71; text-align: center; font-size: 60px;'>{total_score} <span style='font-size:24px;'>점</span></h1>", unsafe_allow_html=True)
            st.markdown(f"**현재가:** {int(now_price):,}원")
            
            st.markdown("---")
            st.markdown("### **🎯 매매 철칙 가격**")
            st.success(f"대기 매수가: {int(buy_target):,}원")
            st.error(f"철벽 손절가: {int(stop_loss):,}원")
            st.info(f"목표 익절가: {int(profit_target):,}원")
            
    with right_col:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['Close'], name='실제 주가', line=dict(color='black', width=2)))
        fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['EMA20'], name='EMA20', line=dict(color='blue', dash='dot')))
        fig.add_trace(go.Scatter(x=chart_data['Date'], y=chart_data['EMA50'], name='EMA50', line=dict(color='orange')))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), legend=orientation="h")
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
            {"title": "Quant: 경영진 및 공시 리스크", "score": f8_score, "desc": f8_desc},
            {"title": "Quant: 차트 지지선 확인", "score": f9_score, "desc": f9_desc},
        ]
        
        for idx, item in enumerate(all_filters):
            with grid_cols[idx % 3]:
                with st.container(border=True):
                    st.markdown(f"**{item['title']}**")
                    color = "#2ECC71" if item['score'] >= 80 else "#E67E22" if item['score'] >= 60 else "#C0392B"
                    st.markdown(f"<h3 style='color: {color}; margin:0;'>{item['score']} 점</h3>", unsafe_allow_html=True)
                    st.caption(item['desc'])
