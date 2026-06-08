import os
import time
import json
import requests
import pandas as pd
import numpy as np
import joblib
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# 💡 인공지능 및 보조지표 라이브러리
import ta
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# -----------------------------------------------------------------------------
# 1. 환경 설정 및 API 키
# -----------------------------------------------------------------------------
load_dotenv()
APP_KEY = os.environ.get("APP_KEY") or os.environ.get("KIS_APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET") or os.environ.get("KIS_APP_SECRET")

if not APP_KEY or not APP_SECRET:
    print("⚠️ '.env' 파일에 API 키가 설정되지 않았습니다.")
    exit()

URL_BASE = "https://openapi.koreainvestment.com:9443"
KST = timezone(timedelta(hours=9))


def get_access_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body), timeout=5)
    return res.json()["access_token"]


TOKEN = get_access_token()


def get_common_headers(tr_id):
    return {
        "Content-Type": "application/json",
        "authorization": f"Bearer {TOKEN}",
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
        "tr_id": tr_id
    }


# -----------------------------------------------------------------------------
# 2. 당일 거래대금 상위 종목 추출 (훈련 대상 선정)
# -----------------------------------------------------------------------------
def get_target_stocks():
    print("🔍 오늘 시장을 주도한 거래대금 상위 종목을 탐색합니다...")
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = get_common_headers("FHPST01710000")

    # 상위 30개 정도만 타겟으로 삼습니다 (API 과부하 방지)
    params = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000",
        "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111",
        "FID_TRGT_EXLS_CLS_CODE": "111111", "FID_INPUT_PRICE_1": "10000", "FID_INPUT_PRICE_2": "2000000",
        "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.json().get('rt_cd') == '0':
            df = pd.DataFrame(res.json()['output'])
            # ETF, ETN, 스팩 등 제외
            df = df[~df['hts_kor_isnm'].str.contains('KODEX|TIGER|KBSTAR|ACE|스팩|ETN|ARIRANG', regex=True)]
            target_codes = df['mksc_shrn_iscd'].head(30).tolist()
            return target_codes
    except Exception as e:
        print(f"🛑 종목 추출 실패: {e}")
    return ['005930', '000660']  # 실패 시 삼성전자, 하이닉스 기본값


