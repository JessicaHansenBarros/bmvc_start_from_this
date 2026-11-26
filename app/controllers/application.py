from datetime import datetime
import os
import sys
import threading
import uuid
from bottle import TEMPLATE_PATH, redirect, request, response, template

# Calcula o diretório base do projeto (bmvc_start_from_this)
CONTROLLER_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(CONTROLLER_DIR)
BASE_DIR = os.path.dirname(APP_DIR)
VIEWS_DIR = os.path.join(APP_DIR, 'views', 'html')

# Adiciona ao sys.path para garantir importações das classes e db
for path in [BASE_DIR, os.path.join(APP_DIR, 'models'), os.path.join(BASE_DIR, 'classes')]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Adiciona ao TEMPLATE_PATH do Bottle de forma absoluta
if VIEWS_DIR not in TEMPLATE_PATH:
    TEMPLATE_PATH.insert(0, VIEWS_DIR)

from app.controllers.websocket_server import WebSocketClient, WebSocketHub
from classes.portal import PortalAlfabeta


def formatar_data(data_str: str) -> str:
    """Converte datas HTML (AAAA-MM-DD) para o formato do banco (DD/MM/AA)."""
    if not data_str:
        return ""
    limpa = data_str.strip()
    if "-" in limpa:
        partes = limpa.split("-")
        if len(partes) == 3:
            ano = partes[0][-2:]
            return f"{partes[2]}/{partes[1]}/{ano}"
    return limpa


def formatar_moeda(valor: float) -> str:
    """Formata um valor numérico em reais (R$ XX,XX)."""
    return f"R$ {valor:.2f}".replace(".", ",")


