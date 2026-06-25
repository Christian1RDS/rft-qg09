
import io
import sqlite3
from datetime import datetime, date, time, timedelta
from calendar import monthrange

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="RFT Automático - V9.9.6", page_icon="R", layout="wide")

DB = "rft_v996_local.db"
POSTOS = ["QG09", "QG07"]
YEAR_CLOSE_DAY = 10
DEFAULT_META = 95.0
CANON = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
FALHA_CANDIDATES = [
    "FALHA", "DEFEITO", "DS_DEFEITO", "NM_DEFEITO", "TIPO_FALHA", "DESCRICAO_DEFEITO",
    "DESCRIÇÃO_DEFEITO", "DESC_DEFEITO", "NOME_FALHA", "DS_FALHA", "NM_FALHA",
    "TIPO_DEFEITO", "CAUSA", "DESCRICAO", "DESCRIÇÃO", "OBS_DEFEITO", "PROBLEMA"
]
ALIASES = {
    "NR_WO": ["NR_WO", "WO", "ORDEM", "ORDEM_PRODUCAO", "ORDEM DE PRODUCAO", "ORDEM DE PRODUÇÃO", "OP", "WORK_ORDER"],
    "DT_HR_INSPECAO": ["DT_HR_INSPECAO", "DATA", "DATA_INSPECAO", "DATA INSPECAO", "DATA INSPEÇÃO", "DT_INSPECAO", "DT_HR", "DATA_HORA", "DATA HORA"],
    "C_DPU_QG_AMARELO": ["C_DPU_QG_AMARELO", "DPU", "QTD_DEFEITO", "QTD_DEFEITOS", "QTDE_DEFEITO", "QTDE_DEFEITOS", "QUANTIDADE", "QTD"],
    "CD_POSTO_CN": ["CD_POSTO_CN", "POSTO", "ESTACAO", "ESTAÇÃO", "STATION", "CD_POSTO", "POSTO_CN"],
}

CSS = """
<style>
:root { --line:rgba(148,163,184,.18); --txt:#e5e7eb; --muted:#94a3b8; --ok:#22c55e; --bad:#ef4444; }
html, body, [data-testid="stAppViewContainer"], .stApp { background: radial-gradient(circle at top left, #13213d 0%, #0b1220 35%, #09101c 100%); color: var(--txt); }
[data-testid="stHeader"] { background: rgba(11,18,32,.76); border-bottom: 1px solid var(--line); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0f172a 0%, #101827 100%); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] * { color: var(--txt) !important; }
.block-container { padding-top: .8rem; padding-bottom: 2rem; }
h1,h2,h3,h4,h5,h6,p,label,div,span { color: var(--txt); }
.hero { background: linear-gradient(135deg, rgba(24,34,53,.97), rgba(16,24,40,.98)); border:1px solid var(--line); border-radius:22px; padding:1.15rem 1.25rem; box-shadow:0 12px 36px rgba(0,0,0,.24); margin-bottom:1rem; }
.panel { background: linear-gradient(180deg, rgba(34,48,73,.96), rgba(21,31,47,.98)); border:1px solid var(--line); border-radius:18px; padding:1rem; box-shadow:0 10px 30px rgba(0,0,0,.18); margin-bottom:1rem; }
.metric-box { border:1px solid var(--line); background: linear-gradient(180deg, rgba(36,50,74,.96), rgba(25,36,54,.98)); border-radius:18px; padding:1rem; min-height:135px; }
.small { color: var(--muted); font-size:.86rem; }
.ok { color: var(--ok); }
.bad { color: var(--bad); }
.neutral { color: var(--txt); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# -------------------- Banco --------------------
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)


def init_db(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT,
        uploaded_at TEXT,
        rows INTEGER,
        message TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS dados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        upload_id INTEGER,
        nr_wo TEXT,
        dt TEXT,
        dpu REAL,
        posto TEXT,
        falha TEXT
    )
    """)
    conn.commit()


def uploads_table(conn):
    return pd.read_sql_query("SELECT id, file_name, uploaded_at, rows, message FROM uploads ORDER BY id DESC", conn)


