import hashlib
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from database import DB_PATH


LOGO_PATH = Path("assets/logo.png")


def exibir_logo_auth(width=290):

    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=width)
    else:
        st.markdown("### Torre Express Driver")


def criar_hash_senha(senha):

    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()

    return f"{salt}:{digest}"


def verificar_senha(senha, senha_hash):

    try:
        salt, digest_salvo = senha_hash.split(":", 1)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()

    return secrets.compare_digest(digest, digest_salvo)


def existem_usuarios():

    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM usuarios"
        ).fetchone()[0]

    return total > 0


def existe_admin():

    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM usuarios WHERE perfil = 'admin'"
        ).fetchone()[0]

    return total > 0


def criar_usuario(usuario, nome, senha, perfil):

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO usuarios (
                usuario,
                nome,
                senha_hash,
                perfil,
                ativo,
                criado_em
            )
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                usuario.strip(),
                nome.strip(),
                criar_hash_senha(senha),
                perfil,
                datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            )
        )
        conn.commit()


def autenticar_usuario(usuario, senha):

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            """
            SELECT id, usuario, nome, senha_hash, perfil, ativo
            FROM usuarios
            WHERE usuario = ?
            """,
            (usuario.strip(),)
        ).fetchone()

    if user is None or user["ativo"] != 1:
        return None

    if not verificar_senha(senha, user["senha_hash"]):
        return None

    return {
        "id": user["id"],
        "usuario": user["usuario"],
        "nome": user["nome"],
        "perfil": user["perfil"]
    }


def carregar_usuarios():

    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT id, usuario, nome, perfil, ativo, criado_em
            FROM usuarios
            ORDER BY id DESC
            """,
            conn
        )


def definir_status_usuario(usuario_id, ativo):

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE usuarios SET ativo = ? WHERE id = ?",
            (1 if ativo else 0, usuario_id)
        )
        conn.commit()


def redefinir_senha_usuario(usuario, nova_senha):

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            UPDATE usuarios
            SET senha_hash = ?
            WHERE usuario = ?
            """,
            (
                criar_hash_senha(nova_senha),
                usuario.strip()
            )
        )
        conn.commit()

    return cur.rowcount > 0


