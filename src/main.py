from orquestrador import Orquestrador
from leitor_manual_pdf import LeitorManualPDF
from registrador import Registrador
from webscrapper import WebScrapper
from config import client

r = Registrador(client)
w = WebScrapper(client, r)
l = LeitorManualPDF(client)

orquestrador = Orquestrador(
    client=client,
    agents=[w, r, l]
)
orquestrador.run()