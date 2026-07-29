from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import pandas as pd
import FinanceDataReader as fdr
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import os
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 기존과 동일한 사이드바 색상/매핑 설정
subject_col_map = {"외국인": "Foreigner", "기관": "Institution", "개인": "Individual"}

# 상장 종목 리스트 불러오기
def load_stock_list():
    if os.path.exists("data/stock_list.csv"):
        return pd.read_csv("data/stock_list.csv")
    else:
        df = fdr.StockListing('KRX')
        df_filtered = df[df['Market'].isin(['KOSPI', 'KOSDAQ'])][['Code', 'Name', 'Market']]
        df_filtered.columns = ['티커', '종목명', '시장']
        if not os.path.exists("data"): os.makedirs("data")
        df_filtered.to_csv("data/stock_list.csv", index=False)
        return df_filtered

def get_all_investor_data(ticker, start, end):
    try:
        df = pd.read_csv("data/investor_data.csv", dtype={'Ticker': str})
        df['Date'] = pd.to_datetime(df['Date'])
        df['Ticker'] = df['Ticker'].astype(str).str.zfill(6)
        mask = (df['Ticker'] == str(ticker).zfill(6)) & (df['Date'] >= pd.to_datetime(start)) & (df['Date'] <= pd.to_datetime(end))
        return df.loc[mask].copy().sort_values('Date')
    except Exception:
        return pd.DataFrame()

def classify_stock_groups(subject_col="Foreigner"):
    if not os.path.exists("data/investor_data.csv"):
        return [], [], []
    df_all = pd.read_csv("data/investor_data.csv", dtype={'Ticker': str})
    df_all['Date'] = pd.to_datetime(df_all['Date'])
    df_all['Ticker'] = df_all['Ticker'].astype(str).str.zfill(6)
    
    stock_df = load_stock_list()
    stock_df['티커'] = stock_df['티커'].astype(str).str.zfill(6)
    
    sprout_list, hope_list, clean_list = [], [], []
    grouped = df_all.groupby('Ticker')
    
    for ticker, group in grouped:
        group = group.sort_values('Date')
        if len(group) < 15: continue
        sub_series = group[subject_col].fillna(0)
        recent_5 = sub_series.iloc[-5:].sum()
        prev_5 = sub_series.iloc[-10:-5].sum()
        prev_prev_5 = sub_series.iloc[-15:-10].sum()
        
        matched_row = stock_df[stock_df['티커'] == ticker]
        if matched_row.empty: continue
        stock_name = matched_row['종목명'].values[0]
        
        # 1. 새싹 로직
        history_before_recent = sub_series.iloc[:-5]
        recent_days = sub_series.iloc[-5:]
        is_sprout = (history_before_recent.max() == 0) and (recent_days > 0).any()
        if is_sprout:
            is_recent_5d = recent_days.iloc[-1] > 0 and (history_before_recent.max() == 0 and sub_series.iloc[-6] == 0 if len(sub_series) >= 6 else True)
            prefix = "🌱 " if is_recent_5d else ""
            sprout_list.append(f"{prefix}{stock_name} ({ticker})")
            
        # 2. 희망 로직
        if prev_5 > 0:
            growth_rate = (recent_5 - prev_5) / prev_5 * 100
            if growth_rate >= 40:
                prev_growth_rate = (prev_5 - prev_prev_5) / abs(prev_prev_5) * 100 if prev_prev_5 != 0 else 0
                is_recent_hot = (growth_rate >= 40 and prev_growth_rate < 40)
                prefix = "🔥 " if is_recent_hot else ""
                hope_list.append(f"{prefix}{stock_name} ({ticker})")

        # 3. 정리 로직
        if prev_5 > 0 and recent_5 < prev_5:
            drop_rate = (prev_5 - recent_5) / prev_5 * 100
            if 10 < drop_rate <= 30:
                prev_drop_rate = (prev_prev_5 - prev_5) / abs(prev_prev_5) * 100 if prev_prev_5 != 0 else 0
                is_recent_warning = (drop_rate > 10 and prev_drop_rate <= 10)
                prefix = "🚨 " if is_recent_warning else ""
                clean_list.append(f"{prefix}{stock_name} ({ticker})")
                
    return sprout_list, hope_list, clean_list

def draw_custom_multi_chart(df, label_name, configs):
    df = df.sort_values(by='Date').reset_index(drop=True)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    for sub, conf in configs.items():
        if not conf.get("active", False): continue
        col_name = subject_col_map[sub]
        if col_name not in df.columns: continue
            
        series = df[col_name].fillna(0)
        base_color = conf["color"]
        
        if conf.get("bar", False):
            bar_colors = [conf["pos_bar"] if val >= 0 else conf["neg_bar"] for val in series]
            fig.add_trace(go.Bar(x=df['Date'], y=series, marker_color=bar_colors, name=f"{sub} 당일 순매수", opacity=0.5), secondary_y=False)
            
        cum_series = series.cumsum()
        aligned_cum = cum_series - (cum_series.iloc[0] if not cum_series.empty else 0)
        
        if conf.get("cum", False):
            fig.add_trace(go.Scatter(x=df['Date'], y=aligned_cum, mode='lines', name=f"{sub} 누적 수급선", line=dict(color=base_color, width=2.5)), secondary_y=True)
        if conf.get("ma5", False):
            fig.add_trace(go.Scatter(x=df['Date'], y=aligned_cum.rolling(window=5).mean(), mode='lines', name=f"{sub} 5일 이평선", line=dict(color=base_color, width=1.5)), secondary_y=True)
        if conf.get("ma10", False):
            fig.add_trace(go.Scatter(x=df['Date'], y=aligned_cum.rolling(window=10).mean(), mode='lines', name=f"{sub} 10일 이평선", line=dict(color=base_color, width=1.5, dash='dash')), secondary_y=True)
        if conf.get("ma20", False):
            fig.add_trace(go.Scatter(x=df['Date'], y=aligned_cum.rolling(window=20).mean(), mode='lines', name=f"{sub} 20일 이평선", line=dict(color=base_color, width=1.5, dash='dot')), secondary_y=True)

    fig.update_layout(template="plotly_white", height=500, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), title=f"📈 {label_name}", dragmode="pan")
    return fig

# --- API 엔드포인트 ---
class ChartRequest(BaseModel):
    ticker: str
    name: str
    start: str
    end: str
    configs: dict

@app.get("/api/init_data")
async def init_data():
    stock_df = load_stock_list()
    stock_df['티커'] = stock_df['티커'].astype(str).str.zfill(6)
    stock_list = (stock_df['종목명'] + " (" + stock_df['티커'] + ")").tolist()
    sprouts, hopes, cleans = classify_stock_groups()
    return JSONResponse({"stocks": stock_list, "sprouts": sprouts, "hopes": hopes, "cleans": cleans})

@app.post("/api/get_chart")
async def get_chart(req: ChartRequest):
    df = get_all_investor_data(req.ticker, req.start, req.end)
    if df.empty: return JSONResponse({"empty": True})
    fig = draw_custom_multi_chart(df, req.name, req.configs)
    return JSONResponse({"empty": False, "chart": json.loads(fig.to_json())})

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request, "index.html")
