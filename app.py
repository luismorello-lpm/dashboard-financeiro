import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe
from sklearn.cluster import KMeans # Usado para encontrar as melhores posições para os rótulos do gráfico

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Meu Dashboard Financeiro",
    page_icon="📊",
    layout="wide"
)

# --- CONFIGURAÇÃO DA CONEXÃO COM O GOOGLE SHEETS ---
NOME_DA_PLANILHA = "DashboardFinanceiroDB"
SCOPES = [
    '[https://www.googleapis.com/auth/spreadsheets](https://www.googleapis.com/auth/spreadsheets)',
    '[https://www.googleapis.com/auth/drive](https://www.googleapis.com/auth/drive)'
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
            
            colunas_numericas = ['ID', 'Ano', 'Valor']
            for col in colunas_numericas:
                if col in df.columns:
                    if col == 'Valor': df[col] = df[col].apply(clean_valor)
                    else: df[col] = pd.to_numeric(df[col], errors='coerce')

            df.dropna(subset=['ID'], inplace=True)
            df['ID'] = df['ID'].astype(int)
            df['Mês'] = pd.Categorical(df['Mês'], categories=MESES_ORDENADOS, ordered=True)
            return df
        except Exception as e:
            st.error(f"Erro ao carregar os dados da planilha: {e}")
            return pd.DataFrame()
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
            
            for col in df_para_salvar.columns:
                df_para_salvar[col] = df_para_salvar[col].astype(str)

            worksheet.clear()
            set_with_dataframe(worksheet, df_para_salvar, include_index=False, include_column_header=True, resize=True)
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"ERRO ao salvar os dados na planilha: {e}")
            return False
    return False
    
# --- PÁGINAS DO STREAMLIT ---

