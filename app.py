import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import cot_reports as cot

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

# Interne Zuordnungen für Yahoo (Preis) und CFTC (Echte Namen in der US-Datenbank)
market_meta = {
    "S&P 500 E-Mini": {"yf": "^SPX", "cftc_name": "E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE"},
    "Nasdaq 100 E-Mini": {"yf": "^NDX", "cftc_name": "E-MINI NASDAQ-100 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE"},
    "Gold": {"yf": "GC=F", "cftc_name": "GOLD - COMMODITY EXCHANGE INC."},
    "Rohöl (WTI)": {"yf": "CL=F", "cftc_name": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE"},
    "10Y US Treasury Note": {"yf": "^TNX", "cftc_name": "10-YEAR U.S. TREASURY NOTES - CHICAGO BOARD OF TRADE"}
}

# 2. ECHTE CFTC COT-DATEN LADEN
@st.cache_data(ttl=86400)
def load_real_cot_data(report_style, start_year):
    current_year = datetime.now().year
    df_list = []
    
    # Schleife lädt die echten Textdateien für die Jahre von den US-Servern
    for yr in range(start_year, current_row := current_year + 1):
        try:
            if report_style == "Klassisch (Commercials vs. Small Specs)":
                # Lädt den echten "Legacy" Report
                annual_df = cot.cot_year(yr, report="legacy_fut")
            else:
                # Lädt den echten "Financial Traders" Report
                annual_df = cot.cot_year(yr, report="traders_in_financial_futures_fut")
            df_list.append(annual_df)
        except:
            continue
            
    if not df_list:
        return pd.DataFrame()
        
    full_cot = pd.concat(df_list, ignore_index=True)
    
    # Spalten bereinigen und Datum als Index setzen
    full_cot['Report_Date_as_MM_DD_YYYY'] = pd.to_datetime(full_cot['Report_Date_as_MM_DD_YYYY'])
    full_cot.set_index('Report_Date_as_MM_DD_YYYY', inplace=True)
    full_cot.sort_index(inplace=True)
    return full_cot

# 3. VERARBEITUNG & HARMONISIERUNG
@st.cache_data(ttl=3600)
def process_dashboard_data(symbol, years, smoothing, ma_int, ma_cot, rep_style):
    meta = market_meta[symbol]
    
    # 10 Jahre Historie berechnen
    start_year = datetime.now().year - years - 2
    
    # Echte COT-Daten von US-Server holen
    raw_cot = load_real_cot_data(rep_style, start_year)
    if raw_cot.empty:
        st.error("Fehler beim Laden der echten CFTC-Daten.")
        return pd.DataFrame()
        
    # Nach dem exakten Marktnamen der US-Behörde filtern
    market_cot = raw_cot[raw_cot['Market_and_Exchange_Names'].str.contains(meta['cftc_name'], na=False, case=False)]
    
    # Reines Kurs-Umfeld von Yahoo holen
    price_df = yf.download(meta['yf'], start=datetime(start_year, 1, 1), end=datetime.now())
    price_weekly = price_df.resample('W-FRI').agg({'Close': 'last', 'High': 'max', 'Low': 'min'}).ffill()
    
    # Makro-Daten holen
    dxy = yf.download("DX-Y.NYB", start=datetime(start_year, 1, 1), end=datetime.now())['Close'].resample('W-FRI').last().ffill()
    oil = yf.download("CL=F", start=datetime(start_year, 1, 1), end=datetime.now())['Close'].resample('W-FRI').last().ffill()
    tnx = yf.download("^TNX", start=datetime(start_year, 1, 1), end=datetime.now())['Close'].resample('W-FRI').last().ffill()
    
    # Daten matchen
    final_df = pd.DataFrame(index=price_weekly.index)
    final_df['Close'] = price_weekly['Close']
    final_df['DXY'] = dxy
    final_df['Oil'] = oil
    final_df['TNX'] = tnx
    
    # Berechnung der echten Netto-Differenzen aus den CFTC-Spalten
    # Wir mappen die Wochentage, da die CFTC Dienstagsstände Freitags ausgibt
    market_cot.index = market_cot.index.map(lambda x: x + timedelta(days=(4 - x.weekday()) % 7))
    
    if rep_style == "Klassisch (Commercials vs. Small Specs)":
        # Echte Formel: Commercial Longs minus Commercial Shorts MINUS (Non-Reportable Longs - Non-Reportable Shorts)
        smart = pd.to_numeric(market_cot['Commercial_Positions_Long_All'], errors='coerce') - pd.to_numeric(market_cot['Commercial_Positions_Short_All'], errors='coerce')
        dumb = pd.to_numeric(market_cot['Nonreportable_Positions_Long_All'], errors='coerce') - pd.to_numeric(market_cot['Nonreportable_Positions_Short_All'], errors='coerce')
    else:
        # Echte Formel für Financials (TFF): Dealer Intermediary Netto MINUS Leveraged Funds Netto
        smart = pd.to_numeric(market_cot['Dealer_Positions_Long_All'], errors='coerce') - pd.to_numeric(market_cot['Dealer_Positions_Short_All'], errors='coerce')
        dumb = pd.to_numeric(market_cot['Asset_Mgr_Positions_Long_All'], errors='coerce') - pd.to_numeric(market_cot['Asset_Mgr_Positions_Short_All'], errors='coerce')
        
    final_df['Real_COT_Diff'] = smart - dumb
    final_df = final_df.ffill().bfill()
    
    # Intermarket Indikator berechnen
    s_n = final_df['Close'] / final_df['Close'].rolling(window=smoothing).mean()
    d_n = final_df['DXY'] / final_df['DXY'].rolling(window=smoothing).mean()
    o_n = final_df['Oil'] / final_df['Oil'].rolling(window=smoothing).mean()
    t_n = final_df['TNX'] / final_df['TNX'].rolling(window=smoothing).mean()
    final_df['Intermarket_Index'] = (s_n * d_n) / (o_n * t_n)
    final_df['Intermarket_MA'] = final_df['Intermarket_Index'].rolling(window=ma_int).mean()
    
    # Echten stochastischen COT Index (0-100) berechnen
    high_diff = final_df['Real_COT_Diff'].rolling(window=smoothing).max()
    low_diff = final_df['Real_COT_Diff'].rolling(window=smoothing).min()
    final_df['COT_Index'] = 100 * (final_df['Real_COT_Diff'] - low_diff) / (high_diff - low_diff)
    final_df['COT_MA'] = final_df['COT_Index'].rolling(window=ma_cot).mean()
    
    return final_df.tail(years * 52)

df = process_dashboard_data(markt, lookback_years, smoothing_weeks, ma_intermarket_len, ma_cot_len, report_type)

# --- ZEITZONEN-GITTER BERECHNEN ---
grid_dates = []
if not df.empty:
    start_dt = df.index
    end_dt = df.index[-1]
    curr = datetime(start_dt.year, start_dt.month, 1)
    while curr <= end_dt:
        if lookback_years <= 2 or curr.month % 3 == 0:
            grid_dates.append(curr.strftime("%Y-%m-%d"))
        if curr.month == 12: curr = datetime(curr.year + 1, 1, 1)
        else: curr = datetime(curr.year, curr.month + 1, 1)

# --- INTERAKTIVES PLOTLY DRAWING ---
if not df.empty:
    rows = 3 if show_intermarket else 2
    heights = [0.5, 0.25, 0.25] if show_intermarket else [0.65, 0.35]
    titles = (f"Kursverlauf: {markt}", "1. Intermarket Makro-Indikator", f"2. ECHTER CFTC COT-Index ({report_type})") if show_intermarket else (f"Kursverlauf: {markt}", f"2. ECHTER CFTC COT-Index ({report_type})")
    
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
    fig.add_shape(type="line", x0=df.index, y0=20, x1=df.index[-1], y1=20, line=dict(color="Red", dash="dash"), row=current_row := c_row, col=1)
    
    for d_str in grid_dates:
        fig.add_vline(x=d_str, line_width=0.8, line_dash="solid", line_color="rgba(255,255,255,0.15)")
        
    fig.update_layout(template="plotly_dark", height=850, showlegend=False, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
    st.info("🎯 Dieses Dashboard visualisiert jetzt die offiziellen, ungefilterten Rohdaten-Meldungen der US-Regierungbehörde CFTC.")
