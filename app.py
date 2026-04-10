import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px  # Nova biblioteca para gráficos interativos
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Meu Dashboard Financeiro",
    page_icon="📊",
    layout="wide"
)

# --- CONFIGURAÇÃO DA CONEXÃO ---
NOME_DA_PLANILHA = "DashboardFinanceiroDB"
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

@st.cache_resource
def connect_to_gsheet():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Erro ao conectar com o Google Sheets: {e}")
        return None

# --- FUNÇÕES AUXILIARES ---
MAPA_MESES = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho', 
    7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}
MESES_ORDENADOS = list(MAPA_MESES.values())

def clean_valor(valor_str):
    s = str(valor_str).strip().replace('R$', '').replace(' ', '')
    if not s: return np.nan
    last_comma = s.rfind(',')
    last_dot = s.rfind('.')
    if last_comma > last_dot: s = s.replace('.', '').replace(',', '.')
    elif last_dot > last_comma: s = s.replace(',', '')
    elif last_comma != -1 and last_dot == -1: s = s.replace(',', '.')
    return pd.to_numeric(s, errors='coerce')

@st.cache_data(ttl=60)
def carregar_dados():
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            worksheet = spreadsheet.sheet1
            data = worksheet.get_all_values()
            if not data or len(data) < 2: return pd.DataFrame()
            df = pd.DataFrame(data[1:], columns=[h.strip() for h in data[0]])
            for col in ['ID', 'Ano', 'Valor']:
                if col in df.columns:
                    if col == 'Valor': df[col] = df[col].apply(clean_valor)
                    else: df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=['ID'], inplace=True)
            df['ID'] = df['ID'].astype(int)
            df['Mês'] = pd.Categorical(df['Mês'], categories=MESES_ORDENADOS, ordered=True)
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

