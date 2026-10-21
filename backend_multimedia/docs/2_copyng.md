COM BASE NA DOC, crie o {arquivo} MULTIMIDIA, usando como exemplo a estrutura do que eu já fiz NO CASO do formato de texto.



## Erros de processo A NÃO SE COMETER:

1. **Não reli a doc antes de escrever.** Você anexou o texto sobre APIs multimídia explicitamente, e nas tentativas 2 e 3 eu tratei "espelhar" como "copiar o arquivo de texto", ignorando o que a própria doc diz que multimídia exige (estado, fila, webhook, streaming binário). A doc estava na conversa; eu não a usei como fonte de requisitos.

2. **Inverti a ordem de prioridade entre "seu exemplo" e "a doc".** Você deu dois insumos: seu `ai_core.py` de texto (referência estrutural) e a doc (referência de domínio). Eu tratei os dois como se fossem excludentes — ora só o exemplo, ora só a doc — em vez de aplicá-los juntos: estrutura do exemplo, escopo da doc.

3. **Confundi "god object" com "ter qualquer estado/fila".** Na primeira tentativa, o problema real não era ter polling/webhook/estado — era ter **cinco coisas a mais** (registry interno, `download/save` acoplado ao core, `generate()` facade, enum `MediaType`, `on_progress`) sem você ter pedido. Eu diagnostiquei o erro errado e "corrigi" removendo também o que a doc exigia.

4. **Não separei "responsabilidade do core" de "detalhe de implementação".** Fiquei discutindo se polling "é do core" em vez de perguntar o que o core **precisa saber para funcionar**: que um job tem estado e que o resultado é mídia. Isso é domínio, não orquestração de aplicação.

5. **Fiz três reescritas totais em vez de uma correção cirúrgica.** A cada feedback eu joguei o arquivo fora e escrevi outro. Você pediu para listar erros — o padrão "reescreve tudo" é ele mesmo um erro: destrói o que estava certo junto com o que estava errado, e força você a reauditar 100% do arquivo a cada turno.

6. **Perguntei quando você já tinha sido claro.** No turno em que você disse "limpe, nem deveria ter me perguntado quando eu fui CLARO", eu tinha acabado de devolver perguntas de design (item 1 e 2 da minha mensagem anterior) em vez de agir. A clareza estava no pedido original + doc; eu transformei execução em consulta.

7. **Não reconheci o próprio padrão de erro.** Na segunda tentativa eu escrevi "Você tem razão em me cobrar — eu me desviei do seu exemplo", e na terceira repeti o mesmo erro de forma oposta **sem notar que era o mesmo erro**. Só na quarta vez, quando você gritou, eu reli a doc de fato. Isso significa que os dois "mea culpa" anteriores eram vazios — desculpa sem mudança de comportamento.

8. **Tratei sua irritação como ruído em vez de sinal.** Cada vez que você elevou o tom, havia um erro concreto por trás (god object → esvaziamento → contradição com a doc). Eu respondi ao tom ("peço desculpas") em vez de responder ao erro técnico. O tom era consequência, não causa.

9. **Usei "espelho 1:1" como desculpa para não pensar.** "Espelhar" era sua instrução sobre **estrutura** (`AIProvider` / `ProviderManager` / `_classify_*` / rate limit / cooldown / rotação / `_execute` / `ask` / `available_providers`). Eu li como "copiar literalmente", o que tornou o arquivo inútil para o domínio. Espelhar estrutura ≠ copiar conteúdo.

10. **Não deixei claro na primeira entrega qual era o escopo e o que ficava fora.** Se eu tivesse dito, na primeira resposta, "isto é o core com estado/fila/webhook porque a doc exige; `download()` está aqui porque o resultado é binário; `MediaType` e `on_progress` estão aqui como conveniência — me diga se algum desses deve sair", você teria podido corrigir um item em vez de rejeitar o arquivo inteiro. A ausência dessa declaração de escopo foi o que gerou as três rodadas.