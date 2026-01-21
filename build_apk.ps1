# Script para Gerar APK (Build)
# Este script configura o ambiente e inicia a compilação.

Write-Host "Configurando ambiente..." -ForegroundColor Cyan

# 1. Configurar Caminhos (PATH) temporariamente
$env:PATH += ";C:\src\flutter\bin"
$env:PATH += ";C:\Program Files\Git\cmd"
$env:PATH += ";C:\Users\Idenilson\AppData\Local\Android\Sdk\platform-tools"
$env:PATH += ";C:\Users\Idenilson\AppData\Local\Android\Sdk\cmdline-tools\latest\bin"

# 2. Configurar Variável ANDROID_HOME
$env:ANDROID_HOME = "C:\Users\Idenilson\AppData\Local\Android\Sdk"

# 2.1 Configurar JAVA_HOME (Microsoft OpenJDK 17)
$env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-17.0.17.10-hotspot"
$env:PATH += ";$env:JAVA_HOME\bin"

# 3. Verificar status do Flutter
Write-Host "Verificando Flutter..." -ForegroundColor Cyan
flutter doctor

# 4. Aceitar licenças (se necessário)
Write-Host "Verificando licenças do Android..." -ForegroundColor Cyan
# O comando abaixo tenta aceitar licenças automaticamente (Compatível com PowerShell)
1..30 | ForEach-Object { "y" } | flutter doctor --android-licenses

# 5. Iniciar Build
Write-Host "`nIniciando compilação do APK..." -ForegroundColor Green
Write-Host "Isso pode demorar 10-20 minutos na primeira vez. Aguarde..." -ForegroundColor Yellow

# Limpar build anterior para evitar erros de cache
if (Test-Path "build") {
    Write-Host "Limpando pasta build antiga..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue
}

flet build apk --project "Ponto2" --product "Ponto Eletronico" --org "com.ponto.app" --module-name main_mobile -v

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[SUCESSO] APK gerado com sucesso!" -ForegroundColor Green
    Write-Host "O arquivo está na pasta: build/apk/app-release.apk" -ForegroundColor Cyan
    Invoke-Item "build/apk"
} else {
    Write-Host "`n[ERRO] Falha na compilação." -ForegroundColor Red
}

Read-Host "Pressione ENTER para sair..."
