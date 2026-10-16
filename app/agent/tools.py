from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain.tools import tool
from ..services.spring_client import get_spring_client
import logging

logger = logging.getLogger(__name__)


class SearchPropertiesInput(BaseModel):
    tipo_operacion: Optional[Literal["ARRIENDO", "VENTA"]] = Field(
        default=None,
        description=(
            "ARRIENDO si el usuario quiere arrendar/alquilar, VENTA si quiere "
            "comprar. Deja vacío si no lo menciona."
        ),
    )
    ciudad: Optional[str] = Field(
        default=None,
        description="Ciudad o municipio que el usuario pide (ej: 'Bogotá', 'Medellín'), si la menciona.",
    )
    habitaciones_min: Optional[int] = Field(
        default=None,
        description="Número mínimo de habitaciones que pide el usuario, si lo menciona.",
    )
    tipo_propiedad: Optional[str] = Field(
        default=None,
        description=(
            "Tipo de inmueble que pide el usuario, por ejemplo: apartamento, "
            "casa, conjunto residencial, oficina, local, bodega, finca, lote. "
            "Deja vacío si el usuario no lo menciona."
        ),
    )
    zona_o_caracteristicas: Optional[str] = Field(
        default=None,
        description=(
            "Palabras sobre barrio o características que el usuario haya "
            "mencionado (ej: 'teusaquillo', 'piscina', 'ascensor', 'vigilancia'). "
            "Deja vacío si no aplica."
        ),
    )
    precio_min: Optional[float] = Field(
        default=None,
        description="Precio mínimo en pesos colombianos (COP), si el usuario lo menciona. Ej: '1.5 millones' → 1500000.",
    )
    precio_max: Optional[float] = Field(
        default=None,
        description=(
            "Precio máximo en pesos colombianos (COP), si el usuario da un presupuesto. "
            "Ej: 'hasta 3 millones' → 3000000; 'máximo 400 millones' → 400000000. "
            "En arriendo es el canon mensual."
        ),
    )


class PropertyDetailInput(BaseModel):
    propiedad_id: int = Field(
        description="ID de la propiedad, tal como aparece como [ID n] en el resultado de search_properties."
    )


@tool("search_properties", args_schema=SearchPropertiesInput)
async def search_properties(
    tipo_operacion: Optional[str] = None,
    ciudad: Optional[str] = None,
    habitaciones_min: Optional[int] = None,
    tipo_propiedad: Optional[str] = None,
    zona_o_caracteristicas: Optional[str] = None,
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
) -> str:
    """Busca propiedades inmobiliarias disponibles según los criterios que el usuario haya mencionado."""
    logger.info(
        "Tool search_properties llamado con tipo_operacion=%r, ciudad=%r, habitaciones_min=%r, "
        "tipo_propiedad=%r, zona_o_caracteristicas=%r, precio_min=%r, precio_max=%r",
        tipo_operacion,
        ciudad,
        habitaciones_min,
        tipo_propiedad,
        zona_o_caracteristicas,
        precio_min,
        precio_max,
    )
    client = get_spring_client()
    try:
        data = await client.get_properties_compact(
            tipo_operacion=tipo_operacion,
            ciudad=ciudad,
            habitaciones_min=habitaciones_min,
            tipo_propiedad=tipo_propiedad,
            zona_o_caracteristicas=zona_o_caracteristicas,
            precio_min=precio_min,
            precio_max=precio_max,
        )
        return data if data else "No se encontraron propiedades con esos criterios."
    except Exception as e:
        logger.error(f"Error buscando propiedades: {e}")
        return "Hubo un error al consultar las propiedades disponibles."


@tool("get_property_detail", args_schema=PropertyDetailInput)
async def get_property_detail(propiedad_id: int) -> str:
    """Obtiene el detalle de una propiedad (resumen, precio, zonas comunes y contacto) cuando el usuario pide más información de una propiedad listada."""
    logger.info("Tool get_property_detail llamado con propiedad_id=%r", propiedad_id)
    client = get_spring_client()
    try:
        return await client.get_property_detail(propiedad_id)
    except Exception as e:
        logger.error(f"Error obteniendo detalle de propiedad: {e}")
        return "Hubo un error al consultar el detalle de la propiedad."
