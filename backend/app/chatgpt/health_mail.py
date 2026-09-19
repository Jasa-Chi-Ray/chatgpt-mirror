"""TLS-only mail transport. Provider responses and passwords must not be logged."""
import imaplib
import smtplib
import ssl
from email.message import EmailMessage
from django.template.loader import render_to_string


class MailDeliveryError(Exception):
    pass


def send_notification(config, subject, text, *, details=None):
    message = EmailMessage()
    message["From"] = config.smtp_username
    message["To"] = config.recipient
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(render_to_string("chatgpt/health_notification.html", {
        "subject": subject,
        "heading": "账号状态异常" if details else "邮件服务测试",
        "summary": "复检后仍未恢复，请检查此账号的登录凭据或连接状态。" if details else text,
        "details": details or [],
    }), subtype="html")
    context = ssl.create_default_context()
    try:
        if config.smtp_security == "ssl":
            client = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15, context=context)
        elif config.smtp_security == "starttls":
            client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)
        else:
            raise MailDeliveryError("SMTP 必须使用 SSL/TLS 或 STARTTLS")
        with client:
            if config.smtp_security == "starttls":
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            client.login(config.smtp_username, config.smtp_password)
            if client.send_message(message):
                raise MailDeliveryError("收件地址被邮件服务器拒绝")
    except smtplib.SMTPAuthenticationError:
        raise MailDeliveryError("SMTP 认证失败，请重新填写授权码") from None
    except MailDeliveryError:
        raise
    except Exception:
        raise MailDeliveryError("SMTP 发送失败，请检查连接、TLS、发件权限及收件地址") from None


def test_imap(config):
    client = None
    try:
        context = ssl.create_default_context()
        if config.imap_security == "ssl":
            client = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, ssl_context=context, timeout=15)
        elif config.imap_security == "starttls":
            client = imaplib.IMAP4(config.imap_host, config.imap_port, timeout=15)
            client.starttls(ssl_context=context)
        else:
            raise MailDeliveryError("IMAP 必须使用 SSL/TLS 或 STARTTLS")
        client.login(config.imap_username, config.imap_password)
    except Exception:
        raise MailDeliveryError("IMAP 连接或认证失败，请检查服务器、TLS 和授权码") from None
    finally:
        if client:
            try:
                client.logout()
            except Exception:
                pass
