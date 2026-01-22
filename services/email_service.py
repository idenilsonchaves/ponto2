import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config.settings import config
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        pass

    def _get_config(self):
        return {
            "host": config.get("EMAIL", "smtp_host", "localhost"),
            "port": int(config.get("EMAIL", "smtp_port", "25")),
            "user": config.get("EMAIL", "smtp_user", ""),
            "password": config.get("EMAIL", "smtp_pass", ""),
            "enabled": config.get("EMAIL", "notify_enabled", "0") == "1"
        }

    def send_email(self, to_email: str, subject: str, body: str, is_html: bool = False) -> bool:
        conf = self._get_config()
        if not conf["enabled"] and "teste" not in subject.lower():
            logger.info("Envio de e-mail desabilitado nas configurações.")
            return False

        msg = MIMEMultipart()
        msg['From'] = conf["user"] or "noreply@ponto2.sistema"
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html' if is_html else 'plain'))

        try:
            server = smtplib.SMTP(conf["host"], conf["port"])
            if conf["user"] and conf["password"]:
                server.starttls()
                server.login(conf["user"], conf["password"])
            
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            logger.error(f"Erro ao enviar e-mail: {e}")
            return False

    def send_test_email(self, to_email: str) -> bool:
        return self.send_email(
            to_email, 
            "Teste de Configuração - Ponto2", 
            "<h1>Teste Bem-Sucedido!</h1><p>Suas configurações de e-mail estão funcionando corretamente.</p>",
            is_html=True
        )

email_service = EmailService()
