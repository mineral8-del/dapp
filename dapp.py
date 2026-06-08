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

# 💡 인공지능 예측을 위한 라이브러리
import joblib
import ta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 📱 1. 레이아웃 설정
st.set_page_config(layout="wide", page_title="🔴 하이모바일 쇼츠 LIVE", initial_sidebar_state="collapsed")

# -----------------------------------------------------------------------------
# [설정] 한국투자증권 API KEY
# -----------------------------------------------------------------------------
load_dotenv()
APP_KEY = os.environ.get("APP_KEY") or os.environ.get("KIS_APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET") or os.environ.get("KIS_APP_SECRET")

if not APP_KEY or not APP_SECRET:
    st.error("⚠️ 서버의 '.env' 파일에 앱키(APP_KEY) 또는 시크릿키(APP_SECRET)가 설정되지 않았습니다.")
    st.stop()

URL_BASE = "https://openapi.koreainvestment.com:9443"
KST = timezone(timedelta(hours=9))
now_kst = datetime.now(KST)

# -----------------------------------------------------------------------------
# 🌐 [개선됨] 안정적인 API 통신을 위한 Session & Retry 세팅
# -----------------------------------------------------------------------------
@st.cache_resource
def get_requests_session():
    session = requests.Session()
    # 429(Too Many Requests), 500, 502 등 서버 에러 시 최대 3번 재시도
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

req_session = get_requests_session()

# -----------------------------------------------------------------------------
# 🤖 [개선됨] AI 모델 및 스케일러 동시 로드
# -----------------------------------------------------------------------------
@st.cache_resource
def load_ai_assets():
    model_path = "ai_stock_model.pkl"
    scaler_path = "ai_stock_scaler.pkl" # 스케일러 파일이 있다면 로드
    
    if not os.path.exists(model_path):
        st.error("⚠️ 'ai_stock_model.pkl' 파일이 없습니다. 먼저 모델을 학습시켜주세요!")
        st.stop()
    
    model = joblib.load(model_path)
    scaler = None
    if os.path.exists(scaler_path):
        scaler = joblib.load(scaler_path)
    else:
        st.warning("⚠️ 'ai_stock_scaler.pkl' 파일이 없습니다. 정규화 없이 원본 데이터로 추론합니다.")
        
    return model, scaler

ai_model, ai_scaler = load_ai_assets()

# -----------------------------------------------------------------------------
# 🎨 CSS 서식
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    html, body, [class*="css"] { margin: 0 !important; padding: 0 !important; }
    .stApp { background-color: #0b1120; }
    .block-container { padding-top: 0rem !important; padding-bottom: 80px !important; padding-left: 0.3rem !important; padding-right: 0.3rem !important; max-width: 100% !important; }
    header[data-testid="stHeader"], #MainMenu, footer, div[data-testid="stToolbar"] { display: none !important; }
    @keyframes blink { 0% { opacity: 1; text-shadow: 0 0 12px red; } 50% { opacity: 0.3; } 100% { opacity: 1; text-shadow: 0 0 12px red; } }
    .live-dot { color: #ef4444; animation: blink 1.5s infinite; font-size: 1.4rem; vertical-align: middle; }
    .main-title { font-size: 2.7rem; font-weight: 900; text-align: center; margin-top: 6px; margin-bottom: 5px; letter-spacing: -1.5px; text-shadow: 3px 3px 6px rgba(0,0,0,0.6); }
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

# -----------------------------------------------------------------------------
# 🛑 휴장일 판별 로직
# -----------------------------------------------------------------------------
def is_market_open(date_kst):
    if date_kst.weekday() in [5, 6]: return False
    holidays = {"2024-06-06", "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18", "2024-10-03", "2024-10-09", "2024-12-25", "2024-12-31"}
    if date_kst.strftime('%Y-%m-%d') in holidays: return False
    return True

with st.expander("🛠️ 시스템 테스트 도구"):
    force_open = st.checkbox("🚀 강제 영업일 모드 켜기", value=False, key="force_test")

# -----------------------------------------------------------------------------
# API 통신 함수 (에러 디버깅 강화)
# -----------------------------------------------------------------------------
@st.cache_resource(ttl=3600 * 20)
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    try:
        res = req_session.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body), timeout=5)
        return res.json()["access_token"]
    except Exception as e:
        st.error(f"🛑 토큰 발급 에러: {e}")
        return None

