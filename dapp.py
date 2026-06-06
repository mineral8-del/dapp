import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
import streamlit.components.v1 as components

# -----------------------------------------------------------------------------
# [설정] 한국투자증권 API KEY (.env 파일 연동)
# -----------------------------------------------------------------------------
load_dotenv() 

APP_KEY = os.environ.get("APP_KEY") or os.environ.get("KIS_APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET") or os.environ.get("KIS_APP_SECRET")

if not APP_KEY or not APP_SECRET:
    st.error("⚠️ 서버의 '.env' 파일에 앱키(APP_KEY) 또는 시크릿키(APP_SECRET)가 설정되지 않았습니다.")
    st.stop()

URL_BASE = "https://openapi.koreainvestment.com:9443" 

# 📱 [쇼츠용 세로 뷰] 레이아웃 설정
st.set_page_config(layout="wide", page_title="🔴 하이모바일 쇼츠 LIVE", initial_sidebar_state="collapsed")

# 🎨 CSS 생략 (기존과 완벽히 동일)
st.markdown("""
<style>
    html, body, [class*="css"] { margin: 0 !important; padding: 0 !important; }
    .stApp { background-color: #0b1120; }
    .block-container { 
        padding-top: 0rem !important; 
        padding-bottom: 80px !important; 
        padding-left: 0.3rem !important; 
        padding-right: 0.3rem !important; 
        max-width: 100% !important; 
    }
    header[data-testid="stHeader"], #MainMenu, footer, div[data-testid="stToolbar"] { display: none !important; }
    @keyframes blink { 0% { opacity: 1; text-shadow: 0 0 12px red; } 50% { opacity: 0.3; } 100% { opacity: 1; text-shadow: 0 0 12px red; } }
    .live-dot { color: #ef4444; animation: blink 1.5s infinite; font-size: 1.4rem; vertical-align: middle; }
    .main-title { color: #facc15; font-size: 2.7rem; font-weight: 900; text-align: center; margin-top: 6px; margin-bottom: 5px; letter-spacing: -1.5px; text-shadow: 3px 3px 6px rgba(0,0,0,0.6); }
    .time-container { text-align: center; margin-bottom: 11px; }
    #clockDisplay { background-color: #1e293b; color: #ffffff; font-size: 1.75rem; font-weight: 900; padding: 7px 22px; border-radius: 12px; border: 2px solid #334155; display: inline-block; letter-spacing: 2px; box-shadow: inset 0 0 12px rgba(0,0,0,0.8); }
    .progress-container { width: 100%; background-color: #1e293b; border-radius: 6px; height: 9px; margin-bottom: 11px; overflow: hidden; }
    #scanProgressBar { height: 100%; background: linear-gradient(90deg, #3b82f6, #facc15, #ef4444); width: 0%; transition: width 0.1s linear; }
    .stock-card { background-color: #151e2d; border-radius: 12px; padding: 20px 10px; margin-bottom: 11px; display: flex; align-items: center; border: 1px solid #334155; box-shadow: 0 4px 6px rgba(0,0,0,0.5); }
    .rank-circle { background: linear-gradient(135deg, #ef4444, #991b1b); color: white; width: 52px; height: 52px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.9rem; font-weight: 900; margin-right: 12px; flex-shrink: 0; border: 2px solid #fca5a5; }
    .name-col { width: 44%; display: flex; flex-direction: column; justify-content: center; text-align: left; }
    .stock-name { color: #ffffff; font-size: 2.1rem; font-weight: 900; letter-spacing: -1.5px; margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .status-text { font-size: 1.25rem; font-weight: 800; color: #fbbf24; margin: 0; }
    .center-col { width: 34%; display: flex; flex-direction: column; justify-content: center; text-align: right; padding-right: 10px; }
    .current-price { font-size: 1.7rem; font-weight: 900; color: #e2e8f0; letter-spacing: -0.5px; }
    .center-return { font-size: 2.0rem; font-weight: 900; letter-spacing: -1px; margin-top: 2px; }
    .right-col { width: 22%; text-align: center; background-color: #0f172a; border-radius: 8px; padding: 11px 0; border: 1px solid #334155; }
    .expected-label { color: #94a3b8; font-size: 1.05rem; font-weight: 800; margin-bottom: 3px; }
    .expected-value { color: #22c55e; font-size: 2.0rem; font-weight: 900; letter-spacing: -1px; }
    .marquee-container { position: fixed; bottom: 0; left: 0; width: 100%; overflow: hidden; background-color: #7f1d1d; color: white; padding: 13px 0; border-top: 3px solid #dc2626; white-space: nowrap; box-shadow: 0 -4px 8px rgba(0,0,0,0.6); z-index: 9999; }
    .marquee-content { display: inline-block; animation: scroll-left 18s linear infinite; font-size: 1.45rem; font-weight: 900; }
    @keyframes scroll-left { 0% { transform: translateX(100vw); } 100% { transform: translateX(-100%); } }
    .holiday-panel { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 80vh; background-color: #0b1120; text-align: center; }
</style>
""", unsafe_allow_html=True)

