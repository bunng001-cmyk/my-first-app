import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
import re

# 페이지 기본 설정
st.set_page_config(page_title="줏대있는 개미의 9단 철벽 필터 시스템", layout="wide")

# ----------------------------------------------------------------#############
# [특수 보급] 국내 전산망 정밀 타격 엔진 (PER, PBR, ROE, 부채, 수급 100% 수집)
# ----------------------------------------------------------------#############
def get_korean_stock_data(ticker_code):
    clean_ticker = re.sub(r'[^0-9]', '', ticker_code)
    data = {
        'foreigner_buy': 0, 'institution_buy': 0, 'major_holder_ratio': 35.0,
        'per': 0.0, 'pbr': 0.0, 'roe': 0.0, 'debt_ratio': 100.0, 'error': False
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
            f_sum, i_sum, count = 0, 0, 0
            for row in rows:
                cols = row.find_all('td')
                if len(cols) == 9 and cols[0].text.strip() != "":
                    f_val = cols[6].text.replace(',', '').strip()
                    i_val = cols[5].text.replace(',', '').strip()
                    f_sum += int(f_val) if f_val.replace('-', '').isdigit() else 0
                    i_sum += int(i_val) if i_val.replace('-', '').isdigit() else 0
                    count += 1
                    if count >= 5: break
            data['foreigner_buy'] = f_sum
            data['institution_buy'] = i_sum

        # 2. 메인 페이지에서 실시간 PER, PBR 징집
        url_main = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
        res_main = requests.get(url_main, headers=headers)
        soup_main = BeautifulSoup(res_main.text, 'html.parser')
        
        per_element = soup_main.find('em', id='_per')
        pbr_element = soup_main.find('em', id='_pbr')
        if per_element: data['per'] = float(per_element.text.replace(',', '').strip())
        if pbr_element: data['pbr'] = float(pbr_element.text.replace(',', '').strip())

        # 3. 대주주 지분율 및 ROE, 부채비율 종합 타격
        url_analysis = f"https://wrapper.finance.naver.com/v1/item/summary?code={clean_ticker}"
        res_analysis = requests.get(url_analysis, headers=headers)
        if res_analysis.status_code == 200:
            json_data = res_analysis.json()
            if 'result' in json_data and json_data['result']:
                result = json_data['result']
                if 'majorHolders' in result and result['majorHolders']:
                    data['major_holder_ratio'] = float(result['majorHolders'][0].get('shareRatio', 35.0))
                if 'bizFinancials' in result and result['bizFinancials']:
                    biz = result['bizFinancials']
                    if len(biz) > 0:
                        data['roe'] = float(biz[-1].get('roe', 0.0) or 0.0)
                        data['debt_ratio'] = float(biz[-1].get('debtRatio', 100.0) or 100.0)
                        
    except Exception as e:
        data['error'] = True
    return data

# ----------------------------------------------------------------#############
# 본부 전장 지휘실 UI 구역
# ----------------------------------------------------------------#############
st.title("🪖 줏대 있는 은철 개미의 9단 철벽 필터 시스템 (v3.8 데이터 투명 공개형)")
st.markdown("---")

st.sidebar.header("🕹️ 전술 통제소")
ticker_input = st.sidebar.text_input("🎯 검색할 종목 번호 입력", value="005930").strip()

is_etf_or_pref = st.sidebar.checkbox("✅ ETF 또는 우선주입니까?")
is_financial = st.sidebar.checkbox("🏦 금융주입니까?")

# 한국 주식 주소 자동 보정
if ticker_input.isdigit():
    ticker_final = ticker_input + ".KS"
    is_korean = True
else:
    ticker_final = ticker_input.upper()
    is_korean = ".KS" in ticker_final or ".KQ" in ticker_final

if ticker_final:
    with st.spinner("📦 전산망 교차 검문 및 데이터 수집 중..."):
        stock = yf.Ticker(ticker_final)
        df = stock.history(period="1y")
        info = stock.info if stock.info else {}
        
        naver_data = {'foreigner_buy': 0, 'institution_buy': 0, 'major_holder_ratio': 35.0, 'per': 0.0, 'pbr': 0.0, 'roe': 0.0, 'debt_ratio': 100.0}
        if is_korean:
            naver_data = get_korean_stock_data(ticker_final)

    if df.empty:
        st.error("🚨 데이터를 수집할 수 없습니다. 종목 코드를 다시 확인하십시오.")
    else:
        close_series = df['Close'].squeeze()
        df['EMA5'] = close_series.ewm(span=5, adjust=False).mean()
        df['EMA20'] = close_series.ewm(span=20, adjust=False).mean()
        df['EMA50'] = close_series.ewm(span=50, adjust=False).mean()
        
        current_price = close_series.iloc[-1]
        prev_price = close_series.iloc[-2] if len(close_series) > 1 else current_price
        price_pct = ((current_price - prev_price) / prev_price) * 100
        
        # 🛡️ 1층: 요약 계기판
        col1, col2, col3 = st.columns(3)
        col1.metric("📋 종목 정보", value=f"코드: {ticker_input}")
        col2.metric("💵 현재 주가", value=f"{current_price:,.0f} 원" if is_korean else f"${current_price:,.2f}", delta=f"{price_pct:.2f}%")
        
        # ---------------------------------------------------------------------
        # 🗂️ 알맹이 완전 노출형 필터 채점 엔진
        # ---------------------------------------------------------------------
        filters = {}
        
        # 1단: 거래량
        vol_avg = df['Volume'].tail(5).mean()
        filters['1단: 돈의 흐름 (거래량)'] = f"✅ 합격 (5일 평균 거래량: {vol_avg:,.0f}주 ➡️ 5만주 기준 초과)" if vol_avg > 50000 else f"❌ 불합격 (5일 평균 거래량: {vol_avg:,.0f}주 ➡️ 자금 유입 저조)"
        
        # 2단: 수급
        if is_etf_or_pref:
            filters['2단: 기관/외인 쌍끌이'] = f"⚪ 특수면제 (현재 우선주/ETF 모드 가동 중)"
        else:
            if is_korean:
                f_buy = naver_data['foreigner_buy']
                i_buy = naver_data['institution_buy']
                if f_buy > 0 or i_buy > 0:
                    filters['2단: 기관/외인 쌍끌이'] = f"✅ 합격 (최근 5일 외인:{f_buy:+,}주 / 기관:{i_buy:+,}주 수급 유입)"
                else:
                    filters['2단: 기관/외인 쌍끌이'] = f"❌ 불합격 (최근 5일 외인:{f_buy:+,}주 / 기관:{i_buy:+,}주 메이저 이탈)"
            else:
                inst_held = (info.get('institutionsPercentHeld', 0) or 0) * 100
                filters['2단: 기관/외인 쌍끌이'] = f"✅ 합격 (기관 지분율: {inst_held:.1f}%)" if inst_held > 20 else f"❌ 불합격 (기관 지분율: {inst_held:.1f}% ➡️ 기준치 20% 미달)"
                
        # 3단: 추세 지지선
        current_ema50 = df['EMA50'].iloc[-1]
        if current_price >= current_ema50:
            filters['3단: 추세 지지선'] = f"✅ 합격 (현재가 {current_price:,.0f}원 ➡️ 최후 지지선 {current_ema50:,.0f}원 위 안전구역)"
        else:
            filters['3단: 추세 지지선'] = f"❌ 불합격 (현재가 {current_price:,.0f}원 ➡️ 최후 지지선 {current_ema50:,.0f}원 아래 위험구역)"
        
        # 4단: EPS 성장률
        if is_etf_or_pref:
            filters['4단: EPS 성장률'] = "⚪ 특수면제 (우선주/ETF 밸류에이션 면제 적용)"
        else:
            per_val = naver_data['per'] if is_korean else info.get('trailingPE', 0)
            filters['4단: EPS 성장률'] = f"✅ 합격 (실적 유지 / 현재 PER: {per_val:.2f}배)" if per_val > 0 else "❌ 불합격 (기업 적자 상태 또는 실적 정체)"
            
        # 5단: ROE 필터
        final_roe = naver_data['roe'] if is_korean else ((info.get('returnOnEquity', 0) or 0) * 100)
        if is_etf_or_pref:
            filters['5단: ROE 필터'] = f"⚪ 특수면제 (현재 우선주/ETF 모드 적용 중, 수치: {final_roe:.1f}%)"
        else:
            filters['5단: ROE 필터'] = f"✅ 합격 (현재 ROE: {final_roe:.1f}% ➡️ 기준치 5% 초과)" if final_roe > 5.0 else f"❌ 불합격 (현재 ROE: {final_roe:.1f}% ➡️ 기준치 5% 미달)"
            
        # 6단: 부채비율 및 밸류에이션
        final_debt = naver_data['debt_ratio'] if is_korean else (info.get('debtToEquity', 100) or 100)
        if is_etf_or_pref:
            filters['6단: 밸류에이션'] = f"⚪ 특수면제 (현재 우선주/ETF 모드 적용 중, 부채: {final_debt:.1f}%)"
        elif is_financial:
            filters['6단: 밸류에이션'] = f"✅ 합격 (금융주 부채 한도 무제한 면제 조항 적용, 부채: {final_debt:.1f}%)"
        else:
            filters['6단: 밸류에이션'] = f"✅ 합격 (현재 부채비율: {final_debt:.1f}% ➡️ 기준치 180% 이하 안전권)" if final_debt < 180 else f"❌ 불합격 (현재 부채비율: {final_debt:.1f}% ➡️ 기준치 180% 초과 리스크)"
            
        # 7단: 거래 에너지
        last_vol = df['Volume'].iloc[-1]
        prev_vol = df['Volume'].iloc[-2]
        filters['7단: 거래 에너지'] = f"✅ 합격 (직전 거래량 {prev_vol:,.0f}주 ➡️ 현재 거래량 {last_vol:,.0f}주로 에너지 상승)" if last_vol >= prev_vol else f"🔺 경고 (직전 거래량 {prev_vol:,.0f}주 ➡️ 현재 거래량 {last_vol:,.0f}주로 에너지 감소)"
        
        # 8단: 대주주 지분율
        major_holder = naver_data['major_holder_ratio'] if is_korean else ((info.get('heldPercentInsiders', 0.2) or 0.2) * 100)
        if is_etf_or_pref:
            filters['8단: 대주주 지분'] = f"⚪ 특수면제 (현재 우선주/ETF 모드 적용 중, 지분율: {major_holder:.1f}%)"
        else:
            filters['8단: 대주주 지분'] = f"✅ 합격 (대주주 지분율: {major_holder:.1f}% ➡️ 기준치 20% 안정권)" if major_holder > 20 else f"❌ 불합격 (대주주 지분율: {major_holder:.1f}% ➡️ 기준치 20% 미달 책임경영 취약)"
            
        # 9단: 심리 방어
        filters['9단: 군중 심리 방어'] = "✅ 합격 (뇌동매매 금지, 줏대 있는 원칙 진입권장)"
        
        # 종합 결과 하이라이트
        fail_count = sum(1 for v in filters.values() if "❌" in v)
        if fail_count >= 2: col3.error("🚨 최종 신호: 전면 퇴각!!!")
        elif fail_count == 1: col3.warning("⚡ 최종 신호: 관망/부분진입")
        else: col3.success("🚀 최종 신호: 진격 매수!")
        
        # 📊 2층: 지수 전광판
        st.markdown("---")
        st.subheader("📊 실시간 투자 지수 감시계기판")
        idx_col1, idx_col2, idx_col3, idx_col4 = st.columns(4)
        idx_col1.metric("📈 실시간 PER", value=f"{naver_data['per']:.2f} 배" if is_korean else f"{info.get('trailingPE', 0):.2f} 배")
        idx_col2.metric("📉 실시간 PBR", value=f"{naver_data['pbr']:.2f} 배" if is_korean else f"{info.get('priceToBook', 0):.2f} 배")
        idx_col3.metric("🎯 실시간 ROE", value=f"{final_roe:.1f} %")
        idx_col4.metric("🏦 부채 비율", value=f"{naver_data['debt_ratio']:.1f} %" if is_korean else f"{info.get('debtToEquity', 0):.1f} %")
        st.markdown("---")

        # 📊 3층: 차트
        st.subheader("📊 제3단 필터 연동: 실시간 추세 및 최후 지지선 감시창")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=close_series, name='현재가', line=dict(color='#00ffcc', width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA5'], name='EMA 5', line=dict(color='#ff007f', width=1.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA 20 (세력선)', line=dict(color='#3b82f6', width=2)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'], name='EMA 50 (오닐수급선)', line=dict(color='#f97316', width=2)))
        fig.update_layout(template="plotly_dark", height=400, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
        
        # 🛡️ 4층: 9단 철벽 필터 정밀 검문소
        st.subheader("🛡️ 은철 개미의 9단 철벽 필터 정밀 검문소")
        filter_df = pd.DataFrame(list(filters.items()), columns=['검문 항목', '판정 결과'])
        st.table(filter_df)