# -----------------------------------------------------------------------------
# 3. 분봉 수집 및 보조지표/정답지(Label) 생성
# -----------------------------------------------------------------------------
def get_minute_chart_with_features(stock_code):
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    headers = get_common_headers("FHKST03010200")

    params = {
        "FID_ETC_CLS_CODE": "",  # 💡 해결된 파라미터 누락 문제
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_HOUR_1": "153000",  # 오후 3시 30분 기준 역순
        "FID_PW_DATA_INCU_YN": "Y"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        if res.json().get('rt_cd') == '0':
            data = res.json().get('output2', [])
            if not data: return pd.DataFrame()

            df = pd.DataFrame(data)[
                ['stck_bsop_date', 'stck_cntg_hour', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'stck_prpr', 'cntg_vol']]
            df.columns = ['날짜', '시간', '시가', '고가', '저가', '종가', '거래량']

            for col in ['시가', '고가', '저가', '종가', '거래량']:
                df[col] = pd.to_numeric(df[col])

            df = df.iloc[::-1].reset_index(drop=True)

            # 💡 [핵심] 실시간 대시보드와 완벽히 동일한 보조지표 계산
            df['MA_5'] = df['종가'].rolling(window=5).mean()
            df['MA_20'] = df['종가'].rolling(window=20).mean()
            df['이격도_20'] = df['종가'] / (df['MA_20'] + 1)
            df['RSI_14'] = ta.momentum.RSIIndicator(close=df['종가'], window=14).rsi()
            df['Vol_MA_5'] = df['거래량'].rolling(window=5).mean()
            df['거래량_비율'] = df['거래량'] / (df['Vol_MA_5'] + 1)
            df['몸통_크기'] = abs(df['종가'] - df['시가']) / (df['시가'] + 1)
            df['고가_저가_폭'] = (df['고가'] - df['저가']) / (df['저가'] + 1)

            # 정답지(Target) 생성: 10분 뒤의 수익률
            df['10분뒤_종가'] = df['종가'].shift(-10)
            df['Target_10분수익률'] = ((df['10분뒤_종가'] - df['종가']) / df['종가']) * 100

            # 결측치(NaN)가 있는 행(초반 보조지표 계산 구간, 막판 10분 구간) 제거
            df = df.dropna()
            df.insert(0, '종목코드', stock_code)

            return df
    except Exception as e:
        pass
    return pd.DataFrame()


# -----------------------------------------------------------------------------
# 4. 메인 파이프라인 (데이터 수집 -> 누적 -> AI 학습)
# -----------------------------------------------------------------------------
def run_daily_pipeline():
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] 🚀 일일 AI 데이터 수집 및 훈련 파이프라인 시작")

    # --- 1단계: 오늘의 데이터 수집 ---
    target_stocks = get_target_stocks()
    daily_data = []

    for i, code in enumerate(target_stocks):
        print(f"[{i + 1}/{len(target_stocks)}] {code} 데이터 수집 중...")
        df = get_minute_chart_with_features(code)
        if not df.empty:
            daily_data.append(df)
        time.sleep(0.1)  # KIS API 속도 제한 방어

    if not daily_data:
        print("⚠️ 수집된 데이터가 없습니다. 파이프라인을 종료합니다.")
        return

    today_df = pd.concat(daily_data, ignore_index=True)
    print(f"✅ 오늘 치 분봉 데이터 {len(today_df)}행 수집 완료!")

    # --- 2단계: 마스터 데이터셋에 누적 (데이터베이스 역할) ---
    master_filename = "master_dataset.csv"
    if os.path.exists(master_filename):
        master_df = pd.read_csv(master_filename)
        # 중복 방지를 위해 오늘 날짜 데이터가 이미 있으면 제거하고 다시 합침
        today_str = today_df['날짜'].iloc[0] if not today_df.empty else ""
        master_df = master_df[master_df['날짜'] != today_str]
        final_df = pd.concat([master_df, today_df], ignore_index=True)
        print(f"✅ 기존 데이터와 병합 완료! (총 누적 데이터: {len(final_df)}행)")
    else:
        final_df = today_df
        print("✅ 새 마스터 데이터셋 생성 완료!")

    final_df.to_csv(master_filename, index=False, encoding='utf-8-sig')

    # --- 3단계: AI 모델 훈련 (LightGBM) ---
    print("🧠 AI 모델 학습을 시작합니다...")

    # 훈련에 사용할 특성(Feature) 컬럼 (대시보드와 동일한 순서)
    features = ['시가', '고가', '저가', '종가', '거래량', 'MA_5', 'MA_20', '이격도_20', 'RSI_14', 'Vol_MA_5', '거래량_비율', '몸통_크기',
                '고가_저가_폭']
    target = 'Target_10분수익률'

    X = final_df[features]
    y = final_df[target]

    # 데이터 스케일링(정규화)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 최신 데이터를 테스트용으로 분리 (시계열 데이터 특성 반영)
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.1, shuffle=False)

    # LightGBM 모델 정의 및 훈련
    model = lgb.LGBMRegressor(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=5,
        random_state=42
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)])

    # --- 4단계: 완성된 뇌(Model)와 안경(Scaler) 저장 ---
    joblib.dump(model, 'ai_stock_model.pkl')
    joblib.dump(scaler, 'ai_stock_scaler.pkl')

    print("🎉 파이프라인 완료! 새로운 'ai_stock_model.pkl'과 'ai_stock_scaler.pkl'이 저장되었습니다.")
    print("내일 장이 열리면 Streamlit 대시보드가 이 최신 모델을 이용해 더욱 똑똑해진 예측을 수행합니다!")


if __name__ == "__main__":
    run_daily_pipeline()