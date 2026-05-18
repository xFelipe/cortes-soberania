# vulture_whitelist.py — false positives para `python -m vulture src/ vulture_whitelist.py`
#
# Adicione aqui símbolos que vulture reporta como mortos mas são usados via
# introspecção, frameworks externos, ou protocolos implícitos.
#
# Formato aceito pelo vulture: qualquer expressão Python válida que referencie
# o símbolo (atribuição a _ é idiomático).

# Nenhum falso positivo no momento — parâmetros de protocolo renomeados com _ prefix.
