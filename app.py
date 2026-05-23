import streamlit as st
import pandas as pd
import folium
import html
import sqlite3
import hashlib
import secrets
import base64
from io import BytesIO
from pathlib import Path

from streamlit_folium import st_folium
import streamlit.components.v1 as components
from datetime import datetime

from utils import (
    normalizar_endereco,
    encontrar_coluna,
    ordenar_paradas_inteligente,
    ordenar_paradas_por_regiao,
    calcular_km_rota,
    calcular_tempo_horas,
    formatar_tempo,
    exportar_excel,
    encontrar_proxima_parada
)
from auth import (
    existem_usuarios as auth_existem_usuarios,
    exibir_cadastro_admin_inicial as auth_exibir_cadastro_admin_inicial,
    exibir_login as auth_exibir_login,
    exibir_sidebar_usuario as auth_exibir_sidebar_usuario,
    exibir_gestao_usuarios as auth_exibir_gestao_usuarios,
    usuario_tem_acesso as auth_usuario_tem_acesso,
    carregar_usuarios as auth_carregar_usuarios
)
from dashboard import exibir_dashboard_gerencial as dashboard_exibir_gerencial
from database import (
    inicializar_banco as db_inicializar_banco,
    salvar_operacao as db_salvar_operacao,
    carregar_historico as db_carregar_historico,
    carregar_dados_dashboard as db_carregar_dados_dashboard
)
from operacoes import (
    exibir_historico_operacional as operacoes_exibir_historico
)

DB_PATH = "torre_express.db"
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logo.png"


def haversine_metros(lat1, lon1, lat2, lon2):
    """Calcula distância em metros entre dois pontos GPS."""
    import math
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def detectar_pacotes_fora_de_rota(pacotes_df, col_lat, col_lon, limiar_metros=300):
    """
    Recebe o DataFrame de pacotes de uma parada e retorna uma lista de índices
    cujas coordenadas estão a mais de limiar_metros do centroide do grupo.
    Retorna lista vazia se a parada tiver menos de 2 pacotes com coordenadas válidas.
    """
    lats = pd.to_numeric(pacotes_df[col_lat], errors="coerce")
    lons = pd.to_numeric(pacotes_df[col_lon], errors="coerce")
    validos = lats.notna() & lons.notna() & (lats != 0) & (lons != 0)

    if validos.sum() < 2:
        return []

    lat_centro = lats[validos].mean()
    lon_centro = lons[validos].mean()

    fora = []
    for idx in pacotes_df[validos].index:
        dist = haversine_metros(lat_centro, lon_centro, lats[idx], lons[idx])
        if dist > limiar_metros:
            fora.append((idx, int(round(dist))))

    return fora  # lista de (idx, distancia_metros)


def exibir_logo_principal(width=280):

    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH.resolve()), width=width)
    else:
        st.title("Torre Express Driver")


def configurar_pwa():

    components.html(
        """
        <script>
            const head = window.parent.document.head;

            function ensureLink(rel, href, attrs = {}) {
                const existing = head.querySelector(`link[rel="${rel}"][href="${href}"]`);
                if (existing) return;

                const link = window.parent.document.createElement("link");
                link.rel = rel;
                link.href = href;

                Object.entries(attrs).forEach(([key, value]) => {
                    link.setAttribute(key, value);
                });

                head.appendChild(link);
            }

            function ensureMeta(name, content) {
                let meta = head.querySelector(`meta[name="${name}"]`);
                if (!meta) {
                    meta = window.parent.document.createElement("meta");
                    meta.name = name;
                    head.appendChild(meta);
                }
                meta.content = content;
            }

            ensureLink("manifest", "/app/static/manifest.json");
            ensureLink("icon", "/app/static/icon.svg", { type: "image/svg+xml" });
            ensureLink("apple-touch-icon", "/app/static/icon.svg");

            ensureMeta("theme-color", "#0b1f3a");
            ensureMeta("mobile-web-app-capable", "yes");
            ensureMeta("apple-mobile-web-app-capable", "yes");
            ensureMeta("apple-mobile-web-app-title", "Torre Driver");
            ensureMeta("apple-mobile-web-app-status-bar-style", "black-translucent");

            if ("serviceWorker" in window.parent.navigator) {
                window.parent.navigator.serviceWorker
                    .register("/app/static/sw.js")
                    .catch(() => {});
            }
        </script>
        """,
        height=0,
        width=0
    )


def formatar_coord_baixa(valor):

    if pd.isna(valor):
        return ""

    return f"{float(valor):.6f}"