def get_common_headers(tr_id):
    token = get_access_token()
    if not token: token = get_access_token()
    return {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": tr_id}

@st.cache_data(ttl=15)
def get_kis_top_trading_value_stocks():
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = get_common_headers("FHPST01710000")
    df_list = []
    
    params_list = [
        {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "111111", "FID_INPUT_PRICE_1": "10000", "FID_INPUT_PRICE_2": "80000", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""},
        {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "111111", "FID_INPUT_PRICE_1": "80000", "FID_INPUT_PRICE_2": "2000000", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""}
    ]
    
    for params in params_list:
        try:
            res = req_session.get(url, headers=headers, params=params, timeout=5)
            if res.json().get('rt_cd') == '0':
                output = res.json().get('output', [])
                if output:
                    df_list.append(pd.DataFrame(output)[['hts_kor_isnm', 'mksc_shrn_iscd', 'stck_prpr', 'prdy_ctrt', 'acml_tr_pbmn']])
            else:
                # 💡 [개선] 실패 시 명확한 메시지 출력
                st.error(f"🛑 거래대금 랭킹 조회 실패: {res.json().get('msg1')}")
        except Exception as e:
            st.error(f"🛑 거래대금 랭킹 API 통신 에러: {e}")
            continue
            
    if not df_list: return pd.DataFrame()
    
    df = pd.concat(df_list, ignore_index=True)
    df.columns = ['종목명', '종목코드', '현재가', '등락률', '거래대금']
    df = df[~df['종목명'].str.contains('|'.join(['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'ARIRANG', 'HANARO', 'KOSEF', 'SOL', 'TIMEFOLIO', 'WOORI', '히어로즈', '스팩', 'ETN']), case=False, regex=True)]
    df['현재가'] = pd.to_numeric(df['현재가'], errors='coerce')
    df['등락률'] = pd.to_numeric(df['등락률'], errors='coerce')
    df['거래대금'] = pd.to_numeric(df['거래대금'], errors='coerce') / 1000000
    return df.sort_values(by='거래대금', ascending=False).drop_duplicates(subset=['종목코드']).dropna()

# -----------------------------------------------------------------------------
# 🧠 [핵심] 실시간 1분봉 데이터 수집 및 보조지표 계산 함수
# -----------------------------------------------------------------------------
def get_live_ai_features(stock_code):
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    headers = get_common_headers("FHKST03010200")
    current_time = datetime.now(KST).strftime("%H%M%S")
    
    params = {
        "FID_ETC_CLS_CODE": "",           # 💡 [추가] 필수 누락 파라미터
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_HOUR_1": current_time, 
        "FID_PW_DATA_INCU_YN": "Y"
    }
    try:
        res = req_session.get(url, headers=headers, params=params, timeout=5)
        
        # 💡 [개선] 실패 시 명확한 에러 메시지 출력
        if res.json().get('rt_cd') == '0':
            data = res.json().get('output2', [])
            if not data:
                return None
                
            df = pd.DataFrame(data)[['stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_prpr', 'cntg_vol']]
            df.columns = ['시가', '고가', '저가', '종가', '거래량']
            
            for col in df.columns: df[col] = pd.to_numeric(df[col])
            df = df.iloc[::-1].reset_index(drop=True)
            
            df['MA_5'] = df['종가'].rolling(window=5).mean()
            df['MA_20'] = df['종가'].rolling(window=20).mean()
            df['이격도_20'] = df['종가'] / (df['MA_20'] + 1)
            df['RSI_14'] = ta.momentum.RSIIndicator(close=df['종가'], window=14).rsi()
            df['Vol_MA_5'] = df['거래량'].rolling(window=5).mean()
            df['거래량_비율'] = df['거래량'] / (df['Vol_MA_5'] + 1)
            df['몸통_크기'] = abs(df['종가'] - df['시가']) / (df['시가'] + 1)
            df['고가_저가_폭'] = (df['고가'] - df['저가']) / (df['저가'] + 1)
            
            df = df.fillna(0)
            return df.iloc[-1].to_dict()
        else:
            st.error(f"🛑 분봉 조회 에러 ({stock_code}): {res.json().get('msg1')}")
            return None
            
    except Exception as e:
        st.error(f"🛑 네트워크 에러 ({stock_code}): {e}")
        return None

def save_latest_snapshot(top_10_df):
    top_10_df.to_csv("latest_snapshot.csv", mode='w', index=False, encoding='utf-8-sig')

# -----------------------------------------------------------------------------
# 🚀 자동 새로고침 타이머 (30초)
# -----------------------------------------------------------------------------
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30000, limit=10000, key="auto_refresh")
except ImportError: pass

# -----------------------------------------------------------------------------
# 📊 데이터 세팅 (AI 라이브 추론 적용)
# -----------------------------------------------------------------------------
is_replay_mode = False
top_10 = pd.DataFrame()

if not is_market_open(now_kst) and not force_open:
    is_replay_mode = True
    snapshot_file = "latest_snapshot.csv"
    if os.path.exists(snapshot_file):
        top_10 = pd.read_csv(snapshot_file)
    else:
        st.stop()
else:
    df_universe = get_kis_top_trading_value_stocks()
    
    if not df_universe.empty:
        df_universe = df_universe[df_universe['등락률'] > -15.0].copy()
        df_top15 = df_universe.head(15).copy()
        
        feature_list = []
        valid_indices = []
        
        for idx, row in df_top15.iterrows():
            code = row['종목코드']
            features = get_live_ai_features(code)
            
            if features is not None:
                feature_list.append(features)
                valid_indices.append(idx)
            
            time.sleep(0.06) 
            
        if feature_list:
            X_live = pd.DataFrame(feature_list)
            X_live = X_live[['시가', '고가', '저가', '종가', '거래량', 'MA_5', 'MA_20', '이격도_20', 'RSI_14', 'Vol_MA_5', '거래량_비율', '몸통_크기', '고가_저가_폭']]
            
            # 🤖 [개선] 모델 추론 전 스케일링 적용
            if ai_scaler is not None:
                try:
                    X_live_input = ai_scaler.transform(X_live)
                except Exception as e:
                    st.error(f"⚠️ 스케일링 오류 발생 (원본 데이터 사용): {e}")
                    X_live_input = X_live
            else:
                X_live_input = X_live
                
            # 예측 수행
            predictions = ai_model.predict(X_live_input)
            
            valid_df = df_top15.loc[valid_indices].copy()
            valid_df['AI_예측수익률'] = predictions
            
            max_pred = valid_df['AI_예측수익률'].max()
            if max_pred > 0:
                valid_df['AI_스코어'] = (valid_df['AI_예측수익률'] / max_pred * 10).clip(0.1, 10.0).round(1)
            else:
                valid_df['AI_스코어'] = 0.1
                
            valid_df['매매상태'] = valid_df.apply(
                lambda r: "🔥 급등 돌파" if r['등락률'] >= 5.0 
                else ("🎯 S급 눌림" if r['등락률'] < 0 
                else "🟡 AI 픽"), axis=1
            )
            
            top_10 = valid_df.sort_values(by='AI_스코어', ascending=False).head(10)
            top_10['기대수익_str'] = top_10['AI_스코어'].apply(lambda x: f"{x:.1f}점")
            top_10['현재가_str'] = top_10['현재가'].apply(lambda x: f"{int(x):,}원")
            
            try: save_latest_snapshot(top_10)
            except: pass

# -----------------------------------------------------------------------------
# 🎯 화면 렌더링
# -----------------------------------------------------------------------------
if is_replay_mode:
    st.markdown("<div class='main-title' style='color:#facc15;'><span style='color:#60a5fa;'>📺</span> [주말 복기] AI 스캐너 최종 결과</div>", unsafe_allow_html=True)
else:
    st.markdown("<div class='main-title' style='color:#facc15;'><span class='live-dot'>●</span> 실시간 AI 타점 스캐너</div>", unsafe_allow_html=True)

st.markdown("""
    <div class='time-container'><div id="clockDisplay">00:00:00</div></div>
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
    # 💡 [개선] 데이터가 없거나 에러 발생 시 명확한 안내
    st.error("⚠️ 데이터를 수집하지 못했습니다. 상단에 붉은색 에러 메시지가 있는지 확인해주세요.")

# -----------------------------------------------------------------------------
# 🔥 면책 조항 전광판
# -----------------------------------------------------------------------------
st.markdown("""
    <div class="marquee-container">
        <div class="marquee-content">
            ⚠️ <b>[투자 유의사항]</b> 본 방송은 딥러닝 AI 모델(LightGBM)에 의한 단순 데이터 제공용이며 <b>투자를 권유하지 않습니다.</b> 모든 투자의 책임은 <b>투자자 본인</b>에게 있습니다. &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp;
            ⚠️ 화면은 <b>30초 간격</b>으로 자동 갱신됩니다. 
        </div>
    </div>
""", unsafe_allow_html=True)
