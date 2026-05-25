import streamlit as st
import requests
from bs4 import BeautifulSoup
import FinanceDataReader as fdr
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
import zipfile
import io
import xml.etree.ElementTree as ET

# 🎯 [핵심] 여기에 발급받으신 40자리 DART API 키를 붙여넣으십시오.
DART_API_KEY = "17143d9c12272709c328c8e3276d8fbc9dbca5a5"

# ─────────────────────────────────────────────
# 0. 페이지 기본 설정
# ─────────────────────────────────────────────
st.set_page_config(layout="wide")

def safe_float(text):
    try:
        if not text: return 0.0
        clean_text = str(text).replace(",", "").strip()
        if clean_text in ["", "N/A", "-", "NaN"]: return 0.0
        return float(clean_text)
    except Exception:
        return 0.0

def get_any_key(d, keys):
    for k in keys:
        if k in d and d[k] is not None:
            return str(d[k])
    return '0'

# ─────────────────────────────────────────────
# 1. 거시 지표 (NaN 폭탄 방어 탑재)
# ─────────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_macro_indicators():
    errors = []
    result = {}
    def fetch_last_two_close(symbol):
        start_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        df = fdr.DataReader(symbol, start=start_date)
        if df.empty or len(df) < 2:
            return 0.0, 0.0
        
        close_curr = df['Close'].iloc[-1]
        close_prev = df['Close'].iloc[-2]
        
        if pd.isna(close_curr): close_curr = 0.0
        if pd.isna(close_prev) or close_prev == 0: 
            chg_pct = 0.0
        else:
            chg_pct = ((close_curr - close_prev) / close_prev) * 100
        
        return close_curr, chg_pct

    for key, symbol in [("kospi", "KS11"), ("sp500", "^GSPC"), ("usd_krw", "USD/KRW"), ("us10y", "^TNX")]:
        try:
            result[key] = fetch_last_two_close(symbol)
        except Exception as e:
            errors.append(f"{key}({symbol}): {e}")
            result[key] = (0.0, 0.0)

    if errors: st.warning("거시지표 일부 로드 실패: " + " | ".join(errors))
    return result

