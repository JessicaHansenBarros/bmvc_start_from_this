(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", () => {
        const passwordInputs = document.querySelectorAll('input[type="password"]');
        passwordInputs.forEach((input) => {
            const wrapper = document.createElement("div");
            wrapper.className = "senha-wrapper";
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);

            const toggleBtn = document.createElement("button");
            toggleBtn.type = "button";
            toggleBtn.className = "btn-toggle-senha";
            toggleBtn.textContent = "Mostrar";
            toggleBtn.setAttribute("aria-label", "Alternar visibilidade da senha");

            toggleBtn.addEventListener("click", () => {
                const oculto = input.type === "password";
                input.type = oculto ? "text" : "password";
                toggleBtn.textContent = oculto ? "Ocultar" : "Mostrar";
            });

            wrapper.appendChild(toggleBtn);
        });

        const form = document.querySelector(".card-login");
        if (form) {
            form.addEventListener("submit", () => {
                const submitBtn = form.querySelector(".btn-logar");
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.textContent = "Processando...";
                }
            });
        }
    });
})();
