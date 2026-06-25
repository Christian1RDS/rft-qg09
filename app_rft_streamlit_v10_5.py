
import io, sqlite3, html, re
from datetime import datetime, date, time, timedelta
from calendar import monthrange
import pandas as pd
import streamlit as st

st.set_page_config(page_title="RFT Automático - V10.5", page_icon="R", layout="wide")
DB="rft_v105_local.db"
POSTOS=["QG09","QG07"]
CANON=["NR_WO","DT_HR_INSPECAO","C_DPU_QG_AMARELO","CD_POSTO_CN"]
ALIASES={
 "NR_WO":["NR_WO","WO","ORDEM","OP"],
 "DT_HR_INSPECAO":["DT_HR_INSPECAO","DATA","DATA_INSPECAO","DATA_HORA","DT_HR"],
 "C_DPU_QG_AMARELO":["C_DPU_QG_AMARELO","DPU","QTD_DEFEITO","QTD_DEFEITOS","QUANTIDADE","QTD"],
 "CD_POSTO_CN":["CD_POSTO_CN","POSTO","ESTACAO","ESTAÇÃO","CD_POSTO"],
 "CD_MODELO":["CD_MODELO","MODELO","MODEL","PRODUTO"]
}
FALHA_CAND=["ANOMALIA_FALHA","FALHA","DEFEITO","DS_DEFEITO","NM_DEFEITO","TIPO_FALHA","DESCRICAO_DEFEITO","DESC_DEFEITO","DS_FALHA","NM_FALHA","CAUSA","PROBLEMA"]
DEFECT_MARKERS=["TRASEIRA","DIANTEIRA","LATERAL","SUPERIOR","INFERIOR","SOLDA","PEÇA","PECA","FALTA","ACABAMENTO","RESPINGO","FURO","RISCADO","AMASSADO","MONTAGEM","PINTURA","QUEBRADO","DANIFICADO","FORA"]

st.markdown("""
<style>
:root{--line:rgba(148,163,184,.18);--txt:#e5e7eb;--muted:#94a3b8;--ok:#22c55e;--bad:#ef4444;}
html,body,[data-testid='stAppViewContainer'],.stApp{background:radial-gradient(circle at top left,#13213d 0%,#0b1220 38%,#09101c 100%);color:var(--txt);} [data-testid='stSidebar']{background:#0f172a;} [data-testid='stSidebar'] *{color:var(--txt)!important;}
h1,h2,h3,h4,h5,h6,p,label,div,span{color:var(--txt);} .hero{background:linear-gradient(135deg,rgba(24,34,53,.97),rgba(16,24,40,.98));border:1px solid var(--line);border-radius:22px;padding:1rem 1.25rem;margin-bottom:1rem;box-shadow:0 12px 36px rgba(0,0,0,.24);} .panel{background:linear-gradient(180deg,rgba(34,48,73,.96),rgba(21,31,47,.98));border:1px solid var(--line);border-radius:18px;padding:1rem;box-shadow:0 10px 30px rgba(0,0,0,.18);margin-bottom:1rem;} .kv{display:flex;justify-content:space-between;gap:1rem;padding:.55rem .7rem;border-radius:12px;background:rgba(255,255,255,.035);border:1px solid rgba(148,163,184,.10);margin-bottom:.45rem;} .small{color:var(--muted);font-size:.86rem;} .ok{color:var(--ok);} .bad{color:var(--bad);} .neutral{color:var(--txt);}
.metric-card{background:linear-gradient(180deg,rgba(36,50,74,.96),rgba(25,36,54,.98));border:1px solid var(--line);border-radius:18px;padding:1rem;min-height:128px}.metric-title{font-size:.92rem;color:var(--muted);font-weight:700}.metric-value{font-size:2rem;font-weight:900;margin:.35rem 0}.metric-sub{font-size:.82rem;color:var(--muted)}
</style>
""", unsafe_allow_html=True)

