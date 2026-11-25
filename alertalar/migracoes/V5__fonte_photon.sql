-- =====================================================================
-- Reserva da geocodificação: Photon (komoot), com os mesmos dados do OpenStreetMap.
-- Usado quando o Nominatim público recusa pedidos (limite por IP) ou não responde.
-- =====================================================================
INSERT INTO fonte_dados (codigo, nome, tipo, url, status_integracao, oficial, descricao, atribuicao) VALUES
('PHOTON', 'Photon (komoot) - geocodificação de reserva', 'API_EXTERNA', 'https://photon.komoot.io', 'ATIVA', FALSE,
 'Converte o endereço em latitude e longitude quando o Nominatim recusa pedidos ou não responde, ou quando ele não encontra o endereço. Usa os mesmos dados do OpenStreetMap. Resultados com nome diferente do digitado valem só como posição aproximada, para a pessoa confirmar no mapa.',
 '© Colaboradores do OpenStreetMap (ODbL); busca: Photon (komoot)');
