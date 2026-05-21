import html

import pandas as pd
import streamlit as st

from utils import calcular_km_rota, calcular_tempo_horas


def calcular_proxima_parada(
    proxima_parada,
    df,
    col_lat,
    col_lon,
    lat_motorista,
    lon_motorista,
    velocidade_media
):

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

    return pacotes_proxima, distancia_proxima, eta_proxima


def exibir_modo_motorista_premium(
    proxima_parada,
    pacotes_proxima,
    distancia_proxima,
    eta_proxima,
    col_endereco,
    progresso_rota,
    finalizados,
    total_pacotes,
    sla
):

    st.subheader("Modo Motorista Premium")

    if proxima_parada is not None:
        ordem_proxima = int(proxima_parada["Ordem"])
        endereco_proxima = html.escape(str(proxima_parada[col_endereco]))
        total_pacotes_proxima = len(pacotes_proxima)
        eta_minutos = int(round(eta_proxima * 60))

        st.markdown(
            f"""
            <div class="premium-shell">
                <div class="premium-kicker">Próxima parada - #{ordem_proxima}</div>
                <div class="premium-address">{endereco_proxima}</div>
                <div class="premium-grid">
                    <div class="premium-stat">
                        <span>Pacotes</span>
                        <strong>{total_pacotes_proxima}</strong>
                    </div>
                    <div class="premium-stat">
                        <span>Distancia</span>
                        <strong>{distancia_proxima:.2f} km</strong>
                    </div>
                    <div class="premium-stat">
                        <span>ETA</span>
                        <strong>{eta_minutos} min</strong>
                    </div>
                    <div class="premium-stat">
                        <span>Progresso</span>
                        <strong>{sla}%</strong>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.success("Rota finalizada. Todos os pacotes foram tratados.")

    st.markdown('<div class="route-progress">', unsafe_allow_html=True)
    st.progress(progresso_rota)
    st.caption(f"{finalizados} de {total_pacotes} pacotes finalizados")
    st.markdown('</div>', unsafe_allow_html=True)
