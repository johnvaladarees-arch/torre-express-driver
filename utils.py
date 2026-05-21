import math
import re
import unicodedata
import pandas as pd
from io import BytesIO


def limpar_texto(texto):

    texto = str(texto).strip().upper()

    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    texto = re.sub(r"\s+", " ", texto)

    texto = re.sub(r"[.,;]", "", texto)

    return texto


def normalizar_endereco(endereco):

    endereco = limpar_texto(endereco)

    endereco = endereco.replace(" R ", " RUA ")
    endereco = endereco.replace(" AV ", " AVENIDA ")
    endereco = endereco.replace(" TV ", " TRAVESSA ")
    endereco = endereco.replace(" R.", " RUA ")
    endereco = endereco.replace(" AV.", " AVENIDA ")

    endereco = re.sub(r"\s+", " ", endereco)

    return endereco.strip()


def distancia_km(lat1, lon1, lat2, lon2):

    raio_terra = 6371

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return raio_terra * c


def encontrar_coluna(df, possibilidades):

    for col in df.columns:

        nome = str(col).lower().strip()

        for p in possibilidades:

            if p in nome:
                return col

    return None


def ordenar_paradas_inteligente(
    paradas,
    col_lat,
    col_lon,
    lat_motorista,
    lon_motorista
):

    if len(paradas) == 0:
        return paradas

    restantes = paradas.copy().reset_index(drop=True)

    rota = []

    menores = restantes.apply(
        lambda r: distancia_km(
            lat_motorista,
            lon_motorista,
            r[col_lat],
            r[col_lon]
        ),
        axis=1
    )

    idx_primeiro = menores.idxmin()

    atual = restantes.loc[idx_primeiro]

    rota.append(atual)

    restantes = (
        restantes
        .drop(index=idx_primeiro)
        .reset_index(drop=True)
    )

    while len(restantes) > 0:

        lat_atual = atual[col_lat]
        lon_atual = atual[col_lon]

        menores = restantes.apply(
            lambda r: distancia_km(
                lat_atual,
                lon_atual,
                r[col_lat],
                r[col_lon]
            ),
            axis=1
        )

        idx_proximo = menores.idxmin()

        atual = restantes.loc[idx_proximo]

        rota.append(atual)

        restantes = (
            restantes
            .drop(index=idx_proximo)
            .reset_index(drop=True)
        )

    return pd.DataFrame(rota).reset_index(drop=True)


def estimar_raio_regiao(paradas, col_lat, col_lon):

    if len(paradas) <= 2:
        return 1.2

    distancias = []

    for idx, row in paradas.iterrows():
        menores = []

        for outro_idx, outra in paradas.iterrows():
            if idx == outro_idx:
                continue

            menores.append(
                distancia_km(
                    row[col_lat],
                    row[col_lon],
                    outra[col_lat],
                    outra[col_lon]
                )
            )

        if menores:
            distancias.append(min(menores))

    if not distancias:
        return 1.2

    mediana = pd.Series(distancias).median()

    return max(0.8, min(3.0, mediana * 2.7))


def nomear_regiao(cluster, numero):

    if "Bairro" in cluster.columns:
        bairros = (
            cluster["Bairro"]
            .dropna()
            .astype(str)
            .str.strip()
        )

        bairros = bairros[bairros != ""]

        if len(bairros) > 0:
            return bairros.mode().iloc[0]

    if "City" in cluster.columns:
        cidades = (
            cluster["City"]
            .dropna()
            .astype(str)
            .str.strip()
        )

        cidades = cidades[cidades != ""]

        if len(cidades) > 0:
            return cidades.mode().iloc[0]

    return f"Zona {numero}"


