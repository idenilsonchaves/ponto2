# Como Gerar o APK (Android)

Existem duas formas de gerar o APK do aplicativo:

## Opção 1: Usando GitHub Actions (Recomendado)
Esta opção é a mais fácil pois não exige instalar nada no seu computador.

1. Faça o upload deste projeto para um repositório no GitHub.
2. Vá na aba **Actions** do seu repositório.
3. Você verá o workflow "Build Android APK".
4. Se ele não rodar automaticamente, clique nele e depois em "Run workflow".
5. Quando terminar (pode levar uns 10-15 minutos), clique no workflow concluído.
6. Role até o final da página e baixe o artefato `app-release.apk`.

## Opção 2: Compilando Localmente (Avançado)
Você precisará ter o **Flutter** instalado e configurado no seu computador.

1. Instale o Flutter: https://flutter.dev/docs/get-started/install
2. Verifique se está tudo certo:
   ```bash
   flutter doctor
   ```
3. Instale as dependências do Python:
   ```bash
   pip install -r requirements.txt
   ```
4. Execute o comando de build:
   ```bash
   flet build apk --project-name "Ponto2" --product-name "Ponto Eletronico" --org "com.ponto.app"
   ```
5. O APK será gerado na pasta `build/apk/`.

## Observações Importantes para Mobile
- **Banco de Dados**: No Android, o banco de dados deve ser salvo em um local onde o app tenha permissão de escrita. O código atual tenta salvar na pasta do app, o que pode ser somente-leitura no Android. Recomenda-se ajustar o caminho do banco de dados para usar `page.client_storage` ou um caminho de sistema adequado se encontrar problemas de persistência.
