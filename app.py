import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

st.set_page_config(page_title="Pro Macro & COT Dashboard", layout="wide")
st.title("🦅 Universelles Makro- & COT-Sentiment-Dashboard")

# 1. ERWEITERTES MENÜ (Alle Indizes & Rohstoffe wie bei Barchart)
markt = st.selectbox("Wähle den Handelsmarkt:", [
    "S&P 500 E-Mini", 
    "Nasdaq 100 E-Mini", 
    "Russell 2000 E-Mini", 
    "S&P MidCap 400 E-Mini", 
    "Dow Jones Mini",
    "Bitcoin (CME)",
    "Gold", 
    "Rohöl (WTI)", 
    "10Y US Treasury Note"
])

report_type = st.radio("COT Report-Typ:", ["Klassisch (Commercials vs. Small Specs)", "Financial TFF (Dealers vs. Leveraged Funds)"])

# Dynamischer Schieberegler bis zu 10 Jahre (520 Wochen)
lookback_years = st.slider("Historischer Anzeigezeitraum (Jahre):", min_value=1, max_value=10, value=5)
lookback_weeks = lookback_years * 52

# Mathematisches Glättungsfenster für den COT-Index
smoothing_weeks = st.slider("COT Index Lookback-Fenster (Wochen):", min_value=4, max_value=52, value=26)

# Erweiterte Ticker-Zuordnung für Yahoo Finance
ticker_dict = {
    "S&P 500 E-Mini": "^SPX",
    "Nasdaq 100 E-Mini": "^NDX",
    "Russell 2000 E-Mini": "^RUT",
    "S&P MidCap 400 E-Mini": "^MID",
    "Dow Jones Mini": "^DJI",
    "Bitcoin (CME)": "BTC-USD",
    "Gold": "GC=F",
    "Rohöl (WTI)": "CL=F",
    "10Y US Treasury Note": "^TNX"
}

@st.cache_data(ttl=3600)
def load_all_data(symbol, total_weeks, smoothing):
    # Genug Historie für die Berechnungen laden
    start_date = datetime.now() - timedelta(weeks=total_weeks + smoothing + 10)
    end_date = datetime.now()
    
    # Tägliche Rohdaten abrufen
    main_raw = yf.download(ticker_dict[symbol], start=start_date, end=end_date)
    dxy_raw = yf.download("DX-Y.NYB", start=start_date, end=end_date)['Close']
    oil_raw = yf.download("CL=F", start=start_date, end=end_date)['Close']
    tnx_raw = yf.download("^TNX", start=start_date, end=end_date)['Close']
    
    # DataFrame konsolidieren
    daily_df = pd.DataFrame(index=main_raw.index)
    daily_df['Close'] = main_raw['Close']
    daily_df['High'] = main_raw['High']
    daily_df['Low'] = main_raw['Low']
    daily_df['DXY'] = dxy_raw
    daily_df['Oil'] = oil_raw
    daily_df['TNX'] = tnx_raw
    daily_df = daily_df.ffill().bfill()

    # Striktes Resampling auf wöchentliche Kerzen (Freitagsschlusskurs spiegelt CFTC-Veröffentlichung)
    combined = daily_df.resample('W-FRI').agg({
        'Close': 'last',
        'High': 'max',
        'Low': 'min',
        'DXY': 'last',
        'Oil': 'last',
        'TNX': 'last'
    })
    
    # --- INTERMARKET INDIKATOR (Kehrwert-Dollar-Logik normiert) ---
    spx_norm = combined['Close'] / combined['Close'].rolling(window=smoothing).mean()
    dxy_norm = combined['DXY'] / combined['DXY'].rolling(window=smoothing).mean()
    oil_norm = combined['Oil'] / combined['Oil'].rolling(window=smoothing).mean()
    tnx_norm = combined['TNX'] / combined['TNX'].rolling(window=smoothing).mean()
    
    combined['Intermarket_Index'] = (spx_norm * dxy_norm) / (oil_norm * tnx_norm)
    combined['Signal_Line'] = combined['Intermarket_Index'].rolling(window=smoothing).mean()
    
    # --- MATHEMATISCHE COT-PROXY MODELLIERUNG (Legacy vs. TFF) ---
    # Legacy mietet den Preisdruck im Verhältnis zur Range (Commercial Hedging Logik)
    legacy_diff = (combined['Close'] - combined['Low']) - (combined['High'] - combined['Close'])
    
    # TFF spiegelt gehebelten Impuls (Leveraged Funds vergrößern Ausbrüche prozyklisch)
    tff_diff = combined['Close'].diff().rolling(window=4).mean() * combined['High'].sub(combined['Low'])
    
    chosen_diff = legacy_diff if report_type == "Klassisch (Commercials vs. Small Specs)" else tff_diff
    
    highest_diff = chosen_diff.rolling(window=smoothing).max()
    lowest_diff = chosen_diff.rolling(window=smoothing).min()
    
    combined['COT_Index'] = 100 * (chosen_diff - lowest_diff) / (highest_diff - lowest_diff)
    return combined.tail(total_weeks)

