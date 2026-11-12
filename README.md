# Sistema de cobro y control de titulares

Sistema local y multiusuario para llevar un padrón de titulares, asignar a cada uno una matrícula única que sirve como referencia de pago y autorizar altas y bajas con tres vías de aprobación (bandeja, delegación temporal y código por teléfono). Todo se configura en un asistente de primer uso: vocabulario, plantilla, conceptos de cobro, roles y políticas. El repositorio no trae datos de ningún negocio.

La especificación está en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md). Este repositorio contiene la Fase 1.

## Requisitos

- Python 3.12 o posterior.
- Nada más: SQLite viene con Python y todas las dependencias están en `requirements.txt`.

## Instalación

### Windows (PowerShell)

```powershell
cd ruta\al\repositorio
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd sistema
python manage.py inicializar
python manage.py migrate
python manage.py servir
```

### Linux

```bash
cd ruta/al/repositorio
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd sistema
python manage.py inicializar
python manage.py migrate
python manage.py servir
```

`inicializar` crea la carpeta `instancia/` (fuera de git) con la clave de Django, la clave de matrícula de 32 bytes y la ruta de la base, e imprime un **token de instalación**. Guárdalo: el asistente lo pide en el primer paso. Si se pierde, `python manage.py inicializar --nuevo-token` genera otro. Nunca borres ni regeneres `instancia/configuracion.json` en una instalación con datos: la clave de matrícula no se puede recuperar.

Para usar otra carpeta de instancia, define la variable de entorno `COBRO_INSTANCIA` con su ruta.

## Primer uso

1. Abre `http://localhost:8000/` en el navegador del servidor. Te lleva al asistente.
2. Captura el token, el nombre del negocio, la plantilla (`escuela` o `generico`), los importes, el primer usuario de Dirección y activa su autenticador (cualquier app TOTP; la clave se muestra como texto y como enlace `otpauth://`).
3. Al terminar, ese navegador queda como el primer equipo aprobado.

Cada navegador nuevo queda **pendiente** y muestra un código; Supervisión o Dirección lo aprueba en *Equipos*. Desde la consola del servidor también se puede aprobar: `python manage.py aprobar_dispositivo CODIGO --nombre "Caja 1"`.

## HTTPS y red local

Por defecto las cookies llevan la marca `Secure`, así que fuera de `localhost` el sistema debe servirse con TLS (por ejemplo, Caddy delante de waitress; ver §3 y §10 de la arquitectura). Para probar en una red local sin TLS, crea la instancia con `python manage.py inicializar --sin-https`.

Los nombres de host aceptados y los orígenes de confianza se editan en `instancia/configuracion.json` (`hosts`, `origenes_confiables`). Para escuchar en la red: `python manage.py servir --host 0.0.0.0 --puerto 8000`.

## Demostración

En una instalación vacía (después de `migrate`):

```bash
python manage.py demostracion --contrasena "una-contrasena-larga"
```

Crea un negocio de demostración con la plantilla `escuela` y los usuarios `operacion`, `supervision` y `direccion`, e imprime los secretos de autenticador. Después aprueba tu navegador con `aprobar_dispositivo`.

## Pruebas

```bash
pip install -r requirements-pruebas.txt
python -m pytest
```

Se corren desde la raíz del repositorio. No necesitan `instancia/`.

## Comandos útiles

| Comando | Para qué |
|---|---|
| `inicializar` | Crea `instancia/` con claves aleatorias |
| `servir` | Servidor de producción (waitress) |
| `aprobar_dispositivo CODIGO` | Aprueba un equipo desde el servidor |
| `verificar_auditoria` | Verifica la cadena de hashes de la auditoría |
| `demostracion` | Configura una instalación de prueba |
