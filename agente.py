from agents import Agent, Runner

agent = Agent(
    name="Mi primer agente",
    instructions="Responde de forma clara, breve y profesional."
)

result = Runner.run_sync(
    agent,
    "Explícame qué es GitHub en tres puntos."
)

print(result.final_output)