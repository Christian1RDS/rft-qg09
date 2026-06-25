
import io, sqlite3, html
from datetime import datetime, date, time, timedelta
from calendar import monthrange
import pandas as pd
import streamlit as st

st.set_page_config(page_title="RFT Automático - V9.9.9", page_icon="R", layout="wide")
DB="rft_v999_local.db"
POSTOS=["QG09","QG07"]
CANON=["NR_WO","DT_HR_INSPECAO","C_DPU_QG_AMARELO","CD_POSTO_CN"]
ALIASES={
 "NR_WO":["NR_WO","WO","ORDEM","ORDEM_PRODUCAO","ORDEM DE PRODUCAO","OP"],
 "DT_HR_INSPECAO":["DT_HR_INSPECAO","DATA","DATA_INSPECAO","DATA INSPECAO","DATA_HORA","DT_HR"],
 "C_DPU_QG_AMARELO":["C_DPU_QG_AMARELO","DPU","QTD_DEFEITO","QTD_DEFEITOS","QUANTIDADE","QTD"],
 "CD_POSTO_CN":["CD_POSTO_CN","POSTO","ESTACAO","ESTAÇÃO","CD_POSTO","POSTO_CN"]
}
FALHA_CAND=["ANOMALIA_FALHA","FALHA","DEFEITO","DS_DEFEITO","NM_DEFEITO","TIPO_FALHA","DESCRICAO_DEFEITO","DESCRIÇÃO_DEFEITO","DESC_DEFEITO","DS_FALHA","NM_FALHA","CAUSA","PROBLEMA"]

st.markdown("""
<style>
html, body, [data-testid='stAppViewContainer'], .stApp {background: radial-gradient(circle at top left,#13213d 0%,#0b1220 38%,#09101c 100%); color:#e5e7eb;}
[data-testid='stSidebar'] {background:#0f172a;}
.hero {background:linear-gradient(135deg,rgba(24,34,53,.97),rgba(16,24,40,.98));border:1px solid rgba(148,163,184,.18);border-radius:22px;padding:1rem;margin-bottom:1rem;}
</style>
""", unsafe_allow_html=True)

