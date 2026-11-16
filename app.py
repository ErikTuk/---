import time
import streamlit as st
from ddgs import DDGS
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

GIGA_KEY = st.secrets["GIGA_KEY"]   # ключ берётся из секретов Space

st.set_page_config(page_title="Бот по охране труда", page_icon="🦺")
st.title("🦺 Ассистент по производственной безопасности")
st.caption("Ищет информацию в интернете и отвечает со ссылками на источники.")

TRUSTED = ("consultant.ru", "glavkniga.ru", "minzdrav.gov.ru",
           "rospotrebnadzor.ru", "mos.ru", "regulation.gov.ru",
           "vsr63.ru", "studfile.net")

SYSTEM_PROMPT = (
    "Ты — ассистент по охране труда и производственной безопасности. "
    "Отвечай на русском, кратко, по делу, на «вы». "
    "Начинай ответ с приветствия: «Привет! Вот ответ на твой вопрос:», "
    "затем давай сам ответ — конкретный и по существу. "
    "Используй только факты из КОНТЕКСТА ниже. "
    "Сохраняй конкретику: определения, сроки, номера пунктов, требования. "
    "Если в контексте мало информации или источники противоречат друг другу, "
    "честно об этом скажи и порекомендуй свериться с официальными документами "
    "(ТК РФ, приказы Минтруда). Не выдумывай номера приказов и сроки."
)

def web_search(query, max_results=5):
    hits = []
    for attempt in range(3):
        try:
            with DDGS() as d:
                results = d.text(query, region="ru-ru", max_results=max_results * 3)
            for r in results:
                if any(site in r.get("href", "") for site in TRUSTED):
                    hits.append({"title": r.get("title", ""),
                                 "url": r.get("href", ""),
                                 "body": r.get("body", "")})
                if len(hits) >= max_results:
                    break
            if hits:
                break
            time.sleep(3)
        except Exception as e:
            st.warning(f"Попытка {attempt + 1} поиска не удалась: {e}")
            time.sleep(3)
    return hits

def build_context(hits):
    return "\n\n".join(
        f"[Источник: {h['title']} — {h['url']}]\n{h['body']}" for h in hits
    )

@st.cache_resource
def get_giga():
    return GigaChat(
        credentials=GIGA_KEY,
        scope="GIGACHAT_API_PERS",
        verify_ssl_certs=False,
    )

def ask_giga(question, context):
    giga = get_giga()
    chat = Chat(
        messages=[
            Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
            Messages(role=MessagesRole.USER,
                     content=f"КОНТЕКСТ:\n{context}\n\nВОПРОС: {question}"),
        ],
        temperature=0.2,
        model="GigaChat-2",
    )
    resp = giga.chat(chat)
    return resp.choices[0].message.content

if "history" not in st.session_state:
    st.session_state.history = []

for role, text in st.session_state.history:
    with st.chat_message(role):
        st.markdown(text)

user_input = st.chat_input("Задайте вопрос по охране труда")
if user_input:
    st.session_state.history.append(("user", user_input))
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.spinner("Ищу информацию в интернете…"):
        query = f"охрана труда производственная безопасность {user_input}"
        hits = web_search(query)
    chunks = hits

    try:
        answer = ask_giga(user_input, build_context(chunks))
        sources = hits
    except Exception as e:
        err = str(e)[:300]
        if chunks:
            answer = ("Не удалось получить ответ от GigaChat (" + err + "). "
                      "Вот что нашлось в интернете:\n\n" + build_context(chunks))
        else:
            answer = ("Поиск не дал результатов, и GigaChat не ответил. "
                      "Причина: " + err)
        sources = []

    with st.chat_message("assistant"):
        st.markdown(answer)
        if sources:
            st.markdown("**Источники:**")
            for s in dict.fromkeys(s["url"] for s in sources):
                st.markdown(f"- [{s}]({s})")
    st.session_state.history.append(("assistant", answer))