# ---------- DB ----------
def con():
    c=sqlite3.connect(DB,check_same_thread=False)
    c.execute("CREATE TABLE IF NOT EXISTS uploads (id INTEGER PRIMARY KEY AUTOINCREMENT,file_name TEXT,uploaded_at TEXT,rows INTEGER,message TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS dados (id INTEGER PRIMARY KEY AUTOINCREMENT,upload_id INTEGER,nr_wo TEXT,dt TEXT,dpu REAL,posto TEXT,falha TEXT,modelo TEXT)")
    cols=[r[1] for r in c.execute("PRAGMA table_info(dados)").fetchall()]
    if "modelo" not in cols: c.execute("ALTER TABLE dados ADD COLUMN modelo TEXT")
    c.commit(); return c

def years(c,posto=None):
    if posto: df=pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y',dt) AS INT) ano FROM dados WHERE posto=? ORDER BY ano",c,params=[posto])
    else: df=pd.read_sql_query("SELECT DISTINCT CAST(strftime('%Y',dt) AS INT) ano FROM dados ORDER BY ano",c)
    return [int(x) for x in df['ano'].dropna().tolist()] if not df.empty else []

def load(c,posto=None,ano=None):
    q="SELECT nr_wo,dt,dpu,posto,COALESCE(falha,'') falha,COALESCE(modelo,'') modelo,upload_id FROM dados WHERE posto IN ('QG09','QG07')"; p=[]
    if posto: q+=" AND posto=?"; p.append(posto)
    if ano: q+=" AND strftime('%Y',dt)=?"; p.append(str(ano))
    df=pd.read_sql_query(q,c,params=p)
    if not df.empty:
        df['dt']=pd.to_datetime(df['dt'],errors='coerce')
        df['dpu']=pd.to_numeric(df['dpu'],errors='coerce').fillna(0)
        df['falha']=df['falha'].fillna('').astype(str).str.strip()
        df['modelo']=df['modelo'].fillna('').astype(str).str.strip()
        df=df[df['dt'].notna()].copy()
        # Campos calculados para Pareto V10.5
        parsed=df.apply(lambda r: parse_model_defect(r['falha'], r['modelo']), axis=1, result_type='expand')
        parsed.columns=['modelo_pareto','falha_principal']
        df=pd.concat([df,parsed],axis=1)
    return df

def uploads(c): return pd.read_sql_query("SELECT id,file_name,uploaded_at,rows,message FROM uploads ORDER BY id DESC",c)
def latest_upload_info(c,df=None):
    if df is not None and not df.empty and 'upload_id' in df.columns:
        out=pd.read_sql_query("SELECT id,file_name,uploaded_at,rows,message FROM uploads WHERE id=?",c,params=[int(df['upload_id'].max())])
    else: out=pd.read_sql_query("SELECT id,file_name,uploaded_at,rows,message FROM uploads ORDER BY id DESC LIMIT 1",c)
    return None if out.empty else out.iloc[0].to_dict()
def save_upload(c,name,df):
    cur=c.execute("INSERT INTO uploads (file_name,uploaded_at,rows,message) VALUES (?,?,?,?)",(name,datetime.now().isoformat(timespec='seconds'),len(df),'Upload V10.5'))
    uid=int(cur.lastrowid)
    rows=[(uid,str(r.NR_WO),r.DT_HR_INSPECAO.isoformat(sep=' ',timespec='seconds'),float(r.C_DPU_QG_AMARELO),r.CD_POSTO_CN,r.FALHA_PARETO,r.CD_MODELO) for r in df.itertuples(index=False)]
    c.executemany("INSERT INTO dados (upload_id,nr_wo,dt,dpu,posto,falha,modelo) VALUES (?,?,?,?,?,?,?)",rows); c.commit()
def delete_period(c,posto,ano,ini,fim): c.execute("DELETE FROM dados WHERE posto=? AND strftime('%Y',dt)=? AND datetime(dt) BETWEEN datetime(?) AND datetime(?)",(posto,str(ano),datetime.combine(ini,time(0,0)).isoformat(sep=' '),datetime.combine(fim,time(23,59,59)).isoformat(sep=' '))); c.commit()
def delete_year(c,posto,ano): c.execute("DELETE FROM dados WHERE posto=? AND strftime('%Y',dt)=?",(posto,str(ano))); c.commit()

