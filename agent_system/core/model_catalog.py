import os
import requests
from agent_system.core.settings_manager import AVAILABLE_MODELS
from agent_system.core.connectors.errors import failure


def catalog(provider):
    url={'groq':'https://api.groq.com/openai/v1/models','openrouter':'https://openrouter.ai/api/v1/models'}[provider]
    key=os.getenv('GROQ_API_KEY' if provider=='groq' else 'OPENROUTER_API_KEY')
    if not key and provider=='groq':raise ValueError('أضف مفتاح Groq إلى ملف .env ثم أعد تشغيل الخادم')
    try:
        response=requests.get(url,headers={'Authorization':'Bearer '+key} if key else {},timeout=15)
        if response.status_code!=200:raise ValueError(failure(provider,'catalog',response.status_code))
        return sorted({r['id'] for r in response.json()['data'] if r.get('id') and r.get('active',True)})
    except requests.RequestException:raise ValueError('تعذر جلب قائمة النماذج من المزود')


RETIRED_GROQ={'llama-3.3-70b-versatile':'openai/gpt-oss-120b','llama-3.1-8b-instant':'openai/gpt-oss-20b','qwen/qwen3-32b':'openai/gpt-oss-120b','gemma2-9b-it':'openai/gpt-oss-20b'}

def replacements(settings):
    result=[]
    for name,config in [('director',settings['director'])]+list(settings.get('workers',{}).items()):
        if config.get('provider')=='groq' and config.get('model') in RETIRED_GROQ:
            result.append({'role':name,'old':config['model'],'new':RETIRED_GROQ[config['model']]})
    return result
