import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 페이지 전체 화면 세팅
st.set_page_config(layout="wide")

# ------------------ [글로벌 및 국내 매크로 데이터 실시간 수집 엔진] ------------------
@st.cache_data(ttl=600)
def load_macro_indicators():
    tickers = {
        "KOSPI": "^KS1",
        "KOSDAQ": "^KQ1",
        "Nasdaq_Fut": "NQ=F",
        "Dow_Fut": "YM=F",
        "USD_KRW": "USDKRW=X",
        "US_10Y": "^TNX"
    }
    macro_data = {}
    for key, ticker in tickers.items():
        try:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period="5d")
            if len(hist) >= 2:
                current_val = float(hist['Close'].iloc[-1].item() if hasattr(hist['Close'].iloc[-1], 'item') else hist['Close'].iloc[-1])
                prev_val = float(hist['Close'].iloc[-2].item() if hasattr(hist['Close'].iloc[-2], 'item') else hist['Close'].iloc[-2])
                change = current_val - prev_val
                change_pct = (change / prev_val * 100) if prev_val != 0 else 0.0
                macro_data[key] = (current_val, change, change_pct)
            elif len(hist) == 1:
                current_val = float(hist['Close'].iloc[-1].item() if hasattr(hist['Close'].iloc[-1], 'item') else hist['Close'].iloc[-1])
                macro_data[key] = (current_val, 0.0, 0.0)
            else:
                macro_data[key] = (0.0, 0.0, 0.0)
        except:
            macro_data[key] = (0.0, 0.0, 0.0)
    return macro_data

macro = load_macro_indicators()

# ------------------ [상단 글로벌 & 국내 매크로 전광판 UI] ------------------
st.markdown("### 🌐 국내외 증시 및 매크로 실시간 지표판")
macro_col1, macro_col2, macro_col3, macro_col4, macro_col5, macro_col6 = st.columns(6)

with macro_col1:
    val, chg, pct = macro.get("KOSPI", (0,0,0))
    st.metric(label="🇰🇷 코스피 지수", value=f"{val:,.2f}", delta=f"{chg:+,.2f} ({pct:+.2f}%)")
with macro_col2:
    val, chg, pct = macro.get("KOSDAQ", (0,0,0))
    st.metric(label="🇰🇷 코스닥 지수", value=f"{val:,.2f}", delta=f"{chg:+,.2f} ({pct:+.2f}%)")
with macro_col3:
    val, chg, pct = macro.get("Nasdaq_Fut", (0,0,0))
    st.metric(label="🇺🇸 나스닥 100 선물", value=f"{val:,.2f}", delta=f"{chg:+,.2f} ({pct:+.2f}%)")
with macro_col4:
    val, chg, pct = macro.get("Dow_Fut", (0,0,0))
    st.metric(label="🇺🇸 다우존스 선물", value=f"{val:,.2f}", delta=f"{chg:+,.2f} ({pct:+.2f}%)")
with macro_col5:
    val, chg, pct = macro.get("USD_KRW", (0,0,0))
    st.metric(label="💵 원/달러 환율", value=f"{val:,.2f} 원", delta=f"{chg:+,.2f}원 ({pct:+.2f}%)", delta_color="inverse")
with macro_col6:
    val, chg, pct = macro.get("US_10Y", (0,0,0))
    st.metric(label="🏦 미국채 10년물 금리", value=f"{val:.3f} %", delta=f"{chg:+.3f}% ({pct:+.2f}%)", delta_color="inverse")

st.markdown("---")

# ------------------ [사이드바 수동 티커 입력 분대] ------------------
st.sidebar.markdown("### 🪖 은철 개미 수동 검문소")

# 주식 티커를 직접 입력받는 방식으로 전면 수정
input_ticker = st.sidebar.text_input(
    "🔍 검문할 종목의 티커를 입력하세요", 
    value="005930.KS", 
    help="국내 코스피는 종목코드 뒤에 .KS, 코스닥은 .KQ를 붙이십시오. (예: 삼성전자 -> 005930.KS / 미국주식은 그냥 티커 입력 예: AAPL)"
).strip()

# 사령관님이 보시는 종목이 특수자산(ETF/우선주)인지 체크박스로 직접 통제하도록 배려
is_special_asset = st.sidebar.checkbox(
    "✅ 이 종목은 ETF 또는 우선주입니까?", 
    value=False,
    help="체크하면 수급, 실적 가속도, ROE, 밸류 필터가 '특수면제' 처리되어 잡주 판정을 방지합니다."
)

