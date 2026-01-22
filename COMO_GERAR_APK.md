# Como ter o Aplicativo no Celular

Como seu sistema é **Web (Online)**, existem duas formas de transformá-lo em App:

## Opção 1: PWA (Mais Fácil e Recomendada)
Seu site já está configurado como um **Progressive Web App (PWA)**.
Isso significa que ele pode ser instalado sem precisar da loja de aplicativos.

1. Acesse o site no navegador do celular (Chrome no Android ou Safari no iPhone).
2. Toque no menu (três pontinhos ou botão de compartilhar).
3. Escolha **"Adicionar à Tela Inicial"** ou **"Instalar Aplicativo"**.
4. Pronto! Ele vai aparecer como um App nativo no seu celular.

---

## Opção 2: Gerar APK via GitHub (Avançado)
Você perguntou se pode gerar um APK pelo Git. **Sim, é possível**, mas com uma ressalva importante:

### ⚠️ O Problema do APK "Offline"
O arquivo `build_apk.yml` que existe no seu Git hoje gera um aplicativo baseado no código `main_mobile.py`.
Este aplicativo é **OFFLINE**. Ele cria um banco de dados novo dentro do celular e **NÃO conversa** com o seu site na UOL Host.
Se você usar esse APK, os pontos batidos nele **não aparecerão** no site.

### ✅ Como gerar um APK que abre o Site (Launcher)
Se você quer um arquivo `.apk` real que apenas abre o seu site (como se fosse um navegador exclusivo):

1. Você precisa de um projeto "Wrapper" (como Bubblewrap ou WebView).
2. O código atual do repositório (`main_mobile.py`) teria que ser substituído por uma lógica que apenas carrega a URL do seu site.

**Minha sugestão:** Use a **Opção 1 (PWA)**. É tecnologia moderna, funciona igual a um app, não precisa pagar conta de desenvolvedor na Google Play e atualiza automaticamente quando você muda o site.
