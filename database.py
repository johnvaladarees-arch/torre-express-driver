import sqlite3

import pandas as pd


DB_PATH = "torre_express.db"


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
                pod_foto TEXT,
                pod_foto_nome TEXT,
                pod_recebedor TEXT,
                pod_assinatura TEXT,
                pod_horario_entrega TEXT,
                pod_latitude_baixa REAL,
                pod_longitude_baixa REAL,
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
            "ocorrencia": "TEXT",
            "pod_foto": "TEXT",
            "pod_foto_nome": "TEXT",
            "pod_recebedor": "TEXT",
            "pod_assinatura": "TEXT",
            "pod_horario_entrega": "TEXT",
            "pod_latitude_baixa": "REAL",
            "pod_longitude_baixa": "REAL"
        }

        for coluna, tipo in novas_colunas.items():
            if coluna not in colunas_historico:
                conn.execute(
                    f"ALTER TABLE historico_pacotes ADD COLUMN {coluna} {tipo}"
                )

        conn.commit()


def salvar_operacao(df, col_spx, col_endereco, col_lat, col_lon, usuario):

    from datetime import datetime

    data_operacao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    registros = []

    for _, pacote in df.iterrows():
        latitude = pd.to_numeric(pacote.get(col_lat, 0), errors="coerce")
        longitude = pd.to_numeric(pacote.get(col_lon, 0), errors="coerce")

        latitude = 0 if pd.isna(latitude) else float(latitude)
        longitude = 0 if pd.isna(longitude) else float(longitude)
        pod_latitude = pd.to_numeric(
            pacote.get("POD_Latitude_Baixa", 0),
            errors="coerce"
        )
        pod_longitude = pd.to_numeric(
            pacote.get("POD_Longitude_Baixa", 0),
            errors="coerce"
        )
        pod_latitude = 0 if pd.isna(pod_latitude) else float(pod_latitude)
        pod_longitude = 0 if pd.isna(pod_longitude) else float(pod_longitude)

        registros.append(
            (
                str(pacote.get(col_spx, "")),
                str(pacote.get(col_endereco, "")),
                str(pacote.get("Status", "")),
                str(pacote.get("Horario_Baixa", "")),
                str(pacote.get("Ocorrencia", "")),
                str(pacote.get("Observacao", "")),
                str(pacote.get("POD_Foto", "")),
                str(pacote.get("POD_Foto_Nome", "")),
                str(pacote.get("POD_Recebedor", "")),
                str(pacote.get("POD_Assinatura", "")),
                str(pacote.get("POD_Horario_Entrega", "")),
                pod_latitude,
                pod_longitude,
                latitude,
                longitude,
                data_operacao,
                usuario["id"],
                usuario["nome"],
                usuario["perfil"]
            )
        )

    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO historico_pacotes (
                spx,
                endereco,
                status,
                horario_baixa,
                ocorrencia,
                observacao,
                pod_foto,
                pod_foto_nome,
                pod_recebedor,
                pod_assinatura,
                pod_horario_entrega,
                pod_latitude_baixa,
                pod_longitude_baixa,
                latitude,
                longitude,
                data_operacao,
                usuario_id,
                usuario_nome,
                usuario_perfil
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registros
        )
        conn.commit()

    return len(registros), data_operacao


def carregar_historico(limite=50):

    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT
                data_operacao,
                spx,
                endereco,
                status,
                horario_baixa,
                ocorrencia,
                observacao,
                pod_foto_nome,
                pod_recebedor,
                pod_assinatura,
                pod_horario_entrega,
                pod_latitude_baixa,
                pod_longitude_baixa,
                latitude,
                longitude,
                usuario_nome,
                usuario_perfil
            FROM historico_pacotes
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(limite,)
        )


def carregar_dados_dashboard():

    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT
                data_operacao,
                spx,
                endereco,
                status,
                horario_baixa,
                ocorrencia,
                observacao,
                pod_foto_nome,
                pod_recebedor,
                pod_assinatura,
                pod_horario_entrega,
                pod_latitude_baixa,
                pod_longitude_baixa,
                latitude,
                longitude,
                usuario_nome,
                usuario_perfil
            FROM historico_pacotes
            ORDER BY id DESC
            """,
            conn
        )
