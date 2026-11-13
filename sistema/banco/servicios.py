from django.db import transaction

from auditoria.servicios import diferencias, registrar

from .models import Banco, CuentaBancaria


def foto_cuenta(cuenta):
    if cuenta is None or cuenta.pk is None:
        return {}
    return {
        "Banco": str(cuenta.banco),
        "CLABE": cuenta.clabe_formateada,
        "Beneficiario": cuenta.beneficiario,
        "Número de cuenta": cuenta.numero_cuenta or None,
        "Convenio": cuenta.convenio or None,
        "Medios aceptados": sorted(str(m) for m in cuenta.medios.all()),
        "Referencia": cuenta.get_referencia_en_display(),
        "Contacto para dudas": cuenta.contacto_dudas or None,
        "Nota adicional": cuenta.nota_adicional or None,
        "Principal": cuenta.principal,
        "Activa": cuenta.activa,
    }


def guardar_cuenta(formulario, usuario, cuenta=None, request=None, forzar_principal=False):
    datos = formulario.cleaned_data
    with transaction.atomic():
        antes = foto_cuenta(cuenta)
        banco = datos["banco"]
        if formulario.banco_nuevo is not None:
            banco, creado = Banco.objects.get_or_create(
                clave=formulario.banco_nuevo["clave"],
                defaults={"nombre": formulario.banco_nuevo["nombre"], "tipo": "otro", "soporte": "sin_probar", "capturado_a_mano": True},
            )
            if creado:
                registrar("banco_capturado_a_mano", usuario=usuario, objeto=banco, datos={"clave": banco.clave, "nombre": banco.nombre}, request=request)
        activa = True if forzar_principal else datos.get("activa", True)
        principal = True if forzar_principal else bool(datos.get("principal"))
        if activa and not CuentaBancaria.objects.filter(principal=True).exclude(pk=getattr(cuenta, "pk", None)).exists():
            principal = True
        if not activa:
            principal = False
        if principal:
            for otra in CuentaBancaria.objects.filter(principal=True).exclude(pk=getattr(cuenta, "pk", None)):
                otra.principal = False
                otra.save(update_fields=["principal"])
                registrar("cuenta_bancaria_cambiada", usuario=usuario, objeto=otra, datos={"cambios": {"Principal": [True, False]}}, request=request)
        nueva = cuenta is None
        cuenta = cuenta or CuentaBancaria()
        cuenta.banco = banco
        cuenta.clabe = datos["clabe"]
        cuenta.beneficiario = datos["beneficiario"].strip()
        cuenta.numero_cuenta = datos.get("numero_cuenta", "")
        cuenta.convenio = datos.get("convenio", "")
        cuenta.referencia_en = datos["referencia_en"]
        cuenta.contacto_dudas = datos.get("contacto_dudas", "")
        cuenta.nota_adicional = datos.get("nota_adicional", "").strip()
        cuenta.principal = principal
        cuenta.activa = activa
        cuenta.save()
        cuenta.medios.set(datos.get("medios") or [])
        cambios = diferencias(antes, foto_cuenta(cuenta))
        if nueva or cambios:
            registrar("cuenta_bancaria_creada" if nueva else "cuenta_bancaria_cambiada", usuario=usuario, objeto=cuenta, datos={"cambios": cambios}, request=request)
    return cuenta
