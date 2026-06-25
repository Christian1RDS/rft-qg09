# RFT Automático - V10.5

Alteração principal no Pareto:
- O Pareto agora agrupa por **falha principal**, sem misturar o modelo no item do Top.
- Exemplo: `GLAZED FRAME G7 TRASEIRA PEÇA ACABAMENTO FORA DO ESPECIFICADO` entra como `TRASEIRA PEÇA ACABAMENTO FORA DO ESPECIFICADO`.
- Ao selecionar uma falha do Top, o app estratifica por modelo: `GLAZED FRAME G7`, `GLAZED FRAME VTBA`, `GLAZED FRAME V2 VT`, etc.

Mantém:
- Cards RFT com regra abaixo da meta = vermelho | acima ou igual = verde.
- Tendência mensal/semanal.
- Leitura diária do RFT.
- Upload robusto CSV UTF-16/tabulado.
- Sem Plotly/Matplotlib.

Deploy:
```text
app_rft_streamlit_v10_5.py
requirements.txt
```

Main file path:
```text
app_rft_streamlit_v10_5.py
```