# ─────────────────────────────────────────────
# 2. 네이버 증권 듀얼 엔진 (모바일 JSON API ➔ PC HTML 폴백)
# ─────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_naver_stock_data(code, run_mode):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    warnings_list = []
    
    stock_name, current_price, per, pbr, industry_per = "종목명 불가", 0.0, 0.0, 0.0, 0.0
    net_foreigner, net_institution, target_date_str = 0.0, 0.0, ""
    
    session = requests.Session()

    # 💡 [엔진 1] 모바일 JSON API 정밀 타격
    try:
        # 1-1. 기본 정보 (주가, PER 등)
        url_basic = f"https://m.stock.naver.com/api/stock/{code}/basic"
        res_basic = session.get(url_basic, headers=headers, timeout=5)
        if res_basic.status_code == 200:
            data = res_basic.json()
            stock_name    = data.get('stockName', '종목명 불가')
            current_price = safe_float(data.get('closePrice', '0'))
            per           = safe_float(data.get('per', '0'))
            pbr           = safe_float(data.get('pbr', '0'))
            industry_per  = safe_float(data.get('cnsPer', '0'))

        # 1-2. 투자자 매매동향 (메이저 수급)
        url_inv = f"https://m.stock.naver.com/api/stock/{code}/investor/days"
        res_inv = session.get(url_inv, headers=headers, timeout=5)
        if res_inv.status_code == 200:
            inv_data = res_inv.json()
            items = inv_data if isinstance(inv_data, list) else inv_data.get('items', [])
            if items:
                target_idx = 1 if run_mode == "장중 (전일 확정 데이터 조회)" else 0
                if target_idx < len(items):
                    t_item = items[target_idx]
                    target_date_str = str(t_item.get('localDate', t_item.get('bizdate', '')))
                    
                    net_inst_str = get_any_key(t_item, ['institutionalNetBuyVol', 'instPureBuyQuant', 'instNetBuyVol'])
                    net_frgn_str = get_any_key(t_item, ['foreignNetBuyVol', 'frgnPureBuyQuant', 'foreignNetBuyQuant'])
                    
                    net_institution = safe_float(net_inst_str)
                    net_foreigner   = safe_float(net_frgn_str)
    except Exception as e:
        warnings_list.append(f"모바일 JSON API 에러 (PC 폴백 가동 예정): {e}")

    # 💡 [엔진 2] 보완 완벽 수술: 기본 정보 및 수급 데이터 누락 시 PC HTML 크롤링으로 자동 우회
    if current_price == 0.0 or stock_name == "종목명 불가" or not target_date_str:
        try:
            url = f"https://finance.naver.com/item/main.naver?code={code}"
            res = session.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.content, 'html.parser')

            wrap = soup.find("div", {"class": "wrap_company"})
            if wrap: stock_name = wrap.find("h2").text.strip()
            
            rate_info = soup.find("div", {"class": "rate_info"})
            if rate_info:
                blind = rate_info.find("span", {"class": "blind"})
                if blind: current_price = safe_float(blind.text)
                
            aside = soup.find("div", {"class": "aside_invest_info"})
            if aside:
                per_e, pbr_e = aside.find("em", {"id": "_per"}), aside.find("em", {"id": "_pbr"})
                if per_e: per = safe_float(per_e.text)
                if pbr_e: pbr = safe_float(pbr_e.text)
                
            ind_table = soup.find("table", {"summary": "동일업종 PER 정보"})
            if ind_table and ind_table.find("em"): industry_per = safe_float(ind_table.find("em").text)
            
            sub_url = f"https://finance.naver.com/item/frgn.naver?code={code}"
            sub_res = session.get(sub_url, headers=headers, timeout=5)
            sub_soup = BeautifulSoup(sub_res.content, 'html.parser')

            frgn_table = sub_soup.find("table", {"summary": "외국인 기관 매매동향 연속 정보"})
            rows = frgn_table.find_all("tr") if frgn_table else []
            t_idx = 1 if run_mode == "장중 (전일 확정 데이터 조회)" else 0
            v_count = 0
            
            for row in rows:
                tds = row.find_all("td")
                if len(tds) >= 7:
                    if v_count == t_idx:
                        target_date_str = tds[0].text.strip()
                        net_institution = safe_float(tds[5].text)
                        net_foreigner = safe_float(tds[6].text)
                        break
                    v_count += 1
        except Exception as e:
            warnings_list.append(f"PC 웹 폴백 크롤링 최종 실패: {e}")

    # 💡 [핵심 수술] 차트 매칭을 위한 날짜 포맷 규격 정상화 (무조건 YYYY.MM.DD 변환)
    if target_date_str:
        clean_date = target_date_str.replace("-", "").replace(".", "").strip()
        if len(clean_date) == 8 and clean_date.isdigit():
            target_date_str = f"{clean_date[:4]}.{clean_date[4:6]}.{clean_date[6:]}"

    if warnings_list: st.warning("⚠️ 데이터 동기화 알림: " + " | ".join(warnings_list[:1]))

    return {
        "name": stock_name, "price": current_price, "per": per, "pbr": pbr,
        "industry_per": industry_per, "target_date": target_date_str,
        "net_foreigner": net_foreigner, "net_institution": net_institution
    }

# ─────────────────────────────────────────────
# 2.5. DART 전자공시 API 연동 (재무 엑스레이)
# ─────────────────────────────────────────────
@st.cache_data(ttl=86400)
def get_dart_mapping(api_key):
    if api_key == "여기에_선생님_키를_붙여넣으세요" or not api_key: return {}
    try:
        url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}"
        res = requests.get(url, timeout=20)
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xml_data = z.read('CORPCODE.xml')
        root = ET.fromstring(xml_data)
        return {node.find('stock_code').text: node.find('corp_code').text for node in root.findall('list') if node.find('stock_code').text}
    except Exception as e:
        st.warning(f"⚠️ DART 기업코드 매핑 실패 (API 키 확인 필요): {e}")
        return {}