# ---------------- Banco ----------------
def con():
    c=sqlite3.connect(DB, check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY AUTOINCREMENT,file_name TEXT,uploaded_at TEXT,rows INTEGER,message TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS dados (id INTEGER PRIMARY KEY AUTOINCREMENT,upload_id INTEGER,nr_wo TEXT,dt TEXT,dpu REAL,posto TEXT,falha TEXT)")
    c.commit(); return c

def years(c, posto=None):
    if posto:
        df=pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y',dt) AS INT) ano FROM dados WHERE posto=? ORDER BY ano", c, params=[posto])
    else:
        df=pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y',dt) AS INT) ano FROM dados ORDER BY ano", c)
    return [int(x) for x in df["ano"].dropna().tolist()] if not df.empty else []

def load(c, posto=None, ano=None):
    q="SELECT nr_wo,dt,dpu,posto,COALESCE(falha,'') falha FROM dados WHERE posto IN ('QG09','QG07')"; p=[]
    if posto: q+=" AND posto=?"; p.append(posto)
    if ano: q+=" AND strftime('%Y',dt)=?"; p.append(str(ano))
    df=pd.read_sql_query(q,c,params=p)
    if not df.empty:
        df["dt"]=pd.to_datetime(df["dt"],errors="coerce")
        df["dpu"]=pd.to_numeric(df["dpu"],errors="coerce").fillna(0)
        df["falha"]=df["falha"].fillna("").astype(str).str.strip()
        df=df[df["dt"].notna()].copy()
    return df

def uploads(c):
    return pd.read_sql_query("SELECT id,file_name,uploaded_at,rows,message FROM uploads ORDER BY id DESC", c)

def save_upload(c,name,df):
    cur=c.execute("INSERT INTO uploads (file_name,uploaded_at,rows,message) VALUES (?,?,?,?)",(name,datetime.now().isoformat(timespec="seconds"),len(df),"Upload V9.9.9"))
    uid=int(cur.lastrowid)
    rows=[(uid,str(r.NR_WO),r.DT_HR_INSPECAO.isoformat(sep=" ",timespec="seconds"),float(r.C_DPU_QG_AMARELO),r.CD_POSTO_CN,r.FALHA_PARETO) for r in df.itertuples(index=False)]
    c.executemany("INSERT INTO dados (upload_id,nr_wo,dt,dpu,posto,falha) VALUES (?,?,?,?,?,?)",rows); c.commit()

def delete_period(c,posto,ano,ini,fim):
    c.execute("DELETE FROM dados WHERE posto=? AND strftime('%Y',dt)=? AND datetime(dt) BETWEEN datetime(?) AND datetime(?)",(posto,str(ano),datetime.combine(ini,time(0,0)).isoformat(sep=" "),datetime.combine(fim,time(23,59,59)).isoformat(sep=" "))); c.commit()

def delete_year(c,posto,ano):
    c.execute("DELETE FROM dados WHERE posto=? AND strftime('%Y',dt)=?",(posto,str(ano))); c.commit()

# ---------------- Upload robusto ----------------
def clean(df):
    d=df.copy()
    fixed=[]
    for c in d.columns:
        s=str(c).replace("\ufeff","").replace("ÿþ","").replace("\x00","").strip()
        fixed.append(s)
    d.columns=fixed
    return d

def sniff_sep(text):
    first=text.splitlines()[0] if text.splitlines() else text
    counts={"\t":first.count("\t"),";":first.count(";"),",":first.count(",")}
    sep=max(counts, key=counts.get)
    return sep if counts[sep]>0 else None

def df_bad(df):
    return len(df.columns)==1 and any(x in str(df.columns[0]) for x in ["\t",";",","])

def read_csv_robust(content):
    encs=[]
    if content[:2] in (b"\xff\xfe", b"\xfe\xff") or content[:4] in (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff") or content[:200].count(b"\x00")>20:
        encs += ["utf-16","utf-16-le","utf-16-be"]
    encs += ["utf-8-sig","latin1","utf-16"]
    last=None
    for enc in encs:
        try:
            text=content.decode(enc, errors="replace")
            text=text.replace("\ufeff","").replace("\x00","")
            sep=sniff_sep(text)
            df=pd.read_csv(io.StringIO(text), sep=sep if sep else None, engine="python")
            df=clean(df)
            if not df_bad(df): return df
        except Exception as e: last=e
    # fallback brute force
    for enc in encs:
        for sep in ["\t",";",",",None]:
            try:
                df=pd.read_csv(io.BytesIO(content), encoding=enc, sep=sep, engine="python" if sep is None else None)
                df=clean(df)
                if not df_bad(df): return df
            except Exception as e: last=e
    raise ValueError(last)

def read_file(up):
    ext=up.name.lower().split(".")[-1]; b=up.getvalue()
    if ext in ["xlsx","xls"]: return clean(pd.read_excel(io.BytesIO(b), engine="openpyxl" if ext=="xlsx" else "xlrd"))
    if ext=="csv": return read_csv_robust(b)
    raise ValueError("Use .xlsx, .xls ou .csv")

def default_col(cols, canon):
    m={str(c).strip().upper():c for c in cols}
    for a in ALIASES.get(canon,[]):
        if a.upper() in m: return m[a.upper()]
    return cols[0] if cols else None

def detect_falha(cols):
    m={str(c).strip().upper():c for c in cols}
    for a in FALHA_CAND:
        if a.upper() in m: return m[a.upper()]
    for c in cols:
        u=str(c).upper()
        if "FALHA" in u or "DEFEITO" in u or "ANOMALIA" in u: return c
    return None

def norm_posto(x):
    t=str(x).upper().strip()
    if "QG09" in t: return "QG09"
    if "QG07" in t: return "QG07"
    return t

def prep(raw,mapa,falha_col):
    out=pd.DataFrame()
    out["NR_WO"]=raw[mapa["NR_WO"]].astype(str).str.strip()
    out["DT_HR_INSPECAO"]=pd.to_datetime(raw[mapa["DT_HR_INSPECAO"]],errors="coerce")
    mask=out["DT_HR_INSPECAO"].isna() & raw[mapa["DT_HR_INSPECAO"]].notna()
    if mask.any(): out.loc[mask,"DT_HR_INSPECAO"]=pd.to_datetime(raw.loc[mask,mapa["DT_HR_INSPECAO"]],errors="coerce",dayfirst=True)
    out["C_DPU_QG_AMARELO"]=pd.to_numeric(raw[mapa["C_DPU_QG_AMARELO"]],errors="coerce").fillna(0)
    out["CD_POSTO_CN"]=raw[mapa["CD_POSTO_CN"]].astype(str).map(norm_posto)
    out["FALHA_PARETO"]=raw[falha_col].fillna("").astype(str).str.strip() if falha_col else ""
    return out[out["CD_POSTO_CN"].isin(POSTOS) & out["DT_HR_INSPECAO"].notna()].copy()

# ---------------- Métricas/Pareto ----------------
def calc_rft(df,ini,fim):
    if df.empty: return None,0,0,0
    f=df[(df["dt"].dt.date>=ini)&(df["dt"].dt.date<=fim)]
    if f.empty: return None,0,0,0
    g=f.groupby("nr_wo",as_index=False)["dpu"].sum(); total=len(g); good=int((g["dpu"]==0).sum()); bad=total-good
    return round(good/total*100,2), total, good, bad

def fmt(v): return "Sem dados" if v is None or pd.isna(v) else f"{v:.2f}%".replace(".",",")

def week_opts(df):
    mons=sorted({d-timedelta(days=d.weekday()) for d in df["dt"].dt.date.unique()})
    return [(f"Semana {i:02d} - {m.strftime('%d/%m/%Y')} a {(m+timedelta(days=6)).strftime('%d/%m/%Y')}",m,m+timedelta(days=6)) for i,m in enumerate(mons,1)]

def month_opts(df,ano):
    res=[]
    for m in sorted(df["dt"].dt.month.unique()):
        s=date(ano,int(m),1); e=date(ano,int(m),monthrange(ano,int(m))[1]); res.append((f"{s.strftime('%m/%Y')} - {s.strftime('%d/%m/%Y')} a {e.strftime('%d/%m/%Y')}",s,e))
    return res

def annual_end(df,ano):
    mx=df["dt"].dt.date.max(); return mx if mx>=date(ano,12,10) else None

def pareto(df):
    f=df[df["falha"].fillna("").astype(str).str.strip()!=""].copy()
    if f.empty: return pd.DataFrame(columns=["Rank","Falha","Quantidade","%","% Acumulado"])
    p=f["falha"].value_counts(sort=True,ascending=False).head(10).reset_index(); p.columns=["Falha","Quantidade"]; total=p["Quantidade"].sum(); p["%"]=(p["Quantidade"]/total*100).round(2); p["% Acumulado"]=p["%"].cumsum().round(2); p.insert(0,"Rank",range(1,len(p)+1)); return p

def plot_svg(p,posto,ano,ini,fim):
    if p.empty: st.info("Sem falhas no período selecionado."); return
    w,h=1100,640; left,right,top,bottom=75,75,70,165; pw,ph=w-left-right,h-top-bottom; maxq=max(float(p["Quantidade"].max()),1); n=len(p); slot=pw/n; bw=slot*.45
    def yq(v): return top+ph-(float(v)/maxq)*ph*.88
    def yp(v): return top+ph-(float(v)/100)*ph
    parts=[f"<div style='background:white;border-radius:12px;padding:12px;overflow-x:auto;'><svg width='100%' viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg'><rect width='{w}' height='{h}' fill='white'/><text x='{w/2}' y='30' text-anchor='middle' font-size='20' font-weight='700' fill='#111827'>Pareto de Falhas - Top 10 | {posto} | {ano} | {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}</text>"]
    for pct in range(0,101,20):
        y=yp(pct); parts.append(f"<line x1='{left}' y1='{y:.1f}' x2='{w-right}' y2='{y:.1f}' stroke='#d1d5db'/><text x='{w-right+10}' y='{y+4:.1f}' font-size='13' fill='#111827'>{pct}%</text>")
    pts=[]
    for i,row in p.iterrows():
        x=left+slot*i+slot/2; yb=yq(row["Quantidade"]); bh=top+ph-yb; lab=html.escape(str(row["Falha"])[:21]+"…" if len(str(row["Falha"]))>22 else str(row["Falha"]))
        parts.append(f"<rect x='{x-bw/2:.1f}' y='{yb:.1f}' width='{bw:.1f}' height='{bh:.1f}' fill='#2f62b3'/><text x='{x:.1f}' y='{yb-8:.1f}' font-size='13' fill='#111827' text-anchor='middle'>{int(row['Quantidade'])}</text><g transform='translate({x-5:.1f},{top+ph+22:.1f}) rotate(-45)'><text font-size='13' fill='#111827' text-anchor='end'>{lab}</text></g>")
        pts.append((x,yp(row["% Acumulado"]),row["% Acumulado"]))
    parts.append(f"<line x1='{left}' y1='{top}' x2='{left}' y2='{top+ph}' stroke='#111827'/><line x1='{left}' y1='{top+ph}' x2='{w-right}' y2='{top+ph}' stroke='#111827'/><line x1='{w-right}' y1='{top}' x2='{w-right}' y2='{top+ph}' stroke='#111827'/>")
    parts.append("<polyline points='"+" ".join([f"{x:.1f},{y:.1f}" for x,y,_ in pts])+"' fill='none' stroke='#111827' stroke-width='3'/>")
    for x,y,pct in pts: parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5' fill='#f97316'/><text x='{x+8:.1f}' y='{y-8:.1f}' font-size='13' fill='#111827'>{pct:.0f}%</text>")
    parts.append(f"<text x='25' y='{top+ph/2}' font-size='15' fill='#111827' transform='rotate(-90 25,{top+ph/2})' text-anchor='middle'>Quantidade</text><text x='{w-20}' y='{top+ph/2}' font-size='15' fill='#111827' transform='rotate(90 {w-20},{top+ph/2})' text-anchor='middle'>% Acumulado</text></svg></div>")
    st.markdown("".join(parts), unsafe_allow_html=True)

# ---------------- App ----------------
c=con()
st.markdown("<div class='hero'><div style='font-size:1.75rem;font-weight:900;'>RFT Automático - V9.9.9</div><div class='small'>Correção robusta de CSV tabulado/UTF-16, sem Plotly/Matplotlib, Pareto em SVG e Dashboard completo.</div></div>", unsafe_allow_html=True)
tabs=st.tabs(["Dashboard","Pareto de Falhas","Base & Upload","Histórico","Sobre"])
with st.sidebar:
    posto=st.radio("Posto",POSTOS,horizontal=True); anos_p=years(c,posto); ano=st.selectbox("Ano",anos_p if anos_p else [date.today().year],index=len(anos_p)-1 if anos_p else 0); modo=st.radio("Modo",["Diário","Semanal","Mensal","Anual"]); meta=st.number_input("Meta RFT (%)",0.0,100.0,95.0,0.1)
with tabs[0]:
    st.subheader("Dashboard"); df=load(c,posto,ano) if anos_p else pd.DataFrame()
    if df.empty: st.info("Sem dados para o posto/ano selecionado.")
    else:
        mn,mx=df["dt"].dt.date.min(),df["dt"].dt.date.max(); st.caption(f"Janela consolidada: {mn.strftime('%d/%m/%Y')} até {mx.strftime('%d/%m/%Y')}")
        if modo=="Diário": start=end=st.date_input("Calendário - Dia",value=mx,min_value=mn,max_value=mx,format="DD/MM/YYYY"); label=start.strftime("%d/%m/%Y")
        elif modo=="Semanal": opts=week_opts(df); labs=[x[0] for x in opts]; ch=st.selectbox("Semana",labs,index=len(labs)-1); _,start,end=opts[labs.index(ch)]; label=ch
        elif modo=="Mensal": opts=month_opts(df,ano); labs=[x[0] for x in opts]; ch=st.selectbox("Mês",labs,index=len(labs)-1); _,start,end=opts[labs.index(ch)]; label=ch
        else: start=date(ano,1,1); ae=annual_end(df,ano); end=ae if ae else mx; label=f"Anual até {end.strftime('%d/%m/%Y')}" if ae else "Anual ainda não fechado"
        daily=calc_rft(df,mx,mx)
        if modo=="Diário": ws=start-timedelta(days=start.weekday()); we=ws+timedelta(days=6); weekly=calc_rft(df,ws,we); monthly=calc_rft(df,date(ano,start.month,1),date(ano,start.month,monthrange(ano,start.month)[1]))
        else: weekly=calc_rft(df,start,end); monthly=calc_rft(df,start,end)
        ae=annual_end(df,ano); annual=calc_rft(df,date(ano,1,1),ae) if ae else (None,0,0,0); ytd=calc_rft(df,date(ano,1,1),end)
        for col,(name,val) in zip(st.columns(5),[("RFT Diário",daily),("RFT Semanal",weekly),("RFT Mensal",monthly),("RFT Anual",annual),("RFT YTD",ytd)]): col.metric(name,fmt(val[0]),f"Total: {val[1]}")
        st.info(f"Recorte selecionado: {label}")
with tabs[1]:
    st.subheader("Pareto de Falhas"); anos=years(c)
    if not anos: st.info("Faça upload de uma base com falhas/defeitos para gerar o Pareto.")
    else:
        a,b=st.columns(2)
        with a: p_ano=st.selectbox("Ano do Pareto",anos,index=len(anos)-1)
        with b: p_posto=st.radio("Posto do Pareto",POSTOS,horizontal=True)
        dfp=load(c,p_posto,p_ano); dfp=dfp[dfp["falha"].fillna("").astype(str).str.strip()!=""] if not dfp.empty else dfp
        if dfp.empty: st.info("Sem falhas preenchidas para o posto/ano selecionado.")
        else:
            mn,mx=dfp["dt"].dt.date.min(),dfp["dt"].dt.date.max(); d1,d2=st.columns(2)
            with d1: ini=st.date_input("Data inicial",value=mn,min_value=mn,max_value=mx,format="DD/MM/YYYY")
            with d2: fim=st.date_input("Data final",value=mx,min_value=mn,max_value=mx,format="DD/MM/YYYY")
            if ini>fim: st.error("A data inicial não pode ser maior que a data final.")
            else:
                p=pareto(dfp[(dfp["dt"].dt.date>=ini)&(dfp["dt"].dt.date<=fim)].copy()); plot_svg(p,p_posto,p_ano,ini,fim)
                if not p.empty:
                    show=p.copy(); show["%"]=show["%"].map(lambda x:f"{x:.2f}%".replace(".",",")); show["% Acumulado"]=show["% Acumulado"].map(lambda x:f"{x:.2f}%".replace(".",",")); st.dataframe(show,use_container_width=True,hide_index=True)
with tabs[2]:
    st.subheader("Base & Upload"); st.warning("V9.9.9 corrige CSV com tabulação em uma única coluna e UTF-16/BOM. Mapeie as colunas abaixo.")
    modo_imp=st.radio("Modo de importação",["Somar ao histórico","Substituir período sobreposto","Reprocessar o ano inteiro"],horizontal=True); up=st.file_uploader("Base operacional (.xlsx, .xls ou .csv)",type=["xlsx","xls","csv"]); prepared=None
    if up is not None:
        try:
            raw=read_file(up); cols=list(raw.columns); st.write("Colunas detectadas:",cols); mapa={}; cc=st.columns(4)
            for i,canon in enumerate(CANON):
                dc=default_col(cols,canon); idx=cols.index(dc) if dc in cols else 0
                with cc[i]: mapa[canon]=st.selectbox(f"Coluna para {canon}",cols,index=idx,key=f"map_{canon}")
            auto=detect_falha(cols); fopts=["Sem coluna de falha"]+cols; fidx=fopts.index(auto) if auto in fopts else 0; escolha=st.selectbox("Coluna para Pareto de Falhas",fopts,index=fidx); falha=None if escolha=="Sem coluna de falha" else escolha
            prepared=prep(raw,mapa,falha); st.success(f"Arquivo carregado: {up.name} | Linhas válidas QG09/QG07: {len(prepared)}")
            if falha: st.info(f"Coluna de falha usada: {falha}")
            else: st.warning("Nenhuma coluna de falha selecionada. O RFT será salvo, mas o Pareto ficará vazio.")
            if not prepared.empty:
                prev=prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year,"CD_POSTO_CN"]).agg(Linhas=("NR_WO","count"),Falhas_preenchidas=("FALHA_PARETO",lambda s:(s!="").sum()),Data_min=("DT_HR_INSPECAO","min"),Data_max=("DT_HR_INSPECAO","max")).reset_index(); st.dataframe(prev,use_container_width=True,hide_index=True)
        except Exception as e: st.error(f"Erro ao processar arquivo: {e}")
    if st.button("Salvar arquivo localmente",type="primary",use_container_width=True):
        if up is None or prepared is None or prepared.empty: st.error("Selecione e carregue uma base válida antes de salvar.")
        else:
            if modo_imp=="Substituir período sobreposto":
                for (yr,pst),part in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year,"CD_POSTO_CN"]): delete_period(c,pst,int(yr),part["DT_HR_INSPECAO"].dt.date.min(),part["DT_HR_INSPECAO"].dt.date.max())
            elif modo_imp=="Reprocessar o ano inteiro":
                for (yr,pst),_ in prepared.groupby([prepared["DT_HR_INSPECAO"].dt.year,"CD_POSTO_CN"]): delete_year(c,pst,int(yr))
            save_upload(c,up.name,prepared); st.success("Arquivo salvo com sucesso."); st.rerun()
with tabs[3]:
    st.subheader("Histórico"); h=uploads(c); st.info("Sem uploads salvos.") if h.empty else st.dataframe(h,use_container_width=True,hide_index=True)
with tabs[4]:
    st.subheader("Sobre"); st.write("V9.9.9: corrige CSV tabulado/UTF-16 em coluna única, sem Plotly/Matplotlib, Pareto SVG, Dashboard Diário/Semanal/Mensal/Anual.")