# ---------- Parser Pareto V10.5 ----------
def norm_text(s):
    s=str(s or '').upper().strip()
    s=re.sub(r'\s+', ' ', s)
    s=s.replace(' – ', ' - ').replace('—','-')
    return s.strip(' -')

def remove_model_prefix(raw, model):
    raw=norm_text(raw); model=norm_text(model)
    if model and raw.startswith(model):
        return raw[len(model):].strip(' -'), model
    return raw, model

def find_marker_split(raw):
    # Retorna (modelo_estimado, falha) procurando primeiro marcador de defeito.
    raw=norm_text(raw)
    best=None
    for marker in DEFECT_MARKERS:
        m=re.search(r'\b'+re.escape(marker)+r'\b', raw)
        if m and (best is None or m.start()<best.start()):
            best=m
    if best and best.start()>0:
        model=raw[:best.start()].strip(' -')
        defect=raw[best.start():].strip(' -')
        return model, defect
    return '', raw

def compact_defect(defect):
    defect=norm_text(defect)
    # Remove prefixos comuns de separador duplicado, mantendo região + defeito quando existir.
    defect=re.sub(r'^[\-:]+\s*','',defect)
    return defect if defect else 'SEM FALHA INFORMADA'

def parse_model_defect(raw_falha, modelo_col=''):
    raw=norm_text(raw_falha); modelo=norm_text(modelo_col)
    if not raw:
        return (modelo if modelo else 'Sem modelo', '')
    stripped, model_from_col = remove_model_prefix(raw, modelo)
    if model_from_col and stripped and stripped != raw:
        return (model_from_col, compact_defect(stripped))
    model_guess, defect = find_marker_split(raw)
    final_model = modelo if modelo else (model_guess if model_guess else 'Sem modelo')
    return (final_model, compact_defect(defect))

# ---------- Upload ----------
def clean(df):
    d=df.copy(); d.columns=[str(x).replace('\ufeff','').replace('ÿþ','').replace('\x00','').strip() for x in d.columns]; return d
def sniff_sep(text):
    first=text.splitlines()[0] if text.splitlines() else text; counts={'\t':first.count('\t'),';':first.count(';'),',':first.count(',')}; sep=max(counts,key=counts.get); return sep if counts[sep]>0 else None
def bad_df(df): return len(df.columns)==1 and any(s in str(df.columns[0]) for s in ['\t',';',','])
def read_csv_robust(content):
    encs=[]
    if content[:2] in (b'\xff\xfe',b'\xfe\xff') or content[:200].count(b'\x00')>20: encs+=['utf-16','utf-16-le','utf-16-be']
    encs+=['utf-8-sig','latin1','utf-16']; last=None
    for enc in encs:
        try:
            text=content.decode(enc,errors='replace').replace('\ufeff','').replace('\x00',''); sep=sniff_sep(text); df=pd.read_csv(io.StringIO(text),sep=sep if sep else None,engine='python'); df=clean(df)
            if not bad_df(df): return df
        except Exception as e: last=e
    for enc in encs:
        for sep in ['\t',';',',',None]:
            try:
                df=pd.read_csv(io.BytesIO(content),encoding=enc,sep=sep,engine='python' if sep is None else None); df=clean(df)
                if not bad_df(df): return df
            except Exception as e: last=e
    raise ValueError(last)
def read_file(up):
    ext=up.name.lower().split('.')[-1]; b=up.getvalue()
    if ext in ['xlsx','xls']: return clean(pd.read_excel(io.BytesIO(b),engine='openpyxl' if ext=='xlsx' else 'xlrd'))
    if ext=='csv': return read_csv_robust(b)
    raise ValueError('Use .xlsx, .xls ou .csv')
def default_col(cols,canon):
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
        if 'FALHA' in u or 'DEFEITO' in u or 'ANOMALIA' in u: return c
    return None
def norm_posto(x):
    t=str(x).upper().strip()
    if 'QG09' in t: return 'QG09'
    if 'QG07' in t: return 'QG07'
    return t
