# docencia-tools

`docencia-tools` separa la lógica docente reusable de la automatización propia de GitHub Actions. Su flujo es:

```text
configuración confiable → estado observado → lógica Python → resultado → publicación
```

La versión inicial valida el protocolo de un pull request, reconstruye el primer instante en que una entrega estuvo completa, clasifica fallos, ejecuta validaciones técnicas declarativas, construye asignaciones reproducibles de revisión y evalúa el ciclo revisión–réplica. Las labels se derivan del estado; nunca son su almacenamiento.

## Instalación para desarrollo

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

## Comandos

```bash
docencia-tools validar-config --config ruta/actividad.yml
docencia-tools dependencias --config ruta/actividad.yml --salida /tmp/requisitos.txt
docencia-tools validar-pr --config ruta/confiable.yml --evento evento.json --repo-head ruta/head --trusted-ref origin/main --salida estado.json
docencia-tools asignar --participantes participantes.yml --privada excepciones.yml --salida asignaciones.json
```

`validar-pr` espera que la configuración proceda de un checkout confiable. El árbol indicado mediante `--repo-head` se considera no confiable: primero se calcula el diff real desde `merge_base`, se validan rutas y archivos, y solo después se permite ejecutar código de la entrega.

## Alcance del MVP

No incluye base de datos, dashboards, IA, detección de plagio, calificación numérica ni merge automático. El estado se conserva como JSON versionado o como artefacto de GitHub Actions. La reconstrucción histórica basada únicamente en fechas de commits se marca como aproximada porque Git no registra el instante en que un commit llegó a GitHub.

La arquitectura, el contrato de configuración, la frontera de confianza y la estrategia de publicación están documentados en [`docs/arquitectura.md`](docs/arquitectura.md). Hay ejemplos públicos y privados sin datos reales en [`examples/`](examples/).