def create_upload(conn, file_name, rows, message="Upload V9.9.6"):
    cur = conn.execute(
        "INSERT INTO uploads (file_name, uploaded_at, rows, message) VALUES (?, ?, ?, ?)",
        (file_name, datetime.now().isoformat(timespec="seconds"), int(rows), message),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_rows(conn, upload_id, df):
    rows = []
    for r in df.itertuples(index=False):
        rows.append((
            int(upload_id),
            str(r.NR_WO),
            r.DT_HR_INSPECAO.isoformat(sep=" ", timespec="seconds"),
            float(r.C_DPU_QG_AMARELO),
            r.CD_POSTO_CN,
            r.FALHA_PARETO,
        ))
    conn.executemany(
        "INSERT INTO dados (upload_id, nr_wo, dt, dpu, posto, falha) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def delete_period(conn, posto, year, start_date, end_date):
    conn.execute(
        "DELETE FROM dados WHERE posto=? AND strftime('%Y', dt)=? AND datetime(dt) BETWEEN datetime(?) AND datetime(?)",
        (
            posto,
            str(year),
            datetime.combine(start_date, time(0, 0, 0)).isoformat(sep=" "),
            datetime.combine(end_date, time(23, 59, 59)).isoformat(sep=" "),
        ),
    )
    conn.commit()


def delete_year(conn, posto, year):
    conn.execute("DELETE FROM dados WHERE posto=? AND strftime('%Y', dt)=?", (posto, str(year)))
    conn.commit()


def years_available(conn, posto=None):
    if posto:
        df = pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y', dt) AS INT) AS ano FROM dados WHERE posto=? ORDER BY ano", conn, params=[posto])
    else:
        df = pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y', dt) AS INT) AS ano FROM dados WHERE posto IN ('QG09','QG07') ORDER BY ano", conn)
    return [int(x) for x in df["ano"].dropna().tolist()] if not df.empty else []


def load_data(conn, posto=None, ano=None):
    q = "SELECT nr_wo, dt, dpu, posto, COALESCE(falha,'') AS falha FROM dados WHERE posto IN ('QG09','QG07')"
    params = []
    if posto:
        q += " AND posto=?"
        params.append(posto)
    if ano:
        q += " AND strftime('%Y', dt)=?"
        params.append(str(ano))
    df = pd.read_sql_query(q, conn, params=params)
    if not df.empty:
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
        df["dpu"] = pd.to_numeric(df["dpu"], errors="coerce").fillna(0)
        df["falha"] = df["falha"].fillna("").astype(str).str.strip()
        df = df[df["dt"].notna()].copy()
    return df

# -------------------- Leitura e mapeamento --------------------
def clean_cols(df):
    out = df.copy()
    out.columns = [str(c).strip().replace("\ufeff", "") for c in out.columns]
    return out


def read_file(uploaded):
    ext = uploaded.name.lower().split(".")[-1]
    content = uploaded.getvalue()
    if ext in ["xlsx", "xls"]:
        return clean_cols(pd.read_excel(io.BytesIO(content), engine="openpyxl" if ext == "xlsx" else "xlrd"))
    if ext == "csv":
        last = None
        for enc in ["utf-8-sig", "latin1", "utf-16"]:
            for sep in [None, ";", ",", "\t"]:
                try:
                    if sep is None:
                        return clean_cols(pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine="python"))
                    return clean_cols(pd.read_csv(io.BytesIO(content), encoding=enc, sep=sep))
                except Exception as e:
                    last = e
        raise ValueError(last)
    raise ValueError("Use .xlsx, .xls ou .csv")


def find_default_col(cols, canonical):
    upper_map = {str(c).strip().upper(): c for c in cols}
    for alias in ALIASES.get(canonical, []):
        if alias.upper() in upper_map:
            return upper_map[alias.upper()]
    return None


def detect_falha_col(df):
    m = {str(c).strip().upper(): c for c in df.columns}
    for c in FALHA_CANDIDATES:
        if c.upper() in m:
            return m[c.upper()]
    for c in df.columns:
        u = str(c).upper()
        if "FALHA" in u or "DEFEITO" in u:
            return c
    return None


def norm_posto(v):
    t = str(v).upper().strip()
    if "QG09" in t:
        return "QG09"
    if "QG07" in t:
        return "QG07"
    return t


def parse_dt(s):
    dt = pd.to_datetime(s, errors="coerce")
    mask = dt.isna() & s.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(s[mask], errors="coerce", dayfirst=True)
    return dt


def prepare_with_mapping(raw, mapping, falha_col=None):
    out = pd.DataFrame()
    out["NR_WO"] = raw[mapping["NR_WO"]].astype(str).str.strip()
    out["DT_HR_INSPECAO"] = parse_dt(raw[mapping["DT_HR_INSPECAO"]])
    out["C_DPU_QG_AMARELO"] = pd.to_numeric(raw[mapping["C_DPU_QG_AMARELO"]], errors="coerce").fillna(0)
    out["CD_POSTO_CN"] = raw[mapping["CD_POSTO_CN"]].astype(str).map(norm_posto)
    out["FALHA_PARETO"] = raw[falha_col].fillna("").astype(str).str.strip() if falha_col else ""
    out = out[out["CD_POSTO_CN"].isin(POSTOS) & out["DT_HR_INSPECAO"].notna()].copy()
    return out

# -------------------- Métricas --------------------
def calc_rft(df, ini, fim):
    if df.empty:
        return None, 0, 0, 0
    f = df[(df["dt"].dt.date >= ini) & (df["dt"].dt.date <= fim)].copy()
    if f.empty:
        return None, 0, 0, 0
    g = f.groupby("nr_wo", as_index=False)["dpu"].sum()
    total = int(len(g))
    good = int((g["dpu"] == 0).sum())
    bad = total - good
    pct = round(good / total * 100, 2) if total else None
    return pct, total, good, bad


def fmt_pct(v):
    return "Sem dados" if v is None or pd.isna(v) else f"{v:.2f}%".replace(".", ",")


def week_options(df):
    dates = sorted(df["dt"].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    return [(f"Semana {i:02d} - {m.strftime('%d/%m/%Y')} a {(m + timedelta(days=6)).strftime('%d/%m/%Y')}", m, m + timedelta(days=6)) for i, m in enumerate(mondays, 1)]


def month_options(df, ano):
    opts = []
    for m in sorted(df["dt"].dt.month.unique().tolist()):
        s = date(ano, int(m), 1)
        e = date(ano, int(m), monthrange(ano, int(m))[1])
        opts.append((f"{s.strftime('%m/%Y')} - {s.strftime('%d/%m/%Y')} a {e.strftime('%d/%m/%Y')}", s, e))
    return opts


def annual_end(df, ano):
    max_d = df["dt"].dt.date.max()
    if max_d >= date(ano, 12, YEAR_CLOSE_DAY):
        return max_d
    return None

# -------------------- Pareto --------------------
def pareto(df):
    f = df[df["falha"].fillna("").astype(str).str.strip() != ""].copy()
    if f.empty:
        return pd.DataFrame(columns=["Rank", "Falha", "Quantidade", "%", "% Acumulado"])
    p = f["falha"].value_counts(sort=True, ascending=False).head(10).reset_index()
    p.columns = ["Falha", "Quantidade"]
    total = p["Quantidade"].sum()
    p["%"] = (p["Quantidade"] / total * 100).round(2)
    p["% Acumulado"] = p["%"].cumsum().round(2)
    p.insert(0, "Rank", range(1, len(p) + 1))
    return p


def plot_pareto(p, posto, ano, ini, fim):
    if p.empty:
        st.info("Sem falhas no período selecionado.")
        return
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=p["Falha"], y=p["Quantidade"], name="Quantidade", text=p["Quantidade"], textposition="outside", marker_color="#2f62b3"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=p["Falha"], y=p["% Acumulado"], name="% Acumulado", mode="lines+markers+text", text=[f"{v:.0f}%" for v in p["% Acumulado"]], textposition="top center", line=dict(color="#f97316", width=3), marker=dict(size=8)),
        secondary_y=True,
    )
    fig.add_hline(y=80, line_dash="dash", line_color="#ef4444", annotation_text="80%", annotation_position="top right", secondary_y=True)
    fig.update_yaxes(title_text="Quantidade", secondary_y=False, range=[0, max(float(p["Quantidade"].max()) * 1.25, 1)])
    fig.update_yaxes(title_text="% Acumulado", ticksuffix="%", secondary_y=True, range=[0, 105])
    fig.update_xaxes(tickangle=-45, title_text="Falha")
    fig.update_layout(
        title=dict(text=f"Pareto de Falhas - Top 10 | {posto} | {ano} | {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}", x=.5),
        height=650,
        margin=dict(l=65, r=65, t=85, b=185),
        legend=dict(orientation="h", y=-.35, x=.5, xanchor="center"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#111827"),
        bargap=.35,
    )
    st.plotly_chart(fig, use_container_width=True)

# -------------------- App --------------------
con = get_conn()
init_db(con)

st.markdown('<div class="hero"><div style="font-size:1.75rem;font-weight:900;">RFT Automático - V9.9.6</div><div class="small">Correção do upload com mapeamento de colunas + retorno do Diário/Semanal/Mensal/Anual com calendário.</div></div>', unsafe_allow_html=True)

tabs = st.tabs(["Dashboard", "Pareto de Falhas", "Base & Upload", "Histórico", "Sobre"])
anos_global = years_available(con)

with st.sidebar:
    posto = st.radio("Posto", POSTOS, horizontal=True)
    anos_posto = years_available(con, posto)
    ano = st.selectbox("Ano", anos_posto if anos_posto else [date.today().year], index=len(anos_posto)-1 if anos_posto else 0)
    modo = st.radio("Modo", ["Diário", "Semanal", "Mensal", "Anual"], index=0)
    meta = st.number_input("Meta RFT (%)", 0.0, 100.0, 95.0, 0.1)

with tabs[0]:
    st.subheader("Dashboard")
    df = load_data(con, posto, ano) if anos_posto else pd.DataFrame()
    if df.empty:
        st.info("Sem dados para o posto/ano selecionado.")
    else:
        min_d = df["dt"].dt.date.min()
        max_d = df["dt"].dt.date.max()
        st.caption(f"Janela consolidada: {min_d.strftime('%d/%m/%Y')} até {max_d.strftime('%d/%m/%Y')}")
        selected_label = f"Ano {ano}"
        if modo == "Diário":
            dia = st.date_input("Calendário - Dia", value=max_d, min_value=min_d, max_value=max_d, format="DD/MM/YYYY")
            day_start = day_end = dia
            selected_label = dia.strftime("%d/%m/%Y")
        elif modo == "Semanal":
            opts = week_options(df)
            labels = [x[0] for x in opts]
            label = st.selectbox("Semana", labels, index=len(labels)-1)
            _, day_start, day_end = opts[labels.index(label)]
            selected_label = label
        elif modo == "Mensal":
            opts = month_options(df, ano)
            labels = [x[0] for x in opts]
            label = st.selectbox("Mês", labels, index=len(labels)-1)
            _, day_start, day_end = opts[labels.index(label)]
            selected_label = label
        else:
            day_start = date(ano, 1, 1)
            end_annual = annual_end(df, ano)
            day_end = end_annual if end_annual is not None else max_d
            selected_label = f"Anual até {day_end.strftime('%d/%m/%Y')}" if end_annual else "Anual ainda não fechado"

        daily = calc_rft(df, max_d, max_d)
        if modo == "Diário":
            ws = day_start - timedelta(days=day_start.weekday())
            we = ws + timedelta(days=6)
            weekly = calc_rft(df, ws, we)
            monthly = calc_rft(df, date(ano, day_start.month, 1), date(ano, day_start.month, monthrange(ano, day_start.month)[1]))
        else:
            weekly = calc_rft(df, day_start, day_end)
            monthly = calc_rft(df, day_start, day_end)
        annual_end_date = annual_end(df, ano)
        annual = calc_rft(df, date(ano,1,1), annual_end_date) if annual_end_date else (None, 0, 0, 0)
        ytd = calc_rft(df, date(ano,1,1), day_end)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("RFT Diário", fmt_pct(daily[0]), f"Total: {daily[1]}")
        c2.metric("RFT Semanal", fmt_pct(weekly[0]), f"Total: {weekly[1]}")
        c3.metric("RFT Mensal", fmt_pct(monthly[0]), f"Total: {monthly[1]}")
        c4.metric("RFT Anual", fmt_pct(annual[0]), f"Total: {annual[1]}")
        c5.metric("RFT YTD", fmt_pct(ytd[0]), f"Total: {ytd[1]}")
        st.info(f"Recorte selecionado: {selected_label}")

with tabs[1]:
    st.subheader("Pareto de Falhas")
    anos = years_available(con)
    if not anos:
        st.info("Faça upload de uma base com falhas/defeitos para gerar o Pareto.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            p_ano = st.selectbox("Ano do Pareto", anos, index=len(anos)-1)
        with c2:
            p_posto = st.radio("Posto do Pareto", POSTOS, horizontal=True)
        dfp = load_data(con, p_posto, p_ano)
        dfp = dfp[dfp["falha"].fillna("").astype(str).str.strip() != ""] if not dfp.empty else dfp
        if dfp.empty:
            st.info("Sem falhas preenchidas para o posto/ano selecionado.")
        else:
            min_d = dfp["dt"].dt.date.min()
            max_d = dfp["dt"].dt.date.max()
            d1, d2 = st.columns(2)
            with d1:
                data_ini = st.date_input("Data inicial", value=min_d, min_value=min_d, max_value=max_d, format="DD/MM/YYYY")
            with d2:
                data_fim = st.date_input("Data final", value=max_d, min_value=min_d, max_value=max_d, format="DD/MM/YYYY")
            if data_ini > data_fim:
                st.error("A data inicial não pode ser maior que a data final.")
            else:
                filt = dfp[(dfp["dt"].dt.date >= data_ini) & (dfp["dt"].dt.date <= data_fim)].copy()
                p = pareto(filt)
                plot_pareto(p, p_posto, p_ano, data_ini, data_fim)
                if not p.empty:
                    show = p.copy()
                    show["%"] = show["%"].map(lambda x: f"{x:.2f}%".replace(".", ","))
                    show["% Acumulado"] = show["% Acumulado"].map(lambda x: f"{x:.2f}%".replace(".", ","))
                    st.dataframe(show, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Base & Upload")
    st.warning("Agora você pode mapear as colunas da sua planilha. Não precisa que elas tenham exatamente os nomes NR_WO, DT_HR_INSPECAO, C_DPU_QG_AMARELO e CD_POSTO_CN.")
    modo_imp = st.radio("Modo de importação", ["Somar ao histórico", "Substituir período sobreposto", "Reprocessar o ano inteiro"], horizontal=True)
    up = st.file_uploader("Base operacional (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"])
    prepared = None
    if up is not None:
        try:
            raw = read_file(up)
            cols = list(raw.columns)
            st.write("Prévia das colunas encontradas:", cols)
            mapping = {}
            map_cols = st.columns(4)
            for i, canonical in enumerate(CANON):
                default_col = find_default_col(cols, canonical)
                default_index = cols.index(default_col) if default_col in cols else 0
                with map_cols[i]:
                    mapping[canonical] = st.selectbox(f"Coluna para {canonical}", cols, index=default_index, key=f"map_{canonical}")
            auto = detect_falha_col(raw)
            falha_opts = ["Sem coluna de falha"] + cols
            falha_index = falha_opts.index(auto) if auto in falha_opts else 0
            falha_choice = st.selectbox("Coluna para Pareto de Falhas", falha_opts, index=falha_index)
            falha_col = None if falha_choice == "Sem coluna de falha" else falha_choice
            prepared = prepare_with_mapping(raw, mapping, falha_col)
            st.success(f"Arquivo carregado: {up.name} | Linhas válidas QG09/QG07: {len(prepared)}")
            if falha_col:
                st.info(f"Coluna de falha usada: {falha_col}")
            else:
                st.warning("Nenhuma coluna de falha selecionada. O RFT será salvo, mas o Pareto ficará vazio.")
            preview = prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year, "CD_POSTO_CN"]).agg(
                Linhas=("NR_WO", "count"),
                Falhas_preenchidas=("FALHA_PARETO", lambda s: (s != "").sum()),
                Data_min=("DT_HR_INSPECAO", "min"),
                Data_max=("DT_HR_INSPECAO", "max"),
            ).reset_index()
            st.dataframe(preview, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}")
    if st.button("Salvar arquivo localmente", type="primary", use_container_width=True):
        if up is None or prepared is None or prepared.empty:
            st.error("Selecione e carregue uma base válida antes de salvar.")
        else:
            if modo_imp == "Substituir período sobreposto":
                for (yr, pst), part in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year, "CD_POSTO_CN"]):
                    delete_period(con, pst, int(yr), part["DT_HR_INSPECAO"].dt.date.min(), part["DT_HR_INSPECAO"].dt.date.max())
            elif modo_imp == "Reprocessar o ano inteiro":
                for (yr, pst), _ in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year, "CD_POSTO_CN"]):
                    delete_year(con, pst, int(yr))
            uid = create_upload(con, up.name, len(prepared), message="Upload V9.9.6")
            insert_rows(con, uid, prepared)
            st.success("Arquivo salvo com sucesso.")
            st.rerun()

with tabs[3]:
    st.subheader("Histórico")
    h = uploads_table(con)
    if h.empty:
        st.info("Sem uploads salvos.")
    else:
        st.dataframe(h, use_container_width=True, hide_index=True)

with tabs[4]:
    st.subheader("Sobre")
    st.write("V9.9.6: corrigido mapeamento de colunas no upload, restaurados modos Diário/Semanal/Mensal/Anual com calendário e mantido Pareto clássico com Plotly.")
