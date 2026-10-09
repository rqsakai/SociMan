import { useState } from "react";

// Rascunho de formulário sobre um registro que muda sozinho (spec 012): enquanto o recorte e o flat
// rodam, o polling traz o produto com `version` nova a cada passo. Sem edição, o formulário segue o
// servidor. Com edição, ele fica como está; se só a versão mudou (os campos do formulário são os
// mesmos), o save usa a versão nova; se os campos mudaram fora daqui, o save manda a versão lida
// (409 `version_conflict`, com "Recarregar") e a tela avisa com `mudouFora`.
export function useRascunho<T>(servidor: T, version: number) {
  const json = JSON.stringify(servidor);
  const [valor, setValor] = useState<T>(servidor);
  const [base, setBase] = useState({ json, version });
  const [visto, setVisto] = useState({ json, version });
  const sujo = JSON.stringify(valor) !== base.json;

  // ajuste no render (padrão do React para estado derivado de props)
  if (visto.json !== json || visto.version !== version) {
    setVisto({ json, version });
    if (!sujo) {
      setValor(servidor);
      setBase({ json, version });
    } else if (json === base.json) {
      setBase({ json, version });
    }
  }

  return {
    valor,
    setValor,
    sujo,
    mudouFora: sujo && json !== base.json,
    versao: base.version,
    // depois do save (com o registro devolvido) ou para descartar: volta a seguir o servidor
    reiniciar: (novo: T, novaVersao: number) => {
      const j = JSON.stringify(novo);
      setValor(novo);
      setBase({ json: j, version: novaVersao });
      setVisto({ json: j, version: novaVersao });
    },
  };
}
