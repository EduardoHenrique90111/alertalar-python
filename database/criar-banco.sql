-- =====================================================================
-- AlertaLar - criação do usuário e dos bancos no PostgreSQL
-- Execute UMA vez como superusuário (ex.: no psql ou no pgAdmin):
--   psql -U postgres -f database/criar-banco.sql
-- Troque a senha abaixo e use a mesma no arquivo .env (DB_PASSWORD).
--
-- As TABELAS não são criadas aqui: o AlertaLar cria e atualiza a estrutura
-- automaticamente quando o servidor inicia, usando as migrações em
-- alertalar/migracoes (V1__esquema_inicial.sql, V2__fontes_de_dados.sql...).
-- =====================================================================

CREATE ROLE alertalar LOGIN PASSWORD 'troque_esta_senha';

CREATE DATABASE alertalar OWNER alertalar ENCODING 'UTF8';

-- Opcional: banco exclusivo para o teste de integração completo (seus dados são apagados pelo teste)
CREATE DATABASE alertalar_test OWNER alertalar ENCODING 'UTF8';
