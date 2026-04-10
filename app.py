import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
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

# --- FUNÇÕES DE CATEGORIA (RESTAURADAS E MELHORADAS) ---
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

def excluir_categoria_db(cat_nome):
    client = connect_to_gsheet()
    if client:
        try:
            ws = client.open(NOME_DA_PLANILHA).worksheet("Categorias")
            celula = ws.find(cat_nome)
            if celula:
                ws.delete_rows(celula.row)
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

# --- PÁGINAS (RESTAURANDO O VISUAL DAS IMAGENS) ---

def pagina_inicial():
    st.title("🏠 Página Inicial")
    st.subheader("Resumo do Mês Corrente")
    df = carregar_dados()
    if df.empty:
        st.warning("Base vazia.")
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
        else:
            st.info("Nenhuma fatura para o próximo mês.")

    st.markdown("---")
    st.subheader("Distribuição de Despesas do Mês")
    despesas_df = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum()
    if not despesas_df.empty:
        fig, ax = plt.subplots(figsize=(10, 7))
        colors = plt.cm.tab20(np.linspace(0, 1, len(despesas_df)))
        wedges, texts = ax.pie(despesas_df, startangle=90, colors=colors, wedgeprops=dict(width=0.4))
        total = despesas_df.sum()
        legend_labels = [f'{label}: R$ {value:,.2f} ({value/total:.1%})' for label, value in despesas_df.items()]
        ax.legend(wedges, legend_labels, title="Categorias", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
        ax.axis('equal')
        st.pyplot(fig)

def pagina_adicionar():
    st.title("✍️ Adicionar Novo Lançamento")
    df_existente = carregar_dados()
    cats = carregar_categorias()
    proximo_id = int(df_existente['ID'].max() + 1) if not df_existente.empty else 1

    with st.form("novo_lancamento_form"):
        st.subheader("Detalhes do Lançamento")
        c1, c2, c3 = st.columns(3)
        data_l = c1.date_input("Data do Lançamento", datetime.now())
        tipo = c2.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        valor = c3.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        desc = st.text_input("Descrição")
        cat = st.selectbox("Categoria", cats)

        st.subheader("Detalhes da Despesa")
        c1, c2 = st.columns(2)
        classif = c1.selectbox("Classificação", ['Essencial', 'Não Essencial', 'Extra'])
        metodo = c2.selectbox("Método de Pagamento", ['Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank', 'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix'])
        forma = c1.selectbox("Forma de Pagamento", ['À Vista', 'Parcelado'])
        pago = c2.selectbox("Já foi pago?", ['Sim', 'Não'])
        obs = st.text_area("Observações", "-")

        st.subheader("Mês/Ano Contábil")
        c1, c2 = st.columns(2)
        m_cont = c1.number_input("Mês Contábil", 1, 12, datetime.now().month)
        a_cont = c2.number_input("Ano Contábil", 2020, 2030, datetime.now().year)
        
        if forma == 'Parcelado':
            st.subheader("Detalhes do Parcelamento")
            cp1, cp2, cp3 = st.columns(3)
            n_parc = cp1.number_input("Número total de parcelas", 2, 60, 2)
            m_ini = cp2.number_input("Mês da 1ª parcela", 1, 12, m_cont)
            a_ini = cp3.number_input("Ano da 1ª parcela", 2020, 2030, a_cont)

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
            if salvar_dados(df_final): st.success("Sucesso!"); st.rerun()

def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")
    df = carregar_dados()
    id_input = st.number_input("Digite o ID do lançamento para buscar", min_value=1)
    if st.button("Buscar ID"):
        res = df[df['ID'] == id_input]
        if not res.empty:
            st.dataframe(res, hide_index=True)
            if st.button("Excluir"):
                df = df[df['ID'] != id_input]
                if salvar_dados(df): st.success("Excluído!"); st.rerun()
        else: st.error("ID não encontrado.")

def pagina_relatorio():
    st.title("📊 Gerador de Relatório Financeiro")
    c1, c2 = st.columns(2)
    ano = c1.number_input("Selecione o Ano", 2020, 2030, datetime.now().year)
    mes = c2.selectbox("Selecione o Mês", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month-1)
    if st.button("Gerar Relatório"):
        df = carregar_dados()
        df_r = df[(df['Ano'] == ano) & (df['Mês'] == MAPA_MESES[mes])]
        if not df_r.empty:
            st.dataframe(df_r, hide_index=True)
        else: st.warning("Sem dados.")

def pagina_faturas():
    st.title("💳 Ver Faturas de Cartão de Crédito")
    cartao = st.selectbox("Selecione o Cartão de Crédito", ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG'])
    c1, c2 = st.columns(2)
    ano = c1.number_input("Ano da fatura", 2020, 2030, datetime.now().year)
    mes = c2.selectbox("Mês da fatura", list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month-1)
    if st.button("Ver Fatura"):
        df = carregar_dados()
        df_f = df[(df['Forma de Pagamento'] == cartao) & (df['Mês'] == MAPA_MESES[mes]) & (df['Ano'] == ano)]
        if not df_f.empty:
            st.metric("Total", f"R$ {df_f['Valor'].sum():,.2f}")
            st.dataframe(df_f, hide_index=True)
        else: st.info("Fatura vazia.")

def pagina_configuracoes():
    st.title("⚙️ Configurações de Categorias")
    cats = carregar_categorias()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("✨ Nova Categoria")
        n_cat = st.text_input("Nome")
        if st.button("Adicionar"):
            if n_cat and n_cat not in cats:
                if salvar_categoria_db(n_cat): st.success("Ok!"); st.rerun()
    with c2:
        st.subheader("📝 Editar Categoria")
        ed_cat = st.selectbox("Atual", ["Selecione..."] + cats)
        novo_n = st.text_input("Novo Nome")
        if st.button("Atualizar"):
            if ed_cat != "Selecione..." and novo_n:
                with st.spinner("Processando..."):
                    if editar_categoria_db(ed_cat, novo_n): st.success("Atualizado!"); st.rerun()
    with c3:
        st.subheader("🗑️ Remover Categoria")
        rm_cat = st.selectbox("Remover", ["Selecione..."] + cats)
        if st.button("Remover"):
            if rm_cat != "Selecione..." and excluir_categoria_db(rm_cat): st.success("Removida!"); st.rerun()

def pagina_graficos():
    st.title("🎨 Gerador de Gráficos Analíticos")
    escolha = st.selectbox("Escolha o Gráfico", ["Selecione um tipo de gráfico...", "Gastos por Categoria (Mensal)", "Gasto com Cartão de Crédito (Mensal)", "Gastos por Classificação (Mensal)", "Gastos por Categoria (Anual)", "Balanço Receitas x Despesas (Anual)", "Faturas de Cartão de Crédito (Anual)"])
    if escolha != "Selecione um tipo de gráfico...":
        df = carregar_dados()
        # Aqui você pode adicionar as lógicas de plotagem para cada tipo conforme necessário
        st.info(f"Gerando gráfico: {escolha}")

# --- MENU LATERAL ---
st.sidebar.title("🏛️ Menu Principal")
paginas = {
    "Página Inicial": pagina_inicial,
    "Adicionar Lançamento": pagina_adicionar,
    "Gerenciar Lançamento": pagina_gerenciar,
    "Relatório Mensal": pagina_relatorio,
    "Ver Faturas de Cartão": pagina_faturas,
    "Configurações": pagina_configuracoes,
    "Gráficos Analíticos": pagina_graficos
}
escolha = st.sidebar.radio("Navegue pelas páginas", list(paginas.keys()))
paginas[escolha]()
