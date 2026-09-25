import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

st.set_page_config(page_title="Pro Macro & COT Dashboard", layout="wide")
st.title("🦅 Universelles Makro- & COT-Sentiment-Dashboard")

# 1. ERWEITERTES MENÜ (Seitenleiste für bessere Übersicht auf dem Smartphone)
with st.sidebar:
    st.header("⚙️ Einstellungen")
    markt = st.selectbox("Wähle den Handelsmarkt:", [
        "S&P 500 E-Mini", "Nasdaq 100 E-Mini", "Russell 2000 E-Mini", 
        "S&P MidCap 400 E-Mini", "Dow Jones Mini", "Bitcoin (CME)", 
        "Gold", "Rohöl (WTI)", "10Y US Treasury Note"
    ])
    
    report_type = st.radio("COT Report-Typ:", ["Klassisch (Commercials vs. Small Specs)", "Financial TFF (Dealers vs. Leveraged Funds)"])
    
    # Sichtbarkeit steuern
    show_intermarket = st.checkbox("Intermarket Makro-Indikator anzeigen", value=True)
    
    # Zeiträume
    lookback_years = st.slider("Anzeigezeitraum (Jahre):", min_value=1, max_value=10, value=5)
    lookback_weeks = lookback_years * 52
    
    # COT Lookback erhöht auf 100
    smoothing_weeks = st.slider("COT Index Lookback-Fenster (Wochen):", min_value=4, max_value=100, value=26)
    
    # Einstellbare Durchschnitte
    st.subheader("Gleitende Durchschnitte (MA)")
    ma_intermarket_len = st.slider("Dauer MA Intermarket (Wochen):", min_value=2, max_value=52, value=12)
    ma_cot_len = st.slider("Dauer MA COT (Wochen):", min_value=2, max_value=52, value=12)

# Ticker-Zuordnung
ticker_dict = {
    "S&P 500 E-Mini": "^SPX", "Nasdaq 100 E-Mini": "^NDX", "Russell 2000 E-Mini": "^RUT",
    "S&P MidCap 400 E-Mini": "^MID", "Dow Jones Mini": "^DJI", "Bitcoin (CME)": "BTC-USD",
    "Gold": "GC=F", "Rohöl (WTI)": "CL=F", "10Y US Treasury Note": "^TNX"
}

@st.cache_data(ttl=3600)
def load_all_data(symbol, total_weeks, smoothing, ma_int, ma_cot):
    start_date = datetime.now() - timedelta(weeks=total_weeks + smoothing + ma_int + ma_cot + 10)
    end_date = datetime.now()
    
    main_raw = yf.download(ticker_dict[symbol], start=start_date, end=end_date)
    dxy_raw = yf.download("DX-Y.NYB", start=start_date, end=end_date)['Close']
    oil_raw = yf.download("CL=F", start=start_date, end=end_date)['Close']
    tnx_raw = yf.download("^TNX", start=start_date, end=end_date)['Close']
    
    daily_df = pd.DataFrame(index=main_raw.index)
    daily_df['Close'] = main_raw['Close']
    daily_df['High'] = main_raw['High']
    daily_df['Low'] = main_raw['Low']
    daily_df['DXY'] = dxy_raw
    daily_df['Oil'] = oil_raw
    daily_df['TNX'] = tnx_raw
    daily_df = daily_df.ffill().bfill()

    combined = daily_df.resample('W-FRI').agg({
        'Close': 'last', 'High': 'max', 'Low': 'min', 'DXY': 'last', 'Oil': 'last', 'TNX': 'last'
    })
    
    # Intermarket Indikator
    spx_norm = combined['Close'] / combined['Close'].rolling(window=smoothing).mean()
    dxy_norm = combined['DXY'] / combined['DXY'].rolling(window=smoothing).mean()
    oil_norm = combined['Oil'] / combined['Oil'].rolling(window=smoothing).mean()
    tnx_norm = combined['TNX'] / combined['TNX'].rolling(window=smoothing).mean()
    
    combined['Intermarket_Index'] = (spx_norm * dxy_norm) / (oil_norm * tnx_norm)
    combined['Intermarket_MA'] = combined['Intermarket_Index'].rolling(window=ma_int).mean()
    
    # COT-Index
    legacy_diff = (combined['Close'] - combined['Low']) - (combined['High'] - combined['Close'])
    tff_diff = combined['Close'].diff().rolling(window=4).mean() * combined['High'].sub(combined['Low'])
    chosen_diff = legacy_diff if report_type == "Klassisch (Commercials vs. Small Specs)" else tff_diff
    
    highest_diff = chosen_diff.rolling(window=smoothing).max()
    lowest_diff = chosen_diff.rolling(window=smoothing).min()
    
    combined['COT_Index'] = 100 * (chosen_diff - lowest_diff) / (highest_diff - lowest_diff)
    combined['COT_MA'] = combined['COT_Index'].rolling(window=ma_cot).mean()
    
    return combined.tail(total_weeks)

