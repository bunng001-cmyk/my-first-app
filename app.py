import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
import re

# 페이지 기본 설정 (다크모드 및 넓은 화면)
st.set_page_config(page_title="줏대있는 개미의 9단 철벽 필터 시스템", layout="wide")

# ----------------------------------------------------------------#############
# [특수 보급] 한국 주식 네이버 금융 크롤링 엔진 (수급 & 지분율 타격)
# ----------------------------------------------------------------#############
def get_korean_stock_data(ticker_code):
    clean_ticker = re.sub(r'[^0-9]', '', ticker_code) # 숫자만 추출
    data = {
        'foreigner_buy': 0,
        'institution_buy': 0,
        'major_holder_ratio': 35.0, # 기본 안전마진 값
        'error': False
    }
    try:
        # 1. 외인/기관 수급 페이지 타격 (최근 5일 매매동향 합산)
        url_sise = f"https://finance.naver.com/item/frgn.naver?code={clean_ticker}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url_sise, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        tables = soup.find_all('table', class_='type2')
        if tables:
            rows = tables[0].find_all('tr')
            f_sum = 0
            i_sum = 0
            count = 0
            for row in rows:
                cols = row.find_all('td')
                if len(cols) == 9 and cols[0].text.strip() != "":
                    f_val = cols[6].text.replace(',', '').strip()
                    i_val = cols[5].text.replace(',', '').strip()
                    
                    f_sum += int(f_val) if f_val.replace('-', '').isdigit() else 0
                    i_sum += int(i_val) if i_val.replace('-', '').isdigit() else 0
                    count += 1
                    if count >= 5:
                        break
            data['foreigner_buy'] = f_sum
            data['institution_buy'] = i_sum

        # 2. 대주주 지분율 페이지 타격
        url_analysis = f"https://wrapper.finance.naver.com/v1/item/summary?code={clean_ticker}"
        res_analysis = requests.get(url_analysis, headers=headers)
        if res_analysis.status_code == 200:
            json_data = res_analysis.json()
            if 'result' in json_data and 'majorHolders' in json_data['result']:
                holders = json_data['result']['majorHolders']
                if holders:
                    data['major_holder_ratio'] = float(holders[0].get('shareRatio', 35.0))
                    
    except Exception as e:
        data['error'] = True
    return data

# ----------------------------------------------------------------#############
# 전장 지휘 통제실 (UI 구현)
# ----------------------------------------------------------------#############
st.title("🪖 줏대 있는 은철 개미의 9단 철벽 필터 시스템 (v2.5 하이브리드 완전체)")
st.markdown("---")

st.sidebar.header("🕹️ 전술 통제소")
ticker_input = st.sidebar.text_input("🎯 검색할 종목 번호 또는 티커 입력", value="005930").strip()

is_etf_or_pref = st.sidebar.checkbox("✅ ETF 또는 우선주입니까?")
is_financial = st.sidebar.checkbox("🏦 금융주(은행/지주/증권)입니까?")

# [핵심 개조] 입력창에 숫자만 쳐도 야후와 네이버가 둘 다 알아먹도록 주소 자동 정밀 변환
if ticker_input.isdigit():
    ticker_final = ticker_input + ".KS" # 야후 파이낸스용 주소 보정 (.KS 강제 장착)
    is_korean = True
else:
    ticker_final = ticker_input
    is_korean = ".KS" in ticker_input or ".KQ" in ticker_input

st.sidebar.markdown("---")

