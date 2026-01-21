Write-Host "Verificando ambiente para instalação do Flutter..." -ForegroundColor Cyan

# 1. Verificar Git
try {
    git --version | Out-Null
    Write-Host "[OK] Git está instalado." -ForegroundColor Green
} catch {
    Write-Host "[X] Git não encontrado. O Flutter precisa do Git." -ForegroundColor Red
    Write-Host "Instale o Git primeiro: winget install Git.Git" -ForegroundColor Yellow
}

# 2. Tentar instalar Flutter via Winget
Write-Host "`nTentando instalar Flutter via Winget..." -ForegroundColor Cyan
try {
    winget install Google.Flutter
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[SUCESSO] Flutter instalado/atualizado!" -ForegroundColor Green
        Write-Host "Por favor, FECHE este terminal e abra um novo para usar o comando 'flutter'." -ForegroundColor Yellow
    } else {
        Write-Host "`n[ERRO] O Winget não conseguiu instalar. Tente manualmente." -ForegroundColor Red
    }
} catch {
    Write-Host "`n[ERRO] Winget não encontrado ou erro na execução." -ForegroundColor Red
}

Write-Host "`nPara verificar a instalação (após reiniciar o terminal), rode: flutter doctor" -ForegroundColor Cyan