def salvar_dados(df):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            worksheet = spreadsheet.sheet1
            df_para_salvar = df.copy()
            if 'Valor' in df_para_salvar.columns:
                 df_para_salvar['Valor'] = df_para_salvar['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ',') if pd.notna(x) else '')
            for col in df_para_salvar.columns: df_para_salvar[col] = df_para_salvar[col].astype(str)
            worksheet.clear()
            set_with_dataframe(worksheet, df_para_salvar, include_index=False, include_column_header=True, resize=True)
            st.cache_data.clear()
            return True
        except: return False
    return False

# --- GESTÃO DE CATEGORIAS ---
@st.cache_data(ttl=60)
def carregar_categorias():
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            ws = spreadsheet.worksheet("Categorias")
            lista = ws.col_values(1)[1:]
            return sorted([c for c in lista if c]) if lista else ["Geral"]
        except: return ["Entrada", "Transporte", "Saúde", "Moradia"]
    return []

def salvar_categoria_db(nova_cat):
    client = connect_to_gsheet()
    if client:
        try:
            ws = client.open(NOME_DA_PLANILHA).worksheet("Categorias")
            ws.append_row([nova_cat])
            st.cache_data.clear()
            return True
        except: return False
    return False

def excluir_categoria_db(cat_nome, cat_substituta):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            ws_dados = spreadsheet.sheet1
            dados = ws_dados.get_all_values()
            df_temp = pd.DataFrame(dados[1:], columns=dados[0])
            if 'Categoria' in df_temp.columns:
                df_temp['Categoria'] = df_temp['Categoria'].replace(cat_nome, cat_substituta)
                salvar_dados(df_temp)
            ws_cat = spreadsheet.worksheet("Categorias")
            celula = ws_cat.find(cat_nome)
            if celula: ws_cat.delete_rows(celula.row)
            st.cache_data.clear()
            return True
        except: return False
    return False

def editar_categoria_db(nome_antigo, nome_novo):
    client = connect_to_gsheet()
    if client:
        try:
            spreadsheet = client.open(NOME_DA_PLANILHA)
            ws_cat = spreadsheet.worksheet("Categorias")
            celula = ws_cat.find(nome_antigo)
            if celula: ws_cat.update_cell(celula.row, celula.col, nome_novo)
            ws_dados = spreadsheet.sheet1
            dados = ws_dados.get_all_values()
            df_temp = pd.DataFrame(dados[1:], columns=dados[0])
            if 'Categoria' in df_temp.columns:
                df_temp['Categoria'] = df_temp['Categoria'].replace(nome_antigo, nome_novo)
                salvar_dados(df_temp)
            return True
        except: return False
    return False

# --- PÁGINAS ---

def pagina_inicial():
    st.title("🏠 Página Inicial")
    st.subheader("Resumo do Mês Corrente")
    df = carregar_dados()
    if df.empty:
        st.warning("Base de dados vazia.")
        return

    df['Valor Fin.'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    hoje = datetime.now()
    mes_atual_nome = MAPA_MESES[hoje.month]
    df_mes = df[(df['Ano'] == hoje.year) & (df['Mês'] == mes_atual_nome)]

    if not df_mes.empty:
        receitas = df_mes[df_mes['Valor Fin.'] > 0]['Valor Fin.'].sum()
        despesas = df_mes[df_mes['Valor Fin.'] < 0]['Valor Fin.'].sum()
        saldo = receitas + despesas

        c1, c2, c3 = st.columns(3)
        c1.metric("🟢 Receitas Totais", f"R$ {receitas:,.2f}")
        c2.metric("🔴 Despesas Totais", f"R$ {despesas:,.2f}")
        c3.metric("💰 Saldo do Mês", f"R$ {saldo:,.2f}")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Últimos 5 Lançamentos do Mês")
        st.dataframe(df_mes.tail(5), hide_index=True)
    with col2:
        st.subheader("Faturas do Próximo Mês")
        prox_mes_num = hoje.month + 1 if hoje.month < 12 else 1
        prox_ano = hoje.year if hoje.month < 12 else hoje.year + 1
        cartoes = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
        df_fat = df[(df['Forma de Pagamento'].isin(cartoes)) & (df['Ano'] == prox_ano) & (df['Mês'] == MAPA_MESES[prox_mes_num])]
        if not df_fat.empty:
            res_fat = df_fat.groupby('Forma de Pagamento')['Valor'].sum().reset_index()
            st.dataframe(res_fat, hide_index=True)
        else: st.info("Sem faturas.")

    st.markdown("---")
    st.subheader("Distribuição de Despesas do Mês")
    despesas_df = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
    if not despesas_df.empty:
        fig = px.pie(despesas_df, values='Valor', names='Categoria', hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)

def pagina_adicionar():
    st.title("✍️ Adicionar Novo Lançamento")
    df_existente = carregar_dados()
    cats = carregar_categorias()
    proximo_id = int(df_existente['ID'].max() + 1) if not df_existente.empty else 1

    with st.form("novo_lancamento_form"):
        c1, c2, c3 = st.columns(3)
        data_l = c1.date_input("Data do Lançamento", datetime.now())
        tipo = c2.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        valor = c3.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        desc = st.text_input("Descrição")
        cat = st.selectbox("Categoria", cats)

        c1, c2 = st.columns(2)
        classif = c1.selectbox("Classificação", ['Essencial', 'Não Essencial', 'Extra'])
        metodo = c2.selectbox("Método de Pagamento", ['Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank', 'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix'])
        forma = c1.selectbox("Forma de Pagamento", ['À Vista', 'Parcelado'])
        pago = c2.selectbox("Já foi pago?", ['Sim', 'Não'])
        obs = st.text_area("Observações", "-")

        c1, c2 = st.columns(2)
        m_cont = c1.number_input("Mês Contábil", 1, 12, datetime.now().month)
        a_cont = c2.number_input("Ano Contábil", 2020, 2030, datetime.now().year)
        
        if forma == 'Parcelado':
            cp1, cp2, cp3 = st.columns(3)
            n_parc = cp1.number_input("Total Parcelas", 2, 60, 2)
            m_ini = cp2.number_input("Mês da 1ª", 1, 12, m_cont)
            a_ini = cp3.number_input("Ano da 1ª", 2020, 2030, a_cont)

        if st.form_submit_button("Adicionar Lançamento"):
            novos = []
            pago_str = 'OK' if pago == 'Sim' else 'NOK'
            if tipo != 'Despesa' or forma == 'À Vista':
                novos.append({'ID': proximo_id, 'Data': data_l.strftime('%d/%m/%Y'), 'Tipo': tipo, 'Descrição': desc, 'Valor': valor, 'Categoria': cat, 'Classificação': classif if tipo=='Despesa' else 'N/A', 'Pagamento': forma if tipo=='Despesa' else 'N/A', 'Forma de Pagamento': metodo if tipo=='Despesa' else 'N/A', 'Parcelas': 'N/A', 'Pagamento Realizado': pago_str, 'Observações': obs, 'Mês': MAPA_MESES[m_cont], 'Ano': a_cont})
            else:
                for i in range(n_parc):
                    m, a = m_ini + i, a_ini
                    while m > 12: m -= 12; a += 1
                    novos.append({'ID': proximo_id+i, 'Data': data_l.strftime('%d/%m/%Y'), 'Tipo': tipo, 'Descrição': f"{desc} ({i+1}/{n_parc})", 'Valor': valor/n_parc, 'Categoria': cat, 'Classificação': classif, 'Pagamento': forma, 'Forma de Pagamento': metodo, 'Parcelas': f"{i+1:02d} de {n_parc:02d}", 'Pagamento Realizado': pago_str, 'Observações': obs, 'Mês': MAPA_MESES[m], 'Ano': a})
            
            df_final = pd.concat([df_existente, pd.DataFrame(novos)], ignore_index=True)
            if salvar_dados(df_final): st.success("Adicionado!"); st.rerun()

def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")
    df = carregar_dados()
    id_input = st.number_input("ID do lançamento", min_value=1)
    if st.button("Buscar"):
        res = df[df['ID'] == id_input]
        if not res.empty:
            st.dataframe(res, hide_index=True)
            if st.button("Excluir"):
                df = df[df['ID'] != id_input]
                if salvar_dados(df): st.success("Excluído!"); st.rerun()

def pagina_relatorio():
    st.title("📊 Relatório Financeiro")
    c1, c2 = st.columns(2)
    ano = c1.number_input("Ano", 2020, 2030, datetime.now().year)
    mes = c2.selectbox("Mês", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month-1)
    if st.button("Gerar Relatório"):
        df = carregar_dados()
        df_r = df[(df['Ano'] == ano) & (df['Mês'] == MAPA_MESES[mes])]
        if not df_r.empty:
            cols = ['ID', 'Data', 'Descrição', 'Categoria', 'Forma de Pagamento', 'Parcelas', 'Valor', 'Observações']
            st.dataframe(df_r[cols], hide_index=True)
        else: st.warning("Sem dados.")

def pagina_faturas():
    st.title("💳 Ver Faturas")
    cartao = st.selectbox("Cartão", ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG'])
    c1, c2 = st.columns(2)
    ano = c1.number_input("Ano fatura", 2020, 2030, datetime.now().year)
    mes = c2.selectbox("Mês fatura", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month-1)
    if st.button("Ver Fatura"):
        df = carregar_dados()
        df_f = df[(df['Forma de Pagamento'] == cartao) & (df['Mês'] == MAPA_MESES[mes]) & (df['Ano'] == ano)]
        if not df_f.empty:
            st.metric(f"Total {cartao}", f"R$ {df_f['Valor'].sum():,.2f}")
            cols = ['ID', 'Data', 'Descrição', 'Categoria', 'Forma de Pagamento', 'Parcelas', 'Valor', 'Observações']
            st.dataframe(df_f[cols], hide_index=True)

def pagina_configuracoes():
    st.title("⚙️ Configurações de Categoria")
    cats = carregar_categorias()
    c1, c2, c3 = st.columns(3)
    with c1:
        n_cat = st.text_input("Nova Categoria")
        if st.button("Adicionar"):
            if n_cat and n_cat not in cats:
                if salvar_categoria_db(n_cat): st.success("Adicionada!"); st.rerun()
    with c2:
        ed_cat = st.selectbox("Editar Categoria", ["Selecione..."] + cats)
        novo_n = st.text_input("Novo Nome")
        if st.button("Atualizar"):
            if ed_cat != "Selecione..." and novo_n:
                if editar_categoria_db(ed_cat, novo_n): st.success("Atualizada!"); st.rerun()
    with c3:
        rm_cat = st.selectbox("Excluir Categoria", ["Selecione..."] + cats)
        cat_sub = st.selectbox("Substituir registros por", ["Selecione..."] + [c for c in cats if c != rm_cat])
        if st.button("Confirmar Exclusão"):
            if rm_cat != "Selecione..." and cat_sub != "Selecione...":
                if excluir_categoria_db(rm_cat, cat_sub): st.success("Excluída!"); st.rerun()

def pagina_graficos():
    st.title("🎨 Gráficos Analíticos Interativos")
    df = carregar_dados()
    if df.empty: return

    escolha = st.selectbox("Escolha o Gráfico", ["Selecione...", "Gastos por Categoria (Mensal)", "Gasto com Cartão (Mensal)", "Balanço (Anual)", "Faturas (Anual)"])
    
    if "Mensal" in escolha:
        c1, c2 = st.columns(2)
        ano = c1.number_input("Ano", 2020, 2030, datetime.now().year, key="ano_g")
        mes = c2.selectbox("Mês", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month-1)
        
        if st.button("Gerar Gráfico"):
            df_m = df[(df['Ano'] == ano) & (df['Mês'] == MAPA_MESES[mes])]
            if escolha == "Gastos por Categoria (Mensal)":
                res = df_m[df_m['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().reset_index()
                fig = px.pie(res, values='Valor', names='Categoria', hole=0.4, title=f"Gastos em {MAPA_MESES[mes]}/{ano}")
                st.plotly_chart(fig, use_container_width=True)
            elif escolha == "Gasto com Cartão (Mensal)":
                cart = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
                res = df_m[df_m['Forma de Pagamento'].isin(cart)].groupby('Forma de Pagamento')['Valor'].sum().reset_index()
                fig = px.bar(res, x='Forma de Pagamento', y='Valor', color='Forma de Pagamento', text_auto='.2f', title="Gastos por Cartão")
                st.plotly_chart(fig, use_container_width=True)

    elif "Anual" in escolha:
        ano = st.number_input("Ano", 2020, 2030, datetime.now().year, key="ano_a")
        if st.button("Gerar Gráfico Anual"):
            df_a = df[df['Ano'] == ano]
            if escolha == "Balanço (Anual)":
                res = df_a.groupby(['Mês', 'Tipo'])['Valor'].sum().reset_index()
                fig = px.bar(res, x='Mês', y='Valor', color='Tipo', barmode='group', title=f"Balanço de {ano}")
                st.plotly_chart(fig, use_container_width=True)
            elif escolha == "Faturas (Anual)":
                cart = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
                res = df_a[df_a['Forma de Pagamento'].isin(cart)].groupby(['Mês', 'Forma de Pagamento'])['Valor'].sum().reset_index()
                fig = px.line(res, x='Mês', y='Valor', color='Forma de Pagamento', markers=True, title="Evolução das Faturas")
                st.plotly_chart(fig, use_container_width=True)

# --- MENU ---
paginas = {
    "Página Inicial": pagina_inicial,
    "Adicionar Lançamento": pagina_adicionar,
    "Gerenciar Lançamento": pagina_gerenciar,
    "Relatório Mensal": pagina_relatorio,
    "Ver Faturas de Cartão": pagina_faturas,
    "Configurações de Categoria": pagina_configuracoes,
    "Gráficos Analíticos": pagina_graficos
}
escolha = st.sidebar.radio("Navegue:", list(paginas.keys()))
paginas[escolha]()
