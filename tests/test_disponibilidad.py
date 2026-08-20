# tests/test_disponibilidad.py — Verificación manual de disponibilidad
# Generado por AgentKit

"""
Script de línea de comandos para consultar disponibilidad real contra el
calendario, sin pasar por WhatsApp. Útil para confirmar que el conteo del
agente coincide con lo que se ve en Google Calendar antes de conectar el
webhook de verdad.

Uso:
    python tests/test_disponibilidad.py C6 2026-09-12 2026-09-13
"""

import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import calendar_service


def main():
    if len(sys.argv) != 4:
        print("Uso: python tests/test_disponibilidad.py PREFIJO FECHA_ENTRADA FECHA_SALIDA")
        print("Ejemplo: python tests/test_disponibilidad.py C6 2026-09-12 2026-09-13")
        sys.exit(1)

    prefijo, fecha_entrada_str, fecha_salida_str = sys.argv[1:4]
    fecha_entrada = date.fromisoformat(fecha_entrada_str)
    fecha_salida = date.fromisoformat(fecha_salida_str)

    resultado = calendar_service.verificar_disponibilidad(prefijo, fecha_entrada, fecha_salida)

    print()
    print(f"Recurso:  {prefijo}")
    print(f"Rango:    {fecha_entrada} a {fecha_salida}")
    if resultado.get("razon") == "evento_exclusivo":
        print("Resultado: NO DISPONIBLE (hay un evento exclusivo ese rango)")
    else:
        print(f"Ocupados: {resultado['ocupados']} de {resultado['capacidad']}")
        print(f"Resultado: {'DISPONIBLE' if resultado['disponible'] else 'NO DISPONIBLE'}")
    print()


if __name__ == "__main__":
    main()