class Application:
    """
    Controlador principal do BMVC (padrão hgmachine/bmvc_start_from_this).
    Gerencia sessões autenticadas, páginas HTML e atualizações em tempo real via WebSocket.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.portal_model = PortalAlfabeta()
        self.sessions: dict[str, int] = {}
        self.ws_hub = WebSocketHub()

        # Dicionário de páginas gerenciadas pelo Controller (padrão BMVC)
        self.pages = {
            'portal': self.portal,
            'helper': self.helper,
            'cadastro': self.pagina_cadastro,
        }

    def get_session_id(self) -> str | None:
        return request.get_cookie('session_id')

    def get_professor_id_by_session(self, session_id: str | None) -> int | None:
        if not session_id:
            return None
        with self._lock:
            professor_id = self.sessions.get(session_id)
            if professor_id is None:
                return None
            if self.portal_model.obter_professor(professor_id) is None:
                self.sessions.pop(session_id, None)
                return None
            return professor_id

    @property
    def current_user(self):
        professor_id = self.get_professor_id_by_session(self.get_session_id())
        if professor_id is None:
            return None
        with self._lock:
            return self.portal_model.obter_professor(professor_id)

    def _invalidar_sessoes_professor(self, professor_id: int) -> None:
        chaves = [sid for sid, pid in self.sessions.items() if pid == professor_id]
        for sid in chaves:
            self.sessions.pop(sid, None)

    def _serializar_resumo(self, resumo) -> dict:
        return {
            'total_aulas': resumo.total_aulas,
            'dias_trabalhados': resumo.dias_trabalhados,
            'total_vale_transporte': resumo.total_vale_transporte,
            'total_geral': resumo.total_geral,
            'total_aulas_fmt': formatar_moeda(resumo.total_aulas),
            'total_vt_fmt': formatar_moeda(resumo.total_vale_transporte),
            'total_geral_fmt': formatar_moeda(resumo.total_geral),
        }

    def _serializar_estado(
        self,
        professor,
        motivo: str = 'atualizacao',
        mensagem: str | None = None,
        tem_vt: str | None = None,
    ) -> dict:
        with self._lock:
            aulas = self.portal_model.listar_aulas(professor)
            resumo_com_vt = self.portal_model.calcular_salario(professor, 11.0)
            resumo_sem_vt = self.portal_model.calcular_salario(professor, None)

            aulas_serializadas = [
                {
                    'indice': idx,
                    'nome': aula.aluno.nome,
                    'tipo_aula': aula.tipo_aula,
                    'data_aula': aula.data_aula,
                    'valor': round(aula.calcular_valor(), 2),
                    'valor_fmt': formatar_moeda(aula.calcular_valor()),
                }
                for idx, aula in enumerate(aulas)
            ]

            payload = {
                'type': 'agenda_atualizada',
                'motivo': motivo,
                'mensagem': mensagem,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'clientes_conectados': self.ws_hub.count_professor_clients(professor.id),
                'professor': {
                    'id': professor.id,
                    'nome': professor.nome,
                    'email': professor.email,
                    'login': professor.login,
                },
                'aulas': aulas_serializadas,
                'total_registros': len(aulas_serializadas),
                'resumo_com_vt': self._serializar_resumo(resumo_com_vt),
                'resumo_sem_vt': self._serializar_resumo(resumo_sem_vt),
            }
            if tem_vt in ('sim', 'nao'):
                payload['tem_vt_selecionado'] = tem_vt
            return payload

    def _notificar_professor(
        self,
        professor,
        motivo: str,
        mensagem: str | None = None,
        tem_vt: str | None = None,
        exclude: WebSocketClient | None = None,
    ) -> None:
        if professor is None or professor.id is None:
            return
        payload = self._serializar_estado(
            professor,
            motivo=motivo,
            mensagem=mensagem,
            tem_vt=tem_vt,
        )
        self.ws_hub.broadcast_professor(professor.id, payload, exclude=exclude)

    #-------------------------------------------------------------------------
    # Callbacks WebSocket (bidirecional em tempo real):

    def ws_on_connect(self, client: WebSocketClient) -> None:
        with self._lock:
            professor = self.portal_model.obter_professor(client.professor_id)
            if professor is None:
                client.close()
                return
            payload = self._serializar_estado(
                professor,
                motivo='conexao_inicial',
                mensagem='Conectado ao canal WebSocket em tempo real.',
            )
        client.send_json(payload)
        self._notificar_professor(
            professor,
            motivo='presenca',
            mensagem=None,
            exclude=client,
        )

    def ws_on_disconnect(self, client: WebSocketClient) -> None:
        with self._lock:
            professor = self.portal_model.obter_professor(client.professor_id)
        if professor is not None:
            self._notificar_professor(professor, motivo='presenca', mensagem=None)

    def ws_on_message(self, client: WebSocketClient, dados: dict) -> None:
        acao = str(dados.get('action') or '').strip().lower()
        if acao == 'ping':
            client.send_json({
                'type': 'pong',
                'timestamp': datetime.now().strftime('%H:%M:%S'),
            })
            return

        with self._lock:
            professor = self.portal_model.obter_professor(client.professor_id)
            if professor is None:
                client.send_json({'type': 'conta_excluida'})
                return

            if acao == 'sincronizar':
                payload = self._serializar_estado(
                    professor,
                    motivo='sincronizacao',
                    mensagem='Dados sincronizados em tempo real.',
                )
                client.send_json(payload)
                return

            try:
                if acao == 'adicionar_aula':
                    nome_limpo = str(dados.get('nome_aluno') or '').strip()
                    opcao_tipo = str(dados.get('opcao_tipo') or '').strip()
                    data_formatada = formatar_data(str(dados.get('data_aula') or ''))
                    if not nome_limpo or not opcao_tipo or not data_formatada:
                        raise ValueError('Todos os campos são obrigatórios!')
                    nova_aula = self.portal_model.adicionar_aula(
                        professor=professor,
                        nome_aluno=nome_limpo,
                        data_aula=data_formatada,
                        opcao_tipo=opcao_tipo,
                    )
                    self._notificar_professor(
                        professor,
                        motivo='aula_adicionada',
                        mensagem=f"Aula para o aluno '{nova_aula.aluno.nome}' adicionada com sucesso!",
                    )
                elif acao == 'alterar_aula':
                    indice = int(dados.get('indice'))
                    novo_nome = str(dados.get('novo_nome') or '')
                    nova_data_raw = str(dados.get('nova_data') or '')
                    nova_opcao_raw = str(dados.get('nova_opcao') or '').strip()
                    data_formatada = formatar_data(nova_data_raw) if nova_data_raw else None
                    opcao = nova_opcao_raw if nova_opcao_raw else None
                    aula_atualizada = self.portal_model.alterar_aula(
                        professor=professor,
                        indice=indice,
                        novo_nome_aluno=novo_nome,
                        nova_data_aula=data_formatada,
                        nova_opcao_tipo=opcao,
                    )
                    self._notificar_professor(
                        professor,
                        motivo='aula_alterada',
                        mensagem=f"Aula de '{aula_atualizada.aluno.nome}' atualizada com sucesso!",
                    )
                elif acao == 'excluir_aula':
                    indice = int(dados.get('indice'))
                    aula_removida = self.portal_model.remover_aula(professor, indice)
                    self._notificar_professor(
                        professor,
                        motivo='aula_excluida',
                        mensagem=(
                            f"Aula do aluno '{aula_removida.aluno.nome}' "
                            f"({aula_removida.data_aula}) excluída com sucesso!"
                        ),
                    )
                elif acao == 'calcular_salario':
                    optou_vt = str(dados.get('tem_vt') or 'sim').strip().lower() in ('sim', '1', 'true')
                    tem_vt = 'sim' if optou_vt else 'nao'
                    self._notificar_professor(
                        professor,
                        motivo='salario_calculado',
                        mensagem='Estimativa salarial recalculada em tempo real.',
                        tem_vt=tem_vt,
                    )
                elif acao == 'finalizar_mes':
                    removidas = self.portal_model.finalizar_mes(professor)
                    self._notificar_professor(
                        professor,
                        motivo='mes_finalizado',
                        mensagem=f"Mês finalizado com sucesso! {removidas} aulas foram arquivadas.",
                    )
                elif acao == 'atualizar_perfil':
                    self.portal_model.atualizar_professor(
                        professor=professor,
                        novo_nome=dados.get('nome'),
                        novo_email=dados.get('email'),
                        novo_login=dados.get('login'),
                        nova_senha=dados.get('nova_senha'),
                    )
                    self._notificar_professor(
                        professor,
                        motivo='perfil_atualizado',
                        mensagem='Dados da conta atualizados com sucesso!',
                    )
                else:
                    client.send_json({
                        'type': 'erro',
                        'mensagem': f"Ação WebSocket desconhecida: '{acao}'.",
                    })
            except Exception as e:
                client.send_json({'type': 'erro', 'mensagem': str(e)})

    #-------------------------------------------------------------------------
    # Métodos de renderização e rotas HTTP:

    def render(self, page, parameter=None, **kwargs):
        """Método de despacho padrão do BMVC."""
        content = self.pages.get(page, self.helper)
        if kwargs:
            return content(**kwargs)
        return content(parameter)

    def helper(self, info=None):
        """Página helper padrão do template BMVC."""
        return template('helper.tpl')

    def pagina_cadastro(self, erro=None, nome='', email='', login=''):
        """Exibe a tela de cadastro de novo professor."""
        return template('cadastro.html', erro=erro, nome=nome, email=email, login=login)

    def cadastrar_professor(self, nome, email, login, senha):
        """Cria um novo professor no banco JSON e exibe a tela de login."""
        try:
            with self._lock:
                self.portal_model.registrar_professor(
                    nome=nome or "",
                    email=email or "",
                    login=login or "",
                    senha=senha or "",
                )
            return template(
                'login.html',
                erro=None,
                mensagem="Conta criada com sucesso! Faça login para continuar."
            )
        except Exception as e:
            return template(
                'cadastro.html',
                erro=str(e),
                nome=nome or "",
                email=email or "",
                login=login or ""
            )

    def portal(
        self,
        aba='adicionar',
        mensagem=None,
        erro=None,
        tem_vt=None,
        resumo=None,
        indice_selecionado=None
    ):
        """
        Página principal:
        - Se logado, exibe o painel do Portal com a aba selecionada.
        - Se deslogado, renderiza a tela de login.
        """
        professor = self.current_user
        if not professor:
            return template('login.html', erro=erro, mensagem=mensagem)

        with self._lock:
            if aba == 'salario' and resumo is None:
                tem_vt = 'sim' if tem_vt is None else tem_vt
                valor_diario = 11.0 if tem_vt == 'sim' else None
                try:
                    resumo = self.portal_model.calcular_salario(professor, valor_diario)
                except Exception as e:
                    print(f"[Erro] Falha ao calcular salário: {e}")

            indice_int = None
            if indice_selecionado is not None and str(indice_selecionado).strip() != "":
                try:
                    indice_int = int(indice_selecionado)
                except (TypeError, ValueError):
                    indice_int = None

            aulas = self.portal_model.listar_aulas(professor)
            return template(
                'portal.html',
                professor=professor,
                aulas=aulas,
                aba=aba,
                mensagem=mensagem,
                erro=erro,
                tem_vt=tem_vt,
                resumo=resumo,
                indice_selecionado=indice_int,
                enumerate=enumerate
            )

    def autenticar(self, login, senha):
        """Autentica o professor contra o banco JSON e inicia sessão por cookie."""
        login_limpo = (login or "").strip()
        senha_limpa = (senha or "").strip()

        if not login_limpo or not senha_limpa:
            return template('login.html', erro="Por favor, preencha o login e a senha.")

        with self._lock:
            professor = self.portal_model.autenticar(login_limpo, senha_limpa)
            if professor and professor.id is not None:
                session_id = uuid.uuid4().hex
                self.sessions[session_id] = professor.id
                response.set_cookie(
                    'session_id',
                    session_id,
                    path='/',
                    httponly=True,
                    max_age=3600,
                )
                return redirect('/portal?aba=adicionar')

        return template('login.html', erro="Login ou senha incorretos! Verifique e tente novamente.")

    def adicionar_aluno(self, nome_aluno, opcao_tipo, data_aula):
        """Cadastra nova aula para o professor logado."""
        professor = self.current_user
        if not professor:
            return redirect('/portal')

        nome_limpo = (nome_aluno or "").strip()
        data_formatada = formatar_data(data_aula)

        if not nome_limpo or not opcao_tipo or not data_formatada:
            return self.portal(aba='adicionar', erro="Todos os campos são obrigatórios!")

        try:
            with self._lock:
                nova_aula = self.portal_model.adicionar_aula(
                    professor=professor,
                    nome_aluno=nome_limpo,
                    data_aula=data_formatada,
                    opcao_tipo=opcao_tipo
                )
                msg = f"Aula para o aluno '{nova_aula.aluno.nome}' adicionada com sucesso!"
            self._notificar_professor(professor, motivo='aula_adicionada', mensagem=msg)
            return self.portal(aba='adicionar', mensagem=msg)
        except Exception as e:
            return self.portal(aba='adicionar', erro=f"Erro ao adicionar aula: {e}")

    def calcular_salario(self, tem_vt_str):
        """Calcula o salário do professor com opção de vale-transporte (R$ 11,00/dia)."""
        professor = self.current_user
        if not professor:
            return redirect('/portal')

        optou_vt = str(tem_vt_str).strip().lower() in ['sim', '1', 'true']
        valor_diario = 11.0 if optou_vt else None

        try:
            with self._lock:
                resumo = self.portal_model.calcular_salario(professor, valor_diario)
            tem_vt = 'sim' if optou_vt else 'nao'
            self._notificar_professor(
                professor,
                motivo='salario_calculado',
                mensagem='Estimativa salarial atualizada.',
                tem_vt=tem_vt,
            )
            return self.portal(aba='salario', tem_vt=tem_vt, resumo=resumo)
        except Exception as e:
            return self.portal(aba='salario', erro=f"Erro ao calcular salário: {e}")

    def alterar_aluno(self, indice_str, novo_nome, nova_data, nova_opcao):
        """Modifica dados de uma aula existente."""
        professor = self.current_user
        if not professor:
            return redirect('/portal')

        try:
            indice = int(indice_str)
            data_formatada = formatar_data(nova_data) if nova_data else None
            opcao = nova_opcao.strip() if nova_opcao and nova_opcao.strip() else None

            with self._lock:
                self.portal_model.alterar_aula(
                    professor=professor,
                    indice=indice,
                    novo_nome_aluno=novo_nome,
                    nova_data_aula=data_formatada,
                    nova_opcao_tipo=opcao
                )
            msg = "Aula atualizada com sucesso!"
            self._notificar_professor(professor, motivo='aula_alterada', mensagem=msg)
            return self.portal(aba='alterar', mensagem=msg)
        except Exception as e:
            return self.portal(aba='alterar', erro=f"Erro ao alterar aula: {e}")

    def remover_aluno(self, indice_str, aba_retorno='excluir'):
        """Remove uma aula específica da agenda do professor logado."""
        professor = self.current_user
        if not professor:
            return redirect('/portal')

        abas_validas = {
            'adicionar', 'salario', 'alterar', 'excluir',
            'historico', 'fim_do_mes', 'perfil'
        }
        aba_destino = aba_retorno if aba_retorno in abas_validas else 'excluir'

        try:
            indice = int(indice_str)
            with self._lock:
                aula_removida = self.portal_model.remover_aula(professor, indice)
            msg = (
                f"Aula do aluno '{aula_removida.aluno.nome}' "
                f"({aula_removida.data_aula}) excluída com sucesso!"
            )
            self._notificar_professor(professor, motivo='aula_excluida', mensagem=msg)
            return self.portal(aba=aba_destino, mensagem=msg)
        except Exception as e:
            return self.portal(aba=aba_destino, erro=f"Erro ao excluir aula: {e}")

    def atualizar_professor(self, nome, email, login, nova_senha):
        """Atualiza os dados cadastrais do professor logado."""
        professor = self.current_user
        if not professor:
            return redirect('/portal')

        try:
            with self._lock:
                self.portal_model.atualizar_professor(
                    professor=professor,
                    novo_nome=nome,
                    novo_email=email,
                    novo_login=login,
                    nova_senha=nova_senha
                )
            msg = "Dados da conta atualizados com sucesso!"
            self._notificar_professor(professor, motivo='perfil_atualizado', mensagem=msg)
            return self.portal(aba='perfil', mensagem=msg)
        except Exception as e:
            return self.portal(aba='perfil', erro=f"Erro ao atualizar conta: {e}")

    def excluir_professor(self):
        """Exclui a conta do professor logado e suas aulas associadas."""
        professor = self.current_user
        if not professor:
            return redirect('/portal')

        try:
            professor_id = professor.id
            with self._lock:
                self.portal_model.remover_professor(professor)
                if professor_id is not None:
                    self._invalidar_sessoes_professor(professor_id)
            response.delete_cookie('session_id', path='/')
            if professor_id is not None:
                self.ws_hub.broadcast_professor(professor_id, {'type': 'conta_excluida'})
            return template(
                'login.html',
                erro=None,
                mensagem="Sua conta foi excluída com sucesso."
            )
        except Exception as e:
            return self.portal(aba='perfil', erro=f"Erro ao excluir conta: {e}")

    def finalizar_mes(self):
        """Encerra e limpa a agenda do professor para o próximo mês."""
        professor = self.current_user
        if not professor:
            return redirect('/portal')

        try:
            with self._lock:
                removidas = self.portal_model.finalizar_mes(professor)
            msg = f"Mês finalizado com sucesso! {removidas} aulas foram arquivadas."
            self._notificar_professor(professor, motivo='mes_finalizado', mensagem=msg)
            return self.portal(aba='fim_do_mes', mensagem=msg)
        except Exception as e:
            return self.portal(aba='fim_do_mes', erro=f"Erro ao finalizar mês: {e}")

    def sair(self):
        """Efetua logout do professor encerrando apenas sua sessão atual."""
        session_id = self.get_session_id()
        if session_id:
            with self._lock:
                self.sessions.pop(session_id, None)
        response.delete_cookie('session_id', path='/')
        return redirect('/portal')
