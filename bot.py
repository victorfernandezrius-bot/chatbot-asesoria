import os
TOKEN                 = os.environ.get("8442937473:AAGyQIdX2H8tAx3a4psW16PmDqFK9L0kdDU")
STRIPE_WEBHOOK_SECRET = os.environ.get("whsec_llllAQoZvXFqc5Zg3IIapTfEZNcMG9Jm")
SMTP_USER             = os.environ.get("victor@contabilidadpersonal.com")
SMTP_PASS             = os.environ.get("090594Victor!")
TU_CORREO             = os.environ.get("victor@contabilidadpersonal.com")
CALENDLY_LINK         = os.environ.get("https://calendly.com/victor-contabilidadpersonal/asesoria")
WEB_LINK_1            = os.environ.get("https://www.contabilidadpersonal.com/test-idoneidad")
import hmac
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from aiohttp import web
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes)


# ─── MENÚS ───────────────────────────────────────────────────
menu_asesoria = [["Básica", "Avanzada"], ["Avanzada +", "Premium"]]
menu_pago     = [["Mensual", "Anual"]]
markup_asesoria = ReplyKeyboardMarkup(menu_asesoria, resize_keyboard=True)
markup_pago     = ReplyKeyboardMarkup(menu_pago, one_time_keyboard=True)

links = {
    "Básica":     {"Anual": "https://buy.stripe.com/14k14NaG91935AA005"},
    "Avanzada":   {"Mensual": "https://buy.stripe.com/9AQ6p74hL1939QQ6ox",
                   "Anual":   "https://buy.stripe.com/8wM28R01v3hb9QQ5kq"},
    "Avanzada +": {"Mensual": "https://buy.stripe.com/28oaFn29D04Zd32fZ8",
                   "Anual":   "https://buy.stripe.com/cN2bJr5lPcRLe766ov"},
    "Premium":    {"Mensual": "https://buy.stripe.com/00gaFng0t2d76EEcMX",
                   "Anual":   "https://buy.stripe.com/7sI28R15zbNH4ww14c"},
}

# ─── ESTADO USUARIOS ─────────────────────────────────────────
# Clave: chat_id de Telegram  |  Valor: dict con asesoria, pago, email, nombre
usuarios = {}

