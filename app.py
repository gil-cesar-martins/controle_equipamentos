import streamlit as st
import qrcode
import io
import os
import time  # Para o delay de 2 segundos
import pandas as pd
import calendar
import altair as alt
from datetime import date, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, Date, ForeignKey, or_, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import plotly.express as px

# ==========================================
# CONFIGURAÇÃO DA PÁGINA (ÚNICA CHAMADA)
# ==========================================
st.set_page_config(
    page_title="Sistema de Gestão",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================
# CSS CUSTOMIZADO — IDENTIDADE VISUAL
# ==========================================
st.markdown("""
<style>
    :root {
        --azul-background: #0F172A;
        --azul-principal: #2563EB;
        --azul-escuro: #1E3A8A;
        --cinza-fundo: #d6d6d6;
        --borda: #2c16c8;
    }
    .stApp { background-color: var(--cinza-fundo); }
    section[data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid var(--borda);
    }
    section[data-testid="stSidebar"] * { color: #F1F5F9 !important; }
    section[data-testid="stSidebar"] button {
        background-color: transparent !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        text-align: left !important;
        margin-bottom: 4px;
        transition: all .15s ease-in-out;
    }
    section[data-testid="stSidebar"] button:hover {
        background-color: var(--azul-principal) !important;
        border-color: var(--azul-principal) !important;
    }
    h1, h2, h3 { color: var(--azul-escuro); font-weight: 700; }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        background-color: white;
    }
    button[kind="primary"], div.stButton > button { border-radius: 8px; }
    div[data-testid="stMetric"] {
        background-color: white;
        border: 1px solid var(--borda);
        border-radius: 12px;
        padding: 10px 14px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    div[data-testid="stDataFrame"], div[data-testid="stTable"] {
        border-radius: 10px;
        overflow: hidden;
    }
    hr { margin: 0.6rem 0; }
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# CONFIGURAÇÃO DO BANCO DE DADOS E MODELOS
# ==========================================
DATABASE_URL = "sqlite:///sistema_gestao.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()

class Cliente(Base):
    __tablename__ = 'clientes'
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True)
    emprestimos = relationship("Emprestimo", back_populates="cliente_responsavel")

class Equipamento(Base):
    __tablename__ = 'equipamentos'
    id = Column(Integer, primary_key=True)
    nome = Column(String)
    patrimonio = Column(String, unique=True)
    descricao = Column(Text)
    foto_path = Column(String)
    status = Column(String, default="DISPONÍVEL")
    emprestimos = relationship("Emprestimo", back_populates="equipamento_alugado")

class Emprestimo(Base):
    __tablename__ = 'emprestimos'
    id = Column(Integer, primary_key=True)
    equipamento_id = Column(Integer, ForeignKey('equipamentos.id'))
    cliente_id = Column(Integer, ForeignKey('clientes.id'))
    processo_pmc = Column(String)
    contrato = Column(String)
    nf1 = Column(String)
    nf2 = Column(String)
    valor = Column(String)
    previsao_coleta = Column(Date)
    data_coleta = Column(Date)
    status = Column(String) 
    data_devolucao = Column(Date)
    faturamento = Column(String)
    data_prox_fatura = Column(Date)
    numero_faturamentos = Column(Integer, default=1)

    equipamento_alugado = relationship("Equipamento", back_populates="emprestimos")
    cliente_responsavel = relationship("Cliente", back_populates="emprestimos")

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# === CÓDIGO DE MIGRAÇÕES SILENCIOSAS ===
try:
    session.execute(text("SELECT data_devolucao FROM emprestimos LIMIT 1"))
except Exception:
    session.execute(text("ALTER TABLE emprestimos ADD COLUMN data_devolucao DATE"))
    session.commit()

try:
    session.execute(text("SELECT numero_faturamentos FROM emprestimos LIMIT 1"))
except Exception:
    session.execute(text("ALTER TABLE emprestimos ADD COLUMN numero_faturamentos INTEGER DEFAULT 1"))
    session.commit()

if not os.path.exists("fotos"): os.makedirs("fotos")

# ==========================================
# ESTADOS DE FORMULÁRIOS (RESET DE CAMPOS)
# ==========================================
if 'eqp_form_version' not in st.session_state: st.session_state.eqp_form_version = 0
if 'cli_form_version' not in st.session_state: st.session_state.cli_form_version = 0
if 'loc_form_version' not in st.session_state: st.session_state.loc_form_version = 0

# ==========================================
# HELPERS GERAIS E DATA
# ==========================================
STATUS_BADGE = {
    "AGUARDANDO": "🟡 AGUARDANDO",
    "COLETADO": "🟢 COLETADO",
    "CANCELADO": "🔴 CANCELADO",
    "DEVOLVIDO": "🔵 DEVOLVIDO",
}

def badge_status(status: str) -> str:
    return STATUS_BADGE.get(status, status or "—")

def parse_moeda(valor_str):
    if not valor_str: return 0.0
    v = str(valor_str).replace('R$', '').strip()
    if ',' in v:
        v = v.replace('.', '')
        v = v.replace(',', '.')
    try:
        return float(v)
    except:
        return 0.0

def calcular_data_fatura(data_base, frequencia, multiplicador=1):
    """Soma datas de maneira exata (ex: 25/06 + 1 mês = 25/07)"""
    if frequencia == "SEMANAL":
        return data_base + timedelta(days=7 * multiplicador)
    elif frequencia == "QUINZENAL":
        return data_base + timedelta(days=15 * multiplicador)
    else: # MENSAL
        m = data_base.month + multiplicador
        y = data_base.year + ((m - 1) // 12)
        m = ((m - 1) % 12) + 1
        d = min(data_base.day, calendar.monthrange(y, m)[1])
        return date(y, m, d)

# ==========================================
# LÓGICA DE PAGINAÇÃO SEPARADA
# ==========================================
ITENS_POR_PAGINA = 10

def get_limites_paginacao(total_itens: int, page_key: str, filtro_atual=None):
    total_paginas = max(1, -(-total_itens // ITENS_POR_PAGINA))
    
    if page_key not in st.session_state: st.session_state[page_key] = 1

    filtro_key = f"{page_key}_filtro_anterior"
    if filtro_key not in st.session_state:
        st.session_state[filtro_key] = filtro_atual
    elif st.session_state[filtro_key] != filtro_atual:
        st.session_state[filtro_key] = filtro_atual
        st.session_state[page_key] = 1

    st.session_state[page_key] = max(1, min(st.session_state[page_key], total_paginas))
    pagina_atual = st.session_state[page_key]

    inicio = (pagina_atual - 1) * ITENS_POR_PAGINA
    fim = inicio + ITENS_POR_PAGINA
    return inicio, fim, total_paginas, pagina_atual

def renderizar_botoes_paginacao(page_key: str, total_paginas: int, total_itens: int, pagina_atual: int):
    col_prev, col_info, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("⬅️ Página Anterior", key=f"{page_key}_prev", width='stretch', disabled=(pagina_atual <= 1)):
            st.session_state[page_key] -= 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center; padding-top:8px; font-weight:600;'>"
            f"Página {pagina_atual} de {total_paginas}  •  {total_itens} registro(s)"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("Próxima Página ➡️", key=f"{page_key}_next", width='stretch', disabled=(pagina_atual >= total_paginas)):
            st.session_state[page_key] += 1
            st.rerun()

# ==========================================
# ESTADOS DE SESSÃO E SIDEBAR
# ==========================================
if 'menu' not in st.session_state: st.session_state.menu = "Equipamento"
if 'edit_id' not in st.session_state: st.session_state['edit_id'] = None
if 'edit_type' not in st.session_state: st.session_state['edit_type'] = None

if os.path.exists("imagens/LOGO.png"): st.sidebar.image("imagens/LOGO.png", width='stretch')
st.sidebar.markdown("## 🗂️ Menu de Navegação")
st.sidebar.caption("Selecione uma área do sistema")
st.sidebar.markdown("---")

st.sidebar.markdown("**EQUIPAMENTOS**")
if st.sidebar.button("📦  Cadastrar Equipamento", width='stretch'):
    st.session_state.menu = "Equipamento"; st.session_state.edit_id = None
if st.sidebar.button("📋  Lista de Equipamentos", width='stretch'):
    st.session_state.menu = "Lista Equipamentos"; st.session_state.edit_id = None

st.sidebar.markdown("**CLIENTES**")
if st.sidebar.button("👤  Cadastrar Cliente", width='stretch'):
    st.session_state.menu = "Cliente"; st.session_state.edit_id = None
if st.sidebar.button("📇  Lista de Clientes", width='stretch'):
    st.session_state.menu = "Lista Clientes"; st.session_state.edit_id = None

st.sidebar.markdown("**LOCAÇÕES**")
if st.sidebar.button("📝  Nova Locação", width='stretch'):
    st.session_state.menu = "Locação"; st.session_state.edit_id = None
if st.sidebar.button("📑  Lista de Locações", width='stretch'):
    st.session_state.menu = "Lista Locações"; st.session_state.edit_id = None

st.sidebar.markdown("**FINANCEIRO**")
if st.sidebar.button("💰 Financeiro", width='stretch'):
    st.session_state.menu = "Financeiro"; st.session_state.edit_id = None

menu = st.session_state.menu

# ==========================================
# LÓGICA DE EDIÇÃO GLOBAL
# ==========================================
if st.session_state['edit_id'] is not None:

    # --- EDITAR EQUIPAMENTO ---
    if st.session_state['edit_type'] == "equipamento":
        equip = session.query(Equipamento).get(st.session_state['edit_id'])
        st.markdown(f"### ✏️ Exibir / Editar Equipamento")
        st.caption(f"Patrimônio: **{equip.patrimonio}**")
        st.divider()

        col_foto, col_form = st.columns([1, 2])
        with col_foto:
            if equip.foto_path and os.path.exists(equip.foto_path):
                st.image(equip.foto_path, caption="Foto Atual", width=200)
            else:
                st.info("Sem foto cadastrada.")

        with col_form:
            with st.form("form_edit_eqp"):
                n_nome = st.text_input("Nome", value=equip.nome)
                n_pat = st.text_input("Patrimônio", value=equip.patrimonio)
                n_desc = st.text_area("Descrição", value=equip.descricao)
                n_foto = st.file_uploader("Alterar Foto", type=['jpg', 'png', 'jpeg'])

                col_salvar, col_cancelar = st.columns(2)
                if col_salvar.form_submit_button("💾 Salvar Alterações", width='stretch'):
                    existente = session.query(Equipamento).filter(Equipamento.patrimonio == n_pat, Equipamento.id != equip.id).first()
                    if existente:
                        st.error(f"⚠️ O patrimônio '{n_pat}' já pertence a outro equipamento!")
                    else:
                        equip.nome = n_nome
                        equip.patrimonio = n_pat
                        equip.descricao = n_desc
                        if n_foto:
                            caminho = f"fotos/{n_pat}_{n_foto.name}"
                            with open(caminho, "wb") as f:
                                f.write(n_foto.getbuffer())
                            equip.foto_path = caminho
                        session.commit()
                        st.success("Equipamento updated!")
                        time.sleep(2)
                        st.session_state['edit_id'] = None
                        st.rerun()
                if col_cancelar.form_submit_button("✖️ Cancelar", width='stretch'):
                    st.session_state['edit_id'] = None
                    st.rerun()

    # --- EDITAR CLIENTE ---
    elif st.session_state['edit_type'] == "cliente":
        cli = session.query(Cliente).get(st.session_state['edit_id'])
        st.markdown("### ✏️ Exibir / Editar Cliente")
        st.caption(f"ID: **{cli.id}**")
        st.divider()

        with st.form("form_edit_cli"):
            n_nome = st.text_input("Nome do Cliente", value=cli.nome)

            col_salvar, col_cancelar = st.columns(2)
            if col_salvar.form_submit_button("💾 Salvar Alterações", width='stretch'):
                existente = session.query(Cliente).filter(Cliente.nome == n_nome, Cliente.id != cli.id).first()
                if existente:
                    st.error("Este nome já está cadastrado para outro cliente!")
                else:
                    cli.nome = n_nome
                    session.commit()
                    st.success("Cliente atualizado!")
                    time.sleep(2)
                    st.session_state['edit_id'] = None
                    st.rerun()

            if col_cancelar.form_submit_button("✖️ Cancelar", width='stretch'):
                st.session_state['edit_id'] = None
                st.rerun()

    # --- EDITAR LOCAÇÃO ---
    elif st.session_state['edit_type'] == "locacao":
        loc = session.query(Emprestimo).get(st.session_state['edit_id'])
        col_esq, col_form_loc, col_vazio = st.columns([1, 2, 1])

        with col_form_loc:
            st.markdown("### ✏️ Editar Locação")
            st.caption(f"ID da Locação: **{loc.id}** •  Status atual: {badge_status(loc.status)}")
            st.divider()

            eqps = session.query(Equipamento).all()
            clis = session.query(Cliente).all()

            with st.container(border=True):
                idx_eqp = next((i for i, e in enumerate(eqps) if e.id == loc.equipamento_id), 0)
                idx_cli = next((i for i, c in enumerate(clis) if c.id == loc.cliente_id), 0)

                sel_eqp = st.selectbox("Equipamento", eqps, index=idx_eqp, format_func=lambda x: f"{x.nome} - Pat: {x.patrimonio}")
                st.info(f"**Descrição do Equipamento:** {sel_eqp.descricao}")
                sel_cli = st.selectbox("Cliente", clis, index=idx_cli, format_func=lambda x: f"{x.id} | {x.nome}")

                st.markdown("##### 📄 Dados do Contrato")
                proc = st.text_input("Processo PMC", value=loc.processo_pmc if loc.processo_pmc else "")
                contrato = st.text_input("Contrato", value=loc.contrato if loc.contrato else "")
                nf1 = st.text_input("NF 1", value=loc.nf1 if loc.nf1 else "")
                nf2 = st.text_input("NF 2", value=loc.nf2 if loc.nf2 else "")
                valor = st.text_input("Valor Bruto (R$)", value=loc.valor if loc.valor else "")

                lista_status = ["AGUARDANDO", "COLETADO", "CANCELADO", "DEVOLVIDO"]
                idx_status = lista_status.index(loc.status) if loc.status in lista_status else 0
                status = st.selectbox("Status", lista_status, index=idx_status)

                data_devolucao = loc.data_devolucao
                if status == "DEVOLVIDO":
                    data_dev_val = loc.data_devolucao if loc.data_devolucao else date.today()
                    data_devolucao = st.date_input("Data de Devolução", value=data_dev_val, format="DD/MM/YYYY")

                st.markdown("##### 📅 Datas e Faturamento")
                prev_coleta = st.date_input("Previsão de Coleta", value=loc.previsao_coleta or date.today(), format="DD/MM/YYYY")
                data_coleta = st.date_input("Data da Coleta (Se aplicável)", value=loc.data_coleta, format="DD/MM/YYYY")
                
                lista_faturamento = ["SEMANAL", "QUINZENAL", "MENSAL"]
                idx_fat = lista_faturamento.index(loc.faturamento) if loc.faturamento in lista_faturamento else 0
                
                col_f1, col_f2 = st.columns(2)
                faturamento = col_f1.selectbox("Frequência", lista_faturamento, index=idx_fat)
                numero_faturamentos = col_f2.number_input("Nº de Faturas", min_value=1, step=1, value=loc.numero_faturamentos or 1)

                data_prox = st.date_input("Data da Primeira Fatura", value=loc.data_prox_fatura or calcular_data_fatura(prev_coleta, faturamento, 1), format="DD/MM/YYYY")

                st.markdown("---")
                col_salvar, col_cancelar = st.columns(2)

                if col_salvar.button("💾 Salvar Alterações", width='stretch'):
                    # --- CORREÇÃO E PROTEÇÃO DE STATUS AQUI ---
                    id_eqp_antigo = loc.equipamento_id
                    
                    loc.equipamento_id = sel_eqp.id
                    loc.cliente_id = sel_cli.id
                    loc.processo_pmc = proc
                    loc.contrato = contrato
                    loc.nf1 = nf1
                    loc.nf2 = nf2
                    loc.valor = valor
                    loc.status = status
                    loc.data_devolucao = data_devolucao
                    loc.previsao_coleta = prev_coleta
                    loc.data_coleta = data_coleta
                    loc.faturamento = faturamento
                    loc.numero_faturamentos = numero_faturamentos
                    loc.data_prox_fatura = data_prox
                    
                    # 1. Se o usuário trocou a máquina neste contrato, a máquina anterior fica livre
                    if id_eqp_antigo != sel_eqp.id:
                        eqp_antigo = session.query(Equipamento).get(id_eqp_antigo)
                        if eqp_antigo:
                            eqp_antigo.status = "DISPONÍVEL"
                            
                    # 2. Atualiza o status da máquina atualmente vinculada à locação
                    eqp_atual = session.query(Equipamento).get(sel_eqp.id)
                    if eqp_atual:
                        eqp_atual.status = "ALUGADO" if status == "COLETADO" else "DISPONÍVEL"
                    # ------------------------------------------

                    session.commit()
                    st.success("Locação atualizada com sucesso!")
                    time.sleep(2)
                    st.session_state['edit_id'] = None
                    st.rerun()

                if col_cancelar.button("✖️ Sair sem Salvar", width='stretch'):
                    st.session_state['edit_id'] = None
                    st.rerun()

# ==========================================
# TELAS PRINCIPAIS (SE NÃO ESTIVER EDITANDO)
# ==========================================
elif menu == "Equipamento":
    st.markdown("## 📦 Cadastro de Equipamento")
    st.divider()

    with st.container(border=True):
        with st.form("form_eqp", clear_on_submit=False):
            col1, col2 = st.columns(2)
            nome = col1.text_input("Nome do Equipamento", key=f"eqp_nome_{st.session_state.eqp_form_version}")
            pat = col2.text_input("Patrimônio", key=f"eqp_pat_{st.session_state.eqp_form_version}")
            desc = st.text_area("Descrição", key=f"eqp_desc_{st.session_state.eqp_form_version}")
            foto = st.file_uploader("Foto", type=['jpg', 'png', 'jpeg'], key=f"eqp_foto_{st.session_state.eqp_form_version}")
            btn_preview = st.form_submit_button("👁️ Pré-visualizar", width='stretch')

            if btn_preview:
                if not nome or not pat: st.error("Preencha o Nome e o Patrimônio!")
                elif not foto: st.error("Insira uma foto para visualizar e cadastrar.")
                else:
                    st.session_state['temp_eqp'] = {
                        'nome': nome, 'pat': pat, 'desc': desc,
                        'foto_bytes': foto.getvalue(), 'foto_name': foto.name
                    }

    if 'temp_eqp' in st.session_state:
        d = st.session_state['temp_eqp']
        with st.container(border=True):
            st.warning("Confirme os dados antes de cadastrar:")
            col_img, col_dados = st.columns(2)
            col_img.image(d['foto_bytes'], width=100, caption="Pré-visualização")
            col_dados.markdown(f"**Nome:** {d['nome']}\n\n**Patrimônio:** {d['pat']}\n\n**Descrição:** {d['desc']}")

            col_a, col_b = st.columns(2)
            if col_a.button("✅ Confirmar Cadastro", width='stretch'):
                existente = session.query(Equipamento).filter_by(patrimonio=d['pat']).first()
                if existente:
                    st.error(f"⚠️ O patrimônio '{d['pat']}' já está cadastrado!")
                else:
                    caminho = f"fotos/{d['pat']}_{d['foto_name']}"
                    with open(caminho, "wb") as f: f.write(d['foto_bytes'])
                    novo_equip = Equipamento(nome=d['nome'], patrimonio=d['pat'], descricao=d['desc'], foto_path=caminho, status="DISPONÍVEL")
                    session.add(novo_equip)
                    session.commit()
                    st.success("Equipamento cadastrado com sucesso!")
                    time.sleep(2)
                    st.session_state.eqp_form_version += 1  # Incrementa para limpar os campos
                    del st.session_state['temp_eqp']
                    st.rerun()

            if col_b.button("✖️ Cancelar", width='stretch'):
                del st.session_state['temp_eqp']
                st.rerun()

elif menu == "Lista Equipamentos":
    st.markdown("## 📋 Equipamentos Cadastrados")
    col_equip1,col_equip_meio,col_equip2 = st.columns([1, 1, 1])
    with col_equip1:
        st.metric("Total de Equipamentos", session.query(Equipamento).count())
    st.divider()

    with col_equip2:
        termo = st.text_input("🔍 Filtrar por Nome ou Patrimônio:")
        query = session.query(Equipamento)
        if termo:
            query = query.filter((Equipamento.nome.ilike(f"%{termo}%")) | (Equipamento.patrimonio.ilike(f"%{termo}%")))
        
    query = query.order_by(text("CASE WHEN status = 'DISPONÍVEL' THEN 0 ELSE 1 END"), Equipamento.nome)
    equipamentos = query.all()

    if not equipamentos:
        st.info("Nenhum equipamento encontrado.")
    else:
        # Tabela (Cima)
        inicio, fim, total_paginas, pagina_atual = get_limites_paginacao(len(equipamentos), "pagina_eqp", termo)
        equipamentos_pagina = equipamentos[inicio:fim]

        dados_eqp = []
        for item in equipamentos_pagina:
            dados_eqp.append({
                "ID_EQUIPAMENTO": item.id,
                "Nome": item.nome,
                "Patrimônio": item.patrimonio,
                "Descrição": item.descricao or "—",
                "Status": badge_status(item.status)
            })
        
        df_eqp = pd.DataFrame(dados_eqp).set_index("ID_EQUIPAMENTO")
        st.dataframe(df_eqp, width='stretch')

        # Paginação (Embaixo)
        renderizar_botoes_paginacao("pagina_eqp", total_paginas, len(equipamentos), pagina_atual)

        st.divider()
        st.markdown("#### ✏️ Exibir / Editar Equipamento")
        col_edit1, col_edit2 = st.columns([1, 3])
        with col_edit1:
            id_para_editar = st.number_input("Digite o ID do equipamento:", min_value=1, step=1, value=None)
        if id_para_editar:
            if session.query(Equipamento).get(id_para_editar):
                st.session_state['edit_id'] = id_para_editar
                st.session_state['edit_type'] = "equipamento"
                if st.button("➡️ Ir para edição"): st.rerun()
            else: st.warning("ID não encontrado.")

elif menu == "Cliente":
    col_cad_cliente1, col_cad_cliente2, col_cad_cliente3 = st.columns([1, 2, 1])
    with col_cad_cliente2:
        st.markdown("## 👤 Cadastro de Cliente")
        st.divider()
        with st.container(border=True):
            with st.form("form_cli"):
                nome_cli = st.text_input("Nome do Cliente", key=f"cli_nome_{st.session_state.cli_form_version}")
                if st.form_submit_button("✅ Cadastrar", width='stretch'):
                    if not nome_cli.strip(): st.error("O nome não pode estar vazio!")
                    elif session.query(Cliente).filter(Cliente.nome.ilike(nome_cli)).first(): st.error("Nome já cadastrado!")
                    else:
                        session.add(Cliente(nome=nome_cli))
                        session.commit()
                        st.success("Cliente cadastrado com sucesso!")
                        time.sleep(2)
                        st.session_state.cli_form_version += 1  # Incrementa para limpar o campo
                        st.rerun()

elif menu == "Lista Clientes":
    st.markdown("## 📇 Clientes Cadastrados")
    col_cliente1, col_cliente_meio, col_cliente2 = st.columns([1, 1, 1])
    with col_cliente1:
        st.metric("Total de Clientes", session.query(Cliente).count())
    st.divider()
    with col_cliente2:
        filtro = st.text_input("🔍 Filtrar por nome (digite pelo menos 3 letras):")
        query = session.query(Cliente)
        if filtro and len(filtro) >= 3: query = query.filter(Cliente.nome.ilike(f"%{filtro}%"))
        clientes = query.all()

    if clientes:
        # Tabela (Cima)
        inicio, fim, total_paginas, pagina_atual = get_limites_paginacao(len(clientes), "pagina_cli", filtro)
        clientes_pagina = clientes[inicio:fim]

        df = pd.DataFrame([{"ID_CLIENTE": c.id, "NOME": c.nome} for c in clientes_pagina]).set_index("ID_CLIENTE")
        st.dataframe(df, width='stretch')

        # Paginação (Embaixo)
        renderizar_botoes_paginacao("pagina_cli", total_paginas, len(clientes), pagina_atual)

        st.divider()
        col_edit1, col_edit2 = st.columns([1,3])
        with col_edit1:
            st.markdown("#### ✏️ Exibir / Editar Cliente")
            id_para_editar = st.number_input("Digite o ID do cliente:", min_value=1, step=1, value=None)
            if id_para_editar:
                if session.query(Cliente).get(id_para_editar):
                    st.session_state['edit_id'] = id_para_editar
                    st.session_state['edit_type'] = "cliente"
                    if st.button("➡️ Ir para edição"): st.rerun()
                else: st.warning("ID não encontrado.")
    else:
        st.info("Digite pelo menos 5 letras ou deixe em branco para ver todos.") if filtro and len(filtro) < 5 else st.info("Nenhum cliente encontrado.")

elif menu == "Locação":
    st.markdown("## 📝 Nova Locação / Empréstimo")
    st.divider()

    eqps = session.query(Equipamento).all()
    clis = session.query(Cliente).all()

    if not eqps or not clis:
        st.warning("É necessário ter pelo menos um Equipamento e um Cliente cadastrados para realizar uma locação.")
    else:
        eqps_labels = {}
        for e in eqps:
            label = f"{e.nome} - {e.descricao or ''}"
            if label not in eqps_labels: eqps_labels[label] = []
            eqps_labels[label].append(e)

        sel_label = st.selectbox("Selecione o Equipamento", list(eqps_labels.keys()), key=f"loc_sel_label_{st.session_state.loc_form_version}")
        eqps_selecionados = eqps_labels[sel_label]
        eqp_base = eqps_selecionados[0]
        
        opcoes_pat = ["-- Digitar Novo Patrimônio --"] + [e.patrimonio for e in eqps_selecionados]
        sel_pat_opcao = st.selectbox("Patrimônio do Equipamento", opcoes_pat, key=f"loc_sel_pat_{st.session_state.loc_form_version}")
        patrimonio_final = st.text_input("Digite o Patrimônio (Obrigatório para salvar)", key=f"loc_pat_{st.session_state.loc_form_version}") if sel_pat_opcao == "-- Digitar Novo Patrimônio --" else sel_pat_opcao

        with st.container(border=True):
            sel_cli = st.selectbox("Selecione o Cliente", clis, format_func=lambda x: f"{x.id} | {x.nome}", key=f"loc_sel_cli_{st.session_state.loc_form_version}")

            st.markdown("##### 📄 Dados do Contrato")
            col1, col2 = st.columns(2)
            proc = col1.text_input("Processo PMC", key=f"loc_proc_{st.session_state.loc_form_version}")
            contrato = col2.text_input("Contrato", key=f"loc_contrato_{st.session_state.loc_form_version}")

            col3, col4 = st.columns(2)
            nf1 = col3.text_input("NF 1", key=f"loc_nf1_{st.session_state.loc_form_version}")
            nf2 = col4.text_input("NF 2", key=f"loc_nf2_{st.session_state.loc_form_version}")

            col5, col6 = st.columns(2)
            valor = col5.text_input("Valor Bruto (R$)", key=f"loc_valor_{st.session_state.loc_form_version}")
            status = col6.selectbox("Status", ["AGUARDANDO", "COLETADO", "CANCELADO", "DEVOLVIDO"], key=f"loc_status_{st.session_state.loc_form_version}")

            data_devolucao = st.date_input("Data de Devolução", format="DD/MM/YYYY", key=f"loc_data_dev_{st.session_state.loc_form_version}") if status == "DEVOLVIDO" else None

            st.markdown("##### 📅 Datas e Faturamento")
            col7, col8 = st.columns(2)
            prev_coleta = col7.date_input("Previsão de Coleta", format="DD/MM/YYYY", key=f"loc_prev_coleta_{st.session_state.loc_form_version}")
            data_coleta = col8.date_input("Data da Coleta (Se aplicável)", value=None, format="DD/MM/YYYY", key=f"loc_data_coleta_{st.session_state.loc_form_version}")

            col9, col10 = st.columns(2)
            faturamento = col9.selectbox("Frequência", ["SEMANAL", "QUINZENAL", "MENSAL"], key=f"loc_faturamento_{st.session_state.loc_form_version}")
            numero_faturamentos = col10.number_input("Nº de Faturas", min_value=1, step=1, value=1, key=f"loc_num_fat_{st.session_state.loc_form_version}")
            
            data_prox = st.date_input("Data da Primeira Fatura", value=calcular_data_fatura(prev_coleta, faturamento, 1), format="DD/MM/YYYY", key=f"loc_data_prox_{st.session_state.loc_form_version}")

            st.markdown("---")
            if st.button("💾 Salvar Locação", width='stretch'):
                if not patrimonio_final: st.error("⚠️ O campo Patrimônio deve ser preenchido ou selecionado para salvar.")
                else:
                    eqp_alvo = session.query(Equipamento).filter_by(patrimonio=patrimonio_final).first()
                    if not eqp_alvo:
                        eqp_alvo = Equipamento(nome=eqp_base.nome, descricao=eqp_base.descricao, patrimonio=patrimonio_final, status="DISPONÍVEL")
                        session.add(eqp_alvo)
                        session.commit()

                    # Automação ao CADASTRAR locação
                    eqp_alvo.status = "ALUGADO" if status == "COLETADO" else "DISPONÍVEL"

                    nova_locacao = Emprestimo(
                        equipamento_id=eqp_alvo.id, cliente_id=sel_cli.id,
                        processo_pmc=proc, contrato=contrato, nf1=nf1, nf2=nf2,
                        valor=valor, previsao_coleta=prev_coleta, data_coleta=data_coleta,
                        status=status, data_devolucao=data_devolucao,
                        faturamento=faturamento, numero_faturamentos=numero_faturamentos, data_prox_fatura=data_prox
                    )
                    session.add(nova_locacao)
                    session.commit()
                    st.success(f"Locação registrada! Equipamento {eqp_alvo.patrimonio} atualizado para o status: {eqp_alvo.status}")
                    time.sleep(2)
                    st.session_state.loc_form_version += 1  # Incrementa para limpar o formulário
                    st.rerun()

elif menu == "Lista Locações":
    st.markdown("## 📑 Locações Registradas")

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Locações", session.query(Emprestimo).count())
    m2.metric("📦 Eqp. Disponíveis", session.query(Equipamento).filter(Equipamento.status == "DISPONÍVEL").count()) 
    m3.metric("🟡 Aguardando", session.query(Emprestimo).filter(Emprestimo.status == "AGUARDANDO").count())
    m4.metric("🟢 Coletado", session.query(Emprestimo).filter(Emprestimo.status == "COLETADO").count())
    m5.metric("🔴 Cancelado", session.query(Emprestimo).filter(Emprestimo.status == "CANCELADO").count())
    m6.metric("🔵 Devolvido", session.query(Emprestimo).filter(Emprestimo.status == "DEVOLVIDO").count())
    st.divider()

    col_texto, col_status = st.columns([1, 2])
    termo = col_texto.text_input("Digite Patrimônio, Equipamento, Cliente ou NF 1:")
    status_selecionado = col_status.radio("Filtrar por Status:", ["TODOS","DISPONÍVEL", "AGUARDANDO", "COLETADO", "CANCELADO", "DEVOLVIDO"], horizontal=True)

    query = session.query(Emprestimo).join(Equipamento).join(Cliente)
    if termo:
        query = query.filter(or_(Equipamento.nome.ilike(f"%{termo}%"), Equipamento.patrimonio.ilike(f"%{termo}%"), Cliente.nome.ilike(f"%{termo}%"), Emprestimo.nf1.ilike(f"%{termo}%")))
    
    if status_selecionado != "TODOS":
        query = query.filter(Equipamento.status == "DISPONÍVEL" if status_selecionado == "DISPONÍVEL" else Emprestimo.status == status_selecionado)

    query = query.order_by(text("CASE WHEN equipamentos.status = 'DISPONÍVEL' THEN 0 ELSE 1 END"), Emprestimo.previsao_coleta.asc())
    locacoes = query.all()

    if locacoes:
        # Tabela (Cima)
        inicio, fim, total_paginas, pagina_atual = get_limites_paginacao(len(locacoes), "pagina_loc", (termo, status_selecionado))
        locacoes_pagina = locacoes[inicio:fim]

        dados = []
        for loc in locacoes_pagina:
            status_eqp = loc.equipamento_alugado.status if loc.equipamento_alugado.status else "DISPONÍVEL"
            dados.append({
                "ID Locação": loc.id,
                "Equipamento": loc.equipamento_alugado.nome,
                "Patrimônio": loc.equipamento_alugado.patrimonio,
                "Status do Eqp.": f"{'🔵' if status_eqp == 'DISPONÍVEL' else '🟠'} {status_eqp}",
                "Cliente": loc.cliente_responsavel.nome,
                "Processo PMC": loc.processo_pmc,
                "Contrato": loc.contrato,
                "NF 1": loc.nf1 if loc.nf1 else "—",
                "Valor (R$)": f"R$ {loc.valor}" if loc.valor else "R$ 0,00",
                "Status": badge_status(loc.status),
                "Prev. Coleta": loc.previsao_coleta.strftime("%d/%m/%Y") if loc.previsao_coleta else "",
                "Devolução": loc.data_devolucao.strftime("%d/%m/%Y") if loc.data_devolucao else "",
                "Faturas": f"{loc.numero_faturamentos or 1}x",
            })

        st.dataframe(pd.DataFrame(dados), width='stretch', hide_index=True)

        # Paginação (Embaixo)
        renderizar_botoes_paginacao("pagina_loc", total_paginas, len(locacoes), pagina_atual)

        st.divider()
        st.markdown("#### ✏️ Exibir / Editar Locação")
        col_edit1, col_edit2 = st.columns([1, 3])
        with col_edit1:
            id_para_editar = st.number_input("Digite o 'ID Locação' que deseja editar:", min_value=1, step=1, value=None)
        if id_para_editar:
            if session.query(Emprestimo).get(id_para_editar):
                st.session_state['edit_id'] = id_para_editar
                st.session_state['edit_type'] = "locacao"
                if st.button("➡️ Ir para edição"): st.rerun()
            else: st.warning("ID de Locação não encontrado.")
    else: st.info("Nenhuma locação encontrada com os filtros selecionados.")


# ==========================================
# FINANCEIRO (TELA NOVA)
# ==========================================
elif menu == "Financeiro":
    st.markdown("## 💰 Relatórios Financeiros")
    st.caption("Visão financeira, projeções de tempo e exportação de faturamentos.")
    st.divider()

    tab_grafico, tab_tempo, tab_tabela = st.tabs(["📊 Gráfico: Status x Valor", "📈 Gráfico: Projeção no Tempo", "📋 Relatório e Exportação"])

    locacoes = session.query(Emprestimo).join(Equipamento).join(Cliente).all()

    # --- ABA 1: BAR CHART (STATUS X VALOR) ---
    with tab_grafico:
        status_filtrados = st.multiselect(
            "Selecione os Status para análise", 
            ["AGUARDANDO", "COLETADO", "CANCELADO", "DEVOLVIDO"], 
            default=["AGUARDANDO", "COLETADO"]
        )
        
        dados_grafico = []
        for loc in locacoes:
            if loc.status in status_filtrados:
                valor_num = parse_moeda(loc.valor)
                dados_grafico.append({"Status": loc.status, "Valor": valor_num})
        
        if dados_grafico:
            df_chart = pd.DataFrame(dados_grafico)
            df_agrupado = df_chart.groupby("Status")["Valor"].sum().reset_index()
            
            # Criação do Gráfico de Colunas com Plotly
            fig = px.bar(
                df_agrupado, 
                x="Status", 
                y="Valor", 
                color="Status", # Adiciona cores diferentes para cada status
                text="Valor",   # Define que queremos exibir o valor sobre a coluna
                title="Valor Total (Bruto) por Status de Locação"
            )
            
            # Formatação dos rótulos e visual
            fig.update_traces(
                texttemplate='R$ %{text:,.2f}', # Formata como moeda
                textposition="outside"          # Valor aparece acima da coluna
            )
            
            fig.update_layout(
                template="plotly_white",
                yaxis_title="Valor Total (R$)",
                xaxis_title="Status da Locação",
                showlegend=False # Esconde a legenda, pois o eixo X já identifica
            )
            
            # Formatação do eixo Y para R$
            fig.update_yaxes(tickprefix="R$ ", tickformat=",.2f")
            
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Nenhum dado encontrado para os status selecionados.")

    # --- ABA 2: LINE CHART (PROJEÇÃO NO TEMPO) ---
    with tab_tempo:
        st.markdown("#### Projeção de Faturamento ao Longo do Tempo")
        st.caption("Use os filtros abaixo para escolher os equipamentos/patrimônios e ver as faturas projetadas com datas exatas.")

        # 1. Obter nomes únicos de equipamentos
        nomes_unicos = sorted(list(set(loc.equipamento_alugado.nome for loc in locacoes if loc.equipamento_alugado)))

        # Inicializa estado de seleção de patrimônios (persiste entre reruns)
        if "pats_selecionados" not in st.session_state:
            st.session_state["pats_selecionados"] = set()

        col_f1, col_f2 = st.columns(2)

        # --- FILTRO 1: EQUIPAMENTO, dentro de um popover (fica compacto mesmo com muitas opções) ---
        with col_f1:
            with st.popover(
                f"📦 Equipamentos ({len(st.session_state.get('nomes_selecionados', []))} selecionados)"
                if st.session_state.get("nomes_selecionados") else "📦 Filtrar por Equipamento",
                width="stretch",
            ):
                selecao_nomes = st.multiselect(
                    "Equipamentos:",
                    options=nomes_unicos,
                    default=st.session_state.get("nomes_selecionados", []),
                    key="nomes_selecionados",
                    help="Deixe em branco para considerar patrimônios de todos os equipamentos.",
                )

        # 2. Patrimônios disponíveis em cascata, conforme o(s) equipamento(s) escolhido(s)
        opcoes_patrimonios = []
        for loc in locacoes:
            if not loc.equipamento_alugado:
                continue
            nome_eqp = loc.equipamento_alugado.nome
            if not selecao_nomes or nome_eqp in selecao_nomes:
                label_completa = f"{nome_eqp} (Pat: {loc.equipamento_alugado.patrimonio})"
                if label_completa not in opcoes_patrimonios:
                    opcoes_patrimonios.append(label_completa)
        opcoes_patrimonios = sorted(opcoes_patrimonios)

        # Remove da seleção persistida qualquer patrimônio que saiu do filtro de equipamento
        st.session_state["pats_selecionados"] = {
            p for p in st.session_state["pats_selecionados"] if p in opcoes_patrimonios
        }

        # --- FILTRO 2: PATRIMÔNIOS, dentro de um popover + tabela com checkbox (escalável p/ muitos itens) ---
        with col_f2:
            qtd_sel = len(st.session_state["pats_selecionados"])
            with st.popover(f"🏷️ Patrimônios ({qtd_sel} selecionados)", width="stretch"):
                busca_pat = st.text_input(
                    "🔎 Buscar patrimônio/equipamento:", key="busca_pat_tempo",
                    placeholder="Digite para filtrar a lista abaixo",
                )

                opcoes_visiveis = (
                    [o for o in opcoes_patrimonios if busca_pat.lower() in o.lower()]
                    if busca_pat else opcoes_patrimonios
                )

                col_sel_all, col_clear_all = st.columns(2)
                if col_sel_all.button("☑️ Selecionar todos (visíveis)", width='stretch', key="sel_all_pat"):
                    st.session_state["pats_selecionados"].update(opcoes_visiveis)
                    st.rerun()
                if col_clear_all.button("🧹 Limpar seleção", width='stretch', key="clear_all_pat"):
                    st.session_state["pats_selecionados"].clear()
                    st.rerun()

                if opcoes_visiveis:
                    df_pat_editor = pd.DataFrame({
                        "Selecionado": [p in st.session_state["pats_selecionados"] for p in opcoes_visiveis],
                        "Patrimônio / Equipamento": opcoes_visiveis,
                    })

                    df_editado = st.data_editor(
                        df_pat_editor,
                        hide_index=True,
                        width='stretch',
                        height=min(38 * (len(opcoes_visiveis) + 1), 280),  # altura cresce até um teto, depois rola
                        column_config={
                            "Selecionado": st.column_config.CheckboxColumn("✔️", width="small"),
                            "Patrimônio / Equipamento": st.column_config.TextColumn(disabled=True),
                        },
                        key="editor_pats_tempo",
                    )

                    novos_marcados = set(df_editado.loc[df_editado["Selecionado"], "Patrimônio / Equipamento"])
                    novos_desmarcados = set(opcoes_visiveis) - novos_marcados

                    st.session_state["pats_selecionados"] |= novos_marcados
                    st.session_state["pats_selecionados"] -= novos_desmarcados
                else:
                    st.caption("Nenhum patrimônio encontrado para essa busca.")

        selecao_pats = [p for p in opcoes_patrimonios if p in st.session_state["pats_selecionados"]]

        if selecao_pats:  # <--- CORREÇÃO AQUI: voltou a usar selecao_pats
            dados_linha = []
            for loc in locacoes:
                if not loc.equipamento_alugado: continue
                
                label_eqp = f"{loc.equipamento_alugado.nome} (Pat: {loc.equipamento_alugado.patrimonio})"
                if label_eqp in selecao_pats:
                    valor_bruto = parse_moeda(loc.valor)
                    qtd = loc.numero_faturamentos or 1
                    valor_parcela = valor_bruto / qtd if qtd > 0 else 0
                    
                    freq = loc.faturamento
                    base_date = loc.previsao_coleta or date.today()
                    
                    # Projeta as faturas e datas
                    for i in range(1, qtd + 1):
                        f_date = calcular_data_fatura(base_date, freq, i)
                        dados_linha.append({
                            "Data da Fatura": pd.to_datetime(f_date),
                            "Equipamento": label_eqp,
                            "Valor Faturado": valor_parcela
                        })
            
            if dados_linha:
                df_linha = pd.DataFrame(dados_linha)
                df_linha = df_linha.groupby(["Data da Fatura", "Equipamento"])["Valor Faturado"].sum().reset_index()

                # --- CÁLCULO DO TOTAL ---
                total_selecionado = df_linha["Valor Faturado"].sum()
                
                # Exibe o card de valor total
                col_total1, col_total2 = st.columns([3, 1])
                with col_total2:
                    st.metric(
                        label="💰 Valor Total da Projeção Selecionada", 
                        value=f"R$ {total_selecionado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    )

                # Criação do gráfico com Plotly (usando o df_linha agrupado)
                fig = px.line(
                    df_linha, 
                    x="Data da Fatura", 
                    y="Valor Faturado", 
                    color="Equipamento",
                    markers=True,
                    title="Projeção de Faturamento por Equipamento"
                )

                # Ajuste dos rótulos para formato BR (usando a técnica de replace)
                df_linha['Valor_Br'] = df_linha['Valor Faturado'].apply(
                    lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
                
                fig.update_traces(
                    text=df_linha['Valor_Br'],
                    texttemplate='%{text}', 
                    textposition="top center", 
                    line_shape='spline', 
                    line_width=3
                )
                
                fig.update_layout(
                    hovermode="x unified",
                    template="plotly_white",
                    xaxis_title="Data da Fatura",
                    yaxis_title="Valor Projetado (R$)",
                    legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="left", x=0)
                )

                # Formatação dos eixos para padrão brasileiro
                fig.update_yaxes(tickprefix="R$ ", tickformat=",.2f")
                fig.update_xaxes(tickformat="%d/%m/%Y")

                st.plotly_chart(fig, width="stretch") 

            else:
                st.warning("Não há projeções para os itens selecionados.")
        else:
            st.info("Nenhum patrimônio selecionado. Abra o filtro '🏷️ Patrimônios' acima para escolher.")

    # --- ABA 3: TABELA EXCEL ---
    with tab_tabela:
        dados_fin = []
        max_faturas = 0 

        for loc in locacoes:
            valor_bruto = parse_moeda(loc.valor)
            qtd_faturas = loc.numero_faturamentos if loc.numero_faturamentos else 1
            valor_parcela = valor_bruto / qtd_faturas if qtd_faturas > 0 else 0
            
            freq = loc.faturamento
            base_date = loc.previsao_coleta if loc.previsao_coleta else date.today()
            
            if qtd_faturas > max_faturas:
                max_faturas = qtd_faturas

            row_data = {
                "Equipamento": loc.equipamento_alugado.nome,
                "Patrimônio": loc.equipamento_alugado.patrimonio,
                "Cliente": loc.cliente_responsavel.nome if loc.cliente_responsavel else "—",
                "Processo PMC": loc.processo_pmc,
                "Contrato": loc.contrato,
                "NF 1": loc.nf1,
                "NF 2": loc.nf2,
                "Status": loc.status,
                "Valor Bruto": f"R$ {valor_bruto:,.2f}",
                "Previsão Coleta": loc.previsao_coleta.strftime("%d/%m/%Y") if loc.previsao_coleta else "",
                "Data Coleta": loc.data_coleta.strftime("%d/%m/%Y") if loc.data_coleta else "",
                "Frequência Fat.": loc.faturamento,
                "Nº Faturas": qtd_faturas,
                "Data 1ª Fatura": loc.data_prox_fatura.strftime("%d/%m/%Y") if loc.data_prox_fatura else "",
            }
            
            for i in range(1, qtd_faturas + 1):
                f_date = calcular_data_fatura(base_date, freq, i)
                row_data[f"{i}ª Fatura"] = f"{f_date.strftime('%d/%m/%Y')} - R$ {valor_parcela:,.2f}"

            dados_fin.append(row_data)

        df_fin = pd.DataFrame(dados_fin)
        
        if not df_fin.empty:
            cols_base = ["Equipamento", "Patrimônio", "Cliente", "Processo PMC", "Contrato", "NF 1", "NF 2", "Status", "Valor Bruto", "Previsão Coleta", "Data Coleta", "Frequência Fat.", "Nº Faturas", "Data 1ª Fatura"]
            cols_faturas = [f"{i}ª Fatura" for i in range(1, max_faturas + 1)]
            
            todas_cols = cols_base + cols_faturas
            for col in cols_faturas:
                if col not in df_fin.columns:
                    df_fin[col] = ""
                    
            df_fin = df_fin[todas_cols].fillna("")
        
        st.dataframe(df_fin, width='stretch', hide_index=True)

        # Nome do arquivo com a data de hoje
        nome_arquivo = f"controle_equipamentos_{date.today().strftime('%d-%m-%Y')}.xlsx"

        st.markdown("#### 📥 Exportar Relatório Excel")
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_fin.to_excel(writer, index=False, sheet_name='Financeiro')
                
                # Acessa os objetos workbook e worksheet para estilizar
                workbook = writer.book
                worksheet = writer.sheets['Financeiro']
                
                # 1. Criar formato para o cabeçalho (Azul claro com texto branco/bold)
                header_format = workbook.add_format({
                    'bold': True,
                    'text_wrap': True,
                    'valign': 'top',
                    'fg_color': '#ADD8E6',  # Azul claro (LightBlue)
                    'border': 1
                })
                
                # Aplicar o formato no cabeçalho
                for col_num, value in enumerate(df_fin.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    
                # 2. Ajustar largura das colunas automaticamente
                for i, col in enumerate(df_fin.columns):
                    # Encontra o comprimento máximo do texto na coluna
                    column_len = max(
                        df_fin[col].astype(str).map(len).max(),
                        len(col)
                    ) + 2  # Adiciona uma margem extra
                    worksheet.set_column(i, i, column_len)

            st.download_button(
                label="📥 Baixar em .XLSX (Formatado)",
                data=output.getvalue(),
                file_name=nome_arquivo, # Nome dinâmico configurado acima
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        except Exception as e:
            st.error(f"Erro ao gerar Excel: {e}")
            # Fallback para CSV caso algo falhe
            csv = df_fin.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
            st.download_button(
                label="📥 Baixar Relatório (CSV Excel)",
                data=csv,
                file_name=f"relatorio_{date.today()}.csv",
                mime="text/csv"
            )

# ==========================================
# RODAPÉ GLOBAL FIXO
# ==========================================
st.markdown("""
<style>
    .rodape-custom {
        position: fixed;
        bottom: 0; left: 0; width: 100%;
        background-color: var(--azul-background, #0F172A);
        color: white; text-align: center;
        padding: 12px 0; font-size: 14px; font-weight: 500;
        box-shadow: 0 -2px 5px rgba(0,0,0,0.1);
    }
    .block-container { padding-bottom: 80px !important; }
</style>
<div class="rodape-custom">PMC Serviços - 2026 <br>Todos direitos reservados</div>
""", unsafe_allow_html=True)