@st.cache_data(ttl=3600)
def get_dart_fundamentals(api_key, stock_code):
    mapping = get_dart_mapping(api_key)
    corp_code = mapping.get(stock_code)
    if not corp_code: return None

    for year_offset in [1, 2]:
        year = str(datetime.now().year - year_offset)
        for acnt_type in ["fnlttCnsldtAcnt", "fnlttSinglAcnt"]:
            url = f"https://opendart.fss.or.kr/api/{acnt_type}.json?crtfc_key={api_key}&corp_code={corp_code}&bsns_year={year}&reprt_code=11011"
            try:
                res = requests.get(url, timeout=10).json()
                if res.get('status') != '000': continue

                data = res['list']
                
                def get_val(keywords):
                    for item in data:
                        clean_nm = item['account_nm'].replace(" ", "")
                        if any(kw in clean_nm for kw in keywords):
                            return safe_float(item['thstrm_amount'])
                    return 0.0

                revenue     = get_val(['매출액', '영업수익'])
                op_income   = get_val(['영업이익'])
                equity      = get_val(['자본총계'])
                liabilities = get_val(['부채총계'])
                net_income  = get_val(['순이익', '당기순이익'])

                return {
                    "year": year,
                    "acnt_type": "연결" if acnt_type == "fnlttCnsldtAcnt" else "별도",
                    "op_margin":  (op_income  / revenue * 100) if revenue > 0 else 0.0,
                    "debt_ratio": (liabilities / equity  * 100) if equity  > 0 else 0.0,
                    "roe":        (net_income  / equity  * 100) if equity  > 0 else 0.0,
                }
            except Exception:
                continue
    return None

