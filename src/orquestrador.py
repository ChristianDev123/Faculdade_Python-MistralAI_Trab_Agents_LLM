import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from interfaces.message import Message
from interfaces.agent import Agent
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from interfaces.json_format import createJsonFormat
import json
load_dotenv()

class Orquestrador(Agent):
    def __init__(self, client:OpenAI, model=None, agents:list[Agent] = []):
        super().__init__('conversacional',client, model)
        self.agents = agents
        self.json_format_orquestrador = createJsonFormat('descisao_orquestrador',[
            {'name':'pensamento', 'type':'string'},
            {'name':'acao', 'type':'string', 'enum':["RESPONDER_USUARIO", "CHAMAR_SUBAGENTE"]},
            {'name':'conteudo', 'type':'string'},
            {'name':'subagente_destino', 'type':'string', 'enum':['LEITOR_MANUAL_PDF', 'CONVERSACIONAL']},
        ])

        self.json_format_leitura_manual = createJsonFormat('envio_dados_leitor_manual',[
            {'name':'modelo', 'type':'string'},
            {'name':'ano', 'type':'integer'},
            {'name':'motorizacao', 'type':'string'},
            {'name':'duvida', 'type':'string'},
        ])

    def run(self):        
        self.send_message(Message('system', self.read_system_prompts('orquestrador_system_prompt.md')))
        
        resposta_inicial = self.get_answer(response_format=self.json_format_orquestrador)
        sys_message = json.loads(resposta_inicial.content)
        print(f"Bot: {sys_message['conteudo']}")

        self.send_message(Message('assistant', resposta_inicial.content))

        contador_passos = 0
        max_passos = 5

        while contador_passos < max_passos:
            contador_passos += 1
            user_input = input('user: ').strip()
            if not user_input: 
                break
                
            self.send_message(Message('user', user_input))
            
            resposta_orquestrador = self.get_answer(response_format=self.json_format_orquestrador)
            sys_message = json.loads(resposta_orquestrador.content)
            
            self.send_message(Message('assistant', resposta_orquestrador.content))

            if sys_message['acao'] == 'RESPONDER_USUARIO':
                print(f"Bot: {sys_message['conteudo']}")

            elif sys_message['acao'] == 'CHAMAR_SUBAGENTE':
                agent = list(filter(lambda x: str(sys_message['subagente_destino']).lower() == x.name, self.agents))[0]
                
                print(f"\n[Orquestrador] Acionando subagente: {agent.name}")
                
                arquivos_disponiveis = agent.tool_calls_func_link['get_pdf_filename']()
                
                # 1. Busca robusta: Extrai apenas números de 4 dígitos (ex: 2015, 2020) ignorando pontuações como "?"
                import re
                anos_encontrados = re.findall(r'\b\d{4}\b', user_input)
                arquivo_escolhido = None
                
                if anos_encontrados:
                    # Se achou um ano na pergunta, busca o PDF correspondente
                    arquivo_escolhido = next((arq for arq in arquivos_disponiveis if anos_encontrados[0] in arq), None)
                
                # 2. Fallback: Se não tem ano, busca por palavras-chave com mais de 3 letras (ex: jetta, fox)
                if not arquivo_escolhido:
                    palavras = [p.strip('?!.,') for p in user_input.lower().split() if len(p.strip('?!.,')) >= 3]
                    arquivo_escolhido = next((arq for arq in arquivos_disponiveis if any(p in arq.lower() for p in palavras)), None)
                
                # 3. Fallback de segurança absoluto
                if not arquivo_escolhido and arquivos_disponiveis:
                    arquivo_escolhido = arquivos_disponiveis[0]
                    
                print(f"[Orquestrador] Arquivo selecionado: {arquivo_escolhido}")

                # Executa a leitura
                resultado_leitura = agent.tool_calls_func_link['read_pdf_pages'](
                    namefile=arquivo_escolhido, 
                    duvida_usuario=user_input
                )
                
                # 4. Injeta o resultado como se fosse o usuário entregando os dados (Role: 'user')
                instrucao_forcada = (
                    f"Os dados do arquivo '{arquivo_escolhido}' foram recuperados:\n"
                    f"--- INÍCIO DO CONTEÚDO DO MANUAL ---\n"
                    f"{resultado_leitura['trechos_encontrados']}\n"
                    f"--- FIM DO CONTEÚDO DO MANUAL ---\n\n"
                    f"REGRA CRÍTICA: Responda à dúvida do usuário baseando-se APENAS no texto contido entre as tags INÍCIO e FIM acima. "
                    f"Se o texto acima estiver em branco ou não contiver a resposta exata, você deve obrigatoriamente responder: 'O manual não especifica essa informação'. "
                    f"Não invente dados. Selecione 'acao' como 'RESPONDER_USUARIO' e escreva a resposta no campo 'conteudo'."
                    )
                self.send_message(Message('user', instrucao_forcada))
                
                # 5. Pede a resposta final ao orquestrador
                resposta_final = self.get_answer(response_format=self.json_format_orquestrador)
                dados_resposta = json.loads(resposta_final.content)
                
                # Remove a instrucao_forcada da memória para não poluir as próximas perguntas
                self.messages.pop() 
                
                # Salva a resposta do bot no histórico
                self.send_message(Message('assistant', resposta_final.content))
                
                # Extrai o conteúdo. Se o modelo teimar e devolver vazio, avisa no terminal.
                texto_final = dados_resposta.get('conteudo', '')
                if not texto_final:
                    print(f"\n[DEBUG - O modelo ignorou a regra]: {resposta_final.content}\n")
                else:
                    print(f"Bot: {texto_final}")
