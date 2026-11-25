-- =====================================================================
-- 1) Novo tipo de evento: chuvas intensas (COBRADE 1.3.2.1.4), usado em muitos registros
--    oficiais de desastres ligados a chuva (ex.: Rio Grande do Sul, 2024).
-- 2) Fonte de dados do cálculo de rotas seguras.
-- =====================================================================
ALTER TABLE ocorrencia DROP CONSTRAINT ck_ocorrencia_tipo;
ALTER TABLE ocorrencia ADD CONSTRAINT ck_ocorrencia_tipo
    CHECK (tipo_evento IN ('ALAGAMENTO', 'INUNDACAO', 'ENXURRADA', 'CHUVA_INTENSA', 'OUTRO'));

INSERT INTO fonte_dados (codigo, nome, tipo, url, status_integracao, oficial, descricao, atribuicao) VALUES
('VALHALLA_ROTAS', 'Valhalla - cálculo de rotas sobre o OpenStreetMap', 'API_EXTERNA',
 'https://valhalla.github.io/valhalla/', 'ATIVA', FALSE,
 'Calcula o caminho a pé ou de carro da rota segura, desviando dos setores de risco hidrológico do SGB quando possível. Por padrão usa o servidor público da FOSSGIS (uso moderado, até 1 requisição por segundo).',
 'Rotas: Valhalla (FOSSGIS). Dados de vias © colaboradores do OpenStreetMap (ODbL)');
