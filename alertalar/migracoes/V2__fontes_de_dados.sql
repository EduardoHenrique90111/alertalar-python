-- =====================================================================
-- Cadastro das fontes de dados conhecidas pelo AlertaLar.
-- São METADADOS (nome, endereço, situação da integração), não dados de risco.
-- data_atualizacao fica vazia até a fonte ser acessada/importada de fato.
-- =====================================================================
INSERT INTO fonte_dados (codigo, nome, tipo, url, status_integracao, oficial, descricao, atribuicao) VALUES
('VIACEP', 'ViaCEP', 'API_EXTERNA', 'https://viacep.com.br', 'ATIVA', FALSE,
 'Consulta de CEP para preencher logradouro, bairro, cidade, UF e código IBGE do município. Não fornece coordenadas.',
 'ViaCEP'),

('NOMINATIM', 'OpenStreetMap Nominatim (geocodificação)', 'API_EXTERNA', 'https://nominatim.openstreetmap.org', 'ATIVA', FALSE,
 'Converte o endereço em latitude e longitude. Serviço público com limite de 1 requisição por segundo; os resultados são guardados em cache no banco.',
 '© Colaboradores do OpenStreetMap (ODbL)'),

('IBGE_LOCALIDADES', 'IBGE - API de Localidades', 'API_EXTERNA', 'https://servicodados.ibge.gov.br/api/docs/localidades', 'ATIVA', TRUE,
 'Identifica o código IBGE do município, usado para relacionar o endereço aos registros oficiais municipais.',
 'IBGE'),

('OSM_CURSOS_AGUA', 'OpenStreetMap - rios, córregos, canais e corpos d''água (Overpass API)', 'BASE_GEOGRAFICA', 'https://overpass-api.de', 'ATIVA', FALSE,
 'Geometria de cursos d''água e corpos d''água próximos ao endereço, consultada no momento da análise. A completude do mapeamento varia por região; córregos canalizados podem não aparecer.',
 '© Colaboradores do OpenStreetMap (ODbL)'),

('COPERNICUS_DEM', 'Copernicus DEM GLO-90 (elevação do terreno, via Open-Meteo)', 'BASE_GEOGRAFICA', 'https://open-meteo.com/en/docs/elevation-api', 'ATIVA', FALSE,
 'Modelo digital de elevação global com resolução de 90 metros (versão 2021). Útil para comparar alturas relativas; não substitui levantamento topográfico local.',
 'Copernicus DEM GLO-90 © DLR e.V. / Airbus, fornecido pelo programa Copernicus; servido pela Open-Meteo'),

('SGB_SETORES_RISCO', 'Serviço Geológico do Brasil (SGB/CPRM) - Setorização de Riscos', 'BASE_GEOGRAFICA', 'https://geoportal.sgb.gov.br/server/rest/services/gestaoterritorial/risco/MapServer', 'ATIVA', TRUE,
 'Setores de risco alto e muito alto mapeados pelo SGB em municípios selecionados. Somente setores de natureza hidrológica (inundação, enxurrada, alagamento) entram na análise. A ausência de setor não significa ausência de risco.',
 'Serviço Geológico do Brasil - SGB'),

('S2ID_RECONHECIMENTOS', 'MIDR/Sedec - S2iD e Atlas Digital de Desastres (registros municipais)', 'IMPORTACAO_OFICIAL', 'https://s2id.mi.gov.br', 'IMPORTACAO_MANUAL', TRUE,
 'Registros oficiais de desastres por município (inundações, enxurradas e alagamentos). Não há API pública documentada: o administrador baixa a planilha oficial no S2iD/Atlas Digital e a importa pelo painel. Os registros são municipais e não indicam a rua afetada.',
 'Ministério da Integração e do Desenvolvimento Regional - Defesa Civil Nacional'),

('ALERTALAR_RELATOS', 'Relatos de usuários do AlertaLar', 'RELATO_USUARIO', NULL, 'ATIVA', FALSE,
 'Relatos de alagamento enviados por usuários. Só entram na análise de risco depois de validados por um administrador.',
 'Usuários do AlertaLar'),

('OPEN_METEO_PREVISAO', 'Open-Meteo - chuva observada e prevista', 'API_EXTERNA', 'https://open-meteo.com/en/docs', 'ATIVA', FALSE,
 'Chuva acumulada recente e prevista para o ponto consultado (modelos meteorológicos). Mostrada como situação atual; não altera a classificação de risco histórico.',
 'Dados meteorológicos por Open-Meteo.com (CC BY 4.0)'),

('OPEN_METEO_GLOFAS', 'GloFAS - vazão modelada de rios (via Open-Meteo Flood API)', 'API_EXTERNA', 'https://open-meteo.com/en/docs/flood-api', 'ATIVA', FALSE,
 'Vazão diária simulada do rio mais próximo na grade de ~5 km do GloFAS (Copernicus). Indicador de contexto da situação atual; pode não representar rios pequenos.',
 'GloFAS / Copernicus Emergency Management Service; servido pela Open-Meteo'),

('CEMADEN', 'CEMADEN - Centro Nacional de Monitoramento e Alertas de Desastres Naturais', 'API_EXTERNA', 'https://www.gov.br/cemaden', 'PLANEJADA', TRUE,
 'Integração ainda NÃO implementada: o acesso programático aos dados de pluviômetros exige cadastro/credencial. A estrutura de fontes está preparada para incluí-la.',
 'CEMADEN/MCTI'),

('INMET', 'INMET - Instituto Nacional de Meteorologia', 'API_EXTERNA', 'https://portal.inmet.gov.br', 'PLANEJADA', TRUE,
 'Integração ainda NÃO implementada: não foi encontrada documentação pública estável da API de avisos. Consulte os avisos oficiais diretamente no portal do INMET.',
 'INMET'),

('ANA_HIDROWEB', 'ANA - HidroWebService (estações hidrológicas)', 'API_EXTERNA', 'https://www.ana.gov.br/hidrowebservice', 'REQUER_CREDENCIAL', TRUE,
 'Integração ainda NÃO implementada: o HidroWebService exige cadastro e credenciais de acesso. Prevista para níveis de rios em tempo real.',
 'Agência Nacional de Águas e Saneamento Básico - ANA');
