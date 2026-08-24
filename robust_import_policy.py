from __future__ import annotations

import app as core
import robust_import_runtime as robust


_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Un archivo de 20 MB crece ~33 % al viajar como base64. El límite HTTP debe
    # contemplar ese sobrecosto para no rechazar un archivo que el parser sí acepta.
    core.MAX_BODY_BYTES = max(int(getattr(core, "MAX_BODY_BYTES", 0) or 0), 32 * 1024 * 1024)

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

    robust._ALIAS_TO_CANONICAL = {
        robust._normalize_header(alias): canonical
        for canonical, aliases in robust.HEADER_ALIASES.items()
        for alias in aliases
        if robust._normalize_header(alias)
    }
    _INSTALLED = True
