import streamlit as st
import requests
from bs4 import BeautifulSoup
import FinanceDataReader as fdr
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# 0. 페이지 기본 설정
# ─────────────────────────────────────────────
st.set_page_config(layout="wide")


def safe_float(text):
    try:
        if not text:
            return 0.0
        clean_text = str(text).replace(",", "").strip()
        if clean_text in ["", "N/A", "-", "NaN"]:
            return 0.0
        return float(clean_text)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────
# 1. 거시 지표
# ─────────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_macro_indicators():
    errors = []
    result = {}

    def fetch_last_two_close(symbol):
        start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        df = fdr.DataReader(symbol, start=start_date)
        if df.empty or len(df) < 2:
            raise ValueError(f"{symbol} 데이터 부족")
        close_curr = df['Close'].iloc[-1]
        close_prev = df['Close'].iloc[-2]
        chg_pct = ((close_curr - close_prev) / close_prev) * 100
        return close_curr, chg_pct

    for key, symbol in [
        ("kospi",   "KS11"),
        ("sp500",   "^GSPC"),
        ("usd_krw", "USD/KRW"),
        ("us10y",   "^TNX"),
    ]:
        try:
            result[key] = fetch_last_two_close(symbol)
        except Exception as e:
            errors.append(f"{key}({symbol}): {e}")
            result[key] = (0.0, 0.0)

    if errors:
        st.warning("거시지표 일부 로드 실패: " + " | ".join(errors))

    return result


# ─────────────────────────────────────────────
# 2. 네이버 증권 스크래핑 (항목별 방어 파싱)
# ─────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_naver_stock_data(code, run_mode):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    warnings_list = []

    stock_name    = "종목명 불가"
    current_price = 0.0
    per           = 0.0
    pbr           = 0.0
    industry_per  = 0.0

    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers=headers, timeout=5)
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
    except Exception as e:
        st.error(f"네이버 증권 메인 페이지 접속 실패: {e}")
        return None

    try:
        wrap = soup.find("div", {"class": "wrap_company"})
        stock_name = wrap.find("h2").text.strip() if wrap else "종목명 불가"
    except Exception as e:
        warnings_list.append(f"종목명 파싱 실패: {e}")

    try:
        rate_info = soup.find("div", {"class": "rate_info"})
        no_today  = rate_info.find("p", {"class": "no_today"}) if rate_info else None
        blind     = no_today.find("span", {"class": "blind"}) if no_today else None
        current_price = safe_float(blind.text) if blind else 0.0
        if current_price == 0.0:
            warnings_list.append("현재가 파싱 실패 (HTML 구조 변경 의심)")
    except Exception as e:
        warnings_list.append(f"현재가 파싱 실패: {e}")

    try:
        aside = soup.find("div", {"class": "aside_invest_info"})
        if aside:
            per_elem = aside.find("em", {"id": "_per"})
            pbr_elem = aside.find("em", {"id": "_pbr"})
            per = safe_float(per_elem.text) if per_elem else 0.0
            pbr = safe_float(pbr_elem.text) if pbr_elem else 0.0
        else:
            warnings_list.append("PER/PBR 영역 없음 (aside_invest_info 미검출)")
    except Exception as e:
        warnings_list.append(f"PER/PBR 파싱 실패: {e}")

    try:
        ind_table = soup.find("table", {"summary": "동일업종 PER 정보"})
        if ind_table:
            ind_em = ind_table.find("em")
            industry_per = safe_float(ind_em.text) if ind_em else 0.0
        else:
            warnings_list.append("업종 PER 테이블 미검출")
    except Exception as e:
        warnings_list.append(f"업종 PER 파싱 실패: {e}")

    net_foreigner   = 0.0
    net_institution = 0.0
    target_date_str = ""

    try:
        sub_url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        sub_res = requests.get(sub_url, headers=headers, timeout=5)
        sub_res.encoding = 'euc-kr'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        frgn_table = sub_soup.find("table", {"summary": "외국인 기관 매매동향 연속 정보"})
        rows = frgn_table.find_all("tr") if frgn_table else []

        target_row_index = 1 if run_mode == "장중 (전일 확정 데이터 조회)" else 0
        valid_row_count  = 0

        for row in rows:
            tds = row.find_all("td")
            if len(tds) >= 7:
                if valid_row_count == target_row_index:
                    target_date_str = tds[0].text.strip()
                    net_institution = safe_float(tds[5].text)
                    net_foreigner   = safe_float(tds[6].text)
                    break
                valid_row_count += 1

        if not target_date_str:
            warnings_list.append("외국인/기관 수급 행 파싱 실패 (테이블 구조 변경 의심)")

    except Exception as e:
        warnings_list.append(f"외국인/기관 수급 페이지 접속/파싱 실패: {e}")

    if warnings_list:
        with st.expander("⚠️ 네이버 증권 파싱 경고 (클릭해서 확인)", expanded=False):
            for w in warnings_list:
                st.warning(w)

    return {
        "name":            stock_name,
        "price":           current_price,
        "per":             per,
        "pbr":             pbr,
        "industry_per":    industry_per,
        "target_date":     target_date_str,
        "net_foreigner":   net_foreigner,
        "net_institution": net_institution,
    }


