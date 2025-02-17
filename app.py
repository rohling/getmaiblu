import os
import pickle
import base64
from datetime import datetime, timezone
from flask import Flask, request
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

app = Flask(__name__)

# Configuração para ambiente do Codespaces
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['SERVER_NAME'] = os.environ.get('CODESPACE_NAME') + '-8080.app.github.dev'

class ReverseProxied:
    def __init__(self, app):
        self.app = app
    def __call__(self, environ, start_response):
        environ['wsgi.url_scheme'] = 'https'
        return self.app(environ, start_response)

app.wsgi_app = ReverseProxied(app.wsgi_app)

# Configurações
CLIENT_SECRETS_FILE = './credentials.json'
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_FILE = './token.pickle'

# Configuração dinâmica do redirect_uri
if os.environ.get('CODESPACES') == 'true':
    codespace_name = os.environ['CODESPACE_NAME']
    REDIRECT_URI = f'https://{codespace_name}-8080.app.github.dev/callback'
else:
    REDIRECT_URI = 'https://localhost:8080/callback'

flow = Flow.from_client_secrets_file(
    client_secrets_file='./credentials.json',
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            auth_url, _ = flow.authorization_url(prompt='consent')
            print(f'URL de autorização: {auth_url}')
            return None
        
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('gmail', 'v1', credentials=creds)

def get_message_content(message):
    # Função para extrair o conteúdo do e-mail, seja ele texto plano ou HTML
    if 'parts' in message['payload']:
        parts = message['payload']['parts']
        for part in parts:
            if part['mimeType'] in ['text/plain', 'text/html']:
                if 'data' in part['body']:
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                elif 'attachmentId' in part['body']:
                    return '[Conteúdo do e-mail está em anexo]'
    elif 'body' in message['payload'] and 'data' in message['payload']['body']:
        return base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')
    return '[Não foi possível recuperar o conteúdo do e-mail]'

@app.route('/')
def index():
    service = get_gmail_service()
    if not service:
        return 'Autentique primeiro em <a href="/auth">/auth</a>'
    
    # Filtros
    start_date = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    end_date = int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    query = f'from:*@*voeazul* subject:"Reserva*" after:{start_date} before:{end_date}'
    
    results = service.users().messages().list(
        userId='me',
        maxResults=100,
        q=query
    ).execute()
    
    messages = results.get('messages', [])
    output = [f'<h1>E-mails contendo "voeazul" no domínio e assunto "Reserva" em 2025 ({len(messages)} encontrados):</h1>']
    
    for msg in messages:
        message = service.users().messages().get(
            userId='me', 
            id=msg['id'],
            format='full'
        ).execute()
        
        headers = {h['name']: h['value'] for h in message['payload']['headers']}
        content = get_message_content(message)
        
        output.append(f'''
            <div style="border: 1px solid #ccc; padding: 10px; margin: 10px;">
                <p><strong>De:</strong> {headers.get('From', 'Desconhecido')}</p>
                <p><strong>Assunto:</strong> {headers.get('Subject', 'Sem assunto')}</p>
                <p><strong>Data:</strong> {headers.get('Date', 'Data não disponível')}</p>
                <p><strong>ID:</strong> {msg['id']}</p>
                <hr>
                <div style="margin-top: 10px;">
                    <strong>Conteúdo do E-mail:</strong>
                    <div style="margin-top: 10px; white-space: pre-wrap;">{content}</div>
                </div>
            </div>
        ''')
    
    return '\n'.join(output)

@app.route('/auth')
def auth():
    auth_url, _ = flow.authorization_url(prompt='consent')
    return f'''
        <h1>Autenticação necessária</h1>
        <a href="{auth_url}">Clique aqui para autenticar com o Google</a>
        <p>Depois da autenticação, você será redirecionado de volta para o aplicativo</p>
    '''

@app.route('/callback')
def callback():
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    
    with open(TOKEN_FILE, 'wb') as token:
        pickle.dump(creds, token)
    
    return '''
        <h1>Autenticação bem-sucedida!</h1>
        <p>Você pode fechar esta janela e voltar ao aplicativo</p>
        <a href="/">Ver emails</a>
    '''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)