def prep(raw,mapa,falha_col,modelo_col):
    out=pd.DataFrame(); out['NR_WO']=raw[mapa['NR_WO']].astype(str).str.strip(); out['DT_HR_INSPECAO']=pd.to_datetime(raw[mapa['DT_HR_INSPECAO']],errors='coerce')
    mask=out['DT_HR_INSPECAO'].isna() & raw[mapa['DT_HR_INSPECAO']].notna()
    if mask.any(): out.loc[mask,'DT_HR_INSPECAO']=pd.to_datetime(raw.loc[mask,mapa['DT_HR_INSPECAO']],errors='coerce',dayfirst=True)
    out['C_DPU_QG_AMARELO']=pd.to_numeric(raw[mapa['C_DPU_QG_AMARELO']],errors='coerce').fillna(0); out['CD_POSTO_CN']=raw[mapa['CD_POSTO_CN']].astype(str).map(norm_posto)
    out['FALHA_PARETO']=raw[falha_col].fillna('').astype(str).str.strip() if falha_col else ''
    out['CD_MODELO']=raw[modelo_col].fillna('').astype(str).str.strip() if modelo_col else ''
    return out[out['CD_POSTO_CN'].isin(POSTOS) & out['DT_HR_INSPECAO'].notna()].copy()

# ---------- Métricas ----------
def calc_rft(df,ini,fim):
    if df.empty: return None,0,0,0
    f=df[(df['dt'].dt.date>=ini)&(df['dt'].dt.date<=fim)]
    if f.empty: return None,0,0,0
    g=f.groupby('nr_wo',as_index=False)['dpu'].sum(); total=len(g); good=int((g['dpu']==0).sum()); bad=total-good
    return round(good/total*100,2), total, good, bad
def fmt(v): return 'Sem dados' if v is None or pd.isna(v) else f'{v:.2f}%'.replace('.',',')
def metric_card(title,val,total,meta):
    if val is None: css='neutral'; status='Sem dados'; diff='-'
    elif val>=meta: css='ok'; status='Acima/igual à meta'; diff=f'{val-meta:+.2f} p.p.'.replace('.',',')
    else: css='bad'; status='Abaixo da meta'; diff=f'{val-meta:+.2f} p.p.'.replace('.',',')
    st.markdown(f"<div class='metric-card'><div class='metric-title'>{title}</div><div class='metric-value {css}'>{fmt(val)}</div><div class='metric-sub'>Total: {total}<br>Meta: {str(meta).replace('.',',')}%<br>{status} | Dif.: {diff}</div></div>", unsafe_allow_html=True)
def week_opts(df):
    mons=sorted({d-timedelta(days=d.weekday()) for d in df['dt'].dt.date.unique()}); return [(f"Semana {i:02d} - {m.strftime('%d/%m/%Y')} a {(m+timedelta(days=6)).strftime('%d/%m/%Y')}",m,m+timedelta(days=6)) for i,m in enumerate(mons,1)]
def month_opts(df,ano):
    res=[]
    for m in sorted(df['dt'].dt.month.unique()):
        s=date(ano,int(m),1); e=date(ano,int(m),monthrange(ano,int(m))[1]); res.append((f"{s.strftime('%m/%Y')} - {s.strftime('%d/%m/%Y')} a {e.strftime('%d/%m/%Y')}",s,e))
    return res
def annual_end(df,ano): mx=df['dt'].dt.date.max(); return mx if mx>=date(ano,12,10) else None
def day_history(df): return pd.DataFrame([{'Dia':d.strftime('%d/%m/%Y'),'RFT':calc_rft(df,d,d)[0] or 0} for d in sorted(df['dt'].dt.date.unique())])
def monthly_trend(df,ano,meta):
    rows=[]
    for m in sorted(df['dt'].dt.month.unique()):
        s=date(ano,int(m),1); e=date(ano,int(m),monthrange(ano,int(m))[1]); rows.append({'Mês':s.strftime('%m/%Y'),'RFT':calc_rft(df,s,e)[0] or 0,'Meta':meta})
    return pd.DataFrame(rows)
def weekly_trend(df): return pd.DataFrame([{'Semana':lab.split(' - ')[0],'RFT':calc_rft(df,s,e)[0] or 0} for lab,s,e in week_opts(df)])