# ─────────────────────────────────────────────
# 3. 차트 / 보조지표
# ─────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_historical_data(code):
    try:
        df = fdr.DataReader(code)
        if df.empty:
            return None
        df = df.reset_index()

        df['EMA20']      = df['Close'].ewm(span=20, adjust=False, min_periods=20).mean()
        df['EMA50']      = df['Close'].ewm(span=50, adjust=False, min_periods=50).mean()
        df['EMA20_prev'] = df['EMA20'].shift(1)                    # 추세 방향 판단용

        df['VMA20'] = df['Volume'].rolling(window=20, min_periods=1).mean()   # 20일 평균 거래량

        df['BB_mid'] = df['Close'].rolling(window=20).mean()
        df['BB_std'] = df['Close'].rolling(window=20).std()
        df['BB_up']  = df['BB_mid'] + 2 * df['BB_std']            # 볼린저 밴드 상단
        df['BB_low'] = df['BB_mid'] - 2 * df['BB_std']            # 볼린저 밴드 하단 (차트용)

        df['H-L']  = df['High'] - df['Low']
        df['H-PC'] = (df['High'] - df['Close'].shift(1)).abs()
        df['L-PC'] = (df['Low']  - df['Close'].shift(1)).abs()
        df['TR']   = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        df['ATR']  = df['TR'].rolling(window=14, min_periods=14).mean()

        delta = df['Close'].diff()
        gain  = (delta.where(delta > 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        loss  = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        loss  = loss.replace(0, 1e-10)
        rs    = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        # fillna(50) 제거 — NaN은 NaN으로 유지, 사용처에서 pd.isna 방어

        df['Date_str'] = df['Date'].dt.strftime('%Y.%m.%d')
        df = df.tail(150)

        return df
    except Exception as e:
        st.warning(f"차트 데이터 로드 실패: {e}")
        return None


# ─────────────────────────────────────────────
# 4. 앱 본문 시작
# ─────────────────────────────────────────────
st.title("📱 주식저장소 개미의 간단 체크 퀀트 스크리너")

macro_data = get_macro_indicators()
if macro_data:
    m_cols = st.columns(4)
    with m_cols[0]:
        st.metric("국내 코스피 지수",   f"{macro_data['kospi'][0]:,.2f}",    f"{macro_data['kospi'][1]:+.2f}%")
    with m_cols[1]:
        st.metric("미국 S&P 500 지수",  f"{macro_data['sp500'][0]:,.2f}",    f"{macro_data['sp500'][1]:+.2f}%")
    with m_cols[2]:
        st.metric("원/달러 환율",       f"{macro_data['usd_krw'][0]:,.2f}원", f"{macro_data['usd_krw'][1]:+.2f}%", delta_color="inverse")
    with m_cols[3]:
        st.metric("미국채 10년물 금리", f"{macro_data['us10y'][0]:.3f}%",    f"{macro_data['us10y'][1]:+.2f}%",  delta_color="inverse")
    st.markdown("---")

mode_cols = st.columns(2)
with mode_cols[0]:
    stock_code = st.text_input("종목코드 6자리", value="005930").strip()
with mode_cols[1]:
    run_mode = st.radio(
        "⏱️ 현재 조회 시점 선택 (필수)",
        ["장 마감 후 / 주말 (최신 데이터)", "장중 (전일 확정 데이터 조회)"],
        horizontal=True
    )

if not stock_code.isdigit() or len(stock_code) != 6:
    st.error("⚠️ 6자리 숫자 코드를 입력해주세요!")
    st.stop()

basic_data = get_naver_stock_data(stock_code, run_mode)
chart_data  = get_historical_data(stock_code)

if basic_data is None:
    st.error("네이버 증권 통신 실패. 네트워크 연결 또는 상장폐지 여부를 확인해 주세요.")
    st.stop()


# ─────────────────────────────────────────────
# 5. 차트 데이터 기준일 확정
# ─────────────────────────────────────────────
is_chart_available = chart_data is not None

if not is_chart_available:
    now_price   = basic_data['price']
    latest_date = datetime.now().strftime('%Y-%m-%d (비상모드)')
    ema20       = 0.0
    ema50       = 0.0
    ema20_prev  = float('nan')
    vma20_val   = 0.0
    bb_up_val   = float('nan')
    bb_low_val  = float('nan')
    rsi_val     = float('nan')
    atr_val     = 0.0
    plot_df     = None
    latest      = None
    prev        = None
    rsi_overheat = False   # 차트 없을 때 명시적 초기화
else:
    target_date   = basic_data['target_date']
    matching_rows = chart_data[chart_data['Date_str'] == target_date]

    if len(matching_rows) > 0:
        pos     = chart_data.index.get_loc(matching_rows.index[0])
        latest  = chart_data.iloc[pos]
        prev    = chart_data.iloc[pos - 1] if pos > 0 else latest
        plot_df = chart_data.iloc[:pos + 1]
    else:
        if "장중" in run_mode and len(chart_data) > 1:
            latest  = chart_data.iloc[-2]
            prev    = chart_data.iloc[-3] if len(chart_data) > 2 else latest
            plot_df = chart_data.iloc[:-1]
        else:
            latest  = chart_data.iloc[-1]
            prev    = chart_data.iloc[-2] if len(chart_data) > 1 else latest
            plot_df = chart_data

    latest_date = latest['Date'].strftime('%Y-%m-%d')
    now_price   = latest['Close']
    ema20       = latest['EMA20']
    ema50       = latest['EMA50']
    ema20_prev  = latest['EMA20_prev']
    vma20_val   = latest['VMA20']
    bb_up_val   = latest['BB_up']
    bb_low_val  = latest['BB_low']
    rsi_val     = latest['RSI']
    atr_val     = latest['ATR']
    rsi_overheat = False   # 아래 F3 계산에서 갱신


# ─────────────────────────────────────────────
# 6. 매매 단가 설정
# ─────────────────────────────────────────────
atr_desc_text = ""   # 미정의 참조 방지 기본값

setup_cols = st.columns(3)

with setup_cols[0]:
    buy_pct    = st.number_input("대기 매수점 (기준가 대비 %)", value=-5.0, step=1.0)
    buy_target = now_price * (1 + (buy_pct / 100))
    st.caption(f"🎯 진입 단가: **{int(buy_target):,}원**")

safe_buy_target = buy_target if buy_target > 0 else (now_price if now_price > 0 else 1e-5)

with setup_cols[1]:
    target_atr_mult = st.number_input("목표 익절 가이드 (ATR 배수)", value=2.0, step=0.1)
    atr_valid = is_chart_available and not pd.isna(atr_val) and atr_val > 0
    if atr_valid:
        profit_target = buy_target + (target_atr_mult * atr_val)
        profit_pct    = ((profit_target - buy_target) / safe_buy_target) * 100
        st.caption(f"📈 예상 수익: **+{profit_pct:.1f}%** ({int(profit_target):,}원)")
        atr_desc_text = f" (ATR {int(atr_val):,}원 적용)"
    else:
        profit_target = buy_target * 1.10
        st.caption("📈 예상 수익: **+10.0%** (데이터 부족 고정치)")
        atr_desc_text = " (데이터 부족 고정 % 대체)"

with setup_cols[2]:
    loss_atr_mult = st.number_input("철벽 손절 가이드 (ATR 배수)", value=1.5, step=0.1)
    if atr_valid:
        stop_loss = max(0.0, buy_target - (loss_atr_mult * atr_val))
        loss_pct  = ((stop_loss - buy_target) / safe_buy_target) * 100
        st.caption(f"📉 예상 손실: **{loss_pct:.1f}%** ({int(stop_loss):,}원)")
    else:
        stop_loss = buy_target * 0.95
        st.caption("📉 예상 손실: **-5.0%** (데이터 부족 고정치)")


# ─────────────────────────────────────────────
# 7. 필터 점수 계산
# ─────────────────────────────────────────────
now_per = basic_data['per']
now_pbr = basic_data['pbr']
ind_per = basic_data['industry_per']
net_f   = basic_data['net_foreigner']
net_i   = basic_data['net_institution']

ETF_KEYWORDS_UPPER = ["KODEX","TIGER","KBSTAR","ARIRANG","KOSEF","HANARO","SOL","ACE","TIMEFOLIO","FOCUS","ETF"]
ETF_KEYWORDS_KR    = ["스팩"]
name_upper  = basic_data['name'].upper()
is_name_etf = (
    any(kw in name_upper for kw in ETF_KEYWORDS_UPPER) or
    any(kw in basic_data['name'] for kw in ETF_KEYWORDS_KR)
)
is_code_etf = stock_code.startswith("1")
is_real_etf = (now_per == 0.0 and now_pbr == 0.0) and (is_name_etf or is_code_etf)

# ── F1: PER ──────────────────────────────────
if is_real_etf:
    f1_score, f1_desc = 50.0, "ETF/스팩주 (가치평가 면제/중립)"
else:
    if now_per <= 0:
        f1_score, f1_desc = 30.0, "🚨 적자 기업 리스크 (진입 주의)"
    elif ind_per > 0:
        if   now_per <= ind_per * 0.85: f1_score, f1_desc = 90.0, f"PER {now_per}배 (업종 {ind_per} 대비 저평가)"
        elif now_per <= ind_per * 1.15: f1_score, f1_desc = 70.0, f"PER {now_per}배 (업종 {ind_per} 수준)"
        else:                            f1_score, f1_desc = 40.0, f"PER {now_per}배 (업종 {ind_per} 대비 고평가)"
    else:
        if   now_per < 15: f1_score, f1_desc = 90.0, f"PER {now_per}배 (절대적 밸류 우량)"
        elif now_per < 30: f1_score, f1_desc = 70.0, f"PER {now_per}배 (절대적 적정 수준)"
        else:               f1_score, f1_desc = 40.0, f"PER {now_per}배 (고평가 리스크)"

# ── F2: PBR ──────────────────────────────────
if is_real_etf:
    f2_score, f2_desc = 50.0, "ETF/스팩주 (가치평가 면제/중립)"
else:
    if   now_pbr <= 0:  f2_score, f2_desc = 30.0, "🚨 자본 잠식 리스크 (진입 주의)"
    elif now_pbr < 2.5: f2_score, f2_desc = 90.0, f"PBR {now_pbr}배 (자산가치 안정권)"
    elif now_pbr < 5.0: f2_score, f2_desc = 70.0, f"PBR {now_pbr}배 (적정 수준)"
    else:                f2_score, f2_desc = 40.0, f"PBR {now_pbr}배 (과열 상태)"

# ── F3·F4·F9: 차트 기반 ──────────────────────
if not is_chart_available or pd.isna(ema50) or pd.isna(ema20):
    f3_score, f3_desc = 50.0, "상장 초기/서버 점검으로 이평선 유보"
    f4_score, f4_desc = 50.0, "상장 초기/서버 점검으로 거래량 유보"
    f9_score, f9_desc = 50.0, "상장 초기/서버 점검으로 지지선 유보"
    # rsi_overheat은 섹션5에서 이미 False로 초기화됨
else:
    # ── F3: 추세 + 볼린저밴드 과열 이중 확인 ──
    rsi_display = f"{rsi_val:.1f}" if not pd.isna(rsi_val) else "N/A"

    if now_price > ema20 > ema50:
        f3_score, f3_desc = 95.0, f"상승 정배열 안착 (RSI: {rsi_display})"
    else:
        f3_score, f3_desc = 35.0, f"역배열 또는 추세 이탈 (RSI: {rsi_display})"

    if not pd.isna(rsi_val):
        is_over_bb = (not pd.isna(bb_up_val)) and (now_price >= bb_up_val)
        if rsi_val >= 70 and is_over_bb:
            # 수정1: f3_score가 105 초과 방지 — clamp 후 -20 적용
            f3_score = max(10.0, min(100.0, f3_score) - 20.0)
            f3_desc += " ⚠️ 과열 (RSI 70+ & 볼린저밴드 상단 돌파)"
            rsi_overheat = True
        elif rsi_val >= 70:
            # RSI만 높고 BB 미돌파 → 추세 강세 유지로 해석, 감점 없음
            f3_desc += " (RSI 70 이상이나 BB 미돌파 — 추세 강세)"
        elif rsi_val <= 30:
            f3_score = min(100.0, f3_score + 10.0)
            f3_desc += " ✨ 과매도 (반등 기대)"

    # 수정2: f3_score 최종 100점 상한 clamp (과매도 +10 후 초과 방지)
    f3_score = min(100.0, f3_score)

    # ── F4: 20일 평균 거래량(VMA20) 대비 거래량 ──
    if latest['Volume'] == 0:
        f4_score, f4_desc = 0.0, "🚨 거래정지 또는 비정상 호가 감지"
    else:
        ref_vol   = prev['VMA20'] if (prev is not None and prev['VMA20'] > 0) else (vma20_val if vma20_val > 0 else 1.0)
        vol_ratio = latest['Volume'] / ref_vol
        is_bullish_candle = latest['Close'] >= latest['Open']

        if vol_ratio >= 2.0:
            if is_bullish_candle:
                f4_score, f4_desc = 95.0, f"🔥 20일평균 {vol_ratio:.1f}배 돌파 양봉"
            else:
                f4_score, f4_desc = 25.0, f"🚨 20일평균 {vol_ratio:.1f}배 폭발 장대음봉"
        elif vol_ratio >= 1.0:
            f4_score = 75.0 if is_bullish_candle else 65.0
            f4_desc  = f"20일평균 {vol_ratio:.1f}배 (평이한 매매)"
        else:
            f4_score, f4_desc = 40.0, f"20일평균 {vol_ratio:.1f}배 소외"

    # ── F9: 이격도 + EMA20 우상향 여부 ──────────
    if pd.isna(ema20) or ema20 <= 0 or pd.isna(ema20_prev):
        f9_score, f9_desc = 50.0, "EMA20 데이터 부족으로 지지선 유보"
    else:
        disparity      = (now_price / ema20) * 100
        is_ema20_rising = ema20 >= ema20_prev

        if disparity < 50 or disparity > 200:
            f9_score, f9_desc = 50.0, "⚠️ 가격 왜곡 감지 (분할/배당락 의심)"
        elif 98 <= disparity <= 102:
            if is_ema20_rising:
                f9_score, f9_desc = 95.0, f"🎯 핵심 지지선 안착 (추세 우상향, 이격도 {disparity:.1f}%)"
            else:
                f9_score, f9_desc = 60.0, f"⚠️ 지지선 부근이나 하락 추세 (이격도 {disparity:.1f}%)"
        # 수정3: 이격도 방향성 구분 — 102 초과(과매수)와 98 미만(이격 과다) 분리
        elif disparity > 102:
            gap_score = max(30.0, 55.0 - (disparity - 102) * 1.5)   # 멀수록 감점
            f9_score  = gap_score
            f9_desc   = f"EMA20 상단 이탈 — 단기 과매수 (이격도 {disparity:.1f}%)"
        else:  # disparity < 98
            gap_score = max(30.0, 55.0 - (98 - disparity) * 1.5)    # 멀수록 감점
            f9_score  = gap_score
            f9_desc   = f"EMA20 하단 이탈 — 지지선 이탈 (이격도 {disparity:.1f}%)"

# ── F6: 수급 ─────────────────────────────────
if   net_f > 0 and net_i > 0:
    f6_score, f6_desc = 95.0, f"🎯 쌍끌이 매수 (외인:{int(net_f):,}, 기관:{int(net_i):,})"
elif net_f > 0 or net_i > 0:
    buyer = "외국인" if net_f > 0 else "기관"
    f6_score, f6_desc = 75.0, f"메이저 단일 수급 ({buyer} 매수)"
elif net_f < 0 and net_i < 0:
    f6_score, f6_desc = 35.0, f"🚨 쌍끌이 매도 리스크 (외인:{int(net_f):,}, 기관:{int(net_i):,})"
elif net_f < 0 or net_i < 0:
    seller = "외국인" if net_f < 0 else "기관"
    f6_score, f6_desc = 45.0, f"메이저 단일 이탈 ({seller} 매도)"
else:
    f6_score, f6_desc = 50.0, "메이저 수급 없음 (관망/소외)"


# ─────────────────────────────────────────────
# 8. 정성적 필터 (수동 슬라이더 — 세로 배치로 모바일 오터치 방지)
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 💡 정성적 필터 수동 체크")
f5_score = st.slider("L: 주도주 매력도 판단  (0=최악 / 100=최고)", 0, 100, 50, step=5)
f7_score = st.slider("M: 시장 위험도 판단    (0=최악 / 100=최고)", 0, 100, 50, step=5)
f8_score = st.slider("Quant: 경영진/공시 리스크 (0=최악 / 100=최고)", 0, 100, 50, step=5)


# ─────────────────────────────────────────────
# 9. 총점 계산 — 동적 가중치
#
# 가중치 설계:
#   높음(x1.5): 추세(f3), 거래량(f4), 수급(f6)  ← 실전 타이밍 핵심
#   보통(x1.0): PER(f1), PBR(f2), 지지선(f9)    ← 기본 필터
#   낮음(x0.5): 수동입력(f5, f7, f8)             ← 주관적 보조
#
# 일반주 가중치 합: 1+1+1.5+1.5+0.5+1.5+0.5+0.5+1.0 = 9.0
# ETF   가중치 합: 1.5+1.5+0.5+1.5+0.5+0.5+1.0      = 7.0
# → 각각 해당 합으로 나눠야 0~100 스케일 유지
# ─────────────────────────────────────────────
if is_real_etf:
    raw = (f3_score*1.5 + f4_score*1.5 + f5_score*0.5
           + f6_score*1.5 + f7_score*0.5 + f8_score*0.5 + f9_score*1.0)
    total_score = int(raw / 7.0)
else:
    raw = (f1_score*1.0 + f2_score*1.0 + f3_score*1.5 + f4_score*1.5
           + f5_score*0.5 + f6_score*1.5 + f7_score*0.5 + f8_score*0.5 + f9_score*1.0)
    total_score = int(raw / 9.0)

total_score = min(100, max(0, total_score))   # 수정4: 최종 0~100 clamp 보장


# ─────────────────────────────────────────────
# 10. 리포트 출력
# ─────────────────────────────────────────────
st.markdown("---")
st.subheader(f"📊 {basic_data['name']} ({stock_code}) 종목 선별 리포트")

left_col, right_col = st.columns([1, 3])

with left_col:
    with st.container(border=True):
        st.markdown("### **철벽 필터 총점**")
        main_color = "#2ECC71" if total_score >= 80 else "#F1C40F" if total_score >= 60 else "#E74C3C"

        vol_zero = is_chart_available and latest is not None and latest['Volume'] == 0

        if vol_zero:
            sig_color, sig_text, sig_desc = "#E74C3C", "🔴 RED / 진입 불가",    "거래정지 또는 비정상 호가입니다."
        elif total_score >= 80 and not rsi_overheat:
            sig_color, sig_text, sig_desc = "#2ECC71", "🟢 GREEN / 진입 적합",  "가중치 필터 통과. 타점 진입을 고려하세요."
        elif total_score >= 80 and rsi_overheat:
            sig_color, sig_text, sig_desc = "#F1C40F", "🟡 YELLOW / 눌림 대기", "완벽하나 단기 과열(BB 상단)입니다. 눌림을 기다리세요."
        elif total_score >= 60:
            sig_color, sig_text, sig_desc = "#F1C40F", "🟡 YELLOW / 관망 유지", "에너지가 부족합니다. 수급/돌파를 확인하세요."
        else:
            sig_color, sig_text, sig_desc = "#E74C3C", "🔴 RED / 진입 부적합",  "필터 미달. 매수 버튼에서 손을 떼십시오."

        st.markdown(
            f"<h1 style='color:{main_color};text-align:center;font-size:60px;margin-bottom:0;'>"
            f"{total_score} <span style='font-size:24px;'>점</span></h1>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='text-align:center;padding:10px;margin-bottom:15px;"
            f"background-color:{sig_color}15;border-radius:8px;border:1.5px solid {sig_color};'>"
            f"<h4 style='color:{sig_color};margin:0;font-weight:bold;'>{sig_text}</h4>"
            f"<span style='font-size:13px;color:gray;'>{sig_desc}</span></div>",
            unsafe_allow_html=True
        )

        st.markdown(f"**확정 기준일 ({latest_date}):** {int(now_price):,}원")
        st.caption(f"PER: {now_per}배 | PBR: {now_pbr}배")
        st.markdown("---")
        st.markdown("### **🎯 매매 전략 단가**")
        st.success(f"대기 매수선: {int(buy_target):,}원")
        st.error(  f"철벽 손절선: {int(stop_loss):,}원"    + atr_desc_text)
        st.info(   f"목표 익절선: {int(profit_target):,}원" + atr_desc_text)

with right_col:
    if is_chart_available and plot_df is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df['Date'], y=plot_df['Close'],
            name='종가 추이', line=dict(color='black', width=2)
        ))
        fig.add_trace(go.Scatter(
            x=plot_df['Date'], y=plot_df['EMA20'],
            name='EMA20', line=dict(color='blue', dash='dot')
        ))
        fig.add_trace(go.Scatter(
            x=plot_df['Date'], y=plot_df['EMA50'],
            name='EMA50', line=dict(color='orange')
        ))
        # 수정1: opacity 파라미터 제거 → rgba 색상으로 투명도 적용
        fig.add_trace(go.Scatter(
            x=plot_df['Date'], y=plot_df['BB_up'],
            name='BB상단(과열선)',
            line=dict(color='rgba(220,50,50,0.45)', width=1, dash='dot')
        ))
        fig.add_trace(go.Scatter(
            x=plot_df['Date'], y=plot_df['BB_low'],
            name='BB하단(지지선)',
            line=dict(color='rgba(50,150,50,0.45)', width=1, dash='dot')
        ))
        fig.update_layout(
            height=300,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ 현재 한국거래소(FDR) 서버 점검으로 차트 출력을 생략하고 비상 정량 점수만 표출합니다.")

    st.markdown("---")

    all_filters = [
        {"title": "C: 가치/성장성 (PER)",      "score": f1_score, "desc": f1_desc},
        {"title": "A: 자본/수익성 (PBR)",       "score": f2_score, "desc": f2_desc},
        {"title": "N: 신고가/추세 (EMA) ★",    "score": f3_score, "desc": f3_desc},
        {"title": "S: 거래량 돌파 (VMA20) ★",  "score": f4_score, "desc": f4_desc},
        {"title": "L: 주도주 매력도 (업황)",    "score": f5_score, "desc": "정성적 판단 (가중치↓)"},
        {"title": "I: 메이저 수급 (외인/기관) ★","score": f6_score, "desc": f6_desc},
        {"title": "M: 시장 방향성 (지수)",      "score": f7_score, "desc": "정성적 판단 (가중치↓)"},
        {"title": "Quant: 경영/공시 리스크",    "score": f8_score, "desc": "정성적 판단 (가중치↓)"},
        {"title": "Quant: 차트 지지선 확인",    "score": f9_score, "desc": f9_desc if is_chart_available else "서버점검"},
    ]

    for i in range(0, 9, 3):
        grid_cols = st.columns(3)
        for j in range(3):
            if i + j < 9:
                item = all_filters[i + j]
                with grid_cols[j]:
                    with st.container(border=True):
                        st.markdown(f"**{item['title']}**")
                        color = "#2ECC71" if item['score'] >= 80 else "#F1C40F" if item['score'] >= 50 else "#E74C3C"
                        st.markdown(
                            f"<h3 style='color:{color};margin:0;'>{item['score']} 점</h3>",
                            unsafe_allow_html=True
                        )
                        st.caption(item['desc'])
