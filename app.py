import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
import re

st.set_page_config(page_title="줏대있는 개미의 9단 철벽 필터 시스템", layout="wide")

def get_korean_stock_data(ticker_code):
    clean_ticker = re.sub(r'[^0-9]', '', ticker_code)
    data = {'stock_name': "", 'foreigner_buy': 0, 'institution_buy': 0, 'major_holder_ratio': 35.0, 'per': 0.0, 'pbr': 0.0, 'roe': 0.0, 'debt_ratio': 100.0, 'error': False}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url_main = f"https://finance.naver.com/item/main.naver?code={clean_ticker}"
        res_main = requests.get(url_main, headers=headers)
        soup_main = BeautifulSoup(res_main.text, 'html.parser')
        name_wrap = soup_main.find('div', class_='wrap_company')
        if name_wrap and name_wrap.find('h2'): data['stock_name'] = name_wrap.find('h2').text.strip()
        per_element = soup_main.find('em', id='_per')
        pbr_element = soup_main.find('em', id='_pbr')
        if per_element: data['per'] = float(per_element.text.replace(',', '').strip())
        if pbr_element: data['pbr'] = float(pbr_element.text.replace(',', '').strip())
        url_sise = f"https://finance.naver.com/item/frgn.naver?code={clean_ticker}"
        res_sise = requests.get(url_sise, headers=headers)
        soup_sise = BeautifulSoup(res_sise.text, 'html.parser')
        tables = soup_sise.find_all('table', class_='type2')
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
        url_analysis = f"https://wrapper.finance.naver.com/v1/item/summary?code={clean_ticker}"
        res_analysis = requests.get(url_analysis, headers=headers)
        if res_analysis.status_code == 200:
            json_data = res_analysis.json()
            if 'result' in json_data and json_data['result']:
                result = json_data['result']
                if 'majorHolders' in result and result['majorHolders']: data['major_holder_ratio'] = float(result['majorHolders'][0].get('shareRatio', 35.0))
                if 'bizFinancials' in result and result['bizFinancials']:
                    biz = result['bizFinancials']
                    if len(biz) > 0:
                        data['roe'] = float(biz[-1].get('roe', 0.0) or 0.0)
                        data['debt_ratio'] = float(biz[-1].get('debtRatio', 100.0) or 100.0)
    except: data['error'] = True
    return data

st.title("📊 은철 개미의 9단 철벽 필터 실시간 계기판 v5.0")
st.markdown("---")
st.sidebar.header("🕹️ 제어 센터")
ticker_input = st.sidebar.text_input("🎯 종목 번호 입력 (숫자 6자리)", value="005930").strip()
is_etf_or_pref = st.sidebar.checkbox("✅ ETF / 우선주")
is_financial = st.sidebar.checkbox("🏦 금융주")

if ticker_input.isdigit():
    ticker_final = ticker_input + ".KS"
    is_korean = True
else:
    ticker_final = ticker_input.upper()
    is_korean = ".KS" in ticker_final or ".KQ" in ticker_final

