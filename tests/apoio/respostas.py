"""Respostas no MESMO FORMATO das APIs reais (ViaCEP, Nominatim, IBGE, Overpass, Open-Meteo, ArcGIS do
SGB, Valhalla). Os valores são fictícios e existem apenas para os testes automatizados."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from alertalar.integracoes.valhalla import codificar

# Ponto de teste (endereço fictício)
LAT = -29.92
LON = -51.18


def via_cep() -> str:
    return """{"cep":"92010-000","logradouro":"Rua de Teste","complemento":"","unidade":"","bairro":"Centro",
 "localidade":"Canoas","uf":"RS","estado":"Rio Grande do Sul","regiao":"Sul","ibge":"4304606",
 "gia":"","ddd":"51","siafi":"8589"}"""


def via_cep_inexistente() -> str:
    return '{"erro": "true"}'


def nominatim_numero() -> str:
    return f"""[{{"place_id":1,"lat":"{LAT:.6f}","lon":"{LON:.6f}","category":"place","type":"house","place_rank":30,
  "addresstype":"place","name":"","display_name":"100, Rua de Teste, Centro, Canoas, Rio Grande do Sul, Brasil",
  "address":{{"house_number":"100","road":"Rua de Teste","suburb":"Centro","city":"Canoas",
  "state":"Rio Grande do Sul","ISO3166-2-lvl4":"BR-RS","postcode":"92010-000","country":"Brasil","country_code":"br"}}}}]"""


def photon(numero: str) -> str:
    """Resposta do Photon (komoot) no formato real (GeoJSON): um imóvel com número, a rua, um lugar
    (shopping) e um resultado fora do Brasil, que deve ser ignorado."""
    return f"""{{"type":"FeatureCollection","features":[
 {{"type":"Feature","geometry":{{"type":"Point","coordinates":[{LON:.6f},{LAT:.6f}]}},
  "properties":{{"osm_type":"N","osm_id":101,"osm_key":"place","osm_value":"house","type":"house",
   "housenumber":"{numero}","street":"Rua de Teste","district":"Centro","city":"Canoas","county":"Região Metropolitana de Porto Alegre",
   "state":"Rio Grande do Sul","postcode":"92010-000","country":"Brasil","countrycode":"BR"}}}},
 {{"type":"Feature","geometry":{{"type":"Point","coordinates":[{LON + 0.001:.6f},{LAT + 0.001:.6f}]}},
  "properties":{{"osm_type":"W","osm_id":102,"osm_key":"highway","osm_value":"residential","type":"street",
   "name":"Rua de Teste","district":"Centro","city":"Canoas","state":"Rio Grande do Sul","country":"Brasil","countrycode":"BR"}}}},
 {{"type":"Feature","geometry":{{"type":"Point","coordinates":[-51.1834,-29.9178]}},
  "properties":{{"osm_type":"W","osm_id":103,"osm_key":"shop","osm_value":"mall","type":"house","name":"Canoas Shopping",
   "housenumber":"6750","street":"Avenida Guilherme Schell","district":"Centro","city":"Canoas","state":"Rio Grande do Sul",
   "postcode":"92310-000","country":"Brasil","countrycode":"BR"}}}},
 {{"type":"Feature","geometry":{{"type":"Point","coordinates":[-58.38,-34.60]}},
  "properties":{{"osm_key":"highway","osm_value":"residential","type":"street","name":"Rua de Teste","city":"Buenos Aires",
   "country":"Argentina","countrycode":"AR"}}}}]}}"""


def nominatim_apenas_rua() -> str:
    return f"""[{{"place_id":2,"lat":"{LAT:.6f}","lon":"{LON:.6f}","category":"highway","type":"residential","place_rank":26,
  "addresstype":"road","display_name":"Rua de Teste, Centro, Canoas, Rio Grande do Sul, Brasil",
  "address":{{"road":"Rua de Teste","suburb":"Centro","city":"Canoas","state":"Rio Grande do Sul",
  "ISO3166-2-lvl4":"BR-RS","country_code":"br"}}}}]"""


def nominatim_apenas_cidade() -> str:
    return """[{"place_id":3,"lat":"-29.9128","lon":"-51.1857","category":"boundary","type":"administrative","place_rank":16,
  "addresstype":"city","display_name":"Canoas, Rio Grande do Sul, Brasil",
  "address":{"city":"Canoas","state":"Rio Grande do Sul","ISO3166-2-lvl4":"BR-RS","country_code":"br"}}]"""


def ibge_municipios_rs() -> str:
    return '[{"id":4304606,"nome":"Canoas"},{"id":4314902,"nome":"Porto Alegre"},{"id":4318705,"nome":"São Leopoldo"}]'


def overpass_com_rio_e_corrego() -> str:
    """Um rio a ~110 m a leste do ponto e um córrego a ~40 m ao norte."""
    lon_rio = LON + 0.00114  # ~110 m
    lat_corrego = LAT + 0.00036  # ~40 m
    return f"""{{"version":0.6,"generator":"Overpass API","elements":[
  {{"type":"way","id":101,"tags":{{"waterway":"river","name":"Rio dos Testes"}},
   "geometry":[{{"lat":{LAT - 0.005:.6f},"lon":{lon_rio:.6f}}},{{"lat":{LAT + 0.005:.6f},"lon":{lon_rio:.6f}}}]}},
  {{"type":"way","id":102,"tags":{{"waterway":"stream","name":"Arroio Pequeno"}},
   "geometry":[{{"lat":{lat_corrego:.6f},"lon":{LON - 0.003:.6f}}},{{"lat":{lat_corrego:.6f},"lon":{LON + 0.003:.6f}}}]}}
]}}"""


def overpass_vazio() -> str:
    return '{"version":0.6,"elements":[]}'


def elevacao(quantidade: int) -> str:
    """Elevações: ponto 4 m, entorno 9 m, água 3 m (mesma ordem da requisição)."""
    valores = ["4.0"] + ["9.0" if i <= 8 else "3.0" for i in range(1, quantidade)]
    return '{"elevation":[' + ",".join(valores) + "]}"


def sgb_sem_setores() -> str:
    return '{"objectIdFieldName":"objectid","geometryType":"esriGeometryPolygon","features":[]}'


def sgb_setor_contendo_ponto() -> str:
    """Setor de inundação "Muito alto" contendo o ponto de teste."""
    d = 0.001
    anel = [(LON - d, LAT - d), (LON + d, LAT - d), (LON + d, LAT + d), (LON - d, LAT + d), (LON - d, LAT - d)]
    aneis = ",".join(f"[{x:.6f},{y:.6f}]" for x, y in anel)
    return ('{"objectIdFieldName":"objectid","geometryType":"esriGeometryPolygon","spatialReference":{"wkid":4326},'
            '"features":[{"attributes":{"objectid":7,"uf":"RS","munic":"Canoas","num_setor":"RS_CANOAS_SR_01_SGB",'
            '"local":"Bairro de teste","tipolo_g1":"Hidrológico","tipolo_e1":"Inundação","cobrade_01":"1.2.1.0.0",'
            '"descricao":"Área de planície às margens do rio","grau_risco":"Muito alto","data_setor":1704067200000},'
            f'"geometry":{{"rings":[[{aneis}]]}}}}]}}')


def sgb_erro() -> str:
    return '{"error":{"code":400,"message":"Unable to complete operation.","details":[]}}'


def previsao_chuva(agora_utc: datetime) -> str:
    """Chuva horária: 2 mm/h nas últimas 24 h e 1 mm/h depois, no fuso -03:00."""
    local = agora_utc.astimezone(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    inicio = local.replace(minute=0, second=0, microsecond=0) - timedelta(hours=30)
    tempos, valores = [], []
    for i in range(30 + 80):
        h = inicio + timedelta(hours=i)
        tempos.append('"' + h.strftime("%Y-%m-%dT%H:%M") + '"')
        valores.append("1.0" if h > local else "2.0")
    return ('{"latitude":-29.92,"longitude":-51.18,"utc_offset_seconds":-10800,"timezone":"America/Sao_Paulo",'
            '"hourly_units":{"precipitation":"mm"},"hourly":{"time":[' + ",".join(tempos) + '],"precipitation":['
            + ",".join(valores) + "]}}")


def vazao(hoje: date) -> str:
    """Vazão diária crescente (100 → 200 m³/s) de 7 dias atrás até 7 dias à frente."""
    tempos = ",".join(f'"{(hoje + timedelta(days=i)).isoformat()}"' for i in range(-7, 8))
    valores = ",".join("100.0" if i <= 0 else "200.0" for i in range(-7, 8))
    return ('{"latitude":-29.92,"longitude":-51.18,"daily_units":{"river_discharge":"m³/s"},'
            '"daily":{"time":[' + tempos + '],"river_discharge":[' + valores + "]}}")


def valhalla_rota(lat_o: float, lon_o: float, lat_d: float, lon_d: float) -> str:
    """Resposta do Valhalla (/route): trajeto em 3 pontos, com o "shape" em polyline de precisão 6."""
    shape = codificar([(lat_o, lon_o), (lat_o, lon_d), (lat_d, lon_d)], 6).replace("\\", "\\\\")
    return f"""{{"trip":{{"locations":[{{"type":"break","lat":{lat_o:.6f},"lon":{lon_o:.6f}}},{{"type":"break","lat":{lat_d:.6f},"lon":{lon_d:.6f}}}],
 "legs":[{{"maneuvers":[
   {{"type":2,"instruction":"Siga a leste na Rua de Teste.","time":120.5,"length":0.150,"begin_shape_index":0,"end_shape_index":1}},
   {{"type":15,"instruction":"Vire à esquerda na Rua do Morro.","time":90.0,"length":0.110,"begin_shape_index":1,"end_shape_index":2}},
   {{"type":4,"instruction":"Você chegou ao seu destino.","time":0.0,"length":0.0,"begin_shape_index":2,"end_shape_index":2}}],
  "summary":{{"length":0.260,"time":210.5}},"shape":"{shape}"}}],
 "summary":{{"length":0.260,"time":210.5}},"status_message":"Found route between points","status":0,
 "units":"kilometers","language":"pt-BR"}}}}"""


def valhalla_sem_caminho() -> str:
    """Erro do Valhalla quando não há caminho entre os pontos (HTTP 400)."""
    return '{"error_code":442,"error":"No path could be found for input","status_code":400,"status":"Bad Request"}'
