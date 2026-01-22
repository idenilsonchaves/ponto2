import os
import shutil
import zipfile
import configparser

def prepare_deploy():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    deploy_dir = os.path.join(base_dir, "deploy_ponto")
    
    # 1. Clean previous deploy dir
    if os.path.exists(deploy_dir):
        shutil.rmtree(deploy_dir)
    os.makedirs(deploy_dir)
    
    print(f"Criando pacote de deploy em: {deploy_dir}")
    
    # 2. Files to copy
    files_to_copy = [
        "web_app.py",
        "requirements.txt",
        "config.ini",
        "passenger_wsgi.py",
        "README_DEPLOY.txt"
    ]
    
    for f in files_to_copy:
        src = os.path.join(base_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(deploy_dir, f))
            print(f"Copiado: {f}")
            
    # 3. Directories to copy
    dirs_to_copy = [
        "templates",
        "static",
        "services",
        "database",
        "models",
        "utils",
        "ui" # In case it's used
    ]
    
    for d in dirs_to_copy:
        src = os.path.join(base_dir, d)
        dst = os.path.join(deploy_dir, d)
        if os.path.exists(src):
            shutil.copytree(src, dst)
            print(f"Copiado diretório: {d}")

    # 4. Handle Config directory separately (to exclude backups/reports)
    config_src = os.path.join(base_dir, "config")
    config_dst = os.path.join(deploy_dir, "config")
    os.makedirs(config_dst, exist_ok=True)
    
    # Copy all files in config
    for item in os.listdir(config_src):
        s = os.path.join(config_src, item)
        d = os.path.join(config_dst, item)
        
        # Skip pycache
        if "__pycache__" in item:
            continue
            
        if os.path.isfile(s):
            shutil.copy2(s, d)
            print(f"Copiado config: {item}")
        elif os.path.isdir(s) and item not in ["backups", "relatorios"]:
            # Copy other subdirs if any
            shutil.copytree(s, d)
            print(f"Copiado config subdir: {item}")
            
    # Explicitly check for database.db in config if not copied
    db_src = os.path.join(config_src, "database.db")
    db_dst = os.path.join(config_dst, "database.db")
    if os.path.exists(db_src) and not os.path.exists(db_dst):
        shutil.copy2(db_src, db_dst)
        print("Copiado explicitamente: config/database.db")
    
    # Also check root database.db if config one doesn't exist
    if not os.path.exists(db_dst):
        root_db = os.path.join(base_dir, "database.db")
        if os.path.exists(root_db):
            shutil.copy2(root_db, db_dst)
            print("Copiado do root para config: database.db")

    # 5. Create empty directories for structure
    os.makedirs(os.path.join(deploy_dir, "backups"), exist_ok=True)
    os.makedirs(os.path.join(deploy_dir, "relatorios"), exist_ok=True)
    
    # 6. Update config.ini for relative paths
    config_path = os.path.join(deploy_dir, "config.ini")
    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')
    
    if "DATABASE" not in config:
        config["DATABASE"] = {}
        
    # Set relative paths
    config["DATABASE"]["path"] = "config/database.db"
    config["DATABASE"]["backup_dir"] = "backups"
    
    # Set production defaults if needed
    if "EMAIL" in config:
        if config["EMAIL"].get("smtp_host") == "localhost":
             # Keep as is, or maybe warn user
             pass
             
    with open(config_path, 'w', encoding='utf-8') as f:
        config.write(f)
    print("Atualizado config.ini para caminhos relativos.")
    
    # 7. Create ZIP
    zip_filename = os.path.join(base_dir, "pacote_deploy.zip")
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(deploy_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, deploy_dir)
                zipf.write(file_path, arcname)
                
    print(f"\nSUCESSO! Arquivo gerado: {zip_filename}")
    print("Conteúdo pronto para upload.")

if __name__ == "__main__":
    prepare_deploy()
