// Tema antes da primeira pintura (spec 018, US1). Arquivo externo e bloqueante no <head>
// (script-src 'self': nada de script inline). O index.html já nasce com class="dark"
// (padrão escuro); aqui só se troca para claro quando o aparelho guardou "claro", ou
// "sistema" com o sistema claro. A mesma regra está em src/lib/tema.ts (mesma chave).
(function () {
  var tema = null;
  try {
    tema = window.localStorage.getItem("sociman:tema");
  } catch (e) {
    // localStorage bloqueado: fica o padrão escuro
  }
  var claro =
    tema === "claro" ||
    (tema === "sistema" && window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches);
  if (claro) {
    document.documentElement.classList.remove("dark");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", "#f0f2f5");
  }
})();