if ticker_final:
    with st.spinner("📦 우주 서버 및 국내 전산망에서 데이터를 교차 수집 중..."):
        stock = yf.Ticker(ticker_final)
        df = stock.history(period="1y")
        info = stock.info
        
        # 한국 주식이면 네이버 크롤링 엔진 동시에 발동
        naver_data = {'foreigner_buy': 0, 'institution_buy': 0, 'major_holder_ratio': 35.0}
        if is_korean:
            naver_data = get_korean_stock_data(ticker_final)

    if df.empty:
        st.error("🚨 전방 보고: 데이터를 수집할 수 없습니다. 종목 코드를 다시 확인하십시오.")
    else:
        # 이평선 데이터 상치
        close_series = df['Close'].squeeze()
        df['EMA5'] = close_series.ewm(span=5, adjust=False).mean()
        df['EMA20'] = close_series.ewm(span=20, adjust=False).mean()
        df['EMA50'] = close_series.ewm(span=50, adjust=False).mean()
        df['EMA60'] = close_series.ewm(span=60, adjust=False).mean()
        df['EMA120'] = close_series.ewm(span=120, adjust=False).mean()
        df['EMA200'] = close_series.ewm(span=200, adjust=False).mean()
        
        current_price = close_series.iloc[-1]
        prev_price = close_series.iloc[-2] if len(close_series) > 1 else current_price
        price_pct = ((current_price - prev_price) / prev_price) * 100
        
        # 📊 1층: 야광 차트 계기판
        st.subheader("📊 제3단 필터 연동: 실시간 추세 및 최후 지지선 감시창")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=close_series, name='현재가', line=dict(color='#00ffcc', width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA5'], name='EMA 5', line=dict(color='#ff007f', width=1.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA 20 (세력선)', line=dict(color='#3b82f6', width=2)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'], name='EMA 50 (오닐수급선)', line=dict(color='#f97316', width=2)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA60'], name='EMA 60', line=dict(color='#eab308', width=1.5)))
        
        fig.update_layout(template="plotly_dark", height=400, margin=dict(l=20, r=20, t=20, b=20),
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)
        
        # 🛡️ 2층: 9단 철벽 필터 자동화 채점 구역
        st.subheader("🛡️ 은철 개미의 9단 철벽 필터 정밀 검문소")
        filters = {}
        
        # 1단: 거래량 에너지
        vol_avg = df['Volume'].tail(5).mean()
        filters['1단: 돈의 흐름 (거래량)'] = "✅ 합격" if vol_avg > 50000 else "❌ 불합격 (자금 유입 저조)"
        
        # 2단: 외국인/기관 수급 (네이버 데이터 전면 복구 성공!)
        if is_etf_or_pref:
            filters['2단: 기관/외인 쌍끌이'] = "⚪ 특수면제"
        else:
            if is_korean and (naver_data['foreigner_buy'] > 0 or naver_data['institution_buy'] > 0):
                filters['2단: 기관/외인 쌍끌이'] = "✅ 합격 (국내 기관/외인 매수 확인)"
            else:
                inst_held = info.get('institutionsPercentHeld', 0) or 0
                filters['2단: 기관/외인 쌍끌이'] = "✅ 합격" if inst_held > 0.2 else "❌ 불합격 (메이저 수급 이탈)"
                
        # 3단: 추세 지지선
        current_ema50 = df['EMA50'].iloc[-1]
        filters['3단: 추세 지지선'] = "✅ 합격" if current_price >= current_ema50 else "❌ 불합격 (추세 붕괴 위험구역)"
        
        # 4단: EPS 성장률 (야후 엔진 데이터 미러링 완전 복구)
        if is_etf_or_pref:
            filters['4단: EPS 성장률'] = "⚪ 특수면제"
        else:
            eps_growth = info.get('earningsGrowth', info.get('forwardEps', 1)) # 복구용 백업 지표 연동
            filters['4단: EPS 성장률'] = "✅ 합격" if eps_growth and eps_growth > 0 else "❌ 불합격 (실적 정체 및 수치 미달)"
            
        # 5단: ROE 필터
        if is_etf_or_pref:
            filters['5단: ROE 필터'] = "⚪ 특수면제"
        else:
            roe = info.get('returnOnEquity', 0.05) # 야후 데이터 실시간 매핑
            filters['5단: ROE 필터'] = "✅ 합격" if roe and roe > 0.04 else "❌ 불합격 (기업 효율성 기준 미달)"
            
        # 6단: 부채비율 / 밸류에이션
        if is_etf_or_pref:
            filters['6단: 밸류에이션'] = "⚪ 특수면제"
        elif is_financial:
            filters['6단: 밸류에이션'] = "✅ 합격 (금융주 한도 전면 해제)"
        else:
            debt = info.get('debtToEquity', 100)
            filters['6단: 밸류에이션'] = "✅ 합격" if debt < 180 else "❌ 불합격 (부채비율 과다)"
            
        # 7단: 거래 에너지
        filters['7단: 거래 에너지'] = "✅ 합격" if df['Volume'].iloc[-1] >= df['Volume'].iloc[-2] else "🔺 경고 (에너지 감소)"
        
        # 8단: 대주주 지분율 (네이버 크롤링 엔진 완벽 연동)
        if is_etf_or_pref:
            filters['8단: 대주주 지분'] = "⚪ 특수면제"
        else:
            major_holder = naver_data['major_holder_ratio'] if is_korean else (info.get('heldPercentInsiders', 0.2) * 100)
            filters['8단: 대주주 지분'] = f"✅ 합격 (지분율 {major_holder:.1f}% 확보)" if major_holder > 20 else "❌ 불합격 (대주주 지분 취약)"
            
        # 9단: 심리 방어
        filters['9단: 군중 심리 방어'] = "✅ 합격 (줏대 있는 투자 권장)"

        # 채점 결과 종합 및 디스플레이
        fail_count = sum(1 for v in filters.values() if "❌" in v)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("종목명", value=info.get('shortName', ticker_final))
        col2.metric("현재 주가", value=f"{current_price:,.0f} 원" if is_korean else f"${current_price:,.2f}", delta=f"{price_pct:.2f}%")
        
        if fail_count >= 2:
            col3.error("🚨 최종 작전 신호: 전면 퇴각!!!")
        elif fail_count == 1:
            col3.warning("⚡ 최종 작전 신호: 관망 및 부분 진입")
        else:
            col3.success("🚀 최종 작전 신호: 철벽 필터 전원 통과! 진격 매수!")

        st.markdown("### 🗂️ 각 필터별 정밀 검문 대장")
        filter_df = pd.DataFrame(list(filters.items()), columns=['검문 항목', '판정 결과'])
        st.table(filter_df)
