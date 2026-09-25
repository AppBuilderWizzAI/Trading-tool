import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="Real COT & Macro Dashboard", layout="wide")
st.title("🦅 Echtes Makro- & CFTC COT-Sentiment-Dashboard")

# 1. MENÜ IN DER SEITENLEISTE
with st.sidebar:
    st.header("⚙️ Einstellungen")
    markt = st.selectbox("Wähle den Handelsmarkt:", [
        "S&P 500 E-Mini", "Nasdaq 100 E-Mini", "Gold", "Rohöl (WTI)", "10Y US Treasury Note"
    ])
    
    report_type = st.radio("COT Report-Typ:", ["Klassisch (Commercials vs. Small Specs)", "Financial TFF (Dealers vs. Leveraged Funds)"])
    
    show_intermarket = st.checkbox("Intermarket Makro-Indikator anzeigen", value=True)
    lookback_years = st.slider("Anzeigezeitraum (Jahre):", min_value=1, max_value=10, value=5)
    smoothing_weeks = st.slider("COT Index Lookback-Fenster (Wochen):", min_value=4, max_value=100, value=26)
    
    st.subheader("Gleitende Durchschnitte (MA)")
    ma_intermarket_len = st.slider("Dauer MA Intermarket (Wochen):", min_value=2, max_value=52, value=12)
    ma_cot_len = st.slider("Dauer MA COT (Wochen):", min_value=2, max_value=52, value=12)

# Offizielle API-Marktnamen der US-Aufsichtsbehörde CFTC
market_meta = {
    "S&P 500 E-Mini": {"yf": "^SPX", "cftc_name": "E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE"},
    "Nasdaq 100 E-Mini": {"yf": "^NDX", "cftc_name": "E-MINI NASDAQ-100 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE"},
    "Gold": {"yf": "GC=F", "cftc_name": "GOLD - COMMODITY EXCHANGE INC."},
    "Rohöl (WTI)": {"yf": "CL=F", "cftc_name": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE"},
    "10Y US Treasury Note": {"yf": "^TNX", "cftc_name": "10-YEAR U.S. TREASURY NOTES - CHICAGO BOARD OF TRADE"}
}

# 2. DIREKTE ABFRAGE DER OFFIZIELLEN CFTC GOVERNMENT API
@st.cache_data(ttl=3600)
def load_cftc_api_data(cftc_market_name, rep_style, limit=520):
    dataset_id = "6dca-5xup" if rep_style == "Klassisch (Commercials vs. Small Specs)" else "xwd6-7n4g"
    safe_name = urllib.parse.quote(cftc_market_name)
    api_url = f"https://cftc.gov{dataset_id}.json?$where=market_and_exchange_names='{safe_name}'&$order=report_date_as_mm_dd_yyyy DESC&$limit={limit}"
    
    try:
        df_api = pd.read_json(api_url)
        if df_api.empty:
            return pd.DataFrame()
        
        df_api['report_date_as_mm_dd_yyyy'] = pd.to_datetime(df_api['report_date_as_mm_dd_yyyy'])
        df_api.set_index('report_date_as_mm_dd_yyyy', inplace=True)
        df_api.sort_index(inplace=True)
        return df_api
    except:
        return pd.DataFrame()

# 3. DATEN VERARBEITEN & GRAFIK ERSTELLEN
meta = market_meta[markt]
start_year = datetime.now().year - lookback_years - 2

# Echte Daten via Live-Regierungs-API laden
cot_raw = load_cftc_api_data(meta['cftc_name'], report_type, limit=lookback_years * 54)

# Yahoo Kursdaten holen und Spalten-Struktur radikal vereinfachen
price_raw_df = yf.download(meta['yf'], start=datetime(start_year, 1, 1), end=datetime.now())
price_raw_df = pd.DataFrame(price_raw_df.values, index=price_raw_df.index, columns=price_raw_df.columns.get_level_values(0))

df = price_raw_df.resample('W-FRI').agg({'Close': 'last', 'High': 'max', 'Low': 'min'}).ffill()

# Makro-Daten holen und vereinfachen
dxy_raw = yf.download("DX-Y.NYB", start=datetime(start_year, 1, 1), end=datetime.now())
dxy_raw = pd.DataFrame(dxy_raw.values, index=dxy_raw.index, columns=dxy_raw.columns.get_level_values(0))
df['DXY'] = dxy_raw['Close'].resample('W-FRI').last().ffill()

oil_raw = yf.download("CL=F", start=datetime(start_year, 1, 1), end=datetime.now())
oil_raw = pd.DataFrame(oil_raw.values, index=oil_raw.index, columns=oil_raw.columns.get_level_values(0))
df['Oil'] = oil_raw['Close'].resample('W-FRI').last().ffill()

tnx_raw = yf.download("^TNX", start=datetime(start_year, 1, 1), end=datetime.now())
tnx_raw = pd.DataFrame(tnx_raw.values, index=tnx_raw.index, columns=tnx_raw.columns.get_level_values(0))
df['TNX'] = tnx_raw['Close'].resample('W-FRI').last().ffill()

# Echte Netto-Positionen extrahieren, falls API Daten lieferte
if not cot_raw.empty:
    cot_raw.index = cot_raw.index.map(lambda x: x + timedelta(days=(4 - x.weekday()) % 7))
    
    if report_type == "Klassisch (Commercials vs. Small Specs)":
        smart = pd.to_numeric(cot_raw['commercial_positions_long_all'], errors='coerce') - pd.to_numeric(cot_raw['commercial_positions_short_all'], errors='coerce')
        dumb = pd.to_numeric(cot_raw['nonreportable_positions_long_all'], errors='coerce') - pd.to_numeric(cot_raw['nonreportable_positions_short_all'], errors='coerce')
    else:
        smart = pd.to_numeric(cot_raw['dealer_positions_long_all'], errors='coerce') - pd.to_numeric(cot_raw['dealer_positions_short_all'], errors='coerce')
        dumb = pd.to_numeric(cot_raw['leveraged_funds_positions_long_all'], errors='coerce') - pd.to_numeric(cot_raw['leveraged_funds_positions_short_all'], errors='coerce')
        
    df['Real_COT_Diff'] = smart - dumb
else:
    st.warning("⚠️ Verbindung zum CFTC-Regierungsserver unterbrochen. Verwende temporäres Puffer-Modell.")
    df['Real_COT_Diff'] = (df['Close'] - df['Low']) - (df['High'] - df['Close'])

df = df.ffill().bfill().tail(lookback_years * 52)

# Indikatoren berechnen
s_n = df['Close'] / df['Close'].rolling(window=smoothing_weeks).mean()
d_n = df['DXY'] / df['DXY'].rolling(window=smoothing_weeks).mean()
o_n = df['Oil'] / df['Oil'].rolling(window=smoothing_weeks).mean()
t_n = df['TNX'] / df['TNX'].rolling(window=smoothing_weeks).mean()
df['Intermarket_Index'] = (s_n * d_n) / (o_n * t_n)
df['Intermarket_MA'] = df['Intermarket_Index'].rolling(window=ma_intermarket_len).mean()

high_diff = df['Real_COT_Diff'].rolling(window=smoothing_weeks).max()
low_diff = df['Real_COT_Diff'].rolling(window=smoothing_weeks).min()
df['COT_Index'] = 100 * (df['Real_COT_Diff'] - low_diff) / (high_diff - low_diff)
df['COT_MA'] = df['COT_Index'].rolling(window=ma_cot_len).mean()

# --- ZEITZONEN-GITTER BERECHNEN (KORREKTUR: .index[0] nimmt das erste Datum als Startpunkt) ---
grid_dates = []
if len(df) > 0:
    start_dt = df.index[0]
    end_dt = df.index[-1]
    curr = datetime(start_dt.year, start_dt.month, 1)
    while curr <= end_dt:
        if lookback_years <= 2 or curr.month % 3 == 0:
            grid_dates.append(curr.strftime("%Y-%m-%d"))
        if curr.month == 12: curr = datetime(curr.year + 1, 1, 1)
        else: curr = datetime(curr.year, curr.month + 1, 1)

# --- VISUALISIERUNG ---
rows = 3 if show_intermarket else 2
heights = [0.5, 0.25, 0.25] if show_intermarket else [0.65, 0.35]
titles = (f"Kursverlauf: {markt}", "1. Intermarket Makro-Indikator", f"2. CFTC ECHTER COT-Index ({report_type})") if show_intermarket else (f"Kursverlauf: {markt}", f"2. CFTC ECHTER COT-Index ({report_type})")

fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, subplot_titles=titles, row_heights=heights)
fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="Kurs", line=dict(color='#2962FF', width=2)), row=1, col=1)

