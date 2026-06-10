#!/usr/bin/env python3
"""
CM4000 Notifier — Módulo de Notificaciones Asíncronas
======================================================
Expone una única API pública: dispatch_alert_async(subject, body)

Despacha en paralelo notificaciones por Telegram y Email usando hilos
daemon en modo fire-and-forget. Nunca bloquea el hilo del SCADA.

Credenciales exclusivamente desde variables de entorno (archivo .env).
"""

import os
import logging
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

log = logging.getLogger("CM4000-Notifier")

# ─────────────────────────────────────────────────────────────
# Lectura de credenciales desde variables de entorno
# ─────────────────────────────────────────────────────────────

# — Telegram —
_TG_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# — Email (SMTP) —
_SMTP_HOST     = os.environ.get("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT     = int(os.environ.get("SMTP_PORT", "587"))
_SMTP_USER     = os.environ.get("SMTP_USER", "")
_SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
# EMAIL_FROM cae back al usuario SMTP si no se define explícitamente
_EMAIL_FROM    = os.environ.get("EMAIL_FROM", "") or _SMTP_USER
# Soporta tanto EMAIL_TO (genérico) como NOTIFY_EMAIL_TO (nombre del .env del proyecto)
_EMAIL_TO      = os.environ.get("EMAIL_TO", "") or os.environ.get("NOTIFY_EMAIL_TO", "")


# ─────────────────────────────────────────────────────────────
# Backends privados
# ─────────────────────────────────────────────────────────────

def _send_telegram(subject: str, body: str) -> None:
    """Envía un mensaje de Telegram al chat configurado. Silencia errores."""
    if not _TG_TOKEN or not _TG_CHAT_ID:
        log.debug("Telegram no configurado — omitiendo.")
        return

    # Texto plano: evita errores 400 por caracteres especiales de Markdown
    # (guiones bajos en nombres de alarma, paréntesis, etc.)
    text = f"{subject}\n\n{body}"
    url  = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": _TG_CHAT_ID,
        "text":    text,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.ok:
            log.info(f"✈️  Telegram enviado: {subject}")
        else:
            log.warning(f"Telegram respondió {resp.status_code}: {resp.text[:120]}")
    except Exception as exc:
        log.error(f"❌ Error enviando Telegram: {exc}")


def _send_email(subject: str, body: str) -> None:
    """Envía un email via SMTP TLS. Silencia errores para no bloquear el SCADA."""
    if not _SMTP_USER or not _SMTP_PASSWORD or not _EMAIL_TO:
        log.debug(f"Email SMTP no configurado — omitiendo. USER={bool(_SMTP_USER)} PASS={bool(_SMTP_PASSWORD)} TO={bool(_EMAIL_TO)}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = _EMAIL_FROM
    msg["To"]      = _EMAIL_TO
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(_SMTP_USER, _SMTP_PASSWORD)
            server.sendmail(_EMAIL_FROM, _EMAIL_TO.split(","), msg.as_string())
        log.info(f"📧 Email enviado: {subject}")
    except Exception as exc:
        log.error(f"❌ Error enviando Email: {exc}")


# ─────────────────────────────────────────────────────────────
# API Pública
# ─────────────────────────────────────────────────────────────

def dispatch_alert_async(subject: str, body: str) -> None:
    """
    Despacha las notificaciones de Telegram y Email en hilos daemon
    independientes (fire-and-forget). Retorna inmediatamente sin bloquear
    el hilo del SCADA.

    Args:
        subject: Asunto/título del mensaje (p. ej. "🚨 ALARMA ACTIVA: FP_Bajo").
        body:    Cuerpo detallado del mensaje.
    """
    for target, name in [(_send_telegram, "telegram"), (_send_email, "email")]:
        t = threading.Thread(
            target=target,
            args=(subject, body),
            name=f"notifier-{name}",
            daemon=True,
        )
        t.start()
