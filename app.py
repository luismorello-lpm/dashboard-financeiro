import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px  
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

MEIOS_PAGAMENTO_PADRAO = [
    'Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank', 
    'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix', 'Transf. BTG'
]

CLASSIFICACOES_PADRAO = ['Essencial', 'Não Essencial', 'Extra']

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
            # Atualiza registros na planilha principal
            df_atual = carregar_dados()
            if not df_atual.empty and 'Categoria' in df_atual.columns:
                df_atual['Categoria'] = df_atual['Categoria'].replace(cat_nome, cat_substituta)
                salvar_dados(df_atual)
            
            # Remove da lista de categorias
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
            
            # 1. Atualizar na aba 'Categorias'
            ws_cat = spreadsheet.worksheet("Categorias")
            celula = ws_cat.find(nome_antigo)
            if celula:
                ws_cat.update_cell(celula.row, celula.col, nome_novo)
            
            # 2. Atualizar todos os lançamentos na planilha principal (Sheet1)
            df_atual = carregar_dados()
            if not df_atual.empty and 'Categoria' in df_atual.columns:
                # Substitui o nome antigo pelo novo em toda a coluna
                df_atual['Categoria'] = df_atual['Categoria'].replace(nome_antigo, nome_novo)
                salvar_dados(df_atual)
            
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"Erro ao atualizar registros: {e}")
            return False
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
        st.subheader("Detalhes do Lançamento")
        c1, c2, c3 = st.columns(3)
        data_l = c1.date_input("Data do Lançamento", datetime.now())
        tipo = c2.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        valor = c3.number_input("Valor Total (R$)", min_value=0.01, format="%.2f")
        desc = st.text_input("Descrição")
        cat = st.selectbox("Categoria", cats)

        st.subheader("Detalhes da Despesa")
        c1, c2 = st.columns(2)
        classif = c1.selectbox("Classificação", CLASSIFICACOES_PADRAO)
        metodo = c2.selectbox("Método de Pagamento", MEIOS_PAGAMENTO_PADRAO)
        forma = c1.selectbox("Forma de Pagamento", ['À Vista', 'Parcelado'])
        pago = c2.selectbox("Já foi pago?", ['Sim', 'Não'])
        obs = st.text_area("Observações", "-")

        st.markdown("---")
        st.subheader("Configuração de Parcelas / Mês Contábil")
        cp1, cp2, cp3 = st.columns(3)
        n_parc = cp1.number_input("Número de parcelas (Se parcelado)", min_value=1, value=1, step=1)
        m_cont = cp2.number_input("Mês Inicial / Contábil", 1, 12, datetime.now().month)
        a_cont = cp3.number_input("Ano Inicial / Contábil", 2020, 2030, datetime.now().year)

        submitted = st.form_submit_button("Adicionar Lançamento")

        if submitted:
            novos_lancamentos = []
            pago_str = 'OK' if pago == 'Sim' else 'NOK'
            if tipo != 'Despesa' or forma == 'À Vista':
                novo = {
                    'ID': proximo_id, 'Data': data_l.strftime('%d/%m/%Y'), 'Tipo': tipo, 
                    'Descrição': desc, 'Valor': valor, 'Categoria': cat, 
                    'Classificação': classif if tipo == 'Despesa' else 'N/A', 
                    'Pagamento': forma if tipo == 'Despesa' else 'N/A', 
                    'Forma de Pagamento': metodo if tipo == 'Despesa' else 'N/A', 
                    'Parcelas': 'N/A', 'Pagamento Realizado': pago_str, 
                    'Observações': obs, 'Mês': MAPA_MESES[m_cont], 'Ano': a_cont
                }
                novos_lancamentos.append(novo)
            else:
                valor_parcela = valor / n_parc
                for i in range(n_parc):
                    m_atual = m_cont + i
                    a_atual = a_cont
                    while m_atual > 12:
                        m_atual -= 12
                        a_atual += 1
                    novo = {
                        'ID': proximo_id + i, 'Data': data_l.strftime('%d/%m/%Y'), 'Tipo': tipo, 
                        'Descrição': f"{desc} ({i+1}/{n_parc})", 'Valor': valor_parcela, 'Categoria': cat, 
                        'Classificação': classif, 'Pagamento': forma, 'Forma de Pagamento': metodo, 
                        'Parcelas': f"{i+1:02d} de {n_parc:02d}", 'Pagamento Realizado': pago_str, 
                        'Observações': obs, 'Mês': MAPA_MESES[m_atual], 'Ano': a_atual
                    }
                    novos_lancamentos.append(novo)
            df_final = pd.concat([df_existente, pd.DataFrame(novos_lancamentos)], ignore_index=True)
            if salvar_dados(df_final): st.success("Adicionado!"); st.rerun()

