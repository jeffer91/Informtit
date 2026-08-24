from __future__ import annotations

import robust_import_runtime as robust


_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Los reportes antiguos no siempre contienen correo institucional o código
    # de carrera. Esos campos ayudan a clasificar, pero no deben impedir leer la
    # base. Si luego no se puede separar Presencial/Online, la validación de
    # población bloqueará el guardado en lugar de inventar datos.
    robust.REQUIRED_CANONICAL = {"identification", "full_name", "career_name"}

    robust.HEADER_ALIASES["identification"].update(
        {"documentoidentidad", "identificacionestudiante", "cedulaestudiante"}
    )
    robust.HEADER_ALIASES["full_name"].update(
        {"estudiantenombre", "nombreyapellido", "nombresyapellidos"}
    )
    robust.HEADER_ALIASES["career_name"].update(
        {"carreraestudiante", "nombreprogramaacademico", "ofertaacademica"}
    )
    robust.HEADER_ALIASES["career_code"].update(
        {"codigoprogramaacademico", "codigodelprograma"}
    )
    robust.HEADER_ALIASES["email"].update(
        {"correoestudiante", "emailestudiante", "mailestudiante"}
    )

    # Regenera el índice de alias después de ampliar el catálogo.
    robust._ALIAS_TO_CANONICAL = {
        robust._normalize_header(alias): canonical
        for canonical, aliases in robust.HEADER_ALIASES.items()
        for alias in aliases
        if robust._normalize_header(alias)
    }
    _INSTALLED = True