def redefinir_senha_usuario_por_id(usuario_id, nova_senha):

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE usuarios
            SET senha_hash = ?
            WHERE id = ?
            """,
            (
                criar_hash_senha(nova_senha),
                int(usuario_id)
            )
        )
        conn.commit()


def usuario_tem_acesso(*perfis):

    usuario = st.session_state.get("usuario_logado")

    if usuario is None:
        return False

    return usuario["perfil"] in perfis


def exibir_cadastro_admin_inicial():

    exibir_login()


def exibir_login():

    st.markdown(
        """
        <style>
            :root {
                --torre-azul: #0b1f3a;
                --torre-laranja: #f97316;
                --torre-fundo: #f3f4f6;
                --torre-card: #ffffff;
            }

            .stApp {
                background: var(--torre-fundo);
            }

            .auth-shell {
                max-width: 520px;
                margin: 7vh auto 0;
                padding: 26px 24px;
                border: 1px solid #e5e7eb;
                border-radius: 18px;
                box-shadow: 0 18px 45px rgba(15, 23, 42, 0.10);
                background: var(--torre-card);
            }

            .auth-brand {
                text-align: center;
                margin-bottom: 18px;
            }

            .auth-brand h1 {
                margin: 0;
                font-size: 1.75rem;
            }

            .auth-brand p {
                margin: 6px 0 0;
                color: #6b7280;
            }

            div[data-testid="stImage"] {
                text-align: center;
                margin: 0 auto 0.65rem;
            }

            div[data-testid="stImage"] img {
                max-width: min(300px, 82vw);
                height: auto;
                object-fit: contain;
            }

            div[data-testid="stFormSubmitButton"] button {
                background: var(--torre-laranja);
                border: 1px solid var(--torre-laranja);
                color: #ffffff;
                border-radius: 8px;
                min-height: 44px;
                font-weight: 700;
            }

            div[data-testid="stFormSubmitButton"] button:hover {
                background: #ea580c;
                border-color: #ea580c;
                color: #ffffff;
            }

            div[data-baseweb="tab-list"] button[aria-selected="true"] {
                color: var(--torre-azul);
                border-bottom-color: var(--torre-laranja);
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    col_esq, col_centro, col_dir = st.columns([1, 1.35, 1])

    with col_centro:
        exibir_logo_auth()
        st.caption("Plataforma operacional de entregas")
        aba_entrar, aba_criar, aba_senha = st.tabs(
            ["Entrar", "Criar conta", "Esqueci minha senha"]
        )

        with aba_entrar:
            with st.form("form_login"):
                usuario = st.text_input("Usuário")
                senha = st.text_input("Senha", type="password")
                entrar = st.form_submit_button("Entrar")

            if entrar:
                user = autenticar_usuario(usuario, senha)

                if user is None:
                    st.error("Usuário ou senha inválidos.")
                    return

                st.session_state.usuario_logado = user
                st.rerun()

        with aba_criar:
            primeiro_admin = not existe_admin()

            if primeiro_admin:
                st.info("Nenhum admin encontrado. Esta primeira conta será admin.")
            else:
                st.caption("Novas contas criadas aqui entram como motorista.")

            with st.form("form_criar_conta_inicial"):
                nome = st.text_input("Nome", key="cad_nome")
                usuario = st.text_input("Usuário", key="cad_usuario")
                senha = st.text_input("Senha", type="password", key="cad_senha")
                confirmar = st.text_input(
                    "Confirmar senha",
                    type="password",
                    key="cad_confirmar"
                )
                criar = st.form_submit_button("Criar conta")

            if criar:
                if not nome or not usuario or not senha:
                    st.error("Preencha nome, usuário e senha.")
                    return

                if senha != confirmar:
                    st.error("As senhas não conferem.")
                    return

                perfil = "admin" if primeiro_admin else "motorista"

                try:
                    criar_usuario(usuario, nome, senha, perfil)
                    st.success("Conta criada. Use a aba Entrar para acessar.")
                except sqlite3.IntegrityError:
                    st.error("Usuário já existe.")

        with aba_senha:
            with st.form("form_redefinir_senha_login"):
                usuario_reset = st.text_input(
                    "Usuário cadastrado",
                    key="reset_usuario_login"
                )
                nova_senha = st.text_input(
                    "Nova senha",
                    type="password",
                    key="reset_senha_login"
                )
                confirmar_senha = st.text_input(
                    "Confirmar nova senha",
                    type="password",
                    key="reset_confirmar_login"
                )
                redefinir = st.form_submit_button("Redefinir senha")

            if redefinir:
                if not usuario_reset or not nova_senha:
                    st.error("Informe usuário e nova senha.")
                    return

                if nova_senha != confirmar_senha:
                    st.error("As senhas não conferem.")
                    return

                if redefinir_senha_usuario(usuario_reset, nova_senha):
                    st.success("Senha redefinida. Volte para a aba Entrar.")
                else:
                    st.error("Usuário não encontrado.")


def exibir_sidebar_usuario():

    usuario = st.session_state["usuario_logado"]

    if LOGO_PATH.exists():
        st.sidebar.image(str(LOGO_PATH), width=200)
    else:
        st.sidebar.title("Torre Express Driver")

    st.sidebar.caption("Usuário logado")
    st.sidebar.write(f"**{usuario['nome']}**")
    st.sidebar.write(f"Perfil: {usuario['perfil']}")

    if st.sidebar.button("Logout"):
        chaves_rota = [
            "df_rota",
            "rota_carregada",
            "rota_iniciada",
            "romaneio_bytes",
            "col_lat",
            "col_lon",
            "col_endereco",
            "col_spx",
            "col_sequencia",
            "regiao_operacional_ativa",
            "regiao_concluida_alerta",
            "paradas_puladas",
            "chave_rota_cerco",
            "paradas_cerco",
            "entregas_manuais"
        ]

        for chave_rota in chaves_rota:
            st.session_state.pop(chave_rota, None)

        for chave_estado in list(st.session_state.keys()):
            if str(chave_estado).startswith("carregar_pacotes_"):
                st.session_state.pop(chave_estado, None)

        st.session_state.pop("usuario_logado", None)
        st.rerun()


def exibir_gestao_usuarios():

    if not usuario_tem_acesso("admin"):
        return

    st.subheader("Usuários")

    with st.form("form_novo_usuario"):
        nome = st.text_input("Nome", key="novo_nome")
        usuario = st.text_input("Usuário", key="novo_usuario")
        senha = st.text_input("Senha", type="password", key="nova_senha")
        perfil = st.selectbox(
            "Perfil",
            ["motorista", "gestor", "admin"],
            key="novo_perfil"
        )
        salvar = st.form_submit_button("Criar usuário")

    if salvar:
        if not nome or not usuario or not senha:
            st.error("Preencha nome, usuário e senha.")
        else:
            try:
                criar_usuario(usuario, nome, senha, perfil)
                st.success("Usuário criado.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Usuário já existe.")

    usuarios = carregar_usuarios()

    if len(usuarios) == 0:
        st.info("Nenhum usuário cadastrado.")
        return

    st.write("Usuários cadastrados")

    for _, user in usuarios.iterrows():
        with st.container(border=True):
            col_info, col_status, col_acao = st.columns([3, 1, 1])

            with col_info:
                st.write(f"**{user['nome']}**")
                st.caption(
                    f"Usuário: {user['usuario']} | Perfil: {user['perfil']} | Criado em: {user['criado_em']}"
                )

            with col_status:
                if int(user["ativo"]) == 1:
                    st.success("Ativo")
                else:
                    st.warning("Inativo")

            with col_acao:
                usuario_logado = st.session_state.get("usuario_logado", {})
                mesmo_usuario = user["id"] == usuario_logado.get("id")

                if int(user["ativo"]) == 1:
                    if st.button(
                        "Desativar",
                        key=f"desativar_user_{user['id']}",
                        disabled=mesmo_usuario
                    ):
                        definir_status_usuario(user["id"], False)
                        st.rerun()
                else:
                    if st.button(
                        "Ativar",
                        key=f"ativar_user_{user['id']}"
                    ):
                        definir_status_usuario(user["id"], True)
                        st.rerun()

            with st.expander("Redefinir senha", expanded=False):
                with st.form(f"form_reset_admin_{user['id']}"):
                    nova_senha = st.text_input(
                        "Nova senha",
                        type="password",
                        key=f"admin_senha_{user['id']}"
                    )
                    confirmar_senha = st.text_input(
                        "Confirmar nova senha",
                        type="password",
                        key=f"admin_confirmar_{user['id']}"
                    )
                    redefinir = st.form_submit_button("Atualizar senha")

                if redefinir:
                    if not nova_senha:
                        st.error("Informe a nova senha.")
                    elif nova_senha != confirmar_senha:
                        st.error("As senhas não conferem.")
                    else:
                        redefinir_senha_usuario_por_id(user["id"], nova_senha)
                        st.success("Senha atualizada.")
