import streamlit as st

from database import carregar_historico


def exibir_historico_operacional():

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
