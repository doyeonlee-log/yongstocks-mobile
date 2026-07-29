from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import FinanceDataReader as fdr
import datetime
import os
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    stock_df = load_stock_list()
    stock_df['티커'] = stock_df['티커'].astype(str).str.zfill(6)
    stock_list = (stock_df['종목명'] + " (" + stock_df['티커'] + ")").tolist()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stock_list": stock_list
    })