is_finance = st.sidebar.checkbox(
    "🏦 이 종목은 금융주(은행/지주)입니까?", 
    value=False,
    help="체크하면 6단 재무 필터에서 부채비율 한도가 무제한으로 허용됩니다."
)

ticker = input_ticker

# 2. 데이터 수집 엔진 (야후 파이낸스 단독 질주)
@st.cache_data(ttl=1800)
def load_savita_data(ticker_symbol):
    end_date = datetime.today()
    start_date = end_date - timedelta(days=365)
    
    df = yf.download(ticker_symbol, start=start_date, end=end_date)
    kospi_df = yf.download("^KS1", start=end_date - timedelta(days=400), end=end_date)
    
    ticker_obj = yf.Ticker(ticker_symbol)
    try:
        info = ticker_obj.info
    except:
        info = {}
        
    return df, kospi_df, info

try:
    df, kospi_df, info = load_savita_data(ticker)

    if not df.empty and len(df) >= 2:
        current_price = float(df['Close'].iloc[-1].item() if hasattr(df['Close'].iloc[-1], 'item') else df['Close'].iloc[-1])
        prev_price = float(df['Close'].iloc[-2].item() if hasattr(df['Close'].iloc[-2], 'item') else df['Close'].iloc[-2])
        price_change = current_price - prev_price
        price_change_pct = (price_change / prev_price * 100) if prev_price != 0 else 0.0
        
        # 종목 한글명 또는 영문명 추출
        stock_display_name = info.get('longName', ticker)
        
        # ------------------ [실시간 종목 주가 현황판 매핑] ------------------
        title_col1, title_col2 = st.columns([2.5, 1.5])
        with title_col1:
            st.title(f"🪖 줏대 있는 은철 개미의 9단 철벽 시스템")
            st.subheader(f"▶ 현재 검문 종목: {stock_display_name} ({ticker})")
        with title_col2:
            st.metric(
                label=f"📊 현재가 (야후 지연시세 주의)", 
                value=f"{current_price:,.0f} 원" if ".KS" in ticker or ".KQ" in ticker else f"$ {current_price:,.2f}", 
                delta=f"{price_change:+,.2f} ({price_change_pct:+.2f}%)"
            )
        st.markdown("---")

        df['EMA5'] = df['Close'].ewm(span=5, adjust=False).mean()
        df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA60'] = df['Close'].ewm(span=60, adjust=False).mean()
        df['EMA120'] = df['Close'].ewm(span=120, adjust=False).mean()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()

        score = 0

        # 1단: 매크로 돈의 흐름
        if not kospi_df.empty and len(kospi_df) >= 2:
            kospi_current = float(kospi_df['Close'].iloc[-1].item() if hasattr(kospi_df['Close'].iloc[-1], 'item') else kospi_df['Close'].iloc[-1])
            kospi_ema200 = float(kospi_df['Close'].ewm(span=200, adjust=False).mean().iloc[-1].item() if hasattr(kospi_df['Close'].ewm(span=200, adjust=False).mean().iloc[-1], 'item') else kospi_df['Close'].ewm(span=200, adjust=False).mean().iloc[-1])
            if kospi_current > kospi_ema200:
                step1_pass = "✅ 합격"
                score += 1
            else:
                step1_pass = "⚠️ 경고 (현금확대)"
            kospi_desc = f"코스피 {kospi_current:,.0f} (기준선: {kospi_ema200:,.0f})"
        else:
            step1_pass = "❌ N/A"
            kospi_desc = "측정불가"

        # 2단: 수급 에너지
        held_inst = info.get('heldPercentInstitutions')
        if is_special_asset:
            step2_pass = "✅ 특수면제"
            score += 1
            held_desc = "ETF/우선주 면제 자동 적용"
        elif held_inst is not None:
            held_pct = held_inst * 100
            if held_pct > 5:
                step2_pass = "✅ 합격"
                score += 1
            else:
                step2_pass = "⚠️ 주의 (수급부족)"
            held_desc = f"기관/외인 추정지분: {held_pct:.1f}%"
        else:
            step2_pass = "⚠️ 정보부재"
            held_desc = "추정 지분 수집 제한됨"

        # 3단: 지지선 방어
        stop_loss_7 = current_price * 0.93
        step3_pass = "✅ 확정"
        score += 1

        # 4단: 실적 가속도
        trailing_eps = info.get('trailingEps')
        forward_eps = info.get('forwardEps')
        if is_special_asset:
            step4_pass = "✅ 특수면제"
            score += 1
            eps_desc = "ETF/우선주 면제 자동 적용"
        elif trailing_eps is not None and forward_eps is not None and trailing_eps != 0:
            eps_growth = ((forward_eps - trailing_eps) / abs(trailing_eps) * 100)
            if eps_growth >= 25:
                step4_pass = "✅ 합격"
                score += 1
            else:
                step4_pass = "⚠️ 불합격 (성장둔화)"
            eps_desc = f"월가 예상 성장률: {eps_growth:.1f}%"
        else:
            step4_pass = "⚠️ 정보부재"
            eps_desc = "성장률 데이터 수집 제한됨"

        # 5단: 업사이드 방패
        roe = info.get('returnOnEquity')
        if is_special_asset:
            step5_pass = "✅ 특수면제"
            score += 1
            roe_desc = "ETF/우선주 면제 자동 적용"
        elif roe is not None:
            roe_pct = roe * 100
            if roe_pct >= 15:
                step5_pass = "✅ 합격"
                score += 1
            else:
                step5_pass = "⚠️ 주의 (기준미달)"
            roe_desc = f"실제 ROE: {roe_pct:.1f}% (기준: 15% 이상)"
        else:
            step5_pass = "⚠️ 정보부재"
            roe_desc = "ROE 데이터 수집 제한됨"

        # 6단: 재무/밸류
        debt_raw = info.get('debtToEquity')
        margin_raw = info.get('operatingMargins')
        per_raw = info.get('trailingPE')
        pbr_raw = info.get('priceToBook')

        per_text = f"{per_raw:.1f}배" if per_raw is not None else "N/A"
        pbr_text = f"{pbr_raw:.1f}배" if pbr_raw is not None else "N/A"
        debt_text = f"{debt_raw:.1f}%" if debt_raw is not None else "N/A"
        margin_text = f"{margin_raw * 100:.1f}%" if margin_raw is not None else "N/A"

        if is_special_asset:
            step6_pass = "✅ 특수면제"
            score += 1
            val_desc = "ETF/우선주 면제 자동 적용"
        elif debt_raw is not None and margin_raw is not None:
            debt_limit = float('inf') if is_finance else 100
            if debt_raw <= debt_limit and (margin_raw * 100) >= 15:
                step6_pass = "✅ 합격"
                score += 1
            else:
                step6_pass = "⚠️ 주의/기준미달"
            val_desc = f"**PER: {per_text} / PBR: {pbr_text}** <br> 부채: {debt_text} / 영익률: {margin_text}"
        else:
            step6_pass = "⚠️ 정보부재"
            val_desc = f"PER: {per_text} / PBR: {pbr_text} (부채/마진 누락)"

        # 7단: 탈출용 거래량 유동성
        today_vol = float(df['Volume'].iloc[-1].item() if hasattr(df['Volume'].iloc[-1], 'item') else df['Volume'].iloc[-1])
        avg_vol_20d = float(df['Volume'].iloc[-21:-1].mean().item() if hasattr(df['Volume'].iloc[-21:-1].mean(), 'item') else df['Volume'].iloc[-21:-1].mean())
        vol_ratio = (today_vol / avg_vol_20d * 100) if (avg_vol_20d and avg_vol_20d > 0) else 100
        if vol_ratio > 100:
            step7_pass = "✅ 합격"
            score += 1
        else:
            step7_pass = "⚠️ 주의 (거래량 침체)"

        # 8단: 청렴도
        insider_sell = info.get('netPercentInsidersSharesTraded')
        if is_special_asset:
            step8_pass = "✅ 특수면제"
            score += 1
            insider_desc = "ETF/우선주 면제 자동 적용"
        elif insider_sell is not None:
            if insider_sell >= 0:
                step8_pass = "✅ 합격"
                score += 1
            else:
                step8_pass = "⚠️ 주의 (지분감소)"
            insider_desc = f"내부자 지분 변동률: {insider_sell:.2f}%"
        else:
            step8_pass = "✅ 면제/N/A"
            score += 1
            insider_desc = "내부자 거래 데이터 없음 (합격 준용)"

        # 9단: 기계적 분할 익절 타겟가 연산
        target_10 = current_price * 1.10
        target_20 = current_price * 1.20
        step9_pass = "✅ 전략수립"
        score += 1

        # 종합 판정 (9점 만점)
        if score >= 8:
            final_decision = "참전 (Buy) 강력 고려"
            decision_color = "green"
        elif score >= 5:
            final_decision = "보류 (Wait) 전략적 관망"
            decision_color = "orange"
        else:
            final_decision = "퇴각 (Sell) 철벽 권고"
            decision_color = "red"

        # ------------------ 화면 레이아웃 ------------------
        col_main1, col_main2 = st.columns([1.7, 2.7])
        
        with col_main1:
            st.subheader("📋 [은철 개미 전용 검문 요약표]")
            st.markdown(f"""
            | 단계 | 철벽 검문 항목 | 실시간 및 신뢰도 수치 구분 | 판정 | 핵심 데이터 및 수치 |
            | :--- | :--- | :---: | :--- | :--- |
            | **1단** | 돈의 흐름 (시장 지수) | **🟢 실시간** | **{step1_pass}** | {kospi_desc} |
            | **2단** | 수급 에너지 (메이저 지분) | **⚠️ 장외추정** | **{step2_pass}** | {held_desc} |
            | **3단** | 지지선 방어 (원일 오닐) | **🟢 실시간** | **{step3_pass}** | **기계적 손절가: {stop_loss_7:,.0f}원 (-7%)** |
            | **4단** | 실적 가속도 (EPS 성장) | **⚠️ 해외전망** | **{step4_pass}** | {eps_desc} |
            | **5단** | 업사이드 방패 (버핏 ROE) | **🟢 실시간** | **{step5_pass}** | **{roe_desc}** |
            | **6단** | 재무/밸류 (PER/PBR/부채) | **🟢 실시간** | **{step6_pass}** | {val_desc} |
            | **7단** | 탈출 유동성 (장중 거래량) | **🟢 실시간** | **{step7_pass}** | 평시 대비 현재 거래량: {vol_ratio:.1f}% |
            | **8단** | 내부자 청렴도 (대주주 지분) | **⚠️ 지연공시** | **{step8_pass}** | {insider_desc} |
            | **9단** | 기계적 익절 (스탑로스) | **🟢 실시간** | **{step9_pass}** | **목표가: 1차 {target_10:,.0f}원 / 2차 {target_20:,.0f}원** |
            """, unsafe_allow_html=True)

        with col_main2:
            st.subheader(f"📈 {stock_display_name} 실시간 확장 이평선 차트")
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'].squeeze(), name='현재가', line=dict(color='#00ffcc', width=2.5)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA5'].squeeze(), name='EMA 5 (단기 단타)', line=dict(color='#d62728', width=1, dash='dot')))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA20'].squeeze(), name='EMA 20 (황금 세력선)', line=dict(color='#1f77b4', width=1.5)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA60'].squeeze(), name='EMA 60 (추세 수급선)', line=dict(color='#bcbd22', width=1.2)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA120'].squeeze(), name='EMA 120 (중기 경기선)', line=dict(color='#7f7f7f', width=1.2)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA50'].squeeze(), name='⭐ EMA 50 [오닐 수급선]', line=dict(color='#ff7f0e', width=2.5)))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA200'].squeeze(), name='👑 EMA 200 [월가 생명선]', line=dict(color='#9467bd', width=3, dash='dash')))
            
            fig.update_layout(
                margin=dict(l=10, r=10, t=10, b=10), 
                height=410, 
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        
        bot_col1, bot_col2 = st.columns(2)
        with bot_col1:
            st.subheader("🕵️ [은철 개미를 위한 사비타의 브리핑]")
            st.warning("""
            💡 주황색 오닐 수급선(50일)과 보라색 월가 생명선(200일) 사이의 추세를 면밀히 감시하십시오.
            사이드바의 [ETF/우선주] 체크박스와 [금융주] 체크박스를 활용하시면, 사령관님의 투자 원칙에 맞게 기계적 필터가 유연하게 작동합니다!
            """)
            
        with bot_col2:
            st.subheader("🎯 [최종 전술 판정]")
            st.markdown(f"""
            <div style='background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center;'>
                <h2 style='color: {decision_color}; margin: 0px;'><b>{final_decision}</b></h2>
                <p style='color: gray; margin-top: 10px;'>은철 개미 9단 필터 중 총 {score}점 획득 완료 (9점 만점)</p>
            </div>
            """, unsafe_allow_html=True)

    else:
        st.error("티커를 찾을 수 없거나 데이터 수집에 실패했습니다. 올바른 티커 규칙(예: 삼성전자 005930.KS)을 입력했는지 확인하십시오.")
except Exception as e:
    st.error(f"부관 시스템 가동 오류: {e}")
