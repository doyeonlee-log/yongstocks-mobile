import os
import datetime
import pandas as pd
import FinanceDataReader as fdr
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc

# ==========================================
# 1. 초기 프레임워크 설정 및 모바일 메타 태그
# ==========================================
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes"}],
    suppress_callback_exceptions=True   # [수정] 동적 레이아웃(콜백 안에서 생성되는 컴포넌트) 대응
)
server = app.server
app.title = "새싹발굴하기 - Pro Dashboard"

# ==========================================
# 2. 데이터 엔진 및 설정 값 메타 데이터
# ==========================================
subjects_meta = {
    "외국인": {
        "color": "#FF0000", "pos_bar": "#FF0000", "neg_bar": "#FFA07A",
        "default_bar": True, "default_cum": True, "default_ma5": True, "default_ma10": False, "default_ma20": False
    },
    "기관": {
        "color": "#1F77B4", "pos_bar": "#1E90FF", "neg_bar": "#B0C4DE",
        "default_bar": False, "default_cum": True, "default_ma5": False, "default_ma10": False, "default_ma20": False
    },
    "개인": {
        "color": "#2CA02C", "pos_bar": "#32CD32", "neg_bar": "#8FBC8F",
        "default_bar": False, "default_cum": False, "default_ma5": False, "default_ma10": False, "default_ma20": False
    }
}

subject_col_map = {"외국인": "Foreigner", "기관": "Institution", "개인": "Individual"}

def load_stock_list():
    if os.path.exists("data/stock_list.csv"):
        try:
            return pd.read_csv("data/stock_list.csv", encoding='utf-8')
        except:
            return pd.read_csv("data/stock_list.csv", encoding='cp949')
    else:
        try:
            df = fdr.StockListing('KRX')
            df_filtered = df[df['Market'].isin(['KOSPI', 'KOSDAQ'])][['Code', 'Name', 'Market']]
            df_filtered.columns = ['티커', '종목명', '시장']
            if not os.path.exists("data"): os.makedirs("data")
            df_filtered.to_csv("data/stock_list.csv", index=False, encoding='utf-8')
            return df_filtered
        except:
            return pd.DataFrame({'티커': ['005930', '000660'], '종목명': ['삼성전자', 'SK하이닉스'], '시장': ['KOSPI', 'KOSPI']})

stock_df = load_stock_list()
stock_df['티커'] = stock_df['티커'].astype(str).str.zfill(6)
stock_df['선택용_이름'] = stock_df['종목명'].astype(str) + " (" + stock_df['티커'] + ")"

def get_all_investor_data(ticker, start, end):
    if not os.path.exists("data/investor_data.csv"):
        return pd.DataFrame()
    try:
        df = pd.read_csv("data/investor_data.csv", dtype={'Ticker': str})
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Ticker'] = df['Ticker'].astype(str).str.zfill(6)
        mask = (df['Ticker'] == ticker.zfill(6)) & (df['Date'] >= pd.to_datetime(start)) & (df['Date'] <= pd.to_datetime(end))
        return df.loc[mask].copy().sort_values('Date')
    except:
        return pd.DataFrame()

