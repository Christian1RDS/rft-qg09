
import io
import sqlite3
from datetime import datetime, date, time
from calendar import monthrange

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="RFT Automático - V9.9.5", page_icon="R", layout="wide")

DB = "rft_v995_local.db"
POSTOS = ["QG09", "QG07"]
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
FALHA_CANDIDATES = [
    "FALHA", "DEFEITO", "DS_DEFEITO", "NM_DEFEITO", "TIPO_FALHA", "DESCRICAO_DEFEITO",
    "DESCRIÇÃO_DEFEITO", "DESC_DEFEITO", "NOME_FALHA", "DS_FALHA", "NM_FALHA",
    "TIPO_DEFEITO", "CAUSA", "DESCRICAO", "DESCRIÇÃO", "OBS_DEFEITO", "PROBLEMA"
]

CSS = """
<style>
:root { --line:rgba(148,163,184,.18); --txt:#e5e7eb; --muted:#94a3b8; }
html, body, [data-testid="stAppViewContainer"], .stApp {
  background: radial-gradient(circle at top left, #13213d 0%, #0b1220 35%, #09101c 100%);
  color: var(--txt);
}
[data-testid="stHeader"] { background: rgba(11,18,32,.76); border-bottom: 1px solid var(--line); }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0f172a 0%, #101827 100%); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] * { color: var(--txt) !important; }
.block-container { padding-top: .8rem; padding-bottom: 2rem; }
h1,h2,h3,h4,h5,h6,p,label,div,span { color: var(--txt); }
.hero { background: linear-gradient(135deg, rgba(24,34,53,.97), rgba(16,24,40,.98)); border:1px solid var(--line); border-radius:22px; padding:1.15rem 1.25rem; box-shadow:0 12px 36px rgba(0,0,0,.24); margin-bottom:1rem; }
.panel { background: linear-gradient(180deg, rgba(34,48,73,.96), rgba(21,31,47,.98)); border:1px solid var(--line); border-radius:18px; padding:1rem; box-shadow:0 10px 30px rgba(0,0,0,.18); margin-bottom:1rem; }
.small { color: var(--muted); font-size:.86rem; }
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
    return pd.read_sql_query(
        "SELECT id, file_name, uploaded_at, rows, message FROM uploads ORDER BY id DESC",
        conn,
    )


def create_upload(conn, file_name, rows, message="Upload V9.9.5"):
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


def years_available(conn):
    df = pd.read_sql_query(
        "SELECT DISTINCT CAST(strftime('%Y', dt) AS INT) AS ano FROM dados WHERE posto IN ('QG09','QG07') ORDER BY ano",
        conn,
    )
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

# -------------------- Leitura e preparação --------------------
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


def norm_posto(v):
    t = str(v).upper().strip()
    if "QG09" in t:
        return "QG09"
    if "QG07" in t:
        return "QG07"
    return t


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


def parse_dt(s):
    dt = pd.to_datetime(s, errors="coerce")
    mask = dt.isna() & s.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(s[mask], errors="coerce", dayfirst=True)
    return dt


def prepare(df, falha_col=None):
    df = clean_cols(df)
    missing = [c for c in REQ if c not in df.columns]
    if missing:
        raise ValueError("Colunas obrigatórias ausentes: " + ", ".join(missing))
    out = df.copy()
    out["DT_HR_INSPECAO"] = parse_dt(out["DT_HR_INSPECAO"])
    out["C_DPU_QG_AMARELO"] = pd.to_numeric(out["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    out["NR_WO"] = out["NR_WO"].astype(str).str.strip()
    out["CD_POSTO_CN"] = out["CD_POSTO_CN"].astype(str).map(norm_posto)
    used_col = falha_col or detect_falha_col(out)
    out["FALHA_PARETO"] = out[used_col].fillna("").astype(str).str.strip() if used_col else ""
    out = out[out["CD_POSTO_CN"].isin(POSTOS) & out["DT_HR_INSPECAO"].notna()].copy()
    return out, used_col

# -------------------- Métricas e Pareto --------------------
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
        go.Bar(
            x=p["Falha"],
            y=p["Quantidade"],
            name="Quantidade",
            text=p["Quantidade"],
            textposition="outside",
            marker_color="#2f62b3",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=p["Falha"],
            y=p["% Acumulado"],
            name="% Acumulado",
            mode="lines+markers+text",
            text=[f"{v:.0f}%" for v in p["% Acumulado"]],
            textposition="top center",
            line=dict(color="#f97316", width=3),
            marker=dict(size=8),
        ),
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
st.title("RFT Automático - V9.9.5")
st.caption("Pareto clássico com Plotly: barras + curva acumulada, Top 10 ordenado e filtro de período.")

tabs = st.tabs(["Dashboard", "Pareto de Falhas", "Base & Upload", "Histórico", "Sobre"])
anos = years_available(con)

with st.sidebar:
    posto = st.radio("Posto", POSTOS, horizontal=True)
    ano = st.selectbox("Ano", anos if anos else [date.today().year], index=len(anos)-1 if anos else 0)
    meta = st.number_input("Meta RFT (%)", 0.0, 100.0, 95.0, 0.1)

with tabs[0]:
    st.subheader("Dashboard")
    df = load_data(con, posto, ano) if anos else pd.DataFrame()
    if df.empty:
        st.info("Sem dados para o posto/ano selecionado.")
    else:
        ini = df["dt"].dt.date.min()
        fim = df["dt"].dt.date.max()
        pct, total, good, bad = calc_rft(df, ini, fim)
        cols = st.columns(3)
        cols[0].metric("RFT YTD", "Sem dados" if pct is None else f"{pct:.2f}%".replace(".", ","), f"Total: {total}")
        cols[1].metric("WOs Boas", good)
        cols[2].metric("WOs Ruins", bad)
        st.caption(f"Janela consolidada: {ini.strftime('%d/%m/%Y')} até {fim.strftime('%d/%m/%Y')}")

with tabs[1]:
    st.subheader("Pareto de Falhas")
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
    modo = st.radio("Modo de importação", ["Somar ao histórico", "Substituir período sobreposto", "Reprocessar o ano inteiro"], horizontal=True)
    up = st.file_uploader("Base operacional (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"])
    prepared = None
    if up is not None:
        try:
            raw = read_file(up)
            auto = detect_falha_col(clean_cols(raw))
            opts = ["Detectar automaticamente / sem coluna"] + [c for c in clean_cols(raw).columns if c not in REQ]
            idx = opts.index(auto) if auto in opts else 0
            chosen = st.selectbox("Coluna para Pareto de Falhas", opts, index=idx)
            prepared, used = prepare(raw, None if chosen == opts[0] else chosen)
            st.success(f"Arquivo carregado: {up.name} | Linhas válidas QG09/QG07: {len(prepared)}")
            st.info(f"Coluna de falha usada: {used}" if used else "Nenhuma coluna de falha detectada/selecionada.")
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
            if modo == "Substituir período sobreposto":
                for (yr, pst), part in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year, "CD_POSTO_CN"]):
                    delete_period(con, pst, int(yr), part["DT_HR_INSPECAO"].dt.date.min(), part["DT_HR_INSPECAO"].dt.date.max())
            elif modo == "Reprocessar o ano inteiro":
                for (yr, pst), _ in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year, "CD_POSTO_CN"]):
                    delete_year(con, pst, int(yr))
            uid = create_upload(con, up.name, len(prepared), message="Upload V9.9.5")
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
    st.write("V9.9.5: Pareto clássico com Plotly, gráfico único, eixo duplo, Top 10, filtro de período e upload com coluna de falha.")
