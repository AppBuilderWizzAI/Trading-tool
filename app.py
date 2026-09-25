import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

st.set_page_config(page_title="Macro & COT Dashboard", layout="wide")
st.title("📊 Mein Makro- & Sentiment-Handels-Dashboard")

# 1. Menü zur Steuerung
markt = st.selectbox("Wähle den zu analysierenden Hauptmarkt:", ["S&P 500", "Nasdaq 100", "Gold", "Rohöl (WTI)", "Bitcoin"])
length = st.slider("Trend-Zeitraum für Normierung / Signallinie (Tage):", min_value=10, max_value=200, value=50)

# Interne Ticker-Zuordnung (Yahoo Finance)
ticker_dict = {
    "S&P 500": "^SPX",
    "Nasdaq 100": "^NDX",
    "Gold": "GC=F",
    "Rohöl (WTI)": "CL=F",
    "Bitcoin": "BTC-USD"
}

@st.cache_data(ttl=3600)
def load_all_data(symbol, lookback_days):
    start_date = datetime.now() - timedelta(days=lookback_days + 365)
    end_date = datetime.now()
    
    # Hauptmarkt laden
    main_df = yf.download(ticker_dict[symbol], start=start_date, end=end_date)
    
    # Makro-Daten für den Intermarket-Indikator laden
    dxy_df = yf.download("DX-Y.NYB", start=start_date, end=end_date)['Close'] # US Dollar Index
    oil_df = yf.download("CL=F", start=start_date, end=end_date)['Close']       # Rohöl WTI
    tnx_df = yf.download("^TNX", start=start_date, end=end_date)['Close']       # 10Y US-Zinsen
    
    # Daten harmonisieren (Zusammenführen über den Zeitstempel)
    combined = pd.DataFrame(index=main_df.index)
    combined['Close'] = main_df['Close']
    combined['High'] = main_df['High']
    combined['Low'] = main_df['Low']
    combined['DXY'] = dxy_df
    combined['Oil'] = oil_df
    combined['TNX'] = tnx_df
    combined = combined.ffill().bfill() # Fehlzeiten glätten
    
    # --- 2. BERECHNUNG: INTERMARKET-INDIKATOR (Zinsen, Öl, Kehrwert-Dollar) ---
    # Werte auf gleitenden Durchschnitt normieren, um "Erdrücken" zu verhindern
    spx_norm = combined['Close'] / combined['Close'].rolling(window=lookback_days).mean()
    dxy_norm = combined['DXY'] / combined['DXY'].rolling(window=lookback_days).mean()
    oil_norm = combined['Oil'] / combined['Oil'].rolling(window=lookback_days).mean()
    tnx_norm = combined['TNX'] / combined['TNX'].rolling(window=lookback_days).mean()
    
    # Logik: spx_norm / (oil_norm * tnx_norm * (1 / dxy_norm)) 
    # Wird mathematisch vereinfacht zu: (spx_norm * dxy_norm) / (oil_norm * tnx_norm)
    combined['Intermarket_Index'] = (spx_norm * dxy_norm) / (oil_norm * tnx_norm)
    combined['Signal_Line'] = combined['Intermarket_Index'].rolling(window=lookback_days).mean()
    
    # --- 3. BERECHNUNG: SMART/DUMB MONEY COT-INDEX (Proxy-Modell) ---
    raw_diff = (combined['Close'] - combined['Low']) - (combined['High'] - combined['Close'])
    highest_diff = raw_diff.rolling(window=lookback_days).max()
    lowest_diff = raw_diff.rolling(window=lookback_days).min()
    combined['COT_Index'] = 100 * (raw_diff - lowest_diff) / (highest_diff - lowest_diff)
    
    return combined.tail(365) # Die letzten 365 Handelstage anzeigen

# Daten verarbeiten
df = load_all_data(markt, length)

# --- 4. VISUALISIERUNG UNTEREINANDER (SUBPLOTS) ---
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                    vertical_spacing=0.05, 
                    subplot_titles=(f"Kursverlauf: {markt}", "1. Intermarket Indikator (Zinsen/Öl/Kehrwert-Dollar)", "2. COT Smart vs. Dumb Money Index"),
                    row_heights=[0.5, 0.25, 0.25])

# Subplot 1: Preis
fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="Kurs", line=dict(color='#2962FF', width=2)), row=1, col=1)

# Subplot 2: Intermarket Indikator
fig.add_trace(go.Scatter(x=df.index, y=df['Intermarket_Index'], name="Intermarket Ind.", line=dict(color='#00E676', width=2)), row=2, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['Signal_Line'], name="Signallinie", line=dict(color='#FF9100', width=1, dash='dot')), row=2, col=1)

# Subplot 3: COT-Index
fig.add_trace(go.Scatter(x=df.index, y=df['COT_Index'], name="COT Index", line=dict(color='#AA00FF', width=2)), row=3, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=80, x1=df.index[-1], y1=80, line=dict(color="Green", dash="dash"), row=3, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=20, x1=df.index[-1], y1=20, line=dict(color="Red", dash="dash"), row=3, col=1)

# Design-Tuning (Dunkler Profi-Look)
fig.update_layout(template="plotly_dark", height=800, showlegend=False,
                  xaxis3=dict(title="Datum"))
fig.update_yaxes(title_text="Preis", row=1, col=1)
fig.update_yaxes(title_text="Index Wert", row=2, col=1)
fig.update_yaxes(title_text="0 - 100", row=3, col=1)

st.plotly_chart(fig, use_container_width=True)

# 5. Live-Signal-Auswertung auf dem Dashboard
current_intermarket = df['Intermarket_Index'].iloc[-1]
current_signal = df['Signal_Line'].iloc[-1]
current_cot = df['COT_Index'].iloc[-1]

col1, col2 = st.columns(2)
with col1:
    if current_intermarket < current_signal:
        st.error(f"⚠️ **Intermarket-Warnung:** Die Makro-Kräfte drehen ab! (Index {current_intermarket:.3f} unter Signallinie {current_signal:.3f})")
    else:
        st.success(f"🍏 **Intermarket stabil:** Das makroökonomische Umfeld stützt den Trend.")

with col2:
    if current_cot > 80:
        st.success(f"🟩 **COT Kaufsignal ({current_cot:.1f}):** Smart Money akkumuliert stark gegen das Dumb Money.")
    elif current_cot < 20:
        st.error(f"🟥 **COT Warnsignal ({current_cot:.1f}):** Dumb Money ist maximal optimistisch, Smart Money zieht sich zurück.")
    else:
        st.info(f"🟪 **COT Neutral ({current_cot:.1f}):** Das Sentiment befindet sich im Gleichgewicht.")
