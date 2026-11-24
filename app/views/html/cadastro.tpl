<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Criar Conta - Portal do Educador - Alfabeta</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400..900;1,400..900&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inder&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/login.css">
    <link rel="stylesheet" href="/static/css/header.css">
</head>
<body>

    <header>
        <section class="logo">
            <img src="/static/assets/imagens/logo alfabeta.png" alt="logo alfabeta">
        </section>
    </header>

    <section class="portal">
        <img src="/static/assets/imagens/Gemini_Generated_Image_n6afk8n6afk8n6af 1.png" alt="fundo site">
        <div class="banner-conteudo">
            <h1>Portal do educador</h1>
        </div>
    </section>

    <main class="container-login">
        <form class="card-login" action="/cadastro" method="POST">
            % if defined('erro') and erro:
                <div class="alerta-login-erro">
                    {{ erro }}
                </div>
            % end

            <div class="campo-grupo">
                <label for="nome">Nome completo:</label>
                <input type="text" id="nome" name="nome" required value="{{ nome if defined('nome') and nome else '' }}" autocomplete="name">
            </div>

            <div class="campo-grupo">
                <label for="email">E-mail:</label>
                <input type="email" id="email" name="email" required value="{{ email if defined('email') and email else '' }}" autocomplete="email">
            </div>

            <div class="campo-grupo">
                <label for="login">Login:</label>
                <input type="text" id="login" name="login" required value="{{ login if defined('login') and login else '' }}" autocomplete="username">
            </div>

            <div class="campo-grupo">
                <label for="senha">Senha:</label>
                <input type="password" id="senha" name="senha" required autocomplete="new-password">
            </div>

            <button type="submit" class="btn-logar">Criar Conta</button>

            <p class="texto-cadastro">
                Já possui conta? <a href="/portal">Fazer login</a>
            </p>
        </form>
    </main>

</body>
</html>