# ---------- Pareto V10.5 ----------
def pareto(df,top_n=10):
    f=df[df['falha_principal'].fillna('').astype(str).str.strip()!=''].copy()
    if f.empty: return pd.DataFrame(columns=['Rank','Falha principal','Quantidade','%','% Acumulado'])
    p=f['falha_principal'].value_counts(sort=True,ascending=False).head(int(top_n)).reset_index()
    p.columns=['Falha principal','Quantidade']; total=p['Quantidade'].sum(); p['%']=(p['Quantidade']/total*100).round(2); p['% Acumulado']=p['%'].cumsum().round(2); p.insert(0,'Rank',range(1,len(p)+1)); return p
def plot_svg(p,posto,ano,ini,fim):
    if p.empty: st.info('Sem falhas no período selecionado.'); return
    w,h=1120,660; left,right,top,bottom=75,75,70,185; pw,ph=w-left-right,h-top-bottom; maxq=max(float(p['Quantidade'].max()),1); n=len(p); slot=pw/n; bw=slot*.45
    def yq(v): return top+ph-(float(v)/maxq)*ph*.88
    def yp(v): return top+ph-(float(v)/100)*ph
    parts=[f"<div style='background:white;border-radius:12px;padding:12px;overflow-x:auto;'><svg width='100%' viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg'><rect width='{w}' height='{h}' fill='white'/><text x='{w/2}' y='30' text-anchor='middle' font-size='20' font-weight='700' fill='#111827'>Pareto de Falhas Principais | {posto} | {ano} | {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}</text>"]
    for pct in range(0,101,20): y=yp(pct); parts.append(f"<line x1='{left}' y1='{y:.1f}' x2='{w-right}' y2='{y:.1f}' stroke='#d1d5db'/><text x='{w-right+10}' y='{y+4:.1f}' font-size='13' fill='#111827'>{pct}%</text>")
    pts=[]
    for i,row in p.iterrows():
        x=left+slot*i+slot/2; yb=yq(row['Quantidade']); bh=top+ph-yb; lab=html.escape(str(row['Falha principal'])[:21]+'…' if len(str(row['Falha principal']))>22 else str(row['Falha principal']))
        parts.append(f"<rect x='{x-bw/2:.1f}' y='{yb:.1f}' width='{bw:.1f}' height='{bh:.1f}' fill='#2f62b3'/><text x='{x:.1f}' y='{yb-8:.1f}' font-size='13' fill='#111827' text-anchor='middle'>{int(row['Quantidade'])}</text><g transform='translate({x-5:.1f},{top+ph+22:.1f}) rotate(-45)'><text font-size='13' fill='#111827' text-anchor='end'>{lab}</text></g>")
        pts.append((x,yp(row['% Acumulado']),row['% Acumulado']))
    parts.append(f"<line x1='{left}' y1='{top}' x2='{left}' y2='{top+ph}' stroke='#111827'/><line x1='{left}' y1='{top+ph}' x2='{w-right}' y2='{top+ph}' stroke='#111827'/><line x1='{w-right}' y1='{top}' x2='{w-right}' y2='{top+ph}' stroke='#111827'/>")
    parts.append("<polyline points='"+" ".join([f"{x:.1f},{y:.1f}" for x,y,_ in pts])+"' fill='none' stroke='#111827' stroke-width='3'/>")
    for x,y,pct in pts: parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5' fill='#f97316'/><text x='{x+8:.1f}' y='{y-8:.1f}' font-size='13' fill='#111827'>{pct:.0f}%</text>")
    parts.append(f"<text x='25' y='{top+ph/2}' font-size='15' fill='#111827' transform='rotate(-90 25,{top+ph/2})' text-anchor='middle'>Quantidade</text><text x='{w-20}' y='{top+ph/2}' font-size='15' fill='#111827' transform='rotate(90 {w-20},{top+ph/2})' text-anchor='middle'>% Acumulado</text></svg></div>")
    st.markdown(''.join(parts), unsafe_allow_html=True)
