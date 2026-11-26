(function () {
    "use strict";

    const state = {
        ws: null,
        reconnectDelay: 1500,
        shouldReconnect: true,
        pingTimer: null,
        lastPayload: null,
        filtroTexto: "",
        temVtSelecionado: "sim",
    };

    const elStatus = document.getElementById("ws-status");
    const elStatusText = document.getElementById("ws-status-text");
    const elFeedback = document.getElementById("ws-feedback");
    const elSyncInfo = document.getElementById("ws-sync-info");
    const elFiltro = document.getElementById("filtro-alunos");
    const elTabelaBody = document.getElementById("tabela-aulas-body");
    const elTabela = document.getElementById("tabela-aulas");
    const elTabelaVazia = document.getElementById("tabela-aulas-vazia");

    const abaAtual = document.body.dataset.aba || "adicionar";

    function atualizarStatusBadge(modo, texto) {
        if (!elStatus || !elStatusText) return;
        elStatus.classList.remove("ws-connecting", "ws-connected", "ws-disconnected");
        elStatus.classList.add(modo);
        elStatusText.textContent = texto;
    }

    function mostrarFeedback(texto, tipo) {
        if (!elFeedback || !texto) return;
        elFeedback.textContent = texto;
        elFeedback.className = tipo === "erro" ? "alert-error" : "alert-success";
        elFeedback.style.display = "block";
        clearTimeout(elFeedback._hideTimer);
        elFeedback._hideTimer = setTimeout(() => {
            elFeedback.style.display = "none";
        }, 5000);
    }

    function wsPronto() {
        return state.ws && state.ws.readyState === WebSocket.OPEN;
    }

    function enviarWs(payload) {
        if (!wsPronto()) return false;
        state.ws.send(JSON.stringify(payload));
        return true;
    }

    function conectarWebSocket() {
        const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${protocolo}//${window.location.host}/ws`;
        atualizarStatusBadge("ws-connecting", "Conectando tempo real...");

        const ws = new WebSocket(url);
        state.ws = ws;

        ws.addEventListener("open", () => {
            state.reconnectDelay = 1500;
            atualizarStatusBadge("ws-connected", "Tempo real ativo");
            clearInterval(state.pingTimer);
            state.pingTimer = setInterval(() => {
                enviarWs({ action: "ping" });
            }, 25000);
        });

        ws.addEventListener("message", (event) => {
            let dados;
            try {
                dados = JSON.parse(event.data);
            } catch (_err) {
                return;
            }
            tratarMensagemServidor(dados);
        });

        ws.addEventListener("close", (event) => {
            clearInterval(state.pingTimer);
            atualizarStatusBadge("ws-disconnected", "Reconectando...");
            if (event.code === 1008 || !state.shouldReconnect) return;
            setTimeout(() => {
                state.reconnectDelay = Math.min(state.reconnectDelay * 1.5, 10000);
                conectarWebSocket();
            }, state.reconnectDelay);
        });

        ws.addEventListener("error", () => {
            atualizarStatusBadge("ws-disconnected", "Erro no WebSocket");
        });
    }

    function tratarMensagemServidor(dados) {
        if (!dados || !dados.type) return;

        if (dados.type === "conta_excluida") {
            state.shouldReconnect = false;
            window.location.href = "/portal";
            return;
        }

        if (dados.type === "erro") {
            mostrarFeedback(dados.mensagem || "Erro ao processar ação.", "erro");
            return;
        }

        if (dados.type === "pong") {
            return;
        }

        if (dados.type === "agenda_atualizada") {
            state.lastPayload = dados;
            if (dados.tem_vt_selecionado) {
                state.temVtSelecionado = dados.tem_vt_selecionado;
            }
            atualizarInterface(dados);

            if (dados.mensagem && dados.motivo !== "conexao_inicial") {
                mostrarFeedback(`⚡ ${dados.mensagem}`, "sucesso");
            }
        }
    }

    function atualizarInterface(dados) {
        const aulas = Array.isArray(dados.aulas) ? dados.aulas : [];

        if (elSyncInfo) {
            const abas = dados.clientes_conectados || 1;
            elSyncInfo.textContent = `⚡ Sincronizado às ${dados.timestamp} • ${abas} aba(s) conectada(s)`;
        }

        if (dados.professor) {
            const elNomeHeader = document.getElementById("header-professor-nome");
            if (elNomeHeader) elNomeHeader.textContent = dados.professor.nome;

            const elPerfilNome = document.getElementById("perfil-nome-resumo");
            const elPerfilEmail = document.getElementById("perfil-email-resumo");
            const elPerfilLogin = document.getElementById("perfil-login-resumo");
            const elPerfilTotal = document.getElementById("perfil-total-aulas");
            if (elPerfilNome) elPerfilNome.textContent = dados.professor.nome;
            if (elPerfilEmail) elPerfilEmail.textContent = dados.professor.email;
            if (elPerfilLogin) elPerfilLogin.textContent = dados.professor.login;
            if (elPerfilTotal) elPerfilTotal.textContent = `${aulas.length} aula(s)`;
        }

        renderizarTabela(aulas);
        atualizarSelects(aulas);
        atualizarSalario(dados);
    }

    function renderizarTabela(aulas) {
        if (!elTabelaBody || !elTabela || !elTabelaVazia) return;

        const termo = state.filtroTexto.trim().toLowerCase();
        const filtradas = termo
            ? aulas.filter(
                  (a) =>
                      a.nome.toLowerCase().includes(termo) ||
                      a.tipo_aula.toLowerCase().includes(termo) ||
                      a.data_aula.toLowerCase().includes(termo)
              )
            : aulas;

        elTabelaBody.innerHTML = "";

        if (aulas.length === 0) {
            elTabela.style.display = "none";
            elTabelaVazia.textContent = "Nenhuma aula adicionada recentemente.";
            elTabelaVazia.style.display = "block";
            return;
        }

        if (filtradas.length === 0) {
            elTabela.style.display = "none";
            elTabelaVazia.textContent = "Nenhuma aula corresponde ao filtro informado.";
            elTabelaVazia.style.display = "block";
            return;
        }

        elTabela.style.display = "table";
        elTabelaVazia.style.display = "none";

        for (const aula of filtradas) {
            const tr = document.createElement("tr");

            const tdNome = document.createElement("td");
            const cell = document.createElement("div");
            cell.className = "aluno-cell";
            const avatar = document.createElement("div");
            avatar.className = "aluno-avatar";
            avatar.textContent = "👤";
            const spanNome = document.createElement("span");
            spanNome.textContent = aula.nome;
            cell.appendChild(avatar);
            cell.appendChild(spanNome);
            tdNome.appendChild(cell);

            const tdTipo = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = "tipo-badge";
            badge.textContent = `Aluno de ${aula.tipo_aula.toLowerCase()} (${aula.valor_fmt})`;
            tdTipo.appendChild(badge);

            const tdData = document.createElement("td");
            tdData.textContent = aula.data_aula;

            const tdAcoes = document.createElement("td");
            const acoes = document.createElement("div");
            acoes.className = "acoes-cell";

            const linkEditar = document.createElement("a");
            linkEditar.href = `/portal?aba=alterar&indice=${aula.indice}`;
            linkEditar.className = "btn-acao btn-acao-editar";
            linkEditar.textContent = "✏️ Editar";

            const formExcluir = document.createElement("form");
            formExcluir.action = "/portal/excluir";
            formExcluir.method = "POST";
            formExcluir.className = "form-excluir-linha";
            formExcluir.style.margin = "0";
            formExcluir.style.display = "inline";

            const inputIndice = document.createElement("input");
            inputIndice.type = "hidden";
            inputIndice.name = "indice";
            inputIndice.value = String(aula.indice);

            const inputAba = document.createElement("input");
            inputAba.type = "hidden";
            inputAba.name = "aba_retorno";
            inputAba.value = abaAtual;

            const btnExcluir = document.createElement("button");
            btnExcluir.type = "submit";
            btnExcluir.className = "btn-acao btn-acao-excluir";
            btnExcluir.textContent = "🗑️ Excluir";

            formExcluir.appendChild(inputIndice);
            formExcluir.appendChild(inputAba);
            formExcluir.appendChild(btnExcluir);

            formExcluir.addEventListener("submit", (event) => {
                if (!confirm("Tem certeza que deseja excluir esta aula?")) {
                    event.preventDefault();
                    return;
                }
                if (wsPronto()) {
                    event.preventDefault();
                    enviarWs({ action: "excluir_aula", indice: aula.indice });
                }
            });

            acoes.appendChild(linkEditar);
            acoes.appendChild(formExcluir);
            tdAcoes.appendChild(acoes);

            tr.appendChild(tdNome);
            tr.appendChild(tdTipo);
            tr.appendChild(tdData);
            tr.appendChild(tdAcoes);
            elTabelaBody.appendChild(tr);
        }
    }

    function atualizarSelects(aulas) {
        const selectAlterar = document.getElementById("indice");
        const formAlterar = document.getElementById("form-alterar");
        const vazioAlterar = document.getElementById("alterar-vazio");
        if (selectAlterar && formAlterar && vazioAlterar) {
            const valorAtual = selectAlterar.value;
            selectAlterar.innerHTML = "";
            for (const aula of aulas) {
                const opt = document.createElement("option");
                opt.value = String(aula.indice);
                opt.textContent = `${aula.indice + 1} - ${aula.nome} (${aula.data_aula} - ${aula.tipo_aula})`;
                if (String(aula.indice) === valorAtual) opt.selected = true;
                selectAlterar.appendChild(opt);
            }
            formAlterar.style.display = aulas.length > 0 ? "block" : "none";
            vazioAlterar.style.display = aulas.length > 0 ? "none" : "block";
        }

        const selectExcluir = document.getElementById("indice_excluir");
        const formExcluir = document.getElementById("form-excluir");
        const vazioExcluir = document.getElementById("excluir-vazio");
        if (selectExcluir && formExcluir && vazioExcluir) {
            const valorAtual = selectExcluir.value;
            selectExcluir.innerHTML = "";
            for (const aula of aulas) {
                const opt = document.createElement("option");
                opt.value = String(aula.indice);
                opt.textContent = `${aula.indice + 1} - ${aula.nome} (${aula.data_aula} - ${aula.tipo_aula} - ${aula.valor_fmt})`;
                if (String(aula.indice) === valorAtual) opt.selected = true;
                selectExcluir.appendChild(opt);
            }
            formExcluir.style.display = aulas.length > 0 ? "block" : "none";
            vazioExcluir.style.display = aulas.length > 0 ? "none" : "block";
        }
    }

    function atualizarSalario(dados) {
        const container = document.getElementById("salario-grid-container");
        if (!container) return;

        const radioChecked = document.querySelector('input[name="tem_vt"]:checked');
        const temVt = dados.tem_vt_selecionado || (radioChecked ? radioChecked.value : state.temVtSelecionado);
        const optouSim = temVt !== "nao";

        const radioSim = document.querySelector('input[name="tem_vt"][value="sim"]');
        const radioNao = document.querySelector('input[name="tem_vt"][value="nao"]');
        if (radioSim && radioNao) {
            radioSim.checked = optouSim;
            radioNao.checked = !optouSim;
        }

        const resumo = optouSim ? dados.resumo_com_vt : dados.resumo_sem_vt;
        if (!resumo) return;

        const elTotalAulas = document.getElementById("sal-total-aulas");
        const elDias = document.getElementById("sal-dias");
        const elVtTitulo = document.getElementById("sal-vt-titulo");
        const elVtValor = document.getElementById("sal-vt-valor");
        const elVtDetalhe = document.getElementById("sal-vt-detalhe");
        const elTotalTitulo = document.getElementById("sal-total-titulo");
        const elTotalGeral = document.getElementById("sal-total-geral");
        const elTotalDetalhe = document.getElementById("sal-total-detalhe");
        const elAvisoZero = document.getElementById("sal-aviso-zero");

        if (elTotalAulas) elTotalAulas.textContent = resumo.total_aulas_fmt;
        if (elDias) elDias.textContent = `${resumo.dias_trabalhados} dia(s)`;

        if (optouSim) {
            if (elVtTitulo) elVtTitulo.textContent = "Vale-Transporte (R$ 11/dia)";
            if (elVtValor) {
                elVtValor.textContent = `+ ${resumo.total_vt_fmt}`;
                elVtValor.style.color = "#2F6F4E";
                elVtValor.style.fontSize = "1.6rem";
            }
            if (elVtDetalhe) {
                elVtDetalhe.textContent = `(${resumo.dias_trabalhados} dia(s) × R$ 11,00)`;
                elVtDetalhe.style.display = "block";
            }
            if (elTotalTitulo) elTotalTitulo.textContent = "Salário Total (Aulas + VT)";
            if (elTotalGeral) elTotalGeral.textContent = resumo.total_geral_fmt;
            if (elTotalDetalhe) {
                elTotalDetalhe.textContent = `(${resumo.total_aulas_fmt} + ${resumo.total_vt_fmt})`;
                elTotalDetalhe.style.display = "block";
            }
        } else {
            if (elVtTitulo) elVtTitulo.textContent = "Vale-Transporte";
            if (elVtValor) {
                elVtValor.textContent = "Não optante (R$ 0,00)";
                elVtValor.style.color = "#718096";
                elVtValor.style.fontSize = "1.1rem";
            }
            if (elVtDetalhe) elVtDetalhe.style.display = "none";
            if (elTotalTitulo) elTotalTitulo.textContent = "Salário Total";
            if (elTotalGeral) elTotalGeral.textContent = resumo.total_geral_fmt;
            if (elTotalDetalhe) elTotalDetalhe.style.display = "none";
        }

        if (elAvisoZero) {
            elAvisoZero.style.display = resumo.dias_trabalhados === 0 && optouSim ? "block" : "none";
        }
    }

    function configurarFormularios() {
        const formAdicionar = document.getElementById("form-adicionar");
        if (formAdicionar) {
            formAdicionar.addEventListener("submit", (event) => {
                if (!wsPronto()) return;
                event.preventDefault();
                const nome = document.getElementById("nome_aluno").value.trim();
                const opcao = document.getElementById("opcao_tipo").value;
                const data = document.getElementById("data_aula").value;
                enviarWs({
                    action: "adicionar_aula",
                    nome_aluno: nome,
                    opcao_tipo: opcao,
                    data_aula: data,
                });
                formAdicionar.reset();
            });
        }

        const formAlterar = document.getElementById("form-alterar");
        if (formAlterar) {
            formAlterar.addEventListener("submit", (event) => {
                if (!wsPronto()) return;
                event.preventDefault();
                enviarWs({
                    action: "alterar_aula",
                    indice: document.getElementById("indice").value,
                    novo_nome: document.getElementById("novo_nome").value,
                    nova_data: document.getElementById("nova_data").value,
                    nova_opcao: document.getElementById("nova_opcao").value,
                });
                document.getElementById("novo_nome").value = "";
                document.getElementById("nova_data").value = "";
                document.getElementById("nova_opcao").value = "";
            });
        }

        const formExcluir = document.getElementById("form-excluir");
        if (formExcluir) {
            formExcluir.addEventListener("submit", (event) => {
                if (!confirm("Tem certeza que deseja excluir esta aula?")) {
                    event.preventDefault();
                    return;
                }
                if (!wsPronto()) return;
                event.preventDefault();
                enviarWs({
                    action: "excluir_aula",
                    indice: document.getElementById("indice_excluir").value,
                });
            });
        }

        const formSalario = document.getElementById("form-salario");
        if (formSalario) {
            const radios = formSalario.querySelectorAll('input[name="tem_vt"]');
            radios.forEach((radio) => {
                radio.addEventListener("change", () => {
                    state.temVtSelecionado = radio.value;
                    if (wsPronto()) {
                        enviarWs({ action: "calcular_salario", tem_vt: radio.value });
                    } else {
                        formSalario.submit();
                    }
                });
            });

            formSalario.addEventListener("submit", (event) => {
                if (!wsPronto()) return;
                event.preventDefault();
                const checked = formSalario.querySelector('input[name="tem_vt"]:checked');
                const temVt = checked ? checked.value : "sim";
                state.temVtSelecionado = temVt;
                enviarWs({ action: "calcular_salario", tem_vt: temVt });
            });
        }

        const formFimMes = document.getElementById("form-fim-mes");
        if (formFimMes) {
            formFimMes.addEventListener("submit", (event) => {
                if (!confirm("Tem certeza que deseja finalizar o mês atual?")) {
                    event.preventDefault();
                    return;
                }
                if (!wsPronto()) return;
                event.preventDefault();
                enviarWs({ action: "finalizar_mes" });
            });
        }

        const formPerfil = document.getElementById("form-perfil-atualizar");
        if (formPerfil) {
            formPerfil.addEventListener("submit", (event) => {
                if (!wsPronto()) return;
                event.preventDefault();
                enviarWs({
                    action: "atualizar_perfil",
                    nome: document.getElementById("perfil_nome").value,
                    email: document.getElementById("perfil_email").value,
                    login: document.getElementById("perfil_login").value,
                    nova_senha: document.getElementById("perfil_nova_senha").value,
                });
                document.getElementById("perfil_nova_senha").value = "";
            });
        }

        const formsLinha = document.querySelectorAll(".form-excluir-linha");
        formsLinha.forEach((form) => {
            form.addEventListener("submit", (event) => {
                if (!confirm("Tem certeza que deseja excluir esta aula?")) {
                    event.preventDefault();
                    return;
                }
                if (!wsPronto()) return;
                event.preventDefault();
                const indiceInput = form.querySelector('input[name="indice"]');
                if (indiceInput) {
                    enviarWs({ action: "excluir_aula", indice: indiceInput.value });
                }
            });
        });
    }

    if (elFiltro) {
        elFiltro.addEventListener("input", () => {
            state.filtroTexto = elFiltro.value;
            if (state.lastPayload && Array.isArray(state.lastPayload.aulas)) {
                renderizarTabela(state.lastPayload.aulas);
            }
        });
    }

    configurarFormularios();
    conectarWebSocket();
})();
