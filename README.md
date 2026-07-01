# Buscador de empleo diario — ventas médicas (Baja California)

Cada día a las **8:00am hora de Tijuana**, GitHub Actions busca vacantes nuevas de
representante/visitador médico y ventas farmacéuticas en Baja California, filtra las
que piden más de 1 año de experiencia, descarta las que ya viste y te manda un correo
con solo las nuevas y su link directo para aplicar.

No requiere que tu Mac esté prendida. Todo corre gratis en GitHub.

## Puesta en marcha (una sola vez, ~10 min)

### 1. Llaves de Adzuna (gratis)
1. Entra a https://developer.adzuna.com/ y crea una cuenta.
2. Copia tu **Application ID** y **Application Key**.

### 2. App Password de Gmail
1. Activa la verificación en 2 pasos en tu cuenta Google.
2. Ve a https://myaccount.google.com/apppasswords y genera una contraseña de aplicación
   (16 caracteres). Es distinta a tu contraseña normal. Esto permite que el script se
   mande correos **a ti mismo**; no da acceso a nadie más a tu bandeja.

### 3. Subir el proyecto a GitHub
```bash
git init
git add .
git commit -m "buscador de empleo"
git branch -M main
git remote add origin https://github.com/byospl1/buscador-empleo.git
git push -u origin main
```

### 4. Guardar los secretos
En el repo → **Settings → Secrets and variables → Actions → New repository secret**.
Crea estos cuatro:

| Nombre                | Valor                              |
|-----------------------|------------------------------------|
| `ADZUNA_APP_ID`       | tu Application ID                  |
| `ADZUNA_APP_KEY`      | tu Application Key                 |
| `GMAIL_USER`          | tu correo (ej. hugo@gmail.com)     |
| `GMAIL_APP_PASSWORD`  | la contraseña de aplicación de 16  |

### 5. Probarlo ya
Pestaña **Actions → Buscador de empleo diario → Run workflow**. Para que mande el
correo sin esperar a las 8am, agrega temporalmente `FORZAR: "1"` en el bloque `env`
del workflow, o córrelo con el botón y revisa el log.

## Ajustes rápidos (en `buscar_empleo.py`)
- `PUESTOS`: agrega o quita términos de búsqueda.
- `UBICACIONES`: ciudades a cubrir.
- `MAX_DIAS`: antigüedad máxima de las vacantes.
- `PATRONES_EXCLUIR`: reglas del filtro de experiencia.

## Cuando encuentres trabajo
Desactiva el workflow en **Actions → ··· → Disable workflow**, o borra el repo.

## Límite honesto
Adzuna agrega muchos portales pero no todos (Computrabajo y OCC a veces no aparecen).
El filtro de experiencia es heurístico: lee el texto de la vacante buscando "2 años",
"mínimo 3", etc. Alguna se puede colar; por eso el correo te muestra la descripción
para que decidas antes de aplicar.
