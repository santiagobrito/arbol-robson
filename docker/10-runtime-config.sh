#!/bin/sh
# Configuracion en tiempo de arranque.
#
# La imagen de nginx ejecuta todo lo que encuentre en /docker-entrypoint.d/
# antes de levantar el servidor. Aqui se generan las dos cosas que dependen del
# entorno y no pueden estar horneadas en el build:
#
#   /tmp/runtime/htpasswd     credenciales de la autenticacion HTTP
#   /tmp/runtime/config.json  configuracion que lee el navegador
#
# Van a /tmp porque el contenedor corre como uid 101 y no puede escribir en
# /usr/share/nginx/html ni en /etc/nginx.

set -eu

RUNTIME_DIR=/tmp/runtime
mkdir -p "$RUNTIME_DIR"

# ---------- Autenticacion HTTP ----------
#
# Por defecto el sitio pide usuario y contrasena, y el contenedor se NIEGA a
# arrancar si falta: un despliegue mal configurado publicaria los datos de mas
# de mil personas vivas, y es preferible que no levante.
#
# PUBLIC_ACCESS=true desactiva la autenticacion. Es una decision deliberada, no
# un descuido: hace falta escribir la variable a mano. Lo que se publica asi
# sale de la mano de quien lo publica.

BASIC_AUTH_USER="${BASIC_AUTH_USER:-familia}"

is_true() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1 | true | yes | on) return 0 ;;
    *) return 1 ;;
  esac
}

if is_true "${PUBLIC_ACCESS:-}"; then
  echo 'auth_basic off;' > "$RUNTIME_DIR/auth.conf"
  rm -f "$RUNTIME_DIR/htpasswd"
  echo "[arbol] AVISO: PUBLIC_ACCESS=true. El sitio queda ABIERTO, sin contrasena." >&2
else
  if [ -z "${BASIC_AUTH_PASSWORD:-}" ]; then
    echo "[arbol] ERROR: falta la variable BASIC_AUTH_PASSWORD." >&2
    echo "[arbol] El arbol tiene datos de personas vivas y no se publica sin clave." >&2
    echo "[arbol] Para publicarlo abierto a proposito: PUBLIC_ACCESS=true." >&2
    exit 1
  fi

  # -m fuerza apr1 (MD5), soportado por nginx en cualquier libc. bcrypt depende
  # del crypt() del sistema y en musl no siempre esta.
  htpasswd -bcm "$RUNTIME_DIR/htpasswd" "$BASIC_AUTH_USER" "$BASIC_AUTH_PASSWORD" >/dev/null 2>&1
  chmod 600 "$RUNTIME_DIR/htpasswd"

  cat > "$RUNTIME_DIR/auth.conf" <<'AUTHEOF'
auth_basic "Arbol familiar";
auth_basic_user_file /tmp/runtime/htpasswd;
AUTHEOF
fi
chmod 644 "$RUNTIME_DIR/auth.conf"

# ---------- Configuracion del frontend ----------

# Escapa comillas y barras para no romper el JSON con un titulo cualquiera.
json_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

# Normaliza cualquier forma de "si" a true/false.
json_bool() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1 | true | yes | on) echo true ;;
    *) echo false ;;
  esac
}

SITE_TITLE="${SITE_TITLE:-Arbol familiar Robson}"
GEDCOM_FILE="${GEDCOM_FILE:-arbol-robson.ged}"
PRIVACY_MODE="$(json_bool "${PRIVACY_MODE:-true}")"
PRIVACY_HIDE_UNDATED="$(json_bool "${PRIVACY_HIDE_UNDATED:-false}")"
PRIVACY_BIRTH_YEAR_CUTOFF="${PRIVACY_BIRTH_YEAR_CUTOFF:-1930}"
DEFAULT_PERSON_ID="${DEFAULT_PERSON_ID:-}"
DEFAULT_GENERATIONS="${DEFAULT_GENERATIONS:-4}"
MAX_NODES="${MAX_NODES:-400}"

if [ -n "$DEFAULT_PERSON_ID" ]; then
  DEFAULT_PERSON_JSON="\"$(json_escape "$DEFAULT_PERSON_ID")\""
else
  DEFAULT_PERSON_JSON=null
fi

cat > "$RUNTIME_DIR/config.json" <<EOF
{
  "title": "$(json_escape "$SITE_TITLE")",
  "gedcomUrl": "/data/$(json_escape "$GEDCOM_FILE")",
  "privacyMode": $PRIVACY_MODE,
  "privacyBirthYearCutoff": $PRIVACY_BIRTH_YEAR_CUTOFF,
  "privacyHideUndated": $PRIVACY_HIDE_UNDATED,
  "defaultPersonId": $DEFAULT_PERSON_JSON,
  "defaultGenerations": $DEFAULT_GENERATIONS,
  "maxNodes": $MAX_NODES
}
EOF
chmod 644 "$RUNTIME_DIR/config.json"

if [ ! -f "/data/$GEDCOM_FILE" ]; then
  echo "[arbol] AVISO: no existe /data/$GEDCOM_FILE." >&2
  echo "[arbol] Comproba que el volumen esta montado en /data." >&2
fi

echo "[arbol] Listo. Usuario: $BASIC_AUTH_USER | GEDCOM: $GEDCOM_FILE | privacidad: $PRIVACY_MODE"