# ─── ENVÍO DE CORREOS ────────────────────────────────────────
def enviar_correo(destinatario: str, asunto: str, cuerpo_html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"]    = SMTP_USER
    msg["To"]      = destinatario
    msg.attach(MIMEText(cuerpo_html, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, destinatario, msg.as_string())

def correo_cliente(nombre: str, email: str, asesoria: str, pago: str) -> str:
    return f"""
    <h2>¡Hola {nombre}! 👋</h2>
    <p>Tu pago de la asesoría <strong>{asesoria} ({pago})</strong> ha sido confirmado.</p>
    <h3>Próximos pasos:</h3>
    <p>👉 <a href="{CALENDLY_LINK}">Reserva tu sesión aquí</a></p>
    <hr>
    <h3>Recursos para empezar:</h3>
    <ul>
      <li><a href="{WEB_LINK_1}">Recurso 1</a></li>
      <li><a href="{WEB_LINK_2}">Recurso 2</a></li>
    </ul>
    <p>Cualquier duda, responde este correo. ¡Nos vemos pronto!</p>
    """

def correo_negocio(nombre: str, email: str, asesoria: str, pago: str) -> str:
    return f"""
    <h2>💰 Nuevo pago recibido</h2>
    <table>
      <tr><td><strong>Nombre:</strong></td><td>{nombre}</td></tr>
      <tr><td><strong>Email:</strong></td><td>{email}</td></tr>
      <tr><td><strong>Asesoría:</strong></td><td>{asesoria}</td></tr>
      <tr><td><strong>Plan:</strong></td><td>{pago}</td></tr>
    </table>
    """

# ─── HANDLERS DEL BOT ────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¿Qué tipo de asesoría quieres?",
        reply_markup=markup_asesoria
    )

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    texto   = update.message.text

    if user_id not in usuarios:
        usuarios[user_id] = {}

    estado = usuarios[user_id]

    # PASO 1: elegir asesoría
    if texto in links:
        estado["asesoria"] = texto
        await update.message.reply_text("¿Cómo quieres pagar?", reply_markup=markup_pago)

    # PASO 2: elegir tipo de pago
    elif texto in ["Mensual", "Anual"] and "asesoria" in estado:
        estado["pago"] = texto
        link = links[estado["asesoria"]][texto]
        await update.message.reply_text(
            f"Perfecto 👌\n\nRealiza el pago aquí:\n{link}\n\n"
            "Cuando termines, escribe /pagado para continuar."
        )

    # PASO 3: usuario dice que pagó (fallback manual, mientras no tienes webhook)
    elif texto == "/pagado" or texto.lower() in ["pagado", "ya pagué", "ya pague"]:
        await update.message.reply_text(
            "Verificando tu pago... ✅\n\n"
            "Por favor escribe tu **nombre completo**:"
        )
        estado["esperando"] = "nombre"

    # PASO 4: recoger nombre
    elif estado.get("esperando") == "nombre":
        estado["nombre"] = texto
        await update.message.reply_text("Ahora escribe tu **correo electrónico**:")
        estado["esperando"] = "email"

    # PASO 5: recoger email y completar flujo
    elif estado.get("esperando") == "email":
        estado["email"] = texto
        estado["esperando"] = None
        await completar_flujo(update, user_id)

    else:
        await update.message.reply_text("Selecciona una opción del menú o escribe /start.")

async def completar_flujo(update: Update, user_id: int):
    """Envía Calendly + correos al cliente y al negocio."""
    d = usuarios[user_id]
    nombre   = d.get("nombre", "Cliente")
    email    = d.get("email", "")
    asesoria = d.get("asesoria", "")
    pago     = d.get("pago", "")

    # Mensaje en Telegram con Calendly
    await update.message.reply_text(
        f"¡Todo listo, {nombre}! 🎉\n\n"
        f"👉 Elige tu fecha de sesión aquí:\n{CALENDLY_LINK}\n\n"
        "También te hemos enviado un correo con todos los detalles y recursos."
    )

    # Correo al cliente
    if email:
        try:
            enviar_correo(
                email,
                f"Confirmación de tu asesoría {asesoria}",
                correo_cliente(nombre, email, asesoria, pago)
            )
        except Exception as e:
            print(f"Error enviando correo al cliente: {e}")

    # Correo al negocio
    try:
        enviar_correo(
            TU_CORREO,
            f"Nuevo cliente: {nombre} – {asesoria} {pago}",
            correo_negocio(nombre, email, asesoria, pago)
        )
    except Exception as e:
        print(f"Error enviando correo al negocio: {e}")

# ─── WEBHOOK DE STRIPE ───────────────────────────────────────
# Stripe llamará a POST https://tu-servidor.com/stripe-webhook
async def stripe_webhook(request: web.Request):
    payload    = await request.read()
    sig_header = request.headers.get("Stripe-Signature", "")

    # Verificar firma de Stripe
    try:
        timestamp = sig_header.split("t=")[1].split(",")[0]
        sig       = sig_header.split("v1=")[1].split(",")[0]
        signed    = f"{timestamp}.{payload.decode()}"
        expected  = hmac.new(
            STRIPE_WEBHOOK_SECRET.encode(),
            signed.encode(),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return web.Response(status=400, text="Invalid signature")
    except Exception:
        return web.Response(status=400, text="Signature error")

    event = await request.json()

    # Solo procesamos pagos completados
    if event.get("type") == "checkout.session.completed":
        session  = event["data"]["object"]
        email    = session.get("customer_details", {}).get("email", "")
        nombre   = session.get("customer_details", {}).get("name", "Cliente")
        metadata = session.get("metadata", {})           # puedes pasar chat_id aquí desde Stripe
        chat_id  = metadata.get("telegram_chat_id")

        if chat_id:
            chat_id = int(chat_id)
            if chat_id not in usuarios:
                usuarios[chat_id] = {}
            usuarios[chat_id]["nombre"] = nombre
            usuarios[chat_id]["email"]  = email

            # Notificar al usuario en Telegram
            app_bot = request.app["bot_app"]
            await app_bot.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ ¡Pago confirmado, {nombre}!\n\n"
                    f"👉 Reserva tu sesión aquí:\n{CALENDLY_LINK}\n\n"
                    "También te enviamos un correo con todos los detalles."
                )
            )

            # Enviar correos
            asesoria = usuarios[chat_id].get("asesoria", "")
            pago     = usuarios[chat_id].get("pago", "")
            enviar_correo(email, f"Confirmación {asesoria}", correo_cliente(nombre, email, asesoria, pago))
            enviar_correo(TU_CORREO, f"Nuevo cliente: {nombre}", correo_negocio(nombre, email, asesoria, pago))

    return web.Response(status=200, text="OK")

# ─── ARRANQUE ────────────────────────────────────────────────
def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    # Servidor web para el webhook de Stripe (corre en paralelo)
    stripe_app = web.Application()
    stripe_app["bot_app"] = application
    stripe_app.router.add_post("/stripe-webhook", stripe_webhook)

    # Iniciar ambos (bot polling + servidor HTTP)
    import asyncio
    async def run_all():
        runner = web.AppRunner(stripe_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8080)
        await site.start()
        print("Webhook Stripe escuchando en :8080/stripe-webhook")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        print("Bot Telegram funcionando")
        await asyncio.Event().wait()  # mantener vivo

    asyncio.run(run_all())

if __name__ == "__main__":
    main()