def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")
    df = carregar_dados()
    if df is None or df.empty:
        st.warning("Base de dados vazia.")
        return

    col_id, col_btn = st.columns([3, 1])
    id_input = col_id.number_input("Digite o ID do lançamento", min_value=1, step=1)
    btn_buscar = col_btn.button("🔍 Buscar Lançamento", use_container_width=True)

    if btn_buscar:
        st.session_state.id_gerenciar = id_input

    if 'id_gerenciar' in st.session_state:
        id_atual = st.session_state.id_gerenciar
        if id_atual in df['ID'].values:
            idx_alvo = df.index[df['ID'] == id_atual].tolist()[0]
            dados_atuais = df.loc[idx_alvo]
            st.success(f"Lançamento ID {id_atual} encontrado!")
            st.dataframe(df.loc[[idx_alvo]], hide_index=True)
            st.markdown("---")
            col_edit, col_del = st.columns(2)
            with col_edit:
                with st.expander("📝 Editar Lançamento"):
                    with st.form("form_edicao_lancamento"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            nova_data = st.text_input("Data", value=str(dados_atuais['Data']))
                            novo_tipo = st.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'], index=['Despesa', 'Receita', 'Sobra'].index(dados_atuais['Tipo']) if dados_atuais['Tipo'] in ['Despesa', 'Receita', 'Sobra'] else 0)
                            novo_valor = st.number_input("Valor (R$)", value=float(dados_atuais['Valor']), format="%.2f")
                        with c2:
                            nova_desc = st.text_input("Descrição", value=str(dados_atuais['Descrição']))
                            cats = carregar_categorias()
                            try: cat_idx = cats.index(dados_atuais['Categoria'])
                            except: cat_idx = 0
                            nova_cat = st.selectbox("Categoria", cats, index=cat_idx)
                            try: cl_idx = CLASSIFICACOES_PADRAO.index(dados_atuais['Classificação'])
                            except: cl_idx = 0
                            nova_class = st.selectbox("Classificação", CLASSIFICACOES_PADRAO, index=cl_idx)
                        with c3:
                            try: forma_idx = MEIOS_PAGAMENTO_PADRAO.index(dados_atuais['Forma de Pagamento'])
                            except: forma_idx = 0
                            nova_forma = st.selectbox("Forma de Pagamento", MEIOS_PAGAMENTO_PADRAO, index=forma_idx)
                            status_atuais = ['OK', 'NOK', 'N/A']
                            status_val = str(dados_atuais['Pagamento Realizado']).upper()
                            novo_pago = st.selectbox("Pago?", status_atuais, index=status_atuais.index(status_val) if status_val in status_atuais else 1)
                            novas_parc = st.text_input("Parcelas", value=str(dados_atuais['Parcelas']))
                        novas_obs = st.text_area("Observações", value=str(dados_atuais['Observações']))
                        ca1, ca2 = st.columns(2)
                        try: mes_idx = MESES_ORDENADOS.index(dados_atuais['Mês'])
                        except: mes_idx = 0
                        novo_mes = ca1.selectbox("Mês Contábil", MESES_ORDENADOS, index=mes_idx)
                        novo_ano = ca2.number_input("Ano Contábil", value=int(dados_atuais['Ano']), step=1)
                        if st.form_submit_button("💾 Salvar Alterações"):
                            df.at[idx_alvo, 'Data'] = nova_data
                            df.at[idx_alvo, 'Tipo'] = novo_tipo
                            df.at[idx_alvo, 'Valor'] = novo_valor
                            df.at[idx_alvo, 'Descrição'] = nova_desc
                            df.at[idx_alvo, 'Categoria'] = nova_cat
                            df.at[idx_alvo, 'Classificação'] = nova_class
                            df.at[idx_alvo, 'Forma de Pagamento'] = nova_forma
                            df.at[idx_alvo, 'Pagamento Realizado'] = novo_pago
                            df.at[idx_alvo, 'Observações'] = novas_obs
                            df.at[idx_alvo, 'Mês'] = novo_mes
                            df.at[idx_alvo, 'Ano'] = novo_ano
                            df.at[idx_alvo, 'Parcelas'] = novas_parc
                            if salvar_dados(df):
                                st.toast(f"ID {id_atual} atualizado!", icon="✅")
                                st.rerun()
            with col_del:
                with st.popover("🗑️ Excluir Lançamento"):
                    st.warning(f"Deseja apagar o ID {id_atual}?")
                    if st.button(f"Confirmar Exclusão do ID {id_atual}", type="primary"):
                        df = df.drop(idx_alvo).reset_index(drop=True)
                        if not df.empty: df['ID'] = range(1, len(df) + 1)
                        if salvar_dados(df):
                            st.success(f"ID {id_atual} excluído!"); del st.session_state.id_gerenciar; st.rerun()
        else: st.error(f"ID {id_atual} não encontrado.")

def pagina_relatorio():
    st.title("📊 Gerador de Relatório Financeiro")
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
    st.title("💳 Ver Faturas de Cartão de Crédito")
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
        st.subheader("✨ Nova Categoria")
        n_cat = st.text_input("Nome da Categoria", key="new_cat")
        if st.button("Adicionar"):
            if n_cat and n_cat not in cats:
                if salvar_categoria_db(n_cat): st.success("Adicionada!"); st.rerun()
    with c2:
        st.subheader("📝 Editar Categoria")
        ed_cat = st.selectbox("Editar Categoria", ["Selecione..."] + cats)
        novo_n = st.text_input("Novo Nome")
        if st.button("Atualizar"):
            if ed_cat != "Selecione..." and novo_n:
                with st.spinner("Atualizando registros na planilha principal..."):
                    if editar_categoria_db(ed_cat, novo_n):
                        st.success(f"Categoria e registros antigos atualizados para: {novo_n}")
                        st.rerun()
    with c3:
        st.subheader("🗑️ Remover Categoria")
        rm_cat = st.selectbox("Excluir Categoria", ["Selecione..."] + cats)
        cat_sub = st.selectbox("Substituir registros por", ["Selecione..."] + [c for c in cats if c != rm_cat])
        if st.button("Confirmar Exclusão"):
            if rm_cat != "Selecione..." and cat_sub != "Selecione...":
                if excluir_categoria_db(rm_cat, cat_sub): st.success("Excluída!"); st.rerun()

def pagina_graficos():
    st.title("🎨 Gerador de Gráficos Analíticos")
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
                st.plotly_chart(px.pie(res, values='Valor', names='Categoria', hole=0.4), use_container_width=True)
            elif escolha == "Gasto com Cartão (Mensal)":
                cart = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
                res = df_m[df_m['Forma de Pagamento'].isin(cart)].groupby('Forma de Pagamento')['Valor'].sum().reset_index()
                st.plotly_chart(px.bar(res, x='Forma de Pagamento', y='Valor'), use_container_width=True)
    elif "Anual" in escolha:
        ano = st.number_input("Ano", 2020, 2030, datetime.now().year, key="ano_a")
        if st.button("Gerar Gráfico Anual"):
            df_a = df[df['Ano'] == ano]
            if escolha == "Balanço (Anual)":
                res = df_a.groupby(['Mês', 'Tipo'])['Valor'].sum().reset_index()
                st.plotly_chart(px.bar(res, x='Mês', y='Valor', color='Tipo', barmode='group'), use_container_width=True)
            elif escolha == "Faturas (Anual)":
                cart = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
                res = df_a[df_a['Forma de Pagamento'].isin(cart)].groupby(['Mês', 'Forma de Pagamento'])['Valor'].sum().reset_index()
                st.plotly_chart(px.line(res, x='Mês', y='Valor', color='Forma de Pagamento'), use_container_width=True)

# --- MENU PRINCIPAL ---
st.sidebar.title("🏛️ Menu Principal")
paginas = {
    "Página Inicial": pagina_inicial,
    "Adicionar Lançamento": pagina_adicionar,
    "Gerenciar Lançamento": pagina_gerenciar,
    "Relatório Mensal": pagina_relatorio,
    "Ver Faturas de Cartão": pagina_faturas,
    "Configurações de Categoria": pagina_configuracoes,
    "Gráficos Analíticos": pagina_graficos
}
escolha = st.sidebar.radio("Navegue pelas páginas", list(paginas.keys()))
paginas[escolha]()
