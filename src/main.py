from orquestrador import Orquestrador
from leitor_manual_pdf import LeitorManualPDF
from registrador import Registrador
from config import client

orquestrador = Orquestrador(
    client=client,
    agents=[
        LeitorManualPDF(client),
        Registrador(client)
    ]
)
orquestrador.run()