KST = timezone(timedelta(hours=9))

# -----------------------------------------------------------------------------
# 🛑 휴장일(주말 및 공휴일) 판별 로직
# -----------------------------------------------------------------------------
def is_market_open(date_kst):
    if date_kst.weekday() in [5, 6]: return False
    holidays = {
        "2024-01-01", "2024-02-09", "2024-02-12", "2024-03-01", "2024-04-10", "2024-05-01", "2024-05-06", "2024-05-15", 
        "2024-06-06", "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18", "2024-10-03", "2024-10-09", "2024-12-25", "2024-12-31",
        "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-03-03", "2025-05-01", "2025-05-05", "2025-05-06", 
        "2025-06-06", "2025-08-15", "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09", "2025-12-25", "2025-12-31",
        "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-01", "2026-05-05", "2026-05-25", 
        "2026-06-06", "2026-08-14", "2026-09-24", "2026-09-25", "2026-09-28", "2026-10-05", "2026-10-09", "2026-12-25", "2026-12-31"
    }
    if date_kst.strftime('%Y-%m-%d') in holidays: return False
    return True

now_kst = datetime.now(KST)

# -----------------------------------------------------------------------------
# 🛠️ [테스트 모드] 메인 화면에 숨겨진 관리자 도구 배치
# -----------------------------------------------------------------------------
with st.expander("🛠️ 시스템 테스트 도구 (클릭하여 열기)"):
    force_open = st.checkbox("🚀 강제 영업일 모드 켜기 (휴장일 무시)", value=False)
    st.info("이 버튼을 켜면 휴장일 로직을 무시하고 정규장처럼 강제로 데이터를 수집합니다.")

if not is_market_open(now_kst) and not force_open:
    st.markdown("""
        <div class="holiday-panel">
            <div style="font-size: 6rem; margin-bottom: 20px;">☕</div>
            <div style="color: #facc15; font-size: 2.8rem; font-weight: 900; letter-spacing: -1px; margin-bottom: 15px;">증권시장 휴장 안내</div>
            <div style="color: #94a3b8; font-size: 1.5rem; font-weight: 700; line-height: 1.6;">
                오늘은 주말 또는 공휴일로 인해<br>주식 시장이 열리지 않습니다.<br><br>다음 거래일에 다시 뵙겠습니다.
            </div>
        </div>
    """, unsafe_allow_html=True)
    st.stop()

# -----------------------------------------------------------------------------
# 영업일 API 통신
# -----------------------------------------------------------------------------
@st.cache_resource(ttl=3600*20)
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    try:
        res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
        return res.json()["access_token"]
    except: return None

