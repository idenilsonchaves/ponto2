# Como Instalar o Flutter no Windows

Para gerar o APK do seu aplicativo localmente, você precisa do Flutter instalado.

## Opção 1: Instalação Automática (Recomendada)
Se você tem o Windows 10 ou 11, pode usar o gerenciador de pacotes oficial.

1. Abra o **PowerShell** como Administrador.
2. Digite o seguinte comando e aperte Enter:
   ```powershell
   winget install Google.Flutter
   ```
3. Aceite os termos se for solicitado.
4. Feche e abra o terminal novamente para atualizar o caminho.

## Opção 2: Instalação Manual (Site Oficial)
1. Baixe o Flutter SDK: [https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.19.0-stable.zip](https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.19.0-stable.zip)
2. Extraia o arquivo zip para uma pasta, por exemplo: `C:\src\flutter` (não instale em "Arquivos de Programas").
3. Adicione o caminho `C:\src\flutter\bin` às variáveis de ambiente do Windows (PATH).

## Passos Pós-Instalação (Importante)

Após instalar, você precisa verificar se está tudo certo:

1. Abra um novo terminal.
2. Digite:
   ```bash
   flutter doctor
   ```
3. O comando vai te dizer o que falta. Geralmente você precisará:
   - Instalar o **Android Studio**.
   - Aceitar as licenças do Android (`flutter doctor --android-licenses`).

## Gerando o APK
Depois de tudo configurado e sem erros no `flutter doctor`, volte para a pasta deste projeto e rode:

```bash
flet build apk --project-name "Ponto2" --product-name "Ponto Eletronico" --org "com.ponto.app"
```