def meta_panel(pct,meta):
    css='neutral' if pct is None else ('ok' if pct>=meta else 'bad'); val=fmt(pct); diff='Sem dados' if pct is None else f'{pct-meta:+.2f} p.p.'.replace('.',',')
    st.markdown(f"<div class='panel'><div style='font-size:1.08rem;font-weight:800;'>Meta x resultado</div><div class='small'>Regra visual aplicada conforme sua configuracao.</div><div class='{css}' style='font-size:2.15rem;font-weight:900;margin:.5rem 0;'>{val}</div><div class='small'>Meta: <b>{str(meta).replace('.', ',')}%</b><br>Diferenca: <b>{diff}</b><br>Regra: abaixo da meta = vermelho | acima ou igual a meta = verde</div></div>", unsafe_allow_html=True)
def resumo_panel(info,posto,ano,min_d,max_d,recorte,meta):
    file='-' if info is None else info.get('file_name','-'); up='-' if info is None else info.get('uploaded_at','-')
    rows=[('Recorte',recorte),('Ultimo arquivo salvo',file),('Ultimo upload',up),('Posto',posto),('Ano',str(ano)),('Janela consolidada',f"{min_d.strftime('%d/%m/%Y')} ate {max_d.strftime('%d/%m/%Y')}"),('Meta ativa',str(meta).replace('.',',')+'%')]
    body=''.join([f"<div class='kv'><div class='small'>{k}</div><div><b>{v}</b></div></div>" for k,v in rows])
    st.markdown(f"<div class='panel'><div style='font-size:1.08rem;font-weight:800;'>Resumo executivo do recorte</div>{body}</div>", unsafe_allow_html=True)

# ---------- App ----------
c=con(); st.markdown("<div class='hero'><div style='font-size:1.75rem;font-weight:900;'>RFT Automático - V10.5</div><div class='small'>Pareto por falha principal, sem misturar modelo; estratificação da falha escolhida por modelo.</div></div>", unsafe_allow_html=True)
tabs=st.tabs(['Dashboard','Tendência','Pareto de Falhas','Base & Upload','Histórico','Sobre'])
with st.sidebar:
    posto=st.radio('Posto',POSTOS,horizontal=True); anos_p=years(c,posto); ano=st.selectbox('Ano',anos_p if anos_p else [date.today().year],index=len(anos_p)-1 if anos_p else 0); modo=st.radio('Modo',['Diário','Semanal','Mensal','Anual']); meta=st.number_input('Meta RFT (%)',0.0,100.0,95.0,0.1)
with tabs[0]:
    st.subheader('Dashboard'); df=load(c,posto,ano) if anos_p else pd.DataFrame()
    if df.empty: st.info('Sem dados para o posto/ano selecionado.')
    else:
        mn,mx=df['dt'].dt.date.min(),df['dt'].dt.date.max()
        if modo=='Diário': start=end=st.date_input('Calendário - Dia',value=mx,min_value=mn,max_value=mx,format='DD/MM/YYYY'); recorte=start.strftime('%d/%m/%Y')
        elif modo=='Semanal': opts=week_opts(df); labs=[x[0] for x in opts]; ch=st.selectbox('Semana',labs,index=len(labs)-1); _,start,end=opts[labs.index(ch)]; recorte=ch
        elif modo=='Mensal': opts=month_opts(df,ano); labs=[x[0] for x in opts]; ch=st.selectbox('Mês',labs,index=len(labs)-1); _,start,end=opts[labs.index(ch)]; recorte=ch
        else: start=date(ano,1,1); ae=annual_end(df,ano); end=ae if ae else mx; recorte=f"Anual até {end.strftime('%d/%m/%Y')}" if ae else 'Anual ainda não fechado'
        daily=calc_rft(df,start,start) if modo=='Diário' else calc_rft(df,mx,mx)
        ws=start-timedelta(days=start.weekday()); we=ws+timedelta(days=6)
        weekly=calc_rft(df,ws,we) if modo=='Diário' else calc_rft(df,start,end)
        monthly=calc_rft(df,date(ano,start.month,1),date(ano,start.month,monthrange(ano,start.month)[1])) if modo=='Diário' else calc_rft(df,start,end)
        ae=annual_end(df,ano); annual=calc_rft(df,date(ano,1,1),ae) if ae else (None,0,0,0); ytd=calc_rft(df,date(ano,1,1),end)
        for col,(name,val) in zip(st.columns(5),[('RFT Diário',daily),('RFT Semanal',weekly),('RFT Mensal',monthly),('RFT Anual',annual),('RFT YTD',ytd)]):
            with col: metric_card(name,val[0],val[1],meta)
        left,right=st.columns([1.15,1.0])
        with left: resumo_panel(latest_upload_info(c,df),posto,ano,mn,mx,recorte,meta)
        with right: meta_panel(ytd[0],meta)
        st.markdown("<div class='panel'><div style='font-size:1.08rem;font-weight:800;'>Leitura diaria do RFT</div><div class='small'>Historico dia a dia dentro da base consolidada.</div>",unsafe_allow_html=True)
        hd=day_history(df)
        if not hd.empty: st.line_chart(hd.set_index('Dia'),use_container_width=True)
        st.markdown('</div>',unsafe_allow_html=True)
