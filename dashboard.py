import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from database import carregar_dados_dashboard


# ── CORES ─────────────────────────────────────────────────────────────────────
AZUL    = "#0b1f3a"
LARANJA = "#f97316"
VERDE   = "#16a34a"
VERM    = "#dc2626"
CINZA   = "#6b7280"


def preparar_dados_dashboard(df_historico):
    df = df_historico.copy()
    if len(df) == 0:
        return df

    df["data_operacao_dt"] = pd.to_datetime(
        df["data_operacao"], format="%d/%m/%Y %H:%M:%S", errors="coerce"
    )
    df["data"] = (
        df["data_operacao_dt"].dt.strftime("%d/%m/%Y")
        .fillna(df["data_operacao"])
    )
    df["latitude"]  = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    if "usuario_nome" in df.columns:
        df["usuario_nome"] = df["usuario_nome"].fillna("Sem usuário").replace("", "Sem usuário")
    if "usuario_perfil" in df.columns:
        df["usuario_perfil"] = df["usuario_perfil"].fillna("-").replace("", "-")
    if "ocorrencia" not in df.columns:
        df["ocorrencia"] = ""
    df["ocorrencia"] = df["ocorrencia"].fillna("").replace("nan", "")

    return df


def _card_kpi(col, label, valor, cor=None):
    cor = cor or AZUL
    col.markdown(
        f"""
        <div style="background:{cor};border-radius:10px;padding:0.8rem 1rem;
                    text-align:center;margin-bottom:0.2rem;">
            <div style="color:#ffffff99;font-size:0.75rem;font-weight:600;
                        letter-spacing:0.05em;text-transform:uppercase;">{label}</div>
            <div style="color:#fff;font-size:1.8rem;font-weight:800;
                        line-height:1.2;">{valor}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def exibir_dashboard_gerencial():

    st.markdown(
        f"""
        <div style="background:{AZUL};border-radius:12px;padding:1rem 1.4rem;
                    margin-bottom:1rem;">
            <span style="color:#fff;font-size:1.3rem;font-weight:800;">
                📊 Dashboard Gerencial
            </span>
            <span style="color:{LARANJA};font-size:0.85rem;margin-left:0.8rem;">
                Torre Express Driver
            </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    df_raw = carregar_dados_dashboard()
    df_all = preparar_dados_dashboard(df_raw)

    if len(df_all) == 0:
        st.info("Nenhum dado salvo ainda. Realize operações e salve para visualizar o dashboard.")
        return

    # ── FILTRO DE PERÍODO ────────────────────────────────────────────────────
    st.markdown("#### Período de análise")
    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        periodo = st.selectbox(
            "Exibir dados dos últimos:",
            ["7 dias", "15 dias", "30 dias", "60 dias", "Tudo"],
            index=0,
            key="dash_periodo"
        )

    if periodo != "Tudo":
        dias = int(periodo.split()[0])
        data_corte = pd.Timestamp.now() - pd.Timedelta(days=dias)
        df = df_all[
            df_all["data_operacao_dt"].notna()
            & (df_all["data_operacao_dt"] >= data_corte)
        ].copy()
        if len(df) == 0:
            st.warning(f"Nenhum dado nos últimos {dias} dias. Tente ampliar o período.")
            return
    else:
        df = df_all.copy()

    st.divider()

    # ══ BLOCO 1 — VISÃO GERAL ════════════════════════════════════════════════
    st.markdown(f"<span style='color:{AZUL};font-size:1.1rem;font-weight:700;'>1 · Visão Geral Operacional</span>", unsafe_allow_html=True)

    total_pacotes   = len(df)
    total_entregues = (df["status"] == "Entregue").sum()
    total_recusados = (df["status"] == "Recusado").sum()
    total_pendentes = (df["status"] == "Pendente").sum()
    sla_geral       = round((total_entregues / total_pacotes) * 100, 1) if total_pacotes > 0 else 0
    motoristas_atv  = df["usuario_nome"].nunique() if "usuario_nome" in df.columns else 0
    dias_operacao   = df["data"].nunique()

    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    _card_kpi(c1, "Pacotes",     total_pacotes,   AZUL)
    _card_kpi(c2, "Entregues",   total_entregues, "#166534")
    _card_kpi(c3, "Recusados",   total_recusados, "#991b1b")
    _card_kpi(c4, "Pendentes",   total_pendentes, "#92400e")
    _card_kpi(c5, "SLA Geral",   f"{sla_geral}%", LARANJA)
    _card_kpi(c6, "Motoristas",  motoristas_atv,  "#1e40af")
    _card_kpi(c7, "Dias Op.",    dias_operacao,   "#374151")

    st.divider()

    # ══ BLOCO 2 — PERFORMANCE POR MOTORISTA ══════════════════════════════════
    st.markdown(f"<span style='color:{AZUL};font-size:1.1rem;font-weight:700;'>2 · Performance por Motorista</span>", unsafe_allow_html=True)

    por_motorista = (
        df.groupby("usuario_nome")
        .agg(
            Pacotes=("spx", "count"),
            Entregues=("status", lambda s: (s == "Entregue").sum()),
            Recusados=("status", lambda s: (s == "Recusado").sum()),
            Pendentes=("status", lambda s: (s == "Pendente").sum()),
            Operações=("data_operacao", "nunique"),
        )
        .reset_index()
        .rename(columns={"usuario_nome": "Motorista"})
    )
    por_motorista["SLA %"] = (
        (por_motorista["Entregues"] / por_motorista["Pacotes"]) * 100
    ).round(1).astype(str) + "%"

    por_motorista = por_motorista.sort_values("Entregues", ascending=False)

    # Colorir SLA
    def colorir_sla(val):
        v = float(val.replace("%", ""))
        if v >= 90:
            return "color: #166534; font-weight: 700"
        elif v >= 70:
            return "color: #92400e; font-weight: 700"
        return "color: #991b1b; font-weight: 700"

    st.dataframe(
        por_motorista.style.applymap(colorir_sla, subset=["SLA %"]),
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # ══ BLOCO 3 — ANÁLISE DE OCORRÊNCIAS ═════════════════════════════════════
    st.markdown(f"<span style='color:{AZUL};font-size:1.1rem;font-weight:700;'>3 · Análise de Ocorrências</span>", unsafe_allow_html=True)

    df_oc = df[
        (df["status"] == "Recusado")
        & (df["ocorrencia"].str.strip() != "")
    ].copy()

    if len(df_oc) == 0:
        st.info("Nenhuma ocorrência registrada no período.")
    else:
        ocorrencias = (
            df_oc.groupby("ocorrencia")
            .size()
            .reset_index(name="Total")
            .rename(columns={"ocorrencia": "Ocorrência"})
            .sort_values("Total", ascending=False)
        )

        col_oc1, col_oc2 = st.columns([1.2, 1])

        with col_oc1:
            st.bar_chart(
                ocorrencias.set_index("Ocorrência")["Total"],
                color=LARANJA,
                height=260
            )

        with col_oc2:
            st.dataframe(ocorrencias, use_container_width=True, hide_index=True, height=260)

    st.divider()

    # ══ BLOCO 4 — MAPA DE CALOR (SOB DEMANDA) ════════════════════════════════
    st.markdown(f"<span style='color:{AZUL};font-size:1.1rem;font-weight:700;'>4 · Mapa de Calor de Entregas</span>", unsafe_allow_html=True)

    pontos = df[
        df["latitude"].notna() & df["longitude"].notna()
        & (df["latitude"] != 0) & (df["longitude"] != 0)
    ]

    if len(pontos) == 0:
        st.info("Nenhuma coordenada GPS registrada no período.")
    else:
        st.caption(f"{len(pontos)} pontos com GPS disponíveis no período selecionado.")

        if st.button("🗺️ Gerar mapa de calor", key="btn_mapa_calor", type="primary"):
            st.session_state["dash_mapa_aberto"] = True

        if st.session_state.get("dash_mapa_aberto"):
            lat_c = pontos["latitude"].mean()
            lon_c = pontos["longitude"].mean()

            mapa = folium.Map(location=[lat_c, lon_c], zoom_start=12, tiles="CartoDB positron")

            cores_status = {
                "Entregue": "green",
                "Recusado": "red",
                "Pendente": "orange",
            }

            for _, p in pontos.iterrows():
                cor = cores_status.get(str(p.get("status", "")), "blue")
                popup_txt = (
                    f"<b>{p.get('status','')}</b><br>"
                    f"{p.get('endereco','')}<br>"
                    f"Motorista: {p.get('usuario_nome','')}<br>"
                    f"{p.get('data','')}"
                )
                folium.CircleMarker(
                    location=[p["latitude"], p["longitude"]],
                    radius=6,
                    color=cor,
                    fill=True,
                    fill_color=cor,
                    fill_opacity=0.7,
                    popup=folium.Popup(popup_txt, max_width=220),
                    tooltip=p.get("status", "")
                ).add_to(mapa)

            # Legenda
            legenda = """
            <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                        background:white;padding:10px 14px;border-radius:8px;
                        border:1px solid #ccc;font-size:13px;font-family:Arial;">
                <b>Legenda</b><br>
                🟢 Entregue &nbsp; 🔴 Recusado &nbsp; 🟠 Pendente
            </div>
            """
            mapa.get_root().html.add_child(folium.Element(legenda))

            st_folium(mapa, use_container_width=True, height=420, returned_objects=[])

    st.divider()

    # ══ BLOCO 5 — EVOLUÇÃO HISTÓRICA ═════════════════════════════════════════
    st.markdown(f"<span style='color:{AZUL};font-size:1.1rem;font-weight:700;'>5 · Evolução Histórica de SLA</span>", unsafe_allow_html=True)

    evolucao = (
        df.groupby("data")
        .agg(
            Pacotes=("spx", "count"),
            Entregues=("status", lambda s: (s == "Entregue").sum()),
        )
        .reset_index()
    )
    evolucao["SLA %"] = (
        (evolucao["Entregues"] / evolucao["Pacotes"]) * 100
    ).round(1)
    evolucao = evolucao.sort_values("data")

    if len(evolucao) < 2:
        st.info("Necessário pelo menos 2 dias de operação para exibir a evolução.")
    else:
        col_ev1, col_ev2 = st.columns([1.5, 1])
        with col_ev1:
            st.line_chart(
                evolucao.set_index("data")["SLA %"],
                color=LARANJA,
                height=220
            )
        with col_ev2:
            st.bar_chart(
                evolucao.set_index("data")["Entregues"],
                color=AZUL,
                height=220
            )
            st.caption("Entregas por dia")

    st.divider()

    # ══ BLOCO 6 — ALERTAS AUTOMÁTICOS ════════════════════════════════════════
    st.markdown(f"<span style='color:{AZUL};font-size:1.1rem;font-weight:700;'>6 · Alertas Automáticos</span>", unsafe_allow_html=True)

    alertas = []

    # SLA geral baixo
    if sla_geral < 70:
        alertas.append(("🔴", f"SLA geral crítico: {sla_geral}% — abaixo de 70%"))
    elif sla_geral < 85:
        alertas.append(("🟡", f"SLA geral em atenção: {sla_geral}% — abaixo de 85%"))

    # Motoristas com SLA baixo
    for _, row in por_motorista.iterrows():
        sla_val = float(str(row["SLA %"]).replace("%", ""))
        if sla_val < 70:
            alertas.append(("🔴", f"Motorista '{row['Motorista']}' com SLA crítico: {sla_val}%"))
        elif sla_val < 85:
            alertas.append(("🟡", f"Motorista '{row['Motorista']}' com SLA em atenção: {sla_val}%"))

    # Ocorrência dominante
    if len(df_oc) > 0:
        top_oc = ocorrencias.iloc[0]
        pct_oc = round((top_oc["Total"] / total_recusados) * 100, 1) if total_recusados > 0 else 0
        if pct_oc >= 50:
            alertas.append(("🟡", f"Ocorrência dominante: '{top_oc['Ocorrência']}' representa {pct_oc}% das recusas"))

    # Alta taxa de recusa
    taxa_recusa = round((total_recusados / total_pacotes) * 100, 1) if total_pacotes > 0 else 0
    if taxa_recusa >= 20:
        alertas.append(("🔴", f"Taxa de recusa alta: {taxa_recusa}% dos pacotes foram recusados"))
    elif taxa_recusa >= 10:
        alertas.append(("🟡", f"Taxa de recusa em atenção: {taxa_recusa}%"))

    # Regiões com alta concentração de recusas
    if "bairro" in df.columns:
        recusas_bairro = (
            df[df["status"] == "Recusado"]
            .groupby("bairro")
            .size()
            .reset_index(name="recusas")
            .sort_values("recusas", ascending=False)
        )
        if len(recusas_bairro) > 0 and recusas_bairro.iloc[0]["recusas"] >= 5:
            top_b = recusas_bairro.iloc[0]
            alertas.append(("🟡", f"Região com mais recusas: '{top_b['bairro']}' com {top_b['recusas']} recusas"))

    if not alertas:
        st.success("✅ Nenhum alerta no período selecionado. Operação dentro dos parâmetros.")
    else:
        for emoji, msg in alertas:
            if emoji == "🔴":
                st.error(f"{emoji} {msg}")
            else:
                st.warning(f"{emoji} {msg}")

    st.divider()
    st.caption(f"Dashboard gerado com dados do período: {periodo}  •  {total_pacotes} pacotes analisados")