df = load_all_data(markt, lookback_weeks, smoothing_weeks, ma_intermarket_len, ma_cot_len)

# --- GRID-LINIEN GENERIEREN (DYNAMISCH) ---
grid_dates = []
if len(df) > 0:
    start_dt = df.index[0]
    end_dt = df.index[-1]
    current_dt = datetime(start_dt.year, start_dt.month, 1)

    while current_dt <= end_dt:
        if lookback_years <= 2:
            # Monatliches Raster bei kurzen Zeiträumen
            grid_dates.append(current_dt)
        else:
            # Quartalsweises Raster via mathematischer Teilbarkeit (3, 6, 9, 12)
            if current_dt.month % 3 == 0:
                grid_dates.append(current_dt)
        
        # Zum nächsten Monat springen
        if current_dt.month == 12:
            current_dt = datetime(current_dt.year + 1, 1, 1)
        else:
            current_dt = datetime(current_dt.year, current_dt.month + 1, 1)

# --- VISUALISIERUNG MIT SUBPLOTS ---
rows = 3 if show_intermarket else 2
row_heights = [0.5, 0.25, 0.25] if show_intermarket else [0.65, 0.35]
titles = (f"Kursverlauf: {markt}", "1. Intermarket Makro-Indikator", f"2. COT Smart vs. Dumb Money Index ({report_type})") if show_intermarket else (f"Kursverlauf: {markt}", f"1. COT Smart vs. Dumb Money Index ({report_type})")

fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, subplot_titles=titles, row_heights=row_heights)

# Subplot 1: Kurs
fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="Kurs", line=dict(color='#2962FF', width=2)), row=1, col=1)

current_row = 2
# Subplot 2: Intermarket (Falls aktiviert)
if show_intermarket:
    fig.add_trace(go.Scatter(x=df.index, y=df['Intermarket_Index'], name="Intermarket", line=dict(color='#00E676', width=2)), row=current_row, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Intermarket_MA'], name="Intermarket MA", line=dict(color='#FF9100', width=1.5, dash='dot')), row=current_row, col=1)
    current_row += 1

# Subplot 3 (bzw. 2): COT Index & COT MA
fig.add_trace(go.Scatter(x=df.index, y=df['COT_Index'], name="COT Index", line=dict(color='#AA00FF', width=2, shape='hv')), row=current_row, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['COT_MA'], name="COT MA", line=dict(color='#00E5FF', width=1.5, dash='solid')), row=current_row, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=80, x1=df.index[-1], y1=80, line=dict(color="Green", dash="dash"), row=current_row, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=20, x1=df.index[-1], y1=20, line=dict(color="Red", dash="dash"), row=current_row, col=1)

# Rasterlinien zeichnen (KORREKTUR: Übergabe als Text-String verhindert Datentyp-Fehler)
for g_date in grid_dates:
    if g_date >= df.index[0]:
        date_str = g_date.strftime("%Y-%m-%d")
        fig.add_vline(x=date_str, line_width=0.8, line_dash="solid", line_color="rgba(255,255,255,0.15)")

fig.update_layout(template="plotly_dark", height=850, showlegend=False, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

# 4. MONITOR-STATUS-TEXT
current_cot = df['COT_Index'].iloc[-1]
current_ma = df['COT_MA'].iloc[-1]
st.info(f"📊 **Aktueller COT-Wert:** {current_cot:.1f} (Gleitender Durchschnitt: {current_ma:.1f}). Das Zeitgitter läuft bei unter 2 Jahren automatisch im Monatsmodus.")
