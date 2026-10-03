from agents import Agent, Runner

agent = Agent(
    name="Mi primer agente",
    instructions="""
    Responde de forma clara, breve y profesional.
    Ayuda especialmente con GitHub, Git, Python y agentes de inteligencia artificial.
    Mantén el contexto de la conversación.
    """
)

historial = []

print("Agente iniciado.")
print("Escribe 'salir' para terminar.\n")

while True:
    mensaje = input("Tú: ")

    if mensaje.lower() == "salir":
        print("Agente: Hasta luego.")
        break

    historial.append({
        "role": "user",
        "content": mensaje
    })

    resultado = Runner.run_sync(
        agent,
        historial
    )

    respuesta = resultado.final_output

    historial.append({
        "role": "assistant",
        "content": respuesta
    })

    print(f"\nAgente: {respuesta}\n")