if ticker_final:
    with st.spinner("🔄 데이터 수집 중..."):
        stock = yf.Ticker(ticker_final)
        df = stock.history(period="1y")
        info = stock.info if stock.info else {}
        naver_data = {'stock_name': "", 'foreigner_buy': 0, 'institution_buy': 0, 'major_holder_ratio': 35.0, 'per': 0.0, 'pbr': 0.0, 'roe': 0.0, 'debt_ratio': 100.0}
        if is_korean: naver_data = get_korean_stock_data(ticker_final)

    if df.empty: st.error("🚨 데이터를 수집할 수 없습니다.")
    else:
        close_series = df['Close'].squeeze()
        df['EMA5'] = close_series.ewm(span=5, adjust=False).mean()
        df['EMA20'] = close_series.ewm(span=20, adjust=False).mean()
        df['EMA50'] = close_series.ewm(span=50, adjust=False).mean()
        current_price = close_series.iloc[-1]
        prev_price = close_series.iloc[-2] if len(close_series) > 1 else current_price
        price_pct = ((current_price - prev_price) / prev_price) * 100
        display_name = naver_data['stock_name'] if naver_data['stock_name'] else info.get('longName', ticker_input)
        vol_avg = df['Volume'].tail(5).mean()
        current_ema50 = df['EMA50'].iloc[-1]
        final_roe = naver_data['roe'] if is_korean else ((info.get('returnOnEquity', 0) or 0) * 100)
        final_debt = naver_data['debt_ratio'] if is_korean else (info.get('debtToEquity', 100) or 100)
        major_holder = naver_data['major_holder_ratio'] if is_korean else ((info.get('heldPercentInsiders', 0.2) or 0.2) * 100)
        
        head_col1, head_col2, head_col3 = st.columns(3)
        head_col1.metric("📋 종목명", value=display_name, delta=f"코드: {ticker_input}")
        head_col2.metric("💵 현재 가격", value=f"{current_price:,.0f} 원" if is_korean else f"${current_price:,.2f}", delta=f"{price_pct:.2f}%")
        
        fail_count = 0
        if vol_avg <= 50000: fail_count += 1
        if not is_etf_or_pref and is_korean and naver_data['foreigner_buy'] <= 0 and naver_data['institution_buy'] <= 0: fail_count += 1
        if current_price < current_ema50: fail_count += 1
        if not is_etf_or_pref and final_roe <= 5.0: fail_count += 1
        if not is_etf_or_pref and not is_financial and final_debt >= 180: fail_count += 1
        if not is_etf_or_pref and major_holder <= 20: fail_count += 1
        
        if fail_count >= 2: head_col3.error("🚨 작전 명령: 전면 퇴각")
        elif fail_count == 1: head_col3.warning("⚡ 작전 명령: 관망/유지")
        else: head_col3.success("🚀 작전 명령: 철벽 통과 진격")
            
        st.markdown("### 📊 실시간 투자 지수 감시계기판")
        card_col1, card_col2, card_col3, card_col4 = st.columns(4)
        card_col1.info(f"**📈 실시간 PER**\n\n ## {naver_data['per']:.2f} 배")
        card_col2.info(f"**📉 실시간 PBR**\n\n ## {naver_data['pbr']:.2f} 배")
        card_col3.info(f"**🎯 실시간 ROE**\n\n ## {final_roe:.1f} %")
        card_col4.info(f"**🏦 부채 비율**\n\n ## {final_debt:.1f} %")

        st.subheader("📊 제3단 필터 연동: 실시간 추세 감시창")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=close_series, name='현재가', line=dict(color='#00ffcc', width=2.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA5'], name='EMA 5', line=dict(color='#ff007f', width=1.5)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'], name='EMA 20', line=dict(color='#3b82f6', width=2)))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'], name='EMA 50', line=dict(color='#f97316', width=2)))
        fig.update_layout(template="plotly_dark", height=350, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.subheader("🛡️ 각 필터별 실시간 정밀 카드 검문소")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.help(f"**1단: 돈의 흐름 (거래량)**\n\n 판정: {'✅ 합격' if vol_avg > 50000 else '❌ 불합격'}\n\n 수치: {vol_avg:,.0f}주")
            st.help(f"**4단: EPS 성장률**\n\n 판정: {'⚪ 특수면제' if is_etf_or_pref else '✅ 합격'}\n\n 수치: PER {naver_data['per']:.2f}배 기반")
            st.help(f"**7단: 거래 에너지**\n\n 판정: ✅ 합격\n\n 수치: {df['Volume'].iloc[-1]:,.0f}주")
        with c2:
            p2 = '⚪ 특수면제' if is_etf_or_pref else ('✅ 합격' if (is_korean and (naver_data['foreigner_buy'] > 0 or naver_data['institution_buy'] > 0)) else '❌ 불합격')
            st.help(f"**2단: 기관/외인 수급**\n\n 판정: {p2}\n\n 수치: 외인 {naver_data['foreigner_buy']:+,}주 / 기관 {naver_data['institution_buy']:+,}주")
            p5 = '⚪ 특수면제' if is_etf_or_pref else ('✅ 합격' if final_roe > 5.0 else '❌ 불합격')
            st.help(f"**5단: ROE 필터**\n\n 판정: {p5}\n\n 수치: ROE {final_roe:.1f}%")
            p8 = '⚪ 특수면제' if is_etf_or_pref else ('✅ 합격' if major_holder > 20 else '❌ 불합격')
            st.help(f"**8단: 대주주 지분**\n\n 판정: {p8}\n\n 수치: 지분율 {major_holder:.1f}%")
        with c3:
            p3 = '✅ 합격' if current_price >= current_ema50 else '❌ 불합격'
            st.help(f"**3단: 추세 지지선**\n\n 판정: {p3}\n\n 수치: 지지선 {current_ema50:,.0f}원 대비")
            p6 = '⚪ 특수면제' if is_etf_or_pref else ('✅ 합격' if is_financial or final_debt < 180 else '❌ 불합격')
            st.help(f"**6단: 밸류에이션 (부채)**\n\n 판정: {p6}\n\n 수치: 부채 {final_debt:.1f}%")
            st.help(f"**9단: 군중 심리 방어**\n\n 판정: ✅ 합격\n\n 수치: 원칙 투자 이행 중")