def get_common_headers(tr_id):
    token = get_access_token()
    if not token: token = get_access_token()
    return {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": tr_id}

@st.cache_data(ttl=15)
def get_kis_top_trading_value_stocks():
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = get_common_headers("FHPST01710000")
    df_list = []
    for params in [{"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "111111", "FID_INPUT_PRICE_1": "10000", "FID_INPUT_PRICE_2": "80000", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""},
                   {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "111111", "FID_INPUT_PRICE_1": "80000", "FID_INPUT_PRICE_2": "2000000", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""}]:
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.json().get('rt_cd') == '0': df_list.append(pd.DataFrame(res.json()['output'])[['hts_kor_isnm', 'mksc_shrn_iscd', 'stck_prpr', 'prdy_ctrt', 'acml_tr_pbmn']])
        except: continue
    if not df_list: return pd.DataFrame()
    df = pd.concat(df_list, ignore_index=True)
    df.columns = ['종목명', '종목코드', '현재가', '등락률', '거래대금']
    df = df[~df['종목명'].str.contains('|'.join(['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'ARIRANG', 'HANARO', 'KOSEF', 'SOL', 'TIMEFOLIO', 'WOORI', '히어로즈', '마이티', '스팩', 'ETN']), case=False, regex=True)]
    df['현재가'], df['등락률'], df['거래대금'] = pd.to_numeric(df['현재가'], errors='coerce'), pd.to_numeric(df['등락률'], errors='coerce'), pd.to_numeric(df['거래대금'], errors='coerce') / 1000000 
    return df.sort_values(by='거래대금', ascending=False).drop_duplicates(subset=['종목코드']).dropna()

# -----------------------------------------------------------------------------
# 💾 [핵심 추가] 데이터 로깅 함수 (CSV 자동 저장)
# -----------------------------------------------------------------------------
def save_log_to_csv(top_10_df):
    """현재 화면에 뜬 10개 종목을 CSV 파일로 매일 누적 저장합니다."""
    today_str = datetime.now(KST).strftime('%Y%m%d')
    file_name = f"ai_stock_log_{today_str}.csv"
    current_time_str = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')

    # 저장용 데이터프레임 가공
    save_df = top_10_df.copy()
    save_df.insert(0, '포착시간', current_time_str)
    save_df.insert(1, '순위', range(1, len(save_df) + 1))
    
    # 엑셀에서 보기 편하게 컬럼 순서 재배치
    cols = ['포착시간', '순위', '종목명', '종목코드', '현재가', '등락률', '거래대금', '10분_상승예측(%)', '매매상태']
    save_df = save_df[cols]

    # 파일이 존재하지 않으면 헤더(컬럼명)를 포함하여 생성, 존재하면 아래에 데이터만 추가(append)
    write_header = not os.path.exists(file_name)
    
    # utf-8-sig 인코딩을 사용해야 엑셀에서 한글이 깨지지 않습니다.
    save_df.to_csv(file_name, mode='a', index=False, encoding='utf-8-sig', header=write_header)

# -----------------------------------------------------------------------------
# 🚀 자동 새로고침 타이머 (30초)
# -----------------------------------------------------------------------------
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30000, limit=10000, key="auto_refresh")
except ImportError: pass

# -----------------------------------------------------------------------------
# 📊 데이터 세팅 및 필터링
# -----------------------------------------------------------------------------
df_universe = get_kis_top_trading_value_stocks()
top_10 = pd.DataFrame()

if not df_universe.empty:
    df_universe = df_universe[df_universe['등락률'] > -15.0].copy()
    
    # AI 스코어 계산
    df_universe['10분_상승예측(%)'] = ((df_universe['등락률'] * 0.5) + np.log1p(df_universe['거래대금'])).round(2)
    
    # 상태 텍스트
    df_universe['매매상태'] = df_universe.apply(
        lambda r: "🔥 급등 돌파" if r['등락률'] >= 5.0 
        else ("🎯 S급 눌림" if r['등락률'] < 0 and r['거래대금'] > 10000 
        else "🟡 지지선 근접"), axis=1
    )
    
    # 점수 높은 순으로 10개 추출
    top_10 = df_universe.sort_values(by='10분_상승예측(%)', ascending=False).head(10)

    # 💾 화면에 그리기 직전, 추출된 Top 10 데이터를 엑셀(CSV)로 은밀하게 저장합니다.
    try:
        save_log_to_csv(top_10)
    except Exception as e:
        pass # 파일 저장 실패 시 방송이 터지면 안 되므로 예외 처리

    # 기대수익 및 현재가 포맷 (UI 표시용)
    top_10['기대수익_str'] = top_10['10분_상승예측(%)'].apply(lambda x: f"+{max(0.1, x):.1f}%")
    top_10['현재가_str'] = top_10['현재가'].apply(lambda x: f"{int(x):,}원") 

# -----------------------------------------------------------------------------
# 🎯 화면 상단 (타이틀 & 동적 시계 & 30초 진행 바)
# -----------------------------------------------------------------------------
st.markdown("<div class='main-title'><span class='live-dot'>●</span> 실시간 AI 타점 스캐너</div>", unsafe_allow_html=True)

st.markdown("""
    <div class='time-container'>
        <div id="clockDisplay">00:00:00</div>
    </div>
    <div class="progress-container"><div id="scanProgressBar"></div></div>
""", unsafe_allow_html=True)

components.html("""
    <script>
        var startTime = Date.now();
        
        function updateDynamicElements() {
            var now = new Date();
            var hours = now.getHours().toString().padStart(2, '0');
            var minutes = now.getMinutes().toString().padStart(2, '0');
            var seconds = now.getSeconds().toString().padStart(2, '0');
            var timeString = hours + ':' + minutes + ':' + seconds + ' 기준';
            
            var clocks = window.parent.document.querySelectorAll('#clockDisplay');
            clocks.forEach(function(el) { el.innerText = timeString; });

            var elapsed = Date.now() - startTime;
            var percent = (elapsed % 30000) / 30000 * 100;
            
            var bars = window.parent.document.querySelectorAll('#scanProgressBar');
            bars.forEach(function(el) { el.style.width = percent + '%'; });
        }
        setInterval(updateDynamicElements, 100);
    </script>
""", height=0, width=0)

# -----------------------------------------------------------------------------
# 🃏 꽉 찬 카드 리스트 그리기
# -----------------------------------------------------------------------------
if not top_10.empty:
    cards_html = ""
    
    for i, (_, row) in enumerate(top_10.iterrows(), start=1):
        curr_ret = row['등락률']
        curr_ret_str = f"{curr_ret:+.2f}%"
        curr_ret_color = "#ef4444" if curr_ret > 0 else "#3b82f6" if curr_ret < 0 else "#9ca3af"
        
        cards_html += f"""<div class="stock-card">
<div class="rank-circle">{i}</div>
<div class="name-col">
<div class="stock-name">{row['종목명']}</div>
<div class="status-text">{row['매매상태']}</div>
</div>
<div class="center-col">
<div class="current-price">{row['현재가_str']}</div>
<div class="center-return" style="color: {curr_ret_color};">{curr_ret_str}</div>
</div>
<div class="right-col">
<div class="expected-label">AI 점수</div>
<div class="expected-value">{row['기대수익_str']}</div>
</div>
</div>"""
    
    cards_html += "<div style='height: 70px; width: 100%; opacity: 0;'></div>"
        
    st.markdown(cards_html, unsafe_allow_html=True)
else:
    st.error("데이터를 수집 중입니다. 장 시작 전이거나 네트워크 상태를 확인해주세요.")

# -----------------------------------------------------------------------------
# 🔥 화면 하단 '고정' 면책 조항 전광판
# -----------------------------------------------------------------------------
st.markdown("""
    <div class="marquee-container">
        <div class="marquee-content">
            ⚠️ <b>[투자 유의사항]</b> 본 방송은 AI 알고리즘에 의한 단순 데이터 제공용이며 <b>투자를 권유하지 않습니다.</b> 모든 투자의 최종 책임은 <b>투자자 본인</b>에게 있습니다. &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp;
            ⚠️ 화면은 <b>30초 간격</b>으로 자동 갱신됩니다. 
        </div>
    </div>
""", unsafe_allow_html=True)