with tabs[1]:
    st.subheader('Tendência'); df=load(c,posto,ano) if anos_p else pd.DataFrame()
    if df.empty: st.info('Sem dados para tendência.')
    else:
        a,b=st.columns(2)
        with a: mt=monthly_trend(df,ano,meta); st.markdown("<div class='panel'><b>Tendência mensal</b>",unsafe_allow_html=True); st.bar_chart(mt.set_index('Mês')[['RFT','Meta']],use_container_width=True); st.dataframe(mt,use_container_width=True,hide_index=True); st.markdown('</div>',unsafe_allow_html=True)
        with b: wt=weekly_trend(df); st.markdown("<div class='panel'><b>Tendência semanal</b>",unsafe_allow_html=True); st.bar_chart(wt.set_index('Semana'),use_container_width=True); st.dataframe(wt,use_container_width=True,hide_index=True); st.markdown('</div>',unsafe_allow_html=True)
with tabs[2]:
    st.subheader('Pareto de Falhas')
    anos=years(c)
    if not anos: st.info('Faça upload de uma base com falhas/defeitos para gerar o Pareto.')
    else:
        a,b,cx=st.columns(3)
        with a: p_ano=st.selectbox('Ano do Pareto',anos,index=len(anos)-1)
        with b: p_posto=st.radio('Posto do Pareto',POSTOS,horizontal=True)
        with cx: top_n=st.number_input('Quantidade do Top',min_value=1,max_value=30,value=10,step=1)
        dfp=load(c,p_posto,p_ano); dfp=dfp[dfp['falha_principal'].fillna('').astype(str).str.strip()!=''] if not dfp.empty else dfp
        if dfp.empty: st.info('Sem falhas preenchidas para o posto/ano selecionado.')
        else:
            mn,mx=dfp['dt'].dt.date.min(),dfp['dt'].dt.date.max(); d1,d2=st.columns(2)
            with d1: ini=st.date_input('Data inicial',value=mn,min_value=mn,max_value=mx,format='DD/MM/YYYY')
            with d2: fim=st.date_input('Data final',value=mx,min_value=mn,max_value=mx,format='DD/MM/YYYY')
            if ini>fim: st.error('A data inicial não pode ser maior que a data final.')
            else:
                filt=dfp[(dfp['dt'].dt.date>=ini)&(dfp['dt'].dt.date<=fim)].copy(); p=pareto(filt,top_n); plot_svg(p,p_posto,p_ano,ini,fim)
                if not p.empty:
                    show=p.copy(); show['%']=show['%'].map(lambda x:f'{x:.2f}%'.replace('.',',')); show['% Acumulado']=show['% Acumulado'].map(lambda x:f'{x:.2f}%'.replace('.',',')); st.dataframe(show,use_container_width=True,hide_index=True)
                    escolha=st.selectbox('Escolha uma falha principal do Top para estratificar por modelo', p['Falha principal'].tolist())
                    detalhe=filt[filt['falha_principal']==escolha].copy(); detalhe['modelo_pareto']=detalhe['modelo_pareto'].replace('', 'Sem modelo')
                    modelos=detalhe['modelo_pareto'].value_counts().head(30).reset_index(); modelos.columns=['Modelo','Quantidade']
                    st.markdown(f"### Estratificação por modelo — {escolha}")
                    if modelos.empty: st.info('Não há modelo preenchido/identificado para esta falha no período selecionado.')
                    else:
                        st.bar_chart(modelos.set_index('Modelo'),use_container_width=True)
                        st.dataframe(modelos,use_container_width=True,hide_index=True)