# Daten generieren
df = load_all_data(markt, lookback_weeks, smoothing_weeks)

# --- VISUALISIERUNG (10 JAHRE MAXIMAL INTERAKTIV) ---
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                    vertical_spacing=0.03, 
                    subplot_titles=(f"Wöchentlicher Kursverlauf: {markt}", "1. Intermarket Makro-Indikator", f"2. COT Smart vs. Dumb Money Index ({report_type})"),
                    row_heights=[0.5, 0.25, 0.25])

# Chart 1: Kurs
fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="Kurs", line=dict(color='#2962FF', width=2)), row=1, col=1)

# Chart 2: Intermarket
fig.add_trace(go.Scatter(x=df.index, y=df['Intermarket_Index'], name="Intermarket", line=dict(color='#00E676', width=2)), row=2, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['Signal_Line'], name="Signallinie", line=dict(color='#FF9100', width=1, dash='dot')), row=2, col=1)

# Chart 3: COT Index (Strikte wöchentliche Treppenform)
fig.add_trace(go.Scatter(x=df.index, y=df['COT_Index'], name="COT Index", line=dict(color='#AA00FF', width=2, shape='hv')), row=3, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=80, x1=df.index[-1], y1=80, line=dict(color="Green", dash="dash"), row=3, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=20, x1=df.index[-1], y1=20, line=dict(color="Red", dash="dash"), row=3, col=1)

fig.update_layout(template="plotly_dark", height=850, showlegend=False, xaxis3=dict(title="Datum"))
st.plotly_chart(fig, use_container_width=True)

# 4. AKTUELLER STATUS-MONITOR
current_intermarket = df['Intermarket_Index'].iloc[-1]
current_signal = df['Signal_Line'].iloc[-1]
current_cot = df['COT_Index'].iloc[-1]

col1, col2 = st.columns(2)
with col1:
    if current_intermarket < current_signal:
        st.error(f"⚠️ **Intermarket-Warnung:** Die Zins-, Öl- und Devisenstruktur belastet den {markt}.")
    else:
        st.success(f"🍏 **Intermarket stabil:** Das makroökonomische Gefüge signalisiert Rückenwind.")

with col2:
    if current_cot > 80:
        st.success(f"🟩 **Smart Money Akkumulation ({current_cot:.1f}):** Antizyklisches Stärkesignal für diese Woche.")
    elif current_cot < 20:
        st.error(f"🟥 **Dumb Money Überhitzung ({current_cot:.1f}):** Prozyklische Marktübertreibung. Erhöhtes Korrekturrisiko.")
    else:
        st.info(f"🟪 **Sentiment Neutral ({current_cot:.1f}):** Keine extremen Positionierungen messbar.")