def inicializar_banco():

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_pacotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spx TEXT,
                endereco TEXT,
                status TEXT,
                horario_baixa TEXT,
                ocorrencia TEXT,
                observacao TEXT,
                latitude REAL,
                longitude REAL,
                data_operacao TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL
            )
            """
        )

        colunas_historico = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(historico_pacotes)"
            ).fetchall()
        }

        novas_colunas = {
            "usuario_id": "INTEGER",
            "usuario_nome": "TEXT",
            "usuario_perfil": "TEXT",
            "ocorrencia": "TEXT"
        }

        for coluna, tipo in novas_colunas.items():
            if coluna not in colunas_historico:
                conn.execute(
                    f"ALTER TABLE historico_pacotes ADD COLUMN {coluna} {tipo}"
                )

        conn.commit()


# Funções de autenticação centralizadas no auth.py



inicializar_banco = db_inicializar_banco
salvar_operacao = db_salvar_operacao
carregar_historico = db_carregar_historico
carregar_dados_dashboard = db_carregar_dados_dashboard
existem_usuarios = auth_existem_usuarios
usuario_tem_acesso = auth_usuario_tem_acesso
carregar_usuarios = auth_carregar_usuarios
exibir_cadastro_admin_inicial = auth_exibir_cadastro_admin_inicial
exibir_login = auth_exibir_login
exibir_sidebar_usuario = auth_exibir_sidebar_usuario
exibir_gestao_usuarios = auth_exibir_gestao_usuarios
exibir_dashboard_gerencial = dashboard_exibir_gerencial
exibir_historico_operacional = operacoes_exibir_historico


def exibir_resumo_rota():

    st.subheader("Resumo da Rota")

    if "df_rota" not in st.session_state:
        st.info("Carregue um romaneio na Operação para visualizar o resumo da rota.")
        return

    df_resumo = st.session_state.df_rota.copy()

    col_lat_resumo = encontrar_coluna(df_resumo, ["latitude", "lat"])
    col_lon_resumo = encontrar_coluna(df_resumo, ["longitude", "lng", "lon"])
    col_endereco_resumo = encontrar_coluna(
        df_resumo,
        ["destination address", "endereço", "endereco", "address"]
    )
    col_spx_resumo = encontrar_coluna(
        df_resumo,
        ["spx tn", "spx", "tracking", "rastreio", "pedido"]
    )

    if (
        col_lat_resumo is None
        or col_lon_resumo is None
        or col_endereco_resumo is None
        or col_spx_resumo is None
    ):
        st.warning("Não foi possível montar o resumo com as colunas atuais.")
        return

    if "_Endereco_Normalizado" not in df_resumo.columns:
        df_resumo["_Endereco_Normalizado"] = (
            df_resumo[col_endereco_resumo].apply(normalizar_endereco)
        )

    if "Status" not in df_resumo.columns:
        df_resumo["Status"] = "Pendente"

    total_pacotes = len(df_resumo)
    entregues = len(df_resumo[df_resumo["Status"] == "Entregue"])
    recusados = len(df_resumo[df_resumo["Status"] == "Recusado"])
    pendentes = len(df_resumo[df_resumo["Status"] == "Pendente"])
    finalizados = entregues + recusados
    sla = int((entregues / total_pacotes) * 100) if total_pacotes > 0 else 0
    progresso = finalizados / total_pacotes if total_pacotes > 0 else 0

    agregacao = {
        col_spx_resumo: "count",
        col_endereco_resumo: "first",
        col_lat_resumo: "mean",
        col_lon_resumo: "mean"
    }

    if "Bairro" in df_resumo.columns:
        agregacao["Bairro"] = "first"

    if "City" in df_resumo.columns:
        agregacao["City"] = "first"

    paradas_base_resumo = (
        df_resumo.groupby("_Endereco_Normalizado")
        .agg(agregacao)
        .reset_index()
    )

    lat_resumo = st.session_state.get("lat_motorista", -26.9194)
    lon_resumo = st.session_state.get("lon_motorista", -49.0661)
    velocidade_resumo = st.session_state.get("velocidade_media", 35)

    paradas_resumo = ordenar_paradas_por_regiao(
        paradas_base_resumo,
        col_lat_resumo,
        col_lon_resumo,
        lat_resumo,
        lon_resumo
    )
    paradas_resumo["Ordem"] = range(1, len(paradas_resumo) + 1)

    km_resumo = calcular_km_rota(
        paradas_resumo,
        col_lat_resumo,
        col_lon_resumo,
        lat_resumo,
        lon_resumo
    )
    tempo_resumo = calcular_tempo_horas(km_resumo, velocidade_resumo)

    ocorrencias = 0
    if "Ocorrencia" in df_resumo.columns:
        ocorrencias = len(df_resumo[df_resumo["Ocorrencia"].fillna("") != ""])

    colunas_pod_resumo = [
        "POD_Foto",
        "POD_Recebedor",
        "POD_Assinatura",
        "POD_Horario_Entrega"
    ]
    colunas_pod_existentes = [
        coluna for coluna in colunas_pod_resumo
        if coluna in df_resumo.columns
    ]
    pods = 0
    if colunas_pod_existentes:
        pods = int(
            df_resumo[colunas_pod_existentes]
            .fillna("")
            .astype(str)
            .ne("")
            .any(axis=1)
            .sum()
        )

    col1, col2, col3 = st.columns(3)
    col1.metric("Pacotes", total_pacotes)
    col2.metric("Paradas", len(paradas_resumo))
    col3.metric("SLA", f"{sla}%")

    col4, col5, col6 = st.columns(3)
    col4.metric("Entregues", entregues)
    col5.metric("Pendentes", pendentes)
    col6.metric("Recusados", recusados)

    col7, col8, col9 = st.columns(3)
    col7.metric("KM estimado", f"{km_resumo:.2f}")
    col8.metric("Tempo", formatar_tempo(tempo_resumo))
    col9.metric("Ocorrências", ocorrencias)

    st.caption(f"PODs registrados: {pods}")
    st.progress(progresso)
    st.caption(f"Progresso geral: {int(progresso * 100)}%")

    if "Bairro" in df_resumo.columns:
        pendencias_bairro = (
            df_resumo[df_resumo["Status"] == "Pendente"]
            .groupby("Bairro")
            .size()
            .sort_values(ascending=False)
            .head(5)
            .reset_index(name="Pendentes")
        )

        if len(pendencias_bairro) > 0:
            st.markdown("**Regiões/bairros com mais pendências**")
            st.dataframe(
                pendencias_bairro,
                use_container_width=True,
                hide_index=True
            )

    st.markdown("**Paradas resumidas**")
    paradas_lista = paradas_resumo.head(80).copy()
    paradas_lista["Pacotes"] = paradas_lista[col_spx_resumo]
    status_paradas = (
        df_resumo
        .groupby(["_Endereco_Normalizado", "Status"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    paradas_lista = paradas_lista.merge(
        status_paradas,
        on="_Endereco_Normalizado",
        how="left"
    )

    for coluna_status in ["Entregue", "Pendente", "Recusado"]:
        if coluna_status not in paradas_lista.columns:
            paradas_lista[coluna_status] = 0

    colunas_resumo = [
        "Ordem",
        "_Regiao_Operacional",
        col_endereco_resumo,
        "Pacotes",
        "Entregue",
        "Pendente",
        "Recusado"
    ]

    if "Bairro" in paradas_lista.columns:
        colunas_resumo.insert(2, "Bairro")

    st.dataframe(
        paradas_lista[colunas_resumo],
        use_container_width=True,
        hide_index=True
    )

    if len(paradas_resumo) > len(paradas_lista):
        st.caption(
            f"Mostrando 80 de {len(paradas_resumo)} paradas para manter a tela rápida."
        )


def exibir_sobre_plataforma():

    exibir_logo_principal(width=290)
    st.subheader("Torre Express Driver")
    st.caption("Plataforma Operacional Inteligente | Versão v1.0")

    with st.container(border=True):
        st.write(
            "Plataforma operacional inteligente para entregas urbanas, "
            "focada em fluidez operacional, experiência do motorista e "
            "organização inteligente de rotas."
        )

    st.markdown("**Ideal para**")
    segmentos = [
        "Shopee",
        "Mercado Livre",
        "Amazon",
        "Transportadoras",
        "Distribuidoras",
        "Operações urbanas"
    ]

    for inicio in range(0, len(segmentos), 2):
        col1, col2 = st.columns(2)
        with col1:
            with st.container(border=True):
                st.write(f"**{segmentos[inicio]}**")

        if inicio + 1 < len(segmentos):
            with col2:
                with st.container(border=True):
                    st.write(f"**{segmentos[inicio + 1]}**")

    st.markdown("**Principais benefícios**")
    col_a, col_b = st.columns(2)

    with col_a:
        with st.container(border=True):
            st.write("**Redução de zigue-zague**")

        with st.container(border=True):
            st.write("**Organização por regiões operacionais**")

        with st.container(border=True):
            st.write("**Melhor aproveitamento da rota**")

    with col_b:
        with st.container(border=True):
            st.write("**Mais produtividade operacional**")

        with st.container(border=True):
            st.write("**Experiência mobile-first**")

    with st.container(border=True):
        st.markdown("**Contato comercial**")
        st.write("E-mail: contato.torreexpress@gmail.com")
        st.write("Telefone: (47) 98833-9355")

    st.caption("Torre Express Driver © 2026")


def exibir_distribuicao_rotas():

    if not usuario_tem_acesso("admin", "gestor"):
        st.error("Acesso restrito a admin e gestor.")
        return

    st.subheader("Distribuição de Rotas")

    if "df_rota" not in st.session_state:
        st.info("Carregue ou crie uma rota na Operação antes de distribuir.")
        return

    df_distribuicao = st.session_state.df_rota

    col_lat_dist = st.session_state.get("col_lat")
    col_lon_dist = st.session_state.get("col_lon")
    col_endereco_dist = st.session_state.get("col_endereco")
    col_spx_dist = st.session_state.get("col_spx")

    if (
        col_lat_dist is None
        or col_lon_dist is None
        or col_endereco_dist is None
        or col_spx_dist is None
    ):
        st.warning("Não foi possível identificar as colunas da rota carregada.")
        return

    if "_Endereco_Normalizado" not in df_distribuicao.columns:
        df_distribuicao["_Endereco_Normalizado"] = (
            df_distribuicao[col_endereco_dist].apply(normalizar_endereco)
        )

    if "Motorista_Responsavel" not in df_distribuicao.columns:
        df_distribuicao["Motorista_Responsavel"] = ""

    usuarios = carregar_usuarios()
    motoristas = usuarios[
        (usuarios["perfil"] == "motorista")
        & (usuarios["ativo"] == 1)
    ].copy()

    if len(motoristas) == 0:
        st.warning("Cadastre ao menos um usuário motorista ativo.")
        return

    nomes_motoristas = motoristas["nome"].tolist()

    agregacao = {
        col_spx_dist: "count",
        col_endereco_dist: "first",
        col_lat_dist: "mean",
        col_lon_dist: "mean"
    }

    if "Bairro" in df_distribuicao.columns:
        agregacao["Bairro"] = "first"

    if "City" in df_distribuicao.columns:
        agregacao["City"] = "first"

    paradas_base_dist = (
        df_distribuicao.groupby("_Endereco_Normalizado")
        .agg(agregacao)
        .reset_index()
    )

    paradas_dist = ordenar_paradas_por_regiao(
        paradas_base_dist,
        col_lat_dist,
        col_lon_dist,
        st.session_state.get("lat_motorista", -26.9194),
        st.session_state.get("lon_motorista", -49.0661)
    )
    paradas_dist["Ordem"] = range(1, len(paradas_dist) + 1)

    atribuicoes = (
        df_distribuicao.groupby("_Endereco_Normalizado")["Motorista_Responsavel"]
        .first()
        .to_dict()
    )
    paradas_dist["Motorista_Responsavel"] = (
        paradas_dist["_Endereco_Normalizado"]
        .map(atribuicoes)
        .fillna("")
    )

    st.markdown("**Atribuir regiões**")
    motorista_regiao = st.selectbox(
        "Motorista",
        nomes_motoristas,
        key="dist_motorista_regiao"
    )

    regioes_opcoes = []
    for regiao, grupo in paradas_dist.groupby("_Regiao_Operacional", sort=False):
        pacotes_regiao = int(
            df_distribuicao[
                df_distribuicao["_Endereco_Normalizado"].isin(
                    grupo["_Endereco_Normalizado"]
                )
            ].shape[0]
        )
        regioes_opcoes.append(
            (
                regiao,
                f"Região {regiao} - {len(grupo)} parada(s), {pacotes_regiao} pacote(s)"
            )
        )

    regioes_label_para_id = {
        label: regiao for regiao, label in regioes_opcoes
    }

    regioes_escolhidas = st.multiselect(
        "Regiões/paradas agrupadas",
        list(regioes_label_para_id.keys()),
        key="dist_regioes"
    )

    if st.button("Atribuir regiões selecionadas"):
        regioes_ids = [
            regioes_label_para_id[label]
            for label in regioes_escolhidas
        ]
        chaves = paradas_dist[
            paradas_dist["_Regiao_Operacional"].isin(regioes_ids)
        ]["_Endereco_Normalizado"]

        mask = st.session_state.df_rota["_Endereco_Normalizado"].isin(chaves)
        st.session_state.df_rota.loc[
            mask,
            "Motorista_Responsavel"
        ] = motorista_regiao
        st.success("Região(ões) atribuída(s).")
        st.rerun()

    st.markdown("**Mover paradas entre motoristas**")
    motorista_parada = st.selectbox(
        "Mover para motorista",
        nomes_motoristas,
        key="dist_motorista_parada"
    )

    opcoes_paradas = []
    for _, row in paradas_dist.iterrows():
        atual = row.get("Motorista_Responsavel", "") or "Sem motorista"
        label = (
            f"#{int(row['Ordem'])} | Região {row.get('_Regiao_Operacional', '-')} | "
            f"{row[col_endereco_dist]} | Atual: {atual}"
        )
        opcoes_paradas.append((row["_Endereco_Normalizado"], label))

    parada_label_para_chave = {
        label: chave for chave, label in opcoes_paradas
    }

    paradas_escolhidas = st.multiselect(
        "Paradas",
        list(parada_label_para_chave.keys()),
        key="dist_paradas"
    )

    if st.button("Mover paradas selecionadas"):
        chaves = [
            parada_label_para_chave[label]
            for label in paradas_escolhidas
        ]
        mask = st.session_state.df_rota["_Endereco_Normalizado"].isin(chaves)
        st.session_state.df_rota.loc[
            mask,
            "Motorista_Responsavel"
        ] = motorista_parada
        st.success("Parada(s) movida(s).")
        st.rerun()

    st.markdown("**Resumo da distribuição**")
    resumo = (
        st.session_state.df_rota
        .assign(
            Motorista_Responsavel=st.session_state.df_rota[
                "Motorista_Responsavel"
            ].replace("", "Sem motorista")
        )
        .groupby("Motorista_Responsavel")
        .size()
        .reset_index(name="Pacotes")
    )
    st.dataframe(resumo, use_container_width=True, hide_index=True)


inicializar_banco()

st.set_page_config(
    page_title="Torre Express Driver",
    page_icon="T",
    layout="wide"
)

configurar_pwa()

if "usuario_logado" not in st.session_state:
    exibir_login()
    st.stop()

exibir_sidebar_usuario()

perfil_logado = st.session_state["usuario_logado"]["perfil"]

exibir_logo_principal()
st.markdown(
    """
    <style>
        /* Esconder toolbar do Streamlit (Fork, GitHub) */
        header[data-testid="stHeader"] {
            display: none !important;
        }
        div[data-testid="stToolbar"] {
            display: none !important;
        }
        #MainMenu {
            display: none !important;
        }
        footer {
            display: none !important;
        }
        :root {
            --torre-azul: #0b1f3a;
            --torre-azul-2: #12355b;
            --torre-laranja: #f97316;
            --torre-laranja-2: #ea580c;
            --torre-fundo: #f3f4f6;
            --torre-card: #ffffff;
            --torre-borda: #e5e7eb;
            color-scheme: light;
        }

        html, body, [class*="css"] {
            color-scheme: light;
        }

        .stApp {
            background: var(--torre-fundo);
            color: #111827;
        }

        .stApp p,
        .stApp label,
        .stApp span,
        .stApp div[data-testid="stMarkdownContainer"] {
            color: #111827;
        }

        .block-container {
            padding-top: 0.75rem;
            padding-bottom: 0.85rem;
            max-width: 820px;
        }

        h1 {
            font-size: 1.45rem !important;
            margin-bottom: 0.2rem !important;
        }

        h2, h3 {
            margin-top: 0.45rem !important;
            margin-bottom: 0.25rem !important;
        }

        div[data-testid="stMetric"] {
            background: var(--torre-card);
            border: 1px solid var(--torre-borda);
            border-radius: 8px;
            padding: 0.36rem 0.48rem;
        }

        section[data-testid="stSidebar"] {
            background: var(--torre-azul);
            min-width: 310px !important;
            width: 310px !important;
        }

        section[data-testid="stSidebar"] > div {
            min-width: 310px !important;
            width: 310px !important;
        }

        .sidebar-logo-shell {
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 1.05rem 0.35rem 1.15rem;
            margin: 0 auto 0.45rem;
            width: 100%;
        }

        .sidebar-logo-img {
            display: block;
            width: min(260px, 94%);
            max-width: 260px;
            height: auto;
            object-fit: contain;
            image-rendering: auto;
        }

        div[data-testid="stImage"] {
            margin-bottom: 0.7rem;
        }

        div[data-testid="stImage"] img {
            max-width: min(360px, 88vw);
            height: auto;
            object-fit: contain;
        }

        section[data-testid="stSidebar"] div[data-testid="stImage"] {
            text-align: center;
            margin: 0 auto 1rem;
        }

        section[data-testid="stSidebar"] div[data-testid="stImage"] img {
            max-width: min(235px, 94%);
            height: auto;
            object-fit: contain;
            background: #ffffff;
            border-radius: 8px;
            padding: 6px 10px;
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] {
            color: #ffffff;
        }

        section[data-testid="stSidebar"] input,
        section[data-testid="stSidebar"] textarea,
        section[data-testid="stSidebar"] div[data-baseweb="select"] span,
        section[data-testid="stSidebar"] div[data-baseweb="input"] span {
            color: #111827 !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"],
        section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"] p {
            color: rgba(255, 255, 255, 0.82) !important;
        }

        section[data-testid="stSidebar"] div[role="radiogroup"] label {
            border-radius: 8px;
        }

        div[data-testid="stVerticalBlock"] {
            gap: 0.34rem;
        }

        div[data-testid="stExpander"] {
            border-radius: 8px;
        }

        div[data-testid="stButton"] button,
        div[data-testid="stLinkButton"] a,
        div[data-testid="stDownloadButton"] button {
            min-height: 50px;
            border-radius: 10px;
            font-weight: 700;
            transition: background 160ms ease, border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
            box-shadow: 0 5px 14px rgba(15, 23, 42, 0.10);
        }

        div[data-testid="stButton"] button,
        div[data-testid="stFormSubmitButton"] button,
        div[data-testid="stDownloadButton"] button {
            background: var(--torre-laranja);
            border: 1px solid var(--torre-laranja);
            color: #ffffff;
        }

        div[data-testid="stButton"] button:hover,
        div[data-testid="stFormSubmitButton"] button:hover,
        div[data-testid="stDownloadButton"] button:hover {
            background: var(--torre-laranja-2);
            border-color: var(--torre-laranja-2);
            color: #ffffff;
            box-shadow: 0 7px 18px rgba(249, 115, 22, 0.18);
            transform: translateY(-1px);
        }

        div[data-testid="stLinkButton"] a {
            background: var(--torre-azul);
            border: 1px solid var(--torre-azul);
            color: #ffffff;
        }

        div[data-testid="stLinkButton"] a:hover {
            background: var(--torre-azul-2);
            border-color: var(--torre-azul-2);
            color: #ffffff;
            box-shadow: 0 7px 18px rgba(15, 23, 42, 0.16);
            transform: translateY(-1px);
        }

        iframe {
            border-radius: 8px;
        }

            @media (max-width: 720px) {
            section[data-testid="stSidebar"],
            section[data-testid="stSidebar"] > div {
                width: min(88vw, 310px) !important;
                min-width: min(88vw, 310px) !important;
            }

            .sidebar-logo-img {
                width: min(250px, 92%);
                max-width: 250px;
            }

            .block-container {
                padding-left: 0.65rem;
                padding-right: 0.65rem;
                max-width: 100%;
            }

            div[data-testid="column"] {
                min-width: 0 !important;
            }

            div[data-testid="stButton"] button,
            div[data-testid="stLinkButton"] a {
                min-height: 58px;
                font-size: 1rem;
            }

            div[data-testid="stMetric"] {
                padding: 0.28rem 0.35rem;
            }

            div[data-testid="stMetric"] label {
                font-size: 0.7rem !important;
            }

            div[data-testid="stMetric"] [data-testid="stMetricValue"] {
                font-size: 1.1rem !important;
            }

            div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] {
                gap: 0.3rem !important;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ── FUNDO ANIMADO (mesmo visual da tela de login) ─────────────────────────────
st.markdown(
    """
    <style>
        :root {
            --torre-azul: #0b1f3a;
            --torre-laranja: #f97316;
            --torre-fundo: #f3f4f6;
            color-scheme: light;
        }

        .stApp {
            background:
                radial-gradient(circle at 16% 14%, rgba(249, 115, 22, 0.08), transparent 22%),
                radial-gradient(circle at 86% 18%, rgba(11, 31, 58, 0.08), transparent 24%),
                linear-gradient(90deg, rgba(11, 31, 58, 0.025) 1px, transparent 1px),
                linear-gradient(0deg, rgba(11, 31, 58, 0.018) 1px, transparent 1px),
                var(--torre-fundo);
            background-size: auto, auto, 72px 72px, 72px 72px, auto;
            overflow-x: hidden;
        }

        html, body, [class*="css"] { color-scheme: light; }
        p, label, span, div, input, textarea { color: #111827; }

        [data-testid="stAppViewContainer"] > .main {
            position: relative;
            z-index: 1;
        }

        .ops-bg {
            position: fixed;
            inset: 0;
            pointer-events: none;
            overflow: hidden;
            z-index: 0;
        }

        .ops-road {
            position: absolute;
            width: 520px;
            height: 220px;
            border: 18px solid rgba(11, 31, 58, 0.055);
            border-left-color: transparent;
            border-bottom-color: transparent;
            border-radius: 55% 45% 50% 50%;
            transform: rotate(-14deg);
        }

        .ops-road::after {
            content: "";
            position: absolute;
            inset: 18px;
            border-top: 2px dashed rgba(11, 31, 58, 0.13);
            border-right: 2px dashed rgba(11, 31, 58, 0.10);
            border-radius: 55% 45% 50% 50%;
        }

        .ops-road.one  { left: -130px; top: 80px; }
        .ops-road.two  { right: -180px; bottom: 58px; transform: rotate(164deg); opacity: 0.82; }

        .ops-route {
            position: absolute;
            width: 430px;
            height: 150px;
            border-top: 3px dashed rgba(249, 115, 22, 0.22);
            border-radius: 50%;
            transform: rotate(18deg);
        }

        .ops-route.one { left: 8%;  bottom: 16%; }
        .ops-route.two { right: 9%; top: 19%; width: 340px; transform: rotate(-21deg); opacity: 0.70; }

        .ops-pin {
            position: absolute;
            width: 13px;
            height: 13px;
            border-radius: 50% 50% 50% 0;
            background: rgba(249, 115, 22, 0.30);
            transform: rotate(-45deg);
            box-shadow: 0 0 0 6px rgba(249, 115, 22, 0.055);
        }

        .ops-pin::after {
            content: "";
            position: absolute;
            width: 5px; height: 5px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.84);
            left: 4px; top: 4px;
        }

        .ops-pin.a { left: 15%;  top: 31%; }
        .ops-pin.b { right: 18%; top: 42%; background: rgba(11, 31, 58, 0.24); box-shadow: 0 0 0 6px rgba(11, 31, 58, 0.045); }
        .ops-pin.c { left: 72%;  bottom: 20%; opacity: 0.75; }

        .ops-vehicle {
            position: absolute;
            width: 38px; height: 19px;
            border-radius: 7px 9px 6px 6px;
            background: rgba(11, 31, 58, 0.20);
            box-shadow: inset 12px 0 0 rgba(249, 115, 22, 0.16);
        }

        .ops-vehicle::before,
        .ops-vehicle::after {
            content: "";
            position: absolute;
            bottom: -4px;
            width: 7px; height: 7px;
            border-radius: 50%;
            background: rgba(11, 31, 58, 0.18);
        }

        .ops-vehicle::before { left: 7px; }
        .ops-vehicle::after  { right: 7px; }

        .ops-vehicle.a { left: 21%;  bottom: 25%; transform: rotate(9deg); }
        .ops-vehicle.b { right: 23%; top: 28%;    transform: rotate(-15deg); opacity: 0.75; }

        @media (max-width: 720px) {
            .ops-bg { opacity: 0.62; }
            .ops-road.one  { left: -260px; top: 90px; }
            .ops-road.two  { right: -300px; bottom: 34px; }
            .ops-route.one { left: -120px; bottom: 12%; }
            .ops-route.two, .ops-vehicle.b, .ops-pin.b { display: none; }
        }
    </style>
    <div class="ops-bg" aria-hidden="true">
        <div class="ops-road one"></div>
        <div class="ops-road two"></div>
        <div class="ops-route one"></div>
        <div class="ops-route two"></div>
        <span class="ops-pin a"></span>
        <span class="ops-pin b"></span>
        <span class="ops-pin c"></span>
        <span class="ops-vehicle a"></span>
        <span class="ops-vehicle b"></span>
    </div>
    """,
    unsafe_allow_html=True
)
# ── FIM FUNDO ANIMADO ─────────────────────────────────────────────────────────

# ── SISTEMA OFFLINE ───────────────────────────────────────────────────────────
import streamlit.components.v1 as _components

_components.html("""
<script>
(function() {

  const CACHE_KEY   = "torre_express_rota_v1";
  const FILA_KEY    = "torre_express_fila_v1";
  const STATUS_KEY  = "torre_express_online_v1";

  // ── Banner de conexão ────────────────────────────────────────────────────
  function criarBanner() {
    if (document.getElementById("te-conexao-banner")) return;
    const b = document.createElement("div");
    b.id = "te-conexao-banner";
    b.style.cssText = [
      "position:fixed","top:0","left:0","width:100%","z-index:99999",
      "text-align:center","padding:6px 12px","font-size:13px",
      "font-weight:700","font-family:Arial,sans-serif",
      "transition:background 0.4s,opacity 0.4s","pointer-events:none"
    ].join(";");
    document.body.appendChild(b);
    return b;
  }

  function atualizarBanner(online) {
    const b = criarBanner();
    if (!b) return;
    if (online) {
      b.textContent = "✅ Conexão restaurada — dados sincronizados";
      b.style.background = "#166534";
      b.style.color       = "#fff";
      b.style.opacity     = "1";
      setTimeout(() => { b.style.opacity = "0"; }, 3500);
    } else {
      b.textContent = "⚠️ Sem conexão — baixas salvas localmente e sincronizadas ao reconectar";
      b.style.background = "#f97316";
      b.style.color       = "#fff";
      b.style.opacity     = "1";
    }
  }

  // ── Detectar mudança de conexão ──────────────────────────────────────────
  function online()  { localStorage.setItem(STATUS_KEY, "1"); atualizarBanner(true);  tentarSincronizar(); }
  function offline() { localStorage.setItem(STATUS_KEY, "0"); atualizarBanner(false); }

  window.addEventListener("online",  online);
  window.addEventListener("offline", offline);

  // Verificar estado atual ao carregar
  if (!navigator.onLine) atualizarBanner(false);

  // ── Salvar rota no localStorage ──────────────────────────────────────────
  window.teSalvarRota = function(jsonStr) {
    try { localStorage.setItem(CACHE_KEY, jsonStr); } catch(e) {}
  };

  // ── Adicionar baixa à fila offline ──────────────────────────────────────
  window.teAdicionarFila = function(baixa) {
    // baixa = {idx, status, horario, ocorrencia}
    try {
      const fila = JSON.parse(localStorage.getItem(FILA_KEY) || "[]");
      fila.push(baixa);
      localStorage.setItem(FILA_KEY, JSON.stringify(fila));
    } catch(e) {}
  };

  // ── Ler fila offline para o Python processar ─────────────────────────────
  window.teLerFila = function() {
    try { return localStorage.getItem(FILA_KEY) || "[]"; } catch(e) { return "[]"; }
  };

  // ── Limpar fila após sincronização ───────────────────────────────────────
  window.teLimparFila = function() {
    try { localStorage.removeItem(FILA_KEY); } catch(e) {}
  };

  // ── Ler rota em cache ────────────────────────────────────────────────────
  window.teLerRota = function() {
    try { return localStorage.getItem(CACHE_KEY) || ""; } catch(e) { return ""; }
  };

  // ── Tentar sincronizar ao voltar o sinal ─────────────────────────────────
  function tentarSincronizar() {
    const fila = JSON.parse(localStorage.getItem(FILA_KEY) || "[]");
    if (fila.length === 0) return;
    // Envia para o Streamlit via URL param para ser processado no próximo rerun
    const url = new URL(window.location.href);
    url.searchParams.set("sincronizar_offline", "1");
    // Usa postMessage para comunicar com o iframe do Streamlit
    window.parent.postMessage({type: "streamlit:setComponentValue", value: "sincronizar"}, "*");
  }

  // Verificar se há fila pendente ao carregar com conexão
  if (navigator.onLine) {
    const fila = JSON.parse(localStorage.getItem(FILA_KEY) || "[]");
    if (fila.length > 0) {
      setTimeout(() => atualizarBanner(true), 1000);
    }
  }

})();
</script>
""", height=0, scrolling=False)
# ── FIM SISTEMA OFFLINE ───────────────────────────────────────────────────────

if perfil_logado == "motorista":
    opcoes_menu = ["Operação", "Resumo da Rota", "Sobre a Plataforma"]
elif perfil_logado == "gestor":
    opcoes_menu = [
        "Operação",
        "Distribuição de Rotas",
        "Resumo da Rota",
        "Dashboard",
        "Histórico",
        "Sobre a Plataforma",
        "Configurações"
    ]
else:
    opcoes_menu = [
        "Operação",
        "Distribuição de Rotas",
        "Resumo da Rota",
        "Dashboard",
        "Histórico",
        "Usuários",
        "Sobre a Plataforma",
        "Configurações"
    ]

if st.session_state.get("menu_principal") not in opcoes_menu:
    st.session_state.pop("menu_principal", None)

pagina_atual = st.sidebar.radio(
    "Menu",
    opcoes_menu,
    key="menu_principal"
)

if pagina_atual == "Resumo da Rota":
    exibir_resumo_rota()
    st.stop()

if pagina_atual == "Distribuição de Rotas":
    exibir_distribuicao_rotas()
    st.stop()

if pagina_atual == "Dashboard":
    dashboard_exibir_gerencial()
    st.stop()

if pagina_atual == "Histórico":
    exibir_historico_operacional()
    st.stop()

if pagina_atual == "Usuários":
    exibir_gestao_usuarios()
    st.stop()

if pagina_atual == "Sobre a Plataforma":
    exibir_sobre_plataforma()
    st.stop()

if pagina_atual == "Configurações":
    st.subheader("Configurações")

    with st.container(border=True):
        st.markdown("**Instalar no celular**")
        st.write(
            "O Torre Express Driver já possui estrutura básica de PWA para "
            "uso como aplicativo instalado na tela inicial do celular."
        )

    col_android, col_iphone = st.columns(2)

    with col_android:
        with st.container(border=True):
            st.markdown("**Android / Chrome**")
            st.write("1. Abra o app no navegador.")
            st.write("2. Toque nos três pontos do Chrome.")
            st.write("3. Toque em Adicionar à tela inicial ou Instalar app.")

    with col_iphone:
        with st.container(border=True):
            st.markdown("**iPhone / Safari**")
            st.write("1. Abra o app no Safari.")
            st.write("2. Toque em Compartilhar.")
            st.write("3. Toque em Adicionar à Tela de Início.")

    with st.container(border=True):
        st.markdown("**Preparação para APK Android**")
        st.caption(
            "A estrutura atual pode ser usada futuramente dentro de um WebView "
            "Android ou TWA. O app continua rodando em Streamlit com manifest, "
            "ícone, cor de tema e service worker básico para assets estáticos."
        )
    st.stop()

if "upload_romaneio_versao" not in st.session_state:
    st.session_state.upload_romaneio_versao = 0

df_base_manual = None

if (
    st.session_state.get("rota_carregada", False)
    and "romaneio_bytes" in st.session_state
):
    arquivo = BytesIO(st.session_state.romaneio_bytes)
else:
    # Layout mobile-first para motorista
    if perfil_logado == "motorista":
        st.markdown(
            """
            <style>
            .mobile-upload-card {
                background: #ffffff;
                border: 2px dashed #f97316;
                border-radius: 16px;
                padding: 2rem 1.5rem;
                text-align: center;
                margin: 1rem 0;
            }
            .mobile-upload-title {
                font-size: 1.4rem;
                font-weight: 700;
                color: #0b1f3a;
                margin-bottom: 0.5rem;
            }
            .mobile-upload-sub {
                font-size: 0.95rem;
                color: #6b7280;
                margin-bottom: 1.5rem;
            }
            .mobile-opcao-btn {
                background: #f3f4f6;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                padding: 1rem;
                margin-bottom: 0.75rem;
                cursor: pointer;
                width: 100%;
                text-align: left;
                font-size: 1rem;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        nome_motorista = st.session_state["usuario_logado"]["nome"].split()[0]
        st.markdown(
            f"""
            <div style="text-align:center; padding: 1rem 0 0.5rem;">
                <div style="font-size:1.6rem; font-weight:700; color:#0b1f3a;">
                    Olá, {nome_motorista}! 👋
                </div>
                <div style="font-size:1rem; color:#6b7280; margin-top:0.3rem;">
                    Pronto para iniciar suas entregas?
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        origem_rota = st.radio(
            "Qual é o seu romaneio?",
            [
                "📦 Tenho uma planilha da Shopee / Mercado Livre",
                "📋 Tenho uma planilha organizada",
                "✏️ Vou digitar os endereços um a um"
            ],
            key="origem_nova_rota"
        )

        arquivo = None

        if origem_rota in [
            "📦 Tenho uma planilha da Shopee / Mercado Livre",
            "📋 Tenho uma planilha organizada"
        ]:
            st.markdown(
                """
                <div style="background:#fff7ed; border:1px solid #fed7aa;
                     border-radius:12px; padding:1rem; margin-bottom:1rem;
                     font-size:0.9rem; color:#9a3412;">
                    📲 Salve a planilha no celular e selecione abaixo
                </div>
                """,
                unsafe_allow_html=True
            )
            arquivo = st.file_uploader(
                "Selecionar planilha",
                type=["xlsx"],
                key=f"upload_romaneio_{st.session_state.upload_romaneio_versao}",
                label_visibility="collapsed"
            )

    else:
        st.subheader("Nova Rota")
        origem_rota = st.radio(
            "Como deseja criar a rota?",
            [
                "Tenho uma planilha da Shopee / Mercado Livre",
                "Tenho uma planilha organizada",
                "Vou digitar os endereços um a um"
            ],
            horizontal=True,
            key="origem_nova_rota"
        )

        arquivo = None

        if origem_rota in ["Tenho uma planilha da Shopee / Mercado Livre", "Tenho uma planilha organizada", "📦 Tenho uma planilha da Shopee / Mercado Livre", "📋 Tenho uma planilha organizada"]:
            arquivo = st.file_uploader(
                "Envie a planilha da rota",
                type=["xlsx"],
                key=f"upload_romaneio_{st.session_state.upload_romaneio_versao}"
            )
        else:
            if "entregas_manuais" not in st.session_state:
                st.session_state.entregas_manuais = []

            with st.form("form_entrega_manual", clear_on_submit=True):
                st.markdown("**Cadastrar entrega**")

                col_m1, col_m2 = st.columns(2)

                with col_m1:
                    codigo_pedido = st.text_input("Código do pedido")
                    cliente = st.text_input("Cliente")
                    telefone = st.text_input("Telefone")
                    endereco_manual = st.text_input("Endereço")
                    complemento = st.text_input("Complemento")

                with col_m2:
                    bairro = st.text_input("Bairro")
                    cidade = st.text_input("Cidade")
                    latitude_manual = st.number_input(
                        "Latitude",
                        value=float(st.session_state.get("lat_motorista", -26.9194)),
                        format="%.6f"
                    )
                    longitude_manual = st.number_input(
                        "Longitude",
                        value=float(st.session_state.get("lon_motorista", -49.0661)),
                        format="%.6f"
                    )
                    motorista_responsavel = st.text_input(
                        "Motorista responsável",
                        value=st.session_state["usuario_logado"]["nome"]
                    )

                observacao_manual = st.text_area("Observação", height=70)
                adicionar_entrega = st.form_submit_button("Adicionar entrega")

            if adicionar_entrega:
                if not codigo_pedido or not endereco_manual:
                    st.error("Informe pelo menos código do pedido e endereço.")
                else:
                    st.session_state.entregas_manuais.append(
                        {
                            "Codigo Pedido": codigo_pedido,
                            "Cliente": cliente,
                            "Telefone": telefone,
                            "Endereco": endereco_manual,
                            "Complemento": complemento,
                            "Bairro": bairro,
                            "City": cidade,
                            "Latitude": latitude_manual,
                            "Longitude": longitude_manual,
                            "Observacao": observacao_manual,
                            "Motorista_Responsavel": motorista_responsavel
                        }
                    )
                    st.success("Entrega adicionada.")

            if len(st.session_state.entregas_manuais) > 0:
                st.dataframe(
                    pd.DataFrame(st.session_state.entregas_manuais),
                    use_container_width=True,
                    hide_index=True
                )

                col_iniciar_manual, col_limpar_manual = st.columns(2)

                with col_iniciar_manual:
                    if st.button("Iniciar rota manual"):
                        df_base_manual = pd.DataFrame(
                            st.session_state.entregas_manuais
                        )

                with col_limpar_manual:
                    if st.button("Limpar entregas manuais"):
                        st.session_state.entregas_manuais = []
                        st.rerun()

if not arquivo and df_base_manual is None:
    st.info("Crie uma nova rota ou carregue uma planilha para iniciar a operação.")
    st.stop()

if arquivo or df_base_manual is not None:

    if arquivo is not None and hasattr(arquivo, "getvalue"):
        st.session_state.romaneio_bytes = arquivo.getvalue()

    if df_base_manual is not None:
        df_base = df_base_manual.copy()
        buffer_manual = BytesIO()
        df_base.to_excel(buffer_manual, index=False)
        buffer_manual.seek(0)
        st.session_state.romaneio_bytes = buffer_manual.getvalue()
    else:
        df_base = pd.read_excel(arquivo)

    origem_atual_rota = st.session_state.get("origem_nova_rota")

    if origem_atual_rota == "Importar planilha padrão":
        col_pedido_padrao = encontrar_coluna(
            df_base,
            ["codigo do pedido", "código do pedido", "codigo", "código", "pedido"]
        )
        col_cliente_padrao = encontrar_coluna(
            df_base,
            ["cliente", "nome"]
        )
        col_telefone_padrao = encontrar_coluna(
            df_base,
            ["telefone", "celular", "phone", "contato"]
        )
        col_endereco_padrao = encontrar_coluna(
            df_base,
            ["endereço", "endereco", "address", "logradouro"]
        )
        col_complemento_padrao = encontrar_coluna(
            df_base,
            ["complemento", "complement"]
        )
        col_bairro_padrao = encontrar_coluna(
            df_base,
            ["bairro", "district"]
        )
        col_cidade_padrao = encontrar_coluna(
            df_base,
            ["cidade", "city", "municipio", "município"]
        )
        col_observacao_padrao = encontrar_coluna(
            df_base,
            ["observação", "observacao", "obs", "nota"]
        )
        col_lat_padrao = encontrar_coluna(
            df_base,
            ["latitude", "lat"]
        )
        col_lon_padrao = encontrar_coluna(
            df_base,
            ["longitude", "lng", "lon"]
        )

        if col_pedido_padrao is None or col_endereco_padrao is None:
            st.error(
                "A planilha padrão precisa ter pelo menos código do pedido e endereço."
            )
            st.stop()

        lat_padrao = float(st.session_state.get("lat_motorista", -26.9194))
        lon_padrao = float(st.session_state.get("lon_motorista", -49.0661))

        df_padrao = pd.DataFrame()
        df_padrao["Codigo Pedido"] = df_base[col_pedido_padrao]
        df_padrao["Cliente"] = (
            df_base[col_cliente_padrao]
            if col_cliente_padrao is not None
            else ""
        )
        df_padrao["Telefone"] = (
            df_base[col_telefone_padrao]
            if col_telefone_padrao is not None
            else ""
        )
        df_padrao["Endereco"] = df_base[col_endereco_padrao]
        df_padrao["Complemento"] = (
            df_base[col_complemento_padrao]
            if col_complemento_padrao is not None
            else ""
        )
        df_padrao["Bairro"] = (
            df_base[col_bairro_padrao]
            if col_bairro_padrao is not None
            else ""
        )
        df_padrao["City"] = (
            df_base[col_cidade_padrao]
            if col_cidade_padrao is not None
            else ""
        )
        df_padrao["Observacao"] = (
            df_base[col_observacao_padrao]
            if col_observacao_padrao is not None
            else ""
        )
        df_padrao["Latitude"] = (
            pd.to_numeric(df_base[col_lat_padrao], errors="coerce")
            if col_lat_padrao is not None
            else lat_padrao
        )
        df_padrao["Longitude"] = (
            pd.to_numeric(df_base[col_lon_padrao], errors="coerce")
            if col_lon_padrao is not None
            else lon_padrao
        )
        df_padrao["Latitude"] = df_padrao["Latitude"].fillna(lat_padrao)
        df_padrao["Longitude"] = df_padrao["Longitude"].fillna(lon_padrao)
        df_padrao["Motorista_Responsavel"] = st.session_state[
            "usuario_logado"
        ]["nome"]

        df_base = df_padrao

    col_lat = encontrar_coluna(
        df_base,
        ["latitude", "lat"]
    )

    col_lon = encontrar_coluna(
        df_base,
        ["longitude", "lng", "lon"]
    )

    col_endereco = encontrar_coluna(
        df_base,
        ["destination address", "endereço", "endereco", "address"]
    )

    col_spx = encontrar_coluna(
        df_base,
        ["spx tn", "spx", "tracking", "rastreio", "pedido"]
    )

    col_sequencia = encontrar_coluna(
        df_base,
        ["sequencia", "sequência", "seq", "sequence", "ordem"]
    )

    if col_lat is None or col_lon is None:
        # Tentar geocodificar usando Google Maps API
        google_key = st.secrets.get("GOOGLE_MAPS_KEY", "")
        if not google_key:
            st.error("Planilha sem coordenadas e chave do Google Maps não configurada.")
            st.stop()

        if col_endereco is None:
            st.error("Não encontrei coluna de endereço para geocodificar.")
            st.stop()

        import requests

        st.info("Geocodificando endereços automaticamente... Aguarde.")

        lats = []
        lons = []
        erros = 0

        for _, row in df_base.iterrows():
            endereco_geo = str(row.get(col_endereco if col_endereco else "", ""))
            if not endereco_geo or endereco_geo == "nan":
                lats.append(None)
                lons.append(None)
                erros += 1
                continue
            try:
                resp = requests.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": endereco_geo, "key": google_key},
                    timeout=5
                )
                resultado = resp.json()
                if resultado.get("status") == "OK":
                    loc = resultado["results"][0]["geometry"]["location"]
                    lats.append(loc["lat"])
                    lons.append(loc["lng"])
                else:
                    lats.append(None)
                    lons.append(None)
                    erros += 1
            except Exception:
                lats.append(None)
                lons.append(None)
                erros += 1

        df_base["Latitude"] = lats
        df_base["Longitude"] = lons

        lat_padrao = float(st.session_state.get("lat_motorista", -26.9194))
        lon_padrao = float(st.session_state.get("lon_motorista", -49.0661))
        df_base["Latitude"] = pd.to_numeric(df_base["Latitude"], errors="coerce").fillna(lat_padrao)
        df_base["Longitude"] = pd.to_numeric(df_base["Longitude"], errors="coerce").fillna(lon_padrao)

        col_lat = "Latitude"
        col_lon = "Longitude"

        if erros > 0:
            st.warning(f"{erros} endereço(s) não foram geocodificados e usarão a localização padrão.")
        else:
            st.success("Todos os endereços foram geocodificados com sucesso!")


    if col_endereco is None:
        st.error("Não encontrei coluna de endereço.")
        st.stop()

    if col_spx is None:
        st.error("Não encontrei coluna SPX.")
        st.stop()

    if "df_rota" not in st.session_state:

        if "Status" not in df_base.columns:
            df_base["Status"] = "Pendente"

        if "Horario_Baixa" not in df_base.columns:
            df_base["Horario_Baixa"] = ""

        if "Observacao" not in df_base.columns:
            df_base["Observacao"] = ""

        if "Ocorrencia" not in df_base.columns:
            df_base["Ocorrencia"] = ""

        if "POD_Foto" not in df_base.columns:
            df_base["POD_Foto"] = ""

        if "POD_Foto_Nome" not in df_base.columns:
            df_base["POD_Foto_Nome"] = ""

        if "POD_Recebedor" not in df_base.columns:
            df_base["POD_Recebedor"] = ""

        if "POD_Assinatura" not in df_base.columns:
            df_base["POD_Assinatura"] = ""

        if "POD_Horario_Entrega" not in df_base.columns:
            df_base["POD_Horario_Entrega"] = ""

        if "POD_Latitude_Baixa" not in df_base.columns:
            df_base["POD_Latitude_Baixa"] = ""

        if "POD_Longitude_Baixa" not in df_base.columns:
            df_base["POD_Longitude_Baixa"] = ""

        if "ENL_Foto" not in df_base.columns:
            df_base["ENL_Foto"] = ""

        if "ENL_Foto_Nome" not in df_base.columns:
            df_base["ENL_Foto_Nome"] = ""

        if "ENL_Observacao" not in df_base.columns:
            df_base["ENL_Observacao"] = ""

        if "ENL_Lat" not in df_base.columns:
            df_base["ENL_Lat"] = ""

        if "ENL_Lon" not in df_base.columns:
            df_base["ENL_Lon"] = ""

        df_base["_Endereco_Normalizado"] = (
            df_base[col_endereco]
            .apply(normalizar_endereco)
        )

        st.session_state.df_rota = df_base

        buffer_rota = BytesIO()
        df_base.to_excel(buffer_rota, index=False)
        buffer_rota.seek(0)
        st.session_state.romaneio_bytes = buffer_rota.getvalue()

        st.session_state.rota_iniciada = False
        st.session_state.rota_carregada = True
        st.session_state.col_lat = col_lat
        st.session_state.col_lon = col_lon
        st.session_state.col_endereco = col_endereco
        st.session_state.col_spx = col_spx
        st.session_state.col_sequencia = col_sequencia
        st.session_state.pop("entregas_manuais", None)

    df = st.session_state.df_rota

    # ── CACHE OFFLINE DA ROTA ─────────────────────────────────────────────────
    try:
        import json as _json
        _cols_offline = [c for c in [
            col_spx, col_endereco, col_lat, col_lon,
            "Status", "Ocorrencia", "Horario_Baixa", "_Endereco_Normalizado"
        ] if c in df.columns]
        _df_cache = df[_cols_offline].copy()
        _df_cache = _df_cache.fillna("").astype(str)
        _rota_json = _df_cache.to_json(orient="records", force_ascii=False)
        _components.html(
            f"""<script>
            if(window.teSalvarRota) window.teSalvarRota({_json.dumps(_rota_json)});
            </script>""",
            height=0, scrolling=False
        )
    except Exception:
        pass

    # ── AVISO DE MAPA OFFLINE ─────────────────────────────────────────────────
    if not st.session_state.get("aviso_mapa_offline_visto"):
        st.info(
            "📴 **Dica para áreas sem sinal:** Baixe o mapa da sua região no Google Maps "
            "antes de sair. Abra o Google Maps → toque na foto do perfil → "
            "**Mapas off-line** → Selecione a área. "
            "As baixas feitas sem sinal serão salvas automaticamente e sincronizadas ao reconectar.",
            icon="🗺️"
        )
        if st.button("✅ Entendi, não mostrar novamente", key="fechar_aviso_offline"):
            st.session_state["aviso_mapa_offline_visto"] = True
            st.rerun()
    # ── FIM CACHE OFFLINE ─────────────────────────────────────────────────────

    if "Motorista_Responsavel" not in df.columns:
        df["Motorista_Responsavel"] = ""

    col_nova_rota, col_resetar_rota = st.columns(2)

    with col_nova_rota:
        if st.button("Nova rota / Trocar romaneio", key="trocar_romaneio"):
            st.session_state["confirmar_nova_rota"] = True

    if st.session_state.get("confirmar_nova_rota"):
        st.warning("⚠️ Isso vai apagar a rota atual. Tem certeza?")
        col_sim, col_nao = st.columns(2)
        with col_sim:
            if st.button("✅ Sim, trocar rota", key="confirmar_nova_rota_sim", type="primary", use_container_width=True):
                chaves_rota = [
                    "df_rota", "rota_carregada", "rota_iniciada", "romaneio_bytes",
                    "col_lat", "col_lon", "col_endereco", "col_spx", "col_sequencia",
                    "regiao_operacional_ativa", "regiao_concluida_alerta",
                    "paradas_puladas", "chave_rota_cerco", "paradas_cerco",
                    "entregas_manuais", "confirmar_nova_rota"
                ]
                for chave_rota in chaves_rota:
                    st.session_state.pop(chave_rota, None)
                for chave_estado in list(st.session_state.keys()):
                    if str(chave_estado).startswith("carregar_pacotes_"):
                        st.session_state.pop(chave_estado, None)
                st.session_state.upload_romaneio_versao += 1
                st.rerun()
        with col_nao:
            if st.button("❌ Cancelar", key="cancelar_nova_rota", use_container_width=True):
                st.session_state.pop("confirmar_nova_rota", None)
                st.rerun()

    with col_resetar_rota:
        if st.button("Resetar rota", key="resetar_rota"):
            st.session_state["confirmar_resetar"] = True

    if st.session_state.get("confirmar_resetar"):
        st.warning("⚠️ Isso vai resetar todos os status para Pendente. Tem certeza?")
        col_sim2, col_nao2 = st.columns(2)
        with col_sim2:
            if st.button("✅ Sim, resetar", key="confirmar_resetar_sim", type="primary", use_container_width=True):
                st.session_state.df_rota["Status"] = "Pendente"
                st.session_state.pop("regiao_operacional_ativa", None)
                st.session_state.pop("regiao_concluida_alerta", None)
                st.session_state.pop("paradas_puladas", None)
                st.session_state.pop("confirmar_resetar", None)
                for chave_estado in list(st.session_state.keys()):
                    if str(chave_estado).startswith("carregar_pacotes_"):
                        st.session_state.pop(chave_estado, None)
                st.success("Status resetado.")
                st.rerun()
        with col_nao2:
            if st.button("❌ Cancelar", key="cancelar_resetar", use_container_width=True):
                st.session_state.pop("confirmar_resetar", None)
                st.rerun()

    if "Status" not in df.columns:
        df["Status"] = "Pendente"

    if "Horario_Baixa" not in df.columns:
        df["Horario_Baixa"] = ""

    if "Observacao" not in df.columns:
        df["Observacao"] = ""

    if "Ocorrencia" not in df.columns:
        df["Ocorrencia"] = ""

    colunas_pod = [
        "POD_Foto",
        "POD_Foto_Nome",
        "POD_Recebedor",
        "POD_Assinatura",
        "POD_Horario_Entrega",
        "POD_Latitude_Baixa",
        "POD_Longitude_Baixa",
        "ENL_Foto",
        "ENL_Foto_Nome",
        "ENL_Observacao",
        "ENL_Lat",
        "ENL_Lon"
    ]

    for coluna_pod in colunas_pod:
        if coluna_pod not in df.columns:
            df[coluna_pod] = ""

    usuario_atual = st.session_state["usuario_logado"]

    if usuario_atual["perfil"] == "motorista":
        atribuicoes_existentes = (
            df["Motorista_Responsavel"]
            .fillna("")
            .astype(str)
            .str.strip()
            != ""
        )

        if atribuicoes_existentes.any():
            df = df[
                df["Motorista_Responsavel"]
                .fillna("")
                .astype(str)
                .str.strip()
                == usuario_atual["nome"]
            ].copy()

            if len(df) == 0:
                st.info("Nenhuma parada atribuída para seu usuário nesta rota.")
                st.stop()

    if "SPX TN" not in df.columns:
        df["SPX TN"] = df[col_spx]

    df["_SPX_Busca"] = (
        df[col_spx]
        .astype(str)
        .str.upper()
    )

    nomes_colunas_busca = {
        "spx tn",
        "spx",
        "pedido",
        "código",
        "codigo",
        "tracking",
        "rastreio",
        "sku",
        "cliente",
        "telefone",
        "endereço",
        "endereco",
        "destination address",
        "observação",
        "observacao",
        "observacoes",
        "observações",
        "observacao_inicial",
        "observação_inicial",
        "Observacao"
    }
    colunas_busca_pedido = [
        coluna for coluna in df.columns
        if str(coluna).strip().lower() in nomes_colunas_busca
    ]

    for coluna_obrigatoria_busca in [col_spx, col_endereco]:
        if (
            coluna_obrigatoria_busca is not None
            and coluna_obrigatoria_busca not in colunas_busca_pedido
        ):
            colunas_busca_pedido.append(coluna_obrigatoria_busca)

    df["_Pedido_Busca"] = (
        df[colunas_busca_pedido]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.upper()
    )

    opcoes_ocorrencia = [
        "",
        "Cliente ausente",
        "Sem contato",
        "Endereço não localizado",
        "Área de risco",
        "Estabelecimento fechado",
        "Reagendado",
        "Cliente recusou",
        "Outros"
    ]

    st.sidebar.title(" Torre Driver")

    ocultar_entregues = st.sidebar.checkbox(
        "Ocultar entregues",
        value=True
    )

    if usuario_tem_acesso("admin", "gestor"):
        lat_motorista = st.sidebar.number_input(
            "Latitude atual",
            value=float(st.session_state.get("lat_motorista", -26.9194)),
            format="%.6f"
        )
        lon_motorista = st.sidebar.number_input(
            "Longitude atual",
            value=float(st.session_state.get("lon_motorista", -49.0661)),
            format="%.6f"
        )
        velocidade_media = st.sidebar.slider(
            "Velocidade média",
            min_value=10,
            max_value=80,
            value=int(st.session_state.get("velocidade_media", 35))
        )
        st.session_state.lat_motorista = lat_motorista
        st.session_state.lon_motorista = lon_motorista
        st.session_state.velocidade_media = velocidade_media
    else:
        lat_motorista = float(st.session_state.get("lat_motorista", -26.9194))
        lon_motorista = float(st.session_state.get("lon_motorista", -49.0661))
        velocidade_media = int(st.session_state.get("velocidade_media", 35))

    busca_pedido = st.sidebar.text_input(
        "Buscar pedido",
        placeholder="Digite pedido, pacote, SKU, cliente ou endereço"
    ).strip()

    lat_baixa = formatar_coord_baixa(lat_motorista)
    lon_baixa = formatar_coord_baixa(lon_motorista)

    def salvar_snapshot_operacional():

        try:
            total_auto, data_auto = salvar_operacao(
                df,
                col_spx,
                col_endereco,
                col_lat,
                col_lon,
                st.session_state["usuario_logado"]
            )
            st.session_state["ultimo_autosalvamento"] = (
                f"{total_auto} pacote(s) em {data_auto}"
            )
        except Exception as erro:
            st.session_state["erro_autosalvamento"] = str(erro)

    def atualizar_status_pacote(idx_pacote, novo_status):

        horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        st.session_state.df_rota.loc[idx_pacote, "Status"] = novo_status

        if novo_status == "Entregue":
            st.session_state.df_rota.loc[idx_pacote, "Ocorrencia"] = ""
            st.session_state.df_rota.loc[idx_pacote, "Horario_Baixa"] = horario
            st.session_state.df_rota.loc[
                idx_pacote,
                "POD_Horario_Entrega"
            ] = horario
            st.session_state.df_rota.loc[
                idx_pacote,
                "POD_Latitude_Baixa"
            ] = lat_baixa
            st.session_state.df_rota.loc[
                idx_pacote,
                "POD_Longitude_Baixa"
            ] = lon_baixa

        elif novo_status == "Recusado":
            ocorrencia_salvar = st.session_state.df_rota.loc[
                idx_pacote,
                "Ocorrencia"
            ]
            if (
                pd.isna(ocorrencia_salvar)
                or str(ocorrencia_salvar).strip() == ""
            ):
                st.session_state.df_rota.loc[
                    idx_pacote,
                    "Ocorrencia"
                ] = "Outros"

            st.session_state.df_rota.loc[idx_pacote, "Horario_Baixa"] = horario
            st.session_state.df_rota.loc[
                idx_pacote,
                "POD_Latitude_Baixa"
            ] = lat_baixa
            st.session_state.df_rota.loc[
                idx_pacote,
                "POD_Longitude_Baixa"
            ] = lon_baixa

        else:
            st.session_state.df_rota.loc[idx_pacote, "Ocorrencia"] = ""
            st.session_state.df_rota.loc[idx_pacote, "Horario_Baixa"] = ""
            for coluna_pod_limpar in [
                "POD_Horario_Entrega",
                "POD_Foto",
                "POD_Foto_Nome",
                "POD_Recebedor",
                "POD_Assinatura",
                "POD_Latitude_Baixa",
                "POD_Longitude_Baixa",
                "ENL_Foto",
                "ENL_Foto_Nome",
                "ENL_Observacao",
                "ENL_Lat",
                "ENL_Lon"
            ]:
                st.session_state.df_rota.loc[idx_pacote, coluna_pod_limpar] = ""

        salvar_snapshot_operacional()

        # ── Atualizar cache offline no localStorage ───────────────────────
        try:
            import json as _json2
            _cols_off = [c for c in [
                col_spx, col_endereco, col_lat, col_lon,
                "Status", "Ocorrencia", "Horario_Baixa", "_Endereco_Normalizado"
            ] if c in st.session_state.df_rota.columns]
            _df_off = st.session_state.df_rota[_cols_off].fillna("").astype(str)
            _json_off = _df_off.to_json(orient="records", force_ascii=False)
            _components.html(
                f"""<script>
                if(window.teSalvarRota) window.teSalvarRota({_json2.dumps(_json_off)});
                </script>""",
                height=0, scrolling=False
            )
        except Exception:
            pass
        # ── FIM cache offline ─────────────────────────────────────────────

    entregues = len(
        df[df["Status"] == "Entregue"]
    )

    recusados = len(
        df[df["Status"] == "Recusado"]
    )

    pendentes = len(
        df[df["Status"] == "Pendente"]
    )

    sla = int(
        (entregues / total_pacotes) * 100
    ) if total_pacotes > 0 else 0

    status_por_parada = (
        df.groupby(["_Endereco_Normalizado", "Status"])
        .size()
        .unstack(fill_value=0)
    )

    for status_coluna in ["Entregue", "Pendente", "Recusado"]:
        if status_coluna not in status_por_parada.columns:
            status_por_parada[status_coluna] = 0

    total_por_parada = df.groupby("_Endereco_Normalizado").size()
    pacotes_por_parada = {
        chave: grupo
        for chave, grupo in df.groupby("_Endereco_Normalizado", sort=False)
    }

    agregacao = {
        col_spx: "count",
        col_endereco: "first",
        col_lat: "mean",
        col_lon: "mean"
    }

    if "Bairro" in df.columns:
        agregacao["Bairro"] = "first"

    if "City" in df.columns:
        agregacao["City"] = "first"

    paradas_base = (
        df.groupby("_Endereco_Normalizado")
        .agg(agregacao)
        .reset_index()
    )

    colunas_chave_rota = [
        "_Endereco_Normalizado",
        col_lat,
        col_lon
    ]

    if "Bairro" in paradas_base.columns:
        colunas_chave_rota.append("Bairro")

    chave_rota = (
        round(float(lat_motorista), 6),
        round(float(lon_motorista), 6),
        tuple(
            pd.util.hash_pandas_object(
                paradas_base[colunas_chave_rota],
                index=False
            ).astype(str)
        )
    )

    if st.session_state.get("chave_rota_cerco") == chave_rota:
        paradas = st.session_state["paradas_cerco"].copy()
    else:
        paradas = ordenar_paradas_por_regiao(
            paradas_base,
            col_lat,
            col_lon,
            lat_motorista,
            lon_motorista
        )
        st.session_state["chave_rota_cerco"] = chave_rota
        st.session_state["paradas_cerco"] = paradas.copy()

    paradas["Ordem"] = range(
        1,
        len(paradas) + 1
    )

    total_paradas = len(paradas)

    km_inteligente = calcular_km_rota(
        paradas,
        col_lat,
        col_lon,
        lat_motorista,
        lon_motorista
    )

    tempo_inteligente = calcular_tempo_horas(
        km_inteligente,
        velocidade_media
    )

    modo_foco_entrega = st.toggle(
        "Modo Foco de Entrega",
        key="modo_foco_entrega",
        help="Mostra apenas a próxima parada e ações principais."
    )

    paradas_puladas = set(st.session_state.get("paradas_puladas", []))
    chaves_pendentes = set(
        status_por_parada[
            status_por_parada["Pendente"] > 0
        ].index
    )
    paradas_puladas = paradas_puladas.intersection(chaves_pendentes)
    st.session_state["paradas_puladas"] = list(paradas_puladas)

    regiao_preferida = st.session_state.get("regiao_operacional_ativa")
    proxima_parada = encontrar_proxima_parada(
        paradas,
        df,
        regiao_preferida,
        paradas_puladas
    )

    regiao_anterior = st.session_state.get("regiao_operacional_ativa")
    regiao_nova = None

    if proxima_parada is not None:
        regiao_nova = proxima_parada.get("_Regiao_Operacional", None)

    if regiao_nova != regiao_anterior:
        if regiao_anterior is not None:
            st.session_state["regiao_concluida_alerta"] = regiao_anterior

        if regiao_nova is None:
            st.session_state.pop("regiao_operacional_ativa", None)
        else:
            st.session_state["regiao_operacional_ativa"] = regiao_nova

    finalizados = entregues + recusados

    progresso_rota = (
        finalizados / total_pacotes
    ) if total_pacotes > 0 else 0
    progresso_rota_pct = (
        f"{progresso_rota * 100:.1f}%"
        if 0 < progresso_rota < 1
        else f"{int(progresso_rota * 100)}%"
    )
    paradas_pendentes_total = int(
        (status_por_parada["Pendente"] > 0).sum()
    )
    paradas_concluidas = max(total_paradas - paradas_pendentes_total, 0)
    pacotes_concluidos = finalizados

    pacotes_proxima = pd.DataFrame()
    distancia_proxima = 0
    eta_proxima = 0

    if proxima_parada is not None:

        pacotes_proxima = df[
            df["_Endereco_Normalizado"]
            == proxima_parada["_Endereco_Normalizado"]
        ]

        distancia_proxima = calcular_km_rota(
            pd.DataFrame([proxima_parada]),
            col_lat,
            col_lon,
            lat_motorista,
            lon_motorista
        )

        eta_proxima = calcular_tempo_horas(
            distancia_proxima,
            velocidade_media
        )

    st.markdown(
        """
        <style>
            .premium-shell {
                background:
                    radial-gradient(circle at 92% 0%, rgba(249, 115, 22, 0.18), transparent 32%),
                    linear-gradient(135deg, #071b34 0%, #0b1f3a 58%, #12355b 100%);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 20px;
                padding: 16px;
                color: #f9fafb;
                box-shadow: 0 14px 34px rgba(11, 31, 58, 0.18);
                margin: 4px auto 8px;
                max-width: 760px;
            }

            .premium-kicker {
                color: #fdba74;
                font-size: 0.72rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                margin-bottom: 5px;
            }

            .premium-address {
                font-size: clamp(1.08rem, 1.6vw, 1.36rem);
                font-weight: 800;
                line-height: 1.2;
                margin-bottom: 12px;
            }

            .premium-hero-grid {
                display: grid;
                grid-template-columns: minmax(0, 1.35fr) minmax(180px, 0.65fr);
                gap: 12px;
                align-items: stretch;
                margin-bottom: 12px;
            }

            .premium-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
                gap: 8px;
            }

            .premium-stat {
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
                padding: 8px 9px;
                box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
            }

            .premium-stat.featured {
                display: flex;
                flex-direction: column;
                justify-content: center;
                min-height: 76px;
                background: rgba(255, 255, 255, 0.15);
            }

            .premium-stat span {
                display: block;
                color: #d8e2ee;
                font-size: 0.68rem;
                margin-bottom: 4px;
            }

            .premium-stat strong {
                display: block;
                color: #ffffff;
                font-size: 0.9rem;
            }

            .premium-stat.featured strong {
                font-size: clamp(1.12rem, 2vw, 1.55rem);
            }

            .premium-section-title {
                color: #fdba74;
                font-size: 0.72rem;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                margin: 12px 0 7px;
            }

            .premium-progress-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 10px;
            }

            .premium-progress-card {
                background: rgba(255, 255, 255, 0.11);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 13px;
                padding: 10px;
            }

            .premium-progress-head {
                display: flex;
                justify-content: space-between;
                gap: 10px;
                color: #d8e2ee;
                font-size: 0.76rem;
                margin-bottom: 7px;
            }

            .premium-progress-head strong {
                color: #ffffff;
            }

            .premium-bar {
                height: 8px;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.16);
                overflow: hidden;
            }

            .premium-bar-fill {
                height: 100%;
                border-radius: 999px;
                background: linear-gradient(90deg, #f97316, #fdba74);
            }

            .route-progress {
                margin: 0 0 10px;
            }

            div[data-testid="stLinkButton"] a,
            div[data-testid="stButton"] button {
                min-height: 52px;
                width: 100%;
                opacity: 1;
                border-radius: 11px;
                box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
            }

            div[data-testid="stLinkButton"] a {
                background: #f97316 !important;
                border: 1px solid #f97316 !important;
                color: #ffffff !important;
            }

            div[data-testid="stLinkButton"] a:hover {
                background: #ea580c !important;
                border-color: #fb923c !important;
                color: #ffffff !important;
                box-shadow: 0 10px 24px rgba(249, 115, 22, 0.20);
            }

            div[data-testid="stButton"] button[kind="primary"] {
                background: #f97316 !important;
                border: 1px solid #f97316 !important;
                color: #ffffff !important;
            }

            div[data-testid="stButton"] button[kind="primary"]:hover {
                background: #ea580c !important;
                border-color: #ea580c !important;
                color: #ffffff !important;
                box-shadow: 0 10px 24px rgba(249, 115, 22, 0.20);
            }

            div[data-testid="stButton"] button[kind="secondary"] {
                background: #f97316 !important;
                border: 1px solid #fed7aa !important;
                color: #ffffff !important;
            }

            div[data-testid="stButton"] button[kind="secondary"]:hover {
                background: #ea580c !important;
                border-color: #fb923c !important;
                color: #ffffff !important;
            }

            button[aria-label="Entregue"] {
                background: #16a34a !important;
                border-color: #16a34a !important;
                color: #ffffff !important;
            }

            button[aria-label="Entregue"]:hover {
                background: #15803d !important;
                border-color: #15803d !important;
                color: #ffffff !important;
            }

            button[aria-label="Recusado"] {
                background: #dc2626 !important;
                border-color: #dc2626 !important;
                color: #ffffff !important;
            }

            button[aria-label="Recusado"]:hover {
                background: #b91c1c !important;
                border-color: #b91c1c !important;
                color: #ffffff !important;
            }

            button[aria-label="Pendente"] {
                background: #334155 !important;
                border-color: #334155 !important;
                color: #ffffff !important;
            }

            button[aria-label="Pendente"]:hover {
                background: #1e293b !important;
                border-color: #1e293b !important;
                color: #ffffff !important;
            }

            @media (max-width: 900px) {
                .premium-hero-grid,
                .premium-progress-grid {
                    grid-template-columns: 1fr;
                }

                .premium-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }

            @media (max-width: 560px) {
                .premium-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }

            }
        </style>
        """,
        unsafe_allow_html=True
    )

    if perfil_logado != "motorista":
        if perfil_logado != "motorista":
            st.subheader("Painel do Motorista")

    if proxima_parada is not None:

        ordem_proxima = int(proxima_parada["Ordem"])
        endereco_proxima = html.escape(
            str(proxima_parada[col_endereco])
        )
        total_pacotes_proxima = len(pacotes_proxima)
        entregues_proxima = len(
            pacotes_proxima[pacotes_proxima["Status"] == "Entregue"]
        )
        recusados_proxima = len(
            pacotes_proxima[pacotes_proxima["Status"] == "Recusado"]
        )
        finalizados_proxima = entregues_proxima + recusados_proxima
        progresso_parada = (
            finalizados_proxima / total_pacotes_proxima
        ) if total_pacotes_proxima > 0 else 0
        progresso_parada_pct = int(progresso_parada * 100)
        pendentes_rota = []

        for _, parada_pendente in paradas.iterrows():
            chave_pendente = parada_pendente["_Endereco_Normalizado"]
            qtd_pendentes_parada = int(
                status_por_parada.at[chave_pendente, "Pendente"]
            ) if chave_pendente in status_por_parada.index else 0

            if qtd_pendentes_parada > 0:
                pendentes_rota.append(
                    (parada_pendente, qtd_pendentes_parada)
                )

        eta_minutos = int(round(eta_proxima * 60))
        regiao_numero = proxima_parada.get("_Regiao_Operacional", "-")
        regiao_nome = proxima_parada.get("_Nome_Regiao", "-")
        bairro_proximo = proxima_parada.get("Bairro", regiao_nome)
        proxima_regiao = f"Região {regiao_numero} - {regiao_nome}"
        pendentes_regiao = [
            item for item in pendentes_rota
            if item[0].get("_Regiao_Operacional", "-") == regiao_numero
        ]
        chave_proxima_painel = proxima_parada["_Endereco_Normalizado"]
        if chave_proxima_painel in paradas_puladas:
            paradas_puladas.discard(chave_proxima_painel)
            st.session_state["paradas_puladas"] = list(paradas_puladas)

        pendentes_regiao = (
            [
                item for item in pendentes_regiao
                if item[0]["_Endereco_Normalizado"] not in paradas_puladas
            ]
            + [
                item for item in pendentes_regiao
                if item[0]["_Endereco_Normalizado"] in paradas_puladas
            ]
        )
        proximas_tres = pendentes_regiao[:3]
        paradas_pendentes_regiao = len(pendentes_regiao)
        paradas_regiao_atual = paradas[
            paradas["_Regiao_Operacional"] == regiao_numero
        ]
        chaves_regiao_atual = paradas_regiao_atual[
            "_Endereco_Normalizado"
        ].tolist()
        total_pacotes_regiao = int(
            total_por_parada.reindex(chaves_regiao_atual, fill_value=0).sum()
        )
        finalizados_regiao = int(
            status_por_parada.reindex(
                chaves_regiao_atual,
                fill_value=0
            )[["Entregue", "Recusado"]].sum().sum()
        )
        progresso_regiao = (
            finalizados_regiao / total_pacotes_regiao
        ) if total_pacotes_regiao > 0 else 0
        progresso_regiao_pct = (
            f"{progresso_regiao * 100:.1f}%"
            if 0 < progresso_regiao < 1
            else f"{int(progresso_regiao * 100)}%"
        )
        paradas_pendentes_df = paradas[
            paradas["_Endereco_Normalizado"].isin(chaves_pendentes)
        ]
        km_restante = calcular_km_rota(
            paradas_pendentes_df,
            col_lat,
            col_lon,
            lat_motorista,
            lon_motorista
        ) if len(paradas_pendentes_df) > 0 else 0
        maps_url_proxima = (
            "https://www.google.com/maps/search/?api=1"
            f"&query={proxima_parada[col_lat]},{proxima_parada[col_lon]}"
        )

        alerta_regiao = st.session_state.pop(
            "regiao_concluida_alerta",
            None
        )

        if alerta_regiao is not None and alerta_regiao != regiao_numero:
            st.success(
                f"Região {alerta_regiao} concluída. Avançando para a Região {regiao_numero}."
            )

        if perfil_logado == "motorista":
            st.markdown(
                f"""
                <div style="background:#0b1f3a;border-radius:16px;padding:1.2rem 1rem;margin-bottom:0.75rem;">
                    <div style="font-size:0.8rem;color:#f97316;font-weight:600;letter-spacing:0.05em;margin-bottom:0.3rem;">
                        PRÓXIMA ENTREGA
                    </div>
                    <div style="font-size:1.3rem;font-weight:700;color:#ffffff;margin-bottom:0.5rem;line-height:1.3;">
                        {endereco_proxima}
                    </div>
                    <div style="font-size:0.95rem;color:#cbd5e1;margin-bottom:0.75rem;">
                        📍 {bairro_proximo}
                    </div>
                    <div style="display:flex;gap:0.5rem;">
                        <div style="background:rgba(255,255,255,0.1);border-radius:8px;padding:0.5rem;flex:1;text-align:center;">
                            <div style="font-size:0.7rem;color:#94a3b8;">ETA</div>
                            <div style="font-size:1.1rem;font-weight:700;color:#ffffff;">{eta_minutos} min</div>
                        </div>
                        <div style="background:rgba(255,255,255,0.1);border-radius:8px;padding:0.5rem;flex:1;text-align:center;">
                            <div style="font-size:0.7rem;color:#94a3b8;">Distância</div>
                            <div style="font-size:1.1rem;font-weight:700;color:#ffffff;">{distancia_proxima:.1f} km</div>
                        </div>
                        <div style="background:rgba(255,255,255,0.1);border-radius:8px;padding:0.5rem;flex:1;text-align:center;">
                            <div style="font-size:0.7rem;color:#94a3b8;">Pacotes</div>
                            <div style="font-size:1.1rem;font-weight:700;color:#ffffff;">{total_pacotes_proxima}</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.info(
                f"Próxima ação recomendada: seguir para a Parada #{ordem_proxima} "
                f"na Região {regiao_numero}."
            )
            if paradas_pendentes_regiao > 1:
                st.caption(f"Ainda há {paradas_pendentes_regiao} parada(s) pendente(s) nesta região.")
            else:
                st.caption("Última parada pendente da região atual.")


        # Layout mobile-first para motorista
        if perfil_logado == "motorista":
            # Barra de progresso simples no topo
            st.markdown(
                f"""
                <div style="background:#f3f4f6;border-radius:12px;padding:0.75rem 1rem;
                            margin-bottom:0.75rem;display:flex;justify-content:space-between;
                            align-items:center;">
                    <span style="font-size:0.9rem;color:#6b7280;">Progresso</span>
                    <span style="font-size:1rem;font-weight:700;color:#0b1f3a;">
                        {pacotes_concluidos} de {total_pacotes} entregas
                    </span>
                    <span style="font-size:0.9rem;font-weight:700;color:#f97316;">
                        {progresso_rota_pct}
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.progress(min(max(progresso_rota, 0), 1))

            # Botão de navegação — largura total
            st.link_button(
                "🗺️ Navegar até este endereço",
                maps_url_proxima,
                use_container_width=True
            )

            # Botões de ação — largura total
            if st.button(
                "✅ Entregar Parada",
                key="painel_entregar_parada",
                type="primary",
                use_container_width=True
            ):
                st.session_state["confirmar_entregar_painel"] = True

            if st.session_state.get("confirmar_entregar_painel"):
                st.warning(f"⚠️ Confirmar entrega de **{total_pacotes_proxima}** pacote(s)?")
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    if st.button("✅ Confirmar", key="conf_entregar_sim", type="primary", use_container_width=True):
                        horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        mask = (
                            st.session_state.df_rota["_Endereco_Normalizado"]
                            == proxima_parada["_Endereco_Normalizado"]
                        )
                        st.session_state.df_rota.loc[mask, "Status"] = "Entregue"
                        st.session_state.df_rota.loc[mask, "Ocorrencia"] = ""
                        st.session_state.df_rota.loc[mask, "Horario_Baixa"] = horario
                        st.session_state.df_rota.loc[mask, "POD_Horario_Entrega"] = horario
                        st.session_state.df_rota.loc[mask, "POD_Latitude_Baixa"] = lat_baixa
                        st.session_state.df_rota.loc[mask, "POD_Longitude_Baixa"] = lon_baixa
                        st.session_state["alteracao_operacional_pendente"] = True
                        st.session_state.pop("confirmar_entregar_painel", None)
                        salvar_snapshot_operacional()
                        st.rerun()
                with col_e2:
                    if st.button("❌ Cancelar", key="conf_entregar_nao", use_container_width=True):
                        st.session_state.pop("confirmar_entregar_painel", None)
                        st.rerun()

        if paradas_pendentes_regiao > 1:
            if st.button(
                "⏭️ Pular Parada",
                key="painel_pular_parada",
                type="secondary",
                use_container_width=True
            ):
                puladas_atuais = set(
                    st.session_state.get("paradas_puladas", [])
                )
                puladas_atuais.add(chave_proxima_painel)
                st.session_state["paradas_puladas"] = list(puladas_atuais)
                st.info("Parada mantida como pendente e enviada para depois na região.")
                st.rerun()

        if st.button(
                "❌ Recusar Parada",
                key="painel_recusar_parada",
                type="secondary",
                use_container_width=True
            ):
                st.session_state["confirmar_recusar_painel"] = True

        if st.session_state.get("confirmar_recusar_painel"):
            st.warning(f"⚠️ Confirmar recusa de **{total_pacotes_proxima}** pacote(s)?")
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                if st.button("✅ Confirmar recusa", key="conf_recusar_sim", type="primary", use_container_width=True):
                    horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    mask = (
                        st.session_state.df_rota["_Endereco_Normalizado"]
                        == proxima_parada["_Endereco_Normalizado"]
                    )
                    st.session_state.df_rota.loc[mask, "Status"] = "Recusado"
                    st.session_state.df_rota.loc[mask, "Horario_Baixa"] = horario
                    st.session_state.df_rota.loc[mask, "POD_Horario_Entrega"] = ""
                    st.session_state.df_rota.loc[mask, "POD_Latitude_Baixa"] = lat_baixa
                    st.session_state.df_rota.loc[mask, "POD_Longitude_Baixa"] = lon_baixa
                    st.session_state.df_rota.loc[
                        mask & (st.session_state.df_rota["Ocorrencia"].fillna("") == ""),
                        "Ocorrencia"
                    ] = "Outros"
                    st.session_state["alteracao_operacional_pendente"] = True
                    st.session_state.pop("confirmar_recusar_painel", None)
                    salvar_snapshot_operacional()
                    st.rerun()
            with col_r2:
                if st.button("❌ Cancelar", key="conf_recusar_nao", use_container_width=True):
                    st.session_state.pop("confirmar_recusar_painel", None)
                    st.rerun()

        # Mostrar próximas paradas só para gestor/admin
        if perfil_logado != "motorista":
            st.caption(
                f"Parada atual: {finalizados_proxima}/{total_pacotes_proxima} pacotes finalizados"
            )
            st.progress(progresso_parada)
            st.caption(
                f"Região atual: {finalizados_regiao}/{total_pacotes_regiao} pacotes finalizados"
            )
            st.progress(progresso_regiao)

            if len(proximas_tres) > 0:
                st.caption("Próximas paradas da região")
                colunas_proximas = st.columns(len(proximas_tres), gap="small")

                for coluna_proxima, (parada_item, qtd_pendente) in zip(
                    colunas_proximas,
                    proximas_tres
                ):
                    endereco_item = str(parada_item[col_endereco])
                    regiao_item = str(parada_item.get("_Nome_Regiao", "-"))
                    bairro_item = str(parada_item.get("Bairro", regiao_item))
                    ordem_item = int(parada_item["Ordem"])

                    with coluna_proxima:
                        with st.container(border=True):
                            if ordem_item == ordem_proxima:
                                st.success(f"Atual #{ordem_item}")
                            else:
                                st.caption(f"Parada #{ordem_item}")

                            st.write(f"**{bairro_item}**")
                            st.caption(f"Região: {regiao_item}")
                            st.write(endereco_item)
                            st.caption(f"{qtd_pendente} pendente(s)")

        if modo_foco_entrega:
            if "ultimo_autosalvamento" in st.session_state:
                st.caption(
                    f"Salvo automaticamente: {st.session_state['ultimo_autosalvamento']}"
                )

            if "erro_autosalvamento" in st.session_state:
                st.warning(
                    f"Não foi possível salvar automaticamente: {st.session_state['erro_autosalvamento']}"
                )

            st.caption(
                "Modo Foco ativo. Desative o modo para voltar ao mapa, lista de paradas e exportação."
            )
            st.stop()

    else:

        alerta_regiao = st.session_state.pop(
            "regiao_concluida_alerta",
            None
        )

        if alerta_regiao is not None:
            st.success(f"Região {alerta_regiao} concluída.")

        st.success(
            "Rota finalizada. Todos os pacotes foram tratados."
        )

        if modo_foco_entrega:
            st.stop()

    if perfil_logado != "motorista":
        st.markdown('<div class="route-progress">', unsafe_allow_html=True)
        st.progress(progresso_rota)
        st.caption(
            f"{finalizados} de {total_pacotes} pacotes finalizados"
        )
        st.markdown('</div>', unsafe_allow_html=True)

        col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5, col_kpi6 = st.columns(6)
        col_kpi1.metric("Paradas", total_paradas)
        col_kpi2.metric("Pacotes", total_pacotes)
        col_kpi3.metric("Entregues", entregues)
        col_kpi4.metric("Pendentes", pendentes)
        col_kpi5.metric("Recusados", recusados)
        col_kpi6.metric("SLA geral", f"{sla}%")

        st.caption(
            f"KM rota inteligente: {km_inteligente:.2f} km | "
            f"Tempo estimado: {formatar_tempo(tempo_inteligente)}"
        )

    st.divider()
    st.subheader("Mapa operacional")

    paradas_mapa = paradas.copy().reset_index(drop=True)
    paradas_mapa["_Lat_Mapa"] = pd.to_numeric(
        paradas_mapa[col_lat],
        errors="coerce"
    )
    paradas_mapa["_Lon_Mapa"] = pd.to_numeric(
        paradas_mapa[col_lon],
        errors="coerce"
    )
    paradas_sem_coordenada = paradas_mapa[
        paradas_mapa[["_Lat_Mapa", "_Lon_Mapa"]].isna().any(axis=1)
    ]
    paradas_mapa = paradas_mapa.dropna(
        subset=["_Lat_Mapa", "_Lon_Mapa"]
    )

    coordenadas_rota = [
        [
            float(lat_motorista),
            float(lon_motorista)
        ]
    ]

    coordenadas_usadas = {}

    for _, row in paradas_mapa.iterrows():
        coordenadas_rota.append([
            float(row["_Lat_Mapa"]),
            float(row["_Lon_Mapa"])
        ])

    mapa = folium.Map(
        location=[
            float(lat_motorista),
            float(lon_motorista)
        ],
        zoom_start=14
    )

    folium.Marker(
        location=[
            float(lat_motorista),
            float(lon_motorista)
        ],
        popup="Motorista",
        tooltip="Motorista",
        icon=folium.Icon(
            color="cadetblue",
            icon="user",
            prefix="fa"
        )
    ).add_to(mapa)

    if len(coordenadas_rota) > 1:
        folium.PolyLine(
            coordenadas_rota,
            color="blue",
            weight=4,
            opacity=0.8
        ).add_to(mapa)

    chave_proxima = None

    if proxima_parada is not None:
        chave_proxima = proxima_parada["_Endereco_Normalizado"]

    for _, row in paradas_mapa.iterrows():

        chave = row["_Endereco_Normalizado"]

        endereco = row[col_endereco]
        total_parada = int(total_por_parada.get(chave, 0))
        entregues_parada = int(
            status_por_parada.at[chave, "Entregue"]
        ) if chave in status_por_parada.index else 0
        pendentes_parada = int(
            status_por_parada.at[chave, "Pendente"]
        ) if chave in status_por_parada.index else 0
        recusados_parada = int(
            status_por_parada.at[chave, "Recusado"]
        ) if chave in status_por_parada.index else 0

        if chave == chave_proxima:
            cor = "blue"
        elif recusados_parada > 0:
            cor = "red"
        elif pendentes_parada == 0:
            cor = "green"
        else:
            cor = "orange"

        lat_pin = float(row["_Lat_Mapa"])
        lon_pin = float(row["_Lon_Mapa"])
        chave_coord = (round(lat_pin, 6), round(lon_pin, 6))
        repeticao_coord = coordenadas_usadas.get(chave_coord, 0)
        coordenadas_usadas[chave_coord] = repeticao_coord + 1

        if repeticao_coord > 0:
            deslocamento = 0.00005 * repeticao_coord
            lat_pin += deslocamento
            lon_pin += deslocamento

        folium.Marker(
            location=[
                lat_pin,
                lon_pin
            ],
            popup=f"""
            <b>Parada {row['Ordem']}</b><br>
            Região {row.get('_Regiao_Operacional', '-')} - {row.get('_Nome_Regiao', '-')}<br>
            {endereco}<br>
            Pacotes: {total_parada}<br>
            Entregues: {entregues_parada}<br>
            Pendentes: {pendentes_parada}<br>
            Falhas: {recusados_parada}
            """,
            tooltip=(
                f"Parada {row['Ordem']} - "
                f"{total_parada} pacote(s)"
            ),
            icon=folium.Icon(
                color=cor,
                icon="truck",
                prefix="fa"
            )
        ).add_to(mapa)

    if len(coordenadas_rota) > 1:
        latitudes = [coord[0] for coord in coordenadas_rota]
        longitudes = [coord[1] for coord in coordenadas_rota]
        min_lat, max_lat = min(latitudes), max(latitudes)
        min_lon, max_lon = min(longitudes), max(longitudes)

        if min_lat == max_lat:
            min_lat -= 0.005
            max_lat += 0.005

        if min_lon == max_lon:
            min_lon -= 0.005
            max_lon += 0.005

        mapa.fit_bounds(
            [[min_lat, min_lon], [max_lat, max_lon]],
            padding=(30, 30)
        )
    else:
        st.warning("Não há coordenadas válidas de paradas para exibir no mapa.")

    if len(paradas_sem_coordenada) > 0:
        st.warning(
            f"{len(paradas_sem_coordenada)} parada(s) sem latitude/longitude "
            "válidas não puderam ser exibidas no mapa."
        )

    st_folium(
        mapa,
        width=1400,
        height=330,
        key=(
            f"mapa_operacional_{len(paradas_mapa)}_"
            f"{entregues}_{recusados}_{pendentes}"
        )
    )

    st.divider()

    st.subheader(" Paradas Inteligentes")

    paradas_lista = paradas

    if busca_pedido:

        busca_normalizada = busca_pedido.upper()

        pacotes_encontrados = df[
            df["_Pedido_Busca"].str.contains(
                busca_normalizada,
                na=False,
                regex=False
            )
        ]

        chaves_encontradas = pacotes_encontrados[
            "_Endereco_Normalizado"
        ].unique()

        paradas_lista = paradas[
            paradas["_Endereco_Normalizado"]
            .isin(chaves_encontradas)
        ]

        st.caption(
            f"Busca por pedido: {len(pacotes_encontrados)} pacote(s) encontrado(s)."
        )

        if len(pacotes_encontrados) == 0:
            st.warning("Nenhum pedido encontrado para a busca informada.")
        else:
            mapa_ordem_busca = paradas.set_index(
                "_Endereco_Normalizado"
            )["Ordem"].to_dict()
            resultados_busca = pacotes_encontrados.copy()
            resultados_busca["Parada"] = resultados_busca[
                "_Endereco_Normalizado"
            ].map(mapa_ordem_busca)

            colunas_resultado_busca = [
                coluna for coluna in [
                    col_spx,
                    "Status",
                    col_endereco,
                    "Parada"
                ]
                if coluna in resultados_busca.columns
            ]

            col_cliente_busca = encontrar_coluna(
                resultados_busca,
                ["cliente", "customer", "nome"]
            )
            if col_cliente_busca is not None:
                colunas_resultado_busca.insert(1, col_cliente_busca)

            st.dataframe(
                resultados_busca[colunas_resultado_busca].head(20),
                use_container_width=True,
                hide_index=True
            )

    regiao_atual = None

    for i, row in paradas_lista.iterrows():

        chave = row["_Endereco_Normalizado"]

        endereco = row[col_endereco]

        regiao_linha = row.get("_Regiao_Operacional", "-")
        nome_regiao_linha = row.get("_Nome_Regiao", "-")

        if regiao_linha != regiao_atual:
            regiao_atual = regiao_linha
            paradas_da_regiao = paradas_lista[
                paradas_lista["_Regiao_Operacional"] == regiao_linha
            ]
            chaves_da_regiao = paradas_da_regiao[
                "_Endereco_Normalizado"
            ].unique()
            qtd_paradas_regiao = len(paradas_da_regiao)
            qtd_pacotes_regiao = int(
                total_por_parada.reindex(
                    chaves_da_regiao,
                    fill_value=0
                ).sum()
            )
            st.markdown(
                f"### Região {regiao_linha} - {nome_regiao_linha}"
            )
            st.caption(
                f"{qtd_paradas_regiao} parada(s) | "
                f"{qtd_pacotes_regiao} pacote(s)"
            )
            if (
                proxima_parada is not None
                and regiao_linha
                == proxima_parada.get("_Regiao_Operacional", "-")
            ):
                st.info("Região atual")

        pacotes = pacotes_por_parada.get(chave, df.iloc[0:0])

        if ocultar_entregues:

            pacotes_visiveis = pacotes[
                pacotes["Status"] != "Entregue"
            ]

        else:

            pacotes_visiveis = pacotes

        total_parada = int(total_por_parada.get(chave, 0))
        entregues_parada = int(
            status_por_parada.at[chave, "Entregue"]
        ) if chave in status_por_parada.index else 0
        pendentes_parada = int(
            status_por_parada.at[chave, "Pendente"]
        ) if chave in status_por_parada.index else 0
        recusados_parada = int(
            status_por_parada.at[chave, "Recusado"]
        ) if chave in status_por_parada.index else 0

        sla_parada = int(
            (entregues_parada / total_parada) * 100
        ) if total_parada > 0 else 0

        if pendentes_parada == 0:
            status_parada = "Finalizada"
        elif recusados_parada > 0:
            status_parada = "Com falha"
        else:
            status_parada = "Em andamento"

        with st.container(border=True):

            st.markdown(
                f"### {int(row['Ordem'])}. {endereco}"
            )

            if (
                proxima_parada is not None
                and chave == proxima_parada["_Endereco_Normalizado"]
            ):

                st.info(
                    "Próxima parada em destaque"
                )

            bairro = row["Bairro"] if "Bairro" in row else "-"
            cidade = row["City"] if "City" in row else "-"

            st.caption(f"{bairro} - {cidade}")
            col_res1, col_res2, col_res3 = st.columns(3)
            col_res1.metric("Pacotes", total_parada)
            col_res2.metric("Pendentes", pendentes_parada)
            col_res3.metric("SLA", f"{sla_parada}%")

            if status_parada == "Finalizada":
                st.success(f"Status da parada: {status_parada}")
            elif status_parada == "Com falha":
                st.error(f"Status da parada: {status_parada}")
            else:
                st.warning(f"Status da parada: {status_parada}")

            # ── DETECTOR DE PACOTES FORA DE ROTA ───────────────────────────
            pacotes_parada_todos = pacotes_por_parada.get(chave, df.iloc[0:0])
            fora_de_rota = detectar_pacotes_fora_de_rota(
                pacotes_parada_todos, col_lat, col_lon, limiar_metros=300
            )
            if fora_de_rota:
                st.markdown(
                    f"""
                    <div style="background:#fef2f2;border:1.5px solid #fca5a5;
                         border-radius:10px;padding:0.7rem 1rem;margin-bottom:0.4rem;">
                        <span style="font-size:1rem;font-weight:700;color:#b91c1c;">
                            ⚠️ {len(fora_de_rota)} pacote(s) fora do agrupamento
                        </span><br>
                        <span style="font-size:0.85rem;color:#7f1d1d;">
                            Este(s) pacote(s) estão em endereços muito distantes
                            dos demais nesta parada. Verifique antes de entregar.
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            # ── FIM DETECTOR ────────────────────────────────────────────────

            maps_url = (
                "https://www.google.com/maps/search/?api=1"
                f"&query={row[col_lat]},{row[col_lon]}"
            )

            st.link_button(
                "Navegar até este endereço",
                maps_url,
                use_container_width=True
            )

            # ── Botões Entregar tudo / Recusar tudo — só com 2+ pendentes ──
            if pendentes_parada >= 2:
                col_a, col_b = st.columns(2)

                with col_a:
                    if st.button(
                        "Entregar tudo",
                        key=f"entregar_{i}",
                        use_container_width=True
                    ):
                        horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        mask = (
                            st.session_state.df_rota["_Endereco_Normalizado"] == chave
                        )
                        st.session_state.df_rota.loc[mask, "Status"] = "Entregue"
                        st.session_state.df_rota.loc[mask, "Ocorrencia"] = ""
                        st.session_state.df_rota.loc[mask, "Horario_Baixa"] = horario
                        st.session_state.df_rota.loc[mask, "POD_Horario_Entrega"] = horario
                        st.session_state.df_rota.loc[mask, "POD_Latitude_Baixa"] = lat_baixa
                        st.session_state.df_rota.loc[mask, "POD_Longitude_Baixa"] = lon_baixa
                        salvar_snapshot_operacional()
                        st.rerun()

                with col_b:
                    if st.button(
                        "Recusar tudo",
                        key=f"recusar_{i}",
                        use_container_width=True
                    ):
                        st.session_state[f"recusar_tudo_aberto_{i}"] = True

                # Ocorrência inline ao recusar tudo
                if st.session_state.get(f"recusar_tudo_aberto_{i}"):
                    st.warning("Selecione a ocorrência para recusar todos os pacotes:")
                    ocorrencia_tudo = st.selectbox(
                        "Ocorrência",
                        [o for o in opcoes_ocorrencia if o != ""],
                        key=f"ocorrencia_tudo_{i}"
                    )
                    col_ct1, col_ct2 = st.columns(2)
                    with col_ct1:
                        if st.button(
                            "✅ Confirmar recusa",
                            key=f"confirmar_recusar_tudo_{i}",
                            type="primary",
                            use_container_width=True
                        ):
                            horario = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                            mask = (
                                st.session_state.df_rota["_Endereco_Normalizado"] == chave
                            )
                            st.session_state.df_rota.loc[mask, "Status"] = "Recusado"
                            st.session_state.df_rota.loc[mask, "Horario_Baixa"] = horario
                            st.session_state.df_rota.loc[mask, "POD_Latitude_Baixa"] = lat_baixa
                            st.session_state.df_rota.loc[mask, "POD_Longitude_Baixa"] = lon_baixa
                            st.session_state.df_rota.loc[mask, "Ocorrencia"] = ocorrencia_tudo
                            st.session_state.pop(f"recusar_tudo_aberto_{i}", None)
                            salvar_snapshot_operacional()
                            st.rerun()
                    with col_ct2:
                        if st.button(
                            "❌ Cancelar",
                            key=f"cancelar_recusar_tudo_{i}",
                            use_container_width=True
                        ):
                            st.session_state.pop(f"recusar_tudo_aberto_{i}", None)
                            st.rerun()

            # ── Ocorrência inline para parada com recusa existente ──────────
            if recusados_parada > 0 and pendentes_parada == 0:
                ocorrencia_parada_atual = (
                    pacotes_por_parada.get(chave, df.iloc[0:0])
                    ["Ocorrencia"]
                    .fillna("")
                    .astype(str)
                    .iloc[0] if len(pacotes_por_parada.get(chave, df.iloc[0:0])) > 0 else ""
                )
                if ocorrencia_parada_atual.lower() == "nan":
                    ocorrencia_parada_atual = ""
                if not ocorrencia_parada_atual:
                    st.error("⚠️ Informe a ocorrência para esta recusa.")

            with st.expander("Ver pacotes", expanded=False):

                carregar_pacotes_key = f"carregar_pacotes_{i}"
                mostrar_pacotes = (
                    bool(busca_pedido)
                    or st.session_state.get(carregar_pacotes_key, False)
                )

                if not mostrar_pacotes:
                    st.caption(
                        f"{len(pacotes_visiveis)} pacote(s) oculto(s) para manter a tela rápida."
                    )

                    if st.button(
                        "Carregar pacotes desta parada",
                        key=f"btn_{carregar_pacotes_key}"
                    ):
                        st.session_state[carregar_pacotes_key] = True
                        st.rerun()

                    pacotes_render = pacotes_visiveis.iloc[0:0]
                else:
                    pacotes_render = pacotes_visiveis

                if mostrar_pacotes and len(pacotes_render) == 0:

                    st.success(
                        "Todos os pacotes finalizados."
                    )

                for idx, pacote in pacotes_render.iterrows():

                    status = pacote["Status"]
                    codigo_pacote = str(pacote.get(col_spx, pacote.get("SPX TN", "")))

                    # Verificar se este pacote específico está fora do agrupamento
                    idxs_fora = [f[0] for f in fora_de_rota]
                    dist_fora = {f[0]: f[1] for f in fora_de_rota}
                    pacote_fora = idx in idxs_fora

                    if pacote_fora:
                        dist_m = dist_fora[idx]
                        dist_txt = f"{dist_m / 1000:.1f} km" if dist_m >= 1000 else f"{dist_m} m"
                        lat_pac = pd.to_numeric(pacote.get(col_lat, 0), errors="coerce")
                        lon_pac = pd.to_numeric(pacote.get(col_lon, 0), errors="coerce")
                        maps_pac = (
                            f"https://www.google.com/maps/search/?api=1"
                            f"&query={lat_pac},{lon_pac}"
                        )
                        st.markdown(
                            f"""
                            <div style="background:#fef2f2;border:1.5px solid #f87171;
                                 border-radius:10px;padding:0.65rem 1rem;margin-bottom:0.3rem;">
                                <span style="font-size:0.85rem;font-weight:700;color:#b91c1c;">
                                    📦 Pacote fora do agrupamento — {dist_txt} do centro desta parada
                                </span><br>
                                <span style="font-size:0.8rem;color:#7f1d1d;">
                                    Endereço: {pacote.get(col_endereco, "")}
                                </span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        st.link_button(
                            f"🗺️ Navegar até endereço real deste pacote",
                            maps_pac,
                            use_container_width=True
                        )

                    st.write(f"**Código/Pedido:** {codigo_pacote}")

                    if status == "Entregue":
                        st.success("Status atual: Entregue")
                    elif status == "Recusado":
                        st.error("Status atual: Recusado")
                    else:
                        st.warning("Status atual: Pendente")

                    col_fast_1, col_fast_2 = st.columns(
                        [1, 1],
                        gap="medium"
                    )

                    with col_fast_1:
                        if st.button(
                            "Entregue",
                            key=f"fast_ent_{idx}",
                            type="primary",
                            use_container_width=True
                        ):
                            atualizar_status_pacote(idx, "Entregue")
                            st.session_state.pop(f"recusar_aberto_{idx}", None)
                            st.rerun()

                    with col_fast_2:
                        if st.button(
                            "Recusado",
                            key=f"fast_rec_{idx}",
                            type="primary",
                            use_container_width=True
                        ):
                            atualizar_status_pacote(idx, "Recusado")
                            st.session_state[f"recusar_aberto_{idx}"] = True
                            st.rerun()

                    # ── Ocorrência inline — aparece direto após recusa ──────
                    ocorrencia_atual = str(pacote.get("Ocorrencia", ""))
                    if ocorrencia_atual.lower() == "nan":
                        ocorrencia_atual = ""

                    if status == "Recusado":
                        if not ocorrencia_atual:
                            st.warning("⚠️ Informe a ocorrência:")
                        if ocorrencia_atual in opcoes_ocorrencia:
                            ocorrencia_idx = opcoes_ocorrencia.index(ocorrencia_atual)
                        else:
                            ocorrencia_idx = 0
                        ocorrencia = st.selectbox(
                            "Ocorrência",
                            opcoes_ocorrencia,
                            index=ocorrencia_idx,
                            key=f"ocorrencia_{idx}"
                        )
                        if ocorrencia != ocorrencia_atual:
                            st.session_state.df_rota.loc[idx, "Ocorrencia"] = ocorrencia
                            salvar_snapshot_operacional()

                        # ENL inline — só quando ocorrência = Endereço não localizado
                        if ocorrencia == "Endereço não localizado":
                            enl_foto_atual = str(pacote.get("ENL_Foto", ""))
                            enl_foto_nome_atual = str(pacote.get("ENL_Foto_Nome", ""))
                            enl_obs_atual = str(pacote.get("ENL_Observacao", ""))
                            enl_lat_atual = str(pacote.get("ENL_Lat", ""))
                            enl_lon_atual = str(pacote.get("ENL_Lon", ""))
                            for _campo in ["enl_foto_atual", "enl_foto_nome_atual",
                                           "enl_obs_atual", "enl_lat_atual", "enl_lon_atual"]:
                                pass
                            if enl_foto_atual.lower() == "nan": enl_foto_atual = ""
                            if enl_foto_nome_atual.lower() == "nan": enl_foto_nome_atual = ""
                            if enl_obs_atual.lower() == "nan": enl_obs_atual = ""
                            if enl_lat_atual.lower() == "nan": enl_lat_atual = ""
                            if enl_lon_atual.lower() == "nan": enl_lon_atual = ""

                            enl_completo = bool(enl_foto_atual) and bool(enl_obs_atual.strip())

                            st.markdown("**📍 Prova de Endereço Não Localizado**")
                            if not enl_completo:
                                st.error("⚠️ Foto do local e descrição são obrigatórios.")
                            else:
                                st.success("✅ Prova registrada.")

                            enl_foto_input = st.camera_input(
                                "📷 Foto do local (obrigatório)",
                                key=f"enl_foto_{idx}"
                            )
                            if enl_foto_input is not None:
                                enl_bytes = enl_foto_input.getvalue()
                                st.session_state.df_rota.loc[idx, "ENL_Foto"] = base64.b64encode(enl_bytes).decode("utf-8")
                                st.session_state.df_rota.loc[idx, "ENL_Foto_Nome"] = f"enl_foto_{idx}.jpg"
                                st.session_state.df_rota.loc[idx, "ENL_Lat"] = lat_baixa
                                st.session_state.df_rota.loc[idx, "ENL_Lon"] = lon_baixa
                                salvar_snapshot_operacional()
                                st.image(enl_bytes, caption="Foto do local registrada", width=180)
                            elif enl_foto_atual:
                                try:
                                    st.image(base64.b64decode(enl_foto_atual),
                                             caption=enl_foto_nome_atual or "Foto do local", width=180)
                                except Exception:
                                    st.caption("Foto do local salva.")

                            enl_obs = st.text_area(
                                "📝 Descreva o que encontrou (obrigatório)",
                                value=enl_obs_atual,
                                placeholder="Ex: Rua não existe no local, número não encontrado...",
                                key=f"enl_obs_{idx}",
                                height=80
                            )
                            if enl_obs != enl_obs_atual:
                                st.session_state.df_rota.loc[idx, "ENL_Observacao"] = enl_obs
                                salvar_snapshot_operacional()

                            if enl_lat_atual and enl_lon_atual:
                                st.caption(f"📡 GPS: {enl_lat_atual}, {enl_lon_atual}")
                            else:
                                st.caption("📡 GPS registrado ao tirar a foto.")
                    # ── FIM ocorrência inline ───────────────────────────────

                    detalhes_pacote = (
                        st.popover("Detalhes")
                        if hasattr(st, "popover")
                        else st.container(border=True)
                    )

                    horario_baixa = str(
                        pacote.get("Horario_Baixa", "")
                    )

                    if horario_baixa.lower() == "nan":
                        horario_baixa = ""

                    detalhes_pacote.write(
                        f"**Endereço completo:** {pacote[col_endereco]}"
                    )

                    if col_sequencia is not None:
                        detalhes_pacote.write(
                            f"**Sequência original:** {pacote[col_sequencia]}"
                        )

                    if horario_baixa:
                        detalhes_pacote.write(
                            f"**Horário da baixa:** {horario_baixa}"
                        )

                    detalhes_pacote.write("**Prova de Entrega (POD)**")

                    pod_recebedor_atual = str(
                        pacote.get("POD_Recebedor", "")
                    )
                    pod_assinatura_atual = str(
                        pacote.get("POD_Assinatura", "")
                    )
                    pod_foto_atual = str(
                        pacote.get("POD_Foto", "")
                    )
                    pod_foto_nome_atual = str(
                        pacote.get("POD_Foto_Nome", "")
                    )
                    pod_horario_entrega = str(
                        pacote.get("POD_Horario_Entrega", "")
                    )
                    pod_latitude_baixa = str(
                        pacote.get("POD_Latitude_Baixa", "")
                    )
                    pod_longitude_baixa = str(
                        pacote.get("POD_Longitude_Baixa", "")
                    )

                    if pod_recebedor_atual.lower() == "nan":
                        pod_recebedor_atual = ""
                    if pod_assinatura_atual.lower() == "nan":
                        pod_assinatura_atual = ""
                    if pod_foto_atual.lower() == "nan":
                        pod_foto_atual = ""
                    if pod_foto_nome_atual.lower() == "nan":
                        pod_foto_nome_atual = ""
                    if pod_horario_entrega.lower() == "nan":
                        pod_horario_entrega = ""
                    if pod_latitude_baixa.lower() == "nan":
                        pod_latitude_baixa = ""
                    if pod_longitude_baixa.lower() == "nan":
                        pod_longitude_baixa = ""

                    pod_recebedor = detalhes_pacote.text_input(
                        "Nome do recebedor",
                        value=pod_recebedor_atual,
                        key=f"pod_recebedor_{idx}"
                    )

                    if pod_recebedor != pod_recebedor_atual:
                        st.session_state.df_rota.loc[
                            idx,
                            "POD_Recebedor"
                        ] = pod_recebedor
                        salvar_snapshot_operacional()

                    pod_assinatura = detalhes_pacote.text_input(
                        "Assinatura digitada",
                        value=pod_assinatura_atual,
                        key=f"pod_assinatura_{idx}"
                    )

                    if pod_assinatura != pod_assinatura_atual:
                        st.session_state.df_rota.loc[
                            idx,
                            "POD_Assinatura"
                        ] = pod_assinatura
                        salvar_snapshot_operacional()

                    pod_foto = detalhes_pacote.camera_input(
                        "Foto da entrega",
                        key=f"pod_foto_{idx}"
                    )

                    if pod_foto is not None:
                        foto_bytes = pod_foto.getvalue()
                        st.session_state.df_rota.loc[
                            idx,
                            "POD_Foto"
                        ] = base64.b64encode(foto_bytes).decode("utf-8")
                        st.session_state.df_rota.loc[
                            idx,
                            "POD_Foto_Nome"
                        ] = f"foto_pod_{idx}.jpg"
                        salvar_snapshot_operacional()
                        detalhes_pacote.image(
                            foto_bytes,
                            caption="Foto registrada",
                            width=180
                        )
                    elif pod_foto_atual:
                        try:
                            detalhes_pacote.image(
                                base64.b64decode(pod_foto_atual),
                                caption=pod_foto_nome_atual or "Foto POD",
                                width=180
                            )
                        except Exception:
                            detalhes_pacote.caption("Foto POD salva.")

                    observacao_atual = str(
                        pacote.get("Observacao", "")
                    )

                    if observacao_atual.lower() == "nan":
                        observacao_atual = ""

                    observacao = detalhes_pacote.text_area(
                        "Observação",
                        value=observacao_atual,
                        key=f"obs_{idx}",
                        height=80
                    )

                    if observacao != observacao_atual:
                        st.session_state.df_rota.loc[
                            idx,
                            "Observacao"
                        ] = observacao
                        salvar_snapshot_operacional()

                    detalhes_pacote.divider()

    st.divider()

    if "ultimo_autosalvamento" in st.session_state:
        st.caption(
            f"Salvo automaticamente no SQLite: {st.session_state['ultimo_autosalvamento']}"
        )

    if "erro_autosalvamento" in st.session_state:
        st.warning(
            f"Não foi possível salvar automaticamente: {st.session_state['erro_autosalvamento']}"
        )

    st.divider()

    st.subheader("Exportar Resultado")

    excel_file = exportar_excel(
        df
    )

    st.download_button(
        label="Baixar Excel Final",
        data=excel_file,
        file_name="torre_express_resultado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.divider()

    st.subheader("Salvar operação")

    if st.button("Salvar operação"):

        total_salvo, data_operacao = salvar_operacao(
            df,
            col_spx,
            col_endereco,
            col_lat,
            col_lon,
            st.session_state["usuario_logado"]
        )

        st.success(
            f"Operação salva em {data_operacao} com {total_salvo} pacote(s)."
        )

    if False:

        st.divider()

        st.subheader("Histórico operacional")

        historico = carregar_historico()

        if len(historico) == 0:
            st.info("Nenhuma operação salva ainda.")
        else:
            st.dataframe(
                historico,
                use_container_width=True,
                hide_index=True
            )


if False:
    exibir_historico_operacional()
    exibir_dashboard_gerencial()

if False:
    exibir_gestao_usuarios()
