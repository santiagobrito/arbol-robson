# Árbol familiar Robson

Visor web del árbol genealógico familiar. Lee un archivo GEDCOM 5.5.1 y dibuja
un árbol interactivo navegable desde el celular. Sin backend ni base de datos:
todo se procesa en el navegador.

**El sitio no es público.** Está detrás de autenticación HTTP y trae un modo de
privacidad que oculta los datos de las personas presuntamente vivas.

---

## Qué hace

- Árbol interactivo con zoom, arrastre y pinza, pensado para pantalla de teléfono.
- Buscador por nombre o apellido, sin distinguir tildes ni mayúsculas.
- Ficha por persona: fechas y lugares de nacimiento y defunción, padres,
  hermanos, pareja con fecha de casamiento e hijos, todos enlazados.
- Tres vistas: descendientes, ascendientes y ambas (reloj de arena).
- Enlace permanente por persona: `https://.../#/I123`, para compartir por WhatsApp.

---

## Cómo está armado

| Pieza | Elección | Por qué |
|---|---|---|
| Dibujo del árbol | [Topola](https://github.com/PeWu/topola) 3.10 | Visor de GEDCOM, no editor de árboles. Trae las tres vistas ya hechas y devuelve la posición del nodo raíz, que es lo que permite centrar la vista en una persona. Mantenida (último release jun-2026). |
| Parseo del GEDCOM | `parse-gedcom`, vía Topola | No hay parser propio. Topola ya lo usa por dentro y expone `gedcomToJson()`, así que el árbol y la ficha comparten un único modelo de datos. |
| Build | Vite + TypeScript, sin framework | Es una sola pantalla. El bundle queda en ~58 kB comprimido, que en 4G se nota. |
| Servidor | nginx unprivileged en Docker | Estático. Corre como uid 101, nunca root. |

### La decisión que sostiene todo: nunca se dibujan las 2.789 personas

Un reloj de arena de 8 generaciones desde el ancestro común expandiría **2.778 de
las 2.789 personas** del archivo. Ningún navegador de teléfono sobrevive a eso en
SVG.

Antes de pasarle nada a Topola, `src/subtree.ts` extrae el subgrafo alrededor de
la persona enfocada: N generaciones hacia arriba y hacia abajo, con un tope duro
de nodos (`MAX_NODES`, 400 por defecto). La expansión va por generaciones
completas, para no dejar la mitad de los hermanos fuera del dibujo, y todo lo
que sale queda referencialmente consistente (Topola no comprueba las referencias
y falla con una colgada). El caso peor real, el patriarca a 8 generaciones,
queda en 316 nodos y la poda tarda 2 ms.

Cuando se recorta, aparece un aviso arriba y se sigue navegando tocando a alguien
del borde y eligiendo **Centrar el árbol aquí**.

---

## Privacidad

Tres capas, de más a menos importante:

### 1. Autenticación HTTP (la que de verdad protege)

nginx pide usuario y contraseña para **todo**: la web, el `config.json` y el
propio archivo `.ged`. Se configura por variables de entorno:

```
BASIC_AUTH_USER=familia
BASIC_AUTH_PASSWORD=<lo que elijas>
```

El contenedor **se niega a arrancar si falta `BASIC_AUTH_PASSWORD`**. Es a
propósito: un despliegue mal configurado publicaría los datos de más de mil
personas vivas, y es preferible que no levante.

Para cambiar la clave: cambiar la variable y reiniciar el servicio. No hace falta
reconstruir la imagen.

> Es una clave compartida para toda la familia: no hay usuarios individuales ni
> forma de revocarle el acceso a una sola persona. Para este uso alcanza, pero
> conviene saberlo. Y tiene que servirse por HTTPS (en EasyPanel lo resuelve
> Traefik con Let's Encrypt): en HTTP la clave viaja en claro.

### 2. Modo privacidad

Con `PRIVACY_MODE=true` (por defecto), de toda persona **sin defunción
registrada y nacida después de `PRIVACY_BIRTH_YEAR_CUTOFF`** (1930) se ocultan:

- fecha y lugar de nacimiento,
- notas,
- y la fecha de casamiento de sus matrimonios.

Queda visible sólo el nombre. En el archivo actual son **1.048 personas de 2.789**.

El filtro se aplica una sola vez, justo después de parsear y antes de construir
el buscador o dibujar nada, así que los datos ocultos no llegan al HTML por
ninguna vía.

**Lo que este modo NO hace:** el nombre y apellido completos siguen visibles,
porque sin ellos nadie puede encontrar a un familiar en el buscador. También
sigue visible la estructura de parentesco. Si eso es un problema, la respuesta
no es este filtro sino a quién le das la contraseña.

`PRIVACY_HIDE_UNDATED=true` extiende la protección a quienes no tienen ninguna
fecha (unas 795 personas más). Más seguro y más pobre; queda a tu criterio.

### 3. No indexable

`noindex` en la etiqueta meta, cabecera `X-Robots-Tag` en todas las respuestas y
un `robots.txt` que bloquea todo. De todos modos un buscador se choca primero
con el 401.

---

## Desplegar en EasyPanel

El servicio es una app normal con build por Dockerfile. **Nunca Nixpacks**: corre
como root y es la regla de este servidor desde el incidente de abril de 2026.

1. **Crear el servicio** (`services.app.createService`) y conectarlo al repo
   (`updateSourceGithub`). El repo va **privado**.

2. **Forzar el build por Dockerfile**:

   ```json
   {"projectName":"arbol","serviceName":"web","build":{"type":"dockerfile","file":"Dockerfile"}}
   ```

3. **Variables de entorno** (`updateEnv`, string con saltos de línea):

   ```
   BASIC_AUTH_USER=familia
   BASIC_AUTH_PASSWORD=<clave>
   SITE_TITLE=Arbol familiar Robson
   GEDCOM_FILE=arbol-robson.ged
   PRIVACY_MODE=true
   PRIVACY_BIRTH_YEAR_CUTOFF=1930
   DEFAULT_GENERATIONS=4
   MAX_NODES=400
   ```

4. **Montar el volumen** en `/data` (tipo *bind*, montaje `/data`). En el host
   queda en:

   ```
   /etc/easypanel/projects/<proyecto>/<servicio>/volumes/data
   ```

5. **Copiar el GEDCOM** al volumen (ver más abajo).

6. **Crear el dominio** (`domains.createDomain`) apuntando al **puerto 8080**.
   Sin dominio explícito, Traefik devuelve 404 aunque el contenedor esté vivo.

7. **Deploy** y comprobar:

   ```bash
   docker exec <container> whoami          # debe decir nginx, NUNCA root
   curl -o /dev/null -w '%{http_code}\n' https://<dominio>/          # 401
   curl -o /dev/null -w '%{http_code}\n' -u familia:<clave> https://<dominio>/   # 200
   ```

### Levantarlo fuera de EasyPanel

```bash
cp .env.example .env      # y poner BASIC_AUTH_PASSWORD
mkdir -p data && cp /ruta/al/arbol-robson.ged data/
docker compose up -d --build
# http://localhost:8080
```

---

## Actualizar el GEDCOM

El archivo vive en el volumen `/data`, **fuera de la imagen**. Reemplazarlo no
requiere reconstruir ni volver a desplegar nada.

1. **Comprobarlo antes de subirlo**, con el mismo parser que usa la web:

   ```bash
   npm run check:gedcom /ruta/al/nuevo.ged
   ```

   Tiene que reportar el número de personas y familias que esperás, `0` familias
   con referencias rotas y `0` sin nombre. Si dice 0 individuos, casi seguro es
   la codificación: el archivo tiene que ser UTF-8.

2. **Copiarlo al volumen**:

   ```bash
   scp nuevo.ged easypanel:/tmp/
   ssh easypanel 'sudo cp /tmp/nuevo.ged \
     /etc/easypanel/projects/<proyecto>/<servicio>/volumes/data/arbol-robson.ged'
   ```

3. **Listo.** El navegador lo pide con `Cache-Control: no-cache`, así que basta
   con recargar. No hace falta reiniciar el contenedor.

Si el archivo tiene otro nombre, cambiar la variable `GEDCOM_FILE` y reiniciar
el servicio (eso sí necesita reinicio, porque el `config.json` se genera al
arrancar).

> Los identificadores (`I123`) vienen del archivo. Si al regenerarlo cambian,
> **los enlaces compartidos dejan de apuntar a la persona correcta**. Al
> reexportar desde otro programa de genealogía, verificar que los IDs se
> conservan antes de reemplazar el archivo.

---

## Configuración

Todo se controla por variables de entorno. El script
`docker/10-runtime-config.sh` las convierte en un `/config.json` en cada
arranque, y la app lo lee al cargar. **Cambiar cualquiera de estas requiere
reiniciar el servicio, no reconstruir la imagen.**

| Variable | Por defecto | Qué hace |
|---|---|---|
| `BASIC_AUTH_USER` | `familia` | Usuario de la autenticación HTTP |
| `BASIC_AUTH_PASSWORD` | — | **Obligatoria.** Sin ella el contenedor no arranca |
| `SITE_TITLE` | `Arbol familiar Robson` | Título de la página |
| `GEDCOM_FILE` | `arbol-robson.ged` | Nombre del archivo dentro de `/data` |
| `DEFAULT_PERSON_ID` | (vacío) | Persona inicial. Vacío = la más antigua con descendencia |
| `PRIVACY_MODE` | `true` | Activa el filtro de privacidad |
| `PRIVACY_BIRTH_YEAR_CUTOFF` | `1930` | Nacidos después de este año se consideran vivos |
| `PRIVACY_HIDE_UNDATED` | `false` | Proteger también a quienes no tienen ninguna fecha |
| `DEFAULT_GENERATIONS` | `4` | Generaciones dibujadas por defecto |
| `MAX_NODES` | `400` | Tope de personas por dibujo. Subirlo penaliza al celular |

---

## Desarrollo

```bash
npm install
cp /ruta/al/arbol-robson.ged data/     # el .ged está gitignoreado
npm run dev                            # http://localhost:5173
```

En desarrollo no hay `config.json`: se usan los valores por defecto, que se
pueden pisar con variables `VITE_*` en un `.env.local` (`VITE_PRIVACY_MODE`,
`VITE_DEFAULT_PERSON_ID`, etc.).

```bash
npm run build          # typecheck + build a dist/
npm run check:gedcom   # valida el GEDCOM contra el parser real
```

### Mapa del código

```
src/
├── main.ts       arranque y cableado de la interfaz
├── config.ts     carga de /config.json con valores por defecto
├── privacy.ts    filtro de personas vivas -> índice del árbol
├── subtree.ts    poda por generaciones y tope de nodos  <- el archivo clave
├── chart.ts      Topola + zoom/arrastre con d3-zoom
├── details.ts    ficha de persona (DOM, nunca innerHTML)
├── search.ts     índice e búsqueda por nombre
├── router.ts     rutas en el hash (#/I123)
└── format.ts     nombres y fechas en castellano
```

---

## El archivo GEDCOM no está en el repositorio

Está en `.gitignore` a propósito. Tiene nombre completo y fecha de nacimiento de
más de mil personas vivas, y un commit deja ese dato en el historial para
siempre aunque después se borre el archivo. Se despliega copiándolo al volumen.

Si preferís versionarlo igual, descomentá las líneas de `data/*.ged` en el
`.gitignore` **y asegurate de que el repositorio esté en privado**:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.github.com/repos/<owner>/<repo>
# 200 = PÚBLICO. Debe dar 404.
```

---

## Comprobado

Con el archivo real (2.789 personas, 902 familias, UTF-8):

- Parseo: 117 ms. Sin referencias rotas, sin personas sin nombre.
- Poda: 0 referencias colgantes y 0 renders por encima del tope en 3.591
  extracciones (399 raíces × 3 vistas × 3 profundidades). Peor caso 2,2 ms.
- Privacidad: 1.048 personas protegidas, 0 fugas de datos sensibles.
- Contenedor: arranca como `nginx` (uid 101), no root. Se niega a arrancar sin
  contraseña. 401 sin credenciales en `/`, `/config.json` y `/data/*.ged`;
  `/healthz` y `/robots.txt` abiertos. Ningún path bajo `/data/` sirve archivos
  que no sean `.ged`. gzip activo (30 kB → 3,2 kB).
- Interfaz en Chrome de escritorio: enlaces permanentes, buscador, ficha,
  cambio de vista y modo privacidad.

**No comprobado:** la interfaz en un teléfono real. El diseño responsive y los
gestos táctiles están implementados pero sólo se validaron en escritorio.
