from orquestrador import Orquestrador
from leitor_manual_pdf import LeitorManualPDF
from registrador import Registrador
from webscrapper import WebScrapper
from config import client

r = Registrador(client)
# orquestrador = Orquestrador(
#     client=client,
#     agents=[
#         LeitorManualPDF(client),
#         r
#     ]
# )
# orquestrador.run()


w = WebScrapper(client, r)
w.send_message({
    'role':'user',
    'content':"""
        'modelo':'Corsa',
        'ano':2008,
        'motorizacao':'1.4',
        'fabricante':'Chevrolet'
    """
})
retorno = w.run()
# print(retorno)