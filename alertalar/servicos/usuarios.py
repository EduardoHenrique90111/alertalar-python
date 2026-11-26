from __future__ import annotations

import bcrypt

from alertalar.erros import ContaDesativada, FalhaAutenticacao, RegraNegocio, RequisicaoInvalida
from alertalar.esquemas import RegistroRequest
from alertalar.modelos.entidades import Usuario
from alertalar.modelos.enums import PapelUsuario
from alertalar.repositorios import UsuarioRepositorio
from alertalar.util import texto as txt

CUSTO_BCRYPT = 12
LIMITE_BYTES_BCRYPT = 72


def gerar_hash(senha: str, custo: int = CUSTO_BCRYPT) -> str:
    dados = senha.encode("utf-8")
    if len(dados) > LIMITE_BYTES_BCRYPT:
        raise RequisicaoInvalida("A senha não pode ter mais de 72 bytes.")
    return bcrypt.hashpw(dados, bcrypt.gensalt(custo)).decode("ascii")


def confere_senha(senha: str, hash_guardado: str) -> bool:
    dados = senha.encode("utf-8")
    if len(dados) > LIMITE_BYTES_BCRYPT:
        return False
    try:
        return bcrypt.checkpw(dados, hash_guardado.encode("ascii"))
    except ValueError:
        return False


class UsuarioService:
    def __init__(self, repositorio: UsuarioRepositorio, custo_bcrypt: int = CUSTO_BCRYPT):
        self.repositorio = repositorio
        self.custo = custo_bcrypt
        self._hash_falso = gerar_hash("senha-inexistente-0", custo_bcrypt)

    def registrar(self, req: RegistroRequest) -> Usuario:
        return self.criar(req.nome, req.email, req.senha, PapelUsuario.USUARIO)

    def criar(self, nome: str, email: str, senha: str, papel: PapelUsuario) -> Usuario:
        email_normalizado = email.strip().lower()
        if self.repositorio.existe_email(email_normalizado):
            raise RegraNegocio("Já existe uma conta com este e-mail.")
        usuario = Usuario(nome=txt.limpar(nome), email=email_normalizado,
                          senha_hash=gerar_hash(senha, self.custo), papel=papel, ativo=True)
        return self.repositorio.salvar(usuario)

    def por_email(self, email: str | None) -> Usuario | None:
        return None if email is None else self.repositorio.por_email(email.strip())

    def autenticar(self, email: str, senha: str) -> Usuario:
        usuario = self.por_email(email)
        if usuario is None:
            confere_senha(senha, self._hash_falso)
            raise FalhaAutenticacao()
        if not usuario.ativo:
            raise ContaDesativada()
        if not confere_senha(senha, usuario.senha_hash):
            raise FalhaAutenticacao()
        return usuario
