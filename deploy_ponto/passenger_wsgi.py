import os
import sys
from a2wsgi import ASGIMiddleware
from web_app import app

# Adiciona o diretório atual ao path para importar módulos corretamente
sys.path.insert(0, os.path.dirname(__file__))

# Define a variável de ambiente para subdiretório se necessário
# Isso ajuda o FastAPI a gerar URLs corretas quando rodando em /ponto ou /pacote_deploy
# O Passenger geralmente lida com isso, mas se precisar forçar:
# os.environ["ROOT_PATH"] = "/pacote_deploy"

# Converte a aplicação ASGI (FastAPI) para WSGI (Passenger/cPanel)
application = ASGIMiddleware(app)
