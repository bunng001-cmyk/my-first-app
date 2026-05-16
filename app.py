import streamlit as st

st.title("드디어 성공했습니다! 🎉")
st.write("제 파이썬 스트림릿 첫 페이지입니다.")
import streamlit as st

# 1. 앱 제목 설정
st.title("줏대 있는 개미의 9가지 철벽 필터")
st.subheader("실시간 종목 점검 대시보드")

# 2. 사이드바 - 보유 종목 리스트 선택박스
st.sidebar.header("포트폴리오 관리")
selected_stock = st.sidebar.selectbox(
    "조회할 종목을 선택하세요",
    ["삼성전자우", "우리금융지주", "한전KPS", "세아베스틸지주", "새로운 종목 검색"]
)

# 3. 메인 화면 - 종목별 진단 결과
st.write(f"### 🔍 **{selected_stock}** 분석 결과")

# 임시 점수 데이터 (나중에 실시간 데이터와 연동할 예정입니다)
if selected_stock == "우리금융지주":
    score = 85
    status = "안전 (금리 상승 수혜 및 배당 매력)"
elif selected_stock == "한전KPS":
    score = 45
    status = "주의 (거래량 부족 및 이자 비용 부담)"
elif selected_stock == "삼성전자우":
    score = 75
    status = "보유 (바닥 다지기 확인 필요)"
else:
    score = 60
    status = "대기 (데이터 분석 준비 중)"

# 점수 시각화 수치로 보여주기
st.metric(label="필터 통과 점수", value=f"{score} / 100점", delta=status)

# 4. 9가지 철벽 필터 체크리스트 화면에 띄우기
st.write("---")
st.write("#### 🛡️ 9가지 철벽 필터 실시간 체크")

col1, col2 = st.columns(2)

with col1:
    st.checkbox("1. 돈의 흐름 (수급 유입 확인)", value=(score > 50))
    st.checkbox("2. 공급과 에너지 (거래량 상승)", value=(score > 60))
    st.checkbox("3. 기관/외국인 바스켓 매수", value=(score > 70))
    st.checkbox("4. 대주주 지분 및 경영진 리스크 없음", value=True)

with col2:
    st.checkbox("5. 유보율 500% 이상 (안전성)", value=True)
    st.checkbox("6. 부채비율 100% 이하", value=(score > 50))
    st.checkbox("7. 지지선 근처 진입 (뇌동매매 방지)", value=(score > 70))
    st.checkbox("8. 분할 익절 및 리스크 관리 계획", value=True)

st.info("💡 월요일 장중 실시간 수급 및 국채 금리 변동에 따라 점수가 연동됩니다.")