def classify_stock_groups(subject_col):
    if not os.path.exists("data/investor_data.csv"):
        return [], [], []
    try:
        df_all = pd.read_csv("data/investor_data.csv", dtype={'Ticker': str})
        df_all['Date'] = pd.to_datetime(df_all['Date'], errors='coerce')
        df_all['Ticker'] = df_all['Ticker'].astype(str).str.zfill(6)
    except:
        return [], [], []

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

        history_before_recent = sub_series.iloc[:-5]
        recent_days = sub_series.iloc[-5:]
        is_sprout = (history_before_recent.max() == 0) and (recent_days > 0).any()

        if is_sprout:
            is_recent_5d = recent_days.iloc[-1] > 0 and (history_before_recent.max() == 0 and sub_series.iloc[-6] == 0 if len(sub_series) >= 6 else True)
            prefix = "🌱 " if is_recent_5d else ""
            sprout_list.append(f"{prefix}{stock_name} ({ticker})")

        if prev_5 > 0:
            growth_rate = (recent_5 - prev_5) / prev_5 * 100
            if growth_rate >= 40:
                prev_growth_rate = (prev_5 - prev_prev_5) / abs(prev_prev_5) * 100 if prev_prev_5 != 0 else 0
                is_recent_hot = (growth_rate >= 40 and prev_growth_rate < 40)
                prefix = "🔥 " if is_recent_hot else ""
                hope_list.append(f"{prefix}{stock_name} ({ticker})")

        if prev_5 > 0 and recent_5 < prev_5:
            drop_rate = (prev_5 - recent_5) / prev_5 * 100
            if 10 < drop_rate <= 30:
                prev_drop_rate = (prev_prev_5 - prev_5) / abs(prev_prev_5) * 100 if prev_prev_5 != 0 else 0
                is_recent_warning = (drop_rate > 10 and prev_drop_rate <= 10)
                prefix = "🚨 " if is_recent_warning else ""
                clean_list.append(f"{prefix}{stock_name} ({ticker})")

    return sprout_list, hope_list, clean_list

def clean_sel_name(val):
    if not val: return ""
    return val.split("(")[-1].replace(")", "").replace("🌱 ", "").replace("🔥 ", "").replace("🚨 ", "").strip()

def clean_pure_name(val):
    if not val: return ""
    return val.split("(")[0].replace("🌱 ", "").replace("🔥 ", "").replace("🚨 ", "").strip()

def draw_custom_multi_chart(df, label_name, configs):
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="데이터가 선택되지 않았거나 없습니다.")
        return fig
    df = df.sort_values(by='Date').reset_index(drop=True)
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    for sub, conf in configs.items():
        if not conf["active"]: continue
        col_name = subject_col_map[sub]
        if col_name not in df.columns: continue

        series = df[col_name].fillna(0)
        base_color = conf["color"]

        if conf["bar"]:
            bar_colors = [conf["pos_bar"] if val >= 0 else conf["neg_bar"] for val in series]
            fig.add_trace(go.Bar(x=df['Date'], y=series, marker_color=bar_colors, name=f"{sub} 당일 순매수", opacity=0.5), secondary_y=False)

        cum_series = series.cumsum()
        first_val = cum_series.iloc[0] if not cum_series.empty else 0
        aligned_cum = cum_series - first_val

        if conf["cum"]:
            fig.add_trace(go.Scatter(x=df['Date'], y=aligned_cum, mode='lines', name=f"{sub} 누적 수급선", line=dict(color=base_color, width=2.5)), secondary_y=True)
        if conf["ma5"]:
            fig.add_trace(go.Scatter(x=df['Date'], y=aligned_cum.rolling(window=5).mean(), mode='lines', name=f"{sub} 5일 이평선", line=dict(color=base_color, width=1.5)), secondary_y=True)
        if conf["ma10"]:
            fig.add_trace(go.Scatter(x=df['Date'], y=aligned_cum.rolling(window=10).mean(), mode='lines', name=f"{sub} 10일 이평선", line=dict(color=base_color, width=1.5, dash='dash')), secondary_y=True)
        if conf["ma20"]:
            fig.add_trace(go.Scatter(x=df['Date'], y=aligned_cum.rolling(window=20).mean(), mode='lines', name=f"{sub} 20일 이평선", line=dict(color=base_color, width=1.5, dash='dot')), secondary_y=True)

    fig.update_layout(
        template="plotly_white", height=400, hovermode="x unified", margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
        title=dict(text=f"📈 {label_name}", font=dict(size=14)), dragmode="pan", uirevision="constant"
    )
    fig.update_xaxes(fixedrange=False)
    fig.update_yaxes(fixedrange=False)
    return fig