def ordenar_paradas_por_regiao(
    paradas,
    col_lat,
    col_lon,
    lat_motorista,
    lon_motorista
):

    if len(paradas) == 0:
        return paradas

    base = paradas.copy().reset_index(drop=True)
    base[col_lat] = pd.to_numeric(base[col_lat], errors="coerce")
    base[col_lon] = pd.to_numeric(base[col_lon], errors="coerce")

    validas = base.dropna(subset=[col_lat, col_lon]).reset_index(drop=True)
    invalidas = base[base[[col_lat, col_lon]].isna().any(axis=1)].copy()

    if len(validas) == 0:
        base["_Regiao_Operacional"] = 1
        base["_Nome_Regiao"] = nomear_regiao(base, 1)
        base["_Raio_Regiao_KM"] = 0
        return base

    raio_regiao = estimar_raio_regiao(validas, col_lat, col_lon)
    nao_visitados = set(validas.index)
    componentes = []

    while nao_visitados:
        inicio = min(nao_visitados)
        fila = [inicio]
        componente = []
        nao_visitados.remove(inicio)

        while fila:
            atual = fila.pop(0)
            componente.append(atual)
            row_atual = validas.loc[atual]

            vizinhos = []
            for idx in sorted(nao_visitados):
                row_vizinho = validas.loc[idx]
                distancia = distancia_km(
                    row_atual[col_lat],
                    row_atual[col_lon],
                    row_vizinho[col_lat],
                    row_vizinho[col_lon]
                )

                if distancia <= raio_regiao:
                    vizinhos.append(idx)

            for idx in sorted(vizinhos):
                nao_visitados.remove(idx)
                fila.append(idx)

        componentes.append(validas.loc[componente].copy())

    regioes = []
    lat_referencia = float(lat_motorista)
    lon_referencia = float(lon_motorista)

    while componentes:
        distancias_regioes = []

        for posicao, componente in enumerate(componentes):
            distancia_entrada = componente.apply(
                lambda r: distancia_km(
                    lat_referencia,
                    lon_referencia,
                    r[col_lat],
                    r[col_lon]
                ),
                axis=1
            ).min()
            distancias_regioes.append((distancia_entrada, posicao))

        _, posicao_regiao = min(distancias_regioes, key=lambda item: item[0])
        componente = componentes.pop(posicao_regiao)

        cluster_ordenado = ordenar_paradas_inteligente(
            componente,
            col_lat,
            col_lon,
            lat_referencia,
            lon_referencia
        )

        numero_regiao = len(regioes) + 1
        nome_regiao = nomear_regiao(cluster_ordenado, numero_regiao)

        cluster_ordenado["_Regiao_Operacional"] = numero_regiao
        cluster_ordenado["_Nome_Regiao"] = nome_regiao
        cluster_ordenado["_Raio_Regiao_KM"] = raio_regiao

        regioes.append(cluster_ordenado)

        ultima_parada = cluster_ordenado.iloc[-1]
        lat_referencia = float(ultima_parada[col_lat])
        lon_referencia = float(ultima_parada[col_lon])

    if len(invalidas) > 0:
        invalidas = invalidas.reset_index(drop=True)
        numero_regiao = len(regioes) + 1
        invalidas["_Regiao_Operacional"] = numero_regiao
        invalidas["_Nome_Regiao"] = "Sem coordenada"
        invalidas["_Raio_Regiao_KM"] = raio_regiao
        regioes.append(invalidas)

    return pd.concat(regioes, ignore_index=True)


def calcular_km_rota(
    paradas,
    col_lat,
    col_lon,
    lat_motorista,
    lon_motorista
):

    if len(paradas) == 0:
        return 0

    km_total = 0

    lat_atual = lat_motorista
    lon_atual = lon_motorista

    for _, row in paradas.iterrows():
        if pd.isna(row[col_lat]) or pd.isna(row[col_lon]):
            continue

        km_total += distancia_km(
            lat_atual,
            lon_atual,
            row[col_lat],
            row[col_lon]
        )

        lat_atual = row[col_lat]
        lon_atual = row[col_lon]

    return km_total


def calcular_tempo_horas(km, velocidade_media):

    if velocidade_media <= 0:
        return 0

    return km / velocidade_media


def formatar_tempo(horas):

    minutos_totais = int(horas * 60)

    h = minutos_totais // 60
    m = minutos_totais % 60

    if h > 0:
        return f"{h}h {m}min"

    return f"{m}min"


def exportar_excel(df):

    output = BytesIO()

    df_export = df.copy()

    colunas_remover = [
        "_Ordem_Original",
        "_Endereco_Normalizado",
        "_SPX_Busca"
    ]

    for col in colunas_remover:

        if col in df_export.columns:
            df_export = df_export.drop(columns=[col])

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df_export.to_excel(
            writer,
            index=False,
            sheet_name="Resultado"
        )

    output.seek(0)

    return output


def encontrar_proxima_parada(
    paradas,
    df,
    regiao_atual=None,
    paradas_puladas=None
):

    if len(paradas) == 0:
        return None

    paradas_puladas = set(paradas_puladas or [])

    pendentes_por_endereco = (
        df[df["Status"] == "Pendente"]
        .groupby("_Endereco_Normalizado")
        .size()
    )

    def primeira_pendente(lista_paradas, permitir_pulada):
        for _, row in lista_paradas.iterrows():
            chave_endereco = row["_Endereco_Normalizado"]

            if not permitir_pulada and chave_endereco in paradas_puladas:
                continue

            if pendentes_por_endereco.get(chave_endereco, 0) > 0:
                return row

        return None

    if regiao_atual is not None:
        paradas_regiao = paradas[
            paradas["_Regiao_Operacional"] == regiao_atual
        ]

        proxima = primeira_pendente(paradas_regiao, permitir_pulada=False)
        if proxima is not None:
            return proxima

        proxima = primeira_pendente(paradas_regiao, permitir_pulada=True)
        if proxima is not None:
            return proxima

    proxima = primeira_pendente(paradas, permitir_pulada=False)
    if proxima is not None:
        return proxima

    proxima = primeira_pendente(paradas, permitir_pulada=True)
    if proxima is not None:
        return proxima

    return None