def pagina_inicial():
    st.title("🏠 Página Inicial")
    st.subheader("Resumo do Mês Corrente")

    df = carregar_dados()
    if df is None or df.empty:
        st.warning("A base de dados está vazia. Adicione um lançamento para começar.")
        return

    df['Valor Financeiro'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])
    
    ano_atual = datetime.now().year
    mes_atual_nome = MAPA_MESES[datetime.now().month]

    df_mes_atual = df[(df['Ano'] == ano_atual) & (df['Mês'] == mes_atual_nome)].copy()

    if df_mes_atual.empty:
        st.info(f"Nenhum dado encontrado para {mes_atual_nome}/{ano_atual}.")
    else:
        receitas = df_mes_atual[df_mes_atual['Valor Financeiro'] > 0]['Valor Financeiro'].sum()
        despesas = df_mes_atual[df_mes_atual['Valor Financeiro'] < 0]['Valor Financeiro'].sum()
        saldo = receitas + despesas

        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 Receitas Totais", f"R$ {receitas:,.2f}")
        col2.metric("🔴 Despesas Totais", f"R$ {despesas:,.2f}")
        col3.metric("💰 Saldo do Mês", f"R$ {saldo:,.2f}")

        st.markdown("---")
        
        col1, col2 = st.columns([2, 3])
        with col1:
            st.subheader("Últimos 5 Lançamentos")
            st.dataframe(df.tail(5), hide_index=True)
        
        with col2:
            st.subheader("Distribuição de Despesas do Mês")
            despesas_df = df_mes_atual[df_mes_atual['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum()
            if not despesas_df.empty:
                fig, ax = plt.subplots(figsize=(8, 6))
                ax.pie(despesas_df, labels=despesas_df.index, autopct=lambda p: f'R$ {p*despesas_df.sum()/100:.2f}\n({p:.1f}%)', startangle=90)
                ax.axis('equal')
                st.pyplot(fig)
            else:
                st.info("Nenhuma despesa registrada para este mês.")


def pagina_adicionar():
    st.title("✍️ Adicionar Novo Lançamento")
    df_existente = carregar_dados()
    if df_existente is None:
        st.warning("Não foi possível carregar a base de dados.")
        return
        
    proximo_id = int(df_existente['ID'].max() + 1) if not df_existente.empty else 1

    with st.form("novo_lancamento_form"):
        st.subheader("Detalhes do Lançamento")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            data_lancamento = st.date_input("Data do Lançamento", datetime.now())
        with col2:
            tipo = st.selectbox("Tipo", ['Despesa', 'Receita', 'Sobra'])
        with col3:
            valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f")
        
        descricao = st.text_input("Descrição")
        
        categorias = [
            'Entrada', 'Transporte', 'Saúde', 'Cuidados Pessoais', 'Entretenimento',
            'Bar / Restaurante / Churrasco', 'Contas Fixas', 'Moradia', 'Roupas e Calçados',
            'Gastos Gerais Corrida', 'Viagens', 'Poupado / Investimento', 
            'Gastos Extras / Diversos', 'Reposição Reserva', 'Ca'
        ]
        categoria = st.selectbox("Categoria", categorias)
        
        mes_contabil = None
        ano_contabil = None

        if tipo == 'Despesa':
            st.subheader("Detalhes da Despesa")
            col1, col2 = st.columns(2)
            with col1:
                classificacao = st.selectbox("Classificação", ['Essencial', 'Não Essencial', 'Extra'])
                pagamento = st.selectbox("Forma de Pagamento", ['À Vista', 'Parcelado'])
            with col2:
                meios_de_pagamento = [
                    'Vale Alimentação', 'Débito Nubank', 'Débito Santander', 'Crédito Nubank',
                    'Crédito Santander', 'Boleto', 'Crédito BTG', 'Dinheiro', 'Pix', 'Transf. BTG'
                ]
                forma_pagamento = st.selectbox("Método de Pagamento", meios_de_pagamento)
                pagamento_realizado = st.selectbox("Já foi pago?", ['Sim', 'Não'])

            observacoes = st.text_area("Observações", "-")
            
            if pagamento == 'À Vista':
                st.subheader("Mês/Ano Contábil")
                col1, col2 = st.columns(2)
                with col1:
                    mes_contabil = st.number_input("Mês Contábil", min_value=1, max_value=12, value=datetime.now().month, step=1)
                with col2:
                    ano_contabil = st.number_input("Ano Contábil", min_value=2020, value=datetime.now().year, step=1)
            else: # Parcelado
                st.subheader("Detalhes do Parcelamento")
                col1, col2, col3 = st.columns(3)
                with col1:
                    total_parcelas = st.number_input("Número total de parcelas", min_value=2, value=2, step=1)
                with col2:
                    mes_inicial_parcela = st.number_input("Mês da 1ª parcela", min_value=1, max_value=12, value=datetime.now().month, step=1)
                with col3:
                    ano_inicial_parcela = st.number_input("Ano da 1ª parcela", min_value=2020, value=datetime.now().year, step=1)
        else: # Receita ou Sobra
            st.subheader("Mês/Ano Contábil")
            col1, col2 = st.columns(2)
            with col1:
                mes_contabil = st.number_input("Mês Contábil", min_value=1, max_value=12, value=datetime.now().month, step=1)
            with col2:
                ano_contabil = st.number_input("Ano Contábil", min_value=2020, value=datetime.now().year, step=1)
        
        submitted = st.form_submit_button("Adicionar Lançamento")

        if submitted:
            novos_lancamentos = []
            
            if tipo in ['Receita', 'Sobra']:
                lancamento = {
                    'ID': proximo_id, 'Data': data_lancamento.strftime('%d/%m/%Y'), 'Tipo': tipo,
                    'Descrição': descricao, 'Valor': valor, 'Categoria': categoria,
                    'Classificação': 'N/A', 'Pagamento': 'N/A', 'Forma de Pagamento': 'N/A',
                    'Parcelas': 'N/A', 'Pagamento Realizado': 'OK', 'Observações': '-',
                    'Mês': MAPA_MESES[mes_contabil], 'Ano': ano_contabil
                }
                novos_lancamentos.append(lancamento)
            else: # Se for Despesa
                pagamento_realizado_str = 'OK' if pagamento_realizado == 'Sim' else 'NOK'
                if pagamento == 'À Vista':
                    lancamento = {
                        'ID': proximo_id, 'Data': data_lancamento.strftime('%d/%m/%Y'), 'Tipo': tipo,
                        'Descrição': descricao, 'Valor': valor, 'Categoria': categoria,
                        'Classificação': classificacao, 'Pagamento': pagamento, 'Forma de Pagamento': forma_pagamento,
                        'Parcelas': 'N/A', 'Pagamento Realizado': pagamento_realizado_str, 'Observações': observacoes,
                        'Mês': MAPA_MESES[mes_contabil], 'Ano': ano_contabil
                    }
                    novos_lancamentos.append(lancamento)
                else: # Se for Parcelado
                    for i in range(total_parcelas):
                        mes_atual = mes_inicial_parcela + i
                        ano_atual = ano_inicial_parcela
                        
                        while mes_atual > 12:
                            mes_atual -= 12
                            ano_atual += 1
                        
                        lancamento = {
                            'ID': proximo_id + i, 'Data': data_lancamento.strftime('%d/%m/%Y'), 'Tipo': tipo,
                            'Descrição': f"{descricao} ({i+1}/{total_parcelas})", 'Valor': valor / total_parcelas, 'Categoria': categoria,
                            'Classificação': classificacao, 'Pagamento': pagamento, 'Forma de Pagamento': forma_pagamento,
                            'Parcelas': f"{i+1:02d} de {total_parcelas:02d}", 
                            'Pagamento Realizado': pagamento_realizado_str, 'Observações': observacoes,
                            'Mês': MAPA_MESES[mes_atual], 'Ano': ano_atual
                        }
                        novos_lancamentos.append(lancamento)

            novos_df = pd.DataFrame(novos_lancamentos)
            df_atualizado = pd.concat([df_existente, novos_df], ignore_index=True)
            
            if salvar_dados(df_atualizado):
                st.success(f"{len(novos_lancamentos)} lançamento(s) adicionado(s) com sucesso!")
                st.dataframe(novos_df, hide_index=True)
                
def pagina_gerenciar():
    st.title("🛠️ Gerenciar Lançamento")
    df = carregar_dados()
    if df is None or df.empty:
        st.warning("Base de dados vazia ou indisponível.")
        return

    if 'id_gerenciar' not in st.session_state:
        st.session_state.id_gerenciar = 0

    id_input = st.number_input("Digite o ID do lançamento para buscar", min_value=1, step=1, key="id_input_widget")

    if st.button("Buscar ID"):
        st.session_state.id_gerenciar = id_input
        st.rerun()

    if st.session_state.id_gerenciar > 0:
        if st.session_state.id_gerenciar in df['ID'].values:
            index_alvo = df.index[df['ID'] == st.session_state.id_gerenciar].tolist()[0]
            
            st.subheader(f"Detalhes do Lançamento ID: {st.session_state.id_gerenciar}")
            st.dataframe(df.loc[[index_alvo]], hide_index=True)

            with st.expander("✏️ Editar este lançamento"):
                colunas_editaveis = df.columns.drop('ID').tolist()
                coluna_para_editar = st.selectbox("Qual coluna deseja editar?", colunas_editaveis, key="edit_column_select")
                
                with st.form(key=f"edit_form_{coluna_para_editar}"):
                    valor_atual = df.loc[index_alvo, coluna_para_editar]
                    st.write(f"Editando a coluna: **{coluna_para_editar}**")
                    
                    novo_valor = None
                    if coluna_para_editar == 'Data':
                        try: default_date = datetime.strptime(str(valor_atual), '%d/%m/%Y')
                        except: default_date = datetime.now()
                        novo_valor = st.date_input("Novo valor", value=default_date)
                    elif coluna_para_editar == 'Valor':
                        novo_valor = st.number_input("Novo valor", value=float(valor_atual), format="%.2f")
                    else:
                        novo_valor = st.text_input("Novo valor", value=str(valor_atual))

                    if st.form_submit_button("Salvar Alteração"):
                        valor_final = novo_valor.strftime('%d/%m/%Y') if isinstance(novo_valor, datetime) else novo_valor
                        df.loc[index_alvo, coluna_para_editar] = valor_final
                        if salvar_dados(df):
                            st.success("Lançamento atualizado!")
                            st.rerun()

            with st.expander("🗑️ Excluir este lançamento"):
                if st.button("Confirmar Exclusão"):
                    df = df.drop(index_alvo).copy()
                    df['ID'] = range(1, len(df) + 1)
                    if salvar_dados(df):
                        st.success(f"Lançamento ID {st.session_state.id_gerenciar} foi excluído.")
                        st.session_state.id_gerenciar = 0
                        st.rerun()
        else:
            st.error(f"ID {st.session_state.id_gerenciar} não encontrado.")
            st.session_state.id_gerenciar = 0

def pagina_relatorio():
    st.title("📊 Gerador de Relatório Financeiro")
    df = carregar_dados()
    if df is None or df.empty:
        st.warning("Não foi possível carregar os dados ou a base de dados está vazia.")
        return

    df['Valor Financeiro'] = np.where(df['Tipo'] == 'Despesa', -df['Valor'], df['Valor'])

    col1, col2 = st.columns(2)
    with col1:
        ano = st.number_input("Selecione o Ano", min_value=2020, max_value=2030, value=datetime.now().year)
    with col2:
        mes_num = st.selectbox("Selecione o Mês", options=list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month - 1)
    
    if st.button("Gerar Relatório"):
        nome_mes = MAPA_MESES.get(mes_num)
        df_mes = df[(df['Ano'] == ano) & (df['Mês'] == nome_mes)].copy()

        if df_mes.empty:
            st.warning(f"Nenhum dado encontrado para {nome_mes}/{ano}.")
            return

        receitas = df_mes[df_mes['Valor Financeiro'] > 0]['Valor Financeiro'].sum()
        despesas = df_mes[df_mes['Valor Financeiro'] < 0]['Valor Financeiro'].sum()
        saldo = receitas + despesas

        st.subheader(f"Resumo para {nome_mes.upper()}/{ano}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 Receitas Totais", f"R$ {receitas:,.2f}")
        col2.metric("🔴 Despesas Totais", f"R$ {despesas:,.2f}")
        col3.metric("💰 Saldo do Mês", f"R$ {saldo:,.2f}")

        st.subheader("Detalhamento de Despesas por Categoria")
        despesas_por_categoria = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum().sort_values(ascending=False)
        
        if not despesas_por_categoria.empty:
            st.dataframe(despesas_por_categoria.map("R$ {:,.2f}".format))
        else:
            st.info("Nenhuma despesa registrada para este mês.")
        
        with st.expander("Ver todos os lançamentos do mês"):
            colunas_para_ver = ['ID', 'Data', 'Tipo', 'Descrição', 'Categoria', 'Valor', 'Forma de Pagamento']
            st.dataframe(df_mes[colunas_para_ver], hide_index=True)

def pagina_faturas():
    st.title("💳 Ver Faturas de Cartão de Crédito")
    df = carregar_dados()
    if df is None or df.empty:
        st.warning("Base de dados vazia ou indisponível.")
        return
        
    cartoes = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
    cartao_selecionado = st.selectbox("Selecione o Cartão de Crédito", cartoes)
    
    col1, col2 = st.columns(2)
    with col1:
        ano = st.number_input("Ano da fatura", min_value=2020, max_value=2030, value=datetime.now().year)
    with col2:
        mes_num = st.selectbox("Mês da fatura", options=list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month - 1)

    if st.button("Ver Fatura"):
        nome_mes = MAPA_MESES.get(mes_num)
        
        fatura_df = df[
            (df['Forma de Pagamento'] == cartao_selecionado) &
            (df['Ano'] == ano) & 
            (df['Mês'] == nome_mes)
        ]

        if fatura_df.empty:
            st.warning(f"Nenhum lançamento encontrado para a fatura de {cartao_selecionado} em {nome_mes}/{ano}.")
        else:
            total_fatura = fatura_df['Valor'].sum()
            st.metric(f"Total da Fatura de {nome_mes.upper()}/{ano}", f"R$ {total_fatura:,.2f}")
            
            with st.expander("Ver detalhes da fatura"):
                colunas_para_ver = ['ID', 'Data', 'Descrição', 'Parcelas', 'Valor']
                st.dataframe(fatura_df[colunas_para_ver], hide_index=True)

def pagina_graficos():
    st.title("🎨 Gerador de Gráficos Analíticos")
    df = carregar_dados()
    if df is None or df.empty:
        st.warning("Nenhum dado para gerar gráficos.")
        return

    opcoes_graficos = {
        "Selecione um tipo de gráfico...": "nenhum",
        "Gastos por Categoria (Mensal)": "cat_mensal",
        "Gasto com Cartão de Crédito (Mensal)": "cc_mensal",
        "Gastos por Classificação (Mensal)": "class_mensal",
        "Gastos por Categoria (Anual)": "cat_anual",
        "Balanço Receitas x Despesas (Anual)": "balanco_anual",
        "Faturas de Cartão de Crédito (Anual)": "faturas_anual"
    }
    escolha_grafico = st.selectbox("Escolha o Gráfico", list(opcoes_graficos.keys()))
    
    tipo_grafico = opcoes_graficos[escolha_grafico]

    if tipo_grafico.endswith("_mensal"):
        col1, col2 = st.columns(2)
        with col1:
            ano = st.number_input("Ano", min_value=2020, max_value=2030, value=datetime.now().year, key="graf_ano_mensal")
        with col2:
            mes_num = st.selectbox("Mês", options=list(range(1, 13)), format_func=lambda x: MAPA_MESES[x], index=datetime.now().month - 1, key="graf_mes_mensal")
        
        if st.button("Gerar Gráfico Mensal"):
            nome_mes = MAPA_MESES.get(mes_num)
            df_mes = df[(df['Ano'] == ano) & (df['Mês'] == nome_mes)].copy()
            
            if df_mes.empty:
                st.warning(f"Nenhum dado para {nome_mes}/{ano}.")
                return

            if tipo_grafico == 'cat_mensal':
                st.subheader(f"Despesas por Categoria - {nome_mes}/{ano}")
                despesas_df = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum()
                if not despesas_df.empty:
                    fig, ax = plt.subplots()
                    ax.pie(despesas_df, labels=despesas_df.index, autopct=lambda p: f'R$ {p*despesas_df.sum()/100:.2f}\n({p:.1f}%)', startangle=90)
                    ax.axis('equal')
                    st.pyplot(fig)
                else: st.info("Nenhuma despesa encontrada.")

            elif tipo_grafico == 'cc_mensal':
                st.subheader(f"Gastos com Cartão de Crédito - {nome_mes}/{ano}")
                cartoes = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
                cc_df = df_mes[df_mes['Forma de Pagamento'].isin(cartoes)].groupby('Forma de Pagamento')['Valor'].sum()
                if not cc_df.empty:
                    fig, ax = plt.subplots(figsize=(8, 5))
                    bars = ax.bar(cc_df.index, cc_df.values, color=['purple', 'red', 'blue'])
                    ax.set_ylabel('Valor Gasto (R$)')
                    for bar in bars:
                        yval = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width()/2.0, yval, f'R$ {yval:,.2f}', va='bottom', ha='center')
                    st.pyplot(fig)
                else: st.info("Nenhum gasto com cartão de crédito encontrado.")
            
            elif tipo_grafico == 'class_mensal':
                st.subheader(f"Despesas por Classificação - {nome_mes}/{ano}")
                class_df = df_mes[df_mes['Tipo'] == 'Despesa'].groupby('Classificação')['Valor'].sum()
                if not class_df.empty:
                    fig, ax = plt.subplots()
                    ax.pie(class_df, labels=class_df.index, autopct=lambda p: f'R$ {p*class_df.sum()/100:.2f}\n({p:.1f}%)', startangle=90)
                    ax.axis('equal')
                    st.pyplot(fig)
                else: st.info("Nenhuma despesa classificada encontrada.")

    elif tipo_grafico.endswith("_anual"):
        ano = st.number_input("Ano", min_value=2020, max_value=2030, value=datetime.now().year, key="graf_ano_anual")
        
        if st.button("Gerar Gráfico Anual"):
            df_ano = df[df['Ano'] == ano].copy()
            if df_ano.empty: st.warning(f"Nenhum dado para o ano de {ano}."); return

            if tipo_grafico == 'cat_anual':
                st.subheader(f"Despesas por Categoria - {ano}")
                despesas_df = df_ano[df_ano['Tipo'] == 'Despesa'].groupby('Categoria')['Valor'].sum()
                if not despesas_df.empty:
                    fig, ax = plt.subplots(figsize=(10, 8))
                    ax.pie(despesas_df, labels=despesas_df.index, autopct=lambda p: f'R$ {p*despesas_df.sum()/100:,.2f}\n({p:.1f}%)', startangle=90)
                    ax.axis('equal')
                    st.pyplot(fig)
                else: st.info("Nenhuma despesa encontrada.")
            
            elif tipo_grafico == 'balanco_anual':
                st.subheader(f"Balanço Anual - {ano}")
                balanco = df_ano.groupby(['Mês', 'Tipo'])['Valor'].sum().unstack().fillna(0)
                if not balanco.empty:
                    fig, ax = plt.subplots(figsize=(12, 6))
                    balanco.plot(kind='bar', stacked=True, ax=ax, color={'Receita': 'green', 'Despesa': 'red', 'Sobra': 'blue'})
                    ax.set_ylabel('Valor (R$)'); ax.set_xlabel('Mês'); plt.xticks(rotation=45)
                    st.pyplot(fig)
                else: st.info("Nenhum dado para o balanço anual.")

            elif tipo_grafico == 'faturas_anual':
                st.subheader(f"Faturas de Cartão de Crédito - {ano}")
                cartoes = ['Crédito Nubank', 'Crédito Santander', 'Crédito BTG']
                cc_df = df_ano[df_ano['Forma de Pagamento'].isin(cartoes)]
                faturas = cc_df.groupby(['Mês', 'Forma de Pagamento'])['Valor'].sum().unstack().fillna(0)
                if not faturas.empty:
                    fig, ax = plt.subplots(figsize=(12, 6))
                    faturas.plot(kind='bar', stacked=True, ax=ax, color={'Crédito Nubank': 'purple', 'Crédito Santander': 'red', 'Crédito BTG': 'blue'})
                    ax.set_ylabel('Valor da Fatura (R$)'); ax.set_xlabel('Mês'); plt.xticks(rotation=45)
                    st.pyplot(fig)
                else: st.info("Nenhum gasto com cartão de crédito encontrado.")

# --- ESTRUTURA PRINCIPAL DO APP ---

st.sidebar.title("🏛️ Menu Principal")
paginas = {
    "Página Inicial": pagina_inicial,
    "Adicionar Lançamento": pagina_adicionar,
    "Gerenciar Lançamento": pagina_gerenciar,
    "Relatório Mensal": pagina_relatorio,
    "Ver Faturas de Cartão": pagina_faturas,
    "Gráficos Analíticos": pagina_graficos,
}
escolha = st.sidebar.radio("Navegue pelas páginas", list(paginas.keys()))
paginas[escolha]()