sidebar_layout = html.Div([
    html.H4("🛠️ 대시보드 제어판", className="text-dark font-weight-bold mb-3", style={"fontSize": "18px"}),
    html.Hr(),
    html.Div([
        dbc.Accordion([
            dbc.AccordionItem([
                dbc.Checkbox(id=f"chk_bar_{sub}", label="당일 순매수 바(Bar)", value=meta["default_bar"], className="mb-1 text-dark"),
                dbc.Checkbox(id=f"chk_cum_{sub}", label="누적 수급선", value=meta["default_cum"], className="mb-1 text-dark"),
                dbc.Checkbox(id=f"chk_ma5_{sub}", label="5일 이동평균선", value=meta["default_ma5"], className="mb-1 text-dark"),
                dbc.Checkbox(id=f"chk_ma10_{sub}", label="10일 이동평균선", value=meta["default_ma10"], className="mb-1 text-dark"),
                dbc.Checkbox(id=f"chk_ma20_{sub}", label="20일 이동평균선", value=meta["default_ma20"], className="mb-1 text-dark"),
            ], title=f"📌 [{sub}] 상세 수급 설정", item_id=f"acc_{sub}", style={"backgroundColor": "#fff"})
            for sub, meta in subjects_meta.items()
        ], active_item="acc_외국인", id="sidebar-accordion")
    ], style={"gap": "8px", "display": "flex", "flexDirection": "column"})
], style={"padding": "15px", "backgroundColor": "#ffffff", "borderRadius": "8px", "border": "1px solid #dee2e6", "marginBottom": "15px"})

tabs_layout = dbc.Tabs([
    dbc.Tab(label="🔎 개별 종목 분석", tab_id="tab-1", tab_style={"cursor": "pointer"}, label_style={"fontWeight": "600", "fontSize": "13px"}),
    dbc.Tab(label="🌱 새싹 발굴", tab_id="tab-2", tab_style={"cursor": "pointer"}, label_style={"fontWeight": "600", "fontSize": "13px"}),
    dbc.Tab(label="🚀 희망 종목", tab_id="tab-3", tab_style={"cursor": "pointer"}, label_style={"fontWeight": "600", "fontSize": "13px"}),
    dbc.Tab(label="🚨 정리 종목", tab_id="tab-4", tab_style={"cursor": "pointer"}, label_style={"fontWeight": "600", "fontSize": "13px"}),
    dbc.Tab(label="⭐ 나의 새싹 즐겨찾기", tab_id="tab-5", tab_style={"cursor": "pointer"}, label_style={"fontWeight": "600", "fontSize": "13px"}),
], id="tabs-control", active_tab="tab-1", className="mb-3 custom-tabs")

app.layout = dbc.Container([
    dcc.Store(id='local-fav-storage', storage_type='local'),
    dbc.Row([
        dbc.Col(sidebar_layout, xs=12, md=3),
        dbc.Col([tabs_layout, html.Div(id="tab-content-render")], xs=12, md=9)
    ], className="g-3")
], fluid=True, style={"backgroundColor": "#f8f9fa", "minHeight": "100vh", "padding": "10px"})