# ─────────────────────────────────────────────
# 3. 차트 / 보조지표
# ─────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_historical_data(code):
    try:
        df = fdr.DataReader(code)
        if df.empty: return None
        df = df.reset_index()

        df['EMA20']      = df['Close'].ewm(span=20, adjust=False, min_periods=20).mean()
        df['EMA50']      = df['Close'].ewm(span=50, adjust=False, min_periods=50).mean()
        df['EMA20_prev'] = df['EMA20'].shift(1)
        df['VMA20']      = df['Volume'].rolling(window=20, min_periods=1).mean()

        df['BB_mid'] = df['Close'].rolling(window=20).mean()
        df['BB_std'] = df['Close'].rolling(window=20).std()
        df['BB_up']  = df['BB_mid'] + 2 * df['BB_std']
        df['BB_low'] = df['BB_mid'] - 2 * df['BB_std']

        df['H-L']  = df['High'] - df['Low']
        df['H-PC'] = (df['High'] - df['Close'].shift(1)).abs()
        df['L-PC'] = (df['Low']  - df['Close'].shift(1)).abs()
        df['TR']   = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        df['ATR']  = df['TR'].rolling(window=14, min_periods=14).mean()

        delta = df['Close'].diff()
        gain  = (delta.where(delta > 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        loss  = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        df['RSI'] = 100 - (100 / (1 + rs))

        df['Date_str'] = df['Date'].dt.strftime('%Y.%m.%d')
        return df.tail(150)
    except Exception as e:
        st.warning(f"차트 데이터 로드 실패: {e}")
        return None

# ─────────────────────────────────────────────
# 4. 앱 본문 시작
# ─────────────────────────────────────────────
st.title("📱 주식저장소 개미의 1차 퀀트 스크리너")

macro_data = get_macro_indicators()
if macro_data:
    m_cols = st.columns(4)
    kospi_v, kospi_c = macro_data['kospi']
    sp500_v, sp500_c = macro_data['sp500']
    usd_v, usd_c     = macro_data['usd_krw']
    us10y_v, us10y_c = macro_data['us10y']
    
    with m_cols[0]: st.metric("국내 코스피 지수", f"{kospi_v:,.2f}", f"{kospi_c:+.2f}%")
    with m_cols[1]: st.metric("미국 S&P 500 지수", f"{sp500_v:,.2f}", f"{sp500_c:+.2f}%")
    with m_cols[2]: st.metric("원/달러 환율", f"{usd_v:,.2f}원", f"{usd_c:+.2f}%", delta_color="inverse")
    with m_cols[3]: 
        if us10y_v == 0.0: st.metric("미국채 10년물 금리", "데이터 지연", "0.0%")
        else: st.metric("미국채 10년물 금리", f"{us10y_v:.3f}%", f"{us10y_c:+.2f}%", delta_color="inverse")
    st.markdown("---")

mode_cols = st.columns(2)
with mode_cols[0]: stock_code = st.text_input("종목코드 6자리", value="005930").strip()
with mode_cols[1]: run_mode = st.radio("⏱️ 현재 조회 시점 선택 (필수)", ["장 마감 후 / 주말 (최신 데이터)", "장중 (전일 확정 데이터 조회)"], horizontal=True)

if not stock_code.isdigit() or len(stock_code) != 6:
    st.error("⚠️ 6자리 숫자 코드를 입력해주세요!")
    st.stop()

basic_data = get_naver_stock_data(stock_code, run_mode)
chart_data = get_historical_data(stock_code)
dart_data  = get_dart_fundamentals(DART_API_KEY, stock_code)

if basic_data is None:
    st.error("데이터 서버 통신 실패. 네트워크 상태나 종목코드를 확인해 주세요.")
    st.stop()

if dart_data: st.info(f"✅ DART 재무 엑스레이 연결 성공 | {dart_data['year']}년 {dart_data['acnt_type']} 재무제표 기준")

# ─────────────────────────────────────────────
# 5. 차트 데이터 기준일 확정
# ─────────────────────────────────────────────
is_chart_available = chart_data is not None

if not is_chart_available:
    now_price = basic_data['price']
    latest_date = datetime.now().strftime('%Y-%m-%d (비상모드)')
    ema20 = ema50 = vma20_val = atr_val = 0.0
    ema20_prev = bb_up_val = bb_low_val = rsi_val = float('nan')
    plot_df = latest = prev = None
    rsi_overheat = False
else:
    target_date = basic_data['target_date']
    matching_rows = chart_data[chart_data['Date_str'] == target_date]

    if len(matching_rows) > 0:
        pos = chart_data.index.get_loc(matching_rows.index[0])
        latest = chart_data.iloc[pos]
        prev = chart_data.iloc[pos - 1] if pos > 0 else latest
        plot_df = chart_data.iloc[:pos + 1]
    else:
        if "장중" in run_mode and len(chart_data) > 1:
            latest = chart_data.iloc[-2]
            prev = chart_data.iloc[-3] if len(chart_data) > 2 else chart_data.iloc[-2]
            plot_df = chart_data.iloc[:-1]
        else:
            latest = chart_data.iloc[-1]
            prev = chart_data.iloc[-2] if len(chart_data) > 1 else chart_data.iloc[-1]
            plot_df = chart_data

    latest_date = latest['Date'].strftime('%Y-%m-%d')
    now_price = latest['Close']
    ema20, ema50, ema20_prev = latest['EMA20'], latest['EMA50'], latest['EMA20_prev']
    vma20_val, bb_up_val, bb_low_val = latest['VMA20'], latest['BB_up'], latest['BB_low']
    rsi_val, atr_val = latest['RSI'], latest['ATR']
    rsi_overheat = False

# ─────────────────────────────────────────────
# 6. 매매 단가 설정
# ─────────────────────────────────────────────
atr_desc_text = ""
setup_cols = st.columns(3)

with setup_cols[0]:
    buy_pct = st.number_input("대기 매수점 (기준가 대비 %)", value=-5.0, step=1.0)
    buy_target = now_price * (1 + (buy_pct / 100))
    st.caption(f"🎯 진입 단가: **{int(buy_target):,}원**")

safe_buy_target = buy_target if buy_target > 0 else (now_price if now_price > 0 else 1e-5)

with setup_cols[1]:
    target_atr_mult = st.number_input("목표 익절 가이드 (ATR 배수)", value=2.0, step=0.1)
    atr_valid = is_chart_available and not pd.isna(atr_val) and atr_val > 0
    if atr_valid:
        profit_target = buy_target + (target_atr_mult * atr_val)
        st.caption(f"📈 예상 수익: **+{((profit_target - buy_target) / safe_buy_target) * 100:.1f}%** ({int(profit_target):,}원)")
        atr_desc_text = f" (ATR {int(atr_val):,}원 적용)"
    else:
        profit_target = buy_target * 1.10
        st.caption("📈 예상 수익: **+10.0%** (데이터 부족)")
        atr_desc_text = " (고정 % 대체)"

with setup_cols[2]:
    loss_atr_mult = st.number_input("철벽 손절 가이드 (ATR 배수)", value=1.5, step=0.1)
    if atr_valid:
        stop_loss = max(0.0, buy_target - (loss_atr_mult * atr_val))
        st.caption(f"📉 예상 손실: **{((stop_loss - buy_target) / safe_buy_target) * 100:.1f}%** ({int(stop_loss):,}원)")
    else:
        stop_loss = buy_target * 0.95
        st.caption("📉 예상 손실: **-5.0%** (데이터 부족)")

# ─────────────────────────────────────────────
# 7. 필터 점수 계산 (DART API 우선 적용)
# ─────────────────────────────────────────────
now_per, now_pbr, ind_per = basic_data['per'], basic_data['pbr'], basic_data['industry_per']
net_f, net_i = basic_data['net_foreigner'], basic_data['net_institution']

is_real_etf = (now_per == 0.0 and now_pbr == 0.0) and (
    any(kw in basic_data['name'].upper() for kw in ["KODEX","TIGER","KBSTAR","ARIRANG","KOSEF","HANARO","SOL","ACE","TIMEFOLIO","FOCUS","ETF","스팩"])
    or stock_code.startswith("1")
)

# ── F1, F2, F8: 재무 엔진 ──
if is_real_etf:
    f1_score, f1_desc = 50, "ETF/스팩주 (가치평가 중립)"
    f2_score, f2_desc = 50, "ETF/스팩주 (자본평가 중립)"
    f8_score, f8_desc = 50, "ETF/스팩주 (개별 리스크 중립)"
elif dart_data:
    opm = dart_data['op_margin']
    if opm >= 15: f1_score, f1_desc = 95, f"영업이익률 {opm:.1f}% (초우량 수익성)"
    elif opm >= 5: f1_score, f1_desc = 75, f"영업이익률 {opm:.1f}% (안정적 수익)"
    elif opm > 0: f1_score, f1_desc = 50, f"영업이익률 {opm:.1f}% (저마진 주의)"
    else: f1_score, f1_desc = 30, f"영업이익률 {opm:.1f}% (적자 지속)"

    debt = dart_data['debt_ratio']
    if debt <= 0: f2_score, f2_desc = 40, "재무 데이터 이상 (자본잠식 의심)"
    elif debt <= 100: f2_score, f2_desc = 95, f"부채비율 {debt:.1f}% (철벽 펀더멘탈)"
    elif debt <= 200: f2_score, f2_desc = 70, f"부채비율 {debt:.1f}% (시장 평균 수준)"
    else: f2_score, f2_desc = 30, f"부채비율 {debt:.1f}% (고위험/레버리지 과다)"

    roe = dart_data['roe']
    if roe >= 15: f8_score, f8_desc = 95, f"ROE {roe:.1f}% (경영진 자본배치 S급)"
    elif roe >= 8: f8_score, f8_desc = 75, f"ROE {roe:.1f}% (경영진 자본배치 B급)"
    elif roe > 0: f8_score, f8_desc = 50, f"ROE {roe:.1f}% (자본 비효율성 주의)"
    else: f8_score, f8_desc = 30, f"ROE {roe:.1f}% (경영/공시 리스크 경고)"
else:
    if now_per <= 0: f1_score, f1_desc = 30, "🚨 적자 기업 리스크 (진입 주의)"
    elif ind_per > 0 and now_per <= ind_per * 0.85: f1_score, f1_desc = 90, f"PER {now_per}배 (업종 {ind_per} 대비 저평가)"
    elif ind_per > 0 and now_per <= ind_per * 1.15: f1_score, f1_desc = 70, f"PER {now_per}배 (업종 수준)"
    else: f1_score, f1_desc = 40, f"PER {now_per}배 (고평가 리스크)"

    if now_pbr <= 0: f2_score, f2_desc = 30, "🚨 자본 잠식 리스크"
    elif now_pbr < 2.5: f2_score, f2_desc = 90, f"PBR {now_pbr}배 (자산가치 안정권)"
    elif now_pbr < 5.0: f2_score, f2_desc = 70, f"PBR {now_pbr}배 (적정 수준)"
    else: f2_score, f2_desc = 40, f"PBR {now_pbr}배 (과열 상태)"
    f8_score, f8_desc = 50, "정성적 판단 (가중치↓)"

# ── F3·F4·F9: 차트 기반 ──
if not is_chart_available or pd.isna(ema50) or pd.isna(ema20):
    f3_score, f3_desc, f4_score, f4_desc, f9_score, f9_desc = 50, "이평선 유보", 50, "거래량 유보", 50, "지지선 유보"
else:
    rsi_display = f"{rsi_val:.1f}" if not pd.isna(rsi_val) else "N/A"
    f3_score = 95.0 if now_price > ema20 > ema50 else 35.0
    f3_desc = f"상승 정배열 안착 (RSI: {rsi_display})" if f3_score == 95.0 else f"역배열 또는 추세 이탈 (RSI: {rsi_display})"

    if not pd.isna(rsi_val):
        is_over_bb = (not pd.isna(bb_up_val)) and (now_price >= bb_up_val)
        if rsi_val >= 70 and is_over_bb:
            f3_score = max(10.0, min(100.0, f3_score) - 20.0)
            f3_desc += " ⚠️ 과열 (RSI 70+ & 볼린저밴드 상단 돌파)"
            rsi_overheat = True
        elif rsi_val >= 70: f3_desc += " (RSI 70 이상이나 BB 미돌파 — 추세 강세)"
        elif rsi_val <= 30:
            f3_score = min(100.0, f3_score + 10.0)
            f3_desc += " ✨ 과매도 (반등 기대)"
    f3_score = int(min(100.0, f3_score))

    if latest['Volume'] == 0:
        f4_score, f4_desc = 0, "🚨 거래정지 또는 비정상 호가 감지"
    else:
        ref_vol = prev['VMA20'] if (prev is not None and prev['VMA20'] > 0) else (vma20_val if vma20_val > 0 else 1.0)
        vol_ratio = latest['Volume'] / ref_vol
        is_bullish = latest['Close'] >= latest['Open']
        if vol_ratio >= 2.0:
            f4_score, f4_desc = (95, f"🔥 20일평균 {vol_ratio:.1f}배 돌파 양봉") if is_bullish else (25, f"🚨 20일평균 {vol_ratio:.1f}배 폭발 장대음봉")
        elif vol_ratio >= 1.0: f4_score, f4_desc = (75 if is_bullish else 65), f"20일평균 {vol_ratio:.1f}배 (평이한 매매)"
        else: f4_score, f4_desc = 40, f"20일평균 {vol_ratio:.1f}배 소외"

    if pd.isna(ema20) or ema20 <= 0 or pd.isna(ema20_prev): f9_score, f9_desc = 50, "EMA20 데이터 부족으로 지지선 유보"
    else:
        disparity = (now_price / ema20) * 100
        if disparity < 50 or disparity > 200: f9_score, f9_desc = 50, "⚠️ 가격 왜곡 감지 (분할/배당락 의심)"
        elif 98 <= disparity <= 102:
            if ema20 >= ema20_prev: f9_score, f9_desc = 95, f"🎯 핵심 지지선 안착 (추세 우상향, 이격도 {disparity:.1f}%)"
            else: f9_score, f9_desc = 60, f"⚠️ 지지선 부근이나 하락 추세 (이격도 {disparity:.1f}%)"
        elif disparity > 102: f9_score, f9_desc = int(max(30.0, 55.0 - (disparity - 102) * 1.5)), f"EMA20 상단 이탈 — 단기 과매수 (이격도 {disparity:.1f}%)"
        else: f9_score, f9_desc = int(max(30.0, 55.0 - (98 - disparity) * 1.5)), f"EMA20 하단 이탈 — 지지선 이탈 (이격도 {disparity:.1f}%)"

# ── F6: 수급 ──
if net_f > 0 and net_i > 0: f6_score, f6_desc = 95, f"🎯 쌍끌이 매수 (외인:{int(net_f):,}, 기관:{int(net_i):,})"
elif net_f > 0 or net_i > 0: f6_score, f6_desc = 75, f"메이저 단일 수급 ({'외국인' if net_f > 0 else '기관'} 매수)"
elif net_f < 0 and net_i < 0: f6_score, f6_desc = 35, f"🚨 쌍끌이 매도 리스크 (외인:{int(net_f):,}, 기관:{int(net_i):,})"
elif net_f < 0 or net_i < 0: f6_score, f6_desc = 45, f"메이저 단일 이탈 ({'외국인' if net_f < 0 else '기관'} 매도)"
else: f6_score, f6_desc = 50, "메이저 수급 없음 (관망/소외)"

# ─────────────────────────────────────────────
# 8. 정성적 필터 (수동 슬라이더)
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 💡 정성적 필터 수동 체크")
f5_score = st.slider("L: 주도주 매력도 판단 (0=최악 / 100=최고)", 0, 100, 50, step=5)
f7_score = st.slider("M: 시장 위험도 판단 (0=최악 / 100=최고)", 0, 100, 50, step=5)
if not dart_data and not is_real_etf:
    f8_score = st.slider("Quant: 경영진/공시 리스크 (0=최악 / 100=최고)", 0, 100, 50, step=5)

# ─────────────────────────────────────────────
# 9. 총점 계산
# ─────────────────────────────────────────────
if is_real_etf: total_score = int((f3_score*1.5 + f4_score*1.5 + f5_score*0.5 + f6_score*1.5 + f7_score*0.5 + f8_score*0.5 + f9_score*1.0) / 7.0)
else: total_score = int((f1_score*1.0 + f2_score*1.0 + f3_score*1.5 + f4_score*1.5 + f5_score*0.5 + f6_score*1.5 + f7_score*0.5 + f8_score*0.5 + f9_score*1.0) / 9.0)
total_score = min(100, max(0, total_score))

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

        if vol_zero: sig_color, sig_text, sig_desc = "#E74C3C", "🔴 RED / 진입 불가", "거래정지 또는 비정상 호가입니다."
        elif total_score >= 80 and not rsi_overheat: sig_color, sig_text, sig_desc = "#2ECC71", "🟢 GREEN / 진입 적합", "가중치 필터 통과. 타점 진입을 고려하세요."
        elif total_score >= 80 and rsi_overheat: sig_color, sig_text, sig_desc = "#F1C40F", "🟡 YELLOW / 눌림 대기", "완벽하나 단기 과열(BB 상단)입니다. 눌림을 기다리세요."
        elif total_score >= 60: sig_color, sig_text, sig_desc = "#F1C40F", "🟡 YELLOW / 관망 유지", "에너지가 부족합니다. 수급/돌파를 확인하세요."
        else: sig_color, sig_text, sig_desc = "#E74C3C", "🔴 RED / 진입 부적합", "필터 미달. 매수 버튼에서 손을 떼십시오."

        st.markdown(f"<h1 style='color:{main_color};text-align:center;font-size:60px;margin-bottom:0;'>{total_score} <span style='font-size:24px;'>점</span></h1>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align:center;padding:10px;margin-bottom:15px;background-color:{sig_color}15;border-radius:8px;border:1.5px solid {sig_color};'><h4 style='color:{sig_color};margin:0;font-weight:bold;'>{sig_text}</h4><span style='font-size:13px;color:gray;'>{sig_desc}</span></div>", unsafe_allow_html=True)
        st.markdown(f"**확정 기준일 ({latest_date}):** {int(now_price):,}원")
        st.caption(f"PER: {now_per}배 | PBR: {now_pbr}배")
        st.markdown("---")
        st.markdown("### **🎯 매매 전략 단가**")
        st.success(f"대기 매수선: {int(buy_target):,}원")
        st.error(f"철벽 손절선: {int(stop_loss):,}원" + atr_desc_text)
        st.info(f"목표 익절선: {int(profit_target):,}원" + atr_desc_text)

with right_col:
    if is_chart_available and plot_df is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['Close'], name='종가 추이', line=dict(color='black', width=2)))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['EMA20'], name='EMA20', line=dict(color='blue', dash='dot')))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['EMA50'], name='EMA50', line=dict(color='orange')))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['BB_up'], name='BB상단(과열선)', line=dict(color='rgba(220,50,50,0.45)', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['BB_low'], name='BB하단(지지선)', line=dict(color='rgba(50,150,50,0.45)', width=1, dash='dot')))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)
    else: st.warning("⚠️ 현재 한국거래소(FDR) 서버 점검으로 차트 출력을 생략하고 비상 정량 점수만 표출합니다.")
    st.markdown("---")
    
    all_filters = [
        {"title": "C: 가치/성장성 (영업이익률)" if dart_data else "C: 가치/성장성 (PER)", "score": f1_score, "desc": f1_desc},
        {"title": "A: 자본/수익성 (부채비율)" if dart_data else "A: 자본/수익성 (PBR)", "score": f2_score, "desc": f2_desc},
        {"title": "N: 신고가/추세 (EMA) ★", "score": f3_score, "desc": f3_desc},
        {"title": "S: 거래량 돌파 (VMA20) ★", "score": f4_score, "desc": f4_desc},
        {"title": "L: 주도주 매력도 (업황)", "score": f5_score, "desc": "정성적 판단 (가중치↓)"},
        {"title": "I: 메이저 수급 (외인/기관) ★", "score": f6_score, "desc": f6_desc},
        {"title": "M: 시장 방향성 (지수)", "score": f7_score, "desc": "정성적 판단 (가중치↓)"},
        {"title": "Quant: 펀더멘탈 팩트 (ROE)" if dart_data else "Quant: 경영/공시 리스크", "score": f8_score, "desc": f8_desc if dart_data else "정성적 판단 (가중치↓)"},
        {"title": "Quant: 차트 지지선 확인", "score": f9_score, "desc": f9_desc if is_chart_available else "서버점검"},
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
                        st.markdown(f"<h3 style='color:{color};margin:0;'>{int(item['score'])} 점</h3>", unsafe_allow_html=True)
                        st.caption(item['desc'])
