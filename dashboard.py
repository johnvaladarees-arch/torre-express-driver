import pandas as pd
import streamlit as st

from database import carregar_dados_dashboard
from mapa import renderizar_mapa_dashboard


def preparar_dados_dashboard(df_historico):

    df_dashboard = df_historico.copy()

    if len(df_dashboard) == 0:
        return df_dashboard

    df_dashboard["data_operacao_dt"] = pd.to_datetime(
        df_dashboard["data_operacao"],
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce"
    )

    df_dashboard["data"] = (
        df_dashboard["data_operacao_dt"]
        .dt.strftime("%d/%m/%Y")
        .fillna(df_dashboard["data_operacao"])
    )

    df_dashboard["latitude"] = pd.to_numeric(
        df_dashboard["latitude"],
        errors="coerce"
    )

    df_dashboard["longitude"] = pd.to_numeric(
        df_dashboard["longitude"],
        errors="coerce"
    )

    if "usuario_nome" in df_dashboard.columns:
        df_dashboard["usuario_nome"] = (
            df_dashboard["usuario_nome"]
            .fillna("Sem usuario")
            .replace("", "Sem usuario")
        )

    if "usuario_perfil" in df_dashboard.columns:
        df_dashboard["usuario_perfil"] = (
            df_dashboard["usuario_perfil"]
            .fillna("-")
            .replace("", "-")
        )

    return df_dashboard


def exibir_dashboard_gerencial():

    st.divider()
    st.subheader("Dashboard Gerencial")

    df_dashboard = preparar_dados_dashboard(
        carregar_dados_dashboard()
    )

    if len(df_dashboard) == 0:
        st.info("Nenhum dado salvo no SQLite para o dashboard.")
        return

    total_operacoes = df_dashboard["data_operacao"].nunique()
    total_entregues = len(
        df_dashboard[df_dashboard["status"] == "Entregue"]
    )
    total_recusados = len(
        df_dashboard[df_dashboard["status"] == "Recusado"]
    )
    total_pacotes = len(df_dashboard)
    sla_geral = int(
        (total_entregues / total_pacotes) * 100
    ) if total_pacotes > 0 else 0

    col_dash1, col_dash2, col_dash3, col_dash4 = st.columns(4)
    col_dash1.metric("Operações salvas", total_operacoes)
    col_dash2.metric("Pacotes entregues", total_entregues)
    col_dash3.metric("Recusados", total_recusados)
    col_dash4.metric("SLA geral", f"{sla_geral}%")

    entregas_por_data = (
        df_dashboard[df_dashboard["status"] == "Entregue"]
        .groupby("data")
        .size()
        .reset_index(name="entregas")
    )

    if len(entregas_por_data) > 0:
        st.write("Entregas por data")
        st.bar_chart(entregas_por_data, x="data", y="entregas")

    status_chart = (
        df_dashboard
        .groupby("status")
        .size()
        .reset_index(name="total")
    )

    st.write("Status dos pacotes")
    st.bar_chart(status_chart, x="status", y="total")

    ranking = (
        df_dashboard
        .groupby(["data_operacao", "usuario_nome"])
        .agg(
            pacotes=("spx", "count"),
            entregues=("status", lambda s: (s == "Entregue").sum()),
            recusados=("status", lambda s: (s == "Recusado").sum())
        )
        .reset_index()
    )

    ranking["sla"] = (
        (ranking["entregues"] / ranking["pacotes"]) * 100
    ).round(1)

    ranking = ranking.sort_values(
        by=["sla", "entregues"],
        ascending=False
    )

    st.write("Ranking de desempenho")
    st.dataframe(ranking, use_container_width=True, hide_index=True)

    por_motorista = (
        df_dashboard
        .groupby("usuario_nome")
        .agg(
            operacoes=("data_operacao", "nunique"),
            pacotes=("spx", "count"),
            entregues=("status", lambda s: (s == "Entregue").sum()),
            recusados=("status", lambda s: (s == "Recusado").sum())
        )
        .reset_index()
    )

    por_motorista["sla"] = (
        (por_motorista["entregues"] / por_motorista["pacotes"]) * 100
    ).round(1)

    por_motorista = por_motorista.sort_values(
        by=["sla", "entregues"],
        ascending=False
    )

    st.write("Operações por motorista")
    st.dataframe(por_motorista, use_container_width=True, hide_index=True)

    pontos_mapa = df_dashboard[
        df_dashboard["latitude"].notna()
        & df_dashboard["longitude"].notna()
        & (df_dashboard["latitude"] != 0)
        & (df_dashboard["longitude"] != 0)
    ].head(200)

    st.write("Mapa operacional basico")

    if not renderizar_mapa_dashboard(pontos_mapa):
        st.info("Não há coordenadas salvas para montar o mapa gerencial.")