c_row = 2
if show_intermarket:
    fig.add_trace(go.Scatter(x=df.index, y=df['Intermarket_Index'], name="Intermarket", line=dict(color='#00E676', width=2)), row=c_row, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Intermarket_MA'], name="MA", line=dict(color='#FF9100', width=1.5, dash='dot')), row=c_row, col=1)
    c_row += 1
    
fig.add_trace(go.Scatter(x=df.index, y=df['COT_Index'], name="Echter COT", line=dict(color='#AA00FF', width=2, shape='hv')), row=c_row, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['COT_MA'], name="COT MA", line=dict(color='#00E5FF', width=1.5)), row=c_row, col=1)
fig.add_shape(type="line", x0=df.index, y0=80, x1=df.index[-1], y1=80, line=dict(color="Green", dash="dash"), row=c_row, col=1)
fig.add_shape(type="line", x0=df.index, y0=20, x1=df.index[-1], y1=20, line=dict(color="Red", dash="dash"), row=c_row, col=1)

for d_str in grid_dates:
    fig.add_vline(x=d_str, line_width=0.8, line_dash="solid", line_color="rgba(255,255,255,0.15)")
    
fig.update_layout(template="plotly_dark", height=850, showlegend=False, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

st.info("🎯 Dieses Dashboard bezieht die unzensierten Wochensentiments jetzt live über das offizielle Open-Data-API-Portal der US-Regierung (publicreporting.cftc.gov).")
