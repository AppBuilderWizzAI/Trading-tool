import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

st.set_page_config(page_title="Macro & COT Dashboard", layout="wide")
st.title("📊 Mein Makro- & Sentiment-Handels-Dashboard (Wöchentlich korrigiert)")

# 1. Menü zur Steuerung
markt = st.selectbox("Wähle den zu analysierenden Hauptmarkt:", ["S&P 500", "Nasdaq 100", "Gold", "Rohöl (WTI)", "Bitcoin"])
length = st.slider("Trend-Zeitraum für Normierung / Signallinie (Wochen):", min_value=4, max_value=52, value=12)

# Interne Ticker-Zuordnung (Yahoo Finance)
ticker_dict = {
    "S&P 500": "^SPX",
    "Nasdaq 100": "^NDX",
    "Gold": "GC=F",
    "Rohöl (WTI)": "CL=F",
    "Bitcoin": "BTC-USD"
}

@st.cache_data(ttl=86400)
def load_all_data(symbol, lookback_weeks):
    # Genug Historie für die wöchentliche Umrechnung laden
    start_date = datetime.now() - timedelta(weeks=lookback_weeks + 150)
    end_date = datetime.now()
    
    # Tägliche Daten laden
    main_raw = yf.download(ticker_dict[symbol], start=start_date, end=end_date)
    dxy_raw = yf.download("DX-Y.NYB", start=start_date, end=end_date)['Close']
    oil_raw = yf.download("CL=F", start=start_date, end=end_date)['Close']
    tnx_raw = yf.download("^TNX", start=start_date, end=end_date)['Close']
    
    # Zusammenführen
    daily_df = pd.DataFrame(index=main_raw.index)
    daily_df['Close'] = main_raw['Close']
    daily_df['High'] = main_raw['High']
    daily_df['Low'] = main_raw['Low']
    daily_df['DXY'] = dxy_raw
    daily_df['Oil'] = oil_raw
    daily_df['TNX'] = tnx_raw
    daily_df = daily_df.ffill().bfill()

    # --- HIER IST DIE KORREKTUR: AUF WÖCHENTLICHE DATEN ZWINGEN ---
    # Wir nehmen den Freitag ('W-FRI'), um den Veröffentlichungsrhythmus der CFTC perfekt zu spiegeln.
    combined = daily_df.resample('W-FRI').agg({
        'Close': 'last',
        'High': 'max',
        'Low': 'min',
        'DXY': 'last',
        'Oil': 'last',
        'TNX': 'last'
    })
    
    # --- 2. BERECHNUNG: INTERMARKET-INDIKATOR (Wöchentlich normiert) ---
    spx_norm = combined['Close'] / combined['Close'].rolling(window=lookback_weeks).mean()
    dxy_norm = combined['DXY'] / combined['DXY'].rolling(window=lookback_weeks).mean()
    oil_norm = combined['Oil'] / combined['Oil'].rolling(window=lookback_weeks).mean()
    tnx_norm = combined['TNX'] / combined['TNX'].rolling(window=lookback_weeks).mean()
    
    combined['Intermarket_Index'] = (spx_norm * dxy_norm) / (oil_norm * tnx_norm)
    combined['Signal_Line'] = combined['Intermarket_Index'].rolling(window=lookback_weeks).mean()
    
    # --- 3. BERECHNUNG: REALISTISCHERER WÖCHENTLICHER COT-INDEX ---
    raw_diff = (combined['Close'] - combined['Low']) - (combined['High'] - combined['Close'])
    highest_diff = raw_diff.rolling(window=lookback_weeks).max()
    lowest_diff = raw_diff.rolling(window=lookback_weeks).min()
    
    combined['COT_Index'] = 100 * (raw_diff - lowest_diff) / (highest_diff - lowest_diff)
    return combined.tail(52) # Die letzten 52 Handelswochen (1 Jahr) anzeigen

# Daten verarbeiten
df = load_all_data(markt, length)

# --- 4. VISUALISIERUNG (SUBPLOTS) ---
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                    vertical_spacing=0.05, 
                    subplot_titles=(f"Wöchentlicher Kursverlauf: {markt}", "1. Intermarket Indikator (Wöchentlicher Makro-Trend)", "2. COT Smart vs. Dumb Money Index (Nur 1 Update pro Woche)"),
                    row_heights=[0.5, 0.25, 0.25])

fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="Kurs", line=dict(color='#2962FF', width=2)), row=1, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['Intermarket_Index'], name="Intermarket Ind.", line=dict(color='#00E676', width=2)), row=2, col=1)
fig.add_trace(go.Scatter(x=df.index, y=df['Signal_Line'], name="Signallinie", line=dict(color='#FF9100', width=1, dash='dot')), row=2, col=1)

# COT-Index wird nun als treppenförmige Linie gezeichnet (shape='hv')
fig.add_trace(go.Scatter(x=df.index, y=df['COT_Index'], name="COT Index", line=dict(color='#AA00FF', width=2, shape='hv')), row=3, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=80, x1=df.index[-1], y1=80, line=dict(color="Green", dash="dash"), row=3, col=1)
fig.add_shape(type="line", x0=df.index[0], y0=20, x1=df.index[-1], y1=20, line=dict(color="Red", dash="dash"), row=3, col=1)

fig.update_layout(template="plotly_dark", height=800, showlegend=False, xaxis3=dict(title="Datum"))
st.plotly_chart(fig, use_container_width=True)

# 5. Live-Signal-Auswertung auf dem Dashboard
current_intermarket = df['Intermarket_Index'].iloc[-1]
current_signal = df['Signal_Line'].iloc[-1]
current_cot = df['COT_Index'].iloc[-1]

col1, col2 = st.columns(2)
with col1:
    if current_intermarket < current_signal:
        st.error(f"⚠️ **Intermarket-Warnung:** Makro-Dynamik schwächt sich ab.")
    else:
        st.success(f"🍏 **Intermarket stabil:** Makro-Umfeld stützt die Bewegung.")

with col2:
    if current_cot > 80:
        st.success(f"🟩 **COT Kaufsignal ({current_cot:.1f}):** Institutionelle Akkumulation in dieser Woche.")
    elif current_cot < 20:
        st.error(f"🟥 **COT Warnsignal ({current_cot:.1f}):** Extreme spekulative Überhitzung in dieser Woche.")
    else:
        st.info(f"🟪 **COT Neutral ({current_cot:.1f}):** Wöchentliches Sentiment im Gleichgewicht.")