@app.callback(
    Output("tab-content-render", "children"),
    Output('local-fav-storage', 'data'),
    Input("tabs-control", "active_tab"),
    Input('local-fav-storage', 'data'),
    [Input(f"chk_bar_{s}", "value") for s in subjects_meta] +
    [Input(f"chk_cum_{s}", "value") for s in subjects_meta] +
    [Input(f"chk_ma5_{s}", "value") for s in subjects_meta] +
    [Input(f"chk_ma10_{s}", "value") for s in subjects_meta] +
    [Input(f"chk_ma20_{s}", "value") for s in subjects_meta],
    State("individual_select", "value"),
    State("date_input_tab1_start", "date"), State("date_input_tab1_end", "date"),
    State("sprout_sel", "value"),
    State("date_input_tab2_start", "date"), State("date_input_tab2_end", "date"),
    State("hope_sel", "value"),
    State("date_input_tab3_start", "date"), State("date_input_tab3_end", "date"),
    State("clean_sel", "value"),
    State("date_input_tab4_start", "date"), State("date_input_tab4_end", "date"),
    State("fav_box", "value"),
    State("date_input_tab5_start", "date"), State("date_input_tab5_end", "date")
)
def render_and_update_tabs(active_tab, local_storage_data, *args):
    checkbox_counts = len(subjects_meta) * 5
    cb_inputs = args[:checkbox_counts]
    states = args[checkbox_counts:]

    current_configs = {}
    idx = 0
    subs = list(subjects_meta.keys())
    for metric in ["bar", "cum", "ma5", "ma10", "ma20"]:
        for s in subs:
            if s not in current_configs:
                current_configs[s] = {"color": subjects_meta[s]["color"], "pos_bar": subjects_meta[s]["pos_bar"], "neg_bar": subjects_meta[s]["neg_bar"]}
            current_configs[s][metric] = cb_inputs[idx]
            idx += 1

    for s in subs:
        current_configs[s]["active"] = any(current_configs[s][m] for m in ["bar", "cum", "ma5", "ma10", "ma20"])

    active_subs = [s for s, c in current_configs.items() if c["active"]]
    primary_subject = active_subs[0] if active_subs else "외국인"   # [수정] [0] 추가 (리스트 → 문자열)
    primary_col = subject_col_map[primary_subject]

    sprouts, hopes, cleans = classify_stock_groups(primary_col)
    (ind_stock, t1_s, t1_e, spr_stock, t2_s, t2_e, hp_stock, t3_s, t3_e, cl_stock, t4_s, t4_e, fav_stocks, t5_s, t5_e) = states

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    jan_1_str = f"{datetime.date.today().year}-01-01"

    t1_s, t1_e = t1_s or jan_1_str, t1_e or today_str
    t2_s, t2_e = t2_s or jan_1_str, t2_e or today_str
    t3_s, t3_e = t3_s or jan_1_str, t3_e or today_str
    t4_s, t4_e = t4_s or jan_1_str, t4_e or today_str
    t5_s, t5_e = t5_s or jan_1_str, t5_e or today_str

    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ""   # [수정] [0] 인덱싱 + [0] 파싱

    out_storage = local_storage_data
    if triggered_id == "fav_box":
        out_storage = ",".join(fav_stocks) if fav_stocks else ""

    if out_storage:
        default_favs = [x.strip() for x in out_storage.split(",") if x.strip() in stock_df['선택용_이름'].values]
    else:
        default_favs = [stock_df['선택용_이름'].iloc[0], stock_df['선택용_이름'].iloc[1]] if len(stock_df) > 2 else []

    if active_tab == "tab-1":
        ind_stock = ind_stock or (stock_df['선택용_이름'].iloc[0] if not stock_df.empty else "")
        ticker = stock_df[stock_df['선택용_이름'] == ind_stock]['티커'].values[0] if ind_stock in stock_df['선택용_이름'].values else ""
        name = stock_df[stock_df['선택용_이름'] == ind_stock]['종목명'].values[0] if ind_stock in stock_df['선택용_이름'].values else ""

        df = get_all_investor_data(ticker, t1_s, t1_e) if ticker else pd.DataFrame()
        chart_node = dcc.Graph(figure=draw_custom_multi_chart(df, name, current_configs), config={"scrollZoom": True, "displayModeBar": False}) if not df.empty else dbc.Alert("데이터가 없습니다. 제어판 설정을 확인해 주세요.", color="warning", className="mt-2")

        return html.Div([
            dbc.Row([
                dbc.Col([
                    html.Label("📊 분석할 종목 선택:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    dcc.Dropdown(id="individual_select", options=[{"label": i, "value": i} for i in stock_df['선택용_이름']], value=ind_stock, clearable=False, style={"fontSize": "14px"})
                ], xs=12, md=6),
                dbc.Col([
                    html.Label("📅 분석 기간:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    html.Div([
                        dcc.DatePickerSingle(id="date_input_tab1_start", date=t1_s, display_format="YYYY-MM-DD", style={"width": "47%"}),
                        html.Span(" ~ ", style={"padding": "0 5px"}),
                        dcc.DatePickerSingle(id="date_input_tab1_end", date=t1_e, display_format="YYYY-MM-DD", style={"width": "47%"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], xs=12, md=6)
            ], className="g-2 mb-3"),
            chart_node
        ]), out_storage

    elif active_tab == "tab-2":
        dropdown_opts = sprouts if sprouts else ["종목 없음"]
        spr_stock = spr_stock if spr_stock in dropdown_opts else dropdown_opts[0]

        if sprouts and spr_stock != "종목 없음":
            s_ticker = clean_sel_name(spr_stock)
            s_name = clean_pure_name(spr_stock)
            df = get_all_investor_data(s_ticker, t2_s, t2_e)
            chart_node = dcc.Graph(figure=draw_custom_multi_chart(df, s_name, current_configs), config={"scrollZoom": True, "displayModeBar": False}) if not df.empty else dbc.Alert("해당 기간 내 데이터가 없습니다.", color="warning", className="mt-2")
        else:
            chart_node = dbc.Alert(f"현재 [{primary_subject}] 기준 조건에 부합하는 새싹 종목이 없습니다.", color="warning", className="mt-2")

        return html.Div([
            dbc.Row([
                dbc.Col([
                    html.Label("발굴된 새싹 종목 선택:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    dcc.Dropdown(id="sprout_sel", options=[{"label": i, "value": i} for i in dropdown_opts], value=spr_stock, clearable=False, style={"fontSize": "14px"})
                ], xs=12, md=6),
                dbc.Col([
                    html.Label("📅 분석 기간:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    html.Div([
                        dcc.DatePickerSingle(id="date_input_tab2_start", date=t2_s, display_format="YYYY-MM-DD", style={"width": "47%"}),
                        html.Span(" ~ ", style={"padding": "0 5px"}),
                        dcc.DatePickerSingle(id="date_input_tab2_end", date=t2_e, display_format="YYYY-MM-DD", style={"width": "47%"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], xs=12, md=6)
            ], className="g-2 mb-3"),
            chart_node
        ]), out_storage

    elif active_tab == "tab-3":
        dropdown_opts = hopes if hopes else ["종목 없음"]
        hp_stock = hp_stock if hp_stock in dropdown_opts else dropdown_opts[0]

        if hopes and hp_stock != "종목 없음":
            h_ticker = clean_sel_name(hp_stock)
            h_name = clean_pure_name(hp_stock)
            df = get_all_investor_data(h_ticker, t3_s, t3_e)
            chart_node = dcc.Graph(figure=draw_custom_multi_chart(df, h_name, current_configs), config={"scrollZoom": True, "displayModeBar": False}) if not df.empty else dbc.Alert("해당 기간 내 데이터가 없습니다.", color="warning", className="mt-2")
        else:
            chart_node = dbc.Alert(f"현재 [{primary_subject}] 기준 조건에 부합하는 희망 종목이 없습니다.", color="warning", className="mt-2")

        return html.Div([
            dbc.Row([
                dbc.Col([
                    html.Label("희망 종목 선택:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    dcc.Dropdown(id="hope_sel", options=[{"label": i, "value": i} for i in dropdown_opts], value=hp_stock, clearable=False, style={"fontSize": "14px"})
                ], xs=12, md=6),
                dbc.Col([
                    html.Label("📅 분석 기간:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    html.Div([
                        dcc.DatePickerSingle(id="date_input_tab3_start", date=t3_s, display_format="YYYY-MM-DD", style={"width": "47%"}),
                        html.Span(" ~ ", style={"padding": "0 5px"}),
                        dcc.DatePickerSingle(id="date_input_tab3_end", date=t3_e, display_format="YYYY-MM-DD", style={"width": "47%"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], xs=12, md=6)
            ], className="g-2 mb-3"),
            chart_node
        ]), out_storage

    elif active_tab == "tab-4":
        dropdown_opts = cleans if cleans else ["종목 없음"]
        cl_stock = cl_stock if cl_stock in dropdown_opts else dropdown_opts[0]

        if cleans and cl_stock != "종목 없음":
            c_ticker = clean_sel_name(cl_stock)
            c_name = clean_pure_name(cl_stock)
            df = get_all_investor_data(c_ticker, t4_s, t4_e)
            chart_node = dcc.Graph(figure=draw_custom_multi_chart(df, c_name, current_configs), config={"scrollZoom": True, "displayModeBar": False}) if not df.empty else dbc.Alert("해당 기간 내 데이터가 없습니다.", color="warning", className="mt-2")
        else:
            chart_node = dbc.Alert(f"현재 [{primary_subject}] 기준 조건에 부합하는 정리 대상 종목이 없습니다.", color="warning", className="mt-2")

        return html.Div([
            dbc.Row([
                dbc.Col([
                    html.Label("정리 종목 선택:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    dcc.Dropdown(id="clean_sel", options=[{"label": i, "value": i} for i in dropdown_opts], value=cl_stock, clearable=False, style={"fontSize": "14px"})
                ], xs=12, md=6),
                dbc.Col([
                    html.Label("📅 분석 기간:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    html.Div([
                        dcc.DatePickerSingle(id="date_input_tab4_start", date=t4_s, display_format="YYYY-MM-DD", style={"width": "47%"}),
                        html.Span(" ~ ", style={"padding": "0 5px"}),
                        dcc.DatePickerSingle(id="date_input_tab4_end", date=t4_e, display_format="YYYY-MM-DD", style={"width": "47%"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], xs=12, md=6)
            ], className="g-2 mb-3"),
            chart_node
        ]), out_storage

    elif active_tab == "tab-5":
        fav_stocks = fav_stocks if fav_stocks is not None else default_favs
        charts_list = []

        if fav_stocks:
            for idx, stock_name in enumerate(fav_stocks):
                if stock_name not in stock_df['선택용_이름'].values: continue
                ticker = stock_df[stock_df['선택용_이름'] == stock_name]['티커'].values[0]
                name = stock_df[stock_df['선택용_이름'] == stock_name]['종목명'].values[0]
                df_fav = get_all_investor_data(ticker, t5_s, t5_e)
                if not df_fav.empty:
                    charts_list.append(dcc.Graph(id=f"chart_fav_{ticker}_{idx}", figure=draw_custom_multi_chart(df_fav, name, current_configs), config={"scrollZoom": True, "displayModeBar": False}))
                else:
                    charts_list.append(dbc.Alert(f"{name} 종목은 선택한 기간 내 데이터가 없습니다.", color="light", className="mt-1"))
        else:
            charts_list.append(dbc.Alert("즐겨찾기할 종목을 위에서 선택해 주세요.", color="info"))

        return html.Div([
            dbc.Row([
                dbc.Col([
                    html.Label("📌 즐겨찾기 종목 선택 (다중):", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    dcc.Dropdown(id="fav_box", options=[{"label": i, "value": i} for i in stock_df['선택용_이름']], value=fav_stocks, multi=True, style={"fontSize": "14px"})
                ], xs=12, md=6),
                dbc.Col([
                    html.Label("📅 분석 기간:", className="font-weight-bold text-secondary", style={"fontSize": "13px"}),
                    html.Div([
                        dcc.DatePickerSingle(id="date_input_tab5_start", date=t5_s, display_format="YYYY-MM-DD", style={"width": "47%"}),
                        html.Span(" ~ ", style={"padding": "0 5px"}),
                        dcc.DatePickerSingle(id="date_input_tab5_end", date=t5_e, display_format="YYYY-MM-DD", style={"width": "47%"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], xs=12, md=6)
            ], className="g-2 mb-3"),
            html.Div(charts_list)
        ]), out_storage

    return html.Div("선택된 탭이 없습니다."), out_storage

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)   # [수정] run_server → run (Dash 3.x+ 제거됨)
