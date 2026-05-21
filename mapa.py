import folium
from streamlit_folium import st_folium


def renderizar_mapa_dashboard(pontos_mapa):

    if len(pontos_mapa) == 0:
        return False

    mapa_dashboard = folium.Map(
        location=[
            pontos_mapa["latitude"].mean(),
            pontos_mapa["longitude"].mean()
        ],
        zoom_start=11
    )

    for _, ponto in pontos_mapa.iterrows():
        cor = "green"

        if ponto["status"] == "Recusado":
            cor = "red"
        elif ponto["status"] == "Pendente":
            cor = "orange"

        folium.Marker(
            location=[
                ponto["latitude"],
                ponto["longitude"]
            ],
            popup=f"""
            <b>{ponto['spx']}</b><br>
            {ponto['endereco']}<br>
            Status: {ponto['status']}<br>
            Operação: {ponto['data_operacao']}
            """,
            icon=folium.Icon(color=cor, icon="truck", prefix="fa")
        ).add_to(mapa_dashboard)

    st_folium(
        mapa_dashboard,
        width=1400,
        height=420,
        key="dashboard_mapa_operacional"
    )

    return True
