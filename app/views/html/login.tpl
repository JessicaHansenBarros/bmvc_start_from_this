<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portal do educador - Alfabeta</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400..900;1,400..900&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inder&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/login.css">
    <link rel="stylesheet" href="/static/css/header.css">
    <script src="/static/js/auth.js" defer></script>
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
        <form class="card-login" action="/portal" method="POST">
            % if defined('mensagem') and mensagem:
                <div class="alerta-login-sucesso">
                    {{ mensagem }}
                </div>
            % end

            % if defined('erro') and erro:
                <div class="alerta-login-erro">
                    {{ erro }}
                </div>
            % end

            <div class="campo-grupo">
                <label for="login">Login:</label>
                <input type="text" id="login" name="login" required autocomplete="username">
            </div>

            <div class="campo-grupo">
                <label for="senha">Senha:</label>
                <input type="password" id="senha" name="senha" required autocomplete="current-password">
            </div>

            <button type="submit" class="btn-logar">Logar</button>

            <p class="texto-cadastro">
                Novo aqui? <a href="/cadastro">Criar conta</a>
            </p>
        </form>
    </main>
    
</body>
</html>