with tabs[3]:
    st.subheader('Base & Upload'); st.warning('Mapeie as colunas. CD_MODELO é opcional; se a falha vier como "modelo + falha", a V10.5 tenta separar automaticamente.')
    modo_imp=st.radio('Modo de importação',['Somar ao histórico','Substituir período sobreposto','Reprocessar o ano inteiro'],horizontal=True); up=st.file_uploader('Base operacional (.xlsx, .xls ou .csv)',type=['xlsx','xls','csv']); prepared=None
    if up is not None:
        try:
            raw=read_file(up); cols=list(raw.columns); st.write('Colunas detectadas:',cols); mapa={}; cc=st.columns(4)
            for i,canon in enumerate(CANON):
                dc=default_col(cols,canon); idx=cols.index(dc) if dc in cols else 0
                with cc[i]: mapa[canon]=st.selectbox(f'Coluna para {canon}',cols,index=idx,key=f'map_{canon}')
            auto=detect_falha(cols); fopts=['Sem coluna de falha']+cols; fidx=fopts.index(auto) if auto in fopts else 0; escolha=st.selectbox('Coluna para Pareto de Falhas',fopts,index=fidx); falha=None if escolha=='Sem coluna de falha' else escolha
            mc=default_col(cols,'CD_MODELO'); mopts=['Sem coluna de modelo']+cols; midx=mopts.index(mc) if mc in mopts else 0; modelo_choice=st.selectbox('Coluna para Modelo (opcional)',mopts,index=midx); modelo=None if modelo_choice=='Sem coluna de modelo' else modelo_choice
            prepared=prep(raw,mapa,falha,modelo); st.success(f'Arquivo carregado: {up.name} | Linhas válidas QG09/QG07: {len(prepared)}')
            if falha: st.info(f'Coluna de falha usada: {falha}')
            if modelo: st.info(f'Coluna de modelo usada: {modelo}')
            if not prepared.empty:
                prev=prepared.groupby([prepared['DT_HR_INSPECAO'].dt.year,'CD_POSTO_CN']).agg(Linhas=('NR_WO','count'),Falhas_preenchidas=('FALHA_PARETO',lambda s:(s!='').sum()),Modelos_preenchidos=('CD_MODELO',lambda s:(s!='').sum()),Data_min=('DT_HR_INSPECAO','min'),Data_max=('DT_HR_INSPECAO','max')).reset_index(); st.dataframe(prev,use_container_width=True,hide_index=True)
        except Exception as e: st.error(f'Erro ao processar arquivo: {e}')
    if st.button('Salvar arquivo localmente',type='primary',use_container_width=True):
        if up is None or prepared is None or prepared.empty: st.error('Selecione e carregue uma base válida antes de salvar.')
        else:
            if modo_imp=='Substituir período sobreposto':
                for (yr,pst),part in prepared.groupby([prepared['DT_HR_INSPECAO'].dt.year,'CD_POSTO_CN']): delete_period(c,pst,int(yr),part['DT_HR_INSPECAO'].dt.date.min(),part['DT_HR_INSPECAO'].dt.date.max())
            elif modo_imp=='Reprocessar o ano inteiro':
                for (yr,pst),_ in prepared.groupby([prepared['DT_HR_INSPECAO'].dt.year,'CD_POSTO_CN']): delete_year(c,pst,int(yr))
            save_upload(c,up.name,prepared); st.success('Arquivo salvo com sucesso.'); st.rerun()
with tabs[4]:
    st.subheader('Histórico'); h=uploads(c); st.info('Sem uploads salvos.') if h.empty else st.dataframe(h,use_container_width=True,hide_index=True)
with tabs[5]:
    st.subheader('Sobre'); st.write('V10.5: Pareto agrupado por falha principal, removendo o modelo do texto da falha quando necessário. Ao selecionar uma falha do Top, o app estratifica a contribuição por modelo.')
