import asyncio
import sys
from unittest.mock import patch

# Parchear el envío de WhatsApp para que solo imprima en consola
async def mock_send_whatsapp_message(to_number: str, message_text: str):
    print("\n" + "="*50)
    print(f"🤖 [MENSAJE GENERADO POR LA IA PARA {to_number}]:")
    print("-" * 50)
    print(message_text)
    print("="*50 + "\n")
    return {"status": "mocked"}

async def run_test():
    print("Iniciando prueba de la IA y comunicación con el backend...")
    
    # Importamos primero el módulo para que esté cargado
    import app.agent.graph as graph
    
    # Parcheamos manualmente la función en el módulo importado
    graph.send_whatsapp_message = mock_send_whatsapp_message
    
    test_number = "+573000000000"
    while True:
        try:
            user_input = input("Tú (escribe 'salir' para terminar): ")
            if user_input.lower() in ['salir', 'exit', 'quit']:
                break
            
            print("Procesando... (la IA está pensando y consultando el backend si es necesario)")
            await graph.process_message(user_input, test_number)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error en la prueba: {e}")

if __name__ == "__main__":
    # Ejecuta el loop de asyncio
    asyncio.run(run_test())
