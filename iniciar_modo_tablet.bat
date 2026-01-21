@echo off
echo Iniciando Servidor do Ponto Tablet...
echo.
echo Para acessar do Tablet, conecte no Wi-Fi e acesse:
echo http://192.168.1.143:8000
echo.
echo Pressione Ctrl+C para parar.
echo.
cd /d "%~dp0"
call .venv\Scripts\activate
flet run mobile_build\main.py --web --port 8000 --host 0.0.0.0
pause